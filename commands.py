from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from asyncpg import Connection

import db
from internal.types import (
    Incident,
    IncidentId,
    InteractivityPayload,
    SlackChannelId,
    SlackUserId,
    Subcommand,
    TeamMemberId,
)
from slack import SlackClient

logger = logging.getLogger("incident-bot")

_CHANNEL_NAME_MAX = 80


def _incident_channel_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "incident"
    prefix = f"incident-{datetime.now(UTC):%Y%m%d}-"
    return f"{prefix}{slug}"[:_CHANNEL_NAME_MAX].rstrip("-")


def mention(user_id: SlackUserId) -> str:
    return f"`@{user_id}`"


HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `update` — update the current incident's description (run in an incident channel)\n"
    "• `action` — add an action item to the current incident (run in an incident channel)\n"
    "• `complete` — mark action items complete (run in an incident channel)\n"
    "• `resolve` — resolve the current incident (run in an incident channel)"
)


async def _require_member(
    conn: Connection, slack: SlackClient, channel_id: SlackChannelId, slack_user_id: SlackUserId
) -> TeamMemberId | None:
    member_id = await db.member_id_by_slack_id(conn, slack_user_id)

    if member_id is None:
        await slack.post_message(
            channel_id,
            f":warning: {mention(slack_user_id)} isn't on the team roster — "
            "add them to @eng and re-run the backfill.",
        )

    return member_id


async def open_incident(
    conn: Connection,
    slack: SlackClient,
    *,
    name: str,
    lead_member_id: TeamMemberId,
    description: str | None,
    invite_slack_ids: set[SlackUserId],
) -> tuple[IncidentId, SlackChannelId]:
    channel_id = await slack.create_channel(_incident_channel_name(name)[:80])
    incident_id = await db.create_incident(conn, name, channel_id, lead_member_id, description)

    await slack.invite_users(channel_id, invite_slack_ids)

    return incident_id, channel_id


async def create_incident(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    origin_channel_id = payload.metadata.channel_id
    name = payload.field("name")
    if not name:
        await slack.post_message(
            origin_channel_id,
            f":warning: {mention(payload.user.id)} an incident name is required.",
        )
        return

    lead = payload.user_field("lead")
    if not lead:
        oncall = await db.current_oncall(conn)
        primary = next((o for o in oncall if o.slack_user_id), None)

        if primary is None or primary.slack_user_id is None:
            await slack.post_message(
                origin_channel_id,
                f":warning: {mention(payload.user.id)} no incident lead was chosen and nobody "
                "is currently on call — pick a lead and try again.",
            )
            return

        lead = primary.slack_user_id

    lead_id = await _require_member(conn, slack, origin_channel_id, lead)

    if lead_id is None:
        return

    incident_id, channel_id = await open_incident(
        conn,
        slack,
        name=name,
        lead_member_id=lead_id,
        description=None,
        invite_slack_ids={payload.user.id, lead},
    )

    await slack.post_message(
        channel_id,
        f":rotating_light: Incident *{name}* (id `{incident_id}`) opened by "
        f"{mention(payload.user.id)} — lead {mention(lead)}.",
    )

    if origin_channel_id != channel_id:
        await slack.post_message(
            origin_channel_id,
            f":rotating_light: Incident *{name}* opened — join <#{channel_id}>.",
        )


async def page_member(conn: Connection, slack: SlackClient, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    target = payload.user_field("target")

    if not target:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} pick a member to page.",
        )
        return

    incident_raw = payload.field("incident_id")
    incident_id = IncidentId(UUID(incident_raw)) if incident_raw else None
    member_id = await _require_member(conn, slack, channel_id, target)

    if member_id is None:
        return

    page = await db.create_page(conn, member_id, incident_id)

    await slack.post_message(
        channel_id,
        page_text(target, mention(payload.user.id), page.slack_channel_id, payload.field("reason")),
    )


def page_text(
    target_slack_id: SlackUserId,
    paged_by: str,
    incident_channel_id: SlackChannelId | None,
    reason: str | None,
) -> str:
    note = f" for incident <#{incident_channel_id}>" if incident_channel_id else ""
    detail = f" — {reason}" if reason else ""
    return f":pager: {mention(target_slack_id)} you've been paged by {paged_by}{note}{detail}"


async def deliver_page(
    conn: Connection, slack: SlackClient, page_id: int, reason: str | None, paged_by: str
) -> None:
    page = await db.get_page_delivery(conn, page_id)

    if page is None:
        raise ValueError(f"page {page_id} not found")

    if page.slack_user_id is None:
        logger.warning("page %s: member %s has no slack user id", page_id, page.member_name)
        return

    text = page_text(page.slack_user_id, paged_by, page.slack_channel_id, reason)

    if page.slack_channel_id:
        await slack.invite_users(page.slack_channel_id, {page.slack_user_id})

    await slack.post_message(page.slack_channel_id or page.slack_user_id, text)


async def update_description(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    incident_id = payload.metadata.incident_id

    if incident_id is None:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} couldn't tell which incident to update.",
        )
        return

    description = payload.field("description")

    if not description:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} a description is required.",
        )
        return

    await db.update_incident_description(conn, incident_id, description)

    await slack.post_message(
        channel_id,
        f":pencil: {mention(payload.user.id)} updated the incident description:\n{description}",
    )


async def create_action_item(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    incident_id = payload.metadata.incident_id

    if incident_id is None:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} couldn't tell which incident this is for.",
        )
        return

    description = payload.field("description")

    if not description:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} an action item description is required.",
        )
        return

    assignee = payload.user_field("assignee")
    assignee_id = None

    if assignee:
        assignee_id = await _require_member(conn, slack, channel_id, assignee)
        if assignee_id is None:
            return

    await db.create_action_item(conn, incident_id, description, assignee_id)

    owner = f" — owner {mention(assignee)}" if assignee else ""
    await slack.post_message(
        channel_id,
        f":white_check_mark: {mention(payload.user.id)} added an action item: {description}{owner}",
    )


async def resolve_incident(
    conn: Connection, slack: SlackClient, incident: Incident, actor_slack_id: SlackUserId
) -> None:
    await db.resolve_incident(conn, incident.id)
    await announce_resolution(conn, slack, incident.id, mention(actor_slack_id))


async def announce_resolution(
    conn: Connection, slack: SlackClient, incident_id: IncidentId, resolved_by: str
) -> None:
    incident = await db.get_incident(conn, incident_id)

    if incident is None:
        raise ValueError(f"incident {incident_id} not found")

    note = (
        f" {incident.open_action_items} action item(s) still open."
        if incident.open_action_items
        else ""
    )

    await slack.post_message(
        incident.slack_channel_id,
        f":checkered_flag: {resolved_by} resolved incident *{incident.name}*.{note}",
    )


async def complete_action_items(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    ids = [int(v) for v in payload.options("items") if v.isdigit()]

    if not ids:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} pick at least one action item to complete.",
        )
        return

    completed = await db.complete_action_items(conn, ids)

    await slack.post_message(
        channel_id,
        f":white_check_mark: {mention(payload.user.id)} completed {completed} action item(s).",
    )


def parse_subcommand(text: str | None) -> Subcommand | None:
    tokens = (text or "").split()

    if not tokens:
        return None

    try:
        return Subcommand(tokens[0].lower())
    except ValueError:
        return None
