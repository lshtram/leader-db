"""Tests for the Chronicle WDI coverage-cache source loader.

These tests verify the Increment 6 (WDI cache GDP improvement)
contract:

- The cache loader reads ``<INDICATOR>_<YEAR_LO>_<YEAR_HI>.json``
  files and maps the four GDP / GDP-per-capita indicator IDs to
  the canonical WDI narrow schema columns.
- The cache is bounded to 1960-2024: a 2025 record is never
  contributed even when the cache JSON is constructed with one.
- The cache loader filters out World Bank aggregate / regional
  codes so the lookup frame only carries real-country rows.
- The WDI loader merges the cache with the processed parquet
  and lets cache rows win on ``(iso3, year)`` collisions.
- The cache loader is the production code path the runner
  uses (not a test seam); the runner is exercised end-to-end
  through :mod:`leaders_db.chronicle._source_orchestration`.

End-to-end economy-fields tests for the cache live alongside
the existing Maddison-vs-WDI tests in
:mod:`tests.test_chronicle_economy_fields` (see the
``wdi_cache_*`` and ``coverage_metric_*`` tests there).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from leaders_db.chronicle._wdi_cache_source import (
    WDI_CACHE_INDICATOR_TO_COLUMN,
    WORLD_BANK_AGGREGATE_CODES,
    load_wdi_cache_frame,
)
from leaders_db.chronicle.sources import load_wdi_source

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_cache_file(
    directory: Path,
    indicator: str,
    records: list[dict[str, object]],
) -> Path:
    """Write a WDI v2 API JSON file under ``directory``."""
    path = directory / f"{indicator}_1960_2024.json"
    payload = [
        {
            "page": 1, "pages": 1, "per_page": 25000,
            "total": len(records), "sourceid": "2", "lastupdated": "2026-04-08",
        },
        records,
    ]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def _record(iso3: str, year: int, value: float | None) -> dict[str, object]:
    """Build one WDI v2 API record."""
    return {
        "indicator": {"id": "NY.GDP.MKTP.KD", "value": "GDP (constant 2015 US$)"},
        "country": {"id": iso3[:2], "value": iso3},
        "countryiso3code": iso3,
        "date": str(year),
        "value": value,
        "unit": "",
        "obs_status": "",
        "decimal": 0,
    }


# ---------------------------------------------------------------------------
# Indicator map invariants
# ---------------------------------------------------------------------------


def test_indicator_map_covers_documented_gdp_indicators() -> None:
    """The four documented GDP / GDP-per-capita indicators are mapped."""
    assert set(WDI_CACHE_INDICATOR_TO_COLUMN) == {
        "NY.GDP.MKTP.KD",
        "NY.GDP.MKTP.CD",
        "NY.GDP.PCAP.CD",
        "NY.GDP.PCAP.PP.KD",
    }
    assert WDI_CACHE_INDICATOR_TO_COLUMN["NY.GDP.MKTP.KD"] == (
        "wdi_gdp_constant_2015_usd"
    )
    assert WDI_CACHE_INDICATOR_TO_COLUMN["NY.GDP.MKTP.CD"] == (
        "wdi_gdp_current_usd"
    )
    assert WDI_CACHE_INDICATOR_TO_COLUMN["NY.GDP.PCAP.CD"] == (
        "wdi_gdp_per_capita"
    )
    assert WDI_CACHE_INDICATOR_TO_COLUMN["NY.GDP.PCAP.PP.KD"] == (
        "wdi_gdp_per_capita_ppp_constant_2017"
    )


def test_world_bank_aggregate_codes_contains_documented_aggregates() -> None:
    """The aggregate-code denylist includes the documented WBG groups."""
    # Spot-check a handful of the documented aggregates.
    for code in ("WLD", "EAS", "SAS", "SSF", "HIC", "LIC"):
        assert code in WORLD_BANK_AGGREGATE_CODES


# ---------------------------------------------------------------------------
# Cache loader semantics
# ---------------------------------------------------------------------------


def test_load_wdi_cache_frame_returns_empty_when_dir_missing(
    tmp_path: Path,
) -> None:
    """A missing cache directory yields an empty frame, not a raise."""
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path / "does_not_exist",
        iso3_scope=("USA",),
    )
    assert frame.empty
    assert "iso3" in frame.columns
    assert "year" in frame.columns


def test_load_wdi_cache_frame_reads_gdp_indicators(
    tmp_path: Path,
) -> None:
    """GDP and GDP-per-capita cache files contribute the right columns."""
    _write_cache_file(
        tmp_path, "NY.GDP.MKTP.KD",
        [
            _record("USA", 2024, 22_568_462_768_174.3),
            _record("USA", 2023, 21_955_252_291_273.6),
        ],
    )
    _write_cache_file(
        tmp_path, "NY.GDP.PCAP.CD",
        [
            {
                "indicator": {"id": "NY.GDP.PCAP.CD", "value": "GDP per capita"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA", "date": "2024",
                "value": 84_534.04, "unit": "", "obs_status": "", "decimal": 0,
            },
        ],
    )
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=("USA",),
    )
    assert sorted(frame["iso3"].unique()) == ["USA"]
    assert sorted(frame["year"].unique()) == [2023, 2024]
    # Constant 2015 USD and per-capita both contribute to the
    # same row for 2024.
    row_2024 = frame.loc[
        (frame["iso3"] == "USA") & (frame["year"] == 2024)
    ].iloc[0]
    assert row_2024["wdi_gdp_constant_2015_usd"] == 22_568_462_768_174.3
    assert row_2024["wdi_gdp_per_capita"] == 84_534.04
    # 2023 has GDP constant-2015-USD but not the per-capita
    # value; the per-capita cell is empty (NaN / NA).
    row_2023 = frame.loc[
        (frame["iso3"] == "USA") & (frame["year"] == 2023)
    ].iloc[0]
    assert row_2023["wdi_gdp_constant_2015_usd"] == 21_955_252_291_273.6
    assert pd.isna(row_2023["wdi_gdp_per_capita"])


def test_load_wdi_cache_frame_filters_aggregates(
    tmp_path: Path,
) -> None:
    """World Bank aggregate / regional codes are filtered out."""
    _write_cache_file(
        tmp_path, "NY.GDP.MKTP.KD",
        [
            _record("AFE", 2024, 1_104_192_151_938.79),  # Africa Eastern and Southern
            _record("WLD", 2024, 100_000_000_000_000.0),  # World
            _record("USA", 2024, 22_568_462_768_174.3),
        ],
    )
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=(),
    )
    isos = set(frame["iso3"].unique())
    assert isos == {"USA"}


def test_load_wdi_cache_frame_drops_null_and_out_of_window_rows(
    tmp_path: Path,
) -> None:
    """Null values, non-integer years, and out-of-window years are dropped.

    The cache contract is exact-year-only: rows whose ``value`` is
    null, whose ``date`` is not an integer, or whose year is
    outside the documented 1960-2024 window are NOT contributed.
    This is the defense-in-depth that prevents 2025/2026 rows
    from leaking into the WDI frame even if a future cache
    carries them.
    """
    _write_cache_file(
        tmp_path, "NY.GDP.MKTP.KD",
        [
            _record("USA", 2024, 22_568_462_768_174.3),
            _record("USA", 2025, 23_000_000_000_000.0),  # out of window
            _record("USA", 2026, 24_000_000_000_000.0),  # out of window
            _record("USA", 2022, None),                   # null
            {
                "indicator": {"id": "NY.GDP.MKTP.KD", "value": "GDP (constant 2015 US$)"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA",
                "date": "twentytwentyfour",               # not an int
                "value": 1.0, "unit": "", "obs_status": "", "decimal": 0,
            },
            _record("USA", 1959, 1_000_000.0),             # before window
        ],
    )
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=("USA",),
    )
    years = sorted(frame["year"].unique())
    assert years == [2024]


def test_load_wdi_cache_frame_honors_iso3_scope(
    tmp_path: Path,
) -> None:
    """An ``iso3_scope`` filter narrows the frame."""
    _write_cache_file(
        tmp_path, "NY.GDP.MKTP.KD",
        [
            _record("USA", 2024, 22_568_462_768_174.3),
            _record("FRA", 2024, 2_900_000_000_000.0),
            _record("IND", 2024, 3_500_000_000_000.0),
        ],
    )
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=("USA", "FRA"),
    )
    assert set(frame["iso3"].unique()) == {"USA", "FRA"}


def test_load_wdi_cache_frame_ignores_unrecognized_indicator(
    tmp_path: Path,
) -> None:
    """Files whose indicator is not in the documented map are ignored.

    The cache dir also carries population / literacy / etc.
    files (e.g. ``SP.POP.TOTL_1960_2024.json``). The loader
    only contributes GDP / GDP-per-capita indicators; other
    files are silently skipped so the frame stays narrow.
    """
    _write_cache_file(
        tmp_path, "SP.POP.TOTL",
        [_record("USA", 2024, 340_000_000.0)],
    )
    _write_cache_file(
        tmp_path, "NY.GDP.MKTP.KD",
        [_record("USA", 2024, 22_568_462_768_174.3)],
    )
    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=("USA",),
    )
    # The frame only carries the GDP column; population was
    # not requested in this pass.
    assert "wdi_population" not in frame.columns
    assert frame["wdi_gdp_constant_2015_usd"].notna().sum() == 1


# ---------------------------------------------------------------------------
# WDI source loader: cache + parquet merge
# ---------------------------------------------------------------------------


def test_load_wdi_source_merges_cache_with_parquet(
    tmp_path: Path,
) -> None:
    """Cache rows fill gaps the processed parquet does not cover.

    The canonical Stage 2 narrow parquet only contains 2022;
    the cache supplies 2023 and 2024 for the same ISO3. The
    merged frame carries both years and the WDI source tag
    survives.
    """
    # Minimal parquet-like frame: just one (USA, 2022) row.
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_gdp_current_usd": 25_604_848_907_611.0,
                "wdi_gdp_constant_2015_usd": 21_339_074_561_820.0,
                "wdi_gdp_per_capita": 76_657.25,
                "wdi_gdp_per_capita_ppp_constant_2017": 72_679.26,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    # Cache supplies 2023 and 2024 for USA, plus 2024 for GBR.
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    _write_cache_file(
        cache_dir, "NY.GDP.MKTP.KD",
        [
            _record("USA", 2023, 21_955_252_291_273.6),
            _record("USA", 2024, 22_568_462_768_174.3),
            _record("GBR", 2024, 3_320_141_500_000.0),
        ],
    )

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA", "GBR"),
        cache_dir=cache_dir,
    )
    # The merged frame has 4 rows: (USA,2022) parquet +
    # (USA,2023), (USA,2024), (GBR,2024) cache.
    assert len(wdi.frame) == 4
    usa_2022 = wdi.lookup("USA", 2022)
    assert usa_2022.get("gdp_constant_2015_usd") == 21_339_074_561_820.0
    usa_2023 = wdi.lookup("USA", 2023)
    assert usa_2023.get("gdp_constant_2015_usd") == 21_955_252_291_273.6
    usa_2024 = wdi.lookup("USA", 2024)
    assert usa_2024.get("gdp_constant_2015_usd") == 22_568_462_768_174.3
    gbr_2024 = wdi.lookup("GBR", 2024)
    assert gbr_2024.get("gdp_constant_2015_usd") == 3_320_141_500_000.0


def test_load_wdi_source_cache_overrides_parquet_on_collision(
    tmp_path: Path,
) -> None:
    """Cache rows win over parquet rows for the same ``(iso3, year)``.

    The cache is the more recent WDI v2 release; collisions
    are resolved in the cache's favor so the WDI frame always
    carries the most recent observation.
    """
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_gdp_current_usd": 25_000_000_000_000.0,  # old value
                "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # The cache carries a different (more recent) USA 2022 value.
    _write_cache_file(
        cache_dir, "NY.GDP.MKTP.KD",
        [_record("USA", 2022, 21_339_074_561_820.0)],
    )

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA",),
        cache_dir=cache_dir,
    )
    rows = wdi.lookup("USA", 2022)
    # Cache wins.
    assert rows.get("gdp_constant_2015_usd") == 21_339_074_561_820.0


def test_load_wdi_source_works_without_cache(
    tmp_path: Path,
) -> None:
    """When ``cache_dir`` is ``None`` the loader behaves as before."""
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_gdp_constant_2015_usd": 21_339_074_561_820.0,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA",),
    )
    assert wdi.frame.shape[0] == 1
    assert wdi.lookup("USA", 2024) == {}


def test_load_wdi_source_handles_missing_cache_dir(
    tmp_path: Path,
) -> None:
    """A non-existent cache directory does not break the loader."""
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_gdp_constant_2015_usd": 21_339_074_561_820.0,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA",),
        cache_dir=tmp_path / "missing_cache_dir",
    )
    assert wdi.frame.shape[0] == 1


# ---------------------------------------------------------------------------
# Regression: parquet columns (including wdi_population) survive a
# cache merge.
# ---------------------------------------------------------------------------


def test_load_wdi_source_preserves_parquet_wdi_population_when_cache_present(
    tmp_path: Path,
) -> None:
    """The processed parquet's ``wdi_population`` survives a cache merge.

    Regression: an earlier implementation narrowed the merged frame
    to GDP / GDPpc columns only, dropping ``wdi_population`` (and
    every other parquet-only column) whenever ``cache_dir`` was
    provided. The contract is that the cache overlays only the GDP
    / GDPpc columns it contributes; every other parquet column is
    preserved. Lookup of ``(USA, 2022)`` must return
    ``population == 333_000_000`` even when the cache carries a
    non-colliding ``(USA, 2023)`` row.
    """
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_population": 333_000_000.0,
                "wdi_gdp_constant_2015_usd": 21_339_074_561_820.0,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # Cache carries a different (USA, 2023) row that does NOT collide
    # with the parquet (USA, 2022) row.
    _write_cache_file(
        cache_dir, "NY.GDP.MKTP.KD",
        [_record("USA", 2023, 21_955_252_291_273.6)],
    )

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA",),
        cache_dir=cache_dir,
    )
    # The merged frame has 2 rows (parquet 2022 + cache 2023) AND
    # carries the parquet's ``wdi_population`` column.
    assert len(wdi.frame) == 2
    assert "wdi_population" in wdi.frame.columns

    # The parquet row keeps its population value through the cache
    # merge.
    parquet_row = wdi.lookup("USA", 2022)
    assert parquet_row.get("population") == 333_000_000.0

    # The cache-only row inherits NA for parquet-only columns; its
    # GDP constant comes from the cache.
    cache_row = wdi.lookup("USA", 2023)
    assert cache_row.get("gdp_constant_2015_usd") == 21_955_252_291_273.6
    assert cache_row.get("population") is None


def test_load_wdi_source_cache_collision_preserves_other_parquet_columns(
    tmp_path: Path,
) -> None:
    """On a ``(iso3, year)`` collision, cache wins on cache columns
    ONLY; every other parquet column (including ``wdi_population``
    and a non-cache GDP field like ``wdi_gdp_current_usd``) is
    preserved from the parquet row.

    Regression: the merge must NOT narrow the merged frame to the
    intersection of cache and parquet columns, and must NOT drop the
    parquet row on collision.
    """
    parquet_path = tmp_path / "wdi.parquet"
    parquet_df = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2022,
                "wdi_population": 333_000_000.0,
                "wdi_gdp_current_usd": 25_000_000_000_000.0,
                "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
            },
        ],
    )
    parquet_df.to_parquet(parquet_path)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # Cache collides on (USA, 2022) with a newer GDP constant value
    # and does NOT carry GDP current or population.
    _write_cache_file(
        cache_dir, "NY.GDP.MKTP.KD",
        [_record("USA", 2022, 21_339_074_561_820.0)],
    )

    wdi = load_wdi_source(
        parquet_path=parquet_path,
        iso3_scope=("USA",),
        cache_dir=cache_dir,
    )
    # Collision is resolved into a single (USA, 2022) row.
    assert len(wdi.frame) == 1
    assert "wdi_population" in wdi.frame.columns

    row = wdi.lookup("USA", 2022)
    # Cache wins on the GDP constant column.
    assert row.get("gdp_constant_2015_usd") == 21_339_074_561_820.0
    # Parquet values for non-cache columns survive.
    assert row.get("population") == 333_000_000.0
    assert row.get("gdp_current_usd") == 25_000_000_000_000.0


# ---------------------------------------------------------------------------
# Production wiring — the runner + source-orchestration
# ---------------------------------------------------------------------------


def test_runner_default_wdi_cache_dir_is_canonical() -> None:
    """The runner's default WDI cache dir is the documented location."""
    from leaders_db.chronicle.runner import default_wdi_cache_dir
    from leaders_db.paths import raw_dir

    assert default_wdi_cache_dir() == raw_dir("world_bank_wdi") / "coverage_cache"


