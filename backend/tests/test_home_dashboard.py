"""Dashboard participation must reflect accepted picks and published artwork only."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.routes.series import list_my_series
from app.db.models import Publication, PublicationState, RoundMember, RoundStatus, SubmissionStatus


def test_dashboard_counts_and_personal_round_priority(
    db, make_user, make_series, make_round, make_track, make_submission
):
    user = make_user()
    other = make_user()
    series = make_series()
    partial = make_round(series, members=[user, other], submission_limit=3)
    empty = make_round(series, members=[user], submission_limit=3)
    make_submission(partial, user, make_track())
    removed = make_submission(partial, user, make_track())
    removed.status = SubmissionStatus.WITHDRAWN
    make_submission(partial, other, make_track())
    db.flush()
    assert list_my_series(db, user)[0]["featuredRound"]["id"] == str(empty.id)
    member = db.scalar(
        select(RoundMember).where(RoundMember.round_id == empty.id, RoundMember.user_id == user.id)
    )
    member.declined_further_submissions_at = datetime.now(UTC)
    db.flush()
    featured = list_my_series(db, user)[0]["featuredRound"]
    assert featured["id"] == str(partial.id)
    assert featured["yourSubmissionCount"] == 1
    assert featured["submittedCount"] == 2
    member = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == partial.id, RoundMember.user_id == user.id
        )
    )
    member.submission_limit_override = 0
    db.flush()
    items = list_my_series(db, user)
    selected = items[0]["featuredRound"]
    # Both are now done; the earlier closing round wins.
    assert selected["id"] == str(partial.id)
    assert selected["submissionLimit"] == 0
    assert selected["isMember"] is True
    admin = make_user(admin=True)
    assert list_my_series(db, admin)[0]["featuredRound"]["isMember"] is False
    member.removed_at = datetime.now(UTC)
    db.flush()
    assert list_my_series(db, user)[0]["featuredRound"]["id"] == str(empty.id)
    assert list_my_series(db, user)[0]["featuredRound"]["declinedFurtherSubmissions"] is True


def test_dashboard_only_uses_published_artwork(
    db, make_user, make_series, make_round, make_track, make_submission, make_spotify_account
):
    user = make_user()
    series = make_series()
    now = datetime.now(UTC)
    closed = make_round(
        series,
        members=[user],
        closes_at=now - timedelta(hours=1),
        publish_at=now + timedelta(hours=1),
    )
    make_submission(closed, user, make_track(artwork_url="https://example.test/private.jpg"))
    db.flush()
    payload = list_my_series(db, user)[0]
    assert payload["fallbackArtworkUrl"] is None
    assert payload["featuredRound"]["artworkUrls"] == []
    published = make_round(series, status=RoundStatus.PUBLISHED, members=[user])
    account = make_spotify_account(user)
    db.add(
        Publication(
            round_id=published.id,
            publisher_account_id=account.id,
            idempotency_key=str(published.id),
            state=PublicationState.PUBLISHED,
            published_at=now,
            spotify_playlist_id="playlist",
        )
    )
    for _ in range(2):
        make_submission(published, user, make_track(artwork_url="https://example.test/public.jpg"))
    db.flush()
    payload = list_my_series(db, user)[0]
    assert payload["fallbackArtworkUrl"] == "https://example.test/public.jpg"
    assert payload["latestPublishedRound"]["artworkUrls"] == ["https://example.test/public.jpg"]
    assert (
        payload["latestPublishedRound"]["spotifyPlaylistUrl"]
        == "https://open.spotify.com/playlist/playlist"
    )
    assert payload["featuredRound"]["artworkUrls"] == []


def test_dashboard_reconciles_every_round_before_selection(db, make_user, make_series, make_round):
    user = make_user()
    now = datetime.now(UTC)
    rounds = [
        make_round(make_series(), members=[user], closes_at=now - timedelta(hours=1))
        for _ in range(2)
    ]
    payloads = list_my_series(db, user)
    assert len(payloads) == 2
    assert all(item["featuredRound"]["status"] == "closed" for item in payloads)
    assert all(round_.status is RoundStatus.CLOSED for round_ in rounds)
