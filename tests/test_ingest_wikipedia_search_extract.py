"""Tests for the Wikipedia Action API (search + extract) Stage 2 adapter.

The Wikipedia Action API adapter is the always-on narrative-context
helper for the prototype. The Action API is the public endpoint at
``https://en.wikipedia.org/w/api.php`` (CC BY-SA 4.0); the Stage 2
adapter persists the verbatim Action API response as the
``source_observations.raw_value`` audit trail.

Tests use cached JSON fixtures under
``tests/fixtures/wikipedia_search_extract/cache/`` (3 JSON files:
two for the ``extracts`` action on ``Joe Biden`` and ``Andrés Manuel
López Obrador``; one for the ``search`` action on ``Joe Biden``).
The orchestrator's deterministic input interface is the
``queries=`` list (the Stage 2 contract is "do not browse / score";
the adapter requires explicit input terms).

Key design decisions exercised by these tests:

- The verbatim Action API response is cached per
  ``(action, query, extra_params)`` parameter set. The cache-key
  builder hashes the lower-cased query so case differences do not
  produce different cache keys.
- ``country_id``, ``leader_id``, and ``year`` are NULL at Stage 2
  (Wikipedia does not emit a year for ``extracts`` or ``search``;
  Stage 3 / Stage 4 resolve them downstream).
- ``normalized_value`` is NULL (Wikipedia is a narrative-context
  source; the "value" is text, not a number).
- ``source_row_reference`` is
  ``wikipedia:<variable_name>:<hint>`` (e.g.
  ``wikipedia:wikipedia_extract_lead:wikipedia:62544:Joe Biden``)
  so Stage 3 / Stage 4 can resolve the observation.
- Re-runs skip HTTP when the cache file exists; ``force_refresh=True``
  overrides.
- The orchestrator surfaces ``indicators_cached`` /
  ``indicators_fetched`` on the result so the CLI end-of-run echo can
  print them.
- Calling ``ingest_wikipedia_search_extract(queries=...)`` with an
  empty list raises ``ValueError`` (the Stage 2 contract: do not
  browse / score).
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
    wikipedia_search_extract,
)

wikipedia = wikipedia_search_extract  # short alias for ruff

try:
    from leaders_db.ingest import (
        wikipedia_search_extract_db,
        wikipedia_search_extract_http,
        wikipedia_search_extract_io,
        wikipedia_search_extract_parse,
        wikipedia_search_extract_read,
    )
    from leaders_db.ingest.wikipedia_search_extract import (
        WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
        IndicatorSpec,
        WikipediaSearchExtractIngestResult,
        attribution,
        ingest_wikipedia_search_extract,
        load_indicator_catalog,
        read_wikipedia_search_extract,
        register_wikipedia_search_extract_source,
        write_wikipedia_search_extract_observations,
        write_wikipedia_search_extract_parquet,
        write_wikipedia_search_extract_run_manifest,
    )
except ImportError:
    wikipedia_search_extract_db = None  # type: ignore[assignment]
    wikipedia_search_extract_http = None  # type: ignore[assignment]
    wikipedia_search_extract_io = None  # type: ignore[assignment]
    wikipedia_search_extract_parse = None  # type: ignore[assignment]
    wikipedia_search_extract_read = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    STAGE2_ADAPTERS = None  # type: ignore[assignment]
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY = None  # type: ignore[assignment]
    WikipediaSearchExtractIngestResult = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    ingest_wikipedia_search_extract = None  # type: ignore[assignment]
    load_indicator_catalog = None  # type: ignore[assignment]
    read_wikipedia_search_extract = None  # type: ignore[assignment]
    register_wikipedia_search_extract_source = None  # type: ignore[assignment]
    write_wikipedia_search_extract_observations = None  # type: ignore[assignment]
    write_wikipedia_search_extract_parquet = None  # type: ignore[assignment]
    write_wikipedia_search_extract_run_manifest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


#: The extracts-cache file for the ``Joe Biden`` query.
JOE_BIDEN_EXTRACTS_FIXTURE: str = (
    "wikipedia_extracts_62f100bfa4_default.json"
)
#: The search-cache file for the ``Joe Biden`` query.
JOE_BIDEN_SEARCH_FIXTURE: str = (
    "wikipedia_search_62f100bfa4_7d0587b5ac.json"
)
#: The extracts-cache file for the ``Andrés Manuel López Obrador`` query.
AMLO_EXTRACTS_FIXTURE: str = (
    "wikipedia_extracts_6f47c90e93_default.json"
)


@pytest.fixture()
def wikipedia_cache_dir(isolated_data_lake: Path) -> Path:
    """Stage the Wikipedia Action API fixture cache under
    ``data/raw/wikipedia_search_extract/cache/``.
    """
    source_cache = (
        isolated_data_lake
        / "data"
        / "raw"
        / "wikipedia_search_extract"
        / "cache"
    )
    fixtures_cache = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "wikipedia_search_extract"
        / "cache"
    )
    if fixtures_cache.exists():
        shutil.copytree(fixtures_cache, source_cache, dirs_exist_ok=True)
    return source_cache


@pytest.fixture()
def wikipedia_catalog_path() -> Path:
    """Return the absolute path of the checked-in catalog."""
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "wikipedia_search_extract.csv"
    )


@pytest.fixture()
def wikipedia_source_key() -> str:
    return "wikipedia_search_extract"


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


def _read_fixture(
    cache_dir: Path, name: str = JOE_BIDEN_EXTRACTS_FIXTURE
) -> dict[str, object]:
    """Read an Action API JSON fixture file."""
    path = cache_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_2_specs(
    wikipedia_catalog_path: Path,
) -> None:
    """The checked-in catalog has 2 indicators (extracts + search)."""
    assert (
        load_indicator_catalog is not None
    ), "wikipedia_search_extract_io module not implemented"
    specs = load_indicator_catalog(wikipedia_catalog_path)
    assert len(specs) == 2, f"Expected 2 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)
    raw_columns = {s.raw_column for s in specs}
    assert raw_columns == {"extracts", "search"}


def test_load_indicator_catalog_required_columns(
    wikipedia_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present; rating_category is leader_identity."""
    assert load_indicator_catalog is not None
    specs = load_indicator_catalog(wikipedia_catalog_path)
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
            "variable_name": "wikipedia_extract_lead",
            "raw_column": "extracts",
            "rating_category": "leader_identity",
            "raw_scale": "text",
            "normalized_scale_target": "text",
            "higher_is_better": "1",
            "unit": "text",
            "description": "Wikipedia article lead",
        }
    )
    assert higher.higher_is_better is True


