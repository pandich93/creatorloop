"""MCP server: tool definitions."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from creatorloop import __version__, analytics, comments, post_queue, reviews
from creatorloop.config import load_settings
from creatorloop.graph_client import GraphAPIError, GraphClient
from creatorloop.instagram import InstagramService
from creatorloop.publish import Publisher, PublishError
from creatorloop.refs import RefFinder, previews
from creatorloop.storage import Storage

# stdout is the MCP stdio channel: logs must go to stderr only.
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("creatorloop")

INSTRUCTIONS = """\
creatorloop: a content studio for one Instagram professional account, via the official Instagram Graph API.
Loop: analyse what works -> plan and make posts/Reels -> publish or queue them -> review results after 24/72 h.
- Publishing is always two-step: show the preview and publish only after the user explicitly confirms.
- Own account: full private insights (reach, views, saves, shares, watch time, demographics).
- Competitors: only public counters of professional accounts (followers, likes, comments, Reels views).
  Personal/private accounts cannot be analysed.
- Hashtags: max 30 unique hashtags per rolling 7 days. Check get_api_status before bulk hashtag research.
- Results are cached in SQLite; pass refresh=true to force fresh data.
Answer the user in the language they write in.
"""

_service: InstagramService | None = None
JOBS: dict[str, dict[str, Any]] = {}  # background prepare_post jobs (the device bridge times out calls at 60 s)

PACKAGE_DIR = Path(__file__).resolve().parent


def code_version() -> str:
    """Short hash of the package sources currently on disk."""
    h = hashlib.sha256()
    for f in sorted(PACKAGE_DIR.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def deps_version() -> str:
    """Hash of pyproject.toml + uv.lock: if these change, `uv run` rebuilds the venv on start,
    which fails when Claude Desktop restarts the server — a manual Desktop restart is needed then.
    Empty when installed from PyPI: there is no project to rebuild."""
    files = [f for f in (PACKAGE_DIR.parents[1] / name for name in ("pyproject.toml", "uv.lock")) if f.exists()]
    if not files:
        return ""
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


STARTED_AT = datetime.now(UTC).isoformat(timespec="seconds")
RUNNING_VERSION = code_version()
RUNNING_DEPS = deps_version()


@contextlib.asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
    """Start the publishing-queue runner; close the shared HTTP client when the server stops."""
    runner = asyncio.create_task(post_queue.QueueRunner(service).run_forever())
    try:
        yield
    finally:
        runner.cancel()
        global _service
        if _service is not None:
            await _service.client.aclose()
            _service = None
            log.info("Graph API client closed")


mcp = MCPServer(name="creatorloop", version=__version__, instructions=INSTRUCTIONS, lifespan=lifespan)
RO = ToolAnnotations(readOnlyHint=True, openWorldHint=True)



def tool(**kwargs: Any):
    """mcp.tool + turn expected errors into ToolError, so the model sees the real message
    (mcp 2.x hides the text of any other exception)."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kw: Any) -> Any:
            try:
                result = await fn(*args, **kw)
                if isinstance(result, dict) and _service is not None and fn.__name__ != "get_api_status":
                    if warning := await _service.token_warning():
                        result["token_warning"] = warning
                return result
            except ToolError:
                raise
            except (GraphAPIError, RuntimeError, PublishError) as exc:
                raise ToolError(str(exc)) from exc

        return mcp.tool(**kwargs)(wrapper)

    return decorator


def service() -> InstagramService:
    global _service
    if _service is None:
        settings = load_settings()
        settings.require_credentials()
        client = GraphClient(settings.base_url, settings.access_token)
        _service = InstagramService(settings, client, Storage(settings.db_path))
    return _service


def _compact_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky fields the model never needs (signed CDN avatar URL)."""
    return {k: v for k, v in profile.items() if k != "profile_picture_url"}


# ---- own account -----------------------------------------------------------


@tool(annotations=RO)
async def get_my_profile(refresh: bool = False) -> dict[str, Any]:
    """Own profile: username, bio, followers, following, posts count. Also saves a daily follower snapshot."""
    return _compact_profile(await service().my_profile(refresh=refresh))


@tool(annotations=RO)
async def get_my_media(
    limit: Annotated[int, Field(ge=1, le=500)] = 25,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Latest own posts/Reels (newest first) with public counters: likes, comments, type, permalink, timestamp."""
    return await service().my_media(limit=limit, refresh=refresh)


