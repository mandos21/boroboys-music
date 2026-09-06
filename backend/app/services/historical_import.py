"""Validated, local-only import of archived Spotify playlist exports.

The importer intentionally does not talk to Spotify.  The source CSVs already
contain the stable playlist and track identifiers needed to reconstruct a
published snapshot exactly, including repeated tracks and its playlist order.
"""

from __future__ import annotations

import csv
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    ExternalAccount,
    ExternalProvider,
    Publication,
    PublicationItem,
    PublicationState,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesAdmin,
    Submission,
    SubmissionStatus,
    Track,
    User,
)

_REQUIRED_COLUMNS = frozenset(
    {"title", "artist", "album", "spotify_id", "submitted_by_email", "submitted_at"}
)
_SOURCE_TIMESTAMP_FORMAT = "%m/%d/%Y %H:%M:%S"


class HistoricalImportError(ValueError):
    """The source bundle or requested import target is unsafe to import."""


@dataclass(frozen=True)
class HistoricalSubmissionSource:
    spotify_track_id: str
    title: str
    artist: str
    album: str | None
    contributor_emails: tuple[str, ...]
    submitted_at: tuple[datetime, ...]
    position: int


@dataclass(frozen=True)
class HistoricalPlaylistSource:
    spotify_playlist_id: str
    submissions: tuple[HistoricalSubmissionSource, ...]
    submission_month: datetime
    source_path: Path


@dataclass(frozen=True)
class HistoricalRoundPlan:
    playlist: HistoricalPlaylistSource
    title: str
    kind: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime


@dataclass(frozen=True)
class HistoricalImportPlan:
    rounds: tuple[HistoricalRoundPlan, ...]
    identity_map: dict[str, str]

    @property
    def playlist_count(self) -> int:
        return len(self.rounds)

    @property
    def playlist_item_count(self) -> int:
        return sum(len(round_.playlist.submissions) for round_ in self.rounds)

    @property
    def submission_count(self) -> int:
        return sum(
            len(item.contributor_emails)
            for round_ in self.rounds
            for item in round_.playlist.submissions
        )

    @property
    def contributor_count(self) -> int:
        return len(
            {
                email
                for round_ in self.rounds
                for item in round_.playlist.submissions
                for email in item.contributor_emails
            }
        )

    @property
    def kind_counts(self) -> Counter[str]:
        return Counter(round_.kind for round_ in self.rounds)


@dataclass(frozen=True)
class HistoricalImportResult:
    round_count: int
    publication_item_count: int
    submission_count: int
    contributor_count: int


def load_historical_import_plan(
    playlist_directory: Path,
    identity_map_path: Path,
    timezone: str,
) -> HistoricalImportPlan:
    """Read and validate a private CSV bundle before any database writes occur."""
    try:
        zone = ZoneInfo(timezone)
    except Exception as error:  # pragma: no cover - protected by the Series model/API
        raise HistoricalImportError(f"series timezone is invalid: {timezone}") from error
    identity_map = _load_identity_map(identity_map_path)
    playlists = _load_playlists(playlist_directory)
    _validate_identity_coverage(playlists, identity_map)
    return HistoricalImportPlan(
        rounds=tuple(_plan_rounds(playlists, zone)),
        identity_map=identity_map,
    )


def validate_historical_import_target(
    db: Session,
    series_slug: str,
    publisher_account_id: uuid.UUID,
    plan: HistoricalImportPlan,
) -> Series:
    """Check the immutable import target and publisher without changing state."""
    series = db.scalar(select(Series).where(Series.slug == series_slug).with_for_update())
    if series is None:
        raise HistoricalImportError("series was not found")
    publisher = db.get(ExternalAccount, publisher_account_id)
    if (
        publisher is None
        or publisher.provider is not ExternalProvider.SPOTIFY
        or not publisher.is_active
    ):
        raise HistoricalImportError("an active Spotify publisher account is required")
    is_series_admin = db.scalar(
        select(SeriesAdmin.id).where(
            SeriesAdmin.series_id == series.id,
            SeriesAdmin.user_id == publisher.user_id,
        )
    )
    if is_series_admin is None:
        raise HistoricalImportError("the Spotify publisher must belong to a series administrator")
    playlist_ids = [round_.playlist.spotify_playlist_id for round_ in plan.rounds]
    existing = list(
        db.scalars(select(Publication.spotify_playlist_id).where(Publication.spotify_playlist_id.in_(playlist_ids)))
    )
    if existing:
        raise HistoricalImportError(
            f"{len(existing)} source playlist(s) have already been imported or published"
        )
    return series