# ---------------------------------------------------------------------------
# URL builders (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_extracts_url_includes_exintro_explaintext() -> None:
    """The extracts URL builder emits the canonical query parameters."""
    assert wikipedia_search_extract_http is not None
    url = wikipedia_search_extract_http.build_extracts_url(
        "https://en.wikipedia.org/w/api.php", "Joe Biden"
    )
    assert url.startswith(
        "https://en.wikipedia.org/w/api.php?"
    )
    assert "action=query" in url
    assert "prop=extracts" in url
    assert "exintro=1" in url
    assert "explaintext=1" in url
    assert "titles=Joe+Biden" in url or "titles=Joe%20Biden" in url
    assert "format=json" in url


def test_build_search_url_includes_srsearch() -> None:
    """The search URL builder emits the canonical query parameters."""
    assert wikipedia_search_extract_http is not None
    url = wikipedia_search_extract_http.build_search_url(
        "https://en.wikipedia.org/w/api.php", "Joe Biden", limit=10
    )
    assert url.startswith("https://en.wikipedia.org/w/api.php?")
    assert "action=query" in url
    assert "list=search" in url
    assert "srsearch=Joe+Biden" in url or "srsearch=Joe%20Biden" in url
    assert "srlimit=10" in url
    assert "format=json" in url


