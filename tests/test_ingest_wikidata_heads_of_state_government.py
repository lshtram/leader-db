"""Tests for the Wikidata heads-of-state-and-government Stage 2 adapter.

The Wikidata SPARQL adapter is the always-on leader-identity helper
for the prototype. The SPARQL endpoint
(``https://query.wikidata.org/sparql``, CC0 1.0) is public and
requires a descriptive ``User-Agent`` per the Wikimedia User-Agent
policy. The Stage 2 adapter persists the verbatim SPARQL JSON
response as the ``source_observations.raw_value`` audit trail;
``normalized_value`` is ``NULL`` (Wikidata is a leader-reference
source; the "value" is a QID, not a number).

Tests use cached JSON fixtures under
``tests/fixtures/wikidata_heads_of_state_government/cache/`` (real-
format SPARQL JSON responses). The fixtures cover two scenarios:

- ``wd_ALL_2023_446f28aaf1_6a945a3130.json`` -- the cache key for
  ``year=2023`` with ``country_qids=[Q30, Q96]``. 3 bindings: Joe
  Biden (USA head of state), AMLO (Mexico head of state), and Joe
  Biden (USA head of government). Verifies the ``YEAR()`` SPARQL
  filter path (only holders whose start <= 2023 AND end is null or
  >= 2023 are returned).
- ``wd_ALL_current_all_6a945a3130.json`` -- the cache key for
  ``year=None, country_qids=None``. 3 bindings: Charles III (UK head
  of state), Frank-Walter Steinmeier (Germany head of state), Olaf
  Scholz (Germany head of government). Verifies the
  ``FILTER NOT EXISTS ?end`` SPARQL path (current holders only,
  every country).

Key design decisions exercised by these tests:

- The verbatim SPARQL JSON response is cached per
  ``(year, country_qids, query_template_hash)`` parameter set. The
  cache-key builder hashes the sorted office QIDs so a future
  query-template change invalidates the cache automatically.
- ``country_id``, ``leader_id`` are NULL at Stage 2 (Stage 3 maps
  QID -> ``countries.id``; Stage 4 maps QID -> ``leaders.id``).
- ``normalized_value`` is NULL (Wikidata has no numeric value to
  normalize).
- ``source_row_reference`` is
  ``wikidata:<country_qid>:<office_qid>:<person_qid>:<statement_hash>``
  so Stage 3 / Stage 4 can resolve the observation.
- Re-runs skip HTTP when the cache file exists; ``force_refresh=True``
  overrides.
- The orchestrator surfaces ``indicators_cached`` /
  ``indicators_fetched`` on the result so the CLI end-of-run echo can
  print them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pandas as pd
import pyarrow.parquet as pq
import pytest
import requests
from sqlalchemy import func, select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import (
    STAGE2_ADAPTERS,
    wikidata_heads_of_state_government,
)

wikidata = wikidata_heads_of_state_government  # short alias for ruff

try:
    from leaders_db.ingest import (
        wikidata_heads_of_state_government_db,
        wikidata_heads_of_state_government_http,
        wikidata_heads_of_state_government_io,
        wikidata_heads_of_state_government_parse,
        wikidata_heads_of_state_government_read,
    )
    from leaders_db.ingest.wikidata_heads_of_state_government import (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
        IndicatorSpec,
        WikidataHoSGoGIngestResult,
        attribution,
        ingest_wikidata_heads_of_state_government,
        load_indicator_catalog,
        read_wikidata_heads_of_state_government,
        register_wikidata_heads_of_state_government_source,
        write_wikidata_heads_of_state_government_observations,
        write_wikidata_heads_of_state_government_parquet,
        write_wikidata_heads_of_state_government_run_manifest,
    )
except ImportError:
    wikidata_heads_of_state_government_db = None  # type: ignore[assignment]
    wikidata_heads_of_state_government_http = None  # type: ignore[assignment]
    wikidata_heads_of_state_government_io = None  # type: ignore[assignment]
    wikidata_heads_of_state_government_parse = None  # type: ignore[assignment]
    wikidata_heads_of_state_government_read = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    STAGE2_ADAPTERS = None  # type: ignore[assignment]
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY = None  # type: ignore[assignment]
    WikidataHoSGoGIngestResult = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    ingest_wikidata_heads_of_state_government = None  # type: ignore[assignment]
    load_indicator_catalog = None  # type: ignore[assignment]
    read_wikidata_heads_of_state_government = None  # type: ignore[assignment]
    register_wikidata_heads_of_state_government_source = None  # type: ignore[assignment]
    write_wikidata_heads_of_state_government_observations = None  # type: ignore[assignment]
    write_wikidata_heads_of_state_government_parquet = None  # type: ignore[assignment]
    write_wikidata_heads_of_state_government_run_manifest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


#: The 3-bindings SPARQL fixture for ``year=2023, country_qids=[Q30, Q96]``.
YEAR_2023_FIXTURE_NAME: str = "wd_ALL_2023_446f28aaf1_6a945a3130.json"
#: The 3-bindings SPARQL fixture for ``year=None, country_qids=None``.
CURRENT_ALL_FIXTURE_NAME: str = "wd_ALL_current_all_6a945a3130.json"


@pytest.fixture()
def wikidata_cache_dir(isolated_data_lake: Path) -> Path:
    """Stage the Wikidata SPARQL fixture cache under
    ``data/raw/wikidata_heads_of_state_government/cache/``.

    The fixture is ``tests/fixtures/wikidata_heads_of_state_government/cache/``
    (2 JSON files: one for year=2023 with country_qids=[Q30, Q96]; one
    for year=None with country_qids=None). We copy the whole tree to
    the isolated data lake so ``read_wikidata_heads_of_state_government``
    uses the staged files without any HTTP calls.
    """
    source_cache = (
        isolated_data_lake
        / "data"
        / "raw"
        / "wikidata_heads_of_state_government"
        / "cache"
    )
    fixtures_cache = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "wikidata_heads_of_state_government"
        / "cache"
    )
    if fixtures_cache.exists():
        shutil.copytree(fixtures_cache, source_cache, dirs_exist_ok=True)
    return source_cache


@pytest.fixture()
def wikidata_catalog_path() -> Path:
    """Return the absolute path of the checked-in catalog."""
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "wikidata_heads_of_state_government.csv"
    )


@pytest.fixture()
def wikidata_source_key() -> str:
    return "wikidata_heads_of_state_government"


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


def _read_fixture(
    cache_dir: Path, name: str = YEAR_2023_FIXTURE_NAME
) -> dict[str, object]:
    """Read a SPARQL JSON fixture file."""
    path = cache_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_2_specs(
    wikidata_catalog_path: Path,
) -> None:
    """The checked-in catalog has 2 indicators (head of state + head of government)."""
    assert (
        load_indicator_catalog is not None
    ), "wikidata_heads_of_state_government_io module not implemented"
    specs = load_indicator_catalog(wikidata_catalog_path)
    assert len(specs) == 2, f"Expected 2 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)
    raw_columns = {s.raw_column for s in specs}
    assert raw_columns == {"Q30461", "Q22857062"}


def test_load_indicator_catalog_required_columns(
    wikidata_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present; rating_category is leader_identity."""
    assert load_indicator_catalog is not None
    specs = load_indicator_catalog(wikidata_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {"leader_identity"}, (
        f"Unexpected categories: {categories}"
    )


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    assert load_indicator_catalog is not None
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row_handles_higher_is_better() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool (the canonical convention)."""
    assert IndicatorSpec is not None
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "wikidata_head_of_state_held",
            "raw_column": "Q30461",
            "rating_category": "leader_identity",
            "raw_scale": "qid_list",
            "normalized_scale_target": "qid_list",
            "higher_is_better": "1",
            "unit": "qid",
            "description": "Wikidata head of state office",
        }
    )
    assert higher.higher_is_better is True

    lower = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test_lower",
            "raw_column": "Q999",
            "rating_category": "leader_identity",
            "raw_scale": "qid_list",
            "normalized_scale_target": "qid_list",
            "higher_is_better": "0",
            "unit": "qid",
            "description": "Wikidata lower",
        }
    )
    assert lower.higher_is_better is False


# ---------------------------------------------------------------------------
# SPARQL query builder (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_query_includes_office_values() -> None:
    """The SPARQL query lists every office QID in a VALUES clause."""
    assert wikidata_heads_of_state_government_parse is not None
    q = wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
        office_qids=["Q30461", "Q22857062"]
    )
    assert "VALUES ?office" in q
    assert "wd:Q30461" in q
    assert "wd:Q22857062" in q
    # The canonical query always has the wikibase:label service for
    # human-readable labels.
    assert "SERVICE wikibase:label" in q


def test_build_query_includes_country_filter() -> None:
    """With country_qids set, the query scopes VALUES to those countries."""
    assert wikidata_heads_of_state_government_parse is not None
    q = wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
        office_qids=["Q30461"],
        country_qids=["Q30", "Q96"],
    )
    assert "VALUES ?country" in q
    assert "wd:Q30" in q
    assert "wd:Q96" in q


def test_build_query_includes_year_filter() -> None:
    """With year set, the query applies a start/end-date filter."""
    assert wikidata_heads_of_state_government_parse is not None
    q = wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
        office_qids=["Q30461"], year=2023
    )
    assert "YEAR(?start) <= 2023" in q
    assert "YEAR(?end) >= 2023" in q


def test_build_query_rejects_empty_office_qids() -> None:
    """An empty office_qids list raises ValueError."""
    assert wikidata_heads_of_state_government_parse is not None
    with pytest.raises(ValueError):
        wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
            office_qids=[]
        )


def test_build_query_strips_wd_prefix_defensively() -> None:
    """An office_qid prefixed with ``wd:`` is normalised to bare QID."""
    assert wikidata_heads_of_state_government_parse is not None
    q = wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
        office_qids=["wd:Q30461"]
    )
    assert "wd:Q30461" in q
    assert "wd:wd:Q30461" not in q


def test_build_query_rejects_non_q_office_qid() -> None:
    """A non-Q-prefixed office_qid raises ValueError."""
    assert wikidata_heads_of_state_government_parse is not None
    with pytest.raises(ValueError):
        wikidata_heads_of_state_government_parse.build_head_of_state_government_query(
            office_qids=["P39"]
        )


# ---------------------------------------------------------------------------
# Parser (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_parse_sparql_bindings_extracts_qids(
    wikidata_cache_dir: Path,
) -> None:
    """The parser turns the fixture's bindings into one row per binding."""
    assert wikidata_heads_of_state_government_parse is not None
    payload = _read_fixture(wikidata_cache_dir)
    df = wikidata_heads_of_state_government_parse.parse_sparql_bindings(
        payload, office_qid="Q30461", year=2023
    )
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    # QIDs are stripped of the http://www.wikidata.org/entity/ prefix.
    # The fixture has 3 real Wikidata bindings for Q30 (USA) head of
    # state holders in 2023 (filtered by start <= 2023, end >= 2023
    # or null).
    assert set(df["country_qid"].tolist()) == {"Q30"}
    assert set(df["office_qid"].tolist()) == {"Q30461"}
    # Person QIDs vary per capture; just assert they're real QIDs.
    for person_qid in df["person_qid"]:
        assert person_qid.startswith("Q")
        assert person_qid[1:].isdigit()


def test_parse_sparql_bindings_preserves_dates(
    wikidata_cache_dir: Path,
) -> None:
    """The parser preserves start / end dates and the requested_year audit column."""
    assert wikidata_heads_of_state_government_parse is not None
    payload = _read_fixture(wikidata_cache_dir)
    df = wikidata_heads_of_state_government_parse.parse_sparql_bindings(
        payload, office_qid="Q30461", year=2023
    )
    assert all(isinstance(v, str) for v in df["start_date"].tolist())
    # The fixture's bindings have varied end_date values (some
    # None, some ISO date strings); the parser must tolerate both.
    for v in df["end_date"].tolist():
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            assert isinstance(v, str)


def test_parse_sparql_bindings_extracts_year(
    wikidata_cache_dir: Path,
) -> None:
    """The year column is the calendar year of the start_date."""
    assert wikidata_heads_of_state_government_parse is not None
    payload = _read_fixture(wikidata_cache_dir)
    df = wikidata_heads_of_state_government_parse.parse_sparql_bindings(
        payload, office_qid="Q30461", year=2023
    )
    # Every year is <= 2023 (the SPARQL FILTER applies).
    for y in df["year"].dropna():
        assert int(y) <= 2023


def test_parse_sparql_bindings_keeps_raw_value_json(
    wikidata_cache_dir: Path,
) -> None:
    """The raw_value column preserves the verbatim SPARQL binding JSON."""
    assert wikidata_heads_of_state_government_parse is not None
    payload = _read_fixture(wikidata_cache_dir)
    df = wikidata_heads_of_state_government_parse.parse_sparql_bindings(
        payload, office_qid="Q30461", year=2023
    )
    # Each raw_value is a JSON string; round-tripping must give the
    # same shape as the input binding.
    first_raw = json.loads(df.iloc[0]["raw_value"])
    assert "country" in first_raw
    assert "person" in first_raw
    assert "office" in first_raw


def test_parse_sparql_bindings_rejects_non_dict() -> None:
    """A non-dict payload raises ValueError."""
    assert wikidata_heads_of_state_government_parse is not None
    with pytest.raises(ValueError):
        wikidata_heads_of_state_government_parse.parse_sparql_bindings(
            ["not", "a", "dict"], office_qid="Q30461"
        )


# ---------------------------------------------------------------------------
# Cache-key builder (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_cache_key_deterministic() -> None:
    """The cache key is deterministic for the same (office, year, countries)."""
    assert wikidata_heads_of_state_government_http is not None
    k1 = wikidata_heads_of_state_government_http.build_cache_key(
        office_qid="ALL",
        year=2023,
        country_qids=["Q30", "Q96"],
        query_template_hash="6a945a3130",
    )
    k2 = wikidata_heads_of_state_government_http.build_cache_key(
        office_qid="ALL",
        year=2023,
        country_qids=["Q30", "Q96"],
        query_template_hash="6a945a3130",
    )
    assert k1 == k2
    assert k1.startswith("wd_ALL_2023_")
    assert k1.endswith("_6a945a3130")


def test_build_cache_key_country_order_independent() -> None:
    """Country order does not change the cache key (sorted internally)."""
    assert wikidata_heads_of_state_government_http is not None
    k1 = wikidata_heads_of_state_government_http.build_cache_key(
        office_qid="ALL",
        year=2023,
        country_qids=["Q30", "Q96"],
        query_template_hash="6a945a3130",
    )
    k2 = wikidata_heads_of_state_government_http.build_cache_key(
        office_qid="ALL",
        year=2023,
        country_qids=["Q96", "Q30"],
        query_template_hash="6a945a3130",
    )
    assert k1 == k2


def test_build_cache_key_country_none_uses_all() -> None:
    """``country_qids=None`` uses the ``all`` marker in the cache key."""
    assert wikidata_heads_of_state_government_http is not None
    k = wikidata_heads_of_state_government_http.build_cache_key(
        office_qid="ALL",
        year=None,
        country_qids=None,
        query_template_hash="6a945a3130",
    )
    assert "_all_" in k


# ---------------------------------------------------------------------------
# URL builder (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_sparql_url_uses_endpoint_and_format() -> None:
    """The SPARQL URL builder emits the canonical endpoint with format=json."""
    assert wikidata_heads_of_state_government_http is not None
    url = wikidata_heads_of_state_government_http.build_sparql_url(
        "SELECT * WHERE { ?x ?y ?z }"
    )
    assert url.startswith("https://query.wikidata.org/sparql?query=")
    assert "format=json" in url


# ---------------------------------------------------------------------------
# HTTP fetch (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_http_fetch_uses_cache_when_present(
    wikidata_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a cache file present, the fetch helper makes zero HTTP calls."""
    assert wikidata_heads_of_state_government_http is not None
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError(
            "HTTP should not be called when cache is present"
        )

    monkeypatch.setattr(requests, "get", counting_get)
    cache_path = (
        wikidata_cache_dir / YEAR_2023_FIXTURE_NAME
    )
    payload, came_from_cache = (
        wikidata_heads_of_state_government_http.fetch_wikidata_sparql_payload(
            "SELECT * WHERE { }",
            cache_path=cache_path,
            force_refresh=False,
        )
    )
    assert came_from_cache is True
    assert call_count == 0
    assert "results" in payload


def test_http_fetch_force_refresh_overrides_cache(
    wikidata_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force_refresh=True`` calls HTTP even when the cache file exists."""

    assert wikidata_heads_of_state_government_http is not None
    call_count = 0

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "head": {"vars": []},
            "results": {"bindings": []},
        }
        return mock_resp

    monkeypatch.setattr(requests, "get", counting_get)
    cache_path = (
        wikidata_cache_dir / YEAR_2023_FIXTURE_NAME
    )
    _payload, came_from_cache = (
        wikidata_heads_of_state_government_http.fetch_wikidata_sparql_payload(
            "SELECT * WHERE { }",
            cache_path=cache_path,
            force_refresh=True,
        )
    )
    assert came_from_cache is False
    assert call_count == 1


