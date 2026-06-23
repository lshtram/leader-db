"""Tests for the CIRIGHTS Stage 2 adapter.

The CIRIGHTS adapter is the tenth Stage 2 adapter built after V-Dem,
WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, UNDP HDI, and
WHO GHO API. These tests define what "done" means for the CIRIGHTS
adapter -- they would fail if any of the production wiring (catalog
load, xlsx read, long-to-wide pivot, source registration,
source_observations write, end-to-end orchestrator, drift-guard for
the attribution text) regresses.

CIRIGHTS is structurally closer to WGI (one local xlsx, single sheet,
no HTTP layer) than to WDI (per-indicator HTTP) or UCDP (event-level
aggregation). The xlsx is 1.2 MB and contains a single sheet
``Sheet1`` with 7,931 data rows x 50 columns.

The Stage 2 adapter narrows the 48 indicator/ID columns to the 7
Physical Integrity Rights + Repression + Civil-Political Rights
indices documented in the catalog
(``src/leaders_db/ingest/catalogs/cirights.csv``). Per the
``docs/sources/attributions.md`` cirights entry, all 7 indicators
follow the CIRIGHTS "higher = greater rights respect" convention
(``higher_is_better=1``). The CIRIGHTS codebook v2.8.27.23 §"Human
Rights Indices" makes this explicit: the additive indices "range
from 0-8" / "0-17" / "0-6" with "higher values indicate greater
levels of human rights respect".

The Stage 2 contract:

- The xlsx is in long format per country-year (one row per
  ``(country, year)``, indicator columns in cells). The "pivot" is
  therefore a column rename + per-cell coercion, not a reshape.
- The country key is the display name (e.g. ``United States of
  America``) -- NOT ISO3. Stage 3 (country match) resolves
  display name + COW code to ISO3. The Stage 2
  ``source_row_reference`` uses the URL-safe-substituted country
  token so the audit trail is locatable.
- Year coverage is 1981-2022 (no 2023). For the prototype target
  year 2023, the orchestrator maps to 2022 as proxy and records
  the mapping in the run manifest (1-year-gap pattern, same as
  UNDP HDI and Leader Survival).
- Empty cells (openpyxl ``None``) are the missing-data sentinel;
  the wide frame uses ``Int64`` nullable dtype; the
  ``source_observations`` row is SKIPPED (per the rule "do not
  invent missing values"). The ``raw_value`` audit column is the
  empty string for missing cells.

Tests use a 5-country x 2-year x 7-indicator fixture at
``tests/fixtures/cirights/sample.xlsx`` (real-format CIRIGHTS xlsx,
real values sliced from the live 1.2 MB bundle with openpyxl, no
invented data). The fixture covers:

  - Mexico 2021, Mexico 2022
  - Norway 2021, Norway 2022
  - China 2021, China 2022
  - Brazil 2021, Brazil 2022
  - United States of America 2021, United States of America 2022

The 10-row fixture produces 70 ``source_observations`` rows (10
country-year pairs x 7 indicators). The "United States of America"
display name exercises the ``safe_country_token`` URL-safe
substitution: the ``source_row_reference`` is
``cirights:United_States_of_America:2022:...``.

The missing-cell test is covered by an in-memory DataFrame
injected directly into :func:`read_cirights_from_dataframe`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from sqlalchemy import func, select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import STAGE2_ADAPTERS

# Try importing cirights modules; they do not exist yet so tests
# fail gracefully (the import block sets the names to ``None`` and
# every test that needs them asserts ``is not None`` first).
try:
    from leaders_db.ingest import cirights, cirights_io
    from leaders_db.ingest.cirights import (
        CIRIGHTS_ATTRIBUTION,
        CIRIGHTS_PROXY_REQUESTED_YEAR,
        CIRIGHTS_PROXY_YEAR,
        CIRIGHTS_SOURCE_KEY,
        CIRIGHTS_YEAR_END,
        CIRIGHTS_YEAR_START,
        CirightsIngestResult,
        IndicatorSpec,
        attribution,
        default_processed_parquet_path,
        default_xlsx_path,
        ingest_cirights,
        load_indicator_catalog,
        read_cirights,
        read_cirights_from_dataframe,
        register_cirights_source,
        safe_country_token,
        write_cirights_observations,
        write_cirights_parquet,
        write_cirights_run_manifest,
    )
    from leaders_db.ingest.cirights_xlsx import (
        read_xlsx_to_wide_dataframe,
    )
except ImportError:
    cirights = None  # type: ignore[assignment]
    cirights_io = None  # type: ignore[assignment]
    CIRIGHTS_ATTRIBUTION = None  # type: ignore[assignment]
    CIRIGHTS_PROXY_REQUESTED_YEAR = None  # type: ignore[assignment]
    CIRIGHTS_PROXY_YEAR = None  # type: ignore[assignment]
    CIRIGHTS_SOURCE_KEY = None  # type: ignore[assignment]
    CIRIGHTS_YEAR_END = None  # type: ignore[assignment]
    CIRIGHTS_YEAR_START = None  # type: ignore[assignment]
    CirightsIngestResult = None  # type: ignore[assignment]
    ingest_cirights = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    load_indicator_catalog = None  # type: ignore[assignment]
    read_cirights = None  # type: ignore[assignment]
    read_cirights_from_dataframe = None  # type: ignore[assignment]
    register_cirights_source = None  # type: ignore[assignment]
    write_cirights_observations = None  # type: ignore[assignment]
    write_cirights_parquet = None  # type: ignore[assignment]
    write_cirights_run_manifest = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    safe_country_token = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    default_xlsx_path = None  # type: ignore[assignment]
    read_xlsx_to_wide_dataframe = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cirights_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the CIRIGHTS fixture xlsx under data/raw/cirights/.

    Also copies data/raw/cirights/metadata.json if the project's
    real one is present.
    """
    target = isolated_data_lake / "data" / "raw" / "cirights"
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = (
        Path(__file__).resolve().parent / "fixtures" / "cirights"
    )
    shutil.copy2(fixtures_dir / "sample.xlsx", target / "cirights_v3.12.10.24.xlsx")

    project_root = Path(__file__).resolve().parents[1]
    real_meta = (
        project_root / "data" / "raw" / "cirights" / "metadata.json"
    )
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def cirights_catalog_path() -> Path:
    """Return the absolute path of the checked-in CIRIGHTS indicator catalog.

    Lives at src/leaders_db/ingest/catalogs/cirights.csv relative
    to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "cirights.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# §1 — Catalog loader (5 tests)
# ---------------------------------------------------------------------------


def test_catalog_has_seven_rows(cirights_catalog_path: Path) -> None:
    """The CSV has exactly 7 data rows
    (physint, repression, civpol, disap, kill, polpris, tort)."""
    assert load_indicator_catalog is not None, (
        "cirights_io module not implemented"
    )
    specs = load_indicator_catalog(cirights_catalog_path)
    assert len(specs) == 7, f"Expected 7 indicators, got {len(specs)}"


def test_catalog_indicator_names_match_xlsx_columns(
    cirights_catalog_path: Path,
) -> None:
    """The raw_column values match the xlsx header verbatim."""
    assert load_indicator_catalog is not None, (
        "cirights_io module not implemented"
    )
    specs = load_indicator_catalog(cirights_catalog_path)
    expected_raw_cols = {
        "Physical Integrity Rights Index",
        "Repression Index",
        "Civil and Political Rights Index",
        "Disappearances",
        "Extrajudicial Killings",
        "Political Imprisonment",
        "Torture",
    }
    actual_raw_cols = {s.raw_column for s in specs}
    assert actual_raw_cols == expected_raw_cols, (
        f"raw_column mismatch: {actual_raw_cols}"
    )


def test_catalog_higher_is_better_is_true(
    cirights_catalog_path: Path,
) -> None:
    """All 7 rows have higher_is_better == True (CIRIGHTS
    convention: higher index value = greater rights respect)."""
    assert load_indicator_catalog is not None, (
        "cirights_io module not implemented"
    )
    specs = load_indicator_catalog(cirights_catalog_path)
    assert all(s.higher_is_better for s in specs), (
        "All CIRIGHTS indicators should have higher_is_better=True "
        "(per codebook v2.8.27.23 §'Human Rights Indices')"
    )


def test_catalog_category_is_domestic_violence(
    cirights_catalog_path: Path,
) -> None:
    """All 7 rows have category == 'domestic_violence'."""
    assert load_indicator_catalog is not None, (
        "cirights_io module not implemented"
    )
    specs = load_indicator_catalog(cirights_catalog_path)
    categories = {s.category for s in specs}
    assert categories == {"domestic_violence"}, (
        f"Expected category 'domestic_violence', got {categories}"
    )


def test_catalog_variable_names_are_canonical(
    cirights_catalog_path: Path,
) -> None:
    """The 7 variable_name values are the canonical
    ``cirights_<short>`` keys (physint, repression, civpol, disap,
    kill, polpris, tort)."""
    assert load_indicator_catalog is not None, (
        "cirights_io module not implemented"
    )
    specs = load_indicator_catalog(cirights_catalog_path)
    expected = {
        "cirights_physint", "cirights_repression",
        "cirights_civpol", "cirights_disap", "cirights_kill",
        "cirights_polpris", "cirights_tort",
    }
    actual = {s.variable_name for s in specs}
    assert actual == expected, (
        f"variable_name mismatch: {actual - expected} missing, "
        f"{expected - actual} extra"
    )


# ---------------------------------------------------------------------------
# §2 — xlsx reader (10 tests)
# ---------------------------------------------------------------------------


def test_xlsx_reader_loads_correct_sheet(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """read_cirights returns a DataFrame from the 'Sheet1' sheet
    (the only sheet)."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10, f"Expected 10 rows, got {len(df)}"


