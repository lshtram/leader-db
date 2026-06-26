"""Unified-source BTI per-row emission-loop helpers.

This module owns the helper functions used by
:func:`leaders_db.sources.adapters.bti._transform.emit_bti_observations`
that are independent of the per-row
:class:`NormalizedObservation` construction contract.

Split out of :mod:`._transform` so the per-row
emission loop stays focused on the iteration + filter
logic, and so the helper functions are unit-testable
in isolation. The helpers cover:

- :func:`_canonical_source_version` -- the canonical
  BTI source-version stamp (the brief
  ``"BTI 2026"`` stamp; the unified adapter
  hardcodes it so the audit trail matches the
  canonical attribution block).
- :func:`_canonical_asset_id` -- the canonical BTI
  xlsx asset id (used for every observation's
  :class:`RawLocator` in a single run).
- :func:`_resolve_sheet_name` -- recover the resolved
  BTI edition sheet name from the wide frame's
  ``_bti_sheet_name`` attribute (set by the legacy
  reader).
- :func:`_resolve_target_year` -- recover the
  canonical in-coverage year for the resolved BTI
  sheet (via the legacy
  :func:`leaders_db.ingest.bti_io.target_year_for_sheet`
  bridge, lazily imported; defensive fallback to the
  wide frame's ``year`` column when the bridge
  returns ``None``).
- :func:`_build_raw_long_lookup` -- build the
  ``(country_name, year, variable_name) -> cell``
  lookup from the legacy pre-coercion long frame
  attached to ``df.attrs["_bti_raw_long"]``.
- :func:`_locate_row_index` -- return the wide-frame
  row index for ``(country_name, year)`` so the
  observation's :class:`RawLocator` carries a
  positional row index for audit traceability.
"""

from __future__ import annotations

from typing import Any


def _canonical_source_version() -> str:
    """Return the canonical BTI source version
    stamp.

    The unified adapter hardcodes the canonical
    version ``"BTI 2026"`` (matches the canonical
    attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not
    arbitrary metadata / request text.
    """
    # Lazy import: keeps this module importable
    # without ``leaders_db.ingest`` at module level.
    from ._observation_builder import _default_source_version

    return _default_source_version()


def _canonical_asset_id() -> str:
    """Return the canonical BTI xlsx asset id.

    The legacy BTI reader does not embed the asset
    id in the wide frame; the transform layer uses
    this helper so all observations in a single run
    share the same logical asset id (matching the
    WGI / V-Dem / CPI / UCDP / PTS / RSF
    convention).
    """
    # Lazy import: keeps this module importable
    # without ``leaders_db.ingest`` at module level.
    from ._observation_builder import _default_asset_id

    return _default_asset_id()


def _resolve_sheet_name(wide_df: Any) -> str | None:
    """Return the resolved BTI edition sheet name
    from the wide frame's attrs, or ``None`` if
    the attrs are not set.

    The legacy
    :func:`leaders_db.ingest.bti_xlsx.read_bti`
    reader attaches ``_bti_sheet_name`` to the wide
    frame's attrs so the unified transform can
    surface the source-edition semantics on every
    observation's ``extension["bti_sheet_name"]``
    without re-resolving.
    """
    if not hasattr(wide_df, "attrs"):
        return None
    raw_sheet_name = wide_df.attrs.get("_bti_sheet_name")
    if not isinstance(raw_sheet_name, str) or not raw_sheet_name.strip():
        return None
    return raw_sheet_name.strip()


