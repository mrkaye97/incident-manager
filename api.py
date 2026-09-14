from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, TypeVar

from asyncpg import Pool, create_pool
from asyncpg.exceptions import ExclusionViolationError, UniqueViolationError
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from hatchet_sdk import FailedTaskRunExceptionGroup
from hatchet_sdk.runnables.workflow import Standalone
from pydantic import BaseModel, Field, model_validator

import auth
import db
import worker
from actions import ActionError, NotFoundError
from internal.types import (
    ActionItem,
    Actor,
    AlertRecord,
    Conn,
    CreateActionItemInput,
    CreateIncidentInput,
    IncidentId,
    IncidentStatus,
    IncidentSummary,
    Member,
    OnCallEntry,
    Override,
    Page,
    PageMemberInput,
    PageRecord,
    PushoverUserKey,
    ResolveIncidentInput,
    Rotation,
    Shift,
    SlackUserId,
    TeamMemberId,
    UpdateActionItemInput,
    UpdateIncidentDescriptionInput,
)
from schedule import build_schedule
from settings import Settings

settings = Settings()  # ty: ignore[missing-argument]

TASK_TIMEOUT_SECONDS = 15

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


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


async def current_member(request: Request, pool: PoolDep) -> Member:
    token = request.cookies.get(auth.SESSION_COOKIE)
    member = None

    if token:
        async with pool.acquire() as conn:
            member = await db.get_session_member(conn, auth.hash_token(token))

    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")

    return member


CurrentMemberDep = Annotated[Member, Depends(current_member)]

router = APIRouter(prefix="/api", dependencies=[Depends(current_member)])
public_router = APIRouter(prefix="/api")


def _actor(member: Member) -> Actor:
    return Actor(name=member.name, slack_user_id=member.slack_user_id)


def _set_cookie(response: Response, key: str, value: str, max_age: timedelta) -> None:
    response.set_cookie(
        key,
        value,
        max_age=int(max_age.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
    )


def _redirect_uri() -> str:
    return f"{settings.api_url or settings.app_url}/api/auth/callback"


def _login_redirect(error: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.app_url}/login?error={error}", status.HTTP_302_FOUND)


@public_router.get("/auth/login")
async def login(next: str | None = None) -> RedirectResponse:
    state = auth.new_token()
    response = RedirectResponse(
        auth.authorize_url(settings.slack_client_id, _redirect_uri(), state),
        status.HTTP_302_FOUND,
    )
    _set_cookie(response, auth.STATE_COOKIE, state, auth.STATE_LIFETIME)
    _set_cookie(response, auth.NEXT_COOKIE, auth.safe_next_path(next), auth.STATE_LIFETIME)
    return response


@public_router.get("/auth/callback")
async def auth_callback(
    request: Request,
    pool: PoolDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    expected_state = request.cookies.get(auth.STATE_COOKIE)

    if error or not code or not state or not expected_state:
        return _login_redirect(error or "invalid_state")

    if not secrets.compare_digest(state, expected_state):
        return _login_redirect("invalid_state")

    try:
        slack_user_id = await auth.slack_user_id_for_code(
            settings.slack_client_id, settings.slack_client_secret, code, _redirect_uri()
        )
    except auth.SlackAuthError:
        return _login_redirect("slack_error")

    async with pool.acquire() as conn:
        member = await db.get_member_by_slack_id(conn, slack_user_id)

        if member is None:
            return _login_redirect("not_on_roster")

        token = auth.new_token()
        await db.create_session(conn, auth.hash_token(token), member.id, auth.session_expiry())

    next_path = auth.safe_next_path(request.cookies.get(auth.NEXT_COOKIE))
    response = RedirectResponse(f"{settings.app_url}{next_path}", status.HTTP_302_FOUND)
    _set_cookie(response, auth.SESSION_COOKIE, token, auth.SESSION_LIFETIME)
    response.delete_cookie(auth.STATE_COOKIE)
    response.delete_cookie(auth.NEXT_COOKIE)
    return response


@public_router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, pool: PoolDep) -> Response:
    if token := request.cookies.get(auth.SESSION_COOKIE):
        async with pool.acquire() as conn:
            await db.delete_session(conn, auth.hash_token(token))

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(auth.SESSION_COOKIE, secure=True, httponly=True, samesite="lax")
    return response


@router.get("/auth/me")
async def me(member: CurrentMemberDep) -> Member:
    return member


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def _run(task: Standalone[TInput, TOutput], input: TInput) -> TOutput:
    try:
        async with asyncio.timeout(TASK_TIMEOUT_SECONDS):
            return await task.aio_run(input)
    except TimeoutError as e:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            f"{task.name} didn't finish within {TASK_TIMEOUT_SECONDS}s — is the worker running?",
        ) from e
    except FailedTaskRunExceptionGroup as e:
        error = e.exceptions[0] if e.exceptions else None

        if error is not None and error.exc_type == NotFoundError.__name__:
            raise HTTPException(status.HTTP_404_NOT_FOUND, error.exc) from e

        if error is not None and error.exc_type == ActionError.__name__:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error.exc) from e

        detail = f"{task.name} failed: {error.exc_type}: {error.exc}" if error else str(e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from e


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


class IncidentCreate(BaseModel):
    name: str = Field(min_length=1)
    lead_id: TeamMemberId | None = None
    description: str | None = None


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


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_incident(member: CurrentMemberDep, body: IncidentCreate) -> IncidentSummary:
    return await _run(
        worker.create_incident,
        CreateIncidentInput(
            name=body.name,
            lead_member_id=body.lead_id,
            description=body.description,
            actor=_actor(member),
        ),
    )


@router.patch("/incidents/{incident_id}")
async def update_incident(
    member: CurrentMemberDep, incident_id: IncidentId, body: IncidentUpdate
) -> IncidentSummary:
    return await _run(
        worker.update_incident_description,
        UpdateIncidentDescriptionInput(
            incident_id=incident_id, description=body.description, actor=_actor(member)
        ),
    )


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(member: CurrentMemberDep, incident_id: IncidentId) -> IncidentSummary:
    return await _run(
        worker.resolve_incident,
        ResolveIncidentInput(incident_id=incident_id, actor=_actor(member)),
    )


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
    member: CurrentMemberDep, incident_id: IncidentId, body: ActionItemCreate
) -> ActionItem:
    return await _run(
        worker.create_action_item,
        CreateActionItemInput(
            incident_id=incident_id,
            description=body.description,
            assignee_id=body.assignee_id,
            actor=_actor(member),
        ),
    )


