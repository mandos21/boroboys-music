"""Mattermost incoming-webhook posts for round-lifecycle events."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings

LOGGER = logging.getLogger(__name__)


class MattermostError(Exception):
    pass


def post_message(settings: Settings, text: str) -> None:
    if settings.mattermost_webhook_url is None:
        raise MattermostError("Mattermost is not configured")
    try:
        response = httpx.post(
            settings.mattermost_webhook_url.get_secret_value(),
            json={"text": text},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise MattermostError("could not post to Mattermost") from error
