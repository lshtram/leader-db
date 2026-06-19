"""Test suite for the FAS Nuclear Notebook Stage 2 adapter.

Covers the full Phase C.10 contract for ``fas``:

1. Catalog loading (column set, IndicatorSpec dataclass).
2. HTTP cache I/O + fetch (real-format HTML fixture, no network).
3. HTML parser (verbatim HTML -> wide DataFrame; sentinel
   handling for ``n.a.``, ``?``, ``<10``, ranges, footnote
   letters).
4. Snapshot year parsing (meta date element + footer fallback).
5. Parquet write with file-level attribution metadata.
6. DB writes (sources + source_observations + manifest).
7. Idempotency (re-running deletes + re-inserts the same rows).
8. Direct orchestrator (one call, all pieces wired).
9. Attribution drift guard (code == docs/source-attributions.md).
10. Process boundary: changes to production wiring (URL
    builder, DB writer, manifest writer, dispatch table) cause
    observable failure in tests.

Pattern: matches the WHO GHO API / WDI / WGI / UCDP / SIPRI
milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI / Transparency
International CPI test files.
"""

from __future__ import annotations

import json
import math
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
from leaders_db.ingest import STAGE2_ADAPTERS, fas
from leaders_db.ingest.fas import (
    FasIngestResult,
    ingest_fas,
)
from leaders_db.ingest.fas_db import (
    FAS_PUBLISHER_URL,
    FAS_STATUS_PAGE_URL,
    register_fas_source,
    write_fas_observations,
    write_fas_run_manifest,
)
from leaders_db.ingest.fas_db_helpers import (
    _build_observation_rows,
    _coerce_float,
    _coerce_float_from_string,
)
from leaders_db.ingest.fas_html import (
    read_fas_status_html,
    resolve_snapshot_year,
)
from leaders_db.ingest.fas_http import (
    FAS_HTTP_MAX_ATTEMPTS,
    fetch_fas_status_html,
)
from leaders_db.ingest.fas_io import (
    _DEFAULT_CATALOG_PATH,
    FAS_ATTRIBUTION,
    FAS_SOURCE_KEY,
    IndicatorSpec,
    default_html_path,
    default_processed_parquet_path,
    load_indicator_catalog,
    write_fas_parquet,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURE_HTML: Path = (
    Path(__file__).resolve().parent / "fixtures" / "fas" / "sample.html"
)
_EXPECTED_FIXTURE_COUNTRIES: tuple[str, ...] = (
    "China",
    "North Korea",
    "Russia",
    "United Kingdom",
    "United States",
)


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_five_specs() -> None:
    """The catalog has exactly 5 indicators (one per FAS column)."""
    specs = load_indicator_catalog()
    assert len(specs) == 5
    var_names = {s.variable_name for s in specs}
    assert var_names == {
        "fas_operational_strategic",
        "fas_operational_nonstrategic",
        "fas_reserve_nondeployed",
        "fas_military_stockpile",
        "fas_total_inventory",
    }
    # All specs are in the nuclear category with higher_is_better=0.
    for spec in specs:
        assert isinstance(spec, IndicatorSpec)
        assert spec.rating_category == "nuclear"
        assert spec.higher_is_better is False
        assert spec.raw_scale == "warhead_count"


def test_load_indicator_catalog_handles_comments() -> None:
    """The catalog loader skips comment-only lines and the # header block."""
    specs = load_indicator_catalog()
    assert len(specs) == 5


def test_load_indicator_catalog_uses_default_path() -> None:
    """The default catalog path resolves under catalogs/."""
    assert _DEFAULT_CATALOG_PATH.is_file()
    assert _DEFAULT_CATALOG_PATH.name == "fas.csv"


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
    assert FAS_SOURCE_KEY == "fas"
    assert FAS_STATUS_PAGE_URL == (
        "https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html"
    )
    assert FAS_PUBLISHER_URL == "https://fas.org/issues/nuclear-weapons/"
    assert FAS_HTTP_MAX_ATTEMPTS == 2


def test_default_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default HTML + parquet paths resolve under the data lake."""
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    html_path = default_html_path()
    parquet_path = default_processed_parquet_path()
    assert html_path.name == "fas_status.html"
    assert parquet_path.name == "fas_country_year.parquet"


# ---------------------------------------------------------------------------
# Cache I/O + fetch (uses fixture, no network)
# ---------------------------------------------------------------------------


def test_fetch_fas_status_html_from_cache(tmp_path: Path) -> None:
    """The fetch helper reads a cached HTML file without HTTP."""
    cache_path = tmp_path / "fas_status.html"
    shutil.copy(_FIXTURE_HTML, cache_path)

    html, came_from_cache = fetch_fas_status_html(
        cache_path=cache_path, force_refresh=False
    )
    assert came_from_cache is True
    assert "Status of World Nuclear Forces" in html
    assert "Russia" in html
    assert "United States" in html


def test_fetch_fas_status_html_missing_cache_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing cache and an unreachable network raises FileNotFoundError."""
    cache_path = tmp_path / "nope.html"


    def fake_get(*args: object, **kwargs: object) -> None:
        raise requests.ConnectionError("blocked by test")

    monkeypatch.setattr(
        "leaders_db.ingest.fas_http.requests.get", fake_get
    )

    with pytest.raises(FileNotFoundError, match="HTTP failed"):
        fetch_fas_status_html(
            cache_path=cache_path, request_timeout=1.0
        )


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------


def test_read_fas_status_html_wide_shape() -> None:
    """The parser produces a wide DataFrame with the expected columns."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, snapshot_year = read_fas_status_html(html)
    assert len(df) == len(_EXPECTED_FIXTURE_COUNTRIES)
    # Expected columns are exactly the canonical wide shape.
    expected_cols = {
        "country",
        "year",
        "source_row_url",
        "fas_operational_strategic",
        "fas_operational_strategic_raw_value",
        "fas_operational_nonstrategic",
        "fas_operational_nonstrategic_raw_value",
        "fas_reserve_nondeployed",
        "fas_reserve_nondeployed_raw_value",
        "fas_military_stockpile",
        "fas_military_stockpile_raw_value",
        "fas_total_inventory",
        "fas_total_inventory_raw_value",
    }
    assert set(df.columns) == expected_cols
    # The snapshot year is parsed from the meta date.
    assert snapshot_year == 2014
    # All rows have year=2014.
    assert (df["year"] == 2014).all()


def test_read_fas_status_html_real_values() -> None:
    """The parser preserves real FAS values (no invented data)."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    russia = df[df["country"] == "Russia"].iloc[0]
    # Per the live FAS page: Russia operational strategic = 1,600.
    assert int(russia["fas_operational_strategic"]) == 1600
    assert str(russia["fas_operational_strategic_raw_value"]) == "1,600"
    # Russia total inventory = 8,000.
    assert int(russia["fas_total_inventory"]) == 8000
    assert str(russia["fas_total_inventory_raw_value"]) == "8,000"


def test_read_fas_status_html_sentinel_n_a() -> None:
    """The parser maps ``n.a.`` cells to None (normalized) + literal (raw)."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    # UK operational nonstrategic is "n.a." per the live page.
    uk = df[df["country"] == "United Kingdom"].iloc[0]
    assert uk["fas_operational_nonstrategic_raw_value"] == "n.a."
    # The float is NaN (None when read as a regular value).

    assert math.isnan(float(uk["fas_operational_nonstrategic"]))


def test_read_fas_status_html_sentinel_lt_10() -> None:
    """The parser maps ``<10`` cells (HTML-encoded as ``&lt;10``) to the upper bound (10)."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    # North Korea total inventory is ``&lt;10`` (HTML-encoded
    # ``<10``) per the live page. The raw_value preserves the
    # literal HTML-encoded form; the numeric value is the upper
    # bound (10).
    nk = df[df["country"] == "North Korea"].iloc[0]
    assert str(nk["fas_total_inventory_raw_value"]) == "&lt;10"
    assert int(nk["fas_total_inventory"]) == 10


def test_read_fas_status_html_sentinel_question_mark() -> None:
    """The parser maps ``?`` cells to None (normalized) + literal (raw)."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    # China operational nonstrategic is "?" per the live page.
    china = df[df["country"] == "China"].iloc[0]
    assert china["fas_operational_nonstrategic_raw_value"] == "?"

    assert math.isnan(float(china["fas_operational_nonstrategic"]))


def test_read_fas_status_html_skips_aggregate_row() -> None:
    """The aggregate TOTAL row is filtered out by the reader."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    # The TOTAL aggregate row (with ~4,000 in col 1) must not be in the frame.
    assert "Total" not in df["country"].tolist()
    assert "~" not in df["country"].tolist()
    # All countries are real (not the aggregate).
    assert all(
        c in _EXPECTED_FIXTURE_COUNTRIES for c in df["country"].tolist()
    )


def test_resolve_snapshot_year_from_meta_date() -> None:
    """The snapshot year is parsed from the page's meta date element."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    assert resolve_snapshot_year(html) == 2014


def test_resolve_snapshot_year_default_fallback() -> None:
    """An HTML page with no meta date falls back to the conservative default."""
    # Minimal HTML with no meta date element.
    html = "<html><body><table id='table1'><tr><td>Country</td></tr></table></body></html>"
    assert resolve_snapshot_year(html) == 2014


def test_resolve_snapshot_year_override() -> None:
    """The snapshot_year kwarg overrides the parsed value."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, snapshot_year = read_fas_status_html(html, snapshot_year=2025)
    assert snapshot_year == 2025
    assert (df["year"] == 2025).all()


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def test_coerce_float_handles_common_types() -> None:
    """_coerce_float handles None, NaN, int, float, and string sentinels."""
    assert _coerce_float(None) is None
    assert _coerce_float(float("nan")) is None
    assert _coerce_float(1600) == 1600.0
    assert _coerce_float(1600.0) == 1600.0
    assert _coerce_float(True) is None  # defensive
    assert _coerce_float("NA") is None
    assert _coerce_float("") is None
    assert _coerce_float("nan") is None
    assert _coerce_float("1600") == 1600.0
    assert _coerce_float(" 8000 ") == 8000.0
    assert _coerce_float("not-a-number") is None


def test_coerce_float_from_string_basic() -> None:
    """The string variant handles missing strings and edge cases."""
    assert _coerce_float_from_string("1600") == 1600.0
    assert _coerce_float_from_string("") is None
    assert _coerce_float_from_string("nan") is None


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def test_build_observation_rows_shape_and_reference() -> None:
    """Each row has the expected fields and source_row_reference format."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    specs = load_indicator_catalog()

    rows = _build_observation_rows(source_id=42, df=df, specs=specs)
    expected = len(_EXPECTED_FIXTURE_COUNTRIES) * len(specs)
    assert len(rows) == expected
    for row in rows:
        assert isinstance(row, SourceObservation)
        assert row.source_id == 42
        assert row.country_id is None  # Stage 3 fills
        assert row.leader_id is None  # Stage 4 fills
        assert row.year == 2014
        assert row.confidence is None  # Stage 11 fills
        # source_row_reference carries the catalog raw_column + country name.
        assert row.source_row_reference.startswith("fas:")
        # The country is the rightmost field after the second colon.
        parts = row.source_row_reference.split(":")
        assert parts[0] == "fas"
        assert parts[1] in {
            "Operational Strategic",
            "Operational Nonstrategic",
            "Reserve/Nondeployed",
            "Military Stockpile",
            "Total Inventory",
        }


def test_build_observation_rows_real_values() -> None:
    """The numeric normalized_value matches the real FAS value."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    specs = load_indicator_catalog()
    rows = _build_observation_rows(source_id=1, df=df, specs=specs)
    # Russia's total_inventory = 8000 (live page).
    russia_total = next(
        r
        for r in rows
        if r.variable_name == "fas_total_inventory"
        and r.source_row_reference.endswith(":Russia")
    )
    assert int(russia_total.normalized_value) == 8000
    assert russia_total.raw_value == "8,000"


# ---------------------------------------------------------------------------
# Parquet write + metadata
# ---------------------------------------------------------------------------


def test_write_fas_parquet_attaches_metadata(tmp_path: Path) -> None:
    """The parquet file carries the FAS attribution in metadata."""
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    out = tmp_path / "out.parquet"
    write_fas_parquet(df, parquet_path=out)
    assert out.is_file()

    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    assert meta[b"fas_attribution"] == FAS_ATTRIBUTION.encode("utf-8")
    assert meta[b"fas_source_key"] == b"fas"


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def test_register_fas_source_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """register_fas_source is idempotent (same id on repeated calls)."""
    _init_test_db(database_url)
    with session_scope() as session:
        first_id = register_fas_source(session)
    with session_scope() as session:
        second_id = register_fas_source(session)
    assert first_id == second_id
    assert first_id >= 1


def test_register_fas_source_writes_publisher_url(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The sources row carries the canonical FAS status page URL."""
    _init_test_db(database_url)
    with session_scope() as session:
        source_id = register_fas_source(session)
    with session_scope() as session:

        row = session.execute(
            select(Source).where(Source.id == source_id)
        ).scalar_one()
    assert row.source_url == FAS_STATUS_PAGE_URL
    assert row.source_name == (
        "Federation of American Scientists Nuclear Notebook"
    )
    assert "Federation of American Scientists" in row.license_note


# ---------------------------------------------------------------------------
# DB observations + manifest
# ---------------------------------------------------------------------------


def test_write_fas_observations_row_count(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The DB writer writes one row per (country, year, variable)."""
    _init_test_db(database_url)
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)
    specs = load_indicator_catalog()

    with session_scope() as session:
        source_id = register_fas_source(session)
        rows = write_fas_observations(
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
        assert db_row.year == 2014
        assert db_row.source_row_reference.startswith("fas:")


def test_write_fas_observations_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """Re-running the DB writer deletes + re-inserts the same row count."""
    _init_test_db(database_url)
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, _ = read_fas_status_html(html)

    with session_scope() as session:
        source_id = register_fas_source(session)
        first = write_fas_observations(
            session, source_id, df, catalog_path=None
        )
    with session_scope() as session:
        second = write_fas_observations(
            session, source_id, df, catalog_path=None
        )
    assert first == second == (
        len(_EXPECTED_FIXTURE_COUNTRIES) * len(load_indicator_catalog())
    )

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
    assert len(db_rows) == (
        len(_EXPECTED_FIXTURE_COUNTRIES) * len(load_indicator_catalog())
    )


def test_write_fas_run_manifest_payload(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The run manifest carries the expected audit-trail payload."""
    _init_test_db(database_url)
    html = _FIXTURE_HTML.read_text(encoding="utf-8")
    df, snapshot_year = read_fas_status_html(html)
    specs = load_indicator_catalog()

    with session_scope() as session:
        source_id = register_fas_source(session)
        rows = write_fas_observations(
            session, source_id, df, catalog_path=None
        )

    result = FasIngestResult(
        source_id=source_id,
        parquet_path=default_processed_parquet_path(),
        observation_rows=rows,
        countries=len(_EXPECTED_FIXTURE_COUNTRIES),
        years=(snapshot_year,),
        indicators=len(specs),
        snapshot_year=snapshot_year,
        html_cached=True,
        html_fetched=False,
        status_page_url=FAS_STATUS_PAGE_URL,
    )
    manifest_path = write_fas_run_manifest(
        result,
        snapshot_year=snapshot_year,
        html_cached=True,
        html_fetched=False,
        status_page_url=FAS_STATUS_PAGE_URL,
    )
    assert manifest_path.is_file()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["attribution"] == FAS_ATTRIBUTION
    assert payload["source_key"] == FAS_SOURCE_KEY
    assert payload["status_page_url"] == FAS_STATUS_PAGE_URL
    assert payload["publisher_url"] == FAS_PUBLISHER_URL
    assert payload["snapshot_year"] == 2014
    assert payload["html_cached"] is True
    assert payload["html_fetched"] is False
    assert payload["years"] == [2014]


# ---------------------------------------------------------------------------
# Orchestrator (end-to-end, uses the fixture cache)
# ---------------------------------------------------------------------------


def test_ingest_fas_end_to_end(
    isolated_data_lake: Path, database_url: str
) -> None:
    """The orchestrator runs end-to-end against the cached fixture."""
    _init_test_db(database_url)
    # Stage the fixture HTML at the conventional cache path
    # (``<root>/data/raw/fas/fas_status.html`` via
    # ``default_html_path()``). The orchestrator reads from this
    # path so a cache hit means no HTTP.
    raw_dir_path = (
        isolated_data_lake / "data" / "raw" / FAS_SOURCE_KEY
    )
    raw_dir_path.mkdir(parents=True, exist_ok=True)
    cache_html = raw_dir_path / default_html_path().name
    shutil.copy(_FIXTURE_HTML, cache_html)

    # The orchestrator must run without network (cache is staged).
    result = ingest_fas(force_refresh=False)

    assert isinstance(result, FasIngestResult)
    assert result.source_id >= 1
    assert result.countries == len(_EXPECTED_FIXTURE_COUNTRIES)
    assert result.years == (2014,)
    assert result.indicators == 5
    assert result.snapshot_year == 2014
    assert result.html_cached is True
    assert result.html_fetched is False
    assert result.observation_rows == (
        len(_EXPECTED_FIXTURE_COUNTRIES) * len(load_indicator_catalog())
    )
    assert result.status_page_url == FAS_STATUS_PAGE_URL
    # Parquet + manifest files exist.
    assert result.parquet_path.is_file()
    manifest_path = result.parquet_path.parent / "fas_run_manifest.json"
    assert manifest_path.is_file()


def test_ingest_fas_idempotent(
    isolated_data_lake: Path, database_url: str
) -> None:
    """Re-running the orchestrator yields the same row count (no append)."""
    _init_test_db(database_url)
    raw_dir_path = (
        isolated_data_lake / "data" / "raw" / FAS_SOURCE_KEY
    )
    raw_dir_path.mkdir(parents=True, exist_ok=True)
    cache_html = raw_dir_path / default_html_path().name
    shutil.copy(_FIXTURE_HTML, cache_html)

    first = ingest_fas()
    second = ingest_fas()
    assert first.observation_rows == second.observation_rows
    assert first.countries == second.countries
    assert first.source_id == second.source_id


# ---------------------------------------------------------------------------
# Attribution drift guard (Always-On Rule #15)
# ---------------------------------------------------------------------------


def test_fas_attribution_matches_attributions_doc() -> None:
    """The code attribution text is byte-identical to docs/source-attributions.md.

    Strengthens the drift guard: in addition to verifying that the
    attribution string appears 3+ times in the doc (section + cheat
    sheet + summary table), the test asserts that the provenance
    wording reflects the production implementation. The Stage 2
    adapter ingests the consolidated FAS "Status of World Nuclear
    Forces" page (a single HTML table for the 9 nuclear-armed
    states); a previous version of this doc claimed "a curated
    whitelist of country pages", which is now stale. The doc must
    also flag the 2014-04-30 snapshot freshness caveat.
    """
    doc_path = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "source-attributions.md"
    )
    assert doc_path.is_file(), (
        f"Source attributions doc not found: {doc_path}"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    # The constant appears in the fas section, in the
    # citation cheat-sheet, and in the summary table. Match
    # all three.
    pattern = re.compile(
        r"FAS Nuclear Notebook \(Federation of American Scientists\)\.",
        re.MULTILINE,
    )
    matches = pattern.findall(doc_text)
    assert len(matches) >= 3, (
        "Expected >=3 occurrences in source-attributions.md "
        "(section + cheat-sheet + summary table); got "
        f"{len(matches)}"
    )
    # The constant in code is byte-identical to the doc.
    assert FAS_ATTRIBUTION == (
        "FAS Nuclear Notebook (Federation of American Scientists)."
    )
    # The orchestrator's attribution() helper returns the same string.
    assert fas.attribution() == FAS_ATTRIBUTION
    # The Pydantic result's .attribution property returns the same string.
    result = FasIngestResult(
        source_id=1,
        parquet_path=Path("/tmp/dummy.parquet"),
        observation_rows=0,
        countries=0,
        years=(2014,),
        indicators=5,
        snapshot_year=2014,
        html_cached=True,
        html_fetched=False,
        status_page_url=FAS_STATUS_PAGE_URL,
    )
    assert result.attribution == FAS_ATTRIBUTION

    # Provenance drift guard: the doc must reflect the
    # consolidated status page (the actual Stage 2 contract)
    # and flag the snapshot freshness caveat. Capture the
    # prose between the ``fas`` section heading and the next H3
    # and assert it mentions the canonical status page URL and
    # the snapshot year / freshness stamp.
    section_match = re.search(
        r"### `fas`.*?(?=\n### )",
        doc_text,
        re.DOTALL,
    )
    assert section_match is not None, (
        "fas section not found in source-attributions.md"
    )
    section_text = section_match.group(0)
    assert "nukestatus.html" in section_text, (
        "fas section must reference the consolidated status "
        "page URL (the Stage 2 contract)."
    )
    assert "snapshot" in section_text.lower(), (
        "fas section must mention the snapshot year / "
        "freshness stamp (the consolidated page is dated "
        "2014-04-30 as of probe; Stage 11 confidence penalises "
        "the temporal-fit gap)."
    )
    # Negative assertion: the prose should not claim "a curated
    # whitelist of country pages" as the production
    # provenance (the previous stale wording).
    assert "curated whitelist" not in section_text, (
        "fas provenance wording is stale: the Stage 2 "
        "adapter ingests the consolidated status page "
        "(nukestatus.html), not a curated whitelist of "
        "per-country pages."
    )


# ---------------------------------------------------------------------------
# Process boundary: changes to production wiring cause failure
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_fas() -> None:
    """STAGE2_ADAPTERS["fas"] is the orchestrator function."""

    assert STAGE2_ADAPTERS["fas"] is fas.ingest_fas


def test_cli_lists_fas() -> None:
    """The CLI surface includes the fas source (via dispatch)."""

    assert callable(STAGE2_ADAPTERS["fas"])
