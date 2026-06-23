"""Test suite for the Transparency International CPI Stage 2 adapter.

Covers the full Phase C.10 contract for ``transparency_cpi``:

1. Catalog loading (column set, IndicatorSpec dataclass).
2. URL builder (HDX mirror URL pattern).
3. HTTP cache I/O + fetch (real-format CSV fixture, no network).
4. CSV parser (records -> wide DataFrame).
5. Parquet write with file-level attribution metadata.
6. DB writes (sources + source_observations + manifest).
7. Idempotency (re-running deletes + re-inserts the same rows).
8. Direct orchestrator (one call, all pieces wired).
9. Attribution drift guard (code == docs/sources/attributions.md).
10. Process boundary: changes to production wiring (URL
   builder, DB writer, manifest writer, dispatch table) cause
   observable failure in tests.

Pattern: matches the WHO GHO API / WDI / WGI / UCDP / SIPRI
milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI test files.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import requests
from sqlalchemy import select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import STAGE2_ADAPTERS, transparency_cpi
from leaders_db.ingest.transparency_cpi import (
    TransparencyCpiIngestResult,
    ingest_transparency_cpi,
)
from leaders_db.ingest.transparency_cpi_csv import read_transparency_cpi_csv
from leaders_db.ingest.transparency_cpi_db import (
    TRANSPARENCY_CPI_HDX_MIRROR_URL,
    TRANSPARENCY_CPI_PUBLISHER_URL,
    register_transparency_cpi_source,
    write_transparency_cpi_observations,
    write_transparency_cpi_run_manifest,
)
from leaders_db.ingest.transparency_cpi_db_helpers import (
    _build_observation_rows,
    _coerce_float,
    _coerce_float_from_string,
)
from leaders_db.ingest.transparency_cpi_http import (
    TRANSPARENCY_CPI_HDX_BASE,
    TRANSPARENCY_CPI_HDX_DATASET_UUID,
    TRANSPARENCY_CPI_HDX_RESOURCE_2023,
    build_transparency_cpi_url,
    fetch_transparency_cpi_csv,
)
from leaders_db.ingest.transparency_cpi_io import (
    _DEFAULT_CATALOG_PATH,
    _PROCESSED_PARQUET_NAME,
    TRANSPARENCY_CPI_ATTRIBUTION,
    TRANSPARENCY_CPI_SOURCE_KEY,
    IndicatorSpec,
    default_csv_path,
    default_processed_parquet_path,
    load_indicator_catalog,
    write_transparency_cpi_parquet,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURE_CSV: Path = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "transparency_cpi"
    / "sample.csv"
)
_EXPECTED_FIXTURE_COUNTRIES: tuple[str, ...] = (
    "IND",  # score=39
    "MEX",  # score=31
    "NGA",  # score=25
    "SWE",  # score=82
    "USA",  # score=69
)


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables.

    The :func:`isolated_data_lake` fixture redirects the data
    lake; this helper applies the checked-in migration
    (``src/leaders_db/db/migrations/0001_initial.sql``) to the
    test SQLite so the ORM can read/write. Mirrors the same
    pattern in test_ingest_pts.py / test_ingest_vdem.py /
    test_ingest_wdi.py / test_ingest_wgi.py /
    test_ingest_sipri_milex.py / test_ingest_sipri_yearbook_ch7.py
    / test_ingest_who_gho_api.py / test_ingest_undp_hdi.py /
    test_ingest_rsf_press_freedom.py / test_ingest_cirights.py /
    test_ingest_bti.py.
    """
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_one_spec() -> None:
    """The catalog has exactly one indicator (cpi_score)."""
    specs = load_indicator_catalog()
    assert len(specs) == 1
    spec = specs[0]
    assert isinstance(spec, IndicatorSpec)
    assert spec.variable_name == "cpi_score"
    assert spec.raw_column == "score"
    assert spec.rating_category == "integrity"
    assert spec.raw_scale == "0-100"
    assert spec.normalized_scale_target == "0-10"
    assert spec.higher_is_better is True
    assert spec.unit == "0-100 scale"


def test_load_indicator_catalog_handles_comments() -> None:
    """The catalog loader skips comment-only lines and the # header block."""
    specs = load_indicator_catalog()
    # The catalog file has 60+ comment lines but only 1 data row.
    assert len(specs) == 1


