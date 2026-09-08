"""Read-model fragments shared by more than one route module.

Each helper here exists because the same shape or query was being written out
in two or more places. Route-specific payload assembly stays with its route.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ScalarSelect, select
from sqlalchemy.orm import Mapped

from app.db.models import ExternalAccount, ExternalProvider, Round

UNKNOWN_CONTRIBUTOR = "Unknown listener"


def spotify_profile_image_subquery(user_column: Mapped[uuid.UUID]) -> ScalarSelect[str | None]:
    """The oldest active Spotify avatar for whichever user the outer query names.

    Correlated rather than joined so a contributor with no Spotify link still
    appears in the outer result.
    """
    return (
        select(ExternalAccount.profile_image_url)
        .where(
            ExternalAccount.user_id == user_column,
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.is_active.is_(True),
        )
        .order_by(ExternalAccount.created_at)
        .limit(1)
        .scalar_subquery()
    )


def contributor_display_name(display_name: str | None, email: str | None) -> str:
    """Never render a blank name; fall back to the address, then to a label."""
    return display_name or email or UNKNOWN_CONTRIBUTOR


def round_timeline(round_: Round) -> dict[str, object]:
    """The round fields every round-shaped response carries."""
    return {
        "id": str(round_.id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
        "prompt": round_.prompt,
    }


def stable_pick(values: Sequence[str], seed: uuid.UUID) -> str | None:
    """Choose one value per identifier, the same way on every request.

    Picking at random made a page change its artwork on each refetch, and
    always picking the first made every round in a series look alike.
    """
    if not values:
        return None
    return values[seed.int % len(values)]
