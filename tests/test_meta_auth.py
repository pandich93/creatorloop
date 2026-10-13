from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from creatorloop.meta_auth import SCOPES, IgAccount, MetaAuth, MetaAuthError, credentials_work

from .conftest import json_response

NOW = datetime(2026, 10, 14, tzinfo=UTC)


def auth(handler) -> MetaAuth:
    return MetaAuth("1234", "secret", transport=httpx.MockTransport(handler))


def meta_error(message: str = "Invalid", code: int = 101) -> httpx.Response:
    return json_response({"error": {"message": message, "code": code}}, status=400)


def test_validate_app_accepts_a_good_pair():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return json_response({"access_token": "1234|app", "token_type": "bearer"})

    auth(handler).validate_app()
    assert seen == {"client_id": "1234", "client_secret": "secret", "grant_type": "client_credentials"}


def test_validate_app_rejects_a_bad_secret():
    with pytest.raises(MetaAuthError) as err:
        auth(lambda r: meta_error("Error validating client secret.", 1)).validate_app()
    assert err.value.code == "bad_app"
    assert "client secret" in err.value.detail


@pytest.mark.parametrize("app_id", ["", "abc", "12 34"])
def test_validate_app_rejects_a_non_numeric_id_without_calling_meta(app_id):
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(MetaAuthError) as err:
        MetaAuth(app_id, "secret", transport=httpx.MockTransport(handler)).validate_app()
    assert err.value.code == "bad_app_id"


def test_network_failure_is_reported_as_network():
    def handler(request):
        raise httpx.ConnectError("offline")

    with pytest.raises(MetaAuthError) as err:
        auth(handler).validate_app()
    assert err.value.code == "network"


def test_login_url_asks_for_every_scope():
    url = MetaAuth("1234", "secret", api_version="v26.0").login_url("http://localhost:5/callback", "STATE")
    parts = urlsplit(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert parts.netloc == "www.facebook.com" and parts.path == "/v26.0/dialog/oauth"
    assert q == {
        "client_id": "1234",
        "redirect_uri": "http://localhost:5/callback",
        "state": "STATE",
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }


def test_login_url_rerequest():
    url = MetaAuth("1234", "secret").login_url("http://localhost:5/callback", "S", rerequest=True)
    assert parse_qs(urlsplit(url).query)["auth_type"] == ["rerequest"]


def test_exchange_code_then_long_lived_token():
    def handler(request):
        p = request.url.params
        if p.get("code") == "CODE":
            assert p["redirect_uri"] == "http://localhost:5/callback"
            return json_response({"access_token": "SHORT"})
        assert p["grant_type"] == "fb_exchange_token" and p["fb_exchange_token"] == "SHORT"
        return json_response({"access_token": "LONG", "expires_in": 5184000})

    a = auth(handler)
    token = a.to_long_lived(a.exchange_code("CODE", "http://localhost:5/callback"), now=NOW)
    assert token.value == "LONG"
    assert token.expires_at == datetime(2026, 12, 13, tzinfo=UTC)


def test_long_lived_token_without_expiry():
    token = auth(lambda r: json_response({"access_token": "LONG"})).to_long_lived("SHORT", now=NOW)
    assert token.expires_at is None


def test_bad_code_is_a_code_exchange_error():
    with pytest.raises(MetaAuthError) as err:
        auth(lambda r: meta_error("This authorization code has expired.", 100)).exchange_code("OLD", "http://localhost:5/callback")
    assert err.value.code == "code_exchange"


def test_missing_permissions_lists_declined_and_absent_scopes():
    excluded = ("business_management", "instagram_manage_comments")
    data = [{"permission": s, "status": "granted"} for s in SCOPES if s not in excluded]
    data.append({"permission": "business_management", "status": "declined"})
    missing = auth(lambda r: json_response({"data": data})).missing_permissions("LONG")
    assert missing == ["business_management", "instagram_manage_comments"]


def accounts_response(*pages):
    return lambda request: json_response({"data": list(pages)})


def test_find_accounts_skips_pages_without_instagram():
    found = auth(
        accounts_response(
            {"name": "Blog", "instagram_business_account": {"id": "1784", "username": "me", "followers_count": 155}},
            {"name": "Old page"},
        )
    ).find_accounts("LONG")
    assert found == [IgAccount("1784", "me", 155, "Blog")]


def test_find_accounts_without_pages():
    with pytest.raises(MetaAuthError) as err:
        auth(accounts_response()).find_accounts("LONG")
    assert err.value.code == "no_pages"


def test_find_accounts_when_no_page_has_instagram():
    with pytest.raises(MetaAuthError) as err:
        auth(accounts_response({"name": "Blog"}, {"name": "Shop"})).find_accounts("LONG")
    assert err.value.code == "no_instagram"
    assert err.value.detail == "Blog, Shop"


def test_credentials_work():
    ok = httpx.MockTransport(lambda r: json_response({"id": "1784"}))
    expired = httpx.MockTransport(lambda r: meta_error("Session has expired", 190))
    assert credentials_work("TOKEN", "1784", transport=ok)
    assert not credentials_work("TOKEN", "1784", transport=expired)
    assert not credentials_work("", "1784", transport=ok)
