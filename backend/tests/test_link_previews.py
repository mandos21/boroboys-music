from __future__ import annotations

import io
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.models import Publication, PublicationItem, PublicationState, RoundStatus
from app.db.session import get_db_session
from app.main import create_app
from app.services import link_previews as previews
from app.services import preview_images as images

NOW = datetime(2026, 10, 28, 16, tzinfo=UTC)


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property", attrs.get("name"))] = attrs.get("content")
        if tag == "script":
            self.scripts.append(attrs)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-31T16:00:00+00:00", "October 31st at 12pm Eastern"),
        ("2026-11-01T04:00:00+00:00", "November 1st at 12am Eastern"),
        ("2026-11-02T17:05:00+00:00", "November 2nd at 12:05pm Eastern"),
        ("2026-11-03T17:00:00+00:00", "November 3rd at 12pm Eastern"),
        ("2026-11-11T17:00:00+00:00", "November 11th at 12pm Eastern"),
        ("2027-01-21T17:00:00+00:00", "January 21st, 2027 at 12pm Eastern"),
    ],
)
def test_friendly_dates_ordinals_and_dst(value, expected):
    assert (
        previews.friendly_date(datetime.fromisoformat(value), "America/New_York", NOW) == expected
    )


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(days=3), "Closes in three days"),
        (timedelta(days=1), "Closes tomorrow"),
        (timedelta(hours=8), "Closes today"),
        (timedelta(hours=2), "Closes in two hours"),
        (timedelta(minutes=1), "Closes in one minute"),
        (timedelta(seconds=30), "Closes in less than a minute"),
    ],
)
def test_relative_deadlines(delta, expected):
    assert previews.relative_deadline("Closes", NOW + delta, "America/New_York", NOW) == expected


def test_calendar_day_count_across_dst():
    start = datetime(2026, 10, 31, 16, tzinfo=UTC)
    end = datetime(2026, 11, 2, 17, tzinfo=UTC)  # 49 hours, two local calendar days
    assert (
        previews.relative_deadline("Closes", end, "America/New_York", start) == "Closes in two days"
    )
    assert "UTC" in previews.friendly_date(end, "Not/AZone", start)


@pytest.fixture
def round_(make_series, make_round):
    result = make_round(
        make_series(),
        title="October 2026",
        submission_limit=3,
        opens_at=NOW - timedelta(days=27),
        closes_at=NOW + timedelta(days=3),
        publish_at=NOW + timedelta(days=4),
        prompt="What were your favorite tracks this month?",
    )
    result.timezone = "America/New_York"
    return result


def test_open_preview_has_no_unpublished_artwork_or_private_data(
    db,
    round_,
    make_user,
    make_track,
    make_submission,
    monkeypatch,
):
    person = make_user(name="PRIVATE PERSON", email="private@example.test")
    track = make_track(name="SECRET SONG", artwork_url="https://i.scdn.co/image/secret")
    make_submission(round_, person, track, note="PRIVATE NOTE")
    monkeypatch.setattr(
        images.httpx, "stream", lambda *a, **kw: pytest.fail("HTML fetched artwork")
    )
    db.flush()
    preview = previews.get_preview(db, str(round_.id), NOW)
    assert preview.headline == "Closes in three days"
    assert preview.detail == "October 31st at 12pm Eastern"
    assert "Share up to 3 tracks" in preview.description
    assert not preview.artwork
    html = previews.render_head(preview, "https://music.example.test")
    assert all(secret not in html for secret in ["PRIVATE", "SECRET", "secret", "private@example"])


def test_timeline_without_scheduler_writes(db, round_):
    db.flush()
    before = previews.get_preview(db, str(round_.id), round_.opens_at - timedelta(days=2))
    assert before.headline == "Opens in two days"
    closing = previews.get_preview(db, str(round_.id), round_.closes_at - timedelta(seconds=12))
    assert closing.max_age == 12
    closed = previews.get_preview(db, str(round_.id), round_.closes_at)
    assert closed.label == "SUBMISSIONS CLOSED"
    assert closed.headline == "Releases tomorrow"
    late = previews.get_preview(db, str(round_.id), round_.publish_at)
    assert late.headline == "The playlist is on its way"
    assert round_.status == RoundStatus.OPEN  # Public GET never reconciles lifecycle state.
    assert closing.revision != closed.revision


@pytest.mark.parametrize(
    "status",
    [RoundStatus.DRAFT, RoundStatus.CANCELLED, RoundStatus.FAILED, RoundStatus.UNPUBLISHING],
)
def test_nonpublic_states_fall_back(db, round_, status):
    round_.status = status
    db.flush()
    assert previews.get_preview(db, str(round_.id), NOW) == previews.Preview()


def test_missing_and_invalid_rounds_are_indistinguishable(db):
    for identifier in [str(uuid.uuid4()), "bad-id", "default"]:
        assert previews.get_preview(db, identifier, NOW) == previews.Preview()


@pytest.fixture
def published(db, round_, make_user, make_spotify_account, make_track):
    round_.status = RoundStatus.PUBLISHED
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=make_spotify_account(make_user()).id,
        state=PublicationState.PUBLISHED,
        published_at=NOW - timedelta(days=1),
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(publication)
    db.flush()
    for position, url in enumerate(["one", "one", "two", "three", "four", "five"]):
        track = make_track(artwork_url=f"https://i.scdn.co/image/{url}")
        db.add(
            PublicationItem(
                publication_id=publication.id,
                track_id=track.id,
                position=position,
                note_snapshot="PRIVATE NOTE",
            )
        )
    db.flush()
    return publication


