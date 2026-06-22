"""Tests for the Country-Year Chronicle Wikidata recent-rulers fallback.

These tests verify the Increment 6 Wikidata recent-rulers adapter:

- The SPARQL query builder emits a query that references both
  ``Q30461`` (head of state) and ``Q22857062`` (head of
  government), joins the country via ``wdt:P27``, and includes
  the ``wdt:P298`` (ISO 3166-1 alpha-3) projection so we can map
  the Wikidata row to a Chronicle ISO3 identity directly.
- The parser turns one SPARQL binding into one long-format row
  keyed by ``(iso3, year, office_qid, person_qid)`` with the
  ``country_qid`` / ``person_qid`` / ``office_qid`` columns
  containing bare QIDs (the ``http://www.wikidata.org/entity/``
  URI prefix is stripped).
- The :class:`WikidataRecentRulersSource.resolve` method applies
  the documented office-precedence tie-break:
  head-of-government (Q22857062) wins over head-of-state
  (Q30461). Within an office the latest ``start_date`` wins,
  with a ``person_label`` tie-break for determinism.
- The cache-first / HTTP-fallback reader writes the verbatim
  SPARQL response as pretty-printed JSON under
  ``<cache_dir>/cyc_<year>_all_<hash>.json``.
- The :class:`RulerResolver` uses the Wikidata source as the
  lowest-precedence fallback: Archigos + REIGN rows are NEVER
  overridden for the years they cover, SUN rows bypass
  Wikidata entirely, and an empty Wikidata frame degrades to
  the canonical missing-ruler placeholder (no exception).

The tests build tiny in-memory SPARQL payloads instead of
hitting the live endpoint, so they run in <1s on any CI box.
The cache I/O uses :class:`tmp_path` so test runs do not
pollute ``data/raw/wikidata_heads_of_state_government/cache/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from leaders_db.chronicle._wikidata_recent_rulers import (
    ISO3_PROPERTY_QID,
    WikidataRecentRulersSource,
    build_recent_rulers_sparql,
    default_cache_dir,
    fetch_recent_rulers_payload,
    load_wikidata_recent_rulers_source,
    parse_recent_rulers_payload,
)
from leaders_db.chronicle.constants import (
    FLAG_COLONIAL_RULE_PLACEHOLDER,
    WIKIDATA_RECENT_RULERS_ATTRIBUTION,
    WIKIDATA_RECENT_RULERS_DIRECT_CONFIDENCE,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import RulerResolver
from leaders_db.chronicle.source_constants import (
    REIGN_COVERAGE_END_YEAR,
    SOURCE_TAG_COLONIAL_RULE_PLACEHOLDER,
    SOURCE_TAG_WIKIDATA_RECENT_RULERS,
)
from leaders_db.chronicle.sources import (
    SipriSource,
    VDemSource,
    WdiSource,
)

# ---------------------------------------------------------------------------
# SPARQL query builder
# ---------------------------------------------------------------------------


def test_sparql_query_includes_both_offices_and_iso3_projection() -> None:
    """The canonical query selects both offices via VALUES, joins
    the country via office jurisdiction (P1001), and projects P298 (ISO3) for direct
    Chronicle identity mapping.
    """
    query = build_recent_rulers_sparql(year=2024)
    assert "Q30461" in query
    assert "Q22857062" in query
    assert "Q14212" in query
    assert "VALUES ?role" in query
    assert "wdt:P1001" in query
    assert "wdt:P279* ?role" in query
    assert "wdt:P31 wd:Q5" in query
    assert f"wdt:{ISO3_PROPERTY_QID}" in query
    assert "FILTER(YEAR(?start) <= 2024)" in query
    assert "FILTER(!BOUND(?end) || YEAR(?end) >= 2024)" in query


def test_sparql_query_year_validation() -> None:
    """Non-int years are rejected by the query builder."""
    with pytest.raises(TypeError):
        build_recent_rulers_sparql(year="2024")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _binding(
    person_qid: str,
    person_label: str,
    office_qid: str,
    office_label: str,
    country_qid: str,
    role_qid: str | None = None,
    country_iso3: str = "",
    country_label: str = "",
    start: str = "2024-01-20T00:00:00Z",
    end: str | None = None,
) -> dict[str, Any]:
    """Build one SPARQL binding row matching the Stage 2 / Chronicle
    parser's expected schema.
    """
    row: dict[str, Any] = {
        "person": {
            "type": "uri",
            "value": f"http://www.wikidata.org/entity/{person_qid}",
        },
        "personLabel": {
            "type": "literal",
            "value": person_label,
            "xml:lang": "en",
        },
        "office": {
            "type": "uri",
            "value": f"http://www.wikidata.org/entity/{office_qid}",
        },
        "officeLabel": {
            "type": "literal",
            "value": office_label,
            "xml:lang": "en",
        },
        "role": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/"
            f"{role_qid or office_qid}",
        },
        "country": {
            "type": "uri",
            "value": f"http://www.wikidata.org/entity/{country_qid}",
        },
        "countryLabel": {
            "type": "literal",
            "value": country_label,
            "xml:lang": "en",
        },
        "start": {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#dateTime",
            "value": start,
        },
    }
    if country_iso3:
        row["countryISO3"] = {
            "type": "literal",
            "value": country_iso3,
        }
    if end is not None:
        row["end"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#dateTime",
            "value": end,
        }
    return row


def _payload(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of binding rows in a SPARQL JSON response envelope."""
    return {
        "head": {
            "vars": [
                "country", "countryISO3", "countryLabel",
                "person", "personLabel",
                "office", "officeLabel", "role",
                "start", "end", "statement",
            ]
        },
        "results": {"bindings": bindings},
    }


