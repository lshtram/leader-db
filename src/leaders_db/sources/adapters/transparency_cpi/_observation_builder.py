"""Unified-source Transparency International CPI
per-row observation-construction helper.

This module owns the per-row
:class:`NormalizedObservation` construction helper used by
:func:`leaders_db.sources.adapters.transparency_cpi._transform.emit_transparency_cpi_observations`.

Split out of :mod:`._transform` so the per-row emission
loop stays focused on the iteration + filter logic, and
so the observation-construction contract is unit-testable
in isolation. The helper builds one observation per
``(iso3, year, variable_name)`` triple and carries the
canonical CPI attribution block, the per-row audit-trail
fields (``cpi_rank`` / ``cpi_sources`` /
``cpi_standard_error`` / ``cpi_lower_ci`` / ``cpi_upper_ci``),
the country / region labels, and the direction hints
(``higher_is_better`` / ``raw_scale`` /
``normalized_scale_target``).

Per-observation contract
------------------------

Every observation's ``extension`` carries:

- ``transparency_cpi_raw_column`` -- the catalog
  ``raw_column`` (``score``); mirrors the WGI / V-Dem /
  WDI convention so downstream score modules can resolve
  the raw value back to the catalog indicator without
  re-reading the legacy catalog.
- ``transparency_cpi_iso3`` -- the canonical ISO3 country
  code (the CPI ``iso3`` column; matches the legacy
  Stage 2 DB writer's ``source_row_reference`` prefix).
- ``transparency_cpi_rating_category`` -- the catalog
  ``rating_category`` value (``integrity``); carried so
  downstream code can filter by category without
  re-reading the legacy catalog.
- ``source_row_reference`` --
  ``"transparency_cpi:score:<iso3>"``; matches the
  legacy Stage 2 DB writer.
- ``attribution`` -- the canonical Transparency
  International CPI citation block (Rule #15;
  byte-identical to the legacy
  ``TRANSPARENCY_CPI_ATTRIBUTION`` constant and the
  ``transparency_cpi`` section in
  ``docs/sources/attributions.md``).
- ``raw_value`` -- the audit-trail raw cell value as a
  string (preserves the verbatim HDX CSV cell).
- ``cpi_country_name`` -- the CPI ``country`` column
  (human-readable country label); preserved verbatim.
- ``cpi_region`` -- the CPI ``region`` column
  (e.g. ``"WE/EU"``, ``"AP"``, ``"MENA"``); preserved
  verbatim.
- ``cpi_rank`` -- the per-country rank (1 = cleanest);
  ``None`` when missing / unparseable.
- ``cpi_sources`` -- the number of underlying sources
  the per-country CPI score aggregates (the TI
  methodology aggregates 8-13 independent sources per
  country); ``None`` when missing / unparseable.
- ``cpi_standard_error`` -- the per-country standard
  error on the CPI score (a 0-1 confidence interval);
  ``None`` when missing / unparseable.
- ``cpi_lower_ci`` / ``cpi_upper_ci`` -- the lower / upper
  bounds of the per-country 90% confidence interval on
  the CPI score; ``None`` when missing / unparseable.
- ``higher_is_better`` -- boolean; preserved from the
  catalog so downstream normalization can resolve the
  direction without re-reading the catalog. The CPI score
  carries ``higher_is_better=True`` (higher = cleaner
  perception).
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"0-100"``).
- ``normalized_scale_target`` -- catalog
  ``normalized_scale_target`` (``"0-10"``).
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
    TRANSPARENCY_CPI_ATTRIBUTION_TEXT,
    TRANSPARENCY_CPI_SOURCE_KEY,
)
from ._missing_values import (
    _coerce_float_or_none,
    _coerce_int_or_none,
    _raw_value_to_string,
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
    row_number: int | None,
    source_version: str,
    source_row_reference: str,
    country_label: str | None,
    region_label: str | None,
    rank_value: int | None,
    sources_value: int | None,
    standard_error_value: float | None,
    lower_ci_value: float | None,
    upper_ci_value: float | None,
) -> NormalizedObservation:
    """Construct a single :class:`NormalizedObservation`
    record.

    Helper extracted from
    :func:`emit_transparency_cpi_observations` so the
    per-row loop stays compact and the
    observation-construction contract is reusable /
    unit-testable in isolation.

    Every observation's ``quality_flags`` is empty (the
    CPI dataset is a direct country-year measurement, not
    an aggregation). The ``transform_locator.rule_id``
    and ``observation_id`` carry the
    ``transparency_cpi:<iso3>:<year>:<variable_name>``
    pattern (the canonical per-row locator convention).
    """
    observation_family = (
        # Defer import to keep this module free of
        # ``._catalog`` cycles (the catalog import is
        # cheap and side-effect free; the lookup is a
        # pure dict access).
        _rating_category_to_family(
            getattr(spec, "rating_category", ""),
        )
    )

    extension: dict[str, Any] = {
        "transparency_cpi_raw_column": getattr(
            spec, "raw_column", None,
        ),
        "transparency_cpi_iso3": iso3,
        "transparency_cpi_rating_category": getattr(
            spec, "rating_category", None,
        ),
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_audit,
        "raw_scale": getattr(spec, "raw_scale", None),
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", False),
        ),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", None,
        ),
        "unit": getattr(spec, "unit", None),
        "attribution": TRANSPARENCY_CPI_ATTRIBUTION_TEXT,
    }
    # Preserve the audit-trail country / region labels on
    # the per-observation extension so downstream audit
    # code can recover the input row's labels without
    # re-reading the legacy CSV.
    if isinstance(country_label, str) and country_label.strip():
        extension["cpi_country_name"] = country_label.strip()
    if isinstance(region_label, str) and region_label.strip():
        extension["cpi_region"] = region_label.strip()
    if rank_value is not None:
        extension["cpi_rank"] = rank_value
    if sources_value is not None:
        extension["cpi_sources"] = sources_value
    if standard_error_value is not None:
        extension["cpi_standard_error"] = standard_error_value
    if lower_ci_value is not None:
        extension["cpi_lower_ci"] = lower_ci_value
    if upper_ci_value is not None:
        extension["cpi_upper_ci"] = upper_ci_value

    rule_id = (
        f"{TRANSPARENCY_CPI_SOURCE_KEY}:{iso3}:"
        f"{year}:{variable_name}"
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family=observation_family,
        indicator_code=variable_name,
        value=float(cell),
        value_type="numeric",
        year=year,
        # The unified contract uses the CPI ``iso3``
        # alpha-3 code (e.g. ``MEX``) as the country
        # code. Stage 3 country match resolves it to the
        # canonical ISO3 (the same string in this case).
        country_code=iso3,
        country_name=(
            country_label
            if isinstance(country_label, str) and country_label.strip()
            else None
        ),
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None) or None,
        scale=getattr(spec, "raw_scale", None) or None,
        source_version=source_version,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=csv_path_str,
            row_number=row_number,
            column_name=getattr(
                spec, "raw_column", None,
            ),
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            # The transform name is bound at module
            # import time below; we resolve it here to
            # keep the helper self-contained.
            transform_name=TRANSPARENCY_CPI_TRANSFORM_NAME,
            catalog_key=TRANSPARENCY_CPI_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _rating_category_to_family(rating_category: str) -> str:
    """Resolve the rating-category to family via the
    catalog helper.

    Local wrapper to keep the per-row builder free of an
    explicit import cycle (the catalog module is small
    and side-effect free).
    """
    # Lazy import to keep this helper importable without
    # the catalog module's transitive dependencies.
    from ._catalog import rating_category_to_observation_family
    return rating_category_to_observation_family(rating_category)


# Module-local binding for the per-row transform name. The
# ``emit_transparency_cpi_observations`` helper resolves
# this constant from the transform module at import time;
# we hardcode it here for symmetry with the UCDP /
# V-Dem / WGI pattern (one module-local constant per
# source).
TRANSPARENCY_CPI_TRANSFORM_NAME: str = "read_transparency_cpi_csv"


# Re-export the audit-trail coercion helpers so the
# per-row emission loop can call them via a single
# import. The helpers themselves live in
# :mod:`._missing_values` (the canonical location per
# the UCDP / V-Dem pattern).
__all__ = [
    "TRANSPARENCY_CPI_TRANSFORM_NAME",
    "_coerce_float_or_none",
    "_coerce_int_or_none",
    "_raw_value_to_string",
    "build_observation",
]
