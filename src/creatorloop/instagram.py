"""Instagram Graph API endpoints used by the MCP tools (with caching)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from creatorloop.config import Settings
from creatorloop.graph_client import GraphAPIError, GraphClient
from creatorloop.storage import Storage

log = logging.getLogger(__name__)

PROFILE_FIELDS = "id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"

OWN_MEDIA_FIELDS = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url"

# Business Discovery: base fields are documented for years; extended ones were added later.
# If the API rejects an extended field we retry with the base set.
BD_PROFILE_FIELDS = "username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"
BD_MEDIA_BASE = "id,caption,media_type,permalink,timestamp,like_count,comments_count"
BD_MEDIA_EXTENDED = BD_MEDIA_BASE + ",media_product_type,view_count"

HASHTAG_MEDIA_FIELDS = "id,caption,media_type,permalink,timestamp,like_count,comments_count"

# Media insights per media_product_type (Graph API v26, deprecated metrics removed).
MEDIA_METRICS: dict[str, list[str]] = {
    "FEED": [
        "reach",
        "views",
        "likes",
        "comments",
        "saved",
        "shares",
        "reposts",
        "total_interactions",
        "profile_visits",
        "follows",
    ],
    "REELS": [
        "reach",
        "views",
        "likes",
        "comments",
        "saved",
        "shares",
        "total_interactions",
        "reposts",
        "ig_reels_avg_watch_time",
        "ig_reels_video_view_total_time",
        "reels_skip_rate",
    ],
    "STORY": ["reach", "views", "shares", "total_interactions", "replies", "profile_visits", "follows"],
}

# Account-level metrics with metric_type=total_value, period=day.
ACCOUNT_TOTAL_METRICS = [
    "reach",
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "saves",
    "shares",
    "replies",
    "profile_links_taps",
]

MAX_INSIGHTS_RANGE = timedelta(days=30)
DATA_LAG_DAYS = 2
TOKEN_WARN_DAYS = 14


class InstagramService:
    def __init__(self, settings: Settings, client: GraphClient, storage: Storage) -> None:
        self.settings = settings
        self.client = client
        self.storage = storage
        self._my_username: str | None = None

    # ---- helpers -----------------------------------------------------------

    async def _cached(self, key: str, ttl_s: int, fetch, *, refresh: bool = False) -> Any:
        if not refresh:
            hit = self.storage.cache_get(key)
            if hit is not None:
                return hit
        value = await fetch()
        self.storage.cache_set(key, value, ttl_s)
        return value

    @property
    def uid(self) -> str:
        return self.settings.ig_user_id

    # ---- own account -------------------------------------------------------

    async def my_profile(self, refresh: bool = False) -> dict[str, Any]:
        async def fetch() -> dict[str, Any]:
            return await self.client.get(f"/{self.uid}", {"fields": PROFILE_FIELDS})

        profile = await self._cached(f"me:profile:{self.uid}", self.settings.ttl_profile_s, fetch, refresh=refresh)
        self._my_username = profile.get("username")
        if self._my_username:
            self.storage.save_snapshot(
                self._my_username,
                profile.get("followers_count"),
                profile.get("follows_count"),
                profile.get("media_count"),
            )
        return profile

    async def my_username(self) -> str:
        if not self._my_username:
            await self.my_profile()
        return self._my_username or "me"

    async def my_media(self, limit: int = 25, refresh: bool = False) -> list[dict[str, Any]]:
        """Newest-first media. One cache entry for all limits: a larger cached list serves smaller requests."""
        key = f"me:media:{self.uid}"
        if not refresh:
            hit = self.storage.cache_get(key)
            if hit and (len(hit["items"]) >= limit or hit["exhausted"]):
                return hit["items"][:limit]
        items = await self.client.paginate(f"/{self.uid}/media", {"fields": OWN_MEDIA_FIELDS}, max_items=limit)
        self.storage.cache_set(key, {"items": items, "exhausted": len(items) < limit}, self.settings.ttl_media_s)
        return items

    async def media_insights(
        self, media_id: str, product_type: str | None = None, media: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Insights for one media. Unsupported metrics are skipped instead of failing the whole call.
        Every fresh (non-cached) fetch is also stored as a history snapshot."""

        async def fetch() -> dict[str, Any]:
            meta = media or {}
            ptype = product_type or meta.get("media_product_type")
            if not ptype:
                meta = await self.client.get(
                    f"/{media_id}", {"fields": "media_type,media_product_type,timestamp,permalink,caption"}
                )
                ptype = ptype or meta.get("media_product_type", "FEED")
            values, unavailable = await self._fetch_insights(f"/{media_id}/insights", self._metrics_for(ptype))
            self._remember_unsupported(ptype, unavailable)
            self.storage.save_media_snapshots(
                await self.my_username(), [_snapshot_item({**meta, "id": media_id}, values)], is_own=True
            )
            return {"media_id": media_id, "media_product_type": ptype, "metrics": values, "unavailable": unavailable}

        return await self._cached(f"media:insights:{media_id}", self.settings.ttl_media_s, fetch)

    def _metrics_for(self, ptype: str) -> list[str]:
        """Metric list minus those the API rejected recently for this media type (avoids N extra calls per post)."""
        skip = set(self.storage.cache_get(f"unsupported:{ptype}") or [])
        return [m for m in MEDIA_METRICS.get(ptype, MEDIA_METRICS["FEED"]) if m not in skip]

    def _remember_unsupported(self, ptype: str, unavailable: dict[str, str]) -> None:
        # code 10 "not enough viewers" is per-post, not a metric problem: don't blacklist on it
        rejected = [m for m, msg in unavailable.items() if "not enough" not in msg.lower()]
        if rejected:
            known = set(self.storage.cache_get(f"unsupported:{ptype}") or [])
            self.storage.cache_set(f"unsupported:{ptype}", sorted(known | set(rejected)), 7 * 86400)

    async def _fetch_insights(self, path: str, metrics: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
        try:
            body = await self.client.get(path, {"metric": ",".join(metrics)})
            return _parse_insight_values(body), {}
        except GraphAPIError as exc:
            if exc.code not in (10, 100):
                raise
            log.info("Bulk insights failed (%s), falling back to per-metric requests", exc)

        values: dict[str, Any] = {}
        unavailable: dict[str, str] = {}
        for metric in metrics:
            try:
                body = await self.client.get(path, {"metric": metric})
                values.update(_parse_insight_values(body))
            except GraphAPIError as exc:
                if exc.code not in (10, 100):
                    raise
                unavailable[metric] = exc.message
        return values, unavailable

    async def account_insights(self, days: int, lag_days: int = DATA_LAG_DAYS) -> dict[str, Any]:
        """Totals for the period plus daily reach. Splits long ranges into 30-day chunks.
        The window ends `lag_days` ago because Meta finalises insights with up to 48h delay."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        until = today - timedelta(days=lag_days)
        since = until - timedelta(days=days)

        async def fetch() -> dict[str, Any]:
            totals: dict[str, int] = {}
            daily_reach: list[dict[str, Any]] = []
            follows_by_type: dict[str, int] = {}
            unavailable: dict[str, str] = {}

            for chunk_since, chunk_until in _chunks(since, until, MAX_INSIGHTS_RANGE):
                window = {"since": int(chunk_since.timestamp()), "until": int(chunk_until.timestamp()), "period": "day"}

                for metric in ACCOUNT_TOTAL_METRICS:
                    try:
                        body = await self.client.get(
                            f"/{self.uid}/insights", {"metric": metric, "metric_type": "total_value", **window}
                        )
                    except GraphAPIError as exc:
                        if exc.code not in (10, 100):
                            raise
                        unavailable[metric] = exc.message
                        continue
                    for name, value in _parse_insight_values(body).items():
                        if isinstance(value, (int, float)):
                            totals[name] = totals.get(name, 0) + value

                try:
                    body = await self.client.get(
                        f"/{self.uid}/insights",
                        {"metric": "follows_and_unfollows", "metric_type": "total_value", "breakdown": "follow_type", **window},
                    )
                    for item in body.get("data", []):
                        for br in item.get("total_value", {}).get("breakdowns", []):
                            for res in br.get("results", []):
                                kind = (res.get("dimension_values") or ["UNKNOWN"])[0].upper()
                                follows_by_type[kind] = follows_by_type.get(kind, 0) + res.get("value", 0)
                except GraphAPIError as exc:
                    if exc.code not in (10, 100):
                        raise
                    unavailable["follows_and_unfollows"] = exc.message

                try:
                    body = await self.client.get(
                        f"/{self.uid}/insights", {"metric": "reach", "metric_type": "time_series", **window}
                    )
                    for item in body.get("data", []):
                        for point in item.get("values", []):
                            daily_reach.append({"date": point.get("end_time", "")[:10], "reach": point.get("value")})
                except GraphAPIError as exc:
                    if exc.code not in (10, 100):
                        raise
                    unavailable["reach_time_series"] = exc.message

            return {
                "since": since.date().isoformat(),
                "until": until.date().isoformat(),
                "totals": totals,
                # Raw breakdown by follow_type. Per Meta docs FOLLOWER = new follows,
                # NON_FOLLOWER = unfollows; verify against the Instagram app on first run.
                "follows_and_unfollows": follows_by_type,
                "daily_reach": daily_reach,
                "unavailable": unavailable,
                "note": f"Window ends {lag_days} day(s) ago (Meta data lags up to 48h). Totals are summed over "
                "30-day chunks; reach/accounts_engaged are de-duplicated by Meta only inside a chunk.",
            }

        return await self._cached(f"me:insights:{self.uid}:{days}:{since.date()}", self.settings.ttl_media_s, fetch)

    async def demographics(self, breakdown: str, timeframe: str, engaged: bool) -> dict[str, Any]:
        metric = "engaged_audience_demographics" if engaged else "follower_demographics"

        async def fetch() -> dict[str, Any]:
            body = await self.client.get(
                f"/{self.uid}/insights",
                {
                    "metric": metric,
                    "period": "lifetime",
                    "metric_type": "total_value",
                    "timeframe": timeframe,
                    "breakdown": breakdown,
                },
            )
            rows: list[dict[str, Any]] = []
            for item in body.get("data", []):
                for br in item.get("total_value", {}).get("breakdowns", []):
                    for res in br.get("results", []):
                        rows.append({"value": " / ".join(res.get("dimension_values", [])), "count": res.get("value", 0)})
            rows.sort(key=lambda r: r["count"], reverse=True)
            total = sum(r["count"] for r in rows) or 1
            for r in rows:
                r["share_pct"] = round(100 * r["count"] / total, 1)
            return {"metric": metric, "breakdown": breakdown, "timeframe": timeframe, "rows": rows}

        return await self._cached(f"me:demo:{self.uid}:{metric}:{breakdown}:{timeframe}", self.settings.ttl_profile_s * 6, fetch)

    # ---- competitors (Business Discovery) ----------------------------------

    async def competitor(self, username: str, media_limit: int = 25, refresh: bool = False) -> dict[str, Any]:
        username = username.lstrip("@").strip().lower()

        async def fetch() -> dict[str, Any]:
            try:
                data = await self._business_discovery(username, media_limit, BD_MEDIA_EXTENDED)
            except GraphAPIError as exc:
                # "(#100) Tried accessing nonexisting field (view_count)" -> retry without extended fields
                if exc.code != 100 or "field" not in exc.message.lower():
                    raise
                log.info("Extended Business Discovery fields rejected (%s); retrying with base fields", exc)
                data = await self._business_discovery(username, media_limit, BD_MEDIA_BASE)
            self.storage.save_media_snapshots(
                username,
                [
                    _snapshot_item(
                        m, {"likes": m.get("like_count"), "comments": m.get("comments_count"), "views": m.get("view_count")}
                    )
                    for m in data.get("media", [])
                ],
                is_own=False,
            )
            return data

        data = await self._cached(f"bd:{username}:{media_limit}", self.settings.ttl_profile_s, fetch, refresh=refresh)
        self.storage.save_snapshot(username, data.get("followers_count"), data.get("follows_count"), data.get("media_count"))
        return data

    async def _business_discovery(self, username: str, media_limit: int, media_fields: str) -> dict[str, Any]:
        media: list[dict[str, Any]] = []
        profile: dict[str, Any] = {}
        after: str | None = None
        while len(media) < media_limit:
            page = min(50, media_limit - len(media))
            edge = f"media.limit({page})" + (f".after({after})" if after else "")
            fields = f"business_discovery.username({username}){{{BD_PROFILE_FIELDS},{edge}{{{media_fields}}}}}"
            body = await self.client.get(f"/{self.uid}", {"fields": fields})
            bd = body.get("business_discovery", {})
            if not profile:
                profile = {k: v for k, v in bd.items() if k != "media"}
            chunk = bd.get("media", {})
            media.extend(chunk.get("data", []))
            after = chunk.get("paging", {}).get("cursors", {}).get("after")
            if not after or not chunk.get("data"):
                break
        profile["media"] = media[:media_limit]
        return profile

    # ---- hashtags ----------------------------------------------------------

    async def hashtag_id(self, hashtag: str) -> str:
        tag = hashtag.lstrip("#").strip().lower()
        if known := self.storage.known_hashtag_id(tag):
            return known
        if not self.storage.can_query_new_hashtag():
            quota = self.storage.hashtag_quota()
            raise RuntimeError(
                "Hashtag quota exhausted: Meta allows 30 unique hashtags per rolling 7 days. "
                f"Next slot frees up at {quota['hashtags'][0]['frees_up_at']} (UTC)."
            )
        body = await self.client.get("/ig_hashtag_search", {"user_id": self.uid, "q": tag})
        data = body.get("data", [])
        if not data:
            raise RuntimeError(f"Hashtag #{tag} not found")
        hid = data[0]["id"]
        self.storage.register_hashtag(tag, hid)
        return hid

    async def hashtag_media(self, hashtag: str, mode: str = "top", limit: int = 50) -> list[dict[str, Any]]:
        tag = hashtag.lstrip("#").strip().lower()
        edge = "top_media" if mode == "top" else "recent_media"

        async def fetch() -> list[dict[str, Any]]:
            hid = await self.hashtag_id(tag)
            return await self.client.paginate(
                f"/{hid}/{edge}", {"user_id": self.uid, "fields": HASHTAG_MEDIA_FIELDS}, max_items=limit
            )

        return await self._cached(f"hashtag:{tag}:{edge}:{limit}", self.settings.ttl_hashtag_s, fetch)

    # ---- token -------------------------------------------------------------

    async def debug_token(self) -> dict[str, Any]:
        """Token validity and expiry. Uses the app token if META_APP_SECRET is set, otherwise the token itself
        (a user token may inspect itself), so no secret is required."""
        inspector = (
            f"{self.settings.app_id}|{self.settings.app_secret}"
            if self.settings.app_id and self.settings.app_secret
            else self.settings.access_token
        )
        body = await self.client.get("/debug_token", {"input_token": self.settings.access_token, "access_token": inspector})
        data = body.get("data", {})
        now = datetime.now(UTC)

        def ts(value: int | None) -> tuple[str, float | None]:
            if not value:
                return "never", None
            when = datetime.fromtimestamp(value, UTC)
            return when.isoformat(timespec="minutes"), round((when - now).total_seconds() / 86400, 1)

        expires_at, days_left = ts(data.get("expires_at"))
        data_access_at, data_days_left = ts(data.get("data_access_expires_at"))
        status: dict[str, Any] = {
            "is_valid": data.get("is_valid"),
            "type": data.get("type"),
            "scopes": data.get("scopes", []),
            "expires_at": expires_at,
            "days_left": days_left,
            "data_access_expires_at": data_access_at,
            "data_access_days_left": data_days_left,
        }
        lefts = [d for d in (days_left, data_days_left) if d is not None]
        if not data.get("is_valid"):
            status["warning"] = "Token is invalid. Reconnect: call open_setup with again=true (or run `creatorloop-auth login`)."
        elif lefts and min(lefts) <= TOKEN_WARN_DAYS:
            status["warning"] = (
                f"Token or its data access expires in {min(lefts)} days. "
                "Renew: call open_setup with again=true, or use a never-expiring System User token "
                "(docs/meta-setup.md, step 3)."
            )
        return status

    async def token_warning(self) -> str | None:
        """Cached (12h) short warning for tool responses; never raises."""
        key = f"token:status:{self.uid}"
        cached = self.storage.cache_get(key)
        if cached is None:
            try:
                status = await self.debug_token()
                cached = {"warning": status.get("warning")}
            except Exception as exc:  # diagnostics must not break real tools
                log.info("Token check failed: %s", exc)
                cached = {"warning": None}
            self.storage.cache_set(key, cached, 12 * 3600)
        return cached.get("warning")


def _snapshot_item(m: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    from creatorloop.analytics import media_format  # local import: analytics is pure, avoid cycles

    return {
        "id": m.get("id"),
        "timestamp": m.get("timestamp"),
        "format": media_format(m),
        "permalink": m.get("permalink"),
        "caption": m.get("caption"),
        "metrics": metrics,
    }


def _parse_insight_values(body: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in body.get("data", []):
        name = item.get("name")
        if "total_value" in item:
            out[name] = item["total_value"].get("value")
        elif item.get("values"):
            out[name] = item["values"][-1].get("value")
    return out


def _chunks(start: datetime, end: datetime, size: timedelta):
    cur = start
    while cur < end:
        nxt = min(cur + size, end)
        yield cur, nxt
        cur = nxt
