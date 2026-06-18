"""Stage 2 -- Political Terror Scale (PTS): catalog, paths, parquet write.

This module is the I/O half of the PTS adapter. It owns:

- :data:`PTS_SOURCE_KEY` and :data:`PTS_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  leading ``#`` comment block + comment-only line filtering).
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`write_pts_parquet` -- persist the wide frame as parquet with
  the PTS attribution attached to the schema metadata.
- :func:`_attach_parquet_metadata` -- pyarrow-level helper for the
  file-level schema metadata.

The 4-case sentinel matrix and the long-to-wide pivot live in
:mod:`leaders_db.ingest.pts_xlsx` (which imports the catalog loader
from this module). The DB writes (sources upsert,
source_observations write, run manifest) live in
:mod:`leaders_db.ingest.pts_db`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.pts`.

PTS is structurally closer to WGI (one local xlsx, no network, no HTTP
layer) than to WDI (per-indicator HTTP, JSON cache) or UCDP
(event-level aggregation). The xlsx is 572 KB and fits in memory; the
read pattern is ``openpyxl`` ``read_only=True`` → single linear pass →
apply the §6 sentinel matrix → 3-indicator wide pivot. The
NA_Status sentinel-precedence logic is the PTS-specific data quirk
(the only Stage 2 source with this 2-signal sentinel pattern).

Constants live here (the lowest-level module that does NOT import
from siblings) so ``pts_db`` and ``pts_xlsx`` can import them from
us, and ``pts`` can re-export them.
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
#: so ``pts_db`` and ``pts_xlsx`` can import it from us, and ``pts``
#: can re-export it. The data lake folder is ``political_terror_scale``
#: (the human-readable bundle name); the source key is the dispatch
#: key (mirrors the multi-word source key convention from V-Dem /
#: WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7).
PTS_SOURCE_KEY: str = "pts"

#: Stable PTS attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (§1, ``pts`` entry). This constant
#: must be a substring of that doc; the
#: :func:`test_pts_attribution_matches_attributions_doc` test enforces
#: byte-for-byte consistency (Always-On Rule #15). The constant lives
#: here to break the import cycle: ``pts_db`` imports it from us, and
#: ``pts`` re-exports it.
PTS_ATTRIBUTION: str = (
    "Wood, Reed M., Mark Gibney, and others. "
    "*The Political Terror Scale (PTS)*. "
    "https://www.politicalterrorscale.org/"
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_pts_run_manifest` in ``pts_db`` can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "pts.csv"
)

#: Raw xlsx file name inside ``data/raw/political_terror_scale/``.
_RAW_XLSX_NAME: str = "PTS-2025.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/pts/``.
_PROCESSED_PARQUET_NAME: str = "pts_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "pts_attribution"
_PARQUET_META_SOURCE_KEY: str = "pts_source_key"

#: The 3 PTS indicator ``variable_name`` values (canonical). Used in
#: the wide frame's column names; used by the test to assert the wide
#: frame's column shape. Named constant per Constraint #11 (used in
#: 3+ places: the catalog loader, the wide-frame construction, the
#: DB writer).
_PTS_INDICATOR_NAMES: tuple[str, ...] = (
    "pts_amnesty_score",
    "pts_human_rights_watch_score",
    "pts_state_dept_score",
)

#: The 3 PTS xlsx raw column names (case-sensitive, no whitespace).
#: Used by the xlsx reader to identify the indicator columns in the
#: 14-column header. Named constant per Constraint #11 (used in 3+
#: places: the catalog loader's matching, the xlsx reader's column
#: extraction, the drift-guard test).
_PTS_RAW_COLUMNS: tuple[str, ...] = ("PTS_A", "PTS_H", "PTS_S")

#: The 7 single-region codes observed in the live xlsx (Constraint
#: #17; the architect verified live 2026-06-18 against the real
#: ``data/raw/political_terror_scale/PTS-2025.xlsx``). These are the
#: **World Bank country-and-lending-groups** codes (NOT the 6 codes
#: in the original metadata.json, which was an approximation). The
#: ``'mena, ssa'`` data anomaly is NOT in this set; it is preserved
#: verbatim in the wide frame's ``region`` column per §6.4.
_PTS_REGION_CODES: frozenset[str] = frozenset({
    "eap", "eca", "lac", "mena", "na", "sa", "ssa",
})

#: The 5 NA_Status code values (Constraint #18; the architect verified
#: live 2026-06-18 that all 5 codes appear in the real xlsx). A cell
#: is "valid data" iff ``NA_Status_X == 0`` (case 1 in §6.1); all
#: other values drop the indicator per the §6 precedence rule. A
#: defensive check warns if a future xlsx release introduces a new
#: code.
_PTS_NA_STATUS_CODES: frozenset[int] = frozenset({0, 66, 77, 88, 99})

# Public aliases (used by :mod:`pts_xlsx` defensive checks). The
# canonical definitions are the underscored names above; these
# unprefixed aliases make the cross-module import ergonomic without
# changing the established naming convention.
PTS_NA_STATUS_CODES: frozenset[int] = _PTS_NA_STATUS_CODES
PTS_REGION_CODES: frozenset[str] = _PTS_REGION_CODES


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the PTS indicator catalog.

    The V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7
    :class:`IndicatorSpec` shape is reused verbatim: every Stage 2
    adapter resolves its raw column from this dataclass so the score
    modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
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
        ``0`` otherwise (the PTS / V-Dem / WGI / UCDP / SIPRI milex /
        SIPRI Yearbook Ch.7 convention). The constructor converts that
        to a real bool. Empty / missing values in the optional fields
        become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=row.get("higher_is_better", "1").strip() == "1",
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the PTS indicator catalog from ``catalogs/pts.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 loaders: handles the leading ``#`` comment block, drops
    comment-only lines, validates the required column set, and returns
    one :class:`IndicatorSpec` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"PTS indicator catalog not found: {path}")

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
    # with ``#`` or is blank. Inline ``#`` characters inside a data row
    # are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"PTS catalog {path} has no data rows after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"PTS catalog {path} is missing required columns: {sorted(missing)}"
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
    """Return the conventional PTS xlsx path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/political_terror_scale/PTS-2025.xlsx``.
    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/pts.md`` §9.4); the adapter
    expects the user to have downloaded the xlsx via the project's
    download workflow first.
    """
    path = raw_dir(PTS_SOURCE_KEY) / _RAW_XLSX_NAME
    # The data-lake folder is ``political_terror_scale`` (the
    # human-readable bundle name), not ``pts`` (the source key).
    # Resolve both candidates so the helper works regardless of
    # which folder convention the operator used.
    if not path.is_file():
        alt = raw_dir("political_terror_scale") / _RAW_XLSX_NAME
        if alt.is_file():
            return alt
        raise FileNotFoundError(f"PTS xlsx not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional PTS narrow parquet path.

    Creates the ``data/processed/pts/`` directory if missing.
    """
    processed_dir(PTS_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(PTS_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_pts_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`wgi_io.write_wgi_parquet` (and
    :func:`vdem_io.write_vdem_parquet`,
    :func:`sipri_milex_io.write_sipri_milex_parquet`,
    :func:`sipri_yearbook_ch7_io.write_sipri_yearbook_ch7_parquet`):
    writes the parquet via ``df.to_parquet``, then re-writes the file
    with the PTS attribution + source key attached as file-level
    schema metadata (Always-On Rule #15). Best-effort on the metadata
    rewrite -- if pyarrow fails, the data parquet is still valid and
    a warning is logged.

    Note: the wide frame may carry a ``_pts_raw_lookup`` key in
    ``df.attrs`` (set by :func:`pts_xlsx.read_pts_from_dataframe`) that
    holds the pre-coercion raw-cell-text lookup for the
    ``source_observations.raw_value`` audit trail. The lookup dict
    uses Python tuples as keys, which pyarrow's attrs serialization
    cannot handle cleanly; we strip it from ``df.attrs`` before the
    parquet write. Callers that need the raw values for a downstream
    DB write should read them off ``df.attrs`` BEFORE calling this
    function.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # pyarrow serializes df.attrs to parquet file-level metadata. The
    # _pts_raw_lookup attr holds a dict keyed by tuples, which is not
    # JSON serializable, so we strip it from df.attrs before the
    # parquet write. The data columns are unchanged.
    df.attrs = {k: v for k, v in (df.attrs or {}).items() if k != "_pts_raw_lookup"}
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or PTS_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the PTS attribution + source key to the parquet's schema metadata.

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
        meta[_PARQUET_META_SOURCE_KEY] = PTS_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the
        # audit metadata is lost. Log and continue -- the attribution
        # is also carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach PTS attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


# Re-export so callers can use the test seam from pts_io if they
# want; the canonical import path is ``from leaders_db.ingest.pts_xlsx
# import read_pts_from_dataframe``.
__all__ = [
    "PTS_ATTRIBUTION",
    "PTS_SOURCE_KEY",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "write_pts_parquet",
]
