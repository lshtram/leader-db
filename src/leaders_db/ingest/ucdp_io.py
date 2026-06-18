"""Stage 2 -- UCDP (Uppsala Conflict Data Program): zip read, parquet write.

This module is the I/O half of the UCDP adapter. It owns:

- :data:`UCDP_SOURCE_KEY` and :data:`UCDP_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :func:`default_zip_path` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`read_ucdp` -- open the zip, stream-read the CSV, hand off
  to the aggregator, attach ``df.attrs["events_total"]`` and
  ``df.attrs["events_filtered"]``.
- :func:`write_ucdp_parquet` -- persist the wide frame as parquet with
  the UCDP attribution attached to the schema metadata.
- :func:`_attach_parquet_metadata` -- pyarrow-level helper for the
  file-level schema metadata.

The indicator catalog dataclass and CSV loader live in
:mod:`leaders_db.ingest.ucdp_catalog`. The long-to-wide aggregation
lives in :mod:`leaders_db.ingest.ucdp_aggregate`. The DB writes
(sources upsert, source_observations write, run manifest,
missing-value coercion) live in :mod:`leaders_db.ingest.ucdp_db` and
:mod:`leaders_db.ingest.ucdp_db_helpers`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.ucdp`.

UCDP is structurally closer to WGI (one local file, no network) than
to WDI (per-indicator HTTP, JSON cache): there is no ``ucdp_http.py``.
The zip is the canonical input; the unzip-streaming read avoids
materializing the 218 MB uncompressed CSV on disk or in memory.

Constants live here (the lowest-level module that does NOT import
from siblings) so :mod:`ucdp_db` and :mod:`ucdp_db_helpers` can
import them from us, and :mod:`ucdp` can re-export them.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir
from .ucdp_aggregate import aggregate_events_to_country_year
from .ucdp_catalog import IndicatorSpec, load_indicator_catalog

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``ucdp_db`` can import it from us, and ``ucdp`` can re-export it.
UCDP_SOURCE_KEY: str = "ucdp"

#: Stable UCDP attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (ucdp section). This constant must
#: be a substring of that doc; the
#: :func:`test_ucdp_attribution_matches_attributions_doc` test enforces
#: byte-for-byte consistency. The constant lives here to break the
#: import cycle: ``ucdp_db`` imports it from us, and ``ucdp``
#: re-exports it. The year ``2023`` is the UCDP release year, not
#: the latest data year (the data ends at 2022).
UCDP_ATTRIBUTION: str = (
    "Davies, Shawn, Garounis, Nicholas, Sollenberg, Ralph, and Allansson, "
    "Marie (2023). UCDP Georeferenced Event Dataset (GED) 23.1. Uppsala "
    "Conflict Data Program. https://ucdp.uu.se/downloads/"
)

#: Raw zip file name inside ``data/raw/ucdp/``.
_RAW_ZIP_NAME: str = "ged231-csv.zip"

#: The CSV member name inside the real UCDP zip. The fixture
#: ``tests/fixtures/ucdp/sample.zip`` uses a different name
#: (``GEDEvent_sample.csv``); the read function prefers this
#: canonical name when present and falls back to the first
#: ``.csv`` member.
_ZIP_CSV_MEMBER: str = "GEDEvent_v23_1.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/ucdp/``.
_PROCESSED_PARQUET_NAME: str = "ucdp_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow
#: schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "ucdp_attribution"
_PARQUET_META_SOURCE_KEY: str = "ucdp_source_key"

#: Columns read from the UCDP CSV. Only these are loaded to keep
#: the in-memory footprint small (the full CSV is 218 MB; with
#: ``usecols`` the DataFrame is ~5 MB for the real 316,818 events).
_UCDP_CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "year",
    "country_id",
    "type_of_violence",
    "best",
    "gwnob",
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_zip_path() -> Path:
    """Return the conventional UCDP zip path inside the data lake.

    Resolves to ``<project_root>/data/raw/ucdp/ged231-csv.zip``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in ``docs/architecture/ucdp.md`` §2.3); the
    adapter expects the user to have downloaded the zip via the
    project's download workflow first.
    """
    path = raw_dir(UCDP_SOURCE_KEY) / _RAW_ZIP_NAME
    if not path.is_file():
        raise FileNotFoundError(f"UCDP zip not found: {path}")
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional UCDP narrow parquet path.

    Creates the ``data/processed/ucdp/`` directory if missing.
    """
    processed_dir(UCDP_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(UCDP_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _resolve_zip_csv_member(zip_path: Path) -> str:
    """Return the CSV member name inside ``zip_path``.

    Prefers the canonical ``_ZIP_CSV_MEMBER`` name when present, so
    the real 25.4 MB / 23.1 release works as designed. Falls back to
    the first ``.csv`` member of the zip -- this is the test-fixture
    path (``tests/fixtures/ucdp/sample.zip`` uses
    ``GEDEvent_sample.csv``). Raises :class:`KeyError` if no CSV
    member is found.
    """
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
    if _ZIP_CSV_MEMBER in members:
        return _ZIP_CSV_MEMBER
    csv_members = [m for m in members if m.lower().endswith(".csv")]
    if not csv_members:
        raise KeyError(
            f"No CSV member found in {zip_path}; members={members}"
        )
    return csv_members[0]


def read_ucdp(
    *,
    year: int | None = None,
    zip_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read UCDP from the zip and aggregate to country-year wide format.

    Steps:

    1. Open the zip and stream-read the CSV member (using ``usecols``
       to limit to 6 columns).
    2. Filter by year if ``year=`` is passed.
    3. Hand the long frame to
       :func:`ucdp_aggregate.aggregate_events_to_country_year` for
       the long->wide pivot (3 groupby's: state-based, one-sided,
       intl subset; dense cross-product of unique countries and
       unique years).
    4. Attach ``df.attrs["events_total"]`` (post-year-filter, pre-type
       count) and ``df.attrs["events_filtered"]`` (post-type filter).

    Args:
        year: filter to a single year (e.g. ``2022``). Default: all
            years present in the zip (1989-2022, 34 distinct years).
        zip_path: override the input zip. Default: data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A wide pandas DataFrame with columns ``country_id``, ``year``,
        then one column per catalog indicator. ``country_id`` is
        UCDP's own integer ID (NOT ISO3); Stage 3 resolves it to
        ISO3. Event-count columns are ``Int64``; fatalities columns
        are ``float``. Empty country-years are present with 0/0.0
        values (the wide frame is dense).

    Raises:
        FileNotFoundError: if the zip is missing.
        KeyError: if the zip does not contain a CSV member, or if a
            required column is absent.
        zipfile.BadZipFile: if the file at ``zip_path`` is not a
            valid zip.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    indicator_vars = [s.variable_name for s in specs]

    path = zip_path or default_zip_path()
    if not path.is_file():
        raise FileNotFoundError(f"UCDP zip not found: {path}")

    csv_member = _resolve_zip_csv_member(path)
    # Stream-read the CSV from inside the zip. ``zipfile.ZipFile.open``
    # yields a ZipExtFile that pandas reads incrementally; the
    # uncompressed 218 MB CSV never fully materializes in memory as
    # a single string (pandas chunks it internally).
    with zipfile.ZipFile(path) as zf, zf.open(csv_member) as member_file:
        df_long = pd.read_csv(
            member_file,
            usecols=list(_UCDP_CSV_COLUMNS),
            low_memory=False,
        )

    # Defensive: confirm the columns the catalog / aggregation
    # depends on are present. A UCDP schema change (e.g., ``best`` ->
    # ``best_est``) would surface here.
    needed_for_agg = ("year", "country_id", "type_of_violence")
    missing_cols = [c for c in needed_for_agg if c not in df_long.columns]
    if missing_cols:
        raise KeyError(
            f"UCDP CSV in {path} is missing required columns "
            f"{missing_cols}. Check that the file is GED 23.1 and the "
            "catalog is in sync."
        )

    # Coerce types defensively. UCDP's CSV stores them as int
    # already but be safe in case the read is a re-read from a
    # processed frame.
    df_long["year"] = df_long["year"].astype(int)
    df_long["country_id"] = df_long["country_id"].astype(int)
    df_long["type_of_violence"] = df_long["type_of_violence"].astype(int)
    # ``best`` may be NaN (events with no fatality estimate) and
    # ``gwnob`` may be NaN (events where side_b is not a state).
    # Both are valid.
    if "best" in df_long.columns:
        df_long["best"] = pd.to_numeric(df_long["best"], errors="coerce")
    if "gwnob" in df_long.columns:
        df_long["gwnob"] = pd.to_numeric(df_long["gwnob"], errors="coerce")

    # Build the cross-product grid BEFORE the year filter is applied,
    # so the grid carries every (unique country, unique year) in the
    # input. Then filter both the long frame and the grid to the
    # requested year. The aggregation helper cross-products the
    # unique countries and years of the year-filtered long frame, so
    # when year=2021 the helper still sees the 5 unique countries
    # from the unfiltered input (passed via the grid's country_id
    # values), producing a 5x1 grid (Germany 2021 gets a row with 0
    # values because it has no 2021 events).
    full_unique_countries = sorted(
        df_long["country_id"].drop_duplicates().tolist()
    )
    full_unique_years = sorted(df_long["year"].drop_duplicates().tolist())
    grid = pd.MultiIndex.from_product(
        [full_unique_countries, full_unique_years],
        names=["country_id", "year"],
    ).to_frame(index=False)

    if year is not None:
        df_long = df_long.loc[df_long["year"] == int(year)].reset_index(drop=True)
        grid = grid.loc[grid["year"] == int(year)].reset_index(drop=True)

    # ``events_total`` is the audit trail of "how much data was in
    # the input" (the post-year-filter event count, before the type
    # filter). ``events_filtered`` is the count after the type=1 OR
    # type=3 filter; the helper computes it and attaches it to
    # ``df.attrs``.
    events_total = len(df_long)
    wide = aggregate_events_to_country_year(
        df_long, indicator_vars, grid=grid,
    )
    wide.attrs["events_total"] = events_total
    return wide


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_ucdp_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and
    :func:`wgi_io.write_wgi_parquet`: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the UCDP
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or UCDP_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the UCDP attribution + source key to the parquet's schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We rewrite
    the parquet in place to add it. This is best-effort: if the
    rewrite fails (corrupt file, race, full disk) the parquet remains
    valid and we log a warning. Schema/data errors are NOT swallowed
    silently -- they re-raise so the orchestrator can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = UCDP_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the
        # audit metadata is lost. Log and continue -- the
        # attribution is also carried in the run manifest, so the
        # audit trail survives.
        _logger.warning(
            "Failed to attach UCDP attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the "
            "audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "UCDP_ATTRIBUTION",
    "UCDP_SOURCE_KEY",
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_zip_path",
    "load_indicator_catalog",
    "read_ucdp",
    "write_ucdp_parquet",
]
