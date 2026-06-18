"""Stage 2 -- UNDP HDI: indicator catalog and path helpers.

This module is the I/O half of the UNDP HDI adapter. It owns:

- :data:`UNDP_HDI_SOURCE_KEY` and :data:`UNDP_HDI_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the
  orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed. Uses a
  ``category`` field (not ``rating_category``) to match the canonical
  UNDP HDI catalog header in
  ``src/leaders_db/ingest/catalogs/undp_hdi.csv``.
- :func:`load_undp_hdi_catalog` -- read the catalog CSV.
- :func:`default_csv_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- Named constants: source key, encoding, static column set, expected
  prefixes, region codes, HDI code values, year window.

The CSV read + wide-to-long narrow-frame construction lives in
:mod:`leaders_db.ingest.undp_hdi_csv`. The DB writes (sources
upsert, source_observations write, run manifest) live in
:mod:`leaders_db.ingest.undp_hdi_db`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.undp_hdi`.

UNDP HDI is structurally distinct from every prior Stage 2 adapter:

- It is the first wide-format CSV (1,076 columns, 207 countries,
  one row per country) and the only one that needs a wide-to-long
  ``pd.melt`` to produce Stage 2 observations.
- It is the first adapter that reads ``latin-1`` (UTF-8 fails on
  country names with diacritics such as ``Côte d'Ivoire``).
- It targets the ``social_wellbeing`` rating category exclusively
  (5 in-scope indicators).
- It uses a 1-year-gap proxy: target year 2023 maps to data year
  2022 per the CIRIGHTS / Leader Survival pattern.

There is no ``undp_hdi_http.py`` because the adapter reads a
staged local CSV (no HTTP layer; the user downloads the file via
the project's download workflow first).
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
#: so ``undp_hdi_db`` and ``undp_hdi_csv`` can import it from us, and
#: ``undp_hdi`` can re-export it.
UNDP_HDI_SOURCE_KEY: str = "undp_hdi"

#: Stable UNDP HDI attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (undp_hdi entry). This constant must
#: be a substring of that doc; the
#: :func:`test_undp_hdi_attribution_matches_attributions_doc` test
#: enforces byte-for-byte consistency (Always-On Rule #15). The
#: constant lives here to break the import cycle: ``undp_hdi_db``
#: imports it from us, and ``undp_hdi`` re-exports it. The version
#: ``2023-24`` is the HDR release year; the data ends at 2022.
UNDP_HDI_ATTRIBUTION: str = (
    "UNDP. 2024. *Human Development Report 2023-2024*. "
    "United Nations Development Programme. https://hdr.undp.org/"
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_undp_hdi_run_manifest` in ``undp_hdi_db`` can import
#: it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "undp_hdi.csv"
)

#: Raw CSV file name inside ``data/raw/undp_hdi/``.
_RAW_CSV_NAME: str = "HDR23-24_Composite_indices_complete_time_series.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/undp_hdi/``.
_PROCESSED_PARQUET_NAME: str = "undp_hdi_country_year.parquet"

#: Source file encoding. UTF-8 fails on country names with diacritics
#: (e.g. ``Côte d'Ivoire``, ``São Tomé``); latin-1 is the canonical
#: encoding per ``docs/architecture/undp_hdi.md`` §2.
UNDP_HDI_ENCODING: str = "latin-1"

#: Static columns preserved from the wide frame (per architecture §2).
#: Used by the reader's schema validation and the UNPIVOT's
#: ``id_vars`` list.
UNDP_HDI_STATIC_COLUMNS: tuple[str, ...] = (
    "iso3", "country", "hdicode", "region",
)

#: The 5 in-scope catalog ``raw_column`` prefixes. The CSV reader
#: selects only ``{prefix}_{year}`` columns whose prefix is in this
#: set; year-2022-only rank/metadata columns (e.g.
#: ``hdi_rank_2022``) and other non-social-wellbeing prefixes are
#: dropped during prefix filtering.
UNDP_HDI_IN_SCOPE_PREFIXES: tuple[str, ...] = (
    "hdi", "le", "eys", "mys", "gnipc",
)

#: The 6 known region codes observed in the live HDR 2023-24 file
#: (per architecture §2). The 55 ``region=NaN`` rows in the live
#: bundle (e.g. USA) are preserved with a warning per §6.
UNDP_HDI_REGION_CODES: frozenset[str] = frozenset(
    {"SA", "ECA", "AS", "SSA", "LAC", "EAP"},
)

#: The 4 known HDI code values (per architecture §2). Unknown codes
#: are preserved with a warning per §6.
UNDP_HDI_HDI_CODES: frozenset[str] = frozenset(
    {"Low", "Medium", "High", "Very High"},
)

#: The earliest and latest data years in the HDR 2023-24 bundle.
#: Used for sanity checks and the orchestrator's no-year run.
UNDP_HDI_YEAR_START: int = 1990
UNDP_HDI_YEAR_END: int = 2022

#: The "proxy target year" -- callers asking for ``year=2023`` get
#: 2022 data (the latest available), per architecture §4 + the
#: CIRIGHTS / Leader Survival 1-year-gap pattern.
UNDP_HDI_PROXY_YEAR: int = 2022
UNDP_HDI_PROXY_REQUESTED_YEAR: int = 2023


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the UNDP HDI indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS :class:`IndicatorSpec` shape, with one key difference:
    UNDP HDI uses a ``category`` field (not ``rating_category``) to
    match the canonical catalog header at
    ``src/leaders_db/ingest/catalogs/undp_hdi.csv``. All 5 UNDP HDI
    indicators are in the ``social_wellbeing`` category.

    Every Stage 2 adapter resolves its raw column from this dataclass
    so the score modules in Stage 9-10 can normalize and direct
    indicators consistently across sources.
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
        ``0`` otherwise (the V-Dem / WDI / WGI / UCDP / SIPRI milex /
        SIPRI Yearbook Ch.7 / PTS convention). The constructor converts
        that to a real bool. Empty / missing values in optional
        fields become ``""``.
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
        )


def load_undp_hdi_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the UNDP HDI indicator catalog from ``catalogs/undp_hdi.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS loaders: handles the leading ``#`` comment block, drops
    comment-only lines, validates the required column set, and returns
    one :class:`IndicatorSpec` per data row in file order.

    The required column set is the 7 columns of the UNDP HDI catalog
    (per architecture §3): ``variable_name``, ``raw_column``,
    ``category``, ``higher_is_better``, ``raw_scale``,
    ``normalized_scale_target``, ``unit``. (Other adapters also
    require ``description``; UNDP HDI's catalog does not include
    that column.)

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"UNDP HDI indicator catalog not found: {path}"
        )

    required = {
        "variable_name",
        "raw_column",
        "category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
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
            f"UNDP HDI catalog {path} has no data rows after "
            "stripting comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"UNDP HDI catalog {path} is missing required columns: "
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
    """Return the conventional UNDP HDI CSV path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/undp_hdi/HDR23-24_Composite_indices_complete_time_series.csv``.
    Raises :class:`FileNotFoundError` if the file is missing (per the
    design contract in ``docs/architecture/undp_hdi.md`` §2); the
    adapter expects the user to have downloaded the CSV via the
    project's download workflow first.
    """
    path = raw_dir(UNDP_HDI_SOURCE_KEY) / _RAW_CSV_NAME
    if not path.is_file():
        raise FileNotFoundError(f"UNDP HDI CSV not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional UNDP HDI narrow parquet path.

    Creates the ``data/processed/undp_hdi/`` directory if missing.
    """
    processed_dir(UNDP_HDI_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(UNDP_HDI_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# Re-export the catalog + path-helper surface. The parquet writer lives
# in ``undp_hdi_parquet`` and is re-exported by the orchestrator module.
__all__ = [
    "UNDP_HDI_ATTRIBUTION",
    "UNDP_HDI_ENCODING",
    "UNDP_HDI_HDI_CODES",
    "UNDP_HDI_IN_SCOPE_PREFIXES",
    "UNDP_HDI_REGION_CODES",
    "UNDP_HDI_SOURCE_KEY",
    "UNDP_HDI_STATIC_COLUMNS",
    "IndicatorSpec",
    "default_csv_path",
    "default_processed_parquet_path",
    "load_undp_hdi_catalog",
]
