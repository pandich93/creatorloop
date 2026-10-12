"""Publishing queue: you approve a post and a time, the server publishes it then.

Safety rules:
- an item is created only by queue_post(confirm=True), i.e. after the user approved this exact preview;
- at approval the server stores a fingerprint of what will be published (caption before '---', media files,
  reel.json); if anything changed by publish time, the item is BLOCKED instead of published;
- if the server was not running at the slot (laptop asleep, Claude Desktop closed), the post is published
  at most LATE_WINDOW late, otherwise it is marked MISSED and nothing is posted.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from creatorloop.publish import (
    Publisher,
    PublishError,
    check_caption,
    check_video,
    list_images,
    list_videos,
    read_caption,
    read_reel_settings,
    resolve_folder,
    to_jpegs,
)

log = logging.getLogger(__name__)

DEFAULT_SLOTS = "Tue,Thu,Sun 19:00"  # override with QUEUE_SLOTS in .env, local time (TIMEZONE)
LATE_WINDOW = timedelta(hours=3)
MIN_LEAD = timedelta(minutes=5)
MAX_AHEAD = timedelta(days=30)
TICK_S = 60
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# One publish at a time: shared by the queue runner and prepare_post
PUBLISH_LOCK = asyncio.Lock()


class QueueError(RuntimeError):
    pass


# ---------------------------------------------------------------- what exactly gets published
def fingerprint(folder: Path) -> str:
    h = hashlib.sha256(read_caption(folder).encode())
    videos = list_videos(folder)
    files = [videos[0], *[p for p in [folder / "reel.json"] if p.exists()]] if videos else list_images(folder)
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def validate(folder: Path) -> dict[str, Any]:
    """Same local checks as prepare_post, without any API call."""
    caption = read_caption(folder)
    stats = check_caption(caption)
    videos = list_videos(folder)
    if len(videos) > 1:
        raise PublishError(f"{len(videos)} videos in {folder.name}; a Reel takes exactly one .mp4/.mov")
    if videos:
        info = {"type": "REELS", "video": check_video(videos[0]), "reel": read_reel_settings(folder)}
    else:
        images = list_images(folder)
        work = Path(tempfile.mkdtemp(prefix="igq-"))
        try:
            to_jpegs(images, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        info = {"type": "CAROUSEL" if len(images) > 1 else "IMAGE", "slides": [p.name for p in images]}
    first = caption.splitlines()[0] if caption else ""
    return {**info, "caption_hook": first[:150], "caption_stats": stats}


# ---------------------------------------------------------------- time slots
def parse_slots(spec: str | None = None) -> tuple[set[int], int, int]:
    spec = (spec or os.getenv("QUEUE_SLOTS") or DEFAULT_SLOTS).strip()
    m = re.fullmatch(r"([A-Za-z,\s]+)\s+(\d{1,2}):(\d{2})", spec)
    if not m:
        raise QueueError(f"QUEUE_SLOTS must look like '{DEFAULT_SLOTS}', got {spec!r}")
    days = {DAYS.index(d.strip().lower()[:3]) for d in m.group(1).split(",") if d.strip()}
    return days, int(m.group(2)), int(m.group(3))


def next_slots(tz: ZoneInfo, now: datetime, taken: set[datetime], n: int = 3, spec: str | None = None) -> list[datetime]:
    days, hh, mm = parse_slots(spec)
    out: list[datetime] = []
    local = now.astimezone(tz)
    for i in range(0, 60):
        d = (local + timedelta(days=i)).date()
        if d.weekday() not in days:
            continue
        slot = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).astimezone(UTC)
        if slot >= now + MIN_LEAD and slot not in taken:
            out.append(slot)
            if len(out) == n:
                break
    return out


def parse_when(when: str | None, tz: ZoneInfo, now: datetime, taken: set[datetime]) -> datetime:
    """None/'next' = next free default slot; otherwise 'YYYY-MM-DD HH:MM' in local time (or ISO with offset)."""
    if not when or when.strip().lower() == "next":
        slots = next_slots(tz, now, taken, n=1)
        if not slots:
            raise QueueError("No free slot in the next 60 days")
        return slots[0]
    try:
        dt = datetime.fromisoformat(when.strip().replace(" ", "T", 1))
    except ValueError as exc:
        raise QueueError("when must be 'next' or 'YYYY-MM-DD HH:MM' (local time)") from exc
    dt = (dt if dt.tzinfo else dt.replace(tzinfo=tz)).astimezone(UTC)
    if dt < now + MIN_LEAD:
        raise QueueError("Publish time must be at least 5 minutes in the future")
    if dt > now + MAX_AHEAD:
        raise QueueError("Publish time must be within 30 days")
    return dt


def local_str(iso_utc: str, tz: ZoneInfo) -> str:
    return datetime.fromisoformat(iso_utc).astimezone(tz).strftime("%a %Y-%m-%d %H:%M")


# ---------------------------------------------------------------- runner
class QueueRunner:
    """Background loop inside the MCP server process: publishes due items once a minute."""

    def __init__(self, get_service: Callable[[], Any], publisher_factory: Callable[[Any], Publisher] = Publisher):
        self.get_service = get_service
        self.publisher_factory = publisher_factory

    async def run_forever(self) -> None:
        log.info("Publishing queue runner started")
        while True:
            try:
                await self.tick()
            except Exception:  # never let the loop die
                log.exception("Queue tick failed")
            await asyncio.sleep(TICK_S)

    async def tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        try:
            svc = self.get_service()
        except Exception as exc:  # no credentials yet
            log.debug("Queue idle: %s", exc)
            return []
        done = []
        for item in svc.storage.queue_due(now.isoformat(timespec="seconds")):
            done.append(await self._handle(svc, item, now))
        return done

    async def _handle(self, svc, item: dict[str, Any], now: datetime) -> dict[str, Any]:
        qid = item["id"]
        at = datetime.fromisoformat(item["publish_at"])
        st = svc.storage
        if now - at > LATE_WINDOW:
            st.queue_update(qid, status="missed", error=f"server was not running between {item['publish_at']} and "
                            f"+{LATE_WINDOW.seconds // 3600}h; nothing was posted")
            return st.queue_get(qid)
        try:
            folder = resolve_folder(item["folder"])
            if fingerprint(folder) != item["fingerprint"]:
                st.queue_update(qid, status="blocked", error="files or caption changed after approval; nothing was posted")
                return st.queue_get(qid)
        except PublishError as exc:
            st.queue_update(qid, status="blocked", error=str(exc))
            return st.queue_get(qid)

        async with PUBLISH_LOCK:
            st.queue_update(qid, status="publishing")
            pub = self.publisher_factory(svc)
            try:
                prepared = await pub.prepare(item["folder"])
                st.queue_update(qid, creation_id=prepared["creation_id"])
                result = await pub.publish(prepared["creation_id"])
            except Exception as exc:
                log.exception("Queued post %s failed", qid)
                st.queue_update(qid, status="failed", error=str(exc))
                return st.queue_get(qid)
        st.queue_update(qid, status="published", permalink=result.get("permalink"), error=None)
        log.info("Queued post %s published: %s", qid, result.get("permalink"))
        return st.queue_get(qid)
