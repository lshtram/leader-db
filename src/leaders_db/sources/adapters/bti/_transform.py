"""Unified-source BTI observation-emission helpers.

This module owns the per-row emission loop for the
unified-source Bertelsmann Transformation Index
adapter. The function takes the wide-format
country-year DataFrame returned by the legacy reader
(:func:`leaders_db.ingest.bti_xlsx.read_bti`) -- one
row per ``(country, year)`` with the canonical BTI
columns ``country``, ``year``, and one column per
catalog ``variable_name`` -- and emits the canonical
observation records via :func:`build_observation`
from :mod:`._observation_builder`.

Split out of :mod:`.adapter` to keep the adapter class
module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and
respect the documented 400-line module convention.

The per-row observation construction contract lives in
:mod:`._observation_builder`. The missing-value
coercion helpers (``_coerce_float`` /
``_raw_value_to_string`` / ``_resolve_value_type``)
live in :mod:`._missing_values`. The per-row
emission-loop helpers (``_canonical_source_version` /
``_canonical_asset_id`` / ``_resolve_sheet_name`` /
``_resolve_target_year`` / ``_build_raw_long_lookup``
/ ``_locate_row_index``) live in
:mod:`._transform_helpers`. This module composes them
into the per-row emission loop.

BTI specific semantics
-----------------------

The BTI xlsx carries numeric 1-10 scores for 12
catalog indicators across 3 categories
(``effectiveness`` / ``political_freedom`` /
``economic_wellbeing``); the legacy reader applies a
wide-format pivot so the unified transform sees one
row per ``(country, year)`` with one column per
catalog indicator. The pre-coercion raw cell text is
preserved in ``df.attrs["_bti_raw_long"]`` (a long
DataFrame keyed by ``(country, year, variable_name)``
-> cell) so the audit trail recovers the original
xlsx text.

The unified transform layer skips rows whose
indicator cell is ``None`` / ``NaN`` -- no silent
conversion of missing raw cells (SRC-OBS-007). The
audit-trail ``raw_value`` is recovered from the
``_bti_raw_long`` attribute so even the dropped
cells carry an auditable raw cell string.

The resolved BTI edition sheet name + covered
interval are carried on the observation's
``extension`` (``bti_sheet_name`` / ``bti_target_year``)
so downstream Stage 5 score modules can apply the
biennial proxy / source-edition semantics without
re-reading the parquet metadata.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    SourceIngestRequest,
)

from ._missing_values import _raw_value_to_string
from ._observation_builder import (
    BTI_TRANSFORM_NAME,
    build_observation,
)
from ._transform_helpers import (
    _build_raw_long_lookup,
    _canonical_asset_id,
    _canonical_source_version,
    _locate_row_index,
    _resolve_row_sheet_context,
    _resolve_sheet_name,
    _resolve_target_year,
)


def emit_bti_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    xlsx_path: Path | None,
    metadata: dict[str, Any] | None,
    *,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide BTI frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by the
        legacy
        :func:`leaders_db.ingest.bti_xlsx.read_bti`
        reader -- one row per ``(country, year)``
        with columns ``country``, ``year``, and one
        column per catalog ``variable_name``.
        ``None`` / ``NaN`` cells in the indicator
        columns are skipped (no silent conversion of
        missing raw cells; SRC-OBS-007).
    request:
        The request-scoped
        :class:`SourceIngestRequest` driving the run.
        Used for the source-version stamp. Year /
        country / leader filters are applied by the
        caller BEFORE this helper is invoked so the
        wide_df has already been narrowed.
    xlsx_path:
        Optional path to the staged xlsx; carried
        verbatim onto every observation's
        :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json``
        payload. Not consumed for the observation
        emission contract -- kept in the signature
        for symmetry with the WGI / V-Dem / CPI /
        UCDP / PTS / RSF transform helpers.
    specs:
        Optional list of legacy
        :class:`IndicatorSpec` records. When ``None``,
        the unified transform receives the narrowed
        frame but emits zero observations (the caller
        must load the catalog and pass ``specs``
        explicitly -- the lazy-load of the catalog is
        the caller's responsibility so the unified
        adapter never imports legacy at module level).

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty
        when ``wide_df`` is empty or ``specs`` is
        ``None`` / empty (e.g. an out-of-coverage year
        request, or the staged fixture has no rows for
        the requested filter scope, or the catalog was
        not provided).
    """
    del metadata  # accepted for signature symmetry only.

    if wide_df is None or specs is None or len(specs) == 0:
        return iter(())

    xlsx_path_str = (
        str(xlsx_path) if isinstance(xlsx_path, Path) else None
    )
    source_version = _canonical_source_version()
    asset_id = _canonical_asset_id()
    sheet_name = _resolve_sheet_name(wide_df)
    target_year = _resolve_target_year(wide_df)

    # The pre-coercion raw cell text lookup. The
    # legacy reader attaches ``_bti_raw_long`` to
    # the wide frame's attrs as a long DataFrame
    # keyed by ``(country, year, variable_name)``
    # -> cell.
    raw_long = (
        wide_df.attrs.get("_bti_raw_long")
        if hasattr(wide_df, "attrs")
        else None
    )
    raw_lookup = _build_raw_long_lookup(raw_long)

    observations: list[NormalizedObservation] = []

    # Iterate via ``itertuples`` for speed: the wide
    # frame has 2 identity columns + 12 indicator
    # columns, so the per-row overhead is minimal.
    for row in wide_df.itertuples(index=False):
        # Identity columns. The legacy wide-format
        # frame has string ``country`` and int
        # ``year`` columns.
        country_name_raw = getattr(row, "country", None)
        if (
            not isinstance(country_name_raw, str)
            or not country_name_raw.strip()
        ):
            continue
        country_name = country_name_raw.strip()
        try:
            year = int(row.year)
        except (TypeError, ValueError):
            continue

        # The canonical per-row source row reference
        # pattern is ``"bti:<country_name>"`` (matches
        # the legacy Stage 2 DB writer).
        source_row_reference = f"bti:{country_name}"

        # The wide frame is sorted by ``country``
        # ascending per the legacy reader's
        # idempotency contract; the positional row
        # index is preserved so audit code can
        # recover the input row.
        row_number = _locate_row_index(
            wide_df, country_name, year,
        )

        row_sheet_name, row_target_year = _resolve_row_sheet_context(
            row,
            fallback_sheet_name=sheet_name,
            fallback_target_year=target_year,
            year=year,
        )

        for spec in specs:
            variable_name = getattr(spec, "variable_name", None)
            if (
                not isinstance(variable_name, str)
                or not variable_name
            ):
                continue
            cell = getattr(row, variable_name, None)

            # Skip ``None`` / ``pd.NA`` cells. The
            # legacy reader applies the
            # ``pd.to_numeric(errors="coerce")``
            # coercion at read time; valid cells
            # appear as float 1-10 values, missing
            # cells appear as NaN. The unified
            # transform does NOT emit observations
            # for missing cells (no silent conversion
            # of missing raw cells; SRC-OBS-007).
            if cell is None:
                continue
            try:
                import math

                if isinstance(cell, float) and math.isnan(cell):
                    continue
                import pandas as _pd

                if _pd.isna(cell):
                    continue
            except ImportError:
                # pandas unavailable (defensive; the
                # project's runtime requires pandas).
                if cell is None:
                    continue

            # Recover the pre-coercion raw cell text
            # for the audit trail. The legacy reader
            # attaches the long frame to
            # ``df.attrs["_bti_raw_long"]`` keyed by
            # ``(country, year, variable_name)``. The
            # raw text follows the §6.3 audit-trail
            # matrix (numeric string for valid cells;
            # ``"nan"`` for pandas NaN; ``""`` for
            # None).
            raw_cell = raw_lookup.get(
                (country_name, year, variable_name),
                cell,
            )
            raw_value_audit = _raw_value_to_string(raw_cell)

            observations.append(
                build_observation(
                    request,
                    country_name=country_name,
                    year=year,
                    variable_name=variable_name,
                    spec=spec,
                    cell=cell,
                    raw_value_audit=raw_value_audit,
                    xlsx_path_str=xlsx_path_str,
                    asset_id=asset_id,
                    row_number=row_number,
                    sheet_name=row_sheet_name,
                    source_version=source_version,
                    source_row_reference=source_row_reference,
                    target_year=row_target_year,
                ),
            )
    return iter(observations)


__all__ = [
    "BTI_TRANSFORM_NAME",
    "emit_bti_observations",
]
