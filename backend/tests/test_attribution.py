"""The "guess who submitted what" game: reveal timing, scoring, and routes."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.rounds import (
    get_attribution_status,
    list_round_submission_counts,
    list_round_submissions,
    submit_attribution_guesses,
)
from app.api.routes.rounds.attribution import AttributionGuessesSubmit, AttributionGuessInput
from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    AttributionGame,
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    Publication,
    PublicationItem,
    PublicationState,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    Submission,
    Track,
    User,
)
from app.services import attribution
from app.services.publications import start_publication


def _publish(
    db: Session,
    round_: Round,
    publisher: User,
    *,
    published_at: datetime | None = None,
) -> Publication:
    """Close, "publish" (without calling Spotify), and shuffle a round's items.

    Mirrors what `execute_publication` does once Spotify confirms every item,
    without needing to mock the Spotify client for tests that only care about
    the attribution game.
    """
    account = ExternalAccount(
        user_id=publisher.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"publisher-{uuid.uuid4().hex[:12]}",
    )
    db.add(account)
    db.flush()
    db.add(
        ExternalCredential(
            external_account_id=account.id,
            ciphertext=encrypt(
                json.dumps({"access_token": "test-token"}),
                get_settings().credential_encryption_key.get_secret_value(),
            ),
            key_version="v1",
        )
    )
    db.flush()
    round_.status = RoundStatus.CLOSED
    db.flush()
    publication = start_publication(db, round_.id, account.id, publisher.id)
    publication.state = PublicationState.PUBLISHED
    publication.spotify_playlist_id = f"playlist-{uuid.uuid4().hex[:12]}"
    publication.published_at = published_at or datetime.now(UTC)
    round_.status = RoundStatus.PUBLISHED
    db.commit()
    return publication


def test_reveal_at_is_publication_completion_plus_the_configured_delay(
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
) -> None:
    series = make_series()
    round_ = make_round(series, attribution_reveal_delay_seconds=3600)
    published_at = datetime.now(UTC) - timedelta(minutes=5)
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=uuid.uuid4(),
        idempotency_key=f"key-{uuid.uuid4().hex[:12]}",
        state=PublicationState.PUBLISHED,
        published_at=published_at,
    )
    assert attribution.reveal_at(round_, publication) == published_at + timedelta(hours=1)
    assert attribution.reveal_at(round_, None) is None

    unpublished = Publication(
        round_id=round_.id,
        publisher_account_id=uuid.uuid4(),
        idempotency_key=f"key-{uuid.uuid4().hex[:12]}",
        state=PublicationState.PUBLISHING,
    )
    assert attribution.reveal_at(round_, unpublished) is None


def test_is_revealed_for_waits_for_the_delay_or_a_completed_guess(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
) -> None:
    viewer = make_user(name="Viewer")
    other = make_user(name="Other")
    series = make_series()
    round_ = make_round(series, attribution_reveal_delay_seconds=3600, members=[viewer, other])
    account = ExternalAccount(
        user_id=viewer.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"publisher-{uuid.uuid4().hex[:12]}",
    )
    db.add(account)
    db.flush()
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=account.id,
        idempotency_key=f"key-{uuid.uuid4().hex[:12]}",
        state=PublicationState.PUBLISHED,
        published_at=datetime.now(UTC) - timedelta(minutes=30),
    )
    db.add(publication)
    db.commit()

    # Delay hasn't elapsed and nobody has guessed yet.
    assert attribution.is_revealed_for(db, round_, publication, viewer.id) is False

    # A viewer who has locked in guesses unlocks their own reveal early.
    finished_game = AttributionGame(
        round_id=round_.id,
        user_id=viewer.id,
        submitted_at=datetime.now(UTC),
        correct_count=0,
        total_count=0,
    )
    db.add(finished_game)
    db.commit()
    assert attribution.is_revealed_for(db, round_, publication, viewer.id) is True
    # A different viewer without a completed game still waits.
    assert attribution.is_revealed_for(db, round_, publication, other.id) is False

    # Once the delay elapses, it's revealed for everyone regardless of guessing.
    publication.published_at = datetime.now(UTC) - timedelta(hours=2)
    db.commit()
    assert attribution.is_revealed_for(db, round_, publication, other.id) is True


def test_submit_guesses_scores_correctly_and_excludes_the_viewers_own_submission(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    bob = make_user(name="Bob")
    series = make_series()
    round_ = make_round(
        series,
        attribution_reveal_delay_seconds=3600,
        submission_limit=5,
        members=[viewer, alice, bob],
    )
    own_track = make_track(name="Mine")
    alice_track = make_track(name="Alice's pick")
    bob_track = make_track(name="Bob's pick")
    make_submission(round_, viewer, own_track)
    alice_submission = make_submission(round_, alice, alice_track)
    bob_submission = make_submission(round_, bob, bob_track)
    db.commit()
    _publish(db, round_, viewer)

    result = attribution.submit_guesses(
        db,
        round_,
        viewer,
        {
            alice_submission.id: bob.id,  # wrong
            bob_submission.id: bob.id,  # right
        },
    )
    db.commit()

    assert result.game.total_count == 2
    assert result.game.correct_count == 1
    assert result.game.submitted_at is not None
    outcomes = {outcome.submission_id: outcome.is_correct for outcome in result.outcomes}
    assert outcomes == {alice_submission.id: False, bob_submission.id: True}


def test_submit_guesses_rejects_a_repeat_attempt(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(
        series, attribution_reveal_delay_seconds=3600, submission_limit=5, members=[viewer, alice]
    )
    alice_submission = make_submission(round_, alice, make_track())
    db.commit()
    _publish(db, round_, viewer)

    attribution.submit_guesses(db, round_, viewer, {alice_submission.id: alice.id})
    db.commit()

    with pytest.raises(attribution.AttributionError, match="already been submitted"):
        attribution.submit_guesses(db, round_, viewer, {alice_submission.id: alice.id})


def test_submit_guesses_requires_the_round_to_have_published(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(
        series, attribution_reveal_delay_seconds=3600, submission_limit=5, members=[viewer, alice]
    )
    alice_submission = make_submission(round_, alice, make_track())
    db.commit()

    with pytest.raises(attribution.AttributionError, match="not published"):
        attribution.submit_guesses(db, round_, viewer, {alice_submission.id: alice.id})


def test_submit_guesses_rejects_incomplete_or_mismatched_coverage(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    bob = make_user(name="Bob")
    series = make_series()
    round_ = make_round(
        series,
        attribution_reveal_delay_seconds=3600,
        submission_limit=5,
        members=[viewer, alice, bob],
    )
    alice_submission = make_submission(round_, alice, make_track())
    make_submission(round_, bob, make_track())
    db.commit()
    _publish(db, round_, viewer)

    with pytest.raises(attribution.AttributionError, match="exactly the round's other"):
        attribution.submit_guesses(db, round_, viewer, {alice_submission.id: alice.id})


def test_submit_guesses_rejects_a_guess_for_a_non_member(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    outsider = make_user(name="Outsider")
    series = make_series()
    round_ = make_round(
        series, attribution_reveal_delay_seconds=3600, submission_limit=5, members=[viewer, alice]
    )
    alice_submission = make_submission(round_, alice, make_track())
    db.commit()
    _publish(db, round_, viewer)

    with pytest.raises(attribution.AttributionError, match="member of this round"):
        attribution.submit_guesses(db, round_, viewer, {alice_submission.id: outsider.id})


def test_submit_guesses_enforces_each_members_submission_limit(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    """A member who could only ever submit 3 tracks can't be guessed a 4th.

    Fewer guesses than their limit stay allowed even if they actually
    submitted fewer than that - the cap only rules out impossible guesses, it
    never reveals the true count.
    """
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(
        series, attribution_reveal_delay_seconds=3600, submission_limit=3, members=[viewer, alice]
    )
    # Alice only actually submitted one track...
    alice_submission = make_submission(round_, alice, make_track(name="Alice's only pick"))
    # ...but three other tracks exist in the round (from the viewer, excluded
    # from guessing, plus two more attributed to nobody in this fixture set is
    # not possible - so borrow the viewer's own submissions' ids is invalid;
    # instead use three more members to have three more guessable submissions).
    bob = make_user(name="Bob")
    carol = make_user(name="Carol")
    dave = make_user(name="Dave")
    db.add_all(
        (
            RoundMember(round_id=round_.id, user_id=bob.id),
            RoundMember(round_id=round_.id, user_id=carol.id),
            RoundMember(round_id=round_.id, user_id=dave.id),
        )
    )
    db.flush()
    bob_submission = make_submission(round_, bob, make_track(name="Bob's pick"))
    carol_submission = make_submission(round_, carol, make_track(name="Carol's pick"))
    dave_submission = make_submission(round_, dave, make_track(name="Dave's pick"))
    db.commit()
    _publish(db, round_, viewer)

    # Guessing three (not-actually-Alice's) tracks onto Alice is allowed -
    # wrong, but within her possible limit.
    result = attribution.submit_guesses(
        db,
        round_,
        viewer,
        {
            alice_submission.id: alice.id,
            bob_submission.id: alice.id,
            carol_submission.id: alice.id,
            dave_submission.id: bob.id,
        },
    )
    assert result.game.correct_count == 1
    db.rollback()

    # A fourth track guessed onto Alice would exceed her round-wide limit.
    with pytest.raises(attribution.AttributionError, match="submission limit"):
        attribution.submit_guesses(
            db,
            round_,
            viewer,
            {
                alice_submission.id: alice.id,
                bob_submission.id: alice.id,
                carol_submission.id: alice.id,
                dave_submission.id: alice.id,
            },
        )


def test_publication_shuffles_item_order_away_from_submission_order(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    publisher = make_user(name="Publisher", admin=True)
    series = make_series()
    round_ = make_round(series, submission_limit=1, members=[publisher])
    contributors = [make_user(name=f"C{i}") for i in range(10)]
    for contributor in contributors:
        db.add(RoundMember(round_id=round_.id, user_id=contributor.id))
    db.flush()
    submission_order = [
        make_submission(round_, contributor, make_track(name=f"T{i}")).id
        for i, contributor in enumerate(contributors)
    ]
    db.commit()
    publication = _publish(db, round_, publisher)

    items = list(
        db.scalars(
            select(PublicationItem)
            .where(PublicationItem.publication_id == publication.id)
            .order_by(PublicationItem.position)
        )
    )
    shuffled_order = [item.submission_id for item in items]
    assert set(shuffled_order) == set(submission_order)
    assert shuffled_order != submission_order


def test_list_round_submissions_hides_identity_until_revealed_then_shows_it(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(series, submission_limit=5, members=[viewer, alice])
    make_submission(round_, viewer, make_track(name="Mine"))
    alice_submission = make_submission(round_, alice, make_track(name="Alice's pick"))
    round_.attribution_reveal_delay_seconds = 3600
    db.commit()
    _publish(db, round_, viewer)

    hidden_view = list_round_submissions(round_.id, db, viewer)
    by_id = {entry["id"]: entry for entry in hidden_view}
    assert by_id[str(alice_submission.id)]["contributor"] is None
    assert by_id[str(alice_submission.id)]["isMine"] is False
    # The viewer's own entry is never hidden from them.
    mine = next(entry for entry in hidden_view if entry["isMine"])
    assert mine["contributor"] is not None

    # Locking in guesses reveals it for this viewer immediately.
    submit_attribution_guesses(
        round_.id,
        AttributionGuessesSubmit(
            guesses=[
                AttributionGuessInput(submission_id=alice_submission.id, contributor_id=alice.id)
            ]
        ),
        db,
        viewer,
    )
    db.commit()
    revealed_view = list_round_submissions(round_.id, db, viewer)
    revealed_entry = next(e for e in revealed_view if e["id"] == str(alice_submission.id))
    assert revealed_entry["contributor"]["id"] == str(alice.id)

    # A second viewer who never guessed still sees it hidden.
    other_viewer = make_user(name="Bystander")
    db.add(RoundMember(round_id=round_.id, user_id=other_viewer.id))
    db.commit()
    still_hidden = list_round_submissions(round_.id, db, other_viewer)
    still_hidden_entry = next(e for e in still_hidden if e["id"] == str(alice_submission.id))
    assert still_hidden_entry["contributor"] is None


def test_submission_counts_hide_totals_while_attribution_is_hidden(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(series, submission_limit=5, members=[viewer, alice])
    make_submission(round_, alice, make_track())
    round_.attribution_reveal_delay_seconds = 3600
    db.commit()
    _publish(db, round_, viewer)

    assert list_round_submission_counts(round_.id, db, viewer) == []

    # Once the delay elapses, counts return like they did before publication.
    publication = db.scalar(select(Publication).where(Publication.round_id == round_.id))
    assert publication is not None
    publication.published_at = datetime.now(UTC) - timedelta(hours=2)
    db.commit()
    counts = list_round_submission_counts(round_.id, db, viewer)
    assert {entry["contributor"]["id"]: entry["count"] for entry in counts}[str(alice.id)] == 1


def test_attribution_status_reports_roster_and_locked_in_game(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(series, submission_limit=5, members=[viewer, alice])
    alice_submission = make_submission(round_, alice, make_track())
    round_.attribution_reveal_delay_seconds = 3600
    db.commit()
    _publish(db, round_, viewer)

    status_before = get_attribution_status(round_.id, db, viewer)
    assert status_before["published"] is True
    assert status_before["revealed"] is False
    assert status_before["game"] is None
    assert status_before["leaderboard"] == []
    assert {entry["contributor"]["id"] for entry in status_before["roster"]} == {
        str(viewer.id),
        str(alice.id),
    }

    submit_attribution_guesses(
        round_.id,
        AttributionGuessesSubmit(
            guesses=[
                AttributionGuessInput(submission_id=alice_submission.id, contributor_id=alice.id)
            ]
        ),
        db,
        viewer,
    )
    db.commit()
    status_after = get_attribution_status(round_.id, db, viewer)
    assert status_after["revealed"] is True
    assert status_after["game"] == {
        "submittedAt": status_after["game"]["submittedAt"],
        "correctCount": 1,
        "totalCount": 1,
    }
    # Playing unlocks the leaderboard for the player - showing only the
    # people who have actually finished guessing, Alice hasn't yet.
    assert [entry["contributor"]["id"] for entry in status_after["leaderboard"]] == [str(viewer.id)]
    assert status_after["leaderboard"][0]["correctCount"] == 1

    # A bystander who hasn't played and is still inside the delay window
    # can't see the leaderboard either - it isn't a way to peek at progress
    # before playing yourself.
    bystander = make_user(name="Bystander")
    db.add(RoundMember(round_id=round_.id, user_id=bystander.id))
    db.commit()
    bystander_status = get_attribution_status(round_.id, db, bystander)
    assert bystander_status["leaderboard"] == []


def test_leaderboard_ranks_by_accuracy_then_by_track_count(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    publisher = make_user(name="Publisher", admin=True)
    sharp = make_user(name="Sharp")
    so_so = make_user(name="SoSo")
    never_played = make_user(name="NeverPlayed")
    series = make_series()
    round_ = make_round(
        series,
        attribution_reveal_delay_seconds=3600,
        submission_limit=5,
        members=[publisher, sharp, so_so, never_played],
    )
    publisher_submission = make_submission(round_, publisher, make_track())
    sharp_submission = make_submission(round_, sharp, make_track())
    soso_submission = make_submission(round_, so_so, make_track())
    db.commit()
    _publish(db, round_, publisher)

    # Sharp guesses on the other two submissions (their own is excluded) and
    # gets both right.
    attribution.submit_guesses(
        db,
        round_,
        sharp,
        {publisher_submission.id: publisher.id, soso_submission.id: so_so.id},
    )
    db.commit()
    # So-so guesses on the other two and gets one of two right.
    attribution.submit_guesses(
        db,
        round_,
        so_so,
        {publisher_submission.id: sharp.id, sharp_submission.id: sharp.id},
    )
    db.commit()

    board = attribution.leaderboard(db, round_.id)
    assert [user.id for user, _correct, _total in board] == [sharp.id, so_so.id]
    assert board[0][1:] == (2, 2)
    assert board[1][1:] == (1, 2)
    assert never_played.id not in [user.id for user, _c, _t in board]


def test_a_round_with_no_delay_configured_has_the_game_disabled_entirely(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
) -> None:
    """`attribution_reveal_delay_seconds=None` (the default) means "no game" -
    identity reveals the instant the round publishes, same as before the
    guessing game existed, and guesses can't be recorded at all."""
    viewer = make_user(name="Viewer", admin=True)
    alice = make_user(name="Alice")
    series = make_series()
    round_ = make_round(series, submission_limit=5, members=[viewer, alice])
    assert round_.attribution_reveal_delay_seconds is None
    alice_submission = make_submission(round_, alice, make_track())
    db.commit()
    _publish(db, round_, viewer)

    assert attribution.is_game_enabled(round_) is False
    assert (
        attribution.is_revealed_for(
            db, round_, attribution.get_publication(db, round_.id), alice.id
        )
        is True
    )

    revealed_view = list_round_submissions(round_.id, db, viewer)
    entry = next(e for e in revealed_view if e["id"] == str(alice_submission.id))
    assert entry["contributor"]["id"] == str(alice.id)

    with pytest.raises(attribution.AttributionError, match="not enabled"):
        attribution.submit_guesses(db, round_, viewer, {alice_submission.id: alice.id})