def test_load_indicator_catalog_uses_default_path() -> None:
    """The default catalog path resolves under catalogs/."""
    assert _DEFAULT_CATALOG_PATH.is_file()
    assert _DEFAULT_CATALOG_PATH.name == "transparency_cpi.csv"


def test_load_indicator_catalog_missing_file_raises(tmp_path: Path) -> None:
    """A missing catalog path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="catalog not found"):
        load_indicator_catalog(catalog_path=tmp_path / "nope.csv")


def test_load_indicator_catalog_missing_columns_raises(tmp_path: Path) -> None:
    """A catalog missing a required column raises ValueError."""
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "variable_name,raw_column\nfoo,bar\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required columns"):
        load_indicator_catalog(catalog_path=bad)


# ---------------------------------------------------------------------------
# URL + constants tests
# ---------------------------------------------------------------------------


def test_constants_match_documented() -> None:
    """The module-level constants are byte-identical to the source-of-truth values."""
    assert TRANSPARENCY_CPI_SOURCE_KEY == "transparency_cpi"
    assert TRANSPARENCY_CPI_HDX_BASE == "https://data.humdata.org/dataset"
    # The HDX UUIDs are stable as of probe (2026-06-19); if HDX
    # migrates the dataset, the constants break and the URL test
    # below catches the migration.
    assert len(TRANSPARENCY_CPI_HDX_DATASET_UUID) == 36
    assert len(TRANSPARENCY_CPI_HDX_RESOURCE_2023) == 36


def test_build_transparency_cpi_url_pattern() -> None:
    """The URL builder produces the documented HDX mirror URL pattern."""
    url = build_transparency_cpi_url(2023)
    assert url == (
        f"{TRANSPARENCY_CPI_HDX_BASE}/"
        f"{TRANSPARENCY_CPI_HDX_DATASET_UUID}/"
        f"resource/{TRANSPARENCY_CPI_HDX_RESOURCE_2023}/"
        "download/global_cpi_2023.csv"
    )


def test_build_transparency_cpi_url_other_year() -> None:
    """The URL builder embeds the requested year in the file name."""
    url = build_transparency_cpi_url(2024)
    assert "global_cpi_2024.csv" in url
    # The URL is deterministic per year (no random tokens).
    assert url == build_transparency_cpi_url(2024)


# ---------------------------------------------------------------------------
# Cache I/O + fetch (uses fixture, no network)
# ---------------------------------------------------------------------------


def test_fetch_transparency_cpi_csv_from_cache(tmp_path: Path) -> None:
    """The fetch helper reads a cached CSV file without HTTP."""
    cache_path = tmp_path / "global_cpi_2023.csv"
    shutil.copy(_FIXTURE_CSV, cache_path)

    records, came_from_cache = fetch_transparency_cpi_csv(
        2023, cache_path=cache_path, force_refresh=False
    )
    assert came_from_cache is True
    assert len(records) == len(_EXPECTED_FIXTURE_COUNTRIES)
    # All records should have the expected HDX CSV columns.
    expected_keys = {
        "country", "iso3", "region", "year", "score", "rank",
        "sources", "standardError", "lowerCi", "upperCi",
    }
    for rec in records:
        assert expected_keys.issubset(rec.keys())
        assert rec["year"] == "2023"


def test_fetch_transparency_cpi_csv_missing_cache_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing cache and an unreachable network raises FileNotFoundError."""
    cache_path = tmp_path / "nope.csv"

    # Block any HTTP attempt; the helper must fall through to
    # the network call, then fail cleanly. The retry policy in
    # ``transparency_cpi_http._http_get_csv`` catches
    # ``requests.ConnectionError`` (and ``requests.Timeout``),
    # so we raise the proper requests exception class. The
    # first attempt raises; the second attempt also raises; the
    # retry loop converts to FileNotFoundError so the caller
    # can fail cleanly without leaking the network exception.
    def fake_get(*args: object, **kwargs: object) -> None:
        raise requests.ConnectionError("blocked by test")

    monkeypatch.setattr(
        "leaders_db.ingest.transparency_cpi_http.requests.get",
        fake_get,
    )

    with pytest.raises(FileNotFoundError, match="HTTP failed"):
        fetch_transparency_cpi_csv(
            2023, cache_path=cache_path, request_timeout=1.0
        )


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------


