from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import NewType, TypeAlias
from uuid import UUID

from asyncpg import Connection, Record
from asyncpg.pool import PoolConnectionProxy
from pydantic import BaseModel, Field, field_validator

IncidentId = NewType("IncidentId", UUID)
TeamMemberId = NewType("TeamMemberId", UUID)
PageId = NewType("PageId", UUID)
ActionItemId = NewType("ActionItemId", UUID)
AlertId = NewType("AlertId", UUID)
RotationId = NewType("RotationId", UUID)
OverrideId = NewType("OverrideId", UUID)
SlackUserId = NewType("SlackUserId", str)
SlackChannelId = NewType("SlackChannelId", str)
PushoverUserKey = NewType("PushoverUserKey", str)
PushoverReceipt = NewType("PushoverReceipt", str)


Conn: TypeAlias = "Connection[Record] | PoolConnectionProxy[Record]"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class OnCallLevel(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class Member(BaseModel):
    id: TeamMemberId
    name: str
    slack_user_id: SlackUserId | None
    slack_handle: str | None
    pushover_user_key: PushoverUserKey | None


class Incident(BaseModel):
    id: IncidentId
    name: str
    slack_channel_id: SlackChannelId
    description: str | None


class IncidentOption(BaseModel):
    id: IncidentId
    name: str
    slack_channel_id: SlackChannelId


class IncidentSummary(BaseModel):
    id: IncidentId
    name: str
    status: IncidentStatus
    slack_channel_id: SlackChannelId
    description: str | None
    start_time: datetime
    end_time: datetime | None
    lead_id: TeamMemberId
    lead_name: str
    open_action_items: int
    total_action_items: int


class ActionItemOption(BaseModel):
    id: ActionItemId
    description: str


class ActionItem(BaseModel):
    id: ActionItemId
    incident_id: IncidentId
    incident_name: str
    description: str
    is_completed: bool
    assignee_id: TeamMemberId | None
    assignee_name: str | None
    created_at: datetime


class AlertRecord(BaseModel):
    id: AlertId
    title: str
    state: str | None
    body: str | None
    source_url: str | None
    created_at: datetime


class Page(BaseModel):
    id: PageId
    incident_id: IncidentId | None
    slack_channel_id: SlackChannelId | None


class PageDelivery(BaseModel):
    id: PageId
    member_name: str
    slack_user_id: SlackUserId | None
    pushover_user_key: PushoverUserKey | None
    pushover_receipt: PushoverReceipt | None
    incident_id: IncidentId | None
    incident_name: str | None
    slack_channel_id: SlackChannelId | None


class PageRecord(BaseModel):
    id: PageId
    incident_id: IncidentId | None
    team_member_id: TeamMemberId
    member_name: str
    paged_at: datetime
    pushed: bool
    acknowledged_at: datetime | None


class PendingAcknowledgement(BaseModel):
    id: PageId
    root_page_id: PageId
    pushover_receipt: PushoverReceipt


class EscalationState(BaseModel):
    root_page_id: PageId
    root_member_id: TeamMemberId
    incident_id: IncidentId | None
    incident_status: IncidentStatus | None
    acknowledged: bool
    step_done: bool


class Rotation(BaseModel):
    id: RotationId
    level: OnCallLevel
    member_ids: list[TeamMemberId]
    period_days: int
    anchor: datetime


class OnCallEntry(BaseModel):
    team_member_id: TeamMemberId
    name: str
    slack_user_id: SlackUserId | None
    level: OnCallLevel


class Override(BaseModel):
    id: OverrideId
    team_member_id: TeamMemberId
    member_name: str
    start: datetime
    end: datetime
    level: OnCallLevel


class Shift(BaseModel):
    team_member_id: TeamMemberId
    level: OnCallLevel
    start: datetime
    end: datetime
    override_id: OverrideId | None = None


class Subcommand(StrEnum):
    CREATE = "create"
    PAGE = "page"
    UPDATE = "update"
    ACTION = "action"
    RESOLVE = "resolve"
    COMPLETE = "complete"


class CallbackID(StrEnum):
    CREATE_INCIDENT = "create_incident"
    PAGE_MEMBER = "page_member"
    UPDATE_DESCRIPTION = "update_description"
    CREATE_ACTION_ITEM = "create_action_item"
    COMPLETE_ACTION_ITEMS = "complete_action_items"


class SlackProfile(BaseModel):
    real_name: str | None = None
    display_name: str | None = None


class SlackMember(BaseModel):
    id: SlackUserId
    name: str
    team_id: str | None = None
    deleted: bool = False
    is_bot: bool = False
    is_app_user: bool = False
    is_stranger: bool = False
    is_restricted: bool = False
    is_ultra_restricted: bool = False
    real_name: str | None = None
    profile: SlackProfile = Field(default_factory=SlackProfile)

    @property
    def display_name(self) -> str:
        return self.profile.real_name or self.real_name or self.profile.display_name or self.name


class ViewMetadata(BaseModel):
    channel_id: SlackChannelId
    user_id: SlackUserId
    incident_id: IncidentId | None = None


class SlackOption(BaseModel):
    value: str


class SlackStateElement(BaseModel):
    value: str | None = None
    selected_user: str | None = None
    selected_date: str | None = None
    selected_option: SlackOption | None = None
    selected_options: list[SlackOption] = Field(default_factory=list)


class SlackViewState(BaseModel):
    values: dict[str, dict[str, SlackStateElement]]


class SlackView(BaseModel):
    callback_id: str
    private_metadata: str = ""
    state: SlackViewState


class SlackActor(BaseModel):
    id: SlackUserId
    username: str | None = None
    name: str | None = None


class InteractivityPayload(BaseModel):
    type: str
    user: SlackActor
    view: SlackView

    def field(self, block: str, action: str = "value") -> str | None:
        el = self.view.state.values.get(block, {}).get(action)
        if el is None:
            return None
        if el.value is not None:
            return el.value
        if el.selected_user is not None:
            return el.selected_user
        if el.selected_date is not None:
            return el.selected_date
        if el.selected_option is not None:
            return el.selected_option.value
        return None

    def user_field(self, block: str) -> SlackUserId | None:
        value = self.field(block)
        return SlackUserId(value) if value else None

    def options(self, block: str, action: str = "value") -> list[str]:
        el = self.view.state.values.get(block, {}).get(action)
        return [o.value for o in el.selected_options] if el is not None else []

    @property
    def metadata(self) -> ViewMetadata:
        return ViewMetadata.model_validate_json(self.view.private_metadata)


class SlackSlashCommand(BaseModel):
    text: str | None
    token: str
    command: str
    team_id: str
    user_id: SlackUserId
    user_name: str
    api_app_id: str
    channel_id: SlackChannelId
    trigger_id: str
    team_domain: str
    channel_name: str
    response_url: str
    is_enterprise_install: bool


LINES_FOUND_RE = re.compile(r"\s*-\s*\d+\s+lines?\s+found\s*$", re.IGNORECASE)


EMPTY_CODE_BLOCK_RE = re.compile(r"```\s*```")


class AlertState(StrEnum):
    ALERT = "ALERT"
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DISABLED = "DISABLED"


class HyperDXAlert(BaseModel):
    title: str
    body: str | None = None
    state: AlertState | None = None
    event_id: str | None = None
    link: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        return LINES_FOUND_RE.sub("", value).strip()

    @field_validator("body")
    @classmethod
    def _clean_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = EMPTY_CODE_BLOCK_RE.sub("", value)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or None


class Actor(BaseModel):
    name: str
    slack_user_id: SlackUserId | None = None


class CreateIncidentInput(BaseModel):
    name: str = Field(min_length=1)
    lead_member_id: TeamMemberId | None = None
    description: str | None = None
    actor: Actor


class PageMemberInput(BaseModel):
    team_member_id: TeamMemberId
    incident_id: IncidentId | None = None
    reason: str | None = None
    actor: Actor
    root_page_id: PageId | None = None
    escalation_step: int | None = None


class EscalatePageInput(BaseModel):
    root_page_id: PageId


class EscalationStepInput(BaseModel):
    root_page_id: PageId
    step: int


class EscalationStepResult(BaseModel):
    done: bool


class ResolveIncidentInput(BaseModel):
    incident_id: IncidentId
    actor: Actor


class UpdateIncidentDescriptionInput(BaseModel):
    incident_id: IncidentId
    description: str
    actor: Actor


class CreateActionItemInput(BaseModel):
    incident_id: IncidentId
    description: str = Field(min_length=1)
    assignee_id: TeamMemberId | None = None
    actor: Actor


class UpdateActionItemInput(BaseModel):
    action_item_id: ActionItemId
    description: str = Field(min_length=1)
    is_completed: bool
    assignee_id: TeamMemberId | None
    actor: Actor
