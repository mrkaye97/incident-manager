from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, Field
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_async_handlers import (
    AsyncConnectionErrorRetryHandler,
    AsyncRateLimitErrorRetryHandler,
)
from slack_sdk.models.blocks import (
    Block,
    CheckboxesElement,
    DatePickerElement,
    InputBlock,
    InputInteractiveElement,
    Option,
    PlainTextInputElement,
    StaticSelectElement,
    UserMultiSelectElement,
    UserSelectElement,
)
from slack_sdk.models.views import View
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.webhook.async_client import AsyncWebhookClient

from db import ActionItemOption, IncidentOption


class Subcommand(StrEnum):
    CREATE = "create"
    PAGE = "page"
    ONCALL = "oncall"
    SCHEDULE = "schedule"
    UPDATE = "update"
    ACTION = "action"
    RESOLVE = "resolve"
    COMPLETE = "complete"


class CallbackID(StrEnum):
    CREATE_INCIDENT = "create_incident"
    PAGE_MEMBER = "page_member"
    CONFIGURE_ROTATION = "configure_rotation"
    UPDATE_DESCRIPTION = "update_description"
    CREATE_ACTION_ITEM = "create_action_item"
    COMPLETE_ACTION_ITEMS = "complete_action_items"


class SlackProfile(BaseModel):
    real_name: str | None = None
    display_name: str | None = None


class SlackMember(BaseModel):
    id: str
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
    channel_id: str
    user_id: str
    incident_id: int | None = None


class SlackOption(BaseModel):
    value: str


class SlackStateElement(BaseModel):
    value: str | None = None
    selected_user: str | None = None
    selected_date: str | None = None
    selected_option: SlackOption | None = None
    selected_users: list[str] = Field(default_factory=list)
    selected_options: list[SlackOption] = Field(default_factory=list)


class SlackViewState(BaseModel):
    values: dict[str, dict[str, SlackStateElement]]


class SlackView(BaseModel):
    callback_id: str
    private_metadata: str = ""
    state: SlackViewState


class SlackActor(BaseModel):
    id: str
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

    def users(self, block: str, action: str = "value") -> list[str]:
        el = self.view.state.values.get(block, {}).get(action)
        return el.selected_users if el is not None else []

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
    user_id: str
    user_name: str
    api_app_id: str
    channel_id: str
    trigger_id: str
    team_domain: str
    channel_name: str
    response_url: str
    is_enterprise_install: bool


class SlackClient:
    def __init__(self, token: str) -> None:
        self._web = AsyncWebClient(
            token=token,
            retry_handlers=[
                AsyncConnectionErrorRetryHandler(max_retry_count=2),
                AsyncRateLimitErrorRetryHandler(max_retry_count=3),
            ],
        )

    async def team_id(self) -> str:
        return (await self._web.auth_test())["team_id"]

    async def users_list(self) -> list[SlackMember]:
        members: list[SlackMember] = []
        async for page in await self._web.users_list(limit=200):
            members.extend(SlackMember.model_validate(m) for m in page["members"])
        return members

    async def usergroup_member_ids(self, handle: str) -> set[str]:
        groups = (await self._web.usergroups_list())["usergroups"]
        match = next((g for g in groups if g["handle"] == handle), None)
        if match is None:
            available = ", ".join(sorted(g["handle"] for g in groups))
            raise RuntimeError(f"user group @{handle} not found (have: {available})")
        return set((await self._web.usergroups_users_list(usergroup=match["id"]))["users"])

    async def views_open(self, trigger_id: str, view: View) -> None:
        await self._web.views_open(trigger_id=trigger_id, view=view)

    async def create_channel(self, name: str) -> str:
        response = await self._web.conversations_create(name=name)

        return cast(str, response["channel"]["id"])

    async def invite_users(self, channel: str, user_ids: Iterable[str]) -> None:
        if not user_ids:
            return

        try:
            await self._web.conversations_invite(channel=channel, users=list(user_ids))
        except SlackApiError as e:
            if e.response.get("error") not in ("already_in_channel", "cant_invite_self"):
                raise

    async def post_message(self, channel: str, text: str) -> None:
        await self._web.chat_postMessage(channel=channel, text=text)

    async def respond(self, response_url: str, text: str) -> None:
        await AsyncWebhookClient(response_url).send(response_type="ephemeral", text=text)


