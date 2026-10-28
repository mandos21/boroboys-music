"""Exercise built nginx + API, without JS or third-party preview services.

Usage: python frontend/scripts/check-preview-http.py http://localhost:8080
Seed the API's disposable test DB using backend/scripts/seed_preview_smoke.py.
Use --fallback after stopping that disposable API to check the SSI error stub.
"""

import struct
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.meta = {}
        self.titles = 0
        self.scripts = []
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.titles += 1
        if tag == "meta":
            key = attrs.get("property", attrs.get("name"))
            assert key not in self.meta, f"Duplicate metadata: {key}"
            self.meta[key] = attrs.get("content")
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])


base = sys.argv[1].rstrip("/")
fallback = "--fallback" in sys.argv
round_path = "/rounds/00000000-0000-4000-8000-000000000001"


def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.read(), response.headers


for path in ["/", round_path, round_path + "?from=chat", round_path + "/", "/settings"]:
    body, headers = get(path)
    html = body.decode()
    page = Page(html)
    assert page.titles == 1
    assert "<!--#" not in html and "[an error occurred" not in html
    assert '<div id="root">' in html
    assert "no-cache" in headers.get("Cache-Control", "")
    assert "Content-Security-Policy" in headers
    if path.startswith(round_path) and not fallback:
        assert page.meta["og:title"] == "Preview smoke round · BoroCrew Music"
        assert "Closes in three days" in page.meta["og:description"]
        assert "Eastern" in page.meta["og:description"]
        assert page.meta["og:url"].endswith(round_path)
        assert "?from=" not in page.meta["og:url"]
    else:
        assert page.meta["og:title"] == "BoroCrew Music"
    assert page.scripts
    for script in page.scripts:
        content, asset_headers = get(script)
        assert "javascript" in asset_headers["Content-Type"]
        assert content and b"<!doctype html>" not in content

if fallback:
    image, _ = get("/share-default.png")
else:
    html, _ = get("/rounds/00000000-0000-4000-8000-000000000002")
    assert b"PRIVATE DRAFT TITLE" not in html
    image, headers = get("/api/v1/previews/00000000-0000-4000-8000-000000000001/image.png")
    assert headers["Content-Type"] == "image/png"
    try:
        get("/api/v1/rounds/00000000-0000-4000-8000-000000000001")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Private round endpoint lost authentication")
assert image.startswith(b"\x89PNG\r\n\x1a\n")
assert struct.unpack(">II", image[16:24]) == (1200, 630)
print("Production preview checks passed" + (" (API unavailable fallback)" if fallback else ""))
