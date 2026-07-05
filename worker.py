import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from asyncpg import Connection, Pool, Record, create_pool
from asyncpg.pool import PoolConnectionProxy
from hatchet_sdk import Context, Depends, EmptyModel, Hatchet
from pydantic import BaseModel

import db
from commands import (
    HELP_TEXT,
    complete_action_items,
    configure_rotation,
    create_action_item,
    create_incident,
    page_member,
    parse_subcommand,
    resolve_incident,
    respond_oncall,
    update_description,
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
    complete_action_items_modal,
    configure_rotation_modal,
    create_action_item_modal,
    create_incident_modal,
    page_member_modal,
    update_description_modal,
)

logger = logging.getLogger("incident-bot")
hatchet = Hatchet()


class Lifespan:
    def __init__(self, pool: Pool, slack: SlackClient, settings: Settings) -> None:
        self.pool = pool
        self.slack = slack
        self.settings = settings


def lifespan_dep(
    _i: BaseModel,
    ctx: Context,
) -> Lifespan:
    return cast(Lifespan, ctx.lifespan)


LifespanDep = Annotated[Lifespan, Depends(lifespan_dep)]


@asynccontextmanager
async def connection(
    _i: BaseModel,
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
            incidents = await db.list_open_incidents(conn)
            await lifespan.slack.views_open(
                event.trigger_id, page_member_modal(metadata, incidents)
            )
        case Subcommand.SCHEDULE:
            await lifespan.slack.views_open(event.trigger_id, configure_rotation_modal(metadata))
        case Subcommand.UPDATE:
            incident = await db.find_open_incident_by_channel_id(conn, event.channel_id)
            if incident is None:
                await lifespan.slack.respond(
                    event.response_url,
                    "Run `update` from an open incident's channel to update its description.",
                )
                return
            metadata.incident_id = incident.id
            await lifespan.slack.views_open(
                event.trigger_id, update_description_modal(metadata, incident.description)
            )
        case Subcommand.ACTION:
            incident = await db.find_open_incident_by_channel_id(conn, event.channel_id)
            if incident is None:
                await lifespan.slack.respond(
                    event.response_url,
                    "Run `action` from an open incident's channel to add an action item.",
                )
                return
            metadata.incident_id = incident.id
            await lifespan.slack.views_open(event.trigger_id, create_action_item_modal(metadata))
        case Subcommand.RESOLVE:
            incident = await db.find_open_incident_by_channel_id(conn, event.channel_id)
            if incident is None:
                await lifespan.slack.respond(
                    event.response_url,
                    "Run `resolve` from an open incident's channel to resolve it.",
                )
                return
            await resolve_incident(conn, lifespan.slack, incident, event.user_id)
        case Subcommand.COMPLETE:
            incident = await db.find_open_incident_by_channel_id(conn, event.channel_id)
            if incident is None:
                await lifespan.slack.respond(
                    event.response_url,
                    "Run `complete` from an open incident's channel to complete action items.",
                )
                return
            items = await db.list_open_action_items(conn, incident.id)
            if not items:
                await lifespan.slack.respond(
                    event.response_url, "This incident has no open action items."
                )
                return
            metadata.incident_id = incident.id
            await lifespan.slack.views_open(
                event.trigger_id, complete_action_items_modal(metadata, items)
            )
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
        case CallbackID.CONFIGURE_ROTATION:
            await configure_rotation(conn, lifespan.slack, payload)
        case CallbackID.UPDATE_DESCRIPTION:
            await update_description(conn, lifespan.slack, payload)
        case CallbackID.CREATE_ACTION_ITEM:
            await create_action_item(conn, lifespan.slack, payload)
        case CallbackID.COMPLETE_ACTION_ITEMS:
            await complete_action_items(conn, lifespan.slack, payload)
        case _:
            logger.warning("unhandled callback_id: %s", payload.view.callback_id)


@hatchet.task(on_crons=["0 6 * * *"])
async def backfill_members(
    _: EmptyModel,
    ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    await backfill(conn, lifespan.slack)


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
        workflows=[
            handle_incident_slash_command,
            handle_interactivity,
            backfill_members,
        ],
        lifespan=lifespan,
    )
    worker.start()


if __name__ == "__main__":
    main()
