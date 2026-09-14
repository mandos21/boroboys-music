"""Seed a throwaway published round for local UI testing.

NOT part of the product - a quick, re-runnable way to get real-looking data
into "Test Series 1" (created if missing) so the genre-mix ("who brings
what") view and the attribution guessing game/leaderboard/profile stat have
something to look at, without waiting for a real round to close and publish.

Safe to run repeatedly: it deletes and recreates its own demo round each
time (cascades clean up its submissions/publication/attribution rows), and
reuses the same four fake accounts across runs instead of piling up more.

Usage (from backend/):
    poetry run python scripts/dev_seed_attribution_demo.py
    poetry run python scripts/dev_seed_attribution_demo.py --as-email you@example.com
"""

from __future__ import annotations

import argparse
import base64
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    PlatformRole,
    Publication,
    PublicationItem,
    PublicationState,
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
from app.services.track_metadata import store_track_genres, sync_track_artists

SERIES_NAME = "Test Series 1"
SERIES_SLUG = "test-series-1"
ROUND_TITLE = "Guess Who? Demo Round"
ATTRIBUTION_REVEAL_DELAY_SECONDS = 3600

# Genre names picked so each fake contributor lands in a couple of distinct
# `genre_taxonomy` groups - the point is to see a colorful, varied "who
# brings what" mix, not a realistic listening history.
DEMO_USERS = [
    ("Test Alice", ["indie rock", "ambient"]),
    ("Test Bob", ["midwest emo", "trip hop"]),
    ("Test Carol", ["art pop", "post-punk"]),
    ("Test Dave", ["k-pop", "soul"]),
]

DEMO_TRACKS = [
    ("Night Drive", "The Amber Hours"),
    ("Lemonlight", "Paper Moths"),
    ("Northbound", "Static Habits"),
    ("Slow Gold", "Coastline Radio"),
    ("Velvet", "The Understudies"),
    ("Blue Hour", "Nightjar"),
    ("Afterglow", "Field Notes"),
    ("Low Tide", "Cassette Ghosts"),
]


