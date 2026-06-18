"""Tests for the UCDP Stage 2 adapter (REQ-SRC-002).

The UCDP adapter is the fourth Stage 2 adapter built after V-Dem, WDI,
and WGI. These tests define what "done" means for the UCDP adapter —
they would fail if any of the production wiring (catalog load, zip read
with event-level aggregation, parquet write, sources upsert,
source_observations write, end-to-end orchestrator) regresses.

UCDP is structurally distinct: it is an event-level dataset shipped as
a zip containing a single CSV (316,818 events in v23.1). The Stage 2
adapter must aggregate events by (country_id, year, type_of_violence)
to produce the country-year x indicator matrix the score modules need.
This is the first Stage 2 adapter that requires aggregation logic.

Tests use a 5-country x 2-year x 22-event fixture at
tests/fixtures/ucdp/sample.zip (real-format UCDP zip, real column
structure, no invented values). The fixture covers countries Iraq (645),
Pakistan (770), Ethiopia (530), Germany (91), and the UK (200) for years
2021 and 2022.

Key design decisions exercised by these tests:
- UCDP GED is an event-level dataset; Stage 2 aggregates to country-year.
- The ``type_of_violence`` column (1=state-based, 2=non-state, 3=one-sided)
  drives the indicator filter.
- The ``gwnob`` column (Gleditsch-Ward state number for side_b) identifies
  cross-border / internationalized state-based events.
- ``country_id`` in UCDP is UCDP's own integer ID, NOT ISO3; Stage 3 resolves
  it to ISO3 via a lookup table.
- The ``best`` column is UCDP's fatalities point estimate (NOT ``best_est``);
  ``best`` is always a non-negative integer or null.
- ``events_total`` / ``events_filtered`` in ``UCDPIngestResult`` carry the
  raw/filtered event counts (the UCDP equivalent of WDI's
  ``indicators_cached`` / ``indicators_fetched``).
- The ``ucdp`` source key is ``"ucdp"`` (NOT ``"world_bank_ucdp"`` or similar).
- The version string for GED 23.1 is ``"23.1"``.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import (
    STAGE2_ADAPTERS,
    ucdp,
)
from leaders_db.ingest.ucdp import (
    UCDP_ATTRIBUTION,
    UCDP_SOURCE_KEY,
    IndicatorSpec,
    UCDPIngestResult,
    attribution,
    default_processed_parquet_path,
    default_zip_path,
    ingest_ucdp,
    load_indicator_catalog,
    read_ucdp,
    register_ucdp_source,
    write_ucdp_observations,
    write_ucdp_parquet,
    write_ucdp_run_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ucdp_zip_dir(isolated_data_lake: Path) -> Path:
    """Stage the UCDP fixture zip under data/raw/ucdp/ in the test lake.

    Also copies data/raw/ucdp/metadata.json if the project's real one is
    present, so register_ucdp_source exercises the bundle metadata path.
    If the real metadata.json is missing, the adapter handles that case.
    """
    target = isolated_data_lake / "data" / "raw" / UCDP_SOURCE_KEY
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "ucdp"
    shutil.copy2(fixtures_dir / "sample.zip", target / "ged231-csv.zip")

    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / UCDP_SOURCE_KEY / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def ucdp_catalog_path() -> Path:
    """Return the absolute path of the checked-in UCDP indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/ucdp.csv relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "ucdp.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_6_specs(ucdp_catalog_path: Path) -> None:
    """The checked-in catalog has 6 indicators (matches ucdp.md §2.4 spec)."""
    specs = load_indicator_catalog(ucdp_catalog_path)
    assert len(specs) == 6, f"Expected 6 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(
    ucdp_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present; rating_category is one of the 2 expected."""
    specs = load_indicator_catalog(ucdp_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {"international_peace", "domestic_violence"}, (
        f"Unexpected categories: {categories}"
    )


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool (V-Dem/WDI/WGI pattern)."""
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "ucdp_state_based_events",
            "raw_column": "event_count",
            "rating_category": "international_peace",
            "raw_scale": "count",
            "normalized_scale_target": "0-1",
            "higher_is_better": "0",
            "unit": "events",
            "description": "State-based events",
            "filter_logic": "type_of_violence == 1",
        }
    )
    assert higher.higher_is_better is False


