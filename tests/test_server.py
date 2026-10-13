import http.client
import json
import os

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from creatorloop import server
from creatorloop.storage import Storage

from .conftest import json_response
from .meta_fakes import FakeAuth

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
    "open_setup",
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
    with pytest.raises(ToolError, match="open_setup") as info:
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


SETUP_KEYS = ("META_APP_ID", "META_APP_SECRET", "IG_ACCESS_TOKEN", "IG_USER_ID")


class FakeOpener:
    """Stands in for setup_web.open_browser: records the urls and returns `ok`."""

    def __init__(self):
        self.calls, self.ok = [], True

    def __call__(self, url, **_):
        self.calls.append(url)
        return self.ok


@pytest.fixture
def opener(monkeypatch):
    fake = FakeOpener()
    monkeypatch.setattr(server.setup_web, "open_browser", fake)
    return fake


@pytest.fixture
def setup_env(tmp_path, monkeypatch, opener):
    monkeypatch.setenv("CREATORLOOP_HOME", str(tmp_path / "home"))
    db = tmp_path / "test.db"
    monkeypatch.setenv("IG_DB_PATH", str(db))
    for key in SETUP_KEYS:
        monkeypatch.setenv(key, "")  # like the empty .env template loaded at server start
    monkeypatch.setattr(server.setup_web, "MetaAuth", lambda i, s, **kw: FakeAuth(i, s))
    monkeypatch.setattr(server, "_setup", None)
    monkeypatch.setattr(server, "_setup_result", None)
    monkeypatch.setattr(server, "_service", None)
    yield db
    if server._setup is not None:
        server._setup.close()


def finish_setup(srv):
    def go(method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        headers = {"Host": f"localhost:{srv.port}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body and json.dumps(body), headers=headers)
        conn.getresponse().read()
        conn.close()

    go("POST", "/api/app", {"app_id": "1234", "app_secret": "secret"})
    go("GET", f"/callback?state={srv.session.state}&code=CODE")


def test_http_client_logs_do_not_print_request_urls():
    """httpx would log GET .../oauth/access_token?client_secret=... at INFO into the server's stderr.
    The logger's own level is checked: under pytest the root level is WARNING anyway, so the effective one proves nothing."""
    import logging

    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).level >= logging.WARNING


async def test_missing_credentials_point_to_open_setup(setup_env):
    with pytest.raises(ToolError) as err:
        await server.get_api_status()
    assert "open_setup" in str(err.value)


async def test_open_setup_returns_one_page_until_done(setup_env):
    first = await server.open_setup(open_browser=False)
    second = await server.open_setup(open_browser=False)
    assert first["url"] == second["url"] and first["url"].startswith("http://localhost:")
    assert "secret" not in json.dumps(first).lower()


async def test_finished_setup_works_without_restart(setup_env):
    await server.open_setup(open_browser=False)
    finish_setup(server._setup)
    status = await server.open_setup()
    assert status == {"done": True, "account": "@me", "token_expires": "2026-12-13"}
    assert os.environ["IG_ACCESS_TOKEN"] == "LONG-TOKEN" and os.environ["IG_USER_ID"] == "1784"
    svc = server.service()
    assert svc.settings.access_token == "LONG-TOKEN" and svc.uid == "1784"


async def test_reconnect_drops_the_cached_token_warning(setup_env):
    storage = Storage(setup_env)
    storage.cache_set("token:status:1784", {"warning": "expires soon"}, 3600)
    await server.open_setup(open_browser=False)
    finish_setup(server._setup)
    assert storage.cache_get("token:status:1784") is None


async def test_open_setup_again_starts_a_new_page(setup_env):
    await server.open_setup(open_browser=False)
    old = server._setup
    finish_setup(old)
    again = await server.open_setup(open_browser=False, again=True)
    assert again["url"] and server._setup is not old


async def test_open_setup_opens_the_browser_once_and_says_so(setup_env, opener):
    page = await server.open_setup()
    assert opener.calls == [page["url"]] and page["opened_in_browser"] is True
    again = await server.open_setup()  # the page is reused: nothing is opened, so nothing is claimed
    assert opener.calls == [page["url"]] and again["url"] == page["url"] and again["opened_in_browser"] is False


async def test_open_setup_without_browser_does_not_open_one(setup_env, opener):
    page = await server.open_setup(open_browser=False)
    assert opener.calls == [] and page["opened_in_browser"] is False


async def test_open_setup_reports_a_browser_that_did_not_start(setup_env, opener):
    opener.ok = False
    page = await server.open_setup()
    assert opener.calls == [page["url"]] and page["opened_in_browser"] is False and page["url"]


async def test_again_never_restarts_an_unfinished_page(setup_env, opener):
    first = await server.open_setup(again=True)
    page = server._setup
    second = await server.open_setup(again=True)
    assert second["url"] == first["url"] and server._setup is page
    assert opener.calls == [first["url"]] and second["opened_in_browser"] is False


async def test_again_after_a_finished_setup_starts_a_new_page(setup_env, opener):
    await server.open_setup(open_browser=False)
    old = server._setup
    finish_setup(old)
    page = await server.open_setup(again=True)
    assert server._setup is not old and old.stopped.is_set() and page["url"] != old.url
    assert opener.calls == [page["url"]] and page["opened_in_browser"] is True


async def test_next_step_tells_the_model_to_confirm_without_again(setup_env):
    page = await server.open_setup(open_browser=False)
    assert "without again" in page["next"]
