"""Tests for the World Bank WGI Stage 2 adapter (REQ-SRC-002).

The WGI adapter is the third Stage 2 adapter built after V-Dem and WDI.
These tests define what "done" means for the WGI adapter — they would fail if
any of the production wiring (catalog load, xlsx read with per-sheet per-year
extraction, long-to-wide pivot, parquet write, sources upsert,
source_observations write, end-to-end orchestrator) regresses.

WGI is structurally distinct from WDI: it is a single xlsx file (not an HTTP
API), with 6 indicator sheets, 214 countries, 24 years, and a "#N/A"
missing-data sentinel. The read pattern is "openpyxl per-sheet row iteration
→ long-format extraction → wide pivot".

Tests use a 5-country x 2-year x 6-indicator fixture at
tests/fixtures/world_bank_wgi/sample.xlsx (real WGI-format xlsx, real
values from the WGI 2023 Update, no invented data). The fixture is
small enough to keep the test suite fast (~1 s) and large enough to
exercise the per-sheet xlsx read, year-filtering, #N/A coercion,
and DB-write paths.
"""

from __future__ import annotations

import json
import math
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
from leaders_db.ingest import STAGE2_ADAPTERS, wgi
from leaders_db.ingest.wgi_io import (
    IndicatorSpec,
    default_processed_parquet_path,
    default_xlsx_path,
    load_indicator_catalog,
    write_wgi_parquet,
)
from leaders_db.ingest.wgi_xlsx import read_wgi

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wgi_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the WGI fixture xlsx under data/raw/world_bank_wgi/ in the test lake.

    Also copies data/raw/world_bank_wgi/metadata.json if the project's real
    one is present, so register_wgi_source exercises the bundle metadata path.
    If the real metadata.json is missing, the adapter handles that case.
    """
    target = isolated_data_lake / "data" / "raw" / wgi.WGI_SOURCE_KEY
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = (
        Path(__file__).resolve().parent / "fixtures" / "world_bank_wgi"
    )
    shutil.copy2(fixtures_dir / "sample.xlsx", target / "wgidataset.xlsx")

    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / wgi.WGI_SOURCE_KEY / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def wgi_catalog_path() -> Path:
    """Return the absolute path of the checked-in WGI indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/wgi.csv relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "wgi.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_6_specs(wgi_catalog_path: Path) -> None:
    """The checked-in catalog has 6 indicators (matches wgi.md §2.4 spec)."""
    specs = load_indicator_catalog(wgi_catalog_path)
    assert len(specs) == 6, f"Expected 6 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(
    wgi_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present; rating_category is one of the 2 expected."""
    specs = load_indicator_catalog(wgi_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {"effectiveness", "integrity"}, (
        f"Unexpected categories: {categories}"
    )


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool."""
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "wgi_voice_and_accountability",
            "raw_column": "VoiceandAccountability",
            "rating_category": "effectiveness",
            "raw_scale": "z_score",
            "normalized_scale_target": "0-1",
            "higher_is_better": "1",
            "unit": "z_score",
            "description": "Voice and Accountability",
        }
    )
    assert higher.higher_is_better is True

    lower = IndicatorSpec.from_csv_row(
        {
            "variable_name": "wgi_control_of_corruption",
            "raw_column": "ControlofCorruption",
            "rating_category": "integrity",
            "raw_scale": "z_score",
            "normalized_scale_target": "0-1",
            "higher_is_better": "0",
            "unit": "z_score",
            "description": "Control of Corruption",
        }
    )
    assert lower.higher_is_better is False


def test_catalog_sheet_names_match_wgi_release(wgi_catalog_path: Path) -> None:
    """The 6 raw_column values are exactly the WGI xlsx sheet names."""
    specs = load_indicator_catalog(wgi_catalog_path)
    raw_columns = {s.raw_column for s in specs}
    expected = {
        "VoiceandAccountability",
        "Political StabilityNoViolence",
        "GovernmentEffectiveness",
        "RegulatoryQuality",
        "RuleofLaw",
        "ControlofCorruption",
    }
    assert raw_columns == expected, (
        f"raw_column mismatch: {raw_columns - expected} missing, "
        f"{expected - raw_columns} extra"
    )


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_wgi_returns_full_fixture(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path,
) -> None:
    """The fixture (5 countries x 2 years x 6 indicators) produces a wide DataFrame.

    Wide format: 10 rows (5 countries x 2 years), 8 columns
    (iso3, year, 6 indicator columns).
    """
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    assert len(df) == 10, f"Expected 10 rows, got {len(df)}"
    expected_cols = {
        "iso3", "year",
        "wgi_voice_and_accountability",
        "wgi_political_stability",
        "wgi_government_effectiveness",
        "wgi_regulatory_quality",
        "wgi_rule_of_law",
        "wgi_control_of_corruption",
    }
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {set(df.columns)}"
    )
    # Year is int
    assert pd.api.types.is_integer_dtype(df["year"])


