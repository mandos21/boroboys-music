"""Published round superlatives, independent of Guess Who participation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.deps import DbSession, get_current_user
from app.api.routes.rounds._common import _viewer_round, router
from app.api.schemas import RoundAwardResponse
from app.db.models import RoundStatus, User
from app.services import attribution
from app.services.round_awards import round_awards


@router.get("/{round_id}/awards", response_model=list[RoundAwardResponse])
def get_round_awards(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    round_, _ = _viewer_round(db, round_id, user)
    if round_.status is not RoundStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="round not published")
    if attribution.is_game_enabled(round_) and not attribution.is_revealed_for(
        db, round_, attribution.get_publication(db, round_id), user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="round awards are not revealed for you yet",
        )
    return round_awards(db, round_id)
