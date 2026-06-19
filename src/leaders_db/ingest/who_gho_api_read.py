"""Stage 2 -- WHO GHO API read orchestrator.

This module holds the read orchestrator
(:func:`read_who_gho_api`) and the small year-resolution helper
(:func:`_resolve_year`). It is split out of :mod:`who_gho_api_io`
to keep the I/O module under the AGENTS.md 400-line convention;
the WDI / WGI / UCDP / SIPRI / PTS / UNDP HDI adapters follow
the same split-when-the-cap-fires pattern.

The read orchestrator iterates the catalog, fetches each
``(year, indicator)`` cell from the cache or the WHO GHO OData
HTTP endpoint, parses the long-format response, and pivots to a
wide-format DataFrame (one row per ``(iso3, year)``, one
column per catalog ``variable_name``). The wide frame also
carries a sibling ``<variable>_raw_value`` column per indicator
so the DB writer can emit the verbatim WHO GHO API ``Value``
field (with confidence-interval bounds) as the
``source_observations.raw_value`` audit trail.

The HTTP + cache layer lives in :mod:`who_gho_api_http`. The
catalog + paths + parquet write live in
:mod:`who_gho_api_io`. The DB writes live in
:mod:`who_gho_api_db`. The orchestrator that ties everything
together lives in :mod:`who_gho_api`.
"""

from __future__ import annotations

import logging

import pandas as pd

