"""Stage 2 -- World Bank WGI orchestrator (REQ-SRC-002).

WGI is the canonical governance / effectiveness source for the
prototype. The dataset is the World Bank's annual "Worldwide Governance
Indicators" release, a single xlsx (one workbook, 7 sheets, 214
countries x 24 years x 6 indicators). It is distributed under CC BY
4.0 per the World Bank's [Terms of Use for Datasets](
https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets).

The adapter is split across three modules for clarity:

- :mod:`leaders_db.ingest.wgi_io` -- catalog, xlsx read, parquet
  write.
- :mod:`leaders_db.ingest.wgi_db` -- source/observation DB writes,
  run manifest, missing-value coercion.
- :mod:`leaders_db.ingest.wgi` (this) -- public orchestrator, the
  :class:`WGIIngestResult` model, the :func:`attribution` helper, and
  the canonical WGI citation text.

There is no ``wgi_http.py`` because WGI is read from a single local
xlsx (not an HTTP API). The Stage 2 contract: open the xlsx with
``openpyxl.read_only=True``, walk the 6 indicator sheets (one per
WGI dimension), extract the ``Estimate`` cell for each
``(country, year)``, pivot long -> wide. No per-indicator HTTP call,
no pagination, no rate limiting.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/wgi.csv`` (the single source of
   truth for which WGI sheets are read).
2. Read the wide-format frame via :func:`read_wgi` -- one xlsx sheet
   per indicator, long -> wide pivot, ``"#N/A"`` -> NaN coercion.
3. Write a narrow ``data/processed/world_bank_wgi/wgi_country_year.parquet``
   with the WGI attribution in the file-level metadata.
4. Upsert the WGI source row into the ``sources`` provenance table.
5. Write one ``source_observations`` row per ``(iso3, year, variable)``
   triple. ``country_id`` is left ``NULL``; Stage 3 (country match)
   fills it in. ``source_row_reference`` carries ``"wgi:<iso3>"`` so
   Stage 3 can resolve it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution` is
the exact wording from ``docs/source-attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_wgi_attribution_matches_attributions_doc` test enforces
that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .wgi_db import (
    register_wgi_source,
    write_wgi_observations,
    write_wgi_run_manifest,
)
from .wgi_io import (
    WGI_ATTRIBUTION,
    WGI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    write_wgi_parquet,
)
from .wgi_xlsx import read_wgi

# Re-exports: ``WGI_ATTRIBUTION``, ``WGI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``wgi_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The DB
# helpers (``register_wgi_source``, ``write_wgi_observations``,
# ``write_wgi_run_manifest``) are also re-exported so the test
# builder's tests can call them through the orchestrator module.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class WGIIngestResult(BaseModel):
    """Summary of a single ``ingest_wgi`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads
    ``source_id``, ``parquet_path``, ``observation_rows``, ``countries``,
    ``years``, and ``indicators`` to print the end-of-run summary. The
    manifest writer in :mod:`wgi_db` also consumes the same fields.
    Pydantic v2 models are the standard for any payload that crosses
    a file, CLI, provider, or artifact boundary
    (:file:`docs/coding-guidelines.md` § Python Standards).

    Unlike the WDI :class:`wdi.WDIIngestResult`, this model does not
    carry ``indicators_cached`` / ``indicators_fetched`` because WGI
    has no HTTP layer -- the xlsx is the cache, and the read is a
    single local-file read.
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow WGI parquet.")
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

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got {type(one_year).__name__}"
                )
        return value

    @property
    def attribution(self) -> str:
        """The WGI attribution text (Always-On Rule #15)."""
        return WGI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the WGI attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-run
    echo) that touches WGI data must include this block verbatim. The
    exact wording is the one in ``docs/source-attributions.md``; do not
    paraphrase.
    """
    return WGI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_wgi(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> WGIIngestResult:
    """Run Stage 2 for WGI end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_wgi`. One openpyxl
       per-indicator-sheet pass; long -> wide pivot; ``"#N/A"`` ->
       NaN coercion.
    3. Write the narrow parquet under
       ``data/processed/world_bank_wgi/`` and attach the WGI
       attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort -- it is
       the audit trail for ``processed/``).
    6. Returns a :class:`WGIIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source world_bank_wgi`` and
    the tests call it.

    Args:
        year: filter to a single year (e.g. ``2022``).
            Default: all 24 years present in xlsx (1996-2022).
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the isolated
        test DB set up by the ``isolated_data_lake`` fixture. No
        explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_wgi(
        year=year, xlsx_path=xlsx_path, catalog_path=catalog_path,
    )
    parquet = write_wgi_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_wgi_source(session)
        rows = write_wgi_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    result = WGIIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["iso3"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_wgi_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``WGI_ATTRIBUTION``, ``WGI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``wgi_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The DB
# helpers are also re-exported so the tests can drive them through
# the orchestrator module (the test builder's test surface is
# ``from leaders_db.ingest import wgi; wgi.register_wgi_source(...)``).
__all__ = [
    "WGI_ATTRIBUTION",
    "WGI_SOURCE_KEY",
    "IndicatorSpec",
    "WGIIngestResult",
    "attribution",
    "ingest_wgi",
    "register_wgi_source",
    "write_wgi_observations",
    "write_wgi_run_manifest",
]