def test_build_search_url_rejects_invalid_limit() -> None:
    """``limit`` outside the 1..50 API range raises ValueError."""
    assert wikipedia_search_extract_http is not None
    with pytest.raises(ValueError):
        wikipedia_search_extract_http.build_search_url(
            "https://en.wikipedia.org/w/api.php", "Joe Biden", limit=0
        )
    with pytest.raises(ValueError):
        wikipedia_search_extract_http.build_search_url(
            "https://en.wikipedia.org/w/api.php", "Joe Biden", limit=51
        )


# ---------------------------------------------------------------------------
# Parser (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_parse_extracts_response_returns_one_row_per_page(
    wikipedia_cache_dir: Path,
) -> None:
    """The extracts parser emits one row per page in the response."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_EXTRACTS_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_extracts_response(
        payload, query="Joe Biden"
    )
    assert len(df) == 1, f"Expected 1 row, got {len(df)}"
    assert df.iloc[0]["pageid"] == 62544
    assert df.iloc[0]["title"] == "Joe Biden"
    assert isinstance(df.iloc[0]["extract"], str)
    assert "Joseph Robinette Biden" in df.iloc[0]["extract"]


def test_parse_extracts_response_preserves_raw_value_json(
    wikipedia_cache_dir: Path,
) -> None:
    """The extracts parser preserves the verbatim per-row payload as raw_value."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_EXTRACTS_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_extracts_response(
        payload, query="Joe Biden"
    )
    first_raw = json.loads(df.iloc[0]["raw_value"])
    assert "pageid" in first_raw
    assert "extract" in first_raw


def test_parse_extracts_response_source_row_reference_hint(
    wikipedia_cache_dir: Path,
) -> None:
    """The hint is ``wikipedia:<pageid>:<title>`` for extracts responses."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_EXTRACTS_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_extracts_response(
        payload, query="Joe Biden"
    )
    assert df.iloc[0]["source_row_reference_hint"] == (
        "wikipedia:62544:Joe Biden"
    )


def test_parse_search_response_returns_one_row_per_hit(
    wikipedia_cache_dir: Path,
) -> None:
    """The search parser emits one row per hit in the search list."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_SEARCH_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_search_response(
        payload, query="Joe Biden"
    )
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    titles = df["title"].tolist()
    assert "Joe Biden" in titles
    assert "Biden family" in titles
    assert "Presidency of Joe Biden" in titles


