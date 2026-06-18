"""Stage 2 — V-Dem (Varieties of Democracy) orchestrator (REQ-SRC-002, REQ-SRC-008, REQ-SRC-005).

V-Dem is the canonical academic source for political-freedom, governance,
corruption, and repression indicators. The dataset is large (~30k
country-year rows per version, 4618 columns) and released annually under
a free academic license.

The adapter is split across three modules for clarity (each under the
400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.vdem_io`     -- catalog, CSV read, parquet write.
- :mod:`leaders_db.ingest.vdem_db`     -- source/observation DB writes,
                                          run manifest, missing-value
                                          coercion.
- :mod:`leaders_db.ingest.vdem` (this) -- public orchestrator, the
                                          ``IngestResult`` model, the
                                          ``attribution()`` helper, and
                                          the canonical V-Dem citation
                                          text.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/vdem.csv`` (the single source of
   truth for which V-Dem columns are read).
2. Read the wide V-Dem CSV from ``data/raw/vdem/`` and narrow it to
   the catalog columns + the four identity columns
   (``country_name``, ``country_text_id``, ``vdem_country_id``,
   ``year``).
3. Optionally filter to a single year (Stage 5 may pull a wider range).
4. Write a narrow ``data/processed/vdem/vdem_country_year.parquet``
   with the V-Dem attribution in the file-level metadata.
5. Upsert the V-Dem source row into the ``sources`` provenance table.
6. Write one ``source_observations`` row per (country, year, variable)
   triple. ``country_id`` is left ``NULL`` — Stage 3 (country match)
   fills it in later. ``source_row_reference`` carries the V-Dem
   ``country_text_id`` (COW code) so Stage 3 can resolve it.
7. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s).

Per Rule #15, the attribution text returned by :func:`attribution` is
the exact wording from ``docs/source-attributions.md``; if the
attributions doc is updated, the same change must be made here in the
same commit. The :func:`test_vdem_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .vdem_db import (
    register_vdem_source,
    write_run_manifest,
    write_vdem_observations,
)
from .vdem_io import (
    VDEM_ATTRIBUTION,
    VDEM_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    read_vdem_csv,
    write_vdem_parquet,
)

# Re-exports: ``VDEM_ATTRIBUTION``, ``VDEM_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``vdem_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class IngestResult(BaseModel):
    """Summary of a single ``ingest_vdem`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads
    ``source_id``, ``parquet_path``, ``observation_rows``, ``countries``,
    ``years``, and ``indicators`` to print the end-of-run summary. The
    manifest writer in :mod:`vdem_db` also consumes the same fields.
    Pydantic v2 models are the standard for any payload that crosses
    a file, CLI, provider, or artifact boundary
    (:file:`docs/coding-guidelines.md` § Python Standards).
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow V-Dem parquet.")
    observation_rows: int = Field(
        ...,
        ge=0,
        description="Number of ``source_observations`` rows written by this run.",
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``vdem_country_id``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(..., description="Years included in the run, sorted.")
    indicators: int = Field(..., ge=0, description="Number of catalog indicators used.")

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for year in value:
            if not isinstance(year, int):
                raise ValueError(f"years must contain ints, got {type(year).__name__}")
        return value

    @property
    def attribution(self) -> str:
        """The V-Dem attribution text (always-on Rule #15)."""
        return VDEM_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the V-Dem attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-run
    echo) that touches V-Dem data must include this block verbatim. The
    exact wording is the one in ``docs/source-attributions.md``; do not
    paraphrase.
    """
    return VDEM_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_vdem(
    *,
    year: int | None = None,
    csv_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> IngestResult:
    """Run Stage 2 for V-Dem end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide CSV and narrow to catalog columns. Optionally filter
       to a single year.
    3. Write the narrow parquet under ``data/processed/vdem/`` and attach
       the V-Dem attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort — it is the
       audit trail for ``processed/``).
    6. Returns an :class:`IngestResult` summary.

    The function is the single public entry point - both the CLI command
    ``leaders-db ingest-source --source vdem`` and the tests call it.

    Args:
        year: filter to a single year (e.g. ``2023``). Default: all years.
        csv_path: override the input CSV. Default: ``data/raw/vdem/...v16.csv``.
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
    df = read_vdem_csv(csv_path=csv_path, year=year, catalog_path=catalog_path)
    parquet = write_vdem_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_vdem_source(session)
        rows = write_vdem_observations(session, source_id, df, catalog_path=catalog_path)

    result = IngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country_text_id"].nunique()),
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
    )
    # Audit trail: write the run manifest every time (not best-effort).
    # Rule #15 makes the attribution normative; the manifest is how
    # downstream stages find it without re-reading the parquet metadata.
    write_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``VDEM_ATTRIBUTION``, ``VDEM_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``vdem_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface.
__all__ = [
    "VDEM_ATTRIBUTION",
    "VDEM_SOURCE_KEY",
    "IndicatorSpec",
    "IngestResult",
    "attribution",
    "ingest_vdem",
]
