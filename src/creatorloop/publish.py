"""Publishing images, carousels and Reels via the Instagram Graph API (content publishing).

Two explicit steps so nothing goes live by accident:
  prepare(folder)          -> validates and creates media containers, waits until Meta has processed them:
                              images/carousels: convert to JPEG, expose through a temporary tunnel;
                              Reels (one .mp4/.mov in the folder): resumable upload straight to Meta
                              (rupload.facebook.com), tunnel + video_url only as a fallback;
  publish(creation_id)     -> media_publish, returns the permalink.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import struct
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from creatorloop import paths
from creatorloop.graph_client import GraphAPIError
from creatorloop.tunnel import PublicTunnel

log = logging.getLogger(__name__)

CONTENT_ROOT = paths.content_root()
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
MAX_ITEMS = 10
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_MENTIONS = 20
MIN_RATIO, MAX_RATIO = 4 / 5, 1.91  # width / height accepted by Instagram feed
MAX_WIDTH = 1440
MAX_BYTES = 8 * 1024 * 1024
STATUS_POLL_S = 2.0
STATUS_TIMEOUT_S = 120.0

# Reels (developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)
VIDEO_EXT = {".mp4", ".mov"}
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MIN_VIDEO_S, MAX_VIDEO_S = 3.0, 15 * 60.0
MAX_VIDEO_WIDTH = 1920
REEL_POLL_S = 10.0  # video processing takes 30 s … minutes; keep the status calls low
REEL_TIMEOUT_S = 600.0
REEL_DEFAULTS = {"cover_ms": None, "share_to_feed": True, "trial": None}
TRIAL_STRATEGIES = {"MANUAL", "SS_PERFORMANCE"}  # trial_params.graduation_strategy


class PublishError(RuntimeError):
    pass


def resolve_folder(folder: str) -> Path:
    """Folder name inside the content folder, or an absolute path inside it. Nothing outside is allowed."""
    p = Path(folder)
    candidate = (p if p.is_absolute() else CONTENT_ROOT / p).resolve()
    if not candidate.is_relative_to(CONTENT_ROOT.resolve()):
        raise PublishError(f"Folder must be inside the content folder: {CONTENT_ROOT}")
    if not candidate.is_dir():
        raise PublishError(f"Folder not found: {candidate}")
    return candidate


def read_caption(folder: Path) -> str:
    """caption.txt; everything after a line '---' is notes (e.g. alternative hooks) and is not published."""
    f = folder / "caption.txt"
    if not f.exists():
        raise PublishError("No caption given and caption.txt not found in the folder")
    text = f.read_text(encoding="utf-8")
    return re.split(r"^---\s*$", text, maxsplit=1, flags=re.M)[0].strip()


def check_caption(caption: str) -> dict[str, int]:
    stats = {
        "length": len(caption),
        "hashtags": len(re.findall(r"#\w+", caption)),
        "mentions": len(re.findall(r"@[\w.]+", caption)),
    }
    problems = []
    if stats["length"] > MAX_CAPTION:
        problems.append(f"caption is {stats['length']} chars (max {MAX_CAPTION})")
    if stats["hashtags"] > MAX_HASHTAGS:
        problems.append(f"{stats['hashtags']} hashtags (max {MAX_HASHTAGS})")
    if stats["mentions"] > MAX_MENTIONS:
        problems.append(f"{stats['mentions']} mentions (max {MAX_MENTIONS})")
    if problems:
        raise PublishError("Caption rejected: " + "; ".join(problems))
    return stats


def list_images(folder: Path) -> list[Path]:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT and p.is_file())
    if not images:
        raise PublishError(f"No images (.png/.jpg) in {folder}")
    if len(images) > MAX_ITEMS:
        raise PublishError(f"{len(images)} images; a carousel takes at most {MAX_ITEMS}")
    return images


def to_jpegs(images: list[Path], out_dir: Path) -> list[dict[str, Any]]:
    """Instagram accepts only JPEG: convert, check aspect ratio, cap width and size."""
    from PIL import Image  # imported lazily: only publishing needs Pillow

    result = []
    for i, src in enumerate(images, 1):
        with Image.open(src) as im:
            w, h = im.size
            ratio = w / h
            if not (MIN_RATIO - 0.01 <= ratio <= MAX_RATIO + 0.01):
                raise PublishError(f"{src.name}: aspect ratio {w}x{h} is outside 4:5 … 1.91:1")
            rgb = im.convert("RGB")
            if w > MAX_WIDTH:
                rgb = rgb.resize((MAX_WIDTH, round(MAX_WIDTH / ratio)), Image.Resampling.LANCZOS)
            dst = out_dir / f"{i:02d}.jpg"
            for quality in (92, 85, 75):
                rgb.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
                if dst.stat().st_size <= MAX_BYTES:
                    break
            else:
                raise PublishError(f"{src.name}: still larger than 8 MB after compression")
        result.append({"source": src.name, "file": dst.name, "size": f"{w}x{h}", "bytes": dst.stat().st_size})
    return result


def list_videos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT and p.is_file())


def _boxes(f, start: int, end: int):
    """Iterate ISO-BMFF boxes: (type, payload_offset, payload_size, box_offset)."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            break
        yield kind.decode("latin-1"), pos + header, size - header, pos
        pos += size


