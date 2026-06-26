"""Unified-source RSF per-row observation-construction
helper.

This module owns the per-row
:class:`NormalizedObservation` construction helper used
by
:func:`leaders_db.sources.adapters.rsf_press_freedom._transform.emit_rsf_press_freedom_observations`.

Split out of :mod:`._transform` so the per-row emission
loop stays focused on the iteration + filter logic, and
so the observation-construction contract is unit-testable
in isolation. The per-row construction primitives
(``_detect_schema_group`` / ``_resolve_value_type`` /
``_default_asset_id_for_year`` /
``_default_source_version`` / ``_raw_columns`` /
``_indicator_names`` +
``RSF_PRESS_FREEDOM_TRANSFORM_NAME`` +
``RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022`` +
``RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022`` +
``RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS``) live in
:mod:`._observation_helpers`.

The helper builds one observation per
``(iso3, year, variable_name)`` triple and carries the
canonical RSF attribution block, the per-row
audit-trail fields (``raw_value`` /
``source_row_reference``), the pre/post-2022 schema
group flag, and the direction hints
(``higher_is_better`` / ``raw_scale`` /
``normalized_scale_target``).

Per-observation contract
------------------------

Every observation's ``extension`` carries:

- ``rsf_raw_column`` -- the catalog ``raw_column``
  (``score`` / ``rank`` / ``political_context`` /
  ``economic_context`` / ``legal_context`` /
  ``social_context`` / ``safety``); mirrors the WGI
  / V-Dem / CPI / UCDP / PTS convention so downstream
  score modules can resolve the raw value back to the
  catalog indicator without re-reading the legacy
  catalog.
- ``rsf_iso3`` -- the canonical ISO 3166-1 alpha-3
  3-letter alphabetic code (e.g. ``USA``); matches
  the legacy Stage 2 DB writer's
  ``source_row_reference`` suffix.
- ``rsf_category`` -- the catalog ``category`` value
  (``political_freedom``); carried so downstream code
  can filter by category without re-reading the
  legacy catalog.
- ``rsf_schema_group`` -- the pre/post-2022 schema
  group flag. ``1`` = pre-2022 (16-col wide format
  with score + rank only); ``2+`` = post-2022 (22-26
  col wide format with score + rank + 5
  component-context columns). The flag is preserved
  on every observation so downstream code can
  distinguish the pre/post-2022 methodology without
  re-reading the legacy CSV.
- ``rsf_actual_column`` -- the year-specific actual
  column name (``Score N`` for 2002-2021, ``Score``
  for 2022-2024, ``Score 2025`` for 2025,
  ``Score 2026`` for 2026; ``Rank N`` for 2002-2021,
  ``Rank`` for 2022+; the literal component column
  names for 2022+). Carried so audit code can recover
  the exact RSF header per observation.
- ``source_row_reference`` --
  ``"rsf_press_freedom:<iso3>:<actual_column>"``;
  matches the legacy Stage 2 DB writer.
- ``attribution`` -- the canonical RSF citation
  block (Rule #15; byte-identical to the legacy
  ``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/rsf_press_freedom_io.py`` and
  to the ``rsf_press_freedom`` section in
  ``docs/sources/attributions.md``).
- ``raw_value`` -- the audit-trail raw cell value as
  a string (preserves the verbatim RSF cell text
  with the comma-decimal separator; e.g. ``"72,67"``
  for a score cell, ``"149"`` for a rank cell,
  empty string for a missing cell).
- ``higher_is_better`` -- boolean; preserved from
  the catalog so downstream normalization can resolve
  the direction without re-reading the catalog. The
  RSF score + 5 components are
  ``higher_is_better=True`` (higher = better
  press-freedom situation); the rank is
  ``higher_is_better=False`` (rank 1 = best country).
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"0-100"`` for the score + 5 components,
  ``"ordinal"`` for the rank per the canonical
  catalog).
- ``normalized_scale_target`` -- catalog
  ``normalized_scale_target`` (``"0-10"`` per the
  canonical catalog; the Stage 5 score module
  normalizes to the 0-10 target).

Direction-hint contract
-----------------------

The RSF raw cell text is preserved verbatim on
``extension["raw_value"]``; the
``normalized_value`` is the comma-decimal-normalized
``float`` (or ``int`` for rank). The
``higher_is_better`` flag tells downstream
normalization which way to interpret the value. The
pre/post-2022 methodology distinction is preserved
on every observation via the ``rsf_schema_group``
flag so downstream score modules can apply the
correct 0-10 normalization (pre-2022 scores use a
different ordinal scale than the post-2022 0-100
scale per the documented pre/post-2022 methodology
change; the Stage 5 score module owns the
normalization).
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._constants import (
    RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
    RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
)
from ._observation_helpers import (
    RSF_PRESS_FREEDOM_TRANSFORM_NAME,
    _detect_schema_group,
    _resolve_value_type,
)


def build_observation(
    request: SourceIngestRequest,
    *,
    iso3: str,
    year: int,
    variable_name: str,
    spec: Any,
    cell: Any,
    raw_value_audit: str,
    csv_path_str: str | None,
    asset_id: str,
    actual_column: str,
    source_row_reference: str,
    source_version: str,
) -> NormalizedObservation:
    """Construct a single
    :class:`NormalizedObservation` record.

    Helper extracted from
    :func:`emit_rsf_press_freedom_observations` so the
    per-row loop stays compact and the
    observation-construction contract is reusable /
    unit-testable in isolation.

    Every observation's ``quality_flags`` carries the
    pre/post-2022 schema group flag (a single int
    constant) so downstream code can distinguish the
    methodology without re-reading the legacy CSV. The
    ``transform_locator.rule_id`` and
    ``observation_id`` carry the
    ``rsf_press_freedom:<iso3>:<year>:<variable_name>``
    pattern (the canonical per-row locator convention
    matching the legacy Stage 2 DB writer's
    ``source_row_reference`` shape).

    The ``value`` is the int / float coerced
    normalized value (rank int; score / components
    float); ``value_type="numeric"``. Missing cells
    (``None`` / ``NaN``) are NOT emitted (the
    transform layer filters them out via
    :func:`._missing_values._is_missing`).
    """
    # RSF catalog uses ``category`` -- not
    # ``rating_category`` -- so the helper resolves the
    # observation family via the catalog helper
    # (lazy-imported to keep this helper importable
    # without the catalog module's transitive
    # dependencies).
    from ._catalog import (
        rating_category_to_observation_family,
    )
    observation_family = rating_category_to_observation_family(
        getattr(spec, "category", ""),
    )

    raw_column = getattr(spec, "raw_column", None)
    is_rank = raw_column == RSF_PRESS_FREEDOM_RAW_COLUMN_RANK
    if is_rank:
        value: int | float = int(cell)
    else:
        value = float(cell)
    value_type = _resolve_value_type(variable_name)

    extension: dict[str, Any] = {
        "rsf_raw_column": raw_column,
        "rsf_iso3": iso3,
        "rsf_category": getattr(spec, "category", None),
        "rsf_schema_group": _detect_schema_group(year),
        "rsf_actual_column": actual_column,
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_audit,
        # Direction hint: RSF raw score is
        # higher_is_better=True (higher = better
        # press-freedom situation); the rank is
        # higher_is_better=False (rank 1 = best).
        # The Stage 5 score module owns the
        # normalization to the 0-10 target.
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", False),
        ),
        "raw_scale": getattr(spec, "raw_scale", None),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", None,
        ),
        "unit": getattr(spec, "unit", None),
        "attribution": RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
    }

    rule_id = (
        f"{RSF_PRESS_FREEDOM_SOURCE_KEY}:{iso3}:"
        f"{year}:{variable_name}"
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family=observation_family,
        indicator_code=variable_name,
        value=value,
        value_type=value_type,
        year=year,
        # The unified contract uses the RSF ISO 3-letter
        # alphabetic code (e.g. ``USA``) as the country
        # code. The country code is the canonical ISO
        # 3166-1 alpha-3 primary key per
        # ``data/raw/rsf_press_freedom/metadata.json``
        # + the legacy Stage 2 DB writer.
        country_code=iso3,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None) or None,
        scale=getattr(spec, "raw_scale", None) or None,
        source_version=source_version,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=csv_path_str,
            row_number=None,
            column_name=actual_column,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=RSF_PRESS_FREEDOM_TRANSFORM_NAME,
            catalog_key=RSF_PRESS_FREEDOM_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


__all__ = ["build_observation"]
