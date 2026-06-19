"""Stage 2 -- REIGN (Bell 2016): catalog, path helpers, parquet write.

This module is the I/O half of the REIGN adapter. It owns:

- :data:`REIGN_SOURCE_KEY` and :data:`REIGN_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the
  orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_reign_catalog` -- read the catalog CSV.
- :func:`default_csv_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`read_reign` -- the read orchestrator. Reads the
  leader-month CSV with pandas, narrows to the 8 catalog
  ``raw_column`` s, and returns a narrow long-format frame keyed
  by (country, year, month, variable_name).
- :func:`write_reign_parquet` -- persist the narrow frame as
  parquet with the REIGN attribution attached to the file-level
  metadata.
- Named constants: source key, attribution block, catalog path, raw
  CSV name, parquet name, parquet metadata keys, the 8 identity
  raw_column -> variable_name map, the year window, and the
  URL-safe substitution helper for country display names.

The CSV read + per-cell coercion helpers live in
:mod:`reign_csv`. The DB writes (sources upsert,
source_observations write, run manifest) live in
:mod:`reign_db`. The pure helpers and bundle-metadata parsing
live in :mod:`reign_db_helpers`. The Pydantic result model lives
in :mod:`reign_result`. The orchestrator that ties everything
together lives in :mod:`reign`.

REIGN is the first Stage 2 adapter that reads a **GitHub raw
CSV** (verified live 2026-06-19 against
``data/raw/reign/REIGN_2021_8.csv``; 138,600 leader-month rows x
41 columns x 200 country-codes, coverage 1950-2021-08). The CSV
uses UTF-8 encoding and is comma-delimited; pandas reads it
without any special parameters.

REIGN is structurally closer to Archigos (long-format per
leader-month) than to V-Dem (wide country-year) or WGI (multi-
sheet xlsx). The Stage 2 adapter writes one
``source_observations`` row per (leader-month-row,
identity-column) pair, keyed by the row's year column.

Per Always-On Rule #15, the :data:`REIGN_ATTRIBUTION` constant is
byte-identical to the per-source entry in
``docs/source-attributions.md`` §1 ``reign``. The
:func:`test_reign_attribution_matches_attributions_doc` test
enforces the byte-for-byte consistency.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..paths import processed_dir, raw_dir

# ``read_reign_csv`` is imported below in the :func:`read_reign`
# function (local import) to break the circular dependency:
# ``reign_csv`` imports constants from this module, so this module
# cannot import the function at the top level without creating a
# cycle.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``reign_db`` and ``reign_csv`` can import it from us, and
#: ``reign`` can re-export it.
REIGN_SOURCE_KEY: str = "reign"

#: Stable REIGN attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (reign entry). This constant must
#: be a substring of that doc; the
#: :func:`test_reign_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle: ``reign_db``
#: imports it from us, and ``reign`` re-exports it. The exact
#: string matches the per-source entry in
#: ``docs/source-attributions.md` §1 ``reign`` (the Stage 15
#: "Attribution text in reports" line).
REIGN_ATTRIBUTION: str = (
    "REIGN dataset (Bell 2016), snapshot of August 2021."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_reign_run_manifest` in ``reign_db`` can import it
#: without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "reign.csv"
)

#: Raw CSV file name inside ``data/raw/reign/``.
_RAW_CSV_NAME: str = "REIGN_2021_8.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/reign/``.
_PROCESSED_PARQUET_NAME: str = "reign_leader_month.parquet"

#: The earliest and latest data years in the REIGN 2021-8 bundle
#: (verified live 2026-06-19; 138,600 leader-month rows, year
#: range 1950-2021, 200 country-codes). Used for sanity checks
#: and the orchestrator's no-year run.
REIGN_YEAR_START: int = 1950
REIGN_YEAR_END: int = 2021

#: The 8 in-scope identity / governance ``raw_column`` names. The
#: CSV reader selects only these columns; the other 33 REIGN
#: columns (e.g. ``elected``, ``age``, ``militarycareer``,
#: ``anticipation``, election-anticipation columns, coup-risk
#: columns) are NOT extracted by the Stage 2 adapter (they are
#: deferred to a future iteration if the Stage 4 resolver needs
#: them). The catalog narrows to the 8 columns that the
#: prototype's evidence-bundle logic most directly consumes.
REIGN_IDENTITY_RAW_COLUMNS: tuple[str, ...] = (
    "leader",
    "government",
    "elected",
    "age",
    "male",
    "tenure_months",
    "political_violence",
    "irregular",
)

#: Compiled regex used by :func:`safe_country_token` to substitute
#: URL-unsafe characters in country display names for the
#: ``source_row_reference`` audit suffix (e.g. ``"Trinidad & Tobago"``
#: -> ``"Trinidad_Tobago"``). The substitute character is
#: underscore. Non-ASCII letters are preserved (e.g. ``Curaçao``
#: stays ``Curaçao``), matching the CIRIGHTS / WGI / UCDP
#: convention of preserving display names verbatim.
_UNSAFE_RE = re.compile(r"[^\w]+", re.UNICODE)


def safe_country_token(country: str) -> str:
    r"""Substitute URL-unsafe characters in a country name with underscores.

    Used to build the ``source_row_reference`` audit suffix
    (e.g. ``reign:USA:Truman:1950:1:leader``). The result is a
    single token (no whitespace, no slashes, no ampersands) so
    the reference is safe to embed in CLI output, parquet
    metadata, and downstream SQL filters. Non-ASCII letters are
    preserved (e.g. ``Curaçao`` stays ``Curaçao``), matching the
    CIRIGHTS / WGI / UCDP convention of preserving display names
    verbatim.

    Note: the helper uses Python's ``\w`` regex class (with the
    ``re.UNICODE`` flag, the default in Python 3) which matches
    Unicode word characters including non-ASCII letters. So a
    character like ``ã`` in ``Curaçao`` is preserved.
    """
    if not country:
        return ""
    # Replace runs of unsafe chars with a single underscore. Trim
    # leading/trailing underscores for cosmetic stability.
    return _UNSAFE_RE.sub("_", str(country)).strip("_")


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the REIGN indicator catalog.

    Mirrors the V-Dem / CIRIGHTS / UNDP HDI / Archigos
    :class:`IndicatorSpec` shape, with a ``category`` field (not
    ``rating_category``) to match the canonical REIGN catalog
    header at
    ``src/leaders_db/ingest/catalogs/reign.csv``. The 8 REIGN
    catalog variables span 2 categories: ``leader_identity`` (6
    columns: leader, government, elected, age, male,
    tenure_months) and ``domestic_violence`` (2 columns:
    political_violence, irregular).
    """

    variable_name: str
    raw_column: str
    category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The CSV uses ``higher_is_better=1`` for "higher is better" and
        ``0`` otherwise (the V-Dem / CIRIGHTS / UNDP HDI / Archigos
        convention). The constructor converts that to a real bool.
        Empty / missing values in optional fields become ``""``.
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
                row.get("higher_is_better", "0").strip() == "1"
            ),
            unit=row.get("unit", "").strip(),
        )


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------


