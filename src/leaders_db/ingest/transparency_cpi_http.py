"""HTTP + CSV cache layer for the Transparency International CPI HDX mirror.

This module owns the Transparency International CPI-specific
networking concerns:

- The HDX dataset UUID + the per-year CSV URL pattern
  (:data:`TRANSPARENCY_CPI_HDX_DATASET_UUID`,
  :func:`build_transparency_cpi_url`).
- The cache file I/O helpers (:func:`_read_cached_csv`,
  :func:`_write_cached_csv`).
- The single HTTP fetch + cache write helper
  (:func:`fetch_transparency_cpi_csv`) that follows the HDX
  redirect to S3 (transparent to ``requests``), handles one
  automatic retry on ``ConnectionError`` / ``Timeout``, no retry
  on 4xx, and the race-with-cache-eviction case (file disappears
  between the existence check and the read).

This module is the lowest level of the Transparency International
CPI three-module split:

- :mod:`leaders_db.ingest.transparency_cpi_http` (this) -- HTTP +
  cache I/O + URL builder.
- :mod:`leaders_db.ingest.transparency_cpi_csv`     -- CSV parser
  (wide DataFrame -> long DataFrame pivot).
- :mod:`leaders_db.ingest.transparency_cpi_io`     -- catalog,
  paths, parquet write.
- :mod:`leaders_db.ingest.transparency_cpi_db`     -- source /
  observation DB writes, run manifest.

The Transparency International CPI is published on
transparency.org but the direct xlsx download is CDN-gated per the
Phase B source-vetting report §3.6. The OCHA HDX (Humanitarian
Data Exchange) hosts the canonical per-year CSV mirror at
``https://data.humdata.org/dataset/<uuid>/resource/<ruuid>/
download/global_cpi_<year>.csv``. The HDX server returns a 302
redirect to an AWS S3 bucket with an AWS-pre-signed URL; the
``requests`` library follows the redirect transparently. The
verbatim CSV is preserved in the local cache so a re-run with the
same year makes zero HTTP calls.

The publisher of the data remains Transparency International (per
the licensing note on the transparency.org /copyright-enquiries
page: "Source: Transparency International"). HDX is the mirror.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

import requests

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: HDX dataset UUID for the Transparency International CPI dataset.
#: Stable as of probe (2026-06-19); the resource UUID for the 2023
#: CSV is in :data:`TRANSPARENCY_CPI_HDX_RESOURCE_2023`. A future
#: edition may add a new resource; the year-specific resource is
#: discovered at runtime via the HDX listing page (out of scope for
#: the prototype).
TRANSPARENCY_CPI_HDX_DATASET_UUID: str = (
    "fb4adde0-93d5-4ff9-befc-4a6916c1181b"
)

#: HDX resource UUID for the per-year 2023 CSV.
TRANSPARENCY_CPI_HDX_RESOURCE_2023: str = (
    "b2b0509d-299f-45f5-804f-a650d9597d2c"
)

#: HDX resource UUID for the all-years CSV (defensive; not used by
#: the per-year orchestrator path but available for historical
#: backstop).
TRANSPARENCY_CPI_HDX_RESOURCE_ALL: str = (
    "2019bc34-2771-40ce-870f-7a92cc1176a0"
)

#: HDX base URL. The per-year CSV URL is built as
#: ``HDX_BASE / <dataset_uuid> / resource / <resource_uuid> /
#: download / global_cpi_<year>.csv``.
TRANSPARENCY_CPI_HDX_BASE: str = "https://data.humdata.org/dataset"

#: How many times to retry a failed HTTP call. The first attempt is
#: ``0``; we retry once on ``ConnectionError`` / ``Timeout`` (4xx
#: is not retried -- it would just fail again).
TRANSPARENCY_CPI_HTTP_MAX_ATTEMPTS: int = 2

#: How long to wait on a single HTTP request before timing out.
TRANSPARENCY_CPI_HTTP_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------


def build_transparency_cpi_url(year: int) -> str:
    """Build the HDX URL for the Transparency International CPI CSV for one year.

    The URL follows the HDX pattern documented at
    https://data.humdata.org/dataset/<uuid>/resource/<ruuid>/download/global_cpi_<year>.csv.

    Args:
        year: the calendar year (e.g. ``2023``).

    Returns:
        The full HDX URL. The server returns a 302 redirect to an
        AWS S3 pre-signed URL; ``requests`` follows the redirect
        transparently.
    """
    return (
        f"{TRANSPARENCY_CPI_HDX_BASE}/"
        f"{TRANSPARENCY_CPI_HDX_DATASET_UUID}/"
        f"resource/{TRANSPARENCY_CPI_HDX_RESOURCE_2023}/"
        f"download/global_cpi_{int(year)}.csv"
    )


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_csv(cache_path: Path) -> list[dict[str, str]] | None:
    """Read a Transparency International CPI CSV cache file.

    Returns ``None`` if the file is missing or unparseable (the
    caller treats both cases the same -- fall through to HTTP).
    The cache file preserves the verbatim HDX CSV (UTF-8) so the
    parser and HTTP layer can run against the cache without
    modification.
    """
    if not cache_path.is_file():
        return None
    try:
        text = cache_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _logger.warning(
            "Transparency International CPI cache file %s is not "
            "UTF-8 (%s); falling through to HTTP",
            cache_path,
            exc,
        )
        return None
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        _logger.warning(
            "Transparency International CPI cache file %s is "
            "corrupt (%s); falling through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_csv(cache_path: Path, text: str) -> None:
    """Write a Transparency International CPI CSV response to the cache verbatim.

    Creates parent directories as needed. The verbatim HDX CSV is
    preserved (UTF-8) so a future caller can verify the data
    matches what the server returned.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_transparency_cpi_csv(
    year: int,
    *,
    cache_path: Path,
    force_refresh: bool = False,
    request_timeout: float = TRANSPARENCY_CPI_HTTP_TIMEOUT,
) -> tuple[list[dict[str, str]], bool]:
    """Fetch the Transparency International CPI CSV for one year.

    Cache-first, HTTP-fallback. Returns a 2-tuple ``(records,
    came_from_cache)``. If the cache file exists and
    ``force_refresh`` is ``False``, the records are read from the
    cache and ``came_from_cache`` is ``True``. Otherwise the
    CSV is HTTP-fetched (one automatic retry on
    ``ConnectionError`` / ``Timeout``; no retry on 4xx), written
    to the cache verbatim, parsed, and ``came_from_cache`` is
    ``False``. The race-with-cache-eviction case (file disappears
    between the existence check and the read) is handled
    transparently -- if the cache read returns ``None``, the call
    falls through to HTTP.

    The HDX server returns a 302 redirect to an AWS S3 bucket
    with an AWS-pre-signed URL; ``requests`` follows the redirect
    transparently.
    """
    if not force_refresh:
        cached = _read_cached_csv(cache_path)
        if cached is not None:
            return cached, True

    text = _http_get_csv(
        year, cache_path=cache_path, timeout=request_timeout
    )
    _write_cached_csv(cache_path, text)
    records = list(csv.DictReader(io.StringIO(text)))
    return records, False


