"""Wikipedia Action API (search + extract) clean-source adapter tests.

Covers the clean ``leaders_db.sources.adapters.wikipedia_search_extract``
slice:

1. Descriptor / factory / register / protocol conformance (the
   ``SourceAdapter`` Protocol).
2. Import boundary: importing
   ``leaders_db.sources.adapters.wikipedia_search_extract`` does NOT
   import ``leaders_db.ingest`` (the package-isolation contract per
   ``docs/architecture/sources.md`` §10.1).
3. Runner end-to-end against the staged fixture JSON cache:
   ``SourceIngestRunner.run(request)`` drives the new registry
   end-to-end against the fixture and produces
   ``NormalizedObservation`` records (one observation per parsed
   ``extracts`` page or ``search`` hit).
4. Cache-policy semantics: ``cache_policy="offline_only"`` /
   ``"prefer_cache"`` is the documented safe default;
   ``cache_policy="refresh"`` / ``"no_cache"`` is NOT supported and
   fails readiness with a structured ``unsupported_cache_policy``
   error before the reader opens the cache.
5. Query-presence readiness: missing / empty ``leaders=`` (the
   clean-slice input contract -- the helper does NOT browse /
   discover) fails readiness with a structured
   ``wikipedia_search_extract_missing_queries`` error before the
   reader opens the cache.
6. Cache-availability readiness: missing or malformed cache files
   fail readiness with a structured ``wikipedia_search_extract_missing_raw``
   error before the reader opens the cache.
7. Request-version readiness: ``request.source_version`` other than
   the canonical ``"Action API"`` fails readiness with a structured
   ``unsupported_version`` error per SRC-REQ-009.
8. Request-scoping warnings: ``years=`` and ``countries=`` are
   unsupported filters and surface a structured ``UNSUPPORTED_FILTER``
   warning (the runner ignores the filters and still emits the
   cached rows; the unified adapter never invents year / country /
   leader values).
9. Cache-key shape: the legacy
   :func:`build_cache_key` shape ``wikipedia_<action>_<query_hash>_<params_hash>.json``
   is preserved (canonical fixture filenames:
   ``wikipedia_extracts_62f100bfa4_default.json``,
   ``wikipedia_search_62f100bfa4_7d0587b5ac.json``,
   ``wikipedia_extracts_6f47c90e93_default.json``).
10. Attribution drift guard: the unified attribution text is
    byte-identical to ``docs/sources/attributions.md`` and to the
    legacy ``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/wikipedia_search_extract_io.py``
    (Always-On Rule #15).
11. Runner does NOT consult legacy ``STAGE2_ADAPTERS`` even when the
    legacy ``wikipedia_search_extract`` slot is monkeypatched to a
    tracker.
12. The legacy ``STAGE2_ADAPTERS["wikipedia_search_extract"]`` slot
    remains callable for backward compatibility (the clean migration
    does not mutate legacy dispatch).
"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from leaders_db.sources import (
    InMemorySourceRegistry,
    SourceAdapter,
    SourceId,
    SourceIngestRequest,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.wikipedia_search_extract import (
    WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR,
    WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT,
    WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATORS,
    WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW,
    WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES,
    WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION,
    WikipediaSearchExtractAdapter,
    build_wikipedia_search_extract_descriptor,
    create_wikipedia_search_extract_adapter,
    register_wikipedia_search_extract,
)
from leaders_db.sources.warnings import UNSUPPORTED_FILTER

# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------


_FIXTURE_CACHE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "wikipedia_search_extract"
    / "cache"
)
_FixtureNames: tuple[str, ...] = (
    "wikipedia_extracts_62f100bfa4_default.json",
    "wikipedia_search_62f100bfa4_7d0587b5ac.json",
    "wikipedia_extracts_6f47c90e93_default.json",
)


def _stage_cache_bundle(
    raw_root: Path,
    *,
    include_biden: bool = True,
    include_amlo: bool = True,
    extra_files: tuple[str, str] = (),
    with_metadata: bool = False,
    source_version: str | None = None,
) -> Path:
    """Stage the canonical Wikipedia Action API fixture cache under ``raw_root``.

    Mirrors the legacy
    ``data/raw/wikipedia_search_extract/cache/<cache_key>.json`` layout.
    The fixture files are real-format Action API responses (the
    ``extracts`` payload has ``query.pages`` dict; the ``search``
    payload has ``query.search`` list). The
    ``wikipedia_extracts_62f100bfa4_default.json`` /
    ``wikipedia_search_62f100bfa4_7d0587b5ac.json`` /
    ``wikipedia_extracts_6f47c90e93_default.json`` filenames match the
    canonical legacy cache-key convention
    (``build_cache_key(action="extracts", query="Joe Biden")`` /
    ``build_cache_key(action="search", query="Joe Biden",
    extra_params={"limit": 10})`` /
    ``build_cache_key(action="extracts", query="Andrés Manuel López
    Obrador")``).
    """
    bundle = raw_root / WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    cache_dir = bundle / WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    if include_biden:
        shutil.copy2(
            _FIXTURE_CACHE_DIR / _FixtureNames[0],
            cache_dir / _FixtureNames[0],
        )
        shutil.copy2(
            _FIXTURE_CACHE_DIR / _FixtureNames[1],
            cache_dir / _FixtureNames[1],
        )
    if include_amlo:
        shutil.copy2(
            _FIXTURE_CACHE_DIR / _FixtureNames[2],
            cache_dir / _FixtureNames[2],
        )
    for src_name, dst_name in extra_files:
        shutil.copy2(
            _FIXTURE_CACHE_DIR / src_name,
            cache_dir / dst_name,
        )
    if with_metadata:
        payload: dict[str, Any] = {
            "source_name": "Wikipedia Action API (search + extract)",
            "source_version": source_version,
            "ingestion_status": "downloaded",
            "license_note": "CC BY-SA 4.0; cite Wikipedia contributors.",
            "source_url": WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
        }
        (bundle / "metadata.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    """Build a default Wikipedia Action API :class:`SourceIngestRequest`."""
    return SourceIngestRequest(
        source_id=SourceId(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    """Register + run the Wikipedia Action API adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_wikipedia_search_extract(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor / factory / register / protocol
# ---------------------------------------------------------------------------


def test_descriptor_factory_register_and_protocol() -> None:
    """Descriptor exposes the canonical Wikipedia Action API static metadata.

    Mirrors the WHO GHO API / Wikidata / FAS test pattern:
    ``create_wikipedia_search_extract_adapter`` returns a
    :class:`WikipediaSearchExtractAdapter` that satisfies the
    runtime-checkable :class:`SourceAdapter` Protocol, the descriptor
    carries the canonical source_id / attribution_key /
    default_version / source_type / coverage / observation family /
    requires_network, and the
    :func:`register_wikipedia_search_extract` helper wires the
    adapter into the :class:`InMemorySourceRegistry`.
    """
    adapter = create_wikipedia_search_extract_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY().descriptor == (
        adapter.descriptor
    )

    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    assert (
        descriptor.attribution_key
        == WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version
        == WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION
    )
    assert descriptor.source_type == "api"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (
        WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    )
    assert descriptor.supported_observation_families == (
        WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES
    )
    assert descriptor.coverage_hint.start_year == (
        WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR
    )
    assert descriptor.coverage_hint.end_year == (
        WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR
    )
    assert descriptor.homepage_url == WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL
    assert descriptor.requires_manual_approval is False

    # Direct factory alias matches the canonical descriptor.
    assert (
        build_wikipedia_search_extract_descriptor().source_id.slug
        == WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    )

    registry = InMemorySourceRegistry()
    returned = register_wikipedia_search_extract(registry)
    assert returned.descriptor == descriptor
    assert (
        registry.get_adapter(SourceId(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY))
        is returned
    )


def test_indicator_and_action_constants_match_legacy_catalog() -> None:
    """The in-scope indicators + action map match the canonical legacy catalog.

    The Wikipedia Action API supports two actions in the prototype
    catalog (``extracts`` and ``search``); the two legacy
    ``variable_name`` values map to those actions.
    """
    assert WIKIPEDIA_SEARCH_EXTRACT_INDICATORS == (
        "wikipedia_extract_lead",
        "wikipedia_search_results",
    )
    assert WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION == {
        "wikipedia_extract_lead": "extracts",
        "wikipedia_search_results": "search",
    }
    assert WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR == {
        "extracts": "wikipedia_extract_lead",
        "search": "wikipedia_search_results",
    }


def test_attribution_text_matches_doc_and_legacy() -> None:
    """Attribution text is byte-identical to ``docs/sources/attributions.md``
    AND to the legacy ``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION``
    constant.

    Drift guard per Always-On Rule #15: the attribution block embedded
    in the unified adapter is the canonical
    ``docs/sources/attributions.md`` wording, byte-for-byte. The
    legacy ``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/wikipedia_search_extract_io.py`` carries
    the same text -- both constants must remain in sync.
    """
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT in doc, (
        "Wikipedia Action API attribution text must be a substring of "
        "docs/sources/attributions.md (Rule #15)."
    )
    from leaders_db.ingest.wikipedia_search_extract_io import (
        WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION as legacy_text,
    )
    assert legacy_text == WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT, (
        "Wikipedia Action API legacy attribution constant must be "
        "byte-identical to the unified "
        "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT constant."
    )


def test_constants_match_documented_values() -> None:
    """Module-level constants are byte-identical to documented values."""
    assert WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY == "wikipedia_search_extract"
    assert WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL == (
        "https://en.wikipedia.org/w/api.php"
    )
    assert WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION == "Action API"
    assert WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS == (
        "Action API (no version)"
    )
    assert WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME == "cache"
    assert WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_CACHE_POLICY == "offline_only"
    assert WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME == (
        "wikipedia_search_extract_query_v1"
    )
    assert WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY == (
        "leader_identity_context"
    )


# ---------------------------------------------------------------------------
# Runner end-to-end
# ---------------------------------------------------------------------------


def test_runner_offline_only_joe_biden_emits_4_observations(
    tmp_path: Path,
) -> None:
    """``cache_policy="offline_only"`` + ``leaders=("Joe Biden",)``
    emits exactly 4 observations: 1 ``extracts`` page + 3 ``search``
    hits, with no readiness warnings.
    """
    _stage_cache_bundle(tmp_path)
    result = _run(
        tmp_path,
        leaders=("Joe Biden",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 4
    indicators = sorted({obs.indicator_code for obs in result.observations})
    assert indicators == sorted(WIKIPEDIA_SEARCH_EXTRACT_INDICATORS)
    assert {obs.observation_family for obs in result.observations} == {
        WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    }
    assert {obs.year for obs in result.observations} == {None}
    assert {obs.country_code for obs in result.observations} == {None}
    assert {obs.leader_id for obs in result.observations} == {None}
    assert {obs.leader_name for obs in result.observations} == {None}
    assert {obs.source_version for obs in result.observations} == {
        WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    }
    # No readiness warnings on the clean-run path.
    assert result.warnings == ()

    # Verify each observation's per-row identity / extension contract.
    extracts_obs = next(
        obs for obs in result.observations
        if obs.indicator_code == "wikipedia_extract_lead"
    )
    assert extracts_obs.value is not None
    assert isinstance(extracts_obs.value, str)
    assert "Biden" in extracts_obs.value
    assert extracts_obs.value_type == "text"
    assert extracts_obs.unit == "text"
    assert extracts_obs.scale == "text"
    assert extracts_obs.extension["action"] == "extracts"
    assert extracts_obs.extension["title"] == "Joe Biden"
    assert extracts_obs.extension["pageid"] == 62544
    assert extracts_obs.extension["query"] == "Joe Biden"
    assert extracts_obs.extension["attribution"] == (
        WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT
    )
    assert extracts_obs.extension["source_row_reference"] == (
        "wikipedia:wikipedia_extract_lead:wikipedia:62544:Joe Biden"
    )
    assert extracts_obs.raw_locator.url == (
        WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL
    )
    assert extracts_obs.raw_locator.api_endpoint == (
        WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL
    )
    assert extracts_obs.transform_locator.transform_name == (
        WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME
    )
    assert extracts_obs.transform_locator.catalog_key == (
        WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    )

    # Verify the search-action contract (3 hits).
    search_obs = [
        obs for obs in result.observations
        if obs.indicator_code == "wikipedia_search_results"
    ]
    assert len(search_obs) == 3
    titles = {obs.extension["title"] for obs in search_obs}
    assert titles == {"Joe Biden", "Biden family", "Presidency of Joe Biden"}
    for obs in search_obs:
        assert obs.extension["action"] == "search"
        assert obs.value is not None
        assert isinstance(obs.value, str)
        # No HTML span tags survive (the legacy parser strips them).
        assert "<span" not in obs.value


def test_runner_two_queries_emits_8_observations(tmp_path: Path) -> None:
    """``leaders=("Joe Biden", "Andrés Manuel López Obrador")``
    emits 8 observations: 2 ``extracts`` pages + 6 ``search`` hits
    (3 hits per query). The readiness gate requires both ``extracts``
    AND ``search`` cache files per query.
    """
    # Stage every fixture, including the AMLO extracts fixture.
    _stage_cache_bundle(tmp_path)
    # Stage a search fixture for AMLO so the readiness gate passes
    # for both queries (the gate validates BOTH actions per query).
    bundle = tmp_path / WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    cache_dir = bundle / WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME
    amlo_search_key = (
        "wikipedia_search_6f47c90e93_7d0587b5ac.json"
    )
    shutil.copy2(
        _FIXTURE_CACHE_DIR / _FixtureNames[1],
        cache_dir / amlo_search_key,
    )

    result = _run(
        tmp_path,
        leaders=("Joe Biden", "Andrés Manuel López Obrador"),
        cache_policy="offline_only",
    )
    # 2 extracts (Joe Biden + AMLO) + 3 search hits per query (6 total).
    assert len(result.observations) == 8
    queries = {obs.extension["query"] for obs in result.observations}
    assert queries == {"Joe Biden", "Andrés Manuel López Obrador"}

    amlo_extracts = next(
        obs for obs in result.observations
        if (
            obs.indicator_code == "wikipedia_extract_lead"
            and obs.extension["query"]
            == "Andrés Manuel López Obrador"
        )
    )
    assert amlo_extracts.extension["pageid"] is not None
    assert amlo_extracts.extension["title"]


# ---------------------------------------------------------------------------
# Readiness failures
# ---------------------------------------------------------------------------


def test_readiness_missing_leaders_fails(tmp_path: Path) -> None:
    """Missing / empty ``leaders=`` fails readiness with
    ``wikipedia_search_extract_missing_queries`` BEFORE ``read_raw``
    is called.
    """
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES
    )


def test_readiness_missing_leaders_with_empty_tuple_fails(
    tmp_path: Path,
) -> None:
    """``leaders=()`` also fails readiness."""
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=()),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES
    )


@pytest.mark.parametrize(
    "leaders",
    [("",), ("   ",), ("", "   "), ("Joe Biden", "   ")],
)
def test_readiness_blank_leaders_fail_as_missing_queries(
    tmp_path: Path,
    leaders: tuple[str, ...],
) -> None:
    """Blank query strings fail with the structured missing-query code."""
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=leaders),
    )

    assert readiness.ready is False
    assert readiness.errors[0].code == (
        WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES
    )


