"""Where creatorloop keeps the user's settings and data.

Everything lives in one per-user folder (CREATORLOOP_HOME), never next to the installed code: after
`uvx creatorloop` / `pip install` the package sits in site-packages, which is not a place for a token,
a database or content folders.

    CREATORLOOP_HOME/
      .env              # IG_ACCESS_TOKEN, IG_USER_ID, ...
      creatorloop.db    # cache, follower/post snapshots, queue
      content/          # post folders for prepare_post / queue_post
        _refs/          # slides saved by get_competitor_post
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

APP = "creatorloop"
PACKAGE_DIR = Path(__file__).resolve().parent


def home_dir(platform: str = sys.platform, *, env: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    if custom := env.get("CREATORLOOP_HOME", "").strip():
        return Path(custom).expanduser()
    home = home or Path.home()
    if platform == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / APP
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / APP


def content_root() -> Path:
    return home_dir() / "content"


def refs_root() -> Path:
    return content_root() / "_refs"


def source_root(package_dir: Path = PACKAGE_DIR) -> Path | None:
    """The repository root when running from a source checkout (src/creatorloop), else None."""
    pyproject = package_dir.parents[1] / "pyproject.toml"
    try:
        name = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"]
    except OSError, KeyError, tomllib.TOMLDecodeError:
        return None
    return pyproject.parent if name == APP else None


def env_template() -> Path:
    return PACKAGE_DIR / "env.example"


def ensure_env_file(home: Path) -> Path | None:
    """Create home/.env from the template; return its path, or None if it already existed."""
    target = home / ".env"
    if target.exists():
        return None
    home.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(env_template(), target)
    return target