def test_published_snapshot_and_revocation(db, round_, published):
    # The retained reversal timestamp is historical after a successful republish.
    published.unpublished_at = NOW - timedelta(days=2)
    db.flush()
    preview = previews.get_preview(db, str(round_.id), NOW)
    assert preview.label == "RELEASE RECAP"
    assert "6 tracks" in preview.description
    assert preview.artwork == tuple(
        f"https://i.scdn.co/image/{name}" for name in ["one", "two", "three", "four"]
    )
    assert "PRIVATE" not in previews.render_head(preview, "https://music.example.test")
    published.retirement_requested = True
    db.flush()
    assert previews.get_preview(db, str(round_.id), NOW) == previews.Preview()


def test_metadata_escapes_all_fields_and_uses_configured_origin():
    identifier = str(uuid.uuid4())
    preview = previews.Preview(
        title='A "round" </title><script>alert(1)</script>',
        description='Listen & share "music" <img src=x onerror=alert(1)>',
        round_id=identifier,
    )
    html = previews.render_head(preview, "https://music.example.test/")
    head = Head(html)
    assert not head.scripts
    assert head.meta["og:title"] == f"{preview.title} · BoroCrew Music"
    assert head.meta["og:description"] == preview.description
    assert head.meta["og:url"] == f"https://music.example.test/rounds/{identifier}"
    assert head.meta["og:image"].startswith(
        f"https://music.example.test/api/v1/previews/{identifier}/image.png?v="
    )
    assert head.meta["og:image:width"] == "1200"


def test_anonymous_routes_and_image_revalidation(db, round_, monkeypatch):
    db.flush()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    # The fixed historical round still has a public preview; request identity
    # must not change it. Do not run app lifespan/background tasks in this test.
    with TestClient(app) as client:
        path = f"/api/v1/previews/{round_.id}"
        response = client.get(path + "/head", headers={"Host": "attacker.example"})
        assert response.status_code == 200
        assert "attacker.example" not in response.text
        assert 'name="twitter:card"' in response.text
        assert client.get(f"/api/v1/rounds/{round_.id}").status_code == 401
        image = client.get(path + "/image.png?v=old")
        assert image.status_code == 200
        assert Image.open(io.BytesIO(image.content)).size == (1200, 630)
        etag = image.headers["etag"]
        assert client.get(path + "/image.png", headers={"If-None-Match": etag}).status_code == 304
        round_.status = RoundStatus.DRAFT
        db.flush()
        revoked = client.get(path + "/image.png?v=old", headers={"If-None-Match": etag})
        assert revoked.status_code == 200
        assert revoked.headers["etag"] != etag
        assert round_.title not in client.get(path + "/head").text


@pytest.mark.parametrize(
    "url",
    [
        "http://i.scdn.co/image/a",
        "https://evil.test/image/a",
        "https://i.scdn.co.evil.test/image/a",
        "https://i.scdn.co@127.0.0.1/image/a",
        "https://i.scdn.co:444/image/a",
        "https://[invalid",
        "file:///etc/passwd",
        "https://i.scdn.co/other/a",
    ],
)
def test_artwork_fetch_rejects_unapproved_urls(monkeypatch, url):
    monkeypatch.setattr(images.httpx, "stream", lambda *a, **kw: pytest.fail("Unexpected network"))
    assert images.artwork_bytes(url, 0) is None


def test_corrupt_and_missing_artwork_still_render(monkeypatch):
    monkeypatch.setattr(images, "artwork_bytes", lambda *a: b"invalid image")
    preview = previews.Preview(title="A long title " * 20, artwork=("https://i.scdn.co/image/bad",))
    image = Image.open(io.BytesIO(images.render_image(preview)))
    assert image.size == (1200, 630)
    assert image.format == "PNG"
    assert images.artwork_image(None, 100) is None
    face = images.font(62)
    wrapped = images.lines("unbroken" * 100, face, 660, 3)
    assert len(wrapped) == 3 and wrapped[-1].endswith("…")
    assert all(face.getlength(line) <= 660 for line in wrapped)


@pytest.mark.parametrize("status,size", [(302, 10), (200, 4 * 1024 * 1024 + 1)])
def test_artwork_redirects_and_oversized_responses_are_rejected(monkeypatch, status, size):
    images.artwork_bytes.cache_clear()

    @contextmanager
    def response(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        with closing(httpx.Response(status, content=b"x" * size)) as result:
            yield result

    monkeypatch.setattr(images.httpx, "stream", response)
    assert images.artwork_bytes("https://i.scdn.co/image/size-test", 1) is None


def test_artwork_timeout_uses_fallback(monkeypatch):
    images.artwork_bytes.cache_clear()

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("test")

    monkeypatch.setattr(images.httpx, "stream", timeout)
    assert images.artwork_bytes("https://i.scdn.co/image/timeout-test", 1) is None


def test_collage_paints_downloaded_covers(monkeypatch):
    colors = [(220, 30, 50), (30, 100, 220), (200, 150, 20), (160, 40, 200)]

    def cover(url, bucket):
        output = io.BytesIO()
        Image.new("RGB", (240, 120), colors[int(url)]).save(output, format="PNG")
        return output.getvalue()

    monkeypatch.setattr(images, "artwork_bytes", cover)
    preview = previews.Preview(title="Collage", artwork=tuple(str(i) for i in range(4)))
    result = Image.open(io.BytesIO(images.render_image(preview)))
    for index, color in enumerate(colors):
        assert result.getpixel((866 + (index % 2) * 178, 236 + (index // 2) * 178)) == color
