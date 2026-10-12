"""Automatic post reviews 24 h and 72 h after publishing (own account).

post_reviews() returns every own post that crossed 24 h or 72 h since its last review, with its insights
compared to the median of mature posts (>= 72 h) of the same format, and remembers what was reported,
so a daily scheduled run reports each post exactly twice.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from creatorloop import analytics

STAGES = ((72, "72h"), (24, "24h"))  # highest first
REVIEW_WINDOW_DAYS = 7  # older posts are never reviewed (no backfill of the whole history)
BASELINE_DAYS = 90
COMPARE = ("reach", "views", "saved", "shares", "follows", "likes", "comments", "avg_watch_s")


def stage_for(age_h: float) -> str | None:
    return next((name for hours, name in STAGES if age_h >= hours), None)


async def _with_insights(svc, media: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(5)

    async def one(m: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            ins = await svc.media_insights(m["id"], m.get("media_product_type"), media=m)
        return {**m, "metrics": analytics.compact_insights(ins["metrics"])}

    return list(await asyncio.gather(*(one(m) for m in media)))


def _medians(items: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    by_format: dict[str, list[dict[str, Any]]] = {}
    for m in items:
        by_format.setdefault(analytics.media_format(m), []).append(m)
    return {
        fmt: {"posts": len(group), **{k: analytics._median([g["metrics"].get(k) for g in group]) for k in COMPARE}}
        for fmt, group in by_format.items()
    }


def _compare(metrics: dict[str, Any], median: dict[str, Any] | None) -> dict[str, Any]:
    out = {}
    for k in COMPARE:
        v = metrics.get(k)
        if v is None:
            continue
        base = (median or {}).get(k)
        out[k] = {"value": v, "median": base, "x_median": round(v / base, 2) if base else None}
    return out


async def post_reviews(svc, *, mark_reported: bool = True, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    media = analytics.media_since(await svc.my_media(limit=60, refresh=True), BASELINE_DAYS)
    due = []
    for m in media:
        age = analytics.age_hours(m, now)
        if age is None or age > REVIEW_WINDOW_DAYS * 24:
            continue
        stage = stage_for(age)
        if stage and svc.storage.review_get(m["id"], stage) is None:
            due.append((m, stage, round(age, 1)))
    if not due:
        return {"due": [], "note": "Nothing crossed 24 h / 72 h since the last run."}

    due_ids = {m["id"] for m, *_ in due}
    mature_ids = {  # baseline: mature posts, never the posts being reviewed
        m["id"] for m in media if (analytics.age_hours(m, now) or 0) >= analytics.YOUNG_POST_HOURS
    } - due_ids
    wanted = [m for m in media if m["id"] in mature_ids | due_ids]
    for m, *_ in due:  # the posts under review need fresh numbers, not the 3 h cache
        svc.storage.cache_clear(f"media:insights:{m['id']}")
    enriched = await _with_insights(svc, wanted)
    by_id = {m["id"]: m for m in enriched}
    medians = _medians([m for m in enriched if m["id"] in mature_ids])

    reports = []
    for m, stage, age in due:
        cur = by_id[m["id"]]
        fmt = analytics.media_format(m)
        report: dict[str, Any] = {
            "media_id": m["id"],
            "stage": stage,
            "age_hours": age,
            "format": fmt,
            "permalink": m.get("permalink"),
            "hook": analytics.caption_hook(m.get("caption"), 100),
            "metrics": cur["metrics"],
            "vs_median": _compare(cur["metrics"], medians.get(fmt)),
            "baseline_posts": (medians.get(fmt) or {}).get("posts", 0),
        }
        if stage == "72h" and (prev := svc.storage.review_get(m["id"], "24h")):
            before = json.loads(prev["metrics"] or "{}")
            report["growth_since_24h"] = {
                k: cur["metrics"][k] - before[k]
                for k in COMPARE
                if isinstance(cur["metrics"].get(k), int | float) and isinstance(before.get(k), int | float)
            }
        reports.append(report)
        if mark_reported:
            svc.storage.review_save(m["id"], stage, cur["metrics"])
            if stage == "72h" and svc.storage.review_get(m["id"], "24h") is None:
                svc.storage.review_save(m["id"], "24h", cur["metrics"])  # skipped 24 h: do not report it later
    return {
        "due": reports,
        "baseline": {fmt: {"posts": v["posts"], "median_reach": v["reach"]} for fmt, v in medians.items()},
        "marked_reported": mark_reported,
        "note": "x_median = value / median of own posts of the same format that are >= 72 h old (last 90 days).",
    }
