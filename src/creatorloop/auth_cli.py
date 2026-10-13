"""Helper CLI: connect your Instagram account, exchange tokens and find your account ID.

Usage:
    uv run creatorloop-auth login [--no-browser] [--port N] [--bind ADDR]
    uv run creatorloop-auth exchange --short-token <TOKEN> [--write]
    uv run creatorloop-auth whoami [--write]
    uv run creatorloop-auth check
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from creatorloop import DISCLAIMER, env_file, paths, setup_web
from creatorloop.config import load_settings

ENV_PATH = paths.home_dir() / ".env"


def _get(url: str, params: dict[str, str]) -> dict:
    resp = httpx.get(url, params=params, timeout=30)
    body = resp.json()
    if "error" in body:
        err = body["error"]
        sys.exit(f"Graph API error: {err.get('message')} (code={err.get('code')})")
    return body


def _write_env(key: str, value: str, path: Path = ENV_PATH) -> None:
    env_file.update(path, {key: value})
    print(f"  -> saved {key} to {path}")


def cmd_login(args: argparse.Namespace) -> None:
    s = load_settings()
    env_path = paths.home_dir() / ".env"
    if args.bind not in {"127.0.0.1", "localhost", "::1"}:
        print(
            f"Listening on {args.bind}: the page is reachable from the network. That is expected inside Docker with "
            "-p 127.0.0.1:PORT:PORT; otherwise keep the default 127.0.0.1.",
            file=sys.stderr,
        )
    try:
        result = setup_web.run(
            env_path,
            open_browser=not args.no_browser,
            port=args.port,
            bind=args.bind,
            api_version=s.api_version,
            app_id=s.app_id or "",
            app_secret=s.app_secret or "",
        )
    except OSError as exc:
        sys.exit(f"Cannot start the setup page on {args.bind}:{args.port}: {exc}. Pass another --port, or check --bind.")
    if result is None:
        sys.exit(
            "The setup page closed before the account was connected (stopped, or the 15-minute limit). "
            "Run `creatorloop-auth login` again."
        )
    print(f"OK: @{result.username} connected, settings saved to {env_path}. "
          f"Restart Claude Desktop if it is running.")


def cmd_exchange(args: argparse.Namespace) -> None:
    s = load_settings()
    if not (s.app_id and s.app_secret):
        sys.exit(f"Set META_APP_ID and META_APP_SECRET in {ENV_PATH} first.")
    body = _get(
        f"{s.base_url}/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": s.app_id,
            "client_secret": s.app_secret,
            "fb_exchange_token": args.short_token,
        },
    )
    token = body["access_token"]
    expires_in = int(body.get("expires_in") or 0)
    expiry = (datetime.now(UTC) + timedelta(seconds=expires_in)).date() if expires_in else "unknown (~60 days)"
    print(f"Long-lived token received, expires: {expiry}")
    if args.write:
        _write_env("IG_ACCESS_TOKEN", token)
    else:
        print(token)


def cmd_whoami(args: argparse.Namespace) -> None:
    s = load_settings()
    if not s.access_token:
        sys.exit("IG_ACCESS_TOKEN is empty.")
    body = _get(
        f"{s.base_url}/me/accounts",
        {"fields": "name,instagram_business_account{id,username,followers_count}", "access_token": s.access_token},
    )
    found = []
    for page in body.get("data", []):
        ig = page.get("instagram_business_account")
        status = f"IG @{ig['username']} id={ig['id']} followers={ig.get('followers_count')}" if ig else "no IG linked"
        print(f"Facebook Page '{page.get('name')}': {status}")
        if ig:
            found.append(ig["id"])
    if not found:
        sys.exit(
            "No Instagram professional account found. Check that IG is Business/Creator, linked to a Facebook Page, "
            "and the token has instagram_basic + pages_show_list."
        )
    if args.write:
        _write_env("IG_USER_ID", found[0])


def cmd_check(_: argparse.Namespace) -> None:
    s = load_settings()
    s.require_credentials()
    body = _get(f"{s.base_url}/{s.ig_user_id}", {"fields": "username,followers_count", "access_token": s.access_token})
    print(f"OK: @{body.get('username')} followers={body.get('followers_count')} api={s.api_version}")
    dbg = _get(f"{s.base_url}/debug_token", {"input_token": s.access_token, "access_token": s.access_token})
    exp = dbg.get("data", {}).get("expires_at") or 0
    if exp:
        left = (datetime.fromtimestamp(exp, UTC) - datetime.now(UTC)).days
        print(f"Token expires {datetime.fromtimestamp(exp, UTC).date()} ({left} days left)")
    else:
        print("Token never expires")


def main() -> None:
    parser = argparse.ArgumentParser(prog="creatorloop-auth", description=__doc__.split("\n")[0], epilog=DISCLAIMER)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("login", help="Connect your Instagram account on a local page in the browser (recommended)")
    p.add_argument("--no-browser", action="store_true", help="Only print the link (e.g. in Docker)")
    p.add_argument("--port", type=int, default=0, help="Port of the setup page (default: any free port)")
    p.add_argument("--bind", default="127.0.0.1", help="Listen address; 0.0.0.0 only inside Docker with -p 127.0.0.1:PORT:PORT")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("exchange", help="Exchange short-lived user token for a long-lived (60 days) one")
    p.add_argument("--short-token", required=True)
    p.add_argument("--write", action="store_true", help="Save to .env instead of printing")
    p.set_defaults(func=cmd_exchange)

    p = sub.add_parser("whoami", help="List Facebook Pages and linked Instagram account IDs")
    p.add_argument("--write", action="store_true", help="Save the first IG_USER_ID to .env")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("check", help="Verify .env credentials with a test request")
    p.set_defaults(func=cmd_check)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:  # missing settings etc.: show the message, not a traceback
        sys.exit(f"Error: {exc}")
    except httpx.HTTPError as exc:
        sys.exit(f"Network error: {exc}")


if __name__ == "__main__":
    main()
