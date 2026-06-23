"""Tests for the UNDP HDI Stage 2 adapter (REQ-SRC-002).

The UNDP HDI adapter is the eighth Stage 2 adapter built after V-Dem,
WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, and PTS. These
tests define what "done" means for the UNDP HDI adapter — they
would fail if any of the production wiring (catalog load, latin-1
CSV read, wide-to-long UNPIVOT, source registration,
source_observations write, end-to-end orchestrator, dispatch table
wiring) regresses.

UNDP HDI is structurally distinct from every prior adapter:

- It is the first wide-format CSV (1,076 columns, 207 countries,
  one row per country) and the only one that needs a wide-to-long
  ``pd.melt`` to produce Stage 2 observations.
- It is the first adapter that reads ``latin-1`` (UTF-8 fails on
  country names with diacritics such as ``Côte d'Ivoire``).
- It is the first adapter that targets the ``social_wellbeing``
  rating category exclusively (5 in-scope indicators: HDI, life
  expectancy, expected years of schooling, mean years of schooling,
  GNI per capita).
- It uses a 1-year-gap proxy: the target year 2023 is mapped to 2022
  (the latest available data) per the CIRIGHTS and Leader Survival
  pattern.

Tests use a 4-country x 2-year x 5-prefix fixture at
``tests/fixtures/undp_hdi/sample.csv`` (real-format UNDP HDI CSV,
real values sliced from the live 1.9 MB bundle with
``build_sample_csv.py``, no invented data). The fixture covers:

- Mexico (MEX, HDI=0.781, LAC, High)
- United States (USA, HDI=0.927, NaN region, Very High) — the
  ``region=NaN`` is real (the live bundle has 55 such rows); the
  adapter must preserve + warn per architecture §6.
- Nigeria (NGA, HDI=0.548, SSA, Low) — has 2 empty in-scope cells
  (``hdi_1990``, ``mys_1990``) so the empty-cell drop path is
  exercised.
- Côte d'Ivoire (CIV, HDI=0.534, SSA, Low) — the diacritic test
  case; the file is latin-1 encoded and UTF-8 would fail.

The fixture preserves the wide ``{prefix}_{year}`` column shape
(static columns first, then 10 ``{prefix}_{year}`` columns), and the
adapter's UNPIVOT produces a narrow frame with one row per
``(iso3, year, prefix)`` triple.

Key design decisions exercised by these tests:
- ``iso3`` is the primary key. ``country`` is preserved verbatim
  (including diacritics). ``source_row_reference`` is
  ``"undp_hdi:<iso3>"`` (e.g., ``"undp_hdi:USA"``).
- ``country_id`` is NULL at Stage 2; ``confidence`` is NULL at
  Stage 2. Stage 3 fills ``country_id``; Stage 11 fills confidence.
- Year 2023 → 2022 proxy: when the caller asks for ``year=2023``,
  the adapter reads 2022 data and records the proxy in the manifest.
- The 5 in-scope prefixes are catalog-driven; the catalog is the
  single source of truth (``src/leaders_db/ingest/catalogs/undp_hdi.csv``).
- The Stage 2 end-to-end row count for the fixture (4 countries x
  2 years x 5 prefixes - 2 empty cells - 1 year filter = 37
  observations for one year, 38 for two years) is asserted
  explicitly. The real-file smoke asserts the 2022 potential of
  roughly 1,035 rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
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
from leaders_db.ingest import STAGE2_ADAPTERS

# Try importing the UNDP HDI modules; they do not exist yet so tests
# fail gracefully (the import block sets the names to ``None`` and
# every test that needs them asserts ``is not None`` first).
try:
    from leaders_db.ingest import undp_hdi, undp_hdi_io
    from leaders_db.ingest.undp_hdi import (
        UNDP_HDI_ATTRIBUTION,
        UNDP_HDI_SOURCE_KEY,
        IndicatorSpec,
        UndpHdiIngestResult,
        attribution,
        build_undp_hdi_observations,
        default_csv_path,
        default_processed_parquet_path,
        ingest_undp_hdi,
        load_undp_hdi_catalog,
        read_undp_hdi_csv,
        register_undp_hdi_source,
        write_undp_hdi_observations,
        write_undp_hdi_parquet,
        write_undp_hdi_run_manifest,
    )
except ImportError:
    # Modules do not exist yet; tests will fail with appropriate
    # errors when they assert against these names.
    undp_hdi = None  # type: ignore[assignment]
    undp_hdi_io = None  # type: ignore[assignment]
    UNDP_HDI_ATTRIBUTION = None  # type: ignore[assignment]
    UNDP_HDI_SOURCE_KEY = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    UndpHdiIngestResult = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    build_undp_hdi_observations = None  # type: ignore[assignment]
    default_csv_path = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    ingest_undp_hdi = None  # type: ignore[assignment]
    load_undp_hdi_catalog = None  # type: ignore[assignment]
    read_undp_hdi_csv = None  # type: ignore[assignment]
    register_undp_hdi_source = None  # type: ignore[assignment]
    write_undp_hdi_observations = None  # type: ignore[assignment]
    write_undp_hdi_parquet = None  # type: ignore[assignment]
    write_undp_hdi_run_manifest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def undp_hdi_csv_dir(isolated_data_lake: Path) -> Path:
    """Stage the UNDP HDI fixture CSV under data/raw/undp_hdi/ in the test lake.

    Also copies the project's real ``metadata.json`` if present, so
    ``register_undp_hdi_source`` exercises the bundle metadata path.
    """
    target = isolated_data_lake / "data" / "raw" / "undp_hdi"
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "undp_hdi"
    shutil.copy2(
        fixtures_dir / "sample.csv",
        target / "HDR23-24_Composite_indices_complete_time_series.csv",
    )

    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / "undp_hdi" / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def undp_hdi_catalog_path() -> Path:
    """Return the absolute path of the checked-in UNDP HDI indicator catalog.

    Lives at ``src/leaders_db/ingest/catalogs/undp_hdi.csv`` relative to
    the project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "undp_hdi.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# §8.1 — Catalog loader (5 tests)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_has_five_specs(
    undp_hdi_catalog_path: Path,
) -> None:
    """The checked-in catalog has exactly 5 indicators (matches undp-hdi.md §3)."""
    assert load_undp_hdi_catalog is not None, "undp_hdi_io module not implemented"
    specs = load_undp_hdi_catalog(undp_hdi_catalog_path)
    assert len(specs) == 5, f"Expected 5 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns_present(
    undp_hdi_catalog_path: Path,
) -> None:
    """The 7 required CSV columns are present and parsed without error.

    The catalog file at ``src/leaders_db/ingest/catalogs/undp_hdi.csv``
    has the columns: ``variable_name, raw_column, category,
    higher_is_better, raw_scale, normalized_scale_target, unit``.
    """
    assert load_undp_hdi_catalog is not None, "undp_hdi_io module not implemented"
    specs = load_undp_hdi_catalog(undp_hdi_catalog_path)
    # Every spec must have the 7 fields populated
    for spec in specs:
        assert spec.variable_name, f"missing variable_name: {spec}"
        assert spec.raw_column, f"missing raw_column: {spec}"
        # ``category`` is the canonical name in the UNDP HDI catalog
        # (per the checked-in file); the other adapters use
        # ``rating_category`` but the UNDP HDI catalog is the source
        # of truth for this adapter.
        assert spec.category, f"missing category: {spec}"
        assert spec.raw_scale, f"missing raw_scale: {spec}"
        assert spec.normalized_scale_target, f"missing normalized_scale_target: {spec}"
        assert spec.unit, f"missing unit: {spec}"
    # All 5 are in social_wellbeing per architecture §3
    categories = {s.category for s in specs}
    assert categories == {"social_wellbeing"}, (
        f"Expected category 'social_wellbeing' for all 5 specs, got {categories}"
    )