def test_xlsx_reader_preserves_country_column(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """The country column round-trips with the display name
    (e.g., 'United States of America')."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    assert "United States of America" in df["country"].values
    assert "Mexico" in df["country"].values
    assert "Norway" in df["country"].values
    assert "China" in df["country"].values
    assert "Brazil" in df["country"].values


def test_xlsx_reader_filters_by_year(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """For year=2022, the DataFrame has only year=2022 rows (5 rows)."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(
        xlsx_path=xlsx_path, year=2022, catalog_path=cirights_catalog_path,
    )
    assert set(df["year"].unique()) == {2022}, (
        f"Expected year={{2022}}, got {set(df['year'].unique())}"
    )
    assert len(df) == 5, f"Expected 5 rows for 2022, got {len(df)}"


def test_xlsx_reader_int_values_preserved(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """For Norway 2022 (the high-rights row), the indicator values
    are int 8 (physint), int 16 (repression), int 6 (civpol)."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    norway_2022 = df.loc[
        (df["country"] == "Norway") & (df["year"] == 2022)
    ]
    assert len(norway_2022) == 1
    row = norway_2022.iloc[0]
    # Norway 2022: physint=8, repression=16, civpol=6 (per live xlsx)
    assert int(row["cirights_physint"]) == 8
    assert int(row["cirights_repression"]) == 16
    assert int(row["cirights_civpol"]) == 6
    assert int(row["cirights_disap"]) == 2
    assert int(row["cirights_kill"]) == 2
    assert int(row["cirights_polpris"]) == 2
    assert int(row["cirights_tort"]) == 2


def test_xlsx_reader_missing_cells_preserved_as_na(
    cirights_catalog_path: Path,
) -> None:
    """When a cell is empty (None in the xlsx), the wide frame
    value is pd.NA (not a sentinel like -1 or 0). The missing
    cells are NOT coerced to int 0 by the read orchestrator.

    The test uses an in-memory DataFrame injected into
    :func:`read_cirights_from_dataframe`.
    """
    assert read_cirights_from_dataframe is not None, (
        "cirights_xlsx module not implemented"
    )
    assert IndicatorSpec is not None, (
        "cirights_io module not implemented"
    )

    # Build a 1-row DataFrame with the catalog's raw_column names
    # + country + year. physint / kill are populated; the other 5
    # are missing (None) to exercise the missing-cell branch.
    missing_data = {
        "country": ["Testland"],
        "year": [2022],
        "Physical Integrity Rights Index": [5],
        "Repression Index": [None],
        "Civil and Political Rights Index": [None],
        "Disappearances": [1],
        "Extrajudicial Killings": [None],
        "Political Imprisonment": [None],
        "Torture": [None],
    }
    df_inject = pd.DataFrame(missing_data)
    specs = [
        IndicatorSpec(
            variable_name="cirights_physint",
            raw_column="Physical Integrity Rights Index",
            category="domestic_violence",
            raw_scale="0-8",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_sum",
            description="Physical Integrity Rights Index",
        ),
        IndicatorSpec(
            variable_name="cirights_repression",
            raw_column="Repression Index",
            category="domestic_violence",
            raw_scale="0-17",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_sum",
            description="Repression Index",
        ),
        IndicatorSpec(
            variable_name="cirights_civpol",
            raw_column="Civil and Political Rights Index",
            category="domestic_violence",
            raw_scale="0-6",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_sum",
            description="Civil and Political Rights Index",
        ),
        IndicatorSpec(
            variable_name="cirights_disap",
            raw_column="Disappearances",
            category="domestic_violence",
            raw_scale="0-2",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_ordinal",
            description="Disappearances",
        ),
        IndicatorSpec(
            variable_name="cirights_kill",
            raw_column="Extrajudicial Killings",
            category="domestic_violence",
            raw_scale="0-2",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_ordinal",
            description="Extrajudicial Killings",
        ),
        IndicatorSpec(
            variable_name="cirights_polpris",
            raw_column="Political Imprisonment",
            category="domestic_violence",
            raw_scale="0-2",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_ordinal",
            description="Political Imprisonment",
        ),
        IndicatorSpec(
            variable_name="cirights_tort",
            raw_column="Torture",
            category="domestic_violence",
            raw_scale="0-2",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_ordinal",
            description="Torture",
        ),
    ]
    df_out = read_cirights_from_dataframe(df_inject, specs)

    # The 2 populated cells (physint=5, disap=1) survive.
    assert int(df_out["cirights_physint"].iloc[0]) == 5
    assert int(df_out["cirights_disap"].iloc[0]) == 1
    # The 5 missing cells become pd.NA.
    for col in [
        "cirights_repression", "cirights_civpol", "cirights_kill",
        "cirights_polpris", "cirights_tort",
    ]:
        assert pd.isna(df_out[col].iloc[0]), (
            f"Expected {col} to be NA, got {df_out[col].iloc[0]!r}"
        )

    # The raw_lookup attr records the literal cell text ("" for
    # the missing cells, "5" / "1" for the populated ones).
    raw_lookup = df_out.attrs.get("_cirights_raw_lookup", {})
    assert raw_lookup[("Testland", 2022, "cirights_physint")] == "5"
    assert raw_lookup[("Testland", 2022, "cirights_disap")] == "1"
    for col in [
        "cirights_repression", "cirights_civpol", "cirights_kill",
        "cirights_polpris", "cirights_tort",
    ]:
        assert raw_lookup[("Testland", 2022, col)] == ""


def test_xlsx_reader_returns_wide_frame_with_seven_indicator_columns(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """The output has exactly 7 indicator columns named
    cirights_physint, cirights_repression, cirights_civpol,
    cirights_disap, cirights_kill, cirights_polpris, cirights_tort.
    """
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    expected_indicators = {
        "cirights_physint", "cirights_repression", "cirights_civpol",
        "cirights_disap", "cirights_kill", "cirights_polpris",
        "cirights_tort",
    }
    assert set(df.columns) == {"country", "year"} | expected_indicators, (
        f"Column mismatch: {set(df.columns)}"
    )


def test_xlsx_reader_short_circuits_on_out_of_range_year(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """For year=2023 with the fixture (which only has 2021/2022
    data), the DataFrame is empty (no rows match)."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(
        xlsx_path=xlsx_path, year=2023, catalog_path=cirights_catalog_path,
    )
    assert df.empty, (
        f"Expected empty DataFrame for year=2023 with the fixture, "
        f"got {len(df)} rows"
    )


