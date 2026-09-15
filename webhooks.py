from __future__ import annotations

import logging

from hatchet_sdk import V1WebhookHMACAlgorithm, V1WebhookHMACEncoding, V1WebhookSourceName
from hatchet_sdk.clients.rest.models.v1_webhook_api_key_auth import V1WebhookAPIKeyAuth
from hatchet_sdk.clients.rest.models.v1_webhook_hmac_auth import V1WebhookHMACAuth
from pydantic import BaseModel

from hatchet_client import hatchet
from settings import Settings

logger = logging.getLogger("incident-bot")

SLACK_SLASH_EVENT = "slack:slash"
SLACK_INTERACTIVITY_EVENT = "slack:interactivity"
HYPERDX_ALERT_EVENT = "hyperdx:alert"

HYPERDX_SECRET_HEADER = "x-api-key"


class WebhookSpec(BaseModel):
    name: str
    source_name: V1WebhookSourceName
    event_key: str
    auth: V1WebhookHMACAuth | V1WebhookAPIKeyAuth


def webhook_specs(settings: Settings) -> list[WebhookSpec]:
    slack_auth = V1WebhookHMACAuth(
        algorithm=V1WebhookHMACAlgorithm.SHA256,
        encoding=V1WebhookHMACEncoding.HEX,
        signatureHeaderName="X-Slack-Signature",
        signingSecret=settings.slack_signing_secret,
    )

    return [
        WebhookSpec(
            name="incident-bot-slack-commands",
            source_name=V1WebhookSourceName.SLACK,
            event_key=SLACK_SLASH_EVENT,
            auth=slack_auth,
        ),
        WebhookSpec(
            name="incident-bot-slack-interactivity",
            source_name=V1WebhookSourceName.SLACK,
            event_key=SLACK_INTERACTIVITY_EVENT,
            auth=slack_auth,
        ),
        WebhookSpec(
            name="incident-bot-hyperdx",
            source_name=V1WebhookSourceName.GENERIC,
            event_key=HYPERDX_ALERT_EVENT,
            auth=V1WebhookAPIKeyAuth(
                headerName=HYPERDX_SECRET_HEADER, apiKey=settings.hyperdx_webhook_secret
            ),
        ),
    ]


def webhook_url(name: str) -> str:
    config = hatchet.config
    return f"{config.server_url}/api/v1/stable/tenants/{config.tenant_id}/webhooks/{name}"


async def ensure_webhooks(settings: Settings) -> None:
    for spec in webhook_specs(settings):
        try:
            await hatchet.webhooks.aio_create(
                source_name=spec.source_name,
                name=spec.name,
                event_key_expression=f"'{spec.event_key}'",
                auth=spec.auth,
                return_event_as_response_payload=False,
            )
            logger.info("created webhook %s: %s", spec.name, webhook_url(spec.name))
        except Exception:
            logger.info("webhook %s already exists: %s", spec.name, webhook_url(spec.name))
