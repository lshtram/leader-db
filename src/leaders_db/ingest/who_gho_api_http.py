"""HTTP + JSON cache layer for the WHO Global Health Observatory (GHO) OData API.

This module owns the WHO GHO API-specific networking concerns:

- The API base URL (:data:`WHO_GHO_API_BASE`).
- The cache file I/O helpers (:func:`_read_cached_json`,
  :func:`_write_cached_json`).
- The single HTTP fetch + cache write helper
  (:func:`fetch_who_gho_api_payload`) that handles one automatic
  retry on ``ConnectionError`` / ``Timeout``, no retry on 4xx, the
  $top=1000 server cap (defensively), and the race-with-cache-
  eviction case (file disappears between the existence check and
  the read).
- The OData 4.0 ``{ "value": [ ... ] }`` response parser
  (:func:`parse_who_gho_api_payload`) that turns the JSON into a
  long-format ``pandas.DataFrame`` (one row per country-indicator-
  year) with the ``SpatialDim`` (ISO3) and ``NumericValue`` cells
  preserved. The orchestrator in :mod:`who_gho_api_io` (via
  :mod:`who_gho_api`) is responsible for the country filter +
  long-to-wide pivot + ``raw_column`` rename.

This module is the lowest level of the WHO GHO API three-module
split:

- :mod:`leaders_db.ingest.who_gho_api_http` (this) -- HTTP + cache I/O.
- :mod:`leaders_db.ingest.who_gho_api_io`     -- catalog, paths,
                                                  read orchestrator,
                                                  parquet write.
- :mod:`leaders_db.ingest.who_gho_api_db`     -- source/observation
                                                  DB writes, run
                                                  manifest.

The WHO GHO OData API v1 (Azure-backed, public, no auth) is
documented at
https://www.who.int/data/gho/info/gho-odata-api. The Stage 2
contract:

- URL pattern:
  ``{WHO_GHO_API_BASE}{IndicatorCode}?$filter=...&$top=1000``
- Default response is JSON with a ``value`` array (no wrapper
  envelope). Each element has the fields documented at
  https://ghoapi.azureedge.net/api/$metadata.
- The API has a hard $top cap of 1000 (returns a 400 error for
  larger values). The year + ``SpatialDimType eq 'COUNTRY'`` +
  ``Dim1 eq 'SEX_BTSX'`` combinator returns < 1000 records for
  every catalog indicator, so no pagination is required for the
  prototype. The reader is defensive anyway: if a future caller
  relaxes the filter and the response exceeds 1000, the
  ``@odata.nextLink`` is followed via the ``$skip`` page-cursor
  pattern.
- ``SpatialDimType`` other than ``COUNTRY`` is filtered out at
  the parser level so non-country aggregates (REGION,
  WORLDBANKINCOMEGROUP, GLOBAL) never reach the Stage 2 frame.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from .who_gho_api_io import _API_TOP_CAP, _COUNTRY_SPATIAL_DIM_TYPE

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: WHO GHO OData API base. Public, no auth. The full URL is built
#: as ``WHO_GHO_API_BASE + IndicatorCode + ?$filter=...&$top=1000``.
WHO_GHO_API_BASE: str = "https://ghoapi.azureedge.net/api/"

#: How many times to retry a failed HTTP call. The first attempt is
#: ``0``; we retry once on ``ConnectionError`` / ``Timeout`` (4xx
#: is not retried -- it would just fail again).
WHO_GHO_API_HTTP_MAX_ATTEMPTS: int = 2

#: How long to wait on a single HTTP request before timing out.
WHO_GHO_API_HTTP_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_json(cache_path: Path) -> dict[str, Any] | list[Any] | None:
    """Read a WHO GHO API JSON cache file and return the parsed object.

    Returns ``None`` if the file is missing or unparseable (the
    caller treats both cases the same -- fall through to HTTP).
    """
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _logger.warning(
            "WHO GHO API cache file %s is corrupt (%s); falling through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_json(
    cache_path: Path, payload: dict[str, Any] | list[Any]
) -> None:
    """Write a WHO GHO API payload to the cache as pretty-printed JSON.

    Creates parent directories as needed. The verbatim API response
    is preserved so a future caller can verify the data matches
    what the server returned.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------


