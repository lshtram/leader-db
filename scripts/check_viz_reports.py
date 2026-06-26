#!/usr/bin/env python3
"""Health check for the Cloudflare/Superset visualization report proxy.

Checks the local nginx proxy by default. Pass the Cloudflare URL after logging in
through Access if you want to check the public route from an authenticated
session-aware environment:

    python scripts/check_viz_reports.py http://127.0.0.1:8088
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

DEFAULT_BASE_URL = "http://127.0.0.1:8088"
TIMEOUT_SECONDS = 15
REPORT_PATHS = (
    "/reports/",
    "/reports/country-metrics-dashboard.html",
    "/reports/briefs/us-equity-ownership.html",
    "/reports/briefs/us-market-size-baseline.html",
)
BRIEF_PATHS = (
    "/reports/briefs/us-equity-ownership.html",
    "/reports/briefs/us-market-size-baseline.html",
)


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        attr_map = dict(attrs)
        src = attr_map.get("src")
        if src:
            self.sources.append(src)


def _url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _fetch(url: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "leaders-db-viz-health/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.status, response.read(), response.headers.get("content-type", "")


def _check_ok(url: str) -> bytes:
    try:
        status, body, content_type = _fetch(url)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{url} failed: {exc.reason}") from exc
    if status != 200:
        raise RuntimeError(f"{url} returned HTTP {status}")
    if not body:
        raise RuntimeError(f"{url} returned an empty body ({content_type})")
    return body


def _extract_images(html: bytes) -> list[str]:
    parser = ImageParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    return parser.sources


def check(base_url: str) -> None:
    print(f"checking visualization reports at {base_url}")
    for path in REPORT_PATHS:
        body = _check_ok(_url(base_url, path))
        print(f"OK page: {path} ({len(body)} bytes)")

    for path in BRIEF_PATHS:
        page_url = _url(base_url, path)
        html = _check_ok(page_url)
        image_sources = _extract_images(html)
        if not image_sources:
            raise RuntimeError(f"{path} contains no <img> tags")
        broken: list[str] = []
        for source in image_sources:
            image_url = urllib.parse.urljoin(page_url, source)
            try:
                body = _check_ok(image_url)
            except RuntimeError:
                broken.append(image_url)
                continue
            if len(body) < 1024:
                broken.append(f"{image_url} (suspiciously small: {len(body)} bytes)")
        if broken:
            formatted = "\n  - ".join(broken)
            raise RuntimeError(f"{path} has broken images:\n  - {formatted}")
        print(f"OK images: {path} ({len(image_sources)} images)")


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    check(base_url)


if __name__ == "__main__":
    main()
