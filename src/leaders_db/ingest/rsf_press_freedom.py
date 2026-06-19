"""Stage 2 -- RSF World Press Freedom Index orchestrator (REQ-SRC-002).

RSF is the **press/media-freedom sub-signal** for the ``political_freedom``
rating category, complementing the regime-structure signals of V-Dem /
Polity V / Freedom House. The data is 24 annual CSVs (2002-2010 and
2012-2026) downloaded directly from RSF's canonical pattern
(``https://rsf.org/sites/default/files/import_classement/{year}.csv``).
The direct 2011.csv is absent; RSF's combined 2011/2012 edition is
represented by the 2012 CSV (its ``Year (N)`` column reads
``"2011-12"``).

The Stage 2 adapter extracts 7 catalog indicators per the catalog at
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``:

- ``rsf_press_freedom_score`` (annual country score, 2002-2026).
- ``rsf_press_freedom_rank`` (annual country rank, 2002-2026).
- ``rsf_press_freedom_political_context`` (component, 2022+ only).
- ``rsf_press_freedom_economic_context`` (component, 2022+ only).
- ``rsf_press_freedom_legal_context`` (component, 2022+ only).
- ``rsf_press_freedom_social_context`` (component, 2022+ only).
- ``rsf_press_freedom_safety`` (component, 2022+ only).

The 2022 schema break is the RSF-specific data quirk: pre-2022 files
carry a 16-col wide format with score + rank only; 2022+ files carry
22-26 cols with the 5 component-context columns added. The adapter
handles both schemas with one CSV reader (``Year (N)`` and column
names differ across years; the catalog's logical ``raw_column`` is
resolved to the year-specific actual column at parse time).

The adapter is split across seven modules for clarity (each under
the 400-line convention from ``docs/coding-guidelines.md``):

- :mod:`leaders_db.ingest.rsf_press_freedom_io` -- catalog, path
  helpers, named constants (encoding fallbacks, column variants per
  year, component columns, missing-direct-year constant).
- :mod:`leaders_db.ingest.rsf_press_freedom_csv` -- CSV read with
  BOM-first / cp1252-fallback encoding detection, semicolon
  delimiter, comma-decimal normalization, blank-row filter,
  logical-to-actual column resolution, narrow observation frame
  construction.
- :mod:`leaders_db.ingest.rsf_press_freedom_parquet` -- parquet
  write with attribution metadata.
- :mod:`leaders_db.ingest.rsf_press_freedom_db_helpers` -- pure
  coercion and bundle-metadata helpers.
- :mod:`leaders_db.ingest.rsf_press_freedom_db` -- sources /
  observation DB writes and the run manifest.
- :mod:`leaders_db.ingest.rsf_press_freedom_result` --
  :class:`RsfPressFreedomIngestResult`.
- :mod:`leaders_db.ingest.rsf_press_freedom` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

There is no ``rsf_press_freedom_http.py`` because RSF has no HTTP
layer (the CSVs are staged locally; the user downloads them via the
project's download workflow first).

The Stage 2 end-to-end flow:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv`` (the
   single source of truth for which RSF indicators are read).
2. For each year in the requested year scope (a single year, or
   the full 2002-2026 window):
   - Read the wide-format CSV via
     :func:`rsf_press_freedom_csv.read_rsf_press_freedom_csv`.
   - Apply BOM-first / cp1252-fallback encoding detection.
   - Resolve the catalog's logical ``raw_column`` to the year-
     specific actual column (``score`` -> ``Score N`` for pre-2022
     or ``Score`` for 2022+; ``rank`` -> ``Rank N`` or ``Rank``).
   - Drop the 2022 blank separator rows (the 2022 file has 181 per
     metadata.json).
   - Normalize comma decimals to period for the score / component
     columns; coerce the rank column to int.
   - Emit one narrow row per ``(iso3, year, variable_name)`` triple
     with ``raw_value`` (verbatim RSF cell text) and
     ``normalized_value`` (float / int / None).
3. Concatenate the per-year narrow frames into one narrow frame.
4. Write the narrow frame to
   ``data/processed/rsf_press_freedom/rsf_press_freedom_country_year.parquet``
   with the RSF attribution attached to the file-level metadata.
5. Open a DB session, upsert the ``sources`` row, and write the
   ``source_observations`` rows.
6. Build the :class:`RsfPressFreedomIngestResult` and write the run
   manifest.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/source-attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_rsf_press_freedom_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte
consistent.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..db.session import session_scope
from .rsf_press_freedom_csv import read_rsf_press_freedom_csv
from .rsf_press_freedom_db import (
    register_rsf_press_freedom_source,
    write_rsf_press_freedom_observations,
    write_rsf_press_freedom_run_manifest,
)
from .rsf_press_freedom_io import (
    AVAILABLE_YEARS,
    MISSING_DIRECT_YEAR,
    RSF_PRESS_FREEDOM_ATTRIBUTION,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    IndicatorSpec,
    default_processed_parquet_path,
    default_raw_csv_path,
    load_rsf_press_freedom_catalog,
)
from .rsf_press_freedom_parquet import write_rsf_press_freedom_parquet
from .rsf_press_freedom_result import RsfPressFreedomIngestResult

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the RSF attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches RSF data must include this block
    verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return RSF_PRESS_FREEDOM_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_rsf_press_freedom(
    *,
    year: int | None = None,
    raw_dir_year_csv_paths: dict[int, Path] | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> RsfPressFreedomIngestResult:
    """Run Stage 2 for RSF end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Determine the year scope: ``year=2023`` reads only 2023;
       ``year=None`` reads the full 2002-2026 window (the 2011
       year is intentionally skipped -- the direct 2011.csv is
       absent per metadata.json ``missing_years_from_direct_csv_pattern``;
       the 2012 file represents the combined 2011/2012 edition).
    3. For each year in the scope, read the annual CSV via
       :func:`rsf_press_freedom_csv.read_rsf_press_freedom_csv`.
       The reader handles BOM-first / cp1252-fallback encoding,
       semicolon delimiter, comma-decimal normalization, blank-row
       filtering, and the pre/post-2022 schema break (the 5
       component-context columns are only present in 2022+ files).
    4. Concatenate the per-year narrow frames.
    5. Write the narrow parquet under
       ``data/processed/rsf_press_freedom/`` with the RSF
       attribution attached to the parquet's file-level metadata.
    6. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows. Idempotent: existing rows
       for the requested years are deleted before the insert.
    7. Build the :class:`RsfPressFreedomIngestResult` and write the
       run manifest.

    The function is the single public entry point -- both a
    future CLI command ``leaders-db ingest-source --source
    rsf_press_freedom`` and the tests call it. The DB session
    resolves through :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit ``database_url``
    kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2023``). Default: all
            years in the canonical direct-CSV pattern
            (2002-2026, skipping 2011).
        raw_dir_year_csv_paths: per-year override of the CSV path.
            Maps ``{year: path}``. Missing years fall back to
            :func:`default_raw_csv_path`. Default: ``None`` (use
            the canonical data-lake path for every year).
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_rsf_press_freedom_catalog(catalog_path=catalog_path)

    # Resolve the year scope. The 2011 file is intentionally
    # absent; the 2012 file represents the combined 2011/2012
    # edition. Year=2011 returns a FileNotFoundError on the path,
    # which the per-year reader call surfaces (the orchestrator's
    # caller is expected to pass a valid year).
    if year is not None:
        years_scope: list[int] = [int(year)]
    else:
        years_scope = list(AVAILABLE_YEARS)

    # Track whether the caller passed a single explicit year. When
    # ``year`` is None (full window), 2011 is silently skipped (the
    # direct 2011.csv is absent and the 2012 file represents the
    # combined 2011/2012 edition). When ``year`` is an explicit
    # value, the caller asked for that specific year; an explicit
    # request for the missing 2011 raises FileNotFoundError so the
    # caller sees the gap explicitly rather than silently losing
    # the year.
    explicit_year_scope: bool = year is not None

    per_year_frames, pre_2022_iso3s, post_2022_iso3s = _read_all_years(
        years_scope=years_scope,
        explicit_year_scope=explicit_year_scope,
        raw_dir_year_csv_paths=raw_dir_year_csv_paths,
        catalog_path=catalog_path,
    )

    if per_year_frames:
        narrow = pd.concat(
            per_year_frames,
            ignore_index=True,
            sort=False,
        )
        # Re-sort for deterministic output. The per-year frames
        # are already sorted; concat preserves the order; the
        # final sort makes the cross-year row order stable.
        narrow = narrow.sort_values(
            by=["year", "iso3", "variable_name"],
            ascending=[True, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
    else:
        narrow = pd.DataFrame(
            columns=(
                "iso3",
                "year",
                "variable_name",
                "raw_value",
                "normalized_value",
                "source_row_reference",
            ),
        )

    # Write the narrow parquet. An empty narrow frame is still
    # written so downstream stages can detect "this run produced
    # no data" without re-reading the CSVs.
    parquet = write_rsf_press_freedom_parquet(
        narrow, parquet_path=parquet_path,
    )

    # DB writes (idempotent by source/year scope).
    with session_scope() as session:
        source_id = register_rsf_press_freedom_source(session)
        rows = write_rsf_press_freedom_observations(
            session, source_id, narrow, catalog_path=catalog_path,
        )

    # Year-window / distinct country count.
    if not narrow.empty:
        year_window_tuple: tuple[int, int] = (
            int(narrow["year"].min()),
            int(narrow["year"].max()),
        )
    else:
        year_window_tuple = (0, 0)

    result = RsfPressFreedomIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(narrow["iso3"].nunique()) if not narrow.empty else 0,
        years=tuple(
            sorted({int(y) for y in narrow["year"].tolist()}),
        ),
        indicators=len(specs),
        pre_2022_country_count=len(pre_2022_iso3s),
        post_2022_country_count=len(post_2022_iso3s),
        year_window=year_window_tuple,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_rsf_press_freedom_run_manifest(result, catalog_path=catalog_path)
    return result


# ---------------------------------------------------------------------------
# Per-year CSV resolution helper
# ---------------------------------------------------------------------------


def _read_all_years(
    *,
    years_scope: list[int],
    explicit_year_scope: bool,
    raw_dir_year_csv_paths: dict[int, Path] | None,
    catalog_path: Path | None,
) -> tuple[list[pd.DataFrame], set[str], set[str]]:
    """Read the per-year narrow frames for the given year scope.

    Helper extracted from :func:`ingest_rsf_press_freedom` so the
    orchestrator's branch count stays under the 12-branch lint
    cap. Walks ``years_scope`` in order, resolves each year's
    CSV path (via the ``raw_dir_year_csv_paths`` override or the
    canonical ``default_raw_csv_path``), and accumulates the
    per-year frames + the pre-2022 / post-2022 ISO3 sets.

    Year=2011 (the missing-direct year) is silently skipped in
    the full-window run (``explicit_year_scope=False``) and
    raises :class:`FileNotFoundError` for an explicit single-year
    request.

    Returns:
        ``(per_year_frames, pre_2022_iso3s, post_2022_iso3s)``.
    """
    per_year_frames: list[pd.DataFrame] = []
    pre_2022_iso3s: set[str] = set()
    post_2022_iso3s: set[str] = set()
    for one_year in years_scope:
        # The direct 2011.csv is absent. In the full-window run we
        # silently skip the 2011 year so the orchestrator does not
        # crash; the 2012 file represents the combined 2011/2012
        # edition.
        if one_year == MISSING_DIRECT_YEAR and not explicit_year_scope:
            _logger.debug(
                "RSF skipping year=%d (direct CSV absent; 2012 file "
                "represents the combined 2011/2012 edition).",
                one_year,
            )
            continue
        # Resolve the canonical CSV path (or use the override).
        try:
            actual_csv_path = _resolve_year_csv_path(
                one_year=one_year,
                raw_dir_year_csv_paths=raw_dir_year_csv_paths,
            )
        except FileNotFoundError:
            if explicit_year_scope:
                # The caller asked for this specific year; surface
                # the missing file as an error rather than silently
                # losing it.
                raise
            # The data-lake path is missing for this year (e.g.
            # the user ran a multi-year ingest before staging the
            # full bundle). Surface the missing year as a debug
            # event and continue -- a partial ingest is still
            # useful.
            _logger.debug(
                "RSF no CSV for year=%d at the data-lake path; "
                "skipping.",
                one_year,
            )
            continue
        frame = read_rsf_press_freedom_csv(
            year=one_year,
            csv_path=actual_csv_path,
            catalog_path=catalog_path,
        )
        if frame.empty:
            continue
        per_year_frames.append(frame)
        if one_year < 2022:
            pre_2022_iso3s.update(frame["iso3"].unique().tolist())
        else:
            post_2022_iso3s.update(frame["iso3"].unique().tolist())
    return per_year_frames, pre_2022_iso3s, post_2022_iso3s


def _resolve_year_csv_path(
    *,
    one_year: int,
    raw_dir_year_csv_paths: dict[int, Path] | None,
) -> Path:
    """Resolve one year's CSV path.

    When ``raw_dir_year_csv_paths`` is provided and contains the
    year, the override is returned. Otherwise the canonical
    :func:`default_raw_csv_path` is used. The
    :class:`FileNotFoundError` propagates (the orchestrator's
    full-window loop catches and skips; the explicit-year loop
    re-raises so the caller sees the gap).
    """
    if raw_dir_year_csv_paths is not None:
        override_path = raw_dir_year_csv_paths.get(one_year)
        if override_path is not None:
            return override_path
    return default_raw_csv_path(one_year)


# Public surface re-exports. ``RSF_PRESS_FREEDOM_ATTRIBUTION``,
# ``RSF_PRESS_FREEDOM_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``rsf_press_freedom_io`` (the lowest-level module) to
# break the import cycle. The re-exports at the top of this file
# make them importable from the canonical orchestrator path; this
# ``__all__`` documents the full public surface. The CSV reader,
# the parquet writer, the path helpers, the catalog loader, and
# the DB helpers are also re-exported so the tests can drive them
# through the orchestrator module -- the V-Dem / WGI / UCDP /
# SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI pattern.
__all__ = [
    "RSF_PRESS_FREEDOM_ATTRIBUTION",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "IndicatorSpec",
    "RsfPressFreedomIngestResult",
    "attribution",
    "default_processed_parquet_path",
    "default_raw_csv_path",
    "ingest_rsf_press_freedom",
    "load_rsf_press_freedom_catalog",
    "read_rsf_press_freedom_csv",
    "register_rsf_press_freedom_source",
    "write_rsf_press_freedom_observations",
    "write_rsf_press_freedom_parquet",
    "write_rsf_press_freedom_run_manifest",
]
