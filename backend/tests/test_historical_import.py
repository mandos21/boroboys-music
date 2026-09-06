"""PostgreSQL-backed coverage for private historical playlist imports."""

from __future__ import annotations

import csv
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    Publication,
    PublicationItem,
    Round,
    RoundMember,
    Series,
    SeriesAdmin,
    Submission,
    User,
)
from app.db.session import get_session_factory
from app.services.historical_import import (
    HistoricalImportError,
    import_historical_playlist_bundle,
    load_historical_import_plan,
)


def test_import_plan_infers_monthly_and_year_end_rounds_and_keeps_repeats(
    tmp_path: Path,
) -> None:
    playlist_directory = tmp_path / "playlists"
    playlist_directory.mkdir()
    _write_playlist(
        playlist_directory / "january-monthly.csv",
        [
            _row("monthly-one", "alpha@example.test", "1/4/2023 10:00:00"),
            _row("monthly-one", "alpha@example.test", "1/5/2023 10:00:00"),
            _row("monthly-three", "alpha@example.test", "1/6/2023 10:00:00"),
        ],
    )
    _write_playlist(
        playlist_directory / "year-end.csv",
        [
            _row(f"year-end-{index}", "alpha@example.test", f"1/{index}/2023 10:00:00")
            for index in range(1, 6)
        ],
    )
    identity_map = _write_identity_map(tmp_path, {"alpha@example.test": "subject-alpha"})

    plan = load_historical_import_plan(playlist_directory, identity_map, "America/New_York")

    assert plan.playlist_count == 2
    assert plan.playlist_item_count == 8
    assert plan.submission_count == 8
    assert plan.kind_counts == {"monthly": 1, "year_end": 1}
    assert [round_.title for round_ in plan.rounds] == ["January 2023", "2022 End of Year"]
    assert all(round_.opens_at.tzinfo is not None for round_ in plan.rounds)
    assert plan.rounds[0].closes_at == datetime(2023, 2, 1, tzinfo=plan.rounds[0].opens_at.tzinfo)


def test_import_plan_refuses_an_unmapped_historical_contributor(tmp_path: Path) -> None:
    playlist_directory = tmp_path / "playlists"
    playlist_directory.mkdir()
    _write_playlist(
        playlist_directory / "march.csv",
        [_row("track-one", "unmapped@example.test", "3/2/2023 10:00:00")],
    )
    identity_map = _write_identity_map(tmp_path, {"other@example.test": "subject-other"})

    with pytest.raises(HistoricalImportError, match="unmapped@example.test"):
        load_historical_import_plan(playlist_directory, identity_map, "UTC")


def test_import_materializes_a_published_snapshot_with_attributed_submissions(
    tmp_path: Path,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    playlist_directory = tmp_path / "playlists"
    playlist_directory.mkdir()
    _write_playlist(
        playlist_directory / f"march-playlist-{suffix}.csv",
        [
            _row("repeat-track", "alpha@example.test", "3/2/2023 10:00:00"),
            _row("repeat-track", "alpha@example.test", "3/4/2023 10:00:00"),
            _row("other-track", "beta@example.test", "3/8/2023 10:00:00"),
            _row(
                "shared-track",
                "alpha@example.test; beta@example.test",
                "3/9/2023 10:00:00; 3/10/2023 10:00:00",
            ),
        ],
    )
    identity_map = _write_identity_map(
        tmp_path,
        {
            "alpha@example.test": "subject-alpha",
            "beta@example.test": "subject-beta",
            "unused@example.test": "subject-unused",
        },
    )
    plan = load_historical_import_plan(playlist_directory, identity_map, "UTC")
    with get_session_factory()() as db:
        administrator = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"administrator-{suffix}",
        )
        series = Series(
            name=f"Historical import {suffix}",
            slug=f"historical-import-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((administrator, series))
        db.flush()
        publisher = ExternalAccount(
            user_id=administrator.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"publisher-{suffix}",
        )
        db.add_all((publisher, SeriesAdmin(series_id=series.id, user_id=administrator.id)))
        db.commit()

        result = import_historical_playlist_bundle(
            db,
            series.slug,
            publisher.id,
            "https://issuer.test",
            plan,
        )
        db.commit()

        imported_round = db.scalar(select(Round).where(Round.series_id == series.id))
        assert imported_round is not None
        assert imported_round.title == "March 2023"
        assert imported_round.published_sequence == 1
        assert imported_round.opens_at == datetime(2023, 3, 1, tzinfo=UTC)
        assert imported_round.submission_limit == 3
        submissions = list(
            db.scalars(
                select(Submission).where(Submission.round_id == imported_round.id).order_by(
                    Submission.submitted_at
                )
            )
        )
        assert len(submissions) == 5
        assert (
            db.scalar(
                select(User).where(
                    User.oidc_issuer == "https://issuer.test",
                    User.oidc_subject == "subject-unused",
                )
            )
            is None
        )
        members = list(db.scalars(select(RoundMember).where(RoundMember.round_id == imported_round.id)))
        assert sorted(member.submission_limit_override for member in members) == [2, 3]
        publication = db.scalar(select(Publication).where(Publication.round_id == imported_round.id))
        assert publication is not None
        assert publication.is_imported is True
        items = list(
            db.scalars(
                select(PublicationItem)
                .where(PublicationItem.publication_id == publication.id)
                .order_by(PublicationItem.position)
            )
        )
        assert [item.position for item in items] == [1, 2, 3, 4]
        assert items[0].track_id == items[1].track_id
        assert result.submission_count == 5

        with pytest.raises(HistoricalImportError, match="already been imported"):
            import_historical_playlist_bundle(
                db,
                series.slug,
                publisher.id,
                "https://issuer.test",
                plan,
            )
        db.rollback()


def _row(spotify_id: str, email: str, submitted_at: str) -> dict[str, str]:
    return {
        "title": f"Title {spotify_id}",
        "artist": "The Importers",
        "album": "Archive",
        "spotify_id": spotify_id,
        "submitted_by_email": email,
        "submitted_at": submitted_at,
    }


def _write_playlist(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_identity_map(tmp_path: Path, identities: dict[str, str]) -> Path:
    path = tmp_path / "identity-map.tsv"
    path.write_text(
        "".join(f"{email}\t{subject}\n" for email, subject in identities.items()), encoding="utf-8"
    )
    return path