def test_parser_returns_one_row_per_binding() -> None:
    """Each SPARQL binding becomes one long-format row with the
    documented columns. URIs are stripped to bare QIDs and the
    ISO3 value is uppercased.
    """
    payload = _payload([
        _binding(
            person_qid="Q6279", person_label="Joe Biden",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="usa",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
            end="2025-01-20T00:00:00Z",
        ),
        _binding(
            person_qid="Q76", person_label="Barack Obama",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2009-01-20T00:00:00Z",
            end="2017-01-20T00:00:00Z",
        ),
    ])
    frame = parse_recent_rulers_payload(payload, year=2024)
    assert len(frame) == 2
    assert set(frame.columns) == {
        "iso3", "country_qid", "country_label",
        "person_qid", "person_label",
        "office_qid", "office_label",
        "role_qid", "start_date", "end_date", "year",
    }
    assert (frame["iso3"] == "USA").all()
    assert (frame["person_qid"] == ["Q6279", "Q76"]).all()
    assert (frame["office_qid"] == "Q30461").all()
    assert (frame["year"] == "2024").all()


def test_parser_handles_empty_bindings() -> None:
    """An empty bindings list returns an empty frame with the
    canonical columns (no KeyError on column access).
    """
    frame = parse_recent_rulers_payload(_payload([]), year=2024)
    assert frame.empty
    assert list(frame.columns) == [
        "iso3", "country_qid", "country_label",
        "person_qid", "person_label",
        "office_qid", "office_label",
        "role_qid", "start_date", "end_date", "year",
    ]


def test_parser_raises_on_malformed_payload() -> None:
    """Non-dict payloads raise :class:`ValueError` so the
    loader can degrade gracefully without crashing the resolver.
    """
    with pytest.raises(ValueError):
        parse_recent_rulers_payload([], year=2024)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WikidataRecentRulersSource.resolve
# ---------------------------------------------------------------------------


def _frame_from_bindings(
    bindings: list[dict[str, Any]], *, year: int
) -> pd.DataFrame:
    """Parse ``bindings`` and return the long-format frame."""
    return parse_recent_rulers_payload(_payload(bindings), year=year)


