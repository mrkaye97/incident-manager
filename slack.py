from __future__ import annotations

from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, Field

SLACK_API_BASE = "https://slack.com/api"


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
    def __init__(self, token: str, http: httpx.AsyncClient) -> None:
        self._token = token
        self._http = http

    async def _post(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(
            f"{SLACK_API_BASE}/{method}",
            json=body,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"slack {method} failed: {data.get('error')} ({data})")
        return data

    async def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.get(
            f"{SLACK_API_BASE}/{method}",
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"slack {method} failed: {data.get('error')} ({data})")
        return data

    async def auth_test(self) -> dict[str, Any]:
        return await self._post("auth.test", {})

    async def users_list(self) -> list[SlackMember]:
        members: list[SlackMember] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await self._get("users.list", params)
            members.extend(SlackMember.model_validate(m) for m in data.get("members", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                return members

    async def usergroup_member_ids(self, handle: str) -> set[str]:
        groups = (await self._get("usergroups.list", {})).get("usergroups", [])
        match = next((g for g in groups if g.get("handle") == handle), None)
        if match is None:
            available = ", ".join(sorted(g.get("handle", "?") for g in groups))
            raise RuntimeError(f"user group @{handle} not found (have: {available})")
        data = await self._get("usergroups.users.list", {"usergroup": match["id"]})
        return set(data.get("users", []))

    async def views_open(self, trigger_id: str, view: dict[str, Any]) -> dict[str, Any]:
        return await self._post("views.open", {"trigger_id": trigger_id, "view": view})

    async def post_message(
        self, channel: str, text: str, blocks: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            body["blocks"] = blocks
        return await self._post("chat.postMessage", body)

    async def users_info(self, user_id: str) -> dict[str, Any]:
        data = await self._get("users.info", {"user": user_id})
        return data["user"]

    async def respond(
        self, response_url: str, text: str, blocks: list[dict[str, Any]] | None = None
    ) -> None:
        body: dict[str, Any] = {"response_type": "ephemeral", "text": text}
        if blocks is not None:
            body["blocks"] = blocks
        await self._http.post(response_url, json=body)


def _text(*, multiline: bool = False) -> dict[str, Any]:
    return {"type": "plain_text_input", "action_id": "value", "multiline": multiline}


def _user_select() -> dict[str, Any]:
    return {"type": "users_select", "action_id": "value"}


def _datepicker() -> dict[str, Any]:
    return {"type": "datepicker", "action_id": "value"}


def _priority_select() -> dict[str, Any]:
    options = [
        {"text": {"type": "plain_text", "text": f"P{p}"}, "value": str(p)} for p in range(1, 6)
    ]
    return {
        "type": "static_select",
        "action_id": "value",
        "options": options,
        "initial_option": options[0],
    }


def _input(
    block_id: str, label: str, element: dict[str, Any], *, optional: bool = False
) -> dict[str, Any]:
    return {
        "type": "input",
        "block_id": block_id,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": element,
    }


def _modal(
    callback_id: str, title: str, blocks: list[dict[str, Any]], metadata: ViewMetadata
) -> dict[str, Any]:
    return {
        "type": "modal",
        "callback_id": callback_id,
        "private_metadata": metadata.model_dump_json(),
        "title": {"type": "plain_text", "text": title},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def create_incident_modal(metadata: ViewMetadata) -> dict[str, Any]:
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


def page_member_modal(metadata: ViewMetadata) -> dict[str, Any]:
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


def add_shift_modal(metadata: ViewMetadata) -> dict[str, Any]:
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
