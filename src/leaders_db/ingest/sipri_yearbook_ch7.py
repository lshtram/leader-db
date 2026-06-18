"""Stage 2 -- SIPRI Yearbook Ch.7 (World Nuclear Forces) orchestrator (REQ-SRC-002).

SIPRI Yearbook Ch.7 is the **arsenal-counts-based** signal for the
``nuclear`` category in the prototype, complementing the
event-based signals of UCDP and the snapshot-based signals of the
client matrix. The data is a single PDF (YB24 07 WNF.pdf, 97
pages, 717 KB, published 2024) distributed by SIPRI on sipri.org
under a free academic license with attribution. The PDF is the
canonical input; the Stage 2 adapter reads Table 7.1 (the
headline summary table on the first content page) and returns 3
catalog indicators (total_inventory, deployed, retired) for the
9 nuclear-armed states.

The adapter is split across five modules for clarity (each under
the 400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.sipri_yearbook_ch7_io` -- catalog, path
  helpers, parquet write, read orchestrator. Owns
  :data:`SIPRI_YEARBOOK_CH7_ATTRIBUTION`,
  :data:`SIPRI_YEARBOOK_CH7_SOURCE_KEY`, the catalog loader, the
  non-country denylist, the snapshot-year regex, and the parquet
  metadata attach.
- :mod:`leaders_db.ingest.sipri_yearbook_ch7_pdf` -- **new**:
  the PDF read. The thin wrapper around ``pdfplumber`` that opens
  the PDF, finds Table 7.1 on the first content page, and
  returns a list of dicts. Owns the cell-coercion helpers for
  the 3 sentinels (``"-"`` for nil, ``".."`` for
  not-applicable, ``"c. <num> [letter]"`` for the circa
  annotation with a footnote letter).
- :mod:`leaders_db.ingest.sipri_yearbook_ch7_db_helpers` -- pure
  coercion and bundle-metadata helpers (extracted to keep
  :mod:`sipri_yearbook_ch7_db` under the 400-line convention).
- :mod:`leaders_db.ingest.sipri_yearbook_ch7_db` -- source /
  observation DB writes, run manifest.
- :mod:`leaders_db.ingest.sipri_yearbook_ch7` (this) -- public
  orchestrator, the :class:`SipriYearbookCh7IngestResult` model,
  the :func:`attribution` helper, and the canonical SIPRI
  Yearbook Ch.7 citation text.

There is no ``sipri_yearbook_ch7_http.py`` because SIPRI Yearbook
Ch.7 has no HTTP layer (the PDF is staged locally; the user
downloads it via ``curl``). The PDF parser is the new piece vs
the WGI / UCDP / SIPRI milex pattern; everything else is reused.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv`` (the
   single source of truth for which SIPRI Yearbook Ch.7
   indicators are read).
2. Read the wide-format frame via
   :func:`read_sipri_yearbook_ch7`. Open the PDF with
   ``pdfplumber``, find Table 7.1 on the first content page,
   extract the table, filter the aggregate ``Total`` row,
   coerce the 3 sentinels (en-dash, two-dot, ``c. <num>
   [letter]``), strip the footnote letter suffix, and pivot
   long -> wide. The wide frame is 9 country rows x 1 year x 3
   indicator columns for the real YB24 PDF (5 countries x 1 year
   for the test fixture).
3. Write a narrow
   ``data/processed/sipri_yearbook_ch7/sipri_yearbook_ch7_country_year.parquet``
   with the SIPRI Yearbook Ch.7 attribution in the file-level
   metadata.
4. Upsert the SIPRI Yearbook Ch.7 source row into the ``sources``
   provenance table. Keyed by
   ``(source_name='SIPRI Yearbook Chapter 7 (World Nuclear Forces)',
   version='YB2024 (data: January 2024)')``.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it.
   ``source_row_reference`` carries
   ``"sipri_yearbook_ch7:<display_name>"`` so Stage 3 can
   resolve it. ``confidence`` is left ``NULL``; Stage 11 fills
   it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/source-attributions.md`; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_sipri_yearbook_ch7_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte
consistent.

**First PDF-based source in the pipeline.** Every prior Stage 2
adapter reads xlsx / CSV / zip-CSV / API JSON. This is the first
PDF source; the :mod:`sipri_yearbook_ch7_pdf` module is the new
file-format-specific reader.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .sipri_yearbook_ch7_db import (
    register_sipri_yearbook_ch7_source,
    write_sipri_yearbook_ch7_observations,
    write_sipri_yearbook_ch7_run_manifest,
)
from .sipri_yearbook_ch7_io import (
    SIPRI_YEARBOOK_CH7_ATTRIBUTION,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    IndicatorSpec,
    default_pdf_path,
    default_processed_parquet_path,
    load_indicator_catalog,
    read_sipri_yearbook_ch7,
    write_sipri_yearbook_ch7_parquet,
)

# Re-exports: ``SIPRI_YEARBOOK_CH7_ATTRIBUTION``,
# ``SIPRI_YEARBOOK_CH7_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``sipri_yearbook_ch7_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them
# from here. Re-export so the public surface stays in one place.
# The path helpers (``default_pdf_path``,
# ``default_processed_parquet_path``) and the parquet writer
# (``write_sipri_yearbook_ch7_parquet``) are also re-exported so
# the test-builder's tests can call them through the
# orchestrator module -- the WGI / WDI / V-Dem / UCDP / SIPRI
# milex pattern. The DB helpers are also re-exported so the
# tests can drive them through the orchestrator module.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class SipriYearbookCh7IngestResult(BaseModel):
    """Summary of a single ``ingest_sipri_yearbook_ch7`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: :func:`leaders_db.cli.ingest_source`
    reads these fields to print the end-of-run summary, and the
    manifest writer in :mod:`sipri_yearbook_ch7_db` consumes the
    same fields. Same shape as V-Dem's
    :class:`vdem.IngestResult`, WGI's
    :class:`wgi.WGIIngestResult`, UCDP's
    :class:`ucdp.UCDPIngestResult`, and SIPRI milex's
    :class:`sipri_milex.SipriMilexIngestResult` for consistency.

    SIPRI-Yearbook-Ch.7-specific extras vs the WGI
    :class:`WGIIngestResult`:

    - ``pdf_pages_total``: the count of pages in the PDF (97 for
      YB24, 1 for the test fixture). Carried forward from
      ``df.attrs["pdf_pages_total"]``. Useful for the audit
      trail to confirm the PDF is the expected edition (a future
      YB25 PDF would have a different page count).
    - ``snapshot_year``: the Yearbook year parsed from the
      Table 7.1 caption (2024 for YB24, with a 2024 default
      fallback for the test fixture which has no caption).
      Carried forward from ``df.attrs["snapshot_year"]``.
      Useful for confirming the wide frame's ``year`` column
      matches the Yearbook year.

    These are the SIPRI-Yearbook-Ch.7-specific equivalents of
    UCDP's ``events_total`` / ``events_filtered`` and SIPRI
    milex's ``regions_covered`` / ``country_count``: they
    capture "what was filtered out" for end-to-end audit.
    """

    source_id: int = Field(
        ..., ge=1,
        description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ...,
        description="Path to the narrow SIPRI Yearbook Ch.7 parquet.",
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this run."
        ),
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct country names in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted.",
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used.",
    )
    pdf_pages_total: int = Field(
        ..., ge=1,
        description="Count of pages in the SIPRI Yearbook Ch.7 PDF.",
    )
    snapshot_year: int = Field(
        ..., ge=1900,
        description="Yearbook year parsed from the Table 7.1 caption.",
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...],
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "years must be a sorted tuple of unique ints"
            )
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        return value

    @property
    def attribution(self) -> str:
        """The SIPRI Yearbook Ch.7 attribution text (Always-On Rule
        #15).
        """
        return SIPRI_YEARBOOK_CH7_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the SIPRI Yearbook Ch.7 attribution block for public
    output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage
    15 report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches SIPRI Yearbook Ch.7 data must
    include this block verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return SIPRI_YEARBOOK_CH7_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_sipri_yearbook_ch7(
    *,
    year: int | None = None,
    pdf_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> SipriYearbookCh7IngestResult:
    """Run Stage 2 for SIPRI Yearbook Ch.7 end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via
       :func:`read_sipri_yearbook_ch7`. Open the PDF with
       ``pdfplumber``, find Table 7.1 on the first content page,
       extract the table, filter the aggregate ``Total`` row,
       coerce the 3 sentinels (en-dash, two-dot, ``"c. <num>
       [letter]"``), and pivot long -> wide.
    3. Write the narrow parquet under
       ``data/processed/sipri_yearbook_ch7/`` and attach the
       SIPRI Yearbook Ch.7 attribution to the parquet's
       file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`SipriYearbookCh7IngestResult` and write
       the run manifest.
    6. Return the result.

    The function is the single public entry point -- both the
    CLI command ``leaders-db ingest-source --source
    sipri_yearbook_ch7`` and the tests call it. The DB session
    resolves through :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2023``). Default:
            the snapshot year of the PDF (2024 for YB24). The
            function returns the snapshot year only; if a
            different year is passed, the function returns an
            empty DataFrame (no data for that year in the
            Yearbook Ch.7 snapshot).
        pdf_path: override the input PDF. Default: data-lake
            path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_sipri_yearbook_ch7(
        year=year, pdf_path=pdf_path, catalog_path=catalog_path,
    )
    parquet = write_sipri_yearbook_ch7_parquet(
        df, parquet_path=parquet_path,
    )

    with session_scope() as session:
        source_id = register_sipri_yearbook_ch7_source(session)
        rows = write_sipri_yearbook_ch7_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    # Surface the SIPRI-specific extras from df.attrs. The
    # ``pdf_pages_total`` and ``snapshot_year`` are
    # JSON-serializable ints; they survive the parquet write.
    pdf_pages_total = int(df.attrs.get("pdf_pages_total", 1))
    snapshot_year = int(df.attrs.get("snapshot_year", 2024))

    result = SipriYearbookCh7IngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        pdf_pages_total=pdf_pages_total,
        snapshot_year=snapshot_year,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative;
    # the manifest is how downstream stages find it without
    # re-reading the parquet metadata.
    write_sipri_yearbook_ch7_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``SIPRI_YEARBOOK_CH7_ATTRIBUTION``,
# ``SIPRI_YEARBOOK_CH7_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``sipri_yearbook_ch7_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top
# of this file make them importable from the canonical
# orchestrator path; this ``__all__`` documents the full
# public surface. The DB helpers are also re-exported so the
# tests can drive them through the orchestrator module.
__all__ = [
    "SIPRI_YEARBOOK_CH7_ATTRIBUTION",
    "SIPRI_YEARBOOK_CH7_SOURCE_KEY",
    "IndicatorSpec",
    "SipriYearbookCh7IngestResult",
    "attribution",
    "default_pdf_path",
    "default_processed_parquet_path",
    "ingest_sipri_yearbook_ch7",
    "load_indicator_catalog",
    "read_sipri_yearbook_ch7",
    "register_sipri_yearbook_ch7_source",
    "write_sipri_yearbook_ch7_observations",
    "write_sipri_yearbook_ch7_parquet",
    "write_sipri_yearbook_ch7_run_manifest",
]