def import_historical_playlist_bundle(
    db: Session,
    series_slug: str,
    publisher_account_id: uuid.UUID,
    oidc_issuer: str,
    plan: HistoricalImportPlan,
) -> HistoricalImportResult:
    """Materialize a fully validated plan in the caller's transaction.

    Callers own the commit so a failure rolls back the entire history bundle.
    """
    series = validate_historical_import_target(db, series_slug, publisher_account_id, plan)
    publisher = db.get(ExternalAccount, publisher_account_id)
    assert publisher is not None  # validated above
    users_by_email = _load_or_create_users(
        db,
        plan.identity_map,
        {
            email
            for round_plan in plan.rounds
            for item in round_plan.playlist.submissions
            for email in item.contributor_emails
        },
        oidc_issuer.rstrip("/"),
    )
    next_sequence = (
        db.scalar(select(func.max(Round.published_sequence)).where(Round.series_id == series.id))
        or 0
    ) + 1

    for sequence, round_plan in enumerate(plan.rounds, start=next_sequence):
        _import_round(db, series, publisher, users_by_email, round_plan, sequence)
    return HistoricalImportResult(
        round_count=plan.playlist_count,
        publication_item_count=plan.playlist_item_count,
        submission_count=plan.submission_count,
        contributor_count=plan.contributor_count,
    )


def _load_identity_map(identity_map_path: Path) -> dict[str, str]:
    if not identity_map_path.is_file():
        raise HistoricalImportError("identity map file was not found")
    identities: dict[str, str] = {}
    for line_number, line in enumerate(
        identity_map_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        email, separator, subject = line.partition("\t")
        email, subject = email.strip().lower(), subject.strip()
        if not separator or not email or not subject:
            raise HistoricalImportError(
                f"identity map line {line_number} must contain an email and OIDC subject separated by a tab"
            )
        existing_subject = identities.get(email)
        if existing_subject is not None and existing_subject != subject:
            raise HistoricalImportError(f"identity map has conflicting subjects on line {line_number}")
        identities[email] = subject
    if not identities:
        raise HistoricalImportError("identity map is empty")
    return identities


def _load_playlists(playlist_directory: Path) -> list[HistoricalPlaylistSource]:
    if not playlist_directory.is_dir():
        raise HistoricalImportError("playlist directory was not found")
    paths = sorted(playlist_directory.glob("*.csv"))
    if not paths:
        raise HistoricalImportError("playlist directory contains no CSV files")
    playlists = [_load_playlist(path) for path in paths]
    playlist_ids = [item.spotify_playlist_id for item in playlists]
    if len(playlist_ids) != len(set(playlist_ids)):
        raise HistoricalImportError("playlist directory contains duplicate playlist identifiers")
    return playlists


def _load_playlist(path: Path) -> HistoricalPlaylistSource:
    playlist_id = path.stem.strip()
    if not playlist_id or len(playlist_id) > 128:
        raise HistoricalImportError(f"invalid playlist identifier in {path.name}")
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = set(reader.fieldnames or ())
        if not _REQUIRED_COLUMNS.issubset(fieldnames):
            raise HistoricalImportError(f"{path.name} does not have the expected CSV columns")
        entries = tuple(
            _load_submission_source(path, row, position)
            for position, row in enumerate(reader, start=1)
        )
    if not entries:
        raise HistoricalImportError(f"{path.name} contains no playlist items")
    months = {
        datetime(value.year, value.month, 1)
        for entry in entries
        for value in entry.submitted_at
    }
    if len(months) != 1:
        raise HistoricalImportError(f"{path.name} has submissions from more than one month")
    return HistoricalPlaylistSource(
        spotify_playlist_id=playlist_id,
        submissions=entries,
        submission_month=months.pop(),
        source_path=path,
    )


def _load_submission_source(
    path: Path, row: dict[str, str | None], position: int
) -> HistoricalSubmissionSource:
    title = _required_field(path, position, row, "title", 500)
    artist = _required_field(path, position, row, "artist", 500)
    spotify_track_id = _required_field(path, position, row, "spotify_id", 64)
    album = (row.get("album") or "").strip() or None
    if album is not None and len(album) > 500:
        raise HistoricalImportError(f"{path.name} row {position} has an album value that is too long")
    emails = tuple(
        value.strip().lower()
        for value in (row.get("submitted_by_email") or "").split(";")
        if value.strip()
    )
    timestamps = tuple(
        _parse_timestamp(path, position, value)
        for value in (row.get("submitted_at") or "").split(";")
        if value.strip()
    )
    if not emails or not timestamps or len(emails) != len(timestamps):
        raise HistoricalImportError(
            f"{path.name} row {position} must have one submission timestamp per contributor"
        )
    return HistoricalSubmissionSource(
        spotify_track_id=spotify_track_id,
        title=title,
        artist=artist,
        album=album,
        contributor_emails=emails,
        submitted_at=timestamps,
        position=position,
    )


def _required_field(
    path: Path, position: int, row: dict[str, str | None], name: str, limit: int
) -> str:
    value = (row.get(name) or "").strip()
    if not value or len(value) > limit:
        raise HistoricalImportError(f"{path.name} row {position} has an invalid {name} value")
    return value


def _parse_timestamp(path: Path, position: int, value: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), _SOURCE_TIMESTAMP_FORMAT)
    except ValueError as error:
        raise HistoricalImportError(
            f"{path.name} row {position} has an invalid submitted_at value"
        ) from error


