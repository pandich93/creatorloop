import json
from datetime import UTC, datetime, timedelta

import httpx

from creatorloop import reviews

from .conftest import json_response

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


MEDIA = [
    {"id": "r_new", "media_type": "VIDEO", "media_product_type": "REELS", "timestamp": ts(30), "caption": "Hook A\nbody"},
    {"id": "c_mid", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "timestamp": ts(80), "caption": "Hook B"},
    {"id": "c_old1", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "timestamp": ts(300), "caption": "x"},
    {"id": "c_old2", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "timestamp": ts(500), "caption": "y"},
    {"id": "r_old", "media_type": "VIDEO", "media_product_type": "REELS", "timestamp": ts(400), "caption": "z"},
    {"id": "too_young", "media_type": "IMAGE", "media_product_type": "FEED", "timestamp": ts(5), "caption": "w"},
]
REACH = {"r_new": 400, "c_mid": 900, "c_old1": 100, "c_old2": 300, "r_old": 200, "too_young": 1}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/media"):
        return json_response({"data": MEDIA})
    if path.endswith("/insights"):
        mid = path.split("/")[-2]
        data = [{"name": "reach", "values": [{"value": REACH[mid]}]}, {"name": "saved", "values": [{"value": 5}]}]
        return json_response({"data": data})
    return json_response({"id": "1784", "username": "me"})


async def test_reviews_report_each_stage_once(make_service):
    svc = make_service(handler)
    first = await reviews.post_reviews(svc, now=NOW)
    got = {r["media_id"]: r for r in first["due"]}
    assert set(got) == {"r_new", "c_mid"}  # old posts are never backfilled, 5 h is too young
    assert got["r_new"]["stage"] == "24h" and got["c_mid"]["stage"] == "72h"
    assert got["c_mid"]["vs_median"]["reach"] == {"value": 900, "median": 200.0, "x_median": 4.5}
    assert got["r_new"]["vs_median"]["reach"]["x_median"] == 2.0  # vs the one mature Reel
    assert svc.storage.review_get("c_mid", "24h") is not None  # skipped 24 h is marked too

    again = await reviews.post_reviews(svc, now=NOW)
    assert again["due"] == []

    REACH["r_new"] = 700
    later = await reviews.post_reviews(svc, now=NOW + timedelta(hours=45))
    r = {x["media_id"]: x for x in later["due"]}["r_new"]
    assert r["stage"] == "72h" and r["growth_since_24h"]["reach"] == 300
    assert json.loads(svc.storage.review_get("r_new", "72h")["metrics"])["reach"] == 700


async def test_peek_does_not_mark(make_service):
    svc = make_service(handler)
    await reviews.post_reviews(svc, now=NOW, mark_reported=False)
    assert svc.storage.review_get("r_new", "24h") is None
