"""The "guess who submitted what" game that gates identity reveal after publication.

Submissions and their track data become visible the moment a round actually
publishes (see `app.api.routes.rounds.discovery`), but *who submitted what*
stays hidden - either until a configured delay after that publication elapses,
or until the viewer locks in a full set of guesses, whichever comes first. A
guess attempt is one-shot: once submitted, `AttributionGame.submitted_at` is
set and the game cannot be replayed or edited.

The game itself is a series/round-configurable option, not a fixed part of
publishing: `Round.attribution_reveal_delay_seconds` (and its series-level
default) being `None` means the game is off for that round, and identity
reveals the instant it publishes - exactly the pre-game behavior. Any
non-negative value, including `0`, turns it on with that many seconds of
hidden delay.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AttributionGame,
    AttributionGuess,
    Publication,
    Round,
    RoundMember,
    Submission,
    SubmissionStatus,
    User,
)


class AttributionError(Exception):
    pass


@dataclass(frozen=True)
class GuessOutcome:
    submission_id: uuid.UUID
    guessed_contributor_id: uuid.UUID
    actual_contributor_id: uuid.UUID
    is_correct: bool


@dataclass(frozen=True)
class AttributionResult:
    game: AttributionGame
    outcomes: list[GuessOutcome]


def get_publication(db: Session, round_id: uuid.UUID) -> Publication | None:
    return db.scalar(select(Publication).where(Publication.round_id == round_id))


def is_game_enabled(round_: Round) -> bool:
    return round_.attribution_reveal_delay_seconds is not None


def reveal_at(round_: Round, publication: Publication | None) -> datetime | None:
    if publication is None or publication.published_at is None:
        return None
    delay = round_.attribution_reveal_delay_seconds
    if delay is None:
        return publication.published_at
    return publication.published_at + timedelta(seconds=delay)


def get_game(db: Session, round_id: uuid.UUID, user_id: uuid.UUID) -> AttributionGame | None:
    return db.scalar(
        select(AttributionGame).where(
            AttributionGame.round_id == round_id, AttributionGame.user_id == user_id
        )
    )


def leaderboard(db: Session, round_id: uuid.UUID) -> list[tuple[User, int, int]]:
    """Everyone who has finished guessing this round, most accurate first."""
    rows = db.execute(
        select(User, AttributionGame.correct_count, AttributionGame.total_count)
        .join(User, User.id == AttributionGame.user_id)
        .where(
            AttributionGame.round_id == round_id,
            AttributionGame.submitted_at.is_not(None),
        )
    ).all()
    # Both columns are set together with `submitted_at` in `submit_guesses`,
    # so this filter guarantees they are integers - the `or 0` is only to
    # satisfy the column's nullable type.
    entries = [(user, correct or 0, total or 0) for user, correct, total in rows]
    return sorted(
        entries,
        key=lambda entry: (
            -(entry[1] / entry[2]) if entry[2] else 0.0,
            -entry[2],
            (entry[0].display_name or entry[0].email or "").lower(),
        ),
    )


def is_revealed_for(
    db: Session, round_: Round, publication: Publication | None, user_id: uuid.UUID
) -> bool:
    """Whether this viewer currently sees who submitted what.

    True once the configured delay after publication has elapsed for anyone,
    or as soon as this specific viewer has locked in their own guesses -
    guessing is a personal, immediate unlock rather than something that waits
    for the shared timer too.
    """
    reveal_time = reveal_at(round_, publication)
    if reveal_time is None:
        return False
    if datetime.now(UTC) >= reveal_time:
        return True
    game = get_game(db, round_.id, user_id)
    return game is not None and game.submitted_at is not None


def _guessable_submissions(
    db: Session, round_id: uuid.UUID, user_id: uuid.UUID
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission).where(
                Submission.round_id == round_id,
                Submission.status == SubmissionStatus.ACCEPTED,
                Submission.contributor_id != user_id,
            )
        )
    )


def _member_limits(db: Session, round_: Round) -> dict[uuid.UUID, int]:
    members = list(db.scalars(select(RoundMember).where(RoundMember.round_id == round_.id)))
    return {
        member.user_id: (
            member.submission_limit_override
            if member.submission_limit_override is not None
            else round_.submission_limit
        )
        for member in members
    }


def submit_guesses(
    db: Session,
    round_: Round,
    user: User,
    guesses: dict[uuid.UUID, uuid.UUID],
) -> AttributionResult:
    """Score and permanently record one attempt. Raises on any invalid or repeat attempt."""
    if not is_game_enabled(round_):
        raise AttributionError("the guessing game is not enabled for this round")
    publication = get_publication(db, round_.id)
    if publication is None or publication.published_at is None:
        raise AttributionError("the round has not published yet")
    if get_game(db, round_.id, user.id) is not None:
        raise AttributionError("guesses have already been submitted for this round")

    submissions = _guessable_submissions(db, round_.id, user.id)
    guessable_ids = {submission.id for submission in submissions}
    if set(guesses) != guessable_ids:
        raise AttributionError("guesses must cover exactly the round's other submissions")

    limits = _member_limits(db, round_)
    guessed_counts: dict[uuid.UUID, int] = {}
    for guessed_contributor_id in guesses.values():
        if guessed_contributor_id not in limits:
            raise AttributionError("a guess must name a member of this round")
        guessed_counts[guessed_contributor_id] = guessed_counts.get(guessed_contributor_id, 0) + 1
    for contributor_id, count in guessed_counts.items():
        if count > limits[contributor_id]:
            raise AttributionError(
                "a guess would assign more tracks to a member than their submission limit"
            )

    game = AttributionGame(round_id=round_.id, user_id=user.id)
    db.add(game)
    db.flush()

    outcomes: list[GuessOutcome] = []
    correct_count = 0
    for submission in submissions:
        guessed_contributor_id = guesses[submission.id]
        is_correct = guessed_contributor_id == submission.contributor_id
        if is_correct:
            correct_count += 1
        db.add(
            AttributionGuess(
                game_id=game.id,
                submission_id=submission.id,
                guessed_contributor_id=guessed_contributor_id,
                is_correct=is_correct,
            )
        )
        outcomes.append(
            GuessOutcome(
                submission_id=submission.id,
                guessed_contributor_id=guessed_contributor_id,
                actual_contributor_id=submission.contributor_id,
                is_correct=is_correct,
            )
        )
    game.submitted_at = datetime.now(UTC)
    game.correct_count = correct_count
    game.total_count = len(submissions)
    return AttributionResult(game=game, outcomes=outcomes)