def _validate_identity_coverage(
    playlists: list[HistoricalPlaylistSource], identity_map: dict[str, str]
) -> None:
    source_emails = {
        email
        for playlist in playlists
        for item in playlist.submissions
        for email in item.contributor_emails
    }
    unmapped = sorted(source_emails - identity_map.keys())
    if unmapped:
        joined = ", ".join(unmapped)
        raise HistoricalImportError(
            f"identity map is missing {len(unmapped)} historical contributor email(s): {joined}"
        )


def _plan_rounds(
    playlists: list[HistoricalPlaylistSource], zone: ZoneInfo
) -> list[HistoricalRoundPlan]:
    by_month: dict[tuple[int, int], list[HistoricalPlaylistSource]] = defaultdict(list)
    for playlist in playlists:
        by_month[(playlist.submission_month.year, playlist.submission_month.month)].append(playlist)
    plans: list[HistoricalRoundPlan] = []
    for (_, month), monthly_playlists in sorted(by_month.items()):
        year_end_ids = _year_end_playlist_ids(monthly_playlists, month)
        for playlist in monthly_playlists:
            kind = "year_end" if playlist.spotify_playlist_id in year_end_ids else "monthly"
            plans.append(_round_plan(playlist, kind, zone))
    return sorted(
        plans,
        key=lambda plan: (
            plan.publish_at,
            0 if plan.kind == "monthly" else 1,
            plan.playlist.spotify_playlist_id,
        ),
    )


def _year_end_playlist_ids(
    playlists: list[HistoricalPlaylistSource], month: int
) -> set[str]:
    if month != 1:
        return set()
    if len(playlists) == 1:
        counts = _submission_counts(playlists[0])
        return {playlists[0].spotify_playlist_id} if min(counts.values()) >= 5 else set()
    largest = max(len(playlist.submissions) for playlist in playlists)
    candidates = [playlist for playlist in playlists if len(playlist.submissions) == largest]
    if len(candidates) != 1:
        raise HistoricalImportError("cannot infer the year-end playlist from equally sized January lists")
    return {candidates[0].spotify_playlist_id}


def _round_plan(
    playlist: HistoricalPlaylistSource, kind: str, zone: ZoneInfo
) -> HistoricalRoundPlan:
    source_month = playlist.submission_month.replace(tzinfo=zone)
    next_month = _next_month(source_month)
    if kind == "year_end":
        title = f"{source_month.year - 1} End of Year"
    else:
        title = source_month.strftime("%B %Y")
    return HistoricalRoundPlan(
        playlist=playlist,
        title=title,
        kind=kind,
        opens_at=source_month,
        closes_at=next_month,
        publish_at=next_month,
    )


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _submission_counts(playlist: HistoricalPlaylistSource) -> Counter[str]:
    return Counter(
        email for item in playlist.submissions for email in item.contributor_emails
    )