def _placeholder_artwork(seed: str) -> str:
    color = f"{abs(hash(seed)) % 0xFFFFFF:06x}"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
        f'<rect width="120" height="120" fill="#{color}"/></svg>'
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-email",
        help="an existing user's email to add to the demo round as a real, "
        "non-submitting member, so you can log in as yourself and play the "
        "guessing game. Defaults to the best real-looking account it can "
        "find; pass this explicitly if that guess is ever wrong.",
    )
    args = parser.parse_args()

    with get_session_factory()() as db:
        # Matched by name, not slug: a "Test Series 1" created by hand
        # through the admin UI won't have this script's slug, and the point
        # is to add the demo round to whatever series already has this name.
        series = db.scalar(select(Series).where(Series.name == SERIES_NAME))
        if series is None:
            series = Series(
                name=SERIES_NAME,
                slug=SERIES_SLUG,
                timezone="UTC",
                default_policies=[],
                auto_start_next_round=False,
            )
            db.add(series)
            db.flush()
            print(f"Created series {SERIES_NAME!r} ({series.id})")
        else:
            print(f"Reusing existing series {series.name!r} ({series.id})")

        existing_round = db.scalar(
            select(Round).where(Round.series_id == series.id, Round.title == ROUND_TITLE)
        )
        if existing_round is not None:
            db.delete(existing_round)
            db.flush()
            print("Removed the previous demo round so this run starts clean.")

        real_user: User | None
        if args.as_email:
            real_user = db.scalar(select(User).where(User.email == args.as_email))
            if real_user is None:
                parser.error(f"no user found with email {args.as_email!r}")
        else:
            # A database that has ever had pytest point at it by mistake can
            # be full of accounts using pytest's fixture issuer, admin-flagged
            # ones included - excluding it is what keeps this auto-detected
            # fallback from grabbing one of those instead of a real account.
            not_pytest_fixtures = User.oidc_issuer.not_in(
                ("https://issuer.test", "https://dev-seed.local")
            )
            real_user = (
                db.scalar(
                    select(User)
                    .where(User.platform_role == PlatformRole.ADMIN, not_pytest_fixtures)
                    .order_by(User.created_at)
                )
                or db.scalar(
                    select(User)
                    .where(User.email.is_not(None), not_pytest_fixtures)
                    .order_by(User.created_at)
                )
                or db.scalar(
                    select(User)
                    .where(User.platform_role == PlatformRole.ADMIN)
                    .order_by(User.created_at)
                )
            )
        if real_user is not None:
            print(f"Including {real_user.email or real_user.id} as a non-submitting member.")
        else:
            print("No existing user found to include - pass --as-email to add yourself.")

        fake_users: list[User] = []
        for name, _genres in DEMO_USERS:
            subject = f"demo-{name.lower().replace(' ', '-')}"
            user = db.scalar(
                select(User).where(
                    User.oidc_issuer == "https://dev-seed.local", User.oidc_subject == subject
                )
            )
            if user is None:
                user = User(
                    oidc_issuer="https://dev-seed.local",
                    oidc_subject=subject,
                    display_name=name,
                    platform_role=PlatformRole.MEMBER,
                )
                db.add(user)
                db.flush()
            fake_users.append(user)

        publisher_owner = real_user or fake_users[0]
        publisher_account = ExternalAccount(
            user_id=publisher_owner.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"demo-publisher-{uuid.uuid4().hex[:8]}",
            display_name="Demo Publisher",
        )
        db.add(publisher_account)
        db.flush()

        now = datetime.now(UTC)
        opens_at = now - timedelta(days=3)
        closes_at = now - timedelta(days=1)
        publish_at = closes_at + timedelta(minutes=5)
        sequence = (
            db.scalar(
                select(func.max(Round.published_sequence)).where(Round.series_id == series.id)
            )
            or 0
        ) + 1

        round_ = Round(
            series_id=series.id,
            title=ROUND_TITLE,
            timezone="UTC",
            submission_limit=2,
            opens_at=opens_at,
            closes_at=closes_at,
            publish_at=publish_at,
            status=RoundStatus.PUBLISHED,
            policy_snapshot=[],
            publisher_account_id=publisher_account.id,
            published_sequence=sequence,
            attribution_reveal_delay_seconds=ATTRIBUTION_REVEAL_DELAY_SECONDS,
        )
        db.add(round_)
        db.flush()

        members = list(fake_users)
        if real_user is not None and real_user.id not in {member.id for member in members}:
            members.append(real_user)
        for member in members:
            db.add(RoundMember(round_id=round_.id, user_id=member.id))

        submissions: list[Submission] = []
        track_pool = iter(DEMO_TRACKS * 2)
        for user, (_name, genres) in zip(fake_users, DEMO_USERS, strict=True):
            for _ in range(2):
                track_name, artist_name = next(track_pool)
                track = Track(
                    spotify_track_id=f"demo-{uuid.uuid4().hex[:12]}",
                    name=track_name,
                    artist=artist_name,
                    spotify_uri=f"spotify:track:demo-{uuid.uuid4().hex[:12]}",
                    artwork_url=_placeholder_artwork(f"{track_name}{artist_name}"),
                )
                db.add(track)
                db.flush()
                sync_track_artists(db, track, [(f"demo-artist-{artist_name}", artist_name, 0)])
                store_track_genres(db, track, genres)
                submission = Submission(
                    round_id=round_.id,
                    contributor_id=user.id,
                    track_id=track.id,
                    status=SubmissionStatus.ACCEPTED,
                )
                db.add(submission)
                submissions.append(submission)
        db.flush()

        # Shuffled the same way a real publish would, so proximity in the
        # list doesn't hint at who submitted what.
        random.shuffle(submissions)
        published_at = now - timedelta(minutes=10)
        publication = Publication(
            round_id=round_.id,
            publisher_account_id=publisher_account.id,
            state=PublicationState.PUBLISHED,
            idempotency_key=f"demo-{uuid.uuid4().hex}",
            spotify_playlist_id=f"demo-playlist-{uuid.uuid4().hex[:12]}",
            published_at=published_at,
        )
        db.add(publication)
        db.flush()
        for position, submission in enumerate(submissions, start=1):
            db.add(
                PublicationItem(
                    publication_id=publication.id,
                    submission_id=submission.id,
                    track_id=submission.track_id,
                    contributor_id=submission.contributor_id,
                    position=position,
                )
            )

        db.commit()

        reveal_at = published_at + timedelta(seconds=ATTRIBUTION_REVEAL_DELAY_SECONDS)
        print(f"\nSeries: {series.name} ({series.id})")
        print(f"Round:  {round_.title} ({round_.id})")
        print(f"Published {published_at.isoformat()}")
        print(f"Attribution hidden until {reveal_at.isoformat()}")
        print(f"Test users: {', '.join(name for name, _ in DEMO_USERS)}")
        print(f"\nhttp://localhost:5173/series/{series.id}")
        print(f"http://localhost:5173/rounds/{round_.id}")


if __name__ == "__main__":
    main()
