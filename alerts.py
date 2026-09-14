from __future__ import annotations

import logging

from asyncpg import Connection

import actions
import db
from actions import ActionError
from escalation import page_and_escalate
from internal.types import (
    Actor,
    AlertState,
    CreateIncidentInput,
    HyperDXAlert,
    IncidentId,
    PageMemberInput,
)
from pushover import PushoverClient
from slack import SlackClient

logger = logging.getLogger("incident-bot")


def _link(alert: HyperDXAlert) -> str:
    return f"\n<{alert.link}|View in HyperDX>" if alert.link else ""


def _body(alert: HyperDXAlert) -> str:
    return f"\n> {alert.body}" if alert.body else ""


async def _record(conn: Connection, alert: HyperDXAlert, incident_id: IncidentId | None) -> None:
    await db.record_alert(conn, alert.title, alert.state, alert.body, alert.link, incident_id)


async def handle_alert(
    conn: Connection, slack: SlackClient, pushover: PushoverClient | None, alert: HyperDXAlert
) -> None:
    existing = await db.find_open_incident_by_alert_title(conn, alert.title)

    if alert.state != AlertState.ALERT:
        # Not an active firing (OK / INSUFFICIENT_DATA / test). Note it on an open incident
        # if we have one, but never open or page off a non-firing state.
        if existing is not None:
            await _record(conn, alert, existing.id)
            await slack.post_message(
                existing.slack_channel_id,
                f":large_green_circle: HyperDX reports *{alert.title}* is now "
                f"`{alert.state}`.{_link(alert)}",
            )
        else:
            logger.info("ignoring non-firing hyperdx alert %r (state=%s)", alert.title, alert.state)

        return

    if existing is not None:
        await _record(conn, alert, existing.id)
        await slack.post_message(
            existing.slack_channel_id,
            f":repeat: HyperDX alert *{alert.title}* fired again "
            f"— folded into this incident.{_link(alert)}{_body(alert)}",
        )
        return

    hyperdx = Actor(name="HyperDX")

    try:
        incident = await actions.create_incident(
            conn,
            slack,
            CreateIncidentInput(name=alert.title, description=alert.body, actor=hyperdx),
        )
    except ActionError as e:
        await _record(conn, alert, None)
        logger.warning("hyperdx alert %r firing but no incident opened: %s", alert.title, e)
        return

    await _record(conn, alert, incident.id)
    await page_and_escalate(
        conn,
        slack,
        pushover,
        PageMemberInput(
            team_member_id=incident.lead_id,
            incident_id=incident.id,
            reason=alert.title,
            actor=hyperdx,
        ),
    )
    await slack.post_message(
        incident.slack_channel_id,
        f":rotating_light: Opened from a HyperDX alert.{_link(alert)}{_body(alert)}",
    )