def load_reign_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the REIGN indicator catalog from ``catalogs/reign.csv``.

    Mirrors the V-Dem / CIRIGHTS / UNDP HDI / Archigos loaders:
    handles the leading ``#`` comment block, drops comment-only
    lines, validates the required column set, and returns one
    :class:`IndicatorSpec` per data row in file order.

    The required column set is the 8 columns of the REIGN
    catalog: ``variable_name``, ``raw_column``, ``category``,
    ``higher_is_better``, ``raw_scale``,
    ``normalized_scale_target``, ``unit``, ``description``.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"REIGN indicator catalog not found: {path}"
        )

    required = {
        "variable_name",
        "raw_column",
        "category",
        "higher_is_better",
        "raw_scale",
        "normalized_scale_target",
        "unit",
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
            f"REIGN catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"REIGN catalog {path} is missing required columns: "
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


def default_csv_path() -> Path:
    """Return the conventional REIGN CSV path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/reign/REIGN_2021_8.csv``. Raises
    :class:`FileNotFoundError` if the file is missing; the
    adapter expects the user to have downloaded the CSV via the
    project's download workflow first (per
    ``docs/local-data-store.md`` § "Adding a New Source").
    """
    path = raw_dir(REIGN_SOURCE_KEY) / _RAW_CSV_NAME
    if not path.is_file():
        raise FileNotFoundError(f"REIGN CSV not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional REIGN narrow parquet path.

    Creates the ``data/processed/reign/`` directory if missing.
    """
    processed_dir(REIGN_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(REIGN_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_reign(
    *,
    csv_path: Path | None = None,
    year: int | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read the REIGN CSV and return a narrow long-format frame.

    The output frame has the following columns (in this order):

    - ``country`` -- country display name (e.g. ``"USA"``);
      locates the raw source row.
    - ``ccode`` -- COW numeric country code (Python float;
      preserved from the raw CSV).
    - ``year`` -- year of the leader-month row (int).
    - ``month`` -- month of the leader-month row (int; 1-12).
    - ``leader`` -- leader display name from the raw row.
    - ``variable_name`` -- one of the 8 catalog ``variable_name`` s
      (e.g. ``"reign_leader"``).
    - ``raw_value`` -- the verbatim cell value from the CSV
      (preserved as the audit trail; e.g. ``"Truman"`` for
      ``reign_leader``).
    - ``normalized_value`` -- the light-coerced value (e.g. the
      float 1.0 for ``male`` = 1, or 2.0 for ``male`` = 0, after
      the gender code convention; or the verbatim float for
      numeric columns). ``pd.NA`` for text fields and missing
      values.
    - ``source_row_reference`` -- the audit-trail locator for the
      raw row + variable; format
      ``reign:<country_token>:<leader_token>:<year>:<month>:<raw_column>``.

    The function reads the 8 catalog ``raw_column`` s only (the
    other 33 REIGN columns are deferred). The CSV is opened once
    with pandas; the wide REIGN frame is narrowed to the catalog
    columns and reshaped to long format via the helpers in
    :mod:`reign_csv`.

    Args:
        csv_path: override the input CSV. Default: data-lake path.
        year: filter to a single year (e.g. ``2020`` for all
            REIGN leader-month rows in 2020). Default: all
            138,600 leader-month rows.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A pandas DataFrame. The frame is empty if ``year`` matches
        no row. ``normalized_value`` is float64 with ``pd.NA``
        for missing values.
    """
    # Local import to break the circular dependency: ``reign_csv``
    # imports constants from this module, so this module cannot
    # import the function at the top level without creating a
    # cycle.
    from .reign_csv import (
        read_reign_csv_to_long_dataframe,
    )

    specs = load_reign_catalog(catalog_path=catalog_path)
    actual_csv_path = csv_path or default_csv_path()
    return read_reign_csv_to_long_dataframe(
        csv_path=actual_csv_path,
        year=year,
        specs=specs,
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_reign_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
) -> Path:
    """Write the narrow long-format frame as a parquet file.

    The parquet's file-level metadata carries the REIGN
    attribution block + the source key + the catalog path so
    downstream stages (Stage 5 evidence bundle, Stage 15 summary
    report) can find the attribution without re-reading the
    source code (per Always-On Rule #15).

    Empty frames are still written (so downstream stages can
    detect "this run produced no data" without re-reading the
    CSV). The parquet schema is preserved across runs (the
    column dtypes are stable for the same catalog).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = parquet_path or default_processed_parquet_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # pyarrow schema-level metadata is bytes; encode the attribution
    # text + source key + catalog path as UTF-8.
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"reign_attribution"] = REIGN_ATTRIBUTION.encode("utf-8")
    metadata[b"reign_source_key"] = REIGN_SOURCE_KEY.encode("utf-8")
    metadata[b"reign_catalog_path"] = str(_DEFAULT_CATALOG_PATH).encode("utf-8")
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, path)
    return path


# Re-export the catalog + path-helper + read + parquet + token surface.
__all__ = [
    "REIGN_ATTRIBUTION",
    "REIGN_IDENTITY_RAW_COLUMNS",
    "REIGN_SOURCE_KEY",
    "REIGN_YEAR_END",
    "REIGN_YEAR_START",
    "IndicatorSpec",
    "default_csv_path",
    "default_processed_parquet_path",
    "load_reign_catalog",
    "read_reign",
    "safe_country_token",
    "write_reign_parquet",
]
