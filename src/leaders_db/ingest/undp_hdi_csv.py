"""Stage 2 -- UNDP HDI CSV read: latin-1 + schema validation + defensive checks.

This module is the CSV-read half of the UNDP HDI adapter. It owns:

- :func:`_parse_col_year` -- parse a single ``{prefix}_{year}``
  column name. Returns ``(prefix, year)`` on success, ``None``
  when the column does not match the pattern.
- :func:`_validate_wide_schema` -- check the wide frame for the
  required static columns + the expected ``{prefix}_{year}``
  columns for the in-scope prefixes and year window.
- :func:`_check_region_codes` / :func:`_check_hdicode_values` --
  §6 defensive checks (warn but preserve).
- :func:`read_undp_hdi_csv` -- read the latin-1 CSV, validate
  the schema, and return the wide-format DataFrame with the
  static columns + the in-scope ``{prefix}_{year}`` columns.

The wide-to-long UNPIVOT (:func:`build_undp_hdi_observations`)
lives in :mod:`leaders_db.ingest.undp_hdi_unpivot` (split out to
keep this module under the 400-line convention cap; per the
architecture §5 split-trigger rule for modules that grow past
the cap, the helper was extracted).

The catalog loader, path helpers, and parquet write function live
in :mod:`leaders_db.ingest.undp_hdi_io`. The DB writes (sources
upsert, source_observations write, run manifest) live in
:mod:`leaders_db.ingest.undp_hdi_db` (with pure helpers in
:mod:`leaders_db.ingest.undp_hdi_db_helpers`). The orchestrator
that ties everything together lives in
:mod:`leaders_db.ingest.undp_hdi`.

UNDP HDI CSV layout (per ``docs/architecture/undp-hdi.md`` §2):

- 206 countries x 1,076 columns, wide format, one row per
  country (10 aggregate regions with ``ZZ*`` iso3 prefixes are
  present but not counted as countries).
- 4 static columns first: ``iso3``, ``country``, ``hdicode``,
  ``region``.
- 1,072 ``{prefix}_{year}`` columns (44 prefixes x 33 years, plus
  year-2022-only rank/metadata columns).
- Encoding: ``latin-1`` (UTF-8 fails on country names with
  diacritics such as ``Côte d'Ivoire``).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .undp_hdi_io import (
    UNDP_HDI_ENCODING,
    UNDP_HDI_HDI_CODES,
    UNDP_HDI_REGION_CODES,
    UNDP_HDI_STATIC_COLUMNS,
    load_undp_hdi_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "read_undp_hdi_csv",
]


# Pattern: ``{prefix}_{year}`` where ``prefix`` is non-empty
# lower-case letters and ``year`` is exactly 4 digits. We use a
# regex (not a naive rsplit) so the year portion is anchored to
# the final ``_<4-digits>`` suffix. Matches the real HDR 2023-24
# column naming convention.
_COL_YEAR_RE = re.compile(r"^(?P<prefix>[a-z][a-z0-9]*)_(?P<year>\d{4})$")


# ---------------------------------------------------------------------------
# Column parsing
# ---------------------------------------------------------------------------


def _parse_col_year(col_name: str) -> tuple[str, int] | None:
    """Parse a ``{prefix}_{year}`` column name.

    Returns ``(prefix, year)`` on success, ``None`` when the
    column does not match the pattern (e.g. static columns,
    year-2022-only rank/metadata columns, non-social-wellbeing
    prefixes).
    """
    match = _COL_YEAR_RE.match(col_name)
    if not match:
        return None
    return match.group("prefix"), int(match.group("year"))


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate_wide_schema(
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
    year: int | None = None,
) -> None:
    """Validate the wide frame's static + ``{prefix}_{year}`` columns.

    Raises :class:`ValueError` with an actionable message when a
    required static column is missing, or when the CSV does not
    deliver an expected ``{prefix}_{year}`` column for an in-scope
    catalog prefix (per architecture §6: "Missing expected
    {prefix}_{year} columns for an in-scope prefix/year: hard
    failure").

    The validation is scoped to the years actually present in the
    CSV: for each year Y observed in the column names, the
    function checks that ALL in-scope prefixes have a
    ``{prefix}_Y`` column. A year-filtered run (``year=2022``) is
    validated against the specific year; the no-year run is
    validated against every year present in the CSV.

    Args:
        df: the wide-format DataFrame returned by ``pd.read_csv``.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        year: if set, validate the columns for this year only. If
            ``None``, validate against every year present in the
            CSV's ``{prefix}_{year}`` columns.
    """
    missing_static = [
        col for col in UNDP_HDI_STATIC_COLUMNS if col not in df.columns
    ]
    if missing_static:
        raise ValueError(
            "UNDP HDI CSV is missing required static column(s): "
            f"{missing_static}. Required: {list(UNDP_HDI_STATIC_COLUMNS)}."
        )

    specs = load_undp_hdi_catalog(catalog_path=catalog_path)
    prefixes = tuple({spec.raw_column for spec in specs})

    # Find the years to validate: the requested year, or every
    # year observed in the column names. For each year, check
    # that all in-scope prefixes have a column. This is the
    # per-year contract from architecture §6.
    if year is not None:
        years_present = [int(year)]
    else:
        years_present_set: set[int] = set()
        for col in df.columns:
            parsed = _parse_col_year(col)
            if parsed is None:
                continue
            years_present_set.add(parsed[1])
        years_present = sorted(years_present_set)

    missing: list[str] = []
    for one_year in years_present:
        for prefix in prefixes:
            col = f"{prefix}_{one_year}"
            if col not in df.columns:
                missing.append(col)
    if missing:
        sample = sorted(missing)[:5]
        raise ValueError(
            "UNDP HDI CSV is missing expected '{prefix}_{year}' "
            f"column(s): {sample} ({len(missing)} total). The catalog "
            "promises these columns; their absence breaks the "
            "Stage 2 contract."
        )


# ---------------------------------------------------------------------------
# Defensive region / hdicode checks
# ---------------------------------------------------------------------------


def _check_region_codes(df: pd.DataFrame) -> None:
    """Log a warning for rows with an unknown or blank ``region`` value.

    Per architecture §6: "Unknown region: warn and preserve the
    row." The 55 ``region=NaN`` rows in the live bundle (e.g.
    USA) are preserved and the empty value is reported as a soft
    warning, not an error. Unknown non-empty region codes (e.g.
    ``"X7"``) are also preserved with a warning.

    The CSV reader uses ``keep_default_na=False`` + ``dtype=str`` so
    blank cells survive as empty strings (``""``) rather than NaN.
    We treat NaN and empty / whitespace-only strings as the same
    "blank region" case and emit one combined warning with the
    blank-row count. Non-blank but unrecognized codes get the
    per-code warning. The wide frame is preserved verbatim in both
    cases (the row is not dropped).
    """
    # Normalize to a stripped string series so empty/whitespace-only
    # cells and NaN (in case the reader config ever changes) collapse
    # to one ``blank`` bucket. ``astype(str)`` on a NaN yields the
    # literal string ``"nan"``; we count both that and ``""`` as
    # blank.
    series_str = df["region"].astype(str).str.strip()
    blank_mask = series_str.isin({"", "nan"})
    blank_count = int(blank_mask.sum())

    unknown_regions: dict[str, int] = {}
    for region in series_str[~blank_mask].unique():
        if region not in UNDP_HDI_REGION_CODES:
            unknown_regions[region] = int((series_str == region).sum())

    if blank_count:
        _logger.warning(
            "UNDP HDI blank/empty region value: count=%d. "
            "Preserving but flagging.",
            blank_count,
        )
    for region_str, count in sorted(unknown_regions.items()):
        _logger.warning(
            "UNDP HDI unknown region code: region=%s count=%d. "
            "Preserving but flagging.",
            region_str, count,
        )


def _check_hdicode_values(df: pd.DataFrame) -> None:
    """Log a warning for rows with an unknown ``hdicode`` value.

    Per architecture §6: "Unknown hdicode: warn and preserve the
    row." Empty ``hdicode`` cells are preserved silently.
    """
    unknown_codes: dict[str, int] = {}
    for code in df["hdicode"].dropna().unique():
        code_str = str(code).strip()
        if code_str and code_str not in UNDP_HDI_HDI_CODES:
            unknown_codes[code_str] = int(
                (df["hdicode"].astype(str) == code_str).sum(),
            )
    for code_str, count in sorted(unknown_codes.items()):
        _logger.warning(
            "UNDP HDI unknown hdicode value: hdicode=%s count=%d. "
            "Preserving but flagging.",
            code_str, count,
        )


# ---------------------------------------------------------------------------
# CSV read
# ---------------------------------------------------------------------------


def read_undp_hdi_csv(
    csv_path: Path,
    *,
    catalog_path: Path | None = None,
    year: int | None = None,
) -> pd.DataFrame:
    """Read the wide-format UNDP HDI CSV into a pandas DataFrame.

    Reads with ``encoding="latin-1"`` (UTF-8 fails on diacritics).
    Validates the schema (4 static columns + the in-scope
    ``{prefix}_{year}`` columns for the requested year). Applies
    the §6 region / ``hdicode`` defensive checks. Returns a
    wide-format DataFrame with the static columns + the in-scope
    ``{prefix}_{year}`` columns; all other columns (rank fields,
    year-2022-only metadata, non-social-wellbeing prefixes) are
    dropped.

    Args:
        csv_path: absolute path to the UNDP HDI CSV.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        year: if set, the function validates the in-scope
            ``{prefix}_{year}`` columns for this year only. The
            returned wide frame contains all years; the year
            filter is applied during the UNPIVOT. Default:
            ``None`` (all years 1990-2022).

    Returns:
        A wide-format DataFrame with the 4 static columns + the
        in-scope ``{prefix}_{year}`` columns. All columns are
        ``object`` dtype (Python strings) so the empty-cell
        semantics survive into the UNPIVOT.

    Raises:
        FileNotFoundError: if the CSV is missing.
        ValueError: if the CSV is missing a required static
            column, or if it is missing an expected
            ``{prefix}_{year}`` column for an in-scope catalog
            prefix.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"UNDP HDI CSV not found: {csv_path}")

    # Read every column as a string so empty cells survive as
    # ``""`` rather than becoming ``NaN`` mid-pipeline (we want
    # to surface them as debug-level drops during the UNPIVOT,
    # not lose them to the pandas NA coercion).
    df = pd.read_csv(
        csv_path,
        encoding=UNDP_HDI_ENCODING,
        dtype=str,
        keep_default_na=False,
    )

    # Schema validation: hard failure for missing required
    # columns (per architecture §6).
    _validate_wide_schema(df, catalog_path=catalog_path, year=year)

    # Defensive §6 checks: warn (not fail) for unknown region /
    # hdicode values. The row is preserved verbatim.
    _check_region_codes(df)
    _check_hdicode_values(df)

    # Keep only the static columns + the in-scope
    # ``{prefix}_{year}`` columns. Rank / metadata / non-social-
    # wellbeing columns are dropped at this step (architecture
    # §3 + §4).
    specs = load_undp_hdi_catalog(catalog_path=catalog_path)
    in_scope_prefixes = {spec.raw_column for spec in specs}

    cols_to_keep: list[str] = list(UNDP_HDI_STATIC_COLUMNS)
    for col in df.columns:
        if col in UNDP_HDI_STATIC_COLUMNS:
            continue
        parsed = _parse_col_year(col)
        if parsed is None:
            continue
        prefix, _year = parsed
        if prefix in in_scope_prefixes:
            cols_to_keep.append(col)
    return df[cols_to_keep].copy()
