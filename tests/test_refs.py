import io
import json

import httpx
import pytest
from PIL import Image as PILImage

from creatorloop import refs, server
from creatorloop.refs import RefError, RefFinder, shortcode_from_url

from .conftest import json_response


def jpeg(color) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (1080, 1350), color).save(buf, "JPEG")
    return buf.getvalue()


def test_shortcode_parsing():
    assert shortcode_from_url("https://www.instagram.com/p/DeCHjDpjuI8/?stkn=bmF1") == "DeCHjDpjuI8"
    assert shortcode_from_url("https://instagram.com/reel/AbC_-1/") == "AbC_-1"
    assert shortcode_from_url("https://www.instagram.com/bezikovkirilll/p/XyZ/") == "XyZ"
    with pytest.raises(RefError):
        shortcode_from_url("https://example.com/p/abc")


def bd_handler(seen_fields, *, reject_extended=False):
    page1 = [
        {
            "id": str(i),
            "permalink": f"https://www.instagram.com/p/other{i}/",
            "media_type": "IMAGE",
            "timestamp": "2026-09-01T10:00:00+0000",
            "like_count": 10,
            "comments_count": 0,
        }
        for i in range(3)
    ]
    target = {
        "id": "t",
        "permalink": "https://www.instagram.com/p/DeCHjDpjuI8/",
        "media_type": "CAROUSEL_ALBUM",
        "timestamp": "2026-09-02T10:00:00+0000",
        "like_count": 40,
        "comments_count": 5,
        "caption": "Собирай не просто проекты\n\nНапиши «КЛИЕНТЫ»",
        "children": {
            "data": [
                {"media_type": "IMAGE", "media_url": "https://cdn.example/1.jpg"},
                {"media_type": "VIDEO", "thumbnail_url": "https://cdn.example/2.jpg"},
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=jpeg((200, 100, 0)))
        if request.url.path.endswith("/instagram_oembed"):
            return json_response({"error": {"message": "Requires Meta oEmbed Read feature", "code": 10}}, 400)
        if request.url.path.endswith("/debug_token"):
            return json_response({"data": {"is_valid": True}})
        fields = request.url.params["fields"]
        seen_fields.append(fields)
        if reject_extended and "view_count" in fields:
            return json_response(
                {"error": {"message": "(#100) Tried accessing nonexisting field (view_count)", "code": 100}}, 400
            )
        if ".after(" in fields:
            media = {"data": [target]}
        else:
            media = {"data": page1, "paging": {"cursors": {"after": "CUR"}}}
        return json_response({"business_discovery": {"followers_count": 1000, "media_count": 4, "media": media}})

    return handler


@pytest.fixture
def refs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(refs, "REFS_ROOT", tmp_path / "_refs")
    return tmp_path / "_refs"


async def test_find_and_download(make_service, refs_root):
    seen: list[str] = []
    handler = bd_handler(seen, reject_extended=True)
    svc = make_service(handler)
    finder = RefFinder(svc, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    info = await finder.get("https://www.instagram.com/p/DeCHjDpjuI8/?stkn=x", "@BezikovKirilll")
    assert info["username"] == "bezikovkirilll" and info["format"] == "CAROUSEL"
    assert info["score"] == 45 and info["account_median"] == 10 and info["x_median"] == 4.5
    assert info["hook"] == "Собирай не просто проекты" and info["has_cta"]
    assert info["files"] == ["01.jpg", "02.jpg"]  # image + video cover
    assert (refs_root / "bezikovkirilll_DeCHjDpjuI8" / "02.jpg").exists()
    assert "view_count" not in seen[-1]  # fell back to base fields


async def test_missing_username_and_oembed_unavailable(make_service, refs_root):
    svc = make_service(bd_handler([]))
    with pytest.raises(RefError, match="^Pass username"):
        await RefFinder(svc).get("https://www.instagram.com/p/DeCHjDpjuI8/", None)


async def test_not_found(make_service, refs_root):
    svc = make_service(bd_handler([]))
    with pytest.raises(RefError, match="not found"):
        await RefFinder(svc).get("https://www.instagram.com/p/NOPE123/", "someone", download=False)


async def test_tool_returns_json_and_images(make_service, refs_root, monkeypatch):
    handler = bd_handler([])
    monkeypatch.setattr(server, "_service", make_service(handler))
    real_init = RefFinder.__init__

    def init(self, service, http=None):
        real_init(self, service, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(RefFinder, "__init__", init)
    result = await server.mcp.call_tool(
        "get_competitor_post", {"url": "https://www.instagram.com/p/DeCHjDpjuI8/", "username": "bezikovkirilll"}
    )
    kinds = [c.type for c in result.content]
    assert kinds == ["text", "image", "image"]
    assert json.loads(result.content[0].text)["slides"] == 2


def test_previews_limit_and_width(tmp_path):
    files = []
    for i in range(22):
        p = tmp_path / f"{i:02d}.jpg"
        p.write_bytes(jpeg((i * 10, 0, 0)))
        files.append(p)
    data = refs.previews(files)
    assert len(data) == 20
    assert PILImage.open(io.BytesIO(data[0])).width == 400
