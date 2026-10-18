from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from creatorloop import config, paths


def test_home_dir_per_platform(tmp_path):
    assert paths.home_dir("darwin", env={}, home=tmp_path) == tmp_path / "Library" / "Application Support" / "creatorloop"
    assert paths.home_dir("linux", env={}, home=tmp_path) == tmp_path / ".local" / "share" / "creatorloop"
    xdg = {"XDG_DATA_HOME": str(tmp_path / "xdg")}
    assert paths.home_dir("linux", env=xdg, home=tmp_path) == tmp_path / "xdg" / "creatorloop"
    appdata = tmp_path / "Roaming"
    assert paths.home_dir("win32", env={"APPDATA": str(appdata)}, home=tmp_path) == appdata / "creatorloop"


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_home_dir_env_override(tmp_path, platform):
    custom = tmp_path / "my-home"
    assert paths.home_dir(platform, env={"CREATORLOOP_HOME": str(custom)}, home=tmp_path) == custom


def test_content_and_refs_live_in_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATORLOOP_HOME", str(tmp_path))
    assert paths.content_root() == tmp_path / "content"
    assert paths.refs_root() == tmp_path / "content" / "_refs"


def test_source_root_only_for_a_source_checkout(tmp_path):
    pkg = tmp_path / "repo" / "src" / "creatorloop"
    pkg.mkdir(parents=True)
    assert paths.source_root(pkg) is None
    (tmp_path / "repo" / "pyproject.toml").write_text('[project]\nname = "creatorloop"\n', encoding="utf-8")
    assert paths.source_root(pkg) == tmp_path / "repo"
    # an unrelated pyproject.toml (e.g. a venv inside another project) does not count
    (tmp_path / "repo" / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    assert paths.source_root(pkg) is None


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    for key in ("IG_ACCESS_TOKEN", "IG_USER_ID", "IG_DB_PATH", "IG_TIMEZONE"):
        monkeypatch.delenv(key, raising=False)
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("CREATORLOOP_HOME", str(home))
    monkeypatch.chdir(cwd)
    yield home, cwd
    for key in ("IG_ACCESS_TOKEN", "IG_USER_ID"):
        os.environ.pop(key, None)  # load_dotenv writes into os.environ


def test_env_precedence(clean_env, monkeypatch):
    home, cwd = clean_env
    (home / ".env").write_text("IG_ACCESS_TOKEN=from-home\nIG_USER_ID=home-id\n", encoding="utf-8")
    (cwd / ".env").write_text("IG_ACCESS_TOKEN=from-cwd\nIG_USER_ID=cwd-id\n", encoding="utf-8")
    monkeypatch.setenv("IG_USER_ID", "from-env")
    s = config.load_settings()
    assert s.ig_user_id == "from-env"  # real environment wins
    assert s.access_token == "from-home"  # then the user's home .env, then ./.env


def test_empty_env_var_does_not_hide_env_file(clean_env, monkeypatch):
    # the Claude Desktop bundle passes "" for a setting the user left empty: the setup page's .env must still count
    home, _ = clean_env
    (home / ".env").write_text("IG_ACCESS_TOKEN=from-home\nIG_USER_ID=home-id\n", encoding="utf-8")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "")
    monkeypatch.setenv("IG_USER_ID", " ")
    s = config.load_settings()
    assert (s.access_token, s.ig_user_id) == ("from-home", "home-id")


def test_env_falls_back_to_cwd(clean_env):
    _, cwd = clean_env
    (cwd / ".env").write_text("IG_ACCESS_TOKEN=from-cwd\n", encoding="utf-8")
    assert config.load_settings().access_token == "from-cwd"


def test_database_defaults_to_home(clean_env):
    home, _ = clean_env
    assert config.load_settings().db_path == home / "creatorloop.db"


def test_env_template_is_packaged():
    template = paths.env_template()
    assert template.is_file()
    text = template.read_text(encoding="utf-8")
    assert "IG_ACCESS_TOKEN=" in text and "IG_USER_ID=" in text


def test_ensure_env_file_creates_once(tmp_path):
    created = paths.ensure_env_file(tmp_path)
    assert created == tmp_path / ".env"
    assert "IG_ACCESS_TOKEN=" in created.read_text(encoding="utf-8")
    created.write_text("IG_ACCESS_TOKEN=keep-me\n", encoding="utf-8")
    assert paths.ensure_env_file(tmp_path) is None
    assert created.read_text(encoding="utf-8") == "IG_ACCESS_TOKEN=keep-me\n"


def test_paths_module_has_no_source_tree_assumptions():
    assert not hasattr(config, "PROJECT_ROOT")
    assert isinstance(paths.home_dir(), Path)


def test_timezone_from_tz_variable(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    assert str(config.system_timezone()) == "Europe/Berlin"


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs admin rights on Windows")
def test_timezone_from_localtime_symlink(tmp_path, monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    target = tmp_path / "usr" / "share" / "zoneinfo" / "America" / "New_York"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    link = tmp_path / "localtime"
    link.symlink_to(target)
    assert str(config.system_timezone(localtime=link, timezone_file=tmp_path / "missing")) == "America/New_York"


def test_timezone_from_etc_timezone(tmp_path, monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    tz_file = tmp_path / "timezone"
    tz_file.write_text("Asia/Tokyo\n", encoding="utf-8")
    assert str(config.system_timezone(localtime=tmp_path / "missing", timezone_file=tz_file)) == "Asia/Tokyo"


def test_timezone_falls_back_to_current_offset(tmp_path, monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    tz = config.system_timezone(localtime=tmp_path / "missing", timezone_file=tmp_path / "missing")
    assert tz.utcoffset(None) is not None  # a fixed-offset tzinfo, e.g. on Windows


def test_settings_use_system_timezone_by_default(clean_env, monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(config, "system_timezone", lambda: ZoneInfo("America/Chicago"))
    assert str(config.load_settings().timezone) == "America/Chicago"
    monkeypatch.setenv("IG_TIMEZONE", "Asia/Seoul")
    assert str(config.load_settings().timezone) == "Asia/Seoul"
