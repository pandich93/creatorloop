"""Add the "creatorloop" MCP server to the Claude Desktop config (keeps all other settings).

Usage (from the project folder, on Windows, macOS or Linux):
    uv run creatorloop-setup [--config PATH] [--no-restart]

Claude Desktop rewrites its config from memory while it runs, so the config is only written while
Desktop is closed: on macOS this command quits and reopens it, elsewhere it asks you to quit it first.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from creatorloop import DISCLAIMER, paths

CONFIG_NAME = "claude_desktop_config.json"
MAC_APP_BINARY = "Claude.app/Contents/MacOS/Claude$"
QUIT_TIMEOUT_S = 30


def config_candidates(platform: str, *, home: Path, env: Mapping[str, str]) -> list[Path]:
    """Where Claude Desktop keeps its config on this OS, most usual location first."""
    if platform == "win32":
        candidates = [Path(env.get("APPDATA", home / "AppData" / "Roaming")) / "Claude" / CONFIG_NAME]
        # Microsoft Store (MSIX) build keeps a virtualised copy of %APPDATA%
        if local := env.get("LOCALAPPDATA"):
            for pkg in sorted((Path(local) / "Packages").glob("Claude_*")):
                candidates.append(pkg / "LocalCache" / "Roaming" / "Claude" / CONFIG_NAME)
        return candidates
    if platform == "darwin":
        return [home / "Library" / "Application Support" / "Claude" / CONFIG_NAME]
    return [Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "Claude" / CONFIG_NAME]


def pick_targets(candidates: list[Path]) -> list[Path]:
    """Every config that already exists; if none does, the first (default) location."""
    return [p for p in candidates if p.exists()] or candidates[:1]


def find_uv() -> str | None:
    if found := shutil.which("uv"):
        return found
    # Claude Desktop does not inherit the shell PATH: we need an absolute path anyway
    exe = "uv.exe" if sys.platform == "win32" else "uv"
    for d in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        if (d / exe).exists():
            return str(d / exe)
    return None


def server_entry(*, uv: str, source: Path | None) -> dict:
    """How Claude Desktop starts the server: from this source checkout, or the published package (= uvx)."""
    if source is not None:
        return {"command": uv, "args": ["--directory", str(source), "run", "creatorloop"]}
    return {"command": uv, "args": ["tool", "run", "creatorloop"]}


def install(config_path: Path, *, entry: dict) -> Path | None:
    """Write the server entry; return the backup path (None when the config did not exist)."""
    backup = None
    config: dict = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8-sig")  # tolerate a BOM left by Windows editors
        if raw.strip():
            try:
                config = json.loads(raw)
            except json.JSONDecodeError as e:
                sys.exit(f"{config_path} is not valid JSON ({e}). Fix it or move it away, then run again.")
        backup = config_path.with_name(f"{config_path.name}.backup-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(config_path, backup)

    servers = config.get("mcpServers") or {}
    servers["creatorloop"] = entry
    config["mcpServers"] = servers

    config_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 without BOM: Claude Desktop fails to parse a BOM-prefixed file
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.loads(config_path.read_text(encoding="utf-8"))  # validate
    return backup


def is_desktop_running(platform: str) -> bool:
    if platform == "darwin":
        cmd = ["pgrep", "-f", MAC_APP_BINARY]
    elif platform == "win32":
        cmd = ["tasklist", "/FI", "IMAGENAME eq Claude.exe", "/NH"]
    else:
        cmd = ["pgrep", "-x", "claude-desktop|Claude"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    if platform == "win32":
        return "claude.exe" in res.stdout.lower()
    return res.returncode == 0


def quit_desktop(timeout: float = QUIT_TIMEOUT_S) -> bool:
    """macOS only: the same graceful quit as Claude -> Quit; True once the process is gone."""
    subprocess.run(["osascript", "-e", 'quit app "Claude"'], capture_output=True, check=False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_desktop_running("darwin"):
            return True
        time.sleep(1)
    return False


def launch_desktop() -> None:
    subprocess.run(["open", "-a", "Claude"], check=False)


def close_desktop_if_running(platform: str, *, restart: bool) -> bool:
    """Desktop rewrites the config from memory while running, so it must be closed first.

    Returns True when we quit it and should start it again afterwards.
    """
    if not is_desktop_running(platform):
        return False
    if platform == "darwin" and restart:
        print("Claude Desktop is running: quitting it so it does not overwrite the config...")
        if not quit_desktop():
            sys.exit(f"Claude Desktop did not quit within {QUIT_TIMEOUT_S} s; nothing was written. Quit it and run again.")
        return True
    hint = " (or run without --no-restart to let this command do it)" if platform == "darwin" else ""
    sys.exit(
        "Claude Desktop is running and would overwrite the config with its own copy. "
        f"Quit it (tray / menu bar -> Quit), then run this command again{hint}."
    )


def main(argv: list[str] | None = None, platform: str = sys.platform) -> None:
    ap = argparse.ArgumentParser(description=__doc__, epilog=DISCLAIMER, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, help=f"path to {CONFIG_NAME} (default: auto-detect)")
    ap.add_argument("--no-restart", action="store_true", help="macOS: do not quit and reopen a running Claude Desktop")
    args = ap.parse_args(argv)

    uv = find_uv()
    if not uv:
        sys.exit("uv not found. Install it first: https://docs.astral.sh/uv/getting-started/installation/")
    targets = [args.config] if args.config else pick_targets(config_candidates(platform, home=Path.home(), env=os.environ))

    source = paths.source_root()
    entry = server_entry(uv=uv, source=source)

    relaunch = close_desktop_if_running(platform, restart=not args.no_restart)
    for path in targets:
        backup = install(path, entry=entry)
        if backup:
            print(f"Backup: {backup}")
        print(f"OK: 'creatorloop' server written to {path}")

    home = paths.home_dir()
    if env_file := paths.ensure_env_file(home):
        print(f"Created {env_file}: fill in IG_ACCESS_TOKEN and IG_USER_ID (see README).")
    print(f"\nrun:     {' '.join([entry['command'], *entry['args']])}\ndata:    {home}")
    if relaunch:
        launch_desktop()
        print("Claude Desktop restarted: the 'creatorloop' tools appear in a new chat.")
    else:
        print("Start Claude Desktop: the 'creatorloop' tools appear in a new chat.")


if __name__ == "__main__":
    main()