def test_source_resolve_returns_winner_for_iso3_year_match() -> None:
    """A clean (single-row) frame resolves to the holder."""
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q6279", person_label="Joe Biden",
            office_qid="Q11696", office_label="President",
            role_qid="Q30461",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
        ),
    ], year=2024)
    source = WikidataRecentRulersSource(
        frame=frame, cache_dir=Path("/tmp"),
    )
    hit = source.resolve("USA", 2024)
    assert hit is not None
    assert hit["person_label"] == "Joe Biden"
    assert hit["role_qid"] == "Q30461"


def test_source_resolve_prefers_head_of_government_over_head_of_state() -> None:
    """When both offices have holders, head of government
    (``Q22857062``) wins over head of state (``Q30461``).
    """
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q6279", person_label="Joe Biden",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
        ),
        _binding(
            person_qid="Q23685", person_label="Kamala Harris",
            office_qid="Q1199654", office_label="Vice President",
            role_qid="Q22857062",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
        ),
    ], year=2024)
    source = WikidataRecentRulersSource(
        frame=frame, cache_dir=Path("/tmp"),
    )
    hit = source.resolve("USA", 2024)
    assert hit is not None
    assert hit["person_label"] == "Kamala Harris"
    assert hit["role_qid"] == "Q22857062"


def test_source_resolve_uses_latest_start_date_within_office() -> None:
    """Within the same office, the row with the latest
    ``start_date`` wins. The lexicographically smallest
    ``person_label`` is the deterministic tie-break.
    """
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Alice",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2009-01-20T00:00:00Z",
        ),
        _binding(
            person_qid="Q2", person_label="Bob",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2021-01-20T00:00:00Z",
        ),
        _binding(
            person_qid="Q3", person_label="Carol",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2021-01-20T00:00:00Z",
        ),
    ], year=2024)
    source = WikidataRecentRulersSource(
        frame=frame, cache_dir=Path("/tmp"),
    )
    hit = source.resolve("USA", 2024)
    # Bob and Carol have the same start_date; Bob sorts first
    # alphabetically so Bob wins.
    assert hit is not None
    assert hit["person_label"] == "Bob"
    assert hit["person_qid"] == "Q2"


def test_source_resolve_returns_none_for_unknown_iso3() -> None:
    """An ISO3 not in the frame returns ``None`` (the resolver
    chain then falls back to missing-ruler).
    """
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Alice",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2021-01-20T00:00:00Z",
        ),
    ], year=2024)
    source = WikidataRecentRulersSource(
        frame=frame, cache_dir=Path("/tmp"),
    )
    assert source.resolve("FRA", 2024) is None


def test_source_resolve_returns_none_for_empty_frame() -> None:
    """An empty frame (no cache, network failed) returns ``None``
    so the resolver degrades gracefully.
    """
    source = WikidataRecentRulersSource(
        frame=pd.DataFrame(),
        cache_dir=Path("/tmp"),
    )
    assert source.is_empty
    assert source.resolve("USA", 2024) is None


def test_source_is_empty_false_when_frame_has_rows() -> None:
    """``is_empty`` is False when the frame has any row."""
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Alice",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2024-01-20T00:00:00Z",
        ),
    ], year=2024)
    source = WikidataRecentRulersSource(
        frame=frame, cache_dir=Path("/tmp"),
    )
    assert not source.is_empty


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def test_cache_key_format_is_stable_and_prefixed() -> None:
    """The cache key prefix is ``cyc_`` to avoid colliding with
    the Stage 2 adapter's ``wd_`` prefix, and the key encodes
    the year + template hash so a query-shape change
    invalidates the cache.
    """
    from leaders_db.chronicle._wikidata_recent_rulers import _cache_key

    key = _cache_key(year=2024)
    assert key.startswith("cyc_2024_all_")
    assert key.endswith(".json") is False


