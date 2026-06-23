"""Stage 2 -- FAS Nuclear Notebook: catalog + paths.

This module is the I/O half of the FAS Nuclear Notebook adapter.
It owns:

- :data:`FAS_SOURCE_KEY` and :data:`FAS_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the
  orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :func:`default_html_path` /
  :func:`default_processed_parquet_path` -- the conventional
  data-lake locations.
- :func:`write_fas_parquet` -- persist the narrow frame as
  parquet with the FAS attribution attached to the schema
  metadata.

The HTTP-specific layer (URL builder, the requests call, the
retry policy, the HTML cache I/O) lives in :mod:`fas_http`. The
HTML table parser (response-shape -> wide DataFrame) lives in
:mod:`fas_html`. The DB writes live in :mod:`fas_db`. The
orchestrator that ties everything together lives in :mod:`fas`.

The FAS (Federation of American Scientists) Nuclear Notebook is
the second source for the ``nuclear`` category in the prototype,
complementing the SIPRI Yearbook Ch.7 PDF. The FAS public "Status
of World Nuclear Forces" page
(https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html)
contains a single parseable HTML table with all 9 nuclear-armed
states and 5 numeric columns (Operational Strategic, Operational
Nonstrategic, Reserve/Nondeployed, Military Stockpile, Total
Inventory). The page is updated "continuously" per FAS's promise
but as of probe (2026-06-19) the consolidated snapshot is dated
April 30, 2014. The Stage 2 adapter ingests the snapshot year as
documented in the page's metadata; the snapshot year is recorded
in the run manifest as the freshness stamp.

The Stage 2 contract:

- URL pattern: ``https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html``
- The response is HTML (text/html, no JSON wrapper). The parser
  extracts the single ``<table id="table1">`` element with the
  per-country rows.
- Per-cell sentinels: ``"n.a."`` (not applicable), ``"?"``
  (unknown), ``"<10"`` (less than 10), ``"100-120"`` (range).
  The reader maps each to None / midpoint / etc. and preserves
  the literal in ``raw_value``.
- The TOTAL aggregate row is filtered out (it's the sum across
  the 9 countries, not a country itself).
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

#: Source key used everywhere in the data lake + CLI dispatch.
#: Lives here (the lowest-level module that does NOT import from
#: siblings) so ``fas_db`` can import it from us, and ``fas`` can
#: re-export it.
FAS_SOURCE_KEY: str = "fas"

#: Stable FAS Nuclear Notebook attribution block. The canonical
#: text lives in ``docs/sources/attributions.md`` (fas section,
#: lines 114-120 + the citation-cheat-sheet summary table row).
#: This constant must be a substring of that doc; the
#: :func:`test_fas_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle: ``fas_db``
#: imports it from us, and ``fas`` re-exports it.
FAS_ATTRIBUTION: str = (
    "FAS Nuclear Notebook (Federation of American Scientists)."
)

#: Canonical FAS consolidated status page URL. Recorded in the
#: run manifest for audit.
FAS_STATUS_PAGE_URL: str = (
    "https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html"
)

#: Canonical FAS Nuclear Notebook landing page (for attribution).
FAS_PUBLISHER_URL: str = "https://fas.org/issues/nuclear-weapons/"

#: Default location of the indicator catalog. Lives here so
#: :func:`write_fas_run_manifest` in ``fas_db`` can import it
#: without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "fas.csv"
)

#: Narrow parquet that Stage 2 writes under ``data/processed/fas/``.
_PROCESSED_PARQUET_NAME: str = "fas_country_year.parquet"

#: The default snapshot year recorded in the run manifest when
#: the page metadata doesn't expose one. The actual snapshot year
#: is parsed from the page's ``<meta name="date">`` element at
#: read time; this constant is the safe fallback. The live page
#: has ``Wed, 30 Apr 2014 12:42:33 -0380`` as of probe.
_DEFAULT_SNAPSHOT_YEAR: int = 2014

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "fas_attribution"
_PARQUET_META_SOURCE_KEY: str = "fas_source_key"


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the FAS Nuclear Notebook indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI / WHO GHO API / Transparency
    International CPI :class:`IndicatorSpec` shape. Every Stage 2
    adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct
    indicators consistently across sources.
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

        The catalog uses ``higher_is_better=1`` for "higher is
        better" and ``0`` otherwise (the V-Dem / WDI / WGI / UCDP /
        SIPRI / PTS / UNDP HDI / WHO GHO API / Transparency
        International CPI convention). The constructor normalizes
        both string and bool values to a real ``bool``. Empty /
        missing values in the optional fields become ``""``.
        """
        raw_higher = row.get("higher_is_better", "1")
        if isinstance(raw_higher, bool):
            higher_is_better = raw_higher
        else:
            higher_is_better = (
                str(raw_higher).strip().lower() in {"1", "true", "yes"}
            )
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=higher_is_better,
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the FAS Nuclear Notebook indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI / PTS / UNDP
    HDI / WHO GHO API / Transparency International CPI loaders:
    handles the leading ``#`` comment block, drops comment-only
    lines, validates the required column set, and returns one
    :class:`IndicatorSpec` per data row in file order.

    The required column set is the 8 columns of the FAS catalog:
    ``variable_name``, ``raw_column``, ``rating_category``,
    ``raw_scale``, ``normalized_scale_target``, ``higher_is_better``,
    ``unit``, ``description``.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"FAS Nuclear Notebook indicator catalog not found: {path}"
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

    # Read raw lines, drop comment-only lines, then hand the
    # cleaned text to csv.DictReader.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"FAS catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"FAS catalog {path} is missing required columns: "
            f"{sorted(missing)}"
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


def default_html_path() -> Path:
    """Return the conventional FAS raw HTML cache path.

    Creates the directory if missing so a caller can write into
    it without an extra ``mkdir`` call. Mirrors the WHO GHO API
    / WDI / Transparency International CPI cache-root pattern.
    """
    raw = raw_dir(FAS_SOURCE_KEY)
    raw.mkdir(parents=True, exist_ok=True)
    return raw / f"{FAS_SOURCE_KEY}_status.html"


def default_processed_parquet_path() -> Path:
    """Return the conventional FAS narrow parquet path.

    Creates the ``data/processed/fas/`` directory if missing.
    """
    processed_dir(FAS_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(FAS_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_fas_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors the WDI / WHO GHO API / UNDP HDI / Transparency
    International CPI pattern: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the FAS
    attribution + source key attached as file-level schema
    metadata (Rule #15). Best-effort on the metadata rewrite.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or FAS_ATTRIBUTION
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the FAS attribution + source key to the parquet's schema metadata."""
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = FAS_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach FAS attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the "
            "audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "FAS_ATTRIBUTION",
    "FAS_PUBLISHER_URL",
    "FAS_SOURCE_KEY",
    "FAS_STATUS_PAGE_URL",
    "_DEFAULT_SNAPSHOT_YEAR",
    "IndicatorSpec",
    "default_html_path",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "write_fas_parquet",
]
