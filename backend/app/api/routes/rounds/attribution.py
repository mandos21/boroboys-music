"""The "guess who submitted what" game for a round that has published."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.payloads import contributor_display_name, spotify_profile_image_subquery
from app.api.routes.rounds._common import _viewer_round, router
from app.api.schemas import AttributionStatusResponse, AttributionSubmitResponse
from app.db.models import RoundMember, User
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
