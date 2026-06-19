"""Stage 2 -- RSF World Press Freedom Index: catalog, paths, parquet write.

This module is the I/O half of the RSF adapter. It owns:

- :data:`RSF_PRESS_FREEDOM_SOURCE_KEY` and
  :data:`RSF_PRESS_FREEDOM_ATTRIBUTION` -- module-level constants
  consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed. Uses a
  ``category`` field (not ``rating_category``) to match the canonical
  RSF catalog header at
  ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``.
- :func:`load_rsf_press_freedom_catalog` -- read the catalog CSV.
- :func:`default_raw_csv_path` -- resolve the canonical data-lake
  path for one year file.
- :func:`default_processed_parquet_path` -- the conventional narrow
  parquet path.
- Named constants: source key, encoding fallbacks, score-column
  variants per year, rank-column variants per year, component-column
  set (2022+ only), the expected comma-decimal separator, and the
  semicolon delimiter.

The CSV reader (``read_rsf_press_freedom_csv``) lives in
:mod:`leaders_db.ingest.rsf_press_freedom_csv`. The DB writes
(sources upsert, source_observations write, run manifest) live in
:mod:`leaders_db.ingest.rsf_press_freedom_db` (with pure helpers in
:mod:`leaders_db.ingest.rsf_press_freedom_db_helpers`). The
orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.rsf_press_freedom`.

RSF is structurally distinct from every prior Stage 2 adapter:

- It is the first source with **multiple local input files** (24
  annual CSVs spanning 2002-2026, with 2011 absent). Per Always-On
  Rule #9 (no raw edits), the orchestrator reads each year file
  independently rather than concatenating them into one wide CSV
  in ``data/interim/``.
- It is the first source with **semicolon-delimited CSVs and a
  comma decimal separator** (European convention). The standard
  V-Dem / WDI / WGI / UCDP / SIPRI milex adapters read comma-
  delimited CSVs with period decimals.
- It is the first source with **mixed encodings across years**:
  2002-2024 are ``utf-8-sig`` (with BOM); 2025-2026 are ``cp1252``
  (no BOM, contains Arabic/Persian country labels not representable
  in UTF-8). The reader applies a BOM-first / cp1252-fallback
  strategy.
- It has **two pre/post-2022 schema generations**: 2002-2021 is a
  16-column wide format; 2022+ adds 5 component-context columns
  (Political Context, Economic Context, Legal Context, Social
  Context, Safety). The Stage 2 indicator catalog lists 7
  indicators (2 from the base format + 5 components); for pre-2022
  files the 5 component columns are absent and the observations
  for those indicators are simply not written for those years.
- The 2022 file contains **181 blank separator rows** between data
  rows (metadata.json ``blank_row_count_excluding_header: 181``).
  The reader drops them; the ISO column is the canonical
  row-presence signal.
- It is the first source where the **direct 2011 file is absent**.
  RSF's combined 2011/2012 edition is represented by the 2012 CSV
  (the 2012 file's ``Year (N)`` column reads ``"2011-12"``). Year
  =2011 queries return an empty DataFrame (FileNotFoundError on
  the path is the canonical signal).
- It is the first source where the **score direction is higher-is-
  better** (higher RSF score = better press-freedom situation --
  the RSF methodology inverts the natural "freedom" framing).
- It targets the ``political_freedom`` rating category exclusively
  (RSF is a press/media-freedom sub-signal per
  ``docs/source-vetting-report.md`` §3.2).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..paths import processed_dir, raw_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``rsf_press_freedom_db`` and ``rsf_press_freedom_csv`` can
#: import it from us, and ``rsf_press_freedom`` can re-export it.
RSF_PRESS_FREEDOM_SOURCE_KEY: str = "rsf_press_freedom"

#: Stable RSF attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (§1, ``rsf_press_freedom`` entry,
#: attribution text in the Summary table). This constant must be a
#: substring of that doc; the
#: :func:`test_rsf_press_freedom_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15).
RSF_PRESS_FREEDOM_ATTRIBUTION: str = (
    "RSF World Press Freedom Index (Reporters Without Borders 2026)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_rsf_press_freedom_run_manifest` in ``rsf_press_freedom_db``
#: can import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "rsf_press_freedom.csv"
)

#: Per-year raw CSV file name pattern inside ``data/raw/rsf_press_freedom/``.
#: ``{year}`` is the 4-digit year (e.g. ``rsf_press_freedom_2023.csv``).
#: Used by :func:`default_raw_csv_path` to resolve the canonical path.
RAW_CSV_NAME_PATTERN: str = "rsf_press_freedom_{year}.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/rsf_press_freedom/``.
PROCESSED_PARQUET_NAME: str = "rsf_press_freedom_country_year.parquet"

#: Run manifest JSON name written next to the parquet.
RUN_MANIFEST_NAME: str = "rsf_press_freedom_run_manifest.json"

#: Encoding fallback order. The reader detects UTF-8-sig (with BOM)
#: first because the 2002-2024 RSF files use it; cp1252 is the
#: fallback for 2025-2026 files that contain non-UTF-8 Arabic/Persian
#: country labels. Latin-1 is the final safety net (never raises
#: on a decode error in this byte range, but the column-name BOM is
#: preserved as a literal ``\ufeff`` prefix -- which is why the BOM
#: detection comes first).
ENCODING_FALLBACKS: tuple[str, ...] = ("utf-8-sig", "cp1252", "latin-1")

#: UTF-8 BOM bytes. Used by the reader to short-circuit encoding
#: detection for the 2002-2024 RSF files.
UTF8_BOM: bytes = b"\xef\xbb\xbf"

#: CSV delimiter used by every RSF annual file (European convention).
CSV_DELIMITER: str = ";"

#: RSF CSV column names that resolve to the canonical
#: ``rsf_press_freedom_score`` indicator. Each year file uses one
#: of these names -- the reader matches the first one found in the
#: header. Per metadata.json ``header_groups``: ``Score N`` (2002-
#: 2021), ``Score`` (2022-2024), ``Score 2025`` (2025),
#: ``Score 2026`` (2026).
SCORE_COLUMN_VARIANTS: tuple[str, ...] = (
    "Score N",
    "Score",
    "Score 2025",
    "Score 2026",
)

#: RSF CSV column names that resolve to the canonical
#: ``rsf_press_freedom_rank`` indicator. Per metadata.json: ``Rank N``
#: (2002-2021), ``Rank`` (2022+).
RANK_COLUMN_VARIANTS: tuple[str, ...] = (
    "Rank N",
    "Rank",
)

#: The 5 component-context indicator column names in 2022+ files.
#: Pre-2022 files do not carry these columns; the reader simply
#: emits no component observations for pre-2022 years. The catalog
#: logical ``raw_column`` values (``political_context`` etc.) are
#: matched to these actual headers.
COMPONENT_COLUMNS: tuple[str, ...] = (
    "Political Context",
    "Economic Context",
    "Legal Context",
    "Social Context",
    "Safety",
)

#: Mapping from the catalog ``raw_column`` (logical) name to the
#: matching actual CSV header in 2022+ files. Used by the reader to
#: resolve a catalog spec to the column to read.
COMPONENT_LOGICAL_TO_HEADER: dict[str, str] = {
    "political_context": "Political Context",
    "economic_context": "Economic Context",
    "legal_context": "Legal Context",
    "social_context": "Social Context",
    "safety": "Safety",
}

#: Years available from the canonical direct-CSV pattern. The 2011
#: file is absent (see metadata.json ``missing_years_from_direct_csv_pattern``);
#: the 2012 file represents RSF's combined 2011/2012 edition.
AVAILABLE_YEARS: tuple[int, ...] = (
    2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    # 2011 absent; the 2012 file represents the combined 2011/2012 edition.
    2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021,
    2022, 2023, 2024, 2025, 2026,
)

#: First / last year of the canonical direct-CSV pattern.
YEAR_START: int = 2002
YEAR_END: int = 2026

#: The year that is absent from the direct-CSV pattern. Year=2011
#: queries return an empty DataFrame (FileNotFoundError on the path
#: is the canonical signal; the orchestrator's empty-frame short
#: circuit covers this case).
MISSING_DIRECT_YEAR: int = 2011

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "rsf_press_freedom_attribution"
_PARQUET_META_SOURCE_KEY: str = "rsf_press_freedom_source_key"


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the RSF indicator catalog.

    Mirrors the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS / UNDP HDI :class:`IndicatorSpec` shape, with one key
    difference: RSF uses a ``category`` field (not
    ``rating_category``) to match the canonical RSF catalog header
    at ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``.

    Every Stage 2 adapter resolves its raw column from this dataclass
    so the score modules in Stage 9-10 can normalize and direct
    indicators consistently across sources.

    The ``raw_column`` here is a LOGICAL name (e.g. ``score``,
    ``rank``, ``political_context``). The CSV reader resolves it to
    the year-specific actual column at parse time
    (e.g. ``score`` -> ``Score N`` for 2002-2021 or ``Score`` for
    2022+). This indirection keeps the catalog stable across the
    pre/post-2022 schema change.
    """

    variable_name: str
    raw_column: str
    category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The CSV uses ``higher_is_better=1`` for "higher is better" and
        ``0`` otherwise (the V-Dem / WGI / UCDP / SIPRI milex /
        SIPRI Yearbook Ch.7 / PTS / UNDP HDI convention). The
        constructor converts that to a real bool. Empty / missing
        values in optional fields become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            category=row.get("category", "").strip(),
            raw_scale=row.get("raw_scale", "").strip(),
            normalized_scale_target=row.get(
                "normalized_scale_target", "",
            ).strip(),
            higher_is_better=(
                row.get("higher_is_better", "1").strip() == "1"
            ),
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_rsf_press_freedom_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the RSF indicator catalog from
    ``catalogs/rsf_press_freedom.csv``.

    Mirrors the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS / UNDP HDI loaders: handles the leading ``#`` comment
    block, drops comment-only lines, validates the required column
    set, and returns one :class:`IndicatorSpec` per data row in
    file order.

    The required column set is the 8 columns of the RSF catalog
    (per architecture §3 + Rule #15 docs contract):
    ``variable_name``, ``raw_column``, ``category``,
    ``higher_is_better``, ``raw_scale``, ``normalized_scale_target``,
    ``unit``, ``description``.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"RSF indicator catalog not found: {path}"
        )

    required = {
        "variable_name",
        "raw_column",
        "category",
        "higher_is_better",
        "raw_scale",
        "normalized_scale_target",
        "unit",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned
    # text to csv.DictReader. Comment-only means: stripped line starts
    # with ``#`` or is blank. Inline ``#`` characters inside a data
    # row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"RSF catalog {path} has no data rows after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"RSF catalog {path} is missing required columns: "
            f"{sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        # Skip empty rows (e.g. trailing blank line).
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_raw_csv_path(year: int) -> Path:
    """Return the conventional RSF annual CSV path for ``year``.

    Resolves to
    ``<project_root>/data/raw/rsf_press_freedom/rsf_press_freedom_<year>.csv``.

    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/rsf_press_freedom.md`` §2);
    the orchestrator expects the user to have downloaded the CSV via
    the project's download workflow first. Note: ``year=2011``
    intentionally raises FileNotFoundError -- the direct 2011.csv is
    absent (RSF's combined 2011/2012 edition is represented by the
    2012 file).
    """
    path = raw_dir(RSF_PRESS_FREEDOM_SOURCE_KEY) / (
        RAW_CSV_NAME_PATTERN.format(year=year)
    )
    if not path.is_file():
        raise FileNotFoundError(f"RSF annual CSV not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional RSF narrow parquet path.

    Creates the ``data/processed/rsf_press_freedom/`` directory if
    missing.
    """
    processed_dir(RSF_PRESS_FREEDOM_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True,
    )
    return processed_dir(RSF_PRESS_FREEDOM_SOURCE_KEY) / PROCESSED_PARQUET_NAME


# Re-exports so the orchestrator and tests can pull the public
# surface from this module (the lowest-level one) without going
# through sibling modules.
__all__ = [
    "AVAILABLE_YEARS",
    "COMPONENT_COLUMNS",
    "COMPONENT_LOGICAL_TO_HEADER",
    "CSV_DELIMITER",
    "ENCODING_FALLBACKS",
    "MISSING_DIRECT_YEAR",
    "PROCESSED_PARQUET_NAME",
    "RANK_COLUMN_VARIANTS",
    "RAW_CSV_NAME_PATTERN",
    "RSF_PRESS_FREEDOM_ATTRIBUTION",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "RUN_MANIFEST_NAME",
    "SCORE_COLUMN_VARIANTS",
    "UTF8_BOM",
    "YEAR_END",
    "YEAR_START",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_raw_csv_path",
    "load_rsf_press_freedom_catalog",
]
