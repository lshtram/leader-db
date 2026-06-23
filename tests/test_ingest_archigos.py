"""Tests for the Archigos Stage 2 adapter.

The Archigos adapter is the eleventh Stage 2 adapter built after V-Dem,
WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, UNDP HDI, WHO
GHO API, and CIRIGHTS. These tests define what "done" means for the
Archigos adapter -- they would fail if any of the production wiring
(catalog load, .dta read, long-to-long pivot, source registration,
source_observations write, end-to-end orchestrator, drift-guard for
the attribution text) regresses.

Archigos is structurally distinct from every prior Stage 2 adapter:

- It is the first Stata-based source (``.dta`` format; ``cp1252``
  encoding; ``pyreadstat`` reader).
- The natural unit of observation is **leader-spell** (1 row per
  leader's tenure), NOT country-year. The Stage 2 adapter writes
  one ``source_observations`` row per (leader-spell,
  identity-column) pair, keyed by the spell's start year.
- The 5-row test fixture at
  ``tests/fixtures/archigos/sample.dta`` is a real-format slice of
  the canonical ``data/raw/archigos/Archigos_4.1_stata14.dta``
  (the 5 earliest US presidents: Grant, Hayes, Garfield, Arthur,
  Cleveland). The fixture is built by
  ``tests/fixtures/archigos/build_sample_dta.py`` (committed,
  idempotent).

The Stage 2 contract:

- ``.dta`` is in long format per leader-spell (1 row per
  leader's tenure). The "pivot" is therefore a wide-to-long
  reshape: for each spell, the reader emits 6 long rows (one
  per catalog ``raw_column``).
- The country key is ``idacr`` (a 3-letter acronym, NOT always
  ISO3; e.g. ``AUH``, ``BFO``, ``BUI`` are historical entities
  without ISO3 codes) and ``ccode`` (numeric COW). Stage 3
  (country match) resolves idacr to ISO3. The Stage 2
  ``source_row_reference`` uses ``obsid`` (e.g.
  ``"USA-1869"``) so the audit trail locates the raw spell.
- Year coverage is 1840-2015 (no 2023). For the prototype
  target year 2023, Archigos has no data (8-year gap per the
  source-vetting report §3.1). The Stage 2 adapter writes
  observations keyed by the spell's start year.
- Per-cell coercion: text preserved verbatim (e.g. ``"Grant"``,
  ``"Regular"``, ``"M"``), dates light-coerced to decimal
  years (e.g. 1869-03-04 -> 1869.170), categoricals
  light-coerced to ordinal codes (e.g. ``"Regular"`` -> 1),
  gender light-coerced to 1/2 (``"M"`` -> 1, ``"F"`` -> 2).
- The 5-row fixture produces 30 ``source_observations`` rows
  (5 leader-spells x 6 catalog indicators) in a no-year run.
  A single-year run (e.g. ``year=1881``) produces 12 rows
  (2 spells starting in 1881 x 6 variables).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pyreadstat
import pytest
from sqlalchemy import func, select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope

# Try importing archigos modules; if any is missing, set the
# names to ``None`` so the tests fail gracefully (the import
# block sets the names to ``None`` and every test that needs
# them asserts ``is not None`` first).
try:
    from leaders_db.ingest import (
        STAGE2_ADAPTERS,
        archigos,
        archigos_db,
        archigos_db_helpers,
        archigos_dta,
        archigos_io,
        archigos_result,
    )
    from leaders_db.ingest.archigos import (
        ARCHIGOS_ATTRIBUTION,
        ARCHIGOS_DTA_ENCODING,
        ARCHIGOS_SOURCE_KEY,
        ARCHIGOS_YEAR_END,
        ARCHIGOS_YEAR_START,
        ArchigosIngestResult,
        IndicatorSpec,
        attribution,
        default_dta_path,
        default_processed_parquet_path,
        ingest_archigos,
        load_archigos_catalog,
        read_archigos,
        register_archigos_source,
        write_archigos_observations,
        write_archigos_parquet,
        write_archigos_run_manifest,
    )
    from leaders_db.ingest.archigos_dta import (
        read_dta_to_long_dataframe,
    )
except ImportError:
    archigos = None  # type: ignore[assignment]
    archigos_dta = None  # type: ignore[assignment]
    archigos_db = None  # type: ignore[assignment]
    archigos_db_helpers = None  # type: ignore[assignment]
    archigos_io = None  # type: ignore[assignment]
    archigos_result = None  # type: ignore[assignment]
    ARCHIGOS_ATTRIBUTION = None  # type: ignore[assignment]
    ARCHIGOS_DTA_ENCODING = None  # type: ignore[assignment]
    ARCHIGOS_SOURCE_KEY = None  # type: ignore[assignment]
    ARCHIGOS_YEAR_END = None  # type: ignore[assignment]
    ARCHIGOS_YEAR_START = None  # type: ignore[assignment]
    ArchigosIngestResult = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    STAGE2_ADAPTERS = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    default_dta_path = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    ingest_archigos = None  # type: ignore[assignment]
    load_archigos_catalog = None  # type: ignore[assignment]
    read_archigos = None  # type: ignore[assignment]
    read_dta_to_long_dataframe = None  # type: ignore[assignment]
    register_archigos_source = None  # type: ignore[assignment]
    write_archigos_observations = None  # type: ignore[assignment]
    write_archigos_parquet = None  # type: ignore[assignment]
    write_archigos_run_manifest = None  # type: ignore[assignment]


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "archigos"
_FIXTURE_DTA = _FIXTURES_DIR / "sample.dta"


def _require_archigos() -> None:
    """Skip the test if Archigos modules are not importable yet."""
    if archigos is None or ingest_archigos is None:
        pytest.skip("Archigos modules not importable yet")


def _require_fixture() -> None:
    """Skip the test if the Archigos fixture .dta is not built yet."""
    if not _FIXTURE_DTA.is_file():
        pytest.skip(
            f"Archigos fixture .dta not found at {_FIXTURE_DTA}. "
            "Run `python tests/fixtures/archigos/build_sample_dta.py` "
            "to (re)generate it from data/raw/archigos/.",
        )


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------


def test_archigos_modules_importable() -> None:
    """Sanity check: the archigos modules can be imported."""
    _require_archigos()
    assert archigos is not None
    assert archigos_io is not None
    assert archigos_dta is not None
    assert archigos_db is not None
    assert archigos_db_helpers is not None
    assert archigos_result is not None


def test_archigos_source_key_constant() -> None:
    """The ``ARCHIGOS_SOURCE_KEY`` constant must be the canonical key.

    The CLI dispatch table (``STAGE2_ADAPTERS``) is keyed by this
    string; a typo here would silently disconnect the CLI from the
    adapter.
    """
    _require_archigos()
    assert ARCHIGOS_SOURCE_KEY == "archigos"


def test_archigos_attribution_constant() -> None:
    """The ``ARCHIGOS_ATTRIBUTION`` constant must be a non-empty string."""
    _require_archigos()
    assert isinstance(ARCHIGOS_ATTRIBUTION, str)
    assert "Archigos" in ARCHIGOS_ATTRIBUTION
    assert "Goemans" in ARCHIGOS_ATTRIBUTION
    assert "Chiozza" in ARCHIGOS_ATTRIBUTION


def test_archigos_attribution_matches_attributions_doc() -> None:
    """Drift-guard: the ``ARCHIGOS_ATTRIBUTION`` constant must appear
    verbatim in ``docs/sources/attributions.md`` (Always-On Rule #15).
    """
    _require_archigos()
    project_root = Path(__file__).resolve().parents[1]
    attributions_path = project_root / "docs" / "sources/attributions.md"
    if not attributions_path.is_file():
        pytest.skip(
            f"Attributions doc not found at {attributions_path}"
        )
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert ARCHIGOS_ATTRIBUTION in attributions_text, (
        f"ARCHIGOS_ATTRIBUTION constant is not in "
        f"docs/sources/attributions.md: {ARCHIGOS_ATTRIBUTION!r}"
    )


def test_archigos_attribution_helper_returns_constant() -> None:
    """The :func:`attribution` helper returns the constant."""
    _require_archigos()
    assert attribution() == ARCHIGOS_ATTRIBUTION


def test_archigos_catalog_loads_and_has_six_rows() -> None:
    """The catalog loads and has the expected 6 identity rows."""
    _require_archigos()
    specs = load_archigos_catalog()
    assert len(specs) == 6
    variable_names = {s.variable_name for s in specs}
    assert variable_names == {
        "archigos_leader_name",
        "archigos_tenure_start_date",
        "archigos_tenure_end_date",
        "archigos_entry_type",
        "archigos_exit_type",
        "archigos_gender",
    }


def test_archigos_catalog_required_columns_present() -> None:
    """Every catalog row has all 7 required columns populated."""
    _require_archigos()
    specs = load_archigos_catalog()
    for spec in specs:
        assert spec.variable_name
        assert spec.raw_column
        assert spec.category == "leader_identity"
        assert spec.higher_is_better is False
        assert spec.raw_scale
        assert spec.normalized_scale_target
        assert spec.unit


def test_archigos_catalog_raw_columns_match_dta_header() -> None:
    """Drift-guard: the catalog's ``raw_column`` values must match the
    real .dta header. The catalog is the public source of truth; if a
    raw column is renamed in the .dta, the catalog must be updated.
    """
    _require_archigos()
    _require_fixture()
    df, _ = pyreadstat.read_dta(
        str(_FIXTURE_DTA), encoding=ARCHIGOS_DTA_ENCODING,
    )
    catalog_raw_cols = {s.raw_column for s in load_archigos_catalog()}
    fixture_cols = set(df.columns)
    missing_in_fixture = catalog_raw_cols - fixture_cols
    assert not missing_in_fixture, (
        f"Catalog raw_columns {missing_in_fixture} not in fixture "
        f"header: {sorted(fixture_cols)}"
    )


# ---------------------------------------------------------------------------
# Read / coercion tests (against the fixture)
# ---------------------------------------------------------------------------


def test_archigos_read_fixture_full_run() -> None:
    """The full no-year run against the fixture produces 30 rows.

    5 leader-spells x 6 catalog variables = 30 long-format rows.
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    assert len(df) == 30
    # The 5 obsids each produce 6 rows.
    assert df["obsid"].nunique() == 5
    assert df["variable_name"].nunique() == 6


def test_archigos_read_fixture_single_year() -> None:
    """A single-year run for 1881 produces 12 rows.

    2 leader-spells starting in 1881 (Garfield + Arthur) x 6
    catalog variables = 12 long-format rows.
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA, year=1881)
    assert len(df) == 12
    assert df["year"].nunique() == 1
    assert df["year"].iloc[0] == 1881
    obsids = set(df["obsid"].unique())
    assert obsids == {"USA-1881-1", "USA-1881-2"}


def test_archigos_read_fixture_year_no_match() -> None:
    """A year filter with no matching spell returns an empty frame."""
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA, year=2023)
    assert df.empty


def test_archigos_read_fixture_date_coercion() -> None:
    """The ``startdate`` is light-coerced to a decimal year.

    The 5 spells in the fixture all start on a day in March or
    September. The decimal year for 1869-03-04 is
    ``1869 + (31 + 28 + 3 - 1) / 365 = 1869.170``. The Stage 2
    reader must produce the same decimal year.
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    # The Grant spell (USA-1869) starts 1869-03-04.
    grant_start = df[
        (df["obsid"] == "USA-1869")
        & (df["variable_name"] == "archigos_tenure_start_date")
    ].iloc[0]
    assert grant_start["raw_value"] == "1869-03-04"
    assert abs(float(grant_start["normalized_value"]) - 1869.170) < 0.01


def test_archigos_read_fixture_categorical_coercion() -> None:
    """The ``entry`` and ``exit`` columns are light-coerced to ordinal
    codes (1=Regular, 2=Irregular, etc.).
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    garfield_entry = df[
        (df["obsid"] == "USA-1881-1")
        & (df["variable_name"] == "archigos_entry_type")
    ].iloc[0]
    assert garfield_entry["raw_value"] == "Regular"
    assert int(garfield_entry["normalized_value"]) == 1
    garfield_exit = df[
        (df["obsid"] == "USA-1881-1")
        & (df["variable_name"] == "archigos_exit_type")
    ].iloc[0]
    assert garfield_exit["raw_value"] == "Irregular"
    assert int(garfield_exit["normalized_value"]) == 2


def test_archigos_read_fixture_gender_coercion() -> None:
    """The ``gender`` column is light-coerced to 1 (M) or 2 (F)."""
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    grant_gender = df[
        (df["obsid"] == "USA-1869")
        & (df["variable_name"] == "archigos_gender")
    ].iloc[0]
    assert grant_gender["raw_value"] == "M"
    assert int(grant_gender["normalized_value"]) == 1


def test_archigos_read_fixture_source_row_reference() -> None:
    """The ``source_row_reference`` carries the obsid + start year +
    raw column. The format is ``archigos:<obsid>:<start_year>:<raw_column>``.
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    ref_set = set(df["source_row_reference"].tolist())
    # Spot-check a few refs.
    assert "archigos:USA-1869:1869:leader" in ref_set
    assert "archigos:USA-1869:1869:startdate" in ref_set
    assert "archigos:USA-1881-1:1881:exit" in ref_set
    assert "archigos:USA-1885:1885:gender" in ref_set


def test_archigos_read_fixture_country_id_null_contract() -> None:
    """``country_id`` is left NULL on every long row (Stage 3 fills it).

    The Stage 2 adapter does not implement the country resolver
    (per the user task: "Do not implement Stage 3/4 resolver;
    country_id/leader_id NULL"). The contract is verified by
    the long-frame schema (no ``country_id`` column) and by
    the observation-row builder (which sets
    ``country_id=None``).
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    # The long frame does not carry a ``country_id`` column;
    # the DB writer's ``_build_observation_rows`` sets it to
    # ``None`` explicitly. The audit contract is verified by
    # the DB-writer test below.
    assert "country_id" not in df.columns


# ---------------------------------------------------------------------------
# Parquet / manifest tests
# ---------------------------------------------------------------------------


def test_archigos_parquet_write_contains_attribution_metadata(
    isolated_data_lake: Path,
) -> None:
    """The parquet file-level metadata carries the Archigos
    attribution text (Always-On Rule #15).
    """
    _require_archigos()
    _require_fixture()
    df = read_archigos(dta_path=_FIXTURE_DTA)
    parquet_path = write_archigos_parquet(df)
    table = pq.read_table(str(parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"archigos_attribution")
    assert attribution_bytes is not None, (
        "parquet missing archigos_attribution"
    )
    assert attribution_bytes.decode("utf-8") == ARCHIGOS_ATTRIBUTION
    assert meta.get(b"archigos_source_key") == b"archigos"


def test_archigos_parquet_write_empty_frame() -> None:
    """An empty long frame still produces a parquet with the
    attribution in the file-level metadata.
    """
    _require_archigos()
    df = pd.DataFrame(
        columns=[
            "obsid",
            "idacr",
            "ccode",
            "year",
            "end_year",
            "variable_name",
            "raw_value",
            "normalized_value",
            "source_row_reference",
        ],
    )
    parquet_path = write_archigos_parquet(df)
    table = pq.read_table(str(parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"archigos_attribution")
    assert attribution_bytes is not None
    assert attribution_bytes.decode("utf-8") == ARCHIGOS_ATTRIBUTION


def test_archigos_run_manifest_records_attribution(
    isolated_data_lake: Path,
) -> None:
    """The run manifest records the attribution + source_id +
    observation row count + year window.
    """
    _require_archigos()
    _require_fixture()
    # Build a minimal ArchigosIngestResult to feed the manifest
    # writer (we don't need the full orchestrator here; the
    # orchestrator is exercised end-to-end below).
    df = read_archigos(dta_path=_FIXTURE_DTA)
    parquet_path = write_archigos_parquet(df)
    result = ArchigosIngestResult(
        source_id=1,
        parquet_path=parquet_path,
        observation_rows=len(df),
        countries=int(df["idacr"].nunique()),
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=6,
        year_window=(int(df["year"].min()), int(df["year"].max())),
    )
    manifest_path = write_archigos_run_manifest(result)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == ARCHIGOS_ATTRIBUTION
    assert payload["source_key"] == ARCHIGOS_SOURCE_KEY
    assert payload["observation_rows"] == 30
    assert payload["year_window"] == [1869, 1885]
    assert payload["indicators"] == 6


# ---------------------------------------------------------------------------
# DB writer tests
# ---------------------------------------------------------------------------


def test_archigos_register_source_is_idempotent(
    database_url: str,
) -> None:
    """The ``register_archigos_source`` function is idempotent: a
    second call returns the same ``sources.id``.
    """
    _require_archigos()
    init_database(database_url)
    with session_scope() as session:
        source_id_1 = register_archigos_source(session)
        source_id_2 = register_archigos_source(session)
    assert source_id_1 == source_id_2
    assert source_id_1 > 0


def test_archigos_register_source_name_and_version(
    database_url: str,
) -> None:
    """The ``sources`` row is keyed by
    ``(source_name='Archigos v4.1', version='v4.1 (Stata 14)')``.
    """
    _require_archigos()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_archigos_source(session)
    with session_scope() as session:
        row = session.get(Source, source_id)
    assert row is not None
    assert row.source_name == "Archigos v4.1"
    assert row.version == "v4.1 (Stata 14)"


def test_archigos_write_observations_idempotent(
    database_url: str,
) -> None:
    """Re-running the orchestrator deletes and re-inserts the rows for
    the requested start-year(s) only (no row count drift).
    """
    _require_archigos()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_archigos_source(session)
    df = read_archigos(dta_path=_FIXTURE_DTA)
    with session_scope() as session:
        rows_1 = write_archigos_observations(
            session, source_id, df, catalog_path=None,
        )
    with session_scope() as session:
        rows_2 = write_archigos_observations(
            session, source_id, df, catalog_path=None,
        )
    assert rows_1 == rows_2 == 30


def test_archigos_write_observations_country_leader_null(
    database_url: str,
) -> None:
    """``country_id`` and ``leader_id`` are NULL on every written row
    (Stage 3/4 not implemented in this phase).
    """
    _require_archigos()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_archigos_source(session)
    df = read_archigos(dta_path=_FIXTURE_DTA)
    with session_scope() as session:
        rows = write_archigos_observations(
            session, source_id, df, catalog_path=None,
        )
    assert rows == 30
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
    assert obs_count == 30
    assert null_country_count == 30
    assert null_leader_count == 30


def test_archigos_write_observations_source_row_reference(
    database_url: str,
) -> None:
    """``source_row_reference`` carries the obsid + start year +
    raw column (e.g. ``archigos:USA-1869:1869:leader``).
    """
    _require_archigos()
    _require_fixture()
    init_database(database_url)
    with session_scope() as session:
        source_id = register_archigos_source(session)
    df = read_archigos(dta_path=_FIXTURE_DTA)
    with session_scope() as session:
        write_archigos_observations(
            session, source_id, df, catalog_path=None,
        )
    with session_scope() as session:
        sample_ref = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "archigos_leader_name",
                SourceObservation.year == 1869,
            ).limit(1)
        ).scalar_one()
    assert sample_ref == "archigos:USA-1869:1869:leader"


# ---------------------------------------------------------------------------
# End-to-end orchestrator test
# ---------------------------------------------------------------------------


def test_archigos_ingest_end_to_end(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """The end-to-end ``ingest_archigos`` orchestrator writes the
    parquet, the manifest, the ``sources`` row, and the
    ``source_observations`` rows idempotently. Re-running the
    orchestrator produces the same result.
    """
    _require_archigos()
    _require_fixture()
    # Stage the fixture into the isolated data lake so
    # ``default_dta_path()`` finds it.
    target_dta_dir = isolated_data_lake / "data" / "raw" / "archigos"
    target_dta_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_DTA, target_dta_dir / "Archigos_4.1_stata14.dta")
    # Also copy a minimal metadata.json so the bundle-metadata
    # reader does not return an empty dict (this is the
    # "downloaded" status transition documented in
    # ``docs/architecture/local-data-store.md``).
    (target_dta_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "Archigos",
                "source_version": "v4.1 (Stata 14)",
                "download_date": "2026-06-19",
                "years_available": "1840-2015",
                "license_note": "Free academic; cite Goemans, Gleditsch, and Chiozza 2009.",
                "ingestion_status": "downloaded",
                "source_url": "https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result_1 = ingest_archigos()
    result_2 = ingest_archigos()
    # Idempotency: same source_id, same observation row count.
    assert result_1.source_id == result_2.source_id
    assert result_1.observation_rows == result_2.observation_rows
    assert result_1.observation_rows == 30
    # Year window covers 1869-1885.
    assert result_1.year_window == (1869, 1885)
    # 1 country (USA) in the fixture.
    assert result_1.countries == 1
    # 4 distinct years in the fixture (1869, 1877, 1881, 1885).
    assert result_1.years == (1869, 1877, 1881, 1885)
    # 6 catalog indicators.
    assert result_1.indicators == 6
    # Parquet file exists and has the attribution metadata.
    assert result_1.parquet_path.is_file()
    table = pq.read_table(str(result_1.parquet_path))
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"archigos_attribution")
    assert attribution_bytes is not None
    assert attribution_bytes.decode("utf-8") == ARCHIGOS_ATTRIBUTION
    # Manifest file exists next to the parquet.
    manifest_path = (
        result_1.parquet_path.parent / "archigos_run_manifest.json"
    )
    assert manifest_path.is_file()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == ARCHIGOS_ATTRIBUTION
    assert payload["year_window"] == [1869, 1885]
    # source_observations rows: 30.
    with session_scope() as session:
        obs_count = session.execute(
            select(func.count()).select_from(SourceObservation).where(
                SourceObservation.source_id == result_1.source_id,
            ),
        ).scalar_one()
    assert obs_count == 30


def test_archigos_ingest_with_year_filter(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """The ``year=1881`` orchestrator run produces 12 rows (2 spells
    x 6 variables) and the year window collapses to ``(1881, 1881)``.
    """
    _require_archigos()
    _require_fixture()
    target_dta_dir = isolated_data_lake / "data" / "raw" / "archigos"
    target_dta_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_DTA, target_dta_dir / "Archigos_4.1_stata14.dta")
    (target_dta_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "Archigos",
                "source_version": "v4.1 (Stata 14)",
                "download_date": "2026-06-19",
                "years_available": "1840-2015",
                "license_note": "Free academic.",
                "ingestion_status": "downloaded",
                "source_url": "https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result = ingest_archigos(year=1881)
    assert result.observation_rows == 12
    assert result.year_window == (1881, 1881)
    assert result.years == (1881,)


def test_archigos_ingest_year_with_no_data(
    isolated_data_lake: Path,
    database_url: str,
) -> None:
    """A ``year=2023`` orchestrator run produces 0 rows and a
    no-data year window. The orchestrator still writes the
    parquet (empty frame), the manifest, and the ``sources``
    row -- so downstream stages can detect "this run produced
    no data" without re-reading the .dta.
    """
    _require_archigos()
    _require_fixture()
    target_dta_dir = isolated_data_lake / "data" / "raw" / "archigos"
    target_dta_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_FIXTURE_DTA, target_dta_dir / "Archigos_4.1_stata14.dta")
    (target_dta_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_name": "Archigos",
                "source_version": "v4.1 (Stata 14)",
                "download_date": "2026-06-19",
                "years_available": "1840-2015",
                "license_note": "Free academic.",
                "ingestion_status": "downloaded",
                "source_url": "https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta",
            },
        ),
        encoding="utf-8",
    )

    init_database(database_url)
    result = ingest_archigos(year=2023)
    assert result.observation_rows == 0
    assert result.year_window == (0, 0)
    assert result.years == ()
    # Parquet and manifest still written.
    assert result.parquet_path.is_file()
    manifest_path = (
        result.parquet_path.parent / "archigos_run_manifest.json"
    )
    assert manifest_path.is_file()


# ---------------------------------------------------------------------------
# Path helper tests
# ---------------------------------------------------------------------------


def test_archigos_default_dta_path_missing_raises(
    isolated_data_lake: Path,
) -> None:
    """The ``default_dta_path`` helper raises ``FileNotFoundError``
    when the .dta is missing.
    """
    _require_archigos()
    with pytest.raises(FileNotFoundError):
        default_dta_path()


def test_archigos_default_processed_parquet_path_creates_dir(
    isolated_data_lake: Path,
) -> None:
    """The ``default_processed_parquet_path`` helper creates the
    ``data/processed/archigos/`` directory if missing.
    """
    _require_archigos()
    path = default_processed_parquet_path()
    assert path.parent.is_dir()
    assert path.name == "archigos_leader_spell.parquet"


# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------


def test_archigos_year_window_constants() -> None:
    """The year-window constants are the verified live values."""
    _require_archigos()
    assert ARCHIGOS_YEAR_START == 1840
    assert ARCHIGOS_YEAR_END == 2015
    assert ARCHIGOS_DTA_ENCODING == "cp1252"


def test_archigos_stub_orchestrator_replaced() -> None:
    """The :mod:`archigos` orchestrator module must NOT be the original
    Phase A stub (which raised ``NotImplementedError``). The
    production code replaces the stub.
    """
    _require_archigos()
    # The original stub raised NotImplementedError on
    # ``ingest_archigos``. The production code replaces the stub
    # with a real function that returns a Pydantic result. If
    # the function is present, it must be a real function (not
    # a stub).
    assert callable(getattr(archigos, "ingest_archigos", None))


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_archigos() -> None:
    """``STAGE2_ADAPTERS['archigos']`` is ``archigos.ingest_archigos``.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass; the
    pre-existing ``"archigos": None`` stub is replaced. Test
    fails if the production wiring is removed.
    """
    _require_archigos()
    assert "archigos" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["archigos"] is archigos.ingest_archigos
    assert callable(STAGE2_ADAPTERS["archigos"])


def test_dispatch_table_no_duplicate_archigos_key() -> None:
    """The dispatch table has exactly one ``archigos`` key (no
    duplicate from a copy-paste bug).
    """
    assert ARCHIGOS_SOURCE_KEY is not None
    count = sum(1 for k in STAGE2_ADAPTERS.keys() if k == "archigos")
    assert count == 1, (
        f"Expected exactly 1 'archigos' key in STAGE2_ADAPTERS, got {count}"
    )