def _load_or_create_users(
    db: Session,
    identity_map: dict[str, str],
    source_emails: set[str],
    issuer: str,
) -> dict[str, User]:
    users_by_subject: dict[str, User] = {}
    for email in source_emails:
        subject = identity_map[email]
        user = users_by_subject.get(subject)
        if user is None:
            user = db.scalar(
                select(User).where(User.oidc_issuer == issuer, User.oidc_subject == subject)
            )
            if user is None:
                user = User(oidc_issuer=issuer, oidc_subject=subject, email=email)
                db.add(user)
                db.flush()
            users_by_subject[subject] = user
    return {email: users_by_subject[identity_map[email]] for email in source_emails}


def _import_round(
    db: Session,
    series: Series,
    publisher: ExternalAccount,
    users_by_email: dict[str, User],
    plan: HistoricalRoundPlan,
    sequence: int,
) -> None:
    round_ = Round(
        series_id=series.id,
        title=plan.title,
        timezone=series.timezone,
        submission_limit=max(_submission_counts(plan.playlist).values()),
        opens_at=plan.opens_at,
        closes_at=plan.closes_at,
        publish_at=plan.publish_at,
        status=RoundStatus.PUBLISHED,
        publisher_account_id=publisher.id,
        policy_snapshot=[],
        published_sequence=sequence,
        created_at=plan.opens_at,
        updated_at=plan.publish_at,
    )
    db.add(round_)
    db.flush()
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=publisher.id,
        state=PublicationState.PUBLISHED,
        spotify_playlist_id=plan.playlist.spotify_playlist_id,
        idempotency_key=str(uuid.uuid4()),
        is_imported=True,
        published_at=plan.publish_at,
        created_at=plan.publish_at,
        updated_at=plan.publish_at,
    )
    db.add(publication)
    db.flush()

    submissions_by_position: dict[int, Submission] = {}
    memberships: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    tracks: dict[str, Track] = {}
    for source in plan.playlist.submissions:
        track = _find_or_create_track(db, tracks, source, series.timezone)
        for email, submitted_at in zip(source.contributor_emails, source.submitted_at, strict=True):
            contributor = users_by_email[email]
            timestamp = submitted_at.replace(tzinfo=ZoneInfo(series.timezone))
            submission = Submission(
                round_id=round_.id,
                contributor_id=contributor.id,
                track_id=track.id,
                status=SubmissionStatus.ACCEPTED,
                submitted_at=timestamp,
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(submission)
            db.flush()
            submissions_by_position.setdefault(source.position, submission)
            memberships[contributor.id].append(timestamp)
    for contributor_id, timestamps in memberships.items():
        db.add(
            RoundMember(
                round_id=round_.id,
                user_id=contributor_id,
                submission_limit_override=len(timestamps),
                joined_at=min(timestamps),
                created_at=min(timestamps),
                updated_at=plan.publish_at,
            )
        )
    for source in plan.playlist.submissions:
        submission = submissions_by_position[source.position]
        db.add(
            PublicationItem(
                publication_id=publication.id,
                submission_id=submission.id,
                track_id=submission.track_id,
                contributor_id=submission.contributor_id,
                position=source.position,
                published_at=plan.publish_at,
                created_at=plan.publish_at,
                updated_at=plan.publish_at,
            )
        )
    db.add(
        AuditEvent(
            actor_id=publisher.user_id,
            action="publication.imported",
            target_type="publication",
            target_id=publication.id,
            details={
                "roundId": str(round_.id),
                "playlistId": plan.playlist.spotify_playlist_id,
                "source": "historical_csv_bundle",
                "kind": plan.kind,
            },
        )
    )


def _find_or_create_track(
    db: Session,
    tracks: dict[str, Track],
    source: HistoricalSubmissionSource,
    timezone: str,
) -> Track:
    track = tracks.get(source.spotify_track_id)
    if track is None:
        track = db.scalar(select(Track).where(Track.spotify_track_id == source.spotify_track_id))
    if track is None:
        first_submitted_at = source.submitted_at[0].replace(tzinfo=ZoneInfo(timezone))
        track = Track(
            spotify_track_id=source.spotify_track_id,
            name=source.title,
            artist=source.artist,
            album=source.album,
            spotify_uri=f"spotify:track:{source.spotify_track_id}",
            provider_metadata={"historicalImport": True},
            created_at=first_submitted_at,
            updated_at=first_submitted_at,
        )
        db.add(track)
        db.flush()
    tracks[source.spotify_track_id] = track
    return track
