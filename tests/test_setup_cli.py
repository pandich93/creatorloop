from __future__ import annotations

import json
import subprocess

import pytest

from creatorloop import setup_cli

REAL_CONNECT_ACCOUNT = setup_cli.connect_account


def test_config_candidates_macos(tmp_path):
    [path] = setup_cli.config_candidates("darwin", home=tmp_path, env={})
    assert path == tmp_path / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def test_config_candidates_linux_respects_xdg(tmp_path):
    assert setup_cli.config_candidates("linux", home=tmp_path, env={}) == [
        tmp_path / ".config" / "Claude" / "claude_desktop_config.json"
    ]
    xdg = tmp_path / "xdg"
    assert setup_cli.config_candidates("linux", home=tmp_path, env={"XDG_CONFIG_HOME": str(xdg)}) == [
        xdg / "Claude" / "claude_desktop_config.json"
    ]


def test_config_candidates_windows_includes_store_version(tmp_path):
    roaming, local = tmp_path / "Roaming", tmp_path / "Local"
    (local / "Packages" / "Claude_pzs8sxrjxfjjc").mkdir(parents=True)
    candidates = setup_cli.config_candidates("win32", home=tmp_path, env={"APPDATA": str(roaming), "LOCALAPPDATA": str(local)})
    assert candidates == [
        roaming / "Claude" / "claude_desktop_config.json",
        local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json",
    ]


