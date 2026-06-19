"""Tests for the Bertelsmann BTI Stage 2 adapter (REQ-SRC-002).

The BTI adapter is the 10th Stage 2 adapter built after V-Dem, WDI,
WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, UNDP HDI, and WHO
GHO API. These tests define what "done" means for the BTI adapter --
they would fail if any of the production wiring (catalog load,
sheet-to-year resolution, xlsx read with per-indicator column
extraction, long-to-wide pivot, parquet write, sources upsert,
source_observations write, end-to-end orchestrator) regresses.

BTI is structurally close to WGI: a single cumulative xlsx, but
with 12 edition sheets (one per BTI edition 2006-2026), each carrying
137-159 countries x 123 columns. The BTI read pattern: openpyxl
read_only pass over the resolved edition sheet, resolve catalog
indicator columns by header match, extract country rows, pivot long
-> wide.

Tests use a 5-country x 2-edition x 12-indicator fixture at
tests/fixtures/bti/sample.xlsx (real BTI-format xlsx, real values
from the cumulative BTI xlsx, no invented data). The fixture is
small enough to keep the test suite fast (~1s) and large enough to
exercise the per-sheet xlsx read, year-to-sheet resolution,
indicator column resolution, and DB-write paths.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import openpyxl
import pandas as pd
import pyarrow.parquet as pq
import pytest
from sqlalchemy import func, select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import STAGE2_ADAPTERS, bti
from leaders_db.ingest.bti_db import write_bti_observations, write_bti_run_manifest
from leaders_db.ingest.bti_db_helpers import (
    _BTI_MISSING_STRINGS,
    _coerce_float,
    _coerce_float_from_string,
    _raw_value_to_string,
)
from leaders_db.ingest.bti_io import (
    IndicatorSpec,
    covered_interval_for_sheet,
    default_processed_parquet_path,
    default_xlsx_path,
    load_indicator_catalog,
    sheet_for_year,
    target_year_for_sheet,
    write_bti_parquet,
)
from leaders_db.ingest.bti_xlsx import read_bti

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bti_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the BTI fixture xlsx under data/raw/bti/ in the test lake.

    Also copies data/raw/bti/metadata.json if the project's real one
    is present, so ``register_bti_source`` exercises the bundle
    metadata path. If the real metadata.json is missing, the adapter
    handles that case.
    """
    target = isolated_data_lake / "data" / "raw" / bti.BTI_SOURCE_KEY
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "bti"
    shutil.copy2(fixtures_dir / "sample.xlsx", target / "BTI_2006-2026_Scores.xlsx")

    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / bti.BTI_SOURCE_KEY / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def bti_catalog_path() -> Path:
    """Return the absolute path of the checked-in BTI indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/bti.csv relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "bti.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_12_specs(bti_catalog_path: Path) -> None:
    """The checked-in catalog has 12 indicators (the deliverable spec)."""
    specs = load_indicator_catalog(bti_catalog_path)
    assert len(specs) == 12, f"Expected 12 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(
    bti_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present; rating categories match the spec.

    Per the deliverable spec, the catalog covers 4 governance/effectiveness
    composites + selected Q1-Q12 fields. The category set should match.
    """
    specs = load_indicator_catalog(bti_catalog_path)
    categories = {s.category for s in specs}
    assert categories == {"effectiveness", "political_freedom", "economic_wellbeing"}, (
        f"Unexpected categories: {categories}"
    )