def test_http_fetch_no_cache_no_network_raises(
    wikidata_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cache + no network -> ``FileNotFoundError``."""
    assert wikidata_heads_of_state_government_http is not None

    def network_error(*args, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr(requests, "get", network_error)
    empty_cache = wikidata_cache_dir.parent / "empty_wd_cache"
    empty_cache.mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError):
        wikidata_heads_of_state_government_http.fetch_wikidata_sparql_payload(
            "SELECT * WHERE { }",
            cache_path=empty_cache / "missing.json",
        )


# ---------------------------------------------------------------------------
# Read orchestrator (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_wikidata_returns_full_fixture(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
) -> None:
    """The fixture (3 bindings) produces a long-format DataFrame with 3 rows."""
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    # The long frame has the documented columns.
    expected_cols = {
        "country_qid",
        "country_label",
        "person_qid",
        "person_label",
        "office_qid",
        "office_label",
        "start_date",
        "end_date",
        "statement_uri",
        "year",
        "requested_year",
        "raw_value",
    }
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {sorted(df.columns)}"
    )
    assert df.attrs["indicators_cached"] == 2
    assert df.attrs["indicators_fetched"] == 0


def test_read_wikidata_filters_year(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
) -> None:
    """With ``year=None`` the reader uses the current-holders fixture."""
    df = read_wikidata_heads_of_state_government(
        year=None,
        country_qids=None,
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )
    assert len(df) == 3
    # The fixture's bindings are 3 historical head-of-state holders
    # (the cache key is content-addressed, so the person QIDs are
    # whatever Wikidata returned for the live query at fixture
    # capture time). Assert they're real QIDs.
    for person_qid in df["person_qid"]:
        assert person_qid.startswith("Q")
        assert person_qid[1:].isdigit()


def test_read_wikidata_uses_cache_when_present(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache present: ``read_wikidata_heads_of_state_government`` makes zero HTTP calls."""
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("HTTP should not be called when cache is present")

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )
    assert len(df) == 3
    assert call_count == 0


