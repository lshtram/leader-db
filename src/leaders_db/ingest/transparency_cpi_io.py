"""Stage 2 -- Transparency International Corruption Perceptions Index (CPI): catalog + paths.

This module is the I/O half of the Transparency International CPI
adapter. It owns:

- :data:`TRANSPARENCY_CPI_SOURCE_KEY` and
  :data:`TRANSPARENCY_CPI_ATTRIBUTION` -- module-level constants
  consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :func:`default_csv_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`write_transparency_cpi_parquet` -- persist the narrow
  frame as parquet with the Transparency International CPI
  attribution attached to the schema metadata.

The HTTP-specific layer (URL builder, the requests call, the
retry policy, the JSON/CSV cache I/O) lives in
:mod:`transparency_cpi_http`. The CSV parser lives in
:mod:`transparency_cpi_csv` (response-shape -> wide DataFrame).
The DB writes live in :mod:`transparency_cpi_db`. The orchestrator
that ties everything together lives in :mod:`transparency_cpi`.

The Transparency International CPI is the perception-based
integrity sub-signal for the prototype. The raw CSV (via the
OCHA HDX mirror) has columns ``country, iso3, region, year,
score, rank, sources, standardError, lowerCi, upperCi`` -- the
adapter narrows to the ``score`` column for the headline
``cpi_score`` indicator. The publisher is Transparency
International; HDX is the durable CSV mirror (the canonical TI
xlsx download is CDN-gated per the source-vetting report §3.6).

The Stage 2 contract:

- URL pattern:
  ``https://data.humdata.org/dataset/<dataset_uuid>/resource/<resource_uuid>/download/global_cpi_<year>.csv``
- The CSV is plain text, ~8 KB for a single year, ~108 KB for the
  all-years CSV; the per-year CSV is the preferred shape because
  the URL is deterministic per year.
- The HDX download redirects to an S3 bucket with an
  AWS-pre-signed URL; the ``requests`` library follows the 302
  redirect transparently.
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
#: so ``transparency_cpi_db`` can import it from us, and
#: ``transparency_cpi`` can re-export it.
TRANSPARENCY_CPI_SOURCE_KEY: str = "transparency_cpi"

#: Stable Transparency International CPI attribution block. The
#: canonical text lives in ``docs/sources/attributions.md``
#: (transparency_cpi section, lines 81-87 + the citation-cheat-sheet
#: summary table row). This constant must be a substring of that
#: doc; the
#: :func:`test_transparency_cpi_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15).
#: The constant lives here to break the import cycle:
#: ``transparency_cpi_db`` imports it from us, and
#: ``transparency_cpi`` re-exports it.
TRANSPARENCY_CPI_ATTRIBUTION: str = "Transparency International CPI 2023."

#: Default location of the indicator catalog. Lives here so
#: :func:`write_transparency_cpi_run_manifest` in
#: ``transparency_cpi_db`` can import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "transparency_cpi.csv"
)

#: Narrow parquet that Stage 2 writes under
#: ``data/processed/transparency_cpi/``.
_PROCESSED_PARQUET_NAME: str = "transparency_cpi_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "transparency_cpi_attribution"
_PARQUET_META_SOURCE_KEY: str = "transparency_cpi_source_key"


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the Transparency International CPI indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI / WHO GHO API
    :class:`IndicatorSpec` shape. Every Stage 2 adapter resolves
    its raw column from this dataclass so the score modules in
    Stage 9-10 can normalize and direct indicators consistently
    across sources.
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
        SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI / WHO
        GHO API convention). The constructor normalizes both
        string and bool values to a real ``bool``. Empty / missing
        values in the optional fields become ``""``.
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
    """Load the Transparency International CPI indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI / PTS / UNDP HDI /
    WHO GHO API loaders: handles the leading ``#`` comment block,
    drops comment-only lines, validates the required column set,
    and returns one :class:`IndicatorSpec` per data row in file
    order.

    The required column set is the 8 columns of the
    Transparency International CPI catalog:
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
            f"Transparency International CPI indicator catalog not "
            f"found: {path}"
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
    # text to csv.DictReader. Comment-only means: stripped line
    # starts with ``#`` or is blank. Inline ``#`` characters inside
    # a data row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"Transparency International CPI catalog {path} has no "
            "data rows after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"Transparency International CPI catalog {path} is "
            f"missing required columns: {sorted(missing)}"
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


def default_csv_path() -> Path:
    """Return the conventional Transparency International CPI raw CSV path.

    Creates the directory if missing so a caller can write into it
    without an extra ``mkdir`` call. Mirrors the WHO GHO API /
    WDI cache-root pattern.
    """
    raw = raw_dir(TRANSPARENCY_CPI_SOURCE_KEY)
    raw.mkdir(parents=True, exist_ok=True)
    return raw / f"{TRANSPARENCY_CPI_SOURCE_KEY}_2023.csv"


def default_processed_parquet_path() -> Path:
    """Return the conventional Transparency International CPI narrow parquet path.

    Creates the ``data/processed/transparency_cpi/`` directory if
    missing.
    """
    processed_dir(TRANSPARENCY_CPI_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True
    )
    return processed_dir(TRANSPARENCY_CPI_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_transparency_cpi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors the WDI / WHO GHO API / UNDP HDI pattern: writes the
    parquet via ``df.to_parquet``, then re-writes the file with the
    Transparency International CPI attribution + source key
    attached as file-level schema metadata (Rule #15). Best-effort
    on the metadata rewrite -- if pyarrow fails, the data parquet
    is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or TRANSPARENCY_CPI_ATTRIBUTION
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the TI CPI attribution + source key to the parquet schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We
    rewrite the parquet in place to add it. This is best-effort: if
    the rewrite fails (corrupt file, race, full disk) the parquet
    remains valid and we log a warning. Schema/data errors are NOT
    swallowed silently -- they re-raise so the orchestrator can
    decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = (
            TRANSPARENCY_CPI_SOURCE_KEY.encode("utf-8")
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach Transparency International CPI "
            "attribution metadata to %s: %s. The data parquet is "
            "valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "TRANSPARENCY_CPI_ATTRIBUTION",
    "TRANSPARENCY_CPI_SOURCE_KEY",
    "IndicatorSpec",
    "default_csv_path",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "write_transparency_cpi_parquet",
]
