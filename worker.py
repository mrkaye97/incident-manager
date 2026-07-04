from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date
from enum import Enum
from typing import cast

from asyncpg import Pool, create_pool
from asyncpg.exceptions import ExclusionViolationError
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel
from slack_sdk.models.views import View

import db
from backfill_members import backfill
from settings import Settings
from slack import (
    CallbackID,
    InteractivityPayload,
    SlackClient,
    Subcommand,
    ViewMetadata,
    add_shift_modal,
    create_incident_modal,
    page_member_modal,
)

logger = logging.getLogger("incident-bot")
hatchet = Hatchet()


class Lifespan:
    def __init__(self, pool: Pool, slack: SlackClient, settings: Settings) -> None:
        self.pool = pool
        self.slack = slack
        self.settings = settings


class SlackSlashCommand(BaseModel):
    text: str | None
    token: str
    command: str
    team_id: str
    user_id: str
    user_name: str
    api_app_id: str
    channel_id: str
    trigger_id: str
    team_domain: str
    channel_name: str
    response_url: str
    is_enterprise_install: bool


class EmptyInput(BaseModel):
    pass


HELP_TEXT = (
    "*Incident bot commands*\n"
    "• `create` — open an incident\n"
    "• `page` — page a team member\n"
    "• `oncall` — show who is currently on call\n"
    "• `schedule` — add an on-call shift"
)


async def _require_member(life: Lifespan, channel_id: str, slack_user_id: str) -> int | None:
    async with life.pool.acquire() as conn:
        member_id = await db.member_id_by_slack_id(conn, slack_user_id)
    if member_id is None:
        await life.slack.post_message(
            channel_id,
            f":warning: <@{slack_user_id}> isn't on the team roster — "
            "add them to @eng and re-run the backfill.",
        )
    return member_id


async def _respond_oncall(life: Lifespan, response_url: str) -> None:
    async with life.pool.acquire() as conn:
        oncall = await db.current_oncall(conn)
    if not oncall:
        await life.slack.respond(response_url, "Nobody is currently on call.")
        return
    lines = "\n".join(
        f"• P{r.escalation_priority}: " + (f"<@{r.slack_user_id}>" if r.slack_user_id else r.name)
        for r in oncall
    )
    await life.slack.respond(response_url, f"*Currently on call*\n{lines}")


