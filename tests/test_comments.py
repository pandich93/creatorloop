import httpx
import pytest

from creatorloop import comments

from .conftest import json_response

MEDIA = [
    {"id": "m1", "media_type": "IMAGE", "timestamp": "2099-01-01T00:00:00+0000", "comments_count": 3, "caption": "Hook"},
    {"id": "m2", "media_type": "IMAGE", "timestamp": "2099-01-01T00:00:00+0000", "comments_count": 0},
]


def handler(posts, *, deny=False):
    def h(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/m1/comments"):
            if deny:
                return json_response({"error": {"message": "(#10) Application does not have permission", "code": 10}}, 400)
            return json_response(
                {
                    "data": [
                        {"id": "c1", "text": "Zo'r!", "username": "ali", "timestamp": "2099-01-01T01:00:00+0000"},
                        {
                            "id": "c2",
                            "text": "Rahmat",
                            "username": "vali",
                            "timestamp": "2099-01-01T02:00:00+0000",
                            "replies": {"data": [{"id": "r1", "username": "me", "text": "!"}]},
                        },
                        {"id": "c3", "text": "my own", "username": "me", "timestamp": "2099-01-01T03:00:00+0000"},
                    ]
                }
            )
        if path.endswith("/media"):
            return json_response({"data": MEDIA})
        if request.method == "POST" and path.endswith("/replies"):
            posts.append(dict(httpx.QueryParams(request.content.decode())))
            return json_response({"id": "r9"})
        return json_response({"id": "1784", "username": "me"})

    return h


async def test_new_comments_and_reply(make_service, monkeypatch):
    monkeypatch.setattr("creatorloop.analytics.media_since", lambda media, days: media)
    posts: list = []
    svc = make_service(handler(posts))
    first = await comments.new_comments(svc)
    assert [c["comment_id"] for c in first["comments"]] == ["c1"]  # answered and own comments skipped
    assert first["posts_checked"] == 1  # posts without comments are not queried
    assert (await comments.new_comments(svc))["comments"] == []  # marked as seen
    assert [c["comment_id"] for c in (await comments.new_comments(svc, only_new=False))["comments"]] == ["c1"]

    res = await comments.reply(svc, "c1", "  Rahmat!  ")
    assert res["reply_id"] == "r9" and posts == [{"message": "Rahmat!", "access_token": "TEST"}]
    assert svc.storage.comment_seen("c1")["reply_id"] == "r9"
    with pytest.raises(comments.CommentsError, match="Empty"):
        await comments.reply(svc, "c1", "  ")


def test_thread_follow_ups_after_my_reply():
    thread = {
        "id": "c1",
        "username": "ali",
        "text": "Savol",
        "timestamp": "2099-01-01T01:00:00+0000",
        "replies": {
            "data": [
                {"id": "r1", "username": "me", "text": "Javob", "timestamp": "2099-01-01T02:00:00+0000"},
                {"id": "r2", "username": "ali", "text": "Rahmat, yana savol", "timestamp": "2099-01-01T03:00:00+0000"},
            ]
        },
    }
    items = comments._unanswered(thread, "me")
    assert [i["comment_id"] for i in items] == ["r2"]
    assert items[0]["reply_to"] == "c1" and items[0]["in_thread"] and items[0]["thread_start"]["text"] == "Savol"
    # a reply under MY own top-level comment is new too
    own = {
        "id": "c9",
        "username": "me",
        "text": "@ali hi",
        "timestamp": "2099-01-01T01:00:00+0000",
        "replies": {"data": [{"id": "r5", "username": "ali", "text": "ok", "timestamp": "2099-01-01T02:00:00+0000"}]},
    }
    assert [i["comment_id"] for i in comments._unanswered(own, "me")] == ["r5"]
    # untouched comment: the comment itself
    assert [i["comment_id"] for i in comments._unanswered({"id": "c5", "username": "x", "text": "?"}, "me")] == ["c5"]


async def test_missing_permission_explained(make_service, monkeypatch):
    monkeypatch.setattr("creatorloop.analytics.media_since", lambda media, days: media)
    svc = make_service(handler([], deny=True))
    with pytest.raises(comments.CommentsError, match="instagram_manage_comments") as info:
        await comments.new_comments(svc)
    assert "open_setup (again=true)" in str(info.value)
    assert "README" not in str(info.value) and "exchange" not in str(info.value)
