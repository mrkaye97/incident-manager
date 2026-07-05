from __future__ import annotations

from datetime import UTC, date, datetime, time

from asyncpg import Connection

import db
from slack import InteractivityPayload, SlackClient, Subcommand

HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `oncall` — show who is currently on call\n"
    "• `schedule` — configure a recurring on-call rotation"
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


async def configure_rotation(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    members = payload.users("members")
    anchor = datetime.combine(date.fromisoformat(payload.field("start")), time.min, tzinfo=UTC)

    raw_period = payload.field("period_days") or ""
    if not raw_period.strip().isdigit() or int(raw_period) < 1:
        await slack.post_message(
            channel_id,
            f":warning: <@{payload.user.id}> days per person must be a positive whole number.",
        )
        return
    period_days = int(raw_period)

    member_ids: list[int] = []
    for slack_user_id in members:
        member_id = await _require_member(conn, slack, channel_id, slack_user_id)
        if member_id is None:
            return
        member_ids.append(member_id)
    if not member_ids:
        await slack.post_message(
            channel_id,
            f":warning: <@{payload.user.id}> a rotation needs at least one member.",
        )
        return

    await db.upsert_rotation(conn, member_ids, period_days, anchor)

    levels = min(db.ESCALATION_LEVELS, len(member_ids))
    order = " → ".join(f"<@{u}>" for u in members)
    await slack.post_message(
        channel_id,
        f":calendar: On-call rotation configured: {order}, rotating every "
        f"{period_days} day(s) from {anchor.date()}. Each shift stacks {levels} level(s) "
        f"(P1–P{levels}).",
    )


def parse_subcommand(text: str | None) -> Subcommand | None:
    tokens = (text or "").split()
    if not tokens:
        return None
    try:
        return Subcommand(tokens[0].lower())
    except ValueError:
        return None