def test_readiness_rejects_refresh_and_no_cache_policies(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` / ``"no_cache"`` is NOT
    supported by the unified Wikipedia Action API adapter in this
    slice -- readiness surfaces a structured
    ``wikipedia_search_extract_unsupported_cache_policy`` error
    BEFORE ``read_raw`` is called.
    """
    _stage_cache_bundle(tmp_path)
    for policy in ("refresh", "no_cache"):
        readiness = create_wikipedia_search_extract_adapter().check_ready(
            _request(tmp_path, leaders=("Joe Biden",), cache_policy=policy),
        )
        assert readiness.ready is False
        assert readiness.errors[0].code == (
            WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY
        )


def test_readiness_missing_cache_file_fails(tmp_path: Path) -> None:
    """A requested (query, action) cache file missing on disk
    fails readiness BEFORE ``read_raw`` is called.
    """
    # Stage only the Joe Biden extracts fixture; do NOT stage the
    # search fixture.
    bundle = _stage_cache_bundle(tmp_path, include_amlo=False)
    cache_dir = bundle / WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME
    (cache_dir / _FixtureNames[1]).unlink()

    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is False
    assert "missing_raw" in readiness.errors[0].code


def test_readiness_missing_cache_dir_fails(tmp_path: Path) -> None:
    """Missing cache directory is a missing-raw readiness failure."""
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW


def test_readiness_malformed_cache_fails(tmp_path: Path) -> None:
    """A malformed cache file (missing ``query.pages`` for
    ``extracts``) fails readiness with a structured
    ``wikipedia_search_extract_missing_raw`` error BEFORE
    ``read_raw`` is called.
    """
    bundle = _stage_cache_bundle(tmp_path, include_amlo=False)
    cache_dir = bundle / WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _FixtureNames[0]).unlink()
    (cache_dir / _FixtureNames[1]).unlink()
    # Stage a malformed extracts cache (missing query.pages).
    (cache_dir / _FixtureNames[0]).write_text(
        json.dumps({"batchcomplete": ""}),
        encoding="utf-8",
    )

    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is False
    assert "missing_raw" in readiness.errors[0].code


def test_readiness_unsupported_request_version_fails(
    tmp_path: Path,
) -> None:
    """``request.source_version`` other than the canonical
    ``"Action API"`` fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009.
    """
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(
            tmp_path,
            leaders=("Joe Biden",),
            source_version="some-other-version",
        ),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION
    )


def test_readiness_accepts_legacy_metadata_alias(tmp_path: Path) -> None:
    """A staged ``metadata.json`` carrying the legacy alias
    ``version="Action API (no version)"`` passes readiness.
    """
    _stage_cache_bundle(
        tmp_path, with_metadata=True,
        source_version=WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS,
    )
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is True


def test_readiness_accepts_canonical_metadata_version(
    tmp_path: Path,
) -> None:
    """A staged ``metadata.json`` carrying the canonical
    ``source_version="Action API"`` passes readiness.
    """
    _stage_cache_bundle(
        tmp_path, with_metadata=True,
        source_version=WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    )
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is True


def test_readiness_rejects_invalid_metadata_version(
    tmp_path: Path,
) -> None:
    """A staged ``metadata.json`` carrying an unsupported
    ``version`` fails readiness with the
    ``wikipedia_search_extract_metadata_version_mismatch`` error.
    """
    _stage_cache_bundle(
        tmp_path, with_metadata=True,
        source_version="some-unsupported-version",
    )
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        "wikipedia_search_extract_metadata_version_mismatch"
    )


def test_readiness_unsupported_metadata_version_payload(
    tmp_path: Path,
) -> None:
    """A staged ``metadata.json`` carrying a non-string / empty
    ``version`` fails readiness.
    """
    _stage_cache_bundle(tmp_path, with_metadata=False)
    bundle = tmp_path / WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    (bundle / "metadata.json").write_text(
        json.dumps({"version": ""}), encoding="utf-8",
    )
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",)),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        "wikipedia_search_extract_metadata_version_mismatch"
    )


# ---------------------------------------------------------------------------
# Request-scoping warnings
# ---------------------------------------------------------------------------


def test_readiness_years_filter_warns_and_is_ignored(
    tmp_path: Path,
) -> None:
    """``years=`` is unsupported and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning; the readiness envelope still
    passes for a well-formed bundle.
    """
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(tmp_path, leaders=("Joe Biden",), years=(2023,)),
    )
    assert readiness.ready is True
    codes = [w.code for w in readiness.warnings]
    assert UNSUPPORTED_FILTER in codes
    year_warnings = [
        w for w in readiness.warnings if w.code == UNSUPPORTED_FILTER
    ]
    assert any(
        "year" in w.message.lower() for w in year_warnings
    )


def test_readiness_countries_filter_warns_and_is_ignored(
    tmp_path: Path,
) -> None:
    """``countries=`` is unsupported and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning; the readiness envelope still
    passes for a well-formed bundle.
    """
    _stage_cache_bundle(tmp_path)
    readiness = create_wikipedia_search_extract_adapter().check_ready(
        _request(
            tmp_path, leaders=("Joe Biden",), countries=("USA",),
        ),
    )
    assert readiness.ready is True
    codes = [w.code for w in readiness.warnings]
    assert UNSUPPORTED_FILTER in codes
    country_warnings = [
        w for w in readiness.warnings if w.code == UNSUPPORTED_FILTER
    ]
    assert any(
        "country" in w.message.lower() for w in country_warnings
    )


# ---------------------------------------------------------------------------
# Cache-key shape
# ---------------------------------------------------------------------------


def test_cache_key_matches_legacy_convention() -> None:
    """The lazy ``build_cache_key`` reuses the legacy cache-key
    convention ``wikipedia_<action>_<query_hash>_<params_hash>``.

    The canonical fixture filenames are
    ``wikipedia_extracts_62f100bfa4_default.json`` (Joe Biden,
    extracts), ``wikipedia_search_62f100bfa4_7d0587b5ac.json``
    (Joe Biden, search), and
    ``wikipedia_extracts_6f47c90e93_default.json`` (AMLO, extracts).
    """
    from leaders_db.sources.adapters.wikipedia_search_extract._paths import (
        build_cache_key,
    )

    biden_extracts = build_cache_key(action="extracts", query="Joe Biden")
    assert biden_extracts == "wikipedia_extracts_62f100bfa4_default"

    biden_search = build_cache_key(
        action="search",
        query="Joe Biden",
        extra_params={"limit": 10},
    )
    assert biden_search == "wikipedia_search_62f100bfa4_7d0587b5ac"

    amlo_extracts = build_cache_key(
        action="extracts",
        query="Andrés Manuel López Obrador",
    )
    assert amlo_extracts == "wikipedia_extracts_6f47c90e93_default"


# ---------------------------------------------------------------------------
# Legacy-dispatch contract
# ---------------------------------------------------------------------------


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unified runner does NOT consult the legacy
    ``STAGE2_ADAPTERS`` table (mirrors the WHO GHO API / Wikidata /
    FAS contract).
    """
    _stage_cache_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(
        legacy_ingest,
        "STAGE2_ADAPTERS",
        {WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY: None},
    )
    result = _run(
        tmp_path, leaders=("Joe Biden",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 4


def test_runner_does_not_invoke_http_layer(tmp_path: Path) -> None:
    """The unified runner does NOT call the legacy ``fetch_wikipedia_action_api_payload``.

    Defense in depth: monkeypatch the legacy HTTP layer to raise an
    exception; the runner must NOT invoke it in this slice.
    """
    _stage_cache_bundle(tmp_path)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "Wikipedia Action API HTTP layer must NOT be invoked by "
            "the unified reader in this slice"
        )

    import leaders_db.ingest.wikipedia_search_extract_http as legacy_http

    monkeypatch_http = pytest.MonkeyPatch()
    monkeypatch_http.setattr(
        legacy_http, "fetch_wikipedia_action_api_payload", _boom,
    )
    try:
        result = _run(
            tmp_path, leaders=("Joe Biden",),
            cache_policy="offline_only",
        )
        assert len(result.observations) == 4
    finally:
        monkeypatch_http.undo()


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------


def test_importing_wikipedia_search_extract_adapter_does_not_import_legacy_ingest() -> None:
    """Importing ``leaders_db.sources.adapters.wikipedia_search_extract``
    MUST NOT import ``leaders_db.ingest`` (the package-isolation
    contract per ``docs/architecture/sources.md`` §10.1).

    The test purges every ``leaders_db.sources`` /
    ``leaders_db.ingest`` entry from ``sys.modules``, imports the
    new adapter, and asserts that no ``leaders_db.ingest`` module
    leaked into ``sys.modules``.
    """
    for name in list(sys.modules):
        if (
            name == "leaders_db.sources"
            or name.startswith("leaders_db.sources.")
        ):
            del sys.modules[name]
        if (
            name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        ):
            del sys.modules[name]
    importlib.import_module(
        "leaders_db.sources.adapters.wikipedia_search_extract"
    )
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest"
        or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing leaders_db.sources.adapters.wikipedia_search_extract "
        f"must not import leaders_db.ingest (leaked modules: {leaked})"
    )


def test_legacy_ingest_wikipedia_search_extract_slot_unchanged() -> None:
    """The legacy ``STAGE2_ADAPTERS['wikipedia_search_extract']``
    slot still resolves to the legacy orchestrator function -- the
    unified migration does not mutate legacy dispatch.
    """
    import leaders_db.ingest as legacy_ingest

    dispatch = legacy_ingest.STAGE2_ADAPTERS
    assert WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY in dispatch
    assert callable(dispatch[WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY])


# Reference static-utility symbols (defensive: keep them live so the
# static analyzer does not flag them as unused imports).
_ = (
    WikipediaSearchExtractAdapter,
)