def test_read_wgi_filters_to_year(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path,
) -> None:
    """year=2022 keeps only the 5 rows for 2022; year=2021 likewise."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"

    df_2022 = read_wgi(
        xlsx_path=xlsx_path, year=2022, catalog_path=wgi_catalog_path,
    )
    assert set(df_2022["year"].unique()) == {2022}
    assert len(df_2022) == 5
    assert set(df_2022["iso3"].unique()) == {
        "MEX", "USA", "SWE", "IND", "NGA",
    }

    df_2021 = read_wgi(
        xlsx_path=xlsx_path, year=2021, catalog_path=wgi_catalog_path,
    )
    assert set(df_2021["year"].unique()) == {2021}
    assert len(df_2021) == 5


def test_read_wgi_pivots_long_to_wide(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path,
) -> None:
    """Each catalog indicator is one column; no row duplication."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    # Each (iso3, year) pair appears exactly once
    assert len(df) == df[["iso3", "year"]].drop_duplicates().shape[0]
    # Indicator columns all have values (or NaN for the #N/A cell)
    va_col = df["wgi_voice_and_accountability"]
    assert len(va_col) == 10


def test_read_wgi_handles_na_cells(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path,
) -> None:
    """The single #N/A cell in the fixture becomes NaN in the DataFrame."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)

    mex_2021_pv = df.loc[
        (df["iso3"] == "MEX") & (df["year"] == 2021),
        "wgi_political_stability",
    ].iloc[0]
    assert math.isnan(mex_2021_pv), (
        f"MEX 2021 political_stability should be NaN, got {mex_2021_pv!r}"
    )
    # The other countries still have real values
    usa_2021_pv = df.loc[
        (df["iso3"] == "USA") & (df["year"] == 2021),
        "wgi_political_stability",
    ].iloc[0]
    assert not math.isnan(usa_2021_pv)


def test_read_wgi_missing_xlsx(
    wgi_catalog_path: Path, tmp_path: Path,
) -> None:
    """Missing xlsx raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_wgi(
            xlsx_path=tmp_path / "missing.xlsx",
            catalog_path=wgi_catalog_path,
        )


def test_read_wgi_missing_sheet(
    wgi_xlsx_dir: Path, tmp_path: Path, wgi_catalog_path: Path,
) -> None:
    """If a catalog raw_column sheet name is absent, read_wgi raises KeyError."""
    # Write a catalog with a non-existent sheet name
    bad_catalog = tmp_path / "bad_wgi.csv"
    bad_catalog.write_text(
        "variable_name,raw_column,rating_category,raw_scale,"
        "normalized_scale_target,higher_is_better,unit,description\n"
        "wgi_nonexistent,NonExistentSheet,effectiveness,z_score,0-1,"
        "True,z_score,Does not exist\n",
        encoding="utf-8",
    )
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    with pytest.raises(KeyError):
        read_wgi(xlsx_path=xlsx_path, catalog_path=bad_catalog)


def test_default_path_helpers(isolated_data_lake: Path) -> None:
    """Default helpers point at the conventional data-lake locations.

    ``default_xlsx_path()`` raises :class:`FileNotFoundError` if the
    file is missing (per the design contract in
    ``docs/architecture/wgi.md`` §2.3), so the test stages an empty
    stub before calling it.
    """
    xlsx_dir = isolated_data_lake / "data" / "raw" / wgi.WGI_SOURCE_KEY
    xlsx_dir.mkdir(parents=True, exist_ok=True)
    (xlsx_dir / "wgidataset.xlsx").touch()

    xlsx_default = default_xlsx_path()
    assert xlsx_default.name == "wgidataset.xlsx"
    assert wgi.WGI_SOURCE_KEY in xlsx_default.parts

    parquet_default = default_processed_parquet_path()
    assert parquet_default.name == "wgi_country_year.parquet"
    assert wgi.WGI_SOURCE_KEY in parquet_default.parts


