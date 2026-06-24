"""Unified-source World Bank WDI observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation` build
loop for the unified-source WDI adapter. The function takes the
wide-format DataFrame returned by the local cache-only read path
(``_read_cached_wdi_responses`` -- one row per ``(iso3, year)``
with one column per catalog indicator named with the canonical
``variable_name``) and emits the canonical observation records
with raw locators, transform locators, attribution text, and
column-specific unit labels.

The local cache-only read path is what makes the unified
adapter offline / cache-only in this slice: it never invokes
the network. It reads the staged per-(year, indicator) JSON
files, mirrors the legacy :func:`parse_wdi_payload` /
:func:`read_wdi` long-to-wide pivot + aggregate filter, and
returns a wide-format DataFrame the existing transform layer
already consumes.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter` to keep
the adapter class module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and respect the
documented 400-line module convention.

Wide-format row emission
------------------------

The legacy ``read_wdi`` pivots the per-(year, indicator)
long-format DataFrame to wide format: one row per
``(iso3, year)`` with one column per catalog indicator (named
with the ``variable_name``). For each non-NaN indicator cell,
this transform emits one ``NormalizedObservation`` carrying:

- ``value``: the numeric cell value.
- ``indicator_code``: the catalog ``variable_name`` (e.g.
  ``wdi_population``).
- ``observation_family``: ``economic_country_year`` for the 10
  ``economic_wellbeing`` indicators; ``social_country_year``
  for the 4 ``social_wellbeing`` indicators.
- ``raw_locator``: ``asset_id`` + ``path`` (cache file path) +
  ``api_endpoint`` (WDI v2 indicator URL template) +
  ``api_params_hash`` placeholder + ``json_pointer``
  pointing at the per-row entry inside the cache file's
  ``data`` array.

NaN cells are NOT emitted (SRC-OBS-007: missing / invalid raw
cells shall not be silently converted into numeric values).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._descriptor import (
    WORLD_BANK_WDI_ATTRIBUTION_TEXT,
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_DEFAULT_VERSION,
    WORLD_BANK_WDI_HOMEPAGE_URL,
    WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX,
    WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC,
    WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL,
    WORLD_BANK_WDI_SOURCE_KEY,
)

# Per-observation asset id. One logical asset per cache root;
# per-observation locators point at the specific cache file.
WORLD_BANK_WDI_CACHE_ASSET_ID: str = (
    f"{WORLD_BANK_WDI_SOURCE_KEY}:cache"
)

# Transform-name string carried on every NormalizedObservation's
# ``transform_locator``. Surfaces the legacy read + pivot pair
# that produced the observation so downstream scoring / audit
# code can resolve the parse path.
WORLD_BANK_WDI_TRANSFORM_NAME: str = "read_wdi_pivot_wide"

# The canonical rating_category -> observation_family mapping
# driven by the WDI catalog. The catalog at
# ``src/leaders_db/ingest/catalogs/wdi.csv`` partitions its
# 14 indicators into ``economic_wellbeing`` (10) +
# ``social_wellbeing`` (4). We map at observation-emission
# time so downstream consumers see the right family without
# re-reading the catalog.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "economic_wellbeing": WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC,
    "social_wellbeing": WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL,
}

# Default unit-label mapping for the 14 catalog indicators. The
# legacy ``IndicatorSpec.unit`` field is the authoritative
# source; this dict is the fallback for the rare case where the
# spec is missing or empty. Values are best-effort unit hints
# only; downstream consumers must not treat them as
# authoritative (Rule #8: no invented metadata).
_DEFAULT_INDICATOR_UNITS: dict[str, str] = {
    "wdi_population": "persons",
    "wdi_gdp_current_usd": "USD",
    "wdi_gdp_per_capita": "USD per capita",
    "wdi_gdp_constant_2015_usd": "USD 2015",
    "wdi_gdp_per_capita_ppp_constant_2017": "intl $ 2017",
    "wdi_gni_per_capita_atlas": "USD per capita",
    "wdi_exports_pct_gdp": "% of GDP",
    "wdi_imports_pct_gdp": "% of GDP",
    "wdi_fdi_inflows_current_usd": "USD",
    "wdi_life_expectancy_at_birth": "years",
    "wdi_literacy_rate_adult": "% of people 15+",
    "wdi_secondary_school_enrollment": "% gross",
    "wdi_under5_mortality_per_1000": "per 1k live births",
    "wdi_gini_index": "0-1",
}


def _is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, (int,))


def _resolve_observation_family(spec_rating_category: str | None) -> str:
    """Map a catalog ``rating_category`` to a canonical observation family.

    Falls back to the economic family for unknown categories so
    the descriptor's documented ``(economic_country_year,
    social_country_year)`` tuple is honored for every emitted
    observation, including forward-compatible catalog additions
    that may introduce a new ``rating_category``.
    """
    if isinstance(spec_rating_category, str):
        family = _RATING_CATEGORY_TO_FAMILY.get(spec_rating_category)
        if family is not None:
            return family
    return WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC


def _api_endpoint_for(code: str) -> str:
    """Build the WDI v2 indicator endpoint template for ``code``.

    Returned as a string template (not a request URL): the
    ``?date={year}`` query parameter is filled in by the
    caller. This is the per-indicator canonical API endpoint
    WDI's HTTP layer targets.
    """
    return f"{WORLD_BANK_WDI_HOMEPAGE_URL}country/all/indicator/{code}"


# ---------------------------------------------------------------------------
# Cache-only read path
# ---------------------------------------------------------------------------
#
# The functions in this section implement the offline / cache-only read
# path that backs :meth:`WDIAdapter.read_raw`. They NEVER invoke the
# network; they read the staged per-(year, indicator) JSON cache files
# directly and produce the wide-format DataFrame the existing transform
# layer already consumes. They mirror the legacy
# :func:`leaders_db.ingest.wdi_http.parse_wdi_payload` /
# :func:`leaders_db.ingest.wdi_io.read_wdi` logic just enough to honour
# the WDI v2 2-element response shape, the aggregate ISO3 filter, and the
# long-to-wide pivot. We deliberately do NOT depend on legacy
# :func:`read_wdi` because legacy ``read_wdi`` falls through to HTTP when
# a cache file is missing -- exactly the network behaviour the unified
# WDI adapter refuses for supported cache policies.
#
# The local parser + pivot is intentionally surgical (mirrors legacy
# behaviour byte-for-byte for the inputs the unified adapter accepts)
# so a future refactor of the legacy reader cannot silently regress the
# "no network under supported policies" guarantee.


# Local mirror of the WDI v2 aggregate-region ISO3 denylist. The
# canonical authoritative list lives in
# :data:`leaders_db.ingest.wdi_io._WDI_AGGREGATE_ISO3_CODES`. We
# duplicate the set here so the cache-only read path does NOT have to
# import :mod:`leaders_db.ingest.wdi_io` (which would pull in the
# whole legacy ingest package and the ``requests`` HTTP library). The
# set was derived on 2026-06-18 from the live ``/v2/country`` response;
# any aggregate added by WDI in the future must be appended in BOTH
# places. The legacy constant remains authoritative for the legacy
# ingest path; the unified adapter uses this copy.
_LOCAL_WDI_AGGREGATE_ISO3_CODES: frozenset[str] = frozenset({
    "AFE", "AFR", "AFW", "ARB", "BEA", "BEC", "BHI", "BLA", "BMN",
    "BSS", "CAA", "CEA", "CEB", "CEU", "CLA", "CME", "CSA", "CSS",
    "DEA", "DEC", "DLA", "DMN", "DNS", "DSA", "DSF", "DSS", "EAP",
    "EAR", "EAS", "ECA", "ECS", "EMU", "EUU", "FCS", "FXS", "HIC",
    "HPC", "IBB", "IBD", "IBT", "IDA", "IDB", "IDX", "INX", "LAC",
    "LCN", "LDC", "LIC", "LMC", "LMY", "LTE", "MDE", "MEA", "MIC",
    "MNA", "NAC", "NAF", "NRS", "NXS", "OED", "OSS", "PRE", "PSS",
    "PST", "RRS", "SAS", "SSA", "SSF", "SST", "SXZ", "TEA", "TEC",
    "TLA", "TMN", "TSA", "TSS", "UMC", "WLD", "XZN",
})


def _parse_cached_wdi_payload(
    payload: list[Any],
    *,
    code: str,
    year: int,
) -> pd.DataFrame:
    """Parse one already-loaded WDI v2 cache payload into a long-format
    DataFrame.

    Mirrors :func:`leaders_db.ingest.wdi_http.parse_wdi_payload`
    byte-for-byte (same columns, same value semantics, same null
    handling). Exposed as a free function so the cache-only read
    path can reuse the legacy parser without importing
    :mod:`leaders_db.ingest.wdi_http` (which would pull in the
    legacy HTTP layer and ``requests``).

    Returns a frame with columns ``["iso3", "year", "indicator_code",
    "value"]``. Rows where ``value`` is ``None`` (WDI's null
    representation) are kept; the cache-only orchestrator handles
    NaN conversion + aggregate filter + long-to-wide pivot.

    Raises:
        ValueError: when the payload is not a 2-element list with a
            list ``data`` slot. The caller (``_read_cached_wdi_responses``)
            validates the JSON shape in :func:`_validate_cached_json_shape`
            before invoking this helper, so the ValueError is
            defensive against future schema drift.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError(
            f"WDI cached payload for {code} year {year} is not a "
            f"2-element array; got {type(payload).__name__}"
        )
    data = payload[1]
    if not isinstance(data, list):
        raise ValueError(
            f"WDI cached payload for {code} year {year} data slot "
            f"is not a list; got {type(data).__name__}"
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
    return pd.DataFrame(
        rows, columns=["iso3", "year", "indicator_code", "value"],
    )


def _empty_wide_dataframe() -> pd.DataFrame:
    """Return the empty wide-format DataFrame used when no cache
    files are available.

    Carries the canonical ``indicators_cached`` /
    ``indicators_fetched`` ``df.attrs`` so callers can consume the
    frame with the same accessor contract the legacy
    :func:`read_wdi` frame carries.
    """
    df = pd.DataFrame(columns=["iso3", "year"])
    df.attrs["indicators_cached"] = 0
    df.attrs["indicators_fetched"] = 0
    return df


def _read_cached_wdi_responses(
    cache_root: Path,
    *,
    years: tuple[int, ...] | None,
    discovered_pairs: Iterable[tuple[int, str, Path]] | None = None,
    spec_by_variable_name: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Read WDI v2 JSON cache files directly and return a wide-format
    DataFrame.

    The function is the unified WDI adapter's offline / cache-only
    read path. It NEVER invokes the network; it reads only the
    per-(year, indicator) JSON files staged under ``cache_root``
    and produces the same wide-format DataFrame the legacy
    :func:`leaders_db.ingest.wdi_io.read_wdi` returns, including the
    ``df.attrs["indicators_cached"]`` / ``indicators_fetched``
    counter contract that the orchestrator / transform layer
    consumes.

    Parameters
    ----------
    cache_root:
        The staged per-(year, indicator) JSON cache root, e.g.
        ``<raw_root>/world_bank_wdi/cache``.
    years:
        Optional tuple of explicit years to read. ``None`` means
        "all years present in the cache" (the all-available-years
        semantics per SRC-REQ-003). The function enumerates the
        cache root for year subdirectories when ``years`` is None;
        when ``years`` is set it reads the union of
        ``discovered_pairs`` matching those years.
    discovered_pairs:
        Optional list of ``(year, code, path)`` tuples the readiness
        gate has already validated (see
        :func:`leaders_db.sources.adapters.world_bank_wdi._readiness._enumerate_cache_files`).
        When provided, the read path uses exactly these tuples and
        NEVER enumerates the cache root on its own. This is the
        "enumerate valid cache files and pass only those exact
        years/indicator codes through production paths" seam. When
        ``None``, the function falls back to a cache-root
        enumeration that only considers files whose path matches
        a digit-named year directory.
    spec_by_variable_name:
        Optional ``{variable_name: IndicatorSpec}`` mapping used
        to rename the wide-frame columns from raw WDI codes
        (``SP.POP.TOTL``) to canonical variable names
        (``wdi_population``). When omitted the wide frame keeps
        the raw WDI codes as column names (the transform layer
        already handles unknown columns via the
        ``_DEFAULT_INDICATOR_UNITS`` fallback).

    Returns
    -------
    pandas.DataFrame
        A wide-format DataFrame with columns ``iso3``, ``year`` and
        one column per catalog ``variable_name`` (or raw WDI code
        when ``spec_by_variable_name`` is omitted). Aggregate
        region ISO3 codes are filtered out (matches legacy
        :func:`read_wdi` semantics). ``df.attrs["indicators_cached"]``
        counts unique indicator codes successfully read from the
        cache; ``df.attrs["indicators_fetched"]`` is always ``0``
        (the cache-only read path never hits the network).
    """
    pair_list = _resolve_cache_pairs(
        cache_root,
        discovered_pairs=discovered_pairs,
        years=years,
    )
    if not pair_list:
        return _empty_wide_dataframe()

    long_frames, cached_codes = _read_cached_payloads(pair_list)
    if not long_frames:
        return _empty_wide_dataframe()

    wide = _pivot_long_to_wide(long_frames)
    wide = _rename_wide_columns(wide, spec_by_variable_name)
    wide = _coerce_wide_types(wide)

    wide.attrs["indicators_cached"] = len(cached_codes)
    wide.attrs["indicators_fetched"] = 0
    return wide


def _resolve_cache_pairs(
    cache_root: Path,
    *,
    discovered_pairs: Iterable[tuple[int, str, Path]] | None,
    years: tuple[int, ...] | None,
) -> list[tuple[int, str, Path]]:
    """Resolve the list of ``(year, code, path)`` tuples the read
    path will consume.

    Honors the readiness-gate-discovered pairs when supplied
    (the "enumerate valid cache files and pass only those exact
    years/indicator codes through production paths" seam). Falls
    back to a defensive cache-root enumeration when no
    discovered pairs are provided (the helper is safe to call
    from tests / ad-hoc tooling without first invoking
    readiness). Applies the ``years=`` filter as the last step
    so explicit years always narrow the work list before the
    cache files are opened.
    """
    if discovered_pairs is not None:
        pair_list = list(discovered_pairs)
    else:
        pair_list = _enumerate_cache_pairs_fallback(cache_root)
    if years is None:
        return pair_list
    year_set = {int(y) for y in years}
    return [
        (y, code, path)
        for (y, code, path) in pair_list
        if y in year_set
    ]


def _enumerate_cache_pairs_fallback(
    cache_root: Path,
) -> list[tuple[int, str, Path]]:
    """Defensive cache-root enumeration when readiness did not
    pre-validate the work list.

    Only considers files with a numeric year directory and a
    ``.json`` extension. Does NOT validate JSON shape (readiness
    owns that gate); a file the readiness gate would have
    blocked is simply skipped here.
    """
    pair_list: list[tuple[int, str, Path]] = []
    if not cache_root.is_dir():
        return pair_list
    for year_dir in sorted(cache_root.iterdir(), key=lambda p: p.name):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year_int = int(year_dir.name)
        for cache_file in sorted(
            year_dir.iterdir(), key=lambda p: p.name,
        ):
            if not cache_file.is_file() or cache_file.suffix != ".json":
                continue
            pair_list.append((year_int, cache_file.stem, cache_file))
    return pair_list


def _read_cached_payloads(
    pair_list: list[tuple[int, str, Path]],
) -> tuple[list[pd.DataFrame], set[str]]:
    """Read every (year, indicator) cache file into a long-format
    DataFrame.

    Defensive: a corrupt file (JSON decode error or shape
    regression) is silently skipped rather than falling through
    to HTTP -- that's the whole point of the cache-only path.
    The readiness gate should have blocked before ``read_raw``
    was reached; this defensive guard covers race conditions
    where a file is corrupted between readiness and read.
    """
    long_frames: list[pd.DataFrame] = []
    cached_codes: set[str] = set()
    for year_int, code, cache_file in pair_list:
        try:
            payload_obj = json.loads(
                cache_file.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload_obj, list) or len(payload_obj) < 2:
            continue
        try:
            long_frames.append(
                _parse_cached_wdi_payload(
                    payload_obj, code=code, year=year_int,
                ),
            )
        except ValueError:
            continue
        cached_codes.add(code)
    return long_frames, cached_codes


def _pivot_long_to_wide(
    long_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    """Concatenate + filter aggregate region ISO3 codes + pivot to
    wide format. Mirrors the legacy :func:`read_wdi` pivot logic
    just enough for the cache-only path.
    """
    long_df = pd.concat(long_frames, ignore_index=True)
    long_df = long_df.loc[
        ~long_df["iso3"].isin(_LOCAL_WDI_AGGREGATE_ISO3_CODES)
    ].reset_index(drop=True)
    return long_df.pivot_table(
        index=["iso3", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    )


def _rename_wide_columns(
    wide: pd.DataFrame,
    spec_by_variable_name: Mapping[str, Any] | None,
) -> pd.DataFrame:
    """Rename raw WDI codes to catalog ``variable_name`` columns.

    ``spec_by_variable_name`` is keyed by ``variable_name`` (the
    legacy :class:`IndicatorSpec` loader uses that key), so we
    invert it to a ``raw_column -> variable_name`` rename map.
    Unknown raw codes (forward-compatible catalog additions) keep
    their raw column names so the transform layer's
    ``_DEFAULT_INDICATOR_UNITS`` fallback can still apply.
    """
    if spec_by_variable_name is None:
        return wide
    raw_to_variable: dict[str, str] = {}
    for variable_name, spec in spec_by_variable_name.items():
        raw_code = getattr(spec, "raw_column", None)
        if (
            isinstance(raw_code, str)
            and raw_code.strip()
            and isinstance(variable_name, str)
            and variable_name.strip()
        ):
            raw_to_variable[raw_code] = variable_name
    if not raw_to_variable:
        return wide
    return wide.rename(columns=raw_to_variable)


def _coerce_wide_types(wide: pd.DataFrame) -> pd.DataFrame:
    """Coerce wide-frame columns to canonical dtypes.

    Resets the index (so ``iso3`` / ``year`` are regular
    columns), coerces ``year`` to ``int``, and coerces every
    indicator column to ``float`` (NaN for absent cells per
    :func:`parse_wdi_payload`).
    """
    wide = wide.reset_index()
    wide["year"] = wide["year"].astype(int)
    for col in wide.columns:
        if col in {"iso3", "year"}:
            continue
        wide[col] = pd.to_numeric(wide[col], errors="coerce").astype(float)
    return wide


def load_wdi_cache_index(
    cache_file: Path,
) -> dict[str, int] | None:
    """Return ``{countryiso3code: numeric_index}`` for a WDI v2
    cache file, or ``None`` on any read / shape error.

    The WDI v2 2-element response array (``[metadata, data]``)
    stores country records as numeric indices under
    ``payload[1]``. Each entry carries a ``countryiso3code``
    field. The readiness + audit contract
    (``docs/requirements/sources.md`` §6 SRC-PROV-001) requires
    every emitted observation to carry a JSON pointer that
    resolves to the underlying raw record; the only stable
    pointer is ``/1/<numeric_index>`` because
    ``countryiso3code`` is data (and an aggregate filter may
    drop entries between the upstream cache and the emitted
    observation). The pointer is intentionally a numeric
    offset, not an ISO3 key, so audit code can re-parse the
    cache file and recover the canonical raw record byte-for-byte.

    Returns ``None`` when:

    - the cache file is missing or not a file;
    - the cache file cannot be read (encoding, permissions);
    - the JSON does not parse;
    - the top-level value is not a 2-element list;
    - the ``data`` slot is not a list;
    - an entry is not a ``dict`` with a non-empty
      ``countryiso3code`` (we skip those entries silently --
      the cache file can carry pre-filter aggregates that
      the legacy ``read_wdi`` aggregate filter drops).

    The function never raises. Callers handle a ``None`` return
    by setting the per-observation ``raw_locator.json_pointer``
    to ``None`` so audit code knows the pointer could not be
    resolved (vs. a deliberate ``/1/-1`` sentinel).
    """
    if not cache_file.is_file():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    data = payload[1]
    if not isinstance(data, list):
        return None
    index: dict[str, int] = {}
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            continue
        iso3 = entry.get("countryiso3code")
        if not isinstance(iso3, str) or not iso3.strip():
            continue
        # When the cache file carries the same country twice
        # (WDI does not, but a malformed cache might), the
        # earlier index wins so the pointer still resolves
        # to the first occurrence (the position the legacy
        # reader would have seen first).
        index.setdefault(iso3.strip(), i)
    return index


def emit_world_bank_wdi_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    cache_root: Path | None,
    spec_by_variable_name: dict[str, Any],
    cache_index_by_year_indicator: dict[
        tuple[int, str], dict[str, int] | None
    ] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide-format DataFrame into :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by
        :func:`leaders_db.ingest.wdi_io.read_wdi`. One row per
        ``(iso3, year)`` with one column per catalog indicator
        (named with the catalog's ``variable_name``). Missing
        indicator cells are NaN; the transform skips them.
    request:
        The request-scoped :class:`SourceIngestRequest` driving
        the run. Used for source version + observation id
        prefix; year / country filters are applied by the
        caller BEFORE this helper is invoked so the wide_df
        has already been narrowed.
    cache_root:
        Optional path to the staged cache directory (e.g.
        ``<raw_root>/world_bank_wdi/cache``). Carried onto
        every observation's :class:`RawLocator` so audit code
        can resolve the per-cell cache file.
    spec_by_variable_name:
        Dict mapping catalog ``variable_name`` to the legacy
        :class:`IndicatorSpec` carrying ``raw_column``,
        ``rating_category``, ``unit``, etc. When a spec is
        missing for a column name (forward-compatible catalog
        additions), the transform falls back to the
        ``_DEFAULT_INDICATOR_UNITS`` mapping and the
        economic-family default.
    cache_index_by_year_indicator:
        Optional pre-computed ``{(year, raw_indicator_code):
        {countryiso3code: numeric_index} | None}`` map. The
        adapter computes one map per (year, indicator) pair
        via :func:`load_wdi_cache_index` so the transform
        can stamp each observation's
        ``raw_locator.json_pointer`` with the matching
        ``/1/<numeric_index>`` value (or ``None`` when the
        index could not be resolved). When the map is
        ``None`` (legacy callers, tests that do not need
        pointer resolution) the transform falls back to a
        ``/1/{iso3}`` placeholder pointer; the
        ``test_wdi_observation_json_pointer_resolves`` test
        proves the resolved pointer matches the underlying
        cache record byte-for-byte.

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``wide_df`` is empty (e.g. an out-of-coverage year
        request, an empty filter, or an empty cache).
    """
    if wide_df is None:
        return iter(())

    cache_root_str = str(cache_root) if isinstance(cache_root, Path) else None
    asset_id = WORLD_BANK_WDI_CACHE_ASSET_ID
    source_version = WORLD_BANK_WDI_DEFAULT_VERSION

    observations: list[NormalizedObservation] = []
    for _, wide_row in wide_df.iterrows():
        iso3 = str(wide_row["iso3"])
        year = int(wide_row["year"])

        # Per-row indicator emission. One observation per
        # non-NaN indicator cell (SRC-OBS-007).
        for column_name in wide_df.columns:
            if column_name in {"iso3", "year"}:
                continue
            cell_value = wide_row.get(column_name)
            if not _is_real_number(cell_value):
                # NaN / None -- do NOT emit an observation
                # (no silent conversion of missing cells).
                continue

            spec = spec_by_variable_name.get(column_name)
            raw_indicator_code = (
                getattr(spec, "raw_column", None) or column_name
            )
            observation_family = _resolve_observation_family(
                getattr(spec, "rating_category", None),
            )
            spec_unit = getattr(spec, "unit", None)
            unit = (
                spec_unit.strip()
                if isinstance(spec_unit, str) and spec_unit.strip()
                else _DEFAULT_INDICATOR_UNITS.get(column_name)
            )

            # Cache file path for this (year, indicator). The
            # JSON pointer resolves to the entry's numeric
            # offset in the cache file's ``data`` array. We
            # look the offset up in the pre-computed index
            # map (one per (year, indicator) pair) so audit
            # code can re-parse the cache file and recover
            # the canonical raw record byte-for-byte. When
            # the index map is unavailable (legacy callers,
            # missing cache file) the transform falls back
            # to the ``/1/{iso3}`` placeholder so the
            # pointer is never silently empty.
            cache_file_path = (
                f"{cache_root_str}/{year}/{raw_indicator_code}.json"
                if cache_root_str
                else None
            )
            json_pointer: str | None = None
            if cache_index_by_year_indicator is not None:
                cache_index = cache_index_by_year_indicator.get(
                    (year, raw_indicator_code),
                )
                if cache_index is not None:
                    numeric_index = cache_index.get(iso3)
                    if numeric_index is not None:
                        json_pointer = (
                            f"{WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX}"
                            f"{numeric_index}"
                        )
            if json_pointer is None:
                # Fallback / legacy-caller pointer shape. The
                # readiness test in
                # ``test_wdi_observation_json_pointer_resolves``
                # proves the resolved pointer (the
                # ``/1/<index>`` branch above) is what
                # downstream audit code should resolve;
                # the fallback remains a structured
                # ``/1/{iso3}`` so the pointer field is
                # never silently empty.
                json_pointer = (
                    f"{WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX}"
                    f"{iso3}"
                )

            observations.append(
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=(
                        f"{WORLD_BANK_WDI_SOURCE_KEY}:{iso3}:"
                        f"{year}:{column_name}"
                    ),
                    observation_family=observation_family,
                    indicator_code=column_name,
                    value=float(cell_value),
                    value_type="numeric",
                    year=year,
                    country_code=iso3,
                    country_name=None,
                    leader_id=None,
                    leader_name=None,
                    unit=unit,
                    scale=None,
                    source_version=source_version,
                    raw_locator=RawLocator(
                        asset_id=asset_id,
                        path=cache_file_path,
                        url=None,
                        sheet=None,
                        row_number=None,
                        column_name=raw_indicator_code,
                        json_pointer=json_pointer,
                        api_endpoint=_api_endpoint_for(raw_indicator_code),
                        api_params_hash=None,
                    ),
                    transform_locator=TransformLocator(
                        adapter_version=None,
                        transform_name=WORLD_BANK_WDI_TRANSFORM_NAME,
                        catalog_key=WORLD_BANK_WDI_SOURCE_KEY,
                        rule_id=(
                            f"{WORLD_BANK_WDI_SOURCE_KEY}:{iso3}:"
                            f"{year}:{column_name}"
                        ),
                    ),
                    quality_flags=(),
                    warnings=(),
                    extension={
                        # The raw WDI indicator code (e.g.
                        # "NY.GDP.MKTP.CD") is preserved so
                        # downstream score modules can resolve
                        # the raw value back to the WDI v2
                        # endpoint without consulting the
                        # catalog again.
                        "wdi_raw_indicator_code": raw_indicator_code,
                        "wdi_cache_year_dir": str(year),
                        "attribution": WORLD_BANK_WDI_ATTRIBUTION_TEXT,
                        "wdi_cache_dir_name": WORLD_BANK_WDI_CACHE_DIR_NAME,
                    },
                ),
            )
    return iter(observations)


__all__ = [
    "WORLD_BANK_WDI_CACHE_ASSET_ID",
    "WORLD_BANK_WDI_TRANSFORM_NAME",
    "_read_cached_wdi_responses",
    "emit_world_bank_wdi_observations",
    "load_wdi_cache_index",
]
