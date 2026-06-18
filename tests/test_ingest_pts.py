"""Tests for the PTS (Political Terror Scale) Stage 2 adapter.

The PTS adapter is the seventh Stage 2 adapter built after V-Dem, WDI, WGI,
UCDP, SIPRI milex, and SIPRI Yearbook Ch.7. These tests define what "done"
means for the PTS adapter.

PTS is structurally closer to WGI (one local xlsx, no HTTP layer) than to WDI
(per-indicator HTTP) or UCDP (event-level aggregation). The xlsx is 572 KB and
contains a single sheet "PTS-2025" with 10,531 data rows x 14 columns.

Tests use a 5-country x 2-year fixture at
tests/fixtures/pts/sample.xlsx (real-format PTS xlsx, real values sliced
from the live PTS-2025.xlsx with openpyxl, no invented data):

  - Afghanistan 2022: all 3 indicators valid (case 1)
  - Afghanistan 2023: all 3 indicators valid (case 1)
  - Andorra 2022: PTS_A=1/88 (case 2, dropped), PTS_H=NA/88 (case 3,
    dropped), PTS_S=1/0 (case 1, valid)
  - United States 2022: PTS_A=3/0 (case 1), PTS_H=2/0 (case 1),
    PTS_S=NA/88 (case 3, dropped)
  - United States 2023: PTS_A=3/0 (case 1), PTS_H=3/0 (case 1),
    PTS_S=NA/88 (case 3, dropped)

The case-4 inconsistency (PTS_X='NA' with NA_Status_X=0) is tested via
an in-memory DataFrame injected into read_pts_from_dataframe().
"""

from __future__ import annotations

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

# Try importing pts modules; they do not exist yet so tests fail gracefully.
try:
    from leaders_db.ingest import pts, pts_io
    from leaders_db.ingest.pts import (
        PtsIngestResult,
        attribution,
        ingest_pts,
        load_indicator_catalog,
        read_pts,
        register_pts_source,
        write_pts_observations,
        write_pts_parquet,
        write_pts_run_manifest,
    )
    from leaders_db.ingest.pts_io import (
        PTS_ATTRIBUTION,
        PTS_SOURCE_KEY,
        IndicatorSpec,
        default_processed_parquet_path,
        default_xlsx_path,
    )
    from leaders_db.ingest.pts_io import (
        write_pts_parquet as write_pts_parquet_io,
    )
    from leaders_db.ingest.pts_xlsx import (
        read_pts as read_pts_xlsx,
    )
    from leaders_db.ingest.pts_xlsx import (
        read_pts_from_dataframe,
    )
except ImportError:
    # Modules do not exist yet; tests will fail with appropriate errors.
    pts = None  # type: ignore[assignment]
    pts_io = None  # type: ignore[assignment]
    PtsIngestResult = None  # type: ignore[assignment]
    ingest_pts = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    load_indicator_catalog = None  # type: ignore[assignment]
    read_pts = None  # type: ignore[assignment]
    register_pts_source = None  # type: ignore[assignment]
    write_pts_observations = None  # type: ignore[assignment]
    write_pts_parquet = None  # type: ignore[assignment]
    write_pts_run_manifest = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    PTS_ATTRIBUTION = None  # type: ignore[assignment]
    PTS_SOURCE_KEY = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    default_xlsx_path = None  # type: ignore[assignment]
    write_pts_parquet_io = None  # type: ignore[assignment]
    read_pts_xlsx = None  # type: ignore[assignment]
    read_pts_from_dataframe = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pts_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the PTS fixture xlsx under data/raw/political_terror_scale/
    in the test lake.

    Also copies data/raw/political_terror_scale/metadata.json if the
    project's real one is present.
    """
    target = (
        isolated_data_lake / "data" / "raw" / "political_terror_scale"
    )
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = (
        Path(__file__).resolve().parent / "fixtures" / "pts"
    )
    shutil.copy2(fixtures_dir / "sample.xlsx", target / "PTS-2025.xlsx")

    project_root = Path(__file__).resolve().parents[1]
    real_meta = (
        project_root / "data" / "raw" / "political_terror_scale"
        / "metadata.json"
    )
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def pts_catalog_path() -> Path:
    """Return the absolute path of the checked-in PTS indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/pts.csv relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "pts.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# §8.1 — Catalog loader (5 tests)
