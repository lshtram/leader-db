"""Unified-source PTS per-row observation-construction
helper.

This module owns the per-row
:class:`NormalizedObservation` construction helper used
by
:func:`leaders_db.sources.adapters.pts._transform.emit_pts_observations`.

Split out of :mod:`._transform` so the per-row emission
loop stays focused on the iteration + filter logic, and
so the observation-construction contract is unit-testable
in isolation. The helper builds one observation per
``(COW_Code_A, year, variable_name)`` triple and carries
the canonical PTS attribution block, the per-row
audit-trail fields (``country`` / ``cow_code`` /
``region`` / ``pts_na_status``), the pre-coercion
``raw_value`` cell text, the canonical
``source_row_reference`` (``"pts:<COW_Code_A>"``) pattern
(matching the legacy Stage 2 DB writer), and the
direction hints (``higher_is_better`` / ``raw_scale`` /
``normalized_scale_target``).

Per-observation contract
------------------------

Every observation's ``extension`` carries:

- ``pts_raw_column`` -- the catalog ``raw_column``
  (``PTS_A`` / ``PTS_H`` / ``PTS_S``); mirrors the
  WGI / V-Dem / CPI / UCDP convention so downstream
  score modules can resolve the raw value back to the
  catalog indicator without re-reading the legacy
  catalog.
- ``pts_cow_code`` -- the canonical COW_Code_A 3-letter
  alphabetic code (e.g. ``USA``); matches the legacy
  Stage 2 DB writer's ``source_row_reference``
  suffix.
- ``pts_rating_category`` -- the catalog
  ``rating_category`` value (``domestic_violence``);
  carried so downstream code can filter by category
  without re-reading the legacy catalog.
- ``source_row_reference`` --
  ``"pts:<COW_Code_A>"``; matches the legacy Stage 2
  DB writer.
- ``attribution`` -- the canonical PTS citation block
  (Rule #15; byte-identical to the legacy
  ``PTS_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/pts_io.py`` and to the
  ``pts`` section in
  ``docs/sources/attributions.md``).
- ``raw_value`` -- the audit-trail raw cell value as a
  string (preserves the verbatim xlsx cell;
  ``"NA"`` for the missing-sentinel string, ``"3"``
  for an int 1-5 cell).
- ``pts_country_name`` -- the xlsx ``Country``
  display name (e.g. ``"United States"``); preserved
  verbatim.
- ``pts_region`` -- the xlsx ``Region`` column
  (e.g. ``"sa"``, ``"lac"``, ``"mena"``); preserved
  verbatim so the manual-review queue can stratify by
  region.
- ``pts_na_status`` -- the paired ``NA_Status_X``
  integer (0/66/77/88/99); preserved verbatim so
  audit code can recover the §6 sentinel matrix
  decision.
- ``higher_is_better`` -- boolean; preserved from the
  catalog so downstream normalization can resolve the
  direction without re-reading the catalog. The PTS
  score carries ``higher_is_better=False`` (higher =
  more terror = worse; the Stage 5 score module
  inverts the direction).
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"ordinal"``).
- ``normalized_scale_target`` -- catalog
  ``normalized_scale_target`` (``"0-10"``; the PTS
  project uses the inverted 0-10 score where 0 =
  most terror / 10 = least terror).

Direction-hint contract
-----------------------

The PTS raw 1-5 scale is preserved verbatim on
``source_observations.normalized_value``; the
``higher_is_better=False`` flag tells downstream
normalization to invert the direction. This is the same
convention as SIPRI milex's 4 indicators (more spending
= worse peace signal) and V-Dem's 3 repression
indicators. The transform layer does NOT silently
invert the value -- the audit trail preserves the raw
1-5 int so the Stage 5 score module can apply the
inverted 0-10 mapping (PTS 1 -> 10, ..., PTS 5 -> 0) per
design doc §3.
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
    PTS_ATTRIBUTION_TEXT,
    PTS_DEFAULT_VERSION,
    PTS_RAW_COLUMNS,
    PTS_SOURCE_KEY,
    PTS_XLSX_ASSET_ID,
    PTS_XLSX_NAME,
)

# Module-local binding for the per-row transform name.
# The ``emit_pts_observations`` helper resolves this
# constant from the transform module at import time; we
# hardcode it here for symmetry with the UCDP / V-Dem /
# WGI / CPI pattern (one module-local constant per
# source). The transform name mirrors the legacy
# ``read_pts`` reader so audit code can recover the
# transform-stage from the observation's
# ``transform_locator.transform_name``.
PTS_TRANSFORM_NAME: str = "read_pts"


def build_observation(
    request: SourceIngestRequest,
    *,
    cow_code: str,
    year: int,
    variable_name: str,
    spec: Any,
    cell: Any,
    raw_value_audit: str,
    na_status_audit: str,
    xlsx_path_str: str | None,
    asset_id: str,
    row_number: int | None,
    source_version: str,
    source_row_reference: str,
    country_label: str | None,
    region_label: str | None,
) -> NormalizedObservation:
    """Construct a single
    :class:`NormalizedObservation` record.

    Helper extracted from
    :func:`emit_pts_observations` so the per-row loop
    stays compact and the observation-construction
    contract is reusable / unit-testable in isolation.

    Every observation's ``quality_flags`` is empty (the
    PTS dataset is a direct country-year measurement,
    not an aggregation). The
    ``transform_locator.rule_id`` and
    ``observation_id`` carry the
    ``pts:<COW_Code_A>:<year>:<variable_name>`` pattern
    (the canonical per-row locator convention matching
    the legacy Stage 2 DB writer's
    ``source_row_reference`` shape).

    The ``value`` is the integer 1-5 raw score (cast to
    ``int``); ``value_type="numeric"``. Missing cells
    (``None``) are NOT emitted (the transform layer
    filters them out per the §6 sentinel matrix).
    """
    observation_family = _rating_category_to_family(
        getattr(spec, "rating_category", ""),
    )

    extension: dict[str, Any] = {
        "pts_raw_column": getattr(spec, "raw_column", None),
        "pts_cow_code": cow_code,
        "pts_rating_category": getattr(
            spec, "rating_category", None,
        ),
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_audit,
        "pts_na_status": na_status_audit,
        "raw_scale": getattr(spec, "raw_scale", None),
        # Direction hint: PTS raw 1-5 is inverted so
        # higher = worse. The Stage 5 score module
        # applies the 0-10 inverted mapping. The flag
        # is preserved here so downstream code can
        # resolve the direction without re-reading the
        # catalog.
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", False),
        ),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", None,
        ),
        "unit": getattr(spec, "unit", None),
        "attribution": PTS_ATTRIBUTION_TEXT,
    }
    # Preserve the audit-trail country / region /
    # na_status labels on the per-observation
    # extension so downstream audit code can recover
    # the input row's labels without re-reading the
    # legacy xlsx.
    if (
        isinstance(country_label, str)
        and country_label.strip()
    ):
        extension["pts_country_name"] = country_label.strip()
    if (
        isinstance(region_label, str) and region_label.strip()
    ):
        extension["pts_region"] = region_label.strip()

    rule_id = (
        f"{PTS_SOURCE_KEY}:{cow_code}:{year}:{variable_name}"
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family=observation_family,
        indicator_code=variable_name,
        # Cast to int: the PTS raw scale is integer 1-5
        # (verified live 2026-06-18 per design doc §2).
        # Defensive cast through int() surfaces any
        # non-int cell that slipped through the
        # sentinel matrix (the transform layer already
        # filters ``None`` / ``NA`` cells so a non-int
        # cell is a programming error).
        value=int(cell),
        value_type="numeric",
        year=year,
        # The unified contract uses the PTS
        # ``COW_Code_A`` 3-letter alphabetic code
        # (e.g. ``USA``) as the country code. Stage 3
        # country match resolves it to ISO3 via the
        # canonical country table (a future Stage 3
        # deliverable; the design doc §7.3 contract is
        # to preserve the COW code at Stage 2 so the
        # lookup is straightforward).
        country_code=cow_code,
        country_name=(
            country_label
            if (
                isinstance(country_label, str)
                and country_label.strip()
            )
            else None
        ),
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None) or None,
        scale=getattr(spec, "raw_scale", None) or None,
        source_version=source_version,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=xlsx_path_str,
            row_number=row_number,
            column_name=getattr(spec, "raw_column", None),
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            # The transform name is bound at module
            # import time below; we resolve it here to
            # keep the helper self-contained.
            transform_name=PTS_TRANSFORM_NAME,
            catalog_key=PTS_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _rating_category_to_family(rating_category: str) -> str:
    """Resolve the rating-category to family via the
    catalog helper.

    Local wrapper to keep the per-row builder free of
    an explicit import cycle (the catalog module is
    small and side-effect free).
    """
    # Lazy import to keep this helper importable
    # without the catalog module's transitive
    # dependencies.
    from ._catalog import rating_category_to_observation_family
    return rating_category_to_observation_family(rating_category)


def _default_asset_id() -> str:
    """Return the canonical PTS xlsx asset id.

    The legacy PTS reader does not embed the asset id
    in the wide frame; the transform layer uses this
    helper so all observations in a single run share
    the same logical asset id (matching the WGI /
    V-Dem / CPI / UCDP convention).
    """
    return PTS_XLSX_ASSET_ID


def _default_source_version() -> str:
    """Return the canonical PTS source version stamp.

    The unified adapter hardcodes the canonical
    version ``"PTS-2025"`` (matches the staged
    ``data/raw/political_terror_scale/metadata.json``
    ``version`` field's canonical stamp + the
    canonical attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not
    arbitrary metadata / request text.
    """
    return PTS_DEFAULT_VERSION


def _raw_columns() -> tuple[str, ...]:
    """Return the canonical 3 PTS raw column names.

    Exposed for symmetry with the WGI / V-Dem / CPI
    pattern so the per-row emission loop can iterate
    the 3 raw columns when needed.
    """
    return PTS_RAW_COLUMNS


def _xlsx_name() -> str:
    """Return the canonical xlsx filename."""
    return PTS_XLSX_NAME


__all__ = [
    "PTS_TRANSFORM_NAME",
    "_default_asset_id",
    "_default_source_version",
    "_raw_columns",
    "_xlsx_name",
    "build_observation",
]
