from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from asyncpg import Connection
from pydantic import BaseModel


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class OnCallEntry(BaseModel):
    name: str
    slack_user_id: str | None
    escalation_priority: int


ESCALATION_LEVELS = 2
GLOBAL_ROTATION_NAME = "default"


class Rotation(BaseModel):
    id: int
    member_ids: list[int]
    period_days: int
    anchor: datetime


class UnexpectedDBError(Exception):
    """Catchall for unexpected error cases that asyncpg can't figure out (since it's executing plain sql)"""


async def member_id_by_slack_id(conn: Connection, slack_user_id: str) -> int | None:
    row = await conn.fetchrow("SELECT id FROM team_member WHERE slack_user_id = $1", slack_user_id)
    return row["id"] if row else None


async def upsert_member(
    conn: Connection, slack_user_id: str, name: str, slack_handle: str | None
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO team_member (name, slack_user_id, slack_handle)
        VALUES ($1, $2, $3)
        ON CONFLICT (slack_user_id)
        DO UPDATE SET name = EXCLUDED.name, slack_handle = EXCLUDED.slack_handle
        RETURNING id
        """,
        name,
        slack_user_id,
        slack_handle,
    )

    if not row:
        raise UnexpectedDBError(f"Failed to upsert member with slack_user_id {slack_user_id}")

    return row["id"]


async def create_incident(
    conn: Connection, name: str, slack_channel_id: str, lead_member_id: int, description: str | None
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO incident (name, slack_channel_id, lead, description)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        name,
        slack_channel_id,
        lead_member_id,
        description,
    )

    if not row:
        raise UnexpectedDBError(f"Failed to create incident with name {name}")

    return row["id"]


class IncidentOption(BaseModel):
    id: int
    name: str
    slack_channel_id: str


class Incident(BaseModel):
    id: int
    name: str
    slack_channel_id: str
    description: str | None


async def find_open_incident_by_channel_id(
    conn: Connection, slack_channel_id: str
) -> Incident | None:
    row = await conn.fetchrow(
        """
        SELECT id, name, slack_channel_id, description
        FROM incident
        WHERE slack_channel_id = $1 AND status = 'OPEN'
        """,
        slack_channel_id,
    )
    return Incident.model_validate(dict(row)) if row else None


async def update_incident_description(conn: Connection, incident_id: int, description: str) -> None:
    await conn.execute(
        """
        UPDATE incident
        SET description = $2, updated_at = now()
        WHERE id = $1
        """,
        incident_id,
        description,
    )


async def resolve_incident(conn: Connection, incident_id: int) -> None:
    await conn.execute(
        """
        UPDATE incident
        SET status = 'RESOLVED', end_time = now(), updated_at = now()
        WHERE id = $1 AND status = 'OPEN'
        """,
        incident_id,
    )


class ActionItemOption(BaseModel):
    id: int
    description: str


async def list_open_action_items(conn: Connection, incident_id: int) -> list[ActionItemOption]:
    rows = await conn.fetch(
        """
        SELECT id, description
        FROM incident_action_item
        WHERE incident_id = $1 AND is_completed = FALSE
        ORDER BY created_at
        """,
        incident_id,
    )
    return [ActionItemOption.model_validate(dict(row)) for row in rows]


async def complete_action_items(conn: Connection, action_item_ids: list[int]) -> int:
    rows = await conn.fetch(
        """
        UPDATE incident_action_item
        SET is_completed = TRUE, updated_at = now()
        WHERE id = ANY($1::BIGINT[]) AND is_completed = FALSE
        RETURNING id
        """,
        action_item_ids,
    )
    return len(rows)


async def create_action_item(
    conn: Connection, incident_id: int, description: str, assignee_member_id: int | None
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO incident_action_item (incident_id, description, assignee_team_member_id)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        incident_id,
        description,
        assignee_member_id,
    )

    if not row:
        raise UnexpectedDBError(f"Failed to create action item for incident {incident_id}")

    return row["id"]


async def list_open_incidents(conn: Connection) -> list[IncidentOption]:
    rows = await conn.fetch(
        """
        SELECT id, name, slack_channel_id
        FROM incident
        WHERE status = 'OPEN'
        ORDER BY start_time DESC
        """,
    )
    return [IncidentOption.model_validate(dict(row)) for row in rows]


class Page(BaseModel):
    id: int
    incident_id: int | None
    slack_channel_id: str | None


async def create_page(conn: Connection, team_member_id: int, incident_id: int | None) -> Page:
    row = await conn.fetchrow(
        """
        WITH page AS (
            INSERT INTO page (team_member_id, incident_id)
            VALUES ($1, $2)
            RETURNING id
        ), incident AS (
            SELECT *
            FROM incident
            WHERE id = $2
        )

        SELECT p.id, i.slack_channel_id, i.id AS incident_id
        FROM page p, incident i
        """,
        team_member_id,
        incident_id,
    )

    if not row:
        raise UnexpectedDBError(f"Failed to create page for team_member_id {team_member_id}")

    return Page.model_validate(dict(row))


async def upsert_rotation(
    conn: Connection,
    member_ids: list[int],
    period_days: int,
    anchor: datetime,
    name: str = GLOBAL_ROTATION_NAME,
) -> Rotation:
    row = await conn.fetchrow(
        """
        INSERT INTO on_call_rotation (name, member_ids, period_days, anchor)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name) DO UPDATE SET
            member_ids = EXCLUDED.member_ids,
            period_days = EXCLUDED.period_days,
            anchor = EXCLUDED.anchor
        RETURNING id, member_ids, period_days, anchor
        """,
        name,
        member_ids,
        period_days,
        anchor,
    )

    if not row:
        raise UnexpectedDBError("Failed to upsert on-call rotation")

    return Rotation.model_validate(dict(row))


async def current_oncall(conn: Connection) -> list[OnCallEntry]:
    rows = await conn.fetch(
        """
        WITH rotation AS (
            SELECT
                member_ids,
                array_length(member_ids, 1) AS num_members,
                LEAST($1::INT, array_length(member_ids, 1)) AS depth,
                -- index of the window covering now(): floor((now - anchor) / period)
                floor(
                    extract(epoch FROM now() - anchor)
                    / extract(epoch FROM make_interval(days => period_days))
                )::BIGINT AS k
            FROM on_call_rotation
            WHERE now() >= anchor
            LIMIT 1
        ), active_override AS (
            SELECT escalation_priority, team_member_id
            FROM on_call_override
            WHERE shift @> now()
        ), oncall AS (
            -- overrides win at their priority (and may add priorities beyond the stack)
            SELECT escalation_priority, team_member_id
            FROM active_override
            UNION ALL
            -- scheduled seat for each priority the round-robin covers, unless overridden
            SELECT
                priority AS escalation_priority,
                (
                    SELECT r.member_ids[((r.k + priority - 1) % r.num_members)::INT + 1]
                    FROM rotation r
                ) AS team_member_id
            -- depth is bounded by how many members are in the rotation, so this is fine to do
            FROM generate_series(1, (SELECT depth FROM rotation)) AS priority
            WHERE priority NOT IN (SELECT escalation_priority FROM active_override)
        )

        SELECT tm.name, tm.slack_user_id, oncall.escalation_priority
        FROM oncall
        JOIN team_member tm ON tm.id = oncall.team_member_id
        ORDER BY oncall.escalation_priority
        """,
        ESCALATION_LEVELS,
    )

    return [OnCallEntry.model_validate(dict(r)) for r in rows]