def test_load_indicator_catalog_raw_prefixes_match_design(
    undp_hdi_catalog_path: Path,
) -> None:
    """The 5 raw_column values are exactly the 5 in-scope prefixes from §3.

    Order: ``hdi, le, eys, mys, gnipc`` (per the catalog file order).
    """
    assert load_undp_hdi_catalog is not None, "undp_hdi_io module not implemented"
    specs = load_undp_hdi_catalog(undp_hdi_catalog_path)
    raw_columns = [s.raw_column for s in specs]
    assert raw_columns == ["hdi", "le", "eys", "mys", "gnipc"], (
        f"raw_column mismatch: got {raw_columns}"
    )


def test_load_indicator_catalog_higher_is_better_is_true(
    undp_hdi_catalog_path: Path,
) -> None:
    """All 5 indicators have higher_is_better=True (more HDI / life
    expectancy / schooling / income = better wellbeing).
    """
    assert load_undp_hdi_catalog is not None, "undp_hdi_io module not implemented"
    specs = load_undp_hdi_catalog(undp_hdi_catalog_path)
    assert all(s.higher_is_better is True for s in specs), (
        "All UNDP HDI indicators should have higher_is_better=True"
    )
    # Defensive: the CSV uses "1" for True; verify the round-trip
    # handles the "1"/"0" string convention.
    assert IndicatorSpec is not None
    spec = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test",
            "raw_column": "hdi",
            "category": "social_wellbeing",
            "raw_scale": "0-1",
            "normalized_scale_target": "0-10",
            "higher_is_better": "1",
            "unit": "index",
        },
    )
    assert spec.higher_is_better is True
    spec_false = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test",
            "raw_column": "hdi",
            "category": "social_wellbeing",
            "raw_scale": "0-1",
            "normalized_scale_target": "0-10",
            "higher_is_better": "0",
            "unit": "index",
        },
    )
    assert spec_false.higher_is_better is False


def test_load_indicator_catalog_missing_file_raises(
    tmp_path: Path,
) -> None:
    """Missing catalog path raises FileNotFoundError, not a silent empty list."""
    assert load_undp_hdi_catalog is not None, "undp_hdi_io module not implemented"
    with pytest.raises(FileNotFoundError):
        load_undp_hdi_catalog(tmp_path / "does-not-exist.csv")


# ---------------------------------------------------------------------------
# §8.2 — CSV reader (6 tests)
# ---------------------------------------------------------------------------


