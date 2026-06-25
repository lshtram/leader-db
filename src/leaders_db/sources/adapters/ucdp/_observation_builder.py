"""Unified-source UCDP observation-construction helper.

This module owns the per-row
:class:`NormalizedObservation` construction helper used by
:func:`leaders_db.sources.adapters.ucdp._transform.emit_ucdp_observations`.

Split out of :mod:`._transform` so the per-row emission
loop stays focused on the iteration + filter logic, and so
the observation-construction contract is unit-testable in
isolation. The helper builds one observation per
``(country_id, year, variable_name)`` triple and carries
the canonical UCDP aggregate locator convention (per-row
event-level provenance is intentionally NOT preserved through
the country-year aggregation; the
``transform_locator.rule_id`` carries the
``ucdp:<country_id>:<year>:<variable_name>`` pattern and
the ``quality_flags`` carries the
``ucdp_aggregated_from_events`` flag so downstream audit
code can recognize the aggregate locator convention).

Event-level aggregation semantics
---------------------------------

UCDP GED is an event-level dataset (316,818 events in
v23.1). The Stage 2 legacy reader aggregates events to
country-year by ``type_of_violence`` and the cross-border
filter (``type=1 AND gwnob.notna()``) before the long-to-wide
pivot. The unified transform layer consumes the wide-format
country-year DataFrame -- per-row event-level provenance is
NOT preserved through the aggregation, so the unified
``RawLocator.row_number`` is intentionally ``None``. Per the
documented contract: "If row-level provenance is not
available after aggregation, document and test the aggregate
locator convention rather than fabricating row numbers."

Per-observation extension payload
---------------------------------

Every observation's ``extension`` carries:

- ``ucdp_country_id`` -- UCDP's own integer country id
  (Stage 3 country match resolves this to our canonical
  ISO3). Always present; matches the legacy Stage 2 DB
  writer's ``source_row_reference="ucdp:<country_id>"``
  pattern.
- ``ucdp_rating_category`` -- the catalog ``rating_category``
  value (``international_peace`` for 4 indicators +
  ``domestic_violence`` for 2 indicators).
- ``source_row_reference`` -- ``"ucdp:<country_id>"``;
  matches the legacy Stage 2 DB writer.
- ``ucdp_raw_column`` -- the catalog ``raw_column``
  (``event_count`` or ``best``).
- ``ucdp_filter_logic`` -- the catalog ``filter_logic``
  string (e.g. ``"type_of_violence == 1"``,
  ``"type_of_violence == 1 and gwnob.notna()"``,
  ``"type_of_violence == 3"``); carried for audit
  traceability so downstream code can re-derive the type +
  cross-border filter from the catalog row without
  re-reading the catalog.
- ``ucdp_events_total`` -- the pre-aggregation event count
  (``df.attrs["events_total"]``) from the legacy read;
  carried onto every observation so audit code can recover
  the input event-count metadata without re-running the
  legacy read. ``None`` when the legacy read did not attach
  the attribute.
- ``ucdp_events_filtered`` -- the post-type-filter event
  count (``df.attrs["events_filtered"]``) from the legacy
  read.
- ``raw_value`` -- the audit-trail raw cell value as a
  string (preserves the pandas Int64 / float representation).
- ``higher_is_better`` -- boolean; preserved from the
  catalog. All 6 UCDP indicators carry
  ``higher_is_better=False`` (more violence = worse rating).
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"count"`` / ``"deaths"``).
- ``normalized_scale_target`` -- catalog
  ``normalized_scale_target`` (always ``"0-1"`` for the 6
  UCDP indicators).
- ``attribution`` -- the canonical UCDP citation block
  (Rule #15; byte-identical to the legacy
  ``UCDP_ATTRIBUTION`` constant and the
  ``docs/sources/attributions.md`` UCDP section).
"""

from __future__ import annotations

import math
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._catalog import rating_category_to_observation_family
from ._constants import (
    UCDP_AGGREGATE_QUALITY_FLAG,
    UCDP_TRANSFORM_NAME,
)
from ._descriptor import (
    UCDP_ATTRIBUTION_TEXT,
    UCDP_SOURCE_KEY,
    UCDP_ZIP_ASSET_ID,
)


