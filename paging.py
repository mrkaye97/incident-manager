from __future__ import annotations

import logging

from asyncpg import Connection

import db
from internal.types import IncidentId
from pushover import PushoverClient
from slack import channel_url

logger = logging.getLogger("incident-bot")


async def push_page(
    conn: Connection,
    pushover: PushoverClient | None,
    page_id: int,
    paged_by: str,
    reason: str | None,
) -> None:
    if pushover is None:
        return

    page = await db.get_page_delivery(conn, page_id)

    if page is None:
        raise ValueError(f"page {page_id} not found")

    if page.pushover_receipt is not None:
        return

    if page.pushover_user_key is None:
        logger.info("page %s: %s has no pushover user key, slack only", page_id, page.member_name)
        return

    receipt, expires_at = await pushover.send_page(
        page.pushover_user_key,
        title=f"Paged: {page.incident_name}" if page.incident_name else "You've been paged",
        message=f"{paged_by}: {reason}" if reason else f"Paged by {paged_by}",
        url=channel_url(page.slack_channel_id) if page.slack_channel_id else None,
        incident_id=page.incident_id,
    )

    await db.set_page_pushover_receipt(conn, page_id, receipt, expires_at)


async def cancel_incident_pages(pushover: PushoverClient | None, incident_id: IncidentId) -> None:
    if pushover is not None:
        await pushover.cancel_incident_pages(incident_id)


async def sync_acknowledgements(conn: Connection, pushover: PushoverClient) -> None:
    for page in await db.list_pending_acknowledgements(conn):
        status = await pushover.receipt(page.pushover_receipt)

        if status.acknowledged_at is not None:
            await db.acknowledge_page(conn, page.id, status.acknowledged_at)
            await _silence_chain(conn, pushover, page.root_page_id)


async def _silence_chain(conn: Connection, pushover: PushoverClient, root_page_id: int) -> None:
    for page in await db.list_ringing_chain_pages(conn, root_page_id):
        await pushover.cancel_receipt(page.pushover_receipt)
        await db.stop_page_alert(conn, page.id)