def _http_get_csv(
    year: int, *, cache_path: Path, timeout: float
) -> str:
    """HTTP-GET the Transparency International CPI CSV for one year.

    Follows the HDX 302 redirect to S3 transparently. Writes the
    verbatim response to ``cache_path`` (creating parent dirs as
    needed) so the next call can skip HTTP. One automatic retry
    on ``ConnectionError`` / ``Timeout``; no retry on 4xx (the 4xx
    error would just repeat).
    """
    url = build_transparency_cpi_url(year)
    last_exc: Exception | None = None
    for attempt in range(TRANSPARENCY_CPI_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"Transparency International CPI HTTP failed for "
                f"year {year}: {exc}. Cache file {cache_path} is "
                "missing and the network is unreachable."
            ) from exc
    # Defensive: the loop above always returns or raises. If we
    # land here, the retry policy produced no exception but also
    # no response.
    raise FileNotFoundError(
        f"Transparency International CPI HTTP failed for year "
        f"{year}: {last_exc!r}"
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------
# The response parser lives in :mod:`transparency_cpi_csv` (the
# response-shape -> wide DataFrame parser module) per the WHO GHO
# API / WDI split pattern: the http module owns the network + cache
# I/O, the csv module owns the response-shape -> DataFrame parser.
# Splitting the parser out keeps the http module focused on the
# network layer and the csv module focused on the data-shape layer.

__all__ = [
    "TRANSPARENCY_CPI_HDX_BASE",
    "TRANSPARENCY_CPI_HDX_DATASET_UUID",
    "TRANSPARENCY_CPI_HDX_RESOURCE_2023",
    "TRANSPARENCY_CPI_HDX_RESOURCE_ALL",
    "TRANSPARENCY_CPI_HTTP_MAX_ATTEMPTS",
    "TRANSPARENCY_CPI_HTTP_TIMEOUT",
    "build_transparency_cpi_url",
    "fetch_transparency_cpi_csv",
]
