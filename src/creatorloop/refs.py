"""Reference posts: find a competitor's post by URL via Business Discovery and download its slides."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import statistics
from pathlib import Path
from typing import Any

import httpx

from creatorloop import analytics, paths
from creatorloop.graph_client import GraphAPIError

log = logging.getLogger(__name__)

REFS_ROOT = paths.refs_root()
SHORTCODE_RE = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")
CHILD_FIELDS = "media_type,media_url,thumbnail_url"
FIELDS_EXTENDED = (
    "id,permalink,caption,media_type,media_product_type,timestamp,like_count,comments_count,view_count,"
    f"media_url,thumbnail_url,children{{{CHILD_FIELDS}}}"
)
FIELDS_BASE = "id,permalink,caption,media_type,timestamp,like_count,comments_count,media_url,children{media_type,media_url}"
PAGE_SIZE = 50
MAX_PAGES = 4


class RefError(RuntimeError):
    pass


def shortcode_from_url(url: str) -> str:
    m = SHORTCODE_RE.search(url)
    if not m:
        raise RefError("Not an Instagram post URL (expected .../p/<code>/, /reel/<code>/ or /tv/<code>/)")
    return m.group(1)


class RefFinder:
    def __init__(self, service, http: httpx.AsyncClient | None = None) -> None:
        self.svc = service
        self.client = service.client
        self._http = http

    async def author_from_oembed(self, url: str) -> str:
        try:
            body = await self.client.get("/instagram_oembed", {"url": url, "fields": "author_name"})
        except GraphAPIError as exc:
            log.info("oEmbed unavailable: %s", exc)
            raise RefError(
                "Pass username: the author can't be detected from the URL "
                "(Meta oEmbed needs App Review). Take it from the profile link."
            ) from exc
        name = body.get("author_name")
        if not name:
            raise RefError("Pass username: oEmbed returned no author.")
        return name.lstrip("@").lower()

    async def _pages(self, username: str, fields: str):
        after: str | None = None
        profile: dict[str, Any] = {}
        for _ in range(MAX_PAGES):
            edge = f"media.limit({PAGE_SIZE})" + (f".after({after})" if after else "")
            q = f"business_discovery.username({username}){{followers_count,media_count,{edge}{{{fields}}}}}"
            body = await self.client.get(f"/{self.svc.uid}", {"fields": q})
            bd = body.get("business_discovery", {})
            if not profile:
                profile = {"followers_count": bd.get("followers_count"), "media_count": bd.get("media_count")}
            chunk = bd.get("media", {})
            yield profile, chunk.get("data", [])
            after = chunk.get("paging", {}).get("cursors", {}).get("after")
            if not after or not chunk.get("data"):
                return

    async def find(self, username: str, shortcode: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        """(post, profile, all media seen). Retries with base fields if extended ones are rejected."""
        for fields in (FIELDS_EXTENDED, FIELDS_BASE):
            seen: list[dict[str, Any]] = []
            try:
                async for profile, items in self._pages(username, fields):
                    seen.extend(items)
                    for m in items:
                        if f"/{shortcode}" in (m.get("permalink") or ""):
                            return m, profile, seen
            except GraphAPIError as exc:
                if exc.code == 100 and "field" in exc.message.lower() and fields is FIELDS_EXTENDED:
                    log.info("Extended reference fields rejected (%s); retrying with base fields", exc)
                    continue
                raise
            raise RefError(
                f"Post {shortcode} not found among the last {len(seen)} posts of @{username}. "
                "It may be older, deleted, or from another account."
            )
        raise RefError("Unreachable")  # pragma: no cover

    @staticmethod
    def slide_urls(post: dict[str, Any]) -> list[tuple[str, str]]:
        """[(kind, url)] in slide order; videos give their cover image when available."""
        items = (post.get("children") or {}).get("data") or [post]
        out = []
        for it in items:
            if it.get("media_type") == "VIDEO":
                url = it.get("thumbnail_url")
                if url:
                    out.append(("video-cover", url))
            elif it.get("media_url"):
                out.append(("image", it["media_url"]))
        return out

    async def download(self, urls: list[tuple[str, str]], folder: Path) -> list[Path]:
        folder.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(5)
        http = self._http or httpx.AsyncClient(timeout=20, follow_redirects=True)

        async def one(i: int, url: str) -> Path:
            async with sem:
                r = await http.get(url)
                r.raise_for_status()
            path = folder / f"{i:02d}.jpg"
            path.write_bytes(r.content)
            return path

        try:
            return list(await asyncio.gather(*(one(i, u) for i, (_, u) in enumerate(urls, 1))))
        finally:
            if self._http is None:
                await http.aclose()

    async def get(self, url: str, username: str | None, *, download: bool = True) -> dict[str, Any]:
        code = shortcode_from_url(url)
        name = (username or "").lstrip("@").strip().lower() or await self.author_from_oembed(url)
        post, profile, seen = await self.find(name, code)

        kind, score = analytics.public_score(post)
        same_kind = [s for m in seen if (s := analytics.public_score(m))[0] == kind and s[1] is not None]
        median = statistics.median(v for _, v in same_kind) if same_kind else None
        urls = self.slide_urls(post)
        files: list[Path] = []
        if download and urls:
            files = await self.download(urls, REFS_ROOT / f"{name}_{code}")
        feats = analytics.caption_features(post)
        return {
            "username": name,
            "shortcode": code,
            "permalink": post.get("permalink"),
            "timestamp": post.get("timestamp"),
            "format": analytics.media_format(post),
            "likes": post.get("like_count"),
            "comments": post.get("comments_count"),
            "views": post.get("view_count"),
            "score_kind": kind,
            "score": score,
            "account_median": round(median, 1) if median is not None else None,
            "x_median": round(score / median, 1) if score is not None and median else None,
            "followers": profile.get("followers_count"),
            "hook": feats["hook"],
            "language": feats["language"],
            "has_cta": feats["has_cta"],
            "caption": post.get("caption"),
            "slides": len(urls),
            "saved_to": str(files[0].parent) if files else None,
            "files": [p.name for p in files],
            "note": "Comment texts of other accounts are not available via the API.",
        }


PREVIEW_LIMIT = 20  # Instagram app carousels hold up to 20 slides
PREVIEW_WIDTH = 400


def previews(files: list[Path], width: int = PREVIEW_WIDTH, limit: int = PREVIEW_LIMIT) -> list[bytes]:
    """Small JPEG previews to return inline as images (keeps the MCP response small)."""
    from PIL import Image

    out = []
    for p in files[:limit]:
        with Image.open(p) as im:
            im = im.convert("RGB")
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=70, optimize=True)
            out.append(buf.getvalue())
    return out
