"""Stage 2 — World Bank WDI orchestrator (REQ-SRC-002).

WDI is the canonical economic + social well-being source for the
prototype. The dataset is large (~196 real countries x 14 indicators
per year, 1960->present) and released under CC BY 4.0. The WDI v2
API is public, free, and requires no authentication; the adapter
caches the verbatim JSON response per ``(year, indicator)`` so re-runs
skip the network entirely.

The adapter is split across four modules for clarity:

- :mod:`leaders_db.ingest.wdi_http` — WDI v2 HTTP fetch, JSON cache
  I/O, retry policy, response parser. The lowest-level module.
- :mod:`leaders_db.ingest.wdi_io` — catalog, read orchestrator,
  parquet write, parquet metadata attachment. Imports from
  ``wdi_http``.
- :mod:`leaders_db.ingest.wdi_db` — source/observation DB writes,
  run manifest, missing-value coercion.
- :mod:`leaders_db.ingest.wdi` (this) — public orchestrator, the
  :class:`WDIIngestResult` model, the :func:`attribution` helper, and
  the canonical WDI citation text.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/wdi.csv`` (the single source of
   truth for which WDI codes are read).
2. Read the wide-format frame via :func:`read_wdi` — one HTTP call per
   uncached indicator, pivot long → wide, filter aggregate ISO3
   codes, handle ``value: null``.
3. Write a narrow ``data/processed/world_bank_wdi/wdi_country_year.parquet``
   with the WDI attribution in the file-level metadata.
4. Upsert the WDI source row into the ``sources`` provenance table.
5. Write one ``source_observations`` row per
   ``(iso3, year, variable)`` triple. ``country_id`` is left ``NULL``;
   Stage 3 (country match) fills it in. ``source_row_reference``
   carries ``"wdi:<iso3>"`` so Stage 3 can resolve it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution` is
the exact wording from ``docs/sources/attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The :func:`test_wdi_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .wdi_db import (
    register_wdi_source,
    write_wdi_observations,
    write_wdi_run_manifest,
)
from .wdi_io import (
    WDI_ATTRIBUTION,
    WDI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    read_wdi,
    write_wdi_parquet,
)

# Re-exports: ``WDI_ATTRIBUTION``, ``WDI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``wdi_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The DB
# helpers (``register_wdi_source``, ``write_wdi_observations``,
# ``write_wdi_run_manifest``) are also re-exported so the test
# builder's tests can call them through the orchestrator module.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class WDIIngestResult(BaseModel):
    """Summary of a single ``ingest_wdi`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads
    ``source_id``, ``parquet_path``, ``observation_rows``, ``countries``,
    ``years``, and ``indicators`` to print the end-of-run summary. The
    manifest writer in :mod:`wdi_db` also consumes the same fields,
    plus ``indicators_cached`` / ``indicators_fetched`` for the audit
    trail. Pydantic v2 models are the standard for any payload that
    crosses a file, CLI, provider, or artifact boundary
    (:file:`docs/process/coding-guidelines.md` § Python Standards).
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow WDI parquet.")
    observation_rows: int = Field(
        ...,
        ge=0,
        description="Number of ``source_observations`` rows written by this run.",
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``iso3``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(..., description="Years included in the run, sorted.")
    indicators: int = Field(..., ge=0, description="Number of catalog indicators used.")
    indicators_cached: int = Field(
        ...,
        ge=0,
        description=(
            "How many of the catalog indicators were read from the JSON "
            "cache (no HTTP call)."
        ),
    )
    indicators_fetched: int = Field(
        ...,
        ge=0,
        description=(
            "How many of the catalog indicators were HTTP-fetched this run."
        ),
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for year in value:
            if not isinstance(year, int):
                raise ValueError(
                    f"years must contain ints, got {type(year).__name__}"
                )
        return value

    @property
    def attribution(self) -> str:
        """The WDI attribution text (always-on Rule #15)."""
        return WDI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the WDI attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-run
    echo) that touches WDI data must include this block verbatim. The
    exact wording is the one in ``docs/sources/attributions.md``; do not
    paraphrase.
    """
    return WDI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_wdi(
    *,
    year: int | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> WDIIngestResult:
    """Run Stage 2 for WDI end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_wdi`. One HTTP call
       per uncached indicator; cached files are read directly.
    3. Write the narrow parquet under ``data/processed/world_bank_wdi/``
       and attach the WDI attribution to the parquet's file-level
       metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort — it is
       the audit trail for ``processed/``).
    6. Returns a :class:`WDIIngestResult` summary.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source world_bank_wdi`` and
    the tests call it.

    Args:
        year: filter to a single year (e.g. ``2023``).
            Default: all years present in cache.
        parquet_path: override the output parquet. Default: data-lake
            path.
        catalog_path: override the indicator catalog. Default:
            checked-in catalog.
        cache_dir: override the JSON cache root. Default: data-lake
            path.
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the isolated
        test DB set up by the ``isolated_data_lake`` fixture. No
        explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_wdi(
        year=year,
        catalog_path=catalog_path,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )
    parquet = write_wdi_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_wdi_source(session)
        rows = write_wdi_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    # Pull the cached/fetched counts that read_wdi attached to the
    # frame's attrs. Default to 0 if read_wdi did not populate them
    # (e.g. a future caller bypasses the orchestrator and constructs
    # a DataFrame from scratch).
    indicators_cached = int(df.attrs.get("indicators_cached", 0))
    indicators_fetched = int(df.attrs.get("indicators_fetched", 0))

    result = WDIIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["iso3"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_wdi_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``WDI_ATTRIBUTION``, ``WDI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``wdi_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The DB
# helpers are also re-exported so the tests can drive them through
# the orchestrator module (the test builder's test surface is
# ``from leaders_db.ingest import wdi; wdi.register_wdi_source(...)``).
__all__ = [
    "WDI_ATTRIBUTION",
    "WDI_SOURCE_KEY",
    "IndicatorSpec",
    "WDIIngestResult",
    "attribution",
    "ingest_wdi",
    "register_wdi_source",
    "write_wdi_observations",
    "write_wdi_run_manifest",
]
