"""Pure analytics over media lists. No I/O here, easy to unit-test."""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

HASHTAG_RE = re.compile(r"#([\wЀ-ӿ]+)", re.UNICODE)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_ts(value: str) -> datetime:
    # Graph API format: 2026-10-01T12:34:56+0000
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def media_format(m: dict[str, Any]) -> str:
    """REELS / CAROUSEL / IMAGE / VIDEO / STORY."""
    if m.get("media_product_type") in ("REELS", "STORY"):
        return m["media_product_type"]
    match m.get("media_type"):
        case "CAROUSEL_ALBUM":
            return "CAROUSEL"
        case "VIDEO":
            return "VIDEO"
        case "IMAGE":
            return "IMAGE"
        case other:
            return other or "UNKNOWN"


def hashtags(caption: str | None) -> list[str]:
    return [t.lower() for t in HASHTAG_RE.findall(caption or "")]


def interactions(m: dict[str, Any]) -> int | None:
    """Public interactions (likes + comments). None if likes are hidden."""
    likes = m.get("like_count")
    if likes is None:
        return None
    return likes + (m.get("comments_count") or 0)


def _avg(values: list[float | int | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(statistics.fmean(clean), 1) if clean else None


def _median(values: list[float | int | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(statistics.median(clean), 1) if clean else None


YOUNG_POST_HOURS = 72  # insights keep growing and lag up to 48h; fresh posts distort averages


def age_hours(m: dict[str, Any], now: datetime | None = None) -> float | None:
    if not m.get("timestamp"):
        return None
    return ((now or datetime.now(UTC)) - parse_ts(m["timestamp"])).total_seconds() / 3600


def split_by_age(
    media: list[dict[str, Any]], min_age_hours: float = YOUNG_POST_HOURS
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(mature, young). Posts without timestamp count as mature."""
    if min_age_hours <= 0:
        return list(media), []
    mature, young = [], []
    for m in media:
        age = age_hours(m)
        (young if age is not None and age < min_age_hours else mature).append(m)
    return mature, young


def own_interactions(metrics: dict[str, Any]) -> int:
    return sum(metrics.get(k) or 0 for k in ("likes", "comments", "saved", "shares"))


def weighted_engagement_rate(items: list[dict[str, Any]]) -> float | None:
    """Σ(likes+comments+saved+shares) / Σreach * 100 — robust to tiny-reach posts."""
    reach = sum((m.get("insights") or {}).get("reach") or 0 for m in items)
    if not reach:
        return None
    total = sum(own_interactions(m.get("insights") or {}) for m in items)
    return round(100 * total / reach, 2)


def _views(m: dict[str, Any]) -> int | None:
    if m.get("view_count") is not None:
        return m["view_count"]
    return (m.get("insights") or {}).get("views")


def _short(m: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    caption = (m.get("caption") or "").replace("\n", " ")
    return {
        "id": m.get("id"),
        "format": media_format(m),
        "timestamp": m.get("timestamp"),
        "permalink": m.get("permalink"),
        "caption": caption[:120] + ("…" if len(caption) > 120 else ""),
        "likes": m.get("like_count"),
        "comments": m.get("comments_count"),
        "views": _views(m),
        **(extra or {}),
    }


KEY_INSIGHTS = ("reach", "views", "likes", "comments", "saved", "shares", "follows", "profile_visits")


def compact_insights(ins: dict[str, Any]) -> dict[str, Any]:
    out = {k: ins[k] for k in KEY_INSIGHTS if ins.get(k) is not None}
    if ins.get("ig_reels_avg_watch_time"):
        out["avg_watch_s"] = round(ins["ig_reels_avg_watch_time"] / 1000, 1)
    return out


def posting_frequency(media: list[dict[str, Any]]) -> dict[str, Any]:
    stamps = sorted(parse_ts(m["timestamp"]) for m in media if m.get("timestamp"))
    if len(stamps) < 2:
        return {"posts": len(stamps), "posts_per_week": None, "span_days": 0}
    span_days = max((stamps[-1] - stamps[0]).total_seconds() / 86400, 1)
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(stamps, stamps[1:], strict=False)]
    return {
        "posts": len(stamps),
        "span_days": round(span_days, 1),
        "posts_per_week": round(len(stamps) / span_days * 7, 2),
        "median_gap_days": round(statistics.median(gaps), 2),
        "first_post": stamps[0].isoformat(),
        "last_post": stamps[-1].isoformat(),
    }


def best_times(media: list[dict[str, Any]], tz: ZoneInfo, score_key=interactions) -> dict[str, Any]:
    by_day: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[int, list[float]] = defaultdict(list)
    for m in media:
        score = score_key(m)
        if score is None or not m.get("timestamp"):
            continue
        local = parse_ts(m["timestamp"]).astimezone(tz)
        by_day[WEEKDAYS[local.weekday()]].append(score)
        by_hour[local.hour].append(score)

    def rank(groups: dict[Any, list[float]]) -> list[dict[str, Any]]:
        rows = [{"slot": k, "posts": len(v), "avg_score": round(statistics.fmean(v), 1)} for k, v in groups.items()]
        return sorted(rows, key=lambda r: r["avg_score"], reverse=True)

    return {
        "timezone": str(tz),
        "by_weekday": rank(by_day),
        "by_hour": rank(by_hour),
        "note": "Small samples (posts < 3 per slot) are noise, not a pattern.",
    }


def format_breakdown(media: list[dict[str, Any]], followers: int | None = None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in media:
        groups[media_format(m)].append(m)
    rows = []
    for fmt, items in groups.items():
        inter = [interactions(m) for m in items]
        row = {
            "format": fmt,
            "posts": len(items),
            "share_pct": round(100 * len(items) / len(media), 1),
            "avg_likes": _avg([m.get("like_count") for m in items]),
            "avg_comments": _avg([m.get("comments_count") for m in items]),
            "avg_views": _avg([m.get("view_count") for m in items]),
            "median_interactions": _median(inter),
        }
        if followers:
            avg_inter = _avg(inter)
            row["er_by_followers_pct"] = round(100 * avg_inter / followers, 2) if avg_inter is not None else None
        rows.append(row)
    return sorted(rows, key=lambda r: r["posts"], reverse=True)


def top_hashtags(media: list[dict[str, Any]], limit: int = 15, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for m in media:
        counter.update(set(hashtags(m.get("caption"))) - (exclude or set()))
    return [{"hashtag": f"#{tag}", "posts": n} for tag, n in counter.most_common(limit)]


def summarize_public_media(
    media: list[dict[str, Any]],
    followers: int | None,
    tz: ZoneInfo,
    top_n: int = 5,
    min_age_hours: float = YOUNG_POST_HOURS,
) -> dict[str, Any]:
    """Analysis based on public counters only (competitors, hashtags).
    Posts younger than min_age_hours are reported separately as still growing."""
    if not media:
        return {"posts_analyzed": 0}
    all_media = media
    media, young = split_by_age(media, min_age_hours)
    if not media:
        return {"posts_analyzed": 0, "still_growing": [_short(m) for m in young]}
    inter = [interactions(m) for m in media]
    hidden = sum(1 for v in inter if v is None)
    avg_inter = _avg(inter)
    ranked = sorted((m for m in media if interactions(m) is not None), key=interactions, reverse=True)
    captions = [len(m.get("caption") or "") for m in media]
    return {
        "posts_analyzed": len(media),
        "avg_likes": _avg([m.get("like_count") for m in media]),
        "avg_comments": _avg([m.get("comments_count") for m in media]),
        "avg_views_reels": _avg([m.get("view_count") for m in media if media_format(m) == "REELS"]),
        "median_interactions": _median(inter),
        "er_by_followers_pct": round(100 * avg_inter / followers, 2) if followers and avg_inter is not None else None,
        "posts_with_hidden_likes": hidden,
        "avg_caption_length": round(statistics.fmean(captions)) if captions else 0,
        "frequency": posting_frequency(all_media),
        "formats": format_breakdown(media, followers),
        "best_times": best_times(media, tz),
        "top_hashtags": top_hashtags(all_media),
        "top_posts": [_short(m) for m in ranked[:top_n]],
        "worst_posts": [_short(m) for m in ranked[-top_n:][::-1]] if len(ranked) > top_n else [],
        "still_growing": [_short(m) for m in young],
    }


def own_engagement_rate(metrics: dict[str, Any]) -> float | None:
    """(likes + comments + saved + shares) / reach * 100."""
    reach = metrics.get("reach")
    if not reach:
        return None
    return round(100 * own_interactions(metrics) / reach, 2)


def summarize_own_media(
    media_with_insights: list[dict[str, Any]],
    tz: ZoneInfo,
    rank_by: str = "reach",
    top_n: int = 5,
    min_age_hours: float = YOUNG_POST_HOURS,
) -> dict[str, Any]:
    """Analysis of own media where private insights (reach, saves, shares, views) are available.
    Posts younger than min_age_hours are excluded from averages and rankings and listed as still growing."""
    if not media_with_insights:
        return {"posts_analyzed": 0}
    mature, young = split_by_age(media_with_insights, min_age_hours)

    def metric(m: dict[str, Any], key: str) -> float | None:
        if key == "engagement_rate":
            return m.get("engagement_rate")
        return (m.get("insights") or {}).get(key)

    by_format: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in mature:
        by_format[media_format(m)].append(m)

    formats = []
    for fmt, items in by_format.items():
        formats.append(
            {
                "format": fmt,
                "posts": len(items),
                "avg_reach": _avg([metric(m, "reach") for m in items]),
                "median_reach": _median([metric(m, "reach") for m in items]),
                "avg_views": _avg([metric(m, "views") for m in items]),
                "avg_saved": _avg([metric(m, "saved") for m in items]),
                "avg_shares": _avg([metric(m, "shares") for m in items]),
                "engagement_rate_pct": weighted_engagement_rate(items),
            }
        )
    formats.sort(key=lambda r: r["avg_reach"] or 0, reverse=True)

    ranked = sorted(
        (m for m in mature if metric(m, rank_by) is not None),
        key=lambda m: metric(m, rank_by),
        reverse=True,
    )

    def short(m: dict[str, Any]) -> dict[str, Any]:
        f = caption_features(m)
        row = _short(
            m,
            {
                "hook": f["hook"],
                "language": f["language"],
                "insights": compact_insights(m.get("insights") or {}),
                "engagement_rate_pct": m.get("engagement_rate"),
            },
        )
        row.pop("caption", None)  # the hook (first line) is enough; keeps responses small
        return row

    return {
        "posts_analyzed": len(mature),
        "ranked_by": rank_by,
        "avg_reach": _avg([metric(m, "reach") for m in mature]),
        "median_reach": _median([metric(m, "reach") for m in mature]),
        "engagement_rate_pct": weighted_engagement_rate(mature),
        "frequency": posting_frequency(media_with_insights),
        "formats": formats,
        "best_times_by_reach": best_times(mature, tz, score_key=lambda m: metric(m, "reach")),
        "top_hashtags": top_hashtags(media_with_insights),
        "top_posts": [short(m) for m in ranked[:top_n]],
        "worst_posts": [short(m) for m in ranked[-top_n:][::-1]] if len(ranked) > top_n else [],
        "conversion": conversion_by_format(mature),
        "reels_watch": reels_watch(mature),
        "still_growing": [short(m) for m in young],
        "young_post_threshold_hours": min_age_hours,
    }


def follower_growth(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    points = [s for s in snapshots if s.get("followers_count") is not None]
    if len(points) < 2:
        return {
            "points": points,
            "change": None,
            "note": "Need at least 2 days of snapshots. They are saved automatically every time the profile is fetched.",
        }
    first, last = points[0], points[-1]
    days = max((datetime.fromisoformat(last["captured_on"]) - datetime.fromisoformat(first["captured_on"])).days, 1)
    change = last["followers_count"] - first["followers_count"]
    return {
        "from": first["captured_on"],
        "to": last["captured_on"],
        "followers_start": first["followers_count"],
        "followers_end": last["followers_count"],
        "change": change,
        "change_pct": round(100 * change / first["followers_count"], 2) if first["followers_count"] else None,
        "avg_per_day": round(change / days, 1),
        "points": points,
    }


def media_since(media: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC).timestamp() - days * 86400
    return [m for m in media if m.get("timestamp") and parse_ts(m["timestamp"]).timestamp() >= cutoff]


# ---- viral posts & growth curves ----------------------------------------------


def public_score(m: dict[str, Any]) -> tuple[str, int | None]:
    """Reels are compared by views (if available), everything else by likes + comments."""
    if media_format(m) == "REELS" and m.get("view_count") is not None:
        return "views", m["view_count"]
    return "interactions", interactions(m)


def viral_posts(
    media: list[dict[str, Any]], multiplier: float = 3.0, min_age_hours: float = 24, limit: int = 10
) -> dict[str, Any]:
    """Posts whose score is >= multiplier × the account's median for the same score kind."""
    mature, _ = split_by_age(media, min_age_hours)
    groups: dict[str, list[tuple[dict[str, Any], int]]] = defaultdict(list)
    for m in mature:
        kind, score = public_score(m)
        if score is not None:
            groups[kind].append((m, score))

    medians = {kind: statistics.median(s for _, s in items) for kind, items in groups.items() if items}
    hits = []
    for kind, items in groups.items():
        median = medians[kind]
        if not median:
            continue
        for m, score in items:
            ratio = score / median
            if ratio >= multiplier:
                hits.append({**_short(m), "score_kind": kind, "score": score, "x_median": round(ratio, 1)})
    hits.sort(key=lambda h: h["x_median"], reverse=True)
    return {
        "multiplier": multiplier,
        "medians": {k: round(v, 1) for k, v in medians.items()},
        "posts_checked": len(mature),
        "viral": hits[:limit],
    }


def post_growth(history: dict[str, Any]) -> dict[str, Any]:
    """Growth curve of one post from stored snapshots."""
    meta = history["media"]
    published = parse_ts(meta["published_at"]) if meta.get("published_at") else None
    points = []
    for snap in history["snapshots"]:
        at = datetime.fromisoformat(snap["captured_at"])
        age = round((at - published).total_seconds() / 3600, 1) if published else None
        points.append({"age_hours": age, **{k: v for k, v in snap.items() if v is not None}})

    result: dict[str, Any] = {"media": meta, "snapshots": len(points), "points": points}
    if len(points) >= 2:
        first, last = points[0], points[-1]
        hours = max(
            (datetime.fromisoformat(last["captured_at"]) - datetime.fromisoformat(first["captured_at"])).total_seconds()
            / 3600,
            1e-9,
        )
        per_day = {}
        for key in ("reach", "views", "likes", "comments", "saved", "shares"):
            if isinstance(first.get(key), int) and isinstance(last.get(key), int):
                per_day[key] = round((last[key] - first[key]) / hours * 24, 1)
        result["gain_per_day"] = per_day
        main = per_day.get("reach", per_day.get("views", per_day.get("likes")))
        base = last.get("reach") or last.get("views") or last.get("likes") or 0
        result["status"] = "growing" if main and base and main / base >= 0.02 else "plateau"
    else:
        result["note"] = "One snapshot so far. Each fresh fetch adds a point (at most one per hour)."
    return result


# ---- captions, hooks, conversion ----------------------------------------------

UZ_CYRILLIC = set("ўқғҳЎҚҒҲ")
# Uzbek written in Russian letters (no ў/қ): typical suffixes and words
UZ_CYRILLIC_RE = re.compile(
    r"(миз|ингиз|лар|нинг|даги|гача|япти|моқда|ман|чилик)(е*)\b"
    r"|\b(ва|бу|учун|эмас|билан|нима|керак|бир|эди|экан|бор|йук)\b",
    re.I,
)
UZ_LATIN_RE = re.compile(
    r"([og]['ʻ’`])|([a-z]['ʻ’][aeiou])|\b(va|bu|uchun|emas|bilan|qanday|nega|nima|men|siz|kerak|ham|yoki|lekin|endi|hamma)\b"
    r"|\w(lar|ning|dagi|ish|ga|da|ni|gacha|adi|ladi|yapti|moqda|miz|siz)\b",
    re.I,
)
CTA_RE = re.compile(
    r"(saqla|obuna|izoh|yozing|havola|link|sohran|сохран|подпиш|пиши|напиши|коммент|ссылк|"
    r"save|follow|comment|share|dm\b|direct|директ|ulash|do'stlaringiz)",
    re.I,
)
LENGTH_BUCKETS = ((0, "none"), (1, "short <80"), (80, "medium 80-300"), (300, "long 300+"))


def caption_language(text: str | None) -> str:
    """Heuristic uz / ru / en / unknown. Uzbek Cyrillic is detected by ў қ ғ ҳ."""
    t = text or ""
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return "unknown"
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    if cyr / len(letters) > 0.5:
        return "uz" if UZ_CYRILLIC & set(t) or UZ_CYRILLIC_RE.search(t) else "ru"
    return "uz" if len(UZ_LATIN_RE.findall(t)) >= 2 else "en"


def caption_hook(text: str | None, limit: int = 150) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def caption_features(m: dict[str, Any]) -> dict[str, Any]:
    text = m.get("caption") or ""
    hook = caption_hook(text)
    length = len(text)
    bucket = next(label for start, label in reversed(LENGTH_BUCKETS) if length >= start)
    return {
        "hook": hook,
        "language": caption_language(text),
        "hook_is_question": hook.endswith("?") or "?" in hook,
        "has_question": "?" in text,
        "has_cta": bool(CTA_RE.search(text)),
        "hook_has_number": bool(re.search(r"\d", hook)),
        "length": length,
        "length_bucket": bucket,
        "hashtags": len(hashtags(text)),
    }


def _own_score(m: dict[str, Any]) -> float | None:
    return (m.get("insights") or {}).get("reach")


def caption_breakdown(media: list[dict[str, Any]], *, own: bool, min_age_hours: float = YOUNG_POST_HOURS) -> dict[str, Any]:
    """Compare posts by caption traits. Own posts: median reach + weighted ER; public: median likes+comments."""
    mature, _ = split_by_age(media, min_age_hours)
    feats = [(m, caption_features(m)) for m in mature]

    def group(key: str) -> list[dict[str, Any]]:
        buckets: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for m, f in feats:
            buckets[f[key]].append(m)
        rows = []
        for value, items in buckets.items():
            row: dict[str, Any] = {"value": value, "posts": len(items)}
            if own:
                row["median_reach"] = _median([_own_score(m) for m in items])
                row["engagement_rate_pct"] = weighted_engagement_rate(items)
            else:
                row["median_interactions"] = _median([interactions(m) for m in items])
                row["median_views"] = _median([m.get("view_count") for m in items])
            rows.append(row)
        sort_key = "median_reach" if own else "median_interactions"
        return sorted(rows, key=lambda r: r.get(sort_key) or 0, reverse=True)

    score = _own_score if own else interactions
    ranked = sorted((mf for mf in feats if score(mf[0]) is not None), key=lambda mf: score(mf[0]), reverse=True)
    return {
        "posts_analyzed": len(feats),
        "by_language": group("language"),
        "by_hook_question": group("hook_is_question"),
        "by_cta": group("has_cta"),
        "by_length": group("length_bucket"),
        "best_hooks": [
            {"hook": f["hook"], "format": media_format(m), "score": score(m), "language": f["language"],
             "permalink": m.get("permalink")}
            for m, f in ranked[:7]
        ],
        "worst_hooks": [
            {"hook": f["hook"], "format": media_format(m), "score": score(m), "language": f["language"]}
            for m, f in ranked[-5:][::-1]
        ]
        if len(ranked) > 7
        else [],
        "score": "reach" if own else "likes+comments",
        "note": "Language and CTA detection are heuristics. Groups with < 3 posts are anecdotes.",
    }


def conversion_by_format(media: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Profile visits and follows per 1000 reach (FEED/STORY expose them; Reels do not)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in media:
        groups[media_format(m)].append(m)
    rows = []
    for fmt, items in groups.items():
        ins = [m.get("insights") or {} for m in items]
        reach = sum(i.get("reach") or 0 for i in ins)
        follows = [i.get("follows") for i in ins if i.get("follows") is not None]
        visits = [i.get("profile_visits") for i in ins if i.get("profile_visits") is not None]
        if not reach or (not follows and not visits):
            continue
        rows.append(
            {
                "format": fmt,
                "posts": len(items),
                "follows_per_1k_reach": round(1000 * sum(follows) / reach, 2) if follows else None,
                "profile_visits_per_1k_reach": round(1000 * sum(visits) / reach, 2) if visits else None,
                "total_follows": sum(follows) if follows else None,
            }
        )
    return sorted(rows, key=lambda r: r["follows_per_1k_reach"] or 0, reverse=True)


def reels_watch(media: list[dict[str, Any]]) -> dict[str, Any] | None:
    reels = [m for m in media if media_format(m) == "REELS"]
    if not reels:
        return None
    ins = [m.get("insights") or {} for m in reels]
    avg_ms = [i.get("ig_reels_avg_watch_time") for i in ins]
    total_ms = [i.get("ig_reels_video_view_total_time") for i in ins if i.get("ig_reels_video_view_total_time")]
    skip = [i.get("reels_skip_rate") for i in ins]
    top = sorted(
        (m for m in reels if (m.get("insights") or {}).get("ig_reels_avg_watch_time")),
        key=lambda m: m["insights"]["ig_reels_avg_watch_time"],
        reverse=True,
    )[:3]
    return {
        "reels": len(reels),
        "avg_watch_time_s": round(_avg(avg_ms) / 1000, 1) if _avg(avg_ms) else None,
        "median_watch_time_s": round(_median(avg_ms) / 1000, 1) if _median(avg_ms) else None,
        "total_watch_hours": round(sum(total_ms) / 3_600_000, 1) if total_ms else None,
        "avg_skip_rate_pct": _avg(skip),
        "longest_watched": [
            {
                "hook": caption_hook(m.get("caption")),
                "avg_watch_time_s": round(m["insights"]["ig_reels_avg_watch_time"] / 1000, 1),
                "permalink": m.get("permalink"),
            }
            for m in top
        ],
    }
