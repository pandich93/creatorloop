"""SQLite storage: response cache, follower snapshots, hashtag quota tracking."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    username        TEXT NOT NULL,
    captured_on     TEXT NOT NULL,          -- YYYY-MM-DD (UTC), one row per day
    captured_at     TEXT NOT NULL,          -- ISO timestamp of the last update that day
    followers_count INTEGER,
    follows_count   INTEGER,
    media_count     INTEGER,
    PRIMARY KEY (username, captured_on)
);

-- v2: post metric history and competitor tracking (additive, no migration of old tables needed)
CREATE TABLE IF NOT EXISTS media (
    media_id     TEXT PRIMARY KEY,
    owner        TEXT NOT NULL,             -- username, lower case
    is_own       INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,                      -- Graph API timestamp
    format       TEXT,
    permalink    TEXT,
    caption_head TEXT
);

CREATE TABLE IF NOT EXISTS media_snapshots (
    media_id    TEXT NOT NULL,
    captured_hr TEXT NOT NULL,              -- YYYY-MM-DDTHH (UTC), at most one row per hour
    captured_at TEXT NOT NULL,
    reach       INTEGER,
    views       INTEGER,
    likes       INTEGER,
    comments    INTEGER,
    saved       INTEGER,
    shares      INTEGER,
    follows     INTEGER,
    PRIMARY KEY (media_id, captured_hr)
);
CREATE INDEX IF NOT EXISTS idx_media_owner ON media (owner);

CREATE TABLE IF NOT EXISTS tracked_accounts (
    username TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    note     TEXT
);

CREATE TABLE IF NOT EXISTS publications (
    creation_id  TEXT PRIMARY KEY,
    folder       TEXT,
    caption      TEXT,
    items        INTEGER,
    status       TEXT NOT NULL,            -- prepared | published | failed
    media_id     TEXT,
    permalink    TEXT,
    error        TEXT,
    prepared_at  TEXT NOT NULL,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS post_reviews (
    media_id    TEXT NOT NULL,
    stage       TEXT NOT NULL,             -- 24h | 72h
    reported_at TEXT NOT NULL,
    metrics     TEXT,                      -- JSON snapshot at review time
    PRIMARY KEY (media_id, stage)
);

CREATE TABLE IF NOT EXISTS post_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    folder      TEXT NOT NULL,
    publish_at  TEXT NOT NULL,             -- UTC ISO
    fingerprint TEXT NOT NULL,             -- hash of caption + media approved by the user
    media_type  TEXT,
    caption_head TEXT,
    status      TEXT NOT NULL,             -- queued | publishing | published | failed | missed | blocked | cancelled
    creation_id TEXT,
    permalink   TEXT,
    error       TEXT,
    approved_at TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments_seen (
    comment_id TEXT PRIMARY KEY,
    media_id   TEXT,
    seen_at    TEXT NOT NULL,
    replied_at TEXT,
    reply_id   TEXT
);

CREATE TABLE IF NOT EXISTS hashtag_queries (
    hashtag         TEXT PRIMARY KEY,
    hashtag_id      TEXT NOT NULL,
    first_queried_at TEXT NOT NULL           -- start of the current 7-day window for this tag
);
"""

# v3: additive column migrations (ignored when already applied)
MIGRATIONS = ["ALTER TABLE publications ADD COLUMN media_type TEXT"]

