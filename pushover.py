from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiohttp
from pydantic import BaseModel

from internal.types import IncidentId, PushoverReceipt, PushoverUserKey

API = "https://api.pushover.net/1"

RETRY_SECONDS = 30
EXPIRE_SECONDS = 50 * RETRY_SECONDS
PAGE_SOUND = "persistent"


class PushoverError(Exception):
    pass


class ReceiptStatus(BaseModel):
    acknowledged: bool
    acknowledged_at: datetime | None
    expired: bool


def incident_tag(incident_id: IncidentId) -> str:
    return f"incident{incident_id.hex}"


class PushoverClient:
    def __init__(self, app_token: str) -> None:
        self._token = app_token

    async def _request(self, method: str, path: str, data: dict[str, str] | None = None) -> dict:
        async with (
            aiohttp.ClientSession() as session,
            session.request(
                method,
                f"{API}{path}",
                data={"token": self._token, **(data or {})} if method == "POST" else None,
                params={"token": self._token} if method == "GET" else None,
            ) as response,
        ):
            body = await response.json()

            if response.status != 200 or body.get("status") != 1:
                raise PushoverError(f"{method} {path} failed ({response.status}): {body}")

            return body

    async def send_page(
        self,
        user_key: PushoverUserKey,
        title: str,
        message: str,
        url: str | None,
        incident_id: IncidentId | None,
    ) -> tuple[PushoverReceipt, datetime]:
        """Send an emergency-priority page; returns its receipt and when it stops re-alerting."""
        data = {
            "user": user_key,
            "title": title[:250],
            "message": message[:1024],
            "priority": "2",
            "sound": PAGE_SOUND,
            "retry": str(RETRY_SECONDS),
            "expire": str(EXPIRE_SECONDS),
        }

        if url:
            data |= {"url": url, "url_title": "Open in Slack"}

        if incident_id:
            data["tags"] = incident_tag(incident_id)

        body = await self._request("POST", "/messages.json", data)
        expires_at = datetime.now(UTC) + timedelta(seconds=EXPIRE_SECONDS)

        return PushoverReceipt(body["receipt"]), expires_at

    async def receipt(self, receipt: PushoverReceipt) -> ReceiptStatus:
        body = await self._request("GET", f"/receipts/{receipt}.json")

        return ReceiptStatus(
            acknowledged=bool(body["acknowledged"]),
            acknowledged_at=(
                datetime.fromtimestamp(body["acknowledged_at"], UTC)
                if body["acknowledged_at"]
                else None
            ),
            expired=bool(body["expired"]),
        )

    async def cancel_receipt(self, receipt: PushoverReceipt) -> None:
        await self._request("POST", f"/receipts/{receipt}/cancel.json")

    async def cancel_incident_pages(self, incident_id: IncidentId) -> None:
        await self._request("POST", f"/receipts/cancel_by_tag/{incident_tag(incident_id)}.json")