def test_xlsx_reader_year_window_attr(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """The wide frame's ``year_window`` attr is (2021, 2022) for
    the full fixture (no year filter)."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    assert df.attrs.get("year_window") == (2021, 2022), (
        f"Expected year_window=(2021, 2022), "
        f"got {df.attrs.get('year_window')}"
    )


def test_xlsx_reader_raw_lookup_preserves_original_cell(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """The wide frame's ``_cirights_raw_lookup`` attr preserves the
    original xlsx cell text (int as string) for audit/debugging."""
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)

    raw_lookup = df.attrs.get("_cirights_raw_lookup")
    assert raw_lookup is not None, (
        "Wide frame should carry _cirights_raw_lookup in attrs"
    )
    assert isinstance(raw_lookup, dict)
    # 10 rows x 7 indicators = 70 entries (the raw_lookup includes
    # entries for missing cells, with the empty string as the
    # cell text; the wide frame's Int64 column has pd.NA for those).
    assert len(raw_lookup) == 70, (
        f"Expected 70 raw_lookup entries (10 rows x 7 indicators), "
        f"got {len(raw_lookup)}"
    )
    # Norway 2022 physint -> "8"
    assert raw_lookup[("Norway", 2022, "cirights_physint")] == "8"
    # China 2022 civpol -> "0"
    assert raw_lookup[("China", 2022, "cirights_civpol")] == "0"


# ---------------------------------------------------------------------------
# §3 — Helpers (3 tests)
# ---------------------------------------------------------------------------


def test_safe_country_token_substitutes_unsafe_chars() -> None:
    """``safe_country_token`` substitutes URL-unsafe characters
    (spaces, slashes, apostrophes) with underscores; preserves
    non-ASCII characters verbatim (e.g. diacritics)."""
    assert safe_country_token is not None, (
        "cirights_io module not implemented"
    )
    assert safe_country_token("Mexico") == "Mexico"
    assert safe_country_token("United States of America") == (
        "United_States_of_America"
    )
    assert safe_country_token("Cote d'Ivoire") == "Cote_d_Ivoire"
    # Trailing whitespace + multiple internal spaces -> single _.
    assert safe_country_token("  Sao  Tome  ") == "Sao_Tome"
    # Non-ASCII is preserved (the data has no diacritics in the
    # display name, but the helper must not strip them).
    assert safe_country_token("Côte d'Ivoire") == "Côte_d_Ivoire"
    # Empty string -> empty string.
    assert safe_country_token("") == ""


# ---------------------------------------------------------------------------
# §4 — DB writers (8 tests)
# ---------------------------------------------------------------------------


def test_db_writers_write_sources_row(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """After ingest_cirights(year=2022), the sources table has a row
    with the canonical source_name + version."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        year=2022,
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == result.source_id)
        ).scalar_one()
        assert row.source_name == "CIRI Human Rights Data Project"
        assert row.version == "v3.12.10.24"
        assert row.source_type == "academic"


