"""Unified-source PWT observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation` build
loop for the unified-source PWT adapter. The function takes the
legacy long-format DataFrame (one row per ``(iso3, year,
variable_name)`` triple) and emits the canonical observation
records with raw locators, transform locators, attribution text,
and column-specific unit labels.

Split out of :mod:`leaders_db.sources.adapters.pwt.adapter` to
keep the adapter class module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and respect
the documented 400-line module convention.

The helper is intentionally a free function (not a method on
:class:`PWTAdapter`) so future callers can compose PWT
observations in custom transforms without instantiating the full
adapter (e.g. dry-run tooling, evidence-query reproducers).
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
    PWT_ATTRIBUTION_TEXT,
    PWT_COLUMN_UNITS,
    PWT_DATA_SHEET_NAME,
    PWT_DEFAULT_VERSION,
    PWT_OBSERVATION_FAMILY,
    PWT_SOURCE_KEY,
    PWT_XLSX_ASSET_ID,
)


def _is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, (int,))


def _metadata_version(
    request: SourceIngestRequest,
    metadata: dict[str, Any],
) -> str:
    """Return the canonical version after readiness validation.

    ``PWTAdapter.check_ready`` rejects unsupported request or
    metadata source-version values before ``read_raw`` / ``transform``
    can run. Observation provenance therefore uses the canonical
    validated PWT 10.01 version rather than echoing arbitrary input.
    """
    _ = request, metadata
    return PWT_DEFAULT_VERSION


def emit_pwt_observations(
    long_df: Any,
    request: SourceIngestRequest,
    xlsx_path: Path | None,
    metadata: dict[str, Any] | None,
) -> Iterable[NormalizedObservation]:
    """Convert the long-format DataFrame into :class:`NormalizedObservation` records.

    Parameters
    ----------
    long_df:
        The long-format DataFrame returned by the legacy
        :func:`leaders_db.ingest.sources.pwt.transform.transform_pwt_long_frame`.
        One row per ``(iso3, year, variable_name)`` triple.
    request:
        The request-scoped :class:`SourceIngestRequest` driving
        the run. Used for source version + observation_id prefix.
    xlsx_path:
        Optional path to the staged ``pwt1001.xlsx``; carried
        verbatim onto every observation's :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload; used
        for source-version fallback.

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``long_df`` is empty (e.g. out-of-coverage year request).
    """
    if metadata is None:
        metadata = {}

    xlsx_path_str = str(xlsx_path) if isinstance(xlsx_path, Path) else None
    asset_id = PWT_XLSX_ASSET_ID
    source_version = _metadata_version(request, metadata)

    observations: list[NormalizedObservation] = []
    for _, long_row in long_df.iterrows():
        iso3 = str(long_row["iso3"])
        year = int(long_row["year"])
        raw_column = str(long_row["raw_column"])
        variable_name = str(long_row["variable_name"])
        numeric_value = long_row.get("numeric_value")
        raw_value = long_row.get("raw_value")
        source_row_reference = str(long_row["source_row_reference"])

        observations.append(
            NormalizedObservation(
                source_id=request.source_id,
                observation_id=(
                    f"pwt:{iso3}:{year}:{raw_column}"
                ),
                observation_family=PWT_OBSERVATION_FAMILY,
                indicator_code=variable_name,
                value=(
                    float(numeric_value)
                    if _is_real_number(numeric_value)
                    else None
                ),
                value_type="numeric",
                year=year,
                country_code=iso3,
                country_name=None,
                leader_id=None,
                leader_name=None,
                unit=PWT_COLUMN_UNITS.get(raw_column),
                scale=None,
                source_version=source_version,
                raw_locator=RawLocator(
                    asset_id=asset_id,
                    path=xlsx_path_str,
                    sheet=PWT_DATA_SHEET_NAME,
                    column_name=raw_column,
                ),
                transform_locator=TransformLocator(
                    adapter_version=None,
                    transform_name="transform_pwt_long_frame",
                    catalog_key=PWT_SOURCE_KEY,
                    rule_id=source_row_reference,
                ),
                quality_flags=(),
                warnings=(),
                extension={
                    "raw_value": raw_value,
                    "source_row_reference": source_row_reference,
                    "temporal_kind": str(
                        long_row.get("temporal_kind", "observed"),
                    ),
                    "attribution": PWT_ATTRIBUTION_TEXT,
                },
            ),
        )
    return iter(observations)


__all__ = [
    "emit_pwt_observations",
]
