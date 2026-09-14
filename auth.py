from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import aiohttp

from internal.types import SlackUserId

SLACK_AUTHORIZE_URL = "https://slack.com/openid/connect/authorize"
SLACK_API = "https://slack.com/api"

SESSION_COOKIE = "session"
STATE_COOKIE = "oauth_state"
NEXT_COOKIE = "oauth_next"
SESSION_LIFETIME = timedelta(days=30)
STATE_LIFETIME = timedelta(minutes=10)


class SlackAuthError(Exception):
    pass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(UTC) + SESSION_LIFETIME


def safe_next_path(next_path: str | None) -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "scope": "openid profile email",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": new_token(),
    }
    return f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}"


async def _slack(
    session: aiohttp.ClientSession,
    method: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    async with session.post(f"{SLACK_API}/{method}", data=data, headers=headers) as response:
        body = await response.json()

    if not body.get("ok"):
        raise SlackAuthError(f"{method} failed: {body.get('error', response.status)}")

    return body


async def slack_user_id_for_code(
    client_id: str, client_secret: str, code: str, redirect_uri: str
) -> SlackUserId:
    async with aiohttp.ClientSession() as session:
        token = await _slack(
            session,
            "openid.connect.token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        user = await _slack(
            session,
            "openid.connect.userInfo",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )

    return SlackUserId(user["https://slack.com/user_id"])
