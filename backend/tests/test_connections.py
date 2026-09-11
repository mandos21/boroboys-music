"""Provider account linking: the callback must belong to whoever started it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import connections
from app.core.config import get_settings
from app.core.security import encrypt, hash_secret, new_secret
from app.db.models import ExternalAccount, ExternalLinkAttempt, ExternalProvider, User


def _start_lastfm_attempt(db: Session, user: User) -> str:
    state = new_secret()
    db.add(
        ExternalLinkAttempt(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            state_hash=hash_secret(state),
            code_verifier_ciphertext=encrypt(
                state, get_settings().credential_encryption_key.get_secret_value()
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db.commit()
    return state


@pytest.fixture
def lastfm_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        connections.lastfm,
        "exchange_session",
        lambda _settings, _token: {"username": "listener", "session_key": "key"},
    )


def test_provider_callback_links_the_account_that_started_the_attempt(
    db: Session, make_user: Callable[..., User], lastfm_exchange: None
) -> None:
    owner = make_user(name="Owner")
    state = _start_lastfm_attempt(db, owner)

    response = connections.complete_lastfm_link(db, owner, token="provider-token", state=state)

    assert response.status_code == 303
    assert "linkError" not in response.headers["location"]
    account = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == owner.id))
    assert account is not None and account.provider is ExternalProvider.LASTFM


def test_provider_callback_consumes_the_attempt_before_the_remote_exchange(
    db: Session, make_user: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed exchange must still burn the one-time state so it cannot be replayed."""
    owner = make_user(name="Owner")
    state = _start_lastfm_attempt(db, owner)

    def failing_exchange(_settings: object, _token: str) -> dict[str, str]:
        attempt = db.scalar(select(ExternalLinkAttempt))
        assert attempt is not None and attempt.consumed_at is not None
        raise connections.lastfm.LastfmError("provider down")

    monkeypatch.setattr(connections.lastfm, "exchange_session", failing_exchange)

    response = connections.complete_lastfm_link(db, owner, token="provider-token", state=state)

    assert "linkError=failed" in response.headers["location"]
    replay = connections.complete_lastfm_link(db, owner, token="provider-token", state=state)
    assert "linkError=expired" in replay.headers["location"]


def test_provider_callback_rejects_a_state_started_by_someone_else(
    db: Session, make_user: Callable[..., User], lastfm_exchange: None
) -> None:
    """A link started on one account must not capture another person's credentials."""
    attacker = make_user(name="Attacker")
    victim = make_user(name="Victim")
    state = _start_lastfm_attempt(db, attacker)

    response = connections.complete_lastfm_link(db, victim, token="provider-token", state=state)

    assert "linkError=expired" in response.headers["location"]
    assert db.scalar(select(ExternalAccount.id)) is None
    attempt = db.scalar(select(ExternalLinkAttempt))
    assert attempt is not None and attempt.consumed_at is None
