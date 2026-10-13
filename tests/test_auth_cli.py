import sys

import pytest

from creatorloop import auth_cli, setup_web

from .meta_fakes import EXPIRES


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATORLOOP_HOME", str(tmp_path / "home"))
    for key in ("META_APP_ID", "META_APP_SECRET", "IG_ACCESS_TOKEN", "IG_USER_ID"):
        monkeypatch.setenv(key, "")
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
    monkeypatch.setattr(auth_cli.setup_web, "run", fake_run)
    run_cli(monkeypatch, "login", "--no-browser", "--port", "8765", "--bind", "0.0.0.0")
    [(env_path, kwargs)] = calls
    assert env_path == isolated_home / ".env"
    assert kwargs["open_browser"] is False and kwargs["port"] == 8765 and kwargs["bind"] == "0.0.0.0"
    assert kwargs["app_id"] == "1234"
    assert "OK: @me connected" in capsys.readouterr().out


def test_login_timeout_exits_with_a_hint(monkeypatch):
    monkeypatch.setattr(auth_cli.setup_web, "run", lambda env_path, **kw: None)
    with pytest.raises(SystemExit) as exit_:
        run_cli(monkeypatch, "login")
    assert "closed before finishing" in str(exit_.value)


def test_login_busy_port(monkeypatch):
    def busy(env_path, **kw):
        raise OSError(48, "Address already in use")

    monkeypatch.setattr(auth_cli.setup_web, "run", busy)
    with pytest.raises(SystemExit) as exit_:
        run_cli(monkeypatch, "login", "--port", "8765")
    assert "--port" in str(exit_.value)
