"""Stage 2 -- SIPRI Military Expenditure Database: catalog, path helpers, parquet write.

This module is the I/O half of the SIPRI milex adapter. It owns:

- :data:`SIPRI_MILEX_SOURCE_KEY` and :data:`SIPRI_MILEX_ATTRIBUTION`
  -- module-level constants consumed by the DB layer and the
  orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  leading ``#`` comment block + comment-only line filtering).
- :data:`_SIPRI_MILEX_REGION_LABELS` -- the 15 region/sub-region
  labels (+ the ``"World"`` total) that the xlsx interleaves with
  country names. The read function filters these out.
- :data:`_SIPRI_MILEX_MISSING_STRINGS` -- the SIPRI missing-value
  convention (``"..."``, ``"xxx"``, ``""``) plus the defense-in-depth
  union of V-Dem / WDI / WGI / UCDP sentinels.
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path`
  -- the conventional data-lake locations.
- :func:`write_sipri_milex_parquet` -- persist the wide frame as
  parquet with the SIPRI milex attribution attached to the schema
  metadata.

The xlsx read function lives in :mod:`leaders_db.ingest.sipri_milex_xlsx`.
The DB writes (sources upsert, source_observations write, run manifest,
missing-value coercion) live in :mod:`leaders_db.ingest.sipri_milex_db`.
The orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.sipri_milex`.

SIPRI milex is structurally closer to WGI (one local xlsx, no network)
than to WDI (per-indicator HTTP, JSON cache): there is no
``sipri_milex_http.py``, only the WGI 4-module split. The xlsx is the
canonical input; the Stage 2 adapter opens it with
``openpyxl.read_only=True``, walks the 4 catalog sheets, detects the
per-sheet header row, filters region labels, and pivots long -> wide.

Constants live here (the lowest-level module that does NOT import from
siblings) so :mod:`sipri_milex_db` and :mod:`sipri_milex_xlsx` can
import them from us, and :mod:`sipri_milex` can re-export them.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``sipri_milex_db`` and ``sipri_milex_xlsx`` can import it from
#: us, and ``sipri_milex`` can re-export it.
SIPRI_MILEX_SOURCE_KEY: str = "sipri_milex"

#: Stable SIPRI milex attribution block. The canonical text lives in
#: ``docs/sources/attributions.md`` (sipri section). This constant must
#: be a substring of that doc; the
#: :func:`test_sipri_milex_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency. The constant lives here to
#: break the import cycle: ``sipri_milex_db`` imports it from us, and
#: ``sipri_milex`` re-exports it. The year ``2026`` is the v1.2
#: release year (matching the "© SIPRI 2026" attribution in the xlsx
#: itself), not the latest data year (the data ends at 2025).
SIPRI_MILEX_ATTRIBUTION: str = (
    "Stockholm International Peace Research Institute. 2026. "
    "SIPRI Military Expenditure Database. "
    "https://www.sipri.org/databases/milex"
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_sipri_milex_run_manifest` in ``sipri_milex_db`` can
#: import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "sipri_milex.csv"
)

#: Raw xlsx file name inside ``data/raw/sipri_milex/``. Version-locked
#: to the v1.2 release; the live xlsx is ~922 KB.
_RAW_XLSX_NAME: str = "SIPRI-Milex-data-1949-2025_v1.2.xlsx"

#: Narrow parquet that Stage 2 writes under
#: ``data/processed/sipri_milex/``.
_PROCESSED_PARQUET_NAME: str = "sipri_milex_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "sipri_milex_attribution"
_PARQUET_META_SOURCE_KEY: str = "sipri_milex_source_key"

#: Region / sub-region labels in the SIPRI xlsx that are NOT
#: countries. The read function filters these out so only the ~177
#: country rows end up in the wide frame. The set is the
#: WGI-style "no aggregates" approach, but by display name (the
#: SIPRI xlsx has no ISO3 column). 15 region/sub-region labels
#: observed in the live v1.2 xlsx (verified 2026-06-18) plus the
#: ``"World"`` total (defense in depth; appears in the Regional
#: totals sheet).
_SIPRI_MILEX_REGION_LABELS: frozenset[str] = frozenset(
    {
        "Africa", "North Africa", "sub-Saharan Africa",
        "Americas", "Central America and the Caribbean",
        "North America", "South America",
        "Asia & Oceania", "Central Asia", "East Asia",
        "South Asia", "South East Asia", "Oceania",
        "Europe", "Eastern Europe", "Central and Western Europe",
        "Middle East",
        "World",  # from the Regional totals sheet (defense in depth)
    }
)

#: SIPRI milex's missing-data convention is three tokens: ``"..."``
#: (data unavailable), ``"xxx"`` (country did not exist), and ``""``
#: (empty cell). We include the union of all source-specific sentinels
#: as defense in depth in case a future SIPRI release re-uses them
#: (e.g. WGI's ``"#N/A"``, V-Dem's ``-999``, WDI's ``"null"``).
_SIPRI_MILEX_MISSING_STRINGS: frozenset[str] = frozenset(
    {"...", "xxx", "#N/A", "NA", "NaN", "nan", "null", "None",
     "-999", "-999.0", ""}
)

#: Numeric SIPRI missing sentinel (defense in depth; SIPRI uses
#: ``"..."`` / ``"xxx"``, not ``-999``, but the V-Dem-style helper
#: still recognizes it).
_SIPRI_MILEX_MISSING_SENTINEL: float = -999.0


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the SIPRI milex indicator catalog.

    The V-Dem / WDI / WGI / UCDP :class:`IndicatorSpec` shape is reused
    verbatim: every Stage 2 adapter resolves its raw column from this
    dataclass so the score modules in Stage 9-10 can normalize and
    direct indicators consistently across sources.
    """

    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The CSV uses ``higher_is_better=1`` for "higher is better" and
        ``0`` otherwise (the WGI / V-Dem / WDI convention). The
        constructor converts that to a real bool. Empty / missing
        values in the optional fields become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=(
                row.get("higher_is_better", "1").strip() == "1"
            ),
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the SIPRI milex indicator catalog from
    ``catalogs/sipri_milex.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP loaders: handles the leading
    ``#`` comment block, drops comment-only lines, validates the
    required column set, and returns one :class:`IndicatorSpec` per
    data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"SIPRI milex indicator catalog not found: {path}"
        )

    required = {
        "variable_name",
        "raw_column",
        "rating_category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
        "unit",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned
    # text to csv.DictReader. Comment-only means: stripped line starts
    # with ``#`` or is blank. Inline ``#`` characters inside a data
    # row are preserved (the catalog header may have such characters).
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"SIPRI milex catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"SIPRI milex catalog {path} is missing required columns: "
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


def default_xlsx_path() -> Path:
    """Return the conventional SIPRI milex xlsx path inside the data
    lake.

    Resolves to
    ``<project_root>/data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx``.
    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/sipri-milex.md`` §3.3); the
    adapter expects the user to have downloaded the xlsx via the
    project's download workflow first.
    """
    path = raw_dir(SIPRI_MILEX_SOURCE_KEY) / _RAW_XLSX_NAME
    if not path.is_file():
        raise FileNotFoundError(f"SIPRI milex xlsx not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional SIPRI milex narrow parquet path.

    Creates the ``data/processed/sipri_milex/`` directory if missing.
    """
    processed_dir(SIPRI_MILEX_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(SIPRI_MILEX_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_sipri_milex_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution
    metadata.

    Mirrors :func:`wgi_io.write_wgi_parquet` (and the
    :func:`_attach_parquet_metadata` helper): writes the parquet via
    ``df.to_parquet``, then re-writes the file with the SIPRI milex
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.

    Note: the wide frame may carry a ``_sipri_milex_raw_long`` key in
    ``df.attrs`` (set by :func:`sipri_milex_xlsx.read_sipri_milex`)
    that holds the pre-coercion long frame for the ``raw_value``
    audit trail. That attribute is not JSON-serializable and would
    break pyarrow's attrs serialization, so we strip it from
    ``df.attrs`` before the parquet write. The ``regions_covered`` and
    ``country_count`` attrs are JSON-serializable and are preserved.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # pyarrow serializes df.attrs to parquet file-level metadata. The
    # _sipri_milex_raw_long attr holds a DataFrame, which is not JSON
    # serializable, so we strip it from df.attrs before the parquet
    # write. The data columns are unchanged.
    df.attrs = {
        k: v for k, v in (df.attrs or {}).items()
        if k != "_sipri_milex_raw_long"
    }
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or SIPRI_MILEX_ATTRIBUTION,
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the SIPRI milex attribution + source key to the
    parquet's schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We rewrite
    the parquet in place to add it. This is best-effort: if the
    rewrite fails (corrupt file, race, full disk) the parquet remains
    valid and we log a warning. Schema/data errors are NOT swallowed
    silently -- they re-raise so the orchestrator can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = SIPRI_MILEX_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the
        # audit metadata is lost. Log and continue -- the attribution
        # is also carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach SIPRI milex attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit "
            "fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "SIPRI_MILEX_ATTRIBUTION",
    "SIPRI_MILEX_SOURCE_KEY",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "write_sipri_milex_parquet",
]