def test_default_cache_dir_lives_under_wikidata_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default cache directory lives under
    ``data/raw/wikidata_heads_of_state_government/cache`` so the
    two adapters share the directory but not the key prefix.
    """
    from leaders_db.chronicle import _wikidata_recent_rulers as mod

    # Redirect raw_dir via env var so the test does not depend on
    # the real project root.
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    # Drop any cached project root.
    from leaders_db import env as _env
    from leaders_db import paths as _paths
    _env._LOADED = False
    if hasattr(_paths, "_project_root_cached"):
        delattr(_paths, "_project_root_cached")
    cache_dir = default_cache_dir()
    assert cache_dir == (
        tmp_path / "data" / "raw"
        / "wikidata_heads_of_state_government" / "cache"
    )
    assert cache_dir.is_dir()
    # Sanity-check the module symbol exists (the function is
    # re-exported).
    assert hasattr(mod, "default_cache_dir")


def test_cache_reader_writes_and_reads_verbatim(
    tmp_path: Path,
) -> None:
    """The cache writer preserves the verbatim SPARQL JSON
    payload so re-runs skip HTTP and a reader can audit the
    data.
    """
    payload = _payload([
        _binding(
            person_qid="Q1", person_label="Alice",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2024-01-20T00:00:00Z",
        ),
    ])
    # Build the cache file the same way the module does.
    from leaders_db.chronicle._wikidata_recent_rulers import (
        _cache_key,
        _write_cached_json,
    )
    cache_path = tmp_path / f"{_cache_key(year=2024)}.json"
    _write_cached_json(cache_path, payload)
    assert cache_path.is_file()
    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
    assert loaded == payload


def test_fetch_payload_degrades_on_malformed_http_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed SPARQL JSON degrades to ``None`` instead of crashing."""
    import requests

    class _MalformedResponse:
        text = '{"results": {"bindings": [}'

        def raise_for_status(self) -> None:
            return None

    def _fake_get(*_args: object, **_kwargs: object) -> _MalformedResponse:
        return _MalformedResponse()

    monkeypatch.setattr(requests, "get", _fake_get)
    result = fetch_recent_rulers_payload(
        year=2024,
        cache_dir=tmp_path,
        force_refresh=True,
        timeout=0.1,
    )
    assert result is None


def test_loader_skips_malformed_cached_payload_shape(tmp_path: Path) -> None:
    """A valid JSON cache with invalid SPARQL shape is skipped."""
    from leaders_db.chronicle._wikidata_recent_rulers import _cache_key

    cache_path = tmp_path / f"{_cache_key(year=2024)}.json"
    cache_path.write_text(
        json.dumps({"results": {"bindings": {}}}),
        encoding="utf-8",
    )
    source = load_wikidata_recent_rulers_source(
        years=(2024,),
        cache_dir=tmp_path,
        force_refresh=False,
    )
    assert source.frame.empty
    assert source.cached_years == ()
    assert source.fetched_years == ()


