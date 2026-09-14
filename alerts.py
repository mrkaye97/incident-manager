from __future__ import annotations

import logging

from asyncpg import Connection

import db
from commands import mention, open_incident
from internal.types import AlertState, HyperDXAlert, IncidentId
from slack import SlackClient

logger = logging.getLogger("incident-bot")


def _link(alert: HyperDXAlert) -> str:
    return f"\n<{alert.link}|View in HyperDX>" if alert.link else ""


def _body(alert: HyperDXAlert) -> str:
    return f"\n> {alert.body}" if alert.body else ""


async def _record(conn: Connection, alert: HyperDXAlert, incident_id: IncidentId | None) -> None:
    await db.record_alert(conn, alert.title, alert.state, alert.body, alert.link, incident_id)


async def handle_alert(conn: Connection, slack: SlackClient, alert: HyperDXAlert) -> None:
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

    oncall = await db.current_oncall(conn)
    primary = next((o for o in oncall if o.slack_user_id), None)

    if primary is None or primary.slack_user_id is None:
        await _record(conn, alert, None)
        logger.warning(
            "hyperdx alert %r firing but nobody is on call — no incident opened", alert.title
        )
        return

    lead_id = await db.member_id_by_slack_id(conn, primary.slack_user_id)

    if lead_id is None:
        await _record(conn, alert, None)
        logger.warning(
            "on-call %s for alert %r isn't on the team roster — no incident opened",
            primary.slack_user_id,
            alert.title,
        )
        return

    incident_id, channel_id = await open_incident(
        conn,
        slack,
        name=alert.title,
        lead_member_id=lead_id,
        description=alert.body,
        invite_slack_ids={primary.slack_user_id},
    )

    await _record(conn, alert, incident_id)
    await db.create_page(conn, lead_id, incident_id)

    await slack.post_message(
        channel_id,
        f":rotating_light: Incident *{alert.title}* opened from a HyperDX alert. "
        f"Paged {mention(primary.slack_user_id)} (on-call).{_link(alert)}{_body(alert)}",
    )