def mp4_info(path: Path) -> dict[str, Any]:
    """Duration, size and 'moov before mdat' (fast start) from the MP4/MOV headers; no ffmpeg needed."""
    end = path.stat().st_size
    info: dict[str, Any] = {"bytes": end, "duration_s": None, "width": None, "height": None, "faststart": None}
    with path.open("rb") as f:
        top = list(_boxes(f, 0, end))
        order = [k for k, *_ in top]
        if "moov" not in order:
            raise PublishError(f"{path.name}: not a valid MP4/MOV (no moov box)")
        info["faststart"] = "mdat" not in order or order.index("moov") < order.index("mdat")
        _, moov_at, moov_len, _ = top[order.index("moov")]
        for kind, at, length, _ in _boxes(f, moov_at, moov_at + moov_len):
            if kind == "mvhd":
                f.seek(at)
                version = f.read(1)[0]
                if version == 1:
                    f.seek(at + 4 + 16)
                    timescale, duration = struct.unpack(">IQ", f.read(12))
                else:
                    f.seek(at + 4 + 8)
                    timescale, duration = struct.unpack(">II", f.read(8))
                info["duration_s"] = round(duration / timescale, 2) if timescale else None
            elif kind == "trak" and info["width"] is None:
                for sub, sat, slen, _ in _boxes(f, at, at + length):
                    if sub == "tkhd":
                        f.seek(sat + slen - 8)
                        w, h = struct.unpack(">II", f.read(8))
                        if w and h:
                            info["width"], info["height"] = w >> 16, h >> 16
    return info


def check_video(path: Path) -> dict[str, Any]:
    info = mp4_info(path)
    problems = []
    if info["bytes"] > MAX_VIDEO_BYTES:
        problems.append(f"{info['bytes'] / 2**20:.0f} MB (max 300 MB)")
    d = info["duration_s"]
    if d is not None and not (MIN_VIDEO_S <= d <= MAX_VIDEO_S):
        problems.append(f"duration {d:.1f}s (allowed 3 s … 15 min)")
    if info["width"] and info["width"] > MAX_VIDEO_WIDTH:
        problems.append(f"width {info['width']} px (max {MAX_VIDEO_WIDTH})")
    if not info["faststart"]:
        problems.append("moov atom must be at the front: re-mux with `ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`")
    if problems:
        raise PublishError(f"{path.name} rejected: " + "; ".join(problems))
    return {"file": path.name, "mb": round(info["bytes"] / 2**20, 1), "duration_s": d,
            "size": f"{info['width']}x{info['height']}" if info["width"] else None}


def read_reel_settings(folder: Path) -> dict[str, Any]:
    """Optional reel.json: {"cover_ms": 1667, "share_to_feed": true, "trial": null | "MANUAL" | "SS_PERFORMANCE"}.

    trial = Trial Reel: shown to non-followers first. MANUAL = you promote it to followers in the app,
    SS_PERFORMANCE = Instagram promotes it automatically if it performs well.
    """
    settings = dict(REEL_DEFAULTS)
    f = folder / "reel.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PublishError(f"reel.json is not valid JSON: {exc}") from exc
        unknown = set(data) - set(REEL_DEFAULTS)
        if unknown:
            raise PublishError(f"reel.json: unknown keys {sorted(unknown)} (allowed: {', '.join(REEL_DEFAULTS)})")
        settings.update(data)
    if settings["cover_ms"] is not None and (not isinstance(settings["cover_ms"], int) or settings["cover_ms"] < 0):
        raise PublishError("reel.json: cover_ms must be a non-negative integer (milliseconds)")
    if settings["trial"] is not None and settings["trial"] not in TRIAL_STRATEGIES:
        raise PublishError(f"reel.json: trial must be null, {' or '.join(sorted(TRIAL_STRATEGIES))}")
    return settings


