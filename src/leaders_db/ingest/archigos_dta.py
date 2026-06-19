"""Stage 2 -- Archigos v4.1: Stata .dta read + identity-column coercion.

This module is the reader half of the Archigos adapter. It owns:

- :func:`read_dta_to_long_dataframe` -- the low-level reader. Opens
  the .dta with ``pyreadstat.read_dta(encoding='cp1252')``, narrows
  to the 6 catalog ``raw_column`` s, and reshapes to long format.
- :func:`_extract_start_year` -- pull the start year (int) from a
  Stata ``%td`` (datetime.date) object.
- :func:`_coerce_text_value` -- per-cell text coercion: ``.``
  (Stata missing) -> ``""`` (the audit-trail empty-string
  convention), everything else preserved verbatim.
- :func:`_coerce_date_to_decimal_year` -- light numeric coercion
  for ``startdate`` / ``enddate``: ``datetime.date`` -> decimal
  year (e.g. 1869-03-04 -> 1869.169).
- :func:`_coerce_entry_code` -- ordinal mapping for the
  ``entry`` column (the categorical entry-type field).
- :func:`_coerce_exit_code` -- ordinal mapping for the
  ``exit`` column.
- :func:`_coerce_gender` -- ``M`` -> 1, ``F`` -> 2 (the same
  convention used by the V-Dem / CIRIGHTS adapters).

The Stata read path is split from the I/O module to keep the
file count manageable and to follow the V-Dem / CIRIGHTS /
SIPRI Yearbook Ch.7 pattern of one file per concern.

The Stata ``%td`` format: pyreadstat reads Stata ``%td`` columns
as Python ``datetime.date`` objects (verified live 2026-06-19
against ``data/raw/archigos/Archigos_4.1_stata14.dta``). The
``%td`` Stata format stores dates as "days since 1960-01-01";
pyreadstat's Python-side conversion handles the offset.

Archigos v4.1 cell values (verified live 2026-06-19):

- ``leader`` -- ASCII text (some non-ASCII letters in diacritics
  are cp1252-encoded; pyreadstat's ``encoding='cp1252'`` reads
  them as Python ``str``).
- ``startdate``, ``enddate`` -- Python ``datetime.date`` (Stata
  ``%td``).
- ``entry`` -- one of: ``"Regular"``, ``"Irregular"``,
  ``"Foreign Imposition"``, ``"Unknown"``.
- ``exit`` -- one of: ``"Regular"``, ``"Irregular"``,
  ``"Natural Death"``, ``"Still in Office"``,
  ``"Retired Due to Ill Health"``, ``"Foreign"``, ``"Suicide"``,
  ``"Unknown"``.
- ``gender`` -- ``"M"`` or ``"F"``.

The reader is defensive: any unexpected value in a categorical
column is preserved as a text ``raw_value`` with a ``None``
``normalized_value`` (per the rule "do not invent missing
values"). A debug log is emitted for each unexpected value.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pyreadstat

from .archigos_io import ARCHIGOS_DTA_ENCODING, IndicatorSpec

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

#: In-code mirror of the catalog's ``raw_column`` -> ordinal-code map
#: for the ``entry`` column. The catalog CSV is the public source of
#: truth; this dict is the in-code mirror for fast lookup when the
#: reader needs to coerce an ``entry`` value. The mapping MUST match
#: the catalog (the drift-guard test catches any divergence).
_ENTRY_CODE_MAP: dict[str, int] = {
    "Regular": 1,
    "Irregular": 2,
    "Foreign Imposition": 3,
    "Unknown": 4,
}

#: In-code mirror of the catalog's ``raw_column`` -> ordinal-code map
#: for the ``exit`` column.
_EXIT_CODE_MAP: dict[str, int] = {
    "Regular": 1,
    "Irregular": 2,
    "Natural Death": 3,
    "Still in Office": 4,
    "Retired Due to Ill Health": 5,
    "Foreign": 6,
    "Suicide": 7,
    "Unknown": 8,
}

#: In-code mirror of the catalog's ``raw_column`` -> ordinal-code map
#: for the ``gender`` column.
_GENDER_CODE_MAP: dict[str, int] = {
    "M": 1,
    "F": 2,
}

__all__ = [
    "read_dta_to_long_dataframe",
]


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_text_value(cell: object) -> str:
    """Coerce a single Stata cell to a Python string for ``raw_value``.

    The Stata ``.`` (missing) sentinel becomes the empty string
    (per the audit-trail convention in
    :mod:`leaders_db.ingest.cirights_xlsx`); all other values
    are preserved verbatim. ``None`` and ``float('nan')`` are
    also treated as missing.
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
    if text in {"", ".", "nan", "NaN", "None"}:
        return ""
    return text


