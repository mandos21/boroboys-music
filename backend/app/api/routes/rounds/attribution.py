"""The "guess who submitted what" game for a round that has published."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.payloads import contributor_display_name, spotify_profile_image_subquery
from app.api.routes.rounds._common import _track_payload, _viewer_round, router
from app.api.schemas import (
    AttributionStatusResponse,
    AttributionSubmitResponse,
    AttributionSubmitterBreakdownResponse,
)
from app.db.models import RoundMember, Track, User
from app.services import attribution


class AttributionGuessInput(BaseModel):
    submission_id: uuid.UUID
    contributor_id: uuid.UUID


class AttributionGuessesSubmit(BaseModel):
    guesses: list[AttributionGuessInput]


@router.get("/{round_id}/attribution", response_model=AttributionStatusResponse)
def get_attribution_status(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, _membership = _viewer_round(db, round_id, user)
    publication = attribution.get_publication(db, round_id)
    published = publication is not None and publication.published_at is not None
    enabled = attribution.is_game_enabled(round_)
    revealed = published and attribution.is_revealed_for(db, round_, publication, user.id)
    reveal_time = attribution.reveal_at(round_, publication)
    game = attribution.get_game(db, round_id, user.id)
    spotify_profile_image = spotify_profile_image_subquery(RoundMember.user_id)
    roster_rows = list(
        db.execute(
            select(RoundMember, User, spotify_profile_image)
            .join(User, User.id == RoundMember.user_id)
            .where(RoundMember.round_id == round_id)
            .order_by(User.display_name, User.email, User.id)
        )
    )
    image_by_user_id = {
        member_user.id: profile_image_url for _member, member_user, profile_image_url in roster_rows
    }
    # A member who submitted nothing can never be the right answer to a
    # guess, so they're excluded here rather than offered as a free wrong one.
    submitter_ids = attribution.guessable_contributor_ids(db, round_id)
    roster = [
        {
            "contributor": {
                "id": str(member_user.id),
                "displayName": contributor_display_name(
                    member_user.display_name, member_user.email
                ),
                "spotifyProfileImageUrl": profile_image_url,
            },
            "maxGuesses": (
                member.submission_limit_override
                if member.submission_limit_override is not None
                else round_.submission_limit
            ),
        }
        for member, member_user, profile_image_url in roster_rows
        if member_user.id in submitter_ids
    ]
    # Only shown once this viewer has earned it - either by finishing their
    # own guesses or by waiting out the reveal delay - so it can never become
    # a way to tell who is close to done before playing yourself.
    leaderboard_rows = attribution.leaderboard(db, round_id) if revealed else []
    return {
        "enabled": enabled,
        "published": published,
        "revealed": revealed,
        "revealAt": reveal_time.isoformat() if reveal_time else None,
        "roster": roster,
        "game": (
            {
                "submittedAt": game.submitted_at.isoformat(),
                "correctCount": game.correct_count,
                "totalCount": game.total_count,
            }
            if game is not None and game.submitted_at is not None
            else None
        ),
        "leaderboard": [
            {
                "contributor": {
                    "id": str(entry_user.id),
                    "displayName": contributor_display_name(
                        entry_user.display_name, entry_user.email
                    ),
                    "spotifyProfileImageUrl": image_by_user_id.get(entry_user.id),
                },
                "correctCount": correct,
                "totalCount": total,
            }
            for entry_user, correct, total in leaderboard_rows
        ],
    }


@router.post(
    "/{round_id}/attribution/guesses",
    response_model=AttributionSubmitResponse,
    dependencies=[Depends(require_csrf)],
)
def submit_attribution_guesses(
    round_id: uuid.UUID,
    payload: AttributionGuessesSubmit,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, _membership = _viewer_round(db, round_id, user)
    guesses = {guess.submission_id: guess.contributor_id for guess in payload.guesses}
    if len(guesses) != len(payload.guesses):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="each submission may only be guessed once",
        )
    try:
        result = attribution.submit_guesses(db, round_, user, guesses)
        db.commit()
    except attribution.AttributionError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {
        "correctCount": result.game.correct_count,
        "totalCount": result.game.total_count,
        "results": [
            {
                "submissionId": str(outcome.submission_id),
                "guessedContributorId": str(outcome.guessed_contributor_id),
                "actualContributorId": str(outcome.actual_contributor_id),
                "isCorrect": outcome.is_correct,
            }
            for outcome in result.outcomes
        ],
    }


@router.get(
    "/{round_id}/attribution/breakdown",
    response_model=list[AttributionSubmitterBreakdownResponse],
)
def get_attribution_breakdown(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """Every submitter's songs and who guessed what for them, once revealed.

    Grouped by who actually submitted each song rather than by who did the
    guessing - that's the more useful lens for reviewing after the fact than
    the one-shot scored reveal shown right after a player submits guesses.
    """
    round_, _membership = _viewer_round(db, round_id, user)
    publication = attribution.get_publication(db, round_id)
    if not attribution.is_revealed_for(db, round_, publication, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="names for this round are not revealed for you yet",
        )
    breakdowns = attribution.submitter_breakdown(db, round_id)
    viewer_game = attribution.get_game(db, round_id, user.id)
    viewer_played = viewer_game is not None and viewer_game.submitted_at is not None

    track_ids = {song.submission.track_id for entry in breakdowns for song in entry.songs}
    tracks_by_id = {
        track.id: track for track in db.scalars(select(Track).where(Track.id.in_(track_ids)))
    }

    contributor_ids = {entry.contributor_id for entry in breakdowns}
    for entry in breakdowns:
        for song in entry.songs:
            for guess in song.guesses:
                contributor_ids.add(guess.guesser_id)
                contributor_ids.add(guess.guessed_contributor_id)
    spotify_profile_image = spotify_profile_image_subquery(User.id)
    contributors_by_id = {
        contributor.id: {
            "id": str(contributor.id),
            "displayName": contributor_display_name(contributor.display_name, contributor.email),
            "spotifyProfileImageUrl": profile_image_url,
        }
        for contributor, profile_image_url in db.execute(
            select(User, spotify_profile_image).where(User.id.in_(contributor_ids))
        )
    }

    payload: list[dict[str, object]] = []
    for entry in sorted(
        breakdowns,
        key=lambda e: (
            contributors_by_id[e.contributor_id]["displayName"].lower(),
            e.contributor_id,
        ),
    ):
        songs_payload: list[dict[str, object]] = []
        group_correct = 0
        group_total = 0
        your_correct = 0
        your_total = 0
        for song in entry.songs:
            song_group_correct = sum(1 for guess in song.guesses if guess.is_correct)
            song_group_total = len(song.guesses)
            group_correct += song_group_correct
            group_total += song_group_total
            for guess in song.guesses:
                if guess.guesser_id == user.id:
                    your_total += 1
                    if guess.is_correct:
                        your_correct += 1
            songs_payload.append(
                {
                    "submissionId": str(song.submission.id),
                    "track": _track_payload(tracks_by_id[song.submission.track_id]),
                    "groupCorrectCount": song_group_correct,
                    "groupTotalCount": song_group_total,
                    "guesses": [
                        {
                            "guesser": contributors_by_id[guess.guesser_id],
                            "guessedContributor": contributors_by_id[guess.guessed_contributor_id],
                            "isCorrect": guess.is_correct,
                        }
                        for guess in sorted(
                            song.guesses,
                            key=lambda g: contributors_by_id[g.guesser_id]["displayName"].lower(),
                        )
                    ],
                }
            )
        show_your_stats = viewer_played and entry.contributor_id != user.id
        payload.append(
            {
                "contributor": contributors_by_id[entry.contributor_id],
                "yourCorrectCount": your_correct if show_your_stats else None,
                "yourTotalCount": your_total if show_your_stats else None,
                "groupCorrectCount": group_correct,
                "groupTotalCount": group_total,
                "songs": songs_payload,
            }
        )
    return payload
