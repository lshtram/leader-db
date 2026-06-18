"""HTTP + JSON cache layer for the World Bank WDI Stage 2 adapter.

This module owns the WDI-specific networking concerns:

- The API base URL and the per-request ``per_page`` setting
  (:data:`WDI_API_BASE`, :data:`WDI_PER_PAGE`).
- The cache file I/O helpers (:func:`_read_cached_json`,
  :func:`_write_cached_json`).
- The single HTTP fetch + cache write helper
  (:func:`fetch_wdi_payload`) that handles one automatic retry on
  ``ConnectionError`` / ``Timeout``, no retry on 4xx, and the
  race-with-cache-eviction case (file disappears between the
  existence check and the read).
- The WDI v2 2-element-array response parser
  (:func:`parse_wdi_payload`) that turns the JSON into a long-format
  ``pandas.DataFrame`` ready for the read orchestrator to pivot.

This module is the lowest level of the WDI three-module split:

- :mod:`leaders_db.ingest.wdi_http` (this) -- HTTP + cache I/O.
- :mod:`leaders_db.ingest.wdi_io`     -- catalog, paths, read
                                          orchestrator, parquet write,
                                          attribution metadata.
- :mod:`leaders_db.ingest.wdi_db`     -- source/observation DB writes,
                                          run manifest.

The WDI v2 response is a 2-element array ``[metadata, data]``. The
``data`` list contains one record per ``(country, indicator, year)``
with ``countryiso3code``, ``date``, and ``value`` (``null`` for
missing). :func:`parse_wdi_payload` unpacks that into a long-format
DataFrame; the orchestrator in :mod:`wdi_io` is responsible for the
aggregate-filter + long-to-wide pivot.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

_logger = logging.getLogger(__name__)

#: WDI v2 indicator endpoint base. Public, no auth. The full URL is
#: built as
#: ``WDI_API_BASE + country/all/indicator/{code}?date={year}&format=json&per_page=...``.
WDI_API_BASE: str = "https://api.worldbank.org/v2/"

#: Per-request ``per_page`` value. WDI v2's default is 50, which is
#: too small for the ``country/all`` endpoint (~266 entries). 32,500
#: is the v2 max and returns the full set in a single page.
WDI_PER_PAGE: int = 32500

#: How many times to retry a failed HTTP call. The first attempt is
#: ``0``; we retry once on ``ConnectionError`` / ``Timeout`` (4xx is
#: not retried — it would just fail again).
WDI_HTTP_MAX_ATTEMPTS: int = 2


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_json(cache_path: Path) -> dict[str, Any] | list[Any] | None:
    """Read a WDI v2 JSON cache file and return the parsed object.

    Returns ``None`` if the file is missing or unparseable (the caller
    treats both cases the same — fall through to HTTP).
    """
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _logger.warning(
            "WDI cache file %s is corrupt (%s); falling through to HTTP",
            cache_path, exc,
        )
        return None


def _write_cached_json(cache_path: Path, payload: dict[str, Any] | list[Any]) -> None:
    """Write a WDI v2 payload to the cache as pretty-printed JSON.

    Creates parent directories as needed. The verbatim API response is
    preserved so a future caller can verify the data matches what the
    server returned.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_wdi_payload(
    code: str,
    year: int,
    *,
    cache_path: Path,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> tuple[list[Any], bool]:
    """Fetch the WDI v2 payload for one ``(code, year)``.

    Cache-first, HTTP-fallback. Returns a 2-tuple
    ``(parsed_payload, came_from_cache)``. If the cache file exists
    and ``force_refresh`` is ``False``, the payload is read from
    the cache and ``came_from_cache`` is ``True``. Otherwise the
    payload is HTTP-fetched (one automatic retry on
    ``ConnectionError`` / ``Timeout``; no retry on 4xx), written
    to the cache verbatim, and ``came_from_cache`` is ``False``.
    The race-with-cache-eviction case (file disappears between the
    existence check and the read) is handled transparently — if
    the cache read returns ``None``, the call falls through to HTTP.
    """
    if not force_refresh:
        cached = _read_cached_json(cache_path)
        if cached is not None:
            return cached, True

    payload = _http_get_indicator(
        code, year, cache_path=cache_path, timeout=request_timeout,
    )
    return payload, False


def _http_get_indicator(
    code: str,
    year: int,
    *,
    cache_path: Path,
    timeout: float,
) -> list[Any]:
    """HTTP-GET a WDI v2 indicator for one year; cache the response on disk.

    The WDI v2 response is a 2-element JSON array ``[metadata, data]``;
    we return the raw parsed array. Writes the verbatim API response
    to ``cache_path`` (creating parent dirs as needed) so the next
    call can skip HTTP. One automatic retry on ``ConnectionError`` /
    ``Timeout``; no retry on 4xx.
    """
    url = (
        f"{WDI_API_BASE}country/all/indicator/{code}"
        f"?date={year}&format=json&per_page={WDI_PER_PAGE}"
    )
    last_exc: Exception | None = None
    for attempt in range(WDI_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"WDI HTTP failed for {code} year {year}: {exc}. "
                f"Cache file {cache_path} is missing and the network "
                f"is unreachable."
            ) from exc
        # Success — write the verbatim response to the cache.
        _write_cached_json(cache_path, payload)
        return payload
    # Defensive: the loop above always returns or raises. If we land
    # here, the retry policy produced no exception but also no payload.
    raise FileNotFoundError(
        f"WDI HTTP failed for {code} year {year}: {last_exc!r}"
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def parse_wdi_payload(
    payload: list[Any],
    *,
    code: str,
    year: int,
) -> pd.DataFrame:
    """Parse a WDI v2 2-element array response into a long-format DataFrame.

    Returns a frame with columns ``["iso3", "year", "indicator_code",
    "value"]``. Rows where ``value`` is ``None`` (WDI's null
    representation) are kept; the orchestrator (``read_wdi``) handles
    the NaN conversion + aggregate filter + long-to-wide pivot.
    Aggregate ISO3 codes are NOT filtered here so the per-indicator
    cache files remain verbatim API responses.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError(
            f"WDI response for {code} year {year} is not a 2-element array; "
            f"got {type(payload).__name__}"
        )
    data = payload[1]
    if not isinstance(data, list):
        raise ValueError(
            f"WDI response for {code} year {year} data field is not a list; "
            f"got {type(data).__name__}"
        )
    rows: list[dict[str, object]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        iso3 = entry.get("countryiso3code")
        if not iso3:
            continue
        rows.append(
            {
                "iso3": str(iso3),
                "year": int(entry.get("date", year)),
                "indicator_code": str(
                    entry.get("indicator", {}).get("id", code) or code
                ),
                "value": entry.get("value", None),
            }
        )
    return pd.DataFrame(rows, columns=["iso3", "year", "indicator_code", "value"])


__all__ = [
    "WDI_API_BASE",
    "WDI_HTTP_MAX_ATTEMPTS",
    "WDI_PER_PAGE",
    "fetch_wdi_payload",
    "parse_wdi_payload",
]
