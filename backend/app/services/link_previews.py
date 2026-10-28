"""The deliberately small, anonymous summary exposed by a shared round URL.

Never serialize a RoundDetailResponse here: it includes member-specific/private
information. These queries explicitly select only the public preview fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Publication, PublicationItem, PublicationState, Round, RoundStatus, Track

BRAND = "BoroCrew Music"
VISIBLE_STATES = (
    RoundStatus.SCHEDULED,
    RoundStatus.OPEN,
    RoundStatus.CLOSED,
    RoundStatus.PUBLISHING,
    RoundStatus.PUBLISHED,
)
ZONE_NAMES = {
    "America/New_York": "Eastern",
    "America/Detroit": "Eastern",
    "America/Toronto": "Eastern",
    "America/Chicago": "Central",
    "America/Winnipeg": "Central",
    "America/Denver": "Mountain",
    "America/Phoenix": "Arizona time",
    "America/Los_Angeles": "Pacific",
    "America/Vancouver": "Pacific",
    "America/Anchorage": "Alaska time",
    "Pacific/Honolulu": "Hawaii time",
    "Europe/London": "UK time",
    "UTC": "UTC",
    "Etc/UTC": "UTC",
}
NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def round_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("UTC")


def friendly_date(value: datetime, timezone: str, now: datetime) -> str:
    zone = round_zone(timezone)
    local = value.astimezone(zone)
    suffix = (
        "th"
        if 10 <= local.day % 100 <= 20
        else {1: "st", 2: "nd", 3: "rd"}.get(local.day % 10, "th")
    )
    year = f", {local.year}" if local.year != now.astimezone(zone).year else ""
    minutes = f":{local.minute:02d}" if local.minute else ""
    clock = f"{local.hour % 12 or 12}{minutes}{'am' if local.hour < 12 else 'pm'}"
    zone_name = ZONE_NAMES.get(zone.key, local.tzname() or zone.key)
    return f"{local.strftime('%B')} {local.day}{suffix}{year} at {clock} {zone_name}"


def relative_deadline(verb: str, value: datetime, timezone: str, now: datetime) -> str:
    seconds = (value - now).total_seconds()
    if seconds <= 0:
        return f"{verb} soon"
    if seconds < 60:
        return f"{verb} in less than a minute"
    if seconds < 3600:
        count, unit = math.ceil(seconds / 60), "minute"
    elif seconds < 6 * 3600:
        count, unit = math.ceil(seconds / 3600), "hour"
    else:
        zone = round_zone(timezone)
        days = (value.astimezone(zone).date() - now.astimezone(zone).date()).days
        if days == 0:
            return f"{verb} today"
        if days == 1:
            return f"{verb} tomorrow"
        count, unit = days, "day"
    number = NUMBERS[count] if count < len(NUMBERS) else str(count)
    return f"{verb} in {number} {unit}{'' if count == 1 else 's'}"


@dataclass(frozen=True)
class Preview:
    title: str = BRAND
    headline: str = "What are you listening to?"
    detail: str = "Favorite tracks. Shared with friends."
    description: str = "Share your favorite tracks with friends and discover your next favorite."
    prompt: str = "A little music for the group chat."
    label: str = "MUSIC FOR THE GROUP CHAT"
    round_id: str | None = None
    artwork: tuple[str, ...] = ()
    max_age: int = 60

    @property
    def revision(self) -> str:
        # Cache identity reflects visible content, including relative wording.
        content = asdict(self)
        content.pop("max_age")
        content["format_version"] = 1
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:20]


def get_preview(db: Session, round_id: str, now: datetime | None = None) -> Preview:
    now = now or datetime.now(UTC)
    try:
        identifier = uuid.UUID(round_id)
    except ValueError:
        return Preview()
    row = db.execute(
        select(
            Round.id,
            Round.title,
            Round.prompt,
            Round.status,
            Round.timezone,
            Round.opens_at,
            Round.closes_at,
            Round.publish_at,
            Round.submission_limit,
        ).where(Round.id == identifier, Round.status.in_(VISIBLE_STATES))
    ).one_or_none()
    if row is None:
        return Preview()

    title = compact(row.title, 200)
    prompt = compact(row.prompt or "What have you been listening to?", 240)
    artwork: tuple[str, ...] = ()
    if row.status == RoundStatus.PUBLISHED:
        publication = db.execute(
            select(Publication.id, Publication.published_at).where(
                Publication.round_id == identifier,
                Publication.state == PublicationState.PUBLISHED,
                Publication.retirement_requested.is_(False),
            )
        ).one_or_none()
        if publication is None or publication.published_at is None:
            return Preview()
        count = (
            db.scalar(
                select(func.count())
                .select_from(PublicationItem)
                .where(PublicationItem.publication_id == publication.id)
            )
            or 0
        )
        # The publication snapshot, never live/unpublished submissions.
        artwork = tuple(
            db.scalars(
                select(Track.artwork_url)
                .join(PublicationItem, PublicationItem.track_id == Track.id)
                .where(
                    PublicationItem.publication_id == publication.id, Track.artwork_url.is_not(None)
                )
                .group_by(Track.artwork_url)
                .order_by(func.min(PublicationItem.position))
                .limit(4)
            )
        )
        headline = "Your playlist is ready"
        detail = (
            f"{count} {'track' if count == 1 else 'tracks'} · "
            f"Released {friendly_date(publication.published_at, row.timezone, now)}"
        )
        description = f"{headline}. {detail}."
        label = "RELEASE RECAP"
        deadline = None
    else:
        if now < row.opens_at:
            label, verb, deadline = "UP NEXT", "Opens", row.opens_at
        elif now < row.closes_at and row.status in (RoundStatus.SCHEDULED, RoundStatus.OPEN):
            label, verb, deadline = "OPEN FOR PICKS", "Closes", row.closes_at
        else:
            label, verb, deadline = "SUBMISSIONS CLOSED", "Releases", row.publish_at
        headline = relative_deadline(verb, deadline, row.timezone, now)
        detail = friendly_date(deadline, row.timezone, now)
        if deadline <= now:
            # A delayed/failed publisher must never promise a release in the past.
            headline, detail = (
                "The playlist is on its way",
                "Submissions are closed. Check back soon.",
            )
        allowance = (
            f" Share up to {row.submission_limit} "
            f"{'track' if row.submission_limit == 1 else 'tracks'}."
            if label == "OPEN FOR PICKS" and row.submission_limit > 0
            else ""
        )
        description = f"{headline} · {detail}. {prompt}{allowance}"
    max_age = 60
    if deadline is not None and deadline > now:
        max_age = max(0, min(60, int((deadline - now).total_seconds())))
    return Preview(
        title=title,
        headline=headline,
        detail=detail,
        description=description,
        prompt=prompt,
        label=label,
        round_id=str(identifier),
        artwork=artwork,
        max_age=max_age,
    )


def render_head(preview: Preview, base_url: str) -> str:
    base = base_url.rstrip("/")
    canonical = f"{base}/rounds/{preview.round_id}" if preview.round_id else f"{base}/"
    image = f"{base}/api/v1/previews/{preview.round_id or 'default'}/image.png?v={preview.revision}"
    title = f"{preview.title} · {BRAND}" if preview.round_id else BRAND
    properties = {
        "og:type": "website",
        "og:site_name": BRAND,
        "og:title": title,
        "og:description": preview.description,
        "og:url": canonical,
        "og:image": image,
        "og:image:type": "image/png",
        "og:image:width": "1200",
        "og:image:height": "630",
        "og:image:alt": f"{preview.title}. {preview.headline}. {preview.detail}",
    }
    names = {
        "description": preview.description,
        "twitter:card": "summary_large_image",
        "twitter:title": title,
        "twitter:description": preview.description,
        "twitter:image": image,
        "twitter:image:alt": properties["og:image:alt"],
    }
    return "\n".join(
        [
            f"<title>{escape(title)}</title>",
            f'<link rel="canonical" href="{escape(canonical, quote=True)}" />',
            *(
                f'<meta property="{key}" content="{escape(value, quote=True)}" />'
                for key, value in properties.items()
            ),
            *(
                f'<meta name="{key}" content="{escape(value, quote=True)}" />'
                for key, value in names.items()
            ),
        ]
    )