def _resolve_target_year(wide_df: Any) -> int | None:
    """Return the canonical in-coverage year for
    the resolved BTI sheet, or ``None`` if the
    frame does not carry a year column.

    The function prefers the resolved sheet name's
    canonical target year (via the legacy
    :func:`leaders_db.ingest.bti_io.target_year_for_sheet`
    bridge) over the wide frame's ``year`` column
    so the audit-trail ``bti_target_year`` extension
    field reflects the source-edition semantics
    (the in-coverage year the BTI edition
    represents -- e.g. ``2023`` for ``BTI 2024``)
    rather than the latest sampled year.
    """
    sheet_name = _resolve_sheet_name(wide_df)
    if sheet_name is not None:
        # Lazy import: keeps this helper importable
        # without ``leaders_db.ingest`` at module
        # level.
        from leaders_db.ingest.bti_io import (
            target_year_for_sheet,
        )

        resolved_target = target_year_for_sheet(sheet_name)
        if isinstance(resolved_target, int):
            return resolved_target

    # Defensive fallback: derive from the wide
    # frame's ``year`` column when the resolved
    # sheet name lookup fails (the frame always
    # carries a year column per the legacy
    # reader's contract).
    if wide_df is None or not hasattr(wide_df, "columns"):
        return None
    if "year" not in wide_df.columns:
        return None
    try:
        years = sorted({
            int(y) for y in wide_df["year"].tolist()
        })
    except (TypeError, ValueError):
        return None
    if not years:
        return None
    # Use the latest year in the frame as the
    # defensive fallback target year. The frame
    # carries a single year for a single-edition
    # run per the legacy reader's contract; the
    # latest year is therefore the canonical
    # target year for this run.
    return int(years[-1])


def _build_raw_long_lookup(
    raw_long: Any,
) -> dict[tuple[str, int, str], Any]:
    """Build the ``(country, year, variable_name) ->
    cell`` lookup from the legacy pre-coercion long
    frame.

    The legacy
    :func:`leaders_db.ingest.bti_xlsx.read_bti`
    reader attaches ``_bti_raw_long`` to the wide
    frame's attrs as a long DataFrame with columns
    ``country``, ``year``, ``variable_name``,
    ``value``. The unified transform iterates the
    wide frame and recovers the pre-coercion raw
    cell text from this lookup so the audit trail
    preserves what the xlsx actually said.
    """
    lookup: dict[tuple[str, int, str], Any] = {}
    if raw_long is None or not hasattr(raw_long, "iterrows"):
        return lookup
    try:
        for _, raw_long_row in raw_long.iterrows():
            country_name = str(raw_long_row["country"])
            year_value = int(raw_long_row["year"])
            variable_name = str(raw_long_row["variable_name"])
            lookup[(country_name, year_value, variable_name)] = (
                raw_long_row["value"]
            )
    except (KeyError, TypeError, ValueError):
        return lookup
    return lookup


def _resolve_row_sheet_context(
    row: Any,
    *,
    fallback_sheet_name: str | None,
    fallback_target_year: int | None,
    year: int,
) -> tuple[str, int]:
    """Return the per-row BTI sheet name and target year."""
    row_sheet_name = getattr(row, "bti_sheet_name", None)
    if not isinstance(row_sheet_name, str) or not row_sheet_name:
        row_sheet_name = fallback_sheet_name or ""
    row_target_year = year if row_sheet_name else fallback_target_year
    if row_target_year is None:
        row_target_year = year
    return row_sheet_name, row_target_year


def _locate_row_index(
    wide_df: Any,
    country_name: str,
    year: int,
) -> int | None:
    """Return the wide-frame row index for
    ``(country_name, year)``.

    The legacy wide-format DataFrame is sorted by
    ``country`` ascending for deterministic
    idempotency (per the legacy reader); the
    ``country`` and ``year`` columns form the
    canonical country-year key. The unified transform
    preserves the row index when feasible (per
    ``docs/architecture/sources.md`` §5.4) so audit
    code can recover the input row from the staged
    xlsx byte-for-byte.

    Returns ``None`` when the ``(country, year)``
    key does not match any row in the frame
    (defensive guard for a malformed wide frame).
    """
    if wide_df is None:
        return None
    try:
        match = wide_df.loc[
            (wide_df["country"] == country_name)
            & (wide_df["year"].astype(int) == int(year))
        ]
    except (KeyError, TypeError, ValueError):
        return None
    if match.empty:
        return None
    idx_value = match.index[0]
    try:
        return int(idx_value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "_build_raw_long_lookup",
    "_canonical_asset_id",
    "_canonical_source_version",
    "_locate_row_index",
    "_resolve_row_sheet_context",
    "_resolve_sheet_name",
    "_resolve_target_year",
]
