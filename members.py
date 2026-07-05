from __future__ import annotations

from asyncpg import Connection

import db
from slack import SlackClient, SlackMember

ENG_GROUP_HANDLE = "eng"


async def backfill(
    conn: Connection,
    slack: SlackClient,
    group_handle: str = ENG_GROUP_HANDLE,
) -> None:
    team_id = await slack.team_id()
    group_ids = await slack.usergroup_member_ids(group_handle)
    members = await slack.users_list()

    for member in members:
        if member.id in group_ids and _is_org_human(member, team_id):
            await db.upsert_member(conn, member.id, member.display_name, member.name)


def _is_org_human(member: SlackMember, team_id: str) -> bool:
    return not (
        member.deleted
        or member.is_bot
        or member.is_app_user
        or member.is_stranger
        or member.is_restricted
        or member.is_ultra_restricted
        or member.id == "USLACKBOT"
        or member.team_id != team_id
    )
