"""Stage 2 -- UNDP Human Development Index (HDR 2023-24) orchestrator.

UNDP HDI is the **composite-index** social-wellbeing source for the
prototype. The dataset is a single wide-format CSV
(``HDR23-24_Composite_indices_complete_time_series.csv``, 1.9 MB,
latin-1 encoded) distributed by the UNDP Human Development Report
project under a free license with attribution. The Stage 2 adapter
extracts the 5 social-wellbeing indicators from architecture §3:
HDI, life expectancy, expected years of schooling, mean years of
schooling, and GNI per capita.

The adapter is split across small modules. ``undp_hdi.py`` remains the
public orchestrator and re-export surface, while helper modules keep the
documented line caps enforceable:

- :mod:`leaders_db.ingest.undp_hdi_io` -- catalog, path helpers,
  named constants.
- :mod:`leaders_db.ingest.undp_hdi_csv` -- CSV read with latin-1,
  schema validation, and source-code validation warnings.
- :mod:`leaders_db.ingest.undp_hdi_unpivot` -- narrow observation
  construction from the validated wide frame, including WIDE-to-LONG
  UNPIVOT.
- :mod:`leaders_db.ingest.undp_hdi_db` -- source / observation
  DB writes + run manifest.
- :mod:`leaders_db.ingest.undp_hdi_db_helpers` -- DB row coercion and
  bundle metadata helpers.
- :mod:`leaders_db.ingest.undp_hdi_parquet` -- parquet write and
  parquet attribution/source-key metadata.
- :mod:`leaders_db.ingest.undp_hdi_result` --
  :class:`UndpHdiIngestResult`.
- :mod:`leaders_db.ingest.undp_hdi` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

There is no ``undp_hdi_http.py`` because UNDP HDI has no HTTP
layer (the CSV is staged locally; the user downloads it via the
project's download workflow first).

Year 2023 is proxied to 2022 (1-year-gap, per the CIRIGHTS /
Leader Survival pattern); the proxy mapping is surfaced in the
manifest.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/source-attributions.md``; the
:func:`test_undp_hdi_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .undp_hdi_csv import read_undp_hdi_csv
from .undp_hdi_db import (
    register_undp_hdi_source,
    write_undp_hdi_observations,
    write_undp_hdi_run_manifest,
)
from .undp_hdi_io import (
    UNDP_HDI_ATTRIBUTION,
    UNDP_HDI_PROXY_REQUESTED_YEAR,
    UNDP_HDI_PROXY_YEAR,
    UNDP_HDI_SOURCE_KEY,
    IndicatorSpec,
    default_csv_path,
    default_processed_parquet_path,
    load_undp_hdi_catalog,
)
from .undp_hdi_parquet import write_undp_hdi_parquet
from .undp_hdi_result import UndpHdiIngestResult
from .undp_hdi_unpivot import build_undp_hdi_observations

# Re-exports: ``UNDP_HDI_ATTRIBUTION``, ``UNDP_HDI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``undp_hdi_io`` (the lowest-level
# module that does NOT import from siblings) to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. The path helpers, the read orchestrator, the build helper,
# and the DB helpers are also re-exported so the test-builder's
# tests can call them through the orchestrator module -- the
# WGI / WDI / V-Dem / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 /
# PTS pattern.


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the UNDP HDI attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches UNDP HDI data must include this block
    verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return UNDP_HDI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_undp_hdi(
    *,
    year: int | None = None,
    csv_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> UndpHdiIngestResult:
    """Run Stage 2 for UNDP HDI end-to-end.

    Steps (each idempotent): load catalog, read wide frame via
    :func:`undp_hdi_csv.read_undp_hdi_csv` (latin-1 + schema
    validation), UNPIVOT to a narrow frame via
    :func:`undp_hdi_unpivot.build_undp_hdi_observations` (empty cells
    dropped at DEBUG), write the narrow parquet, upsert the
    ``sources`` row + write ``source_observations`` rows, write
    the run manifest, return the result.

    Year proxy semantics: ``year=2023`` is mapped to ``year=2022``
    (the latest available data) per architecture §4 + the
    CIRIGHTS / Leader Survival 1-year-gap pattern. The mapping is
    surfaced in the manifest's ``proxy_year_semantics`` field and
    in ``requested_year``.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source undp_hdi`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2022`` or ``2023``).
            Default: all years present in the CSV (1990-2022).
        csv_path: override the input CSV. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_undp_hdi_catalog(catalog_path=catalog_path)

    # Year 2023 -> 2022 proxy (per architecture §4 + CIRIGHTS /
    # Leader Survival 1-year-gap pattern). The orchestrator
    # surfaces the proxy mapping on the result so the manifest
    # can record it.
    requested_year = year
    effective_year = year
    proxy_year_semantics: str | None = None
    if year is not None and year == UNDP_HDI_PROXY_REQUESTED_YEAR:
        effective_year = UNDP_HDI_PROXY_YEAR
        proxy_year_semantics = (
            f"year={UNDP_HDI_PROXY_REQUESTED_YEAR} -> "
            f"data_year={UNDP_HDI_PROXY_YEAR} (1-year-gap proxy, "
            "per docs/architecture/undp_hdi.md §4 + CIRIGHTS / "
            "Leader Survival pattern)"
        )

    # Read the wide frame. The ``year=`` argument to the reader
    # affects the schema validation: it asserts the
    # ``{prefix}_{year}`` columns for the requested year exist.
    # The wide frame itself still contains every year (the
    # year filter is applied in the UNPIVOT step).
    actual_csv_path = csv_path or default_csv_path()
    wide_df = read_undp_hdi_csv(
        csv_path=actual_csv_path,
        catalog_path=catalog_path,
        year=effective_year,
    )

    # UNPIVOT to a narrow frame; apply the year filter here so
    # the narrow frame is correctly scoped for both the parquet
    # write and the DB observation write.
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=catalog_path,
        year=effective_year,
    )

    # Surface the audit-trail extras from the narrow frame.
    # ``regions_covered``: sorted list of unique region codes
    # observed in the narrow frame (the 6 known codes plus any
    # unknown / NaN values, preserved verbatim per §6).
    regions_covered = sorted(
        {str(r) for r in narrow_df["region"].dropna().unique().tolist()}
    )
    if not narrow_df.empty:
        year_window_tuple: tuple[int, int] = (
            int(narrow_df["year"].min()),
            int(narrow_df["year"].max()),
        )
    else:
        year_window_tuple = (0, 0)

    # Write the narrow parquet. Even an empty narrow frame is
    # written so downstream stages can detect "this run produced
    # no data" without re-reading the CSV.
    parquet = write_undp_hdi_parquet(
        narrow_df, parquet_path=parquet_path,
    )

    # DB writes (idempotent by source/year scope).
    with session_scope() as session:
        source_id = register_undp_hdi_source(session)
        rows = write_undp_hdi_observations(
            session, source_id, narrow_df, catalog_path=catalog_path,
        )

    result = UndpHdiIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(narrow_df["iso3"].nunique()) if not narrow_df.empty else 0,
        years=tuple(
            sorted({int(y) for y in narrow_df["year"].tolist()}),
        ),
        indicators=len(specs),
        regions_covered=regions_covered,
        year_window=year_window_tuple,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata. The proxy_year_semantics /
    # requested_year are surfaced here (not on the result model)
    # so the result's 8-field contract is preserved (architecture
    # §9) while the manifest still records the 2023 -> 2022
    # proxy mapping.
    write_undp_hdi_run_manifest(
        result,
        catalog_path=catalog_path,
        proxy_year_semantics=proxy_year_semantics,
        requested_year=(
            int(requested_year) if requested_year is not None else None
        ),
    )
    return result


# Public surface: ``UNDP_HDI_ATTRIBUTION``, ``UNDP_HDI_SOURCE_KEY``,
# and ``IndicatorSpec`` are defined in ``undp_hdi_io`` (the
# lowest-level module) to break the import cycle. The re-exports
# at the top of this file make them importable from the canonical
# orchestrator path; this ``__all__`` documents the full public
# surface. The path helpers, the read orchestrator, the build
# helper, and the DB helpers are also re-exported so the tests
# can drive the adapter through the orchestrator module.
__all__ = [
    "UNDP_HDI_ATTRIBUTION",
    "UNDP_HDI_SOURCE_KEY",
    "IndicatorSpec",
    "UndpHdiIngestResult",
    "attribution",
    "build_undp_hdi_observations",
    "default_csv_path",
    "default_processed_parquet_path",
    "ingest_undp_hdi",
    "load_undp_hdi_catalog",
    "read_undp_hdi_csv",
    "register_undp_hdi_source",
    "write_undp_hdi_observations",
    "write_undp_hdi_parquet",
    "write_undp_hdi_run_manifest",
]
