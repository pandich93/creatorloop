import httpx
import pytest

from creatorloop.graph_client import RateLimitError, TokenError
from creatorloop.storage import HASHTAG_LIMIT

from .conftest import json_response


async def test_rate_limit_not_retried(make_service):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response({"error": {"message": "Application request limit reached", "code": 4}}, 400)

    svc = make_service(handler)
    with pytest.raises(RateLimitError):
        await svc.my_profile()
    assert calls == 1


async def test_token_error(make_service):
    svc = make_service(lambda r: json_response({"error": {"message": "Session has expired", "code": 190}}, 400))
    with pytest.raises(TokenError, match="open_setup"):
        await svc.my_profile()


async def test_retry_on_transient(make_service, monkeypatch):
    monkeypatch.setattr("creatorloop.graph_client.asyncio.sleep", _no_sleep)
    responses = [
        json_response({"error": {"message": "temporary", "code": 2, "is_transient": True}}, 500),
        json_response({"id": "1784", "username": "me", "followers_count": 10}),
    ]
    svc = make_service(lambda r: responses.pop(0))
    profile = await svc.my_profile()
    assert profile["username"] == "me"
    # snapshot saved
    assert svc.storage.get_snapshots("me", 1)[0]["followers_count"] == 10


async def test_usage_headers_recorded(make_service):
    svc = make_service(
        lambda r: json_response({"id": "1", "username": "me"}, headers={"x-app-usage": '{"call_count": 12}'})
    )
    await svc.my_profile()
    assert svc.client.usage.app_usage == {"call_count": 12}


async def test_business_discovery_fallback_and_pagination(make_service):
    seen_fields: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fields = request.url.params["fields"]
        seen_fields.append(fields)
        if "view_count" in fields:
            err = {"message": "(#100) Tried accessing nonexisting field (view_count)", "code": 100}
            return json_response({"error": err}, 400)
        if ".after(" not in fields:
            media = {"data": [{"id": "a", "timestamp": "2026-09-01T10:00:00+0000", "like_count": 1}],
                     "paging": {"cursors": {"after": "CUR"}}}
        else:
            media = {"data": [{"id": "b", "timestamp": "2026-09-02T10:00:00+0000", "like_count": 2}]}
        return json_response({"business_discovery": {"username": "rival", "followers_count": 500, "media": media}, "id": "1784"})

    svc = make_service(handler)
    data = await svc.competitor("@Rival", media_limit=2)
    assert [m["id"] for m in data["media"]] == ["a", "b"]
    assert data["followers_count"] == 500
    assert "business_discovery.username(rival)" in seen_fields[-1]
    assert svc.storage.get_snapshots("rival", 1)[0]["followers_count"] == 500


async def test_media_insights_per_metric_fallback(make_service):
    def handler(request: httpx.Request) -> httpx.Response:
        if "metric" not in request.url.params:  # profile lookup for the snapshot owner
            return json_response({"id": "1784", "username": "me"})
        metric = request.url.params["metric"]
        if "," in metric or metric == "ig_reels_video_view_total_time":
            return json_response({"error": {"message": "(#100) metric not supported", "code": 100}}, 400)
        return json_response({"data": [{"name": metric, "values": [{"value": 7}]}]})

    svc = make_service(handler)
    ins = await svc.media_insights("m1", "REELS")
    assert ins["metrics"]["reach"] == 7
    assert "ig_reels_video_view_total_time" in ins["unavailable"]
    history = svc.storage.media_history("m1")
    assert history["media"]["owner"] == "me" and history["snapshots"][0]["reach"] == 7


async def test_hashtag_quota(make_service):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ig_hashtag_search"):
            return json_response({"data": [{"id": "h-" + request.url.params["q"]}]})
        return json_response({"data": [{"id": "x", "like_count": 1, "comments_count": 0}]})

    svc = make_service(handler)
    for i in range(HASHTAG_LIMIT):
        svc.storage.register_hashtag(f"tag{i}", f"id{i}")
    # already-known tag is still allowed
    assert await svc.hashtag_id("#tag0") == "id0"
    with pytest.raises(RuntimeError, match="quota exhausted"):
        await svc.hashtag_id("brandnew")


async def _no_sleep(_):
    return None


async def test_my_media_cache_serves_smaller_limits(make_service):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response({"data": [{"id": str(i)} for i in range(int(request.url.params["limit"]))]})

    svc = make_service(handler)
    assert len(await svc.my_media(limit=30)) == 30
    assert len(await svc.my_media(limit=10)) == 10
    assert calls == 1


async def test_debug_token_warns_before_expiry(make_service):
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "TEST"  # self-inspection, no app secret needed
        return json_response({"data": {"is_valid": True, "type": "USER", "expires_at": int(time.time()) + 5 * 86400,
                                        "data_access_expires_at": int(time.time()) + 80 * 86400}})

    svc = make_service(handler)
    status = await svc.debug_token()
    assert status["days_left"] == 5.0 and "5.0 days" in status["warning"]
    assert await svc.token_warning() == status["warning"]


async def test_unsupported_metrics_are_remembered(make_service):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "metric" not in request.url.params:
            return json_response({"id": "1784", "username": "me"})
        metric = request.url.params["metric"]
        calls.append(metric)
        if "reels_skip_rate" in metric:
            return json_response({"error": {"message": "(#100) metric not supported", "code": 100}}, 400)
        return json_response({"data": [{"name": n, "values": [{"value": 1}]} for n in metric.split(",")]})

    svc = make_service(handler)
    await svc.media_insights("a", "REELS")
    calls.clear()
    await svc.media_insights("b", "REELS")
    assert len(calls) == 1 and "reels_skip_rate" not in calls[0]  # one bulk call, skip_rate excluded


def test_plan_hashtags(make_service):
    svc = make_service(lambda r: json_response({}))
    svc.storage.register_hashtag("ai", "1")
    plan = svc.storage.plan_hashtags(["#AI", "dasturchi", "#ai"])
    assert plan["free_already_queried"] == ["#ai"] and plan["new_slots_needed"] == ["#dasturchi"]
    assert plan["remaining_after"] == 28 and plan["fits_in_quota"]