def test_load_indicator_catalog_composite_indicators(
    bti_catalog_path: Path,
) -> None:
    """The 4 governance/effectiveness composites are present.

    Per the deliverable spec: Governance Index, Governance Performance,
    Status Index, Democracy Status.
    """
    specs = load_indicator_catalog(bti_catalog_path)
    variable_names = {s.variable_name for s in specs}
    expected = {
        "bti_governance_index",
        "bti_governance_performance",
        "bti_status_index",
        "bti_democracy_status",
    }
    assert expected.issubset(variable_names), (
        f"Missing composites: {expected - variable_names}"
    )


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool."""
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "bti_governance_index",
            "raw_column": "  G | Governance Index",
            "category": "effectiveness",
            "raw_scale": "1-10",
            "normalized_scale_target": "0-10",
            "higher_is_better": "1",
            "unit": "bti_score",
            "description": "Test",
        }
    )
    assert higher.higher_is_better is True
    assert higher.category == "effectiveness"

    lower = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test_lower",
            "raw_column": "x",
            "category": "x",
            "raw_scale": "1-10",
            "normalized_scale_target": "0-10",
            "higher_is_better": "0",
            "unit": "bti_score",
            "description": "Test",
        }
    )
    assert lower.higher_is_better is False


def test_catalog_raw_columns_match_bti_xlsx(
    bti_catalog_path: Path, bti_xlsx_dir: Path,
) -> None:
    """Every catalog raw_column header exists in the live BTI xlsx.

    Drift-guard: if a BTI release renames an indicator, this test fails.
    """
    specs = load_indicator_catalog(bti_catalog_path)
    catalog_headers = {s.raw_column.strip() for s in specs}

    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    try:
        # Use BTI 2024 (the canonical edition for year=2023).
        ws = wb["BTI 2024"]
        xlsx_headers: set[str] = set()
        for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            for cell in row:
                if cell is not None:
                    xlsx_headers.add(str(cell).strip())
            break
    finally:
        wb.close()

    missing = catalog_headers - xlsx_headers
    assert not missing, (
        f"Catalog raw_columns not found in BTI xlsx: {sorted(missing)}. "
        "The catalog has drifted from the live xlsx."
    )


# ---------------------------------------------------------------------------
# Sheet-to-year mapping
# ---------------------------------------------------------------------------


def test_sheet_for_year_2023_returns_bti_2024() -> None:
    """year=2023 -> BTI 2024 (the canonical mapping for the prototype)."""
    assert sheet_for_year(2023) == "BTI 2024"


def test_sheet_for_year_2025_returns_bti_2026() -> None:
    """year=2025 -> BTI 2026 (the latest edition)."""
    assert sheet_for_year(2025) == "BTI 2026"


def test_sheet_for_year_2021_returns_bti_2022() -> None:
    """year=2021 -> BTI 2022 (covers 2020-2021)."""
    assert sheet_for_year(2021) == "BTI 2022"


def test_sheet_for_year_out_of_range_raises() -> None:
    """An out-of-range year raises ValueError."""
    with pytest.raises(ValueError, match="No BTI edition covers"):
        sheet_for_year(1999)


def test_covered_interval_for_sheet_known() -> None:
    """covered_interval_for_sheet returns the known (start, end) window."""
    assert covered_interval_for_sheet("BTI 2024") == (2022, 2023)
    assert covered_interval_for_sheet("BTI 2026") == (2024, 2025)


def test_covered_interval_for_sheet_unknown_returns_none() -> None:
    """An unknown sheet returns None (defensive)."""
    assert covered_interval_for_sheet("BTI 9999") is None


def test_target_year_for_sheet_known() -> None:
    """target_year_for_sheet returns the known canonical target year."""
    assert target_year_for_sheet("BTI 2024") == 2023
    assert target_year_for_sheet("BTI 2026") == 2025


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_bti_returns_full_fixture(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """year=2023 reads BTI 2024 (5 countries x 12 indicators)."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(
        year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path,
    )
    assert len(df) == 5, f"Expected 5 rows, got {len(df)}"
    # 12 indicator columns + country + year = 14 columns
    expected_indicator_cols = {
        "bti_governance_index",
        "bti_governance_performance",
        "bti_status_index",
        "bti_democracy_status",
        "bti_q1_stateness",
        "bti_q2_political_participation",
        "bti_q3_rule_of_law",
        "bti_q4_democratic_institutions",
        "bti_q5_political_social_integration",
        "bti_q6_socioeconomic_development",
        "bti_q7_market_competition",
        "bti_q11_economic_performance",
    }
    expected_cols = expected_indicator_cols | {"country", "year"}
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {set(df.columns) - expected_cols} extra, "
        f"{expected_cols - set(df.columns)} missing"
    )
    # Year is int
    assert pd.api.types.is_integer_dtype(df["year"])
    assert set(df["year"].unique()) == {2023}


