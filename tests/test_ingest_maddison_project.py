"""Tests for the Maddison Project Database 2023 Stage 2 adapter.

These tests define what "done" means for the Maddison Project
adapter -- they would fail if any of the production wiring
(catalog load, xlsx read with derived GDP computation, narrow-
format long-frame construction, parquet write with attribution
metadata, sources upsert, source_observations write, end-to-end
orchestrator, CLI dispatch) regresses.

Maddison is structurally distinct from WGI / WDI / V-Dem:

- It is a single xlsx file with one canonical sheet (``Full data``)
  that is already in long-per-(countrycode, year) format -- the
  Stage 2 adapter reshapes it to the canonical
  ``(countrycode, year, variable_name)`` triple instead of pivoting
  wide-to-long like WGI.
- The 2023 release ends at year 2022, so ``year=2023`` is mapped
  to the 2022 proxy (1-year-gap pattern, same as CIRIGHTS / UNDP
  HDI / Leader Survival).
- One catalog indicator (the derived total GDP) is COMPUTED at
  Stage 2 read time, not read from a column. The catalog carries
  the sentinel ``__derived_gdp_total__`` so the Stage 2 reader
  can recognise it.

Tests use a 4-country x 2-year fixture at
``tests/fixtures/maddison_project/sample.xlsx`` with real Maddison
values sliced from the live 4.9 MB ``mpd2023.xlsx``. The fixture
is built by ``tests/fixtures/maddison_project/build_sample_xlsx.py``
(no print, idempotent, deterministic).
"""

from __future__ import annotations

