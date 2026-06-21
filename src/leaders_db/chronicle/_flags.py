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
    FLAG_AREA_PROXY_YEAR_USED,
    FLAG_COLONIAL_STATUS_ISSUE,
    FLAG_CONTROLLED_AREA_COUNTRY_ONLY,
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
    has_area: bool,
    controlled_area_country_only: bool,
    area_proxy_used: bool,
    extra_flags: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Build the deduplicated, deterministic flag tuple for one row.

    Order:

        1. pre-existence / post-existence / successor_state / colonial
           status flags (from country metadata).
        2. ``area_proxy_year_used`` (when the area value came from a
           CShapes proxy year because the requested year is beyond
           CShapes 2.0 coverage).
        3. ``proxy_year_used`` (when the regime value came from the
           proxy year).
        4. ``regime_source_gap`` / ``system_type_low_confidence``
           (added by the regime / system_type modules).
        5. Field-level missing flags
           (``missing_population`` / ``missing_gdp`` /
           ``missing_military_spend`` / ``missing_area`` /
           ``missing_ruler``).
        6. ``controlled_area_not_modeled`` (always emitted; imperial
           summing is deferred per the Increment 4 work item).
           ``controlled_area_country_only`` is added on top when the
           conservative controlled-area fallback (controlled == country)
           is used for the row.
        7. ``extra_flags`` in the caller's order (used by the
           Maddison proxy path and the multi-ruler ruler resolver
           to inject ``proxy_year_used`` / ``multiple_rulers``).
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
    # Area proxy flag (Increment 3): when CShapes coverage ends but
    # the requested year is later, the area was copied from the most
    # recent CShapes year and tagged with ``area_proxy_year_used``.
    if area_proxy_used:
        add(FLAG_AREA_PROXY_YEAR_USED)

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
    if not has_area:
        add(FLAG_MISSING_AREA)
    if not has_ruler:
        add(FLAG_MISSING_RULER)

    # Controlled-area handling. The conservative fallback is the
    # default behavior: ``controlled_area_not_modeled`` is emitted
    # unconditionally because imperial / dependency summing is
    # deferred per Increment 4. When the controlled area was filled
    # with the country-area value as a no-dependencies fallback,
    # ``controlled_area_country_only`` is added on top of
    # ``controlled_area_not_modeled`` so the audit trail records
    # both facts.
    add(FLAG_CONTROLLED_AREA_NOT_MODELED)
    if controlled_area_country_only:
        add(FLAG_CONTROLLED_AREA_COUNTRY_ONLY)

    # Caller-supplied extras (Maddison proxy / multiple rulers).
    for flag in extra_flags:
        add(flag)

    return tuple(flags)


__all__ = ["assemble_flags"]
