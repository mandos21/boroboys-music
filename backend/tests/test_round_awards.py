"""Qualification uses each person's share of tracks, including unknown metadata."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import tasks
from app.db.models import (
    ExternalAccount,
    Publication,
    PublicationState,
    Round,
    RoundStatus,
    Series,
    Submission,
    Track,
    User,
)
from app.services.round_awards import AwardTrack, award_candidates, round_awards


def _track(
    person: uuid.UUID,
    *,
    listeners: int | None = None,
    groups: tuple[str, ...] = (),
    complete: bool = True,
) -> AwardTrack:
    return AwardTrack(
        contributor_id=person,
        track_id=uuid.uuid4(),
        listeners=listeners,
        groups=frozenset(groups),
        genre_complete=complete,
        has_genres=bool(groups),
    )


def test_genre_awards_require_eighty_percent_but_allow_one_unknown_of_five() -> None:
    eclectic = uuid.uuid4()
    specialized = uuid.uuid4()
    tracks = [
        *[_track(eclectic, groups=(genre,)) for genre in ("rock", "pop", "jazz", "metal")],
        _track(eclectic, complete=False),
        *[_track(specialized, groups=("rock",)) for _ in range(4)],
        _track(specialized, complete=False),
    ]
    awards = award_candidates(tracks)
    assert {(award.title, award.contributor_id) for award in awards} >= {
        ("Eclectic", eclectic),
        ("Specialized", specialized),
    }


def test_one_unknown_of_three_prevents_genre_award() -> None:
    person = uuid.uuid4()
    tracks = [
        _track(person, groups=("rock",)),
        _track(person, groups=("pop",)),
        _track(person, complete=False),
    ]
    assert not {"Eclectic", "Specialized"} & {award.title for award in award_candidates(tracks)}


def test_listener_awards_need_both_relative_third_and_absolute_floor() -> None:
    underground = uuid.uuid4()
    mainstream = uuid.uuid4()
    middle = uuid.uuid4()
    tracks = [
        *[_track(underground, listeners=n) for n in (100, 500, 1_000)],
        *[_track(middle, listeners=n) for n in (50_000, 75_000, 100_000)],
        *[_track(mainstream, listeners=n) for n in (300_000, 500_000, 1_000_000)],
    ]
    awards = award_candidates(tracks)
    assert ("Underground", underground) in {(award.title, award.contributor_id) for award in awards}
    assert ("Mainstream", mainstream) in {(award.title, award.contributor_id) for award in awards}
    assert not any(
        award.contributor_id == middle and award.title in {"Underground", "Mainstream"}
        for award in awards
    )


def test_missing_listener_values_do_not_count_as_zero() -> None:
    person = uuid.uuid4()
    other = uuid.uuid4()
    tracks = [
        _track(person, listeners=10),
        _track(person, listeners=20),
        _track(person),
        *[_track(other, listeners=n) for n in (500_000, 600_000, 700_000)],
    ]
    assert not any(
        award.title == "Underground" and award.contributor_id == person
        for award in award_candidates(tracks)
    )


def test_uncharted_requires_successful_no_tag_enrichment() -> None:
    person = uuid.uuid4()
    candidates = award_candidates(
        [
            _track(person, complete=True),
            _track(person, complete=False),
            _track(person, groups=("rock",)),
        ]
    )
    assert not any(award.title == "Uncharted" for award in candidates)
    candidates = award_candidates(
        [
            _track(person, complete=True),
            _track(person, complete=True),
            _track(person, groups=("rock",)),
        ]
    )
    assert any(award.title == "Uncharted" for award in candidates)


def test_published_round_awards_read_cached_listener_counts(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    first = make_user(name="Quiet Listener")
    second = make_user(name="Hit Listener")
    middle = make_user(name="Middle Listener")
    round_ = make_round(make_series(), members=[first, second, middle])
    for person, values in (
        (first, (100, 200, 300)),
        (middle, (50_000, 75_000, 100_000)),
        (second, (300_000, 400_000, 500_000)),
    ):
        for listeners in values:
            track = make_track(provider_metadata={"lastfmTrackListeners": listeners})
            make_submission(round_, person, track)
    db.commit()

    awards = round_awards(db, round_.id)

    assert {(award["title"], award["contributor"]["displayName"]) for award in awards} == {
        ("Underground", "Quiet Listener"),
        ("Mainstream", "Hit Listener"),
    }


def test_award_metadata_backfill_query_runs_on_postgres(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
    make_spotify_account: Callable[..., ExternalAccount],
) -> None:
    publisher = make_user(name="Publisher")
    round_ = make_round(make_series(), members=[publisher], status=RoundStatus.PUBLISHED)
    account = make_spotify_account(publisher)
    db.add(
        Publication(
            round_id=round_.id,
            publisher_account_id=account.id,
            idempotency_key=f"key-{uuid.uuid4().hex[:12]}",
            state=PublicationState.PUBLISHED,
            published_at=datetime.now(UTC),
        )
    )
    missing = make_track()
    ready = make_track(
        provider_metadata={
            "lastfmTrackListenersCheckedAt": datetime.now(UTC).isoformat(),
            "lastfmTrackListenersStatus": "complete",
            "genreEnrichmentStatus": "complete",
        }
    )
    make_submission(round_, publisher, missing)
    make_submission(round_, publisher, ready)
    db.commit()
    queued: list[str] = []
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(lastfm_api_key="test"))
    monkeypatch.setattr(tasks, "get_session_factory", lambda: sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(tasks, "defer_track_genre_enrichment", queued.append)
    tasks.backfill_track_award_metadata(0)
    assert queued == [str(missing.id)]
