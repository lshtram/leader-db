"""Unified-source Polity V observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified-source Polity V adapter. The
function takes the wide-format country-year DataFrame returned
by :func:`leaders_db.sources.adapters.polity_v._raw_read
.read_polity_v_sav` (already filtered to the canonical 1800-2018
envelope by the raw-read layer) and emits one
:class:`NormalizedObservation` per valid
``(country, year, raw_column)`` triple. The 11 Polity V
catalog indicators are emitted under the single
``political_freedom_country_year`` observation family.

Split out of :mod:`leaders_db.sources.adapters.polity_v
.adapter` to keep the adapter class module focused on the
lifecycle methods (``check_ready`` / ``read_raw`` /
``transform``) and respect the documented 400-line module
convention. The missing-value coercion helpers (the documented
``-66`` / ``-77`` / ``-88`` special-code matrix + the
indicator-specific valid range: ``-10..+10`` for composite
scores / ``0..10`` for sub-components / ``>= 0`` unbounded
for ``durable``) live in :mod:`._missing_values`.

Per-row emission contract
-------------------------

For each ``(country, year)`` row in the filtered wide frame:

1. The identity columns (``country`` / ``year`` / ``scode`` /
   ``ccode``) are preserved as raw locator context for audit
   code.
2. For each of the 11 catalog indicator columns, the cell is
   coerced via :func:`._missing_values._coerce_polity_value`:

   - A valid int (in the indicator-specific valid range) is
     emitted as ``value=<int>`` / ``value_type='numeric'``.
     Valid negative scores (``-10..-1``) for ``polity`` /
     ``polity2`` are NOT treated as special codes -- they are
     real political-freedom observations and must be preserved
     as numeric. The ``durable`` indicator is special-cased:
     its valid range is ``>= 0`` with NO upper cap (it is the
     regime-durability YEARS counter, not a 0-10 sub-component
     score; the live ``p5v2018.sav`` carries ``durable``
     values up to 170).
   - A special code (``-66`` / ``-77`` / ``-88``) is emitted as
     ``value=None`` / ``value_type='missing'`` + the verbatim
     raw cell text on ``extension.raw_value``. The observation
     is NOT dropped; the analyst can see the upstream gap
     without losing the observation id / locator (matches the
     PTS / RSF / FAS defensive pattern).
   - NaN / blank / non-numeric cells are emitted as
     ``value=None`` / ``value_type='missing'`` + the verbatim
     raw cell text on ``extension.raw_value``.
   - Out-of-range cells are emitted as
     ``value=None`` / ``value_type='missing'`` + the verbatim
     raw cell text on ``extension.raw_value`` (defensive
     coverage).

The unified transform does NOT fabricate values, does NOT
invent countries, and does NOT relabel rows. The
``source_row_reference`` pattern is
``polity_v:<scode>:<year>:<raw_column>`` (matches the legacy
ingestion-plan § ``polity_v`` locator pattern).
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
    POLITY_V_ATTRIBUTION_TEXT,
    POLITY_V_DEFAULT_VERSION,
    POLITY_V_OBSERVATION_FAMILY,
    POLITY_V_RAW_COLUMN_CCODE,
    POLITY_V_RAW_COLUMN_COUNTRY,
    POLITY_V_RAW_COLUMN_DURABLE,
    POLITY_V_RAW_COLUMN_POLITY,
    POLITY_V_RAW_COLUMN_POLITY2,
    POLITY_V_RAW_COLUMN_SCODE,
    POLITY_V_RAW_COLUMN_YEAR,
    POLITY_V_RAW_COLUMNS,
    POLITY_V_SAV_ASSET_ID,
    POLITY_V_SOURCE_KEY,
)
from ._missing_values import _coerce_polity_value, _raw_cell_text

# Composite indicator columns (``polity`` / ``polity2``) have a
# valid range of ``-10..+10`` (composite scores). The remaining
# sub-component indicators (``democ`` / ``autoc`` / ``xrreg`` /
# ``xrcomp`` / ``xropen`` / ``xconst`` / ``parreg`` / ``parcomp``)
# have a valid range of ``0..10`` (sub-component scores). The
# ``durable`` indicator is INDICATOR-SPECIFIC: it is the
# regime-durability YEARS counter per the Polity V codebook with
# a valid range of ``>= 0`` and NO upper cap (long-running
# regimes produce values well above 10; the live ``p5v2018.sav``
# carries ``durable`` values up to 170). The valid negative
# scores on ``polity`` / ``polity2`` are REAL political-freedom
# observations, NOT special codes; the documented special codes
# ``-66`` / ``-77`` / ``-88`` are NON-numeric for every
# indicator.
_POLITY_V_COMPOSITE_COLUMNS: frozenset[str] = frozenset({
    POLITY_V_RAW_COLUMN_POLITY,
    POLITY_V_RAW_COLUMN_POLITY2,
})


def _is_composite_column(raw_column: str) -> bool:
    """Return True iff ``raw_column`` is a composite score column.

    Composite scores (``polity`` / ``polity2``) have a valid
    range of ``-10..+10``; sub-component scores have a valid
    range of ``0..N``. The transform uses the indicator-specific
    valid range to coerce cells. ``durable`` is special-cased in
    :func:`leaders_db.sources.adapters.polity_v._missing_values
    ._coerce_polity_value`; this helper only discriminates
    composite-vs-sub-component for the ``scale`` field on the
    emitted observation.
    """
    return raw_column in _POLITY_V_COMPOSITE_COLUMNS


def _is_durable_column(raw_column: str) -> bool:
    """Return True iff ``raw_column`` is the ``durable`` indicator.

    The ``durable`` indicator carries regime-durability YEARS
    counts (not a sub-component score on a 0-10 scale); the
    transform labels it with a dedicated ``scale`` so downstream
    Stage 5 score code does not mistakenly treat it as a 0-10
    sub-component.
    """
    return raw_column == POLITY_V_RAW_COLUMN_DURABLE


def emit_polity_v_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    sav_path: Path | None,
    metadata: dict[str, Any] | None,
) -> Iterable[NormalizedObservation]:
    """Convert the filtered wide DataFrame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by
        :func:`leaders_db.sources.adapters.polity_v._raw_read
        .read_polity_v_sav`. One row per
        ``(ccode, country, year)`` triple with the 11 catalog
        indicator columns + 26 other Polity V columns (which
        are preserved in the DataFrame for audit code but are
        NOT emitted as observations).
    request:
        The request-scoped :class:`SourceIngestRequest`
        driving the run. Used for source version +
        observation_id prefix.
    sav_path:
        Optional path to the staged ``p5v2018.sav``; carried
        verbatim onto every observation's :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload; used
        for source URL fallback on the raw asset (the raw-read
        layer already propagates the URL onto the
        :class:`RawAsset`).

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``wide_df`` is empty (e.g. the canonical-coverage filter
        removed every row).
    """
    if metadata is None:
        metadata = {}

    sav_path_str = str(sav_path) if isinstance(sav_path, Path) else None
    asset_id = POLITY_V_SAV_ASSET_ID
    source_version = POLITY_V_DEFAULT_VERSION

    observations: list[NormalizedObservation] = []

    if wide_df is None:
        return iter(observations)

    # The DataFrame iterrows pattern matches the PWT
    # ``emit_pwt_observations`` style -- one observation per
    # valid ``(country, year, raw_column)`` triple.
    for _, row in wide_df.iterrows():
        # Defensive: the canonical 11 columns + identity
        # columns must be present on every row. ``pyreadstat``
        # returns ``NaN`` for missing cells (not a KeyError);
        # the per-cell coercion in :func:`_coerce_polity_value`
        # handles the NaN case uniformly.
        try:
            year_raw = row[POLITY_V_RAW_COLUMN_YEAR]
            country_raw = row[POLITY_V_RAW_COLUMN_COUNTRY]
            scode_raw = row[POLITY_V_RAW_COLUMN_SCODE]
            ccode_raw = row[POLITY_V_RAW_COLUMN_CCODE]
        except KeyError:
            # The reader filtered a row that does not carry the
            # canonical identity columns -- skip it. This is
            # defensive coverage; the canonical 37-column
            # schema always carries these columns.
            continue

        # ``year`` is a float64 column in the SPSS file; coerce
        # to int when the float is integral (the Polity V year
        # column is always whole-number). NaN year values are
        # skipped (the canonical-coverage filter already drops
        # them, but be defensive here in case the caller
        # passes a non-filtered frame).
        if year_raw is None:
            continue
        try:
            year_float = float(year_raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(year_float):
            continue
        if not year_float.is_integer():
            continue
        year_int = int(year_float)

        country_str = (
            str(country_raw).strip()
            if country_raw is not None and not (
                isinstance(country_raw, float)
                and math.isnan(country_raw)
            )
            else ""
        )
        scode_str = (
            str(scode_raw).strip()
            if scode_raw is not None and not (
                isinstance(scode_raw, float)
                and math.isnan(scode_raw)
            )
            else ""
        )
        ccode_str = (
            str(ccode_raw).strip()
            if ccode_raw is not None and not (
                isinstance(ccode_raw, float)
                and math.isnan(ccode_raw)
            )
            else ""
        )

        for raw_column in POLITY_V_RAW_COLUMNS:
            if raw_column not in row.index:
                continue
            cell = row[raw_column]
            coerced = _coerce_polity_value(
                cell,
                indicator=raw_column,
                composite=_is_composite_column(raw_column),
            )
            raw_value_text = _raw_cell_text(cell)

            if coerced is None:
                # Special code / NaN / out-of-range: emit
                # ``value=None`` / ``value_type='missing'`` so
                # the analyst can see the upstream gap without
                # losing the observation id / locator. The
                # verbatim raw cell text is preserved on
                # ``extension.raw_value`` so audit code can
                # recover the original cell.
                value_type: str = "missing"
                emitted_value: int | None = None
            else:
                value_type = "numeric"
                emitted_value = int(coerced)

            source_row_reference = (
                f"{POLITY_V_SOURCE_KEY}:{scode_str}:"
                f"{year_int}:{raw_column}"
            )

            observations.append(
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=(
                        f"{POLITY_V_SOURCE_KEY}:{scode_str}:"
                        f"{year_int}:{raw_column}"
                    ),
                    observation_family=POLITY_V_OBSERVATION_FAMILY,
                    indicator_code=(
                        f"{POLITY_V_SOURCE_KEY}_{raw_column}"
                    ),
                    value=emitted_value,
                    value_type=value_type,
                    year=year_int,
                    country_code=None,
                    country_name=country_str if country_str else None,
                    leader_id=None,
                    leader_name=None,
                    unit=None,
                    scale=(
                        "polity_-10_to_10"
                        if _is_composite_column(raw_column)
                        else (
                            "polity_durable_years"
                            if _is_durable_column(raw_column)
                            else "polity_subcomponent"
                        )
                    ),
                    source_version=source_version,
                    raw_locator=RawLocator(
                        asset_id=asset_id,
                        path=sav_path_str,
                        column_name=raw_column,
                    ),
                    transform_locator=TransformLocator(
                        adapter_version=None,
                        transform_name="polity_v_wide_to_long",
                        catalog_key=POLITY_V_SOURCE_KEY,
                        rule_id=source_row_reference,
                    ),
                    quality_flags=(),
                    warnings=(),
                    extension={
                        "raw_value": raw_value_text,
                        "source_row_reference": source_row_reference,
                        "polity_v_country_display": country_str,
                        "polity_v_scode": scode_str,
                        "polity_v_ccode": ccode_str,
                        "attribution": POLITY_V_ATTRIBUTION_TEXT,
                    },
                ),
            )

    return iter(observations)


__all__ = [
    "emit_polity_v_observations",
]
