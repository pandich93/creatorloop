"""Temporary public URL for local files: local HTTP server + Cloudflare Quick Tunnel.

Instagram's publishing API downloads media from a public URL. Instead of uploading slides to a
third-party host, we expose a temp folder for a minute via `cloudflared tunnel --url` (no account,
random *.trycloudflare.com host) and shut everything down right after Meta has fetched the files.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


class TunnelError(RuntimeError):
    pass


def _fallback_candidates(platform: str, *, home: Path, env: Mapping[str, str]) -> list[Path]:
    """Usual install locations, for when PATH lacks them (Claude Desktop started from Dock / Start menu)."""
    if platform == "win32":
        local = env.get("LOCALAPPDATA", "")
        winget_pkgs = Path(local) / "Microsoft" / "WinGet" / "Packages"
        return [
            Path(local) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
            Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "cloudflared" / "cloudflared.exe",
            Path(env.get("ProgramFiles", r"C:\Program Files")) / "cloudflared" / "cloudflared.exe",
            *(Path(p) for p in glob.glob(str(winget_pkgs / "Cloudflare.cloudflared*" / "*.exe"))),
        ]
    dirs = ["/opt/homebrew/bin", "/usr/local/bin"] if platform == "darwin" else ["/usr/local/bin", "/usr/bin"]
    return [*(Path(d) / "cloudflared" for d in dirs), home / ".local" / "bin" / "cloudflared"]


def install_hint(platform: str = sys.platform) -> str:
    if platform == "win32":
        how = "`winget install --id Cloudflare.cloudflared -e`"
    elif platform == "darwin":
        how = "`brew install cloudflared`"
    else:
        how = "the package from https://pkg.cloudflare.com/index.html (or your distro's package manager)"
    return f"cloudflared not found. Install it once: {how} (or set CLOUDFLARED_PATH in .env), then restart the server."


def find_cloudflared() -> str | None:
    if env := os.getenv("CLOUDFLARED_PATH"):
        return env if Path(env).exists() else None
    if found := shutil.which("cloudflared"):
        return found
    for c in _fallback_candidates(sys.platform, home=Path.home(), env=os.environ):
        if c.exists():
            return str(c)
    return None


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        log.debug("tunnel http: " + format, *args)


class PublicTunnel:
    """async with PublicTunnel(folder) as base_url: ...  -> files are at f"{base_url}/{name}"."""

    def __init__(self, directory: Path, *, cloudflared: str | None = None, timeout: float = 45.0) -> None:
        self.directory = directory
        self.cloudflared = cloudflared or find_cloudflared()
        self.timeout = timeout
        self._server: ThreadingHTTPServer | None = None
        self._proc: subprocess.Popen | None = None
        self.url: str | None = None
        self.locally_reachable = True

    async def __aenter__(self) -> str:
        return await self.start()

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def start(self) -> str:
        if not self.cloudflared:
            raise TunnelError(install_hint())
        handler = functools.partial(_QuietHandler, directory=str(self.directory))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

        # stdin/stdout must NOT be inherited: they are the MCP stdio channel
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [self.cloudflared, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        found: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        loop = asyncio.get_running_loop()

        def pump() -> None:
            # read cloudflared logs until exit; keeps the pipe drained so the process never blocks
            assert self._proc and self._proc.stderr
            for line in self._proc.stderr:
                if not found.done() and (m := URL_RE.search(line)):
                    loop.call_soon_threadsafe(found.set_result, m.group(0))
            if not found.done():
                loop.call_soon_threadsafe(found.set_exception, TunnelError("cloudflared exited before giving a URL"))

        threading.Thread(target=pump, daemon=True).start()
        try:
            self.url = await asyncio.wait_for(found, timeout=self.timeout)
            await self._wait_reachable()
        except BaseException:
            await self.stop()
            raise
        log.info("Tunnel up: %s -> %s", self.url, self.directory)
        return self.url

    async def _wait_reachable(self) -> None:
        """New trycloudflare hosts need a few seconds before DNS/edge serve them."""
        probe = next((p.name for p in sorted(self.directory.iterdir()) if p.is_file()), None)
        if probe is None:
            return
        deadline = asyncio.get_running_loop().time() + self.timeout
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                with contextlib.suppress(httpx.HTTPError):
                    r = await client.get(f"{self.url}/{probe}")
                    if r.status_code == 200:
                        return
                if asyncio.get_running_loop().time() > deadline:
                    # Often only the local resolver lags behind for a fresh *.trycloudflare.com host while
                    # Meta's fetchers already see it. Continue; if Meta can't fetch, the container reports ERROR.
                    log.warning("Tunnel %s not reachable from this machine after %.0fs; continuing", self.url, self.timeout)
                    self.locally_reachable = False
                    return
                await asyncio.sleep(2)

    async def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                await asyncio.to_thread(self._proc.wait, 10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        log.info("Tunnel closed")
