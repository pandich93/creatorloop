import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from creatorloop import server

from .conftest import json_response

EXPECTED_TOOLS = {
    "get_my_profile",
    "get_my_media",
    "get_media_insights",
    "get_my_content_report",
    "get_account_insights",
    "get_audience_demographics",
    "get_competitor",
    "compare_accounts",
    "get_follower_history",
    "search_hashtag",
    "compare_hashtags",
    "get_api_status",
    "clear_cache",
    "track_competitor",
    "untrack_competitor",
    "list_tracked_competitors",
    "update_tracked_competitors",
    "find_viral_posts",
    "get_post_history",
    "get_caption_insights",
    "plan_hashtag_research",
    "restart_server",
    "prepare_post",
    "get_post_job",
    "publish_media",
    "list_publications",
    "get_competitor_post",
    "post_reviews",
    "queue_post",
    "list_queue",
    "cancel_queued",
    "get_new_comments",
    "reply_comment",
}


async def test_tools_registered():
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert t.description, t.name


async def test_compare_accounts_end_to_end(make_service, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        fields = request.url.params["fields"]
        if fields.startswith("id,username"):
            return json_response({"id": "1784", "username": "me", "followers_count": 100})
        name = fields.split("username(")[1].split(")")[0]
        if name == "ghost":
            return json_response({"error": {"message": "Invalid user id", "code": 110}}, 400)
        followers = {"me": 100, "rival": 1000}[name]
        media = {"data": [{"id": f"{name}{i}", "media_type": "IMAGE", "timestamp": f"2026-09-0{i + 1}T10:00:00+0000",
                           "like_count": 10 * (i + 1), "comments_count": 1} for i in range(3)]}
        return json_response({"business_discovery": {"username": name, "followers_count": followers, "media": media}})

    monkeypatch.setattr(server, "_service", make_service(handler))
    result = await server.mcp.call_tool("compare_accounts", {"usernames": ["@rival", "ghost"], "media_limit": 5})
    payload = result.structured_content or json.loads(result.content[0].text)
    names = [a["username"] for a in payload["accounts"]]
    assert names == ["me", "rival"]  # me: 21% ER, rival: 2.1%
    assert "ghost" in payload["errors"]


async def test_api_errors_reach_the_model(make_service, monkeypatch):
    svc = make_service(lambda r: json_response({"error": {"message": "Session has expired", "code": 190}}, 400))
    monkeypatch.setattr(server, "_service", svc)
    # MCPServer.call_tool raises ToolError; over stdio it becomes isError=True with this text.
    with pytest.raises(ToolError, match="IG_ACCESS_TOKEN") as info:
        await server.mcp.call_tool("get_my_profile", {})
    assert not isinstance(info.value, UnexpectedToolError)


async def test_token_warning_attached_to_tool_results(make_service, monkeypatch):
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/debug_token"):
            return json_response({"data": {"is_valid": True, "expires_at": int(time.time()) + 3 * 86400}})
        return json_response({"id": "1784", "username": "me", "followers_count": 1})

    monkeypatch.setattr(server, "_service", make_service(handler))
    result = await server.mcp.call_tool("get_my_profile", {})
    payload = result.structured_content or json.loads(result.content[0].text)
    assert "expires in" in payload["token_warning"]


async def test_tracking_flow_detects_new_posts(make_service, monkeypatch):
    state = {"posts": ["p1", "p2"]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/debug_token"):
            return json_response({"data": {"is_valid": True}})
        media = {"data": [{"id": p, "media_type": "IMAGE", "timestamp": "2026-08-01T10:00:00+0000",
                           "like_count": 5, "comments_count": 0} for p in state["posts"]]}
        return json_response({"business_discovery": {"username": "rival", "followers_count": 10, "media": media}})

    monkeypatch.setattr(server, "_service", make_service(handler))
    await server.mcp.call_tool("track_competitor", {"username": "@Rival"})
    state["posts"] = ["p3", "p1", "p2"]
    result = await server.mcp.call_tool("update_tracked_competitors", {})
    payload = result.structured_content or json.loads(result.content[0].text)
    acc = payload["accounts"][0]
    assert acc["username"] == "rival"
    assert [p["id"] for p in acc["new_posts_since_last_update"]] == ["p3"]

    hist = await server.mcp.call_tool("get_post_history", {"media_id": "p1"})
    hist_payload = hist.structured_content or json.loads(hist.content[0].text)
    assert hist_payload["media"]["owner"] == "rival"


async def test_prompts_registered():
    prompts = await server.mcp.list_prompts()
    assert {p.name for p in prompts} == {"weekly_report", "competitor_brief", "content_ideas"}


async def test_restart_server_schedules_exit(monkeypatch):
    calls = []

    class FakeLoop:
        def call_later(self, delay, fn, *args):
            calls.append((delay, fn, args))

    monkeypatch.setattr(server.asyncio, "get_running_loop", lambda: FakeLoop())
    result = await server.mcp.call_tool("restart_server", {"exit_code": 1})
    payload = result.structured_content or json.loads(result.content[0].text)
    assert payload["restarting"] is True
    assert calls == [(1.0, server.os._exit, (1,))]


def test_deps_version_is_stable_without_project_files(tmp_path, monkeypatch):
    # installed from PyPI: no pyproject.toml / uv.lock next to the package, so deps never "change"
    monkeypatch.setattr(server, "PACKAGE_DIR", tmp_path / "site-packages" / "creatorloop")
    assert server.deps_version() == ""


def test_code_version_is_stable():
    assert server.code_version() == server.RUNNING_VERSION


async def test_restart_refused_when_deps_changed(monkeypatch):
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(server, "deps_version", lambda: "changed")
    with pytest.raises(ToolError, match="manually"):
        await server.mcp.call_tool("restart_server", {})


async def test_prepare_post_runs_as_background_job(monkeypatch):
    import asyncio

    async def fake_prepare(self, folder, caption=None, on_stage=lambda _: None):
        on_stage("starting tunnel")
        await asyncio.sleep(0.05)
        return {"creation_id": "c9"}

    monkeypatch.setattr(server.Publisher, "prepare", fake_prepare)
    from types import SimpleNamespace

    monkeypatch.setattr(server, "service", lambda: SimpleNamespace(client=None, storage=None))
    server.JOBS.clear()
    started = await server.mcp.call_tool("prepare_post", {"folder": "demo"})
    job = (started.structured_content or json.loads(started.content[0].text))["job_id"]
    await asyncio.sleep(0.1)
    res = await server.mcp.call_tool("get_post_job", {"job_id": job})
    payload = res.structured_content or json.loads(res.content[0].text)
    assert payload["status"] == "done" and payload["result"]["creation_id"] == "c9"


async def test_prompts_are_in_english():
    import re

    cyrillic = re.compile(r"[Ѐ-ӿ]")
    for p in await server.mcp.list_prompts():
        assert not cyrillic.search(p.title or ""), p.name
    texts = [server.weekly_report(), server.competitor_brief("someone"), server.content_ideas()]
    assert not any(cyrillic.search(t) for t in texts)
    assert "content/_rules" not in "".join(texts)


async def test_api_status_reports_package_version(make_service, monkeypatch):
    import json

    import creatorloop

    from .conftest import json_response

    svc = make_service(lambda r: json_response({"data": {"is_valid": True, "expires_at": 0, "scopes": []}}))
    monkeypatch.setattr(server, "_service", svc)
    res = await server.mcp.call_tool("get_api_status", {})
    payload = res.structured_content or json.loads(res.content[0].text)
    assert payload["server"]["version"] == creatorloop.__version__
