from __future__ import annotations

import re
from datetime import UTC, date, datetime, time

from asyncpg import Connection

import db
from slack import InteractivityPayload, SlackClient, Subcommand

_CHANNEL_NAME_MAX = 80


def _incident_channel_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "incident"
    prefix = f"incident-{datetime.now(UTC):%Y%m%d}-"
    return f"{prefix}{slug}"[:_CHANNEL_NAME_MAX].rstrip("-")


def mention(user_id: str) -> str:
    return f"`@{user_id}`"


HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `oncall` — show who is currently on call\n"
    "• `schedule` — configure a recurring on-call rotation\n"
    "• `update` — update the current incident's description (run in an incident channel)\n"
    "• `action` — add an action item to the current incident (run in an incident channel)\n"
    "• `complete` — mark action items complete (run in an incident channel)\n"
    "• `resolve` — resolve the current incident (run in an incident channel)"
)


async def _require_member(
    conn: Connection, slack: SlackClient, channel_id: str, slack_user_id: str
) -> int | None:
    member_id = await db.member_id_by_slack_id(conn, slack_user_id)

    if member_id is None:
        await slack.post_message(
            channel_id,
            f":warning: {mention(slack_user_id)} isn't on the team roster — "
            "add them to @eng and re-run the backfill.",
        )

    return member_id


async def respond_oncall(conn: Connection, slack: SlackClient, response_url: str) -> None:
    oncall = await db.current_oncall(conn)

    if not oncall:
        await slack.respond(response_url, "Nobody is currently on call.")
        return

    lines = "\n".join(
        f"• P{r.escalation_priority}: " + (mention(r.slack_user_id) if r.slack_user_id else r.name)
        for r in oncall
    )

    await slack.respond(response_url, f"*Currently on call*\n{lines}")


async def open_incident(
    conn: Connection,
    slack: SlackClient,
    *,
    name: str,
    lead_member_id: int,
    description: str | None,
    invite_slack_ids: set[str],
) -> tuple[int, str]:
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

    lead = payload.field("lead")
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
        f":rotating_light: Incident #{incident_id} *{name}* opened by "
        f"{mention(payload.user.id)} — lead {mention(lead)}.",
    )

    if origin_channel_id != channel_id:
        await slack.post_message(
            origin_channel_id,
            f":rotating_light: Incident #{incident_id} *{name}* opened — join <#{channel_id}>.",
        )


async def page_member(conn: Connection, slack: SlackClient, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    target = payload.field("target")

    if not target:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} pick a member to page.",
        )
        return

    incident_raw = payload.field("incident_id")
    incident_id = int(incident_raw) if incident_raw and incident_raw.strip().isdigit() else None
    member_id = await _require_member(conn, slack, channel_id, target)

    if member_id is None:
        return

    page = await db.create_page(conn, member_id, incident_id)

    note = f" for incident <#{page.slack_channel_id}>" if page.slack_channel_id else ""
    reason = payload.field("reason")
    detail = f" — {reason}" if reason else ""

    await slack.post_message(
        channel_id,
        f":pager: {mention(target)} you've been paged by {mention(payload.user.id)}{note}{detail}",
    )


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

    assignee = payload.field("assignee")
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
    conn: Connection, slack: SlackClient, incident: db.Incident, actor_slack_id: str
) -> None:
    await db.resolve_incident(conn, incident.id)

    open_items = await db.list_open_action_items(conn, incident.id)
    note = f" {len(open_items)} action item(s) still open." if open_items else ""

    await slack.post_message(
        incident.slack_channel_id,
        f":checkered_flag: {mention(actor_slack_id)} resolved incident *{incident.name}*.{note}",
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


async def configure_rotation(
    conn: Connection, slack: SlackClient, payload: InteractivityPayload
) -> None:
    channel_id = payload.metadata.channel_id
    members = payload.users("members")
    start = payload.field("start")

    if not start:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} a rotation start date is required.",
        )
        return

    anchor = datetime.combine(date.fromisoformat(start), time.min, tzinfo=UTC)

    raw_period = payload.field("period_days") or ""

    if not raw_period.strip().isdigit() or int(raw_period) < 1:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} days per person must be a positive whole number.",
        )
        return

    period_days = int(raw_period)

    member_ids = [
        member_id
        for slack_user_id in members
        if (member_id := await _require_member(conn, slack, channel_id, slack_user_id)) is not None
    ]

    if not member_ids:
        await slack.post_message(
            channel_id,
            f":warning: {mention(payload.user.id)} a rotation needs at least one member.",
        )
        return

    await db.upsert_rotation(conn, member_ids, period_days, anchor)

    levels = min(db.ESCALATION_LEVELS, len(member_ids))
    order = " → ".join(mention(u) for u in members)

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
