"""Stage 2 -- Bertelsmann BTI: indicator catalog, path helpers, parquet write.

This module is the I/O half of the BTI adapter. It owns:

- :data:`BTI_SOURCE_KEY` and :data:`BTI_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :data:`_BTI_EDITION_YEARS` -- the mapping from a BTI edition name
  (e.g. ``"BTI 2024"``) to the canonical target year the edition
  represents (e.g. ``2023``). The mapping is conservative: every
  edition covers the two years preceding its publication year
  (verified in ``data/raw/bti/metadata.json`` for BTI 2024 -> 2022-2023;
  the same pattern holds for the other editions).
- :data:`_BTI_EDITION_COVERED_INTERVAL` -- per-edition
  ``(start_year, end_year)`` tuple recording the ~2-year coverage
  window the edition represents. Written into the run manifest for
  audit; never used in scoring.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  leading ``#`` comment block + comment-only line filtering).
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`sheet_for_year` -- resolve the BTI edition sheet name for a
  given target year. Returns the closest BTI edition whose covered
  interval contains the year.
- :func:`write_bti_parquet` -- persist the wide frame as parquet with
  the BTI attribution attached to the schema metadata.

The xlsx read function lives in :mod:`leaders_db.ingest.bti_xlsx`. The
DB writes (sources upsert, source_observations write, run manifest,
missing-value coercion) live in :mod:`leaders_db.ingest.bti_db` and
:mod:`leaders_db.ingest.bti_db_helpers`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.bti`.

BTI is structurally closer to WGI and SIPRI milex (one local file,
no network) than to WDI (per-indicator HTTP, JSON cache). The
cumulative xlsx is the canonical input; there is no
``bti_http.py``. The 12-sheet structure (one BTI edition per sheet)
is read with a single openpyxl pass per requested year.

Constants live here (the lowest-level module that does NOT import from
siblings) so :mod:`bti_db`, :mod:`bti_xlsx`, and :mod:`bti_db_helpers`
can import them from us, and :mod:`bti` can re-export them.
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
#: so ``bti_db`` can import it from us, and ``bti`` can re-export it.
BTI_SOURCE_KEY: str = "bti"

#: Stable BTI attribution block. The canonical text lives in
#: ``docs/sources/attributions.md`` (bti section); this constant must
#: be byte-identical to the "Attribution text in reports" line there
#: (the short form, NOT the full citation). The
#: :func:`test_bti_attribution_matches_attributions_doc` test enforces
#: byte-for-byte consistency. The constant lives here to break the
#: import cycle: ``bti_db`` imports it from us, and ``bti`` re-exports
#: it.
BTI_ATTRIBUTION: str = "BTI 2026 (Bertelsmann Stiftung 2026)."

#: Default location of the indicator catalog. Lives here so
#: :func:`write_bti_run_manifest` in ``bti_db`` can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "bti.csv"

#: Raw xlsx file name inside ``data/raw/bti/``.
_RAW_XLSX_NAME: str = "BTI_2006-2026_Scores.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/bti/``.
_PROCESSED_PARQUET_NAME: str = "bti_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "bti_attribution"
_PARQUET_META_SOURCE_KEY: str = "bti_source_key"

#: Per-edition mapping: BTI edition label -> canonical target year the
#: edition represents. Conservative convention: every edition covers
#: the 2 years preceding its publication year, so the canonical
#: "target year" the data is best suited for is ``YYYY - 1``. This
#: matches the source-vetting report and the metadata.json: BTI 2024
#: (covers 2022-2023) -> target year 2023.
_BTI_EDITION_YEARS: dict[str, int] = {
    "BTI 2026": 2025,
    "BTI 2024": 2023,
    "BTI 2022": 2021,
    "BTI 2020": 2019,
    "BTI 2018": 2017,
    "BTI 2016": 2015,
    "BTI 2014": 2013,
    "BTI 2012": 2011,
    "BTI 2010": 2009,
    "BTI 2008": 2007,
    "BTI 2006": 2005,
    # BTI 2006_old uses a different (pre-2006) methodology; target
    # year 2003 to avoid the methodology switch.
    "BTI 2006_old": 2003,
}

#: Per-edition covered interval: (start_year, end_year). The data in
#: each BTI edition covers this ~2-year window preceding the
#: publication year. Used by the run manifest for audit, and by the
#: ``_sheet_interval_for_target_year`` helper to find the closest
#: edition for a target year.
_BTI_EDITION_COVERED_INTERVAL: dict[str, tuple[int, int]] = {
    "BTI 2026": (2024, 2025),
    "BTI 2024": (2022, 2023),
    "BTI 2022": (2020, 2021),
    "BTI 2020": (2018, 2019),
    "BTI 2018": (2016, 2017),
    "BTI 2016": (2014, 2015),
    "BTI 2014": (2012, 2013),
    "BTI 2012": (2010, 2011),
    "BTI 2010": (2008, 2009),
    "BTI 2008": (2006, 2007),
    "BTI 2006": (2004, 2005),
    # BTI 2006_old pre-dates the 2006 methodology refresh.
    "BTI 2006_old": (2002, 2003),
}


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the BTI indicator catalog.

    The :class:`IndicatorSpec` shape is reused from the V-Dem / WGI /
    PTS / SIPRI adapters, with one deviation: the catalog CSV uses the
    column name ``category`` (per the Stage 2 deliverable spec) rather
    than ``rating_category``. The dataclass field is named
    ``category`` to match the CSV header; the Stage 5 score modules
    consume this as the per-indicator rating category.
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
        ``0`` otherwise (the WGI / V-Dem / PTS convention). The
        constructor converts that to a real bool. Empty / missing
        values in the optional fields become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            category=row["category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=row.get("higher_is_better", "1").strip() == "1",
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the BTI indicator catalog from ``catalogs/bti.csv``.

    Mirrors the WGI / SIPRI / V-Dem loader: handles the leading ``#``
    comment block, drops comment-only lines, validates the required
    column set, and returns one :class:`IndicatorSpec` per data row in
    file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"BTI indicator catalog not found: {path}")

    required = {
        "variable_name",
        "raw_column",
        "category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
        "unit",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned text
    # to csv.DictReader. Comment-only means: stripped line starts with ``#``
    # or is blank. Inline ``#`` characters inside a data row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(f"BTI catalog {path} has no data rows after stripping comments")

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"BTI catalog {path} is missing required columns: {sorted(missing)}"
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
    """Return the conventional BTI xlsx path inside the data lake.

    Resolves to ``<project_root>/data/raw/bti/BTI_2006-2026_Scores.xlsx``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in ``docs/architecture/local-data-store.md``); the adapter
    expects the user to have placed the cumulative xlsx via the
    project's download workflow first.
    """
    path = raw_dir(BTI_SOURCE_KEY) / _RAW_XLSX_NAME
    if not path.is_file():
        raise FileNotFoundError(f"BTI xlsx not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional BTI narrow parquet path.

    Creates the ``data/processed/bti/`` directory if missing.
    """
    processed_dir(BTI_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(BTI_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Sheet-to-year mapping
# ---------------------------------------------------------------------------


def sheet_for_year(year: int) -> str:
    """Return the BTI edition sheet name whose covered interval contains ``year``.

    Iterates the per-edition ``(start, end)`` intervals and returns the
    first one whose window contains the requested target year. If no
    edition covers the year, raises :class:`ValueError` so the
    orchestrator can surface a useful error to the caller.

    Raises:
        ValueError: if no BTI edition covers the requested target year.
    """
    for sheet, (start, end) in _BTI_EDITION_COVERED_INTERVAL.items():
        if start <= year <= end:
            return sheet
    raise ValueError(
        f"No BTI edition covers target year {year}. "
        f"Covered intervals: {_BTI_EDITION_COVERED_INTERVAL}"
    )


def covered_interval_for_sheet(sheet_name: str) -> tuple[int, int] | None:
    """Return the (start, end) covered interval for a BTI sheet, or None.

    Used by the orchestrator to record proxy/source-edition semantics
    in the run manifest. Returns ``None`` for an unrecognized sheet
    name (defensive fix for a future BTI release).
    """
    return _BTI_EDITION_COVERED_INTERVAL.get(sheet_name)


def target_year_for_sheet(sheet_name: str) -> int | None:
    """Return the canonical target year for a BTI sheet, or None.

    Returns ``None`` for an unrecognized sheet name (defensive fix).
    The target year is the in-coverage year that best matches the
    edition's publication year minus 1 convention.
    """
    return _BTI_EDITION_YEARS.get(sheet_name)


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_bti_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`wgi_io.write_wgi_parquet`: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the BTI attribution
    + source key attached as file-level schema metadata (Rule #15).
    Best-effort on the metadata rewrite -- if pyarrow fails, the data
    parquet is still valid and a warning is logged.

    The wide frame may carry ``_bti_raw_long`` (set by
    :func:`bti_xlsx.read_bti`) that holds the pre-coercion long frame
    for the ``raw_value`` audit trail. That attribute is not
    JSON-serializable and would break pyarrow's attrs serialization,
    so it is stripped from ``df.attrs`` before the parquet write.
    Callers that need the raw values for a downstream DB write should
    read them off ``df.attrs`` BEFORE calling this function.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # pyarrow serializes df.attrs to parquet file-level metadata. The
    # _bti_raw_long attr holds a DataFrame, which is not JSON
    # serializable, so we strip it from df.attrs before the parquet
    # write. The data columns are unchanged.
    df.attrs = {k: v for k, v in (df.attrs or {}).items() if k != "_bti_raw_long"}
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or BTI_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the BTI attribution + source key to the parquet's schema metadata.

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
        meta[_PARQUET_META_SOURCE_KEY] = BTI_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the audit
        # metadata is lost. Log and continue -- the attribution is
        # also carried in the run manifest, so the audit trail survives.
        _logger.warning(
            "Failed to attach BTI attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "BTI_ATTRIBUTION",
    "BTI_SOURCE_KEY",
    "IndicatorSpec",
    "covered_interval_for_sheet",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "sheet_for_year",
    "target_year_for_sheet",
    "write_bti_parquet",
]