def test_pick_targets_prefers_existing_configs(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert setup_cli.pick_targets([a, b]) == [a]
    b.write_text("{}")
    assert setup_cli.pick_targets([a, b]) == [b]


def test_server_entry_from_source_checkout(tmp_path):
    project = tmp_path / "creatorloop"
    assert setup_cli.server_entry(uv="/opt/homebrew/bin/uv", source=project) == {
        "command": "/opt/homebrew/bin/uv",
        "args": ["--directory", str(project), "run", "creatorloop"],
    }


def test_server_entry_from_pypi_install():
    # installed from PyPI: run the published package, like `uvx creatorloop`
    assert setup_cli.server_entry(uv="/opt/homebrew/bin/uv", source=None) == {
        "command": "/opt/homebrew/bin/uv",
        "args": ["tool", "run", "creatorloop"],
    }


def test_install_creates_config(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    entry = {"command": "uv", "args": ["tool", "run", "creatorloop"]}
    backup = setup_cli.install(cfg, entry=entry)
    assert backup is None
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"mcpServers": {"creatorloop": entry}}


def test_install_keeps_other_settings_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    original = {"theme": "dark", "mcpServers": {"other": {"command": "x"}, "creatorloop": {"command": "old"}}}
    cfg.write_text(json.dumps(original), encoding="utf-8")
    backup = setup_cli.install(cfg, entry={"command": "uv"})
    assert backup is not None and json.loads(backup.read_text(encoding="utf-8")) == original
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["creatorloop"]["command"] == "uv"


def test_install_writes_utf8_without_bom(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_bytes(b"\xef\xbb\xbf{}")  # BOM written by some Windows editors
    setup_cli.install(cfg, entry={"command": "uv"})
    assert not cfg.read_bytes().startswith(b"\xef\xbb\xbf")


def test_install_refuses_broken_json(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        setup_cli.install(cfg, entry={"command": "uv"})
    assert cfg.read_text(encoding="utf-8") == "{not json"


def test_find_uv_falls_back_to_installer_location(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_cli.shutil, "which", lambda name: None)
    uv = tmp_path / ".local" / "bin" / ("uv.exe" if setup_cli.sys.platform == "win32" else "uv")
    uv.parent.mkdir(parents=True)
    uv.write_bytes(b"")
    monkeypatch.setattr(setup_cli.Path, "home", lambda: tmp_path)
    assert setup_cli.find_uv() == str(uv)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATORLOOP_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture(autouse=True)
def no_setup_page(monkeypatch):
    """main() opens the setup page; existing tests only check the Desktop config part."""
    calls = []
    monkeypatch.setattr(setup_cli, "connect_account", lambda env_path, **kw: calls.append((env_path, kw)))
    return calls


def test_setup_creates_env_file_in_home(tmp_path, monkeypatch, isolated_home):
    FakeDesktop(monkeypatch, running=False)
    setup_cli.main(["--config", str(tmp_path / "claude_desktop_config.json")], platform="linux")
    assert "IG_ACCESS_TOKEN=" in (isolated_home / ".env").read_text(encoding="utf-8")


class FakeDesktop:
    """Records quit / install / launch calls; Desktop 'runs' until quit succeeds."""

    def __init__(self, monkeypatch, *, running: bool, quits: bool = True):
        self.running, self.calls = running, []
        monkeypatch.setattr(setup_cli, "is_desktop_running", lambda platform: self.running)
        monkeypatch.setattr(setup_cli, "quit_desktop", self.quit)
        monkeypatch.setattr(setup_cli, "launch_desktop", lambda: self.calls.append("launch"))
        monkeypatch.setattr(setup_cli, "find_uv", lambda: "uv")
        real_install = setup_cli.install

        def install(path, **kw):
            self.calls.append("install")
            return real_install(path, **kw)

        monkeypatch.setattr(setup_cli, "install", install)
        self._quits = quits

    def quit(self) -> bool:
        self.calls.append("quit")
        self.running = not self._quits
        return self._quits


def test_macos_running_desktop_is_quit_then_relaunched(tmp_path, monkeypatch):
    desktop = FakeDesktop(monkeypatch, running=True)
    cfg = tmp_path / "claude_desktop_config.json"
    setup_cli.main(["--config", str(cfg)], platform="darwin")
    assert desktop.calls == ["quit", "install", "launch"]
    assert "creatorloop" in json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]


def test_macos_desktop_that_does_not_quit_leaves_config_untouched(tmp_path, monkeypatch):
    desktop = FakeDesktop(monkeypatch, running=True, quits=False)
    cfg = tmp_path / "claude_desktop_config.json"
    with pytest.raises(SystemExit) as exc:
        setup_cli.main(["--config", str(cfg)], platform="darwin")
    assert exc.value.code not in (0, None)
    assert desktop.calls == ["quit"]
    assert not cfg.exists()


@pytest.mark.parametrize(("platform", "argv"), [("darwin", ["--no-restart"]), ("win32", []), ("linux", [])])
def test_running_desktop_without_auto_restart_is_refused(tmp_path, monkeypatch, platform, argv):
    desktop = FakeDesktop(monkeypatch, running=True)
    cfg = tmp_path / "claude_desktop_config.json"
    with pytest.raises(SystemExit) as exc:
        setup_cli.main(["--config", str(cfg), *argv], platform=platform)
    assert "Quit" in str(exc.value.code)
    assert desktop.calls == []
    assert not cfg.exists()


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_closed_desktop_is_written_without_restart(tmp_path, monkeypatch, platform):
    desktop = FakeDesktop(monkeypatch, running=False)
    cfg = tmp_path / "claude_desktop_config.json"
    setup_cli.main(["--config", str(cfg)], platform=platform)
    assert desktop.calls == ["install"]
    assert cfg.exists()


@pytest.mark.parametrize(
    ("platform", "stdout", "returncode", "expected"),
    [
        ("darwin", "", 0, True),
        ("darwin", "", 1, False),
        ("win32", "Claude.exe   1234 Console   1   200,000 K\n", 0, True),
        ("win32", "INFO: No tasks are running which match the specified criteria.\n", 0, False),
        ("linux", "", 0, True),
        ("linux", "", 1, False),
    ],
)
def test_is_desktop_running(monkeypatch, platform, stdout, returncode, expected):
    monkeypatch.setattr(
        setup_cli.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    )
    assert setup_cli.is_desktop_running(platform) is expected


def test_is_desktop_running_without_process_tools(monkeypatch):
    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(setup_cli.subprocess, "run", missing)
    assert setup_cli.is_desktop_running("linux") is False


def test_help_carries_meta_disclaimer(capsys):
    with pytest.raises(SystemExit):
        setup_cli.main(["--help"])
    out = capsys.readouterr().out
    assert "Not affiliated with, endorsed or sponsored by Meta or Instagram" in out


def test_setup_connects_the_account_before_relaunching_desktop(tmp_path, monkeypatch, isolated_home, no_setup_page):
    desktop = FakeDesktop(monkeypatch, running=True)
    monkeypatch.setattr(setup_cli, "connect_account", lambda env_path, **kw: desktop.calls.append("connect"))
    setup_cli.main(["--config", str(tmp_path / "claude_desktop_config.json")], platform="darwin")
    assert desktop.calls == ["quit", "install", "connect", "launch"]


def test_setup_passes_flags(tmp_path, monkeypatch, isolated_home, no_setup_page):
    FakeDesktop(monkeypatch, running=False)
    setup_cli.main(["--config", str(tmp_path / "c.json"), "--reauth", "--no-browser"], platform="linux")
    assert no_setup_page == [(isolated_home / ".env", {"reauth": True, "open_browser": False})]


def test_connect_account_skips_a_working_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(setup_cli.meta_auth, "credentials_work", lambda *a, **kw: True)
    monkeypatch.setattr(setup_cli.setup_web, "run", lambda *a, **kw: pytest.fail("page must not open"))
    REAL_CONNECT_ACCOUNT(tmp_path / ".env", reauth=False, open_browser=True)
    assert "already connected" in capsys.readouterr().out


def test_connect_account_opens_the_page(monkeypatch, tmp_path, capsys):
    from creatorloop.setup_web import Result

    monkeypatch.setattr(setup_cli.meta_auth, "credentials_work", lambda *a, **kw: True)
    seen = {}

    def run(env_path, **kw):
        seen.update(kw)
        return Result("me", "1784", 155, None, {})

    monkeypatch.setattr(setup_cli.setup_web, "run", run)
    REAL_CONNECT_ACCOUNT(tmp_path / ".env", reauth=True, open_browser=False)
    assert seen["open_browser"] is False
    assert "OK: @me connected" in capsys.readouterr().out


def test_connect_account_unfinished(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(setup_cli.meta_auth, "credentials_work", lambda *a, **kw: False)
    monkeypatch.setattr(setup_cli.setup_web, "run", lambda *a, **kw: None)
    REAL_CONNECT_ACCOUNT(tmp_path / ".env", reauth=False, open_browser=True)
    assert "creatorloop-auth login" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RuntimeError("IG_TIMEZONE='x' is not a known timezone"), "IG_TIMEZONE='x' is not a known timezone"),
        (KeyboardInterrupt(), "KeyboardInterrupt"),
    ],
)
def test_setup_relaunches_desktop_even_if_the_setup_page_fails(tmp_path, monkeypatch, capsys, error, reason):
    desktop = FakeDesktop(monkeypatch, running=True)

    def boom(env_path, **kw):
        raise error

    monkeypatch.setattr(setup_cli, "connect_account", boom)
    setup_cli.main(["--config", str(tmp_path / "claude_desktop_config.json")], platform="darwin")
    out = capsys.readouterr().out
    assert desktop.calls == ["quit", "install", "launch"]
    assert reason in out
    assert "creatorloop-auth login" in out


def test_config_write_errors_still_propagate_and_desktop_is_not_relaunched(tmp_path, monkeypatch):
    desktop = FakeDesktop(monkeypatch, running=True)

    def broken_install(path, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(setup_cli, "install", broken_install)
    with pytest.raises(OSError, match="disk full"):
        setup_cli.main(["--config", str(tmp_path / "claude_desktop_config.json")], platform="darwin")
    assert desktop.calls == ["quit"]
