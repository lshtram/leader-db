"""Stage 2 -- REIGN (Bell 2016): CSV read + identity-column coercion.

This module is the reader half of the REIGN adapter. It owns:

- :func:`read_reign_csv_to_long_dataframe` -- the low-level
  reader. Opens the REIGN CSV with pandas (``read_csv``), narrows
  to the 8 catalog ``raw_column`` s + the 4 audit columns
  (``ccode``, ``country``, ``year``, ``month``), and reshapes
  to long format.
- :func:`_coerce_text_value` -- per-cell text coercion: NaN
  -> ``""`` (the audit-trail empty-string convention),
  everything else preserved verbatim.
- :func:`_coerce_numeric_value` -- per-cell numeric coercion:
  NaN -> ``None``, otherwise float.
- :func:`_coerce_gender` -- REIGN ``male`` is 1 (male) or 0
  (female). Light-coerce to 1 (M) or 2 (F) for consistency
  with Archigos.

The CSV read path is split from the I/O module to keep the file
count manageable and to follow the V-Dem / CIRIGHTS / Archigos /
SIPRI Yearbook Ch.7 pattern of one file per concern.

REIGN 2021-8 cell values (verified live 2026-06-19):

- ``leader`` -- ASCII text (some non-ASCII letters in
  diacritics).
- ``government`` -- text regime-type label (e.g.
  ``"Presidential Democracy"``, ``"Military"``,
  ``"Parliamentary Democracy"``).
- ``elected`` -- float 0 or 1.
- ``age`` -- float (age in years).
- ``male`` -- float 0 or 1.
- ``tenure_months`` -- float (months in office).
- ``political_violence`` -- float (continuous; can be negative;
  from the OEF coup-risk model).
- ``irregular`` -- float (continuous; can be negative; from the
  OEF coup-risk model).

The reader is defensive: missing values (pandas NaN) become
``""`` in ``raw_value`` and ``None`` in ``normalized_value``;
the long row is skipped entirely (per the rule "do not invent
missing values"). Numeric NaNs are dropped at the long-frame
level so the ``source_observations`` row count reflects only
non-missing observations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .reign_io import IndicatorSpec, safe_country_token

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

__all__ = [
    "read_reign_csv_to_long_dataframe",
]


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_text_value(cell: object) -> str:
    """Coerce a single CSV cell to a Python string for ``raw_value``.

    The pandas NaN sentinel becomes the empty string (per the
    audit-trail convention in
    :mod:`leaders_db.ingest.cirights_xlsx`); all other values
    are preserved verbatim.
    """
    if cell is None:
        return ""
    if isinstance(cell, float):
        try:
            if pd.isna(cell):
                return ""
        except (TypeError, ValueError):
            pass
    text = str(cell).strip()
    if text in {"", "nan", "NaN", "None"}:
        return ""
    return text


def _coerce_numeric_value(cell: object) -> float | None:
    """Light-coerce a CSV cell to a Python float for ``normalized_value``.

    Returns ``None`` for missing values (pandas NaN).
    """
    if cell is None:
        return None
    if isinstance(cell, float):
        try:
            if pd.isna(cell):
                return None
        except (TypeError, ValueError):
            pass
        return float(cell)
    try:
        return float(cell)
    except (TypeError, ValueError):
        return None


def _coerce_gender(cell: object) -> int | None:
    """Map REIGN's ``male`` (1/0) to the standard 1/2 code.

    REIGN's ``male`` is 1 (male) or 0 (female). For consistency
    with Archigos (which uses 1=M, 2=F), the Stage 2 reader
    inverts: 1 -> 1, 0 -> 2. ``raw_value`` preserves the
    original 0/1.

    Returns ``None`` for missing values.
    """
    val = _coerce_numeric_value(cell)
    if val is None:
        return None
    if val == 1.0:
        return 1
    if val == 0.0:
        return 2
    _logger.debug(
        "reign: unexpected male value %r (raw_value preserved)",
        val,
    )
    return None


def _coerce_normalized_for_spec(
    spec: IndicatorSpec,
    cell: object,
    raw_value: str,
) -> float | int | None:
    """Light-coerce a cell value to ``normalized_value`` per the spec.

    The rules:

    - ``leader`` / ``government`` (text fields) -> ``None`` (no
      numeric coercion).
    - ``elected`` / ``age`` / ``tenure_months`` (numeric) ->
      float via :func:`_coerce_numeric_value`.
    - ``male`` (1/0) -> 1 or 2 via :func:`_coerce_gender`.
    - ``political_violence`` / ``irregular`` (numeric) -> float
      via :func:`_coerce_numeric_value`.
    - Anything else -> ``None`` (no coercion).

    Returns ``None`` for missing values.
    """
    if spec.raw_column in {"leader", "government"}:
        return None
    if spec.raw_column == "male":
        return _coerce_gender(cell)
    return _coerce_numeric_value(cell)


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_reign_csv_to_long_dataframe(
    *,
    csv_path: Path,
    year: int | None,
    specs: list[IndicatorSpec],
) -> pd.DataFrame:
    """Read the REIGN CSV into a narrow long-format frame.

    The output frame has the columns documented in
    :func:`leaders_db.ingest.reign_io.read_reign`. The function:

    1. Opens the CSV with ``pandas.read_csv`` (UTF-8, comma-
       delimited, no special parameters).
    2. Filters to the 4 audit columns (``ccode``, ``country``,
       ``year``, ``month``) + the 8 catalog ``raw_column`` s.
    3. Optionally filters to a single year.
    4. Pivots wide -> long: for each leader-month row, emits one
       ``source_observations``-shaped row per catalog variable.
    5. Coerces ``normalized_value`` per the variable's column
       (text -> None, numeric -> float, gender -> 1/2).
    6. Builds ``source_row_reference`` of the form
       ``reign:<country_token>:<leader_token>:<year>:<month>:<raw_column>``.

    Args:
        csv_path: absolute path to the CSV file.
        year: filter to a single year. Default: all years.
        specs: the loaded catalog (one :class:`IndicatorSpec` per
            identity column).

    Returns:
        A pandas DataFrame in long format. Empty if no rows
        match the year filter.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"REIGN CSV not found: {csv_path}")

    # 1. Open the CSV.
    df_wide = pd.read_csv(csv_path)
    if df_wide.empty:
        return _empty_long_dataframe()

    # 2. Filter to the audit columns + the 8 catalog raw_columns.
    audit_cols = ["ccode", "country", "year", "month"]
    catalog_raw_cols = [s.raw_column for s in specs]
    needed = list(dict.fromkeys(audit_cols + catalog_raw_cols))
    missing_cols = [c for c in needed if c not in df_wide.columns]
    if missing_cols:
        raise ValueError(
            f"REIGN CSV is missing expected columns: {missing_cols}"
        )
    df_wide = df_wide[needed].copy()

    # Coerce year and month to int (REIGN's year + month are
    # float in the raw CSV; the row index and year filter
    # need int).
    df_wide["year"] = df_wide["year"].astype("Int64")
    df_wide["month"] = df_wide["month"].astype("Int64")

    # 3. Optional year filter.
    if year is not None:
        df_wide = df_wide[df_wide["year"] == int(year)].copy()
        if df_wide.empty:
            return _empty_long_dataframe()

    # 4. Pivot wide -> long. For each (leader-month row,
    # raw_column) we emit one long row. We do this by iterating
    # the specs in catalog order (so the long frame is stable
    # across runs).
    long_rows: list[dict[str, object]] = []
    for _, raw_row in df_wide.iterrows():
        country = _coerce_text_value(raw_row.get("country"))
        ccode = raw_row.get("ccode")
        row_year = raw_row.get("year")
        row_month = raw_row.get("month")
        leader = _coerce_text_value(raw_row.get("leader"))

        # The source_row_reference is built once per
        # leader-month row and suffixed with the raw_column
        # name. The leader_token is the URL-safe-substituted
        # leader name; the country_token is the URL-safe-
        # substituted country name.
        country_token = safe_country_token(country)
        leader_token = safe_country_token(leader)
        if row_year is not None and not pd.isna(row_year):
            try:
                year_int = int(row_year)
            except (TypeError, ValueError):
                year_int = 0
        else:
            year_int = 0
        if row_month is not None and not pd.isna(row_month):
            try:
                month_int = int(row_month)
            except (TypeError, ValueError):
                month_int = 0
        else:
            month_int = 0
        base_ref = (
            f"reign:{country_token}:{leader_token}:"
            f"{year_int}:{month_int}"
        )

        for spec in specs:
            cell = raw_row.get(spec.raw_column)
            raw_value = _coerce_text_value(cell)
            # If the cell is missing, skip the long row entirely
            # (per the rule "do not invent missing values"). The
            # raw_value audit column would be empty; the row
            # contributes nothing to source_observations.
            if not raw_value:
                continue
            normalized = _coerce_normalized_for_spec(
                spec, cell, raw_value,
            )
            long_rows.append(
                {
                    "country": country,
                    "ccode": ccode,
                    "year": year_int,
                    "month": month_int,
                    "leader": leader,
                    "variable_name": spec.variable_name,
                    "raw_value": raw_value,
                    "normalized_value": normalized,
                    "source_row_reference": (
                        f"{base_ref}:{spec.raw_column}"
                    ),
                },
            )

    if not long_rows:
        return _empty_long_dataframe()
    return pd.DataFrame(long_rows)


def _empty_long_dataframe() -> pd.DataFrame:
    """Return an empty long-format frame with the canonical schema.

    Used when the year filter matches no rows.
    """
    return pd.DataFrame(
        columns=[
            "country",
            "ccode",
            "year",
            "month",
            "leader",
            "variable_name",
            "raw_value",
            "normalized_value",
            "source_row_reference",
        ],
    )