def test_read_transparency_cpi_csv_wide_shape() -> None:
    """The parser produces a wide DataFrame with the expected columns."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    assert len(df) == len(_EXPECTED_FIXTURE_COUNTRIES)
    # Expected columns are exactly the canonical wide shape.
    expected_cols = {
        "iso3", "year", "country", "region", "cpi_score",
        "cpi_score_raw_value", "rank", "sources",
        "standard_error", "lower_ci", "upper_ci",
    }
    assert set(df.columns) == expected_cols
    # Sorted by iso3 (deterministic idempotency).
    assert list(df["iso3"]) == sorted(_EXPECTED_FIXTURE_COUNTRIES)


def test_read_transparency_cpi_csv_real_values() -> None:
    """The parser preserves real HDX values (no invented data)."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    usa = df[df["iso3"] == "USA"].iloc[0]
    assert int(usa["cpi_score"]) == 69
    assert int(usa["year"]) == 2023
    swe = df[df["iso3"] == "SWE"].iloc[0]
    assert int(swe["cpi_score"]) == 82
    nga = df[df["iso3"] == "NGA"].iloc[0]
    assert int(nga["cpi_score"]) == 25
    # The raw_value column preserves the verbatim cell.
    assert str(usa["cpi_score_raw_value"]) == "69"
    assert str(swe["cpi_score_raw_value"]) == "82"


def test_read_transparency_cpi_csv_audit_trail_columns() -> None:
    """The audit-trail columns (rank, sources, CI bounds) are preserved."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    usa = df[df["iso3"] == "USA"].iloc[0]
    assert int(usa["rank"]) == 24
    assert int(usa["sources"]) == 9
    assert float(usa["standard_error"]) == pytest.approx(2.14)
    assert int(usa["lower_ci"]) == 65
    assert int(usa["upper_ci"]) == 73


def test_read_transparency_cpi_csv_missing_columns_raises() -> None:
    """Missing required columns raises ValueError."""
    with pytest.raises(ValueError, match="missing required columns"):
        read_transparency_cpi_csv(
            [{"country": "Foo", "iso3": "FOO"}], year=2023
        )


def test_read_transparency_cpi_csv_empty_records() -> None:
    """An empty records list returns an empty wide DataFrame with the expected shape."""
    df = read_transparency_cpi_csv([], year=2023)
    assert df.empty
    assert "iso3" in df.columns
    assert "cpi_score" in df.columns


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def test_coerce_float_handles_common_types() -> None:
    """_coerce_float handles None, NaN, int, float, and string sentinels."""
    assert _coerce_float(None) is None
    assert _coerce_float(float("nan")) is None
    assert _coerce_float(69) == 69.0
    assert _coerce_float(69.0) == 69.0
    assert _coerce_float(True) is None  # defensive
    assert _coerce_float("NA") is None
    assert _coerce_float("") is None
    assert _coerce_float("nan") is None
    assert _coerce_float("69") == 69.0
    assert _coerce_float(" 82 ") == 82.0
    assert _coerce_float("not-a-number") is None
    assert _coerce_float([1, 2]) is None


def test_coerce_float_from_string_basic() -> None:
    """The string variant handles missing strings and edge cases."""
    assert _coerce_float_from_string("69") == 69.0
    assert _coerce_float_from_string("") is None
    assert _coerce_float_from_string("nan") is None
    assert _coerce_float_from_string("NA") is None
    assert _coerce_float_from_string("null") is None


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def test_build_observation_rows_shape_and_reference() -> None:
    """Each row has the expected fields and source_row_reference format."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    specs = load_indicator_catalog()

    rows = _build_observation_rows(source_id=42, df=df, specs=specs)
    assert len(rows) == len(_EXPECTED_FIXTURE_COUNTRIES)
    for row in rows:
        assert isinstance(row, SourceObservation)
        assert row.source_id == 42
        assert row.country_id is None  # Stage 3 fills
        assert row.leader_id is None  # Stage 4 fills
        assert row.year == 2023
        assert row.variable_name == "cpi_score"
        assert row.confidence is None  # Stage 11 fills
        # source_row_reference carries the catalog raw_column + ISO3.
        assert row.source_row_reference.startswith(
            "transparency_cpi:score:"
        )
        assert row.normalized_value is not None
        assert isinstance(row.normalized_value, float)


