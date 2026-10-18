import sys

import pytest

from creatorloop import auth_cli, setup_web

from .meta_fakes import EXPIRES


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATORLOOP_HOME", str(tmp_path / "home"))
    for key in ("META_APP_ID", "META_APP_SECRET", "IG_ACCESS_TOKEN", "IG_USER_ID"):
        monkeypatch.setenv(key, "")
    monkeypatch.chdir(tmp_path)  # never read the repo's own ./.env
    return tmp_path / "home"


def run_cli(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["creatorloop-auth", *argv])
    auth_cli.main()


def test_login_passes_flags_and_reports_the_account(monkeypatch, isolated_home, capsys):
    calls = []

    def fake_run(env_path, **kwargs):
        calls.append((env_path, kwargs))
        return setup_web.Result("me", "1784", 155, EXPIRES, {})

    monkeypatch.setenv("META_APP_ID", "1234")
    monkeypatch.setenv("META_APP_SECRET", "shh")
    monkeypatch.setenv("GRAPH_API_VERSION", "v99.0")
    monkeypatch.setattr(auth_cli.setup_web, "run", fake_run)
    run_cli(monkeypatch, "login", "--no-browser", "--port", "8765", "--bind", "0.0.0.0")
    [(env_path, kwargs)] = calls
    assert env_path == isolated_home / ".env"
    assert kwargs["open_browser"] is False and kwargs["port"] == 8765 and kwargs["bind"] == "0.0.0.0"
    assert kwargs["app_id"] == "1234" and kwargs["app_secret"] == "shh" and kwargs["api_version"] == "v99.0"
    assert "OK: @me connected" in capsys.readouterr().out


def _login_result(env_path, **kwargs):
    return setup_web.Result("me", "1784", 155, EXPIRES, {})


@pytest.mark.parametrize("bind", ["0.0.0.0", "192.168.1.5"])
def test_login_warns_when_listening_beyond_localhost(monkeypatch, capsys, bind):
    monkeypatch.setattr(auth_cli.setup_web, "run", _login_result)
    run_cli(monkeypatch, "login", "--bind", bind)
    err = capsys.readouterr().err
    assert f"Listening on {bind}: the page is reachable from the network." in err
    assert "-p 127.0.0.1:PORT:PORT" in err and "keep the default 127.0.0.1" in err


@pytest.mark.parametrize("bind", [[], ["--bind", "127.0.0.1"], ["--bind", "localhost"], ["--bind", "::1"]])
def test_login_on_localhost_prints_no_warning(monkeypatch, capsys, bind):
    monkeypatch.setattr(auth_cli.setup_web, "run", _login_result)
    run_cli(monkeypatch, "login", *bind)
    assert capsys.readouterr().err == ""


def test_login_timeout_exits_with_a_hint(monkeypatch):
    monkeypatch.setattr(auth_cli.setup_web, "run", lambda env_path, **kw: None)
    with pytest.raises(SystemExit) as exit_:
        run_cli(monkeypatch, "login")
    assert str(exit_.value) == (
        "The setup page closed before the account was connected (stopped, or the 15-minute limit). "
        "Run `creatorloop-auth login` again."
    )


def test_login_busy_port(monkeypatch):
    def busy(env_path, **kw):
        raise OSError(48, "Address already in use")

    monkeypatch.setattr(auth_cli.setup_web, "run", busy)
    with pytest.raises(SystemExit) as exit_:
        run_cli(monkeypatch, "login", "--port", "8765")
    assert str(exit_.value) == (
        "Cannot start the setup page on 127.0.0.1:8765: [Errno 48] Address already in use. Pass another --port, or check --bind."
    )
