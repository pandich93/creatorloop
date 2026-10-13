import os
import sys

import pytest

from creatorloop import env_file


def test_updates_keys_and_keeps_other_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# token\nIG_ACCESS_TOKEN=\nQUEUE_SLOTS=Tue 19:00\n# IG_USER_ID=commented\nIG_USER_ID=old\n",
        encoding="utf-8",
    )
    env_file.update(path, {"IG_ACCESS_TOKEN": "NEW", "IG_USER_ID": "1784"})
    assert path.read_text(encoding="utf-8") == (
        "# token\nIG_ACCESS_TOKEN=NEW\nQUEUE_SLOTS=Tue 19:00\n# IG_USER_ID=commented\nIG_USER_ID=1784\n"
    )


def test_appends_missing_keys_and_creates_parent(tmp_path):
    path = tmp_path / "home" / ".env"
    env_file.update(path, {"META_APP_ID": "123"})
    assert path.read_text(encoding="utf-8") == "META_APP_ID=123\n"


def test_replaces_every_duplicate(tmp_path):
    path = tmp_path / ".env"
    path.write_text("IG_USER_ID=a\nIG_USER_ID=b\n", encoding="utf-8")
    env_file.update(path, {"IG_USER_ID": "c"})
    assert path.read_text(encoding="utf-8") == "IG_USER_ID=c\nIG_USER_ID=c\n"


def test_leaves_no_temp_files(tmp_path):
    path = tmp_path / ".env"
    env_file.update(path, {"A": "1"})
    env_file.update(path, {"A": "2"})
    assert sorted(p.name for p in tmp_path.iterdir()) == [".env"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_file_is_private(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\n", encoding="utf-8")
    os.chmod(path, 0o644)
    env_file.update(path, {"A": "2"})
    assert (path.stat().st_mode & 0o777) == 0o600
