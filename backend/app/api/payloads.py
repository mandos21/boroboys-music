"""Read-model fragments shared by more than one route module.

Each helper here exists because the same shape or query was being written out
in two or more places. Route-specific payload assembly stays with its route.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ScalarSelect, select
from sqlalchemy.orm import Mapped, Session

from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    Round,
    Submission,
    SubmissionStatus,
    Track,
)

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
    """Never render a blank name, and never render a full email address.

    A provider that sends no name still usually sends an address. The part
    before the "@" identifies the person to their friends without publishing
    the address itself to every round they are in; administrators see the
    full address through the admin endpoints.
    """
    if display_name:
        return display_name
    local_part = email.split("@", 1)[0].strip() if email else ""
    return local_part or UNKNOWN_CONTRIBUTOR


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


def round_artwork_urls_by_round(
    db: Session, round_ids: Sequence[uuid.UUID], limit: int = 8
) -> dict[uuid.UUID, list[str]]:
    """Pick per-round artwork round-robin in one query for history pages."""
    if not round_ids:
        return {}
    rows = list(
        db.execute(
            select(Submission.round_id, Submission.contributor_id, Track.artwork_url)
            .join(Track, Track.id == Submission.track_id)
            .where(
                Submission.round_id.in_(round_ids),
                Submission.status == SubmissionStatus.ACCEPTED,
                Track.artwork_url.is_not(None),
            )
            .order_by(Submission.round_id, Submission.created_at, Submission.id)
        )
    )
    by_round: dict[uuid.UUID, dict[uuid.UUID, list[str]]] = {}
    for round_id, contributor_id, artwork_url in rows:
        if isinstance(artwork_url, str):
            by_round.setdefault(round_id, {}).setdefault(contributor_id, []).append(artwork_url)
    selected_by_round: dict[uuid.UUID, list[str]] = {}
    for round_id, by_contributor in by_round.items():
        selected: list[str] = []
        while by_contributor and len(selected) < limit:
            for contributor_id in list(by_contributor):
                selected.append(by_contributor[contributor_id].pop(0))
                if not by_contributor[contributor_id]:
                    del by_contributor[contributor_id]
                if len(selected) == limit:
                    break
        selected_by_round[round_id] = selected
    return selected_by_round
