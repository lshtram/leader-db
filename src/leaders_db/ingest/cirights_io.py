"""Stage 2 -- CIRI Human Rights Data Project (CIRIGHTS): catalog, paths, parquet.

This module is the I/O half of the CIRIGHTS adapter. It owns:

- :data:`CIRIGHTS_SOURCE_KEY` and :data:`CIRIGHTS_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed. Uses a
  ``category`` field (not ``rating_category``) to match the canonical
  CIRIGHTS catalog header at
  ``src/leaders_db/ingest/catalogs/cirights.csv``.
- :func:`load_indicator_catalog` -- read the catalog CSV.
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`read_cirights` -- the read orchestrator. Opens the
  single-sheet xlsx with ``openpyxl.read_only=True``, narrows to the
  7 catalog columns, pivots long -> wide, and attaches the audit-trail
  attrs (``year_window``, ``_cirights_raw_lookup``).
- :func:`write_cirights_parquet` -- persist the wide frame as parquet
  with the CIRIGHTS attribution attached to the file-level metadata.
- :func:`_attach_parquet_metadata` -- pyarrow-level helper for the
  file-level schema metadata.
- Named constants: source key, attribution block, catalog path, raw
  xlsx name, parquet name, parquet metadata keys, the 7 indicator
  ``raw_column`` -> ``variable_name`` map, the 1-year-gap proxy
  constants, the year window, and the country-name URL-safe helper.

The xlsx read helpers (per-cell coercion, the long-to-wide pivot) live
in :mod:`leaders_db.ingest.cirights_xlsx`. The DB writes (sources
upsert, source_observations write, run manifest) live in
:mod:`leaders_db.ingest.cirights_db`. The pure coercion helpers and
bundle-metadata parsing live in
:mod:`leaders_db.ingest.cirights_db_helpers`. The orchestrator lives
in :mod:`leaders_db.ingest.cirights`.

CIRIGHTS is structurally closer to WGI (one local xlsx, single sheet,
no HTTP layer) than to WDI (per-indicator HTTP) or UCDP (event-level
aggregation). The xlsx is 1.2 MB and fits in memory; the read pattern
is ``openpyxl`` ``read_only=True`` -> single linear pass -> per-cell
coercion (empty -> pd.NA, int stays int) -> 7-indicator wide pivot.

CIRIGHTS-specific data quirks (vs WGI / SIPRI milex):

- Single sheet ``Sheet1`` (vs WGI's 6 per-indicator sheets or SIPRI
  milex's 4 per-indicator sheets). All 7 indicators live in the same
  sheet; the country-year identity is two columns (``country``,
  ``year``).
- Country key is the display name (e.g. ``United States of America``)
  -- NOT ISO3. Stage 3 (country match) resolves display name + COW
  code to ISO3. The Stage 2 source_row_reference uses the country
  display name (URL-safe substitution applied) for now; this is the
  conservative "audit trail locatable" choice.
- Year coverage is 1981-2022 (no 2023). For the prototype target year
  2023, the orchestrator maps to 2022 as proxy and records the
  mapping in the manifest (1-year-gap pattern, same as UNDP HDI and
  Leader Survival).
- Empty cells (openpyxl ``None``) are the missing-data sentinel;
  there is no ``"#N/A"`` or ``"NA"`` string. The wide frame uses
  ``Int64`` nullable dtype; missing cells become ``pd.NA``.
- Scale varies by indicator (0-2, 0-6, 0-8, 0-17); the catalog
  records the raw scale per indicator and the
  ``normalized_scale_target`` (0-10 for all 7) so the Stage 5 score
  module can linear-scale at the right unit.

Constants live here (the lowest-level module that does NOT import
from siblings) so :mod:`cirights_db`, :mod:`cirights_xlsx`, and
:mod:`cirights_db_helpers` can import them from us, and
:mod:`cirights` can re-export them.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir

# ``read_xlsx_to_wide_dataframe`` is imported below in the
# :func:`read_cirights` function (local import) to break the
# circular dependency: ``cirights_xlsx`` imports constants
# from this module, so this module cannot import the
# function at the top level without creating a cycle.

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``cirights_db`` and ``cirights_xlsx`` can import it from us, and
#: ``cirights`` can re-export it.
CIRIGHTS_SOURCE_KEY: str = "cirights"

#: Stable CIRIGHTS attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (cirights entry). This constant
#: must be a substring of that doc; the
#: :func:`test_cirights_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle: ``cirights_db``
#: imports it from us, and ``cirights`` re-exports it. The exact
#: string matches the per-source entry in
#: ``docs/source-attributions.md` §1 ``cirights`` (the Stage 15
#: "Attribution text in reports" line).
CIRIGHTS_ATTRIBUTION: str = (
    "CIRI Human Rights Data Project v3.12.10.24 "
    "(Cingranelli, Richards, and Crepaz 2024)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_cirights_run_manifest` in ``cirights_db`` can import
#: it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "cirights.csv"
)

#: Raw xlsx file name inside ``data/raw/cirights/``.
_RAW_XLSX_NAME: str = "cirights_v3.12.10.24.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/cirights/``.
_PROCESSED_PARQUET_NAME: str = "cirights_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "cirights_attribution"
_PARQUET_META_SOURCE_KEY: str = "cirights_source_key"

#: The earliest and latest data years in the CIRIGHTS v3.12.10.24
#: bundle (verified live 2026-06-18 against the real
#: ``data/raw/cirights/cirights_v3.12.10.24.xlsx``; 7931 data rows,
#: year range 1981-2022, 207 countries).
CIRIGHTS_YEAR_START: int = 1981
CIRIGHTS_YEAR_END: int = 2022

#: The "proxy target year" -- callers asking for ``year=2023`` get
#: 2022 data (the latest available), per docs/workplan.md §"Phase B
#: addendum -- CIRIGHTS user-managed (2026-06-17)" and the
#: source-vetting report §3.8. This is the same 1-year-gap proxy
#: pattern as UNDP HDI and Leader Survival.
CIRIGHTS_PROXY_YEAR: int = 2022
CIRIGHTS_PROXY_REQUESTED_YEAR: int = 2023

#: In-code mirror of the catalog's ``raw_column`` -> xlsx column
#: name map. The catalog CSV is the public source of truth; this
#: dict is the in-code mirror for fast lookup when the read
#: function needs to confirm a column exists. The mapping MUST match
#: the catalog (the drift-guard test
#: ``test_cirights_catalog_raw_columns_match_xlsx_header`` catches
#: any divergence).
_INDICATOR_RAW_COLUMNS: tuple[str, ...] = (
    "Physical Integrity Rights Index",
    "Repression Index",
    "Civil and Political Rights Index",
    "Disappearances",
    "Extrajudicial Killings",
    "Political Imprisonment",
    "Torture",
)

#: Compiled regex used by :func:`safe_country_token` to substitute
#: URL-unsafe characters in country display names for the
#: ``source_row_reference`` audit suffix (e.g. ``"Cote d'Ivoire"``
#: -> ``"Cote_d_Ivoire"``). The substitute character is underscore.
#: The regex matches ASCII-only "unsafe" characters (whitespace,
#: punctuation, control characters); non-ASCII letters are
#: preserved verbatim (e.g. ``Côte`` stays ``Côte``). The
#: ``re.UNICODE`` flag (default in Python 3) means ``\w`` matches
#: Unicode word characters; the negated class ``[^\w]`` therefore
#: preserves non-ASCII letters.
_UNSAFE_RE = re.compile(r"[^\w]+", re.UNICODE)


def safe_country_token(country: str) -> str:
    r"""Substitute URL-unsafe characters in a country name with underscores.

    Used to build the ``source_row_reference`` audit suffix
    (e.g. ``cirights:Cote_d_Ivoire:2022:PhysInt``). The result is a
    single token (no whitespace, no slashes) so the reference is
    safe to embed in CLI output, parquet metadata, and downstream
    SQL filters. Non-ASCII letters are preserved (e.g. ``Côte``
    stays ``Côte``), matching the CIRIGHTS / WGI / UCDP convention
    of preserving display names verbatim.

    Note: the helper uses Python's ``\w`` regex class (with the
    ``re.UNICODE`` flag, the default in Python 3) which matches
    Unicode word characters including non-ASCII letters. So a
    character like ``ô`` in ``Côte`` is preserved.
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
    """One row of the CIRIGHTS indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS :class:`IndicatorSpec` shape, with the same
    difference as UNDP HDI: the catalog field is ``category`` (not
    ``rating_category``) to match the canonical catalog header.
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
        ``0`` otherwise (the V-Dem / WDI / WGI / UCDP / SIPRI milex /
        SIPRI Yearbook Ch.7 / PTS convention). The constructor
        converts that to a real bool. Empty / missing values in
        optional fields become ``""``.
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


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the CIRIGHTS indicator catalog from ``catalogs/cirights.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI loaders: handles the leading ``#``
    comment block, drops comment-only lines, validates the required
    column set, and returns one :class:`IndicatorSpec` per data row
    in file order.

    The required column set is the 8 columns of the CIRIGHTS catalog:
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
            f"CIRIGHTS indicator catalog not found: {path}"
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
            f"CIRIGHTS catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"CIRIGHTS catalog {path} is missing required columns: "
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
    """Return the conventional CIRIGHTS xlsx path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/cirights/cirights_v3.12.10.24.xlsx``.
    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/cirights.md`` §2.3); the
    adapter expects the user to have downloaded the xlsx via the
    project's download workflow first.
    """
    path = raw_dir(CIRIGHTS_SOURCE_KEY) / _RAW_XLSX_NAME
    if not path.is_file():
        raise FileNotFoundError(f"CIRIGHTS xlsx not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional CIRIGHTS narrow parquet path.

    Creates the ``data/processed/cirights/`` directory if missing.
    """
    processed_dir(CIRIGHTS_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(CIRIGHTS_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_cirights(
    xlsx_path: Path | None = None,
    *,
    year: int | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read the CIRIGHTS xlsx and return the wide-format frame.

    The read orchestrator is the single entry point: opens the single
    sheet ``Sheet1`` with ``openpyxl.read_only=True``, narrows to the
    7 catalog ``raw_column`` s, coerces each cell, and pivots to
    wide format (one row per ``(country, year)``, one column per
    catalog ``variable_name``). The wide frame carries
    ``_cirights_raw_lookup`` (pre-coercion cell text) and
    ``year_window`` in ``df.attrs`` for the DB write and the audit
    trail.

    Args:
        xlsx_path: absolute path to the CIRIGHTS xlsx. Default: data-lake path.
        year: filter to a single year. Default: all 42 years present
            in the xlsx (1981-2022).
        catalog_path: override the catalog. Default: checked-in.

    Returns:
        A pandas DataFrame with columns ``country``, ``year``, then
        one column per catalog ``variable_name``. ``year`` is int;
        indicator columns are ``Int64`` (nullable; ``pd.NA`` = missing).
        The wide frame is dense: every ``(country, year)`` row is
        present, even when all 7 indicator cells are missing.

    Raises:
        FileNotFoundError: if the xlsx is missing.
        ValueError: if the sheet name has drifted from ``Sheet1`` or
            a catalog ``raw_column`` is missing from the xlsx header.
    """
    # Local import to break the cycle: cirights_xlsx imports
    # constants from this module.
    from .cirights_xlsx import read_xlsx_to_wide_dataframe

    if xlsx_path is None:
        xlsx_path = default_xlsx_path()
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"CIRIGHTS xlsx not found: {xlsx_path}")
    specs = load_indicator_catalog(catalog_path=catalog_path)
    return read_xlsx_to_wide_dataframe(
        xlsx_path, specs=specs, year=year,
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_cirights_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`wgi_io.write_wgi_parquet` and
    :func:`pts_io.write_pts_parquet`: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the CIRIGHTS
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.

    The wide frame may carry a ``_cirights_raw_lookup`` key in
    ``df.attrs`` (set by :func:`cirights_xlsx.read_xlsx_to_wide_dataframe`)
    that holds the pre-coercion cell text for the
    ``source_observations.raw_value`` audit trail. That attribute is
    not JSON-serializable; we strip it from ``df.attrs`` before the
    parquet write. Callers that need the raw values for a downstream
    DB write should read them off ``df.attrs`` BEFORE calling this
    function.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Strip the non-JSON-serializable raw_lookup from df.attrs before
    # the parquet write; the data columns are unchanged.
    df.attrs = {
        k: v for k, v in (df.attrs or {}).items()
        if k != "_cirights_raw_lookup"
    }
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or CIRIGHTS_ATTRIBUTION,
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the CIRIGHTS attribution + source key to the parquet's
    schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We rewrite
    the parquet in place to add it. Best-effort: if the rewrite fails
    (corrupt file, race, full disk) the parquet remains valid and we
    log a warning. Schema/data errors re-raise so the orchestrator
    can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = CIRIGHTS_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the
        # audit metadata is lost. Log and continue -- the attribution
        # is also carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach CIRIGHTS attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "CIRIGHTS_ATTRIBUTION",
    "CIRIGHTS_PROXY_REQUESTED_YEAR",
    "CIRIGHTS_PROXY_YEAR",
    "CIRIGHTS_SOURCE_KEY",
    "CIRIGHTS_YEAR_END",
    "CIRIGHTS_YEAR_START",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "read_cirights",
    "safe_country_token",
    "write_cirights_parquet",
]
