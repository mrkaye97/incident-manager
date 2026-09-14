from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import aiosql
from pydantic import BaseModel

from internal.types import (
    ActionItem,
    ActionItemOption,
    AlertRecord,
    Conn,
    Incident,
    IncidentId,
    IncidentOption,
    IncidentStatus,
    IncidentSummary,
    Member,
    OnCallEntry,
    Override,
    Page,
    PageDelivery,
    PageRecord,
    PendingAcknowledgement,
    PushoverReceipt,
    PushoverUserKey,
    Rotation,
    SlackChannelId,
    SlackUserId,
    TeamMemberId,
)

QUERIES_DIR = Path(__file__).parent / "queries"

ESCALATION_LEVELS = 2
GLOBAL_ROTATION_NAME = "default"

T = TypeVar("T")


class UnexpectedDBError(Exception):
    """Catchall for unexpected error cases that asyncpg can't figure out (since it's executing plain sql)"""


RECORD_CLASSES: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        Member,
        Incident,
        IncidentOption,
        IncidentSummary,
        ActionItemOption,
        ActionItem,
        AlertRecord,
        Page,
        PageDelivery,
        PageRecord,
        PendingAcknowledgement,
        Rotation,
        OnCallEntry,
        Override,
    )
}

queries: Any = aiosql.from_path(QUERIES_DIR, "asyncpg", record_classes=RECORD_CLASSES)


async def _all(rows: AsyncIterator[T]) -> list[T]:
    return [row async for row in rows]


async def member_id_by_slack_id(conn: Conn, slack_user_id: SlackUserId) -> TeamMemberId | None:
    return await queries.member_id_by_slack_id(conn, slack_user_id=slack_user_id)


async def upsert_member(
    conn: Conn, slack_user_id: SlackUserId, name: str, slack_handle: str | None
) -> TeamMemberId:
    member_id = await queries.upsert_member(
        conn, name=name, slack_user_id=slack_user_id, slack_handle=slack_handle
    )

    if member_id is None:
        raise UnexpectedDBError(f"Failed to upsert member with slack_user_id {slack_user_id}")

    return member_id


async def list_members(conn: Conn) -> list[Member]:
    return await _all(queries.list_members(conn))


async def get_member(conn: Conn, member_id: TeamMemberId) -> Member | None:
    return await queries.get_member(conn, member_id=member_id)


async def get_member_by_slack_id(conn: Conn, slack_user_id: SlackUserId) -> Member | None:
    return await queries.get_member_by_slack_id(conn, slack_user_id=slack_user_id)


async def missing_member_ids(conn: Conn, member_ids: list[TeamMemberId]) -> set[TeamMemberId]:
    rows = await _all(queries.existing_member_ids(conn, member_ids=member_ids))
    return set(member_ids) - {row["id"] for row in rows}


async def create_member(
    conn: Conn,
    name: str,
    slack_user_id: SlackUserId | None,
    slack_handle: str | None,
    pushover_user_key: PushoverUserKey | None,
) -> Member:
    member = await queries.create_member(
        conn,
        name=name,
        slack_user_id=slack_user_id,
        slack_handle=slack_handle,
        pushover_user_key=pushover_user_key,
    )

    if member is None:
        raise UnexpectedDBError(f"Failed to create member {name}")

    return member


async def update_member(
    conn: Conn,
    member_id: TeamMemberId,
    name: str,
    slack_user_id: SlackUserId | None,
    slack_handle: str | None,
    pushover_user_key: PushoverUserKey | None,
) -> Member | None:
    return await queries.update_member(
        conn,
        member_id=member_id,
        name=name,
        slack_user_id=slack_user_id,
        slack_handle=slack_handle,
        pushover_user_key=pushover_user_key,
    )


async def create_incident(
    conn: Conn,
    name: str,
    slack_channel_id: SlackChannelId,
    lead_member_id: TeamMemberId,
    description: str | None,
) -> IncidentId:
    incident_id = await queries.create_incident(
        conn,
        name=name,
        slack_channel_id=slack_channel_id,
        lead_member_id=lead_member_id,
        description=description,
    )

    if incident_id is None:
        raise UnexpectedDBError(f"Failed to create incident with name {name}")

    return incident_id


async def find_open_incident_by_channel_id(
    conn: Conn, slack_channel_id: SlackChannelId
) -> Incident | None:
    return await queries.find_open_incident_by_channel_id(conn, slack_channel_id=slack_channel_id)


async def find_open_incident_by_alert_title(conn: Conn, title: str) -> Incident | None:
    return await queries.find_open_incident_by_alert_title(conn, title=title)


async def list_open_incidents(conn: Conn) -> list[IncidentOption]:
    return await _all(queries.list_open_incidents(conn))


async def list_incidents(
    conn: Conn, status: IncidentStatus | None, limit: int
) -> list[IncidentSummary]:
    return await _all(queries.list_incidents(conn, status=status, limit=limit))


async def get_incident(conn: Conn, incident_id: IncidentId) -> IncidentSummary | None:
    return await queries.get_incident(conn, incident_id=incident_id)


async def update_incident_description(
    conn: Conn, incident_id: IncidentId, description: str
) -> None:
    await queries.update_incident_description(
        conn, incident_id=incident_id, description=description
    )


async def resolve_incident(conn: Conn, incident_id: IncidentId) -> IncidentSummary | None:
    """Resolve an open incident, returning it, or None if there's no open incident with that id."""
    if await queries.resolve_incident(conn, incident_id=incident_id) is None:
        return None

    return await get_incident(conn, incident_id)