def test_db_writers_write_observations_rows(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """The source_observations table has rows for each
    ``(country, year, indicator)`` triple. For the full fixture
    (10 country-year pairs x 7 indicators = 70 possible), 66
    observations are expected (4 cells are missing: US 2021 and
    US 2022 have None for Repression Index and Civil and Political
    Rights Index per the live xlsx; per the design contract,
    missing cells are NOT written to source_observations)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == result.source_id,
            )
        ).scalar_one()
    assert count == 66, f"Expected 66 observations, got {count}"


def test_db_writers_country_id_and_confidence_are_null(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """country_id and confidence are NULL for all CIRIGHTS rows
    (Stage 3 fills country_id; Stage 11 fills confidence).
    leader_id is also NULL (no leader association at Stage 2)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == result.source_id,
            )
        ).scalars().all()

    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows)


def test_db_writers_manifest_written(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """The run_manifest JSON is written with source_key='cirights'
    and the expected observation_rows count (66 for the fixture
    with 4 missing cells)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    manifest = result.parquet_path.parent / "cirights_run_manifest.json"
    assert manifest.exists(), f"Manifest not found at {manifest}"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload.get("source_key") == "cirights"
    assert payload.get("observation_rows") == 66


def test_db_writers_idempotent_rerun(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """Running ingest_cirights(year=2022) twice produces the same
    final state (no double-writes). For year=2022 with the fixture,
    33 observations are expected (5 countries x 7 indicators = 35
    possible; US 2022 has None for Repression Index and Civil and
    Political Rights Index, so 2 are missing -> 33)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    first = ingest_cirights(
        year=2022,
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    second = ingest_cirights(
        year=2022,
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 33

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == first.source_id,
            )
        ).scalar_one()
    # 5 countries x 7 indicators = 35 possible; US 2022 has 2
    # missing cells -> 33 observations for year=2022.
    assert count == 33, f"Expected 33 observations, got {count}"


def test_db_writers_preserve_raw_value(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """For Norway 2022 physint, the raw_value preserves the
    original int 8 as the string '8'."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    with session_scope(database_url) as session:
        row = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == result.source_id,
                SourceObservation.variable_name == "cirights_physint",
                SourceObservation.year == 2022,
                SourceObservation.source_row_reference
                == "cirights:Norway:2022:Physical Integrity Rights Index",
            )
        ).scalar_one()
    assert row.raw_value == "8", (
        f"Norway 2022 physint raw_value should be '8', "
        f"got {row.raw_value!r}"
    )
    assert row.normalized_value == 8.0


def test_db_writers_source_row_reference_uses_country_token(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """Every source_row_reference starts with ``cirights:`` and the
    country token is URL-safe-substituted (e.g. ``United_States_of_America``).
    """
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )

    with session_scope(database_url) as session:
        refs = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.source_id == result.source_id,
            )
        ).scalars().all()

    assert all(r.startswith("cirights:") for r in refs)
    # United States of America -> United_States_of_America
    assert any(
        "United_States_of_America" in r for r in refs
    ), f"Expected a US reference with underscore token, got: {refs[:3]}"


def test_db_writers_parquet_written_with_metadata(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path,
) -> None:
    """The parquet file exists at data/processed/cirights/ and has
    CIRIGHTS attribution in the parquet metadata."""
    assert write_cirights_parquet is not None, (
        "cirights_io module not implemented"
    )
    assert read_cirights is not None, (
        "cirights_io module not implemented"
    )
    assert CIRIGHTS_ATTRIBUTION is not None, (
        "cirights_io module not implemented"
    )

    xlsx_path = cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx"
    df = read_cirights(xlsx_path=xlsx_path, catalog_path=cirights_catalog_path)
    out = write_cirights_parquet(df)

    assert out.exists()
    assert out.parent.name == "cirights"

    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"cirights_attribution")
    assert attribution_bytes is not None, (
        "parquet missing cirights_attribution"
    )
    assert attribution_bytes.decode("utf-8") == CIRIGHTS_ATTRIBUTION
    assert meta.get(b"cirights_source_key") == b"cirights"


# ---------------------------------------------------------------------------
# §5 — Drift-guard (1 test)
# ---------------------------------------------------------------------------


def test_cirights_attribution_matches_attributions_doc() -> None:
    """CIRIGHTS_ATTRIBUTION is a substring of
    docs/sources/attributions.md (drift guard; Always-On Rule #15).
    The exact wording is the ``cirights`` Stage 15 "Attribution
    text in reports" line in the document.
    """
    assert CIRIGHTS_ATTRIBUTION is not None, (
        "cirights_io module not implemented"
    )

    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "sources/attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert CIRIGHTS_ATTRIBUTION in doc_text, (
        f"CIRIGHTS_ATTRIBUTION not found in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# §6 — Orchestrator (5 tests)
# ---------------------------------------------------------------------------


def test_orchestrator_returns_pydantic_ingest_result(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """ingest_cirights() returns a CirightsIngestResult instance
    (not a dict or dataclass)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    assert CirightsIngestResult is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    assert isinstance(result, CirightsIngestResult)


def test_orchestrator_attribution_in_result(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """The result's attribution property returns the
    CIRIGHTS_ATTRIBUTION constant byte-for-byte."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    assert CIRIGHTS_ATTRIBUTION is not None, (
        "cirights_io module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    assert result.attribution == CIRIGHTS_ATTRIBUTION


def test_orchestrator_year_window(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """The result's year_window is (2021, 2022) for the full
    fixture run (no year filter)."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    assert result.year_window == (2021, 2022), (
        f"Expected year_window=(2021, 2022), got {result.year_window}"
    )


def test_orchestrator_proxy_year_semantics_for_2023(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """When the caller asks for year=2023, the orchestrator maps
    to 2022 (the 1-year-gap proxy) and records the mapping on
    the result and in the run manifest.

    Note: the fixture has data for 2021 and 2022 only. For
    year=2023, the adapter maps to 2022 and reads 2022 data.
    With 5 countries x 7 indicators = 35 possible, US 2022 has
    2 missing cells -> 33 observations for the 2023->2022 proxy.
    """
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        year=2023,  # The prototype target year
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    # 2023 -> 2022 proxy: 5 countries x 7 indicators = 35 possible;
    # US 2022 has 2 missing cells -> 33 observations.
    assert result.observation_rows == 33, (
        f"Expected 33 observations for the 2023->2022 proxy "
        f"(5 countries x 7 indicators - 2 missing), "
        f"got {result.observation_rows}"
    )
    assert result.years == (2022,), (
        f"Expected years=(2022,) for the 2023->2022 proxy, "
        f"got {result.years}"
    )
    assert result.proxy_year_semantics is not None, (
        "proxy_year_semantics should be set for the 2023->2022 proxy"
    )
    assert "2023" in result.proxy_year_semantics
    assert "2022" in result.proxy_year_semantics
    # Manifest records the proxy mapping.
    manifest = result.parquet_path.parent / "cirights_run_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload.get("proxy_year_semantics") is not None
    assert payload.get("requested_year") == 2023
    assert payload.get("proxy_requested_year") == 2023
    assert payload.get("proxy_data_year") == 2022


def test_orchestrator_short_circuits_on_out_of_range_year(
    cirights_xlsx_dir: Path, cirights_catalog_path: Path, database_url: str,
) -> None:
    """ingest_cirights(year=1900) returns an empty
    CirightsIngestResult without raising."""
    assert ingest_cirights is not None, (
        "cirights module not implemented"
    )
    _init_test_db(database_url)

    result = ingest_cirights(
        year=1900,
        xlsx_path=cirights_xlsx_dir / "cirights_v3.12.10.24.xlsx",
        catalog_path=cirights_catalog_path,
    )
    assert result.countries == 0
    assert result.observation_rows == 0
    assert result.years == ()
    assert result.parquet_path.exists()


# ---------------------------------------------------------------------------
# §7 — Public surface (1 test)
# ---------------------------------------------------------------------------


def test_cirights_module_public_surface() -> None:
    """The cirights module re-exports ingest_cirights,
    CirightsIngestResult, and CIRIGHTS_ATTRIBUTION (and all other
    documented public symbols)."""
    assert cirights is not None, "cirights module not implemented yet"

    for name in cirights.__all__:
        assert hasattr(cirights, name), f"cirights.{name} not found in __all__"
        assert getattr(cirights, name) is not None, (
            f"cirights.{name} is None"
        )

    # Key public symbols
    assert hasattr(cirights, "ingest_cirights")
    assert hasattr(cirights, "CirightsIngestResult")
    assert hasattr(cirights, "CIRIGHTS_ATTRIBUTION")
    assert hasattr(cirights, "CIRIGHTS_SOURCE_KEY")
    assert hasattr(cirights, "IndicatorSpec")
    assert hasattr(cirights, "attribution")
    assert hasattr(cirights, "load_indicator_catalog")
    assert hasattr(cirights, "read_cirights")
    assert hasattr(cirights, "register_cirights_source")
    assert hasattr(cirights, "write_cirights_observations")
    assert hasattr(cirights, "write_cirights_parquet")
    assert hasattr(cirights, "write_cirights_run_manifest")
    assert hasattr(cirights, "safe_country_token")


# ---------------------------------------------------------------------------
# §8 — STAGE2_ADAPTERS dispatch (1 test)
# ---------------------------------------------------------------------------


def test_cirights_dispatch_entry() -> None:
    """``STAGE2_ADAPTERS['cirights']`` is the orchestrator function.

    After the Phase C.10 integration pass, the CIRIGHTS orchestrator
    is wired into the central dispatch table; the pre-existing
    ``"cirights": None`` stub is replaced with
    ``cirights.ingest_cirights``. This is the boundary test that
    fails if the production wiring is removed.
    """
    assert cirights is not None
    assert cirights.ingest_cirights is not None
    assert "cirights" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["cirights"] is cirights.ingest_cirights
    # The dispatch is callable through the public surface.
    assert callable(STAGE2_ADAPTERS["cirights"])


# ---------------------------------------------------------------------------
# §9 — Public constants (1 test)
# ---------------------------------------------------------------------------


def test_cirights_constants() -> None:
    """The CIRIGHTS module-level constants have the expected
    values: source_key='cirights', year_window=(1981, 2022),
    proxy=(2023, 2022), attribution substring check.
    """
    assert CIRIGHTS_SOURCE_KEY == "cirights"
    assert CIRIGHTS_YEAR_START == 1981
    assert CIRIGHTS_YEAR_END == 2022
    assert CIRIGHTS_PROXY_REQUESTED_YEAR == 2023
    assert CIRIGHTS_PROXY_YEAR == 2022
    # Attribution substring check (the exact wording is in §5
    # drift-guard above).
    assert "CIRI Human Rights Data Project v3.12.10.24" in (
        CIRIGHTS_ATTRIBUTION
    )
    assert "Cingranelli, Richards, and Crepaz 2024" in CIRIGHTS_ATTRIBUTION