@tool(annotations=RO)
async def get_media_insights(media_id: str) -> dict[str, Any]:
    """Private insights for ONE own post/Reel/Story: reach, views, saved, shares, profile visits, follows,
    Reels average watch time (ms). Metrics the API refuses are listed in `unavailable`."""
    return await service().media_insights(media_id)


@tool(annotations=RO)
async def get_my_content_report(
    days: Annotated[int, Field(ge=1, le=365, description="Analyse posts published in the last N days")] = 30,
    rank_by: Literal["reach", "views", "saved", "shares", "total_interactions", "engagement_rate"] = "reach",
    max_posts: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Full content report for own account: best/worst posts with hooks, format comparison (Reels vs carousel
    vs image), weighted engagement rate, follows/profile visits per 1k reach, Reels watch time,
    posting frequency, best weekday/hour, most used hashtags, posts still growing (<72h).
    Makes 1 insights request per post (cached), so large max_posts is slower."""
    svc = service()
    enriched = await _own_media_with_insights(days, max_posts)
    report = analytics.summarize_own_media(enriched, svc.settings.timezone, rank_by=rank_by)
    report["period_days"] = days
    report["engagement_rate_formula"] = (
        "sum(likes + comments + saved + shares) / sum(reach) * 100 over the group (weighted, not a mean of ratios)"
    )
    return report


async def _own_media_with_insights(days: int, max_posts: int) -> list[dict[str, Any]]:
    svc = service()
    media = analytics.media_since(await svc.my_media(limit=max_posts), days)
    sem = asyncio.Semaphore(5)

    async def enrich(m: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            ins = await svc.media_insights(m["id"], m.get("media_product_type"), media=m)
        metrics = ins["metrics"]
        return {**m, "insights": metrics, "engagement_rate": analytics.own_engagement_rate(metrics)}

    return list(await asyncio.gather(*(enrich(m) for m in media)))


@tool(annotations=RO)
async def get_caption_insights(
    username: Annotated[str | None, Field(description="Empty = own account (by reach); else a competitor")] = None,
    days: Annotated[int, Field(ge=7, le=365)] = 90,
    max_posts: Annotated[int, Field(ge=5, le=200)] = 50,
) -> dict[str, Any]:
    """What in captions works: language (uz/ru/en), question in the hook, call-to-action, caption length;
    best and worst hooks (first line). Own account is scored by reach, competitors by likes+comments."""
    svc = service()
    if username:
        data = await svc.competitor(username, media_limit=max_posts)
        media = analytics.media_since(data.get("media", []), days)
        result = analytics.caption_breakdown(media, own=False)
        result["username"] = username.lstrip("@").lower()
    else:
        result = analytics.caption_breakdown(await _own_media_with_insights(days, max_posts), own=True)
        result["username"] = await svc.my_username()
    result["period_days"] = days
    return result


@tool(annotations=RO)
async def get_account_insights(
    days: Annotated[int, Field(ge=1, le=90, description="Period length in days, ending yesterday")] = 30,
) -> dict[str, Any]:
    """Account-level totals for the period: reach, views, accounts engaged, interactions, likes, comments,
    saves, shares, link taps, follows/unfollows, plus daily reach. Meta data can lag up to 48h."""
    return await service().account_insights(days)


@tool(annotations=RO)
async def get_audience_demographics(
    breakdown: Literal["country", "city", "age", "gender"] = "country",
    timeframe: Literal["this_week", "this_month", "prev_month", "last_14_days", "last_30_days", "last_90_days"] = "this_month",
    engaged: Annotated[bool, Field(description="True = engaged audience, False = all followers")] = False,
) -> dict[str, Any]:
    """Audience demographics (top 45 rows). Requires 100+ followers (or 100+ engagements for engaged=True)."""
    return await service().demographics(breakdown, timeframe, engaged)


# ---- competitors -----------------------------------------------------------


@tool(annotations=RO)
async def get_competitor(
    username: Annotated[str, Field(description="Instagram username, with or without @")],
    media_limit: Annotated[int, Field(ge=1, le=200)] = 30,
    refresh: bool = False,
) -> dict[str, Any]:
    """Public analysis of another PROFESSIONAL (business/creator) account via Business Discovery:
    profile, ER by followers, formats, posting frequency, best times, hashtags, top/worst posts.
    Saves a daily follower snapshot so growth can be tracked with get_follower_history."""
    svc = service()
    data = await svc.competitor(username, media_limit=media_limit, refresh=refresh)
    media = data.pop("media", [])
    return {
        "profile": _compact_profile(data),
        "analysis": analytics.summarize_public_media(media, data.get("followers_count"), svc.settings.timezone),
    }


@tool(annotations=RO)
async def compare_accounts(
    usernames: Annotated[list[str], Field(min_length=1, max_length=10)],
    include_me: bool = True,
    media_limit: Annotated[int, Field(ge=5, le=100)] = 30,
) -> dict[str, Any]:
    """Side-by-side comparison of up to 10 professional accounts (optionally including own account, measured
    the same public way): followers, posts/week, avg likes/comments/Reels views, ER by followers, main format."""
    svc = service()
    names = [u.lstrip("@").strip().lower() for u in usernames]
    if include_me:
        me = (await svc.my_username()).lower()
        if me not in names:
            names.insert(0, me)

    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for name in names:
        try:
            data = await svc.competitor(name, media_limit=media_limit)
        except Exception as exc:  # one bad username must not break the whole comparison
            errors[name] = str(exc)
            continue
        media = data.get("media", [])
        summary = analytics.summarize_public_media(media, data.get("followers_count"), svc.settings.timezone)
        formats = summary.get("formats") or []
        rows.append(
            {
                "username": name,
                "followers": data.get("followers_count"),
                "posts_total": data.get("media_count"),
                "posts_per_week": (summary.get("frequency") or {}).get("posts_per_week"),
                "avg_likes": summary.get("avg_likes"),
                "avg_comments": summary.get("avg_comments"),
                "avg_views_reels": summary.get("avg_views_reels"),
                "er_by_followers_pct": summary.get("er_by_followers_pct"),
                "main_format": formats[0]["format"] if formats else None,
                "top_post": (summary.get("top_posts") or [None])[0],
            }
        )
    rows.sort(key=lambda r: r["er_by_followers_pct"] or 0, reverse=True)
    return {
        "media_per_account": media_limit,
        "er_formula": "(avg likes + avg comments) / followers * 100",
        "accounts": rows,
        "errors": errors,
    }


@tool(annotations=RO)
async def get_follower_history(
    username: Annotated[str | None, Field(description="Username; empty = own account")] = None,
    days: Annotated[int, Field(ge=2, le=730)] = 90,
) -> dict[str, Any]:
    """Follower growth from local daily snapshots (own account or any competitor fetched before).
    History starts from the first time the account was fetched through this server."""
    svc = service()
    name = (username or await svc.my_username()).lstrip("@").lower()
    result = analytics.follower_growth(svc.storage.get_snapshots(name, days))
    result["username"] = name
    result["tracked_accounts"] = svc.storage.tracked_usernames()
    return result


# ---- tracking & history ----------------------------------------------------


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def track_competitor(
    username: Annotated[str, Field(description="Professional account username, with or without @")],
    note: Annotated[str | None, Field(description="Why you track it, e.g. 'AI-blog, uz'")] = None,
) -> dict[str, Any]:
    """Add an account to the tracked list (validated with one Business Discovery request).
    Tracked accounts are refreshed together by update_tracked_competitors."""
    svc = service()
    name = username.lstrip("@").strip().lower()
    data = await svc.competitor(name, media_limit=25, refresh=True)
    svc.storage.track(name, note)
    return {"tracked": name, "followers": data.get("followers_count"), "tracked_total": len(svc.storage.tracked())}


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
async def untrack_competitor(username: str) -> dict[str, Any]:
    """Remove an account from the tracked list. Its history stays in the database."""
    svc = service()
    removed = svc.storage.untrack(username.lstrip("@").strip())
    return {"removed": removed, "tracked": [t["username"] for t in svc.storage.tracked()]}


@tool(annotations=RO)
async def list_tracked_competitors() -> dict[str, Any]:
    """Tracked accounts with the date added and note."""
    return {"tracked": service().storage.tracked()}


@tool(annotations=RO)
async def update_tracked_competitors(
    media_limit: Annotated[int, Field(ge=5, le=100)] = 25,
    viral_multiplier: Annotated[float, Field(ge=1.5, le=20)] = 3.0,
) -> dict[str, Any]:
    """Refresh all tracked accounts (fresh API data, 1-2 requests each): follower change over the stored history,
    new posts since the previous update and viral posts (score >= multiplier × the account's median).
    Run it regularly (e.g. weekly) to build history."""
    svc = service()
    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for t in svc.storage.tracked():
        name = t["username"]
        known = svc.storage.owner_media_ids(name)
        try:
            data = await svc.competitor(name, media_limit=media_limit, refresh=True)
        except Exception as exc:
            errors[name] = str(exc)
            continue
        media = data.get("media", [])
        growth = analytics.follower_growth(svc.storage.get_snapshots(name, 90))
        new_posts = [analytics._short(m) for m in media if known and m.get("id") not in known]
        rows.append(
            {
                "username": name,
                "followers": data.get("followers_count"),
                "followers_change_90d": growth.get("change"),
                "history_from": growth.get("from"),
                "new_posts_since_last_update": new_posts,
                "viral": analytics.viral_posts(analytics.media_since(media, 90), multiplier=viral_multiplier)["viral"],
            }
        )
    return {"accounts": rows, "errors": errors, "note": "First update of an account cannot detect new posts yet."}


@tool(annotations=RO)
async def find_viral_posts(
    username: Annotated[str | None, Field(description="Empty = all tracked accounts")] = None,
    multiplier: Annotated[float, Field(ge=1.5, le=20)] = 3.0,
    media_limit: Annotated[int, Field(ge=10, le=100)] = 50,
    days: Annotated[int, Field(ge=7, le=730, description="Only posts from the last N days")] = 90,
) -> dict[str, Any]:
    """Posts that outperformed their account: Reels by views, other formats by likes+comments,
    compared with the account's own median. Good source of proven topics and hooks."""
    svc = service()
    names = [username.lstrip("@").strip().lower()] if username else [t["username"] for t in svc.storage.tracked()]
    if not names:
        raise ToolError("No tracked accounts. Pass a username or add accounts with track_competitor.")
    out: dict[str, Any] = {}
    for name in names:
        try:
            data = await svc.competitor(name, media_limit=media_limit)
            media = analytics.media_since(data.get("media", []), days)
            out[name] = analytics.viral_posts(media, multiplier=multiplier)
        except Exception as exc:
            out[name] = {"error": str(exc)}
    return {"accounts": out}


@tool(annotations=RO, structured_output=False)
async def get_competitor_post(
    url: Annotated[str, Field(description="Instagram post/reel URL, e.g. https://www.instagram.com/p/DeCHjDpjuI8/")],
    username: Annotated[
        str | None,
        Field(description="Author's username (required in practice: oEmbed auto-detection needs Meta App Review)"),
    ] = None,
    show_slides: Annotated[bool, Field(description="Return small previews of the slides as images")] = True,
) -> list[Any]:
    """Analyse ONE post of a professional account by its URL, without a browser: caption, hook, likes, comments,
    Reels views, format, how many times better than the account's median, and all slides downloaded to
    <content folder>/_refs/<username>_<code>/ (videos: cover image). With show_slides the slide previews are returned as
    images (up to 20, 400 px wide) so their text and design can be read directly. Pass username: the author can't be
    detected from the URL without Meta App Review. Comment texts are not available via the API."""
    info = await RefFinder(service()).get(url, username)
    result: list[Any] = [info]
    if show_slides and info["files"]:
        folder = Path(info["saved_to"])
        data = await asyncio.to_thread(previews, [folder / f for f in info["files"]])
        info["previews_shown"] = len(data)
        if len(data) < len(info["files"]):
            info["previews_not_shown"] = len(info["files"]) - len(data)
        result += [Image(data=d, format="jpeg") for d in data]
    return result


@tool(annotations=RO)
async def get_post_history(media_id: str) -> dict[str, Any]:
    """Growth curve of one post (own or competitor) from stored snapshots: points by post age,
    gain per day and status growing/plateau. Snapshots are added on every fresh fetch (max 1 per hour)."""
    history = service().storage.media_history(media_id)
    if history is None:
        raise ToolError("No history for this media_id yet. Fetch it first via a report or get_competitor.")
    return analytics.post_growth(history)


# ---- hashtags / trends -----------------------------------------------------


@tool(annotations=RO)
async def search_hashtag(
    hashtag: Annotated[str, Field(description="Hashtag with or without #")],
    mode: Literal["top", "recent"] = "top",
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Top (most popular) or recent (last 24h) public posts for a hashtag, with a trend summary:
    formats, avg likes/comments, related hashtags, caption length, posting times.
    Author usernames are NOT available from the API. Uses 1 of 30 weekly hashtag slots for a new tag."""
    svc = service()
    tag = hashtag.lstrip("#").strip().lower()
    media = await svc.hashtag_media(tag, mode=mode, limit=limit)
    summary = analytics.summarize_public_media(media, None, svc.settings.timezone, min_age_hours=0)
    summary["related_hashtags"] = analytics.top_hashtags(media, limit=20, exclude={tag})
    summary.pop("top_hashtags", None)
    return {"hashtag": f"#{tag}", "mode": mode, "summary": summary, "quota": svc.storage.hashtag_quota()}


@tool(annotations=RO)
async def compare_hashtags(
    hashtags: Annotated[list[str], Field(min_length=2, max_length=10)],
    limit: Annotated[int, Field(ge=10, le=100)] = 50,
) -> dict[str, Any]:
    """Compare several hashtags by their top posts: avg likes/comments, dominant format, Reels share.
    Each NEW hashtag uses 1 of 30 weekly slots; check get_api_status first."""
    svc = service()
    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for raw in hashtags:
        tag = raw.lstrip("#").strip().lower()
        try:
            media = await svc.hashtag_media(tag, mode="top", limit=limit)
        except Exception as exc:
            errors[tag] = str(exc)
            continue
        s = analytics.summarize_public_media(media, None, svc.settings.timezone, min_age_hours=0)
        formats = s.get("formats") or []
        rows.append(
            {
                "hashtag": f"#{tag}",
                "posts_analyzed": s.get("posts_analyzed"),
                "avg_likes": s.get("avg_likes"),
                "avg_comments": s.get("avg_comments"),
                "median_interactions": s.get("median_interactions"),
                "dominant_format": formats[0]["format"] if formats else None,
                "reels_share_pct": next((f["share_pct"] for f in formats if f["format"] == "REELS"), 0.0),
                "related": [h["hashtag"] for h in analytics.top_hashtags(media, 5, exclude={tag})],
            }
        )
    rows.sort(key=lambda r: r["median_interactions"] or 0, reverse=True)
    return {"hashtags": rows, "errors": errors, "quota": svc.storage.hashtag_quota()}


@tool(annotations=RO)
async def plan_hashtag_research(
    hashtags: Annotated[list[str], Field(min_length=1, max_length=30)],
) -> dict[str, Any]:
    """Dry run before search_hashtag / compare_hashtags: which tags are free (queried within the last 7 days),
    which need a new slot out of 30 per week, and whether they all fit. Makes no API calls."""
    return service().storage.plan_hashtags(hashtags)


# ---- publishing ------------------------------------------------------------


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def prepare_post(
    folder: Annotated[str, Field(description="Folder in the content folder (e.g. 'my-first-reel') or an absolute path in it")],
    caption: Annotated[str | None, Field(description="Empty = caption.txt from the folder (text before a '---' line)")] = None,
) -> dict[str, Any]:
    """Step 1 of publishing (does NOT publish). Starts a BACKGROUND job and returns job_id immediately.
    Folder with ONE .mp4/.mov -> Reel: validates the video (3 s-15 min, <=300 MB, moov at front), uploads it straight
    to Meta (resumable upload; tunnel only as fallback), cover frame and feed sharing from optional reel.json
    {"cover_ms": 1667, "share_to_feed": true}; images in that folder are ignored. Processing takes 1-10 min.
    Otherwise 1-10 images (sorted by file name) -> photo/carousel: converts to JPEG, serves them through a temporary
    Cloudflare tunnel, creates containers and waits until Meta has processed them (30-120 s).
    Caption: caption.txt (text before a '---' line). Poll get_post_job(job_id) every ~15-30 s. When done it returns
    creation_id and a preview: show it to the user and call publish_media only after their explicit confirmation."""
    running = [j for j in JOBS.values() if j["status"] == "running"]
    if running:
        raise ToolError(f"Another post is being prepared (job {running[0]['job_id']}). Wait for it to finish.")
    job_id = datetime.now(UTC).strftime("%H%M%S")
    job: dict[str, Any] = {"job_id": job_id, "folder": folder, "status": "running", "stage": "queued",
                           "started_at": datetime.now(UTC).isoformat(timespec="seconds")}
    JOBS[job_id] = job

    def stage(name: str) -> None:
        job["stage"] = name
        log.info("prepare_post %s: %s", job_id, name)

    async def run() -> None:
        try:
            async with post_queue.PUBLISH_LOCK:  # never overlaps with a queued post being published
                job["result"] = await Publisher(service()).prepare(folder, caption, on_stage=stage)
            job["status"] = "done"
        except Exception as exc:  # reported through get_post_job
            log.exception("prepare_post %s failed", job_id)
            job["status"], job["error"] = "failed", str(exc)
        finally:
            job["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")

    job["task"] = asyncio.create_task(run())
    return {"job_id": job_id, "status": "running", "next": "Call get_post_job(job_id) in ~15-30 s."}


@tool(annotations=RO)
async def get_post_job(job_id: str) -> dict[str, Any]:
    """Status of a prepare_post job: running (with current stage), done (with creation_id + preview) or failed."""
    job = JOBS.get(job_id)
    if job is None:
        raise ToolError("Unknown job_id (jobs live only until the server restarts).")
    return {k: v for k, v in job.items() if k != "task"}


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def publish_media(
    creation_id: Annotated[str, Field(description="creation_id returned by prepare_post")],
) -> dict[str, Any]:
    """Step 2: PUBLISHES the prepared post to Instagram (public, irreversible from here).
    Call ONLY after the user explicitly confirmed this exact preview."""
    return await Publisher(service()).publish(creation_id)


@tool(annotations=RO)
async def list_publications(limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict[str, Any]:
    """Prepared and published posts made through this server, plus the 24h publishing quota."""
    svc = service()
    try:
        quota = await Publisher(svc).limit()
    except Exception as exc:
        quota = {"error": str(exc)}
    return {"publications": svc.storage.publications(limit), "publishing_limit": quota}


def _queue_view(item: dict[str, Any]) -> dict[str, Any]:
    tz = service().settings.timezone
    keep = ("id", "folder", "media_type", "caption_head", "status", "permalink", "error")
    return {**{k: item.get(k) for k in keep}, "publish_at_local": post_queue.local_str(item["publish_at"], tz),
            "publish_at_utc": item["publish_at"]}


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
async def queue_post(
    folder: Annotated[str, Field(description="Folder inside the content folder (same as prepare_post)")],
    when: Annotated[str | None, Field(description="'next' / empty = next free slot, or 'YYYY-MM-DD HH:MM' local")] = None,
    confirm: Annotated[bool, Field(description="false = preview only; true = add to the queue (after approval)")] = False,
) -> dict[str, Any]:
    """Schedule a post/carousel/Reel to be PUBLISHED AUTOMATICALLY at a time (default slots Tue/Thu/Sun 19:00 local).
    Call first with confirm=false and show the preview (type, caption hook, local time) to the user. Call again with
    confirm=true ONLY after the user explicitly approved this post AND this time. The server fingerprints caption and
    media: if they change before the slot, the post is blocked. Late by more than 3 h (laptop asleep) = missed."""
    svc = service()
    tz = svc.settings.timezone
    path = post_queue.resolve_folder(folder)
    if active := svc.storage.queue_active_for(str(path)):
        raise ToolError(f"{path.name} is already queued (id {active['id']}, {active['publish_at']}). Cancel it first.")
    now = datetime.now(UTC)
    taken = {datetime.fromisoformat(i["publish_at"]) for i in svc.storage.queue_list()}
    try:
        at = post_queue.parse_when(when, tz, now, taken)
    except post_queue.QueueError as exc:
        raise ToolError(str(exc)) from exc
    check = await asyncio.to_thread(post_queue.validate, path)
    fp = await asyncio.to_thread(post_queue.fingerprint, path)
    at_iso = at.isoformat(timespec="seconds")
    preview = {"folder": str(path), "publish_at_local": post_queue.local_str(at_iso, tz), "publish_at_utc": at_iso,
               "fingerprint": fp, **check}
    if not confirm:
        return {"queued": False, "preview": preview,
                "next": "Show this to the user. Call queue_post(..., confirm=true) with the SAME folder and when "
                "only after they explicitly approve the post and the time."}
    qid = svc.storage.queue_add(str(path), at_iso, fp, check["type"], check["caption_hook"])
    return {"queued": True, "id": qid, **preview,
            "note": "Published automatically while Claude Desktop runs on the laptop. Cancel with cancel_queued(id)."}


@tool(annotations=RO)
async def list_queue(include_done: bool = False) -> dict[str, Any]:
    """Publishing queue: scheduled posts (and with include_done=true also published/failed/missed/blocked/cancelled),
    local times, plus the next free default slots."""
    svc = service()
    items = svc.storage.queue_list(include_done=include_done)
    taken = {datetime.fromisoformat(i["publish_at"]) for i in svc.storage.queue_list()}
    tz = svc.settings.timezone
    free = post_queue.next_slots(tz, datetime.now(UTC), taken, n=3)
    return {"items": [_queue_view(i) for i in items],
            "next_free_slots": [s.astimezone(tz).strftime("%a %Y-%m-%d %H:%M") for s in free],
            "slots_rule": os.getenv("QUEUE_SLOTS") or post_queue.DEFAULT_SLOTS}


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def cancel_queued(queue_id: int) -> dict[str, Any]:
    """Remove a scheduled post from the queue (nothing is deleted on Instagram)."""
    st = service().storage
    item = st.queue_get(queue_id)
    if item is None:
        raise ToolError(f"No queue item {queue_id}")
    if item["status"] != "queued":
        raise ToolError(f"Item {queue_id} is {item['status']}, only queued items can be cancelled")
    st.queue_update(queue_id, status="cancelled")
    return _queue_view(st.queue_get(queue_id))


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def post_reviews(
    mark_reported: Annotated[bool, Field(description="False = just look, do not mark posts as reported")] = True,
) -> dict[str, Any]:
    """Post-mortems for the daily report: own posts (last 7 days) that crossed 24 h or 72 h since the last run,
    with fresh insights vs the median of own mature posts of the same format (x_median), and growth 24 h -> 72 h.
    Each post is reported once per stage. Explain the numbers to the user and give one concrete takeaway."""
    return await reviews.post_reviews(service(), mark_reported=mark_reported)


# ---- comments ----------------------------------------------------------------


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def get_new_comments(
    days: Annotated[int, Field(ge=1, le=90, description="Posts published in the last N days")] = 14,
    only_new: Annotated[bool, Field(description="false = all unanswered, including ones shown before")] = True,
) -> dict[str, Any]:
    """Comments under own posts that you have not answered yet, including follow-ups inside threads you already
    answered (new since the last call by default; they are marked as seen). For each: author, text, post, reply_to
    (the top-level comment to answer in that thread). Draft replies in the comment's language and show them to the
    user; send with reply_comment(reply_to) only after explicit approval. Needs instagram_manage_comments."""
    return await comments.new_comments(service(), days=days, only_new=only_new)


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def reply_comment(
    comment_id: Annotated[str, Field(description="reply_to from get_new_comments (the top-level comment of the thread)")],
    message: Annotated[str, Field(description="Reply text exactly as the user approved it")],
) -> dict[str, Any]:
    """PUBLICLY replies to a comment under your post. Call ONLY after the user explicitly approved this exact text."""
    return await comments.reply(service(), comment_id, message)


# ---- prompts (ready-made report scenarios) ----------------------------------


@mcp.prompt(title="Weekly Instagram report")
def weekly_report(days: str = "7") -> str:
    """Weekly report: account totals, content, competitors, viral posts, 3 actions for next week."""
    return f"""Make a weekly report on my Instagram for the last {days} days.

1. get_api_status — if there is a token warning, start the report with it.
2. get_account_insights(days={days}) — reach, views, accounts engaged, follows/unfollows.
3. get_my_content_report(days=30) — what worked, formats, follows per reach, Reels watch time, posts still growing.
4. update_tracked_competitors — competitors' changes and new posts; if the list is empty, say so.
5. find_viral_posts — competitors' posts that went viral.

Format: the week's 5 key numbers in a table, 3 conclusions (each backed by a number), 3 concrete actions for next week
(format + topic + hook). Do not invent data: if a metric is missing, say it is missing.
Answer in the language I write to you in."""


@mcp.prompt(title="Competitor brief")
def competitor_brief(username: str) -> str:
    """Competitor brief: profile, formats, hooks, viral posts, comparison with me."""
    return f"""Analyse the competitor @{username.lstrip("@")}.

1. get_competitor(username="{username}", media_limit=50) — profile, posting frequency, formats, best time.
2. get_caption_insights(username="{username}") — which hooks, languages and CTAs work for them.
3. find_viral_posts(username="{username}") — their posts that went viral.
4. compare_accounts(usernames=["{username}"], include_me=true) — comparison with me.

Format: a "Them vs Me" table (followers, posts per week, ER by followers, main format),
5 techniques worth adopting (with links to their posts), and 2 things I already do better.
Answer in the language I write to you in."""


@mcp.prompt(title="Data-driven content ideas")
def content_ideas(count: str = "5", language: str = "") -> str:
    """Content ideas grounded in my best posts and competitors' viral posts."""
    lang = f"in {language}" if language.strip() else "in the language of my recent captions"
    return f"""Suggest {count} ideas for my next posts, {lang}.

1. get_my_content_report(days=90) — my best formats and topics.
2. get_caption_insights() — which hooks and caption lengths work for me.
3. find_viral_posts() — what went viral for tracked competitors (skip if the list is empty).

For each idea: format (carousel/Reel), topic, a ready hook (first line), a 3–5 point outline,
and the data it is based on (a specific post or metric). No generic advice.

For Reels apply the first-second rule: frame 0 shows the result or a surprising fact, with no intro, greeting
or logo. For every Reel idea give the first-frame text (up to 6 words) and 2 hook variants for a trial Reel."""


# ---- service ---------------------------------------------------------------


@tool(annotations=RO)
async def get_api_status() -> dict[str, Any]:
    """Diagnostics: token validity, days until expiry (warns 14 days ahead), last rate-limit usage headers,
    hashtag quota for the rolling 7 days, cache location."""
    svc = service()
    try:
        token = await svc.debug_token()
    except Exception as exc:
        token = {"error": str(exc)}
    svc.storage.cache_clear(f"token:status:{svc.uid}")
    disk_version = code_version()
    return {
        "server": {
            "version": __version__,
            "pid": os.getpid(),
            "started_at": STARTED_AT,
            "running_code_version": RUNNING_VERSION,
            "disk_code_version": disk_version,
            "restart_needed": disk_version != RUNNING_VERSION,
            "deps_changed": deps_version() != RUNNING_DEPS,
        },
        "api_version": svc.settings.api_version,
        "ig_user_id": svc.uid,
        "token": token,
        "rate_limit_usage": {
            "x_app_usage": svc.client.usage.app_usage,
            "x_business_use_case_usage": svc.client.usage.business_usage,
            "x_ig_business_use_case_usage": svc.client.usage.instagram_usage,
            "note": "Percent of quota used. Empty until the first API call in this session.",
        },
        "hashtag_quota": svc.storage.hashtag_quota(),
        "database": str(svc.storage.path),
    }


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
async def clear_cache(
    prefix: Annotated[
        str | None, Field(description="me: | media: | bd: | hashtag: ; empty = everything. Snapshots are kept.")
    ] = None,
) -> dict[str, Any]:
    """Drop cached API responses so next calls fetch fresh data. Follower history is not affected."""
    return {"deleted": service().storage.cache_clear(prefix)}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def restart_server(
    exit_code: Annotated[int, Field(ge=0, le=255, description="1 = report as crash (Desktop restarts it)")] = 1,
    force: Annotated[bool, Field(description="Restart even if pyproject.toml/uv.lock changed (will likely fail)")] = False,
) -> dict[str, Any]:
    """Restart this MCP server so updated .py code is loaded, without restarting Claude Desktop.
    The process exits ~1 s after replying; Claude Desktop starts it again on the next call. Use only after a code
    update (get_api_status shows restart_needed=true). Wait 10-20 s before the next call.
    Refuses when dependencies/version changed: then Claude Desktop must be restarted manually."""
    if deps_version() != RUNNING_DEPS and not force:
        raise ToolError(
            "pyproject.toml or uv.lock changed since start: `uv run` would rebuild the environment and the "
            "automatic restart fails. Restart Claude Desktop manually (tray -> Quit -> open)."
        )
    log.warning("restart_server called: exiting with code %s", exit_code)
    asyncio.get_running_loop().call_later(1.0, os._exit, exit_code)
    return {
        "restarting": True,
        "pid": os.getpid(),
        "running_code_version": RUNNING_VERSION,
        "disk_code_version": code_version(),
        "next": "Wait 10-20 s, then call get_api_status and compare pid / running_code_version.",
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
