"""Stage 2 -- CIRI Human Rights Data Project (CIRIGHTS) xlsx pivot / test seam.

This module holds the per-cell coercion, the audit-trail text
helper, the in-memory test seam, and the empty-frame helper for
the CIRIGHTS adapter. It is split out of
:mod:`leaders_db.ingest.cirights_xlsx` so the xlsx reader stays
focused on the file-format I/O and this module stays focused on the
data transformation.

Owns:

- :func:`_coerce_cirights_value` -- coerce a single xlsx / pandas
  cell into ``int | None``. The CIRIGHTS missing-data convention
  is the empty cell (openpyxl reads as ``None``); there is no
  string sentinel (``"NA"`` / ``"#N/A"``). The coerced int is
  what goes into the wide frame's ``Int64`` column.
- :func:`_raw_cell_text` -- render the original xlsx cell text
  for the ``source_observations.raw_value`` audit column. For
  empty cells, the audit text is the empty string (per the
  coding-guidelines design contract: do not invent values for
  missing cells).
- :func:`_empty_wide` -- build an empty wide frame with the
  expected column shape (used by the no-rows and out-of-range-year
  short circuits).
- :func:`read_cirights_from_dataframe` -- the test seam. Takes a
  pre-loaded long DataFrame (matching the 50-column xlsx header
  shape with the 7 catalog ``raw_column`` indicators) and returns
  the wide frame. Used by the tests to inject in-memory data and
  exercise the pivot without re-reading the xlsx.

The xlsx reader (:func:`read_xlsx_to_wide_dataframe`,
:func:`read_cirights`) lives in :mod:`leaders_db.ingest.cirights_xlsx`
(the file-format I/O module). The DB writers live in
:mod:`leaders_db.ingest.cirights_db` and
:mod:`leaders_db.ingest.cirights_db_helpers`. The orchestrator
lives in :mod:`leaders_db.ingest.cirights`.

The split is mandated by architecture §5: "no separate
``_helpers.py`` unless the module grows past 350 lines."
:mod:`cirights_xlsx` reached 555 lines (the trigger fired at 351),
so the pivot / test-seam was extracted into this module --
mirroring the UCDP / PTS 6-module split (``pts_xlsx.py`` +
``pts_xlsx_pivot.py``).
"""

from __future__ import annotations

import logging

import pandas as pd

from .cirights_io import IndicatorSpec

_logger = logging.getLogger(__name__)

__all__ = [
    "read_cirights_from_dataframe",
]


# ---------------------------------------------------------------------------
# Single-cell coercion
# ---------------------------------------------------------------------------


