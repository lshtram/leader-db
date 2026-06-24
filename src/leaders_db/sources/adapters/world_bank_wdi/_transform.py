"""Unified-source World Bank WDI observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation` build
loop for the unified-source WDI adapter. The function takes the
legacy wide-format DataFrame returned by
:func:`leaders_db.ingest.wdi_io.read_wdi` (one row per
``(iso3, year)`` with one column per catalog indicator named with
the canonical ``variable_name``) and emits the canonical
observation records with raw locators, transform locators,
attribution text, and column-specific unit labels.

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

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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


def emit_world_bank_wdi_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    cache_root: Path | None,
    spec_by_variable_name: dict[str, Any],
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
            # json_pointer is the offset of the country's entry
            # inside the cache file's ``data`` array. We
            # cannot resolve the offset without re-parsing the
            # cache file; we record a structured pointer
            # ``/1/{country_iso3_or_index}`` so audit code can
            # re-parse to find the exact entry.
            cache_file_path = (
                f"{cache_root_str}/{year}/{raw_indicator_code}.json"
                if cache_root_str
                else None
            )
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
    "emit_world_bank_wdi_observations",
]