async def list_open_action_items(conn: Conn, incident_id: IncidentId) -> list[ActionItemOption]:
    return await _all(queries.list_open_action_items(conn, incident_id=incident_id))


async def create_action_item(
    conn: Conn,
    incident_id: IncidentId,
    description: str,
    assignee_member_id: TeamMemberId | None,
) -> int:
    action_item_id = await queries.create_action_item(
        conn,
        incident_id=incident_id,
        description=description,
        assignee_member_id=assignee_member_id,
    )

    if action_item_id is None:
        raise UnexpectedDBError(f"Failed to create action item for incident {incident_id}")

    return action_item_id


async def list_action_items(
    conn: Conn, incident_id: IncidentId | None = None, open_only: bool = False
) -> list[ActionItem]:
    return await _all(queries.list_action_items(conn, incident_id=incident_id, open_only=open_only))


async def get_action_item(conn: Conn, action_item_id: int) -> ActionItem | None:
    return await queries.get_action_item(conn, action_item_id=action_item_id)


async def update_action_item(
    conn: Conn,
    action_item_id: int,
    description: str,
    is_completed: bool,
    assignee_member_id: TeamMemberId | None,
) -> None:
    await queries.update_action_item(
        conn,
        action_item_id=action_item_id,
        description=description,
        is_completed=is_completed,
        assignee_member_id=assignee_member_id,
    )


async def record_alert(
    conn: Conn,
    title: str,
    state: str | None,
    body: str | None,
    source_url: str | None,
    incident_id: IncidentId | None,
) -> int:
    alert_id = await queries.record_alert(
        conn,
        title=title,
        state=state,
        body=body,
        source_url=source_url,
        incident_id=incident_id,
    )

    if alert_id is None:
        raise UnexpectedDBError(f"Failed to record alert with title {title}")

    return alert_id


async def list_incident_alerts(conn: Conn, incident_id: IncidentId) -> list[AlertRecord]:
    return await _all(queries.list_incident_alerts(conn, incident_id=incident_id))


async def create_page(
    conn: Conn, team_member_id: TeamMemberId, incident_id: IncidentId | None
) -> Page:
    page = await queries.create_page(conn, team_member_id=team_member_id, incident_id=incident_id)

    if page is None:
        raise UnexpectedDBError(f"Failed to create page for team_member_id {team_member_id}")

    return page


async def get_page_delivery(conn: Conn, page_id: int) -> PageDelivery | None:
    return await queries.get_page_delivery(conn, page_id=page_id)


async def list_pages(conn: Conn, incident_id: IncidentId | None, limit: int) -> list[PageRecord]:
    return await _all(queries.list_pages(conn, incident_id=incident_id, limit=limit))


async def set_page_pushover_receipt(
    conn: Conn, page_id: int, receipt: PushoverReceipt, expires_at: datetime
) -> None:
    await queries.set_page_pushover_receipt(
        conn, page_id=page_id, pushover_receipt=receipt, pushover_expires_at=expires_at
    )


async def list_pending_acknowledgements(conn: Conn) -> list[PendingAcknowledgement]:
    return await _all(queries.list_pending_acknowledgements(conn))


async def acknowledge_page(conn: Conn, page_id: int, acknowledged_at: datetime) -> None:
    await queries.acknowledge_page(conn, page_id=page_id, acknowledged_at=acknowledged_at)


async def get_rotation(conn: Conn, name: str = GLOBAL_ROTATION_NAME) -> Rotation | None:
    return await queries.get_rotation(conn, name=name)


async def upsert_rotation(
    conn: Conn,
    member_ids: list[TeamMemberId],
    period_days: int,
    anchor: datetime,
    name: str = GLOBAL_ROTATION_NAME,
) -> Rotation:
    rotation = await queries.upsert_rotation(
        conn, name=name, member_ids=member_ids, period_days=period_days, anchor=anchor
    )

    if rotation is None:
        raise UnexpectedDBError("Failed to upsert on-call rotation")

    return rotation


async def current_oncall(conn: Conn) -> list[OnCallEntry]:
    return await _all(queries.current_oncall(conn, escalation_levels=ESCALATION_LEVELS))


async def list_overrides(conn: Conn, start: datetime, end: datetime) -> list[Override]:
    return await _all(queries.list_overrides(conn, start=start, end=end))


async def create_override(
    conn: Conn,
    team_member_id: TeamMemberId,
    start: datetime,
    end: datetime,
    escalation_priority: int,
) -> Override:
    override = await queries.create_override(
        conn,
        team_member_id=team_member_id,
        start=start,
        end=end,
        escalation_priority=escalation_priority,
    )

    if override is None:
        raise UnexpectedDBError(f"Failed to create override for member {team_member_id}")

    return override


async def delete_override(conn: Conn, override_id: int) -> bool:
    return await queries.delete_override(conn, override_id=override_id) != "DELETE 0"


async def create_session(
    conn: Conn, token_hash: str, team_member_id: TeamMemberId, expires_at: datetime
) -> None:
    await queries.create_session(
        conn, token_hash=token_hash, team_member_id=team_member_id, expires_at=expires_at
    )


async def get_session_member(conn: Conn, token_hash: str) -> Member | None:
    return await queries.get_session_member(conn, token_hash=token_hash)


async def delete_session(conn: Conn, token_hash: str) -> None:
    await queries.delete_session(conn, token_hash=token_hash)
