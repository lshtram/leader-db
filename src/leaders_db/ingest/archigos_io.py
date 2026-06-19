"""Stage 2 -- Archigos v4.1: catalog, path helpers, parquet write.

This module is the I/O half of the Archigos adapter. It owns:

- :data:`ARCHIGOS_SOURCE_KEY` and :data:`ARCHIGOS_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the
  orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_archigos_catalog` -- read the catalog CSV.
- :func:`default_dta_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`read_archigos` -- the read orchestrator. Opens the .dta with
  pyreadstat (cp1252 encoding, the only encoding that parses the
  Archigos v4.1 file), narrows to the 6 catalog ``raw_column`` s,
  and returns a narrow long-format frame keyed by (idacr, year,
  variable_name).
- :func:`write_archigos_parquet` -- persist the narrow frame as
  parquet with the Archigos attribution attached to the file-level
  metadata.
- Named constants: source key, attribution block, catalog path, raw
  dta name, parquet name, parquet metadata keys, the 6 identity
  raw_column -> variable_name map, the start-date year extraction,
  and the year window.

The Stata read helpers (per-cell coercion, identity-column coercion,
date -> year-decimal coercion) live in :mod:`archigos_dta`. The DB
writes (sources upsert, source_observations write, run manifest)
live in :mod:`archigos_db`. The pure coercion helpers and
bundle-metadata parsing live in :mod:`archigos_db_helpers`. The
Pydantic result model lives in :mod:`archigos_result`. The
orchestrator that ties everything together lives in
:mod:`archigos`.

Archigos is the first Stage 2 adapter that reads a Stata .dta file
(verified live 2026-06-19 against
``data/raw/archigos/Archigos_4.1_stata14.dta``; 3,409 leader spells
x 28 columns x 189 country-codes, coverage 1840-2015). The .dta
uses cp1252 (Windows-1252) encoding; ``pyreadstat.read_dta``
requires ``encoding='cp1252'`` to parse correctly (other encodings
either fail with "Unable to convert string" or "unsupported
character set"). pyreadstat>=1.3 is the new runtime dependency
added in Phase C for this source.

Per Always-On Rule #15, the :data:`ARCHIGOS_ATTRIBUTION` constant is
byte-identical to the per-source entry in
``docs/source-attributions.md`` §1 ``archigos``. The
:func:`test_archigos_attribution_matches_attributions_doc` test
enforces the byte-for-byte consistency.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..paths import processed_dir, raw_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``archigos_db`` and ``archigos_dta`` can import it from us, and
#: ``archigos`` can re-export it.
ARCHIGOS_SOURCE_KEY: str = "archigos"

#: Stable Archigos attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (archigos entry). This constant
#: must be a substring of that doc; the
#: :func:`test_archigos_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle: ``archigos_db``
#: imports it from us, and ``archigos`` re-exports it. The exact
#: string matches the per-source entry in
#: ``docs/source-attributions.md` §1 ``archigos`` (the Stage 15
#: "Attribution text in reports" line).
ARCHIGOS_ATTRIBUTION: str = (
    "Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_archigos_run_manifest` in ``archigos_db`` can import
#: it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "archigos.csv"
)

#: Raw .dta file name inside ``data/raw/archigos/``.
_RAW_DTA_NAME: str = "Archigos_4.1_stata14.dta"

#: Narrow parquet that Stage 2 writes under ``data/processed/archigos/``.
_PROCESSED_PARQUET_NAME: str = "archigos_leader_spell.parquet"

#: The cp1252 encoding the Archigos v4.1 .dta file uses. UTF-8
#: fails on country names with diacritics; ``pyreadstat`` requires
#: this exact encoding or it raises
#: "File has an unsupported character set".
ARCHIGOS_DTA_ENCODING: str = "cp1252"

#: The earliest and latest start years in the Archigos v4.1 bundle
#: (verified live 2026-06-19; 3,409 leader spells, startdate year
#: range 1840-2015). Used for sanity checks and the orchestrator's
#: no-year run.
ARCHIGOS_YEAR_START: int = 1840
ARCHIGOS_YEAR_END: int = 2015

#: The 6 in-scope identity ``raw_column`` names. The .dta reader
#: selects only these columns; the other 22 Archigos columns (e.g.
#: ``prevtimesinoffice``, ``posttenurefate``, ``yrborn``, ``yrdied``,
#: ``dbpediauri``) are NOT extracted by the Stage 2 adapter (they
#: are deferred to a future iteration if the Stage 4 resolver needs
#: them).
ARCHIGOS_IDENTITY_RAW_COLUMNS: tuple[str, ...] = (
    "leader",
    "startdate",
    "enddate",
    "entry",
    "exit",
    "gender",
)


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the Archigos indicator catalog.

    Mirrors the V-Dem / CIRIGHTS / UNDP HDI :class:`IndicatorSpec`
    shape, with a ``category`` field (not ``rating_category``) to
    match the canonical Archigos catalog header at
    ``src/leaders_db/ingest/catalogs/archigos.csv``. All 6 Archigos
    catalog variables are in the ``leader_identity`` category and
    carry ``higher_is_better=0`` (these are identity fields, not
    indicator scores; no scoring direction applies).
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
        ``0`` otherwise (the V-Dem / CIRIGHTS / UNDP HDI convention).
        The constructor converts that to a real bool. Empty / missing
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
                row.get("higher_is_better", "0").strip() == "1"
            ),
            unit=row.get("unit", "").strip(),
        )


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------


def load_archigos_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the Archigos indicator catalog from
    ``catalogs/archigos.csv``.

    Mirrors the V-Dem / CIRIGHTS / UNDP HDI loaders: handles the
    leading ``#`` comment block, drops comment-only lines, validates
    the required column set, and returns one :class:`IndicatorSpec`
    per data row in file order.

    The required column set is the 8 columns of the Archigos
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
            f"Archigos indicator catalog not found: {path}"
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
            f"Archigos catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"Archigos catalog {path} is missing required columns: "
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


def default_dta_path() -> Path:
    """Return the conventional Archigos .dta path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/archigos/Archigos_4.1_stata14.dta``.
    Raises :class:`FileNotFoundError` if the file is missing; the
    adapter expects the user to have downloaded the .dta via the
    project's download workflow first (per
    ``docs/local-data-store.md`` § "Adding a New Source").
    """
    path = raw_dir(ARCHIGOS_SOURCE_KEY) / _RAW_DTA_NAME
    if not path.is_file():
        raise FileNotFoundError(f"Archigos .dta not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional Archigos narrow parquet path.

    Creates the ``data/processed/archigos/`` directory if missing.
    """
    processed_dir(ARCHIGOS_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(ARCHIGOS_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_archigos(
    *,
    dta_path: Path | None = None,
    year: int | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read the Archigos .dta and return a narrow long-format frame.

    The output frame has the following columns (in this order):

    - ``obsid`` -- Archigos observation id (e.g. ``"USA-1869"``),
      locates the raw source row.
    - ``idacr`` -- Archigos 3-letter country code (NOT always
      ISO3; ``idacr`` is the audit-trail-friendly form).
    - ``ccode`` -- Archigos numeric COW code (Python int).
    - ``year`` -- start year of the leader's tenure (int; e.g. 1869
      for the spell beginning 1869-03-04).
    - ``end_year`` -- end year of the leader's tenure (int; e.g.
      1877 for the spell ending 1877-03-04).
    - ``variable_name`` -- one of the 6 catalog ``variable_name`` s
      (e.g. ``"archigos_leader_name"``).
    - ``raw_value`` -- the verbatim cell text from the .dta
      (preserved as the audit trail; e.g. ``"Grant"`` for
      ``archigos_leader_name``).
    - ``normalized_value`` -- the light-coerced value (e.g. the
      decimal year 1869.169 for a ``startdate`` of 1869-03-04).
      ``pd.NA`` for text fields (no numeric coercion).
    - ``source_row_reference`` -- the audit-trail locator for the
      raw row + variable; format
      ``archigos:<obsid>:<start_year>:<raw_column>``.

    The function reads the 6 catalog ``raw_column`` s only (the
    other 22 Archigos columns are deferred). The .dta is opened
    once with ``pyreadstat.read_dta(encoding='cp1252')`` (the only
    encoding that parses the Archigos v4.1 file); the wide
    Archigos frame is narrowed to the catalog columns and
    reshaped to long format via the helpers in
    :mod:`archigos_dta`.

    Args:
        dta_path: override the input .dta. Default: data-lake path.
        year: filter to a single start-year (e.g. ``2000`` for all
            Archigos spells starting in 2000). Default: all 3,409
            spells.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A pandas DataFrame. The frame is empty if ``year`` matches
        no spell. ``normalized_value`` is float64 with ``pd.NA``
        for missing values.
    """
    # Local import to break the circular dependency:
    # ``archigos_dta`` imports constants from this module, so this
    # module cannot import the function at the top level without
    # creating a cycle.
    from .archigos_dta import (
        read_dta_to_long_dataframe,
    )

    specs = load_archigos_catalog(catalog_path=catalog_path)
    actual_dta_path = dta_path or default_dta_path()
    return read_dta_to_long_dataframe(
        dta_path=actual_dta_path,
        year=year,
        specs=specs,
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_archigos_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
) -> Path:
    """Write the narrow long-format frame as a parquet file.

    The parquet's file-level metadata carries the Archigos
    attribution block + the source key + the catalog path so
    downstream stages (Stage 5 evidence bundle, Stage 15 summary
    report) can find the attribution without re-reading the
    source code (per Always-On Rule #15).

    Empty frames are still written (so downstream stages can
    detect "this run produced no data" without re-reading the
    .dta). The parquet schema is preserved across runs (the column
    dtypes are stable for the same catalog).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = parquet_path or default_processed_parquet_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # pyarrow schema-level metadata is bytes; encode the attribution
    # text + source key + catalog path as UTF-8.
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"archigos_attribution"] = ARCHIGOS_ATTRIBUTION.encode("utf-8")
    metadata[b"archigos_source_key"] = ARCHIGOS_SOURCE_KEY.encode("utf-8")
    metadata[b"archigos_catalog_path"] = str(_DEFAULT_CATALOG_PATH).encode("utf-8")
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, path)
    return path


# Re-export the catalog + path-helper + read + parquet surface.
__all__ = [
    "ARCHIGOS_ATTRIBUTION",
    "ARCHIGOS_DTA_ENCODING",
    "ARCHIGOS_IDENTITY_RAW_COLUMNS",
    "ARCHIGOS_SOURCE_KEY",
    "ARCHIGOS_YEAR_END",
    "ARCHIGOS_YEAR_START",
    "IndicatorSpec",
    "default_dta_path",
    "default_processed_parquet_path",
    "load_archigos_catalog",
    "read_archigos",
    "write_archigos_parquet",
]
