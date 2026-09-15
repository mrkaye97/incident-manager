import logging
from collections.abc import AsyncGenerator

from asyncpg import Connection, create_pool
from hatchet_sdk import Context, EmptyModel

import actions
import commands
import db
from actions import ActionError
from alerts import handle_alert
from escalation import escalate_page, escalation_step, page_and_escalate
from hatchet_client import ConnectionDep, Lifespan, LifespanDep, hatchet
from internal.types import (
    ActionItem,
    CallbackID,
    CreateActionItemInput,
    CreateIncidentInput,
    HyperDXAlert,
    Incident,
    IncidentSummary,
    InteractivityPayload,
    Page,
    PageMemberInput,
    ResolveIncidentInput,
    SlackSlashCommand,
    Subcommand,
    UpdateActionItemInput,
    UpdateIncidentCustomersInput,
    UpdateIncidentDescriptionInput,
    ViewMetadata,
)
from members import backfill
from paging import sync_acknowledgements
from pushover import PushoverClient
from settings import Settings
from slack import (
    SlackClient,
    complete_action_items_modal,
    create_action_item_modal,
    create_incident_modal,
    mention,
    page_member_modal,
    update_description_modal,
)
from webhooks import (
    HYPERDX_ALERT_EVENT,
    SLACK_INTERACTIVITY_EVENT,
    SLACK_SLASH_EVENT,
    ensure_webhooks,
)

logger = logging.getLogger("incident-bot")

CHANNEL_COMMAND_HINTS = {
    Subcommand.UPDATE: "update its description",
    Subcommand.ACTION: "add an action item",
    Subcommand.RESOLVE: "resolve it",
    Subcommand.COMPLETE: "complete action items",
}


async def _open_incident_here(
    conn: Connection,
    slack: SlackClient,
    event: SlackSlashCommand,
    subcommand: Subcommand,
    metadata: ViewMetadata,
) -> Incident | None:
    incident = await db.find_open_incident_by_channel_id(conn, event.channel_id)

    if incident is None:
        await slack.respond(
            event.response_url,
            f"Run `{subcommand}` from an open incident's channel to "
            f"{CHANNEL_COMMAND_HINTS[subcommand]}.",
        )
        return None

    metadata.incident_id = incident.id
    return incident