def _coerce_cirights_value(cell: object) -> int | None:
    """Coerce a single xlsx cell to ``int | None``.

    The CIRIGHTS missing-data convention is the empty cell
    (openpyxl reads as ``None``); there is no string sentinel
    (``"NA"`` / ``"#N/A"``). A defensive check for unexpected types
    is included: if a future xlsx release introduces a string
    sentinel, the cell is treated as missing and a WARNING is logged.

    Note on pandas apply: ``Series.apply`` on an ``Int64`` nullable
    Series converts the cell values to ``float`` (this is a known
    pandas behavior, not a data error). The function therefore
    accepts both ``int`` and clean-integer ``float`` values without
    warning. A ``float`` that is NOT a clean integer (e.g. ``5.3``)
    is treated as a data error and logged at WARNING; this is the
    same behavior as the V-Dem / WGI / WDI sentinels.

    Args:
        cell: the raw xlsx cell value (``int``, ``float``,
            ``None``, or defensive for other types).

    Returns:
        The int for numeric cells (cast to ``int`` so the wide frame
        column is the ``Int64`` nullable dtype); ``None`` for
        ``None`` cells or unexpected types.
    """
    if cell is None:
        return None
    # pandas NA (the Int64 nullable dtype's missing marker) is
    # neither None nor a basic type; check pd.isna before
    # isinstance to avoid ``str(pd.NA)`` -> ``"<NA>"`` and to
    # correctly handle missing values from the Int64 column.
    try:
        if pd.isna(cell):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(cell, bool):
        # bool is a subclass of int in Python; exclude so True/False
        # are not coerced to 1/0 (a bug, not data).
        _logger.warning(
            "CIRIGHTS unexpected cell value (bool): cell=%r. "
            "Treating as missing.",
            cell,
        )
        return None
    if isinstance(cell, int):
        return int(cell)
    if isinstance(cell, float):
        # Clean integer values (e.g. ``8.0`` from ``Series.apply`` on
        # an Int64 column) are coerced to int without warning. Non-
        # clean-integer floats (e.g. ``5.3``) are logged at WARNING
        # as a data error and rounded to int.
        if cell == int(cell):
            return int(cell)
        coerced = round(cell)
        _logger.warning(
            "CIRIGHTS unexpected float cell value: cell=%r. "
            "Coerced to int %d.",
            cell, coerced,
        )
        return int(coerced)
    # Anything else (str, list, dict, etc.). The live xlsx never
    # produces these for the 7 catalog columns; if a future release
    # does, log and treat as missing.
    _logger.warning(
        "CIRIGHTS unexpected cell type: cell=%r type=%s. "
        "Treating as missing.",
        cell, type(cell).__name__,
    )
    return None


def _raw_cell_text(cell: object) -> str:
    """Render the original xlsx cell text for the
    ``source_observations.raw_value`` audit column.

    Rules:

    - ``None`` (empty cell) or ``pd.NA`` -> ``""`` (no audit trail;
      the row is skipped by the orchestrator anyway, so this
      branch is defensive).
    - int -> ``str(int)`` (e.g. ``"5"``).
    - float (with a clean integer value) -> ``str(int(value))`` so
      the audit trail records the original integer, not ``"16.0"``.
      This is a defense in depth for the rare case where pandas
      upgrades an int column to float64 because of a missing
      value in the column.
    - Other types (defensive) -> ``str(cell)``.

    Per the design contract: the audit trail preserves the literal
    cell text the xlsx held. Empty cells are the missing-data
    sentinel; the wide frame drops them via the Int64 nullable
    dtype and the DB write skips the row.
    """
    if cell is None:
        return ""
    # pandas NA (the Int64 nullable dtype's missing marker) is
    # neither None nor a basic type; check pd.isna before
    # isinstance(cell, int/float) to avoid ``str(pd.NA)`` ->
    # ``"<NA>"`` (the literal pandas string).
    try:
        if pd.isna(cell):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(cell, bool):
        return str(cell)
    if isinstance(cell, int):
        return str(int(cell))
    if isinstance(cell, float):
        # Clean integer values that pandas upgraded to float64 (e.g.
        # because the column has a None elsewhere) get the integer
        # string form to keep the audit trail clean.
        if cell == int(cell):
            return str(int(cell))
        return str(cell)
    return str(cell)


# ---------------------------------------------------------------------------
# Empty-frame helper
# ---------------------------------------------------------------------------


def _empty_wide(specs: list[IndicatorSpec]) -> pd.DataFrame:
    """Build an empty wide frame with the expected column shape.

    Used when the year filter matches no rows, or when the source
    bundle is empty. Downstream code (``_build_observation_rows``)
    handles the empty case by returning an empty list.
    """
    cols: list[str] = ["country", "year"] + [s.variable_name for s in specs]
    wide = pd.DataFrame(columns=cols)
    wide.attrs["_cirights_raw_lookup"] = {}
    wide.attrs["year_window"] = (0, 0)
    return wide


# ---------------------------------------------------------------------------
# Test seam + long-to-wide pivot
# ---------------------------------------------------------------------------


