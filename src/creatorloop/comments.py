"""Comments on own posts: digest of new / unanswered comments and replies (only after user approval).

Needs the token permission instagram_manage_comments (kept ticked on the setup page, see docs/meta-setup.md).
"""

from __future__ import annotations

import asyncio
from typing import Any

from creatorloop import analytics
from creatorloop.graph_client import GraphAPIError

COMMENT_FIELDS = "id,text,username,timestamp,like_count,replies{id,text,username,timestamp,like_count}"
MAX_REPLY = 2200
PERMISSION_CODES = {10, 200}  # (#10) / (#200) permission errors


class CommentsError(RuntimeError):
    pass


def _permission_hint(exc: GraphAPIError) -> CommentsError:
    if exc.code in PERMISSION_CODES or "permission" in exc.message.lower():
        return CommentsError(
            "The token has no instagram_manage_comments permission. Reconnect with open_setup (again=true) "
            f"and keep instagram_manage_comments ticked. Graph API said: {exc}"
        )
    return CommentsError(f"Graph API error: {exc}")


def _unanswered(c: dict[str, Any], me: str) -> list[dict[str, Any]]:
    """Messages in one thread (top-level comment + its replies) written by others AFTER my last word there.

    A thread I already answered still yields new items when the person writes again. Instagram only allows
    replies to top-level comments, so every item carries `reply_to` = the top-level id to answer in that thread.
    """
    replies = list((c.get("replies") or {}).get("data") or [])
    if all(r.get("timestamp") for r in replies):
        replies.sort(key=lambda r: r["timestamp"])  # chronological; otherwise keep the API order
    msgs = [c] + replies
    own = [i for i, x in enumerate(msgs) if (x.get("username") or "").lower() == me]
    last_mine = own[-1] if own else -1
    items = []
    for i, x in enumerate(msgs):
        if i <= last_mine or (x.get("username") or "").lower() == me:
            continue  # mine, or already answered by a later message of mine
        in_thread = x is not c
        items.append({
            "comment_id": x["id"],
            "reply_to": c["id"],
            "username": x.get("username"),
            "text": x.get("text"),
            "timestamp": x.get("timestamp"),
            "likes": x.get("like_count"),
            "in_thread": in_thread,
            "thread_start": {"username": c.get("username"), "text": c.get("text")} if in_thread else None,
        })
    return items


async def new_comments(svc, *, days: int = 14, only_new: bool = True, mark_seen: bool = True) -> dict[str, Any]:
    me = (await svc.my_username()).lower()
    media = [m for m in analytics.media_since(await svc.my_media(limit=50, refresh=True), days)
             if (m.get("comments_count") or 0) > 0]
    sem = asyncio.Semaphore(4)

    async def fetch(m: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with sem:
            try:
                items = await svc.client.paginate(f"/{m['id']}/comments", {"fields": COMMENT_FIELDS}, max_items=100)
            except GraphAPIError as exc:
                raise _permission_hint(exc) from exc
        return m, items

    results = await asyncio.gather(*(fetch(m) for m in media))
    out = []
    for m, items in results:
        post = {"media_id": m["id"], "permalink": m.get("permalink"), "hook": analytics.caption_hook(m.get("caption"), 80)}
        for c in items:
            for item in _unanswered(c, me):
                seen = svc.storage.comment_seen(item["comment_id"])
                if only_new and seen:
                    continue
                out.append({**item, "post": post, "already_seen": bool(seen)})
    if mark_seen:
        for c in out:
            svc.storage.comment_mark(c["comment_id"], c["post"]["media_id"])
    out.sort(key=lambda c: c["timestamp"] or "", reverse=True)
    return {
        "comments": out,
        "posts_checked": len(media),
        "next": "Draft a short reply for each (same language as the comment, the user's tone). Send with "
        "reply_comment(comment_id=<reply_to>) ONLY after the user explicitly approves that exact text; "
        "in_thread items are answers inside a thread, thread_start shows what they reply to.",
    }


async def reply(svc, comment_id: str, message: str) -> dict[str, Any]:
    text = message.strip()
    if not text:
        raise CommentsError("Empty reply")
    if len(text) > MAX_REPLY:
        raise CommentsError(f"Reply is {len(text)} chars (max {MAX_REPLY})")
    try:
        body = await svc.client.post(f"/{comment_id}/replies", {"message": text})
    except GraphAPIError as exc:
        raise _permission_hint(exc) from exc
    svc.storage.comment_mark(comment_id, None, reply_id=body.get("id"))
    return {"replied": True, "reply_id": body.get("id"), "comment_id": comment_id, "text": text}