# ---------------------------------------------------------------------------
# Parquet write + DB (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_wgi_parquet_creates_file(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """``write_wgi_parquet`` writes a valid parquet under processed/world_bank_wgi/."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    out = write_wgi_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = isolated_data_lake / "data" / "processed" / wgi.WGI_SOURCE_KEY
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_wgi_parquet_attaches_attribution_metadata(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries wgi_attribution and wgi_source_key."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    out = write_wgi_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"wgi_attribution")
    assert attribution_bytes is not None, "parquet missing wgi_attribution metadata"
    assert attribution_bytes.decode("utf-8") == wgi.WGI_ATTRIBUTION
    assert meta.get(b"wgi_source_key") == b"world_bank_wgi"


def test_register_wgi_source_is_idempotent(
    wgi_xlsx_dir: Path, database_url: str,
) -> None:
    """``register_wgi_source`` returns the same id on repeated calls; row shape."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wgi.register_wgi_source(session)
    with session_scope(database_url) as session:
        second_id = wgi.register_wgi_source(session)
    assert first_id == second_id, "register_wgi_source should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "World Bank WGI"
        assert row.version == "2023"
        assert row.source_type == "official"


def test_register_wgi_source_non_destructive_update(
    wgi_xlsx_dir: Path, database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wgi.register_wgi_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    # Remove bundle metadata.json (if present) so next call sees empty
    bundle_meta = wgi_xlsx_dir / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = wgi.register_wgi_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_wgi_observations_row_count(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """``len(df) * len(specs)`` observations are written (60 with the full fixture)."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    specs = load_indicator_catalog(wgi_catalog_path)
    expected_rows = len(df) * len(specs)  # 10 * 6 = 60

    with session_scope(database_url) as session:
        source_id = wgi.register_wgi_source(session)
        rows_written = wgi.write_wgi_observations(
            session, source_id, df, catalog_path=wgi_catalog_path,
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_wgi_observations_is_idempotent(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``write_wgi_observations`` produces the same count, not double."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    specs = load_indicator_catalog(wgi_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = wgi.register_wgi_source(session)
        wgi.write_wgi_observations(
            session, source_id, df, catalog_path=wgi_catalog_path,
        )
    with session_scope(database_url) as session:
        wgi.write_wgi_observations(
            session, source_id, df, catalog_path=wgi_catalog_path,
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_wgi_observations_country_id_is_null(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """Stage 2 leaves country_id and confidence NULL; Stage 3/11 fills them.

    source_row_reference starts with "wgi:" so Stage 3 can resolve it.
    """
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    specs = load_indicator_catalog(wgi_catalog_path)

    with session_scope(database_url) as session:
        source_id = wgi.register_wgi_source(session)
        wgi.write_wgi_observations(
            session, source_id, df, catalog_path=wgi_catalog_path,
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
        r.source_row_reference and r.source_row_reference.startswith("wgi:")
        for r in rows
    )


def test_write_wgi_observations_handles_na_cells(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """A #N/A row becomes NULL normalized_value; raw_value is "#N/A"."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)

    with session_scope(database_url) as session:
        source_id = wgi.register_wgi_source(session)
        wgi.write_wgi_observations(
            session, source_id, df, catalog_path=wgi_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "wgi_political_stability",
            )
        ).scalars().all()

    # Sort by (iso3, year DESC) so the dict comprehension's last-seen
    # per iso3 is the earliest year (2021, which holds the fixture's
    # single #N/A cell). Without an explicit sort the dict lookup is
    # not deterministic (it depends on whichever index the SQLite
    # query planner picks).
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.source_row_reference.split(":")[1], -r.year),
    )
    by_iso3 = {r.source_row_reference.split(":")[1]: r for r in sorted_rows}
    # MEX 2021 political stability is the #N/A cell
    mex_2021 = by_iso3["MEX"]
    assert mex_2021.normalized_value is None
    assert mex_2021.raw_value == "#N/A"
    # USA 2021 political stability is a real value
    usa_2021 = by_iso3["USA"]
    assert usa_2021.normalized_value is not None


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_wgi_end_to_end(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """``ingest_wgi`` writes parquet + observations + sources + manifest in one call.

    Full fixture: 5 countries x 2 years x 6 indicators = 60 source_observations rows.
    """
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    result = wgi.ingest_wgi(
        xlsx_path=xlsx_path,
        catalog_path=wgi_catalog_path,
    )

    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    assert result.observation_rows == 60  # 5 * 2 * 6
    assert result.countries == 5
    assert set(result.years) == {2021, 2022}
    assert result.indicators == 6
    # Attribution on result
    assert result.attribution == wgi.WGI_ATTRIBUTION
    # Run manifest auto-written
    manifest = result.parquet_path.parent / "wgi_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == wgi.WGI_ATTRIBUTION
    assert manifest_payload["observation_rows"] == 60


def test_ingest_wgi_filters_to_year(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """year=2022 keeps 5 countries x 1 year x 6 indicators = 30 observation rows."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    result = wgi.ingest_wgi(
        year=2022,
        xlsx_path=xlsx_path,
        catalog_path=wgi_catalog_path,
    )
    assert result.countries == 5
    assert result.years == (2022,)
    assert result.observation_rows == 30  # 5 * 6


def test_ingest_wgi_is_idempotent(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """Re-running ``ingest_wgi`` produces same row count, same source_id, no double-write."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    first = wgi.ingest_wgi(
        xlsx_path=xlsx_path,
        catalog_path=wgi_catalog_path,
    )
    second = wgi.ingest_wgi(
        xlsx_path=xlsx_path,
        catalog_path=wgi_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 60


def test_ingest_wgi_result_carries_attribution(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, database_url: str,
) -> None:
    """The WGIIngestResult.attribution property returns WGI_ATTRIBUTION byte-for-byte."""
    _init_test_db(database_url)
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    result = wgi.ingest_wgi(
        xlsx_path=xlsx_path,
        catalog_path=wgi_catalog_path,
    )
    assert result.attribution == wgi.WGI_ATTRIBUTION
    assert "World Bank" in result.attribution
    assert "2023" in result.attribution
    assert "Worldwide Governance Indicators" in result.attribution
    assert "CC BY 4.0" in result.attribution


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    wgi_xlsx_dir: Path, wgi_catalog_path: Path, isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    xlsx_path = wgi_xlsx_dir / "wgidataset.xlsx"
    df = read_wgi(xlsx_path=xlsx_path, catalog_path=wgi_catalog_path)
    out = write_wgi_parquet(df)

    result = wgi.WGIIngestResult(
        source_id=1,
        parquet_path=out,
        observation_rows=60,
        countries=5,
        years=(2021, 2022),
        indicators=6,
    )
    manifest_path = wgi.write_wgi_run_manifest(
        result,
        manifest_dir=isolated_data_lake / "data" / "processed" / wgi.WGI_SOURCE_KEY,
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 60
    assert payload["years"] == [2021, 2022]
    assert payload["attribution"] == wgi.WGI_ATTRIBUTION


def test_attribution_matches_constant() -> None:
    """``wgi.attribution()`` returns the module-level WGI_ATTRIBUTION constant."""
    assert wgi.attribution() == wgi.WGI_ATTRIBUTION
    assert "World Bank" in wgi.attribution()
    assert "2023" in wgi.attribution()
    assert "Worldwide Governance Indicators" in wgi.attribution()
    assert "CC BY 4.0" in wgi.attribution()


def test_wgi_attribution_matches_attributions_doc() -> None:
    """WGI_ATTRIBUTION is a substring of docs/source-attributions.md (drift guard).

    Per AGENTS.md Always-On Rule #15, the code's attribution text and the
    doc's citation text must be byte-for-byte consistent. If either changes,
    both must be updated in the same commit.
    """
    doc_path = (
        Path(__file__).resolve().parents[1] / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert wgi.WGI_ATTRIBUTION in doc_text, (
        f"WGI_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table() -> None:
    """The dispatch table registers the WGI orchestrator."""
    assert STAGE2_ADAPTERS[wgi.WGI_SOURCE_KEY] is wgi.ingest_wgi
    expected_keys = {
        "vdem", "world_bank_wdi", "world_bank_wgi", "ucdp",
        "sipri_milex", "sipri_yearbook_ch7", "pts", "undp_hdi",
        "who_gho_api", "polity_v", "pwt", "archigos", "reign",
        "leader_survival", "transparency_cpi", "fas",
        "wikidata_heads_of_state_government", "wikipedia_search_extract",
        "freedom_house", "imf_weo", "cow_mid", "cirights",
        "nti", "bti", "cia_world_leaders", "rsf_press_freedom",
        "maddison_project",
    }
    assert set(STAGE2_ADAPTERS.keys()) == expected_keys


def test_cli_ingest_source_rejects_unknown() -> None:
    """The CLI's ``ingest-source`` command rejects unknown source keys."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Public surface — verify wgi module exports match the design doc §2.3
# ---------------------------------------------------------------------------


def test_wgi_module_public_surface() -> None:
    """The wgi module exports the items in __all__ from the design doc §2.3."""
    assert hasattr(wgi, "WGI_ATTRIBUTION")
    assert hasattr(wgi, "WGI_SOURCE_KEY")
    assert hasattr(wgi, "IndicatorSpec")
    assert hasattr(wgi, "WGIIngestResult")
    assert hasattr(wgi, "attribution")
    assert hasattr(wgi, "ingest_wgi")
    assert "WGI_ATTRIBUTION" in wgi.__all__
    assert "WGI_SOURCE_KEY" in wgi.__all__
    assert "IndicatorSpec" in wgi.__all__
    assert "WGIIngestResult" in wgi.__all__
    assert "attribution" in wgi.__all__
    assert "ingest_wgi" in wgi.__all__
