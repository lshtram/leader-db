"""Stage 2 -- Penn World Table 10.01 adapter.

This package provides the public surface for the Penn World Table
10.01 Stage 2 adapter:

- :data:`PWT_SOURCE_KEY` -- the canonical ``"pwt"`` source key.
- :data:`PWT_XLSX_NAME` -- the canonical filename ``pwt1001.xlsx``.
- :data:`PWT_METADATA_NAME` -- the canonical bundle metadata file
  ``metadata.json``.
- :data:`PWT_DATA_SHEET_NAME` -- the canonical ``Data`` sheet the
  reader opens (NOT ``Info`` / ``Legend``).
- :data:`PWT_CATALOG_RAW_COLUMNS` -- the 11 catalog numeric
  columns the Stage 2 reader / transform drive.
- :data:`PWT_REQUIRED_IDENTITY_COLUMNS` -- the 4 identity columns
  the reader always validates.
- :data:`PWT_ATTRIBUTION` -- the canonical citation block (Always-
  On Rule #15; byte-identical to ``docs/source-attributions.md``).
- :class:`PWTAdapter` -- the production Stage 2 adapter class
  implementing the shared :class:`SourceAdapter` Protocol
  (:func:`check_ready` -> :func:`read` -> :func:`transform` ->
  :func:`write`).
- :func:`read_pwt` -- the reader module's public function. Opens
  ``pwt1001.xlsx``, validates identity + catalog columns, returns
  the wide ``Data``-sheet-shaped DataFrame.
- :func:`transform_pwt_long_frame` -- the transform module's
  public function. Pivots the wide frame to the canonical long
  format (9 columns: ``iso3``, ``year``, ``variable_name``,
  ``raw_value``, ``numeric_value``, ``raw_column``,
  ``source_row_reference``, ``temporal_kind``, ``attribution``).
- :func:`ingest_pwt` -- the public orchestrator. Drives the full
  pipeline (read -> transform -> write) end-to-end and returns an
  :class:`IngestResult` carrying the canonical PWT summary
  (observation_rows, years, parquet_path, manifest_path,
  warnings, attribution). The CLI ``leaders-db ingest-source
  --source pwt`` and the registry runner both call this.

PWT year semantics
------------------

PWT 10.01 covers 1950-2019 per the canonical citation block in
``docs/source-attributions.md``. Per the source-ingestion-plan PWT
section and requirement §13 ("no invented historical data"), the
adapter emits direct observed source-year rows only -- a request
for ``year=2023`` produces zero observations AND a
``requested_year_out_of_coverage`` manifest warning. No
2019 -> 2023 stale-proxy fill is permitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapter import PWTAdapter
from .reader import read_pwt
from .transform import transform_pwt_long_frame

PWT_SOURCE_KEY: str = "pwt"
PWT_XLSX_NAME: str = "pwt1001.xlsx"
PWT_METADATA_NAME: str = "metadata.json"
PWT_DATA_SHEET_NAME: str = "Data"

# The 11 catalog numeric columns the Stage 2 catalog drives
# (per ``docs/source-ingestion-plan.md`` PWT section, verified
# against the live ``pwt1001.xlsx`` ``Data`` sheet on 2026-06-22).
# Together with the 4 identity columns (countrycode, country,
# currency_unit, year), the reader emits 15 columns total; only
# the 11 catalog columns are cataloged.
PWT_CATALOG_RAW_COLUMNS: tuple[str, ...] = (
    "rgdpe",
    "rgdpo",
    "pop",
    "emp",
    "avh",
    "hc",
    "ccon",
    "cda",
    "ctfp",
    "rkna",
    "rtfpna",
)

PWT_REQUIRED_IDENTITY_COLUMNS: tuple[str, ...] = (
    "countrycode",
    "country",
    "currency_unit",
    "year",
)

# Canonical PWT attribution text (matches the citation block in
# ``docs/source-attributions.md`` §pwt -- Rule #15).
PWT_ATTRIBUTION: str = (
    "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)."
)


def ingest_pwt(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    database_url: str | None = None,
    processed_root: Path | None = None,
) -> Any:
    """Run Stage 2 for the Penn World Table 10.01 end-to-end.

    Steps (each idempotent):

    1. Convert every public override (``xlsx_path``,
       ``parquet_path``, ``catalog_path``, ``database_url``,
       ``processed_root``, ``year``) into the equivalent
       request-scoped field on an :class:`IngestRequest` so the
       adapter reads / writes / persists at the locations the
       caller asked for.
    2. Delegate the full pipeline to
       :meth:`PWTAdapter.ingest` (check_ready -> read ->
       transform -> write) so the convenience path and the
       registry runner share the same code path.
    3. The adapter writes parquet + manifest + DB rows at the
       request-scoped locations only. Out-of-coverage requests
       (e.g. ``year=2023`` against a 1950-2019 PWT bundle)
       still upsert the ``sources`` row AND clean up any
       pre-existing stale ``source_observations`` rows for the
       requested year(s), and surface a
       ``requested_year_out_of_coverage`` manifest warning.
       No stale-proxy fill.
    4. Return the :class:`IngestResult` from the adapter with
       the canonical PWT summary + attribution block (Rule #15).

    Args:
        year: filter to a single year (e.g. ``2019``). Default: all
            years present in the xlsx (1950-2019). ``year=2023``
            produces zero observations + an out-of-coverage
            warning.
        xlsx_path: override the input xlsx path. The function
            derives ``request.raw_root`` from it (the
            convention is ``xlsx_path = <raw_root>/pwt/pwt1001.xlsx``).
            When omitted, the data-lake default is used.
        parquet_path: override the output parquet path. The
            function derives ``request.processed_root`` from it
            (the convention is
            ``parquet_path = <processed_root>/pwt_country_year.parquet``).
            When omitted, the data-lake default is used.
        catalog_path: override the indicator catalog path. The
            catalog is consumed by the transform layer.
            When omitted, the per-source ``catalog.csv`` is
            used.
        database_url: override the SQLAlchemy URL. Honored by
            the DB write block.
        processed_root: override the processed output root.
            Useful when ``parquet_path`` is not given but the
            caller wants to redirect the output directory.

    Returns:
        An :class:`IngestResult` with ``observation_rows``,
        ``years``, ``parquet_path``, ``manifest_path``, ``warnings``
        (including ``requested_year_out_of_coverage`` for
        out-of-coverage requests), and the canonical PWT
        attribution block.

    Raises:
        RuntimeError: when the readiness gate returns
            ``ready=False`` (the blocker names the missing /
            invalid field or file).
    """
    from ...interfaces import IngestRequest
    from .adapter import PWTAdapter

    adapter = PWTAdapter()

    # Convert every public override into the equivalent
    # request-scoped field so the adapter sees a single,
    # canonical ``IngestRequest``. The convenience path and
    # the registry runner therefore produce identical
    # artifacts (per Phase B Increment B reviewer feedback).
    request_raw_root: Path | None = None
    if xlsx_path is not None:
        # Convention: ``xlsx_path`` lives at
        # ``<raw_root>/pwt/pwt1001.xlsx``. When the path
        # follows the bundle convention we derive
        # ``raw_root = xlsx_path.parent.parent``; otherwise
        # we fall back to ``xlsx_path.parent`` (the bundle
        # subdirectory) and the adapter resolves the
        # ``metadata.json`` / xlsx pair from there.
        if xlsx_path.parent.name == PWT_SOURCE_KEY:
            request_raw_root = xlsx_path.parent.parent
        else:
            request_raw_root = xlsx_path.parent

    # ``parquet_path`` is the EXACT output parquet path the
    # caller wants. Pass it through to the request verbatim
    # so the adapter honors it via ``request.parquet_path``
    # (which the ``write_pwt_parquet`` helper uses as the
    # exact-path override).
    request_parquet_path: Path | None = parquet_path
    request_processed_root: Path | None = processed_root
    if request_processed_root is None and parquet_path is not None:
        # Mirror the parquet's parent directory as the
        # ``processed_root`` so the run manifest lands next
        # to the parquet (manifest follows the parquet's
        # parent directory by default).
        request_processed_root = parquet_path.parent

    request = IngestRequest(
        source_key=PWT_SOURCE_KEY,
        year=year,
        raw_root=request_raw_root,
        processed_root=request_processed_root,
        parquet_path=request_parquet_path,
        catalog_path=catalog_path,
        database_url=database_url,
    )

    # Drive the full pipeline on the request so the
    # convenience path and the registry runner produce
    # identical artifacts (no delegation that drops the
    # request scope).
    return adapter.ingest(request)


__all__ = [
    "PWT_ATTRIBUTION",
    "PWT_CATALOG_RAW_COLUMNS",
    "PWT_DATA_SHEET_NAME",
    "PWT_METADATA_NAME",
    "PWT_REQUIRED_IDENTITY_COLUMNS",
    "PWT_SOURCE_KEY",
    "PWT_XLSX_NAME",
    "PWTAdapter",
    "ingest_pwt",
    "read_pwt",
    "transform_pwt_long_frame",
]
