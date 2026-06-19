"""Stage 2 -- Wikipedia Action API (search + extract): catalog + paths.

This module is the I/O half of the Wikipedia Action API adapter. It
owns:

- :data:`WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY` and
  :data:`WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :func:`default_cache_dir` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`write_wikipedia_search_extract_parquet` -- persist the long
  frame as parquet with the Wikipedia attribution attached to the
  schema metadata.

The HTTP + Action API endpoint layer lives in
:mod:`leaders_db.ingest.wikipedia_search_extract_http`. The Action API
response parser lives in
:mod:`leaders_db.ingest.wikipedia_search_extract_parse`. The DB-side
functions live in
:mod:`leaders_db.ingest.wikipedia_search_extract_db`. The orchestrator
that ties everything together lives in
:mod:`leaders_db.ingest.wikipedia_search_extract`.

The Stage 2 contract:

- Wikipedia Action API endpoint: ``https://en.wikipedia.org/w/api.php``
  (no auth, public, English Wikipedia). Other language wikis use the
  same path with a different host; the orchestrator's ``base_url``
  parameter lets a caller override.
- Required HTTP header: descriptive ``User-Agent`` per the Wikimedia
  User-Agent policy
  (https://meta.wikimedia.org/wiki/User-Agent_policy).
- The Action API supports many actions; the prototype's catalog
  covers two:
  - ``extracts`` (action=query&prop=extracts&exintro=1&explaintext=1&titles=...)
    -- the article lead / intro paragraph for a given title.
  - ``search`` (action=query&list=search&srsearch=...) -- a search
    hit list for a given query.
- The verbatim Action API response is cached at
  ``data/raw/wikipedia_search_extract/cache/<cache_key>.json`` so a
  re-run with the same input parameters makes zero HTTP calls.
- ``country_id`` and ``leader_id`` are intentionally NULL at Stage 2:
  the helper does not resolve country or leader from the response
  (that decision is downstream Stage 4 / Stage 15).

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`wikipedia_search_extract.attribution` is the exact wording
from ``docs/source-attributions.md``; the
:func:`test_wikipedia_search_extract_attribution_matches_attributions_doc`
test enforces byte-for-byte consistency.

Helper-blocked / needs downstream inputs (per the user's Stage 2
contract):

The Action API helper needs explicit input terms to query; the
adapter does NOT browse, score, or do leader resolution. The
orchestrator's ``queries`` parameter is the deterministic input
interface. Stage 3 / Stage 4 use the persisted observations as the
input to their own leader resolution.
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
#: so ``wikipedia_search_extract_db`` can import it from us, and the
#: orchestrator module can re-export it.
WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY: str = "wikipedia_search_extract"

#: Stable Wikipedia attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (wikipedia_search_extract section,
#: lines 130-136 + the citation-cheat-sheet summary table row).
#: This constant must be a substring of that doc; the
#: :func:`test_wikipedia_search_extract_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15).
#:
#: The attribution is the exact required text:
#: ``"Wikipedia (CC BY-SA 4.0)."`` per the source-attributions doc.
WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION: str = "Wikipedia (CC BY-SA 4.0)."

#: Default location of the indicator catalog. Lives here so
#: :func:`write_wikipedia_search_extract_run_manifest` in
#: ``wikipedia_search_extract_db`` can import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent
    / "catalogs"
    / "wikipedia_search_extract.csv"
)

#: Narrow parquet that Stage 2 writes under
#: ``data/processed/wikipedia_search_extract/``.
_PROCESSED_PARQUET_NAME: str = (
    "wikipedia_search_extract_observations.parquet"
)

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "wikipedia_attribution"
_PARQUET_META_SOURCE_KEY: str = "wikipedia_source_key"


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the Wikipedia search-extract catalog.

    Mirrors the V-Dem / WDI / WHO GHO API :class:`IndicatorSpec`
    shape. ``raw_column`` is the API action name (``"extracts"`` or
    ``"search"``); the orchestrator picks the action + parameters
    from this field plus the caller's ``queries`` list.
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
        better" and ``0`` otherwise (the V-Dem / WDI / WHO GHO API
        convention). The constructor normalizes both string and bool
        values to a real ``bool``. Empty / missing values in the
        optional fields become ``""``.
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
    """Load the Wikipedia search-extract catalog from its CSV.

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
            f"Wikipedia search-extract catalog not found: {path}"
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
            f"Wikipedia search-extract catalog {path} has no data rows "
            "after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"Wikipedia search-extract catalog {path} is missing "
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
    """Return the conventional Wikipedia Action API JSON cache root.

    Layout: ``<project_root>/data/raw/wikipedia_search_extract/cache/``.
    The cache is flat (no per-year subdirectory) because the API
    response is parameterised by (action, query) and the cache key
    encodes the full parameter set. Per-action sub-folders would only
    complicate the cache invalidation logic. Creates the cache root
    directory if missing so a caller can write into it without an
    extra ``mkdir`` call.
    """
    cache = raw_dir(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def default_processed_parquet_path() -> Path:
    """Return the conventional Wikipedia narrow parquet path.

    Creates the ``data/processed/wikipedia_search_extract/`` directory
    if missing.
    """
    processed_dir(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True
    )
    return (
        processed_dir(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY)
        / _PROCESSED_PARQUET_NAME
    )


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_wikipedia_search_extract_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the long-format frame as parquet with attribution metadata.

    Mirrors the WHO GHO API / WDI / Wikidata pattern: writes the
    parquet via ``df.to_parquet``, then re-writes the file with the
    Wikipedia attribution + source key attached as file-level schema
    metadata (Rule #15). Best-effort on the metadata rewrite -- if
    pyarrow fails, the data parquet is still valid and a warning is
    logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out,
        attribution=(
            attribution or WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION
        ),
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the Wikipedia attribution + source key to parquet schema metadata."""
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = (
            WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY.encode("utf-8")
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach Wikipedia attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit "
            "fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION",
    "WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY",
    "IndicatorSpec",
    "default_cache_dir",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "write_wikipedia_search_extract_parquet",
]
