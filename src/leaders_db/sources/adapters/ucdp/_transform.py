"""Unified-source UCDP observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation`
emission loop for the unified-source UCDP adapter. The
function takes the wide-format country-year DataFrame
returned by the legacy :func:`leaders_db.ingest.ucdp_io.read_ucdp`
reader (one row per ``(country_id, year)`` with one column
per catalog ``variable_name``, plus the two identity
columns ``country_id`` and ``year``) and emits the canonical
observation records via :func:`build_observation` from
:mod:`._observation_builder`.

Split out of
:mod:`leaders_db.sources.adapters.ucdp.adapter` to keep the
adapter class module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and respect
the documented 400-line module convention.

The missing-value coercion helpers live in
:mod:`._missing_values`; the per-row observation
construction lives in :mod:`._observation_builder`. This
module composes them into the per-row emission loop.

Event-level aggregation semantics
---------------------------------

UCDP GED is an event-level dataset (316,818 events in
v23.1). The Stage 2 legacy reader aggregates events to
country-year by ``type_of_violence`` and the cross-border
filter (``type=1 AND gwnob.notna()``) before the long-to-wide
pivot. The unified transform layer consumes the wide-format
country-year DataFrame -- per-row event-level provenance is
NOT preserved through the aggregation, so the unified
``RawLocator.row_number`` is intentionally ``None`` and the
``transform_locator.rule_id`` carries the
``ucdp:<country_id>:<year>:<variable_name>`` pattern.

Missing-value semantics
-----------------------

``NaN`` cells in the wide-format fatalities columns (events
with ``best=null``) are skipped: no silent conversion of
missing raw cells (SRC-OBS-007). The unified transform
emits a :class:`NormalizedObservation` for every non-NaN
cell only; missing cells produce zero observations for that
``(country_id, year, variable_name)`` triple.

The ``ucdp_state_based_events`` /
``ucdp_intl_events`` / ``ucdp_onesided_events`` columns are
``Int64`` (nullable pandas); the wide frame fills NaN with
``0`` (the country-year had no events of that type). The
``ucdp_state_based_fatalities`` /
``ucdp_intl_fatalities`` / ``ucdp_onesided_fatalities``
columns are ``float``; NaN only arises when the underlying
event has ``best=null``. The unified transform treats NaN
in either column as "skip this observation".
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    SourceIngestRequest,
)

from ._constants import (
    UCDP_AGGREGATE_QUALITY_FLAG,
    UCDP_TRANSFORM_NAME,
)
from ._descriptor import UCDP_DEFAULT_VERSION
from ._missing_values import _coerce_cell
from ._observation_builder import (
    build_observation,
    extract_events_attrs,
)


def _canonical_version() -> str:
    """Return the canonical UCDP version stamp.

    The unified adapter hardcodes the canonical version
    ``"GED 23.1"`` (matches the staged
    ``data/raw/ucdp/metadata.json`` ``source_version``
    field and the canonical attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not arbitrary
    metadata / request text.
    """
    return UCDP_DEFAULT_VERSION


def emit_ucdp_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    zip_path: Path | None,
    metadata: dict[str, Any] | None,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide UCDP frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by the legacy
        :func:`leaders_db.ingest.ucdp_io.read_ucdp` reader
        -- one row per ``(country_id, year)`` with one
        column per catalog ``variable_name``, plus the two
        identity columns (``country_id`` and ``year``).
        ``NaN`` cells in the fatalities columns are
        skipped (no silent conversion of missing raw cells;
        SRC-OBS-007). ``df.attrs`` carries ``events_total``
        and ``events_filtered`` from the legacy read;
        these are surfaced on every observation's extension.
    request:
        The request-scoped :class:`SourceIngestRequest`
        driving the run. Used for the source-version stamp.
        Year / country / leader filters are applied by the
        caller BEFORE this helper is invoked so the
        wide_df has already been narrowed.
    zip_path:
        Optional path to the staged ``ged231-csv.zip``;
        carried verbatim onto every observation's
        :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload.
        Not consumed for the observation emission contract
        -- kept in the signature for symmetry with the PWT
        / Maddison / WDI / WGI / V-Dem transform helpers.
    specs:
        Optional list of legacy :class:`IndicatorSpec`
        records. When ``None``, the unified transform
        receives the narrowed frame but emits zero
        observations (the caller must load the catalog and
        pass ``specs`` explicitly -- the lazy-load of the
        catalog is the caller's responsibility so the
        unified adapter never imports legacy at module
        level).

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``wide_df`` is empty or ``specs`` is ``None`` /
        empty (e.g. an out-of-coverage year request, or
        the staged fixture has no rows for the requested
        filter scope, or the catalog was not provided).
    """
    if metadata is None:
        metadata = {}

    if wide_df is None or specs is None or len(specs) == 0:
        return iter(())

    zip_path_str = (
        str(zip_path) if isinstance(zip_path, Path) else None
    )
    source_version = _canonical_version()

    # Carry the legacy pre-aggregation event counts onto
    # every observation's extension payload so audit code
    # can recover the input event-count metadata without
    # re-running the legacy read.
    events_total_value, events_filtered_value = extract_events_attrs(
        wide_df,
    )

    observations: list[NormalizedObservation] = []
    for _, wide_row in wide_df.iterrows():
        # Identity columns. The legacy wide frame keeps the
        # UCDP integer ``country_id`` (NOT ISO3) -- Stage 3
        # country match resolves it to our canonical ISO3.
        # Match the legacy Stage 2 DB writer's
        # ``source_row_reference="ucdp:<country_id>"``
        # pattern.
        country_id_raw = wide_row.get("country_id")
        try:
            country_id_int = int(country_id_raw)
        except (TypeError, ValueError):
            # Skip rows with a malformed country_id; the
            # wide frame should never produce such a row
            # but the guard is defense in depth.
            continue
        year_value = wide_row.get("year")
        try:
            year = int(year_value)
        except (TypeError, ValueError):
            continue

        source_row_reference = f"ucdp:{country_id_int}"

        for spec in specs:
            variable_name = getattr(spec, "variable_name", None)
            if not isinstance(variable_name, str) or not variable_name:
                continue
            cell = wide_row.get(variable_name)
            numeric_value, raw_value_str = _coerce_cell(cell)
            if numeric_value is None:
                # NaN / None -- do NOT emit an observation
                # (no silent conversion of missing cells).
                continue

            observations.append(
                build_observation(
                    request,
                    country_id_int=country_id_int,
                    year=year,
                    variable_name=variable_name,
                    spec=spec,
                    numeric_value=numeric_value,
                    raw_value_str=raw_value_str,
                    zip_path_str=zip_path_str,
                    source_version=source_version,
                    source_row_reference=source_row_reference,
                    events_total_value=events_total_value,
                    events_filtered_value=events_filtered_value,
                ),
            )
    return iter(observations)


__all__ = [
    "UCDP_AGGREGATE_QUALITY_FLAG",
    "UCDP_TRANSFORM_NAME",
    "emit_ucdp_observations",
]
