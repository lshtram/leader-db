"""Stage 2 -- PWT long-format transform.

This module is the wide-to-long reshape half of the PWT adapter. It
owns:

- :func:`transform_pwt_long_frame` -- the long-format pivot.
  Takes the wide DataFrame returned by :func:`read_pwt` and pivots
  it to the canonical long-format shape (one row per
  ``(iso3, year, variable_name)`` triple) with the canonical audit-
  trail columns:

    - ``iso3`` -- ISO3 country code (from ``countrycode``)
    - ``year`` -- integer year
    - ``variable_name`` -- the catalog ``variable_name`` for the
      raw column (looked up from the per-source indicator catalog)
    - ``raw_value`` -- the verbatim cell value (preserved for audit)
    - ``numeric_value`` -- the coerced ``float`` value
      (drops to ``None`` when the cell is invalid)
    - ``raw_column`` -- the catalog ``raw_column`` (e.g. ``rgdpe``)
    - ``source_row_reference`` -- the canonical locator
      ``pwt:Data:<iso3>:<year>:<raw_column>``
    - ``temporal_kind`` -- always ``"observed"`` for PWT (the source
      emits direct observed source-year rows only -- per
      ``docs/source-ingestion-plan.md`` PWT section, no proxy /
      stale-fill / derivation is permitted)
    - ``attribution`` -- the canonical PWT citation text
      (Always-On Rule #15)

Year semantics
--------------

PWT 10.01 covers 1950-2019. The transform does NOT invent data: a
request for ``year=2023`` is filtered upstream (the reader returns
no rows for 2023 because the workbook has no 2023 data), and the
adapter surfaces a ``requested_year_out_of_coverage`` manifest
warning. There is no 2019 -> 2023 stale-proxy path; this is a
deliberate architectural decision per ``docs/source-ingestion-plan.md``
and ``docs/req/top-level-requirements.md`` §13 ("no invented
historical data; older years degrade gracefully").

Missing-cell emission rule
--------------------------

The transform DROPS a cell -- does NOT emit a long row -- when the
raw cell is:

  1. ``None`` (openpyxl empty cell)
  2. ``""`` (empty string)
  3. ``"  "`` (whitespace-only)
  4. ``"NA"`` / ``"N/A"`` / ``"NaN"`` / ``"nan"`` / ``"null"``
     (string sentinels -- the same set the other Stage 2 adapters
     use for defense-in-depth)
  5. Any non-numeric, non-empty string (e.g. ``"not-a-number"``)

The transform EMITS a long row when the raw cell is:

  1. A numeric ``int`` / ``float`` (e.g. ``1234.5``)
  2. A numeric-like string (e.g. ``"1234.5"`` -- coerces to
     ``float``)

The ``raw_value`` is preserved as the verbatim cell value; the
``numeric_value`` is the coerced ``float``. For ``int`` cells, the
``numeric_value`` is ``float(int)`` (e.g. ``42`` -> ``42.0``).

Catalog-driven emission
-----------------------

The transform emits one long row per catalog raw column whose cell
is non-missing. Raw columns in the wide frame that are NOT in the
PWT catalog (e.g. ``extra_not_in_catalog``) are dropped -- the
catalog is the source of truth for which raw indicators are
ingested, and the transform never invents rows for non-catalog
columns (Rule #8: no invented historical data).

Duplicate-rejection
-------------------

The transform rejects wide rows with duplicate ``(countrycode,
year)`` keys with a clear :class:`ValueError`. This guards against
source-data bugs (the live PWT xlsx has exactly one row per
``(countrycode, year)`` pair; a duplicate row in a future release
would be a data bug, not something to silently dedupe). The error
message names the duplicate key so a developer can act on it
without re-reading the source code.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

# Canonical long-format columns (per
# ``docs/source-ingestion-plan.md`` and the
# ``docs/req/requirements-core.md`` schema).
_LONG_COLUMNS: tuple[str, ...] = (
    "iso3",
    "year",
    "variable_name",
    "raw_value",
    "numeric_value",
    "raw_column",
    "source_row_reference",
    "temporal_kind",
    "attribution",
)

#: The canonical PWT attribution text. Mirrors ``PWT_ATTRIBUTION``
#: in ``__init__.py`` and the citation block in
#: ``docs/source-attributions.md`` (Always-On Rule #15). Defined
#: locally so the transform module can be imported without
#: triggering the package ``__init__`` cycle.
PWT_ATTRIBUTION: str = (
    "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)."
)

#: Sentinel strings that the transform drops entirely (no long
#: row emitted). Matches the union of string sentinels used by the
#: other Stage 2 adapters (defense in depth -- the live PWT xlsx
#: uses openpyxl NaN for missing cells, no string sentinels).
_PWT_MISSING_STRINGS: frozenset[str] = frozenset(
    {
        "NA",
        "N/A",
        "NaN",
        "nan",
        "null",
        "None",
        "-999",
        "-999.0",
        "",
    },
)

#: The 4 identity columns the wide frame always carries. Used to
#: build the per-row iso3 / year pair.
_PWT_IDENTITY_COLUMNS: tuple[str, ...] = (
    "countrycode",
    "country",
    "currency_unit",
    "year",
)

#: The canonical 11 catalog raw columns (mirror of
#: ``PWT_CATALOG_RAW_COLUMNS`` in the package ``__init__``). The
#: reader / catalog carry the same list; the transform iterates
#: this set when emitting long rows.
_PWT_CATALOG_RAW_COLUMNS: tuple[str, ...] = (
    "rgdpe",
    "rgdpo",
    "pop",
    "emp",
    "avh",
    "hc",
    "ccon",
    "cda",
    "ctfp",
    "rkna",
    "rtfpna",
)


def _default_catalog_path() -> Path:
    """Return the per-source ``catalog.csv`` path.

    Defined locally so the transform module can be imported without
    a cycle (the package ``__init__`` imports this module).
    """
    return Path(__file__).resolve().parent / "catalog.csv"


def _load_catalog_raw_columns(
    catalog_path: Path | None,
) -> set[str]:
    """Read the per-source ``catalog.csv`` and return the set of
    ``raw_column`` values it declares.

    Mirrors the Maddison / WGI / BTI / CIRIGHTS catalog loader:
    strips leading ``#`` comment lines, validates the
    ``variable_name`` and ``raw_column`` columns are present, and
    returns the deduplicated ``raw_column`` set.
    """
    path = catalog_path or _default_catalog_path()
    if not path.is_file():
        # Defensive: the catalog is committed alongside the
        # adapter. If it ever drifts (e.g. a move) we still want
        # the transform to run against the hard-coded canonical
        # list rather than crash -- the canonical list is the
        # catalog-of-last-resort.
        return set(_PWT_CATALOG_RAW_COLUMNS)
    cleaned: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned.append(raw_line)
    reader = csv.DictReader(cleaned)
    raw_columns: set[str] = set()
    for row in reader:
        if not row.get("variable_name"):
            continue
        raw = row.get("raw_column")
        if raw:
            raw_columns.add(raw.strip())
    return raw_columns or set(_PWT_CATALOG_RAW_COLUMNS)


def _load_catalog_variable_names(
    catalog_path: Path | None,
) -> dict[str, str]:
    """Return ``{raw_column: variable_name}`` from the catalog.

    The transform maps each ``raw_column`` (e.g. ``rgdpe``) to the
    canonical ``variable_name`` (e.g. ``pwt_real_gdp_expenditure_side``)
    the catalog declares. If the catalog is missing, the fallback
    returns ``{raw_column: raw_column}`` (identity mapping) so the
    transform still emits rows; downstream Stage 5 code resolves
    the canonical variable names.
    """
    path = catalog_path or _default_catalog_path()
    if not path.is_file():
        return {col: col for col in _PWT_CATALOG_RAW_COLUMNS}
    cleaned: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned.append(raw_line)
    reader = csv.DictReader(cleaned)
    mapping: dict[str, str] = {}
    for row in reader:
        if not row.get("variable_name"):
            continue
        raw = (row.get("raw_column") or "").strip()
        var = (row.get("variable_name") or "").strip()
        if raw and var:
            mapping[raw] = var
    return mapping or {
        col: col for col in _PWT_CATALOG_RAW_COLUMNS
    }


def _cell_is_missing(cell: Any) -> bool:
    """Return True iff ``cell`` is a missing-value sentinel.

    Rules:

    - ``None`` (openpyxl empty cell) -> missing.
    - pandas ``NaN`` / ``float('nan')`` -> missing.
    - ``str`` after ``.strip()``: empty / whitespace /
      ``"NA"`` / ``"N/A"`` / ``"NaN"`` / ``"nan"`` / ``"null"`` /
      ``"None"`` / ``"-999"`` / ``"-999.0"`` -> missing.
    - Anything else: not missing (the caller decides whether it's
      numeric / numeric-like).
    """
    if cell is None:
        return True
    if isinstance(cell, float):
        import math

        return math.isnan(cell)
    if isinstance(cell, str):
        return cell.strip() in _PWT_MISSING_STRINGS
    return False


def _coerce_to_float(cell: Any) -> float | None:
    """Return ``float(cell)`` if numeric / numeric-like, else None.

    Numeric (``int`` / ``float``) -> ``float(cell)`` (preserving the
    int -> float widening so the DB ``normalized_value`` column is
    consistently ``REAL``).

    Numeric-like string (e.g. ``"1234.5"``) -> ``float(stripped)``.

    Anything else -> ``None`` (the transform DROPS such cells).
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        # ``bool`` is a subclass of ``int`` -- but the PWT xlsx has
        # no boolean cells and treating True / False as 1 / 0 would
        # silently emit a bogus observation. Drop explicitly.
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    if isinstance(cell, str):
        try:
            return float(cell.strip())
        except ValueError:
            return None
    return None


