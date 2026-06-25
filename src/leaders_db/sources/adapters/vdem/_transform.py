"""Unified-source V-Dem observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified-source V-Dem adapter. The function
takes the narrow DataFrame returned by the legacy reader
(one row per ``(country_text_id, year)`` with one column per
catalog indicator, plus the four identity columns
``country_name`` / ``country_text_id`` / ``vdem_country_id``
/ ``year``) and emits the canonical observation records
with raw locators (CSV path + column name + row number when
feasible), transform locators (transform name + catalog key
+ rule id), attribution text (Rule #15), and source-version
stamps (canonical ``v16``).

Split out of
:mod:`leaders_db.sources.adapters.vdem.adapter` to keep the
adapter class module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and respect
the documented 400-line module convention.

The missing-value coercion helpers live in
:mod:`._missing_values`; this module delegates to them so the
legacy sentinel contract is preserved verbatim without
inflating the transform module's line count.

Per-observation contract
------------------------

Every observation's ``extension`` carries:

- ``vdem_raw_column`` -- the catalog ``raw_column`` (e.g.
  ``v2x_polyarchy``); mirrors the WDI / WGI convention so
  downstream score modules can resolve the raw value back to
  the catalog indicator without re-reading the legacy
  catalog.
- ``vdem_country_id`` -- V-Dem's own integer country id
  (Stage 3 country match resolves this to our canonical
  ISO3). Always present; ``None`` only when the source CSV
  is missing the column.
- ``vdem_country_text_id`` -- V-Dem's COW code
  (``country_text_id``); matches the legacy Stage 2 DB
  writer's ``source_row_reference`` prefix.
- ``vdem_rating_category`` -- the catalog ``rating_category``
  value (``political_freedom`` / ``integrity`` /
  ``effectiveness`` / ``domestic_violence`` /
  ``social_wellbeing``); carried so downstream code can
  filter by category without re-reading the legacy catalog.
- ``source_row_reference`` -- ``"vdem:<country_text_id>"``;
  matches the legacy Stage 2 DB writer.
- ``attribution`` -- the canonical V-Dem citation block
  (Rule #15; byte-identical to the legacy
  ``VDEM_ATTRIBUTION`` constant and the
  ``docs/sources/attributions.md`` entry).
- ``raw_value`` -- the audit-trail raw cell value as a string
  (preserves V-Dem missing sentinels like ``"-999.0"`` or
  ``"nan"``).
- ``higher_is_better`` -- boolean; preserved from the catalog
  so downstream normalization can resolve the direction
  without re-reading the catalog.
- ``raw_scale`` -- catalog ``raw_scale`` string
  (``"0-1"`` / ``"0-3"`` / ``"0-4"`` / ``"continuous"``).
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

from ._catalog import rating_category_to_observation_family
from ._descriptor import (
    VDEM_ATTRIBUTION_TEXT,
    VDEM_CSV_ASSET_ID,
    VDEM_DEFAULT_VERSION,
    VDEM_SOURCE_KEY,
)
from ._missing_values import (
    coerce_float,
    is_real_number,
    raw_value_to_string,
)

# Transform-name string carried on every NormalizedObservation's
# ``transform_locator``. Surfaces the legacy reader /
# transform that produced the observation so downstream
# scoring can audit the parse path.
VDEM_TRANSFORM_NAME: str = "read_vdem_csv"


def _canonical_version() -> str:
    """Return the canonical V-Dem version stamp.

    The unified adapter hardcodes the canonical version
    ``"v16"`` (matches the staged
    ``data/raw/vdem/metadata.json`` ``source_version``
    field and the canonical attribution block in
    ``docs/sources/attributions.md``). Observations therefore
    carry this validated version, not arbitrary metadata /
    request text.
    """
    return VDEM_DEFAULT_VERSION


def emit_vdem_observations(
    narrow_df: Any,
    request: SourceIngestRequest,
    csv_path: Path | None,
    metadata: dict[str, Any] | None,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the narrow V-Dem frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    narrow_df:
        The narrow DataFrame returned by the legacy
        :func:`leaders_db.ingest.vdem_io.read_vdem_csv`
        reader -- one row per ``(country_text_id, year)``
        with one column per catalog ``raw_column``, plus the
        four identity columns (``country_name`` /
        ``country_text_id`` / ``vdem_country_id`` /
        ``year``). ``NaN`` / ``-999`` cells are coerced to
        ``None`` and emitted with ``value_type="missing"``
        (no silent conversion of missing raw cells;
        SRC-OBS-007).
    request:
        The request-scoped :class:`SourceIngestRequest`
        driving the run. Used for the source-version stamp.
        Year / country / leader filters are applied by the
        caller BEFORE this helper is invoked so the
        narrow_df has already been narrowed.
    csv_path:
        Optional path to the staged
        ``V-Dem-CY-Full+Others-v16.csv``; carried verbatim
        onto every observation's :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload. Not
        consumed for the observation emission contract --
        kept in the signature for symmetry with the PWT /
        Maddison / WDI / WGI transform helpers.
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
        ``narrow_df`` is empty or ``specs`` is ``None`` /
        empty (e.g. an out-of-coverage year request, or the
        staged fixture has no rows for the requested filter
        scope, or the catalog was not provided).
    """
    if metadata is None:
        metadata = {}

    if narrow_df is None or specs is None or len(specs) == 0:
        return iter(())

    csv_path_str = str(csv_path) if isinstance(csv_path, Path) else None
    asset_id = VDEM_CSV_ASSET_ID
    source_version = _canonical_version()

    # Pre-build a lookup from ``raw_column`` -> spec so the
    # per-row emission loop does not have to scan the
    # catalog for every cell.
    specs_by_raw_column: dict[str, Any] = {
        spec.raw_column: spec for spec in specs
    }

    observations: list[NormalizedObservation] = []
    # Iterate via ``itertuples`` for speed: the narrow frame
    # has up to 22 columns + 4 identity columns, so the
    # per-row overhead matters. We do NOT rely on
    # ``DataFrame.columns`` ordering -- we read each row's
    # cell by catalog ``raw_column`` so the output order is
    # the catalog order (deterministic for downstream audit).
    for row in narrow_df.itertuples(index=False):
        # Identity columns. The legacy reader renames
        # ``country_id`` -> ``vdem_country_id`` so the
        # narrow frame does not collide with the
        # ``countries.id`` FK on Stage 3.
        country_text_id = str(row.country_text_id)
        year = int(row.year)
        country_name = getattr(row, "country_name", None)
        vdem_country_id_value = getattr(
            row, "vdem_country_id", None,
        )

        # The legacy source row reference pattern is
        # ``"vdem:<country_text_id>"`` (matches the legacy
        # Stage 2 DB writer).
        source_row_reference = f"vdem:{country_text_id}"

        for raw_column, spec in specs_by_raw_column.items():
            cell = getattr(row, raw_column)
            numeric_value = coerce_float(cell)
            is_real = is_real_number(numeric_value)

            observation_family = rating_category_to_observation_family(
                spec.rating_category,
            )

            extension: dict[str, Any] = {
                "vdem_raw_column": raw_column,
                "vdem_country_text_id": country_text_id,
                "vdem_rating_category": spec.rating_category,
                "source_row_reference": source_row_reference,
                "raw_value": raw_value_to_string(cell),
                "raw_scale": spec.raw_scale,
                "higher_is_better": spec.higher_is_better,
                "normalized_scale_target": spec.normalized_scale_target,
                "unit": spec.unit,
                "attribution": VDEM_ATTRIBUTION_TEXT,
            }
            if vdem_country_id_value is not None and not (
                isinstance(vdem_country_id_value, float)
                and math.isnan(vdem_country_id_value)
            ):
                # Preserve the V-Dem integer country id for
                # Stage 3 country match. Cast to int when
                # possible; keep the raw value otherwise.
                try:
                    extension["vdem_country_id"] = int(
                        vdem_country_id_value,
                    )
                except (TypeError, ValueError):
                    extension["vdem_country_id"] = (
                        vdem_country_id_value
                    )
            if isinstance(country_name, str) and country_name.strip():
                extension["vdem_country_name"] = country_name

            observations.append(
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=(
                        f"vdem:{country_text_id}:{year}:"
                        f"{raw_column}"
                    ),
                    observation_family=observation_family,
                    indicator_code=spec.variable_name,
                    value=(
                        float(numeric_value) if is_real else None
                    ),
                    value_type=(
                        "numeric" if is_real else "missing"
                    ),
                    year=year,
                    # The unified contract uses the V-Dem
                    # ``country_text_id`` as the country code
                    # (it is the COW code, the canonical
                    # V-Dem country identifier). Stage 3
                    # country match resolves it to our
                    # canonical ISO3.
                    country_code=country_text_id,
                    country_name=(
                        country_name
                        if isinstance(country_name, str)
                        and country_name.strip()
                        else None
                    ),
                    leader_id=None,
                    leader_name=None,
                    unit=spec.unit or None,
                    scale=spec.raw_scale or None,
                    source_version=source_version,
                    raw_locator=RawLocator(
                        asset_id=asset_id,
                        path=csv_path_str,
                        # The legacy narrow frame is the
                        # pivot of the wide V-Dem CSV; the
                        # original CSV row index is not
                        # preserved through the long-to-wide
                        # pivot. Per the brief: "If row
                        # numbers are not available from
                        # legacy wide frame, use best
                        # available locator and
                        # document/test that row_number is
                        # None rather than fabricated."
                        row_number=None,
                        column_name=raw_column,
                    ),
                    transform_locator=TransformLocator(
                        adapter_version=None,
                        transform_name=VDEM_TRANSFORM_NAME,
                        catalog_key=VDEM_SOURCE_KEY,
                        rule_id=(
                            f"vdem:{country_text_id}:{year}:"
                            f"{raw_column}"
                        ),
                    ),
                    quality_flags=(),
                    warnings=(),
                    extension=extension,
                ),
            )
    return iter(observations)


__all__ = [
    "VDEM_TRANSFORM_NAME",
    "emit_vdem_observations",
]
