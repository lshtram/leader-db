"""Unified-source BTI per-row observation-construction
helper.

This module owns the per-row
:class:`NormalizedObservation` construction helper used by
:func:`leaders_db.sources.adapters.bti._transform.emit_bti_observations`.

Split out of :mod:`._transform` so the per-row emission
loop stays focused on the iteration + filter logic, and
so the observation-construction contract is unit-testable
in isolation. The helper builds one observation per
``(country_name, year, variable_name)`` triple and carries
the canonical BTI attribution block, the per-row
audit-trail fields (``country`` / ``bti_sheet_name`` /
``bti_target_year``), the pre-coercion ``raw_value`` cell
text, the canonical ``source_row_reference``
(``"bti:<country_name>"``) pattern (matching the legacy
Stage 2 DB writer), and the direction hints
(``higher_is_better`` / ``raw_scale`` /
``normalized_scale_target``).

Per-observation contract
------------------------

Every observation's ``extension`` carries:

- ``bti_raw_column`` -- the catalog ``raw_column``
  (e.g. ``"  G | Governance Index"``); mirrors the
  WGI / V-Dem / CPI / UCDP / PTS convention so
  downstream score modules can resolve the raw value
  back to the catalog indicator without re-reading
  the legacy catalog.
- ``bti_country_name`` -- the BTI display name (e.g.
  ``"Mexico"``); preserved verbatim from the xlsx
  col 0 so downstream Stage 3 country match can
  resolve it to ISO3 via the canonical country
  alias table (same pattern as SIPRI milex's
  display-name convention and V-Dem's pre-v13
  ``country_text_id``).
- ``bti_sheet_name`` -- the resolved BTI edition
  sheet name (e.g. ``"BTI 2024"`` for the 2023
  target year); preserved verbatim so audit code
  can recover the source-edition semantics from
  the observation.
- ``bti_target_year`` -- the canonical in-coverage
  year the sheet represents (e.g. ``2023`` for
  ``BTI 2024``); preserved so downstream Stage 5
  score modules can resolve the proxy / source-
  edition semantics.
- ``bti_rating_category`` -- the catalog
  ``category`` value (``effectiveness`` /
  ``political_freedom`` / ``economic_wellbeing``);
  carried so downstream code can filter by category
  without re-reading the legacy catalog.
- ``source_row_reference`` --
  ``"bti:<country_name>"``; matches the legacy
  Stage 2 DB writer.
- ``attribution`` -- the canonical BTI citation
  block (Rule #15; byte-identical to the legacy
  ``BTI_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/bti_io.py` and to the
  ``bti`` section in
  ``docs/sources/attributions.md``).
- ``raw_value`` -- the audit-trail raw cell value
  as a string (preserves the verbatim BTI xlsx
  cell; numeric string for valid cells,
  ``"nan"`` for pandas NaN, ``""`` for None).
- ``higher_is_better`` -- boolean; preserved from
  the catalog so downstream normalization can
  resolve the direction without re-reading the
  catalog. The BTI 1-10 score carries
  ``higher_is_better=True`` (10 = best per the
  canonical catalog).
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"1-10"``).
- ``normalized_scale_target`` -- catalog
  ``normalized_scale_target`` (``"0-10"``; the BTI
  raw 1-10 value is preserved verbatim and the
  Stage 5 score module applies the linear
  1 -> 1, 10 -> 10 mapping per the canonical
  rubric).

Direction-hint contract
-----------------------

The BTI raw 1-10 scale is preserved verbatim on
``source_observations.normalized_value``; the
``higher_is_better=True`` flag tells downstream
normalization the direction is conventional (no
inversion needed). This is the same convention as
WGI's quantitative estimates and V-Dem's democracy
indicators. The transform layer does NOT silently
invert the value -- the audit trail preserves the
raw 1-10 float so the Stage 5 score module can
apply the linear 0-10 mapping per design doc §3.
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._descriptor import (
    BTI_ATTRIBUTION_TEXT,
    BTI_DEFAULT_VERSION,
    BTI_SOURCE_KEY,
    BTI_XLSX_ASSET_ID,
    BTI_XLSX_NAME,
)

# Module-local binding for the per-row transform name.
# The ``emit_bti_observations`` helper resolves this
# constant from the transform module at import time; we
# hardcode it here for symmetry with the UCDP / V-Dem /
# WGI / CPI / PTS / RSF pattern (one module-local
# constant per source). The transform name mirrors the
# legacy ``bti_xlsx.read_bti`` reader so audit code can
# recover the transform-stage from the observation's
# ``transform_locator.transform_name``.
BTI_TRANSFORM_NAME: str = "read_bti"


def build_observation(
    request: SourceIngestRequest,
    *,
    country_name: str,
    year: int,
    variable_name: str,
    spec: Any,
    cell: Any,
    raw_value_audit: str,
    xlsx_path_str: str | None,
    asset_id: str,
    row_number: int | None,
    sheet_name: str,
    source_version: str,
    source_row_reference: str,
    target_year: int,
) -> NormalizedObservation:
    """Construct a single
    :class:`NormalizedObservation` record.

    Helper extracted from
    :func:`emit_bti_observations` so the per-row loop
    stays compact and the observation-construction
    contract is reusable / unit-testable in isolation.

    Every observation's ``quality_flags`` is empty (the
    BTI dataset is a direct country-edition
    measurement, not an aggregation). The
    ``transform_locator.rule_id`` and
    ``observation_id`` carry the
    ``bti:<country_name>:<year>:<variable_name>``
    pattern (the canonical per-row locator convention
    matching the legacy Stage 2 DB writer's
    ``source_row_reference`` shape).

    The ``value`` is the float 1-10 raw score; the
    helper applies :func:`_coerce_float` defensively
    so a non-numeric cell that slipped through the
    transform filter does not raise (the transform
    layer already filters ``None`` / ``NaN`` cells so
    a non-numeric cell is a programming error). The
    ``country_code`` is intentionally ``None`` because
    BTI does not carry ISO3 codes (Stage 3 country
    match resolves the BTI display name to ISO3 via
    the canonical country alias table).
    """
    # Lazy import: keeps this module importable
    # without the catalog module's transitive
    # dependencies.
    from ._catalog import rating_category_to_observation_family

    observation_family = rating_category_to_observation_family(
        getattr(spec, "category", ""),
    )

    extension: dict[str, Any] = {
        "bti_raw_column": getattr(spec, "raw_column", None),
        "bti_country_name": country_name,
        "bti_sheet_name": sheet_name,
        "bti_target_year": target_year,
        "bti_rating_category": getattr(spec, "category", None),
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_audit,
        "raw_scale": getattr(spec, "raw_scale", None),
        # Direction hint: BTI raw 1-10 is
        # higher-is-better (10 = best per the
        # canonical catalog). The Stage 5 score
        # module applies the linear 0-10 mapping.
        # The flag is preserved here so downstream
        # code can resolve the direction without
        # re-reading the catalog.
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", False),
        ),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", None,
        ),
        "unit": getattr(spec, "unit", None),
        "attribution": BTI_ATTRIBUTION_TEXT,
    }

    rule_id = (
        f"{BTI_SOURCE_KEY}:{country_name}:{year}:{variable_name}"
    )

    # Defensive coerce: the transform layer already
    # filters ``None`` / ``NaN`` cells, so the cell
    # here is a numeric 1-10 score cast to float. If
    # a non-numeric cell slipped through, the
    # :func:`_coerce_float` helper returns ``None`` and
    # the observation's ``value`` is ``None`` (the
    # :class:`NormalizedObservation`` contract allows
    # ``None`` for missing cells).
    from ._missing_values import _coerce_float

    coerced_value = _coerce_float(cell)

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family=observation_family,
        indicator_code=variable_name,
        value=coerced_value,
        value_type=(
            "numeric" if coerced_value is not None else "missing"
        ),
        year=year,
        # The unified contract leaves ``country_code``
        # as ``None`` for BTI because BTI does not
        # carry ISO3 codes (Stage 3 country match
        # resolves the BTI display name to ISO3 via
        # the canonical country alias table).
        country_code=None,
        country_name=country_name,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None) or None,
        scale=getattr(spec, "raw_scale", None) or None,
        source_version=source_version,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=xlsx_path_str,
            sheet=sheet_name,
            row_number=row_number,
            column_name=getattr(spec, "raw_column", None),
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            # The transform name is bound at module
            # import time below; we resolve it here
            # to keep the helper self-contained.
            transform_name=BTI_TRANSFORM_NAME,
            catalog_key=BTI_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _default_asset_id() -> str:
    """Return the canonical BTI xlsx asset id.

    The legacy BTI reader does not embed the asset
    id in the wide frame; the transform layer uses
    this helper so all observations in a single run
    share the same logical asset id (matching the
    WGI / V-Dem / CPI / UCDP / PTS convention).
    """
    return BTI_XLSX_ASSET_ID


def _default_source_version() -> str:
    """Return the canonical BTI source version
    stamp.

    The unified adapter hardcodes the canonical
    version ``"BTI 2026"`` (matches the canonical
    attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not
    arbitrary metadata / request text.
    """
    return BTI_DEFAULT_VERSION


def _xlsx_name() -> str:
    """Return the canonical xlsx filename."""
    return BTI_XLSX_NAME


__all__ = [
    "BTI_TRANSFORM_NAME",
    "_default_asset_id",
    "_default_source_version",
    "_xlsx_name",
    "build_observation",
]
