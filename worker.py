from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

from asyncpg import Connection, Pool, create_pool
from hatchet_sdk import Context, Depends, Hatchet
from pydantic import BaseModel

from backfill_members import backfill
from commands import HELP_TEXT, Modal, respond_oncall
from settings import Settings
from slack import (
    InteractivityPayload,
    SlackClient,
    Subcommand,
    ViewMetadata,
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


def lifespan_dep(
    _i: Any,
    ctx: Context,
) -> Lifespan:
    return cast(Lifespan, ctx.lifespan)


@asynccontextmanager
async def connection(
    _i: Any,
    ctx: Context,
    lifespan: Annotated[Lifespan, Depends(lifespan_dep)],
) -> AsyncGenerator[Connection, None]:
    async with lifespan.pool.acquire() as conn:
        yield conn


LifespanDep = Annotated[Lifespan, Depends(lifespan_dep)]
ConnectionDep = Annotated[Connection, Depends(connection)]


@hatchet.task(on_events=["slack:slash"], input_validator=SlackSlashCommand)
async def handle_incident_slash_command(
    event: SlackSlashCommand,
    ctx: Context,
    conn: ConnectionDep,
    life: LifespanDep,
) -> None:
    tokens = (event.text or "").split()
    try:
        subcommand = Subcommand(tokens[0].lower()) if tokens else None
    except ValueError:
        subcommand = None

    if subcommand is Subcommand.ONCALL:
        await respond_oncall(conn, life.slack, event.response_url)
        return

    modal = Modal.for_subcommand(subcommand) if subcommand else None
    if modal is None:
        await life.slack.respond(event.response_url, HELP_TEXT)
        return

    metadata = ViewMetadata(channel_id=event.channel_id, user_id=event.user_id)
    await life.slack.views_open(event.trigger_id, modal.value.build(metadata))


@hatchet.task(on_events=["slack:interactivity"], input_validator=InteractivityPayload)
async def handle_interactivity(
    payload: InteractivityPayload,
    ctx: Context,
    conn: ConnectionDep,
    life: LifespanDep,
) -> None:
    if payload.type != "view_submission":
        return
    modal = Modal.for_callback(payload.view.callback_id)
    if modal is None:
        logger.warning("unhandled callback_id: %s", payload.view.callback_id)
        return
    await modal.value.handle(conn, life.slack, payload)


@hatchet.task(on_crons=["0 6 * * *"], input_validator=EmptyInput)
async def backfill_members_cron(
    _: EmptyInput,
    ctx: Context,
    conn: ConnectionDep,
    life: LifespanDep,
) -> None:
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
