"""Unified-source RSF per-row emission-loop helpers.

This module owns the per-row helper functions used by
the unified-source RSF observation-emission code in
:mod:`._transform`. The helpers handle:

- :func:`_resolve_actual_column_name` -- resolve the
  year-specific actual column name from the
  narrow-frame ``source_row_reference`` third
  segment (e.g. ``Score N`` for 2002-2021, ``Score``
  for 2022-2024, ``Score 2025`` for 2025, ``Score
  2026`` for 2026).
- :func:`_parse_source_row_reference` -- parse the
  legacy ``source_row_reference`` shape
  (``"rsf_press_freedom:<iso3>:<actual_column>"``)
  into ``(iso3, actual_column)``.
- :func:`_find_spec_for_variable` -- linear scan to
  find the catalog spec matching one
  ``variable_name``.
- :func:`_is_component_raw_column` -- guard for the
  pre/post-2022 schema break (the 5
  component-context indicators are 2022+ only).
- :func:`_resolve_actual_column_for_year` -- resolve
  the per-year actual column name from the
  descriptor constants (used by the
  per-observation extension field).

Split out of :mod:`._transform` so the per-row
emission loop stays focused on the iteration +
filter logic + the :class:`NormalizedObservation`
construction. The helpers mirror the WGI / V-Dem /
CPI / UCDP / PTS missing-value helper shape so the
unified-source subsystem stays consistent across
adapters.
"""

from __future__ import annotations

from typing import Any


def _resolve_actual_column_name(
    raw_column: str | None,
    actual_column: str | None,
) -> str:
    """Return the year-specific actual column name
    preserved on the per-observation
    ``rsf_actual_column`` extension field.

    The legacy narrow frame's ``source_row_reference``
    carries the actual column name in its third
    segment (``rsf_press_freedom:<iso3>:<actual>``);
    the helper extracts the third segment for the
    per-observation ``rsf_actual_column`` /
    ``column_name`` field. Falls back to the catalog
    ``raw_column`` when the actual column is not
    preserved (defensive guard for a future refactor).
    """
    if isinstance(actual_column, str) and actual_column.strip():
        return actual_column.strip()
    if isinstance(raw_column, str) and raw_column.strip():
        return raw_column.strip()
    return ""


def _parse_source_row_reference(
    source_row_reference: str | None,
) -> tuple[str, str]:
    """Parse the legacy ``source_row_reference`` into
    ``(iso3, actual_column)``.

    The canonical legacy shape is
    ``"rsf_press_freedom:<iso3>:<actual_column>"``
    (per the legacy
    :func:`leaders_db.ingest.rsf_press_freedom_csv._build_rows_for_iso3`
    helper). The helper extracts the
    ``<iso3>`` and ``<actual_column>`` segments and
    returns ``("", "")`` on a malformed reference
    (defensive guard).
    """
    if not isinstance(source_row_reference, str):
        return "", ""
    parts = source_row_reference.split(":")
    if len(parts) < 3:
        return "", ""
    iso3 = parts[1].strip().upper() if len(parts) > 1 else ""
    actual = parts[2].strip() if len(parts) > 2 else ""
    return iso3, actual


def _find_spec_for_variable(
    specs: list[Any],
    variable_name: str,
) -> Any:
    """Return the spec matching ``variable_name`` (or
    ``None`` if no match).

    The legacy catalog spec exposes a ``variable_name``
    field that matches the narrow frame's
    ``variable_name`` column. The helper is a linear
    scan so the per-row emission loop's overhead stays
    minimal (the 7 RSF specs are loaded once and
    scanned per row; the per-row scan is O(7) so the
    overall emission is O(N) for N narrow-frame rows).
    """
    for spec in specs:
        if getattr(spec, "variable_name", None) == variable_name:
            return spec
    return None


def _is_component_raw_column(raw_column: str | None) -> bool:
    """Return ``True`` if ``raw_column`` is one of the
    5 component-context indicator raw_columns (2022+
    files only).

    The unified transform uses this guard to enforce
    the pre/post-2022 schema break: pre-2022 files
    do not carry the 5 component-context columns, so
    the per-row emission loop should never emit a
    component observation for a pre-2022 year. The
    guard is defensive; the narrow frame's
    ``source_row_reference`` already carries the
    year-specific actual column name, so a
    ``source_row_reference`` whose third segment
    matches a component column name is implicitly
    2022+ only.
    """
    from ._observation_builder import (
        RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS,
    )
    return raw_column in RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS


__all__ = [
    "_find_spec_for_variable",
    "_is_component_raw_column",
    "_parse_source_row_reference",
    "_resolve_actual_column_name",
]
