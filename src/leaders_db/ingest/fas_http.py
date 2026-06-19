"""HTTP + HTML cache layer for the FAS Nuclear Notebook status page.

This module owns the FAS-specific networking concerns:

- The consolidated status page URL
  (:data:`FAS_STATUS_PAGE_URL`).
- The cache file I/O helpers (:func:`_read_cached_html`,
  :func:`_write_cached_html`).
- The single HTTP fetch + cache write helper
  (:func:`fetch_fas_status_html`) that follows the FAS server's
  redirects, handles one automatic retry on ``ConnectionError``
  / ``Timeout``, no retry on 4xx, and the race-with-cache-
  eviction case (file disappears between the existence check and
  the read).

This module is the lowest level of the FAS three-module split:

- :mod:`leaders_db.ingest.fas_http` (this) -- HTTP + cache I/O.
- :mod:`leaders_db.ingest.fas_html` -- HTML table parser
  (response-shape -> wide DataFrame).
- :mod:`leaders_db.ingest.fas_io` -- catalog, paths, parquet
  write.
- :mod:`leaders_db.ingest.fas_db` -- source / observation DB
  writes, run manifest.

The FAS "Status of World Nuclear Forces" page at
``https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html``
returns a single HTML page (~54 KB) with one parseable
``<table id="table1">`` containing all 9 nuclear-armed states. The
verbatim HTML is preserved in the local cache so a re-run with no
URL change makes zero HTTP calls.

Per-country pages (``nuke.fas.org/guide/<country>/``) are mostly
table-of-contents and not the consolidated snapshot; the
status-of-world-nuclear-forces page is the canonical FAS-Nuclear-
Notebook summary cited by SIPRI Yearbook Ch.7.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: How many times to retry a failed HTTP call. The first attempt
#: is ``0``; we retry once on ``ConnectionError`` / ``Timeout``
#: (4xx is not retried -- it would just fail again).
FAS_HTTP_MAX_ATTEMPTS: int = 2

#: How long to wait on a single HTTP request before timing out.
FAS_HTTP_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_html(cache_path: Path) -> str | None:
    """Read a FAS HTML cache file.

    Returns ``None`` if the file is missing or unreadable (the
    caller treats both cases the same -- fall through to HTTP).
    The cache file preserves the verbatim FAS HTML so the parser
    can run against the cache without modification.
    """
    if not cache_path.is_file():
        return None
    try:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _logger.warning(
            "FAS cache file %s is unreadable (%s); falling "
            "through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_html(cache_path: Path, html: str) -> None:
    """Write a FAS HTML response to the cache verbatim.

    Creates parent directories as needed. The verbatim FAS HTML
    is preserved (UTF-8 with replacement) so a future caller can
    verify the data matches what the server returned.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_fas_status_html(
    *,
    cache_path: Path,
    force_refresh: bool = False,
    request_timeout: float = FAS_HTTP_TIMEOUT,
    url: str | None = None,
) -> tuple[str, bool]:
    """Fetch the FAS Status of World Nuclear Forces HTML page.

    Cache-first, HTTP-fallback. Returns a 2-tuple ``(html,
    came_from_cache)``. If the cache file exists and
    ``force_refresh`` is ``False``, the HTML is read from the
    cache and ``came_from_cache`` is ``True``. Otherwise the HTML
    is HTTP-fetched (one automatic retry on ``ConnectionError`` /
    ``Timeout``; no retry on 4xx), written to the cache verbatim,
    and ``came_from_cache`` is ``False``.

    The FAS server returns 200 with a text/html content type;
    the response body is the verbatim page HTML.
    """
    if not force_refresh:
        cached = _read_cached_html(cache_path)
        if cached is not None:
            return cached, True

    html = _http_get_html(
        cache_path=cache_path,
        timeout=request_timeout,
        url=url,
    )
    _write_cached_html(cache_path, html)
    return html, False


def _http_get_html(
    *,
    cache_path: Path,
    timeout: float,
    url: str | None,
) -> str:
    """HTTP-GET the FAS status page; cache the response verbatim.

    One automatic retry on ``ConnectionError`` / ``Timeout``;
    no retry on 4xx (the 4xx error would just repeat).
    """
    target_url = url or "https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html"
    last_exc: Exception | None = None
    for attempt in range(FAS_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(target_url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"FAS HTTP failed: {exc}. Cache file {cache_path} "
                "is missing and the network is unreachable."
            ) from exc
    # Defensive: the loop above always returns or raises. If we
    # land here, the retry policy produced no exception but also
    # no response.
    raise FileNotFoundError(
        f"FAS HTTP failed: {last_exc!r}"
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------
# The response parser lives in :mod:`fas_html` (the
# response-shape -> wide DataFrame parser module) per the WDI /
# WHO GHO API / Transparency International CPI split pattern: the
# http module owns the network + cache I/O, the html module owns
# the response-shape -> DataFrame parser.

__all__ = [
    "FAS_HTTP_MAX_ATTEMPTS",
    "FAS_HTTP_TIMEOUT",
    "fetch_fas_status_html",
]
