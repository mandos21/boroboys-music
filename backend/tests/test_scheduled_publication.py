"""PostgreSQL-backed coverage for publication at the configured publish time."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    PlatformRole,
    Publication,
    PublicationState,
    Round,
    RoundStatus,
    Series,
    User,
)
from app.db.session import get_session_factory
from app.services.publications import start_due_publications


def _publisher(db, suffix: str, *, with_credential: bool = True) -> ExternalAccount:
    user = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"scheduled-publisher-{suffix}",
        platform_role=PlatformRole.ADMIN,
    )
    db.add(user)
    db.flush()
    account = ExternalAccount(
        user_id=user.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"scheduled-publisher-{suffix}",
        display_name="Publisher",
    )
    db.add(account)
    db.flush()
    if with_credential:
        db.add(
            ExternalCredential(
                external_account_id=account.id,
                ciphertext=encrypt(
                    json.dumps({"access_token": "test-token"}),
                    get_settings().credential_encryption_key.get_secret_value(),
                ),
                key_version="v1",
            )
        )
    return account


def _closed_round(
    db, series: Series, suffix: str, *, publish_at: datetime, publisher: uuid.UUID | None
) -> Round:
    round_ = Round(
        series_id=series.id,
        title=f"Scheduled round {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=publish_at - timedelta(days=3),
        closes_at=publish_at - timedelta(days=1),
        publish_at=publish_at,
        status=RoundStatus.CLOSED,
        policy_snapshot=[],
        publisher_account_id=publisher,
    )
    db.add(round_)
    db.flush()
    return round_


def _series(db, suffix: str) -> Series:
    series = Series(
        name=f"Scheduled {suffix}",
        slug=f"scheduled-{suffix}",
        timezone="UTC",
        default_policies=[],
        auto_start_next_round=False,
    )
    db.add(series)
    db.flush()
    return series


def test_due_round_with_a_configured_publisher_starts_publishing() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        series = _series(db, suffix)
        account = _publisher(db, suffix)
        round_ = _closed_round(
            db, series, suffix, publish_at=now - timedelta(minutes=5), publisher=account.id
        )
        db.commit()

        started = start_due_publications(db, now=now)

        db.refresh(round_)
        assert round_.status is RoundStatus.PUBLISHING
        publication = db.scalar(select(Publication).where(Publication.round_id == round_.id))
        assert publication is not None
        assert publication.id in started
        assert publication.state is PublicationState.PUBLISHING
        assert publication.publisher_account_id == account.id

        # The same round must not be picked up a second time.
        assert publication.id not in start_due_publications(db, now=now)


def test_round_without_a_publisher_or_before_its_time_is_left_alone() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        series = _series(db, suffix)
        account = _publisher(db, f"{suffix}-b")
        unconfigured = _closed_round(
            db, series, f"{suffix}-none", publish_at=now - timedelta(minutes=5), publisher=None
        )
        not_yet_due = _closed_round(
            db, series, f"{suffix}-later", publish_at=now + timedelta(days=3650), publisher=account.id
        )
        db.commit()

        start_due_publications(db, now=now)

        db.refresh(unconfigured)
        db.refresh(not_yet_due)
        assert unconfigured.status is RoundStatus.CLOSED
        assert not_yet_due.status is RoundStatus.CLOSED


def test_a_publisher_without_a_credential_does_not_publish_automatically() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        series = _series(db, suffix)
        account = _publisher(db, suffix, with_credential=False)
        round_ = _closed_round(
            db, series, suffix, publish_at=now - timedelta(minutes=5), publisher=account.id
        )
        db.commit()

        start_due_publications(db, now=now)

        db.refresh(round_)
        # Waiting for a manual publication is correct here; failing the round
        # would only produce a stuck state a person has to clear by hand.
        assert round_.status is RoundStatus.CLOSED


def test_a_disconnected_publisher_stops_publishing_automatically() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        series = _series(db, suffix)
        account = _publisher(db, suffix)
        account.is_active = False
        account.disconnected_at = now
        round_ = _closed_round(
            db, series, suffix, publish_at=now - timedelta(minutes=5), publisher=account.id
        )
        db.commit()

        start_due_publications(db, now=now)

        db.refresh(round_)
        assert round_.status is RoundStatus.CLOSED