def _text(*, multiline: bool = False, initial: str | None = None) -> PlainTextInputElement:
    return PlainTextInputElement(action_id="value", multiline=multiline, initial_value=initial)


def _user_select() -> UserSelectElement:
    return UserSelectElement(action_id="value")


def _incident_select(incidents: list[IncidentOption]) -> StaticSelectElement:
    return StaticSelectElement(
        action_id="value",
        placeholder="Select an incident",
        options=[Option(text=incident.name, value=str(incident.id)) for incident in incidents],
    )


def _user_multi_select() -> UserMultiSelectElement:
    return UserMultiSelectElement(action_id="value")


def _datepicker() -> DatePickerElement:
    return DatePickerElement(action_id="value")


def _action_item_checkboxes(items: list[ActionItemOption]) -> CheckboxesElement:
    return CheckboxesElement(
        action_id="value",
        options=[Option(text=item.description[:75], value=str(item.id)) for item in items],
    )


def _input(
    block_id: str, label: str, element: InputInteractiveElement, *, optional: bool = False
) -> InputBlock:
    return InputBlock(block_id=block_id, label=label, element=element, optional=optional)


def _modal(
    callback_id: CallbackID, title: str, blocks: list[Block], metadata: ViewMetadata
) -> View:
    return View(
        type="modal",
        callback_id=callback_id,
        private_metadata=metadata.model_dump_json(),
        title=title,
        submit="Submit",
        close="Cancel",
        blocks=blocks,
    )


def create_incident_modal(metadata: ViewMetadata) -> View:
    return _modal(
        CallbackID.CREATE_INCIDENT,
        "Create incident",
        [
            _input("name", "Name", _text()),
            _input(
                "lead", "Incident lead (defaults to current on-call)", _user_select(), optional=True
            ),
        ],
        metadata,
    )


def page_member_modal(metadata: ViewMetadata, incidents: list[IncidentOption]) -> View:
    blocks = [_input("target", "Who to page", _user_select())]
    if incidents:
        blocks.append(
            _input("incident_id", "Incident (optional)", _incident_select(incidents), optional=True)
        )
    blocks.append(_input("reason", "Reason", _text(multiline=True), optional=True))
    return _modal(CallbackID.PAGE_MEMBER, "Page someone", blocks, metadata)


def update_description_modal(metadata: ViewMetadata, current: str | None) -> View:
    return _modal(
        CallbackID.UPDATE_DESCRIPTION,
        "Update description",
        [_input("description", "Description", _text(multiline=True, initial=current))],
        metadata,
    )


def create_action_item_modal(metadata: ViewMetadata) -> View:
    return _modal(
        CallbackID.CREATE_ACTION_ITEM,
        "Add action item",
        [
            _input("description", "Action item", _text(multiline=True)),
            _input("assignee", "Assignee", _user_select(), optional=True),
        ],
        metadata,
    )


def complete_action_items_modal(metadata: ViewMetadata, items: list[ActionItemOption]) -> View:
    return _modal(
        CallbackID.COMPLETE_ACTION_ITEMS,
        "Complete action items",
        [_input("items", "Mark as complete", _action_item_checkboxes(items))],
        metadata,
    )


def configure_rotation_modal(metadata: ViewMetadata) -> View:
    return _modal(
        CallbackID.CONFIGURE_ROTATION,
        "Configure rotation",
        [
            _input("members", "Members (in rotation order)", _user_multi_select()),
            _input(
                "period_days",
                "Days per person",
                PlainTextInputElement(action_id="value", placeholder="e.g. 7"),
            ),
            _input("start", "First handoff date", _datepicker()),
        ],
        metadata,
    )