def test_build_observation_rows_real_values() -> None:
    """The numeric normalized_value matches the real HDX value."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    specs = load_indicator_catalog()
    rows = _build_observation_rows(source_id=1, df=df, specs=specs)
    by_iso3 = {
        row.source_row_reference.split(":")[-1]: row
        for row in rows
    }
    assert int(by_iso3["USA"].normalized_value) == 69
    assert int(by_iso3["SWE"].normalized_value) == 82
    assert int(by_iso3["NGA"].normalized_value) == 25


# ---------------------------------------------------------------------------
# Parquet write + metadata
# ---------------------------------------------------------------------------


def test_write_transparency_cpi_parquet_attaches_metadata(
    tmp_path: Path,
) -> None:
    """The parquet file carries the Transparency International CPI attribution in metadata."""
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    out = tmp_path / "out.parquet"
    write_transparency_cpi_parquet(df, parquet_path=out)
    assert out.is_file()

    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    assert meta[b"transparency_cpi_attribution"] == (
        TRANSPARENCY_CPI_ATTRIBUTION.encode("utf-8")
    )
    assert meta[b"transparency_cpi_source_key"] == b"transparency_cpi"


def test_default_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default CSV + parquet paths resolve under the data lake."""
    # Re-point the data lake to a tmp dir for an isolated check.
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    csv_path = default_csv_path()
    parquet_path = default_processed_parquet_path()
    assert csv_path.name == "transparency_cpi_2023.csv"
    assert parquet_path.name == _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def test_register_transparency_cpi_source_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """register_transparency_cpi_source is idempotent (same id on repeated calls)."""
    _init_test_db(database_url)
    with session_scope() as session:
        first_id = register_transparency_cpi_source(session)
    with session_scope() as session:
        second_id = register_transparency_cpi_source(session)
    assert first_id == second_id
    assert first_id >= 1


def test_register_transparency_cpi_source_writes_publisher_url(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The sources row carries the canonical Transparency International publisher URL."""
    _init_test_db(database_url)
    with session_scope() as session:
        source_id = register_transparency_cpi_source(session)
    with session_scope() as session:

        row = session.execute(
            select(Source).where(Source.id == source_id)
        ).scalar_one()
    # The publisher URL (Transparency International, not the HDX
    # mirror) is the source-of-record; the HDX mirror is recorded
    # in the manifest only.
    assert row.source_url == TRANSPARENCY_CPI_PUBLISHER_URL
    assert row.source_name == (
        "Transparency International Corruption Perceptions Index"
    )
    assert "Transparency International" in row.license_note


# ---------------------------------------------------------------------------
# DB observations + manifest
# ---------------------------------------------------------------------------


def test_write_transparency_cpi_observations_row_count(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The DB writer writes one row per (iso3, year, variable)."""
    _init_test_db(database_url)
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    specs = load_indicator_catalog()

    with session_scope() as session:
        source_id = register_transparency_cpi_source(session)
        rows = write_transparency_cpi_observations(
            session, source_id, df, catalog_path=None
        )
    expected = len(_EXPECTED_FIXTURE_COUNTRIES) * len(specs)
    assert rows == expected

    with session_scope() as session:

        db_rows = (
            session.execute(
                select(SourceObservation).where(
                    SourceObservation.source_id == source_id
                )
            )
            .scalars()
            .all()
        )
    assert len(db_rows) == expected
    for db_row in db_rows:
        assert db_row.country_id is None
        assert db_row.leader_id is None
        assert db_row.year == 2023
        assert db_row.variable_name == "cpi_score"
        assert db_row.source_row_reference.startswith(
            "transparency_cpi:score:"
        )
        assert db_row.normalized_value is not None


def test_write_transparency_cpi_observations_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """Re-running the DB writer deletes + re-inserts the same row count."""
    _init_test_db(database_url)
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)

    with session_scope() as session:
        source_id = register_transparency_cpi_source(session)
        first = write_transparency_cpi_observations(
            session, source_id, df, catalog_path=None
        )
    with session_scope() as session:
        second = write_transparency_cpi_observations(
            session, source_id, df, catalog_path=None
        )
    assert first == second == len(_EXPECTED_FIXTURE_COUNTRIES)

    # The DB row count is the same after re-running (no append).
    with session_scope() as session:

        db_rows = (
            session.execute(
                select(SourceObservation).where(
                    SourceObservation.source_id == source_id
                )
            )
            .scalars()
            .all()
        )
    assert len(db_rows) == len(_EXPECTED_FIXTURE_COUNTRIES)


