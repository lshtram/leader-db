"""Row builder for the Country-Year Chronicle slice.

The row builder composes the per-(iso3, year) dict that the CSV writer
turns into one CSV row. It is pure: no I/O, no logging side effects,
no shared mutable state. Every dependency is passed in.

Public entry point: :func:`build_chronicle_rows`. The supporting
helpers live in focused sibling modules:

- :mod:`._formatters` — value-coercion helpers
  (``coerce_int``, ``coerce_float``, ``safe_int``,
  ``empty_row_template``).
- :mod:`._flags` — flag tuple assembly
  (:func:`assemble_flags`).
- :mod:`._economy_fields` — Maddison + WDI population / GDP /
  per-capita column population (:func:`populate_economy_fields`).
- :mod:`._provenance` — row-level row_confidence /
  provenance_summary assembly
  (:func:`populate_provenance_and_flags`).
- :mod:`._row_identity` — year / iso3 / country / status columns
  (:func:`populate_identity`, :func:`derive_country_status`).
- :mod:`._row_ruler` — ruler-column population
  (:func:`populate_ruler_placeholder`,
  :func:`populate_ruler_fields`).
- :mod:`._row_regime` — political-regime + system-type columns
  (:func:`populate_regime`, :func:`populate_system_type`).
- :mod:`._row_sipri` — SIPRI military-spend columns
  (:func:`populate_sipri_fields`).
- :mod:`._row_area` — area / controlled-area columns
  (:func:`populate_area_placeholders`,
  :func:`populate_area_fields`).
- :mod:`ruler_resolver` — provenance-aware ruler resolver
  (:func:`load_ruler_resolver`, :class:`RulerResolver`).
- :mod:`._area_source` — CShapes 2.0 area loader
  (:class:`CShapesSource`, :func:`load_cshapes_source`).

Increment 2 changes:

- Maddison Project Database 2023 is integrated into the economy
  fields with the documented precedence (Maddison preferred for
  1900-2022; WDI preferred for 2023+; Maddison 2022 used as a
  1-year-gap proxy for 2023 only when WDI is missing).
- A narrow read-only ruler resolver (Archigos + REIGN, no client
  matrix, no LLM) populates the ruler columns. Rows that the
  resolver cannot resolve keep the ``missing_ruler`` flag and the
  row builder no longer hard-codes ``missing_ruler`` for every row.

Increment 3 changes:

- CShapes 2.0 is integrated as the country-area source. Years
  within CShapes coverage (1886-2019) emit ``country_area_km2``
  from the exact-match row. Years past coverage (2020+) copy the
  most recent CShapes row and emit ``area_proxy_year_used``.
- A curated, Wikipedia-anchored Soviet-leaders spell list is
  integrated into the ruler resolver, so SUN rows 1922-1991 carry
  real leader names (Lenin, Stalin, Malenkov, Khrushchev,
  Brezhnev, Andropov, Chernenko, Gorbachev) with
  ``multiple_rulers`` for the documented transition years.
- ``controlled_area_km2`` is populated with the conservative
  fallback value ``country_area_km2`` when country area is
  available; the ``controlled_area_country_only`` flag is added
  on top of ``controlled_area_not_modeled`` so the audit trail
  records both facts.

Reviewer-gate follow-up (Increment 3):

- The five ``_populate_*`` helper clusters were extracted into
  focused sibling modules (:mod:`._row_identity`,
  :mod:`._row_ruler`, :mod:`._row_regime`, :mod:`._row_sipri`,
  :mod:`._row_area`) so this module stays comfortably below the
  400-line convention. Public import path
  ``leaders_db.chronicle.row_builder.build_chronicle_rows`` is
  preserved unchanged across the split.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._economy_fields import populate_economy_with_proxy
from ._formatters import empty_row_template
from ._provenance import populate_provenance_and_flags
from ._row_area import populate_area_fields
from ._row_identity import populate_identity
from ._row_regime import populate_regime, populate_system_type
from ._row_ruler import populate_ruler_fields
from ._row_sipri import populate_sipri_fields
from .constants import (
    DEFAULT_PROXY_YEAR,
    FLAG_MULTIPLE_RULERS,
    FLAG_PROXY_YEAR_USED,
    SOURCE_TAG_SIPRI,
    VDEM_MAX_COVERED_YEAR,
)
from .ruler_resolver import RulerResolver
from .sources import (
    MaddisonSource,
    RegimeSource,
    SipriSource,
    VDemSource,
    WdiSource,
)

if TYPE_CHECKING:
    from ._area_source import CShapesSource
    from .regime import RegimeBucketResult
    from .system_type import SystemTypeResult

# Re-export so callers can pull :class:`CShapesSource` from
# ``row_builder`` without an extra import line. The symbol itself
# lives in :mod:`._area_source`; this keeps the public surface stable.
from ._area_source import CShapesSource


@dataclass(frozen=True)
class _RowDeps:
    """Bundle of source dependencies for the row builder.

    Passing a frozen dataclass instead of 4+ positional args keeps the
    call sites short and explicit. Frozen so the row builder cannot
    accidentally mutate a shared loader.
    """

    vdem: VDemSource
    wdi: WdiSource
    sipri: SipriSource
    maddison: MaddisonSource | None
    ruler_resolver: RulerResolver
    cshapes: CShapesSource | None
    regime: RegimeSource
    regime_bucket: RegimeBucketResult
    system_type: SystemTypeResult


def _build_one_row(
    *, iso3: str, year: int, deps: _RowDeps
) -> dict[str, str]:
    """Build the dict for a single ``(iso3, year)`` pair.

    The function is private; callers must use
    :func:`build_chronicle_rows` so the cross-row invariants (column
    set, flag order) are enforced once.
    """
    row = empty_row_template()
    populate_identity(row, iso3, year)
    ruler = deps.ruler_resolver.resolve(iso3, year)
    populate_ruler_fields(row, ruler)
    populate_regime(row, deps.regime_bucket)
    populate_system_type(row, deps.system_type)

    has_population, has_gdp, maddison_is_proxy = populate_economy_with_proxy(
        row,
        iso3=iso3,
        year=year,
        wdi=deps.wdi,
        maddison=deps.maddison,
    )
    has_maddison = bool(
        row.get("population_source") == "maddison_project"
        or row.get("gdp_source") == "maddison_project"
    )

    sipri_values = deps.sipri.lookup(iso3, year)
    has_sipri = populate_sipri_fields(row, sipri_values, year=year)

    has_area, controlled_area_country_only, area_proxy_used = (
        populate_area_fields(row, iso3=iso3, year=year, cshapes=deps.cshapes)
    )

    extra_flags: tuple[str, ...] = ()
    if ruler.multiple_rulers:
        extra_flags = (*extra_flags, FLAG_MULTIPLE_RULERS)
    if maddison_is_proxy:
        extra_flags = (*extra_flags, FLAG_PROXY_YEAR_USED)
    populate_provenance_and_flags(
        row,
        iso3=iso3,
        year=year,
        bucket=deps.regime_bucket,
        st=deps.system_type,
        has_population=has_population,
        has_gdp=has_gdp,
        has_sipri=has_sipri,
        has_maddison=has_maddison,
        has_ruler=ruler.has_ruler,
        has_area=has_area,
        controlled_area_country_only=controlled_area_country_only,
        area_proxy_used=area_proxy_used,
        extra_flags=extra_flags,
    )
    return row


def build_chronicle_rows(
    *,
    iso3_scope: tuple[str, ...],
    start_year: int,
    end_year: int,
    vdem: VDemSource,
    wdi: WdiSource,
    sipri: SipriSource,
    maddison: MaddisonSource | None = None,
    ruler_resolver: RulerResolver | None = None,
    cshapes: CShapesSource | None = None,
    allow_regime_proxy: bool = True,
) -> list[dict[str, str]]:
    """Build the full row list for the chronicle run.

    The row order is deterministic: iso3 in the caller's order, year
    ascending. One row per (iso3, year) pair is emitted regardless of
    whether any source has data for that pair; the row simply carries
    more ``missing_*`` flags.

    Parameters
    ----------
    iso3_scope:
        ISO3 keys to include, in the order to emit.
    start_year:
        First year (inclusive).
    end_year:
        Last year (inclusive).
    vdem, wdi, sipri:
        Pre-loaded source loaders.
    maddison:
        Optional Maddison Project source. When ``None`` the row
        builder behaves exactly like the Increment 1 pilot (no
        Maddison-backed economy fields); this keeps the older
        fixtures and tests valid.
    ruler_resolver:
        Optional ruler resolver. When ``None`` the row builder
        emits the Increment 1 placeholder for every row (no ruler
        columns populated, ``missing_ruler`` flag set). When a
        resolver is provided the row builder uses
        :func:`RulerResolver.resolve` per ``(iso3, year)`` pair.
    cshapes:
        Optional CShapes 2.0 source. When ``None`` the row builder
        uses the Increment 1 area placeholder (no area columns
        populated, ``missing_area`` flag set). When provided, the
        row builder populates ``country_area_km2`` from CShapes and
        sets the conservative ``controlled_area_km2`` fallback.
    allow_regime_proxy:
        When True, the row builder accepts the 2025 V-Dem proxy for
        years beyond V-Dem coverage (2026 today) and tags those rows
        with ``proxy_year_used``. When False, the row builder emits
        ``Unknown`` + ``regime_source_gap`` for any year beyond
        V-Dem's coverage regardless of how close the proxy year is.
        Defaults to True per Increment 0 §5.1.
    """
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) must be <= end_year ({end_year})"
        )

    effective_ruler_resolver = (
        ruler_resolver
        if ruler_resolver is not None
        else RulerResolver()
    )

    rows: list[dict[str, str]] = []
    for iso3 in iso3_scope:
        for year in range(start_year, end_year + 1):
            regime_source = RegimeSource.from_vdem_lookup(vdem, iso3, year)
            # If the caller did not opt in to the proxy, downgrade any
            # proxy match to a no-match so the bucket lands in Unknown.
            if not allow_regime_proxy and regime_source.is_proxy:
                regime_source = RegimeSource(
                    regime=None,
                    polyarchy=None,
                    libdem=None,
                    source_year_used=year,
                    is_proxy=False,
                )
            # Lazy import to avoid the regime/system_type dependency
            # cycle in tests that import only ``row_builder``.
            from .regime import derive_regime_bucket
            from .system_type import classify_system_type

            bucket = derive_regime_bucket(regime_source)
            system_type = classify_system_type(
                iso3=iso3,
                year=year,
                regime_bucket=bucket.bucket,
            )
            deps = _RowDeps(
                vdem=vdem,
                wdi=wdi,
                sipri=sipri,
                maddison=maddison,
                ruler_resolver=effective_ruler_resolver,
                cshapes=cshapes,
                regime=regime_source,
                regime_bucket=bucket,
                system_type=system_type,
            )
            rows.append(_build_one_row(iso3=iso3, year=year, deps=deps))
    return rows


# Re-export the proxy constant so callers do not have to import the
# sources module just to look up the proxy year.
__all__ = [
    "DEFAULT_PROXY_YEAR",
    "SOURCE_TAG_SIPRI",
    "VDEM_MAX_COVERED_YEAR",
    "CShapesSource",
    "build_chronicle_rows",
]
