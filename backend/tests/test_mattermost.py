from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.services import mattermost


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


def test_post_message_sends_text_to_the_configured_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(mattermost.httpx, "post", fake_post)
    settings = Settings(mattermost_webhook_url="https://mattermost.example.com/hooks/token")

    mattermost.post_message(settings, "hello channel")

    assert calls[0]["url"] == "https://mattermost.example.com/hooks/token"
    assert calls[0]["json"] == {"text": "hello channel"}


def test_post_message_requires_a_webhook_url() -> None:
    with pytest.raises(mattermost.MattermostError):
        mattermost.post_message(Settings(mattermost_webhook_url=None), "hello")


def test_post_message_wraps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_post(*_args: object, **_kwargs: object) -> FakeResponse:
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(mattermost.httpx, "post", failing_post)
    settings = Settings(mattermost_webhook_url="https://mattermost.example.com/hooks/token")

    with pytest.raises(mattermost.MattermostError):
        mattermost.post_message(settings, "hello")