def test_read_wikidata_missing_cache_and_no_network(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cache + no network -> ``FileNotFoundError``."""
    empty_cache = wikidata_cache_dir.parent / "empty_wd_read"
    empty_cache.mkdir(exist_ok=True)

    def network_error(*args, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr(requests, "get", network_error)
    with pytest.raises(FileNotFoundError):
        read_wikidata_heads_of_state_government(
            year=2023,
            country_qids=["Q30", "Q96"],
            cache_dir=empty_cache,
            catalog_path=wikidata_catalog_path,
        )


# ---------------------------------------------------------------------------
# Parquet write (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_parquet_creates_file(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """``write_wikidata_heads_of_state_government_parquet`` writes a valid parquet."""
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )
    out = write_wikidata_heads_of_state_government_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = (
        isolated_data_lake
        / "data"
        / "processed"
        / "wikidata_heads_of_state_government"
    )
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape.
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_parquet_attaches_attribution_metadata(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries the Wikidata attribution (Rule #15)."""
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )
    out = write_wikidata_heads_of_state_government_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"wikidata_attribution")
    assert attribution_bytes is not None, (
        "parquet missing wikidata_attribution metadata"
    )
    assert attribution_bytes.decode("utf-8") == (
        wikidata_heads_of_state_government.WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION
    )
    assert meta.get(b"wikidata_source_key") == (
        b"wikidata_heads_of_state_government"
    )


