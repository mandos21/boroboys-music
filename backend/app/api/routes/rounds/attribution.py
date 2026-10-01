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
    AttributionGameDetailResponse,
    AttributionStatusResponse,
    AttributionSubmitResponse,
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
    "/{round_id}/attribution/games/{user_id}",
    response_model=AttributionGameDetailResponse,
)
def get_attribution_game_detail(
    round_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Review any completed player's stored guesses - not the one-time submit reveal.

    Gated on the requesting viewer's own reveal state, same as the
    leaderboard it's linked from: seeing how someone else did is part of
    what unlocks once names are revealed for you, not a separate privilege.
    """
    round_, _membership = _viewer_round(db, round_id, user)
    publication = attribution.get_publication(db, round_id)
    if not attribution.is_revealed_for(db, round_, publication, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="names for this round are not revealed for you yet",
        )
    detail = attribution.game_detail_rows(db, round_id, user_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="that player has not completed this round's guessing game",
        )
    game, rows = detail

    track_ids = {submission.track_id for _guess, submission in rows}
    tracks_by_id = {
        track.id: track for track in db.scalars(select(Track).where(Track.id.in_(track_ids)))
    }

    contributor_ids = (
        {user_id}
        | {guess.guessed_contributor_id for guess, _s in rows}
        | {submission.contributor_id for _guess, submission in rows}
    )
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

    return {
        "contributor": contributors_by_id[user_id],
        "submittedAt": game.submitted_at.isoformat() if game.submitted_at else None,
        "correctCount": game.correct_count,
        "totalCount": game.total_count,
        "items": [
            {
                "submissionId": str(submission.id),
                "track": _track_payload(tracks_by_id[submission.track_id]),
                "guessedContributor": contributors_by_id[guess.guessed_contributor_id],
                "actualContributor": contributors_by_id[submission.contributor_id],
                "isCorrect": guess.is_correct,
            }
            for guess, submission in rows
        ],
    }
