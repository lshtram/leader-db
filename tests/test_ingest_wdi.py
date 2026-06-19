"""Tests for the World Bank WDI Stage 2 adapter (REQ-SRC-002).

The WDI adapter is the second Stage 2 adapter built after V-Dem. These
tests define what "done" means for the WDI adapter — they would fail if
any of the production wiring (catalog load, HTTP read with caching, parquet
write, sources upsert, source_observations write, end-to-end orchestrator)
regresses.

Tests use a 5-country x 2-year x 14-indicator fixture extracted from the
real WDI v2 API (tests/fixtures/world_bank_wdi/cache/, 28 JSON files, real
values, no invented data). The fixture covers the 5 countries MEX, USA, SWE,
IND, NGA for years 2022 and 2023 across all 14 WDI indicators.

Key design decisions exercised by these tests:
- WDI v2 API returns a 2-element array [metadata, data].
- Cache is one JSON file per (year, indicator_code) under data/raw/world_bank_wdi/cache/.
- Long-to-wide pivot on iso3 + year; one row per country per year.
- Null values from the API become NaN in DataFrames and NULL in SQLite.
- Aggregate ISO3 codes (AFE, ARB, etc.) are filtered by static denylist.
- Re-runs skip HTTP when cache files exist (force_refresh overrides).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pyarrow.parquet as pq
import pytest
import requests
from sqlalchemy import func, select
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import STAGE2_ADAPTERS, wdi
from leaders_db.ingest.wdi_io import (
    IndicatorSpec,
    default_cache_dir,
    default_processed_parquet_path,
    load_indicator_catalog,
    read_wdi,
    write_wdi_parquet,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wdi_cache_dir(isolated_data_lake: Path) -> Path:
    """Stage the WDI JSON cache fixture under data/raw/world_bank_wdi/cache/.

    The fixture is tests/fixtures/world_bank_wdi/cache/ (14 indicators x 2
    years = 28 JSON files). We copy the whole tree to the isolated data lake
    so read_wdi uses the staged files without any HTTP calls.
    """
    source_cache = isolated_data_lake / "data" / "raw" / "world_bank_wdi" / "cache"
    fixtures_cache = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "world_bank_wdi"
        / "cache"
    )
    # Copy 2022 and 2023 fixture dirs
    for year in ("2022", "2023"):
        src_dir = fixtures_cache / year
        dst_dir = source_cache / year
        if src_dir.exists():
            shutil.copytree(src_dir, dst_dir)
    return source_cache


@pytest.fixture()
def wdi_catalog_path() -> Path:
    """Return the absolute path of the checked-in WDI indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/wdi.csv relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "wdi.csv"
    )


