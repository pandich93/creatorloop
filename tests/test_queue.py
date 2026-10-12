import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from creatorloop import post_queue as pq
from creatorloop import publish as pub
from creatorloop import server

TZ = ZoneInfo("Asia/Karachi")
# Monday 2026-10-05 10:00 Karachi
NOW = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)


@pytest.fixture
def content(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    folder = root / "content" / "demo"
    folder.mkdir(parents=True)
    for i in range(2):
        Image.new("RGB", (1080, 1350), (i * 60, 20, 20)).save(folder / f"s{i}.png")
    (folder / "caption.txt").write_text("Hook\n\nbody #ai\n---\nnotes", encoding="utf-8")
    monkeypatch.setattr(pub, "CONTENT_ROOT", root / "content")
    return folder


def test_slots_and_when():
    slots = pq.next_slots(TZ, NOW, set(), n=3)
    assert [s.astimezone(TZ).strftime("%a %H:%M") for s in slots] == ["Tue 19:00", "Thu 19:00", "Sun 19:00"]
    assert pq.parse_when("next", TZ, NOW, {slots[0]}) == slots[1]  # taken slot is skipped
    assert pq.parse_when("2026-10-07 08:30", TZ, NOW, set()) == datetime(2026, 10, 7, 3, 30, tzinfo=UTC)
    with pytest.raises(pq.QueueError, match="future"):
        pq.parse_when("2026-10-05 09:00", TZ, NOW, set())
    with pytest.raises(pq.QueueError, match="30 days"):
        pq.parse_when("2026-12-25 10:00", TZ, NOW, set())
    assert pq.parse_slots("Mon, Fri 08:15") == ({0, 4}, 8, 15)


def test_fingerprint_ignores_notes_but_not_caption(content):
    fp = pq.fingerprint(content)
    (content / "caption.txt").write_text("Hook\n\nbody #ai\n---\nother notes", encoding="utf-8")
    assert pq.fingerprint(content) == fp
    (content / "caption.txt").write_text("Hook!\n\nbody #ai", encoding="utf-8")
    assert pq.fingerprint(content) != fp
    assert pq.validate(content)["type"] == "CAROUSEL"


class FakePublisher:
    calls: list = []

    def __init__(self, svc):
        pass

    async def prepare(self, folder):
        FakePublisher.calls.append(("prepare", folder))
        return {"creation_id": "c1"}

    async def publish(self, cid):
        FakePublisher.calls.append(("publish", cid))
        return {"permalink": "https://www.instagram.com/p/Q/"}


async def test_runner_publishes_blocks_and_misses(make_service, content):
    svc = make_service(lambda r: None)
    st = svc.storage
    fp = pq.fingerprint(content)
    due = (NOW - timedelta(minutes=1)).isoformat(timespec="seconds")
    ok = st.queue_add(str(content), due, fp, "CAROUSEL", "Hook")
    late = st.queue_add(str(content), (NOW - timedelta(hours=4)).isoformat(timespec="seconds"), fp, "CAROUSEL", "Hook")
    future = st.queue_add(str(content), (NOW + timedelta(hours=1)).isoformat(timespec="seconds"), fp, "CAROUSEL", "H")
    FakePublisher.calls = []
    runner = pq.QueueRunner(lambda: svc, publisher_factory=FakePublisher)
    await runner.tick(NOW)
    assert st.queue_get(ok)["status"] == "published" and st.queue_get(ok)["permalink"].endswith("/Q/")
    assert st.queue_get(late)["status"] == "missed"
    assert st.queue_get(future)["status"] == "queued"
    assert FakePublisher.calls == [("prepare", str(content)), ("publish", "c1")]

    (content / "caption.txt").write_text("Changed hook", encoding="utf-8")
    await runner.tick(NOW + timedelta(hours=1, minutes=1))
    assert st.queue_get(future)["status"] == "blocked"
    assert len(FakePublisher.calls) == 2  # nothing more was published


async def test_queue_tools_preview_then_confirm(make_service, content, monkeypatch):
    svc = make_service(lambda r: None)
    monkeypatch.setattr(server, "_service", svc)

    def payload(res):
        return res.structured_content or json.loads(res.content[0].text)

    prev = payload(await server.mcp.call_tool("queue_post", {"folder": "demo", "when": "next"}))
    assert prev["queued"] is False and prev["preview"]["type"] == "CAROUSEL"
    assert svc.storage.queue_list() == []
    done = payload(await server.mcp.call_tool("queue_post", {"folder": "demo", "when": "next", "confirm": True}))
    assert done["queued"] is True
    listed = payload(await server.mcp.call_tool("list_queue", {}))
    assert listed["items"][0]["status"] == "queued" and len(listed["next_free_slots"]) == 3
    with pytest.raises(Exception, match="already queued"):
        await server.mcp.call_tool("queue_post", {"folder": "demo", "confirm": True})
    cancelled = payload(await server.mcp.call_tool("cancel_queued", {"queue_id": done["id"]}))
    assert cancelled["status"] == "cancelled"
