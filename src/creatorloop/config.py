"""Settings loaded from environment variables / .env files (see creatorloop.paths for locations)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from creatorloop import paths

DEFAULT_API_VERSION = "v26.0"


def _load_env() -> None:
    # Real environment variables win (override=False), then the user's home .env, then ./.env (development).
    # Claude Desktop starts the process with an arbitrary cwd, so the home .env is the one that matters.
    load_dotenv(paths.home_dir() / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)


def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name.strip()) if name.strip() else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def system_timezone(localtime: Path = Path("/etc/localtime"), timezone_file: Path = Path("/etc/timezone")) -> tzinfo:
    """The computer's timezone: TZ, the /etc/localtime link (macOS, Linux), /etc/timezone (Debian),
    else the current fixed UTC offset (Windows; set IG_TIMEZONE there to get daylight-saving changes right)."""
    if tz := _zone(os.getenv("TZ", "").lstrip(":")):
        return tz
    try:
        target = str(localtime.resolve(strict=True))
        if "zoneinfo/" in target and (tz := _zone(target.split("zoneinfo/", 1)[1])):
            return tz
    except OSError:
        pass
    try:
        if tz := _zone(timezone_file.read_text(encoding="utf-8")):
            return tz
    except OSError:
        pass
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True, slots=True)
class Settings:
    access_token: str
    ig_user_id: str
    api_version: str
    app_id: str | None
    app_secret: str | None
    db_path: Path
    timezone: tzinfo
    ttl_profile_s: int
    ttl_media_s: int
    ttl_hashtag_s: int

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"

    def require_credentials(self) -> None:
        missing = [name for name, value in (("IG_ACCESS_TOKEN", self.access_token), ("IG_USER_ID", self.ig_user_id)) if not value]
        if missing:
            raise RuntimeError(
                f"Missing required settings: {', '.join(missing)}. Connect your Instagram account: call the open_setup "
                "tool, or run `uvx --from creatorloop creatorloop-auth login` in a terminal."
            )


def _configured_timezone() -> tzinfo:
    raw = os.getenv("IG_TIMEZONE", "").strip()
    if not raw:
        return system_timezone()
    if tz := _zone(raw):
        return tz
    raise RuntimeError(f"IG_TIMEZONE={raw!r} is not a known timezone; use an IANA name like 'Europe/Berlin'.")


def load_settings() -> Settings:
    _load_env()
    db_raw = os.getenv("IG_DB_PATH", "").strip()
    db_path = Path(db_raw).expanduser() if db_raw else paths.home_dir() / "creatorloop.db"
    return Settings(
        access_token=os.getenv("IG_ACCESS_TOKEN", "").strip(),
        ig_user_id=os.getenv("IG_USER_ID", "").strip(),
        api_version=os.getenv("GRAPH_API_VERSION", DEFAULT_API_VERSION).strip() or DEFAULT_API_VERSION,
        app_id=os.getenv("META_APP_ID", "").strip() or None,
        app_secret=os.getenv("META_APP_SECRET", "").strip() or None,
        db_path=db_path,
        timezone=_configured_timezone(),
        ttl_profile_s=_int("CACHE_TTL_PROFILE_MIN", 60) * 60,
        ttl_media_s=_int("CACHE_TTL_MEDIA_MIN", 180) * 60,
        ttl_hashtag_s=_int("CACHE_TTL_HASHTAG_MIN", 360) * 60,
    )
