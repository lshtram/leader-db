"""Stage 2 -- RSF World Press Freedom Index: CSV read + long-to-wide pivot.

This module is the CSV-read half of the RSF adapter. It owns:

- :func:`_detect_encoding` -- BOM-first / cp1252-fallback encoding
  detection per the RSF metadata.json ``encodings_observed_for_metadata_parse``.
- :func:`_resolve_actual_column` -- resolve a catalog ``raw_column``
  (logical name) to the year-specific actual column (e.g.
  ``score`` -> ``Score N`` for 2002-2021 or ``Score`` for 2022+).
- :func:`_normalize_decimal` -- convert an RSF comma-decimal cell
  (``"72,67"``) to the period-decimal Python float (``72.67``).
- :func:`_parse_decimal_optional` -- parse + empty-cell handling.
- :func:`_coerce_rank_optional` -- parse + empty-cell handling for
  the int-typed RSF rank cell.
- :func:`read_rsf_press_freedom_csv` -- read the wide-format RSF
  annual CSV with the right encoding + delimiter + decimal separator,
  resolve the catalog's logical ``raw_column`` names to the actual
  columns, drop the 2022 blank separator rows, normalize commas,
  and return the narrow observation frame.

The narrow frame carries one row per
``(iso3, year, variable_name)`` triple with these columns:

- ``iso3`` -- the canonical country key (3-letter uppercase).
- ``year`` -- int (the file's staged year, supplied by the caller).
- ``variable_name`` -- the catalog ``variable_name`` (e.g.
  ``rsf_press_freedom_score``).
- ``raw_value`` -- the verbatim RSF cell text (``"72,67"``,
  ``"149"``, ``""`` for missing). This is the audit trail that
  Stage 15 reports quote.
- ``normalized_value`` -- the ``float`` / ``int``-coerced numeric
  value, or ``None`` for missing. The comma-decimal separator is
  normalized to period; ranks are coerced to int.
- ``source_row_reference`` -- ``"rsf_press_freedom:<iso3>:<raw_column>"``
  (e.g. ``"rsf_press_freedom:MEX:Score N"`` per the pre-2022 header)
  so Stage 3 / 5 / 15 can locate the source row without re-parsing
  the CSV. The post-2022 header is
  ``"rsf_press_freedom:MEX:Score"`` etc. The raw column suffix
  preserves the year-specific actual column name; downstream
  tooling that wants the canonical ``raw_column`` can parse the
  third segment.

The DB writes (``register_rsf_press_freedom_source``,
``write_rsf_press_freedom_observations``,
``write_rsf_press_freedom_run_manifest``) live in
:mod:`leaders_db.ingest.rsf_press_freedom_db` (with pure helpers in
:mod:`leaders_db.ingest.rsf_press_freedom_db_helpers`). The
catalog loader, path helpers, and parquet write live in
:mod:`leaders_db.ingest.rsf_press_freedom_io`. The orchestrator that
ties everything together lives in
:mod:`leaders_db.ingest.rsf_press_freedom`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .rsf_press_freedom_io import (
    COMPONENT_LOGICAL_TO_HEADER,
    CSV_DELIMITER,
    ENCODING_FALLBACKS,
    RANK_COLUMN_VARIANTS,
    SCORE_COLUMN_VARIANTS,
    UTF8_BOM,
    IndicatorSpec,
    default_raw_csv_path,
    load_rsf_press_freedom_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = ["read_rsf_press_freedom_csv"]


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------


def _detect_encoding(path: Path) -> str:
    """Detect the encoding of an RSF annual CSV.

    Strategy (per the metadata.json ``encodings_observed_for_metadata_parse``):

    1. UTF-8 BOM (3 bytes ``EF BB BF``): the canonical RSF encoding
       for 2002-2024 files. Detected first because it cleanly strips
       the BOM via the ``utf-8-sig`` codec.
    2. cp1252: the canonical RSF encoding for 2025-2026 files
       (Arabic/Persian country labels are not representable in
       UTF-8). Detected by trying ``raw.decode("cp1252")`` without
       raising.
    3. utf-8 (no BOM): the absolute fallback. Rare in the wild for
       RSF; included for defense in depth.
    4. latin-1: the final safety net (never raises on a decode error
       in this byte range, but the column-name BOM is preserved as a
       literal ``\\ufeff`` prefix -- which is why the BOM detection
       comes first).

    The function returns the canonical codec name (one of
    ``ENCODING_FALLBACKS``).
    """
    raw = path.read_bytes()
    if raw.startswith(UTF8_BOM):
        return "utf-8-sig"
    try:
        raw.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    # Final safety net. Must be the last entry in ENCODING_FALLBACKS.
    return ENCODING_FALLBACKS[-1]


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------


def _resolve_actual_column(
    actual_columns: list[str], variants: tuple[str, ...],
) -> str | None:
    """Find the first variant that appears in the file's actual columns.

    The catalog's ``raw_column`` is a LOGICAL name (e.g. ``score``);
    the file's header carries a YEAR-SPECIFIC variant (e.g.
    ``Score N`` for 2002-2021 or ``Score`` for 2022+). The reader
    matches the first variant that appears in the actual column
    list, preserving the year-specific name in
    ``source_row_reference``.

    Returns ``None`` when no variant is found (e.g. the 5 component
    columns are absent in pre-2022 files; the catalog's
    ``rsf_press_freedom_political_context`` spec simply does not
    produce an observation for that year).
    """
    for variant in variants:
        if variant in actual_columns:
            return variant
    return None


# ---------------------------------------------------------------------------
# Numeric coercion
# ---------------------------------------------------------------------------


def _normalize_decimal(cell: str) -> str:
    """Convert an RSF comma-decimal cell to a period-decimal string.

    RSF files use ``","`` as the decimal separator (European
    convention) and ``";"`` as the delimiter. ``"72,67"`` ->
    ``"72.67"``; ``"0,5"`` -> ``"0.5"``. The function is a no-op
    for cells without a comma; integer cells like ``"149"`` round-
    trip unchanged. Used by the float coercion helper below.
    """
    if cell is None:
        return ""
    return str(cell).replace(",", ".").strip()


def _parse_decimal_optional(cell: str) -> float | None:
    """Parse a comma-decimal RSF score cell into ``float``.

    Empty / whitespace-only / ``"nan"`` / ``"NA"`` cells return
    ``None``. Cells that fail the float parse (defensive only --
    RSF data is well-formed in practice) also return ``None`` with
    a debug log.
    """
    if cell is None:
        return None
    normalized = _normalize_decimal(cell)
    if not normalized or normalized.lower() in {"nan", "na", "null"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        _logger.debug(
            "RSF could not parse decimal cell %r; treating as missing.",
            cell,
        )
        return None


def _coerce_rank_optional(cell: str) -> int | None:
    """Parse an RSF rank cell into ``int``.

    RSF rank cells are always integers in the live data (e.g.
    ``"149"``, ``"1"``); the function handles empty cells and
    defensive fall-throughs to ``None`` (a missing rank would
    itself be a data anomaly worth flagging).
    """
    if cell is None:
        return None
    stripped = str(cell).strip()
    if not stripped or stripped.lower() in {"nan", "na", "null"}:
        return None
    try:
        return int(stripped)
    except ValueError:
        _logger.debug(
            "RSF could not parse rank cell %r; treating as missing.",
            cell,
        )
        return None


# ---------------------------------------------------------------------------
# CSV read
# ---------------------------------------------------------------------------


def _build_rows_for_iso3(
    *,
    raw_row: pd.Series,
    iso3: str,
    year: int,
    specs: list[IndicatorSpec],
    actual_columns: list[str],
    score_actual: str | None,
    rank_actual: str | None,
) -> list[dict[str, object]]:
    """Build the narrow-frame rows for one input CSV row.

    Helper extracted from :func:`read_rsf_press_freedom_csv` to keep
    the orchestrator's branch count under the lint cap. Resolves
    each catalog spec's logical ``raw_column`` to the year-specific
    actual column, reads the raw cell, applies the right numeric
    coercion (rank int, score / components comma-decimal float),
    and emits the per-(iso3, variable_name) row dicts.
    """
    rows: list[dict[str, object]] = []
    for spec in specs:
        actual_col: str | None
        if spec.raw_column == "score":
            actual_col = score_actual
        elif spec.raw_column == "rank":
            actual_col = rank_actual
        elif spec.raw_column in COMPONENT_LOGICAL_TO_HEADER:
            # Components are present in 2022+ files only.
            actual_col = _resolve_actual_column(
                actual_columns,
                (COMPONENT_LOGICAL_TO_HEADER[spec.raw_column],),
            )
        else:
            # Defensive: unknown logical name -- should not
            # happen because the catalog is the source of truth.
            _logger.warning(
                "RSF catalog spec has unknown logical raw_column=%s "
                "(iso3=%s, year=%d). Skipping.",
                spec.raw_column, iso3, year,
            )
            continue
        if actual_col is None:
            # The column is absent in this year's file (e.g.
            # component columns in a pre-2022 file). Skip without
            # emitting an observation; this is the documented
            # pre/post-2022 schema break.
            continue
        cell = raw_row[actual_col]
        raw_value_str = "" if cell is None else str(cell)
        if spec.raw_column == "rank":
            # Rank is int in the raw cell (always an integer in
            # the live data); preserve the raw_value verbatim for
            # the audit trail.
            normalized = _coerce_rank_optional(raw_value_str)
        else:
            # Score and components are comma-decimal floats.
            normalized = _parse_decimal_optional(raw_value_str)
        rows.append(
            {
                "iso3": iso3,
                "year": int(year),
                "variable_name": spec.variable_name,
                "raw_value": raw_value_str,
                "normalized_value": normalized,
                "source_row_reference": (
                    f"rsf_press_freedom:{iso3}:{actual_col}"
                ),
            },
        )
    return rows


def read_rsf_press_freedom_csv(
    year: int,
    *,
    csv_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read one RSF annual CSV into a narrow observation DataFrame.

    Steps (per ``docs/architecture/rsf_press_freedom.md`` §6 + the
    PTS / WGI / UNDP HDI read pattern):

    1. Resolve the canonical ``data/raw/rsf_press_freedom/rsf_press_freedom_<year>.csv``
       path (or use the caller-supplied ``csv_path`` override).
    2. Detect the encoding (BOM-first / cp1252-fallback / latin-1
       safety net).
    3. Read the wide-format CSV with ``encoding=<detected>``,
       ``sep=;``, ``keep_default_na=False``, ``dtype=str`` so blank
       cells survive as empty strings (not NaN).
    4. Drop blank rows (the 2022 file has 181 blank separator rows
       per metadata.json). The ISO column is the canonical row-
       presence signal: a row with a non-empty ISO is a data row;
       a row with an empty ISO is a separator row (dropped).
    5. Resolve the catalog's logical ``raw_column`` names to the
       year-specific actual columns. Pre-2022 files do not carry
       the 5 component-context columns; for those years the
       corresponding specs simply produce no observation.
    6. Build the narrow frame: one row per
       ``(iso3, variable_name)`` pair per year. ``year`` is set
       from the ``year=`` argument (NOT from the file's ``Year (N)``
       column -- the file's ``Year (N)`` may be ``"2011-12"`` for the
       2012 file's combined edition; we always emit ``year=<year>``
       for downstream consistency).
    7. Empty cells in the score / rank / component columns are
       preserved as empty ``raw_value`` strings and ``None``
       ``normalized_value`` floats (no imputation per Always-On
       Rule #8). Comma decimals are normalized to period in
       ``normalized_value`` only; ``raw_value`` preserves the
       verbatim RSF cell text.

    Args:
        year: the 4-digit year. The orchestrator passes the same
            value it passes to ``default_raw_csv_path``. The narrow
            frame's ``year`` column is set to this value.
        csv_path: override the input CSV. Default: data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A narrow DataFrame with the columns ``iso3``, ``year``,
        ``variable_name``, ``raw_value``, ``normalized_value``,
        ``source_row_reference``. ``year`` is int. ``iso3`` and
        ``variable_name`` are str. ``raw_value`` is str. Empty
        cells produce ``raw_value=""`` and ``normalized_value=None``.

    Raises:
        FileNotFoundError: if the CSV is missing (e.g. ``year=2011``
            which is intentionally absent).
        ValueError: if the file's header is missing a required base
            column (``ISO``).
    """
    if csv_path is None:
        csv_path = default_raw_csv_path(year)
    if not csv_path.is_file():
        raise FileNotFoundError(f"RSF annual CSV not found: {csv_path}")

    encoding = _detect_encoding(csv_path)

    df = pd.read_csv(
        csv_path,
        sep=CSV_DELIMITER,
        encoding=encoding,
        keep_default_na=False,
        dtype=str,
    )

    if "ISO" not in df.columns:
        raise ValueError(
            f"RSF annual CSV {csv_path} is missing the required ISO "
            "column. The RSF schema always carries ISO as the country "
            "key; an absent ISO column breaks the Stage 2 contract."
        )

    # Drop blank separator rows (the 2022 file has 181 per
    # metadata.json). The ISO column is the canonical row-presence
    # signal: a row with a non-empty ISO is a data row.
    before = len(df)
    iso_stripped = df["ISO"].astype(str).str.strip()
    df = df.loc[~iso_stripped.eq("")].copy()
    dropped = before - len(df)
    if dropped:
        _logger.debug(
            "RSF dropped %d blank separator row(s) (empty ISO) for "
            "year=%d (debug-level per architecture §6).",
            dropped, year,
        )

    specs = load_rsf_press_freedom_catalog(catalog_path=catalog_path)
    actual_columns = df.columns.tolist()

    # Resolve the score + rank actual columns once (they're shared
    # across all rows of the same file).
    score_actual = _resolve_actual_column(
        actual_columns, SCORE_COLUMN_VARIANTS,
    )
    rank_actual = _resolve_actual_column(
        actual_columns, RANK_COLUMN_VARIANTS,
    )

    # Build the narrow frame: one row per
    # (iso3, variable_name) pair. The frame is constructed in a
    # list-of-dicts and assembled at the end so we can pre-sort the
    # catalog specs by raw_column for deterministic iteration.
    rows: list[dict[str, object]] = []
    for _, raw_row in df.iterrows():
        iso3 = str(raw_row["ISO"]).strip()
        if not iso3:
            # Defensive -- should not happen after the blank-row
            # filter above, but the empty-ISO check is cheap.
            continue
        rows.extend(
            _build_rows_for_iso3(
                raw_row=raw_row,
                iso3=iso3,
                year=year,
                specs=specs,
                actual_columns=actual_columns,
                score_actual=score_actual,
                rank_actual=rank_actual,
            ),
        )

    narrow = pd.DataFrame(
        rows,
        columns=(
            "iso3",
            "year",
            "variable_name",
            "raw_value",
            "normalized_value",
            "source_row_reference",
        ),
    )
    if narrow.empty:
        return narrow

    # Sort for deterministic output: (year ASC, iso3 ASC,
    # variable_name ASC). Stable mergesort matches the V-Dem / WGI /
    # UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI
    # convention.
    narrow = narrow.sort_values(
        by=["year", "iso3", "variable_name"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return narrow
