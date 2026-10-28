"""Bounded PNG card rendering. Remote artwork is fetched only for image requests."""

from __future__ import annotations

import io
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from app.services.link_previews import BRAND, Preview

FONT_PATH = Path(__file__).resolve().parents[1] / "assets/fonts/Inter.ttf"
ARTWORK_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="preview-artwork")
BACKGROUND = "#0e1713"
SURFACE = "#182a20"
TEXT = "#eff8f1"
MUTED = "#abc2b1"
ACCENT = "#81e6a6"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    result = ImageFont.truetype(str(FONT_PATH), size)
    result.set_variation_by_axes([32, 650 if bold else 400])
    return result


def lines(text: str, face: ImageFont.FreeTypeFont, width: int, limit: int) -> list[str]:
    """Wrap even unbroken titles, then ellipsize without painting outside the card."""
    result: list[str] = []
    remaining = text
    while remaining and len(result) < limit:
        end = len(remaining)
        while end > 1 and face.getlength(remaining[:end]) > width:
            end -= 1
        if end < len(remaining):
            space = remaining.rfind(" ", 0, end + 1)
            if space > 0:
                end = space
        line, remaining = remaining[:end].rstrip(), remaining[end:].lstrip()
        if len(result) == limit - 1 and remaining:
            while line and face.getlength(line + "…") > width:
                line = line[:-1]
            line = line.rstrip() + "…"
        result.append(line)
    return result


@lru_cache(maxsize=128)
def artwork_bytes(url: str, bucket: int) -> bytes | None:
    """Only Spotify's image CDN; redirects, custom hosts and oversized files fail closed.

    The bucket bounds both successful and negative caching. Nothing accepts a URL
    from a request parameter, and downloads never forward cookies or credentials.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "i.scdn.co"
        or parsed.netloc != "i.scdn.co"
        or not parsed.path.startswith("/image/")
    ):
        return None
    try:
        started = time.monotonic()
        with httpx.stream("GET", url, timeout=2.0, follow_redirects=False) as response:
            if response.status_code != 200:
                return None
            data = bytearray()
            for chunk in response.iter_bytes(64 * 1024):
                data.extend(chunk)
                if len(data) > 4 * 1024 * 1024 or time.monotonic() - started > 3:
                    return None
            return bytes(data)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None


def artwork_image(data: bytes | None, size: int) -> Image.Image | None:
    if not data:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > 16_000_000:
                    return None
                return ImageOps.fit(source.convert("RGB"), (size, size))
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None


def record(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: str) -> None:
    draw.rounded_rectangle((x, y, x + size, y + size), radius=16, fill=color)
    inset = size // 7
    draw.ellipse((x + inset, y + inset, x + size - inset, y + size - inset), fill=BACKGROUND)
    for offset in (size // 4, size // 3):
        draw.ellipse(
            (x + offset, y + offset, x + size - offset, y + size - offset),
            outline="#365344",
            width=2,
        )
    center, radius = size // 2, size // 10
    draw.ellipse(
        (x + center - radius, y + center - radius, x + center + radius, y + center + radius),
        fill=ACCENT,
    )


def render_image(preview: Preview) -> bytes:
    # Both caches are bounded and expire naturally, including failed artwork loads.
    return _render_image(preview, int(time.time() // 300))


@lru_cache(maxsize=32)
def _render_image(preview: Preview, bucket: int) -> bytes:
    canvas = Image.new("RGB", (1200, 630), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (20, 20, 1180, 610), radius=28, fill="#14231b", outline="#385342", width=2
    )
    draw.rounded_rectangle((56, 52, 108, 104), radius=14, fill="#16833e")
    # The same music-note geometry as the site's favicon, at card resolution.
    draw.ellipse((68, 77, 83, 92), outline=TEXT, width=3)
    draw.line((83, 84, 83, 63, 95, 70), fill=TEXT, width=3)
    draw.text((123, 54), BRAND, font=font(27, bold=True), fill=TEXT)
    draw.text((124, 86), "What are you listening to?", font=font(17), fill=MUTED)
    draw.text((64, 141), preview.label, font=font(15, bold=True), fill=ACCENT)

    face = font(62)
    title_lines = lines(preview.title, face, 660, 3)
    for index, line in enumerate(title_lines):
        draw.text((60, 177 + index * 68), line, font=face, fill=TEXT)
    for index, line in enumerate(lines(preview.prompt, font(23), 650, 2)):
        draw.text((64, 400 + index * 29), line, font=font(23), fill=MUTED)

    futures = [ARTWORK_POOL.submit(artwork_bytes, url, bucket) for url in preview.artwork]
    colors = ("#284e3b", "#31514f", "#3a4937", "#454539")
    for index in range(4):
        x, y, size = 784 + (index % 2) * 178, 154 + (index // 2) * 178, 164
        artwork = artwork_image(futures[index].result(), size) if index < len(futures) else None
        if artwork is None:
            record(draw, x, y, size, colors[index])
        else:
            mask = Image.new("L", (size, size))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=12, fill=255)
            canvas.paste(artwork, (x, y), mask)

    draw.line((64, 477, 728, 477), fill="#385342", width=2)
    for line in lines(preview.headline, font(32, bold=True), 670, 1):
        draw.text((64, 494), line, font=font(32, bold=True), fill=ACCENT)
    for index, line in enumerate(lines(preview.detail, font(21), 1050, 2)):
        draw.text((64, 542 + index * 26), line, font=font(21), fill=MUTED)
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()
