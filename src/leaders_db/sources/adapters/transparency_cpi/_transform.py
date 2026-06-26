"""Unified-source Transparency International CPI
observation-emission helpers.

This module owns the per-row emission loop for the
unified-source Transparency International CPI adapter.
The function takes the wide-format country-year DataFrame
returned by the legacy reader
(:func:`leaders_db.ingest.transparency_cpi_csv.read_transparency_cpi_csv`)
-- one row per ``(iso3, year)`` with the canonical CPI
columns ``country``, ``region``, ``cpi_score``,
``cpi_score_raw_value``, ``rank``, ``sources``,
``standard_error``, ``lower_ci``, ``upper_ci`` -- and
emits the canonical observation records via
:func:`build_observation` from
:mod:`._observation_builder`.

Split out of
:mod:`leaders_db.sources.adapters.transparency_cpi.adapter`
to keep the adapter class module focused on the lifecycle
methods (``check_ready`` / ``read_raw`` / ``transform``)
and respect the documented 400-line module convention.

The per-row observation construction contract lives in
:mod:`._observation_builder`. The missing-value coercion
helpers live in :mod:`._missing_values`. This module
composes them into the per-row emission loop + the
positional-row-index lookup helper.

Missing-value semantics
-----------------------

The CPI 2023 dataset (via HDX) has 180 country rows.
Every row carries an integer 0-100 score; no
missing-data sentinels are expected per the legacy
catalog documentation. If a future edition introduces
missing cells, the parser handles empty / ``NA`` strings
as ``None`` (the legacy ``_coerce_int_score`` helper).
The unified transform layer skips rows whose
``cpi_score`` cell is ``None`` / ``NaN`` -- no silent
conversion of missing raw cells (SRC-OBS-007).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    SourceIngestRequest,
)

from ._descriptor import (
    TRANSPARENCY_CPI_DEFAULT_VERSION,
    _csv_asset_id_for_year,
)
from ._missing_values import (
    _coerce_float_or_none,
    _coerce_int_or_none,
    _coerce_score_cell,
    _is_real_number,
    _raw_value_to_string,
)
from ._observation_builder import (
    TRANSPARENCY_CPI_TRANSFORM_NAME,
    build_observation,
)


def _canonical_version() -> str:
    """Return the canonical Transparency International
    CPI version stamp.

    The unified adapter hardcodes the canonical version
    ``"CPI 2023"`` (matches the staged
    ``data/raw/transparency_cpi/metadata.json``
    ``source_version`` field and the canonical
    attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not arbitrary
    metadata / request text.
    """
    return TRANSPARENCY_CPI_DEFAULT_VERSION


def _locate_row_index(
    wide_df: Any,
    iso3: str,
    year: int,
) -> int | None:
    """Return the wide-frame row index for ``(iso3, year)``.

    The legacy wide-format DataFrame is sorted by ``iso3``
    ascending for deterministic idempotency (per
    ``transparency_cpi_csv.read_transparency_cpi_csv``);
    the ``iso3`` and ``year`` columns form the
    canonical country-year key. The unified transform
    preserves the row index when feasible (per
    ``docs/architecture/sources.md`` section 5.4) so
    audit code can recover the input row from the staged
    CSV byte-for-byte.

    Returns ``None`` when the ``(iso3, year)`` key does
    not match any row in the frame (defensive guard for
    a malformed wide frame).
    """
    if wide_df is None:
        return None
    try:
        match = wide_df.loc[
            (wide_df["iso3"] == iso3)
            & (wide_df["year"].astype(int) == int(year))
        ]
    except (KeyError, TypeError, ValueError):
        return None
    if match.empty:
        return None
    # The legacy reader returns a frame sorted by iso3
    # ascending; the first matching row is the canonical
    # one. Return the positional index of the matching
    # row in the wide frame.
    idx_value = match.index[0]
    try:
        return int(idx_value)
    except (TypeError, ValueError):
        return None


def emit_transparency_cpi_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    csv_path: Path | None,
    metadata: dict[str, Any] | None,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide CPI frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by the legacy
        :func:`leaders_db.ingest.transparency_cpi_csv.read_transparency_cpi_csv`
        reader -- one row per ``(iso3, year)`` with
        columns ``country``, ``region``, ``cpi_score``,
        ``cpi_score_raw_value``, ``rank``, ``sources``,
        ``standard_error``, ``lower_ci``, ``upper_ci``.
        ``NaN`` cells in ``cpi_score`` are skipped (no
        silent conversion of missing raw cells;
        SRC-OBS-007).
    request:
        The request-scoped :class:`SourceIngestRequest`
        driving the run. Used for the source-version
        stamp. Year / country / leader filters are
        applied by the caller BEFORE this helper is
        invoked so the wide_df has already been
        narrowed.
    csv_path:
        Optional path to the staged per-year CSV;
        carried verbatim onto every observation's
        :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json``
        payload. Not consumed for the observation
        emission contract -- kept in the signature for
        symmetry with the PWT / Maddison / WDI / WGI /
        V-Dem / UCDP transform helpers.
    specs:
        Optional list of legacy :class:`IndicatorSpec`
        records. When ``None``, the unified transform
        receives the narrowed frame but emits zero
        observations (the caller must load the catalog
        and pass ``specs`` explicitly -- the lazy-load
        of the catalog is the caller's responsibility so
        the unified adapter never imports legacy at
        module level).

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
    if metadata is None:
        metadata = {}

    if wide_df is None or specs is None or len(specs) == 0:
        return iter(())

    csv_path_str = (
        str(csv_path) if isinstance(csv_path, Path) else None
    )
    source_version = _canonical_version()
    # The CPI reader is annual; the per-year CSV asset id
    # embeds the request year so audit code can group
    # observations by their raw CSV.
    raw_year = metadata.get("raw_year")
    if not isinstance(raw_year, int):
        # Fall back to the canonical 2023 year when the
        # raw payload did not carry the year stamp
        # (defensive guard against an older raw payload).
        raw_year = 2023
    asset_id = _csv_asset_id_for_year(int(raw_year))

    observations: list[NormalizedObservation] = []

    # Iterate via ``itertuples`` for speed: the wide
    # frame has up to 11 columns + the iso3 / year
    # identity columns, so the per-row overhead is
    # minimal.
    for row in wide_df.itertuples(index=False):
        # Identity columns. The legacy wide-format frame
        # has string ``iso3`` and integer ``year``
        # columns.
        iso3_raw = getattr(row, "iso3", None)
        if not isinstance(iso3_raw, str) or not iso3_raw.strip():
            continue
        iso3 = iso3_raw.strip().upper()
        try:
            year = int(row.year)
        except (TypeError, ValueError):
            continue

        # The canonical per-row source row reference
        # pattern is ``"transparency_cpi:score:<iso3>"``
        # (matches the legacy Stage 2 DB writer).
        source_row_reference = f"transparency_cpi:score:{iso3}"

        # The wide frame is sorted by iso3 ascending per
        # the legacy reader's idempotency contract; the
        # positional row index is preserved so audit code
        # can recover the input row.
        row_number = _locate_row_index(wide_df, iso3, year)

        # Country + region audit-trail columns are
        # preserved verbatim from the HDX CSV so audit
        # code can recover the input row's labels.
        country_label = getattr(row, "country", None)
        region_label = getattr(row, "region", None)

        # Audit-trail columns (rank, sources,
        # standard_error, lower_ci, upper_ci) are
        # coerced via the missing-value helpers so
        # ``None`` cells do NOT silently convert to a
        # fabricated numeric.
        rank_value = _coerce_int_or_none(
            getattr(row, "rank", None),
        )
        sources_value = _coerce_int_or_none(
            getattr(row, "sources", None),
        )
        standard_error_value = _coerce_float_or_none(
            getattr(row, "standard_error", None),
        )
        lower_ci_value = _coerce_float_or_none(
            getattr(row, "lower_ci", None),
        )
        upper_ci_value = _coerce_float_or_none(
            getattr(row, "upper_ci", None),
        )

        for spec in specs:
            variable_name = getattr(spec, "variable_name", None)
            if not isinstance(variable_name, str) or not variable_name:
                continue
            cell = getattr(row, variable_name, None)
            numeric_value, _audit_str = _coerce_score_cell(cell)
            if numeric_value is None:
                # NaN / None -- do NOT emit an observation
                # (no silent conversion of missing cells).
                continue
            if not _is_real_number(numeric_value):
                continue

            observations.append(
                build_observation(
                    request,
                    iso3=iso3,
                    year=year,
                    variable_name=variable_name,
                    spec=spec,
                    cell=numeric_value,
                    raw_value_audit=_raw_value_to_string(cell),
                    csv_path_str=csv_path_str,
                    asset_id=asset_id,
                    row_number=row_number,
                    source_version=source_version,
                    source_row_reference=source_row_reference,
                    country_label=country_label,
                    region_label=region_label,
                    rank_value=rank_value,
                    sources_value=sources_value,
                    standard_error_value=standard_error_value,
                    lower_ci_value=lower_ci_value,
                    upper_ci_value=upper_ci_value,
                ),
            )
    return iter(observations)


__all__ = [
    "TRANSPARENCY_CPI_TRANSFORM_NAME",
    "emit_transparency_cpi_observations",
]
