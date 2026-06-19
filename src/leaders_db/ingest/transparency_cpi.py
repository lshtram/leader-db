"""Stage 2 -- Transparency International Corruption Perceptions Index (CPI) orchestrator.

Transparency International CPI is the perception-based integrity
sub-signal for the prototype, complementing the aggregate signals
of WGI Control of Corruption and the expert-coded signals of
V-Dem. The CPI is annual, scored 0-100 per country (higher =
cleaner), and the dataset is published by Transparency
International. The direct xlsx download from transparency.org is
CDN-gated per the Phase B source-vetting report §3.6, so the
Stage 2 adapter downloads the canonical CSV from the OCHA HDX
mirror (data.humdata.org), which preserves the verbatim
Transparency International release. The publisher remains
Transparency International; the attribution text in
:data:`TRANSPARENCY_CPI_ATTRIBUTION` is the canonical wording
from ``docs/source-attributions.md``.

The adapter is split across six modules for clarity (each under
the 400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.transparency_cpi_io` -- catalog,
  paths, parquet write, attribution constant.
- :mod:`leaders_db.ingest.transparency_cpi_http` -- HDX URL
  builder, CSV cache I/O, HTTP fetch (one retry on
  ConnectionError / Timeout; no retry on 4xx).
- :mod:`leaders_db.ingest.transparency_cpi_csv` -- HDX CSV
  parser (response-shape -> wide DataFrame).
- :mod:`leaders_db.ingest.transparency_cpi_db_helpers` -- pure
  helpers: value coercion, bundle metadata parser, observation
  row builder.
- :mod:`leaders_db.ingest.transparency_cpi_db` -- source /
  observation DB writes, run manifest.
- :mod:`leaders_db.ingest.transparency_cpi_result` --
  :class:`TransparencyCpiIngestResult`.
- :mod:`leaders_db.ingest.transparency_cpi` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/transparency_cpi.csv`` (the
   single source of truth for which Transparency International
   CPI indicators are read).
2. Read the wide-format frame via
   :func:`read_transparency_cpi_csv` -- one HTTP call per
   uncached year, parsed via
   :func:`transparency_cpi_csv.read_transparency_cpi_csv`.
3. Write a narrow
   ``data/processed/transparency_cpi/transparency_cpi_country_year.parquet``
   with the Transparency International CPI attribution in the
   file-level metadata.
4. Upsert the Transparency International CPI source row into
   the ``sources`` provenance table. Keyed by
   ``(source_name='Transparency International Corruption
   Perceptions Index', version='CPI <year>')``.
5. Write one ``source_observations`` row per
   ``(iso3, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it.
   ``source_row_reference`` carries
   ``"transparency_cpi:<raw_column>:<iso3>"`` so Stage 3 can
   resolve it and the audit trail identifies the source's
   indicator code + ISO3.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/source-attributions.md`; the
:func:`test_transparency_cpi_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte
consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .transparency_cpi_csv import read_transparency_cpi_csv
from .transparency_cpi_db import (
    register_transparency_cpi_source,
    write_transparency_cpi_observations,
    write_transparency_cpi_run_manifest,
)
from .transparency_cpi_http import fetch_transparency_cpi_csv
from .transparency_cpi_io import (
    TRANSPARENCY_CPI_ATTRIBUTION,
    TRANSPARENCY_CPI_SOURCE_KEY,
    IndicatorSpec,
    default_csv_path,
    default_processed_parquet_path,
    load_indicator_catalog,
    write_transparency_cpi_parquet,
)
from .transparency_cpi_result import TransparencyCpiIngestResult

# Re-exports: ``TRANSPARENCY_CPI_ATTRIBUTION``,
# ``TRANSPARENCY_CPI_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``transparency_cpi_io`` (the lowest-level module
# that does NOT import from siblings) to break the import cycle,
# but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The
# path helpers (``default_csv_path``,
# ``default_processed_parquet_path``), the parquet writer
# (``write_transparency_cpi_parquet``), the CSV reader
# (``read_transparency_cpi_csv``), the HTTP fetch helper
# (``fetch_transparency_cpi_csv``), and the DB writers
# (``register_transparency_cpi_source``,
# ``write_transparency_cpi_observations``,
# ``write_transparency_cpi_run_manifest``) are also re-exported
# so the test-builder's tests can call them through the
# orchestrator module -- the WDI / WGI / UCDP / SIPRI milex /
# SIPRI Yearbook Ch.7 / PTS / UNDP HDI / WHO GHO API / CIRIGHTS /
# BTI / RSF pattern.


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the Transparency International CPI attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage
    15 report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches Transparency International CPI
    data must include this block verbatim. The exact wording is
    the one in ``docs/source-attributions.md``; do not
    paraphrase.
    """
    return TRANSPARENCY_CPI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_transparency_cpi(
    *,
    year: int | None = None,
    csv_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> TransparencyCpiIngestResult:
    """Run Stage 2 for the Transparency International CPI end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via
       :func:`read_transparency_cpi_csv`. One HTTP call per
       uncached year (the CSV is fetched from the OCHA HDX
       mirror); cached files are read directly.
    3. Write the narrow parquet under
       ``data/processed/transparency_cpi/`` and attach the
       Transparency International CPI attribution to the
       parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort --
       it is the audit trail for ``processed/``).
    6. Returns a :class:`TransparencyCpiIngestResult` summary.

    The function is the single public entry point -- both the
    CLI command ``leaders-db ingest-source --source
    transparency_cpi`` and the tests call it.

    Args:
        year: filter to a single year (e.g. ``2023``). The
            Transparency International CPI Stage 2 reader is a
            single-year reader; the prototype's CLI always
            passes the resolved
            ``RunConfig.project.target_year`` (2023 by default).
        csv_path: override the per-year CSV path. Default:
            data-lake path (``data/raw/transparency_cpi/``).
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in catalog.
        force_refresh: re-download even when the cache file
            exists.
        request_timeout: per-request HTTP timeout in seconds.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The
        CLI runs against the production DB; tests run against the
        isolated test DB set up by the ``isolated_data_lake``
        fixture. No explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    if year is None:
        raise ValueError(
            "year is required for ingest_transparency_cpi (the "
            "Transparency International CPI Stage 2 reader is a "
            "single-year reader; pass year=int)"
        )
    target_year = int(year)

    # Fetch (cache-first, HTTP-fallback) the per-year CSV. The
    # cache path is the conventional data-lake CSV location.
    cache_csv_path = csv_path or default_csv_path()
    records, came_from_cache = fetch_transparency_cpi_csv(
        target_year,
        cache_path=cache_csv_path,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )

    df = read_transparency_cpi_csv(
        records, year=target_year, cache_path=cache_csv_path
    )
    parquet = write_transparency_cpi_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_transparency_cpi_source(session)
        rows = write_transparency_cpi_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    result = TransparencyCpiIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["iso3"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        csv_cached=came_from_cache,
        csv_fetched=not came_from_cache,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative;
    # the manifest is how downstream stages find it without
    # re-reading the parquet metadata.
    write_transparency_cpi_run_manifest(
        result,
        catalog_path=catalog_path,
        csv_cached=came_from_cache,
        csv_fetched=not came_from_cache,
    )
    return result


# Public surface: ``TRANSPARENCY_CPI_ATTRIBUTION``,
# ``TRANSPARENCY_CPI_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``transparency_cpi_io`` (the lowest-level module)
# to break the import cycle. The re-exports at the top of this
# file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The
# DB helpers are also re-exported so the tests can drive them
# through the orchestrator module.
__all__ = [
    "TRANSPARENCY_CPI_ATTRIBUTION",
    "TRANSPARENCY_CPI_SOURCE_KEY",
    "IndicatorSpec",
    "TransparencyCpiIngestResult",
    "attribution",
    "default_csv_path",
    "default_processed_parquet_path",
    "ingest_transparency_cpi",
    "load_indicator_catalog",
    "read_transparency_cpi_csv",
    "register_transparency_cpi_source",
    "write_transparency_cpi_observations",
    "write_transparency_cpi_parquet",
    "write_transparency_cpi_run_manifest",
]
