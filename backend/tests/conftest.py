"""Shared test fixtures: isolated sessions and domain factories.

Tests run against a real PostgreSQL database because the code under test uses
row locks, advisory locks, and `ON CONFLICT`, none of which a substitute models
faithfully. The `db` fixture keeps that honest by making each test's writes
disappear afterwards, so a test can assert on global state instead of working
around whatever earlier runs left behind.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.db.session import get_session_factory


@pytest.fixture(scope="session")
def engine() -> Engine:
    return get_session_factory().kw["bind"]


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session whose writes never outlive the test.

    The session is bound to a connection with an already-open transaction, and
    `join_transaction_mode="create_savepoint"` turns the code-under-test's own
    `commit()` calls into savepoint releases. Rolling the outer transaction back
    on teardown therefore discards everything, without the code under test
    having to know it is being tested.

    A test that needs its writes visible to a *different* connection - the
    concurrency tests, which use threads - cannot use this fixture and manages
    its own session instead.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def suffix() -> str:
    """A short unique tag for values that carry a uniqueness constraint."""
    return uuid.uuid4().hex[:12]


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(
        *,
        name: str | None = None,
        email: str | None = None,
        admin: bool = False,
        active: bool = True,
    ) -> User:
        tag = uuid.uuid4().hex[:12]
        user = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"{name or 'user'}-{tag}",
            email=email,
            display_name=name,
            platform_role=PlatformRole.ADMIN if admin else PlatformRole.MEMBER,
            is_active=active,
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def make_series(db: Session) -> Callable[..., Series]:
    def _make(*, name: str = "Series", auto_start: bool = False, **kwargs: object) -> Series:
        tag = uuid.uuid4().hex[:12]
        series = Series(
            name=f"{name} {tag}",
            slug=f"{name.lower().replace(' ', '-')}-{tag}",
            timezone="UTC",
            default_policies=[],
            auto_start_next_round=auto_start,
            **kwargs,
        )
        db.add(series)
        db.flush()
        return series

    return _make


@pytest.fixture
def make_round(db: Session) -> Callable[..., Round]:
    def _make(
        series: Series,
        *,
        title: str = "Round",
        status: RoundStatus = RoundStatus.OPEN,
        opens_at: datetime | None = None,
        closes_at: datetime | None = None,
        publish_at: datetime | None = None,
        submission_limit: int = 1,
        members: list[User] | None = None,
        **kwargs: object,
    ) -> Round:
        now = datetime.now(UTC)
        opens = opens_at or now - timedelta(days=1)
        closes = closes_at or now + timedelta(days=1)
        round_ = Round(
            series_id=series.id,
            title=f"{title} {uuid.uuid4().hex[:8]}",
            timezone="UTC",
            submission_limit=submission_limit,
            opens_at=opens,
            closes_at=closes,
            publish_at=publish_at or closes + timedelta(hours=1),
            status=status,
            policy_snapshot=[],
            **kwargs,
        )
        db.add(round_)
        db.flush()
        for member in members or []:
            db.add(RoundMember(round_id=round_.id, user_id=member.id))
        db.flush()
        return round_

    return _make


@pytest.fixture
def make_track(db: Session) -> Callable[..., Track]:
    def _make(*, name: str = "Track", artist: str = "The Testers", **kwargs: object) -> Track:
        tag = uuid.uuid4().hex[:12]
        track = Track(
            spotify_track_id=f"track-{tag}",
            name=name,
            artist=artist,
            spotify_uri=f"spotify:track:track-{tag}",
            **kwargs,
        )
        db.add(track)
        db.flush()
        return track

    return _make


@pytest.fixture
def make_spotify_account(db: Session) -> Callable[..., ExternalAccount]:
    def _make(user: User, *, with_credential: bool = True, active: bool = True) -> ExternalAccount:
        tag = uuid.uuid4().hex[:12]
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"spotify-{tag}",
            display_name="Publisher",
            is_active=active,
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
            db.flush()
        return account

    return _make


@pytest.fixture
def make_lastfm_account(db: Session) -> Callable[..., ExternalAccount]:
    def _make(user: User, **kwargs: object) -> ExternalAccount:
        tag = uuid.uuid4().hex[:12]
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"listener-{tag}",
            **kwargs,
        )
        db.add(account)
        db.flush()
        return account

    return _make


@pytest.fixture
def make_submission(db: Session) -> Callable[..., Submission]:
    def _make(round_: Round, contributor: User, track: Track, **kwargs: object) -> Submission:
        submission = Submission(
            round_id=round_.id,
            contributor_id=contributor.id,
            track_id=track.id,
            status=SubmissionStatus.ACCEPTED,
            **kwargs,
        )
        db.add(submission)
        db.flush()
        return submission

    return _make