from .who_gho_api_io import (
    default_cache_dir,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = ["read_who_gho_api"]


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def _resolve_year(year: int | None) -> list[int]:
    """Return the list of years to read.

    The WHO GHO API reader is a single-year reader (the API
    returns < 1000 records per year + COUNTRY + Dim1 filter so
    no pagination is needed). If the caller passes ``year=None``
    the function raises :class:`ValueError` -- the prototype's
    CLI always supplies a year via the
    ``RunConfig.project.target_year`` default.
    """
    if year is None:
        raise ValueError(
            "year is required for read_who_gho_api (the WHO GHO API "
            "Stage 2 reader is a single-year reader; pass year=int)"
        )
    return [int(year)]


def read_who_gho_api(
    *,
    year: int | None = None,
    catalog_path: str | None = None,
    cache_dir: object = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> pd.DataFrame:
    """Read the WHO GHO API for ``year`` and pivot to wide format.

    Steps:

    1. Load the catalog (or use the ``indicator_codes`` override).
    2. For each indicator: build the cache path
       ``<cache_dir>/<year>/<raw_column>.json``. If the cache
       file exists AND ``force_refresh`` is ``False``, read the
       cached JSON; else HTTP-GET the WHO GHO OData endpoint via
       :mod:`who_gho_api_http`, write the verbatim response to
       the cache, then parse.
    3. The parser filters non-country ``SpatialDimType`` records
       (``REGION`` / ``WORLDBANKINCOMEGROUP`` / ``GLOBAL``) and
       rows with a missing or non-3-letter ``SpatialDim`` -- so
       the long frame is country-only.
    4. Pivot from long format (one row per
       ``(country, indicator, year)``) to wide format (one row
       per ``(iso3, year)``, one column per catalog
       ``variable_name``). A sibling ``<variable>_raw_value``
       column per indicator carries the verbatim ``Value``
       field for the audit trail.
    5. Coerce the ``year`` column to ``int`` and the indicator
       columns to ``float`` (NaN for absent values).

    The returned DataFrame carries two extra attributes on
    ``df.attrs`` so the orchestrator can surface them in
    :class:`WhoGhoApiIngestResult`:

    - ``df.attrs["indicators_cached"]`` -- count of catalog
      indicators that were read from the JSON cache.
    - ``df.attrs["indicators_fetched"]`` -- count of catalog
      indicators that were HTTP-fetched in this call.

    Args:
        year: filter to a single year (e.g. ``2023``).
        catalog_path: override the indicator catalog. Default:
            checked-in.
        cache_dir: override the JSON cache root. Default:
            data-lake path (``data/raw/who_gho_api/cache/``).
        force_refresh: re-download even when the cache file
            exists.
        request_timeout: per-request HTTP timeout in seconds.

    Returns:
        A pandas DataFrame with columns ``iso3``, ``year``, then
        one column per catalog indicator (named with the
        ``variable_name``) + one sibling ``<variable>_raw_value``
        column per indicator. ``year`` is integer. Indicator
        columns are float (NaN = missing).

    Raises:
        FileNotFoundError: no cached file and no network
            reachability (or ``force_refresh=True`` and HTTP
            fails).
        requests.HTTPError: non-2xx WHO GHO API response.
        ValueError: malformed JSON or a catalog code absent
            from the API.
    """
    # Local import to break the io <-> http cycle (the http
    # module needs the OData API constants from io; this module
    # needs the http functions and the io parser).
    from .who_gho_api_http import fetch_who_gho_api_payload
    from .who_gho_api_io import parse_who_gho_api_payload

    # ``catalog_path`` is typed as ``str | None`` here so this
    # module has no :mod:`pathlib` import; the I/O module's
    # :func:`load_indicator_catalog` accepts the same shape.
    specs = load_indicator_catalog(catalog_path=catalog_path)
    years_to_read = _resolve_year(year)

    cache_root = cache_dir or default_cache_dir()
    long_frames: list[pd.DataFrame] = []
    cached_codes: set[str] = set()
    fetched_codes: set[str] = set()

    for one_year in years_to_read:
        cache_year_dir = cache_root / str(one_year)
        if not cache_year_dir.is_dir():
            cache_year_dir.mkdir(parents=True, exist_ok=True)
        for spec in specs:
            cache_path = cache_year_dir / f"{spec.raw_column}.json"
            dim1 = spec.dim1_filter or None
            payload, came_from_cache = fetch_who_gho_api_payload(
                spec.raw_column,
                one_year,
                cache_path=cache_path,
                dim1=dim1,
                force_refresh=force_refresh,
                request_timeout=request_timeout,
            )
            if came_from_cache:
                cached_codes.add(spec.raw_column)
            else:
                fetched_codes.add(spec.raw_column)
            long_frames.append(
                parse_who_gho_api_payload(
                    payload, code=spec.raw_column, year=one_year
                )
            )

    if not long_frames:
        df = pd.DataFrame(columns=["iso3", "year"])
        df.attrs["indicators_cached"] = 0
        df.attrs["indicators_fetched"] = 0
        return df

    long_df = pd.concat(long_frames, ignore_index=True)
    # Wide pivot on the float ``value`` column: one row per
    # ``(iso3, year)``, one column per indicator (named with the
    # catalog's ``variable_name``). The WHO GHO API's verbatim
    # ``Value`` field (e.g. ``"76.4 [76.3-76.5]"`` with bounds)
    # is the audit-trail ``raw_value``; we preserve it in a
    # sibling column per indicator (``<variable>_raw_value``)
    # so the DB write can emit the verbatim string for the
    # ``source_observations.raw_value`` audit field without
    # losing the confidence-interval bounds.
    value_wide = long_df.pivot_table(
        index=["iso3", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    )
    raw_value_wide = long_df.pivot_table(
        index=["iso3", "year"],
        columns="indicator_code",
        values="raw_value",
        aggfunc="first",
    )
    rename_map = {spec.raw_column: spec.variable_name for spec in specs}
    value_wide = value_wide.rename(columns=rename_map)
    raw_value_wide = raw_value_wide.rename(
        columns={code: f"{name}_raw_value" for code, name in rename_map.items()}
    )
    # Concatenate horizontally on the (iso3, year) index.
    wide = pd.concat([value_wide, raw_value_wide], axis="columns")
    wide = wide.reset_index()
    # Type coercion: year to int, indicator columns to float.
    wide["year"] = wide["year"].astype(int)
    for col in wide.columns:
        if col in {"iso3", "year"}:
            continue
        if col.endswith("_raw_value"):
            # Audit-trail columns: keep as object dtype (the
            # verbatim ``Value`` field is a string).
            continue
        wide[col] = pd.to_numeric(wide[col], errors="coerce").astype(float)
    df = wide

    # Carry cached/fetched counts through df.attrs so the
    # orchestrator can populate
    # WhoGhoApiIngestResult.indicators_cached/_fetched without
    # re-inspecting the cache. Counts are in unique indicators,
    # not per (year, indicator) -- see the loop above.
    df.attrs["indicators_cached"] = len(cached_codes)
    df.attrs["indicators_fetched"] = len(fetched_codes)
    return df
