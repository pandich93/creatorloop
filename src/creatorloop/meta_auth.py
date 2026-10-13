"""Facebook Login for the setup page: check the Meta app, turn a login code into a 60-day token, find the account.

Every failure is a MetaAuthError with a stable `code`; the setup page shows a translated text for it (setup_i18n)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from creatorloop.config import DEFAULT_API_VERSION

SCOPES = (
    "instagram_basic",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
    "instagram_content_publish",
    "instagram_manage_comments",
)


class MetaAuthError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class IgAccount:
    id: str
    username: str
    followers: int | None
    page: str


@dataclass(frozen=True, slots=True)
class LongLivedToken:
    value: str = field(repr=False)  # the access token: keep it out of logs and tracebacks
    expires_at: datetime | None  # None: Meta gave no expiry (the token does not expire)


class MetaAuth:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.api_version = api_version
        self._http = httpx.Client(base_url=f"https://graph.facebook.com/{api_version}", timeout=30, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, str], *, error: str) -> dict[str, Any]:
        try:
            resp = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise MetaAuthError("network", str(exc)) from exc
        try:
            body = resp.json()
        except ValueError as exc:
            raise MetaAuthError("meta_error", f"HTTP {resp.status_code}") from exc
        # Body must be a dict
        if not isinstance(body, dict):
            raise MetaAuthError("meta_error", f"HTTP {resp.status_code}")
        if "error" in body:
            err = body["error"]
            # Message is err.get("message") when err is a dict, else str(err)
            message = err.get("message", "") if isinstance(err, dict) else str(err)
            raise MetaAuthError(error, message)
        # If no "error" key but response is not successful
        if not resp.is_success:
            raise MetaAuthError("meta_error", f"HTTP {resp.status_code}")
        return body

    def _app(self) -> dict[str, str]:
        return {"client_id": self.app_id, "client_secret": self.app_secret}

    def validate_app(self) -> None:
        if not self.app_id.isdigit():
            raise MetaAuthError("bad_app_id")
        body = self._get("/oauth/access_token", {**self._app(), "grant_type": "client_credentials"}, error="bad_app")
        if "access_token" not in body:
            raise MetaAuthError("bad_app", "no app token in the response")

    def login_url(self, redirect_uri: str, state: str, *, rerequest: bool = False) -> str:
        params = {
            "client_id": self.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(SCOPES),
            "response_type": "code",
        }
        if rerequest:
            params["auth_type"] = "rerequest"
        return f"https://www.facebook.com/{self.api_version}/dialog/oauth?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> str:
        body = self._get(
            "/oauth/access_token",
            {**self._app(), "redirect_uri": redirect_uri, "code": code},
            error="code_exchange",
        )
        if "access_token" not in body or not body["access_token"]:
            raise MetaAuthError("code_exchange", "no access token in the response")
        return body["access_token"]

    def to_long_lived(self, short_token: str, *, now: datetime | None = None) -> LongLivedToken:
        body = self._get(
            "/oauth/access_token",
            {**self._app(), "grant_type": "fb_exchange_token", "fb_exchange_token": short_token},
            error="code_exchange",
        )
        if "access_token" not in body or not body["access_token"]:
            raise MetaAuthError("code_exchange", "no access token in the response")
        try:
            expires_in = int(body.get("expires_in") or 0)
        except (ValueError, TypeError) as exc:
            raise MetaAuthError("meta_error", "bad expires_in in the response") from exc
        expires_at = (now or datetime.now(UTC)) + timedelta(seconds=expires_in) if expires_in else None
        return LongLivedToken(body["access_token"], expires_at)

    def missing_permissions(self, token: str) -> list[str]:
        body = self._get("/me/permissions", {"access_token": token}, error="meta_error")
        data = body.get("data", [])
        if not isinstance(data, list):
            raise MetaAuthError("meta_error", "invalid data format in response")
        granted = {p.get("permission") for p in data if isinstance(p, dict) and p.get("status") == "granted"}
        return [scope for scope in SCOPES if scope not in granted]

    def find_accounts(self, token: str) -> list[IgAccount]:
        body = self._get(
            "/me/accounts",
            {"fields": "name,instagram_business_account{id,username,followers_count}", "limit": "100", "access_token": token},
            error="meta_error",
        )
        pages = body.get("data", [])
        if not isinstance(pages, list):
            raise MetaAuthError("meta_error", "invalid data format in response")
        if not pages:
            raise MetaAuthError("no_pages")
        accounts = [
            IgAccount(ig["id"], ig.get("username", ""), ig.get("followers_count"), page.get("name", ""))
            for page in pages
            if isinstance(page, dict) and (ig := page.get("instagram_business_account"))
        ]
        if not accounts:
            raise MetaAuthError("no_instagram", ", ".join(page.get("name", "?") for page in pages if isinstance(page, dict)))
        return accounts


def credentials_work(
    access_token: str,
    ig_user_id: str,
    *,
    api_version: str = DEFAULT_API_VERSION,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """True when the saved token can read the saved account (creatorloop-setup then skips the setup page)."""
    if not (access_token and ig_user_id):
        return False
    try:
        with httpx.Client(timeout=15, transport=transport) as http:
            resp = http.get(
                f"https://graph.facebook.com/{api_version}/{ig_user_id}",
                params={"fields": "id", "access_token": access_token},
            )
    except httpx.HTTPError:
        return False
    return resp.status_code == 200
