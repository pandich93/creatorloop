"""One-session local web page that connects creatorloop to Instagram (docs/meta-setup.md).

The page talks only to this server; the App Secret and tokens go nowhere but graph.facebook.com and the .env file.
Used by `creatorloop-setup`, `creatorloop-auth login` and the MCP tool `open_setup`."""

from __future__ import annotations

import contextlib
import json
import logging
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from creatorloop import env_file, setup_i18n
from creatorloop.config import DEFAULT_API_VERSION
from creatorloop.meta_auth import SCOPES, IgAccount, LongLivedToken, MetaAuth, MetaAuthError

log = logging.getLogger("creatorloop.setup")
PAGE = Path(__file__).with_name("setup_page.html")
GUIDE_URL = "https://github.com/pandich93/creatorloop/blob/main/docs/meta-setup.md"
MAX_BODY = 64 * 1024


@dataclass(frozen=True, slots=True)
class Result:
    username: str
    ig_user_id: str
    followers: int | None
    expires_at: datetime | None
    values: dict[str, str]  # exactly what was written to .env


class SetupSession:
    """State of one setup run, independent of HTTP."""

    def __init__(
        self,
        env_path: Path,
        *,
        api_version: str = DEFAULT_API_VERSION,
        app_id: str = "",
        app_secret: str = "",
        make_auth: Callable[[str, str], MetaAuth] | None = None,
        on_done: Callable[[Result], None] | None = None,
    ) -> None:
        self.env_path = env_path
        self.app_id = app_id
        self._saved_secret = app_secret
        self._make_auth = make_auth or (lambda i, s: MetaAuth(i, s, api_version=api_version))
        self._on_done = on_done
        self.state = secrets.token_urlsafe(24)
        self.auth: MetaAuth | None = None
        self.token: LongLivedToken | None = None
        self.accounts: list[IgAccount] = []
        self.error: MetaAuthError | None = None
        self.result: Result | None = None
        self.done = threading.Event()
        self._lock = threading.Lock()

    @property
    def step(self) -> str:
        if self.result:
            return "done"
        if self.accounts:
            return "choose"
        return "connect" if self.auth else "app"

    def snapshot(self) -> dict[str, Any]:
        """Everything the page may see: never the App Secret or a token."""
        r = self.result
        return {
            "step": self.step,
            "app_id": self.app_id,
            "secret_saved": bool(self._saved_secret),
            "accounts": [
                {"id": a.id, "username": a.username, "followers": a.followers, "page": a.page} for a in self.accounts
            ],
            "result": r
            and {
                "username": r.username,
                "followers": r.followers,
                "expires": r.expires_at.date().isoformat() if r.expires_at else None,
                "env_path": str(self.env_path),
            },
            "error": self.error and {"code": self.error.code, "detail": self.error.detail},
            "guide": GUIDE_URL,
        }

    @contextlib.contextmanager
    def _step(self) -> Iterator[None]:
        with self._lock:
            self.error = None
            try:
                yield
            except MetaAuthError as exc:
                self.error = exc
                raise
            except Exception as exc:  # e.g. the .env cannot be written: show it on the page instead of a dead request
                log.exception("setup step failed")
                self.error = MetaAuthError("meta_error", str(exc))
                raise self.error from exc

    def set_app(self, app_id: str, app_secret: str) -> None:
        with self._step():
            app_id = app_id.strip()
            secret = app_secret.strip() or (self._saved_secret if app_id == self.app_id else "")
            auth = self._make_auth(app_id, secret)
            auth.validate_app()
            if self.auth:
                self.auth.close()
            self.app_id, self.auth, self.token, self.accounts = app_id, auth, None, []

    def login_url(self, redirect_uri: str, *, rerequest: bool = False) -> str:
        with self._step():
            if not self.auth:
                raise MetaAuthError("no_app")
            return self.auth.login_url(redirect_uri, self.state, rerequest=rerequest)

    def callback(self, params: Mapping[str, str], redirect_uri: str) -> None:
        if self.result:  # the page was reloaded after success
            return
        with self._step():
            if not secrets.compare_digest(params.get("state", "").encode(), self.state.encode()):
                raise MetaAuthError("bad_state")
            if params.get("error"):
                denied = params.get("error") == "access_denied" or params.get("error_reason") == "user_denied"
                raise MetaAuthError("access_denied" if denied else "meta_error", params.get("error_description", ""))
            if not self.auth:
                raise MetaAuthError("no_app")
            if "code" not in params:
                raise MetaAuthError("meta_error", "Facebook returned no code")
            token = self.auth.to_long_lived(self.auth.exchange_code(params["code"], redirect_uri))
            if missing := self.auth.missing_permissions(token.value):
                raise MetaAuthError("missing_permissions", ",".join(missing))
            self.accounts = self.auth.find_accounts(token.value)
            self.token = token
        if len(self.accounts) == 1:
            self.choose(self.accounts[0].id)

    def choose(self, ig_user_id: str) -> None:
        with self._step():
            if self.result:  # a double click or a retry after success: keep the first result, finish only once
                return
            account = next((a for a in self.accounts if a.id == ig_user_id), None)
            if account is None or self.token is None or self.auth is None:
                raise MetaAuthError("bad_state")
            values = {
                "META_APP_ID": self.auth.app_id,
                "META_APP_SECRET": self.auth.app_secret,
                "IG_ACCESS_TOKEN": self.token.value,
                "IG_USER_ID": account.id,
            }
            env_file.update(self.env_path, values)
            self.result = Result(account.username, account.id, account.followers, self.token.expires_at, values)
        log.info("Setup finished: @%s connected", account.username)
        if self._on_done:
            try:
                self._on_done(self.result)
            except Exception:
                log.exception("on_done failed")
        self.done.set()


