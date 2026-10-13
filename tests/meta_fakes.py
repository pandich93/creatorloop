"""A stand-in for meta_auth.MetaAuth: no network, configurable outcomes."""

from datetime import UTC, datetime

from creatorloop.meta_auth import IgAccount, LongLivedToken, MetaAuthError

EXPIRES = datetime(2026, 12, 13, tzinfo=UTC)
ME = IgAccount("1784", "me", 155, "Blog")
SHOP = IgAccount("1785", "shop", 20, "Shop")


class FakeAuth:
    def __init__(self, app_id, app_secret, *, accounts=(ME,), missing=(), find_error=None, expires_at=EXPIRES, **_):
        self.app_id, self.app_secret = app_id.strip(), app_secret.strip()
        self.accounts, self.missing, self.find_error, self.expires_at = list(accounts), list(missing), find_error, expires_at
        self.redirect_uri = None
        self.closed = False

    def validate_app(self):
        if self.app_secret != "secret":
            raise MetaAuthError("bad_app", "Error validating client secret.")

    def login_url(self, redirect_uri, state, *, rerequest=False):
        return f"https://facebook.test/dialog?state={state}&rerequest={int(rerequest)}"

    def exchange_code(self, code, redirect_uri):
        if code != "CODE":
            raise MetaAuthError("code_exchange", "bad code")
        self.redirect_uri = redirect_uri
        return "SHORT"

    def to_long_lived(self, short_token, *, now=None):
        return LongLivedToken("LONG-TOKEN", self.expires_at)

    def missing_permissions(self, token):
        return self.missing

    def find_accounts(self, token):
        if self.find_error:
            raise self.find_error
        return self.accounts

    def close(self):
        self.closed = True
