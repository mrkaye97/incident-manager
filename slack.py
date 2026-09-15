from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import cast

from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_async_handlers import (
    AsyncConnectionErrorRetryHandler,
    AsyncRateLimitErrorRetryHandler,
)
from slack_sdk.models.blocks import (
    Block,
    CheckboxesElement,
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

from internal.types import (
    ActionItemOption,
    CallbackID,
    IncidentOption,
    SlackChannelId,
    SlackMember,
    SlackUserId,
    ViewMetadata,
)

logger = logging.getLogger("incident-bot")


def mention(user_id: SlackUserId) -> str:
    return f"<@{user_id}>"


def channel_url(channel_id: SlackChannelId) -> str:
    return f"https://slack.com/app_redirect?channel={channel_id}"


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

    async def user_info(self, user_id: SlackUserId) -> SlackMember:
        return SlackMember.model_validate((await self._web.users_info(user=user_id))["user"])

    async def users_list(self) -> list[SlackMember]:
        members: list[SlackMember] = []
        async for page in await self._web.users_list(limit=200):
            members.extend(SlackMember.model_validate(m) for m in page["members"])
        return members

    async def usergroup_member_ids(self, handle: str) -> set[SlackUserId]:
        groups = (await self._web.usergroups_list())["usergroups"]
        match = next((g for g in groups if g["handle"] == handle), None)
        if match is None:
            available = ", ".join(sorted(g["handle"] for g in groups))
            raise RuntimeError(f"user group @{handle} not found (have: {available})")
        return set((await self._web.usergroups_users_list(usergroup=match["id"]))["users"])

    async def views_open(self, trigger_id: str, view: View) -> None:
        await self._web.views_open(trigger_id=trigger_id, view=view)

    async def create_channel(self, name: str) -> SlackChannelId:
        response = await self._web.conversations_create(name=name)

        return SlackChannelId(cast(str, response["channel"]["id"]))

    async def invite_users(self, channel: SlackChannelId, user_ids: Iterable[SlackUserId]) -> None:
        if not user_ids:
            return

        try:
            await self._web.conversations_invite(channel=channel, users=list(user_ids))
        except SlackApiError as e:
            if e.response.get("error") not in (
                "already_in_channel",
                "cant_invite_self",
                "is_archived",
            ):
                raise

    async def post_message(self, channel: SlackChannelId | SlackUserId, text: str) -> None:
        try:
            await self._web.chat_postMessage(channel=channel, text=text)
        except SlackApiError as e:
            if e.response.get("error") != "is_archived":
                raise
            logger.info("skipped message to archived channel %s", channel)

    async def archive_channel(self, channel: SlackChannelId) -> None:
        try:
            await self._web.conversations_archive(channel=channel)
        except SlackApiError as e:
            if e.response.get("error") != "already_archived":
                raise

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