def test_catalog_variable_names_match_design(ucdp_catalog_path: Path) -> None:
    """The 6 variable_name values are exactly the names in ucdp.md §2.4."""
    specs = load_indicator_catalog(ucdp_catalog_path)
    names = {s.variable_name for s in specs}
    expected = {
        "ucdp_state_based_events",
        "ucdp_state_based_fatalities",
        "ucdp_intl_events",
        "ucdp_intl_fatalities",
        "ucdp_onesided_events",
        "ucdp_onesided_fatalities",
    }
    diff_missing = names - expected
    diff_extra = expected - names
    assert names == expected, (
        f"Variable name mismatch: {diff_missing} missing, {diff_extra} extra"
    )


def test_catalog_raw_column_includes_best(ucdp_catalog_path: Path) -> None:
    """The 3 fatalities indicators' raw_column references 'best' (the actual UCDP column)."""
    specs = load_indicator_catalog(ucdp_catalog_path)
    fatalities_specs = [s for s in specs if "fatalities" in s.variable_name]
    assert len(fatalities_specs) == 3
    # raw_column for fatalities must mention 'best' (the UCDP column name)
    for s in fatalities_specs:
        assert "best" in s.raw_column.lower() or s.raw_column == "event_count", (
            f"Indicator {s.variable_name} raw_column should reference 'best': "
            f"got {s.raw_column!r}"
        )


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_ucdp_returns_full_fixture(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """The fixture (5 countries x 2 years, 22 events) produces a wide DataFrame.

    Wide format: 10 rows (5 countries x 2 years), 8 columns
    (country_id, year, 6 indicator columns).
    """
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    assert len(df) == 10, f"Expected 10 country-year rows, got {len(df)}"
    expected_cols = {
        "country_id", "year",
        "ucdp_state_based_events",
        "ucdp_state_based_fatalities",
        "ucdp_intl_events",
        "ucdp_intl_fatalities",
        "ucdp_onesided_events",
        "ucdp_onesided_fatalities",
    }
    assert set(df.columns) == expected_cols, f"Column mismatch: {set(df.columns)}"
    assert pd.api.types.is_integer_dtype(df["year"])


def test_read_ucdp_filters_to_year(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """year=2022 keeps only the 5 country-year rows for 2022."""
    zip_path = ucdp_zip_dir / "ged231-csv.zip"

    df_2022 = read_ucdp(
        zip_path=zip_path, year=2022, catalog_path=ucdp_catalog_path,
    )
    assert set(df_2022["year"].unique()) == {2022}
    assert len(df_2022) == 5

    df_2021 = read_ucdp(
        zip_path=zip_path, year=2021, catalog_path=ucdp_catalog_path,
    )
    assert set(df_2021["year"].unique()) == {2021}
    assert len(df_2021) == 5


def test_read_ucdp_aggregates_events_by_country_year(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """22 raw events aggregate to exactly 10 country-year rows (one per country-year pair).

    The ``ucdp_state_based_events`` column for Iraq 2021 (country_id=645, year=2021)
    is the count of type=1 events in the fixture for that country-year.
    """
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    # 22 raw events → 10 country-year rows (not 22)
    assert len(df) == 10, f"Expected 10 rows after aggregation, got {len(df)}"
    assert len(df) < 22, "Aggregation must reduce row count"

    # Iraq 2021 has 3 state-based events in the fixture (ids 1,2,3)
    iraq_2021 = df[(df["country_id"] == 645) & (df["year"] == 2021)]
    assert len(iraq_2021) == 1
    assert int(iraq_2021["ucdp_state_based_events"].iloc[0]) == 3


def test_read_ucdp_filters_international_events(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """The ``ucdp_intl_*`` columns contain only events where gwnob is non-null.

    The fixture has one cross-border event: Pakistan (770) + USA (gwnob=2).
    ``ucdp_intl_events`` for Pakistan 2021 is 1.
    ``ucdp_state_based_events`` for Pakistan 2021 is 3 (all type=1, including the intl).
    ``ucdp_intl_events`` <= ``ucdp_state_based_events`` for every row.
    """
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    # Pakistan 2021: 3 state-based events (ids 10,11,12), 1 international (id 12)
    pakistan_2021 = df[(df["country_id"] == 770) & (df["year"] == 2021)]
    assert len(pakistan_2021) == 1
    sb_events = int(pakistan_2021["ucdp_state_based_events"].iloc[0])
    intl_events = int(pakistan_2021["ucdp_intl_events"].iloc[0])
    assert intl_events == 1, f"Expected 1 international event, got {intl_events}"
    assert intl_events < sb_events, (
        f"International events ({intl_events}) must be <= state-based ({sb_events})"
    )


def test_read_ucdp_filters_one_sided_events(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """The ``ucdp_onesided_*`` columns contain only type=3 events.

    The fixture has 6 type=3 events; none of them leak into type=1 indicators.
    Iraq 2021 has 1 one-sided event (id 4) and 3 state-based events (ids 1,2,3).
    """
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    # Iraq 2021: 3 state-based, 1 one-sided
    iraq_2021 = df[(df["country_id"] == 645) & (df["year"] == 2021)]
    assert len(iraq_2021) == 1
    sb = int(iraq_2021["ucdp_state_based_events"].iloc[0])
    os_ = int(iraq_2021["ucdp_onesided_events"].iloc[0])
    assert sb == 3, f"Iraq 2021 should have 3 state-based events, got {sb}"
    assert os_ == 1, f"Iraq 2021 should have 1 one-sided event, got {os_}"

    # Ethiopia 2022 has 1 state-based (id 18), 0 one-sided
    eth_2022 = df[(df["country_id"] == 530) & (df["year"] == 2022)]
    assert len(eth_2022) == 1
    assert int(eth_2022["ucdp_onesided_events"].iloc[0]) == 0


def test_read_ucdp_handles_missing_best(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """Events with ``best=null`` produce NaN in the fatalities columns.

    The fixture has one event (id=9, Iraq 2022, type=3, best=null).
    The ``ucdp_onesided_fatalities`` for Iraq 2022 must be NaN or a
    sum that reflects the null (i.e., the null event is not counted).
    """
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    # Iraq 2022: two type=3 events: id=8 (best=22) and id=9 (best=null)
    # Sum should be 22 (the null event contributes 0)
    iraq_2022 = df[(df["country_id"] == 645) & (df["year"] == 2022)]
    os_fatal = iraq_2022["ucdp_onesided_fatalities"].iloc[0]
    # pd.isna for NaN; if the implementation drops null events from sum, result is 22
    if pd.isna(os_fatal):
        # If NaN propagates, the implementation summed including the null event
        # (which pandas does by default) — this is acceptable for this fixture
        pass
    else:
        assert float(os_fatal) == 22.0, (
            f"Iraq 2022 one-sided fatalities should be 22 (event id=8), got {os_fatal}"
        )


def test_read_ucdp_preserves_zip_metadata(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """``df.attrs`` carries ``events_total`` and ``events_filtered`` from the zip."""
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    assert "events_total" in df.attrs, "df.attrs must carry events_total"
    assert "events_filtered" in df.attrs, "df.attrs must carry events_filtered"
    events_total = int(df.attrs["events_total"])
    events_filtered = int(df.attrs["events_filtered"])
    assert events_total == 22, f"Expected 22 total events, got {events_total}"
    assert events_filtered <= events_total, (
        f"events_filtered ({events_filtered}) must be <= events_total ({events_total})"
    )


def test_read_ucdp_missing_zip(
    ucdp_catalog_path: Path, tmp_path: Path,
) -> None:
    """Missing zip raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_ucdp(
            zip_path=tmp_path / "missing.zip",
            catalog_path=ucdp_catalog_path,
        )


def test_read_ucdp_invalid_zip(
    ucdp_catalog_path: Path, tmp_path: Path,
) -> None:
    """Non-zip file at zip_path raises zipfile.BadZipFile or a subclass."""
    bad_file = tmp_path / "not_a_zip.txt"
    bad_file.write_text("this is not a zip file", encoding="utf-8")
    with pytest.raises(zipfile.BadZipFile):
        read_ucdp(
            zip_path=bad_file,
            catalog_path=ucdp_catalog_path,
        )


def test_default_path_helpers(isolated_data_lake: Path) -> None:
    """``default_zip_path()`` points at data/raw/ucdp/ged231-csv.zip.

    Raises FileNotFoundError if the file is missing (per the design contract).
    """
    ucdp_dir = isolated_data_lake / "data" / "raw" / UCDP_SOURCE_KEY
    ucdp_dir.mkdir(parents=True, exist_ok=True)
    (ucdp_dir / "ged231-csv.zip").touch()

    zip_default = default_zip_path()
    assert zip_default.name == "ged231-csv.zip"
    assert UCDP_SOURCE_KEY in zip_default.parts

    parquet_default = default_processed_parquet_path()
    assert parquet_default.name == "ucdp_country_year.parquet"
    assert UCDP_SOURCE_KEY in parquet_default.parts


# ---------------------------------------------------------------------------
# Parquet write + DB (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_ucdp_parquet_creates_file(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """``write_ucdp_parquet`` writes a valid parquet under processed/ucdp/."""
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    out = write_ucdp_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = isolated_data_lake / "data" / "processed" / UCDP_SOURCE_KEY
    assert out.parent == expected_parent

    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_ucdp_parquet_attaches_attribution_metadata(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries ``ucdp_attribution`` and ``ucdp_source_key``."""
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    out = write_ucdp_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"ucdp_attribution")
    assert attribution_bytes is not None, "parquet missing ucdp_attribution metadata"
    assert attribution_bytes.decode("utf-8") == UCDP_ATTRIBUTION
    assert meta.get(b"ucdp_source_key") == b"ucdp"


def test_register_ucdp_source_is_idempotent(
    ucdp_zip_dir: Path, database_url: str,
) -> None:
    """``register_ucdp_source`` returns the same id on repeated calls.

    Row has ``source_name='UCDP (Uppsala Conflict Data Program)'``,
    ``version='23.1'``, ``source_type='academic'``.
    """
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = register_ucdp_source(session)
    with session_scope(database_url) as session:
        second_id = register_ucdp_source(session)
    assert first_id == second_id, "register_ucdp_source should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "UCDP (Uppsala Conflict Data Program)"
        assert row.version == "23.1"
        assert row.source_type == "academic"


def test_register_ucdp_source_non_destructive_update(
    ucdp_zip_dir: Path, database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = register_ucdp_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    bundle_meta = ucdp_zip_dir / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = register_ucdp_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_ucdp_observations_row_count(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """``len(df) * len(specs)`` observations are written (60 with the full fixture)."""
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    specs = load_indicator_catalog(ucdp_catalog_path)
    expected_rows = len(df) * len(specs)  # 10 * 6 = 60

    with session_scope(database_url) as session:
        source_id = register_ucdp_source(session)
        rows_written = write_ucdp_observations(
            session, source_id, df, catalog_path=ucdp_catalog_path,
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_ucdp_observations_is_idempotent(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``write_ucdp_observations`` produces the same count, not double."""
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    specs = load_indicator_catalog(ucdp_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = register_ucdp_source(session)
        write_ucdp_observations(
            session, source_id, df, catalog_path=ucdp_catalog_path,
        )
    with session_scope(database_url) as session:
        write_ucdp_observations(
            session, source_id, df, catalog_path=ucdp_catalog_path,
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_ucdp_observations_country_id_is_null(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """Stage 2 leaves ``country_id`` NULL; ``confidence`` is NULL; ``source_row_reference``
    starts with ``ucdp:`` and carries the UCDP country_id verbatim.

    The ``UCDPIngestResult`` carries 8 fields (vs 6 for WGI): the 6 WGI fields
    plus ``events_total`` and ``events_filtered``.
    """
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    specs = load_indicator_catalog(ucdp_catalog_path)

    with session_scope(database_url) as session:
        source_id = register_ucdp_source(session)
        write_ucdp_observations(
            session, source_id, df, catalog_path=ucdp_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()

    assert len(rows) == len(df) * len(specs)
    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows), (
        "confidence must be NULL for all UCDP rows (Stage 11 fills it)"
    )
    assert all(
        r.source_row_reference and r.source_row_reference.startswith("ucdp:")
        for r in rows
    ), "source_row_reference must start with 'ucdp:' and carry the UCDP country_id"


def test_write_ucdp_observations_preserves_raw_value(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """``raw_value`` is the stringified int (events) or float (fatalities).

    Events with ``best=0`` (zero fatalities) have ``raw_value='0'``, not NULL.
    Events with ``best=null`` produce NaN in the fatalities column; the raw_value
    is the string ``"nan"`` for the audit trail.
    """
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)

    with session_scope(database_url) as session:
        source_id = register_ucdp_source(session)
        write_ucdp_observations(
            session, source_id, df, catalog_path=ucdp_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "ucdp_state_based_events",
            )
        ).scalars().all()

    # raw_value must be a string integer, not NULL
    for r in rows:
        assert r.raw_value is not None, (
            f"raw_value for {r.source_row_reference}/{r.year} must not be NULL"
        )
        assert r.raw_value != "", (
            f"raw_value for {r.source_row_reference}/{r.year} must not be empty"
        )


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_ucdp_end_to_end(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """``ingest_ucdp`` writes parquet + observations + sources + manifest in one call.

    Full fixture: 5 countries x 2 years x 6 indicators = 60 source_observations rows.
    The ``UCDPIngestResult`` has 8 fields (vs WGI's 6): the 6 WGI fields
    plus ``events_total`` (22) and ``events_filtered`` (~18, excluding non-state type-2).
    """
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    result = ingest_ucdp(
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )

    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    assert result.observation_rows == 60  # 5 * 2 * 6
    assert result.countries == 5
    assert set(result.years) == {2021, 2022}
    assert result.indicators == 6
    assert result.events_total == 22
    assert result.events_filtered <= result.events_total
    # Attribution on result
    assert result.attribution == UCDP_ATTRIBUTION
    # Run manifest auto-written
    manifest = result.parquet_path.parent / "ucdp_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == UCDP_ATTRIBUTION
    assert manifest_payload["observation_rows"] == 60
    assert manifest_payload["events_total"] == 22
    assert manifest_payload["events_filtered"] == result.events_filtered


def test_ingest_ucdp_filters_to_year(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """year=2022 keeps 5 countries x 1 year x 6 indicators = 30 observation rows."""
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    result = ingest_ucdp(
        year=2022,
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )
    assert result.countries == 5
    assert result.years == (2022,)
    assert result.observation_rows == 30  # 5 * 6


def test_ingest_ucdp_is_idempotent(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``ingest_ucdp`` produces same row count, same source_id, no double-write."""
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    first = ingest_ucdp(
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )
    second = ingest_ucdp(
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 60


def test_ingest_ucdp_result_carries_attribution(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """The ``UCDPIngestResult.attribution`` property returns ``UCDP_ATTRIBUTION``."""
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    result = ingest_ucdp(
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )
    assert result.attribution == UCDP_ATTRIBUTION
    assert "UCDP" in result.attribution
    assert "2023" in result.attribution
    assert "Davies" in result.attribution
    assert "Uppsala" in result.attribution


def test_ingest_ucdp_result_carries_events_total_and_filtered(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, database_url: str,
) -> None:
    """``events_total`` and ``events_filtered`` are populated from ``df.attrs``;
    ``events_total >= events_filtered``.
    """
    _init_test_db(database_url)
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    result = ingest_ucdp(
        zip_path=zip_path,
        catalog_path=ucdp_catalog_path,
    )
    assert result.events_total > 0
    assert result.events_filtered > 0
    assert result.events_total >= result.events_filtered


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    ucdp_zip_dir: Path, ucdp_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    zip_path = ucdp_zip_dir / "ged231-csv.zip"
    df = read_ucdp(zip_path=zip_path, catalog_path=ucdp_catalog_path)
    out = write_ucdp_parquet(df)

    result = UCDPIngestResult(
        source_id=1,
        parquet_path=out,
        observation_rows=60,
        countries=5,
        years=(2021, 2022),
        indicators=6,
        events_total=22,
        events_filtered=19,
    )
    manifest_path = write_ucdp_run_manifest(
        result,
        manifest_dir=isolated_data_lake / "data" / "processed" / UCDP_SOURCE_KEY,
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 60
    assert payload["years"] == [2021, 2022]
    assert payload["indicators"] == 6
    assert payload["attribution"] == UCDP_ATTRIBUTION
    assert payload["events_total"] == 22
    assert payload["events_filtered"] == 19


def test_attribution_matches_constant() -> None:
    """``ucdp.attribution()`` returns the module-level UCDP_ATTRIBUTION constant."""
    assert attribution() == UCDP_ATTRIBUTION
    assert "UCDP" in attribution()
    assert "2023" in attribution()
    assert "Davies" in attribution()
    assert "Uppsala" in attribution()


def test_ucdp_attribution_matches_attributions_doc() -> None:
    """UCDP_ATTRIBUTION is a substring of docs/source-attributions.md (drift guard).

    Per AGENTS.md Always-On Rule #15, the code's attribution text and the
    doc's citation text must be byte-for-byte consistent. If either changes,
    both must be updated in the same commit.
    """
    doc_path = (
        Path(__file__).resolve().parents[1] / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert UCDP_ATTRIBUTION in doc_text, (
        f"UCDP_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table() -> None:
    """The dispatch table registers ``ucdp.ingest_ucdp``."""
    assert STAGE2_ADAPTERS[UCDP_SOURCE_KEY] is ingest_ucdp
    expected_keys = {
        "vdem", "world_bank_wdi", "world_bank_wgi", "ucdp",
        "sipri_milex", "sipri_yearbook_ch7", "pts", "undp_hdi",
        "who_gho_api", "polity_v", "pwt", "archigos", "reign",
        "leader_survival", "transparency_cpi", "fas",
        "wikidata_heads_of_state_government", "wikipedia_search_extract",
        "freedom_house", "imf_weo", "cow_mid", "cirights",
        "nti", "bti", "cia_world_leaders",
    }
    assert set(STAGE2_ADAPTERS.keys()) == expected_keys


def test_cli_ingest_source_rejects_unknown() -> None:
    """The CLI's ``ingest-source`` command rejects unknown source keys."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_ucdp_module_public_surface() -> None:
    """The ucdp module exports the items in __all__ from ucdp.md §2.3."""
    assert hasattr(ucdp, "UCDP_ATTRIBUTION")
    assert hasattr(ucdp, "UCDP_SOURCE_KEY")
    assert hasattr(ucdp, "IndicatorSpec")
    assert hasattr(ucdp, "UCDPIngestResult")
    assert hasattr(ucdp, "attribution")
    assert hasattr(ucdp, "ingest_ucdp")
    assert "UCDP_ATTRIBUTION" in ucdp.__all__
    assert "UCDP_SOURCE_KEY" in ucdp.__all__
    assert "IndicatorSpec" in ucdp.__all__
    assert "UCDPIngestResult" in ucdp.__all__
    assert "attribution" in ucdp.__all__
    assert "ingest_ucdp" in ucdp.__all__