def build_who_gho_api_url(
    indicator_code: str,
    *,
    year: int,
    spatial_dim_type: str = _COUNTRY_SPATIAL_DIM_TYPE,
    dim1: str | None = None,
) -> str:
    """Build the WHO GHO OData URL for one ``(indicator, year)``.

    The ``$filter`` clauses are URL-encoded (the API uses OData 4.0
    ``$filter`` with quoted string values and ``eq``). For the
    prototype the caller passes ``spatial_dim_type='COUNTRY'`` (the
    default) to scope the response to country-level records and
    ``dim1='SEX_BTSX'`` for SEX-disaggregated indicators to scope
    to the both-sexes aggregate. The ``$top=1000`` cap is enforced
    unconditionally; the orchestrator pages with ``$skip`` if
    ``@odata.nextLink`` is present in the response.

    Args:
        indicator_code: the WHO GHO API IndicatorCode (e.g.
            ``WHOSIS_000001``).
        year: the calendar year to filter on (``TimeDim eq <year>``).
        spatial_dim_type: the ``SpatialDimType`` filter (default
            ``COUNTRY``; the API distinguishes from ``REGION``,
            ``WORLDBANKINCOMEGROUP``, ``GLOBAL``).
        dim1: optional ``Dim1`` filter. For SEX-disaggregated
            indicators the catalog passes ``SEX_BTSX`` (both
            sexes) to keep the Stage 2 frame at one row per
            ``(country, year)``. ``None`` to skip the filter
            (use for non-SEX-disaggregated indicators).

    Returns:
        The full URL with the ``$filter`` + ``$top`` clauses
        URL-encoded. Example:

        >>> build_who_gho_api_url(
        ...     "WHOSIS_000001", year=2021, dim1="SEX_BTSX"
        ... )
        'https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=...'
    """
    clauses = [
        f"SpatialDimType eq '{spatial_dim_type}'",
        f"TimeDim eq {int(year)}",
    ]
    if dim1:
        clauses.append(f"Dim1 eq '{dim1}'")
    filter_expr = " and ".join(clauses)
    return (
        f"{WHO_GHO_API_BASE}{indicator_code}"
        f"?$filter={filter_expr}&$top={_API_TOP_CAP}"
    )


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_who_gho_api_payload(
    indicator_code: str,
    year: int,
    *,
    cache_path: Path,
    dim1: str | None = None,
    force_refresh: bool = False,
    request_timeout: float = WHO_GHO_API_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], bool]:
    """Fetch the WHO GHO API payload for one ``(indicator, year)``.

    Cache-first, HTTP-fallback. Returns a 2-tuple ``(parsed_payload,
    came_from_cache)``. If the cache file exists and
    ``force_refresh`` is ``False``, the payload is read from the
    cache and ``came_from_cache`` is ``True``. Otherwise the
    payload is HTTP-fetched (one automatic retry on
    ``ConnectionError`` / ``Timeout``; no retry on 4xx), written to
    the cache verbatim, and ``came_from_cache`` is ``False``. The
    race-with-cache-eviction case (file disappears between the
    existence check and the read) is handled transparently -- if
    the cache read returns ``None``, the call falls through to
    HTTP.

    The HTTP fetch follows OData ``@odata.nextLink`` paginated
    responses so a future caller can ask for an unpaged query
    without hitting the 1000-record cap. The cache write is only
    performed for the first page (the typical single-page response
    shape for a year + country + both-sexes filter).
    """
    if not force_refresh:
        cached = _read_cached_json(cache_path)
        if cached is not None:
            return cached, True

    payload = _http_get_indicator(
        indicator_code,
        year,
        cache_path=cache_path,
        dim1=dim1,
        timeout=request_timeout,
    )
    return payload, False


