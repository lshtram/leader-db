"""Stage 2 -- Political Terror Scale (PTS) orchestrator (REQ-SRC-007).

PTS is the **event-count-light, score-heavy** source for the
``domestic_violence`` rating category. It carries an expert-coded
ordinal score (1-5) per country-year from 3 independent coding teams
(Amnesty International, Human Rights Watch, US State Department)
alongside a paired NA_Status provenance flag (0/66/77/88/99). It
complements UCDP's event-level signals (2 indicators) and V-Dem's
repression indicators (3 indicators) for the cross-source comparison
in Stage 12.

The dataset is a single xlsx (``PTS-2025.xlsx``, 572 KB, 10,531
country-year rows x 14 columns, 1 sheet ``PTS-2025``) distributed by
the Political Terror Scale project under free academic use with
attribution. The Stage 2 adapter opens the xlsx with
``openpyxl.read_only=True``, walks the single sheet, applies the
§6 sentinel matrix (NA_Status takes precedence over PTS_X), and
pivots long -> wide. No HTTP layer; the xlsx is staged locally.

The adapter is split across four modules for clarity (each under
the 400-line convention from ``docs/coding-guidelines.md``):

- :mod:`leaders_db.ingest.pts_io` -- catalog, path helpers, parquet
  write. Owns :data:`PTS_ATTRIBUTION`, :data:`PTS_SOURCE_KEY`, the
  catalog loader, the 4 named constants, and the parquet metadata
  attach.
- :mod:`leaders_db.ingest.pts_xlsx` -- xlsx read with the §6
  sentinel matrix and the long-to-wide pivot.
- :mod:`leaders_db.ingest.pts_db` -- source / observation DB writes
  and the run manifest.
- :mod:`leaders_db.ingest.pts` (this) -- public orchestrator, the
  :class:`PtsIngestResult` model, the :func:`attribution` helper, and
  the canonical PTS citation text.

There is no ``pts_http.py`` because PTS has no HTTP layer (the xlsx
is staged locally; the user downloads it via ``curl``).

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/pts.csv`` (the single source of
   truth for which PTS indicators are read).
2. Read the wide-format frame via :func:`pts_io.read_pts`. Open the
   xlsx with ``openpyxl.read_only=True``, walk the single sheet,
   apply the §6 sentinel matrix (4-case precedence rule), pivot
   long -> wide. The wide frame carries ``_pts_raw_lookup`` in
   ``df.attrs`` for the ``source_observations.raw_value`` audit
   trail.
3. Write a narrow ``data/processed/pts/pts_country_year.parquet``
   with the PTS attribution in the file-level metadata.
4. Upsert the PTS source row into the ``sources`` provenance table.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it. ``source_row_reference``
   carries ``"pts:<COW_Code_A>"`` (e.g. ``"pts:USA"``) so Stage 3 can
   resolve it. ``confidence`` is left ``NULL``; Stage 11 fills it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/source-attributions.md``; if the attributions doc is updated,
the same change must be made here in the same commit. The
:func:`test_pts_attribution_matches_attributions_doc` test enforces
that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .pts_db import (
    register_pts_source,
    write_pts_observations,
    write_pts_run_manifest,
)
from .pts_io import (
    PTS_ATTRIBUTION,
    PTS_SOURCE_KEY,
    IndicatorSpec,
    default_processed_parquet_path,
    default_xlsx_path,
    load_indicator_catalog,
    write_pts_parquet,
)
from .pts_xlsx import read_pts

# Re-exports: ``PTS_ATTRIBUTION``, ``PTS_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``pts_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The DB
# helpers (``register_pts_source``, ``write_pts_observations``,
# ``write_pts_run_manifest``) are also re-exported so the test
# builder's tests can call them through the orchestrator module. The
# path helpers and the read orchestrator are re-exported so the
# tests can drive the adapter through the orchestrator module --
# the WGI / WDI / V-Dem / UCDP / SIPRI milex / SIPRI Yearbook Ch.7
# pattern.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class PtsIngestResult(BaseModel):
    """Summary of a single ``ingest_pts`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: :func:`leaders_db.cli.ingest_source`
    reads ``source_id``, ``parquet_path``, ``observation_rows``,
    ``countries``, ``years``, and ``indicators`` to print the
    end-of-run summary. The manifest writer in :mod:`pts_db`
    consumes the same fields. Pydantic v2 models are the standard
    for any payload that crosses a file, CLI, provider, or artifact
    boundary (``docs/coding-guidelines.md`` § Python Standards).

    PTS-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``regions_covered``: a sorted list of the Region codes found
      in the wide frame (e.g. ``["lac", "mena", "sa", "ssa"]``).
      Carried forward from ``df.attrs["regions_covered"]``. The 7
      single-region codes plus the ``'mena, ssa'`` data anomaly are
      preserved verbatim per §6.4. Useful for the audit trail to
      confirm the wide frame's regional coverage.
    - ``year_window``: a ``(start_year, end_year)`` tuple
      representing the min/max year in the wide frame (e.g.
      ``(2022, 2023)`` for a 2-year filtered run, or ``(1976, 2024)``
      for the full unfiltered run). Carried forward from
      ``df.attrs["year_window"]``. Useful for confirming the wide
      frame's temporal coverage.

    These are the PTS-specific equivalents of SIPRI milex's
    ``regions_covered`` / ``country_count`` and SIPRI Yearbook Ch.7's
    ``pdf_pages_total`` / ``snapshot_year``: they capture the
    audit-trail metadata for end-to-end audit.

    Fields: 8 total.
    """

    source_id: int = Field(
        ..., ge=1,
        description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow PTS parquet.",
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description="Number of ``source_observations`` rows written by this run.",
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``COW_Code_A``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted.",
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used.",
    )
    regions_covered: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted list of Region codes found in the wide frame "
            "(preserves the 7 single-region codes plus the "
            "'mena, ssa' anomaly per §6.4)."
        ),
    )
    year_window: tuple[int, int] = Field(
        ...,
        description=(
            "(start_year, end_year) tuple representing the min/max "
            "year in the wide frame."
        ),
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...],
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got {type(one_year).__name__}"
                )
        return value

    @field_validator("regions_covered")
    @classmethod
    def _regions_covered_is_sorted_unique(
        cls, value: list[str],
    ) -> list[str]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "regions_covered must be a sorted list of unique strings"
            )
        return value

    @field_validator("year_window")
    @classmethod
    def _year_window_is_ordered_pair(
        cls, value: tuple[int, int],
    ) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        if value[0] > value[1]:
            raise ValueError("year_window must have start <= end")
        return value

    @property
    def attribution(self) -> str:
        """The PTS attribution text (Always-On Rule #15)."""
        return PTS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the PTS attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches PTS data must include this block
    verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return PTS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_pts(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> PtsIngestResult:
    """Run Stage 2 for PTS end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`pts_io.read_pts`. One
       openpyxl ``read_only=True`` pass; apply the §6 sentinel
       matrix; pivot long -> wide. The wide frame carries the
       ``_pts_raw_lookup`` attr for the ``raw_value`` audit trail.
    3. Write the narrow parquet under ``data/processed/pts/`` and
       attach the PTS attribution to the parquet's file-level
       metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Build the :class:`PtsIngestResult` and write the run manifest.
       The manifest carries ``source_key``, ``status``, and
       ``year_window`` in addition to the standard fields.
    6. Returns a :class:`PtsIngestResult` summary.

    Short-circuit: ``year=`` out of the xlsx's range (1976-2024)
    produces an empty wide DataFrame. The function returns a
    :class:`PtsIngestResult` with empty fields and ``status="no_data"``
    in the manifest; it does NOT raise.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source pts`` and the tests
    call it. The DB session resolves through :func:`session_scope`,
    which honors the ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2023``). Default: all
            years present in the xlsx (1976-2024).
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_pts(
        xlsx_path=xlsx_path, catalog_path=catalog_path, year=year,
    )

    # Surface the source-specific extras from df.attrs before the
    # parquet write strips ``_pts_raw_lookup`` (the audit-trail
    # lookup). The lookup is JSON-serializable (string keys + tuple
    # keys); the parquet writer strips it for cleanliness, but we
    # need to surface ``regions_covered`` and ``year_window`` to the
    # result here.
    regions_covered = list(df.attrs.get("regions_covered", []))
    year_window_tuple: tuple[int, int] = df.attrs.get("year_window", (0, 0))

    parquet = write_pts_parquet(
        df, parquet_path=parquet_path,
    )

    # Short-circuit: if the wide frame is empty (year out of range),
    # skip the DB writes and return an empty PtsIngestResult with a
    # "no_data" manifest. The parquet is still written (empty frame)
    # so downstream stages can detect "this run produced no data"
    # without re-reading the xlsx.
    if df.empty:
        # Register the source row even on short-circuit so the
        # ``sources`` table has a provenance entry for this run.
        # The Pydantic ``source_id`` field requires ``ge=1``; the
        # registered source row always has ``id >= 1`` because the
        # DB assigns a primary key.
        with session_scope() as session:
            source_id = register_pts_source(session)
        empty_result = PtsIngestResult(
            source_id=source_id,
            parquet_path=parquet,
            observation_rows=0,
            countries=0,
            years=(),
            indicators=len(specs),
            regions_covered=[],
            year_window=(0, 0),
        )
        # Write the manifest with status="no_data" so the audit
        # trail records the short-circuit explicitly.
        write_pts_run_manifest(empty_result, catalog_path=catalog_path)
        return empty_result

    with session_scope() as session:
        source_id = register_pts_source(session)
        rows = write_pts_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    result = PtsIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        # ``countries`` is the count of distinct country entities in
        # the wide frame. The design doc says "distinct COW_Code_A",
        # but the xlsx carries 14 entities (African Union, Crimea,
        # etc.) that all share ``COW_Code_A='NA'`` -- these are real
        # entities that Stage 3 will need to disambiguate, NOT
        # duplicates of Namibia. Reporting ``len(df)`` (the wide
        # frame row count) preserves all 14 entities as separate
        # rows for the audit trail; reporting ``nunique()`` would
        # collapse them. The audit-trail interpretation matches the
        # real-data quirk documented in ``docs/architecture/pts.md``
        # §6.4 ("Stage 3 resolves the COW code to ISO3 via the
        # canonical country table").
        countries=len(df) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        regions_covered=regions_covered,
        year_window=year_window_tuple,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_pts_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``PTS_ATTRIBUTION``, ``PTS_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``pts_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The DB
# helpers, path helpers, and read orchestrator are also re-exported
# so the tests can drive the adapter through the orchestrator module.
__all__ = [
    "PTS_ATTRIBUTION",
    "PTS_SOURCE_KEY",
    "IndicatorSpec",
    "PtsIngestResult",
    "attribution",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "ingest_pts",
    "load_indicator_catalog",
    "read_pts",
    "register_pts_source",
    "write_pts_observations",
    "write_pts_parquet",
    "write_pts_run_manifest",
]