def test_loader_skips_malformed_http_payload_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fetched JSON payload with invalid SPARQL shape is skipped."""
    import requests

    class _MalformedShapeResponse:
        text = json.dumps({"results": {"bindings": {}}})

        def raise_for_status(self) -> None:
            return None

    def _fake_get(*_args: object, **_kwargs: object) -> _MalformedShapeResponse:
        return _MalformedShapeResponse()

    monkeypatch.setattr(requests, "get", _fake_get)
    source = load_wikidata_recent_rulers_source(
        years=(2024,),
        cache_dir=tmp_path,
        force_refresh=True,
        timeout=0.1,
    )
    assert source.frame.empty
    assert source.cached_years == ()
    assert source.fetched_years == ()


# ---------------------------------------------------------------------------
# RulerResolver integration
# ---------------------------------------------------------------------------


def _empty_resolver_with_wikidata(
    frame: pd.DataFrame | None,
) -> RulerResolver:
    """Build a resolver with empty Archigos / REIGN / SUN frames
    and the supplied Wikidata frame.
    """
    source = (
        WikidataRecentRulersSource(frame=frame, cache_dir=Path("/tmp"))
        if frame is not None
        else None
    )
    return RulerResolver(
        archigos_frame=pd.DataFrame(),
        reign_frame=pd.DataFrame(),
        sun_frame=pd.DataFrame(),
        wikidata_recent_source=source,
    )


def test_resolver_uses_wikidata_for_post_reign_year() -> None:
    """USA 2024 (past REIGN coverage 2021) resolves from the
    Wikidata recent-rulers frame when Archigos + REIGN are
    empty.
    """
    frame = _frame_from_bindings([
        _binding(
            person_qid="Q6279", person_label="Joe Biden",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
            end="2025-01-20T00:00:00Z",
        ),
    ], year=2024)
    resolver = _empty_resolver_with_wikidata(frame)
    result = resolver.resolve("USA", 2024)
    assert result.has_ruler is True
    assert result.ruler_name == "Joe Biden"
    assert result.ruler_title == "President"
    assert result.ruler_source == SOURCE_TAG_WIKIDATA_RECENT_RULERS
    assert result.ruler_confidence == WIKIDATA_RECENT_RULERS_DIRECT_CONFIDENCE
    assert result.ruler_source_year_used == 2024


def test_resolver_does_not_override_archigos_year() -> None:
    """An Archigos row for a year that is also covered by the
    Wikidata frame wins; the resolver does NOT consult
    Wikidata when Archigos returns a hit.
    """
    archigos_frame = pd.DataFrame(
        [
            {
                "iso3": "USA",
                "leader": "Herbert Hoover",
                "startdate": pd.Timestamp("1929-03-04"),
                "enddate": pd.Timestamp("1933-03-04"),
            },
        ]
    )
    wikidata_frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Wrong Person",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2024-01-20T00:00:00Z",
        ),
    ], year=1930)
    resolver = RulerResolver(
        archigos_frame=archigos_frame,
        wikidata_recent_source=WikidataRecentRulersSource(
            frame=wikidata_frame, cache_dir=Path("/tmp"),
        ),
    )
    result = resolver.resolve("USA", 1930)
    assert result.has_ruler is True
    assert result.ruler_name == "Herbert Hoover"
    assert result.ruler_source == "archigos"


def test_resolver_does_not_override_reign_year() -> None:
    """A REIGN row for a year that is also covered by the
    Wikidata frame wins; the resolver does NOT consult
    Wikidata when REIGN returns a hit.
    """
    reign_frame = pd.DataFrame(
        [
            {
                "iso3": "USA", "year": 2000, "month": m,
                "leader": "George W. Bush",
                "government": "Presidential Democracy",
            }
            for m in range(1, 13)
        ]
    )
    wikidata_frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Wrong Person",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2000-01-20T00:00:00Z",
        ),
    ], year=2000)
    resolver = RulerResolver(
        reign_frame=reign_frame,
        wikidata_recent_source=WikidataRecentRulersSource(
            frame=wikidata_frame, cache_dir=Path("/tmp"),
        ),
    )
    result = resolver.resolve("USA", 2000)
    assert result.has_ruler is True
    assert result.ruler_name == "George W. Bush"
    assert result.ruler_source == "reign"


def test_resolver_returns_missing_when_wikidata_frame_empty() -> None:
    """When the Wikidata frame is empty (network failed, no
    cache), the resolver degrades to missing-ruler without
    raising.
    """
    resolver = _empty_resolver_with_wikidata(pd.DataFrame())
    result = resolver.resolve("USA", 2024)
    assert result.has_ruler is False
    assert result.ruler_source == ""
    assert result.ruler_confidence == 0


def test_resolver_returns_missing_when_wikidata_source_is_none() -> None:
    """When the resolver is built without a Wikidata source
    (``wikidata_recent_source=None``), it falls back to missing
    for any year past REIGN coverage. This is the default
    behaviour for callers that do not opt in to the fallback.
    """
    resolver = RulerResolver(
        archigos_frame=pd.DataFrame(),
        reign_frame=pd.DataFrame(),
        sun_frame=pd.DataFrame(),
        wikidata_recent_source=None,
    )
    result = resolver.resolve("USA", 2024)
    assert result.has_ruler is False


def test_resolver_sun_row_bypasses_wikidata() -> None:
    """SUN rows never consult the Wikidata frame; the curated
    SUN source is the only SUN ruler input. An empty curated
    SUN frame returns missing even when a Wikidata row exists
    for an iso3 of ``"SUN"``.
    """
    wikidata_frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Wrong Person",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="SUN",  # unlikely but defensive
            start="1950-01-01T00:00:00Z",
        ),
    ], year=1950)
    resolver = RulerResolver(
        archigos_frame=pd.DataFrame(),
        reign_frame=pd.DataFrame(),
        sun_frame=pd.DataFrame(),
        wikidata_recent_source=WikidataRecentRulersSource(
            frame=wikidata_frame, cache_dir=Path("/tmp"),
        ),
    )
    result = resolver.resolve("SUN", 1950)
    assert result.has_ruler is False


# ---------------------------------------------------------------------------
# Row builder integration
# ---------------------------------------------------------------------------


def _stub_vdem() -> VDemSource:
    class _Stub:
        pass

    frame = pd.DataFrame(
        columns=[
            "country_text_id", "year", "v2x_regime",
            "v2x_polyarchy", "v2x_libdem", "v2svindep", "COWcode",
        ]
    )
    return VDemSource(raw_csv_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _colonial_vdem() -> VDemSource:
    class _Stub:
        pass

    frame = pd.DataFrame(
        [
            {
                "country_text_id": "AGO",
                "year": 1920,
                "v2x_regime": None,
                "v2x_polyarchy": None,
                "v2x_libdem": None,
                "v2svindep": 0,
                "COWcode": None,
            },
        ]
    )
    return VDemSource(raw_csv_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_wdi() -> WdiSource:
    class _Stub:
        pass

    frame = pd.DataFrame(
        columns=[
            "iso3", "year", "wdi_population", "wdi_gdp_current_usd",
            "wdi_gdp_constant_2015_usd", "wdi_gdp_per_capita",
            "wdi_gdp_per_capita_ppp_constant_2017",
        ]
    )
    return WdiSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_sipri() -> SipriSource:
    class _Stub:
        pass

    frame = pd.DataFrame(columns=["country", "year", "sipri_milex_constant_usd"])
    return SipriSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def test_row_builder_emits_wikidata_row_for_post_reign_year() -> None:
    """The row builder propagates the Wikidata-resolved ruler
    into the chronicle CSV row with the
    ``SOURCE_TAG_WIKIDATA_RECENT_RULERS`` tag and the
    documented confidence.
    """
    wikidata_frame = _frame_from_bindings([
        _binding(
            person_qid="Q6279", person_label="Joe Biden",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            country_label="United States",
            start="2021-01-20T00:00:00Z",
            end="2025-01-20T00:00:00Z",
        ),
    ], year=2024)
    resolver = _empty_resolver_with_wikidata(wikidata_frame)
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    assert row["ruler_name"] == "Joe Biden"
    assert row["ruler_title"] == "President"
    assert row["ruler_source"] == SOURCE_TAG_WIKIDATA_RECENT_RULERS
    assert row["ruler_confidence"] == str(
        WIKIDATA_RECENT_RULERS_DIRECT_CONFIDENCE
    )
    flags = row["data_quality_flags"].split("|")
    assert "missing_ruler" not in flags
    assert "ruler=wikidata_recent_rulers" in row["provenance_summary"]


def test_row_builder_keeps_missing_ruler_flag_when_no_wikidata_hit() -> None:
    """When the Wikidata frame has no row for the
    ``(iso3, year)`` pair, the row builder emits the
    canonical ``missing_ruler`` flag.
    """
    resolver = _empty_resolver_with_wikidata(pd.DataFrame())
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert "missing_ruler" in flags


def test_row_builder_fills_colonial_rule_placeholder_for_non_independent_year() -> None:
    """V-Dem non-independent country-years get the temporary
    ``colonial-rule`` fill instead of counting as missing rulers.
    """
    resolver = _empty_resolver_with_wikidata(pd.DataFrame())
    rows = build_chronicle_rows(
        iso3_scope=("AGO",),
        start_year=1920,
        end_year=1920,
        vdem=_colonial_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert row["ruler_name"] == "colonial-rule"
    assert row["ruler_source"] == SOURCE_TAG_COLONIAL_RULE_PLACEHOLDER
    assert row["ruler_confidence"] == "0"
    assert "missing_ruler" not in flags
    assert FLAG_COLONIAL_RULE_PLACEHOLDER in flags


def test_row_builder_fills_colonial_rule_for_bracketed_vdem_gap() -> None:
    """Internal V-Dem gaps bracketed by non-independent rows are
    treated as colonial/dependent for the temporary ruler fill.
    """
    resolver = _empty_resolver_with_wikidata(pd.DataFrame())
    class _Stub:
        pass

    vdem = VDemSource(
        raw_csv_path=_Stub(),  # type: ignore[arg-type]
        frame=pd.DataFrame(
            [
                {
                    "country_text_id": "BFA", "year": 1931,
                    "v2x_regime": None, "v2x_polyarchy": None,
                    "v2x_libdem": None, "v2svindep": 0,
                    "COWcode": 439,
                },
                {
                    "country_text_id": "BFA", "year": 1947,
                    "v2x_regime": None, "v2x_polyarchy": None,
                    "v2x_libdem": None, "v2svindep": 0,
                    "COWcode": 439,
                },
            ]
        ),
    )
    rows = build_chronicle_rows(
        iso3_scope=("BFA",),
        start_year=1939,
        end_year=1939,
        vdem=vdem,
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    assert row["ruler_name"] == "colonial-rule"
    assert FLAG_COLONIAL_RULE_PLACEHOLDER in row["data_quality_flags"].split("|")


# ---------------------------------------------------------------------------
# Attribution drift guard
# ---------------------------------------------------------------------------


def test_wikidata_recent_rulers_attribution_matches_stage2() -> None:
    """The Chronicle attribution text is the same string the
    Stage 2 adapter uses (``"Wikidata (CC0 1.0)."``). Drift
    between the two adapter pipelines' attribution blocks
    would surface here.
    """
    from leaders_db.ingest.wikidata_heads_of_state_government_io import (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION,
    )
    assert (
        WIKIDATA_RECENT_RULERS_ATTRIBUTION
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION
    )


# ---------------------------------------------------------------------------
# REIGN end-year guard
# ---------------------------------------------------------------------------


def test_resolver_does_not_consult_wikidata_before_reign_end_year() -> None:
    """The Wikidata fallback fires only when ``year >
    REIGN_COVERAGE_END_YEAR``. A year inside the REIGN window
    with no REIGN hit falls through to missing (Wikidata is
    not consulted), matching the documented precedence.
    """
    assert REIGN_COVERAGE_END_YEAR == 2021
    wikidata_frame = _frame_from_bindings([
        _binding(
            person_qid="Q1", person_label="Alice",
            office_qid="Q30461", office_label="President",
            country_qid="Q30", country_iso3="USA",
            start="2021-01-20T00:00:00Z",
        ),
    ], year=2020)
    resolver = _empty_resolver_with_wikidata(wikidata_frame)
    result = resolver.resolve("USA", 2020)
    assert result.has_ruler is False