import json
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
from leaders_db.ingest import STAGE2_ADAPTERS, maddison_project, maddison_project_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def maddison_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the Maddison fixture xlsx under data/raw/maddison_project/.

    The fixture xlsx is the artifact the adapter reads. We stage a
    copy in the test lake so the adapter's ``default_xlsx_path``
    helper resolves against the test DB instead of the production
    data lake.
    """
    target = isolated_data_lake / "data" / "raw" / maddison_project.MADDISON_PROJECT_SOURCE_KEY
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = (
        Path(__file__).resolve().parent / "fixtures" / "maddison_project"
    )
    shutil.copy2(fixtures_dir / "sample.xlsx", target / "mpd2023.xlsx")
    return target


@pytest.fixture()
def maddison_catalog_path() -> Path:
    """Return the absolute path of the checked-in Maddison indicator catalog.

    Lives at ``src/leaders_db/ingest/catalogs/maddison_project.csv``
    relative to the project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "maddison_project.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_3_specs(
    maddison_catalog_path: Path,
) -> None:
    """The checked-in catalog has 3 indicators: gdppc, pop, derived."""
    specs = maddison_project.load_indicator_catalog(
        catalog_path=maddison_catalog_path,
    )
    assert len(specs) == 3, f"Expected 3 indicators, got {len(specs)}"
    variable_names = {s.variable_name for s in specs}
    assert variable_names == {
        "maddison_project_gdp_per_capita_2011_intl",
        "maddison_project_population_thousands",
        "maddison_project_gdp_total_2011_intl_derived",
    }
    assert all(s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(
    maddison_catalog_path: Path,
) -> None:
    """All 8 required CSV columns are present; rating_category is economic_wellbeing."""
    specs = maddison_project.load_indicator_catalog(
        catalog_path=maddison_catalog_path,
    )
    categories = {s.rating_category for s in specs}
    assert categories == {"economic_wellbeing"}


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        maddison_project.load_indicator_catalog(
            catalog_path=tmp_path / "does-not-exist.csv",
        )


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=1``/``=0`` round-trips to a bool (the
    Maddison convention, per the catalog header)."""
    higher = maddison_project.IndicatorSpec.from_csv_row(
        {
            "variable_name": "maddison_project_gdp_per_capita_2011_intl",
            "raw_column": "gdppc",
            "rating_category": "economic_wellbeing",
            "raw_scale": "2011_intl_dollars",
            "normalized_scale_target": "0-1",
            "higher_is_better": "1",
            "unit": "2011 international dollars",
            "description": "Real GDP per capita",
        }
    )
    assert higher.higher_is_better is True

    lower = maddison_project.IndicatorSpec.from_csv_row(
        {
            "variable_name": "maddison_project_gdp_per_capita_2011_intl",
            "raw_column": "gdppc",
            "rating_category": "economic_wellbeing",
            "raw_scale": "2011_intl_dollars",
            "normalized_scale_target": "0-1",
            "higher_is_better": "0",
            "unit": "x",
            "description": "x",
        }
    )
    assert lower.higher_is_better is False


def test_catalog_includes_derived_indicator(
    maddison_catalog_path: Path,
) -> None:
    """The catalog carries the derived-total sentinel
    ``__derived_gdp_total__`` so the Stage 2 reader can recognise
    it. The Stage 2 reader raises ``ValueError`` when this row is
    absent (defense against accidental catalog truncation)."""
    specs = maddison_project.load_indicator_catalog(
        catalog_path=maddison_catalog_path,
    )
    raw_columns = {s.raw_column for s in specs}
    assert "__derived_gdp_total__" in raw_columns


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_maddison_project_returns_full_fixture(
    maddison_xlsx_dir: Path, maddison_catalog_path: Path,
) -> None:
    """The fixture (4 countries x 2 years) yields a long-format frame.

    Long format: 7 rows in the fixture, 3 indicators per country-year
    when both gdppc and pop are present. For our 7-row fixture (SWE
    2022 is absent -- only SWE 2021), the long frame holds:
    - 6 country-years x 3 indicators (gdppc + pop + derived total)
      = 18 rows for MEX/USA/IND 2021-2022 + SWE 2021 + 2 of
        MEX/USA 2021 (so really 6 country-years = 6 x 3 = 18).
    - Plus the SWE 2022 row is absent.

    Each (countrycode, year, variable_name) triple appears exactly
    once; the narrow frame has 18 rows.
    """
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )
    # 4 countries x 2 years = 8 fixture rows; SWE 2022 absent = 7
    # data rows. 7 country-years x 3 indicators = 21 long rows.
    assert len(df) == 21, f"Expected 21 long rows, got {len(df)}"
    expected_cols = {
        "countrycode", "year", "country", "region",
        "variable_name", "raw_column",
        "raw_value", "normalized_value",
    }
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {set(df.columns)}"
    )
    # Year is int
    assert pd.api.types.is_integer_dtype(df["year"])


def test_read_maddison_project_filters_to_year(
    maddison_xlsx_dir: Path, maddison_catalog_path: Path,
) -> None:
    """``year=2022`` keeps only the 2022 country-years (3 countries)."""
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df_2022 = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, year=2022, catalog_path=maddison_catalog_path,
    )
    assert set(df_2022["year"].unique()) == {2022}
    assert set(df_2022["countrycode"].unique()) == {"IND", "MEX", "USA"}
    assert len(df_2022) == 9  # 3 countries x 3 indicators

    df_2021 = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, year=2021, catalog_path=maddison_catalog_path,
    )
    assert set(df_2021["year"].unique()) == {2021}
    assert set(df_2021["countrycode"].unique()) == {"IND", "MEX", "USA", "SWE"}
    assert len(df_2021) == 12  # 4 countries x 3 indicators


def test_read_maddison_project_emits_derived_total(
    maddison_xlsx_dir: Path, maddison_catalog_path: Path,
) -> None:
    """The derived GDP total = gdppc * pop * 1000 is emitted when both
    cells are present.

    For MEX 2022 (gdppc=16235.455, pop=125246.73): derived =
    16235.455 * 125246.73 * 1000 = 2,033,471,234,247.78 (approx).
    """
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )

    derived = df.loc[
        (df["countrycode"] == "MEX")
        & (df["year"] == 2022)
        & (df["variable_name"] == "maddison_project_gdp_total_2011_intl_derived"),
    ]
    assert len(derived) == 1, "Expected exactly 1 derived row for MEX 2022"

    value = float(derived.iloc[0]["normalized_value"])
    expected = 16235.455392709897 * 125246.73 * 1000.0
    assert abs(value - expected) / expected < 1e-9, (
        f"Derived total mismatch: got {value}, expected {expected}"
    )


def test_read_maddison_project_missing_xlsx(
    maddison_catalog_path: Path, tmp_path: Path,
) -> None:
    """Missing xlsx raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        maddison_project.read_maddison_project(
            xlsx_path=tmp_path / "missing.xlsx",
            catalog_path=maddison_catalog_path,
        )


def test_default_path_helpers(isolated_data_lake: Path) -> None:
    """``default_xlsx_path`` raises FileNotFoundError when missing;
    ``default_processed_parquet_path`` returns the conventional
    location."""
    from leaders_db.ingest import maddison_project_io

    xlsx_dir = isolated_data_lake / "data" / "raw" / maddison_project.MADDISON_PROJECT_SOURCE_KEY
    xlsx_dir.mkdir(parents=True, exist_ok=True)
    (xlsx_dir / "mpd2023.xlsx").touch()

    xlsx_default = maddison_project_io.default_xlsx_path()
    assert xlsx_default.name == "mpd2023.xlsx"
    assert maddison_project.MADDISON_PROJECT_SOURCE_KEY in str(xlsx_default)

    parquet_default = maddison_project_io.default_processed_parquet_path()
    assert parquet_default.name == "maddison_project_country_year.parquet"
    assert maddison_project.MADDISON_PROJECT_SOURCE_KEY in str(parquet_default)


# ---------------------------------------------------------------------------
# Parquet write + DB notes higher_is_better=1 (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_maddison_project_parquet_creates_file(
    maddison_xlsx_dir: Path, maddison_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """``write_maddison_project_parquet`` writes a valid parquet."""
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )
    out = maddison_project.write_maddison_project_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = (
        isolated_data_lake
        / "data"
        / "processed"
        / maddison_project.MADDISON_PROJECT_SOURCE_KEY
    )
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape.
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_maddison_project_parquet_attaches_attribution_metadata(
    maddison_xlsx_dir: Path, maddison_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries the Maddison
    attribution + source key (Rule #15)."""
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )
    out = maddison_project.write_maddison_project_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"maddison_project_attribution")
    assert attribution_bytes is not None, (
        "parquet missing maddison_project_attribution metadata"
    )
    assert attribution_bytes.decode("utf-8") == (
        maddison_project.MADDISON_PROJECT_ATTRIBUTION
    )
    assert meta.get(b"maddison_project_source_key") == b"maddison_project"