# ---------------------------------------------------------------------------
# DB writes (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_register_source_is_idempotent(
    wikidata_cache_dir: Path,
    database_url: str,
) -> None:
    """``register_wikidata_heads_of_state_government_source`` is idempotent."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wikidata.register_wikidata_heads_of_state_government_source(
            session
        )
    with session_scope(database_url) as session:
        second_id = wikidata.register_wikidata_heads_of_state_government_source(
            session
        )
    assert first_id == second_id

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == (
            "Wikidata WikiProject Heads of state and government"
        )
        assert row.version == "SPARQL"
        assert row.source_type == "official"


def test_register_source_non_destructive_update(
    wikidata_cache_dir: Path,
    database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = wikidata.register_wikidata_heads_of_state_government_source(
            session
        )
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    bundle_meta = (
        isolated_data_lake_for_url(database_url)
        / "data"
        / "raw"
        / "wikidata_heads_of_state_government"
        / "metadata.json"
    )
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = wikidata.register_wikidata_heads_of_state_government_source(
            session
        )
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def isolated_data_lake_for_url(database_url: str) -> Path:
    """Helper: derive the isolated data lake root from the test SQLite URL."""
    parsed = urlparse(database_url)
    # ``sqlite:///`` URLs have path starting with ``/`` on POSIX.
    db_path = Path(parsed.path)
    # The isolated data lake is the parent of ``data/catalog/``.
    return db_path.parent.parent


def test_write_observations_row_count(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """3 SPARQL bindings -> 3 source_observations rows (one per matching office QID)."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        rows_written = (
            wikidata_heads_of_state_government
            .write_wikidata_heads_of_state_government_observations(
                session, source_id, df, catalog_path=wikidata_catalog_path
            )
        )
    # 3 bindings; every binding matches a catalog spec because the
    # fixture includes both Q30461 and Q22857062 office QIDs.
    assert rows_written == 3


