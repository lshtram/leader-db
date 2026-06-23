"""Stage 2 -- Maddison Project Database 2023: indicator catalog, path helpers, parquet write.

This module is the I/O half of the Maddison Project Database 2023
adapter. It owns:

- :data:`MADDISON_PROJECT_SOURCE_KEY` and
  :data:`MADDISON_PROJECT_ATTRIBUTION` -- module-level constants
  consumed by the DB layer and the orchestrator.
- :data:`MADDISON_PROJECT_SHEET_NAME` -- the xlsx sheet name the
  Stage 2 reader opens (``"Full data"``).
- :data:`MADDISON_PROJECT_XLSX_COLUMNS` -- the canonical column set
  the xlsx must carry (``countrycode``, ``country``, ``region``,
  ``year``, ``gdppc``, ``pop``).
- :data:`MADDISON_PROJECT_PROXY_YEAR` /
  :data:`MADDISON_PROJECT_PROXY_REQUESTED_YEAR` -- the 2023 -> 2022
  proxy mapping constants (1-year-gap pattern, same as CIRIGHTS /
  UNDP HDI / Leader Survival).
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path`
  -- the conventional data-lake locations.
- :func:`write_maddison_project_parquet` -- persist the narrow
  frame as parquet with the Maddison attribution attached to the
  schema metadata.

The xlsx read function lives in
:mod:`leaders_db.ingest.maddison_project_xlsx`. The DB writes
(sources upsert, source_observations write, run manifest, missing-
value coercion) live in :mod:`leaders_db.ingest.maddison_project_db`
and :mod:`leaders_db.ingest.maddison_project_db_helpers`. The
orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.maddison_project`.

Maddison is structurally closer to WGI / BTI / CIRIGHTS (one local
xlsx, no network) than to WDI (per-indicator HTTP, JSON cache).
There is no ``maddison_project_http.py`` -- the Stage 2 contract is
``openpyxl.read_only=True`` on the canonical ``Full data`` sheet.

Constants live here (the lowest-level module that does NOT import
from siblings) so :mod:`maddison_project_db`,
:mod:`maddison_project_xlsx`, and
:mod:`maddison_project_db_helpers` can import them from us, and
:mod:`maddison_project` can re-export them.
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
#: so ``maddison_project_db`` can import it from us, and
#: ``maddison_project`` can re-export it.
MADDISON_PROJECT_SOURCE_KEY: str = "maddison_project"

#: Stable Maddison Project Database 2023 attribution block. The
#: canonical text lives in ``docs/sources/attributions.md``
#: (maddison_project section). This constant must be a substring of
#: that doc; the
#: :func:`test_maddison_project_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle:
#: ``maddison_project_db`` imports it from us, and
#: ``maddison_project`` re-exports it.
MADDISON_PROJECT_ATTRIBUTION: str = (
    "Bolt, Jutta and Jan Luiten van Zanden (2024), "
    "'Maddison style estimates of the evolution of the world economy: "
    "A new 2023 update', Journal of Economic Surveys, 1-41. "
    "DOI: 10.1111/joes.12618. Licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_maddison_project_run_manifest` in
#: ``maddison_project_db`` can import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent
    / "catalogs"
    / "maddison_project.csv"
)

#: Raw xlsx file name inside ``data/raw/maddison_project/``.
_RAW_XLSX_NAME: str = "mpd2023.xlsx"

#: Narrow parquet that Stage 2 writes under
#: ``data/processed/maddison_project/``.
_PROCESSED_PARQUET_NAME: str = "maddison_project_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "maddison_project_attribution"
_PARQUET_META_SOURCE_KEY: str = "maddison_project_source_key"

#: The xlsx sheet name the Stage 2 reader opens. The Maddison 2023
#: release's workbook has 7 sheets (``Notes``, ``Sources``,
#: ``GDPpc``, ``Population``, ``Full data``, ``Regional data``,
#: ``Maddison original sources``); the Stage 2 contract reads ONLY
#: ``Full data`` (one row per ``(countrycode, year)``, columns
#: ``countrycode``, ``country``, ``region``, ``year``, ``gdppc``,
#: ``pop``). The other sheets are the same data restructured as
#: per-indicator tabs and are not used by the Stage 2 adapter.
MADDISON_PROJECT_SHEET_NAME: str = "Full data"

#: The canonical column set the xlsx must carry. The Stage 2 reader
#: validates these columns are present before walking the data
#: rows; the validator raises ``ValueError`` with the missing
#: columns if the live release drifts.
MADDISON_PROJECT_XLSX_COLUMNS: tuple[str, ...] = (
    "countrycode",
    "country",
    "region",
    "year",
    "gdppc",
    "pop",
)

#: Sentinel string for the derived total GDP indicator's
#: ``raw_column``. The Stage 2 reader computes the derived value
#: at runtime; the sentinel cannot collide with a real xlsx column
#: because the xlsx only has 6 columns (all listed above).
MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN: str = "__derived_gdp_total__"

#: ``countrycode`` is the ISO3 country key for every country row in
#: the xlsx. The Stage 3 country matcher maps ISO3 -> countries.id
#: (no per-country fuzzing needed because the xlsx is ISO3-clean).
MADDISON_PROJECT_COUNTRY_KEY_COLUMN: str = "countrycode"

#: The "proxy target year" -- callers asking for ``year=2023`` get
#: 2022 data (the latest available), per the CIRIGHTS / UNDP HDI /
#: Leader Survival 1-year-gap pattern. The orchestrator surfaces
#: the mapping in the run manifest.
MADDISON_PROJECT_PROXY_YEAR: int = 2022
MADDISON_PROJECT_PROXY_REQUESTED_YEAR: int = 2023


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the Maddison Project indicator catalog.

    The :class:`IndicatorSpec` shape is reused from the V-Dem / WDI /
    WGI / UCDP / SIPRI / BTI / CIRIGHTS / UNDP HDI / WHO GHO API /
    PTS adapters, with one catalog-level deviation: the catalog
    includes a DERIVED indicator (``maddison_project_gdp_total_2011_intl_derived``)
    whose ``raw_column`` is the sentinel
    ``__derived_gdp_total__``. The Stage 2 read helper recognises the
    sentinel and computes the value at runtime when both ``gdppc`` and
    ``pop`` are non-NULL for the same ``(countrycode, year)``.
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
        ``0`` otherwise (the WGI / V-Dem / BTI / CIRIGHTS convention).
        The constructor converts that to a real bool. Empty / missing
        values in the optional fields become ``""``.
        """
        higher_raw = (row.get("higher_is_better") or "1").strip()
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=(higher_raw == "1"),
            unit=(row.get("unit") or "").strip(),
            description=(row.get("description") or "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the Maddison Project indicator catalog from
    ``catalogs/maddison_project.csv``.

    Mirrors the WGI / BTI / CIRIGHTS / UNDP HDI loader: handles the
    leading ``#`` comment block, drops comment-only lines, validates
    the required column set, and returns one :class:`IndicatorSpec`
    per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"Maddison Project indicator catalog not found: {path}"
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

    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"Maddison Project catalog {path} has no data rows "
            "after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"Maddison Project catalog {path} is missing required "
            f"columns: {sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_xlsx_path() -> Path:
    """Return the conventional Maddison Project xlsx path inside the
    data lake.

    Resolves to
    ``<project_root>/data/raw/maddison_project/mpd2023.xlsx``.
    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/local-data-store.md``); the adapter
    expects the user to have downloaded the xlsx via the project's
    download workflow first.
    """
    path = raw_dir(MADDISON_PROJECT_SOURCE_KEY) / _RAW_XLSX_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"Maddison Project xlsx not found: {path}"
        )
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional Maddison Project narrow parquet path.

    Creates the ``data/processed/maddison_project/`` directory if
    missing.
    """
    processed_dir(MADDISON_PROJECT_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True,
    )
    return (
        processed_dir(MADDISON_PROJECT_SOURCE_KEY)
        / _PROCESSED_PARQUET_NAME
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_maddison_project_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the narrow-format frame as parquet with attribution
    metadata.

    Mirrors :func:`wgi_io.write_wgi_parquet`: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the Maddison
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or MADDISON_PROJECT_ATTRIBUTION,
    )
    return out


def _attach_parquet_metadata(
    parquet_path: Path, *, attribution: str,
) -> None:
    """Attach the Maddison Project attribution + source key to the
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
        meta[_PARQUET_META_SOURCE_KEY] = (
            MADDISON_PROJECT_SOURCE_KEY.encode("utf-8")
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach Maddison Project attribution metadata "
            "to %s: %s. The data parquet is valid; the run manifest "
            "is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "MADDISON_PROJECT_ATTRIBUTION",
    "MADDISON_PROJECT_COUNTRY_KEY_COLUMN",
    "MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN",
    "MADDISON_PROJECT_PROXY_REQUESTED_YEAR",
    "MADDISON_PROJECT_PROXY_YEAR",
    "MADDISON_PROJECT_SHEET_NAME",
    "MADDISON_PROJECT_SOURCE_KEY",
    "MADDISON_PROJECT_XLSX_COLUMNS",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "write_maddison_project_parquet",
]
