from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from asyncpg import Pool, create_pool
from asyncpg.exceptions import (
    ExclusionViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
)
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

import db
from internal.types import (
    ActionItem,
    AlertRecord,
    AnnounceResolutionInput,
    Conn,
    DeliverPageInput,
    IncidentId,
    IncidentStatus,
    IncidentSummary,
    Member,
    OnCallEntry,
    Override,
    PageRecord,
    Rotation,
    Shift,
    SlackUserId,
    TeamMemberId,
)
from schedule import build_schedule
from settings import Settings
from worker import announce_incident_resolution, backfill_members, deliver_page_notification

settings = Settings()  # ty: ignore[missing-argument]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.pool = await create_pool(dsn=settings.database_url)
    try:
        yield
    finally:
        await app.state.pool.close()


def pool(request: Request) -> Pool:
    return request.app.state.pool


PoolDep = Annotated[Pool, Depends(pool)]

router = APIRouter(prefix="/api")


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def _require_members(conn: Conn, member_ids: list[TeamMemberId]) -> None:
    if missing := await db.missing_member_ids(conn, member_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown team member(s): {sorted(missing)}"
        )


class AppConfig(BaseModel):
    status_page_url: str
    escalation_levels: int


@router.get("/config")
async def get_config() -> AppConfig:
    return AppConfig(
        status_page_url=settings.status_page_url, escalation_levels=db.ESCALATION_LEVELS
    )


class IncidentDetail(BaseModel):
    incident: IncidentSummary
    action_items: list[ActionItem]
    alerts: list[AlertRecord]
    pages: list[PageRecord]


class IncidentUpdate(BaseModel):
    description: str