def extract_events_attrs(
    wide_df: Any,
) -> tuple[int | None, int | None]:
    """Return ``(events_total, events_filtered)`` from ``df.attrs``.

    The legacy ``read_ucdp`` reader attaches the
    pre-aggregation event counts to ``df.attrs``; the
    transform layer carries them onto every observation's
    extension so audit code can recover the input
    event-count metadata without re-running the legacy
    read.

    Returns ``(None, None)`` when the wide frame does not
    carry the ``attrs`` mapping (e.g., a synthetic /
    fixture path that did not go through the legacy read).
    """
    events_total_value: int | None = None
    events_filtered_value: int | None = None
    events_attrs = getattr(wide_df, "attrs", None)
    if isinstance(events_attrs, dict):
        total_attr = events_attrs.get("events_total")
        if isinstance(total_attr, (int, float)) and not (
            isinstance(total_attr, float) and math.isnan(total_attr)
        ):
            events_total_value = int(total_attr)
        filtered_attr = events_attrs.get("events_filtered")
        if isinstance(filtered_attr, (int, float)) and not (
            isinstance(filtered_attr, float)
            and math.isnan(filtered_attr)
        ):
            events_filtered_value = int(filtered_attr)
    return events_total_value, events_filtered_value


def build_observation(
    request: SourceIngestRequest,
    *,
    country_id_int: int,
    year: int,
    variable_name: str,
    spec: Any,
    numeric_value: float,
    raw_value_str: str,
    zip_path_str: str | None,
    source_version: str,
    source_row_reference: str,
    events_total_value: int | None,
    events_filtered_value: int | None,
) -> NormalizedObservation:
    """Construct a single :class:`NormalizedObservation` record.

    Helper extracted from :func:`emit_ucdp_observations` so
    the per-row loop stays compact and the observation
    construction is reusable / unit-testable in isolation.

    Every ``quality_flags`` tuple carries the
    ``ucdp_aggregated_from_events`` flag so downstream audit
    code can recognize the aggregate locator convention.
    The ``transform_locator.rule_id`` and ``observation_id``
    carry the ``ucdp:<country_id>:<year>:<variable_name>``
    pattern (the documented aggregate locator convention).
    """
    observation_family = rating_category_to_observation_family(
        spec.rating_category,
    )

    extension: dict[str, Any] = {
        "ucdp_country_id": country_id_int,
        "ucdp_rating_category": spec.rating_category,
        "ucdp_raw_column": getattr(spec, "raw_column", None),
        "ucdp_filter_logic": getattr(spec, "filter_logic", ""),
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_str,
        "raw_scale": getattr(spec, "raw_scale", None),
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", False),
        ),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", None,
        ),
        "attribution": UCDP_ATTRIBUTION_TEXT,
    }
    if events_total_value is not None:
        extension["ucdp_events_total"] = events_total_value
    if events_filtered_value is not None:
        extension["ucdp_events_filtered"] = events_filtered_value

    rule_id = (
        f"{UCDP_SOURCE_KEY}:{country_id_int}:"
        f"{year}:{variable_name}"
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family=observation_family,
        indicator_code=variable_name,
        value=numeric_value,
        value_type="numeric",
        year=year,
        # The unified contract uses the UCDP ``country_id``
        # integer as the country code (the canonical UCDP
        # country identifier). Stage 3 country match
        # resolves it to our canonical ISO3.
        country_code=str(country_id_int),
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None) or None,
        scale=getattr(spec, "raw_scale", None) or None,
        source_version=source_version,
        raw_locator=RawLocator(
            asset_id=UCDP_ZIP_ASSET_ID,
            path=zip_path_str,
            # The legacy wide frame is the country-year
            # aggregation of the event-level UCDP CSV; the
            # original event row index is not preserved
            # through the long-to-wide pivot. Per the
            # documented contract: "If row-level provenance
            # is not available after aggregation, document
            # and test the aggregate locator convention
            # rather than fabricating row numbers."
            row_number=None,
            column_name=variable_name,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=UCDP_TRANSFORM_NAME,
            catalog_key=UCDP_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(UCDP_AGGREGATE_QUALITY_FLAG,),
        warnings=(),
        extension=extension,
    )


__all__ = [
    "build_observation",
    "extract_events_attrs",
]