@hatchet.task(on_events=[SLACK_SLASH_EVENT], input_validator=SlackSlashCommand)
async def handle_incident_slash_command(
    event: SlackSlashCommand,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    slack = lifespan.slack
    metadata = ViewMetadata(channel_id=event.channel_id, user_id=event.user_id)

    match subcommand := commands.parse_subcommand(event.text):
        case Subcommand.CREATE:
            await slack.views_open(event.trigger_id, create_incident_modal(metadata))
        case Subcommand.PAGE:
            incidents = await db.list_open_incidents(conn)
            await slack.views_open(event.trigger_id, page_member_modal(metadata, incidents))
        case Subcommand.UPDATE:
            incident = await _open_incident_here(conn, slack, event, subcommand, metadata)
            if incident is None:
                return
            await slack.views_open(
                event.trigger_id, update_description_modal(metadata, incident.description)
            )
        case Subcommand.ACTION:
            incident = await _open_incident_here(conn, slack, event, subcommand, metadata)
            if incident is None:
                return
            await slack.views_open(event.trigger_id, create_action_item_modal(metadata))
        case Subcommand.RESOLVE:
            incident = await _open_incident_here(conn, slack, event, subcommand, metadata)
            if incident is None:
                return
            try:
                await actions.resolve_incident(
                    conn,
                    slack,
                    lifespan.pushover,
                    ResolveIncidentInput(
                        incident_id=incident.id, actor=commands.command_actor(event)
                    ),
                )
            except ActionError as e:
                await slack.respond(event.response_url, f":warning: {e}")
        case Subcommand.COMPLETE:
            incident = await _open_incident_here(conn, slack, event, subcommand, metadata)
            if incident is None:
                return
            items = await db.list_open_action_items(conn, incident.id)
            if not items:
                await slack.respond(event.response_url, "This incident has no open action items.")
                return
            await slack.views_open(event.trigger_id, complete_action_items_modal(metadata, items))
        case _:
            await slack.respond(event.response_url, commands.HELP_TEXT)


@hatchet.task(on_events=[SLACK_INTERACTIVITY_EVENT], input_validator=InteractivityPayload)
async def handle_interactivity(
    payload: InteractivityPayload,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    if payload.type != "view_submission":
        return

    slack = lifespan.slack

    try:
        match payload.view.callback_id:
            case CallbackID.CREATE_INCIDENT:
                await commands.submit_create_incident(conn, slack, payload)
            case CallbackID.PAGE_MEMBER:
                await commands.submit_page_member(conn, slack, lifespan.pushover, payload)
            case CallbackID.UPDATE_DESCRIPTION:
                await commands.submit_update_description(conn, slack, payload)
            case CallbackID.CREATE_ACTION_ITEM:
                await commands.submit_create_action_item(conn, slack, payload)
            case CallbackID.COMPLETE_ACTION_ITEMS:
                await commands.submit_complete_action_items(conn, slack, payload)
            case _:
                logger.warning("unhandled callback_id: %s", payload.view.callback_id)
    except ActionError as e:
        await slack.post_message(
            payload.metadata.channel_id, f":warning: {mention(payload.user.id)} {e}"
        )


@hatchet.task(
    ## todo: idempotency here, probably?
    on_events=[HYPERDX_ALERT_EVENT],
    input_validator=HyperDXAlert,
    concurrency=1,
)
async def handle_critical_alert(
    alert: HyperDXAlert,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    await handle_alert(conn, lifespan.slack, lifespan.pushover, alert)


@hatchet.task(input_validator=CreateIncidentInput, retries=0)
async def create_incident(
    input: CreateIncidentInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> IncidentSummary:
    return await actions.create_incident(conn, lifespan.slack, input)


@hatchet.task(input_validator=PageMemberInput, retries=0)
async def page_member(
    input: PageMemberInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> Page:
    return await page_and_escalate(conn, lifespan.slack, lifespan.pushover, input)


@hatchet.task(input_validator=ResolveIncidentInput, retries=0)
async def resolve_incident(
    input: ResolveIncidentInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> IncidentSummary:
    return await actions.resolve_incident(conn, lifespan.slack, lifespan.pushover, input)


@hatchet.task(input_validator=UpdateIncidentCustomersInput, retries=0)
async def update_incident_customers(
    input: UpdateIncidentCustomersInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> IncidentSummary:
    return await actions.update_incident_customers(conn, lifespan.slack, input)


@hatchet.task(input_validator=UpdateIncidentDescriptionInput, retries=0)
async def update_incident_description(
    input: UpdateIncidentDescriptionInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> IncidentSummary:
    return await actions.update_incident_description(conn, lifespan.slack, input)


@hatchet.task(input_validator=CreateActionItemInput, retries=0)
async def create_action_item(
    input: CreateActionItemInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> ActionItem:
    return await actions.create_action_item(conn, lifespan.slack, input)


@hatchet.task(input_validator=UpdateActionItemInput, retries=0)
async def update_action_item(
    input: UpdateActionItemInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> ActionItem:
    return await actions.update_action_item(conn, lifespan.slack, input)


@hatchet.task(on_crons=["0 6 * * *"])
async def backfill_members(
    _: EmptyModel,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    await backfill(conn, lifespan.slack)


@hatchet.task(on_crons=["* * * * *"])
async def sync_page_acknowledgements(
    _: EmptyModel,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> None:
    if lifespan.pushover is not None:
        await sync_acknowledgements(conn, lifespan.pushover)


async def lifespan() -> AsyncGenerator[Lifespan, None]:
    settings = Settings()  # ty: ignore[missing-argument]
    await ensure_webhooks(settings)
    pool = await create_pool(dsn=settings.database_url)
    slack = SlackClient(settings.slack_bot_oauth_token)
    pushover = PushoverClient(settings.pushover_app_token) if settings.pushover_app_token else None
    try:
        yield Lifespan(pool, slack, pushover)
    finally:
        await pool.close()


def main() -> None:
    worker = hatchet.worker(
        name="incident-bot",
        workflows=[
            handle_incident_slash_command,
            handle_interactivity,
            handle_critical_alert,
            backfill_members,
            sync_page_acknowledgements,
            create_incident,
            page_member,
            resolve_incident,
            update_incident_description,
            update_incident_customers,
            create_action_item,
            update_action_item,
            escalate_page,
            escalation_step,
        ],
        lifespan=lifespan,
    )
    worker.start()


if __name__ == "__main__":
    main()