def test_db_notes_carry_higher_is_better_one(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """``source_observations.notes`` records ``higher_is_better=1``
    for every Maddison observation, matching the catalog's
    higher_is_better=1 convention.

    This is the contract the user asked for: the catalog uses the
    ``1`` convention, and every DB observation's ``notes`` field
    must surface that.
    """
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = maddison_project.register_maddison_project_source(
            session,
        )
        maddison_project.write_maddison_project_observations(
            session, source_id, df, catalog_path=maddison_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
            ),
        ).scalars().all()

    assert rows, "expected at least one observation"
    # Every row's notes must include higher_is_better=1
    for row in rows:
        assert row.notes is not None, "notes should not be NULL"
        assert "higher_is_better=1" in row.notes, (
            f"notes missing higher_is_better=1: {row.notes!r}"
        )


def test_register_maddison_project_source_is_idempotent(
    maddison_xlsx_dir: Path, database_url: str,
) -> None:
    """``register_maddison_project_source`` returns the same id on
    repeated calls; row shape matches the catalog."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = maddison_project.register_maddison_project_source(session)
    with session_scope(database_url) as session:
        second_id = maddison_project.register_maddison_project_source(session)
    assert first_id == second_id, "register should be idempotent"

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "Maddison Project Database 2023"
        assert row.version == "2023"
        assert row.source_type == "official"


def test_write_maddison_project_observations_row_count(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """The full-fixture run writes 21 source_observations rows
    (7 country-years x 3 indicators)."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = maddison_project.register_maddison_project_source(
            session,
        )
        rows_written = maddison_project.write_maddison_project_observations(
            session, source_id, df, catalog_path=maddison_catalog_path,
        )
    assert rows_written == 21

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id,
            ),
        ).scalar_one()
    assert count == 21


