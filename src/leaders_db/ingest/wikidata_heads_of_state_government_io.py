"""Stage 2 -- Wikidata WikiProject Heads of state and government: catalog + paths.

This module is the I/O half of the Wikidata heads-of-state-and-government
adapter. It owns:

- :data:`WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY` and
  :data:`WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed. Same shape as
  V-Dem / WDI / WHO GHO API / etc., with the helper-extension fields
  documented below.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  leading ``#`` comment block + comment-only line filtering).
- :func:`default_cache_dir` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`write_wikidata_heads_of_state_government_parquet` -- persist
  the narrow frame as parquet with the Wikidata attribution attached to
  the schema metadata.

The HTTP + SPARQL endpoint layer lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_http`. The
SPARQL JSON response parser lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_parse`. The
DB-side functions live in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_db`. The
orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government`.

The Stage 2 contract:

- Wikidata SPARQL endpoint:
  ``https://query.wikidata.org/sparql`` (no auth, public).
- Required HTTP header: descriptive ``User-Agent`` per the Wikimedia
  User-Agent policy
  (https://meta.wikimedia.org/wiki/User-Agent_policy).
- Response is SPARQL JSON: ``{"head": {"vars": [...]}, "results":
  {"bindings": [...]}}`` with one binding per (country, person, office,
  statement, start, end) tuple.
- The verbatim SPARQL response is cached at
  ``data/raw/wikidata_heads_of_state_government/cache/<cache_key>.json``
  so a re-run with the same input parameters makes zero HTTP calls.
- ``country_id`` and ``leader_id`` are intentionally NULL at Stage 2:
  the country's Wikidata QID is preserved as part of the audit trail
  (in ``source_row_reference`` + ``raw_value``) and Stage 3 maps the
  QID to our ``countries`` table (ISO3); Stage 4 maps the person QID
  to a canonical ``leaders`` row.

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`wikidata_heads_of_state_government.attribution` is the exact
wording from ``docs/sources/attributions.md``; the
:func:`test_wikidata_heads_of_state_government_attribution_matches_attributions_doc`
test enforces byte-for-byte consistency.
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
#: so ``wikidata_heads_of_state_government_db`` can import it from us,
#: and the orchestrator module can re-export it.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY: str = (
    "wikidata_heads_of_state_government"
)

#: Stable Wikidata attribution block. The canonical text lives in
#: ``docs/sources/attributions.md`` (wikidata_heads_of_state_government
#: section, lines 122-128 + the citation-cheat-sheet summary table
#: row). This constant must be a substring of that doc; the
#: :func:`test_wikidata_heads_of_state_government_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15).
#:
#: The attribution is the exact required text:
#: ``"Wikidata (CC0 1.0)."`` per the source-attributions doc.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION: str = "Wikidata (CC0 1.0)."

#: Default location of the indicator catalog. Lives here so
#: :func:`write_wikidata_heads_of_state_government_run_manifest` in
#: ``wikidata_heads_of_state_government_db`` can import it without a
#: cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent
    / "catalogs"
    / "wikidata_heads_of_state_government.csv"
)

#: Narrow parquet that Stage 2 writes under
#: ``data/processed/wikidata_heads_of_state_government/``.
_PROCESSED_PARQUET_NAME: str = (
    "wikidata_heads_of_state_government_country_year.parquet"
)

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "wikidata_attribution"
_PARQUET_META_SOURCE_KEY: str = "wikidata_source_key"


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the Wikidata heads-of-state-and-government catalog.

    Mirrors the V-Dem / WDI / WHO GHO API :class:`IndicatorSpec` shape.
    ``raw_column`` is the Wikidata office QID (the value node of P39)
    such as ``Q30461`` (head of state) or ``Q22857062`` (head of
    government). The Stage 2 orchestrator builds a SPARQL query per
    office QID and persists the verbatim API response.
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

        The catalog uses ``higher_is_better=1`` for "higher is better"
        and ``0`` otherwise (the V-Dem / WDI / WHO GHO API convention).
        The constructor normalizes both string and bool values to a
        real ``bool``. Empty / missing values in the optional fields
        become ``""``.
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
    """Load the Wikidata heads-of-state catalog from its CSV.

    Mirrors the V-Dem / WDI / WHO GHO API loaders: handles the leading
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
            f"Wikidata heads-of-state catalog not found: {path}"
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
            f"Wikidata heads-of-state catalog {path} has no data rows "
            "after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"Wikidata heads-of-state catalog {path} is missing "
            f"required columns: {sorted(missing)}"
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


def default_cache_dir() -> Path:
    """Return the conventional Wikidata SPARQL JSON cache root.

    Layout: ``<project_root>/data/raw/wikidata_heads_of_state_government/cache/``.
    The cache is flat (no per-year subdirectory) because the SPARQL
    query is parameterised by (office_qid, year, country_qids) and the
    cache key encodes the full parameter set. Per-indicator or
    per-year sub-folders would only complicate the cache invalidation
    logic. Creates the cache root directory if missing so a caller can
    write into it without an extra ``mkdir`` call.
    """
    cache = raw_dir(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def default_processed_parquet_path() -> Path:
    """Return the conventional Wikidata narrow parquet path.

    Creates the ``data/processed/wikidata_heads_of_state_government/``
    directory if missing.
    """
    processed_dir(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True
    )
    return (
        processed_dir(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY)
        / _PROCESSED_PARQUET_NAME
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_wikidata_heads_of_state_government_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the long-format frame as parquet with attribution metadata.

    Mirrors the WHO GHO API / WDI pattern: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the Wikidata
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out,
        attribution=(
            attribution or WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION
        ),
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the Wikidata attribution + source key to parquet schema metadata.

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
            WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY.encode("utf-8")
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the audit
        # metadata is lost. Log and continue -- the attribution is
        # also carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach Wikidata attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit "
            "fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY",
    "IndicatorSpec",
    "default_cache_dir",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "write_wikidata_heads_of_state_government_parquet",
]