def _extract_year(date_value: object) -> int | None:
    """Extract the year (int) from a Stata ``%td`` value.

    ``pyreadstat`` reads Stata ``%td`` columns as Python
    ``datetime.date`` (or pandas Timestamp for some column
    shapes). Returns ``None`` for missing values.
    """
    if date_value is None:
        return None
    if isinstance(date_value, date) and not isinstance(date_value, datetime):
        return int(date_value.year)
    if isinstance(date_value, datetime):
        return int(date_value.year)
    if isinstance(date_value, pd.Timestamp):
        try:
            if pd.isna(date_value):
                return None
        except (TypeError, ValueError):
            pass
        return int(date_value.year)
    text = str(date_value).strip()
    if not text or text == ".":
        return None
    try:
        # Accept either ``"YYYY-MM-DD"`` or ``"YYYY/MM/DD"`` (the
        # latter is rare but observed in some Archigos rows when
        # ``enddate`` is missing or partial).
        return int(text[:4])
    except (ValueError, TypeError):
        return None


def _coerce_date_to_decimal_year(date_value: object) -> float | None:
    """Convert a Stata ``%td`` value to a decimal year.

    Example: ``1869-03-04`` -> ``1869 + (31 + 28 + 3 - 1) / 365``
    = ``1869.169``. Returns ``None`` for missing values.
    """
    if date_value is None:
        return None
    dt: date | None = None
    if isinstance(date_value, datetime):
        dt = date_value.date()
    elif isinstance(date_value, date):
        dt = date_value
    elif isinstance(date_value, pd.Timestamp):
        try:
            if pd.isna(date_value):
                return None
        except (TypeError, ValueError):
            pass
        dt = date_value.date()
    if dt is None:
        text = str(date_value).strip()
        if not text or text == ".":
            return None
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            try:
                dt = datetime.strptime(text[:10], "%Y/%m/%d").date()
            except ValueError:
                return None
    year = dt.year
    # Day-of-year: 1-365 (or 366 in leap years). For the decimal
    # year convention, the day-of-year / 365 gives a value in
    # [0.0, ~1.0]. Use the actual day-of-year (1-based) so
    # Jan 1 = 0.0 (midnight at the start of the year) and Dec 31
    # = ~0.997.
    day_of_year = dt.timetuple().tm_yday
    return float(year) + (float(day_of_year) - 1.0) / 365.0


def _coerce_entry_code(value: str) -> int | None:
    """Map an ``entry`` cell value to its ordinal code.

    Returns ``None`` for missing values (``""`` after
    :func:`_coerce_text_value`) and for unexpected values
    (preserved as text in ``raw_value`` but missing from the
    map).
    """
    if not value:
        return None
    code = _ENTRY_CODE_MAP.get(value)
    if code is None:
        _logger.debug(
            "archigos: unexpected entry value %r (raw_value preserved)",
            value,
        )
    return code


def _coerce_exit_code(value: str) -> int | None:
    """Map an ``exit`` cell value to its ordinal code.

    Same rules as :func:`_coerce_entry_code`.
    """
    if not value:
        return None
    code = _EXIT_CODE_MAP.get(value)
    if code is None:
        _logger.debug(
            "archigos: unexpected exit value %r (raw_value preserved)",
            value,
        )
    return code


