import http.client
import json
import os
import re
import socket
import subprocess
import threading

import pytest

from creatorloop import setup_i18n, setup_web
from creatorloop.meta_auth import MetaAuthError

from .meta_fakes import EXPIRES, ME, SHOP, FakeAuth


@pytest.fixture
def env_path(tmp_path):
    return tmp_path / "home" / ".env"


@pytest.fixture
def make_server(env_path):
    servers = []

    def factory(*, start=None, **fake):
        fakes = []

        def make_auth(app_id, app_secret):
            fakes.append(FakeAuth(app_id, app_secret, **fake))
            return fakes[-1]

        kwargs = {"linger": 60, "make_auth": make_auth, **(start or {})}
        srv = setup_web.start(kwargs.pop("env_path", env_path), **kwargs)
        srv.fakes = fakes
        servers.append(srv)
        return srv

    yield factory
    for srv in servers:
        srv.close()


def call(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    hdrs = {"Host": f"localhost:{srv.port}", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, payload


def state_of(srv):
    return json.loads(call(srv, "GET", "/api/state")[2])


def login(srv, app_secret="secret"):
    status, _, body = call(srv, "POST", "/api/app", {"app_id": "1234", "app_secret": app_secret})
    return status, json.loads(body)


def back_from_facebook(srv, **params):
    query = "&".join(f"{k}={v}" for k, v in {"state": srv.session.state, **params}.items())
    return call(srv, "GET", f"/callback?{query}")


def test_full_path_with_one_account(make_server, env_path):
    srv = make_server()
    status, state = login(srv)
    assert status == 200 and state["step"] == "connect"

    status, headers, _ = call(srv, "GET", "/login")
    assert status == 302 and f"state={srv.session.state}" in headers["location"]

    status, headers, _ = back_from_facebook(srv, code="CODE")
    assert status == 303 and headers["location"] == "/"

    state = state_of(srv)
    assert state["step"] == "done"
    assert state["result"] == {"username": "me", "followers": 155, "expires": "2026-12-13", "env_path": str(env_path)}
    assert srv.fakes[-1].redirect_uri == srv.redirect_uri == f"http://localhost:{srv.port}/callback"
    text = env_path.read_text(encoding="utf-8")
    for line in ("META_APP_ID=1234", "META_APP_SECRET=secret", "IG_ACCESS_TOKEN=LONG-TOKEN", "IG_USER_ID=1784"):
        assert line in text
    assert srv.session.result.expires_at == EXPIRES


def test_two_accounts_need_a_choice(make_server, env_path):
    srv = make_server(accounts=(ME, SHOP))
    login(srv)
    back_from_facebook(srv, code="CODE")
    state = state_of(srv)
    assert state["step"] == "choose"
    assert [a["username"] for a in state["accounts"]] == ["me", "shop"]
    assert not env_path.exists()

    status, _, body = call(srv, "POST", "/api/account", {"ig_user_id": "1785"})
    assert status == 200 and json.loads(body)["step"] == "done"
    assert "IG_USER_ID=1785" in env_path.read_text(encoding="utf-8")


def test_wrong_state_saves_nothing(make_server, env_path):
    srv = make_server()
    login(srv)
    call(srv, "GET", "/callback?state=forged&code=CODE")
    state = state_of(srv)
    assert state["error"]["code"] == "bad_state" and state["step"] == "connect"
    assert not env_path.exists()


def test_cancelled_login(make_server):
    srv = make_server()
    login(srv)
    back_from_facebook(srv, error="access_denied", error_reason="user_denied", error_description="Permissions+error")
    assert state_of(srv)["error"]["code"] == "access_denied"


def test_unticked_permissions_are_reported(make_server, env_path):
    srv = make_server(missing=("business_management",))
    login(srv)
    back_from_facebook(srv, code="CODE")
    state = state_of(srv)
    assert state["error"] == {"code": "missing_permissions", "detail": "business_management"}
    assert state["step"] == "connect"
    assert not env_path.exists()
    _, headers, _ = call(srv, "GET", "/login?rerequest=1")
    assert "rerequest=1" in headers["location"]


def test_page_without_instagram_is_explained(make_server):
    srv = make_server(find_error=MetaAuthError("no_instagram", "Blog"))
    login(srv)
    back_from_facebook(srv, code="CODE")
    assert state_of(srv)["error"] == {"code": "no_instagram", "detail": "Blog"}


def test_bad_secret_is_rejected_and_never_echoed(make_server):
    srv = make_server()
    status, state = login(srv, app_secret="wrong-secret")
    assert status == 400
    assert state["error"]["code"] == "bad_app" and state["step"] == "app"
    assert "wrong-secret" not in json.dumps(state)


def test_empty_secret_reuses_the_saved_one_for_the_same_app(make_server):
    srv = make_server(start={"app_id": "1234", "app_secret": "secret"})
    assert state_of(srv)["app_id"] == "1234" and state_of(srv)["secret_saved"] is True
    status, state = login(srv, app_secret="")
    assert status == 200 and state["step"] == "connect"


def test_saved_secret_is_not_used_for_another_app(make_server):
    srv = make_server(start={"app_id": "9999", "app_secret": "secret"})
    status, state = login(srv, app_secret="")
    assert status == 400 and state["error"]["code"] == "bad_app"


def test_other_settings_survive_reconnect(make_server, env_path):
    env_path.parent.mkdir(parents=True)
    env_path.write_text("# mine\nIG_TIMEZONE=Asia/Tashkent\nQUEUE_SLOTS=Tue 19:00\nIG_ACCESS_TOKEN=OLD\n", encoding="utf-8")
    srv = make_server()
    login(srv)
    back_from_facebook(srv, code="CODE")
    text = env_path.read_text(encoding="utf-8")
    assert "# mine\nIG_TIMEZONE=Asia/Tashkent\nQUEUE_SLOTS=Tue 19:00\nIG_ACCESS_TOKEN=LONG-TOKEN\n" in text


def test_state_never_contains_secrets(make_server):
    srv = make_server()
    login(srv)
    back_from_facebook(srv, code="CODE")
    raw = call(srv, "GET", "/api/state")[2].decode()
    assert "LONG-TOKEN" not in raw
    assert '"secret"' not in raw and "app_secret" not in raw  # the JSON value "secret" / the key; paths may contain the word


def test_foreign_host_is_rejected(make_server):
    srv = make_server()
    assert call(srv, "GET", "/api/state", headers={"Host": "evil.example:80"})[0] == 403
    assert call(srv, "POST", "/api/app", {"app_id": "1"}, headers={"Host": "evil.example"})[0] == 403


def test_post_needs_json(make_server):
    srv = make_server()
    status, _, _ = call(srv, "POST", "/api/app", None, headers={"Content-Type": "text/plain"})
    assert status == 415


def test_page_language_and_safe_boot_data(make_server, monkeypatch):
    monkeypatch.setitem(setup_i18n.STRINGS["ru"], "title", "</script><b>x")
    srv = make_server()
    status, headers, body = call(srv, "GET", "/", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    page = body.decode()
    assert status == 200 and headers["content-type"].startswith("text/html")
    assert '"lang": "ru"' in page
    assert "</script><b>" not in page
    assert "/*BOOT*/" not in page


def _lang_of(srv, path="/", **headers):
    page = call(srv, "GET", path, headers=headers)[2].decode()
    return re.search(r'"lang": "(\w+)"', page).group(1)


def test_language_cookie_survives_the_facebook_round_trip(make_server):
    srv = make_server()
    assert _lang_of(srv, **{"Cookie": "creatorloop_lang=uz", "Accept-Language": "ru"}) == "uz"
    assert _lang_of(srv, **{"Cookie": "other=1; creatorloop_lang=ru", "Accept-Language": "en"}) == "ru"


def test_query_language_beats_the_cookie(make_server):
    srv = make_server()
    assert _lang_of(srv, "/?lang=en", **{"Cookie": "creatorloop_lang=uz", "Accept-Language": "ru"}) == "en"


def test_invalid_language_values_fall_back(make_server):
    srv = make_server()
    assert _lang_of(srv, **{"Cookie": "creatorloop_lang=xx", "Accept-Language": "ru"}) == "ru"
    assert _lang_of(srv, "/?lang=xx", **{"Cookie": "creatorloop_lang=uz"}) == "uz"
    assert _lang_of(srv, **{"Cookie": "creatorloop_lang", "Accept-Language": "uz"}) == "uz"
    assert _lang_of(srv, **{"Cookie": "\x00;;=;", "Accept-Language": "uz"}) == "uz"


def test_page_stores_the_chosen_language_in_a_lax_cookie():
    page = setup_web.PAGE.read_text(encoding="utf-8")
    assert re.search(r'document\.cookie\s*=\s*"creatorloop_lang="\s*\+\s*lang\s*\+\s*"; path=/; SameSite=Lax"', page)


def test_secret_and_token_stay_out_of_reprs(make_server):
    srv = make_server()
    login(srv)
    back_from_facebook(srv, code="CODE")
    result = srv.session.result
    assert result.values["META_APP_SECRET"] == "secret" and result.values["IG_ACCESS_TOKEN"] == "LONG-TOKEN"
    assert "secret" not in repr(result) and "LONG-TOKEN" not in repr(result)
    assert "LONG-TOKEN" not in repr(srv.session.token)


def test_a_rejected_app_closes_the_connection_it_opened(make_server):
    srv = make_server()
    status, state = login(srv, "wrong")
    assert status == 400 and state["step"] == "app"
    assert [f.closed for f in srv.fakes] == [True]


def test_closing_the_server_closes_the_auth_client(make_server):
    srv = make_server()
    login(srv)
    assert [f.closed for f in srv.fakes] == [False]
    srv.close()
    assert [f.closed for f in srv.fakes] == [True]


def raw_post(srv, headers, body=b""):
    head = "".join(f"{k}: {v}\r\n" for k, v in {"Host": f"localhost:{srv.port}", **headers}.items())
    with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as sock:
        sock.sendall(f"POST /api/app HTTP/1.0\r\n{head}\r\n".encode() + body)
        return sock.makefile("rb").readline().decode()


@pytest.mark.parametrize(
    ("length", "body"), [("abc", b""), ("-1", b""), ("2", b"[]"), ("4", b"null"), ("2", b"42")]
)
def test_malformed_posts_get_400_and_the_server_lives(make_server, length, body):
    srv = make_server()
    json_type = {"Content-Type": "application/json", "Content-Length": length}
    assert raw_post(srv, json_type, body).startswith("HTTP/1.0 400")
    assert state_of(srv)["step"] == "app"


def test_responses_forbid_framing_and_sniffing(make_server):
    _, headers, _ = call(make_server(), "GET", "/")
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == "frame-ancestors 'none'"
    assert headers["x-content-type-options"] == "nosniff"


def test_boot_data_has_no_dead_scopes(make_server):
    assert '"scopes"' not in call(make_server(), "GET", "/")[2].decode()


def test_unknown_path_is_404(make_server):
    assert call(make_server(), "GET", "/etc/passwd")[0] == 404


def test_failed_save_is_an_error_not_done(make_server, tmp_path):
    done = []
    srv = make_server(start={"env_path": tmp_path, "on_done": done.append})  # a folder: the write fails
    login(srv)
    back_from_facebook(srv, code="CODE")
    state = state_of(srv)
    assert state["step"] != "done" and state["error"]["code"] == "meta_error"
    assert done == []


def test_closes_after_success(make_server):
    done = []
    srv = make_server(start={"linger": 0, "on_done": done.append})
    login(srv)
    back_from_facebook(srv, code="CODE")
    assert srv.stopped.wait(5)
    assert [r.username for r in done] == ["me"]


def test_timeout_closes_without_result(make_server):
    srv = make_server(start={"timeout": 0.2})
    assert srv.stopped.wait(5)
    assert srv.session.result is None


def test_run_returns_the_result(env_path, monkeypatch):
    opened, printed = [], []
    monkeypatch.setattr(setup_web.webbrowser, "open", opened.append)

    def finish(srv):
        login(srv)
        back_from_facebook(srv, code="CODE")

    real_start = setup_web.start

    def start(*args, **kwargs):
        srv = real_start(*args, **kwargs)
        threading.Timer(0.1, finish, args=(srv,)).start()
        return srv

    monkeypatch.setattr(setup_web, "start", start)
    result = setup_web.run(env_path, out=printed.append, make_auth=lambda i, s: FakeAuth(i, s), linger=0)
    assert result.username == "me"
    assert opened == [printed[0].removeprefix("Setup page: ")]


def test_second_choice_after_completion_changes_nothing(env_path):
    done = []
    session = setup_web.SetupSession(
        env_path, make_auth=lambda i, s: FakeAuth(i, s, accounts=(ME, SHOP)), on_done=done.append
    )
    session.set_app("1234", "secret")
    session.callback({"state": session.state, "code": "CODE"}, "http://localhost/callback")
    session.choose(ME.id)
    session.choose(SHOP.id)
    assert [r.username for r in done] == ["me"]
    assert session.result.username == "me"
    assert "IG_USER_ID=1784" in env_path.read_text(encoding="utf-8")
    assert session.error is None


def test_double_click_on_an_account_is_a_no_op(make_server, env_path):
    srv = make_server(accounts=(ME, SHOP))
    login(srv)
    back_from_facebook(srv, code="CODE")
    assert call(srv, "POST", "/api/account", {"ig_user_id": "1784"})[0] == 200
    status, _, body = call(srv, "POST", "/api/account", {"ig_user_id": "1785"})
    assert status == 200 and json.loads(body)["step"] == "done"
    assert "IG_USER_ID=1784" in env_path.read_text(encoding="utf-8")
    assert "1785" not in env_path.read_text(encoding="utf-8")


def test_reloading_the_callback_after_success_changes_nothing(make_server, env_path):
    srv = make_server()
    login(srv)
    back_from_facebook(srv, code="CODE")
    before = env_path.read_text(encoding="utf-8")
    status, headers, _ = back_from_facebook(srv, code="CODE")
    assert status == 303 and headers["location"] == "/"
    assert state_of(srv)["step"] == "done" and state_of(srv)["error"] is None
    assert env_path.read_text(encoding="utf-8") == before


def test_page_keeps_the_typed_secret_when_the_check_fails():
    # Pins the retry behaviour: the secret field is cleared only when the response carries no error,
    # otherwise the next click would send an empty secret and fail with bad_app.
    page = setup_web.PAGE.read_text(encoding="utf-8")
    assert re.search(r"if\s*\(\s*!state\.error\s*\)\s*\$\(\"app-secret\"\)\.value\s*=\s*\"\"", page)


def test_page_disables_sections_for_the_keyboard_too():
    page = setup_web.PAGE.read_text(encoding="utf-8")
    for section in ("s-app", "s-connect"):
        assert re.search(rf'\$\("{section}"\)\.inert\s*=', page)
    assert re.search(r"\.err\s*\{[^}]*overflow-wrap:\s*anywhere", page)


@pytest.mark.parametrize(("platform", "command"), [("linux", "xdg-open"), ("darwin", "open")])
def test_open_browser_detaches_the_child_from_our_stdio(monkeypatch, platform, command):
    """Inside the MCP server stdout is the protocol channel: a browser started with webbrowser.open inherits it."""
    calls = []
    monkeypatch.setattr(setup_web.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    assert setup_web.open_browser("http://localhost:1/", platform=platform) is True
    (args, kwargs), = calls
    assert args[0] == [command, "http://localhost:1/"]
    for stream in ("stdin", "stdout", "stderr"):
        assert kwargs[stream] == subprocess.DEVNULL
    assert kwargs["start_new_session"] is True


def test_open_browser_on_windows_uses_startfile(monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    assert setup_web.open_browser("http://localhost:1/", platform="win32") is True
    assert opened == ["http://localhost:1/"]


def test_open_browser_reports_a_missing_opener(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr(setup_web.subprocess, "Popen", boom)
    assert setup_web.open_browser("http://localhost:1/", platform="linux") is False