def read_cirights_from_dataframe(
    long_df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> pd.DataFrame:
    """Apply the per-cell coercion + wide pivot + raw_lookup to a
    pre-loaded long DataFrame.

    Test seam: takes a pre-loaded DataFrame (matching the 50-column
    xlsx header shape with the catalog's ``raw_column`` indicator
    names) and returns the wide-format frame. Used by the tests to
    inject in-memory data and exercise the pivot without re-reading
    the xlsx.

    The xlsx is already in long format per country-year (one row
    per ``(country, year)``, indicator columns in cells). The
    "pivot" is therefore a column rename + per-cell coercion, not
    a reshape. The rename preserves the catalog's
    ``raw_column`` -> ``variable_name`` mapping; the per-cell
    coercion (:func:`_coerce_cirights_value`) preserves the int
    values while treating empty cells (openpyxl ``None``) as
    missing.

    Args:
        long_df: long-format input frame with the catalog's
            ``raw_column`` s + ``country`` + ``year`` columns. The
            indicator columns may be any numeric type (int, float);
            the coerce function handles both.
        specs: the catalog specs.

    Returns:
        A wide-format DataFrame (one row per ``(country, year)``,
        one column per catalog ``variable_name``). Indicator columns
        are ``Int64``; the wide frame carries
        ``_cirights_raw_lookup`` and ``year_window`` in ``df.attrs``.
    """
    if long_df.empty:
        return _empty_wide(specs)

    # Narrow to the 9 columns we care about (2 identity + 7 indicator)
    # and rename the indicator columns from ``raw_column`` to
    # ``variable_name``. The renaming is the "pivot" for CIRIGHTS
    # (the xlsx is already in long format per country-year).
    keep_cols: list[str] = (
        ["country", "year"] + [s.raw_column for s in specs]
    )
    keep_cols = [c for c in keep_cols if c in long_df.columns]
    narrow = long_df[keep_cols].copy()
    # Convert the indicator columns to ``Int64`` nullable dtype so
    # a column with missing values does not get coerced to
    # ``float64`` (a column with int + NaN gets converted to
    # float64 by pandas; ``Int64`` preserves the int-ness).
    for spec in specs:
        if spec.raw_column in narrow.columns:
            narrow[spec.raw_column] = (
                pd.to_numeric(narrow[spec.raw_column], errors="coerce")
                .astype("Int64")
            )
    rename_map: dict[str, str] = {
        s.raw_column: s.variable_name for s in specs
    }
    narrow = narrow.rename(columns=rename_map)

    # Build raw_lookup + coerce indicator cells. The narrow frame's
    # columns are now the catalog ``variable_name`` s.
    raw_lookup: dict[tuple[str, int, str], str] = {}
    for spec in specs:
        col = spec.variable_name
        if col not in narrow.columns:
            continue
        for idx, cell in narrow[col].items():
            country = str(narrow.at[idx, "country"] or "")
            try:
                raw_year = narrow.at[idx, "year"]
                year_value = int(raw_year) if raw_year is not None else 0
            except (TypeError, ValueError):
                year_value = 0
            raw_lookup[(country, year_value, col)] = _raw_cell_text(cell)
        narrow[col] = narrow[col].apply(_coerce_cirights_value).astype("Int64")

    narrow["year"] = pd.to_numeric(
        narrow["year"], errors="coerce",
    ).astype("Int64")

    years_present = (
        pd.Series(narrow["year"].dropna().astype(int).tolist())
        if not narrow.empty
        else pd.Series([], dtype=int)
    )
    if not years_present.empty:
        year_window_tuple: tuple[int, int] = (
            int(years_present.min()),
            int(years_present.max()),
        )
    else:
        year_window_tuple = (0, 0)
    narrow.attrs["_cirights_raw_lookup"] = raw_lookup
    narrow.attrs["year_window"] = year_window_tuple
    narrow = narrow.sort_values(
        by=["year", "country"],
        ascending=[True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return narrow