async def _create_incident(life: Lifespan, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    name = payload.field("name")
    lead = payload.field("lead")
    lead_id = await _require_member(life, channel_id, lead)
    if lead_id is None:
        return
    async with life.pool.acquire() as conn:
        incident_id = await db.create_incident(
            conn, name, channel_id, lead_id, payload.field("description")
        )
    await life.slack.post_message(
        channel_id,
        f":rotating_light: Incident #{incident_id} *{name}* opened by "
        f"<@{payload.user.id}> — lead <@{lead}>.",
    )


async def _page_member(life: Lifespan, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    target = payload.field("target")
    incident_raw = payload.field("incident_id")
    incident_id = int(incident_raw) if incident_raw and incident_raw.strip().isdigit() else None
    member_id = await _require_member(life, channel_id, target)
    if member_id is None:
        return
    async with life.pool.acquire() as conn:
        await db.create_page(conn, member_id, incident_id)

    note = f" for incident #{incident_id}" if incident_id else ""
    reason = payload.field("reason")
    detail = f" — {reason}" if reason else ""
    await life.slack.post_message(
        channel_id,
        f":pager: <@{target}> you've been paged by <@{payload.user.id}>{note}{detail}",
    )


async def _add_shift(life: Lifespan, payload: InteractivityPayload) -> None:
    channel_id = payload.metadata.channel_id
    member = payload.field("member")
    start = date.fromisoformat(payload.field("start"))
    end = date.fromisoformat(payload.field("end"))
    priority = int(payload.field("escalation_priority"))
    member_id = await _require_member(life, channel_id, member)
    if member_id is None:
        return
    try:
        async with life.pool.acquire() as conn:
            await db.add_shift(conn, member_id, start, end, priority)
    except ExclusionViolationError:
        await life.slack.post_message(
            channel_id,
            f":warning: <@{payload.user.id}> that P{priority} shift overlaps an existing one.",
        )
        return
    await life.slack.post_message(
        channel_id,
        f":calendar: <@{member}> is on call at P{priority} from {start} to {end}.",
    )


ModalBuilder = Callable[[ViewMetadata], View]
ModalHandler = Callable[["Lifespan", InteractivityPayload], Awaitable[None]]


class Modal(Enum):
    CREATE = (
        Subcommand.CREATE,
        CallbackID.CREATE_INCIDENT,
        create_incident_modal,
        _create_incident,
    )
    PAGE = (Subcommand.PAGE, CallbackID.PAGE_MEMBER, page_member_modal, _page_member)
    SCHEDULE = (Subcommand.SCHEDULE, CallbackID.ADD_SHIFT, add_shift_modal, _add_shift)

    subcommand: Subcommand
    callback_id: CallbackID
    build: ModalBuilder
    handle: ModalHandler

    def __init__(
        self,
        subcommand: Subcommand,
        callback_id: CallbackID,
        build: ModalBuilder,
        handle: ModalHandler,
    ) -> None:
        self.subcommand = subcommand
        self.callback_id = callback_id
        self.build = build
        self.handle = handle

    @classmethod
    def for_subcommand(cls, subcommand: Subcommand) -> Modal | None:
        return next((m for m in cls if m.subcommand is subcommand), None)

    @classmethod
    def for_callback(cls, callback_id: str) -> Modal | None:
        return next((m for m in cls if m.callback_id == callback_id), None)


@hatchet.task(on_events=["slack:slash"], input_validator=SlackSlashCommand)
async def handle_incident_slash_command(event: SlackSlashCommand, ctx: Context) -> None:
    life = cast(Lifespan, ctx.lifespan)
    tokens = (event.text or "").split()
    try:
        subcommand = Subcommand(tokens[0].lower()) if tokens else None
    except ValueError:
        subcommand = None

    if subcommand is Subcommand.ONCALL:
        await _respond_oncall(life, event.response_url)
        return

    modal = Modal.for_subcommand(subcommand) if subcommand else None
    if modal is None:
        await life.slack.respond(event.response_url, HELP_TEXT)
        return

    metadata = ViewMetadata(channel_id=event.channel_id, user_id=event.user_id)
    await life.slack.views_open(event.trigger_id, modal.build(metadata))


@hatchet.task(on_events=["slack:interactivity"], input_validator=InteractivityPayload)
async def handle_interactivity(payload: InteractivityPayload, ctx: Context) -> None:
    if payload.type != "view_submission":
        return
    modal = Modal.for_callback(payload.view.callback_id)
    if modal is None:
        logger.warning("unhandled callback_id: %s", payload.view.callback_id)
        return
    await modal.handle(cast(Lifespan, ctx.lifespan), payload)


@hatchet.task(on_crons=["0 6 * * *"], input_validator=EmptyInput)
async def backfill_members_cron(_: EmptyInput, ctx: Context) -> None:
    life = cast(Lifespan, ctx.lifespan)
    async with life.pool.acquire() as conn:
        upserted, scanned = await backfill(conn, life.slack)
    ctx.log(f"backfilled {upserted}/{scanned} members")


async def lifespan() -> AsyncGenerator[Lifespan, None]:
    settings = Settings()  # ty: ignore[missing-argument]
    pool = cast(Pool, await create_pool(dsn=settings.database_url))
    slack = SlackClient(settings.slack_bot_oauth_token)
    try:
        yield Lifespan(pool, slack, settings)
    finally:
        await pool.close()


def main() -> None:
    worker = hatchet.worker(
        name="incident-bot",
        workflows=[handle_incident_slash_command, handle_interactivity, backfill_members_cron],
        lifespan=lifespan,
    )
    worker.start()


if __name__ == "__main__":
    main()
