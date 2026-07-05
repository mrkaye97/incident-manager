import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

from asyncpg import Connection, Pool, Record, create_pool
from asyncpg.pool import PoolConnectionProxy
from hatchet_sdk import Context, Depends, EmptyModel, Hatchet

from commands import (
    HELP_TEXT,
    add_shift,
    create_incident,
    page_member,
    parse_subcommand,
    respond_oncall,
)
from members import backfill
from settings import Settings
from slack import (
    CallbackID,
    InteractivityPayload,
    SlackClient,
    SlackSlashCommand,
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


def lifespan_dep(
    _i: Any,
    ctx: Context,
) -> Lifespan:
    return cast(Lifespan, ctx.lifespan)


LifespanDep = Annotated[Lifespan, Depends(lifespan_dep)]


@asynccontextmanager
async def connection(
    _i: Any,
    ctx: Context,
    lifespan: LifespanDep,
) -> "AsyncGenerator[PoolConnectionProxy[Record], None]":
    async with lifespan.pool.acquire() as conn, conn.transaction():
        yield conn


ConnectionDep = Annotated[Connection, Depends(connection)]


@hatchet.task(on_events=["slack:slash"], input_validator=SlackSlashCommand)
async def handle_incident_slash_command(
    event: SlackSlashCommand,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    metadata = ViewMetadata(channel_id=event.channel_id, user_id=event.user_id)
    match parse_subcommand(event.text):
        case Subcommand.ONCALL:
            await respond_oncall(conn, lifespan.slack, event.response_url)
        case Subcommand.CREATE:
            await lifespan.slack.views_open(event.trigger_id, create_incident_modal(metadata))
        case Subcommand.PAGE:
            await lifespan.slack.views_open(event.trigger_id, page_member_modal(metadata))
        case Subcommand.SCHEDULE:
            await lifespan.slack.views_open(event.trigger_id, add_shift_modal(metadata))
        case _:
            await lifespan.slack.respond(event.response_url, HELP_TEXT)


@hatchet.task(on_events=["slack:interactivity"], input_validator=InteractivityPayload)
async def handle_interactivity(
    payload: InteractivityPayload,
    ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    if payload.type != "view_submission":
        return

    match payload.view.callback_id:
        case CallbackID.CREATE_INCIDENT:
            await create_incident(conn, lifespan.slack, payload)
        case CallbackID.PAGE_MEMBER:
            await page_member(conn, lifespan.slack, payload)
        case CallbackID.ADD_SHIFT:
            await add_shift(conn, lifespan.slack, payload)
        case _:
            logger.warning("unhandled callback_id: %s", payload.view.callback_id)


@hatchet.task(on_crons=["0 6 * * *"])
async def backfill_members(
    _: EmptyModel,
    ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    upserted, scanned = await backfill(conn, lifespan.slack)
    ctx.log(f"backfilled {upserted}/{scanned} members")


async def lifespan() -> AsyncGenerator[Lifespan, None]:
    settings = Settings()  # ty: ignore[missing-argument]
    pool = await create_pool(dsn=settings.database_url)
    slack = SlackClient(settings.slack_bot_oauth_token)
    try:
        yield Lifespan(pool, slack, settings)
    finally:
        await pool.close()


def main() -> None:
    worker = hatchet.worker(
        name="incident-bot",
        workflows=[handle_incident_slash_command, handle_interactivity, backfill_members],
        lifespan=lifespan,
    )
    worker.start()


if __name__ == "__main__":
    main()
