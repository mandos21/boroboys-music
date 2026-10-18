"""Round superlatives from published submissions and durable track metadata."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.payloads import contributor_display_name, contributor_profile_image_subquery
from app.db.models import Submission, SubmissionStatus, Track, TrackGenre, User
from app.services.genre_taxonomy import OTHER_GROUP, group_for


@dataclass(frozen=True)
class AwardTrack:
    contributor_id: uuid.UUID
    track_id: uuid.UUID
    listeners: int | None
    groups: frozenset[str]
    genre_complete: bool
    has_genres: bool


@dataclass(frozen=True)
class AwardCandidate:
    title: str
    contributor_id: uuid.UUID
    detail: str
    explanation: str
    strength: float


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def award_candidates(tracks: list[AwardTrack]) -> list[AwardCandidate]:
    """Return eligible candidates with a comparable strength for slot selection."""
    by_person: dict[uuid.UUID, list[AwardTrack]] = defaultdict(list)
    for track in tracks:
        by_person[track.contributor_id].append(track)
    known = sorted(
        ((track.listeners, track.track_id) for track in tracks if track.listeners is not None),
        key=lambda item: (item[0], str(item[1])),
    )
    third = max(1, math.ceil(len(known) / 3))
    lower = known[third - 1][0] if known else None
    upper = known[-third][0] if known else None
    candidates: list[AwardCandidate] = []
    for person_id, selections in by_person.items():
        count = len(selections)
        eighty = math.ceil(count * 0.8)
        two_thirds = math.ceil(count * 2 / 3)
        for title, cutoff in (("Underground", lower), ("Mainstream", upper)):
            if cutoff is None:
                continue
            qualifying = [
                track.listeners
                for track in selections
                if track.listeners is not None
                and (
                    track.listeners <= min(cutoff, 25_000)
                    if title == "Underground"
                    else track.listeners >= max(cutoff, 250_000)
                )
            ]
            if len(qualifying) >= eighty:
                values = sorted(qualifying)
                median = values[len(values) // 2]
                category = "least" if title == "Underground" else "most"
                detail = (
                    "Dug deepest into the catalog."
                    if title == "Underground"
                    else "Found the familiar hits."
                )
                bonus = (
                    1 / (1 + median / 25_000)
                    if title == "Underground"
                    else min(median / 250_000, 3) / 3
                )
                candidates.append(
                    AwardCandidate(
                        title,
                        person_id,
                        detail,
                        f"{len(qualifying)} of {count} tracks in this round's {category} "
                        f"listened-to third (median {median:,} Last.fm listeners)",
                        len(qualifying) / count + bonus / 10,
                    )
                )
        if count >= 2:
            tagged = [track for track in selections if track.groups]
            averages = (
                [
                    sum(
                        _jaccard(track.groups, other.groups)
                        for other in tagged
                        if other is not track
                    )
                    / (len(tagged) - 1)
                    for track in tagged
                ]
                if len(tagged) >= 2
                else []
            )
            for title in ("Eclectic", "Specialized"):
                qualified = [
                    value
                    for value in averages
                    if (value <= 0.25 if title == "Eclectic" else value >= 0.4)
                ]
                if len(qualified) >= eighty:
                    overall = sum(averages) / len(averages)
                    eclectic = title == "Eclectic"
                    candidates.append(
                        AwardCandidate(
                            title,
                            person_id,
                            "Took the long way around the genres."
                            if eclectic
                            else "Stayed in a familiar lane.",
                            f"{len(qualified)} of {count} tracks "
                            f"{'covered distinct' if eclectic else 'shared similar'} "
                            "genre groups",
                            len(qualified) / count + ((1 - overall) if eclectic else overall) / 10,
                        )
                    )
        no_tags = sum(track.genre_complete and not track.has_genres for track in selections)
        if no_tags >= two_thirds:
            candidates.append(
                AwardCandidate(
                    "Uncharted",
                    person_id,
                    "Made the genre map draw a blank.",
                    f"{no_tags} of {count} tracks had no recognized genre tags",
                    no_tags / count,
                )
            )
    return candidates


def round_awards(db: Session, round_id: uuid.UUID) -> list[dict[str, object]]:
    rows = list(
        db.execute(
            select(Submission, Track, User, contributor_profile_image_subquery(User.id))
            .join(Track, Track.id == Submission.track_id)
            .join(User, User.id == Submission.contributor_id)
            .where(Submission.round_id == round_id, Submission.status == SubmissionStatus.ACCEPTED)
            .order_by(Submission.id)
        )
    )
    if not rows:
        return []
    ids = {track.id for _, track, _, _ in rows}
    genre_names: dict[uuid.UUID, list[str]] = defaultdict(list)
    genre_query = select(TrackGenre.track_id, TrackGenre.name).where(TrackGenre.track_id.in_(ids))
    for track_id, name in db.execute(genre_query):
        genre_names[track_id].append(name)
    people = {user.id: (user, image) for _, _, user, image in rows}
    tracks = []
    for submission, track, _, _ in rows:
        raw_listeners = track.provider_metadata.get("lastfmTrackListeners")
        genres = genre_names[track.id]
        groups = frozenset(group for name in genres if (group := group_for(name)) != OTHER_GROUP)
        tracks.append(
            AwardTrack(
                contributor_id=submission.contributor_id,
                track_id=track.id,
                listeners=raw_listeners
                if type(raw_listeners) is int and raw_listeners >= 0
                else None,
                groups=groups,
                genre_complete=track.provider_metadata.get("genreEnrichmentStatus") == "complete",
                has_genres=bool(groups),
            )
        )
    # One winner per title. Prefer different people where strengths are close;
    # return up to four actual findings rather than filling empty slots.
    ranked = sorted(
        award_candidates(tracks),
        key=lambda row: (-row.strength, row.title, str(row.contributor_id)),
    )
    selected: list[AwardCandidate] = []
    seen_titles: set[str] = set()
    seen_people: set[uuid.UUID] = set()
    while len(selected) < 4:
        options = [row for row in ranked if row.title not in seen_titles]
        if not options:
            break
        choice = max(
            options,
            key=lambda row: (
                row.strength - (0.08 if row.contributor_id in seen_people else 0),
                -ranked.index(row),
            ),
        )
        selected.append(choice)
        seen_titles.add(choice.title)
        seen_people.add(choice.contributor_id)
    return [
        {
            "title": row.title,
            "variant": row.title.lower(),
            "detail": row.detail,
            "explanation": row.explanation,
            "contributor": {
                "id": str(row.contributor_id),
                "displayName": contributor_display_name(
                    people[row.contributor_id][0].display_name,
                    people[row.contributor_id][0].email,
                ),
                "profileImageUrl": people[row.contributor_id][1],
            },
        }
        for row in selected
    ]