def test_parse_search_response_strips_searchmatch_span(
    wikipedia_cache_dir: Path,
) -> None:
    """The snippet column strips the ``<span class="searchmatch">`` wrapper."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_SEARCH_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_search_response(
        payload, query="Joe Biden"
    )
    # No row's extract should contain the HTML span tags.
    for extract in df["extract"].tolist():
        if extract is not None:
            assert "<span" not in extract
            assert "</span>" not in extract
    # The full HTML is preserved in raw_value.
    first_raw = json.loads(df.iloc[0]["raw_value"])
    assert "snippet" in first_raw


def test_parse_search_response_source_row_reference_hint(
    wikipedia_cache_dir: Path,
) -> None:
    """The hint is ``wikipedia:search:<pageid>:<title>`` for search responses."""
    assert wikipedia_search_extract_parse is not None
    payload = _read_fixture(
        wikipedia_cache_dir, JOE_BIDEN_SEARCH_FIXTURE
    )
    df = wikipedia_search_extract_parse.parse_search_response(
        payload, query="Joe Biden"
    )
    assert df.iloc[0]["source_row_reference_hint"] == (
        "wikipedia:search:62544:Joe Biden"
    )


def test_parse_extracts_response_rejects_non_dict() -> None:
    """A non-dict payload raises ValueError."""
    assert wikipedia_search_extract_parse is not None
    with pytest.raises(ValueError):
        wikipedia_search_extract_parse.parse_extracts_response(
            ["not", "a", "dict"], query="Joe Biden"
        )


# ---------------------------------------------------------------------------
# Cache-key builder (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_cache_key_deterministic() -> None:
    """The cache key is deterministic for the same (action, query, params)."""
    assert wikipedia_search_extract_http is not None
    k1 = wikipedia_search_extract_http.build_cache_key(
        action="extracts", query="Joe Biden"
    )
    k2 = wikipedia_search_extract_http.build_cache_key(
        action="extracts", query="Joe Biden"
    )
    assert k1 == k2
    assert k1.startswith("wikipedia_extracts_")


def test_build_cache_key_case_insensitive_query() -> None:
    """Query case differences do not change the cache key."""
    assert wikipedia_search_extract_http is not None
    k1 = wikipedia_search_extract_http.build_cache_key(
        action="extracts", query="Joe Biden"
    )
    k2 = wikipedia_search_extract_http.build_cache_key(
        action="extracts", query="joe bidEN"
    )
    assert k1 == k2


def test_build_cache_key_distinguishes_actions() -> None:
    """The same query for different actions produces different cache keys."""
    assert wikipedia_search_extract_http is not None
    k1 = wikipedia_search_extract_http.build_cache_key(
        action="extracts", query="Joe Biden"
    )
    k2 = wikipedia_search_extract_http.build_cache_key(
        action="search", query="Joe Biden"
    )
    assert k1 != k2


def test_build_cache_key_rejects_empty_query() -> None:
    """An empty query raises ValueError."""
    assert wikipedia_search_extract_http is not None
    with pytest.raises(ValueError):
        wikipedia_search_extract_http.build_cache_key(
            action="extracts", query=""
        )


def test_build_cache_key_rejects_unsupported_action() -> None:
    """An unsupported action raises ValueError."""
    assert wikipedia_search_extract_http is not None
    with pytest.raises(ValueError):
        wikipedia_search_extract_http.build_cache_key(
            action="bogus_action", query="Joe Biden"
        )


# ---------------------------------------------------------------------------
# HTTP fetch (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_http_fetch_uses_cache_when_present(
    wikipedia_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a cache file present, the fetch helper makes zero HTTP calls."""
    assert wikipedia_search_extract_http is not None
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError(
            "HTTP should not be called when cache is present"
        )

    monkeypatch.setattr(requests, "get", counting_get)
    cache_path = wikipedia_cache_dir / JOE_BIDEN_EXTRACTS_FIXTURE
    payload, came_from_cache = (
        wikipedia_search_extract_http.fetch_wikipedia_action_api_payload(
            "https://en.wikipedia.org/w/api.php?action=query&prop=extracts",
            cache_path=cache_path,
            force_refresh=False,
        )
    )
    assert came_from_cache is True
    assert call_count == 0
    assert "query" in payload


