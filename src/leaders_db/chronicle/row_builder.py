"""Row builder for the Country-Year Chronicle slice.

The row builder composes the per-(iso3, year) dict that the CSV writer
turns into one CSV row. It is pure: no I/O, no logging side effects,
no shared mutable state. Every dependency is passed in.

Public entry point: :func:`build_chronicle_rows`. The supporting
helpers live alongside:

- :mod:`._formatters` — value-coercion helpers
  (``coerce_int``, ``coerce_float``, ``safe_int``,
  ``empty_row_template``).
- :mod:`._flags` — flag tuple assembly
  (:func:`assemble_flags`).
- :mod:`._wdi_fields` — WDI population / GDP / per-capita column
  population (:func:`populate_wdi_fields`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._flags import assemble_flags
from ._formatters import (
    coerce_float,
    coerce_int,
    empty_row_template,
    safe_int,
)
from ._wdi_fields import populate_wdi_fields
from .constants import (
    COUNTRY_METADATA,
    DEFAULT_PROXY_YEAR,
    PLACEHOLDER_RULER_CONFIDENCE,
    SOURCE_NA,
    SOURCE_TAG_SIPRI,
    VDEM_MAX_COVERED_YEAR,
    WDI_DIRECT_CONFIDENCE,
)
from .regime import RegimeBucketResult
from .sources import RegimeSource, SipriSource, VDemSource, WdiSource
from .system_type import SystemTypeResult


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
    regime: RegimeSource
    regime_bucket: RegimeBucketResult
    system_type: SystemTypeResult


def _row_confidence(
    *,
    regime_confidence: int,
    system_type_confidence: int,
    has_wdi: bool,
    has_sipri: bool,
) -> int:
    """Compute a simple transparent availability-based aggregate.

    Per Increment 0 §6: ``row_confidence`` should initially be a simple
    transparent aggregate of field-level availability/confidence, NOT
    the fixed 0.35/0.25/0.25/0.15 formula. We compute:

        0.40 * regime_confidence
      + 0.30 * system_type_confidence
      + 0.15 * (WDI_DIRECT_CONFIDENCE if has_wdi else 0)
      + 0.15 * (SIPRI_DIRECT_CONFIDENCE if has_sipri else 0)

    Then clamp to 0..100. The weights are intentionally simple and
    transparent (different from the ruler-score formula).
    """
    wdi_term = WDI_DIRECT_CONFIDENCE if has_wdi else 0
    sipri_term = (
        # SIPRI milex direct confidence matches WDI by convention.
        WDI_DIRECT_CONFIDENCE
        if has_sipri
        else 0
    )
    weighted = (
        0.40 * regime_confidence
        + 0.30 * system_type_confidence
        + 0.15 * wdi_term
        + 0.15 * sipri_term
    )
    return max(0, min(100, round(weighted)))


def _provenance_summary(
    *,
    regime_source: str,
    wdi_hit: bool,
    sipri_hit: bool,
    flags: tuple[str, ...],
) -> str:
    """Build a short machine-readable provenance summary string.

    Format: ``regime=<tag>|wdi=<yes|no>|sipri=<yes|no>|flags=<csv>``.
    The summary is intentionally compact so a downstream filter can
    parse it deterministically.
    """
    return (
        f"regime={regime_source or 'none'}"
        f"|wdi={'yes' if wdi_hit else 'no'}"
        f"|sipri={'yes' if sipri_hit else 'no'}"
        f"|flags={','.join(flags) if flags else 'none'}"
    )


def _populate_identity(row: dict[str, str], iso3: str, year: int) -> None:
    """Populate year / iso3 / country metadata into the row in place.

    ``country_status`` is computed dynamically: when the country
    metadata declares a ``colonial_status_until`` year, years at or
    before that cutoff are emitted as ``colonial/dependent`` and
    later years fall back to the metadata's static
    ``country_status`` (typically ``independent``). This is how we
    keep IND's pre-1947 rows honest without duplicating the country
    record for British India — the same ISO3 spans both eras and the
    status flips at the documented cutoff.
    """
    metadata = COUNTRY_METADATA.get(iso3, {})
    row["year"] = coerce_int(year)
    row["iso3"] = iso3
    row["country_name"] = metadata.get("country_name", iso3)
    row["country_status"] = _derive_country_status(metadata, year)
    row["region"] = metadata.get("region", "")
    row["subregion"] = metadata.get("subregion", "")


def _derive_country_status(metadata: dict[str, str], year: int) -> str:
    """Compute ``country_status`` from the metadata + requested year.

    The default is the metadata's static ``country_status`` (usually
    ``independent`` or ``successor_state``). For countries with a
    ``colonial_status_until`` cutoff (currently just IND with
    ``colonial_status_until=1946``) the row flips to
    ``colonial/dependent`` for years at or before that cutoff, and
    back to the static value for later years. This keeps a single
    IND identity spanning the colonial/independent transition without
    inventing a new country record.
    """
    static_status = metadata.get("country_status", "unknown")
    colonial_until = safe_int(metadata.get("colonial_status_until"))
    if colonial_until is not None and year <= colonial_until:
        return "colonial/dependent"
    return static_status


def _populate_ruler_placeholder(row: dict[str, str]) -> None:
    """Populate the ruler fields with placeholder values + ``missing_ruler`` flag.

    The Increment 1 slice has no full ruler resolver; the columns are
    emitted empty with a 0-confidence placeholder so the CSV row is
    well-formed and downstream consumers can filter on the
    ``ruler_confidence`` field.
    """
    row["ruler_name"] = ""
    row["ruler_title"] = ""
    row["ruler_type"] = ""
    row["ruler_source"] = SOURCE_NA
    row["ruler_source_year_used"] = ""
    row["ruler_confidence"] = coerce_int(PLACEHOLDER_RULER_CONFIDENCE)
    row["shared_rule_flag"] = ""
    row["disputed_rule_flag"] = ""


def _populate_regime(row: dict[str, str], bucket: RegimeBucketResult) -> None:
    """Populate the political-regime columns from a :class:`RegimeBucketResult`."""
    row["political_regime_bucket"] = bucket.bucket
    row["political_regime_raw_score"] = bucket.raw_score
    row["political_regime_source"] = bucket.source
    row["political_regime_source_year_used"] = coerce_int(
        bucket.source_year_used
    )
    row["political_regime_confidence"] = coerce_int(bucket.confidence)


def _populate_system_type(row: dict[str, str], st: SystemTypeResult) -> None:
    """Populate the system-type columns from a :class:`SystemTypeResult`."""
    row["system_type_primary"] = st.primary
    row["system_type_secondary"] = st.secondary
    row["system_type_source"] = st.source
    row["system_type_confidence"] = coerce_int(st.confidence)
    row["system_type_notes"] = st.notes


def _populate_sipri_fields(
    row: dict[str, str],
    sipri_values: dict[str, float | None],
    *,
    year: int,
) -> bool:
    """Populate the SIPRI military-spend columns. Returns ``has_milex``.

    The ``missing_military_spend`` flag is driven **only** by the
    canonical CSV target field ``milex_constant_usd``. Ancillary
    SIPRI fields (per-capita, share-of-GDP) may be present in the
    lookup result but must not clear the flag on their own — the row
    builder treats them as supporting context, not as evidence that
    a usable military-spend value was found.
    """
    milex = sipri_values.get("milex_constant_usd")
    has_milex = milex is not None
    if has_milex:
        row["military_spend"] = coerce_float(milex, decimals=0)
        row["military_spend_unit"] = "constant_usd"
        row["military_spend_source"] = SOURCE_TAG_SIPRI
        row["military_spend_source_year_used"] = coerce_int(year)
    else:
        row["military_spend"] = ""
        row["military_spend_unit"] = ""
        row["military_spend_source"] = SOURCE_NA
        row["military_spend_source_year_used"] = ""
    return has_milex


def _populate_area_placeholders(row: dict[str, str]) -> None:
    """Populate the area / controlled-area columns with the Increment 1 placeholders."""
    row["country_area_km2"] = ""
    row["controlled_area_km2"] = ""
    row["area_source"] = SOURCE_NA
    row["area_source_year_used"] = ""
    row["controlled_area_note"] = (
        "controlled_area not modeled in Increment 1; standard area empty "
        "pending a vetted static area source."
    )


def _populate_provenance_and_flags(
    row: dict[str, str],
    *,
    iso3: str,
    year: int,
    bucket: RegimeBucketResult,
    st: SystemTypeResult,
    has_population: bool,
    has_gdp: bool,
    has_sipri: bool,
) -> None:
    """Assemble flags, row_confidence, and provenance_summary, then write them."""
    flags = assemble_flags(
        iso3=iso3,
        year=year,
        regime_bucket=bucket,
        system_type=st,
        has_population=has_population,
        has_gdp=has_gdp,
        has_sipri=has_sipri,
        has_ruler=False,
    )
    row["data_quality_flags"] = "|".join(flags)
    row["row_confidence"] = coerce_int(
        _row_confidence(
            regime_confidence=bucket.confidence,
            system_type_confidence=st.confidence,
            has_wdi=has_population or has_gdp,
            has_sipri=has_sipri,
        )
    )
    row["provenance_summary"] = _provenance_summary(
        regime_source=bucket.source,
        wdi_hit=has_population or has_gdp,
        sipri_hit=has_sipri,
        flags=flags,
    )


def _build_one_row(
    *, iso3: str, year: int, deps: _RowDeps
) -> dict[str, str]:
    """Build the dict for a single ``(iso3, year)`` pair.

    The function is private; callers must use
    :func:`build_chronicle_rows` so the cross-row invariants (column
    set, flag order) are enforced once.
    """
    row = empty_row_template()
    _populate_identity(row, iso3, year)
    _populate_ruler_placeholder(row)
    _populate_regime(row, deps.regime_bucket)
    _populate_system_type(row, deps.system_type)

    wdi_values = deps.wdi.lookup(iso3, year)
    has_population, has_gdp = populate_wdi_fields(row, wdi_values, year=year)

    sipri_values = deps.sipri.lookup(iso3, year)
    has_sipri = _populate_sipri_fields(row, sipri_values, year=year)

    _populate_area_placeholders(row)
    _populate_provenance_and_flags(
        row,
        iso3=iso3,
        year=year,
        bucket=deps.regime_bucket,
        st=deps.system_type,
        has_population=has_population,
        has_gdp=has_gdp,
        has_sipri=has_sipri,
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
    "VDEM_MAX_COVERED_YEAR",
    "build_chronicle_rows",
]