def test_write_transparency_cpi_run_manifest_payload(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The run manifest carries the expected audit-trail payload."""
    _init_test_db(database_url)
    text = _FIXTURE_CSV.read_text(encoding="utf-8")
    records = list(csv.DictReader(io.StringIO(text)))
    df = read_transparency_cpi_csv(records, year=2023)
    specs = load_indicator_catalog()

    with session_scope() as session:
        source_id = register_transparency_cpi_source(session)
        rows = write_transparency_cpi_observations(
            session, source_id, df, catalog_path=None
        )

    result = TransparencyCpiIngestResult(
        source_id=source_id,
        parquet_path=default_processed_parquet_path(),
        observation_rows=rows,
        countries=len(_EXPECTED_FIXTURE_COUNTRIES),
        years=(2023,),
        indicators=len(specs),
        csv_cached=True,
        csv_fetched=False,
    )
    manifest_path = write_transparency_cpi_run_manifest(
        result, csv_cached=True, csv_fetched=False
    )
    assert manifest_path.is_file()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == TRANSPARENCY_CPI_ATTRIBUTION
    assert payload["source_key"] == TRANSPARENCY_CPI_SOURCE_KEY
    assert payload["publisher_url"] == TRANSPARENCY_CPI_PUBLISHER_URL
    assert payload["hdx_mirror_url"] == TRANSPARENCY_CPI_HDX_MIRROR_URL
    assert payload["csv_cached"] is True
    assert payload["csv_fetched"] is False
    assert payload["years"] == [2023]


# ---------------------------------------------------------------------------
# Orchestrator (end-to-end, uses the fixture cache)
# ---------------------------------------------------------------------------


def test_ingest_transparency_cpi_end_to_end(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The orchestrator runs end-to-end against the cached fixture."""
    _init_test_db(database_url)
    # Stage the fixture CSV at the conventional cache path
    # (``<root>/data/raw/transparency_cpi/transparency_cpi_2023.csv``
    # via ``default_csv_path()``). The orchestrator reads from
    # this path so a cache hit means no HTTP.
    raw_dir_path = (
        isolated_data_lake / "data" / "raw" / TRANSPARENCY_CPI_SOURCE_KEY
    )
    raw_dir_path.mkdir(parents=True, exist_ok=True)
    cache_csv = raw_dir_path / default_csv_path().name
    shutil.copy(_FIXTURE_CSV, cache_csv)

    # The orchestrator must run without network (cache is staged).
    result = ingest_transparency_cpi(year=2023, force_refresh=False)

    assert isinstance(result, TransparencyCpiIngestResult)
    assert result.source_id >= 1
    assert result.countries == len(_EXPECTED_FIXTURE_COUNTRIES)
    assert result.years == (2023,)
    assert result.indicators == 1
    assert result.csv_cached is True
    assert result.csv_fetched is False
    assert result.observation_rows == len(_EXPECTED_FIXTURE_COUNTRIES)
    # Parquet + manifest files exist.
    assert result.parquet_path.is_file()
    manifest_path = (
        result.parquet_path.parent / "transparency_cpi_run_manifest.json"
    )
    assert manifest_path.is_file()


def test_ingest_transparency_cpi_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """Re-running the orchestrator yields the same row count (no append)."""
    _init_test_db(database_url)
    raw_dir_path = (
        isolated_data_lake / "data" / "raw" / TRANSPARENCY_CPI_SOURCE_KEY
    )
    raw_dir_path.mkdir(parents=True, exist_ok=True)
    cache_csv = raw_dir_path / default_csv_path().name
    shutil.copy(_FIXTURE_CSV, cache_csv)

    first = ingest_transparency_cpi(year=2023)
    second = ingest_transparency_cpi(year=2023)
    assert first.observation_rows == second.observation_rows
    assert first.countries == second.countries
    assert first.source_id == second.source_id


def test_ingest_transparency_cpi_missing_year_raises(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The orchestrator requires a year (single-year reader)."""
    _init_test_db(database_url)
    with pytest.raises(ValueError, match="year is required"):
        ingest_transparency_cpi(year=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Attribution drift guard (Always-On Rule #15)
# ---------------------------------------------------------------------------


def test_transparency_cpi_attribution_matches_attributions_doc() -> None:
    """The code attribution text is byte-identical to docs/sources/attributions.md.

    Strengthens the drift guard: in addition to verifying that the
    attribution string appears 3+ times in the doc (section + cheat
    sheet + summary table), the test asserts that the provenance
    wording reflects the production implementation. The Stage 2
    adapter ingests the OCHA HDX-mirrored CSV (the canonical TI
    xlsx is CDN-gated per the source-vetting report §3.6); a
    previous version of this doc claimed "HTML scrape of the
    report page", which is now stale.
    """
    # ``tests/test_<source>.py`` -> ``tests/`` is .parent, repo
    # root is ``.parent.parent``. (Earlier versions of this
    # assertion used ``.parent.parent.parent`` which pointed
    # one level above the repo root.)
    doc_path = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "sources/attributions.md"
    )
    assert doc_path.is_file(), (
        f"Source attributions doc not found: {doc_path}"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    # The constant appears in the transparency_cpi section
    # AND in the citation cheat-sheet AND in the summary
    # table. Match all three.
    pattern = re.compile(
        r"Transparency International CPI 2023\.",
        re.MULTILINE,
    )
    matches = pattern.findall(doc_text)
    assert len(matches) >= 3, (
        "Expected >=3 occurrences in sources/attributions.md "
        "(section + cheat-sheet + summary table); got "
        f"{len(matches)}"
    )
    # The constant in code is byte-identical to the doc.
    assert TRANSPARENCY_CPI_ATTRIBUTION == "Transparency International CPI 2023."
    # The orchestrator's attribution() helper returns the same string.
    assert transparency_cpi.attribution() == TRANSPARENCY_CPI_ATTRIBUTION
    # The Pydantic result's .attribution property returns the same string.
    result = TransparencyCpiIngestResult(
        source_id=1,
        parquet_path=Path("/tmp/dummy.parquet"),
        observation_rows=0,
        countries=0,
        years=(2023,),
        indicators=1,
        csv_cached=True,
        csv_fetched=False,
    )
    assert result.attribution == TRANSPARENCY_CPI_ATTRIBUTION

    # Provenance drift guard: the doc must reflect the HDX-CSV
    # provenance (the actual Stage 2 contract), not the stale
    # "HTML scrape" wording. Capture the prose between the
    # ``transparency_cpi`` section heading and the next H3 and
    # assert it mentions HDX / CSV.
    section_match = re.search(
        r"### `transparency_cpi`.*?(?=\n### )",
        doc_text,
        re.DOTALL,
    )
    assert section_match is not None, (
        "transparency_cpi section not found in sources/attributions.md"
    )
    section_text = section_match.group(0)
    assert "HDX" in section_text or "hdx" in section_text, (
        "transparency_cpi section must mention HDX (the OCHA "
        "Humanitarian Data Exchange CSV mirror is the production "
        "provenance; the canonical TI xlsx is CDN-gated)."
    )
    assert "CSV" in section_text, (
        "transparency_cpi section must mention CSV (the Stage 2 "
        "adapter ingests a CSV, not an HTML scrape)."
    )
    # Negative assertion: the prose should not claim "HTML scrape"
    # as the production provenance.
    assert "HTML scrape" not in section_text, (
        "transparency_cpi provenance wording is stale: the "
        "Stage 2 adapter reads the OCHA HDX-mirrored CSV, not "
        "an HTML scrape of the TI report page."
    )


# ---------------------------------------------------------------------------
# Process boundary: changes to production wiring cause failure
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_transparency_cpi() -> None:
    """STAGE2_ADAPTERS["transparency_cpi"] is the orchestrator function."""
    assert STAGE2_ADAPTERS["transparency_cpi"] is (
        transparency_cpi.ingest_transparency_cpi
    )


def test_cli_lists_transparency_cpi() -> None:
    """The CLI surface includes the transparency_cpi source (via dispatch)."""
    # The Typer app exposes the source list via the
    # ``ingest-source`` command's ``--source`` choices. We can't
    # easily enumerate Typer choices here, but we can confirm
    # the orchestrator is wired and callable.
    assert callable(STAGE2_ADAPTERS["transparency_cpi"])
