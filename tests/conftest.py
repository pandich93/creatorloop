from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from creatorloop.config import Settings
from creatorloop.graph_client import GraphClient
from creatorloop.instagram import InstagramService
from creatorloop.storage import Storage

Handler = Callable[[httpx.Request], httpx.Response]


def json_response(body: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body), headers={"content-type": "application/json", **(headers or {})})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        access_token="TEST",
        ig_user_id="1784",
        api_version="v26.0",
        app_id=None,
        app_secret=None,
        db_path=tmp_path / "test.db",
        timezone=ZoneInfo("Asia/Karachi"),
        ttl_profile_s=60,
        ttl_media_s=60,
        ttl_hashtag_s=60,
    )


@pytest.fixture
def make_service(settings: Settings):
    def factory(handler: Handler) -> InstagramService:
        client = GraphClient(settings.base_url, settings.access_token, transport=httpx.MockTransport(handler), max_retries=2)
        return InstagramService(settings, client, Storage(settings.db_path))

    return factory