@router.patch("/action-items/{action_item_id}")
async def update_action_item(
    member: CurrentMemberDep, pool: PoolDep, action_item_id: int, body: ActionItemUpdate
) -> ActionItem:
    async with pool.acquire() as conn:
        item = await db.get_action_item(conn, action_item_id)

    if item is None:
        raise _not_found("action item")

    return await _run(
        worker.update_action_item,
        UpdateActionItemInput(
            action_item_id=action_item_id,
            description=body.description if body.description is not None else item.description,
            is_completed=body.is_completed if body.is_completed is not None else item.is_completed,
            assignee_id=(
                body.assignee_id if "assignee_id" in body.model_fields_set else item.assignee_id
            ),
            actor=_actor(member),
        ),
    )


class MemberInput(BaseModel):
    name: str = Field(min_length=1)
    slack_user_id: SlackUserId | None = None
    slack_handle: str | None = None
    pushover_user_key: PushoverUserKey | None = None


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
            return await db.create_member(
                conn, body.name, body.slack_user_id, body.slack_handle, body.pushover_user_key
            )
    except UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slack user id already in use") from e


@router.put("/members/{member_id}")
async def update_member(pool: PoolDep, member_id: TeamMemberId, body: MemberInput) -> Member:
    try:
        async with pool.acquire() as conn:
            member = await db.update_member(
                conn,
                member_id,
                body.name,
                body.slack_user_id,
                body.slack_handle,
                body.pushover_user_key,
            )
    except UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slack user id already in use") from e

    if member is None:
        raise _not_found("team member")

    return member


@router.post("/members/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_members() -> TriggeredRun:
    ref = await worker.backfill_members.aio_run(wait_for_result=False)
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


@router.get("/pages")
async def list_pages(
    pool: PoolDep,
    incident_id: IncidentId | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[PageRecord]:
    async with pool.acquire() as conn:
        return await db.list_pages(conn, incident_id, limit)


@router.post("/pages", status_code=status.HTTP_201_CREATED)
async def create_page(member: CurrentMemberDep, body: PageInput) -> Page:
    return await _run(
        worker.page_member,
        PageMemberInput(
            team_member_id=body.team_member_id,
            incident_id=body.incident_id,
            reason=body.reason,
            actor=_actor(member),
        ),
    )


class Health(BaseModel):
    status: Literal["ok"] = "ok"


@public_router.get("/healthz")
async def healthz() -> Health:
    return Health()


app = FastAPI(title="Incident Manager", lifespan=lifespan)
app.include_router(public_router)
app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