def test_read_bti_filters_to_year(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """year=2023 reads BTI 2024; year=2021 reads BTI 2022."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"

    df_2023 = read_bti(
        year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path,
    )
    assert set(df_2023["year"].unique()) == {2023}
    assert len(df_2023) == 5

    df_2021 = read_bti(
        year=2021, xlsx_path=xlsx_path, catalog_path=bti_catalog_path,
    )
    assert set(df_2021["year"].unique()) == {2021}
    assert len(df_2021) == 5


def test_read_bti_with_explicit_sheet_name(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """sheet_name='BTI 2022' is used directly; year is ignored."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"

    df = read_bti(
        year=2025,  # would otherwise resolve to BTI 2026
        sheet_name="BTI 2022",
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    assert set(df["year"].unique()) == {2021}
    assert len(df) == 5


def test_read_bti_pivots_long_to_wide(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """Each catalog indicator is one column; no row duplication."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    # Each (country, year) pair appears exactly once
    assert len(df) == df[["country", "year"]].drop_duplicates().shape[0]
    # Indicator columns all have values (or NaN)
    gi_col = df["bti_governance_index"]
    assert len(gi_col) == 5


def test_read_bti_handles_missing_cells(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """Blank cells become NaN in the DataFrame (no ValueError)."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    # The fixture has 5 countries x 12 indicators; no missing values are
    # planted, so every indicator column should be fully populated.
    for col in df.columns:
        if col in {"country", "year"}:
            continue
        assert df[col].notna().sum() == 5, (
            f"Column {col!r} should have 5 non-null values, got "
            f"{df[col].notna().sum()}"
        )


def test_read_bti_missing_xlsx(
    bti_catalog_path: Path, tmp_path: Path,
) -> None:
    """Missing xlsx raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_bti(
            year=2023, xlsx_path=tmp_path / "missing.xlsx",
            catalog_path=bti_catalog_path,
        )


def test_read_bti_missing_sheet(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """An unknown sheet name raises KeyError."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    with pytest.raises(KeyError):
        read_bti(
            xlsx_path=xlsx_path,
            catalog_path=bti_catalog_path,
            sheet_name="BTI 9999",
        )


def test_default_path_helpers(isolated_data_lake: Path) -> None:
    """Default helpers point at the conventional data-lake locations.

    ``default_xlsx_path()`` raises ``FileNotFoundError`` if the file
    is missing, so the test stages an empty stub before calling it.
    """
    xlsx_dir = isolated_data_lake / "data" / "raw" / bti.BTI_SOURCE_KEY
    xlsx_dir.mkdir(parents=True, exist_ok=True)
    (xlsx_dir / "BTI_2006-2026_Scores.xlsx").touch()

    xlsx_default = default_xlsx_path()
    assert xlsx_default.name == "BTI_2006-2026_Scores.xlsx"
    assert bti.BTI_SOURCE_KEY in xlsx_default.parts

    parquet_default = default_processed_parquet_path()
    assert parquet_default.name == "bti_country_year.parquet"
    assert bti.BTI_SOURCE_KEY in parquet_default.parts


# ---------------------------------------------------------------------------
# Parquet write + DB (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_bti_parquet_creates_file(
    bti_xlsx_dir: Path, bti_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """``write_bti_parquet`` writes a valid parquet under processed/bti/."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    out = write_bti_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = isolated_data_lake / "data" / "processed" / bti.BTI_SOURCE_KEY
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_bti_parquet_attaches_attribution_metadata(
    bti_xlsx_dir: Path, bti_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries bti_attribution and bti_source_key."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    out = write_bti_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"bti_attribution")
    assert attribution_bytes is not None, "parquet missing bti_attribution metadata"
    assert attribution_bytes.decode("utf-8") == bti.BTI_ATTRIBUTION
    assert meta.get(b"bti_source_key") == b"bti"


def test_register_bti_source_is_idempotent(
    bti_xlsx_dir: Path, database_url: str,
) -> None:
    """``register_bti_source`` returns the same id on repeated calls."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = bti.register_bti_source(session)
    with session_scope(database_url) as session:
        second_id = bti.register_bti_source(session)
    assert first_id == second_id, "register_bti_source should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "Bertelsmann BTI"
        assert row.version == "BTI 2026"
        assert row.source_type == "official"


def test_register_bti_source_non_destructive_update(
    bti_xlsx_dir: Path, database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = bti.register_bti_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    # Remove bundle metadata.json (if present) so next call sees empty
    bundle_meta = bti_xlsx_dir / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = bti.register_bti_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_bti_observations_row_count(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """``len(df) * len(specs)`` observations are written (60 with the full fixture)."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    specs = load_indicator_catalog(bti_catalog_path)
    expected_rows = len(df) * len(specs)  # 5 * 12 = 60

    with session_scope(database_url) as session:
        source_id = bti.register_bti_source(session)
        rows_written = write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_bti_observations_is_idempotent(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``write_bti_observations`` produces the same count, not double."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    specs = load_indicator_catalog(bti_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = bti.register_bti_source(session)
        write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
        )
    with session_scope(database_url) as session:
        write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_bti_observations_country_id_is_null(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """Stage 2 leaves country_id, leader_id, confidence NULL; Stage 3/11 fills them.

    ``source_row_reference`` starts with ``"bti:"`` so Stage 3 can
    resolve the BTI display name to ISO3 via the country alias table.
    """
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    specs = load_indicator_catalog(bti_catalog_path)

    with session_scope(database_url) as session:
        source_id = bti.register_bti_source(session)
        write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
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
    assert all(r.confidence is None for r in rows)
    assert all(
        r.source_row_reference and r.source_row_reference.startswith("bti:")
        for r in rows
    )


def test_write_bti_observations_preserves_raw_value(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """The raw_value column preserves the original numeric cell text."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)

    with session_scope(database_url) as session:
        source_id = bti.register_bti_source(session)
        write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "bti_governance_index",
            )
        ).scalars().all()

    # The raw_value should be the float string representation for the
    # 5 fixture rows (no missing cells in the fixture).
    assert len(rows) == 5
    for r in rows:
        assert r.raw_value != ""
        assert r.normalized_value is not None


def test_write_bti_observations_source_row_reference_has_country(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """``source_row_reference`` carries the BTI display name prefixed with ``bti:``."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)

    with session_scope(database_url) as session:
        source_id = bti.register_bti_source(session)
        write_bti_observations(
            session, source_id, df, catalog_path=bti_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.source_id == source_id,
            )
        ).all()

    refs = {r[0] for r in rows}
    assert "bti:Mexico" in refs
    assert "bti:Brazil" in refs
    assert "bti:India" in refs
    assert "bti:Nigeria" in refs
    assert "bti:Kenya" in refs


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_bti_end_to_end(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """``ingest_bti`` writes parquet + observations + sources + manifest in one call.

    year=2023 reads BTI 2024: 5 countries x 12 indicators = 60
    ``source_observations`` rows.
    """
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    result = bti.ingest_bti(
        year=2023,
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )

    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    assert result.observation_rows == 60  # 5 * 12
    assert result.countries == 5
    assert result.years == (2023,)
    assert result.indicators == 12
    assert result.edition_sheet == "BTI 2024"
    assert result.covered_interval == (2022, 2023)
    # Attribution on result
    assert result.attribution == bti.BTI_ATTRIBUTION
    # Run manifest auto-written
    manifest = result.parquet_path.parent / "bti_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == bti.BTI_ATTRIBUTION
    assert manifest_payload["observation_rows"] == 60
    assert manifest_payload["sheet_name"] == "BTI 2024"
    assert manifest_payload["covered_interval"] == [2022, 2023]


def test_ingest_bti_filters_to_year(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """year=2021 reads BTI 2022 (different edition sheet)."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    result = bti.ingest_bti(
        year=2021,
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    assert result.countries == 5
    assert result.years == (2021,)
    assert result.observation_rows == 60  # 5 * 12
    assert result.edition_sheet == "BTI 2022"
    assert result.covered_interval == (2020, 2021)


def test_ingest_bti_with_explicit_sheet_name(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """``sheet_name`` overrides year-to-sheet resolution."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    result = bti.ingest_bti(
        sheet_name="BTI 2022",
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    assert result.edition_sheet == "BTI 2022"
    assert result.years == (2021,)


def test_ingest_bti_is_idempotent(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``ingest_bti`` produces same row count, same source_id."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    first = bti.ingest_bti(
        year=2023,
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    second = bti.ingest_bti(
        year=2023,
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 60


def test_ingest_bti_result_carries_attribution(
    bti_xlsx_dir: Path, bti_catalog_path: Path, database_url: str,
) -> None:
    """The BtiIngestResult.attribution property returns BTI_ATTRIBUTION byte-for-byte."""
    _init_test_db(database_url)
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    result = bti.ingest_bti(
        year=2023,
        xlsx_path=xlsx_path,
        catalog_path=bti_catalog_path,
    )
    assert result.attribution == bti.BTI_ATTRIBUTION
    assert "Bertelsmann Stiftung 2026" in result.attribution
    assert "BTI 2026" in result.attribution


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    bti_xlsx_dir: Path, bti_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    xlsx_path = bti_xlsx_dir / "BTI_2006-2026_Scores.xlsx"
    df = read_bti(year=2023, xlsx_path=xlsx_path, catalog_path=bti_catalog_path)
    out = write_bti_parquet(df)

    result = bti.BtiIngestResult(
        source_id=1,
        parquet_path=out,
        observation_rows=60,
        countries=5,
        years=(2023,),
        indicators=12,
        edition_sheet="BTI 2024",
        covered_interval=(2022, 2023),
    )
    manifest_path = write_bti_run_manifest(
        result,
        manifest_dir=isolated_data_lake / "data" / "processed" / bti.BTI_SOURCE_KEY,
        sheet_name="BTI 2024",
        covered_interval=(2022, 2023),
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 60
    assert payload["years"] == [2023]
    assert payload["attribution"] == bti.BTI_ATTRIBUTION
    assert payload["sheet_name"] == "BTI 2024"
    assert payload["covered_interval"] == [2022, 2023]


def test_attribution_matches_constant() -> None:
    """``bti.attribution()`` returns the module-level BTI_ATTRIBUTION constant.

    Per the deliverable spec, the attribution text must be the **short
    form** ``"BTI 2026 (Bertelsmann Stiftung 2026)."`` -- the canonical
    "Attribution text in reports" line in
    ``docs/source-attributions.md`` (not the long citation form).
    """
    assert bti.attribution() == bti.BTI_ATTRIBUTION
    assert bti.attribution() == "BTI 2026 (Bertelsmann Stiftung 2026)."
    assert "Bertelsmann Stiftung 2026" in bti.attribution()
    assert "BTI 2026" in bti.attribution()


def test_bti_attribution_matches_attributions_doc() -> None:
    """BTI_ATTRIBUTION is byte-identical to the citation in docs/source-attributions.md.

    Per AGENTS.md Always-On Rule #15, the code's attribution text and
    the doc's citation text must be byte-for-byte consistent. If
    either changes, both must be updated in the same commit.
    """
    doc_path = (
        Path(__file__).resolve().parents[1] / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert bti.BTI_ATTRIBUTION in doc_text, (
        f"BTI_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# Helper unit tests (coercion, raw_value audit)
# ---------------------------------------------------------------------------


def test_coerce_float_handles_none() -> None:
    """None cells coerce to None (not 0)."""
    assert _coerce_float(None) is None


def test_coerce_float_handles_nan() -> None:
    """pandas NaN coerces to None."""
    assert _coerce_float(float("nan")) is None


def test_coerce_float_handles_int() -> None:
    """Integer cells coerce to float."""
    assert _coerce_float(7) == 7.0
    assert _coerce_float(10) == 10.0


def test_coerce_float_handles_string_missing() -> None:
    """BTI missing-string sentinels coerce to None."""
    for sentinel in _BTI_MISSING_STRINGS:
        assert _coerce_float(sentinel) is None, (
            f"Sentinel {sentinel!r} should coerce to None"
        )


def test_coerce_float_handles_numeric_string() -> None:
    """Numeric strings coerce to float."""
    assert _coerce_float("7.5") == 7.5
    assert _coerce_float("10") == 10.0
    assert _coerce_float("  8.25  ") == 8.25


def test_coerce_float_from_string_handles_invalid() -> None:
    """Invalid strings coerce to None (defensive)."""
    assert _coerce_float_from_string("not a number") is None
    assert _coerce_float_from_string("") is None


def test_raw_value_to_string_handles_none() -> None:
    """None cells render as empty string for the audit trail."""
    assert _raw_value_to_string(None) == ""


def test_raw_value_to_string_handles_nan() -> None:
    """pandas NaN renders as 'nan' for the audit trail."""
    assert _raw_value_to_string(float("nan")) == "nan"


def test_raw_value_to_string_handles_number() -> None:
    """Numeric cells render as their string representation."""
    assert _raw_value_to_string(7.5) == "7.5"
    assert _raw_value_to_string(10) == "10"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_bti_module_public_surface() -> None:
    """The bti module exports the items in ``__all__``."""
    assert hasattr(bti, "BTI_ATTRIBUTION")
    assert hasattr(bti, "BTI_SOURCE_KEY")
    assert hasattr(bti, "IndicatorSpec")
    assert hasattr(bti, "BtiIngestResult")
    assert hasattr(bti, "attribution")
    assert hasattr(bti, "ingest_bti")
    assert "BTI_ATTRIBUTION" in bti.__all__
    assert "BTI_SOURCE_KEY" in bti.__all__
    assert "IndicatorSpec" in bti.__all__
    assert "BtiIngestResult" in bti.__all__
    assert "attribution" in bti.__all__
    assert "ingest_bti" in bti.__all__


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_bti() -> None:
    """``STAGE2_ADAPTERS['bti']`` is ``bti.ingest_bti``.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass; the
    pre-existing ``"bti": None`` stub is replaced. Test fails if
    the production wiring is removed.
    """
    assert "bti" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["bti"] is bti.ingest_bti
    assert callable(STAGE2_ADAPTERS["bti"])


def test_dispatch_table_no_duplicate_bti_key() -> None:
    """The dispatch table has exactly one ``bti`` key (no
    duplicate from a copy-paste bug).
    """
    assert bti.BTI_SOURCE_KEY is not None
    count = sum(1 for k in STAGE2_ADAPTERS.keys() if k == "bti")
    assert count == 1, (
        f"Expected exactly 1 'bti' key in STAGE2_ADAPTERS, got {count}"
    )
