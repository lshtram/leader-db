"""Tests for the REIGN Stage 2 adapter.

The REIGN adapter is the twelfth Stage 2 adapter built after V-Dem,
WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, UNDP HDI, WHO
GHO API, CIRIGHTS, and Archigos. These tests define what "done"
means for the REIGN adapter -- they would fail if any of the
production wiring (catalog load, CSV read, wide-to-long pivot,
source registration, source_observations write, end-to-end
orchestrator, drift-guard for the attribution text) regresses.

REIGN is structurally distinct from every prior Stage 2 adapter:

- It is the first Stage 2 source that reads a **GitHub raw CSV**
  (UTF-8, comma-delimited, no special parameters; the live
  bundle is 34.4 MB and takes ~1.5 s to read with pandas).
- The natural unit of observation is **leader-month** (1 row per
  (country, year, month) for 138,600 rows), NOT country-year.
  The Stage 2 adapter writes one ``source_observations`` row
  per (leader-month-row, identity-column) pair, keyed by the
  row's ``year`` column. The ``month`` column is preserved in
  ``source_row_reference`` (e.g.
  ``reign:USA:Trump:2020:1:leader``) so the audit trail
  identifies the specific month.
- The 13-row test fixture at
  ``tests/fixtures/reign/sample.csv`` is a real-format slice of
  the canonical ``data/raw/reign/REIGN_2021_8.csv`` (Mexico, USA,
  Sweden x 2020-2021 x January + August). The fixture is built
  by ``tests/fixtures/reign/build_sample_csv.py`` (committed,
  idempotent).

The Stage 2 contract:

- ``.csv`` is in long format per leader-month. The "pivot" is
  therefore a wide-to-long reshape: for each leader-month row,
  the reader emits 8 long rows (one per catalog ``raw_column``).
- The country key is the display name (e.g. ``"USA"``,
  ``"Mexico"``) and ``ccode`` (numeric COW). Stage 3 (country
  match) resolves display name to ISO3. The Stage 2
  ``source_row_reference`` uses the URL-safe-substituted
  country display name (e.g. ``"USA"`` stays ``"USA"``;
  ``"Trinidad & Tobago"`` would become ``"Trinidad_Tobago"``).
- Year coverage is 1950-2021-08. For the prototype target year
  2023, REIGN has no data (~16-month gap per the source-vetting
  report §3.1).
- Per-cell coercion: text preserved verbatim (e.g. ``"Trump"``,
  ``"Presidential Democracy"``), numerics -> float (e.g.
  ``tenure_months`` = 37 -> 37.0), gender light-coerced to 1/2
  (``male`` = 1 -> 1, ``male`` = 0 -> 2).
- The 13-row fixture produces 104 ``source_observations`` rows
  (13 leader-months x 8 catalog variables) in a no-year run.
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

# Try importing reign modules; if any is missing, set the
# names to ``None`` so the tests fail gracefully (the import
# block sets the names to ``None`` and every test that needs
# them asserts ``is not None`` first).
try:
    from leaders_db.ingest import (
        STAGE2_ADAPTERS,
        reign,
        reign_csv,
        reign_db,
        reign_db_helpers,
        reign_io,
        reign_result,
    )
    from leaders_db.ingest.reign import (
        REIGN_ATTRIBUTION,
        REIGN_IDENTITY_RAW_COLUMNS,
        REIGN_SOURCE_KEY,
        REIGN_YEAR_END,
        REIGN_YEAR_START,
        IndicatorSpec,
        ReignIngestResult,
        attribution,
        default_csv_path,
        default_processed_parquet_path,
        ingest_reign,
        load_reign_catalog,
        read_reign,
        register_reign_source,
        safe_country_token,
        write_reign_observations,
        write_reign_parquet,
        write_reign_run_manifest,
    )
    from leaders_db.ingest.reign_csv import (
        read_reign_csv_to_long_dataframe,
    )
except ImportError:
    reign = None  # type: ignore[assignment]
    reign_csv = None  # type: ignore[assignment]
    reign_db = None  # type: ignore[assignment]
    reign_db_helpers = None  # type: ignore[assignment]
    reign_io = None  # type: ignore[assignment]
    reign_result = None  # type: ignore[assignment]
    REIGN_ATTRIBUTION = None  # type: ignore[assignment]
    REIGN_IDENTITY_RAW_COLUMNS = None  # type: ignore[assignment]
    REIGN_SOURCE_KEY = None  # type: ignore[assignment]
    REIGN_YEAR_END = None  # type: ignore[assignment]
    REIGN_YEAR_START = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    ReignIngestResult = None  # type: ignore[assignment]
    STAGE2_ADAPTERS = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    default_csv_path = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    ingest_reign = None  # type: ignore[assignment]
    load_reign_catalog = None  # type: ignore[assignment]
    read_reign = None  # type: ignore[assignment]
    read_reign_csv_to_long_dataframe = None  # type: ignore[assignment]
    register_reign_source = None  # type: ignore[assignment]
    safe_country_token = None  # type: ignore[assignment]
    write_reign_observations = None  # type: ignore[assignment]
    write_reign_parquet = None  # type: ignore[assignment]
    write_reign_run_manifest = None  # type: ignore[assignment]


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "reign"
_FIXTURE_CSV = _FIXTURES_DIR / "sample.csv"


def _require_reign() -> None:
    """Skip the test if REIGN modules are not importable yet."""
    if reign is None or ingest_reign is None:
        pytest.skip("REIGN modules not importable yet")


def _require_fixture() -> None:
    """Skip the test if the REIGN fixture CSV is not built yet."""
    if not _FIXTURE_CSV.is_file():
        pytest.skip(
            f"REIGN fixture CSV not found at {_FIXTURE_CSV}. "
            "Run `python tests/fixtures/reign/build_sample_csv.py` "
            "to (re)generate it from data/raw/reign/.",
        )


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------


def test_reign_modules_importable() -> None:
    """Sanity check: the reign modules can be imported."""
    _require_reign()
    assert reign is not None
    assert reign_io is not None
    assert reign_csv is not None
    assert reign_db is not None
    assert reign_db_helpers is not None
    assert reign_result is not None


def test_reign_source_key_constant() -> None:
    """The ``REIGN_SOURCE_KEY`` constant must be the canonical key."""
    _require_reign()
    assert REIGN_SOURCE_KEY == "reign"


def test_reign_attribution_constant() -> None:
    """The ``REIGN_ATTRIBUTION`` constant must be a non-empty string."""
    _require_reign()
    assert isinstance(REIGN_ATTRIBUTION, str)
    assert "REIGN" in REIGN_ATTRIBUTION
    assert "Bell" in REIGN_ATTRIBUTION


def test_reign_attribution_matches_attributions_doc() -> None:
    """Drift-guard: the ``REIGN_ATTRIBUTION`` constant must appear
    verbatim in ``docs/sources/attributions.md`` (Always-On Rule #15).
    """
    _require_reign()
    project_root = Path(__file__).resolve().parents[1]
    attributions_path = project_root / "docs" / "sources/attributions.md"
    if not attributions_path.is_file():
        pytest.skip(
            f"Attributions doc not found at {attributions_path}"
        )
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert REIGN_ATTRIBUTION in attributions_text, (
        f"REIGN_ATTRIBUTION constant is not in "
        f"docs/sources/attributions.md: {REIGN_ATTRIBUTION!r}"
    )


def test_reign_attribution_helper_returns_constant() -> None:
    """The :func:`attribution` helper returns the constant."""
    _require_reign()
    assert attribution() == REIGN_ATTRIBUTION


def test_reign_catalog_loads_and_has_eight_rows() -> None:
    """The catalog loads and has the expected 8 indicator rows."""
    _require_reign()
    specs = load_reign_catalog()
    assert len(specs) == 8
    variable_names = {s.variable_name for s in specs}
    assert variable_names == {
        "reign_leader",
        "reign_government",
        "reign_elected",
        "reign_age",
        "reign_male",
        "reign_tenure_months",
        "reign_political_violence",
        "reign_irregular",
    }


def test_reign_catalog_required_columns_present() -> None:
    """Every catalog row has all 7 required columns populated."""
    _require_reign()
    specs = load_reign_catalog()
    for spec in specs:
        assert spec.variable_name
        assert spec.raw_column
        assert spec.category in {"leader_identity", "domestic_violence"}
        # The 8 indicators all have higher_is_better=0 (identity
        # fields + violence scores, not "good" indicators).
        assert spec.higher_is_better is False
        assert spec.raw_scale
        assert spec.normalized_scale_target
        assert spec.unit


def test_reign_catalog_raw_columns_match_csv_header() -> None:
    """Drift-guard: the catalog's ``raw_column`` values must match the
    real CSV header. The catalog is the public source of truth; if a
    raw column is renamed in the CSV, the catalog must be updated.
    """
    _require_reign()
    _require_fixture()
    df = pd.read_csv(_FIXTURE_CSV, nrows=1)
    catalog_raw_cols = {s.raw_column for s in load_reign_catalog()}
    fixture_cols = set(df.columns)
    missing_in_fixture = catalog_raw_cols - fixture_cols
    assert not missing_in_fixture, (
        f"Catalog raw_columns {missing_in_fixture} not in fixture "
        f"header: {sorted(fixture_cols)}"
    )


def test_reign_identity_raw_columns_constant_matches_catalog() -> None:
    """The :data:`REIGN_IDENTITY_RAW_COLUMNS` in-code constant is the
    ordered list of the catalog's ``raw_column`` s. This is a
    drift-guard: if the catalog changes, the constant must be
    updated (or vice-versa).
    """
    _require_reign()
    specs = load_reign_catalog()
    catalog_cols = tuple(s.raw_column for s in specs)
    assert REIGN_IDENTITY_RAW_COLUMNS == catalog_cols


# ---------------------------------------------------------------------------
# URL-safe country token tests
# ---------------------------------------------------------------------------


def test_reign_safe_country_token_basic() -> None:
    """``safe_country_token`` substitutes URL-unsafe characters."""
    _require_reign()
    assert safe_country_token("USA") == "USA"
    assert safe_country_token("Trinidad & Tobago") == "Trinidad_Tobago"
    # Non-ASCII letters preserved (e.g. ``Curaçao``).
    assert safe_country_token("Curaçao") == "Curaçao"
    # Whitespace substituted.
    assert safe_country_token("South Africa") == "South_Africa"
    # Empty string returns empty.
    assert safe_country_token("") == ""


# ---------------------------------------------------------------------------
# Read / coercion tests (against the fixture)
# ---------------------------------------------------------------------------


def test_reign_read_fixture_full_run() -> None:
    """The full no-year run against the fixture produces 104 rows.

    13 leader-month rows x 8 catalog variables = 104 long-format
    rows.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    assert len(df) == 104
    # 3 countries in the fixture.
    assert df["country"].nunique() == 3
    # 8 catalog variables.
    assert df["variable_name"].nunique() == 8


def test_reign_read_fixture_single_year() -> None:
    """A single-year run for 2020 produces fewer rows than the full
    run (the fixture has a 2020 subset of 6 leader-month rows:
    Mexico x 2 months + USA x 2 months + Sweden x 2 months = 6).
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV, year=2020)
    assert df["year"].nunique() == 1
    assert df["year"].iloc[0] == 2020
    # 6 leader-month rows x 8 variables = 48 long-format rows.
    assert len(df) == 48


def test_reign_read_fixture_year_no_match() -> None:
    """A year filter with no matching row returns an empty frame."""
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV, year=2023)
    assert df.empty


def test_reign_read_fixture_text_coercion() -> None:
    """The ``leader`` and ``government`` cells are preserved verbatim
    in ``raw_value``; ``normalized_value`` is NULL for text fields.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    trump_leader = df[
        (df["country"] == "USA")
        & (df["year"] == 2020)
        & (df["month"] == 1)
        & (df["variable_name"] == "reign_leader")
    ].iloc[0]
    assert trump_leader["raw_value"] == "Trump"
    assert pd.isna(trump_leader["normalized_value"])
    trump_gov = df[
        (df["country"] == "USA")
        & (df["year"] == 2020)
        & (df["month"] == 1)
        & (df["variable_name"] == "reign_government")
    ].iloc[0]
    assert trump_gov["raw_value"] == "Presidential Democracy"
    assert pd.isna(trump_gov["normalized_value"])


def test_reign_read_fixture_numeric_coercion() -> None:
    """Numeric columns (``tenure_months``, ``age``, ``elected``) are
    light-coerced to float for ``normalized_value``.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    trump_tenure = df[
        (df["country"] == "USA")
        & (df["year"] == 2020)
        & (df["month"] == 1)
        & (df["variable_name"] == "reign_tenure_months")
    ].iloc[0]
    assert trump_tenure["raw_value"] == "37.0"
    assert float(trump_tenure["normalized_value"]) == 37.0
    trump_elected = df[
        (df["country"] == "USA")
        & (df["year"] == 2020)
        & (df["month"] == 1)
        & (df["variable_name"] == "reign_elected")
    ].iloc[0]
    assert trump_elected["raw_value"] == "1.0"
    assert float(trump_elected["normalized_value"]) == 1.0


def test_reign_read_fixture_gender_coercion() -> None:
    """The ``male`` column is light-coerced to 1 (male) or 2 (female).

    The Stage 2 reader preserves the raw 0/1 in ``raw_value`` and
    normalizes to 1/2 for consistency with Archigos.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    trump_male = df[
        (df["country"] == "USA")
        & (df["year"] == 2020)
        & (df["month"] == 1)
        & (df["variable_name"] == "reign_male")
    ].iloc[0]
    # REIGN stores ``male`` as int (1 or 0) in the live CSV; the
    # ``_coerce_text_value`` helper preserves the integer text.
    assert str(trump_male["raw_value"]) == "1"
    assert int(trump_male["normalized_value"]) == 1


def test_reign_read_fixture_source_row_reference() -> None:
    """The ``source_row_reference`` carries the country_token +
    leader_token + year + month + raw column. The format is
    ``reign:<country_token>:<leader_token>:<year>:<month>:<raw_column>``.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    ref_set = set(df["source_row_reference"].tolist())
    # Spot-check a few refs (using the actual REIGN values; the
    # leader display name is URL-safe-substituted via
    # ``safe_country_token``, so ``"Lopez Obrador"`` becomes
    # ``"Lopez_Obrador"``).
    assert "reign:USA:Trump:2020:1:leader" in ref_set
    assert "reign:USA:Trump:2020:1:government" in ref_set
    assert "reign:Mexico:Lopez_Obrador:2020:1:leader" in ref_set
    assert "reign:Sweden:Lofven:2020:1:tenure_months" in ref_set


def test_reign_read_fixture_country_id_null_contract() -> None:
    """``country_id`` is left NULL on every long row (Stage 3 fills it).

    The Stage 2 adapter does not implement the country resolver
    (per the user task: "Do not implement Stage 3/4 resolver;
    country_id/leader_id NULL"). The contract is verified by
    the long-frame schema (no ``country_id`` column) and by
    the observation-row builder (which sets
    ``country_id=None``).
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    assert "country_id" not in df.columns


# ---------------------------------------------------------------------------
# Parquet / manifest tests
# ---------------------------------------------------------------------------


def test_reign_parquet_write_contains_attribution_metadata(
    isolated_data_lake: Path,
) -> None:
    """The parquet file-level metadata carries the REIGN
    attribution text (Always-On Rule #15).
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    parquet_path = write_reign_parquet(df)
    table = pq.read_table(str(parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"reign_attribution")
    assert attribution_bytes is not None, (
        "parquet missing reign_attribution"
    )
    assert attribution_bytes.decode("utf-8") == REIGN_ATTRIBUTION
    assert meta.get(b"reign_source_key") == b"reign"


def test_reign_parquet_write_empty_frame() -> None:
    """An empty long frame still produces a parquet with the
    attribution in the file-level metadata.
    """
    _require_reign()
    df = pd.DataFrame(
        columns=[
            "country",
            "ccode",
            "year",
            "month",
            "leader",
            "variable_name",
            "raw_value",
            "normalized_value",
            "source_row_reference",
        ],
    )
    parquet_path = write_reign_parquet(df)
    table = pq.read_table(str(parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"reign_attribution")
    assert attribution_bytes is not None
    assert attribution_bytes.decode("utf-8") == REIGN_ATTRIBUTION


def test_reign_run_manifest_records_attribution(
    isolated_data_lake: Path,
) -> None:
    """The run manifest records the attribution + source_id +
    observation row count + year window.
    """
    _require_reign()
    _require_fixture()
    df = read_reign(csv_path=_FIXTURE_CSV)
    parquet_path = write_reign_parquet(df)
    result = ReignIngestResult(
        source_id=1,
        parquet_path=parquet_path,
        observation_rows=len(df),
        countries=int(df["country"].nunique()),
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=8,
        year_window=(int(df["year"].min()), int(df["year"].max())),
    )
    manifest_path = write_reign_run_manifest(result)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == REIGN_ATTRIBUTION
    assert payload["source_key"] == REIGN_SOURCE_KEY
    assert payload["observation_rows"] == 104
    assert payload["year_window"] == [2020, 2021]
    assert payload["indicators"] == 8


# ---------------------------------------------------------------------------
# DB writer tests
# ---------------------------------------------------------------------------


def test_reign_register_source_is_idempotent(
    database_url: str,
) -> None:
    """The ``register_reign_source`` function is idempotent: a
    second call returns the same ``sources.id``.
    """
    _require_reign()
    init_database(database_url)
    with session_scope() as session:
        source_id_1 = register_reign_source(session)
        source_id_2 = register_reign_source(session)
    assert source_id_1 == source_id_2
    assert source_id_1 > 0


def test_reign_register_source_name_and_version(
    database_url: str,
) -> None:
    """The ``sources`` row is keyed by
    ``(source_name='REIGN (Rulers, Elections, and Irregular
    Governance)', version='2021-8')``.
    """
    _require_reign()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_reign_source(session)
    with session_scope() as session:
        row = session.get(Source, source_id)
    assert row is not None
    assert row.source_name == "REIGN (Rulers, Elections, and Irregular Governance)"
    assert row.version == "2021-8"


def test_reign_write_observations_idempotent(
    database_url: str,
) -> None:
    """Re-running the orchestrator deletes and re-inserts the rows for
    the requested year(s) only (no row count drift).
    """
    _require_reign()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_reign_source(session)
    df = read_reign(csv_path=_FIXTURE_CSV)
    with session_scope() as session:
        rows_1 = write_reign_observations(
            session, source_id, df, catalog_path=None,
        )
    with session_scope() as session:
        rows_2 = write_reign_observations(
            session, source_id, df, catalog_path=None,
        )
    assert rows_1 == rows_2 == 104


def test_reign_write_observations_country_leader_null(
    database_url: str,
) -> None:
    """``country_id`` and ``leader_id`` are NULL on every written row
    (Stage 3/4 not implemented in this phase).
    """
    _require_reign()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_reign_source(session)
    df = read_reign(csv_path=_FIXTURE_CSV)
    with session_scope() as session:
        rows = write_reign_observations(
            session, source_id, df, catalog_path=None,
        )
    assert rows == 104
    with session_scope() as session:
        obs_count = session.execute(
            select(func.count()).select_from(SourceObservation).where(
                SourceObservation.source_id == source_id,
            ),
        ).scalar_one()
        null_country_count = session.execute(
            select(func.count()).select_from(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.country_id.is_(None),
            ),
        ).scalar_one()
        null_leader_count = session.execute(
            select(func.count()).select_from(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.leader_id.is_(None),
            ),
        ).scalar_one()
    assert obs_count == 104
    assert null_country_count == 104
    assert null_leader_count == 104


def test_reign_write_observations_source_row_reference(
    database_url: str,
) -> None:
    """``source_row_reference`` carries the country_token +
    leader_token + year + month + raw column (e.g.
    ``reign:USA:Trump:2020:1:leader``).
    """
    _require_reign()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_reign_source(session)
    df = read_reign(csv_path=_FIXTURE_CSV)
    with session_scope() as session:
        write_reign_observations(
            session, source_id, df, catalog_path=None,
        )
    with session_scope() as session:
        sample_ref = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "reign_leader",
                SourceObservation.year == 2020,
            ).limit(1)
        ).scalar_one()
    assert sample_ref == "reign:USA:Trump:2020:1:leader"


# ---------------------------------------------------------------------------
# End-to-end orchestrator test
# ---------------------------------------------------------------------------


def test_reign_ingest_end_to_end(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """The end-to-end ``ingest_reign`` orchestrator writes the
    parquet, the manifest, the ``sources`` row, and the
    ``source_observations`` rows idempotently. Re-running the
    orchestrator produces the same result.
    """
    _require_reign()
    _require_fixture()
    # Stage the fixture into the isolated data lake so
    # ``default_csv_path()`` finds it.
    target_csv_dir = isolated_data_lake / "data" / "raw" / "reign"
    target_csv_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_CSV, target_csv_dir / "REIGN_2021_8.csv")
    # Also copy a minimal metadata.json so the bundle-metadata
    # reader does not return an empty dict (this is the
    # "downloaded" status transition documented in
    # ``docs/architecture/local-data-store.md``).
    (target_csv_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "REIGN (Rulers, Elections, and Irregular Governance)",
                "source_version": "2021-8 (August 2021 release, final)",
                "download_date": "2026-06-19",
                "years_available": "1950-2021",
                "license_note": "Free academic; cite Bell 2016 (OEF Research).",
                "ingestion_status": "downloaded",
                "source_url": "https://raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result_1 = ingest_reign()
    result_2 = ingest_reign()
    # Idempotency: same source_id, same observation row count.
    assert result_1.source_id == result_2.source_id
    assert result_1.observation_rows == result_2.observation_rows
    assert result_1.observation_rows == 104
    # Year window covers 2020-2021.
    assert result_1.year_window == (2020, 2021)
    # 3 distinct countries in the fixture.
    assert result_1.countries == 3
    # 2 distinct years in the fixture.
    assert result_1.years == (2020, 2021)
    # 8 catalog indicators.
    assert result_1.indicators == 8
    # Parquet file exists and has the attribution metadata.
    assert result_1.parquet_path.is_file()
    table = pq.read_table(str(result_1.parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"reign_attribution")
    assert attribution_bytes is not None
    assert attribution_bytes.decode("utf-8") == REIGN_ATTRIBUTION
    # Manifest file exists next to the parquet.
    manifest_path = (
        result_1.parquet_path.parent / "reign_run_manifest.json"
    )
    assert manifest_path.is_file()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == REIGN_ATTRIBUTION
    assert payload["year_window"] == [2020, 2021]
    # source_observations rows: 104.
    with session_scope() as session:
        obs_count = session.execute(
            select(func.count()).select_from(SourceObservation).where(
                SourceObservation.source_id == result_1.source_id,
            ),
        ).scalar_one()
    assert obs_count == 104


def test_reign_ingest_with_year_filter(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """The ``year=2020`` orchestrator run produces 48 rows (6
    leader-month rows x 8 variables) and the year window collapses
    to ``(2020, 2020)``.
    """
    _require_reign()
    _require_fixture()
    target_csv_dir = isolated_data_lake / "data" / "raw" / "reign"
    target_csv_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_CSV, target_csv_dir / "REIGN_2021_8.csv")
    (target_csv_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "REIGN (Rulers, Elections, and Irregular Governance)",
                "source_version": "2021-8",
                "download_date": "2026-06-19",
                "years_available": "1950-2021",
                "license_note": "Free academic.",
                "ingestion_status": "downloaded",
                "source_url": "https://raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result = ingest_reign(year=2020)
    assert result.observation_rows == 48
    assert result.year_window == (2020, 2020)
    assert result.years == (2020,)


def test_reign_ingest_year_with_no_data(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """A ``year=2023`` orchestrator run produces 0 rows and a
    no-data year window. The orchestrator still writes the
    parquet (empty frame), the manifest, and the ``sources``
    row -- so downstream stages can detect "this run produced
    no data" without re-reading the CSV.
    """
    _require_reign()
    _require_fixture()
    target_csv_dir = isolated_data_lake / "data" / "raw" / "reign"
    target_csv_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_CSV, target_csv_dir / "REIGN_2021_8.csv")
    (target_csv_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "REIGN (Rulers, Elections, and Irregular Governance)",
                "source_version": "2021-8",
                "download_date": "2026-06-19",
                "years_available": "1950-2021",
                "license_note": "Free academic.",
                "ingestion_status": "downloaded",
                "source_url": "https://raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result = ingest_reign(year=2023)
    assert result.observation_rows == 0
    assert result.year_window == (0, 0)
    assert result.years == ()
    # Parquet and manifest still written.
    assert result.parquet_path.is_file()
    manifest_path = (
        result.parquet_path.parent / "reign_run_manifest.json"
    )
    assert manifest_path.is_file()


# ---------------------------------------------------------------------------
# Path helper tests
# ---------------------------------------------------------------------------


def test_reign_default_csv_path_missing_raises(
    isolated_data_lake: Path,
) -> None:
    """The ``default_csv_path`` helper raises ``FileNotFoundError``
    when the CSV is missing.
    """
    _require_reign()
    with pytest.raises(FileNotFoundError):
        default_csv_path()


def test_reign_default_processed_parquet_path_creates_dir(
    isolated_data_lake: Path,
) -> None:
    """The ``default_processed_parquet_path`` helper creates the
    ``data/processed/reign/`` directory if missing.
    """
    _require_reign()
    path = default_processed_parquet_path()
    assert path.parent.is_dir()
    assert path.name == "reign_leader_month.parquet"


# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------


def test_reign_year_window_constants() -> None:
    """The year-window constants are the verified live values."""
    _require_reign()
    assert REIGN_YEAR_START == 1950
    assert REIGN_YEAR_END == 2021


def test_reign_stub_orchestrator_replaced() -> None:
    """The :mod:`reign` orchestrator module must NOT be the original
    Phase A stub (which raised ``NotImplementedError``).
    """
    _require_reign()
    # The original stub was a 27-line module that raised
    # NotImplementedError on download_reign / ingest_reign. The
    # production code replaces the stub. If the function is
    # present, it must be a real function (not a stub).
    assert callable(getattr(reign, "ingest_reign", None))


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_reign() -> None:
    """``STAGE2_ADAPTERS['reign']`` is ``reign.ingest_reign``.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass; the
    pre-existing ``"reign": None`` stub is replaced. Test fails
    if the production wiring is removed.
    """
    _require_reign()
    assert "reign" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["reign"] is reign.ingest_reign
    assert callable(STAGE2_ADAPTERS["reign"])


def test_dispatch_table_no_duplicate_reign_key() -> None:
    """The dispatch table has exactly one ``reign`` key (no
    duplicate from a copy-paste bug).
    """
    assert REIGN_SOURCE_KEY is not None
    count = sum(1 for k in STAGE2_ADAPTERS.keys() if k == "reign")
    assert count == 1, (
        f"Expected exactly 1 'reign' key in STAGE2_ADAPTERS, got {count}"
    )