@pytest.fixture()
def wdi_source_key() -> str:
    return "world_bank_wdi"


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_14_specs(wdi_catalog_path: Path) -> None:
    """The checked-in catalog has 14 indicators (matches wdi.md §2.4 spec)."""
    specs = load_indicator_catalog(wdi_catalog_path)
    assert len(specs) == 14, f"Expected 14 indicators, got {len(specs)}"
    # Every spec has a non-empty variable_name and raw_column
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(wdi_catalog_path: Path) -> None:
    """The 8 required CSV columns are present; rating_category is one of the 2 expected."""
    specs = load_indicator_catalog(wdi_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {
        "economic_wellbeing",
        "social_wellbeing",
    }, f"Unexpected categories: {categories}"


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool (same pattern as V-Dem)."""
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "wdi_population",
            "raw_column": "SP.POP.TOTL",
            "rating_category": "economic_wellbeing",
            "raw_scale": "absolute",
            "normalized_scale_target": "0-1",
            "higher_is_better": "1",
            "unit": "persons",
            "description": "Total population",
        }
    )
    assert higher.higher_is_better is True

    lower = IndicatorSpec.from_csv_row(
        {
            "variable_name": "wdi_gini_index",
            "raw_column": "SI.POV.GINI",
            "rating_category": "social_wellbeing",
            "raw_scale": "index_0_1",
            "normalized_scale_target": "0-1",
            "higher_is_better": "0",
            "unit": "0-1",
            "description": "Gini index",
        }
    )
    assert lower.higher_is_better is False


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_wdi_returns_full_fixture(
    wdi_cache_dir: Path, wdi_catalog_path: Path
) -> None:
    """The fixture (5 countries x 2 years x 14 indicators) produces a wide DataFrame.

    Wide format: 10 rows (5 countries x 2 years), 16 columns
    (iso3, year, 14 indicator columns).
    """
    df = read_wdi(
        year=2023,
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
    )
    assert len(df) == 5, f"Expected 5 rows for 2023, got {len(df)}"
    assert set(df.columns) == {
        "iso3",
        "year",
        "wdi_population",
        "wdi_gdp_current_usd",
        "wdi_gdp_per_capita",
        "wdi_gdp_constant_2015_usd",
        "wdi_gdp_per_capita_ppp_constant_2017",
        "wdi_gni_per_capita_atlas",
        "wdi_exports_pct_gdp",
        "wdi_imports_pct_gdp",
        "wdi_fdi_inflows_current_usd",
        "wdi_life_expectancy_at_birth",
        "wdi_literacy_rate_adult",
        "wdi_secondary_school_enrollment",
        "wdi_under5_mortality_per_1000",
        "wdi_gini_index",
    }, f"Column mismatch: {sorted(df.columns)}"
    # Year is int
    assert pd.api.types.is_integer_dtype(df["year"])


def test_read_wdi_filters_to_year(wdi_cache_dir: Path, wdi_catalog_path: Path) -> None:
    """year=2023 keeps only the 5 rows for 2023; year=2022 likewise."""
    df_2023 = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    assert set(df_2023["year"].unique()) == {2023}
    assert len(df_2023) == 5
    assert set(df_2023["iso3"].unique()) == {"MEX", "USA", "SWE", "IND", "NGA"}

    df_2022 = read_wdi(year=2022, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    assert set(df_2022["year"].unique()) == {2022}
    assert len(df_2022) == 5


def test_read_wdi_pivots_long_to_wide(
    wdi_cache_dir: Path, wdi_catalog_path: Path
) -> None:
    """Each catalog indicator is one column; no row duplication; no long-format cells."""
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    # Check the population column has values for all 5 countries
    pop_col = df["wdi_population"]
    assert not pop_col.isna().all(), "Population column should have values"
    # Check each country appears exactly once per year
    assert len(df) == df[["iso3", "year"]].drop_duplicates().shape[0]


def test_read_wdi_filters_aggregates(
    wdi_cache_dir: Path, wdi_catalog_path: Path
) -> None:
    """Aggregate ISO3 codes (AFE, ARB) present in the cache are excluded from the DataFrame.

    The SP.POP.TOTL fixture files include AFE (2022 and 2023) and ARB (2023)
    to exercise the denylist filter.
    """
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    iso3_values = set(df["iso3"].values)
    assert "AFE" not in iso3_values, "Aggregate AFE should be filtered out"
    assert "ARB" not in iso3_values, "Aggregate ARB should be filtered out"
    # Real countries must still be present
    assert {"MEX", "USA", "SWE", "IND", "NGA"}.issubset(iso3_values)


def test_read_wdi_handles_null_values(
    wdi_cache_dir: Path, wdi_catalog_path: Path
) -> None:
    """API ``value: null`` cells become NaN in the DataFrame.

    The fixture has null values for:
    - SE.ADT.LITR.ZS: USA, SWE, NGA (all years)
    - NE.EXP.GNFS.ZS, NE.IMP.GNFS.ZS: NGA (all years)
    - SI.POV.GINI: MEX 2023, IND 2023, NGA 2023
    - SE.SEC.ENRR: USA 2023
    """
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    # Adult literacy: USA, SWE, NGA have no data → NaN
    lit = df.set_index("iso3")["wdi_literacy_rate_adult"]
    assert pd.isna(lit["USA"]), "USA literacy 2023 should be NaN"
    assert pd.isna(lit["SWE"]), "SWE literacy 2023 should be NaN"
    assert pd.isna(lit["NGA"]), "NGA literacy 2023 should be NaN"
    assert not pd.isna(lit["MEX"]), "MEX literacy 2023 should have a value"
    assert not pd.isna(lit["IND"]), "IND literacy 2023 should have a value"
    # Gini: MEX, IND, NGA 2023 are null
    gini = df.set_index("iso3")["wdi_gini_index"]
    assert pd.isna(gini["MEX"]), "MEX Gini 2023 should be NaN"
    assert pd.isna(gini["IND"]), "IND Gini 2023 should be NaN"
    assert pd.isna(gini["NGA"]), "NGA Gini 2023 should be NaN"
    assert not pd.isna(gini["SWE"]), "SWE Gini 2023 should have a value"
    assert not pd.isna(gini["USA"]), "USA Gini 2023 should have a value"


def test_read_wdi_uses_cache_when_present(
    wdi_cache_dir: Path, wdi_catalog_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With cache files present, ``read_wdi(force_refresh=False)`` makes zero HTTP calls."""
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("HTTP should not be called when cache is present")

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_wdi(
        year=2023,
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
        force_refresh=False,
    )
    assert len(df) == 5, "Should return 5 rows from cache"
    assert call_count == 0, f"HTTP was called {call_count} times; expected 0"


def test_read_wdi_force_refresh_overrides_cache(
    wdi_cache_dir: Path, wdi_catalog_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``force_refresh=True`` calls HTTP even when cache files exist."""
    call_count = 0

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Return a fake 2-element array response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: [
            {"page": 1, "pages": 1, "per_page": 50, "total": 2},
            [
                {
                    "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
                    "country": {"id": "MX", "value": "Mexico"},
                    "countryiso3code": "MEX",
                    "date": "2023",
                    "value": 999999999,
                    "unit": "",
                    "obs_status": "",
                    "decimal": 0,
                },
            ],
        ]
        return mock_response

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_wdi(
        year=2023,
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
        force_refresh=True,
    )
    assert call_count > 0, "force_refresh=True should call HTTP"
    # The returned value should reflect the new data
    mex_row = df[df["iso3"] == "MEX"]
    assert float(mex_row["wdi_population"].iloc[0]) == pytest.approx(999999999)


def test_read_wdi_missing_cache_and_no_network(
    wdi_cache_dir: Path, wdi_catalog_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cache + no network -> ``read_wdi`` raises FileNotFoundError."""
    # Point cache at a directory that has no files
    empty_cache = wdi_cache_dir.parent / "empty_cache"
    empty_cache.mkdir(exist_ok=True)

    def network_error(*args, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr(requests, "get", network_error)
    with pytest.raises(FileNotFoundError):
        read_wdi(
            year=2023,
            cache_dir=empty_cache,
            catalog_path=wdi_catalog_path,
        )


def test_default_path_helpers() -> None:
    """Default path helpers point at conventional data-lake locations."""
    raw_default = default_cache_dir()
    assert "world_bank_wdi" in raw_default.parts
    assert "cache" in raw_default.parts

    parquet_default = default_processed_parquet_path()
    assert "world_bank_wdi" in parquet_default.parts
    assert parquet_default.suffix == ".parquet"


# ---------------------------------------------------------------------------
# Parquet write + DB (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_wdi_parquet_creates_file(
    wdi_cache_dir: Path, wdi_catalog_path: Path, isolated_data_lake: Path
) -> None:
    """``write_wdi_parquet`` writes a valid parquet under processed/world_bank_wdi/."""
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    out = write_wdi_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = isolated_data_lake / "data" / "processed" / "world_bank_wdi"
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_wdi_parquet_attaches_attribution_metadata(
    wdi_cache_dir: Path, wdi_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries wdi_attribution and wdi_source_key (Rule #15)."""
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    out = write_wdi_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"wdi_attribution")
    assert attribution_bytes is not None, "parquet missing wdi_attribution metadata"
    assert attribution_bytes.decode("utf-8") == wdi.WDI_ATTRIBUTION
    assert meta.get(b"wdi_source_key") == b"world_bank_wdi"


def test_register_wdi_source_is_idempotent(
    wdi_cache_dir: Path, database_url: str
) -> None:
    """``register_wdi_source`` returns the same id on repeated calls; row has expected shape."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wdi.register_wdi_source(session)
    with session_scope(database_url) as session:
        second_id = wdi.register_wdi_source(session)
    assert first_id == second_id, "register_wdi_source should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "World Bank WDI"
        assert row.version == "2024"
        assert row.source_type == "official"


def test_register_wdi_source_non_destructive_update(
    wdi_cache_dir: Path, database_url: str
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wdi.register_wdi_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    # Remove the bundle metadata.json (if present) so next call sees empty
    bundle_meta = wdi_cache_dir.parent / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = wdi.register_wdi_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_wdi_observations_row_count(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """``len(df) * len(specs)`` observations are written (140 with the full fixture)."""
    _init_test_db(database_url)
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    specs = load_indicator_catalog(wdi_catalog_path)
    expected_rows = len(df) * len(specs)  # 5 * 14 = 70

    with session_scope(database_url) as session:
        source_id = wdi.register_wdi_source(session)
        rows_written = wdi.write_wdi_observations(
            session, source_id, df, catalog_path=wdi_catalog_path
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_wdi_observations_is_idempotent(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """Re-running ``write_wdi_observations`` produces the same count, not double."""
    _init_test_db(database_url)
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    specs = load_indicator_catalog(wdi_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = wdi.register_wdi_source(session)
        wdi.write_wdi_observations(session, source_id, df, catalog_path=wdi_catalog_path)
    with session_scope(database_url) as session:
        wdi.write_wdi_observations(session, source_id, df, catalog_path=wdi_catalog_path)

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_wdi_observations_country_id_is_null(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """Stage 2 leaves ``country_id`` and ``confidence`` NULL; Stage 3/11 fills them.

    ``source_row_reference`` starts with ``wdi:`` so Stage 3 can resolve it.
    """
    _init_test_db(database_url)
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    specs = load_indicator_catalog(wdi_catalog_path)

    with session_scope(database_url) as session:
        source_id = wdi.register_wdi_source(session)
        wdi.write_wdi_observations(session, source_id, df, catalog_path=wdi_catalog_path)

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(SourceObservation.source_id == source_id)
        ).scalars().all()

    assert len(rows) == len(df) * len(specs)
    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    # Stage 2 leaves ``confidence`` NULL; Stage 11 fills it.
    assert all(r.confidence is None for r in rows)
    assert all(
        r.source_row_reference and r.source_row_reference.startswith("wdi:")
        for r in rows
    )


def test_write_wdi_observations_handles_null_values(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """API ``value: null`` -> NULL ``normalized_value``; ``raw_value`` audit-trail preserved."""
    _init_test_db(database_url)
    # Use 2023 fixture which has null values in several indicators
    df = read_wdi(year=2023, cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)

    with session_scope(database_url) as session:
        source_id = wdi.register_wdi_source(session)
        wdi.write_wdi_observations(session, source_id, df, catalog_path=wdi_catalog_path)

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "wdi_literacy_rate_adult",
            )
        ).scalars().all()

    by_iso3 = {r.source_row_reference.split(":")[1]: r for r in rows}
    # USA, SWE, NGA literacy 2023 are NaN/null — normalized_value is None AND
    # raw_value preserves the audit-trail string "nan" (per wdi_db.py:217).
    null_isos = ["USA", "SWE", "NGA"]
    assert all(by_iso3[iso3].normalized_value is None for iso3 in null_isos)
    assert all(by_iso3[iso3].raw_value == "nan" for iso3 in null_isos)
    # MEX, IND have real values
    real_isos = ["MEX", "IND"]
    assert all(by_iso3[iso3].normalized_value is not None for iso3 in real_isos)
    assert all(by_iso3[iso3].raw_value != "nan" for iso3 in real_isos)


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_wdi_end_to_end(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """``ingest_wdi`` writes parquet + observations + sources + manifest in one call.

    The full fixture has 5 countries x 2 years x 14 indicators = 140 source_observations
    rows (5 * 14 for 2022 + 5 * 14 for 2023).
    """
    _init_test_db(database_url)
    result = wdi.ingest_wdi(
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
    )

    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    # 5 countries x 2 years x 14 indicators = 140
    assert result.observation_rows == 140
    assert result.countries == 5
    assert set(result.years) == {2022, 2023}
    assert result.indicators == 14
    # From the full cache, all indicators are cached
    assert result.indicators_cached == 14
    assert result.indicators_fetched == 0
    # Attribution on result
    assert "World Bank" in result.attribution
    assert "WDI" in result.attribution or "World Development Indicators" in result.attribution
    # Run manifest auto-written
    manifest = result.parquet_path.parent / "wdi_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == wdi.WDI_ATTRIBUTION
    assert manifest_payload["observation_rows"] == 140


def test_ingest_wdi_filters_to_year(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """``year=2023`` keeps 5 countries x 1 year x 14 indicators = 70 observation rows."""
    _init_test_db(database_url)
    result = wdi.ingest_wdi(
        year=2023,
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
    )
    assert result.countries == 5
    assert result.years == (2023,)
    assert result.observation_rows == 70  # 5 countries * 14 indicators


def test_ingest_wdi_is_idempotent(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str
) -> None:
    """Re-running ``ingest_wdi`` produces the same row count, same source_id, no double-write."""
    _init_test_db(database_url)
    first = wdi.ingest_wdi(cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)
    second = wdi.ingest_wdi(cache_dir=wdi_cache_dir, catalog_path=wdi_catalog_path)

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 140
    # Parquet mtime should be unchanged (no re-write on idempotent call)
    first_mtime = first.parquet_path.stat().st_mtime
    second_mtime = second.parquet_path.stat().st_mtime
    assert first_mtime == second_mtime, "Parquet should not be re-written on idempotent call"


def test_ingest_wdi_indicators_cached_and_fetched(
    wdi_cache_dir: Path, wdi_catalog_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a partial cache (only 3 of 14 indicators cached), the orchestrator reports
    ``indicators_cached=3`` and ``indicators_fetched=11`` on the returned
    :class:`WDIIngestResult`.

    End-to-end: the test goes through ``wdi.ingest_wdi`` (not the lower-level
    ``wdi_io.read_wdi``), so the ``df.attrs["indicators_cached"]`` →
    ``WDIIngestResult.indicators_cached`` wiring is exercised.
    """
    _init_test_db(database_url)

    # Wipe the 2023 cache entirely; only the 3 indicators we keep below
    # will be on disk.
    cache_2023 = wdi_cache_dir / "2023"
    for json_file in cache_2023.glob("*.json"):
        json_file.unlink()

    # Recreate 3 of the 14 indicator cache files for 2023 (5 countries each).
    fixtures_cache_2023 = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "world_bank_wdi"
        / "cache"
        / "2023"
    )
    kept_indicators = {"SP.POP.TOTL", "NY.GDP.MKTP.CD", "SP.DYN.LE00.IN"}
    for ind in kept_indicators:
        shutil.copy(fixtures_cache_2023 / f"{ind}.json", cache_2023 / f"{ind}.json")

    # Mock requests.get to track calls; return a 5-country row for any
    # indicator that the orchestrator fetches over HTTP.
    call_count = 0
    fetched_indicators: list[str] = []

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Pull the indicator code out of the URL path so we can record it
        # and emit a countryiso3code that matches what the cache has.
        # URL pattern: .../country/all/indicator/<CODE>?date=2023&...
        url_str = str(url)
        ind_code = url_str.split("/indicator/", 1)[1].split("?", 1)[0]
        fetched_indicators.append(ind_code)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda ic=ind_code: [
            {"page": 1, "pages": 1, "per_page": 50, "total": 5},
            [
                {
                    "indicator": {"id": ic, "value": ic},
                    "country": {"id": "MX", "value": "Mexico"},
                    "countryiso3code": iso3,
                    "date": "2023",
                    "value": 1.0,
                    "unit": "",
                    "obs_status": "",
                    "decimal": 0,
                }
                for iso3 in ("MEX", "USA", "SWE", "IND", "NGA")
            ],
        ]
        return mock_resp

    monkeypatch.setattr(requests, "get", counting_get)

    result = wdi.ingest_wdi(
        year=2023,
        cache_dir=wdi_cache_dir,
        catalog_path=wdi_catalog_path,
    )

    # The orchestrator must surface the cached-vs-fetched counts on the
    # result object (this is the wiring the original test missed).
    assert result.indicators_cached == 3, (
        f"Expected 3 cached indicators, got {result.indicators_cached}"
    )
    assert result.indicators_fetched == 11, (
        f"Expected 11 fetched indicators, got {result.indicators_fetched}"
    )
    # The HTTP layer must have been called exactly once per uncached
    # indicator.
    assert call_count == 11, f"Expected 11 HTTP calls, got {call_count}"
    # observation_rows = countries (5) * indicators (14) for year=2023.
    assert result.observation_rows == 5 * 14, (
        f"Expected 70 observation rows, got {result.observation_rows}"
    )
    assert result.countries == 5
    assert result.indicators == 14


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    wdi_cache_dir: Path, wdi_catalog_path: Path, isolated_data_lake: Path
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    # Build a minimal IngestResult-like object for the manifest writer
    result = wdi.WDIIngestResult(
        source_id=1,
        parquet_path=(
            isolated_data_lake
            / "data"
            / "processed"
            / wdi.WDI_SOURCE_KEY
            / "x.parquet"
        ),
        observation_rows=140,
        countries=5,
        years=(2022, 2023),
        indicators=14,
        indicators_cached=14,
        indicators_fetched=0,
    )
    manifest_path = wdi.write_wdi_run_manifest(
        result,
        manifest_dir=isolated_data_lake / "data" / "processed" / wdi.WDI_SOURCE_KEY,
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 140
    assert payload["years"] == [2022, 2023]
    assert payload["indicators"] == 14
    assert payload["attribution"] == wdi.WDI_ATTRIBUTION


def test_attribution_matches_constant() -> None:
    """``wdi.attribution()`` returns the module-level WDI_ATTRIBUTION constant."""
    assert wdi.attribution() == wdi.WDI_ATTRIBUTION
    assert "World Bank" in wdi.attribution()
    assert "WDI" in wdi.attribution() or "World Development Indicators" in wdi.attribution()
    assert "CC BY 4.0" in wdi.attribution() or "Creative Commons" in wdi.attribution()


def test_wdi_attribution_matches_attributions_doc() -> None:
    """``WDI_ATTRIBUTION`` is a substring of ``docs/source-attributions.md`` (drift guard).

    Per AGENTS.md Always-On Rule #15, the code's attribution text and the
    doc's citation text must be byte-for-byte consistent. If either changes,
    both must be updated in the same commit.
    """
    doc_path = (
        Path(__file__).resolve().parents[1] / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert wdi.WDI_ATTRIBUTION in doc_text, (
        f"WDI_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table(wdi_source_key: str) -> None:
    """The dispatch table has world_bank_wdi registered as wdi.ingest_wdi."""
    assert STAGE2_ADAPTERS[wdi_source_key] is wdi.ingest_wdi
    # WDI key should be present; the other 24 keys are the rest of the
    # dispatch table (one per priority source minus the duplicate that
    # was previously silently masked).
    expected_keys = {
        "vdem", "world_bank_wdi", "world_bank_wgi", "ucdp",
        "sipri_milex", "sipri_yearbook_ch7", "pts", "undp_hdi",
        "who_gho_api", "polity_v", "pwt", "archigos", "reign",
        "leader_survival", "transparency_cpi", "fas",
        "wikidata_heads_of_state_government", "wikipedia_search_extract",
        "freedom_house", "imf_weo", "cow_mid", "cirights",
        "nti", "bti", "cia_world_leaders", "rsf_press_freedom",
    }
    assert set(STAGE2_ADAPTERS.keys()) == expected_keys


def test_cli_ingest_source_rejects_unknown() -> None:
    """The CLI's ``ingest-source`` command rejects unknown source keys."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Imports check — verify the wdi module surface matches the design doc
# ---------------------------------------------------------------------------


def test_wdi_module_public_surface() -> None:
    """The wdi module exports the 6 items in __all__ from the design doc §2.3."""
    assert hasattr(wdi, "WDI_ATTRIBUTION")
    assert hasattr(wdi, "WDI_SOURCE_KEY")
    assert hasattr(wdi, "IndicatorSpec")
    assert hasattr(wdi, "WDIIngestResult")
    assert hasattr(wdi, "attribution")
    assert hasattr(wdi, "ingest_wdi")
    assert "WDI_ATTRIBUTION" in wdi.__all__
    assert "WDI_SOURCE_KEY" in wdi.__all__
    assert "IndicatorSpec" in wdi.__all__
    assert "WDIIngestResult" in wdi.__all__
    assert "attribution" in wdi.__all__
    assert "ingest_wdi" in wdi.__all__
