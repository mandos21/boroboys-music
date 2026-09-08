"""PostgreSQL-backed coverage for publication at the configured publish time."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ExternalAccount,
    Publication,
    PublicationState,
    Round,
    RoundStatus,
    Series,
    User,
)
from app.services.publications import start_due_publications

NOW = datetime.now(UTC)


def _round_ids(db: Session, publication_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    return set(db.scalars(select(Publication.round_id).where(Publication.id.in_(publication_ids))))


def _closed(
    make_round: Callable[..., Round],
    series: Series,
    *,
    due: bool,
    publisher: ExternalAccount | None,
) -> Round:
    publish_at = NOW - timedelta(minutes=5) if due else NOW + timedelta(days=3650)
    return make_round(
        series,
        title="Scheduled",
        status=RoundStatus.CLOSED,
        opens_at=publish_at - timedelta(days=3),
        closes_at=publish_at - timedelta(days=1),
        publish_at=publish_at,
        publisher_account_id=publisher.id if publisher else None,
    )


def test_due_round_with_a_configured_publisher_starts_publishing(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_spotify_account: Callable[..., ExternalAccount],
) -> None:
    account = make_spotify_account(make_user(admin=True))
    round_ = _closed(make_round, make_series(), due=True, publisher=account)
    db.commit()

    started = start_due_publications(db, now=NOW)

    # Scoped to this round rather than asserting on the global result. The
    # fixture stops new accumulation, but the development database still holds
    # rows from before it existed, some of which have since come due.
    db.refresh(round_)
    assert round_.status is RoundStatus.PUBLISHING
    publication = db.scalar(select(Publication).where(Publication.round_id == round_.id))
    assert publication is not None
    assert publication.id in started
    assert publication.state is PublicationState.PUBLISHING
    assert publication.publisher_account_id == account.id

    # The same round must not be picked up a second time.
    assert publication.id not in start_due_publications(db, now=NOW)


def test_round_without_a_publisher_or_before_its_time_is_left_alone(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_spotify_account: Callable[..., ExternalAccount],
) -> None:
    series = make_series()
    account = make_spotify_account(make_user(admin=True))
    unconfigured = _closed(make_round, series, due=True, publisher=None)
    not_yet_due = _closed(make_round, series, due=False, publisher=account)
    db.commit()

    started = start_due_publications(db, now=NOW)

    db.refresh(unconfigured)
    db.refresh(not_yet_due)
    assert unconfigured.status is RoundStatus.CLOSED
    assert not_yet_due.status is RoundStatus.CLOSED
    assert not {unconfigured.id, not_yet_due.id} & _round_ids(db, started)


def test_a_publisher_without_a_credential_does_not_publish_automatically(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_spotify_account: Callable[..., ExternalAccount],
) -> None:
    account = make_spotify_account(make_user(admin=True), with_credential=False)
    round_ = _closed(make_round, make_series(), due=True, publisher=account)
    db.commit()

    started = start_due_publications(db, now=NOW)

    db.refresh(round_)
    # Waiting for a manual publication is correct here; failing the round would
    # only produce a stuck state a person has to clear by hand.
    assert round_.status is RoundStatus.CLOSED
    assert round_.id not in _round_ids(db, started)


def test_a_disconnected_publisher_stops_publishing_automatically(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_spotify_account: Callable[..., ExternalAccount],
) -> None:
    account = make_spotify_account(make_user(admin=True), active=False)
    round_ = _closed(make_round, make_series(), due=True, publisher=account)
    db.commit()

    started = start_due_publications(db, now=NOW)

    db.refresh(round_)
    assert round_.status is RoundStatus.CLOSED
    assert round_.id not in _round_ids(db, started)