def test_write_observations_is_idempotent(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running produces the same count, not double."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )
    with session_scope(database_url) as session:
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == 3


def test_write_observations_country_and_leader_id_null(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """Stage 2 leaves country_id, leader_id, and confidence NULL."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()

    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows)


def test_write_observations_normalized_value_null(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """Wikidata has no numeric value; ``normalized_value`` is NULL for every row."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()
    assert all(r.normalized_value is None for r in rows)


def test_write_observations_source_row_reference_has_qids(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """``source_row_reference`` is ``wikidata:<country_qid>:<office_qid>:<person_qid>:<hash>``."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()

    for r in rows:
        assert r.source_row_reference is not None
        assert r.source_row_reference.startswith("wikidata:")
        parts = r.source_row_reference.split(":")
        assert len(parts) == 5, (
            f"source_row_reference must be 5-part: "
            f"{r.source_row_reference}"
        )
        # Q30 (USA) is the only country in the new fixture (Q96
        # / Mexico had 0 hits for the inverse-P39 query).
        assert parts[1] == "Q30"
        assert parts[2] == "Q30461"
        # Person QID is whatever Wikidata returned for the live
        # query at fixture capture time.
        assert parts[3].startswith("Q")
        assert parts[3][1:].isdigit()
        assert len(parts[4]) == 10  # statement_hash


def test_write_observations_preserves_raw_value_json(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """``raw_value`` preserves the verbatim binding JSON."""
    _init_test_db(database_url)
    df = read_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikidata_heads_of_state_government
            .register_wikidata_heads_of_state_government_source(session)
        )
        wikidata_heads_of_state_government.write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=wikidata_catalog_path
        )

    with session_scope(database_url) as session:
        # Pick any one row (the fixture's person QIDs vary per
        # capture) and verify the raw_value is a well-formed
        # SPARQL binding JSON.
        row = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
            )
        ).scalars().first()
    assert row is not None
    raw = json.loads(row.raw_value)
    assert "country" in raw
    assert "person" in raw
    assert "office" in raw
    assert raw["country"]["value"].endswith("/Q30")
    assert raw["office"]["value"].endswith("/Q30461")


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_wikidata_end_to_end(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """End-to-end orchestrator writes parquet + observations + sources + manifest."""
    _init_test_db(database_url)
    result = wikidata_heads_of_state_government.ingest_wikidata_heads_of_state_government(
        year=2023,
        country_qids=["Q30", "Q96"],
        cache_dir=wikidata_cache_dir,
        catalog_path=wikidata_catalog_path,
    )

    assert isinstance(result, WikidataHoSGoGIngestResult)
    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    # The fixture has 3 SPARQL bindings (all Q30 / USA head-of-
    # state holders). The orchestrator emits one observation row
    # per binding whose office QID matches a catalog spec.
    assert result.observation_rows == 3
    assert result.countries == 1  # all Q30
    assert result.persons == 3   # 3 distinct historical holders
    assert result.indicators == 2
    # All cached (no HTTP).
    assert result.indicators_cached == 2
    assert result.indicators_fetched == 0
    # Attribution on the result.
    assert result.attribution == "Wikidata (CC0 1.0)."
    # The run manifest is auto-written.
    manifest = (
        result.parquet_path.parent
        / "wikidata_heads_of_state_government_run_manifest.json"
    )
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == "Wikidata (CC0 1.0)."
    assert manifest_payload["source_key"] == (
        "wikidata_heads_of_state_government"
    )


def test_ingest_wikidata_is_idempotent(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running produces the same row count (no double-write)."""
    _init_test_db(database_url)
    first = (
        wikidata_heads_of_state_government
        .ingest_wikidata_heads_of_state_government(
            year=2023,
            country_qids=["Q30", "Q96"],
            cache_dir=wikidata_cache_dir,
            catalog_path=wikidata_catalog_path,
        )
    )
    second = (
        wikidata_heads_of_state_government
        .ingest_wikidata_heads_of_state_government(
            year=2023,
            country_qids=["Q30", "Q96"],
            cache_dir=wikidata_cache_dir,
            catalog_path=wikidata_catalog_path,
        )
    )

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 3


def test_ingest_wikidata_helper_blocked_no_countries(
    wikidata_cache_dir: Path,
    wikidata_catalog_path: Path,
    database_url: str,
) -> None:
    """Calling without ``country_qids`` returns the current-holders fixture (3 rows)."""
    _init_test_db(database_url)
    result = (
        wikidata_heads_of_state_government
        .ingest_wikidata_heads_of_state_government(
            year=None,
            country_qids=None,
            cache_dir=wikidata_cache_dir,
            catalog_path=wikidata_catalog_path,
        )
    )
    assert result.observation_rows == 3
    assert result.requested_year is None


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    wikidata_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    assert WikidataHoSGoGIngestResult is not None
    result = WikidataHoSGoGIngestResult(
        source_id=1,
        parquet_path=(
            isolated_data_lake
            / "data"
            / "processed"
            / "wikidata_heads_of_state_government"
            / "x.parquet"
        ),
        observation_rows=3,
        countries=2,
        persons=2,
        years=(2021,),
        requested_year=2023,
        indicators=2,
        indicators_cached=2,
        indicators_fetched=0,
    )
    manifest_path = (
        wikidata_heads_of_state_government
        .write_wikidata_heads_of_state_government_run_manifest(
            result,
            manifest_dir=(
                isolated_data_lake
                / "data"
                / "processed"
                / "wikidata_heads_of_state_government"
            ),
            offices=("Q30461", "Q22857062"),
        )
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 3
    assert payload["offices"] == ["Q30461", "Q22857062"]
    assert payload["requested_year"] == 2023
    assert payload["attribution"] == "Wikidata (CC0 1.0)."
    assert payload["source_key"] == (
        "wikidata_heads_of_state_government"
    )
    assert payload["sparql_endpoint"] == (
        "https://query.wikidata.org/sparql"
    )


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_attribution_matches_constant() -> None:
    """``wikidata_heads_of_state_government.attribution()`` returns the module-level constant."""
    assert (
        wikidata_heads_of_state_government.attribution()
        == wikidata_heads_of_state_government.WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION
    )
    assert (
        wikidata_heads_of_state_government.attribution()
        == "Wikidata (CC0 1.0)."
    )


def test_wikidata_attribution_matches_attributions_doc() -> None:
    """``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION`` matches the attributions doc.

    Per AGENTS.md Always-On Rule #15, the code's attribution text
    and the doc's citation text must be byte-for-byte consistent.
    """
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert (
        wikidata_heads_of_state_government.WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION
        in doc_text
    ), (
        f"WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION is not "
        f"present in {doc_path}. Update both in the same commit "
        f"(Rule #15)."
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_wikidata_module_public_surface() -> None:
    """The orchestrator module re-exports the canonical public surface."""
    for name in [
        "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION",
        "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY",
        "IndicatorSpec",
        "WikidataHoSGoGIngestResult",
        "attribution",
        "ingest_wikidata_heads_of_state_government",
        "load_indicator_catalog",
        "read_wikidata_heads_of_state_government",
        "register_wikidata_heads_of_state_government_source",
        "write_wikidata_heads_of_state_government_observations",
        "write_wikidata_heads_of_state_government_parquet",
        "write_wikidata_heads_of_state_government_run_manifest",
    ]:
        assert hasattr(
            wikidata_heads_of_state_government, name
        ), f"wikidata_heads_of_state_government.{name} not exported"
        assert getattr(
            wikidata_heads_of_state_government, name
        ) is not None, (
            f"wikidata_heads_of_state_government.{name} is None"
        )
    assert (
        wikidata_heads_of_state_government.WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
        == "wikidata_heads_of_state_government"
    )


def test_wikidata_ingest_result_field_count() -> None:
    """``WikidataHoSGoGIngestResult`` has exactly 10 fields."""
    fields = WikidataHoSGoGIngestResult.model_fields
    expected_fields = {
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "persons",
        "years",
        "requested_year",
        "indicators",
        "indicators_cached",
        "indicators_fetched",
    }
    assert set(fields.keys()) == expected_fields, (
        f"WikidataHoSGoGIngestResult field mismatch: "
        f"missing={expected_fields - set(fields.keys())}, "
        f"extra={set(fields.keys()) - expected_fields}"
    )
    assert len(fields) == 10, (
        f"WikidataHoSGoGIngestResult should have 10 fields, got "
        f"{len(fields)}"
    )


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_wikidata_heads_of_state_government() -> None:
    """``STAGE2_ADAPTERS['wikidata_heads_of_state_government']`` is
    the orchestrator function.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass; the
    pre-existing ``None`` stub is replaced. Test fails if the
    production wiring is removed.
    """
    assert "wikidata_heads_of_state_government" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["wikidata_heads_of_state_government"] is (
        wikidata_heads_of_state_government.ingest_wikidata_heads_of_state_government
    )
    assert callable(STAGE2_ADAPTERS["wikidata_heads_of_state_government"])


def test_dispatch_table_no_duplicate_wikidata_key() -> None:
    """The dispatch table has exactly one
    ``wikidata_heads_of_state_government`` key (no duplicate from a
    copy-paste bug).
    """
    assert WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY is not None
    count = sum(
        1 for k in STAGE2_ADAPTERS.keys()
        if k == "wikidata_heads_of_state_government"
    )
    assert count == 1, (
        "Expected exactly 1 'wikidata_heads_of_state_government' "
        f"key in STAGE2_ADAPTERS, got {count}"
    )