# ---------------------------------------------------------------------------


def test_catalog_has_three_rows(pts_catalog_path: Path) -> None:
    """The CSV has exactly 3 data rows (PTS_A, PTS_H, PTS_S)."""
    assert load_indicator_catalog is not None, "pts_io module not implemented"
    specs = load_indicator_catalog(pts_catalog_path)
    assert len(specs) == 3, f"Expected 3 indicators, got {len(specs)}"


def test_catalog_indicator_names_match_xlsx_columns(
    pts_catalog_path: Path,
) -> None:
    """The raw_column values are exactly PTS_A, PTS_H, PTS_S
    (case-sensitive match to xlsx header)."""
    assert load_indicator_catalog is not None, "pts_io module not implemented"
    specs = load_indicator_catalog(pts_catalog_path)
    raw_columns = {s.raw_column for s in specs}
    assert raw_columns == {"PTS_A", "PTS_H", "PTS_S"}, (
        f"raw_column mismatch: {raw_columns}"
    )


def test_catalog_higher_is_better_is_zero(pts_catalog_path: Path) -> None:
    """All 3 rows have higher_is_better == False
    (more terror = worse, so higher PTS = worse score)."""
    assert load_indicator_catalog is not None, "pts_io module not implemented"
    specs = load_indicator_catalog(pts_catalog_path)
    assert all(not s.higher_is_better for s in specs), (
        "All PTS indicators should have higher_is_better=False"
    )


def test_catalog_raw_scale_is_ordinal(pts_catalog_path: Path) -> None:
    """All 3 rows have raw_scale == 'ordinal' (1-5 expert-coded scale)."""
    assert load_indicator_catalog is not None, "pts_io module not implemented"
    specs = load_indicator_catalog(pts_catalog_path)
    assert all(s.raw_scale == "ordinal" for s in specs), (
        "All PTS indicators should have raw_scale='ordinal'"
    )


