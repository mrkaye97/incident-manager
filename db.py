from __future__ import annotations

from datetime import datetime

from asyncpg import Connection
from pydantic import BaseModel


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


async def create_page(conn: Connection, team_member_id: int, incident_id: int | None) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO page (team_member_id, incident_id)
        VALUES ($1, $2)
        RETURNING id
        """,
        team_member_id,
        incident_id,
    )

    if not row:
        raise UnexpectedDBError(f"Failed to create page for team_member_id {team_member_id}")

    return row["id"]


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
