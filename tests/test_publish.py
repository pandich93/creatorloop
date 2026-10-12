import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from PIL import Image

from creatorloop import publish as pub
from creatorloop.publish import Publisher, PublishError
from creatorloop.tunnel import PublicTunnel

from .conftest import json_response


@pytest.fixture
def content(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    folder = root / "content" / "demo"
    folder.mkdir(parents=True)
    for i in range(3):
        Image.new("RGB", (1080, 1350), (i * 40, 30, 30)).save(folder / f"slide_{i + 1:02d}.png")
    (folder / "caption.txt").write_text("Hook line\n\nBody #ai #dasturchi\n---\nAlt hooks: not published", encoding="utf-8")
    monkeypatch.setattr(pub, "CONTENT_ROOT", root / "content")
    monkeypatch.setattr(pub, "STATUS_POLL_S", 0)
    return folder


class FakeTunnel:
    served: list[str] = []

    def __init__(self, directory: Path):
        self.directory = directory

    async def __aenter__(self):
        FakeTunnel.served = sorted(p.name for p in self.directory.iterdir())
        return "https://demo.trycloudflare.com"

    async def __aexit__(self, *exc):
        return None


def graph_handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        form = dict(httpx.QueryParams(request.content.decode())) if request.method == "POST" else {}
        calls.append((request.method, path, form))
        if path.endswith("/content_publishing_limit"):
            return json_response({"data": [{"config": {"quota_total": 50}, "quota_usage": 2}]})
        if request.method == "POST" and path.endswith("/media"):
            n = sum(1 for c in calls if c[0] == "POST" and c[1].endswith("/media"))
            return json_response({"id": f"c{n}"})
        if request.method == "POST" and path.endswith("/media_publish"):
            return json_response({"id": "m1"})
        if path.endswith("/m1"):
            return json_response({"permalink": "https://www.instagram.com/p/X/", "timestamp": "2026-10-05T10:00:00+0000"})
        if "status_code" in request.url.params.get("fields", ""):
            return json_response({"status_code": "FINISHED"})
        return json_response({"id": "1784", "username": "me"})

    return handler


async def test_prepare_and_publish_carousel(make_service, content):
    calls: list = []
    svc = make_service(graph_handler(calls))
    p = Publisher(svc, tunnel_factory=FakeTunnel)

    prepared = await p.prepare("demo")
    assert prepared["type"] == "CAROUSEL" and len(prepared["slides"]) == 3
    assert FakeTunnel.served == ["01.jpg", "02.jpg", "03.jpg"]  # PNG converted to JPEG, ordered
    posts = [c for c in calls if c[0] == "POST"]
    assert posts[0][2]["image_url"] == "https://demo.trycloudflare.com/01.jpg" and posts[0][2]["is_carousel_item"] == "true"
    carousel = posts[3][2]
    assert carousel["media_type"] == "CAROUSEL" and carousel["children"] == "c1,c2,c3"
    assert carousel["caption"] == "Hook line\n\nBody #ai #dasturchi"  # notes after '---' dropped
    assert not any(c[1].endswith("/media_publish") for c in calls)  # prepare never publishes

    result = await p.publish(prepared["creation_id"])
    assert result["permalink"] == "https://www.instagram.com/p/X/"
    assert svc.storage.get_publication("c4")["status"] == "published"
    again = await p.publish("c4")  # idempotent: no second post
    assert again["already_published"] is True
    assert sum(1 for c in calls if c[1].endswith("/media_publish")) == 1


async def test_publish_post_is_not_retried(make_service, content, monkeypatch):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path.endswith("/media_publish"):
            attempts += 1
            return json_response({"error": {"message": "temporary", "code": 2, "is_transient": True}}, 500)
        return graph_handler([])(request)

    monkeypatch.setattr("creatorloop.graph_client.asyncio.sleep", _no_sleep)
    svc = make_service(handler)
    p = Publisher(svc, tunnel_factory=FakeTunnel)
    prepared = await p.prepare("demo")
    with pytest.raises(PublishError):
        await p.publish(prepared["creation_id"])
    assert attempts == 1
    assert svc.storage.get_publication(prepared["creation_id"])["status"] == "failed"


def test_validation(content, tmp_path):
    with pytest.raises(PublishError, match="inside the content folder"):
        pub.resolve_folder(str(tmp_path))
    with pytest.raises(PublishError, match="hashtags"):
        pub.check_caption(" ".join(f"#t{i}" for i in range(31)))
    Image.new("RGB", (1080, 1920)).save(content / "slide_99.png")  # 9:16 is not allowed in the feed
    with pytest.raises(PublishError, match="aspect ratio"):
        pub.to_jpegs(pub.list_images(content), tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell launcher")
async def test_tunnel_with_fake_cloudflared(tmp_path, monkeypatch):
    fake = tmp_path / "fake_cloudflared.py"
    fake.write_text(
        "import sys, time\n"
        "print('INF |  https://abc-def.trycloudflare.com  |', file=sys.stderr, flush=True)\n"
        "time.sleep(30)\n"
    )
    launcher = tmp_path / "cloudflared"
    launcher.write_text(f"#!/bin/sh\nexec {sys.executable} {fake} \"$@\"\n")
    launcher.chmod(0o755)
    (tmp_path / "a.jpg").write_bytes(b"x")

    async def reachable(self):
        return None

    monkeypatch.setattr(PublicTunnel, "_wait_reachable", reachable)
    t = PublicTunnel(tmp_path, cloudflared=str(launcher), timeout=10)
    async with t as url:
        assert url == "https://abc-def.trycloudflare.com"
        port = t._server.server_address[1]
        r = await asyncio.to_thread(httpx.get, f"http://127.0.0.1:{port}/a.jpg", trust_env=False)
        assert r.content == b"x"
    assert t._proc is None and t._server is None


async def _no_sleep(_):
    return None


# ---- Reels -------------------------------------------------------------------


def make_mp4(path: Path, seconds: float = 34.0, *, faststart: bool = True, width: int = 1080, height: int = 1920) -> Path:
    """Minimal ISO-BMFF file: ftyp + moov(mvhd, trak(tkhd)) + mdat, enough for mp4_info."""
    import struct

    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", 8 + len(payload)) + kind + payload

    timescale = 1000
    times = struct.pack(">II", timescale, int(seconds * timescale))
    mvhd = box(b"mvhd", b"\x00\x00\x00\x00" + b"\x00" * 8 + times + b"\x00" * 80)
    tkhd = box(b"tkhd", b"\x00\x00\x00\x03" + b"\x00" * 72 + struct.pack(">II", width << 16, height << 16))
    moov = box(b"moov", mvhd + box(b"trak", tkhd))
    mdat = box(b"mdat", b"\x00" * 2048)
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")
    path.write_bytes(ftyp + (moov + mdat if faststart else mdat + moov))
    return path


@pytest.fixture
def reel(content):
    for p in content.glob("*.png"):
        p.unlink()
    Image.new("RGB", (1080, 1920)).save(content / "cover.png")  # extra files in a reel folder are ignored
    make_mp4(content / "reel.mp4")
    (content / "reel.json").write_text('{"cover_ms": 1667, "share_to_feed": true}', encoding="utf-8")
    return content


def reel_handler(calls, *, statuses=("IN_PROGRESS", "FINISHED"), upload_ok=True, resumable_ok=True):
    seq = iter(statuses)
    base = graph_handler(calls)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rupload.facebook.com":
            calls.append(("UPLOAD", request.url.path, dict(request.headers)))
            if not upload_ok:
                return json_response({"debug_info": {"message": "ProcessingFailedError"}}, 400)
            return json_response({"success": True, "message": "Upload successful."})
        form = dict(httpx.QueryParams(request.content.decode())) if request.method == "POST" else {}
        if request.method == "POST" and form.get("upload_type") == "resumable" and not resumable_ok:
            calls.append(("POST", request.url.path, form))
            return json_response({"error": {"message": "(#100) Invalid parameter", "code": 100}}, 400)
        if "status_code" in request.url.params.get("fields", ""):
            calls.append(("GET", request.url.path, {}))
            return json_response({"status_code": next(seq, "FINISHED")})
        return base(request)

    return handler


async def test_prepare_reel_resumable_upload(make_service, reel, monkeypatch):
    monkeypatch.setattr(pub, "REEL_POLL_S", 0)
    calls: list = []
    svc = make_service(reel_handler(calls))
    p = Publisher(svc, tunnel_factory=FakeTunnel)
    prepared = await p.prepare("demo")

    assert prepared["type"] == "REELS" and prepared["status"] == "FINISHED"
    assert prepared["upload"] == "resumable upload"
    assert prepared["video"] == {"file": "reel.mp4", "mb": 0.0, "duration_s": 34.0, "size": "1080x1920"}
    assert prepared["ignored_files"] == ["cover.png"]
    create = next(c for c in calls if c[0] == "POST" and c[1].endswith("/media"))[2]
    assert create["media_type"] == "REELS" and create["upload_type"] == "resumable"
    assert create["thumb_offset"] == "1667" and create["share_to_feed"] == "true" and "video_url" not in create
    upload = next(c for c in calls if c[0] == "UPLOAD")
    assert upload[1] == "/ig-api-upload/v26.0/c1"
    assert upload[2]["authorization"] == "OAuth TEST" and upload[2]["offset"] == "0"
    assert upload[2]["file_size"] == str((reel / "reel.mp4").stat().st_size)
    assert sum(1 for c in calls if c[0] == "GET" and c[1].endswith("/c1")) == 2  # IN_PROGRESS -> FINISHED
    assert not any(c[1].endswith("/media_publish") for c in calls)  # prepare never publishes
    assert svc.storage.publications()[0]["media_type"] == "REELS"

    result = await p.publish(prepared["creation_id"])
    assert result["published"] is True


async def test_reel_processing_error_is_reported(make_service, reel, monkeypatch):
    monkeypatch.setattr(pub, "REEL_POLL_S", 0)
    svc = make_service(reel_handler([], statuses=("IN_PROGRESS", "ERROR")))
    with pytest.raises(PublishError, match="ERROR"):
        await Publisher(svc, tunnel_factory=FakeTunnel).prepare("demo")
    assert svc.storage.publications() == []


async def test_reel_falls_back_to_tunnel_when_resumable_is_rejected(make_service, reel, monkeypatch):
    monkeypatch.setattr(pub, "REEL_POLL_S", 0)
    calls: list = []
    svc = make_service(reel_handler(calls, resumable_ok=False))
    prepared = await Publisher(svc, tunnel_factory=FakeTunnel).prepare("demo")
    assert prepared["upload"].startswith("tunnel video_url")
    assert FakeTunnel.served == ["reel.mp4"]
    fallback = [c for c in calls if c[0] == "POST" and c[1].endswith("/media")][-1][2]
    assert fallback["video_url"] == "https://demo.trycloudflare.com/reel.mp4" and "upload_type" not in fallback


def test_video_validation(tmp_path):
    ok = make_mp4(tmp_path / "ok.mp4", 34)
    assert pub.mp4_info(ok)["faststart"] is True
    with pytest.raises(PublishError, match="moov atom"):
        pub.check_video(make_mp4(tmp_path / "slow.mp4", faststart=False))
    with pytest.raises(PublishError, match="duration"):
        pub.check_video(make_mp4(tmp_path / "short.mp4", 2))
    with pytest.raises(PublishError, match="width"):
        pub.check_video(make_mp4(tmp_path / "wide.mp4", width=3840, height=2160))
    (tmp_path / "junk.mp4").write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00")
    with pytest.raises(PublishError, match="no moov"):
        pub.mp4_info(tmp_path / "junk.mp4")
    (tmp_path / "reel.json").write_text('{"cover": 5}', encoding="utf-8")
    with pytest.raises(PublishError, match="unknown keys"):
        pub.read_reel_settings(tmp_path)


def test_real_mp4_header_is_parsed():
    """A real ffmpeg-made MP4 (3 s, 1080x1920, -movflags +faststart) parses with the right duration and size."""
    p = Path(__file__).parent / "fixtures" / "tiny-reel-faststart.mp4"
    info = pub.mp4_info(p)
    assert info["faststart"] and info["width"] == 1080 and info["height"] == 1920 and 2.9 < info["duration_s"] < 3.1


async def test_trial_reel_params(make_service, reel, monkeypatch):
    monkeypatch.setattr(pub, "REEL_POLL_S", 0)
    (reel / "reel.json").write_text('{"cover_ms": 1667, "trial": "SS_PERFORMANCE"}', encoding="utf-8")
    calls: list = []
    prepared = await Publisher(make_service(reel_handler(calls)), tunnel_factory=FakeTunnel).prepare("demo")
    create = next(c for c in calls if c[0] == "POST" and c[1].endswith("/media"))[2]
    assert create["trial_params"] == '{"graduation_strategy": "SS_PERFORMANCE"}' and "share_to_feed" not in create
    assert prepared["trial"] == "SS_PERFORMANCE"
    (reel / "reel.json").write_text('{"trial": "AUTO"}', encoding="utf-8")
    with pytest.raises(PublishError, match="trial must be"):
        pub.read_reel_settings(reel)
