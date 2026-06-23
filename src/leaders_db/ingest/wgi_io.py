"""Stage 2 -- World Bank WGI: indicator catalog, path helpers, parquet write.

This module is the I/O half of the WGI adapter. It owns:

- :data:`WGI_SOURCE_KEY` and :data:`WGI_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  leading ``#`` comment block + comment-only line filtering).
- :func:`default_xlsx_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`write_wgi_parquet` -- persist the wide frame as parquet with
  the WGI attribution attached to the schema metadata.
- :func:`_attach_parquet_metadata` -- pyarrow-level helper for the
  file-level schema metadata.

The xlsx read function lives in :mod:`leaders_db.ingest.wgi_xlsx`. The
DB writes (sources upsert, source_observations write, run manifest,
missing-value coercion) live in :mod:`leaders_db.ingest.wgi_db` and
:mod:`leaders_db.ingest.wgi_db_helpers`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.wgi`.

WGI is structurally closer to V-Dem (one local file, no network) than
to WDI (per-indicator HTTP, JSON cache): there is no ``wgi_http.py``,
only the V-Dem 3-module split. The xlsx is the canonical input; the
WGI HTTP API is left as a fallback for future single-cell queries.

Constants live here (the lowest-level module that does NOT import from
siblings) so :mod:`wgi_db`, :mod:`wgi_xlsx`, and :mod:`wgi_db_helpers`
can import them from us, and :mod:`wgi` can re-export them.
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
#: so ``wgi_db`` can import it from us, and ``wgi`` can re-export it.
WGI_SOURCE_KEY: str = "world_bank_wgi"

#: Stable WGI attribution block. The canonical text lives in
#: ``docs/sources/attributions.md`` (world_bank_wgi section). This
#: constant must be a substring of that doc; the
#: :func:`test_wgi_attribution_matches_attributions_doc` test enforces
#: byte-for-byte consistency. The constant lives here to break the
#: import cycle: ``wgi_db`` imports it from us, and ``wgi`` re-exports
#: it. The year ``2023`` is the World Bank's release year, not the
#: latest data year (the data ends at 2022).
WGI_ATTRIBUTION: str = (
    "World Bank. 2023. Worldwide Governance Indicators. "
    "Washington, D.C.: The World Bank. https://info.worldbank.org/governance/wgi/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_wgi_run_manifest` in ``wgi_db`` can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "wgi.csv"

#: Raw xlsx file name inside ``data/raw/world_bank_wgi/``.
_RAW_XLSX_NAME: str = "wgidataset.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/world_bank_wgi/``.
_PROCESSED_PARQUET_NAME: str = "wgi_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "wgi_attribution"
_PARQUET_META_SOURCE_KEY: str = "wgi_source_key"

#: In-code mirror of the catalog's ``raw_column`` -> xlsx sheet name map.
#: The catalog CSV is the public source of truth; this dict is the
#: in-code mirror for fast lookup when the read function needs to
#: confirm a sheet exists. The mapping MUST match the catalog (the
#: drift-guard test ``test_catalog_sheet_names_match_wgi_release``
#: catches any divergence).
_INDICATOR_SHEET_NAMES: dict[str, str] = {
    "wgi_voice_and_accountability": "VoiceandAccountability",
    "wgi_political_stability": "Political StabilityNoViolence",
    "wgi_government_effectiveness": "GovernmentEffectiveness",
    "wgi_regulatory_quality": "RegulatoryQuality",
    "wgi_rule_of_law": "RuleofLaw",
    "wgi_control_of_corruption": "ControlofCorruption",
}


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the WGI indicator catalog.

    The V-Dem / WDI :class:`IndicatorSpec` shape is reused verbatim: every
    Stage 2 adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct indicators
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
            higher_is_better=row.get("higher_is_better", "1").strip() == "1",
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the WGI indicator catalog from ``catalogs/wgi.csv``.

    Mirrors the V-Dem / WDI loader: handles the leading ``#`` comment
    block, drops comment-only lines, validates the required column set,
    and returns one :class:`IndicatorSpec` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"WGI indicator catalog not found: {path}")

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

    # Read raw lines, drop comment-only lines, then hand the cleaned text
    # to csv.DictReader. Comment-only means: stripped line starts with ``#``
    # or is blank. Inline ``#`` characters inside a data row are preserved
    # (the WGI catalog header may have such characters; the read WGI
    # sheet has them too).
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(f"WGI catalog {path} has no data rows after stripping comments")

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"WGI catalog {path} is missing required columns: {sorted(missing)}"
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
    """Return the conventional WGI xlsx path inside the data lake.

    Resolves to ``<project_root>/data/raw/world_bank_wgi/wgidataset.xlsx``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in ``docs/architecture/wgi.md`` §2.3); the
    adapter expects the user to have downloaded the xlsx via the
    project's download workflow first.
    """
    path = raw_dir(WGI_SOURCE_KEY) / _RAW_XLSX_NAME
    if not path.is_file():
        raise FileNotFoundError(f"WGI xlsx not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional WGI narrow parquet path.

    Creates the ``data/processed/world_bank_wgi/`` directory if missing.
    """
    processed_dir(WGI_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(WGI_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_wgi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and
    :func:`wdi_io.write_wdi_parquet` (and the
    :func:`vdem_io._attach_parquet_metadata` helper): writes the parquet
    via ``df.to_parquet``, then re-writes the file with the WGI
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow fails,
    the data parquet is still valid and a warning is logged.

    Note: the wide frame may carry a ``_wgi_raw_long`` key in
    ``df.attrs`` (set by :func:`wgi_xlsx.read_wgi`) that holds the
    pre-coercion long frame for the ``raw_value`` audit trail. That
    attribute is not JSON-serializable and would break pyarrow's attrs
    serialization, so we strip it from ``df.attrs`` before the parquet
    write. Callers that need the raw values for a downstream DB write
    should read them off ``df.attrs`` BEFORE calling this function.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # pyarrow serializes df.attrs to parquet file-level metadata. The
    # _wgi_raw_long attr holds a DataFrame, which is not JSON
    # serializable, so we strip it from df.attrs before the parquet
    # write. The data columns are unchanged.
    df.attrs = {k: v for k, v in (df.attrs or {}).items() if k != "_wgi_raw_long"}
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or WGI_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the WGI attribution + source key to the parquet's schema metadata.

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
        meta[_PARQUET_META_SOURCE_KEY] = WGI_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the audit
        # metadata is lost. Log and continue -- the attribution is
        # also carried in the run manifest, so the audit trail survives.
        _logger.warning(
            "Failed to attach WGI attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "WGI_ATTRIBUTION",
    "WGI_SOURCE_KEY",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "load_indicator_catalog",
    "write_wgi_parquet",
]