class _Handler(BaseHTTPRequestHandler):
    server: SetupServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        log.debug("setup http: " + format, *args)

    def _send(self, status: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()
        self.wfile.write(body)

    def _state(self, status: int = 200) -> None:
        self._send(status, json.dumps(self.server.session.snapshot()).encode(), "application/json")

    def _host_ok(self) -> bool:
        # blocks DNS rebinding: a foreign site resolved to 127.0.0.1 still sends its own Host
        return self.headers.get("Host", "") in self.server.allowed_hosts

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._send(403, b"forbidden")
        url = urlsplit(self.path)
        query = dict(parse_qsl(url.query))
        session = self.server.session
        match url.path:
            case "/":
                page = self.server.render_page(self.headers.get("Accept-Language"), query.get("lang"))
                return self._send(200, page, "text/html; charset=utf-8")
            case "/api/state":
                return self._state()
            case "/login":
                try:
                    target = session.login_url(self.server.redirect_uri, rerequest="rerequest" in query)
                except MetaAuthError:
                    target = "/"
                return self._send(302, Location=target)
            case "/callback":
                with contextlib.suppress(MetaAuthError):
                    session.callback(query, self.server.redirect_uri)
                return self._send(303, Location="/")
            case _:
                return self._send(404, b"not found")

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._send(403, b"forbidden")
        # cross-site forms cannot send application/json without a preflight this server never answers
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(415, b"application/json only")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, b"too large")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, b"bad JSON")
        session = self.server.session
        try:
            match urlsplit(self.path).path:
                case "/api/app":
                    session.set_app(str(data.get("app_id", "")), str(data.get("app_secret", "")))
                case "/api/account":
                    session.choose(str(data.get("ig_user_id", "")))
                case _:
                    return self._send(404, b"not found")
        except MetaAuthError:
            return self._state(400)
        return self._state()


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, session: SetupSession, *, port: int = 0, bind: str = "127.0.0.1") -> None:
        super().__init__((bind, port), _Handler)
        self.session = session
        self.port = self.server_address[1]
        self.url = f"http://localhost:{self.port}/"
        self.redirect_uri = f"http://localhost:{self.port}/callback"  # Meta allows localhost without registering it
        self.allowed_hosts = {f"localhost:{self.port}", f"127.0.0.1:{self.port}"}
        self.stopped = threading.Event()
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def render_page(self, accept_language: str | None, override: str | None) -> bytes:
        lang = setup_i18n.pick_language(accept_language, override)
        boot = {"lang": lang, "strings": setup_i18n.STRINGS, "scopes": list(SCOPES)}
        data = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
        return PAGE.read_text(encoding="utf-8").replace("/*BOOT*/null", data).encode()

    def close(self) -> None:
        if not self.stopped.is_set():
            self.stopped.set()
            self.shutdown()
            self.server_close()


def start(
    env_path: Path,
    *,
    api_version: str = DEFAULT_API_VERSION,
    app_id: str = "",
    app_secret: str = "",
    port: int = 0,
    bind: str = "127.0.0.1",
    timeout: float = 900,
    linger: float = 10,
    make_auth: Callable[[str, str], MetaAuth] | None = None,
    on_done: Callable[[Result], None] | None = None,
) -> SetupServer:
    """Serve the page in background threads. It closes itself `linger` s after success (so the browser can still
    show the result) or after `timeout` s. OSError when `port` is busy."""
    session = SetupSession(
        env_path, api_version=api_version, app_id=app_id, app_secret=app_secret, make_auth=make_auth, on_done=on_done
    )
    srv = SetupServer(session, port=port, bind=bind)

    def watch() -> None:
        if session.done.wait(timeout):
            time.sleep(linger)
        srv.close()

    threading.Thread(target=watch, daemon=True).start()
    return srv


def run(
    env_path: Path, *, open_browser: bool = True, out: Callable[[str], None] = print, **start_kwargs: Any
) -> Result | None:
    """Blocking: show the page, wait until it closes, return the result (None on timeout or Ctrl+C)."""
    srv = start(env_path, **start_kwargs)
    out(f"Setup page: {srv.url}")
    if open_browser:
        webbrowser.open(srv.url)
    try:
        while not srv.stopped.wait(0.5):
            pass
    except KeyboardInterrupt:
        srv.close()
    return srv.session.result
