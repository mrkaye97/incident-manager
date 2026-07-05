from __future__ import annotations

from datetime import UTC, date, datetime, time

from asyncpg import Connection
from pydantic import BaseModel


class OnCallEntry(BaseModel):
    name: str
    slack_user_id: str | None
    escalation_priority: int


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


async def add_shift(
    conn: Connection,
    team_member_id: int,
    start: date,
    end: date,
    escalation_priority: int,
) -> int:
    start_ts = datetime.combine(start, time.min, tzinfo=UTC)
    end_ts = datetime.combine(end, time.min, tzinfo=UTC)
    row = await conn.fetchrow(
        """
        INSERT INTO on_call_shift (team_member_id, shift, escalation_priority)
        VALUES ($1, tstzrange($2, $3, '[)'), $4)
        RETURNING id
        """,
        team_member_id,
        start_ts,
        end_ts,
        escalation_priority,
    )

    if not row:
        raise UnexpectedDBError(
            f"Failed to add shift for team_member_id {team_member_id} from {start} to {end}"
        )

    return row["id"]


async def current_oncall(conn: Connection) -> list[OnCallEntry]:
    rows = await conn.fetch("""
        SELECT tm.name, tm.slack_user_id, s.escalation_priority
        FROM on_call_shift s
        JOIN team_member tm ON tm.id = s.team_member_id
        WHERE s.shift @> now()
        ORDER BY s.escalation_priority
        """)

    return [OnCallEntry.model_validate(dict(r)) for r in rows]