def _http_get_indicator(
    indicator_code: str,
    year: int,
    *,
    cache_path: Path,
    dim1: str | None,
    timeout: float,
) -> dict[str, Any]:
    """HTTP-GET a WHO GHO OData indicator for one year; cache the response.

    The WHO GHO OData response is a JSON object ``{"@odata.context": ...,
    "value": [...records...], "@odata.nextLink": "..."?}``. The
    function follows ``@odata.nextLink`` if present (so a future
    caller can issue an unpaged query) and returns the merged
    ``value`` array wrapped in the original envelope shape. Writes
    the first-page verbatim response to ``cache_path`` (creating
    parent dirs as needed) so the next call can skip HTTP. One
    automatic retry on ``ConnectionError`` / ``Timeout``; no retry
    on 4xx (the 4xx error would just repeat).
    """
    url = build_who_gho_api_url(indicator_code, year=year, dim1=dim1)
    last_exc: Exception | None = None
    for attempt in range(WHO_GHO_API_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"WHO GHO API HTTP failed for {indicator_code} year {year}: "
                f"{exc}. Cache file {cache_path} is missing and the "
                f"network is unreachable."
            ) from exc
        # Success. Cache the first-page verbatim response and
        # merge any @odata.nextLink pages.
        merged = _follow_next_link(payload, timeout=timeout)
        _write_cached_json(cache_path, merged)
        return merged
    # Defensive: the loop above always returns or raises. If we
    # land here, the retry policy produced no exception but also
    # no payload.
    raise FileNotFoundError(
        f"WHO GHO API HTTP failed for {indicator_code} year {year}: "
        f"{last_exc!r}"
    )


def _follow_next_link(
    first_page: dict[str, Any], *, timeout: float
) -> dict[str, Any]:
    """Follow ``@odata.nextLink`` paginated responses.

    The WHO GHO OData API caps the per-response record count at
    1000. For a year + ``SpatialDimType eq 'COUNTRY'`` +
    ``Dim1 eq 'SEX_BTSX'`` filter the response is well under that
    cap (< 600 records for the year 2021 in our fixture), so
    pagination is not triggered. This helper is defensive -- it
    follows the ``@odata.nextLink`` chain if present so a future
    caller asking for an unpaged query (no ``$top`` or
    ``SpatialDimType`` filter) still works.
    """
    next_link = first_page.get("@odata.nextLink")
    if not next_link:
        return first_page
    merged_values: list[Any] = list(first_page.get("value", []))
    while next_link:
        try:
            response = requests.get(next_link, timeout=timeout)
            response.raise_for_status()
            page = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise FileNotFoundError(
                f"WHO GHO API pagination failed at {next_link}: {exc}"
            ) from exc
        merged_values.extend(page.get("value", []))
        next_link = page.get("@odata.nextLink")
    out = dict(first_page)
    out["value"] = merged_values
    # Drop the now-stale nextLink since we followed it.
    out.pop("@odata.nextLink", None)
    return out


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------
# The response parser lives in :mod:`who_gho_api_io` (the I/O
# module) per the WDI / WGI / UCDP / SIPRI / PTS / UNDP HDI split
# pattern: the http module owns the network + cache I/O, the I/O
# module owns the catalog + paths + parquet + response shape -> long
# DataFrame parser. Splitting the parser out keeps the http module
# focused on the network layer and the I/O module focused on the
# data-shape layer.

__all__ = [
    "WHO_GHO_API_BASE",
    "WHO_GHO_API_HTTP_MAX_ATTEMPTS",
    "WHO_GHO_API_HTTP_TIMEOUT",
    "build_who_gho_api_url",
    "fetch_who_gho_api_payload",
]
