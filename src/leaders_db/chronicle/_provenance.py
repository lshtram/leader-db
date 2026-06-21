"""Row-level provenance + flag assembly for the Chronicle row builder.

The row's ``data_quality_flags``, ``row_confidence``, and
``provenance_summary`` columns are deterministic, deduplicated,
ordered outputs of the row builder. Building them combines three
inputs:

- field-level has_* booleans (population / GDP / SIPRI / Maddison
  / ruler);
- regime / system-type module flag lists;
- caller-supplied ``extra_flags`` (used by the Maddison proxy path
  and the multi-ruler ruler resolver).

This module owns the assembly so the row builder can stay focused
on per-row composition. The order is fixed; the CSV output is
byte-identical across runs.

Source-tag provenance. ``wdi_hit`` and ``maddison_hit`` are derived
from the per-field ``population_source`` / ``gdp_source`` tags
written by the economy-fields helper (not from the ``has_*``
booleans). This is critical: when Maddison alone populates a row
for a pre-1960 historical year, WDI is **not** a hit even though
``has_population=True`` and ``has_gdp=True``. Computing the hit
flag from booleans mis-attributes the evidence; computing it from
the source tag matches the audit trail.
"""

from __future__ import annotations

from ._flags import assemble_flags
from ._formatters import coerce_int
from .constants import SOURCE_TAG_MADDISON, SOURCE_TAG_WDI, WDI_DIRECT_CONFIDENCE
from .regime import RegimeBucketResult
from .system_type import SystemTypeResult


def compute_row_confidence(
    *,
    regime_confidence: int,
    system_type_confidence: int,
    has_wdi: bool,
    has_sipri: bool,
    has_maddison: bool,
    has_ruler: bool,
) -> int:
    """Compute the row_confidence aggregate (0-100).

    Per Increment 0 §6: ``row_confidence`` is a simple transparent
    aggregate of field-level availability/confidence, NOT the fixed
    0.35/0.25/0.25/0.15 formula. We compute:

        0.35 * regime_confidence
      + 0.25 * system_type_confidence
      + 0.13 * (WDI_DIRECT_CONFIDENCE if has_wdi else 0)
      + 0.10 * (WDI_DIRECT_CONFIDENCE if has_sipri else 0)
      + 0.10 * (WDI_DIRECT_CONFIDENCE if has_maddison else 0)
      + 0.07 * (WDI_DIRECT_CONFIDENCE if has_ruler else 0)

    Then clamp to 0..100. The Increment 2 weights split the
    field-source bucket into 4 equal components so the addition of
    Maddison + ruler does not dilute the regime / system-type
    contribution.
    """
    wdi_term = WDI_DIRECT_CONFIDENCE if has_wdi else 0
    sipri_term = WDI_DIRECT_CONFIDENCE if has_sipri else 0
    maddison_term = WDI_DIRECT_CONFIDENCE if has_maddison else 0
    ruler_term = WDI_DIRECT_CONFIDENCE if has_ruler else 0
    weighted = (
        0.35 * regime_confidence
        + 0.25 * system_type_confidence
        + 0.13 * wdi_term
        + 0.10 * sipri_term
        + 0.10 * maddison_term
        + 0.07 * ruler_term
    )
    return max(0, min(100, round(weighted)))


def _source_tag_hit(row: dict[str, str], tag: str) -> bool:
    """Return True if any of the row's per-field source tags equals ``tag``.

    Inspects the canonical ``*_source`` columns populated by the
    economy-fields helper (``population_source``, ``gdp_source``) and
    the ruler resolver (``ruler_source``). This is the audit-trail
    answer to "did source X contribute a value to this row?" and is
    NOT the same as the field-level ``has_*`` booleans.
    """
    if not row or not tag:
        return False
    for column in ("population_source", "gdp_source", "ruler_source"):
        value = row.get(column, "")
        if value == tag:
            return True
    return False


def wdi_hit_from_row(row: dict[str, str]) -> bool:
    """Return True iff the row carries a WDI source tag in any field."""
    return _source_tag_hit(row, SOURCE_TAG_WDI)


def maddison_hit_from_row(row: dict[str, str]) -> bool:
    """Return True iff the row carries a Maddison source tag in any field."""
    return _source_tag_hit(row, SOURCE_TAG_MADDISON)


def build_provenance_summary(
    *,
    regime_source: str,
    wdi_hit: bool,
    sipri_hit: bool,
    maddison_hit: bool,
    ruler_source: str,
    flags: tuple[str, ...],
) -> str:
    """Build the compact machine-readable provenance summary string.

    Format:
    ``regime=<tag>|wdi=<yes|no>|sipri=<yes|no>|maddison=<yes|no>|ruler=<tag|none>|flags=<csv>``.
    """
    return (
        f"regime={regime_source or 'none'}"
        f"|wdi={'yes' if wdi_hit else 'no'}"
        f"|sipri={'yes' if sipri_hit else 'no'}"
        f"|maddison={'yes' if maddison_hit else 'no'}"
        f"|ruler={ruler_source or 'none'}"
        f"|flags={','.join(flags) if flags else 'none'}"
    )


def populate_provenance_and_flags(
    row: dict[str, str],
    *,
    iso3: str,
    year: int,
    bucket: RegimeBucketResult,
    st: SystemTypeResult,
    has_population: bool,
    has_gdp: bool,
    has_sipri: bool,
    has_maddison: bool,
    has_ruler: bool,
    has_area: bool,
    controlled_area_country_only: bool,
    area_proxy_used: bool,
    extra_flags: tuple[str, ...] = (),
) -> None:
    """Assemble flags, row_confidence, and provenance_summary, then write them.

    The ``wdi_hit`` flag is derived from the row's per-field source
    tags (``population_source == "wdi"`` or ``gdp_source == "wdi"``),
    NOT from the ``has_population or has_gdp`` booleans. This is
    the audit-trail contract for the Increment 2 reviewer gate.
    Maddison alone populating a row does NOT make ``wdi=yes``.
    """
    flags = assemble_flags(
        iso3=iso3,
        year=year,
        regime_bucket=bucket,
        system_type=st,
        has_population=has_population,
        has_gdp=has_gdp,
        has_sipri=has_sipri,
        has_ruler=has_ruler,
        has_area=has_area,
        controlled_area_country_only=controlled_area_country_only,
        area_proxy_used=area_proxy_used,
        extra_flags=extra_flags,
    )
    wdi_hit = wdi_hit_from_row(row)
    row["data_quality_flags"] = "|".join(flags)
    row["row_confidence"] = coerce_int(
        compute_row_confidence(
            regime_confidence=bucket.confidence,
            system_type_confidence=st.confidence,
            has_wdi=wdi_hit,
            has_sipri=has_sipri,
            has_maddison=has_maddison,
            has_ruler=has_ruler,
        )
    )
    row["provenance_summary"] = build_provenance_summary(
        regime_source=bucket.source,
        wdi_hit=wdi_hit,
        sipri_hit=has_sipri,
        maddison_hit=has_maddison,
        ruler_source=row.get("ruler_source", ""),
        flags=flags,
    )


__all__ = [
    "build_provenance_summary",
    "compute_row_confidence",
    "maddison_hit_from_row",
    "populate_provenance_and_flags",
    "wdi_hit_from_row",
]