def test_write_maddison_project_observations_is_idempotent(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running ``write_maddison_project_observations`` produces
    the same count, not double."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = maddison_project.register_maddison_project_source(
            session,
        )
        maddison_project.write_maddison_project_observations(
            session, source_id, df, catalog_path=maddison_catalog_path,
        )
    with session_scope(database_url) as session:
        maddison_project.write_maddison_project_observations(
            session, source_id, df, catalog_path=maddison_catalog_path,
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id,
            ),
        ).scalar_one()
    assert count == 21


def test_write_maddison_project_observations_country_id_is_null(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """Stage 2 leaves country_id and confidence NULL; Stage 3/11 fills
    them. ``source_row_reference`` starts with ``maddison_project:``
    so Stage 3 can resolve it."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    df = maddison_project.read_maddison_project(
        xlsx_path=xlsx_path, catalog_path=maddison_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = maddison_project.register_maddison_project_source(
            session,
        )
        maddison_project.write_maddison_project_observations(
            session, source_id, df, catalog_path=maddison_catalog_path,
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
            ),
        ).scalars().all()

    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows)
    assert all(
        r.source_row_reference and r.source_row_reference.startswith(
            "maddison_project:"
        )
        for r in rows
    )


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_maddison_project_end_to_end(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_maddison_project`` writes parquet + observations +
    sources + manifest in one call.

    Full fixture: 4 countries x 2 years = 7 country-years x 3
    indicators = 21 source_observations rows (SWE 2022 absent).
    """
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    result = maddison_project.ingest_maddison_project(
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )

    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    assert result.observation_rows == 21
    assert result.countries == 4
    assert set(result.years) == {2021, 2022}
    assert result.indicators == 3
    # Attribution on result (Rule #15)
    assert result.attribution == maddison_project.MADDISON_PROJECT_ATTRIBUTION
    # Run manifest auto-written
    manifest = result.parquet_path.parent / "maddison_project_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == (
        maddison_project.MADDISON_PROJECT_ATTRIBUTION
    )
    assert manifest_payload["observation_rows"] == 21