@router.get("/incidents")
async def list_incidents(
    pool: PoolDep,
    status: IncidentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[IncidentSummary]:
    async with pool.acquire() as conn:
        return await db.list_incidents(conn, status, limit)


@router.get("/incidents/{incident_id}")
async def get_incident(pool: PoolDep, incident_id: IncidentId) -> IncidentDetail:
    async with pool.acquire() as conn:
        incident = await db.get_incident(conn, incident_id)

        if incident is None:
            raise _not_found("incident")

        return IncidentDetail(
            incident=incident,
            action_items=await db.list_action_items(conn, incident_id),
            alerts=await db.list_incident_alerts(conn, incident_id),
            pages=await db.list_pages(conn, incident_id, limit=100),
        )


@router.patch("/incidents/{incident_id}")
async def update_incident(
    pool: PoolDep, incident_id: IncidentId, body: IncidentUpdate
) -> IncidentSummary:
    async with pool.acquire() as conn:
        await db.update_incident_description(conn, incident_id, body.description)
        incident = await db.get_incident(conn, incident_id)

    if incident is None:
        raise _not_found("incident")

    return incident


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(pool: PoolDep, incident_id: IncidentId) -> IncidentSummary:
    async with pool.acquire() as conn:
        incident = await db.resolve_incident(conn, incident_id)

    if incident is None:
        raise _not_found("open incident")

    await announce_incident_resolution.aio_run(
        AnnounceResolutionInput(incident_id=incident_id), wait_for_result=False
    )

    return incident


# --- action items ---


class ActionItemCreate(BaseModel):
    description: str = Field(min_length=1)
    assignee_id: TeamMemberId | None = None


class ActionItemUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    is_completed: bool | None = None
    assignee_id: TeamMemberId | None = None


@router.get("/action-items")
async def list_action_items(pool: PoolDep, open_only: bool = True) -> list[ActionItem]:
    async with pool.acquire() as conn:
        return await db.list_action_items(conn, open_only=open_only)


@router.post("/incidents/{incident_id}/action-items", status_code=status.HTTP_201_CREATED)
async def create_action_item(
    pool: PoolDep, incident_id: IncidentId, body: ActionItemCreate
) -> ActionItem:
    async with pool.acquire() as conn, conn.transaction():
        if await db.get_incident(conn, incident_id) is None:
            raise _not_found("incident")

        if body.assignee_id is not None:
            await _require_members(conn, [body.assignee_id])

        item_id = await db.create_action_item(conn, incident_id, body.description, body.assignee_id)
        item = await db.get_action_item(conn, item_id)

    if item is None:
        raise db.UnexpectedDBError(f"action item {item_id} vanished after insert")

    return item


@router.patch("/action-items/{action_item_id}")
async def update_action_item(
    pool: PoolDep, action_item_id: int, body: ActionItemUpdate
) -> ActionItem:
    async with pool.acquire() as conn, conn.transaction():
        item = await db.get_action_item(conn, action_item_id)

        if item is None:
            raise _not_found("action item")

        assignee_id = (
            body.assignee_id if "assignee_id" in body.model_fields_set else item.assignee_id
        )

        if assignee_id is not None:
            await _require_members(conn, [assignee_id])

        await db.update_action_item(
            conn,
            action_item_id,
            description=body.description if body.description is not None else item.description,
            is_completed=(
                body.is_completed if body.is_completed is not None else item.is_completed
            ),
            assignee_member_id=assignee_id,
        )
        updated = await db.get_action_item(conn, action_item_id)

    if updated is None:
        raise _not_found("action item")

    return updated


class MemberInput(BaseModel):
    name: str = Field(min_length=1)
    slack_user_id: SlackUserId | None = None
    slack_handle: str | None = None


class TriggeredRun(BaseModel):
    run_id: str


@router.get("/members")
async def list_members(pool: PoolDep) -> list[Member]:
    async with pool.acquire() as conn:
        return await db.list_members(conn)


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def create_member(pool: PoolDep, body: MemberInput) -> Member:
    try:
        async with pool.acquire() as conn:
            return await db.create_member(conn, body.name, body.slack_user_id, body.slack_handle)
    except UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slack user id already in use") from e


@router.put("/members/{member_id}")
async def update_member(pool: PoolDep, member_id: TeamMemberId, body: MemberInput) -> Member:
    try:
        async with pool.acquire() as conn:
            member = await db.update_member(
                conn, member_id, body.name, body.slack_user_id, body.slack_handle
            )
    except UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slack user id already in use") from e

    if member is None:
        raise _not_found("team member")

    return member


@router.post("/members/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_members() -> TriggeredRun:
    ref = await backfill_members.aio_run(wait_for_result=False)
    return TriggeredRun(run_id=ref.workflow_run_id)


class RotationInput(BaseModel):
    member_ids: list[TeamMemberId] = Field(min_length=1)
    period_days: int = Field(ge=1)
    anchor: datetime


class OverrideInput(BaseModel):
    team_member_id: TeamMemberId
    start: datetime
    end: datetime
    escalation_priority: int = Field(ge=1)

    @model_validator(mode="after")
    def _end_after_start(self) -> OverrideInput:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


@router.get("/oncall")
async def current_oncall(pool: PoolDep) -> list[OnCallEntry]:
    async with pool.acquire() as conn:
        return await db.current_oncall(conn)


@router.get("/rotation")
async def get_rotation(pool: PoolDep) -> Rotation | None:
    async with pool.acquire() as conn:
        return await db.get_rotation(conn)


@router.put("/rotation")
async def put_rotation(pool: PoolDep, body: RotationInput) -> Rotation:
    if len(set(body.member_ids)) != len(body.member_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "a member can only appear once in the rotation"
        )

    async with pool.acquire() as conn, conn.transaction():
        await _require_members(conn, body.member_ids)
        return await db.upsert_rotation(conn, body.member_ids, body.period_days, body.anchor)


def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    start = start or datetime.now(UTC)
    end = end or start + timedelta(days=28)

    if end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end must be after start")

    if end - start > timedelta(days=366):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "window is at most a year")

    return start, end


@router.get("/schedule")
async def get_schedule(
    pool: PoolDep, start: datetime | None = None, end: datetime | None = None
) -> list[Shift]:
    start, end = _window(start, end)

    async with pool.acquire() as conn:
        rotation = await db.get_rotation(conn)
        overrides = await db.list_overrides(conn, start, end)

    return build_schedule(rotation, overrides, start, end)


@router.get("/overrides")
async def list_overrides(
    pool: PoolDep, start: datetime | None = None, end: datetime | None = None
) -> list[Override]:
    start, end = _window(start, end)

    async with pool.acquire() as conn:
        return await db.list_overrides(conn, start, end)


@router.post("/overrides", status_code=status.HTTP_201_CREATED)
async def create_override(pool: PoolDep, body: OverrideInput) -> Override:
    try:
        async with pool.acquire() as conn, conn.transaction():
            await _require_members(conn, [body.team_member_id])
            return await db.create_override(
                conn, body.team_member_id, body.start, body.end, body.escalation_priority
            )
    except ExclusionViolationError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"overlaps an existing P{body.escalation_priority} override",
        ) from e


@router.delete("/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_override(pool: PoolDep, override_id: int) -> None:
    async with pool.acquire() as conn:
        deleted = await db.delete_override(conn, override_id)

    if not deleted:
        raise _not_found("override")


class PageInput(BaseModel):
    team_member_id: TeamMemberId
    incident_id: IncidentId | None = None
    reason: str | None = None


class PageResult(BaseModel):
    page_id: int
    run_id: str


@router.get("/pages")
async def list_pages(
    pool: PoolDep,
    incident_id: IncidentId | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[PageRecord]:
    async with pool.acquire() as conn:
        return await db.list_pages(conn, incident_id, limit)


@router.post("/pages", status_code=status.HTTP_202_ACCEPTED)
async def create_page(pool: PoolDep, body: PageInput) -> PageResult:
    try:
        async with pool.acquire() as conn:
            page = await db.create_page(conn, body.team_member_id, body.incident_id)
    except ForeignKeyViolationError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown team member or incident"
        ) from e

    ref = await deliver_page_notification.aio_run(
        DeliverPageInput(page_id=page.id, reason=body.reason), wait_for_result=False
    )

    return PageResult(page_id=page.id, run_id=ref.workflow_run_id)


class Health(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/healthz")
async def healthz() -> Health:
    return Health()


app = FastAPI(title="Incident Manager", lifespan=lifespan)
app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