def _coerce_gender(value: str) -> int | None:
    """Map a ``gender`` cell value to its ordinal code (1=M, 2=F).

    Returns ``None`` for missing values and unexpected values
    (preserved as text in ``raw_value`` but missing from the
    map).
    """
    if not value:
        return None
    code = _GENDER_CODE_MAP.get(value)
    if code is None:
        _logger.debug(
            "archigos: unexpected gender value %r (raw_value preserved)",
            value,
        )
    return code


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_dta_to_long_dataframe(
    *,
    dta_path: Path,
    year: int | None,
    specs: list[IndicatorSpec],
) -> pd.DataFrame:
    """Read the Archigos .dta into a narrow long-format frame.

    The output frame has the columns documented in
    :func:`leaders_db.ingest.archigos_io.read_archigos`. The
    function:

    1. Opens the .dta with ``pyreadstat.read_dta(encoding='cp1252')``.
    2. Filters to the 6 catalog ``raw_column`` s + the 3 audit
       columns (``obsid``, ``idacr``, ``ccode``).
    3. Extracts the start year and end year from the Stata
       ``%td`` columns.
    4. Optionally filters to a single start year.
    5. Pivots wide -> long: for each row, emits one
       ``source_observations``-shaped row per catalog variable.
    6. Coerces ``normalized_value`` per the variable's column
       (text -> text, date -> decimal year, categorical -> ordinal
       code, gender -> 1/2).

    Args:
        dta_path: absolute path to the .dta file.
        year: filter to a single start-year. Default: all years.
        specs: the loaded catalog (one :class:`IndicatorSpec` per
            identity column).

    Returns:
        A pandas DataFrame in long format. Empty if no spells
        match the year filter.
    """
    if not dta_path.is_file():
        raise FileNotFoundError(f"Archigos .dta not found: {dta_path}")

    # Build the in-code raw_column -> spec map for fast lookup.
    spec_by_raw_column = {s.raw_column: s for s in specs}

    # 1. Open the .dta.
    df_wide, _meta = pyreadstat.read_dta(
        str(dta_path), encoding=ARCHIGOS_DTA_ENCODING,
    )
    if df_wide.empty:
        return _empty_long_dataframe()

    # 2. Filter to the audit columns + the 6 catalog raw_columns.
    audit_cols = ["obsid", "idacr", "ccode"]
    catalog_raw_cols = [s.raw_column for s in specs]
    needed = list(dict.fromkeys(audit_cols + catalog_raw_cols))
    missing_cols = [c for c in needed if c not in df_wide.columns]
    if missing_cols:
        raise ValueError(
            f"Archigos .dta is missing expected columns: {missing_cols}"
        )
    df_wide = df_wide[needed].copy()

    # 3. Extract start year + end year from the Stata %td columns.
    has_enddate = "enddate" in spec_by_raw_column
    df_wide["year"] = df_wide["startdate"].apply(_extract_year)
    if has_enddate:
        df_wide["end_year"] = df_wide["enddate"].apply(_extract_year)
    else:
        df_wide["end_year"] = None  # type: ignore[assignment]

    # 4. Optional year filter.
    if year is not None:
        df_wide = df_wide[df_wide["year"] == int(year)].copy()
        if df_wide.empty:
            return _empty_long_dataframe()

    # 5. Pivot wide -> long. For each (spell, raw_column) we emit
    # one long row. We do this by iterating the specs in catalog
    # order (so the long frame is stable across runs).
    long_rows: list[dict[str, object]] = []
    for _, spell_row in df_wide.iterrows():
        obsid = _coerce_text_value(spell_row.get("obsid"))
        idacr = _coerce_text_value(spell_row.get("idacr"))
        ccode = spell_row.get("ccode")
        spell_year = spell_row.get("year")
        spell_end_year = spell_row.get("end_year")

        # The source_row_reference is built once per spell and
        # suffixed with the raw_column name (the audit trail
        # locates the raw row + the variable).
        if obsid:
            base_ref = f"archigos:{obsid}:{int(spell_year) if spell_year is not None else 0}"
        else:
            base_ref = f"archigos:{idacr}:{int(spell_year) if spell_year is not None else 0}"

        for spec in specs:
            cell = spell_row.get(spec.raw_column)
            raw_value = _coerce_text_value(cell)
            # If the cell is missing, skip the long row entirely
            # (per the rule "do not invent missing values"). The
            # raw_value audit column would be empty; the row
            # contributes nothing to source_observations.
            if spec.raw_column not in {"startdate", "enddate"} and not raw_value:
                continue
            normalized = _coerce_normalized_for_spec(
                spec, cell, raw_value,
            )
            long_rows.append(
                {
                    "obsid": obsid,
                    "idacr": idacr,
                    "ccode": ccode,
                    "year": int(spell_year) if spell_year is not None else None,
                    "end_year": (
                        int(spell_end_year) if spell_end_year is not None else None
                    ),
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


def _coerce_normalized_for_spec(
    spec: IndicatorSpec,
    cell: object,
    raw_value: str,
) -> float | None:
    """Light-coerce a cell value to ``normalized_value`` per the spec.

    The rules:

    - ``leader`` (text field) -> ``None`` (no numeric coercion).
    - ``startdate`` / ``enddate`` (date) -> decimal year via
      :func:`_coerce_date_to_decimal_year`.
    - ``entry`` / ``exit`` (categorical) -> ordinal code via
      :func:`_coerce_entry_code` / :func:`_coerce_exit_code`.
    - ``gender`` (categorical) -> 1 (M) or 2 (F) via
      :func:`_coerce_gender`.
    - Anything else -> ``None`` (no coercion).

    Returns ``None`` for missing values.
    """
    if spec.raw_column in {"startdate", "enddate"}:
        return _coerce_date_to_decimal_year(cell)
    if spec.raw_column == "entry":
        return _coerce_entry_code(raw_value)
    if spec.raw_column == "exit":
        return _coerce_exit_code(raw_value)
    if spec.raw_column == "gender":
        return _coerce_gender(raw_value)
    return None


def _empty_long_dataframe() -> pd.DataFrame:
    """Return an empty long-format frame with the canonical schema.

    Used when the year filter matches no spells.
    """
    return pd.DataFrame(
        columns=[
            "obsid",
            "idacr",
            "ccode",
            "year",
            "end_year",
            "variable_name",
            "raw_value",
            "normalized_value",
            "source_row_reference",
        ],
    )
