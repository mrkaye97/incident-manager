from __future__ import annotations

from datetime import date

from asyncpg import Connection
from asyncpg.exceptions import ExclusionViolationError

import db
from slack import InteractivityPayload, SlackClient, Subcommand

HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `oncall` — show who is currently on call\n"
    "• `schedule` — add an on-call shift"
)


async def _require_member(
    conn: Connection, slack: SlackClient, channel_id: str, slack_user_id: str
) -> int | None:
    member_id = await db.member_id_by_slack_id(conn, slack_user_id)
    if member_id is None:
        await slack.post_message(
            channel_id,
            f":warning: <@{slack_user_id}> isn't on the team roster — "
            "add them to @eng and re-run the backfill.",
        )
    return member_id


async def respond_oncall(conn: Connection, slack: SlackClient, response_url: str) -> None:
    oncall = await db.current_oncall(conn)
    if not oncall:
        await slack.respond(response_url, "Nobody is currently on call.")
        return
    lines = "\n".join(
        f"• P{r.escalation_priority}: " + (f"<@{r.slack_user_id}>" if r.slack_user_id else r.name)
        for r in oncall
    )
    await slack.respond(response_url, f"*Currently on call*\n{lines}")


async def create_incident(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    name = payload.field("name")
    lead = payload.field("lead")
    lead_id = await _require_member(conn, slack, channel_id, lead)
    if lead_id is None:
        return
    incident_id = await db.create_incident(
        conn, name, channel_id, lead_id, payload.field("description")
    )
    await slack.post_message(
        channel_id,
        f":rotating_light: Incident #{incident_id} *{name}* opened by "
        f"<@{payload.user.id}> — lead <@{lead}>.",
    )


async def page_member(conn: Connection, slack: SlackClient, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    target = payload.field("target")
    incident_raw = payload.field("incident_id")
    incident_id = int(incident_raw) if incident_raw and incident_raw.strip().isdigit() else None
    member_id = await _require_member(conn, slack, channel_id, target)
    if member_id is None:
        return
    await db.create_page(conn, member_id, incident_id)

    note = f" for incident #{incident_id}" if incident_id else ""
    reason = payload.field("reason")
    detail = f" — {reason}" if reason else ""
    await slack.post_message(
        channel_id,
        f":pager: <@{target}> you've been paged by <@{payload.user.id}>{note}{detail}",
    )


async def add_shift(conn: Connection, slack: SlackClient, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    member = payload.field("member")
    start = date.fromisoformat(payload.field("start"))
    end = date.fromisoformat(payload.field("end"))
    priority = int(payload.field("escalation_priority"))
    member_id = await _require_member(conn, slack, channel_id, member)
    if member_id is None:
        return
    try:
        await db.add_shift(conn, member_id, start, end, priority)
    except ExclusionViolationError:
        await slack.post_message(
            channel_id,
            f":warning: <@{payload.user.id}> that P{priority} shift overlaps an existing one.",
        )
        return
    await slack.post_message(
        channel_id,
        f":calendar: <@{member}> is on call at P{priority} from {start} to {end}.",
    )


def parse_subcommand(text: str | None) -> Subcommand | None:
    tokens = (text or "").split()
    if not tokens:
        return None
    try:
        return Subcommand(tokens[0].lower())
    except ValueError:
        return None
