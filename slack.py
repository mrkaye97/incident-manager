from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from slack_sdk.http_retry.builtin_async_handlers import (
    AsyncConnectionErrorRetryHandler,
    AsyncRateLimitErrorRetryHandler,
)
from slack_sdk.models.blocks import (
    Block,
    DatePickerElement,
    InputBlock,
    InputInteractiveElement,
    Option,
    PlainTextInputElement,
    StaticSelectElement,
    UserSelectElement,
)
from slack_sdk.models.views import View
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.webhook.async_client import AsyncWebhookClient


class Subcommand(StrEnum):
    CREATE = "create"
    PAGE = "page"
    ONCALL = "oncall"
    SCHEDULE = "schedule"


class CallbackID(StrEnum):
    CREATE_INCIDENT = "create_incident"
    PAGE_MEMBER = "page_member"
    ADD_SHIFT = "add_shift"


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


class SlackViewState(BaseModel):
    values: dict[str, dict[str, dict[str, Any]]]


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

    def field(self, block: str, action: str = "value") -> Any:
        el = self.view.state.values.get(block, {}).get(action, {})
        for key in ("value", "selected_user", "selected_date"):
            if key in el:
                return el[key]
        if option := el.get("selected_option"):
            return option["value"]
        return None

    @property
    def metadata(self) -> ViewMetadata:
        return ViewMetadata.model_validate_json(self.view.private_metadata)


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

    async def post_message(self, channel: str, text: str) -> None:
        await self._web.chat_postMessage(channel=channel, text=text)

    async def respond(self, response_url: str, text: str) -> None:
        await AsyncWebhookClient(response_url).send(response_type="ephemeral", text=text)


def _text(*, multiline: bool = False) -> PlainTextInputElement:
    return PlainTextInputElement(action_id="value", multiline=multiline)


def _user_select() -> UserSelectElement:
    return UserSelectElement(action_id="value")


def _datepicker() -> DatePickerElement:
    return DatePickerElement(action_id="value")


def _priority_select() -> StaticSelectElement:
    options = [Option(label=f"P{p}", value=str(p)) for p in range(1, 6)]
    return StaticSelectElement(action_id="value", options=options, initial_option=options[0])


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
            _input("lead", "Incident lead", _user_select()),
            _input("description", "Description", _text(multiline=True), optional=True),
        ],
        metadata,
    )


def page_member_modal(metadata: ViewMetadata) -> View:
    return _modal(
        CallbackID.PAGE_MEMBER,
        "Page someone",
        [
            _input("target", "Who to page", _user_select()),
            _input("incident_id", "Incident ID (optional)", _text(), optional=True),
            _input("reason", "Reason", _text(multiline=True), optional=True),
        ],
        metadata,
    )


def add_shift_modal(metadata: ViewMetadata) -> View:
    return _modal(
        CallbackID.ADD_SHIFT,
        "Add on-call shift",
        [
            _input("member", "Team member", _user_select()),
            _input("start", "Start date", _datepicker()),
            _input("end", "End date", _datepicker()),
            _input("escalation_priority", "Escalation priority", _priority_select()),
        ],
        metadata,
    )
