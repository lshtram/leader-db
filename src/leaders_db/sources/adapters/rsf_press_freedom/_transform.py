"""Unified-source RSF observation-emission helpers.

This module owns the per-row emission loop for the
unified-source Reporters Without Borders World Press
Freedom Index adapter. The function takes the
narrow-format country-year DataFrame returned by the
legacy reader
(:func:`leaders_db.ingest.rsf_press_freedom_csv.read_rsf_press_freedom_csv`)
-- one row per
``(iso3, year, variable_name)`` triple with the audit-
trail columns ``raw_value`` / ``normalized_value`` /
``source_row_reference`` -- and emits the canonical
observation records via :func:`build_observation` from
:mod:`._observation_builder`.

Split out of
:mod:`leaders_db.sources.adapters.rsf_press_freedom.adapter`
to keep the adapter class module focused on the
lifecycle methods (``check_ready`` / ``read_raw`` /
``transform``) and respect the documented 400-line
module convention. The per-row emission-loop helpers
(``_resolve_actual_column_name`` /
``_parse_source_row_reference`` /
``_find_spec_for_variable`` /
``_is_component_raw_column``) live in :mod:`._helpers`.

The per-row observation construction contract lives in
:mod:`._observation_builder`. The missing-value
coercion helpers (the comma-decimal normalization +
the int-coercion for rank) live in
:mod:`._missing_values`. This module composes them
into the per-row emission loop.

Pre/post-2022 schema semantics
------------------------------

The RSF World Press Freedom Index changed methodology
around the 2022 edition:

- Pre-2022 (2002-2021): 16-col wide format with
  ``Score N`` + ``Rank N`` columns only. The
  catalog's 5 component-context indicators
  (``rsf_press_freedom_political_context`` /
  ``rsf_press_freedom_economic_context`` /
  ``rsf_press_freedom_legal_context`` /
  ``rsf_press_freedom_social_context`` /
  ``rsf_press_freedom_safety``) are NOT emitted for
  these years because the actual columns are absent
  in the legacy CSV.
- 2022+: 22-26 col wide format with
  ``Score`` / ``Rank`` + 5 component-context columns
  (``Political Context`` / ``Economic Context`` /
  ``Legal Context`` / ``Social Context`` /
  ``Safety``). All 7 catalog indicators are emitted
  for these years.

The pre/post-2022 methodology/schema distinction is
preserved on every observation via the
``extension["rsf_schema_group"]`` field (1 = pre-2022;
2+ = post-2022). The pre-2022 scores use a different
ordinal scale than the post-2022 0-100 scale; the
Stage 5 score module owns the normalization to the
0-10 target. The unified transform does NOT silently
merge pre/post-2022 methodology -- the raw cell text
is preserved verbatim on
``extension["raw_value"]`` and the
``rsf_schema_group`` flag tells downstream code which
methodology applied.

The unified transform skips rows whose
``normalized_value`` cell is ``None`` / ``NaN`` -- no
silent conversion of missing raw cells (SRC-OBS-007).
The audit-trail ``raw_value`` is preserved on the
observation's ``extension`` so even the dropped cells
carry an auditable raw cell string.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    SourceIngestRequest,
)

from ._helpers import (
    _find_spec_for_variable,
    _parse_source_row_reference,
    _resolve_actual_column_name,
)
from ._missing_values import (
    _is_missing,
    _raw_cell_text,
)
from ._observation_builder import build_observation
from ._observation_helpers import (
    RSF_PRESS_FREEDOM_TRANSFORM_NAME,
    _default_asset_id_for_year,
    _default_source_version,
)


def _build_csv_path_for_year(
    csv_paths: list[Path] | None,
) -> dict[int, Path]:
    """Return a ``year -> per-year CSV path`` lookup.

    The path stem must match the canonical pattern
    ``rsf_press_freedom_<year>.csv`` (per
    :data:`leaders_db.sources.adapters.rsf_press_freedom._constants.RSF_PRESS_FREEDOM_CSV_NAME_PATTERN`);
    non-conforming paths are silently skipped. Missing
    years fall back to ``None`` in the caller (defensive
    guard for an out-of-band bundle mutation).
    """
    lookup: dict[int, Path] = {}
    if not csv_paths:
        return lookup
    for path in csv_paths:
        if not isinstance(path, Path):
            continue
        stem = path.stem
        if not stem.startswith("rsf_press_freedom_"):
            continue
        year_str = stem.removeprefix("rsf_press_freedom_")
        try:
            year_int = int(year_str)
        except ValueError:
            continue
        lookup[year_int] = path
    return lookup


def _resolve_row_identity(
    row: Any,
) -> tuple[str, int, str] | None:
    """Return ``(iso3, year, variable_name)`` for one
    narrow-frame row, or ``None`` when the identity
    columns are missing / malformed.

    The legacy narrow-format frame carries string
    ``iso3``, int ``year``, string ``variable_name``,
    and the audit-trail columns ``raw_value``,
    ``normalized_value``, ``source_row_reference``.
    Malformed identity columns drop the row (no
    fabricated observation).
    """
    iso3_raw = getattr(row, "iso3", None)
    if not isinstance(iso3_raw, str) or not iso3_raw.strip():
        return None
    iso3 = iso3_raw.strip().upper()
    try:
        year = int(row.year)
    except (TypeError, ValueError):
        return None
    variable_name = getattr(row, "variable_name", None)
    if not isinstance(variable_name, str) or not variable_name:
        return None
    return iso3, year, variable_name


def _resolve_iso3_from_reference(
    row_iso3: str,
    source_row_reference: Any,
    parsed_actual_column: str,
) -> tuple[str, str]:
    """Return ``(iso3, source_row_reference)`` after
    reconciling the row iso3 with the legacy
    ``source_row_reference`` iso3.

    The legacy reader's reference iso3 may be
    lowercased; the unified transform normalizes to
    upper case for the canonical observation
    ``country_code``. The returned
    ``source_row_reference`` is the trimmed raw
    value when present (preserved on the per-row
    audit trail) or the canonical
    ``rsf_press_freedom:<iso3>:<actual>`` pattern
    fallback.
    """
    ref_iso3, _ = _parse_source_row_reference(
        source_row_reference,
    )
    iso3 = ref_iso3 if ref_iso3 and ref_iso3 != row_iso3 else row_iso3
    if (
        isinstance(source_row_reference, str)
        and source_row_reference.strip()
    ):
        reference = source_row_reference.strip()
    else:
        reference = (
            f"rsf_press_freedom:{iso3}:{parsed_actual_column}"
        )
    return iso3, reference


def _build_row_observation(
    row: Any,
    request: SourceIngestRequest,
    specs: list[Any],
    source_version: str,
    csv_path_for_year: dict[int, Path],
) -> NormalizedObservation | None:
    """Build one :class:`NormalizedObservation` for one
    narrow-frame row, or ``None`` when the row is
    dropped (missing identity / missing cell /
    catalog miss).

    Per-row contract:

    - The legacy ``source_row_reference`` carries the
      ``rsf_press_freedom:<iso3>:<actual_column>``
      shape; the actual column is the year-specific
      actual column name (e.g. ``Score N`` for
      2002-2021, ``Score`` for 2022-2024,
      ``Score 2025`` for 2025, ``Score 2026`` for
      2026; ``Rank N`` for 2002-2021, ``Rank`` for
      2022+; the literal component column names for
      2022+).
    - ``normalized_value`` cells that are
      ``None`` / ``NaN`` are skipped (no silent
      conversion of missing raw cells; SRC-OBS-007).
    - ``raw_value`` is preserved verbatim on the
      observation's ``extension["raw_value"]`` audit
      column so downstream audit code can recover the
      original cell text without re-reading the
      legacy CSV.
    """
    identity = _resolve_row_identity(row)
    if identity is None:
        return None
    iso3, year, variable_name = identity

    cell = getattr(row, "normalized_value", None)
    if _is_missing(cell):
        return None

    ref_iso3_raw, actual_column = _parse_source_row_reference(
        getattr(row, "source_row_reference", None),
    )
    iso3, source_row_reference = _resolve_iso3_from_reference(
        iso3,
        getattr(row, "source_row_reference", None),
        actual_column,
    )
    _ = ref_iso3_raw  # touched by _resolve_iso3_from_reference

    spec = _find_spec_for_variable(specs, variable_name)
    if spec is None:
        return None

    raw_cell_raw = getattr(row, "raw_value", None)
    raw_value_audit = (
        _raw_cell_text(raw_cell_raw)
        if raw_cell_raw is not None
        else _raw_cell_text(cell)
    )

    actual_column_name = _resolve_actual_column_name(
        getattr(spec, "raw_column", None),
        actual_column,
    )

    csv_path = csv_path_for_year.get(year)
    csv_path_str = (
        str(csv_path) if isinstance(csv_path, Path) else None
    )
    asset_id = _default_asset_id_for_year(year)

    return build_observation(
        request,
        iso3=iso3,
        year=year,
        variable_name=variable_name,
        spec=spec,
        cell=cell,
        raw_value_audit=raw_value_audit,
        csv_path_str=csv_path_str,
        asset_id=asset_id,
        actual_column=actual_column_name,
        source_row_reference=source_row_reference,
        source_version=source_version,
    )


def emit_rsf_press_freedom_observations(
    narrow_df: Any,
    request: SourceIngestRequest,
    csv_paths: list[Path] | None,
    metadata: dict[str, Any] | None,
    *,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the narrow RSF frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    narrow_df:
        The narrow-format DataFrame returned by the
        legacy
        :func:`leaders_db.ingest.rsf_press_freedom_csv.read_rsf_press_freedom_csv`
        reader -- one row per
        ``(iso3, year, variable_name)`` triple with
        columns ``iso3``, ``year``, ``variable_name``,
        ``raw_value``, ``normalized_value``,
        ``source_row_reference``. ``None`` /
        ``NaN`` cells in the ``normalized_value``
        column are skipped (no silent conversion of
        missing raw cells; SRC-OBS-007).
    request:
        The request-scoped
        :class:`SourceIngestRequest` driving the run.
        Used for the source-version stamp. Year /
        country / leader filters are applied by the
        caller BEFORE this helper is invoked so the
        narrow_df has already been narrowed.
    csv_paths:
        Optional list of per-year CSV paths. The
        per-observation ``RawLocator`` carries the
        CSV path matching the observation's year
        (so audit code can recover the exact
        per-year file).
    metadata:
        Optional parsed bundle ``metadata.json``
        payload. Not consumed for the observation
        emission contract -- kept in the signature
        for symmetry with the WGI / V-Dem / CPI /
        UCDP / PTS transform helpers.
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
        when ``narrow_df`` is empty or ``specs`` is
        ``None`` / empty (e.g. an out-of-coverage year
        request, or the staged fixture has no rows for
        the requested filter scope, or the catalog was
        not provided).
    """
    if metadata is None:
        metadata = {}
    del metadata  # accepted for signature symmetry only.

    if narrow_df is None or specs is None or len(specs) == 0:
        return iter(())

    csv_path_for_year = _build_csv_path_for_year(csv_paths)
    source_version = _default_source_version()

    observations: list[NormalizedObservation] = []
    for row in narrow_df.itertuples(index=False):
        observation = _build_row_observation(
            row,
            request,
            specs,
            source_version,
            csv_path_for_year,
        )
        if observation is not None:
            observations.append(observation)
    return iter(observations)


__all__ = [
    "RSF_PRESS_FREEDOM_TRANSFORM_NAME",
    "emit_rsf_press_freedom_observations",
]
