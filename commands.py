from __future__ import annotations

from uuid import UUID

from asyncpg import Connection

import actions
import db
from actions import ActionError
from escalation import page_and_escalate
from internal.types import (
    Actor,
    CreateActionItemInput,
    CreateIncidentInput,
    IncidentId,
    InteractivityPayload,
    PageMemberInput,
    SlackSlashCommand,
    SlackUserId,
    Subcommand,
    TeamMemberId,
    UpdateActionItemInput,
    UpdateIncidentDescriptionInput,
)
from pushover import PushoverClient
from slack import SlackClient, mention

HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `update` — update the current incident's description (run in an incident channel)\n"
    "• `action` — add an action item to the current incident (run in an incident channel)\n"
    "• `complete` — mark action items complete (run in an incident channel)\n"
    "• `resolve` — resolve the current incident (run in an incident channel)"
)


def parse_subcommand(text: str | None) -> Subcommand | None:
    tokens = (text or "").split()

    if not tokens:
        return None

    try:
        return Subcommand(tokens[0].lower())
    except ValueError:
        return None


def payload_actor(payload: InteractivityPayload) -> Actor:
    return Actor(
        name=payload.user.name or payload.user.username or payload.user.id,
        slack_user_id=payload.user.id,
    )


def command_actor(command: SlackSlashCommand) -> Actor:
    return Actor(name=command.user_name, slack_user_id=command.user_id)


async def _member_id(conn: Connection, slack_user_id: SlackUserId) -> TeamMemberId:
    member_id = await db.member_id_by_slack_id(conn, slack_user_id)

    if member_id is None:
        raise ActionError(
            f"{mention(slack_user_id)} isn't on the team roster — "
            "add them to @eng and re-run the backfill."
        )

    return member_id


def _incident_id(payload: InteractivityPayload) -> IncidentId:
    if payload.metadata.incident_id is None:
        raise ActionError("couldn't tell which incident this is for.")

    return payload.metadata.incident_id


async def submit_create_incident(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    name = payload.field("name")

    if not name:
        raise ActionError("an incident name is required.")

    lead = payload.user_field("lead")
    incident = await actions.create_incident(
        conn,
        slack,
        CreateIncidentInput(
            name=name,
            lead_member_id=await _member_id(conn, lead) if lead else None,
            actor=payload_actor(payload),
        ),
    )

    if payload.metadata.channel_id != incident.slack_channel_id:
        await slack.post_message(
            payload.metadata.channel_id,
            f":rotating_light: Incident *{incident.name}* opened — "
            f"join <#{incident.slack_channel_id}>.",
        )


async def submit_page_member(
    conn: Connection,
    slack: SlackClient,
    pushover: PushoverClient | None,
    payload: InteractivityPayload,
) -> None:
    target = payload.user_field("target")

    if not target:
        raise ActionError("pick a member to page.")

    incident_raw = payload.field("incident_id")
    page = await page_and_escalate(
        conn,
        slack,
        pushover,
        PageMemberInput(
            team_member_id=await _member_id(conn, target),
            incident_id=IncidentId(UUID(incident_raw)) if incident_raw else None,
            reason=payload.field("reason"),
            actor=payload_actor(payload),
        ),
    )

    if payload.metadata.channel_id != page.slack_channel_id:
        await slack.post_message(
            payload.metadata.channel_id,
            f":pager: {mention(payload.user.id)} paged {mention(target)}.",
        )


async def submit_update_description(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    description = payload.field("description")

    if not description:
        raise ActionError("a description is required.")

    await actions.update_incident_description(
        conn,
        slack,
        UpdateIncidentDescriptionInput(
            incident_id=_incident_id(payload),
            description=description,
            actor=payload_actor(payload),
        ),
    )


async def submit_create_action_item(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    description = payload.field("description")

    if not description:
        raise ActionError("an action item description is required.")

    assignee = payload.user_field("assignee")

    await actions.create_action_item(
        conn,
        slack,
        CreateActionItemInput(
            incident_id=_incident_id(payload),
            description=description,
            assignee_id=await _member_id(conn, assignee) if assignee else None,
            actor=payload_actor(payload),
        ),
    )


async def submit_complete_action_items(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    ids = [int(v) for v in payload.options("items") if v.isdigit()]

    if not ids:
        raise ActionError("pick at least one action item to complete.")

    for item_id in ids:
        item = await db.get_action_item(conn, item_id)

        if item is None or item.is_completed:
            continue

        await actions.update_action_item(
            conn,
            slack,
            UpdateActionItemInput(
                action_item_id=item.id,
                description=item.description,
                is_completed=True,
                assignee_id=item.assignee_id,
                actor=payload_actor(payload),
            ),
        )