class Publisher:
    def __init__(self, service, tunnel_factory: Callable[[Path], Any] = PublicTunnel) -> None:
        self.svc = service
        self.client = service.client
        self.storage = service.storage
        self.tunnel_factory = tunnel_factory

    @property
    def uid(self) -> str:
        return self.svc.uid

    async def limit(self) -> dict[str, Any]:
        body = await self.client.get(f"/{self.uid}/content_publishing_limit", {"fields": "config,quota_usage"})
        data = (body.get("data") or [{}])[0]
        total = (data.get("config") or {}).get("quota_total")
        used = data.get("quota_usage")
        return {"used_24h": used, "limit_24h": total, "remaining": (total - used) if total and used is not None else None}

    async def _wait_finished(self, container_id: str, *, poll: float | None = None, timeout: float | None = None) -> str:
        poll = STATUS_POLL_S if poll is None else poll
        timeout = STATUS_TIMEOUT_S if timeout is None else timeout
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            body = await self.client.get(f"/{container_id}", {"fields": "status_code,status"})
            code = body.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return code
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(f"Container {container_id}: {code} {body.get('status', '')}".strip())
            if asyncio.get_running_loop().time() > deadline:
                raise PublishError(f"Container {container_id} still {code} after {timeout:.0f}s")
            await asyncio.sleep(poll)

    async def prepare(
        self, folder: str, caption: str | None = None, on_stage: Callable[[str], None] = lambda _: None
    ) -> dict[str, Any]:
        on_stage("validating")
        path = resolve_folder(folder)
        caption = caption if caption is not None else read_caption(path)
        stats = check_caption(caption)
        videos = list_videos(path)
        if len(videos) > 1:
            raise PublishError(f"{len(videos)} videos in {path.name}; a Reel takes exactly one .mp4/.mov")
        if videos:
            return await self._prepare_reel(path, videos[0], caption, stats, on_stage)
        images = list_images(path)

        quota = await self._check_quota()

        work = Path(tempfile.mkdtemp(prefix="igpub-"))
        try:
            on_stage("converting to JPEG")
            files = await asyncio.to_thread(to_jpegs, images, work)
            on_stage("starting tunnel")
            async with self.tunnel_factory(work) as base_url:
                on_stage(f"creating containers via {base_url}")
                children: list[str] = []
                if len(files) == 1:
                    body = await self.client.post(
                        f"/{self.uid}/media", {"image_url": f"{base_url}/{files[0]['file']}", "caption": caption}
                    )
                    creation_id = body["id"]
                else:
                    for f in files:
                        body = await self.client.post(
                            f"/{self.uid}/media", {"image_url": f"{base_url}/{f['file']}", "is_carousel_item": "true"}
                        )
                        children.append(body["id"])
                    on_stage("waiting for Meta to process slides")
                    for child in children:
                        await self._wait_finished(child)
                    body = await self.client.post(
                        f"/{self.uid}/media",
                        {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
                    )
                    creation_id = body["id"]
                # Meta copies the media while processing; once FINISHED the tunnel is no longer needed
                on_stage("waiting for the post container")
                status = await self._wait_finished(creation_id)
        except GraphAPIError as exc:
            raise PublishError(f"Graph API rejected the media: {exc}") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)

        kind = "CAROUSEL" if len(files) > 1 else "IMAGE"
        self.storage.save_publication(creation_id, str(path), caption, len(files), kind)
        return {
            "creation_id": creation_id,
            "status": status,
            "type": kind,
            "slides": files,
            "caption_preview": caption[:300] + ("…" if len(caption) > 300 else ""),
            "caption_stats": stats,
            "publishing_limit": quota,
            "next": "Show this to the user. Call publish_media(creation_id) ONLY after an explicit 'publish' from them. "
            "Containers expire after 24h.",
        }

    async def _check_quota(self) -> dict[str, Any]:
        quota = await self.limit()
        if quota["remaining"] is not None and quota["remaining"] <= 0:
            raise PublishError(f"Publishing limit reached: {quota['used_24h']}/{quota['limit_24h']} in 24h")
        return quota

    async def _prepare_reel(
        self, path: Path, video: Path, caption: str, stats: dict[str, int], on_stage: Callable[[str], None]
    ) -> dict[str, Any]:
        info = check_video(video)
        settings = read_reel_settings(path)
        quota = await self._check_quota()
        params: dict[str, Any] = {
            "media_type": "REELS",
            "caption": caption,
            "share_to_feed": "true" if settings["share_to_feed"] else "false",
            "thumb_offset": settings["cover_ms"],
        }
        if settings["trial"]:
            # Trial Reels go to non-followers first, so feed sharing does not apply
            params.pop("share_to_feed")
            params["trial_params"] = json.dumps({"graduation_strategy": settings["trial"]})
        method = "resumable upload"
        try:
            on_stage("creating REELS container")
            body = await self.client.post(f"/{self.uid}/media", {**params, "upload_type": "resumable"})
            creation_id = body["id"]
            on_stage(f"uploading video ({info['mb']} MB)")
            await self.client.upload_video(creation_id, video)
        except GraphAPIError as exc:
            # Fallback: let Meta fetch the file from a temporary public URL (same tunnel as for images)
            log.warning("Resumable upload failed (%s); falling back to video_url via tunnel", exc)
            method = f"tunnel video_url (resumable failed: {exc})"
            creation_id = await self._reel_via_tunnel(video, params, on_stage)
            status = "FINISHED"
        else:
            on_stage("waiting for Meta to process the video")
            status = await self._wait_finished(creation_id, poll=REEL_POLL_S, timeout=REEL_TIMEOUT_S)

        self.storage.save_publication(creation_id, str(path), caption, 1, "REELS")
        ignored = sorted(p.name for p in path.iterdir() if p.suffix.lower() in IMAGE_EXT)
        return {
            "creation_id": creation_id,
            "status": status,
            "type": "REELS",
            "video": info,
            "cover_ms": settings["cover_ms"],
            "share_to_feed": None if settings["trial"] else settings["share_to_feed"],
            "trial": settings["trial"],
            "upload": method,
            "ignored_files": ignored,
            "caption_preview": caption[:300] + ("…" if len(caption) > 300 else ""),
            "caption_stats": stats,
            "publishing_limit": quota,
            "next": "Show this to the user. Call publish_media(creation_id) ONLY after an explicit 'publish' from them. "
            "Containers expire after 24h.",
        }

    async def _reel_via_tunnel(self, video: Path, params: dict[str, Any], on_stage: Callable[[str], None]) -> str:
        work = Path(tempfile.mkdtemp(prefix="igreel-"))
        try:
            name = "reel" + video.suffix.lower()
            await asyncio.to_thread(shutil.copyfile, video, work / name)
            on_stage("starting tunnel")
            async with self.tunnel_factory(work) as base_url:
                on_stage("creating REELS container (video_url)")
                body = await self.client.post(f"/{self.uid}/media", {**params, "video_url": f"{base_url}/{name}"})
                creation_id = body["id"]
                on_stage("waiting for Meta to download and process the video")
                await self._wait_finished(creation_id, poll=REEL_POLL_S, timeout=REEL_TIMEOUT_S)
                return creation_id
        except GraphAPIError as exc:
            raise PublishError(f"Graph API rejected the Reel: {exc}") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def publish(self, creation_id: str) -> dict[str, Any]:
        record = self.storage.get_publication(creation_id)
        if record is None:
            raise PublishError("Unknown creation_id: prepare it with prepare_post first")
        if record["status"] == "published":
            return {"already_published": True, **record}
        await self._wait_finished(creation_id)
        try:
            body = await self.client.post(f"/{self.uid}/media_publish", {"creation_id": creation_id})
        except GraphAPIError as exc:
            self.storage.update_publication(creation_id, status="failed", error=str(exc))
            raise PublishError(f"Publishing failed: {exc}") from exc
        media_id = body["id"]
        info = await self.client.get(f"/{media_id}", {"fields": "permalink,timestamp,media_type"})
        self.storage.update_publication(
            creation_id, status="published", media_id=media_id, permalink=info.get("permalink")
        )
        self.storage.cache_clear("me:")  # profile / media lists changed
        return {"published": True, "media_id": media_id, "permalink": info.get("permalink"), "timestamp": info.get("timestamp")}