def test_runner_threads_wdi_cache_dir_into_load_wdi_source_via_cli(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Production-path proof: a real-format WDI cache JSON staged
    under ``data/raw/world_bank_wdi/coverage_cache/`` in an isolated
    data lake flows through ``run-country-year-chronicle`` into a
    CSV row whose ``gdp_source == 'wdi'`` and
    ``gdp_source_year_used == '<exact requested year>'``.

    The runner / ``load_all_sources`` thread ``wdi_cache_dir`` into
    ``load_wdi_source``; this test would fail if that wiring were
    broken (e.g. the runner stopped passing ``wdi_cache_dir``,
    because no other source carries 2024 GDP for USA). Maddison /
    Archigos / REIGN / SUN / CShapes are staged at their canonical
    paths so the runner end-to-end produces a well-formed CSV; V-Dem
    is intentionally NOT staged (the existing
    ``test_runner_loads_real_maddison_xlsx_into_chronicle_csv`` test
    already proves V-Dem works in this layout). The WDI processed
    parquet is intentionally NOT staged: the loader falls back to
    cache-only.
    """
    import shutil

    from typer.testing import CliRunner

    from leaders_db.chronicle.constants import SOURCE_TAG_WDI
    from leaders_db.cli import app

    runner = CliRunner()

    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    maddison_dir = isolated_data_lake / "data" / "raw" / "maddison_project"
    archigos_dir = isolated_data_lake / "data" / "raw" / "archigos"
    reign_dir = isolated_data_lake / "data" / "raw" / "reign"
    sun_dir = isolated_data_lake / "data" / "raw" / "soviet_leaders_curated"
    cshapes_dir = isolated_data_lake / "data" / "raw" / "cshapes"
    wdi_cache_dir = (
        isolated_data_lake / "data" / "raw" / "world_bank_wdi" / "coverage_cache"
    )
    for d in (
        maddison_dir, archigos_dir, reign_dir, sun_dir, cshapes_dir,
        wdi_cache_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        fixtures_dir / "maddison_project" / "sample.xlsx",
        maddison_dir / "mpd2023.xlsx",
    )
    shutil.copy2(
        fixtures_dir / "archigos" / "sample.dta",
        archigos_dir / "Archigos_4.1_stata14.dta",
    )
    shutil.copy2(
        fixtures_dir / "reign" / "sample.csv",
        reign_dir / "REIGN_2021_8.csv",
    )
    # SUN and CShapes CSVs are gitignored; copy from the project
    # data lake if present (matches the existing
    # production-wiring test pattern).
    for src_name, dst_dir, dst_name in (
        (
            "soviet_leaders.csv", sun_dir, "soviet_leaders.csv",
        ),
        ("CShapes-2.0.csv", cshapes_dir, "CShapes-2.0.csv"),
    ):
        src = (
            Path(__file__).resolve().parent.parent
            / "data" / "raw" / dst_dir.name / src_name
        )
        if src.is_file():
            shutil.copy2(src, dst_dir / dst_name)

    # Stage a real-format WDI cache JSON under the canonical
    # coverage_cache path. The cache must supply a 2024 USA GDP
    # constant observation so the runner can populate the row's
    # ``gdp`` / ``gdp_source`` / ``gdp_source_year_used``.
    _write_cache_file(
        wdi_cache_dir, "NY.GDP.MKTP.KD",
        [_record("USA", 2024, 22_568_462_768_174.3)],
    )

    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    assert row["iso3"] == "USA"
    assert row["year"] == "2024"
    # Cache-backed WDI row: source tag is the canonical WDI tag and
    # the year used is the exact requested year (NOT a Maddison 2022
    # proxy).
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert row["gdp_source_year_used"] == "2024"
    assert row["gdp"] == "22568462768174"
    assert row["gdp_unit"] == "constant_2015_usd"
    # The runner echoes ``sources_used`` in stdout; wdi must be there
    # so operators can see the cache-backed contribution.
    assert "wdi" in result.stdout


__all__ = [
    "test_indicator_map_covers_documented_gdp_indicators",
]
