"""Thin async client for the Facebook Graph API (Instagram API with Facebook Login)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

# https://developers.facebook.com/docs/graph-api/overview/rate-limiting
RATE_LIMIT_CODES = {4, 17, 32, 613, 80001, 80002, 80006}
TRANSIENT_CODES = {1, 2}
TOKEN_ERROR_CODE = 190
RUPLOAD_HOST = "https://rupload.facebook.com"  # resumable video uploads (Reels)


class GraphAPIError(Exception):
    """Error returned by the Graph API."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        subcode: int | None = None,
        status: int | None = None,
        fbtrace_id: str | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.subcode = subcode
        self.status = status
        self.fbtrace_id = fbtrace_id
        self.transient = transient

    def __str__(self) -> str:
        parts = [self.message]
        if self.code is not None:
            parts.append(f"code={self.code}")
        if self.subcode is not None:
            parts.append(f"subcode={self.subcode}")
        if self.fbtrace_id:
            parts.append(f"fbtrace_id={self.fbtrace_id}")
        return " | ".join(parts)


class RateLimitError(GraphAPIError):
    """Rate limit reached. Retrying immediately makes it worse, so we do not retry."""


class TokenError(GraphAPIError):
    """Access token is invalid or expired."""


@dataclass(slots=True)
class UsageInfo:
    """Last seen rate-limit usage headers."""

    app_usage: dict[str, Any] = field(default_factory=dict)
    business_usage: dict[str, Any] = field(default_factory=dict)
    instagram_usage: dict[str, Any] = field(default_factory=dict)


def _parse_json_header(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class GraphClient:
    def __init__(
        self,
        base_url: str,
        access_token: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._access_token = access_token
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self.usage = UsageInfo()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params, retries=self._max_retries)

    async def post(self, path: str, params: dict[str, Any] | None = None, *, retries: int = 0) -> dict[str, Any]:
        """POST with form params. No retries by default: repeating a publish call could post twice."""
        return await self._request("POST", path, params, retries=retries)

    async def _request(self, method: str, path: str, params: dict[str, Any] | None, *, retries: int) -> dict[str, Any]:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        query.setdefault("access_token", self._access_token)

        attempt = 0
        while True:
            attempt += 1
            try:
                if method == "GET":
                    response = await self._client.get(path, params=query)
                else:
                    response = await self._client.post(path, data=query)
            except httpx.TransportError as exc:
                if attempt > retries:
                    raise GraphAPIError(f"Network error: {exc}", transient=True) from exc
                await self._backoff(attempt, reason=str(exc))
                continue

            self._record_usage(response)
            try:
                return self._handle(response)
            except GraphAPIError as exc:
                retryable = exc.transient or (exc.status is not None and exc.status >= 500)
                if isinstance(exc, (RateLimitError, TokenError)) or not retryable or attempt > retries:
                    raise
                await self._backoff(attempt, reason=str(exc))

    @property
    def api_version(self) -> str:
        return str(self._client.base_url).rstrip("/").rsplit("/", 1)[-1]

    async def upload_video(self, container_id: str, path: Path, *, timeout: float = 600.0) -> dict[str, Any]:
        """Resumable upload of a local video into a REELS container created with upload_type=resumable.

        POST https://rupload.facebook.com/ig-api-upload/<version>/<container_id>, headers Authorization/offset/file_size.
        Sent in one request from offset 0. Not retried automatically (a partial upload is simply redone by prepare).
        """
        url = f"{RUPLOAD_HOST}/ig-api-upload/{self.api_version}/{container_id}"
        data = await asyncio.to_thread(path.read_bytes)
        headers = {"Authorization": f"OAuth {self._access_token}", "offset": "0", "file_size": str(len(data))}
        try:
            response = await self._client.post(url, content=data, headers=headers, timeout=timeout)
        except httpx.TransportError as exc:
            raise GraphAPIError(f"Video upload failed: {exc}", transient=True) from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success or not body.get("success"):
            debug = body.get("debug_info") or body.get("error") or response.text[:300]
            raise GraphAPIError(f"Video upload rejected (HTTP {response.status_code}): {debug}", status=response.status_code)
        return body

    async def paginate(self, path: str, params: dict[str, Any] | None = None, *, max_items: int = 100) -> list[dict[str, Any]]:
        """Follow cursor pagination (`paging.cursors.after`) until max_items."""
        items: list[dict[str, Any]] = []
        page_params = dict(params or {})
        while len(items) < max_items:
            page_params["limit"] = min(page_params.get("limit") or 50, max_items - len(items), 100)
            body = await self.get(path, page_params)
            items.extend(body.get("data", []))
            after = body.get("paging", {}).get("cursors", {}).get("after")
            if not after or not body.get("paging", {}).get("next"):
                break
            page_params["after"] = after
        return items[:max_items]

    async def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(2 ** (attempt - 1), 8)
        log.warning("Graph API retry %s in %ss: %s", attempt, delay, reason)
        await asyncio.sleep(delay)

    def _record_usage(self, response: httpx.Response) -> None:
        headers = response.headers
        if app := _parse_json_header(headers.get("x-app-usage")):
            self.usage.app_usage = app
        if biz := _parse_json_header(headers.get("x-business-use-case-usage")):
            self.usage.business_usage = biz
        if ig := _parse_json_header(headers.get("x-ig-business-use-case-usage")):
            self.usage.instagram_usage = ig

    @staticmethod
    def _handle(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            if response.is_success:
                raise GraphAPIError("Non-JSON response from Graph API", status=response.status_code) from None
            raise GraphAPIError(f"HTTP {response.status_code}: {response.text[:300]}", status=response.status_code) from None

        if response.is_success and "error" not in body:
            return body

        err = body.get("error", {}) if isinstance(body, dict) else {}
        message = err.get("error_user_msg") or err.get("message") or f"HTTP {response.status_code}"
        code = err.get("code")
        kwargs = dict(
            code=code,
            subcode=err.get("error_subcode"),
            status=response.status_code,
            fbtrace_id=err.get("fbtrace_id"),
            transient=bool(err.get("is_transient")) or code in TRANSIENT_CODES,
        )
        if code in RATE_LIMIT_CODES:
            raise RateLimitError(
                f"Rate limit reached: {message}. Wait before the next request (see get_api_status).",
                **kwargs,
            )
        if code == TOKEN_ERROR_CODE:
            raise TokenError(
                f"Access token problem: {message}. Reconnect the account: call open_setup with again=true "
                "(or run `creatorloop-auth login`).",
                **kwargs,
            )
        raise GraphAPIError(message, **kwargs)