HASHTAG_LIMIT = 30
HASHTAG_WINDOW = timedelta(days=7)


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            for ddl in MIGRATIONS:
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:  # column already exists
                    pass

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- cache -------------------------------------------------------------

    def cache_get(self, key: str) -> Any | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or row["expires_at"] < time.time():
            return None
        return json.loads(row["value"])

    def cache_set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), time.time() + ttl_s),
            )

    def cache_clear(self, prefix: str | None = None) -> int:
        with self._conn() as conn:
            if prefix:
                cur = conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
            else:
                cur = conn.execute("DELETE FROM cache")
            return cur.rowcount

    # ---- profile snapshots -------------------------------------------------

    def save_snapshot(self, username: str, followers: int | None, follows: int | None, media: int | None) -> None:
        now = datetime.now(UTC)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO profile_snapshots
                    (username, captured_on, captured_at, followers_count, follows_count, media_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (username, captured_on) DO UPDATE SET
                    captured_at = excluded.captured_at,
                    followers_count = excluded.followers_count,
                    follows_count = excluded.follows_count,
                    media_count = excluded.media_count
                """,
                (username.lower(), now.date().isoformat(), now.isoformat(timespec="seconds"), followers, follows, media),
            )

    def get_snapshots(self, username: str, days: int) -> list[dict[str, Any]]:
        since = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT captured_on, followers_count, follows_count, media_count
                FROM profile_snapshots
                WHERE username = ? AND captured_on >= ?
                ORDER BY captured_on
                """,
                (username.lower(), since),
            ).fetchall()
        return [dict(r) for r in rows]

    def tracked_usernames(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT username FROM profile_snapshots ORDER BY username").fetchall()
        return [r["username"] for r in rows]

    # ---- media history -----------------------------------------------------

    def save_media_snapshots(self, owner: str, items: list[dict[str, Any]], *, is_own: bool) -> int:
        """items: {id, timestamp, format, permalink, caption, metrics:{reach, views, likes, ...}}"""
        now = datetime.now(UTC)
        hour = now.strftime("%Y-%m-%dT%H")
        stamp = now.isoformat(timespec="seconds")
        cols = ("reach", "views", "likes", "comments", "saved", "shares", "follows")
        with self._conn() as conn:
            for it in items:
                conn.execute(
                    """
                    INSERT INTO media (media_id, owner, is_own, published_at, format, permalink, caption_head)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (media_id) DO UPDATE SET
                        is_own = MAX(media.is_own, excluded.is_own),
                        format = excluded.format, permalink = excluded.permalink, caption_head = excluded.caption_head
                    """,
                    (
                        it["id"],
                        owner.lower(),
                        int(is_own),
                        it.get("timestamp"),
                        it.get("format"),
                        it.get("permalink"),
                        (it.get("caption") or "").split("\n", 1)[0][:200],
                    ),
                )
                m = it.get("metrics") or {}
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO media_snapshots (media_id, captured_hr, captured_at, {", ".join(cols)})
                    VALUES (?, ?, ?, {", ".join("?" for _ in cols)})
                    """,
                    (it["id"], hour, stamp, *(m.get(c) for c in cols)),
                )
        return len(items)

    def media_history(self, media_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            meta = conn.execute("SELECT * FROM media WHERE media_id = ?", (media_id,)).fetchone()
            if meta is None:
                return None
            rows = conn.execute(
                """
                SELECT captured_at, reach, views, likes, comments, saved, shares, follows
                FROM media_snapshots WHERE media_id = ? ORDER BY captured_at
                """,
                (media_id,),
            ).fetchall()
        return {"media": dict(meta), "snapshots": [dict(r) for r in rows]}

    def owner_media_ids(self, owner: str) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT media_id FROM media WHERE owner = ?", (owner.lower(),)).fetchall()
        return {r["media_id"] for r in rows}

    # ---- tracked accounts --------------------------------------------------

    def track(self, username: str, note: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tracked_accounts (username, added_at, note) VALUES (?, ?, ?)
                ON CONFLICT (username) DO UPDATE SET note = COALESCE(excluded.note, tracked_accounts.note)
                """,
                (username.lower(), datetime.now(UTC).isoformat(timespec="seconds"), note),
            )

    def untrack(self, username: str) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM tracked_accounts WHERE username = ?", (username.lower(),)).rowcount > 0

    def tracked(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT username, added_at, note FROM tracked_accounts ORDER BY username").fetchall()
        return [dict(r) for r in rows]

    # ---- publications ------------------------------------------------------

    def save_publication(
        self, creation_id: str, folder: str, caption: str, items: int, media_type: str | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO publications (creation_id, folder, caption, items, status, prepared_at, media_type)
                VALUES (?, ?, ?, ?, 'prepared', ?, ?)
                """,
                (creation_id, folder, caption, items, datetime.now(UTC).isoformat(timespec="seconds"), media_type),
            )

    def update_publication(self, creation_id: str, **fields: Any) -> None:
        if fields.get("status") == "published":
            fields["published_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(f"UPDATE publications SET {cols} WHERE creation_id = ?", (*fields.values(), creation_id))

    def get_publication(self, creation_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM publications WHERE creation_id = ?", (creation_id,)).fetchone()
        return dict(row) if row else None

    def publications(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT creation_id, folder, media_type, items, status, media_id, permalink, prepared_at, published_at, error "
                "FROM publications ORDER BY prepared_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- publishing queue --------------------------------------------------

    def queue_add(self, folder: str, publish_at: str, fingerprint: str, media_type: str, caption_head: str) -> int:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO post_queue (folder, publish_at, fingerprint, media_type, caption_head, status, approved_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)",
                (folder, publish_at, fingerprint, media_type, caption_head, now, now),
            )
            return int(cur.lastrowid)

    def queue_get(self, qid: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM post_queue WHERE id = ?", (qid,)).fetchone()
        return dict(row) if row else None

    def queue_update(self, qid: int, **fields: Any) -> None:
        fields["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(f"UPDATE post_queue SET {cols} WHERE id = ?", (*fields.values(), qid))

    def queue_due(self, now_iso: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_queue WHERE status = 'queued' AND publish_at <= ? ORDER BY publish_at", (now_iso,)
            ).fetchall()
        return [dict(r) for r in rows]

    def queue_list(self, include_done: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        where = "" if include_done else "WHERE status IN ('queued', 'publishing')"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM post_queue {where} ORDER BY publish_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def queue_active_for(self, folder: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM post_queue WHERE folder = ? AND status IN ('queued', 'publishing')", (folder,)
            ).fetchone()
        return dict(row) if row else None

    # ---- comments ----------------------------------------------------------

    def comment_seen(self, comment_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM comments_seen WHERE comment_id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None

    def comment_mark(self, comment_id: str, media_id: str | None, reply_id: str | None = None) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO comments_seen (comment_id, media_id, seen_at) VALUES (?, ?, ?) "
                "ON CONFLICT(comment_id) DO UPDATE SET media_id = COALESCE(excluded.media_id, media_id)",
                (comment_id, media_id, now),
            )
            if reply_id:
                conn.execute(
                    "UPDATE comments_seen SET replied_at = ?, reply_id = ? WHERE comment_id = ?",
                    (now, reply_id, comment_id),
                )

    # ---- post reviews ------------------------------------------------------

    def review_get(self, media_id: str, stage: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM post_reviews WHERE media_id = ? AND stage = ?", (media_id, stage)
            ).fetchone()
        return dict(row) if row else None

    def review_save(self, media_id: str, stage: str, metrics: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO post_reviews (media_id, stage, reported_at, metrics) VALUES (?, ?, ?, ?)",
                (media_id, stage, datetime.now(UTC).isoformat(timespec="seconds"), json.dumps(metrics)),
            )

    # ---- hashtag quota -----------------------------------------------------

    def _active_hashtags(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        cutoff = (datetime.now(UTC) - HASHTAG_WINDOW).isoformat(timespec="seconds")
        return conn.execute(
            "SELECT hashtag, hashtag_id, first_queried_at FROM hashtag_queries WHERE first_queried_at >= ?",
            (cutoff,),
        ).fetchall()

    def hashtag_quota(self) -> dict[str, Any]:
        with self._conn() as conn:
            active = self._active_hashtags(conn)
        used = sorted(active, key=lambda r: r["first_queried_at"])
        return {
            "limit": HASHTAG_LIMIT,
            "used": len(used),
            "remaining": max(HASHTAG_LIMIT - len(used), 0),
            "hashtags": [
                {
                    "hashtag": r["hashtag"],
                    "frees_up_at": (datetime.fromisoformat(r["first_queried_at"]) + HASHTAG_WINDOW).isoformat(
                        timespec="minutes"
                    ),
                }
                for r in used
            ],
            "note": "Local estimate: counts only queries made through this server.",
        }

    def plan_hashtags(self, hashtags: list[str]) -> dict[str, Any]:
        """Dry run: which tags are free (already in their 7-day window) and which cost a new slot."""
        quota = self.hashtag_quota()
        active = {h["hashtag"] for h in quota["hashtags"]}
        tags = list(dict.fromkeys(t.lstrip("#").strip().lower() for t in hashtags if t.strip("# ")))
        free = [t for t in tags if t in active]
        new = [t for t in tags if t not in active]
        fits = len(new) <= quota["remaining"]
        return {
            "free_already_queried": [f"#{t}" for t in free],
            "new_slots_needed": [f"#{t}" for t in new],
            "remaining_before": quota["remaining"],
            "remaining_after": max(quota["remaining"] - len(new), 0),
            "fits_in_quota": fits,
            "would_be_skipped": [f"#{t}" for t in new[quota["remaining"]:]] if not fits else [],
            "next_slot_frees_up_at": quota["hashtags"][0]["frees_up_at"] if quota["hashtags"] else None,
        }

    def known_hashtag_id(self, hashtag: str) -> str | None:
        """Hashtag ID if the tag is inside its current 7-day window (re-query costs no quota)."""
        with self._conn() as conn:
            for row in self._active_hashtags(conn):
                if row["hashtag"] == hashtag:
                    return row["hashtag_id"]
        return None

    def can_query_new_hashtag(self) -> bool:
        with self._conn() as conn:
            return len(self._active_hashtags(conn)) < HASHTAG_LIMIT

    def register_hashtag(self, hashtag: str, hashtag_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO hashtag_queries (hashtag, hashtag_id, first_queried_at) VALUES (?, ?, ?)",
                (hashtag, hashtag_id, datetime.now(UTC).isoformat(timespec="seconds")),
            )