def test_http_fetch_force_refresh_overrides_cache(
    wikipedia_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force_refresh=True`` calls HTTP even when the cache file exists."""

    assert wikipedia_search_extract_http is not None
    call_count = 0

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"batchcomplete": "", "query": {}}
        return mock_resp

    monkeypatch.setattr(requests, "get", counting_get)
    cache_path = wikipedia_cache_dir / JOE_BIDEN_EXTRACTS_FIXTURE
    _payload, came_from_cache = (
        wikipedia_search_extract_http.fetch_wikipedia_action_api_payload(
            "https://en.wikipedia.org/w/api.php?action=query&prop=extracts",
            cache_path=cache_path,
            force_refresh=True,
        )
    )
    assert came_from_cache is False
    assert call_count == 1


def test_http_fetch_no_cache_no_network_raises(
    wikipedia_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cache + no network -> ``FileNotFoundError``."""
    assert wikipedia_search_extract_http is not None

    def network_error(*args, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr(requests, "get", network_error)
    empty_cache = (
        wikipedia_cache_dir.parent / "empty_wikipedia_cache"
    )
    empty_cache.mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError):
        wikipedia_search_extract_http.fetch_wikipedia_action_api_payload(
            "https://en.wikipedia.org/w/api.php?action=query",
            cache_path=empty_cache / "missing.json",
        )


# ---------------------------------------------------------------------------
# Read orchestrator (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_wikipedia_extracts_query(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """The extracts query for ``Joe Biden`` produces 1 row."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    assert len(df) == 1
    assert df.iloc[0]["pageid"] == 62544
    assert df.attrs["indicators_cached"] == 1
    assert df.attrs["indicators_fetched"] == 0


def test_read_wikipedia_search_query(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """The search query for ``Joe Biden`` produces 3 rows (3 hits)."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["search"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    assert len(df) == 3
    assert df.attrs["indicators_cached"] == 1
    assert df.attrs["indicators_fetched"] == 0


def test_read_wikipedia_all_actions_default(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """``actions=None`` uses every action in the catalog (extracts + search)."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=None,
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    # 1 extracts row + 3 search rows = 4 rows total.
    assert len(df) == 4
    # The cached-vs-fetched counter counts (query, action) pairs: 2
    # pairs cached, 0 fetched.
    assert df.attrs["indicators_cached"] == 2
    assert df.attrs["indicators_fetched"] == 0


def test_read_wikipedia_multiple_queries(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """Multiple queries produce a concat of per-query frames."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden", "Andrés Manuel López Obrador"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    assert len(df) == 2
    assert set(df["title"].tolist()) == {
        "Joe Biden", "Andrés Manuel López Obrador"
    }
    assert df.attrs["indicators_cached"] == 2


def test_read_wikipedia_uses_cache_when_present(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With cache files present, the reader makes zero HTTP calls."""
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("HTTP should not be called when cache is present")

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    assert len(df) == 1
    assert call_count == 0


def test_read_wikipedia_requires_queries(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """``queries=None`` raises ``ValueError`` (the Stage 2 contract)."""
    with pytest.raises(ValueError):
        read_wikipedia_search_extract(
            queries=None,
            actions=["extracts"],
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )


def test_read_wikipedia_empty_queries_raises(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """``queries=[]`` raises ``ValueError`` (do not browse / score)."""
    with pytest.raises(ValueError):
        read_wikipedia_search_extract(
            queries=[],
            actions=["extracts"],
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )


def test_read_wikipedia_unsupported_action_raises(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """An unsupported action raises ``ValueError``."""
    with pytest.raises(ValueError):
        read_wikipedia_search_extract(
            queries=["Joe Biden"],
            actions=["bogus"],
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )


# ---------------------------------------------------------------------------
# Parquet write (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_parquet_creates_file(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """``write_wikipedia_search_extract_parquet`` writes a valid parquet."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    out = write_wikipedia_search_extract_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = (
        isolated_data_lake
        / "data"
        / "processed"
        / "wikipedia_search_extract"
    )
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape.
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape


def test_write_parquet_attaches_attribution_metadata(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries the Wikipedia attribution (Rule #15)."""
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )
    out = write_wikipedia_search_extract_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"wikipedia_attribution")
    assert attribution_bytes is not None
    assert attribution_bytes.decode("utf-8") == (
        wikipedia_search_extract.WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION
    )
    assert meta.get(b"wikipedia_source_key") == b"wikipedia_search_extract"


# ---------------------------------------------------------------------------
# DB writes (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_register_source_is_idempotent(
    wikipedia_cache_dir: Path,
    database_url: str,
) -> None:
    """``register_wikipedia_search_extract_source`` returns the same id on repeated calls."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
    with session_scope(database_url) as session:
        second_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
    assert first_id == second_id

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "Wikipedia Action API (search + extract)"
        assert row.version == "Action API"
        assert row.source_type == "official"


def test_register_source_non_destructive_update(
    wikipedia_cache_dir: Path,
    database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
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
        / "wikipedia_search_extract"
        / "metadata.json"
    )
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
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
    db_path = Path(parsed.path)
    return db_path.parent.parent


def test_write_observations_row_count(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """1 extracts row + 3 search rows = 4 source_observations rows."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=None,
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        rows_written = (
            wikipedia_search_extract
            .write_wikipedia_search_extract_observations(
                session, source_id, df, catalog_path=wikipedia_catalog_path
            )
        )
    assert rows_written == 4


def test_write_observations_is_idempotent(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running produces the same count, not double."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=None,
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )
    with session_scope(database_url) as session:
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == 4


def test_write_observations_year_country_leader_id_null(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """Stage 2 leaves year, country_id, leader_id, and confidence NULL."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()
    assert all(r.year is None for r in rows)
    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows)


def test_write_observations_normalized_value_null(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """Wikipedia has no numeric value; ``normalized_value`` is NULL for every row."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()
    assert all(r.normalized_value is None for r in rows)


def test_write_observations_source_row_reference_has_variable_name(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """``source_row_reference`` starts with ``wikipedia:<variable_name>:...``."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=None,
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()

    # Every row's reference starts with "wikipedia:wikipedia_extract_lead:"
    # (extracts rows) or "wikipedia:wikipedia_search_results:" (search
    # rows).
    extracts_count = 0
    search_count = 0
    for r in rows:
        assert r.source_row_reference is not None
        assert r.source_row_reference.startswith("wikipedia:")
        if r.variable_name == "wikipedia_extract_lead":
            assert r.source_row_reference.startswith(
                "wikipedia:wikipedia_extract_lead:wikipedia:62544:Joe Biden"
            )
            extracts_count += 1
        elif r.variable_name == "wikipedia_search_results":
            assert r.source_row_reference.startswith(
                "wikipedia:wikipedia_search_results:wikipedia:search:"
            )
            search_count += 1
    assert extracts_count == 1
    assert search_count == 3


def test_write_observations_preserves_raw_value_json(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """``raw_value`` preserves the verbatim per-row payload JSON."""
    _init_test_db(database_url)
    df = read_wikipedia_search_extract(
        queries=["Joe Biden"],
        actions=["extracts"],
        cache_dir=wikipedia_cache_dir,
        catalog_path=wikipedia_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = (
            wikipedia_search_extract
            .register_wikipedia_search_extract_source(session)
        )
        wikipedia.write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=wikipedia_catalog_path
        )

    with session_scope(database_url) as session:
        row = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "wikipedia_extract_lead",
            )
        ).scalar_one()
    raw = json.loads(row.raw_value)
    assert "pageid" in raw
    assert raw["title"] == "Joe Biden"


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_wikipedia_end_to_end(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_wikipedia_search_extract`` writes parquet + observations + sources + manifest."""
    _init_test_db(database_url)
    result = (
        wikipedia_search_extract
        .ingest_wikipedia_search_extract(
            queries=["Joe Biden"],
            actions=None,
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )
    )

    assert isinstance(result, WikipediaSearchExtractIngestResult)
    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    # 1 extracts row + 3 search rows = 4 rows.
    assert result.observation_rows == 4
    assert result.indicators == 2
    # 2 (query, action) pairs cached.
    assert result.indicators_cached == 2
    assert result.indicators_fetched == 0
    # Queries are preserved on the result.
    assert result.queries == ("Joe Biden",)
    # Attribution on the result.
    assert result.attribution == "Wikipedia (CC BY-SA 4.0)."
    # The run manifest is auto-written.
    manifest = (
        result.parquet_path.parent
        / "wikipedia_search_extract_run_manifest.json"
    )
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == "Wikipedia (CC BY-SA 4.0)."
    assert manifest_payload["source_key"] == "wikipedia_search_extract"
    assert manifest_payload["queries"] == ["Joe Biden"]


def test_ingest_wikipedia_is_idempotent(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running produces the same row count (no double-write)."""
    _init_test_db(database_url)
    first = (
        wikipedia_search_extract
        .ingest_wikipedia_search_extract(
            queries=["Joe Biden"],
            actions=None,
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )
    )
    second = (
        wikipedia_search_extract
        .ingest_wikipedia_search_extract(
            queries=["Joe Biden"],
            actions=None,
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )
    )

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 4


def test_ingest_wikipedia_helper_blocked_no_queries(
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """Calling without ``queries`` raises ``ValueError`` (the Stage 2 contract)."""
    _init_test_db(database_url)
    with pytest.raises(ValueError):
        wikipedia.ingest_wikipedia_search_extract(
            queries=None,
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )
    with pytest.raises(ValueError):
        wikipedia.ingest_wikipedia_search_extract(
            queries=[],
            cache_dir=wikipedia_cache_dir,
            catalog_path=wikipedia_catalog_path,
        )


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    wikipedia_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    assert WikipediaSearchExtractIngestResult is not None
    result = WikipediaSearchExtractIngestResult(
        source_id=1,
        parquet_path=(
            isolated_data_lake
            / "data"
            / "processed"
            / "wikipedia_search_extract"
            / "x.parquet"
        ),
        observation_rows=4,
        queries=("Joe Biden",),
        indicators=2,
        indicators_cached=2,
        indicators_fetched=0,
    )
    manifest_path = (
        wikipedia_search_extract
        .write_wikipedia_search_extract_run_manifest(
            result,
            manifest_dir=(
                isolated_data_lake
                / "data"
                / "processed"
                / "wikipedia_search_extract"
            ),
            queries=("Joe Biden",),
            actions=("extracts", "search"),
        )
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 4
    assert payload["queries"] == ["Joe Biden"]
    assert payload["actions"] == ["extracts", "search"]
    assert payload["attribution"] == "Wikipedia (CC BY-SA 4.0)."
    assert payload["source_key"] == "wikipedia_search_extract"
    assert payload["action_api_base"] == "https://en.wikipedia.org/w/api.php"


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_attribution_matches_constant() -> None:
    """``wikipedia_search_extract.attribution()`` returns the module-level constant."""
    assert (
        wikipedia_search_extract.attribution()
        == wikipedia_search_extract.WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION
    )
    assert (
        wikipedia_search_extract.attribution()
        == "Wikipedia (CC BY-SA 4.0)."
    )


def test_wikipedia_attribution_matches_attributions_doc() -> None:
    """``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION`` is a substring of ``docs/sources/attributions.md``.

    Per AGENTS.md Always-On Rule #15, the code's attribution text
    and the doc's citation text must be byte-for-byte consistent.
    """
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "sources/attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert (
        wikipedia_search_extract.WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION
        in doc_text
    ), (
        f"WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION is not present in "
        f"{doc_path}. Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_wikipedia_module_public_surface() -> None:
    """The orchestrator module re-exports the canonical public surface."""
    for name in [
        "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION",
        "WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY",
        "IndicatorSpec",
        "WikipediaSearchExtractIngestResult",
        "attribution",
        "ingest_wikipedia_search_extract",
        "load_indicator_catalog",
        "read_wikipedia_search_extract",
        "register_wikipedia_search_extract_source",
        "write_wikipedia_search_extract_observations",
        "write_wikipedia_search_extract_parquet",
        "write_wikipedia_search_extract_run_manifest",
    ]:
        assert hasattr(
            wikipedia_search_extract, name
        ), f"wikipedia_search_extract.{name} not exported"
        assert getattr(
            wikipedia_search_extract, name
        ) is not None, (
            f"wikipedia_search_extract.{name} is None"
        )
    assert (
        wikipedia_search_extract.WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
        == "wikipedia_search_extract"
    )


def test_wikipedia_ingest_result_field_count() -> None:
    """``WikipediaSearchExtractIngestResult`` has exactly 7 fields."""
    fields = WikipediaSearchExtractIngestResult.model_fields
    expected_fields = {
        "source_id",
        "parquet_path",
        "observation_rows",
        "queries",
        "indicators",
        "indicators_cached",
        "indicators_fetched",
    }
    assert set(fields.keys()) == expected_fields, (
        f"WikipediaSearchExtractIngestResult field mismatch: "
        f"missing={expected_fields - set(fields.keys())}, "
        f"extra={set(fields.keys()) - expected_fields}"
    )
    assert len(fields) == 7


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_wikipedia_search_extract() -> None:
    """``STAGE2_ADAPTERS['wikipedia_search_extract']`` is the
    orchestrator function.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass; the
    pre-existing ``None`` stub is replaced. Test fails if the
    production wiring is removed.
    """
    assert "wikipedia_search_extract" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["wikipedia_search_extract"] is (
        wikipedia_search_extract.ingest_wikipedia_search_extract
    )
    assert callable(STAGE2_ADAPTERS["wikipedia_search_extract"])


def test_dispatch_table_no_duplicate_wikipedia_search_extract_key() -> None:
    """The dispatch table has exactly one
    ``wikipedia_search_extract`` key (no duplicate from a
    copy-paste bug).
    """
    assert WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY is not None
    count = sum(
        1 for k in STAGE2_ADAPTERS.keys()
        if k == "wikipedia_search_extract"
    )
    assert count == 1, (
        "Expected exactly 1 'wikipedia_search_extract' key in "
        f"STAGE2_ADAPTERS, got {count}"
    )


# ---------------------------------------------------------------------------
# CLI dispatch (production path)
# ---------------------------------------------------------------------------


def test_cli_ingest_source_wikipedia_with_query(
    isolated_data_lake: Path,
    wikipedia_cache_dir: Path,
    wikipedia_catalog_path: Path,
    database_url: str,
) -> None:
    """``leaders-db ingest-source --source wikipedia_search_extract
    --query 'Joe Biden'`` runs through the public CLI path against
    the staged fixture cache (no HTTP), writes the parquet, the DB
    observations, and the run manifest, and exits 0.

    This is the production CLI path for Stage 2 of the Wikipedia
    helper. The test asserts:

    - exit code 0 (no TypeError from passing ``year=`` to the
      queries-only adapter);
    - the adapter's end-of-run echo surfaces the source key;
    - the parquet + manifest files land under
      ``data/processed/wikipedia_search_extract/``;
    - the DB has the expected observation row count.
    """
    from sqlalchemy import func, select
    from typer.testing import CliRunner

    from leaders_db.cli import app as leaders_db_app
    from leaders_db.db.models import SourceObservation

    _init_test_db(database_url)

    runner = CliRunner()
    result = runner.invoke(
        leaders_db_app,
        [
            "ingest-source",
            "--source",
            "wikipedia_search_extract",
            "--query",
            "Joe Biden",
        ],
    )
    assert result.exit_code == 0, (
        f"CLI exited with code {result.exit_code}, "
        f"output: {result.output}"
    )
    # The CLI echoes the source key and the queries list.
    assert "wikipedia_search_extract" in result.output
    assert "Joe Biden" in result.output
    # And the attribution block (Rule #15 — the CLI must echo it).
    assert "Wikipedia (CC BY-SA 4.0)." in result.output

    # The parquet + manifest were written under data/processed/.
    parquet_path = (
        isolated_data_lake
        / "data"
        / "processed"
        / "wikipedia_search_extract"
        / "wikipedia_search_extract_observations.parquet"
    )
    assert parquet_path.is_file()
    manifest_path = parquet_path.parent / (
        "wikipedia_search_extract_run_manifest.json"
    )
    assert manifest_path.is_file()

    # The DB has the expected observation row count.
    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id))
        ).scalar_one()
    assert count == 4  # 1 extracts row + 3 search rows for Joe Biden


def test_cli_ingest_source_wikipedia_without_query_fails(
    isolated_data_lake: Path,
) -> None:
    """``leaders-db ingest-source --source wikipedia_search_extract``
    without ``--query`` fails fast with a clear Typer error
    mentioning ``--query``, not an opaque ``TypeError`` from
    passing ``year=`` to a queries-only adapter.
    """
    from typer.testing import CliRunner

    from leaders_db.cli import app as leaders_db_app

    runner = CliRunner()
    result = runner.invoke(
        leaders_db_app,
        ["ingest-source", "--source", "wikipedia_search_extract"],
    )
    assert result.exit_code != 0
    # The Typer BadParameter message is in stdout (CliRunner mixes
    # stdout + stderr); it must mention --query and the source.
    combined = result.output
    assert "wikipedia_search_extract" in combined
    assert "--query" in combined