def test_read_csv_handles_latin_1_with_diacritics(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The CSV reader reads the latin-1 file without error; the
    ``Côte d'Ivoire`` diacritic round-trips correctly.
    """
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"
    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    df = read_undp_hdi_csv(csv_path=csv_path, catalog_path=undp_hdi_catalog_path)
    assert "Côte d'Ivoire" in df["country"].values, (
        "Latin-1 diacritic in 'Côte d'Ivoire' should round-trip; the reader must not use UTF-8."
    )
    assert "USA" in df["iso3"].values


def test_read_csv_missing_csv_raises(
    undp_hdi_catalog_path: Path,
    tmp_path: Path,
) -> None:
    """Missing CSV path raises FileNotFoundError, not a silent empty list."""
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"
    with pytest.raises(FileNotFoundError):
        read_undp_hdi_csv(
            csv_path=tmp_path / "missing.csv",
            catalog_path=undp_hdi_catalog_path,
        )


def test_read_csv_missing_static_column_raises(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    tmp_path: Path,
) -> None:
    """A CSV missing a required static column (e.g. ``hdicode``) raises
    ValueError with an actionable message.
    """
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"
    # Build a CSV missing the ``hdicode`` static column
    bad_csv = tmp_path / "missing_static.csv"
    bad_csv.write_text(
        "iso3,country,region,hdi_2022\nMEX,Mexico,LAC,0.781\n",
        encoding="latin-1",
    )
    with pytest.raises(ValueError):
        read_undp_hdi_csv(
            csv_path=bad_csv,
            catalog_path=undp_hdi_catalog_path,
        )


def test_read_csv_missing_expected_prefix_year_column_raises(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    tmp_path: Path,
) -> None:
    """A CSV missing an expected ``{prefix}_{year}`` column for an
    in-scope catalog prefix raises ValueError.

    Mirrors the WGI "missing sheet" pattern: if the catalog promises
    a prefix (e.g. ``gnipc``) and the CSV does not deliver it, the
    contract is broken.
    """
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"
    # Build a CSV missing the ``gnipc_2022`` column (one of the 10
    # in-scope columns the catalog promises)
    bad_csv = tmp_path / "missing_col.csv"
    bad_csv.write_text(
        "iso3,country,hdicode,region,hdi_1990,hdi_2022,le_1990,le_2022,"
        "eys_1990,eys_2022,mys_1990,mys_2022,gnipc_1990\n"
        "USA,United States,Very High,,0.875,0.927,75.37,78.203,"
        "15.60052013,16.41274071,12.98377037,40920.16756\n",
        encoding="latin-1",
    )
    with pytest.raises(ValueError):
        read_undp_hdi_csv(
            csv_path=bad_csv,
            catalog_path=undp_hdi_catalog_path,
        )


def test_read_csv_warns_on_unknown_region_but_preserves_row(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """A row with an unknown region code (not in the 6 known region
    codes from architecture §2) is preserved in the wide frame and a
    warning is logged.

    The fixture has USA with ``region=NaN`` (real, not invented —
    55 rows in the     live bundle have NaN region) and we add a
    synthetic ``region="X7"`` row via a copy of the fixture to
    exercise the unknown-code warning path explicitly.
    """
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"

    # Build a fixture copy with one synthetic unknown region
    csv_src = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    csv_dst = tmp_path / "with_unknown_region.csv"
    csv_dst.write_bytes(csv_src.read_bytes())

    # Mutate: change MEX's region to an unknown code
    text = csv_dst.read_text(encoding="latin-1")
    text = text.replace("MEX,Mexico,High,LAC,", "MEX,Mexico,High,X7,", 1)
    csv_dst.write_text(text, encoding="latin-1")

    caplog.set_level(logging.WARNING)
    df = read_undp_hdi_csv(csv_path=csv_dst, catalog_path=undp_hdi_catalog_path)

    # Mexico is preserved (the wide frame has 4 countries, all kept)
    assert "Mexico" in df["country"].values
    # A warning was logged mentioning the unknown region
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("X7" in msg for msg in warning_messages), (
        f"Expected a warning mentioning the unknown region 'X7', got: {warning_messages}"
    )


def test_read_csv_warns_on_blank_region_but_preserves_row(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A row with a blank/empty ``region`` (e.g. USA in the real
    bundle) is preserved in the wide frame and a warning is logged.

    Per architecture §6, blank/NaN region values are a soft warning,
    not a hard error: the row is preserved verbatim. The CSV reader
    uses ``keep_default_na=False`` + ``dtype=str`` so blank cells
    survive as empty strings (``""``) rather than NaN; the reader
    must catch both shapes (NaN if the reader config ever changes,
    and the empty-string form produced by the current config).

    The fixture contains a real USA row with an empty region (the
    live HDR 2023-24 bundle has 55 such rows, USA being one of
    them) -- this test exercises that case directly, without
    injecting synthetic mutations.
    """
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"

    caplog.set_level(logging.WARNING)
    df = read_undp_hdi_csv(csv_path=csv_path, catalog_path=undp_hdi_catalog_path)

    # USA is preserved (the row is not dropped just because the
    # region is empty -- per architecture §6).
    assert "USA" in df["iso3"].values, (
        "USA must be preserved in the wide frame even with an empty region"
    )
    # The USA row's region is the empty string (or NaN if the reader
    # config changes); in either case it is not one of the 6 known
    # region codes from architecture §2.
    usa_rows = df[df["iso3"] == "USA"]
    assert len(usa_rows) == 1
    usa_region = usa_rows["region"].iloc[0]
    assert str(usa_region).strip() not in {
        "SA", "ECA", "AS", "SSA", "LAC", "EAP",
    }, f"USA's region is expected to be blank/unknown, got {usa_region!r}"

    # A warning was logged mentioning the blank region.
    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    blank_warnings = [
        msg for msg in warning_messages if "blank" in msg.lower() or "empty" in msg.lower()
    ]
    assert blank_warnings, (
        f"Expected at least one WARNING mentioning a blank/empty region, "
        f"got: {warning_messages}"
    )


def test_read_csv_empty_cells_dropped_at_debug_not_warning(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Empty numeric cells are dropped (not warning-spammed) per §6.

    Nigeria in the fixture has 2 empty in-scope cells (hdi_1990,
    mys_1990). The narrow frame should drop those observations; the
    log should NOT contain WARNING-level messages for the empty
    cells (they are debug-level events per §6).
    """
    assert build_undp_hdi_observations is not None, "undp_hdi_csv module not implemented"
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )

    caplog.set_level(logging.DEBUG)
    caplog.clear()
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )

    # Narrow frame must not include rows for NGA 1990 hdi or NGA 1990 mys
    nga_1990_hdi = narrow_df[
        (narrow_df["iso3"] == "NGA")
        & (narrow_df["year"] == 1990)
        & (narrow_df["variable_name"] == "undp_hdi_hdi")
    ]
    assert len(nga_1990_hdi) == 0, "NGA 1990 hdi was empty; the row should be dropped, not kept"
    nga_1990_mys = narrow_df[
        (narrow_df["iso3"] == "NGA")
        & (narrow_df["year"] == 1990)
        & (narrow_df["variable_name"] == "undp_hdi_mean_years_schooling")
    ]
    assert len(nga_1990_mys) == 0

    # No WARNING-level events for the empty cells (they are
    # debug-level per architecture §6)
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any(
        "NGA" in msg and "1990" in msg and "empty" in msg.lower() for msg in warning_messages
    ), f"Empty cells should be debug-level events, not WARNINGs; got: {warning_messages}"


# ---------------------------------------------------------------------------
# §8.3 — Wide-to-long / narrow frame (7 tests)
# ---------------------------------------------------------------------------


def test_build_observations_unpivots_wide_to_narrow(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """``build_undp_hdi_observations`` returns a narrow DataFrame: one
    row per ``(iso3, year, variable_name)`` triple (UNPIVOT result).
    """
    assert build_undp_hdi_observations is not None, "undp_hdi_csv module not implemented"
    assert read_undp_hdi_csv is not None, "undp_hdi_csv module not implemented"

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )

    # 4 countries x 2 years x 5 prefixes - 2 empty cells = 38 rows
    assert len(narrow_df) == 38, (
        f"Expected 38 narrow rows (4 countries x 2 years x 5 prefixes "
        f"minus 2 empty cells), got {len(narrow_df)}"
    )
    # Each (iso3, year, variable_name) triple appears exactly once
    assert len(narrow_df) == narrow_df[["iso3", "year", "variable_name"]].drop_duplicates().shape[0]


def test_build_observations_parses_prefix_year_correctly(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The ``{prefix}_{year}`` parsing handles a single underscore split.

    For each narrow row, ``variable_name`` is one of the 5 catalog
    variable names and ``year`` is an int.
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )

    expected_variables = {
        "undp_hdi_hdi",
        "undp_hdi_life_expectancy",
        "undp_hdi_expected_years_schooling",
        "undp_hdi_mean_years_schooling",
        "undp_hdi_gni_per_capita",
    }
    assert set(narrow_df["variable_name"].unique()) == expected_variables
    assert set(narrow_df["year"].unique()) == {1990, 2022}


def test_build_observations_drops_year_2022_only_rank_columns(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """Year-2022-only rank/metadata columns (e.g. ``hdi_rank_2022``)
    are dropped during the wide-to-long melt, NOT included as
    variables in the narrow frame.

    The fixture omits those columns to keep the file small, but the
    reader must not pick up ``hdi_rank_2022`` even if it is present.
    We inject one such column into a copy of the fixture and verify
    it does not appear in the narrow frame.
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_src = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"

    # Read the source, add a hdi_rank_2022 column, write back
    df_src = pd.read_csv(csv_src, encoding="latin-1", dtype=str)
    df_src["hdi_rank_2022"] = "1"  # synthetic; will be filtered out
    df_src["gdi_group_2022"] = "1"  # synthetic; will be filtered out
    df_src["gii_rank_2022"] = "1"  # synthetic; will be filtered out
    df_src["rankdiff_hdi_phdi_2022"] = "1"  # synthetic; filtered out
    csv_with_rank = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    df_src.to_csv(csv_with_rank, index=False, encoding="latin-1")

    wide_df = read_undp_hdi_csv(
        csv_path=csv_with_rank,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )

    # None of the synthetic columns should appear as variable_names
    forbidden = {
        "hdi_rank_2022",
        "gdi_group_2022",
        "gii_rank_2022",
        "rankdiff_hdi_phdi_2022",
    }
    assert not (set(narrow_df["variable_name"].unique()) & forbidden), (
        "Year-2022-only rank/metadata columns must be dropped from "
        "the narrow frame, not included as variables"
    )


def test_build_observations_only_catalog_prefixes_appear(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """Only the 5 catalog prefixes appear in the narrow frame; gdi /
    gii / phdi / etc. are not extracted (per architecture §3).
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )

    catalog_prefixes = {"hdi", "le", "eys", "mys", "gnipc"}
    # The set of variable_names must equal the set of catalog
    # variable_names exactly.
    specs = load_undp_hdi_catalog(undp_hdi_catalog_path)
    catalog_variables = {s.variable_name for s in specs}
    assert set(narrow_df["variable_name"].unique()) == catalog_variables, (
        f"Expected variable_names == {catalog_variables}, "
        f"got {set(narrow_df['variable_name'].unique())}"
    )
    # The unused prefix set is "in-scope minus catalog" — there is
    # no overlap; the catalog IS the spec.
    assert catalog_prefixes == {s.raw_column for s in specs}, (
        "raw_column should be the 5 in-scope prefixes"
    )


def test_build_observations_year_column_is_int(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The narrow frame's ``year`` column is int dtype (coerced from
    the ``{prefix}_{year}`` suffix).
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )
    assert pd.api.types.is_integer_dtype(narrow_df["year"])


def test_build_observations_preserves_static_columns(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The 4 static columns (``iso3``, ``country``, ``region``,
    ``hdicode``) are preserved in the narrow frame per architecture §4.
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )
    for col in ("iso3", "country", "region", "hdicode"):
        assert col in narrow_df.columns, f"Missing static column: {col}"
    # Country diacritics preserved
    civ_rows = narrow_df[narrow_df["iso3"] == "CIV"]
    assert all(civ_rows["country"] == "Côte d'Ivoire"), (
        "CIV country name should preserve diacritics in the narrow frame"
    )


def test_build_observations_source_row_reference_format(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The narrow frame carries ``source_row_reference = "undp_hdi:<iso3>"``
    (e.g. ``"undp_hdi:USA"``) per architecture §7.
    """
    assert build_undp_hdi_observations is not None
    assert read_undp_hdi_csv is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )
    assert "source_row_reference" in narrow_df.columns
    # All values must start with "undp_hdi:"
    assert all(ref.startswith("undp_hdi:") for ref in narrow_df["source_row_reference"])
    # Spot-check the format for a known row
    civ_2022_hdi = narrow_df[
        (narrow_df["iso3"] == "CIV")
        & (narrow_df["year"] == 2022)
        & (narrow_df["variable_name"] == "undp_hdi_hdi")
    ]
    assert len(civ_2022_hdi) == 1
    assert civ_2022_hdi["source_row_reference"].iloc[0] == "undp_hdi:CIV"


# ---------------------------------------------------------------------------
# §8.4 — DB writers (6 tests)
# ---------------------------------------------------------------------------


def test_db_writers_register_source_idempotent(
    undp_hdi_csv_dir: Path,
    database_url: str,
) -> None:
    """``register_undp_hdi_source`` returns the same ``id`` on every
    call. The row carries the canonical ``source_name`` and ``version``
    from the architecture.
    """
    assert register_undp_hdi_source is not None, "undp_hdi_db module not implemented"
    _init_test_db(database_url)

    with session_scope(database_url) as session:
        first_id = register_undp_hdi_source(session)
    with session_scope(database_url) as session:
        second_id = register_undp_hdi_source(session)
    assert first_id == second_id, "register_undp_hdi_source should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(select(Source).where(Source.id == first_id)).scalar_one()
        assert row.source_name == "UNDP Human Development Index (HDR 2023-24)"
        assert row.version == "2023-24"
        assert row.source_type == "official"


def test_db_writers_observation_count_matches_non_empty_cells(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """The number of ``source_observations`` rows written equals the
    number of non-empty cells in the narrow frame for the requested year.

    For the full fixture (4 countries x 2 years x 5 prefixes - 2
    empty cells) the count is 38; for a ``year=2022`` filter it is
    20 (4 countries x 5 indicators, all populated for 2022).
    """
    assert ingest_undp_hdi is not None, "undp_hdi module not implemented"
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    # Filter to year=2022 (the real data year)
    result_2022 = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    # 4 countries x 5 indicators, all populated for 2022
    assert result_2022.observation_rows == 20, (
        f"Expected 20 observations for year=2022, got {result_2022.observation_rows}"
    )

    # Full run (both years): 38 rows
    result_full = ingest_undp_hdi(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    assert result_full.observation_rows == 38


def test_db_writers_country_id_and_confidence_are_null(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """``country_id`` and ``confidence`` are NULL for all rows
    (Stage 3 fills ``country_id``; Stage 11 fills ``confidence``).
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )

    with session_scope(database_url) as session:
        rows = (
            session.execute(
                select(SourceObservation).where(
                    SourceObservation.source_id == result.source_id,
                )
            )
            .scalars()
            .all()
        )

    assert all(r.country_id is None for r in rows), (
        "country_id must be NULL for all UNDP HDI rows (Stage 3 fills it)"
    )
    assert all(r.confidence is None for r in rows), (
        "confidence must be NULL for all UNDP HDI rows (Stage 11 fills it)"
    )
    assert all(r.source_row_reference.startswith("undp_hdi:") for r in rows), (
        "source_row_reference must start with 'undp_hdi:'"
    )


def test_db_writers_rerun_is_idempotent(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """Running ``ingest_undp_hdi`` twice with the same year produces
    the same final state (no double-writes).
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    first = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    second = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 20

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == first.source_id,
            )
        ).scalar_one()
    assert count == 20, f"Expected 20 observations after idempotent rerun, got {count}"


def test_db_writers_manifest_records_run_metadata(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """The run manifest JSON captures ``source_key``, ``attribution``,
    ``observation_rows``, ``countries``, ``years``, and the year window
    (with proxy-year semantics when ``year=2023`` is requested).
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    manifest_path = result.parquet_path.parent / "undp_hdi_run_manifest.json"
    assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_key"] == "undp_hdi"
    assert payload["attribution"] == UNDP_HDI_ATTRIBUTION
    assert payload["observation_rows"] == 20
    assert payload["countries"] == 4
    assert 2022 in payload["years"]
    # year_window must be (2022, 2022) for a single-year run
    assert tuple(payload["year_window"]) == (2022, 2022), (
        f"Expected year_window=(2022, 2022) for year=2022, got {tuple(payload['year_window'])}"
    )


def test_db_writers_source_row_reference_uses_iso3(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """Every ``source_observations.source_row_reference`` starts with
    ``"undp_hdi:"`` and the suffix is the ISO3 code (e.g. ``USA``,
    ``MEX``, ``NGA``, ``CIV``).
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )

    with session_scope(database_url) as session:
        refs = (
            session.execute(
                select(SourceObservation.source_row_reference).where(
                    SourceObservation.source_id == result.source_id,
                )
            )
            .scalars()
            .all()
        )

    expected_iso3 = {"MEX", "USA", "NGA", "CIV"}
    for ref in refs:
        assert ref.startswith("undp_hdi:"), f"Bad prefix: {ref}"
        suffix = ref.split(":", 1)[1]
        assert suffix in expected_iso3, f"Unexpected ISO3 suffix: {suffix}"


# ---------------------------------------------------------------------------
# §8.5 — Attribution drift-guard (2 tests)
# ---------------------------------------------------------------------------


def test_undp_hdi_attribution_matches_attributions_doc() -> None:
    """``UNDP_HDI_ATTRIBUTION`` is a substring of
    ``docs/sources/attributions.md`` (drift guard per Rule #15).
    """
    assert UNDP_HDI_ATTRIBUTION is not None, "undp_hdi_io module not implemented"
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "sources/attributions.md"
    doc_text = doc_path.read_text(encoding="utf-8")
    assert UNDP_HDI_ATTRIBUTION in doc_text, (
        f"UNDP_HDI_ATTRIBUTION not found in {doc_path}. Update both in the same commit (Rule #15)."
    )


def test_parquet_metadata_carries_attribution_and_source_key(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
) -> None:
    """The narrow parquet's file-level metadata carries
    ``undp_hdi_attribution`` and ``undp_hdi_source_key``
    (mirror of V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS pattern, per architecture §12 regression checklist
    item 12).
    """
    assert write_undp_hdi_parquet is not None
    assert read_undp_hdi_csv is not None
    assert UNDP_HDI_ATTRIBUTION is not None

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    wide_df = read_undp_hdi_csv(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    narrow_df = build_undp_hdi_observations(
        wide_df,
        catalog_path=undp_hdi_catalog_path,
    )
    out = write_undp_hdi_parquet(narrow_df)

    assert out.exists()
    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"undp_hdi_attribution")
    assert attribution_bytes is not None, "parquet missing undp_hdi_attribution metadata"
    assert attribution_bytes.decode("utf-8") == UNDP_HDI_ATTRIBUTION
    assert meta.get(b"undp_hdi_source_key") == b"undp_hdi"


# ---------------------------------------------------------------------------
# §8.6 — End-to-end real-file smoke (3 tests)
# ---------------------------------------------------------------------------


def test_end_to_end_real_file_year_2022_row_count(
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """Gated on the real local 1.9MB CSV. For ``year=2022``, the
    output has roughly 1,035 rows (207 countries x 5 indicators),
    minus the few empty cells. Asserts ``< 1,200`` and ``>= 1,000``
    rows for the 2022 production run.
    """
    assert ingest_undp_hdi is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = (
        project_root
        / "data"
        / "raw"
        / "undp_hdi"
        / "HDR23-24_Composite_indices_complete_time_series.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real UNDP HDI CSV not on disk")

    _init_test_db(database_url)
    result = ingest_undp_hdi(
        year=2022,
        csv_path=real_csv,
        catalog_path=undp_hdi_catalog_path,
    )
    # 207 countries x 5 indicators = 1,035 potential 2022 rows.
    # Empty cells (the metadata says ~12.8% of all cells are empty,
    # which is much higher for the 2022-only population) reduce
    # this; we assert the lower bound is reasonable.
    assert result.observation_rows >= 1_000, (
        f"Expected >= 1,000 observations for 2022 against the real "
        f"file, got {result.observation_rows}"
    )
    assert result.observation_rows <= 1_200, (
        f"Expected <= 1,200 observations for 2022 against the real "
        f"file, got {result.observation_rows}"
    )
    assert result.countries >= 195, f"Expected >= 195 countries for 2022, got {result.countries}"
    assert result.indicators == 5


def test_end_to_end_real_file_does_not_modify_raw(
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """The end-to-end smoke against the real 1.9MB CSV must not
    modify the raw file (Phase C convention #2: no raw edits).
    """
    assert ingest_undp_hdi is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = (
        project_root
        / "data"
        / "raw"
        / "undp_hdi"
        / "HDR23-24_Composite_indices_complete_time_series.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real UNDP HDI CSV not on disk")

    # Capture SHA-256 of the raw file before
    sha_before = hashlib.sha256(real_csv.read_bytes()).hexdigest()

    _init_test_db(database_url)
    ingest_undp_hdi(
        year=2022,
        csv_path=real_csv,
        catalog_path=undp_hdi_catalog_path,
    )

    # SHA-256 after
    sha_after = hashlib.sha256(real_csv.read_bytes()).hexdigest()
    assert sha_before == sha_after, (
        f"Real raw CSV was modified during ingest: before={sha_before} after={sha_after}"
    )


def test_end_to_end_real_file_year_none_covers_full_range(
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """Gated on the real local 1.9MB CSV. With ``year=None``, the
    output covers the full 1990-2022 window and 5 indicators.
    """
    assert ingest_undp_hdi is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = (
        project_root
        / "data"
        / "raw"
        / "undp_hdi"
        / "HDR23-24_Composite_indices_complete_time_series.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real UNDP HDI CSV not on disk")

    _init_test_db(database_url)
    result = ingest_undp_hdi(
        csv_path=real_csv,
        catalog_path=undp_hdi_catalog_path,
    )
    # The full 1990-2022 range is 33 years per country
    assert result.year_window == (1990, 2022), (
        f"Expected year_window=(1990, 2022), got {result.year_window}"
    )
    assert result.indicators == 5
    # 206 countries x 33 years x 5 indicators ~= 33,990 potential;
    # with the 12.8% empty-cell rate and the years where 1990 is
    # missing for some countries, the actual count is well under
    # 34,000. (The architecture doc originally said 207 countries;
    # the live bundle has 206 distinct iso3 values -- the
    # difference is one aggregate row that the original metadata
    # counted; we report 206.)
    assert result.observation_rows >= 25_000, (
        f"Expected >= 25,000 observations for the full run against "
        f"the real file, got {result.observation_rows}"
    )
    assert result.countries == 206, f"Expected 206 countries, got {result.countries}"


# ---------------------------------------------------------------------------
# §8.7 — Orchestrator end-to-end (4 tests)
# ---------------------------------------------------------------------------


def test_orchestrator_writes_parquet_db_rows_and_manifest(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_undp_hdi()`` writes the parquet, the DB rows, and the
    run manifest in one call. The result is a ``UndpHdiIngestResult``
    with the expected 8 fields.
    """
    assert ingest_undp_hdi is not None
    assert UndpHdiIngestResult is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )

    assert isinstance(result, UndpHdiIngestResult)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    # Full fixture: 4 countries x 2 years x 5 prefixes - 2 empty = 38
    assert result.observation_rows == 38
    assert result.countries == 4
    assert set(result.years) == {1990, 2022}
    assert result.indicators == 5
    # The run manifest is auto-written
    manifest = result.parquet_path.parent / "undp_hdi_run_manifest.json"
    assert manifest.exists()


def test_orchestrator_year_filter_works(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_undp_hdi(year=2022)`` keeps only 2022 observations
    (4 countries x 5 indicators = 20 rows).
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        year=2022,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    assert result.years == (2022,)
    assert result.observation_rows == 20
    assert result.countries == 4


def test_orchestrator_year_2023_proxies_to_2022(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_undp_hdi(year=2023)`` uses 2022 data as a 1-year-gap
    proxy (per architecture §4 + the CIRIGHTS / Leader Survival
    pattern). The result's effective year is 2022; the manifest
    records the proxy semantics.
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    result = ingest_undp_hdi(
        year=2023,
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    # The effective data year is 2022 (the latest available)
    assert 2022 in result.years, (
        f"Expected result.years to include 2022 (the 2023→2022 proxy), got {result.years}"
    )
    assert 2023 not in result.years, (
        f"2023 should NOT appear in result.years (the bundle only "
        f"covers 1990-2022); got {result.years}"
    )
    # The manifest records the proxy semantics
    manifest = result.parquet_path.parent / "undp_hdi_run_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    # The manifest must surface the proxy mapping in some form
    # (either a ``proxy_year_semantics`` field, a ``requested_year``
    # field, or equivalent). The required_year is 2023 and the
    # effective year is 2022.
    assert payload.get("proxy_year_semantics") or payload.get("requested_year"), (
        f"Manifest must record the 2023→2022 proxy semantics; got: {list(payload.keys())}"
    )


def test_orchestrator_result_fields_are_stable_and_sorted(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """The result's ``years`` tuple is sorted, ``regions_covered`` is
    a sorted list, and consecutive runs produce identical results.
    """
    assert ingest_undp_hdi is not None
    _init_test_db(database_url)

    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"
    first = ingest_undp_hdi(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    second = ingest_undp_hdi(
        csv_path=csv_path,
        catalog_path=undp_hdi_catalog_path,
    )
    # years is sorted and a tuple
    assert list(first.years) == sorted(first.years)
    assert isinstance(first.years, tuple)
    # regions_covered is sorted
    assert list(first.regions_covered) == sorted(first.regions_covered)
    # Two consecutive runs are identical
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows
    assert first.years == second.years
    assert first.countries == second.countries


# ---------------------------------------------------------------------------
# §8.8 — CLI dispatch (3 tests)
# ---------------------------------------------------------------------------


def test_dispatch_table_has_undp_hdi_key() -> None:
    """``STAGE2_ADAPTERS["undp_hdi"]`` is ``undp_hdi.ingest_undp_hdi``
    (not ``None``). The full key set is unchanged.
    """
    assert undp_hdi is not None, "undp_hdi module not implemented yet"
    assert ingest_undp_hdi is not None, "undp_hdi module not implemented yet"
    assert STAGE2_ADAPTERS["undp_hdi"] is ingest_undp_hdi, (
        "STAGE2_ADAPTERS['undp_hdi'] must point to undp_hdi.ingest_undp_hdi, not None"
    )


def test_dispatch_table_no_duplicate_undp_hdi_key() -> None:
    """The dispatch table has exactly one ``undp_hdi`` key (no
    duplicate from a copy-paste bug, as the UCDP reviewer found).
    """
    assert UNDP_HDI_SOURCE_KEY is not None
    count = sum(1 for k in STAGE2_ADAPTERS.keys() if k == "undp_hdi")
    assert count == 1, f"Expected exactly 1 'undp_hdi' key in STAGE2_ADAPTERS, got {count}"
    # And the value is not None
    assert STAGE2_ADAPTERS["undp_hdi"] is not None, "STAGE2_ADAPTERS['undp_hdi'] must not be None"


def test_cli_ingest_source_runs_undp_hdi(
    undp_hdi_csv_dir: Path,
    undp_hdi_catalog_path: Path,
    database_url: str,
) -> None:
    """``leaders-db ingest-source --source undp_hdi --year 2022``
    runs through the dispatch table to the production orchestrator,
    producing the end-of-run ``Done. Summary`` block, the Rule #15
    attribution echo, and the resulting parquet + DB rows + run
    manifest. The test must fail if the CLI dispatch stops invoking
    the adapter or if any production-path side effect is missing.
    Uses the test-isolated data lake + DB; patches
    ``default_csv_path`` so the orchestrator finds the fixture.
    """
    assert ingest_undp_hdi is not None
    assert undp_hdi is not None
    assert undp_hdi_io is not None, "undp_hdi_io module not implemented"
    assert UNDP_HDI_ATTRIBUTION is not None
    _init_test_db(database_url)

    # Patch undp_hdi_io.default_csv_path to return our fixture CSV
    original_default_csv = undp_hdi_io.default_csv_path
    csv_path = undp_hdi_csv_dir / "HDR23-24_Composite_indices_complete_time_series.csv"

    def patched_default_csv() -> Path:
        return csv_path

    undp_hdi_io.default_csv_path = patched_default_csv  # type: ignore[assignment]

    try:
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["ingest-source", "--source", "undp_hdi", "--year", "2022"],
        )
        assert result.exit_code == 0, (
            f"CLI exited with code {result.exit_code}, output: {result.output}"
        )

        # The CLI must echo the production-path header lines so a
        # stub or no-op adapter cannot pass this test. A dispatcher
        # that early-returns or skips the adapter would never
        # produce these strings.
        assert "Done. Summary" in result.output, (
            f"Expected 'Done. Summary' in CLI output "
            f"(production-path adapter invocation proof); "
            f"got: {result.output!r}"
        )
        assert "Attribution:" in result.output, (
            f"Expected 'Attribution:' header in CLI output "
            f"(Rule #15 echo); got: {result.output!r}"
        )
        # The exact attribution text must be echoed (the constant
        # is the substring from docs/sources/attributions.md). This
        # catches both stubs that skip the adapter AND adapters
        # that paraphrase the attribution text.
        assert UNDP_HDI_ATTRIBUTION in result.output, (
            f"Expected UNDP_HDI_ATTRIBUTION in CLI output "
            f"(Rule #15 verbatim echo); got: {result.output!r}"
        )
        # The summary must surface the per-field counts so a stub
        # returning ``None`` or an empty object would fail this.
        assert "observation_rows:" in result.output, (
            f"Expected 'observation_rows:' in CLI output "
            f"(production-path adapter invocation proof); "
            f"got: {result.output!r}"
        )

        # Production-path side effects must be observable after
        # the CLI exits 0. A CLI that simply prints "Done" without
        # invoking the adapter cannot produce these.
        # 1) SourceObservation rows in the DB.
        with session_scope(database_url) as session:
            db_rows = (
                session.execute(select(func.count(SourceObservation.id)))
                .scalar_one()
            )
        assert db_rows == 20, (
            f"Expected 20 source_observations rows written by the "
            f"CLI-driven adapter (4 countries x 5 indicators for "
            f"year=2022), got {db_rows}. If this is 0, the CLI "
            f"dispatch did not invoke the production adapter."
        )

        # 2) Narrow parquet on disk in the processed data lake.
        # ``undp_hdi_csv_dir`` is ``<isolated_data_lake>/data/raw/undp_hdi``,
        # so the processed data lake root is
        # ``<isolated_data_lake>/data/processed/<source>``.
        parquet_path = (
            undp_hdi_csv_dir.parent.parent  # <isolated_data_lake>/data
            / "processed"
            / "undp_hdi"
            / "undp_hdi_country_year.parquet"
        )
        assert parquet_path.exists(), (
            f"Expected narrow parquet at {parquet_path} "
            f"(production-path side effect); a CLI that bypasses "
            f"the adapter would not produce this file."
        )

        # 3) Run manifest on disk next to the parquet.
        manifest_path = parquet_path.parent / "undp_hdi_run_manifest.json"
        assert manifest_path.exists(), (
            f"Expected run manifest at {manifest_path} "
            f"(production-path audit trail per architecture §4 + "
            f"§12); a CLI that bypasses the adapter would not "
            f"produce this file."
        )
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload.get("source_key") == "undp_hdi"
        assert payload.get("attribution") == UNDP_HDI_ATTRIBUTION
        assert payload.get("observation_rows") == 20
    finally:
        undp_hdi_io.default_csv_path = original_default_csv  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# §8.9 — Public surface (2 tests)
# ---------------------------------------------------------------------------


def test_undp_hdi_module_public_surface() -> None:
    """The ``undp_hdi`` module re-exports the public surface from
    architecture §9: ``ingest_undp_hdi``, ``UndpHdiIngestResult``,
    ``UNDP_HDI_ATTRIBUTION``, ``UNDP_HDI_SOURCE_KEY``,
    ``IndicatorSpec``, ``attribution``, ``load_undp_hdi_catalog``,
    ``read_undp_hdi_csv``, ``build_undp_hdi_observations``,
    ``default_csv_path``, ``default_processed_parquet_path``,
    ``register_undp_hdi_source``, ``write_undp_hdi_observations``,
    ``write_undp_hdi_parquet``, ``write_undp_hdi_run_manifest``.
    """
    assert undp_hdi is not None, "undp_hdi module not implemented yet"
    for name in [
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
    ]:
        assert hasattr(undp_hdi, name), f"undp_hdi.{name} not exported"
        assert getattr(undp_hdi, name) is not None, f"undp_hdi.{name} is None"
    # The attribution() helper returns the module-level constant
    assert attribution() == UNDP_HDI_ATTRIBUTION
    # The source key constant is "undp_hdi"
    assert UNDP_HDI_SOURCE_KEY == "undp_hdi"


def test_undp_hdi_ingest_result_field_count() -> None:
    """``UndpHdiIngestResult`` has exactly 8 fields per
    architecture §9: ``source_id``, ``parquet_path``,
    ``observation_rows``, ``countries``, ``years``, ``indicators``,
    ``regions_covered``, ``year_window``.
    """
    assert UndpHdiIngestResult is not None, "undp_hdi module not implemented"
    fields = UndpHdiIngestResult.model_fields
    expected_fields = {
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "years",
        "indicators",
        "regions_covered",
        "year_window",
    }
    assert set(fields.keys()) == expected_fields, (
        f"UndpHdiIngestResult field mismatch: "
        f"missing={expected_fields - set(fields.keys())}, "
        f"extra={set(fields.keys()) - expected_fields}"
    )
    assert len(fields) == 8, f"UndpHdiIngestResult should have 8 fields, got {len(fields)}"
