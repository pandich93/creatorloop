"""Parsing tests on response shapes captured from the live Graph API (v26.0)."""

import json
from pathlib import Path

from creatorloop import analytics

from .conftest import json_response

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    data.pop("_source", None)
    return data


async def test_business_discovery_real_shape(make_service):
    body = load("business_discovery_v26.json")
    pages = [body, {"business_discovery": {"followers_count": 144, "media": {"data": []}}}]
    svc = make_service(lambda r: json_response(pages.pop(0)))
    data = await svc.competitor("example.creator", media_limit=5)
    assert data["followers_count"] == 144
    assert [m["view_count"] for m in data["media"]] == [25, 132]
    assert analytics.public_score(data["media"][1]) == ("views", 132)


async def test_media_insights_real_shape(make_service):
    body = load("media_insights_reels_v26.json")
    svc = make_service(lambda r: json_response(body if "metric" in r.url.params else {"id": "1", "username": "me"}))
    ins = await svc.media_insights("18000000000000002", "REELS")
    assert ins["metrics"] == {"reach": 119, "views": 132, "saved": 0, "shares": 3, "ig_reels_avg_watch_time": 5525}
    assert analytics.compact_insights(ins["metrics"])["avg_watch_s"] == 5.5