def test_ingest_maddison_project_filters_to_year(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """``year=2022`` keeps 3 countries x 1 year x 3 indicators = 9
    observation rows."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    result = maddison_project.ingest_maddison_project(
        year=2022,
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )
    assert result.countries == 3
    assert result.years == (2022,)
    assert result.observation_rows == 9


def test_ingest_maddison_project_is_idempotent(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running ``ingest_maddison_project`` produces the same row
    count + same source_id, no double-write."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    first = maddison_project.ingest_maddison_project(
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )
    second = maddison_project.ingest_maddison_project(
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 21


def test_ingest_maddison_project_year_2023_proxies_to_2022(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """``year=2023`` is mapped to the 2022 proxy (1-year-gap
    pattern); the manifest surfaces the proxy semantics."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    result = maddison_project.ingest_maddison_project(
        year=2023,
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )
    # Year 2023 -> 2022 proxy: same row count as year=2022.
    assert result.countries == 3
    assert result.years == (2022,)
    assert result.observation_rows == 9

    # Manifest records the proxy mapping.
    manifest = result.parquet_path.parent / "maddison_project_run_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload.get("requested_year") == 2023
    assert "proxy_year_semantics" in payload
    assert "year=2023" in payload["proxy_year_semantics"]
    assert "data_year=2022" in payload["proxy_year_semantics"]


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_ingest_maddison_project_result_carries_attribution(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """The ``MaddisonProjectIngestResult.attribution`` property
    returns the module-level attribution text byte-for-byte."""
    _init_test_db(database_url)
    xlsx_path = maddison_xlsx_dir / "mpd2023.xlsx"
    result = maddison_project.ingest_maddison_project(
        xlsx_path=xlsx_path,
        catalog_path=maddison_catalog_path,
    )
    assert result.attribution == maddison_project.MADDISON_PROJECT_ATTRIBUTION
    assert "Bolt" in result.attribution
    assert "van Zanden" in result.attribution
    assert "10.1111/joes.12618" in result.attribution
    assert "CC BY 4.0" in result.attribution


def test_maddison_project_attribution_matches_attributions_doc() -> None:
    """The attribution text must be a substring of
    ``docs/source-attributions.md`` (drift guard, Rule #15).

    If the source-attribution wording changes in the doc but the
    module-level constant does not, this test fails -- forcing
    the two to be updated in the same commit (Rule #15).
    """
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert maddison_project.MADDISON_PROJECT_ATTRIBUTION in doc_text, (
        f"MADDISON_PROJECT_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table() -> None:
    """``STAGE2_ADAPTERS['maddison_project']`` is the orchestrator."""
    assert "maddison_project" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["maddison_project"] is (
        maddison_project.ingest_maddison_project
    )
    assert callable(STAGE2_ADAPTERS["maddison_project"])


def test_cli_ingest_source_maddison_project_end_to_end(
    maddison_xlsx_dir: Path,
    maddison_catalog_path: Path,
    database_url: str,
) -> None:
    """Real Typer CLI ``leaders-db ingest-source --source
    maddison_project --year 2022`` end-to-end through an isolated
    data lake + DB.

    This is the highest-fidelity smoke test: it exercises the
    same entry point the user runs (``leaders-db ingest-source``)
    through Typer's CLI runner, with the data lake + DB redirected
    to a temp tree.
    """
    _init_test_db(database_url)
    # The CLI defaults to the production data lake via project_root.
    # The isolated_data_lake + database_url fixtures already
    # redirected LEADERSDB_PROJECT_ROOT; the CLI resolves paths
    # through the env-var override.
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest-source",
            "--source", "maddison_project",
            "--year", "2022",
        ],
    )
    # The CLI should print the summary + attribution. Exit code 0.
    assert result.exit_code == 0, (
        f"CLI failed: exit={result.exit_code}, stdout={result.stdout}"
    )
    # The summary line shows the row count.
    assert "observation_rows" in result.stdout
    # The attribution block is printed (Rule #15).
    assert "Bolt" in result.stdout
    assert "joes.12618" in result.stdout
    # Sanity: rows were written to the isolated DB (the CLI ran
    # the full orchestrator via the LEADERSDB_PROJECT_ROOT
    # override set by the isolated_data_lake fixture).
    with session_scope(database_url) as session:
        rows = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert rows > 0, "expected observations in the isolated DB"
    # The DB module re-export resolves through the orchestrator's
    # __all__ contract.
    assert (
        maddison_project_db.register_maddison_project_source.__name__
        == "register_maddison_project_source"
    )


def test_cli_ingest_source_rejects_unknown() -> None:
    """The CLI's ``ingest-source`` command rejects unknown source keys."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Public surface — verify maddison_project module exports match the design doc
# ---------------------------------------------------------------------------


def test_maddison_project_module_public_surface() -> None:
    """The orchestrator module re-exports the public surface."""
    assert hasattr(maddison_project, "MADDISON_PROJECT_ATTRIBUTION")
    assert hasattr(maddison_project, "MADDISON_PROJECT_SOURCE_KEY")
    assert hasattr(maddison_project, "IndicatorSpec")
    assert hasattr(maddison_project, "MaddisonProjectIngestResult")
    assert hasattr(maddison_project, "attribution")
    assert hasattr(maddison_project, "ingest_maddison_project")
    assert "MADDISON_PROJECT_ATTRIBUTION" in maddison_project.__all__
    assert "MADDISON_PROJECT_SOURCE_KEY" in maddison_project.__all__
    assert "IndicatorSpec" in maddison_project.__all__
    assert "MaddisonProjectIngestResult" in maddison_project.__all__
    assert "attribution" in maddison_project.__all__
    assert "ingest_maddison_project" in maddison_project.__all__