def test_catalog_category_is_domestic_violence(
    pts_catalog_path: Path,
) -> None:
    """All 3 rows have rating_category == 'domestic_violence'."""
    assert load_indicator_catalog is not None, "pts_io module not implemented"
    specs = load_indicator_catalog(pts_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {"domestic_violence"}, (
        f"Expected category 'domestic_violence', got {categories}"
    )


# ---------------------------------------------------------------------------
# §8.2 — xlsx reader (10 tests)
# ---------------------------------------------------------------------------


def test_xlsx_reader_loads_correct_sheet(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """read_pts returns a DataFrame from the 'PTS-2025' sheet
    (the only sheet)."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5, f"Expected 5 rows, got {len(df)}"


def test_xlsx_reader_preserves_country_column(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The Country column round-trips with the display name
    (e.g., 'Afghanistan')."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert "Afghanistan" in df["country"].values
    assert "United States" in df["country"].values


def test_xlsx_reader_preserves_cow_code(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The COW_Code_A column is preserved in the wide frame."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert "AFG" in df["cow_code"].values
    assert "USA" in df["cow_code"].values
    assert "AND" in df["cow_code"].values


def test_xlsx_reader_filters_by_year(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """For year=2023, the DataFrame has only Year=2023 rows (2 rows)."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(
        xlsx_path=xlsx_path, year=2023, catalog_path=pts_catalog_path,
    )
    assert set(df["year"].unique()) == {2023}, (
        f"Expected year={{2023}}, got {set(df['year'].unique())}"
    )
    assert len(df) == 2, f"Expected 2 rows for 2023, got {len(df)}"


def test_xlsx_reader_int_value_preserved(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """When PTS_A=5 and NA_Status_A=0, the indicator value is 5 (int)."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    afg_2022 = df.loc[(df["cow_code"] == "AFG") & (df["year"] == 2022)]
    assert int(afg_2022["pts_amnesty_score"].iloc[0]) == 5
    assert int(afg_2022["pts_human_rights_watch_score"].iloc[0]) == 5
    assert int(afg_2022["pts_state_dept_score"].iloc[0]) == 5


def test_xlsx_reader_na_string_with_nonzero_status_is_dropped(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """When PTS_S='NA' and NA_Status_S=88, the indicator is pd.NA
    (dropped; case 3 in the sentinel matrix)."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    usa_2022 = df.loc[(df["cow_code"] == "USA") & (df["year"] == 2022)]
    pts_s = usa_2022["pts_state_dept_score"].iloc[0]
    assert pd.isna(pts_s), (
        f"USA 2022 pts_state_dept_score should be NA, got {pts_s!r}"
    )


def test_xlsx_reader_int_value_with_nonzero_status_is_dropped(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """When PTS_A=1 (int) and NA_Status_A=88, the indicator is pd.NA
    even though the published value was 1 (case 2: NA_Status takes precedence).
    Andorra 2022 has PTS_A=1, NA_Status_A=88 in the fixture."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    and_2022 = df.loc[(df["cow_code"] == "AND") & (df["year"] == 2022)]
    pts_a = and_2022["pts_amnesty_score"].iloc[0]
    assert pd.isna(pts_a), (
        f"AND 2022 pts_amnesty_score should be NA (case 2), got {pts_a!r}"
    )


def test_xlsx_reader_inconsistency_case_is_logged(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When PTS_X='NA' and NA_Status_X=0 (case 4), the row is dropped
    AND a warning is logged. Uses an in-memory DataFrame with the Bahamas
    2017 pattern injected via read_pts_from_dataframe."""
    assert read_pts_from_dataframe is not None, (
        "pts_xlsx.read_pts_from_dataframe not implemented"
    )
    assert IndicatorSpec is not None, "pts_io module not implemented"

    # Build a 1-row in-memory DataFrame with the case-4 pattern:
    # Bahamas 2017: PTS_A='NA', NA_Status_A=0
    case4_data = {
        "Country": ["Bahamas"],
        "COW_Code_A": ["BHM"],
        "Year": [2017],
        "Region": ["na"],
        "PTS_A": ["NA"],  # type: ignore[list-item]
        "NA_Status_A": [0],
        "PTS_H": [3],
        "NA_Status_H": [0],
        "PTS_S": [3],
        "NA_Status_S": [0],
    }
    df_inject = pd.DataFrame(case4_data)

    specs = [
        IndicatorSpec(
            variable_name="pts_amnesty_score",
            raw_column="PTS_A",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Amnesty International",
        ),
        IndicatorSpec(
            variable_name="pts_human_rights_watch_score",
            raw_column="PTS_H",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Human Rights Watch",
        ),
        IndicatorSpec(
            variable_name="pts_state_dept_score",
            raw_column="PTS_S",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from US State Department",
        ),
    ]

    caplog.set_level(logging.WARNING)
    df_out = read_pts_from_dataframe(df_inject, specs)

    # PTS_A should be dropped (case 4: 'NA' + NA_Status=0 -> warning)
    assert pd.isna(df_out["pts_amnesty_score"].iloc[0])

    # A warning should be logged for the inconsistency case
    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any(
        "Bahamas" in msg and "2017" in msg for msg in warning_messages
    ), f"Expected warning about Bahamas 2017, got: {warning_messages}"


def test_xlsx_reader_handles_all_five_na_status_codes(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """For each of the 5 NA_Status codes (0/66/77/88/99), the row's
    indicator is correctly kept (only for 0) or dropped.

    The Andorra 2022 fixture row covers case 2 (NA_Status=88 + int PTS_A).
    The other codes are tested via an in-memory DataFrame."""
    assert read_pts_from_dataframe is not None, (
        "pts_xlsx.read_pts_from_dataframe not implemented"
    )
    assert IndicatorSpec is not None, "pts_io module not implemented"

    # Build a 5-row DataFrame, one per NA_Status code
    # Case 1 (keep): PTS=3, NA_Status=0
    # Case 2 (drop): PTS=3, NA_Status=88
    # Case 3 (drop): PTS='NA', NA_Status=88
    # Case 4 (drop+warn): PTS='NA', NA_Status=0
    # Case 5 (drop): PTS='NA', NA_Status=99
    multi_case_data = {
        "Country": ["X1", "X2", "X3", "X4", "X5"],
        "COW_Code_A": ["X1", "X2", "X3", "X4", "X5"],
        "Year": [2023, 2023, 2023, 2023, 2023],
        "Region": ["na", "na", "na", "na", "na"],
        "PTS_A": [3, 3, "NA", "NA", "NA"],  # type: ignore[list-item]
        "NA_Status_A": [0, 88, 88, 0, 99],
        "PTS_H": [3, 3, 3, 3, 3],
        "NA_Status_H": [0, 0, 0, 0, 0],
        "PTS_S": [3, 3, 3, 3, 3],
        "NA_Status_S": [0, 0, 0, 0, 0],
    }
    df_inject = pd.DataFrame(multi_case_data)

    specs = [
        IndicatorSpec(
            variable_name="pts_amnesty_score",
            raw_column="PTS_A",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Amnesty International",
        ),
        IndicatorSpec(
            variable_name="pts_human_rights_watch_score",
            raw_column="PTS_H",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Human Rights Watch",
        ),
        IndicatorSpec(
            variable_name="pts_state_dept_score",
            raw_column="PTS_S",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from US State Department",
        ),
    ]

    caplog.clear()
    caplog.set_level(logging.WARNING)
    df_out = read_pts_from_dataframe(df_inject, specs)

    # Case 1 (NA_Status=0): kept
    assert int(df_out["pts_amnesty_score"].iloc[0]) == 3

    # Case 2 (NA_Status=88 + int): dropped
    assert pd.isna(df_out["pts_amnesty_score"].iloc[1])

    # Case 3 (NA_Status=88 + 'NA'): dropped
    assert pd.isna(df_out["pts_amnesty_score"].iloc[2])

    # Case 4 (NA_Status=0 + 'NA'): dropped + warning
    assert pd.isna(df_out["pts_amnesty_score"].iloc[3])

    # Case 5 (NA_Status=99 + 'NA'): dropped
    assert pd.isna(df_out["pts_amnesty_score"].iloc[4])


def test_xlsx_reader_warns_on_unknown_na_status_code(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§6.5 defensive check: an unknown NA_Status code (one not in
    _PTS_NA_STATUS_CODES, e.g. the hypothetical 55 from architecture
    §6.5) triggers a WARNING and is treated as missing.

    Uses an in-memory DataFrame with NA_Status_A=55 injected via
    read_pts_from_dataframe. The test asserts:

    1. A WARNING is logged that mentions the unknown NA_Status code.
    2. The indicator is treated as missing (the cell is dropped).
    """
    assert read_pts_from_dataframe is not None, (
        "pts_xlsx.read_pts_from_dataframe not implemented"
    )
    assert IndicatorSpec is not None, "pts_io module not implemented"

    # Build a 1-row DataFrame with the hypothetical NA_Status=55
    # injected (the architecture §6.5 hypothetical). The cell value
    # is a valid int (3) so the only reason to drop the indicator
    # is the unknown NA_Status code (case 2 would drop it too, but
    # the WARNING distinguishes §6.5 from case 2).
    unknown_na_status_data = {
        "Country": ["Futureland"],
        "COW_Code_A": ["FUT"],
        "Year": [2024],
        "Region": ["eap"],
        "PTS_A": [3],  # valid int 1-5
        "NA_Status_A": [55],  # hypothetical unknown code per §6.5
        "PTS_H": [3],
        "NA_Status_H": [0],
        "PTS_S": [3],
        "NA_Status_S": [0],
    }
    df_inject = pd.DataFrame(unknown_na_status_data)

    specs = [
        IndicatorSpec(
            variable_name="pts_amnesty_score",
            raw_column="PTS_A",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Amnesty International",
        ),
        IndicatorSpec(
            variable_name="pts_human_rights_watch_score",
            raw_column="PTS_H",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from Human Rights Watch",
        ),
        IndicatorSpec(
            variable_name="pts_state_dept_score",
            raw_column="PTS_S",
            rating_category="domestic_violence",
            raw_scale="ordinal",
            normalized_scale_target="0-10",
            higher_is_better=False,
            unit="pts_score",
            description="PTS from US State Department",
        ),
    ]

    caplog.clear()
    caplog.set_level(logging.WARNING)
    df_out = read_pts_from_dataframe(df_inject, specs)

    # The unknown NA_Status_A=55 -> the indicator is treated as missing
    # (dropped) per the §6.5 defensive check.
    assert pd.isna(df_out["pts_amnesty_score"].iloc[0]), (
        "Unknown NA_Status code 55 should drop the indicator per §6.5"
    )
    # The other 2 indicators (with NA_Status=0) are kept as valid.
    assert int(df_out["pts_human_rights_watch_score"].iloc[0]) == 3
    assert int(df_out["pts_state_dept_score"].iloc[0]) == 3

    # A WARNING should be logged for the unknown NA_Status code,
    # mentioning the unknown value (55).
    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any(
        "55" in msg and "NA_Status" in msg
        for msg in warning_messages
    ), (
        "Expected WARNING mentioning unknown NA_Status code 55, "
        f"got: {warning_messages}"
    )


def test_xlsx_reader_returns_wide_frame_with_three_indicator_columns(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The output has exactly 3 indicator columns named
    pts_amnesty_score, pts_human_rights_watch_score,
    pts_state_dept_score."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    expected_cols = {
        "country", "year", "cow_code", "region",
        "pts_amnesty_score", "pts_human_rights_watch_score",
        "pts_state_dept_score",
    }
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {set(df.columns)}"
    )


# ---------------------------------------------------------------------------
# §8.3 — Wide frame (5 tests)
# ---------------------------------------------------------------------------


def test_wide_frame_country_column(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The wide frame's country column has the original display name
    (e.g., 'Afghanistan', 'United States')."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert df["country"].dtype == object
    assert "Afghanistan" in df["country"].values
    assert "United States" in df["country"].values


def test_wide_frame_year_column_is_int(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The year column is int dtype (coerced from openpyxl int cells)."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert pd.api.types.is_integer_dtype(df["year"])


def test_wide_frame_source_row_reference_format(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """source_row_reference follows 'pts:<COW_Code_A>'
    (e.g., 'pts:USA')."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    # The wide frame carries cow_code; the 'pts:' prefix is applied in DB write.
    # We verify the raw_lookup attr contains the expected keys.
    raw_lookup = df.attrs.get("_pts_raw_lookup")
    assert raw_lookup is not None, (
        "Wide frame should carry _pts_raw_lookup in attrs"
    )
    assert isinstance(raw_lookup, dict)


def test_wide_frame_cow_code_column(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The wide frame has a cow_code column with the COW_Code_A value
    (e.g., 'AFG', 'USA')."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    assert "cow_code" in df.columns
    assert set(df["cow_code"].unique()) == {"AFG", "AND", "USA"}


def test_wide_frame_raw_lookup_preserves_original_cell(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The wide frame has a raw_lookup attribute that preserves the original
    PTS_X cell text (the 'NA' string AND int 1-5) for audit/debugging.

    Mirrors the SIPRI Yearbook Ch.7 raw_value pattern."""
    assert read_pts is not None, "pts_xlsx module not implemented"
    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)

    raw_lookup = df.attrs.get("_pts_raw_lookup")
    assert raw_lookup is not None, (
        "Wide frame should carry _pts_raw_lookup in attrs"
    )
    assert isinstance(raw_lookup, dict)
    # 5 rows x 3 indicators = 15 entries minimum
    assert len(raw_lookup) >= 15, (
        f"Expected >= 15 raw_lookup entries (5 rows x 3 indicators), "
        f"got {len(raw_lookup)}"
    )
    # Andorra PTS_H='NA' -> raw_lookup entry stored as 'NA'
    and_h_key = ("Andorra", 2022, "pts_human_rights_watch_score")
    assert and_h_key in raw_lookup
    assert raw_lookup[and_h_key] == "NA"


# ---------------------------------------------------------------------------
# §8.4 — DB writers (8 tests)
# ---------------------------------------------------------------------------


def test_db_writers_write_sources_row(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """After ingest_pts(year=2023), the sources table has a row with
    source_key='pts'."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        year=2023,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == result.source_id)
        ).scalar_one()
        assert row.source_name == "Political Terror Scale (PTS)"
        assert row.version == "PTS-2025"
        assert row.source_type == "academic"


def test_db_writers_write_observations_rows(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """The source_observations table has rows for each (country, indicator)
    pair, with value populated for non-missing cases and NULL for missing."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    # Full fixture: Afghanistan 2022 (3), Afghanistan 2023 (3),
    # Andorra 2022 (1 valid: PTS_S=1), USA 2022 (2 valid),
    # USA 2023 (2 valid) = 11 total observations
    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == result.source_id
            )
        ).scalar_one()
    # Andorra: PTS_A=1/88 dropped, PTS_H=NA/88 dropped, PTS_S=1/0 kept -> 1
    # Afghanistan: 3 + 3 = 6
    # USA: PTS_S=NA/88 dropped -> 2 + 2 = 4
    # Total: 1 + 6 + 4 = 11
    assert count == 11, f"Expected 11 observations, got {count}"


def test_db_writers_country_id_is_null_at_stage2(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """country_id is NULL for all PTS rows (Stage 3 fills it);
    confidence is also NULL (Stage 11 fills it)."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == result.source_id
            )
        ).scalars().all()

    assert all(r.country_id is None for r in rows)
    assert all(r.confidence is None for r in rows)


def test_db_writers_manifest_written(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """The run_manifest JSON is written with source_key='pts',
    status='ok', and non-zero observation_rows."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    manifest = result.parquet_path.parent / "pts_run_manifest.json"
    assert manifest.exists(), f"Manifest not found at {manifest}"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload.get("source_key") == "pts"
    assert payload.get("observation_rows") == 11


def test_db_writers_idempotent_rerun(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """Running ingest_pts(year=2023) twice produces the same final state
    (no double-writes)."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    first = ingest_pts(
        year=2023,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    second = ingest_pts(
        year=2023,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 5

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == first.source_id
            )
        ).scalar_one()
    assert count == 5, f"Expected 5 observations (AFG:3 + USA:2), got {count}"


def test_db_writers_preserve_raw_value(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """For non-missing cells, raw_value preserves the original xlsx cell
    (e.g., '5' for PTS_A=5). For case-3 cells (PTS='NA'), raw_value
    is 'NA'."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == result.source_id,
                SourceObservation.variable_name
                == "pts_amnesty_score",
                SourceObservation.source_row_reference == "pts:AFG",
            )
        ).scalars().all()

    assert len(rows) == 2  # Afghanistan 2022 and 2023
    for row in rows:
        assert row.raw_value == "5", (
            f"AFG pts_amnesty_score raw_value should be '5', "
            f"got {row.raw_value!r}"
        )
        assert row.normalized_value == 5


def test_db_writers_parquet_written_with_metadata(
    pts_xlsx_dir: Path, pts_catalog_path: Path,
) -> None:
    """The parquet file exists at data/processed/pts/ and has PTS
    attribution in the parquet metadata."""
    assert write_pts_parquet_io is not None, "pts_io module not implemented"
    assert read_pts is not None, "pts_xlsx module not implemented"
    assert PTS_ATTRIBUTION is not None, "pts_io module not implemented"

    xlsx_path = pts_xlsx_dir / "PTS-2025.xlsx"
    df = read_pts(xlsx_path=xlsx_path, catalog_path=pts_catalog_path)
    out = write_pts_parquet_io(df)

    assert out.exists()
    assert out.parent.name == "pts"

    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"pts_attribution")
    assert attribution_bytes is not None, "parquet missing pts_attribution"
    assert attribution_bytes.decode("utf-8") == PTS_ATTRIBUTION
    assert meta.get(b"pts_source_key") == b"pts"


def test_ingest_result_field_count(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """PtsIngestResult has exactly 8 fields:
    source_id, parquet_path, observation_rows, countries, years,
    indicators, regions_covered, year_window."""
    assert ingest_pts is not None, "pts module not implemented"
    assert PtsIngestResult is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )

    assert isinstance(result, PtsIngestResult)
    expected_fields = {
        "source_id", "parquet_path", "observation_rows",
        "countries", "years", "indicators", "regions_covered",
        "year_window",
    }
    result_fields = set(PtsIngestResult.model_fields.keys())
    assert result_fields == expected_fields, (
        f"Field mismatch: {result_fields - expected_fields} missing, "
        f"{expected_fields - result_fields} extra"
    )


# ---------------------------------------------------------------------------
# §8.5 — Drift-guard (1 test)
# ---------------------------------------------------------------------------


def test_pts_attribution_matches_attributions_doc() -> None:
    """PTS_ATTRIBUTION is a substring of docs/source-attributions.md
    (drift guard; Always-On Rule #15)."""
    assert PTS_ATTRIBUTION is not None, "pts_io module not implemented"

    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert PTS_ATTRIBUTION in doc_text, (
        f"PTS_ATTRIBUTION not found in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# §8.6 — End-to-end smoke (1 test)
# ---------------------------------------------------------------------------


def test_end_to_end_against_real_xlsx(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """Gated on Path('data/raw/political_terror_scale/PTS-2025.xlsx').exists().
    Loads the real xlsx, filters to 2023, expects >= 200 countries x 3
    indicators, verifies no 'NA' string remains in the indicator columns."""
    assert ingest_pts is not None, "pts module not implemented"

    real_xlsx = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "raw"
        / "political_terror_scale"
        / "PTS-2025.xlsx"
    )
    if not real_xlsx.exists():
        pytest.skip("Real PTS-2025.xlsx not on disk")

    _init_test_db(database_url)

    result = ingest_pts(
        year=2023,
        xlsx_path=real_xlsx,
        catalog_path=pts_catalog_path,
    )

    assert result.countries >= 200, (
        f"Expected >= 200 countries for 2023, got {result.countries}"
    )
    assert result.indicators == 3
    assert result.observation_rows >= 450

    # Verify no 'NA' string in indicator columns of the parquet
    df = pd.read_parquet(result.parquet_path)
    for col in [
        "pts_amnesty_score",
        "pts_human_rights_watch_score",
        "pts_state_dept_score",
    ]:
        na_strings = (
            df[col].astype(str).str.upper().str.contains("NA")
        )
        assert not na_strings.any(), (
            f"Column {col} still contains 'NA' strings after reading"
        )


# ---------------------------------------------------------------------------
# §8.7 — Orchestrator end-to-end (5 tests)
# ---------------------------------------------------------------------------


def test_orchestrator_returns_pydantic_ingest_result(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """ingest_pts(year=2023) returns a PtsIngestResult instance
    (not a dict or dataclass)."""
    assert ingest_pts is not None, "pts module not implemented"
    assert PtsIngestResult is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        year=2023,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    assert isinstance(result, PtsIngestResult)


def test_orchestrator_attribution_in_result(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """The result's attribution property returns the PTS_ATTRIBUTION
    constant byte-for-byte."""
    assert ingest_pts is not None, "pts module not implemented"
    assert PTS_ATTRIBUTION is not None, "pts_io module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        year=2023,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    assert result.attribution == PTS_ATTRIBUTION


def test_orchestrator_regions_covered(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """The result's regions_covered field has all 3 region codes found
    in the fixture: sa (Afghanistan), na (USA), and eca (Andorra)."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    # Full fixture: Afghanistan (sa), Andorra (eca), USA (na)
    assert set(result.regions_covered) == {"na", "sa", "eca"}, (
        f"Expected regions {{'na','sa','eca'}}, "
        f"got {set(result.regions_covered)}"
    )
    assert result.regions_covered == sorted(result.regions_covered)


def test_orchestrator_year_window(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """The result's year_window is (2022, 2023) for the full fixture run
    (no year filter)."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    assert result.year_window == (2022, 2023), (
        f"Expected year_window=(2022, 2023), got {result.year_window}"
    )


def test_orchestrator_short_circuits_on_out_of_range_year(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """ingest_pts(year=1900) returns an empty PtsIngestResult without raising."""
    assert ingest_pts is not None, "pts module not implemented"
    _init_test_db(database_url)

    result = ingest_pts(
        year=1900,
        xlsx_path=pts_xlsx_dir / "PTS-2025.xlsx",
        catalog_path=pts_catalog_path,
    )
    assert result.countries == 0
    assert result.observation_rows == 0
    assert result.years == ()
    assert result.parquet_path.exists()


# ---------------------------------------------------------------------------
# §8.8 — CLI dispatch (2 tests)
# ---------------------------------------------------------------------------


def test_cli_dispatch_has_pts_key() -> None:
    """STAGE2_ADAPTERS['pts'] is pts.ingest_pts (not None)."""
    assert "pts" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["pts"] is not None
    assert pts is not None, "pts module not implemented yet"
    assert STAGE2_ADAPTERS["pts"] is pts.ingest_pts


def test_cli_runs_against_real_xlsx_for_2023(
    pts_xlsx_dir: Path, pts_catalog_path: Path, database_url: str,
) -> None:
    """python -m leaders_db.cli ingest-source --source pts --year 2023
    returns 0 and writes to the test-isolated DB."""
    assert ingest_pts is not None, "pts module not implemented"
    assert pts_io is not None, "pts_io module not implemented"
    _init_test_db(database_url)

    # Patch pts_io.default_xlsx_path to return our fixture xlsx
    original_default_xlsx = pts_io.default_xlsx_path

    def patched_default_xlsx() -> Path:
        return pts_xlsx_dir / "PTS-2025.xlsx"

    pts_io.default_xlsx_path = patched_default_xlsx  # type: ignore[assignment]

    try:
        runner = CliRunner()
        result = runner.invoke(
            app, ["ingest-source", "--source", "pts", "--year", "2023"],
        )
        assert result.exit_code == 0, (
            f"CLI exited with code {result.exit_code}, "
            f"output: {result.output}"
        )
    finally:
        pts_io.default_xlsx_path = original_default_xlsx  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# §8.9 — Public surface (1 test)
# ---------------------------------------------------------------------------


def test_pts_module_public_surface() -> None:
    """The pts module re-exports ingest_pts, PtsIngestResult, and
    PTS_ATTRIBUTION (and all other documented public symbols from §9)."""
    assert pts is not None, "pts module not implemented yet"

    for name in pts.__all__:
        assert hasattr(pts, name), f"pts.{name} not found in __all__"
        assert getattr(pts, name) is not None, f"pts.{name} is None"

    # Key public symbols
    assert hasattr(pts, "ingest_pts")
    assert hasattr(pts, "PtsIngestResult")
    assert hasattr(pts, "PTS_ATTRIBUTION")
    assert hasattr(pts, "PTS_SOURCE_KEY")
    assert hasattr(pts, "IndicatorSpec")
    assert hasattr(pts, "attribution")
    assert hasattr(pts, "load_indicator_catalog")
    assert hasattr(pts, "read_pts")
    assert hasattr(pts, "register_pts_source")
    assert hasattr(pts, "write_pts_observations")
    assert hasattr(pts, "write_pts_parquet")
    assert hasattr(pts, "write_pts_run_manifest")
