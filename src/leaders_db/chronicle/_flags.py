"""Flag assembly for the Country-Year Chronicle row builder.

The row's ``data_quality_flags`` column is a deterministic,
deduplicated, ordered tuple of flag strings. Building that tuple
combines three inputs:

- country metadata (pre-existence gap, post-existence gap,
  successor-state, colonial-status-issue, controlled-area);
- the regime / system-type modules' own flag lists;
- field-level missing flags driven by the source lookup results.

This module owns the assembly so the row builder can stay focused
on row composition. The order is fixed; the CSV output is
byte-identical across runs.
"""

from __future__ import annotations

from ._formatters import safe_int
from .constants import (
    COUNTRY_METADATA,
    FLAG_COLONIAL_STATUS_ISSUE,
    FLAG_CONTROLLED_AREA_NOT_MODELED,
    FLAG_MISSING_AREA,
    FLAG_MISSING_GDP,
    FLAG_MISSING_MILITARY_SPEND,
    FLAG_MISSING_POPULATION,
    FLAG_MISSING_RULER,
    FLAG_POST_EXISTENCE_GAP,
    FLAG_PRE_EXISTENCE_GAP,
    FLAG_SUCCESSOR_STATE_ISSUE,
)
from .regime import RegimeBucketResult
from .system_type import SystemTypeResult


def assemble_flags(
    *,
    iso3: str,
    year: int,
    regime_bucket: RegimeBucketResult,
    system_type: SystemTypeResult,
    has_population: bool,
    has_gdp: bool,
    has_sipri: bool,
    has_ruler: bool,
) -> tuple[str, ...]:
    """Build the deduplicated, deterministic flag tuple for one row.

    Order:

        1. pre-existence / post-existence / successor_state / colonial
           status flags (from country metadata).
        2. ``proxy_year_used`` (when the regime value came from the
           proxy year).
        3. ``regime_source_gap`` / ``system_type_low_confidence``
           (added by the regime / system_type modules).
        4. ``missing_population`` / ``missing_gdp`` /
           ``missing_military_spend`` / ``missing_area`` /
           ``missing_ruler`` (when the source had no value).
        5. ``controlled_area_not_modeled`` (always for Increment 1).
    """
    flags: list[str] = []
    seen: set[str] = set()

    def add(flag: str) -> None:
        if flag and flag not in seen:
            flags.append(flag)
            seen.add(flag)

    metadata = COUNTRY_METADATA.get(iso3, {})
    start_year = safe_int(metadata.get("start_year"))
    end_year = safe_int(metadata.get("end_year"))
    colonial_until = safe_int(metadata.get("colonial_status_until"))
    country_status = metadata.get("country_status", "")

    # Pre-existence gap.
    if start_year is not None and year < start_year:
        add(FLAG_PRE_EXISTENCE_GAP)
    # Post-existence gap (only meaningful when end_year is set).
    if end_year is not None and year > end_year:
        add(FLAG_POST_EXISTENCE_GAP)
    # Successor-state / colonial issues from country metadata.
    if country_status == "successor_state":
        add(FLAG_SUCCESSOR_STATE_ISSUE)
    if (
        country_status == "independent"
        and colonial_until is not None
        and year <= colonial_until
    ):
        add(FLAG_COLONIAL_STATUS_ISSUE)
    # Controlled area is always flagged as not modeled in Increment 1.
    add(FLAG_CONTROLLED_AREA_NOT_MODELED)

    # Regime flags.
    for flag in regime_bucket.flags:
        add(flag)

    # System-type flags.
    for flag in system_type.flags:
        add(flag)

    # Field-level missing flags.
    if not has_population:
        add(FLAG_MISSING_POPULATION)
    if not has_gdp:
        add(FLAG_MISSING_GDP)
    if not has_sipri:
        add(FLAG_MISSING_MILITARY_SPEND)
    add(FLAG_MISSING_AREA)
    if not has_ruler:
        add(FLAG_MISSING_RULER)

    return tuple(flags)


__all__ = ["assemble_flags"]
