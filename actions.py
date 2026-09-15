from __future__ import annotations

import re
from datetime import UTC, datetime

from asyncpg import Connection
from hatchet_sdk import NonRetryableException

import db
from internal.types import (
    ActionItem,
    Actor,
    CreateActionItemInput,
    CreateIncidentInput,
    IncidentId,
    IncidentSummary,
    Member,
    Page,
    PageMemberInput,
    ResolveIncidentInput,
    SlackChannelId,
    SlackUserId,
    TeamMemberId,
    UpdateActionItemInput,
    UpdateIncidentDescriptionInput,
)
from paging import cancel_incident_pages, push_page
from pushover import PushoverClient
from slack import SlackClient, mention

_CHANNEL_NAME_MAX = 80


class ActionError(NonRetryableException):
    pass


class NotFoundError(ActionError):
    pass


def _incident_channel_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "incident"
    prefix = f"incident-{datetime.now(UTC):%Y%m%d}-"
    return f"{prefix}{slug}"[:_CHANNEL_NAME_MAX].rstrip("-")


def _who(actor: Actor) -> str:
    return mention(actor.slack_user_id) if actor.slack_user_id else actor.name


def _member_label(member: Member) -> str:
    return mention(member.slack_user_id) if member.slack_user_id else member.name


async def _require_member(conn: Connection, member_id: TeamMemberId) -> Member:
    member = await db.get_member(conn, member_id)

    if member is None:
        raise NotFoundError(f"team member {member_id} not found")

    return member


async def _require_incident(conn: Connection, incident_id: IncidentId) -> IncidentSummary:
    incident = await db.get_incident(conn, incident_id)

    if incident is None:
        raise NotFoundError("incident not found")

    return incident


def page_text(
    target_slack_id: SlackUserId,
    paged_by: str,
    incident_channel_id: SlackChannelId | None,
    reason: str | None,
) -> str:
    note = f" for incident <#{incident_channel_id}>" if incident_channel_id else ""
    detail = f" — {reason}" if reason else ""
    return f":pager: {mention(target_slack_id)} you've been paged by {paged_by}{note}{detail}"


async def create_incident(
    conn: Connection, slack: SlackClient, input: CreateIncidentInput
) -> IncidentSummary:
    lead_id = input.lead_member_id

    if lead_id is None:
        oncall = await db.current_oncall(conn)

        if not oncall:
            raise ActionError("no incident lead was chosen and nobody is currently on call")

        lead_id = oncall[0].team_member_id

    lead = await _require_member(conn, lead_id)
    channel_id = await slack.create_channel(_incident_channel_name(input.name))
    incident_id = await db.create_incident(conn, input.name, channel_id, lead.id, input.description)

    await slack.invite_users(
        channel_id, {u for u in (input.actor.slack_user_id, lead.slack_user_id) if u}
    )
    await slack.post_message(
        channel_id,
        f":rotating_light: Incident *{input.name}* (id `{incident_id}`) opened by "
        f"{_who(input.actor)} — lead {_member_label(lead)}.",
    )

    return await _require_incident(conn, incident_id)


async def page_member(
    conn: Connection,
    slack: SlackClient,
    pushover: PushoverClient | None,
    input: PageMemberInput,
) -> Page:
    member = await _require_member(conn, input.team_member_id)

    if input.incident_id is not None:
        await _require_incident(conn, input.incident_id)

    page = await db.create_page(
        conn, member.id, input.incident_id, input.root_page_id, input.escalation_step
    )

    await push_page(conn, pushover, await slack.team_id(), page.id, input.actor.name, input.reason)

    if member.slack_user_id is not None:
        if page.slack_channel_id:
            await slack.invite_users(page.slack_channel_id, {member.slack_user_id})

        await slack.post_message(
            page.slack_channel_id or member.slack_user_id,
            page_text(member.slack_user_id, _who(input.actor), page.slack_channel_id, input.reason),
        )

    return page


async def resolve_incident(
    conn: Connection,
    slack: SlackClient,
    pushover: PushoverClient | None,
    input: ResolveIncidentInput,
) -> IncidentSummary:
    incident = await db.resolve_incident(conn, input.incident_id)

    if incident is None:
        raise NotFoundError("no open incident with that id")

    await cancel_incident_pages(pushover, incident.id)

    note = (
        f" {incident.open_action_items} action item(s) still open."
        if incident.open_action_items
        else ""
    )

    await slack.post_message(
        incident.slack_channel_id,
        f":checkered_flag: {_who(input.actor)} resolved incident *{incident.name}*.{note}",
    )
    await slack.archive_channel(incident.slack_channel_id)

    return incident


async def update_incident_description(
    conn: Connection, slack: SlackClient, input: UpdateIncidentDescriptionInput
) -> IncidentSummary:
    await _require_incident(conn, input.incident_id)
    await db.update_incident_description(conn, input.incident_id, input.description)
    incident = await _require_incident(conn, input.incident_id)

    await slack.post_message(
        incident.slack_channel_id,
        f":pencil: {_who(input.actor)} updated the incident description:\n{input.description}",
    )

    return incident


async def create_action_item(
    conn: Connection, slack: SlackClient, input: CreateActionItemInput
) -> ActionItem:
    incident = await _require_incident(conn, input.incident_id)
    assignee = (
        await _require_member(conn, input.assignee_id) if input.assignee_id is not None else None
    )

    item_id = await db.create_action_item(
        conn, input.incident_id, input.description, input.assignee_id
    )
    item = await db.get_action_item(conn, item_id)

    if item is None:
        raise db.UnexpectedDBError(f"action item {item_id} vanished after insert")

    owner = f" — owner {_member_label(assignee)}" if assignee else ""

    await slack.post_message(
        incident.slack_channel_id,
        f":white_check_mark: {_who(input.actor)} added an action item: {input.description}{owner}",
    )

    return item


async def update_action_item(
    conn: Connection, slack: SlackClient, input: UpdateActionItemInput
) -> ActionItem:
    before = await db.get_action_item(conn, input.action_item_id)

    if before is None:
        raise NotFoundError("action item not found")

    if input.assignee_id is not None:
        await _require_member(conn, input.assignee_id)

    await db.update_action_item(
        conn, input.action_item_id, input.description, input.is_completed, input.assignee_id
    )
    after = await db.get_action_item(conn, input.action_item_id)

    if after is None:
        raise NotFoundError("action item not found")

    if after.is_completed and not before.is_completed:
        incident = await _require_incident(conn, after.incident_id)
        await slack.post_message(
            incident.slack_channel_id,
            f":white_check_mark: {_who(input.actor)} completed an action item: {after.description}",
        )

    return after