def transform_pwt_long_frame(
    wide_df: Any,
    *,
    catalog_path: Path | None = None,
    year: int | None = None,
    years: tuple[int, ...] | None = None,
    country_filter: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Pivot the wide ``Data``-sheet DataFrame to the canonical
    long-format.

    The transform:

    1. Resolves the catalog ``raw_column`` set (loaded from
       ``catalog.csv`` if available, else the canonical 11-column
       fallback) and the per-raw-column ``variable_name`` mapping.
    2. Validates the wide frame has the 4 identity columns. Raises
       :class:`ValueError` listing the missing identity columns if
       not.
    3. Detects duplicate ``(countrycode, year)`` source rows and
       raises :class:`ValueError` naming the duplicate key
       (canonical source rows must be unique; a duplicate is a
       source-data bug, not something to silently dedupe).
    4. Iterates every wide row; for each catalog raw_column whose
       cell is NOT a missing-value sentinel, emits one long row
       with the canonical schema (9 columns). The
       ``source_row_reference`` is ``pwt:Data:<iso3>:<year>:<raw_column>``;
       ``temporal_kind`` is always ``"observed"``; ``attribution``
       is the canonical PWT citation.
    5. Applies the optional request-scoped filters
       (``year`` / ``years`` / ``country_filter``) so the
       long-format frame only carries rows that the request
       asked for. The orchestrator (``PWTAdapter``) passes
       ``years=request.effective_years`` and
       ``country_filter=request.country_filter`` so the
       registry path and the convenience path produce
       identical artifacts. The ``year`` argument is preserved
       as a single-year shortcut (defense-in-depth; equivalent
       to ``years=(year,)``).
    6. Sorts the long frame by
       ``(year ASC, iso3 ASC, raw_column ASC)`` so insertion order
       is fully deterministic.

    Args:
        wide_df: the wide-format DataFrame from
            :func:`leaders_db.ingest.sources.pwt.reader.read_pwt`.
            Must carry the 4 identity columns + the 11 catalog
            columns. Other columns are ignored.
        catalog_path: optional override for the catalog CSV path.
            Default: the per-source ``catalog.csv``.
        year: optional single-year filter. Default: emit rows for
            every year present in the wide frame. Equivalent to
            ``years=(year,)``. Kept for backward-compat with the
            Increment A stub signature.
        years: optional tuple of years to include. When set (and
            non-empty), only wide rows whose ``year`` is in this
            tuple survive the transform. ``country_filter`` and
            ``years`` may be combined; both filters are applied
            independently.
        country_filter: optional tuple of ISO3 codes to include.
            When set (and non-empty), only wide rows whose
            ``countrycode`` (== ``iso3``) is in this tuple
            survive the transform. An empty tuple is the same
            as ``None`` (no filter).

    Returns:
        A pandas DataFrame with the canonical 9-column long schema.
        Rows for missing / sentinel / non-numeric cells are DROPPED
        entirely -- the returned frame never contains an observation
        row for an invalid cell. The ``temporal_kind`` column is
        ``"observed"`` for every row.

    Raises:
        ValueError: if the wide frame is missing identity columns
            or contains duplicate ``(countrycode, year)`` source
            rows.
    """
    if not isinstance(wide_df, pd.DataFrame):
        raise ValueError(
            "transform_pwt_long_frame requires a pandas DataFrame; "
            f"got {type(wide_df).__name__}"
        )
    # Validate identity columns are present.
    present = set(wide_df.columns)
    missing_identity = [
        col for col in _PWT_IDENTITY_COLUMNS if col not in present
    ]
    if missing_identity:
        raise ValueError(
            f"transform_pwt_long_frame: wide DataFrame is missing "
            f"required identity column(s): {missing_identity}"
        )

    catalog_raw_columns = _load_catalog_raw_columns(catalog_path)
    variable_name_map = _load_catalog_variable_names(catalog_path)

    # Build the canonical row keys first to detect duplicates in a
    # single pass. ``countrycode`` may be a pandas ``string``
    # dtype (NaN-aware); ``year`` may be ``Int64`` (NaN-aware
    # int). Drop rows missing either key defensively.
    if wide_df.empty:
        long_records: list[dict[str, Any]] = []
    else:
        # Detect duplicate (countrycode, year) keys. The check
        # ignores rows with missing countrycode or year -- those
        # are dropped below anyway.
        key_columns = ["countrycode", "year"]
        # ``duplicated`` on the wide frame catches exact-duplicate
        # rows. We raise on the FIRST occurrence for an
        # actionable error message.
        dup_mask = wide_df.duplicated(
            subset=key_columns, keep=False,
        )
        if dup_mask.any():
            dup_rows = wide_df.loc[dup_mask, key_columns]
            first_key = dup_rows.iloc[0]
            raise ValueError(
                f"transform_pwt_long_frame: duplicate (countrycode, "
                f"year) wide row detected: countrycode="
                f"{first_key['countrycode']!r}, year="
                f"{int(first_key['year']) if pd.notna(first_key['year']) else 'NaN'}. "
                "Canonical PWT source rows must be unique; the "
                "duplicate is a source-data bug."
            )

        long_records = []
        for _, wide_row in wide_df.iterrows():
            countrycode_cell = wide_row.get("countrycode")
            year_cell = wide_row.get("year")
            if _cell_is_missing(countrycode_cell):
                continue
            if pd.isna(year_cell) if hasattr(pd, "isna") else (
                year_cell is None
            ):
                continue
            iso3 = str(countrycode_cell).strip()
            if not iso3:
                continue
            try:
                year_value = int(year_cell)
            except (TypeError, ValueError):
                continue

            # Request-scoped year + country filters. The
            # ``year`` keyword is a single-year shortcut for
            # backward-compat with the Increment A stub
            # signature; the orchestrator passes
            # ``years=request.effective_years`` so the registry
            # runner's tuple-of-years contract is honored
            # end-to-end. ``country_filter`` scopes the wide
            # frame to a tuple of ISO3 codes so a request like
            # ``country_filter=('USA',)`` never emits rows for
            # MEX / SWE / others. The empty-tuple form is
            # equivalent to ``None`` (no filter).
            if year is not None and year_value != int(year):
                continue
            if years is not None and len(years) > 0:
                if year_value not in {int(y) for y in years}:
                    continue
            if country_filter is not None and len(country_filter) > 0:
                if iso3 not in {str(c) for c in country_filter}:
                    continue

            for raw_column in _PWT_CATALOG_RAW_COLUMNS:
                if catalog_raw_columns and (
                    raw_column not in catalog_raw_columns
                ):
                    # The catalog deliberately excluded this raw
                    # column (e.g. a future downgrade). Skip.
                    continue
                if raw_column not in wide_df.columns:
                    # The wide frame did not carry this column
                    # (e.g. a malformed workbook). Skip -- the
                    # reader is responsible for raising on
                    # missing required columns; the transform is
                    # defensive here.
                    continue
                cell_value = wide_row.get(raw_column)
                if _cell_is_missing(cell_value):
                    # Drop missing / sentinel cells entirely.
                    continue
                numeric_value = _coerce_to_float(cell_value)
                if numeric_value is None:
                    # Non-numeric, non-empty string -- drop per
                    # the canonical missing-cell rule.
                    continue
                raw_value_preserved: Any = cell_value
                long_records.append(
                    {
                        "iso3": iso3,
                        "year": int(year_value),
                        "variable_name": variable_name_map.get(
                            raw_column, raw_column,
                        ),
                        "raw_value": raw_value_preserved,
                        "numeric_value": numeric_value,
                        "raw_column": raw_column,
                        "source_row_reference": (
                            f"pwt:Data:{iso3}:{int(year_value)}:"
                            f"{raw_column}"
                        ),
                        "temporal_kind": "observed",
                        "attribution": PWT_ATTRIBUTION,
                    },
                )

    if not long_records:
        return pd.DataFrame(columns=list(_LONG_COLUMNS))

    long_df = pd.DataFrame.from_records(long_records)
    # Sort for deterministic insertion order. The DB write layer
    # relies on this for the per-source ``source_observations``
    # insertion order; the registry runner relies on it for the
    # canonical IngestResult.years / .observation_rows summary.
    long_df = long_df.sort_values(
        by=["year", "iso3", "raw_column"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    # Reorder columns to the canonical long schema.
    return long_df.loc[:, list(_LONG_COLUMNS)]


__all__ = ["transform_pwt_long_frame"]
