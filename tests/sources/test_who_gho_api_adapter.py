"""WHO Global Health Observatory (GHO) API clean-source adapter tests."""

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
from leaders_db.sources.adapters.who_gho_api import (
    WHO_GHO_API_ADAPTER_FACTORY,
    WHO_GHO_API_ATTRIBUTION_TEXT,
    WHO_GHO_API_CACHE_DIR_NAME,
    WHO_GHO_API_COVERAGE_END_YEAR,
    WHO_GHO_API_COVERAGE_START_YEAR,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_HOMEPAGE_URL,
    WHO_GHO_API_INDICATOR_CODES,
    WHO_GHO_API_METADATA_NAME,
    WHO_GHO_API_OBSERVATION_FAMILY,
    WHO_GHO_API_SOURCE_KEY,
    WHO_GHO_API_SUPPORTED_FAMILIES,
    WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
    WhoGhoApiAdapter,
    build_who_gho_api_descriptor,
    create_who_gho_api_adapter,
    register_who_gho_api,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
)

# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------


_FIXTURE_CACHE_ROOT = Path("tests/fixtures/who_gho_api/cache")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_cache: bool = True,
    with_primary_version: bool = False,
    missing_indicator: str | None = None,
    version: str | None = WHO_GHO_API_DEFAULT_VERSION,
    source_key: str | None = WHO_GHO_API_SOURCE_KEY,
) -> Path:
    """Stage the canonical WHO GHO API bundle shape under ``raw_root``.

    The bundle mirrors the existing
    ``data/raw/who_gho_api/metadata.json`` legacy shape
    (``source_key`` / ``version`` / ``source_url`` / ``sha256:
    null`` / ``ingestion_status``) -- the clean adapter's
    readiness gate accepts BOTH the canonical primary shape
    (``source_version``) AND the legacy shape (``version``).
    The ``with_primary_version`` flag flips the test bundle to
    the canonical primary shape.
    """
    bundle = raw_root / WHO_GHO_API_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    cache_root = bundle / WHO_GHO_API_CACHE_DIR_NAME
    if with_cache:
        if cache_root.exists():
            shutil.rmtree(cache_root)
        for year_dir in sorted(_FIXTURE_CACHE_ROOT.iterdir()):
            if not year_dir.is_dir():
                continue
            target_year = cache_root / year_dir.name
            target_year.mkdir(parents=True, exist_ok=True)
            for cache_file in sorted(year_dir.iterdir()):
                if (
                    missing_indicator is not None
                    and cache_file.name == f"{missing_indicator}.json"
                ):
                    continue
                shutil.copy2(cache_file, target_year / cache_file.name)
    if with_metadata:
        payload: dict[str, Any] = {
            "source_key": source_key or WHO_GHO_API_SOURCE_KEY,
            "source_name": "WHO Global Health Observatory (OData API)",
            "source_short_name": "WHO GHO",
            "download_date": "2026-06-18",
            "source_url": WHO_GHO_API_HOMEPAGE_URL,
            "license": "open; cite WHO Global Health Observatory",
            "file_format": (
                "OData 4.0 JSON API (no download; one JSON file per "
                "(year, indicator_code) under data/raw/who_gho_api/cache/)"
            ),
            "file_encoding": "utf-8",
            "file_size_bytes": None,
            "sha256": None,
            "ingestion_status": "available",
            "notes": "test bundle",
        }
        if with_primary_version:
            payload["source_version"] = version
        else:
            payload["version"] = version
        (bundle / WHO_GHO_API_METADATA_NAME).write_text(
            json.dumps(payload), encoding="utf-8",
        )
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    """Build a default WHO GHO API :class:`SourceIngestRequest`."""
    return SourceIngestRequest(
        source_id=SourceId(WHO_GHO_API_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    """Register + run the WHO GHO API adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_who_gho_api(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor / factory / register / protocol
# ---------------------------------------------------------------------------


def test_descriptor_factory_register_and_protocol() -> None:
    """Descriptor exposes the canonical WHO GHO API static metadata.

    Mirrors the cirights / undp_hdi / WDI test pattern:
    ``create_who_gho_api_adapter`` returns a :class:`WhoGhoApiAdapter`
    that satisfies the runtime-checkable :class:`SourceAdapter`
    Protocol, the descriptor carries the canonical source_id /
    attribution_key / default_version / source_type / coverage /
    observation family / requires_network, and the
    :func:`register_who_gho_api` helper wires the adapter into
    the :class:`InMemorySourceRegistry`.
    """
    adapter = create_who_gho_api_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert WHO_GHO_API_ADAPTER_FACTORY().descriptor == adapter.descriptor

    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == WHO_GHO_API_SOURCE_KEY
    assert descriptor.attribution_key == WHO_GHO_API_SOURCE_KEY
    assert descriptor.default_version == WHO_GHO_API_DEFAULT_VERSION
    assert descriptor.source_type == "api"
    assert descriptor.requires_network is True
    assert descriptor.supported_observation_families == (
        WHO_GHO_API_OBSERVATION_FAMILY,
    )
    assert descriptor.supported_observation_families == WHO_GHO_API_SUPPORTED_FAMILIES
    assert descriptor.coverage_hint.start_year == WHO_GHO_API_COVERAGE_START_YEAR
    assert descriptor.coverage_hint.end_year == WHO_GHO_API_COVERAGE_END_YEAR
    assert descriptor.homepage_url == WHO_GHO_API_HOMEPAGE_URL

    # Direct factory alias matches the canonical descriptor.
    assert (
        build_who_gho_api_descriptor().source_id.slug
        == WHO_GHO_API_SOURCE_KEY
    )

    registry = InMemorySourceRegistry()
    returned = register_who_gho_api(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(WHO_GHO_API_SOURCE_KEY)) is returned


def test_indicator_constants_match_legacy_catalog() -> None:
    """The in-scope indicator codes match the canonical 5-indicator catalog."""
    assert WHO_GHO_API_INDICATOR_CODES == (
        "WHOSIS_000001",
        "MDG_0000000007",
        "WHS4_100",
        "WHS4_117",
        "WHS4_543",
    )


def test_attribution_text_matches_doc() -> None:
    """Attribution text is byte-identical to ``docs/sources/attributions.md``.

    Drift guard per Always-On Rule #15: the attribution block
    embedded in the unified adapter is the canonical
    ``docs/sources/attributions.md`` wording, byte-for-byte.
    """
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert WHO_GHO_API_ATTRIBUTION_TEXT in doc, (
        "WHO GHO API attribution text must be a substring of "
        "docs/sources/attributions.md (Rule #15)."
    )


# ---------------------------------------------------------------------------
# Runner end-to-end
# ---------------------------------------------------------------------------


def test_runner_offline_only_single_year_emits_one_observation_per_indicator(
    tmp_path: Path,
) -> None:
    """``cache_policy="offline_only"`` + ``years=(2021,)`` +
    ``countries=("MEX",)`` emits exactly the 4 MEX 2021 observations
    present in the staged fixture cache.

    The staged fixture has 4 MEX 2021 records (life expectancy +
    3 immunization indicators); under-5 mortality for MEX in 2021
    is absent from the fixture, so the transform must skip that
    cell -- the runner must NOT invent the value.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("MEX",),
        cache_policy="offline_only",
    )
    assert {obs.year for obs in result.observations} == {2021}
    assert {obs.country_code for obs in result.observations} == {"MEX"}
    assert {obs.leader_id for obs in result.observations} == {None}
    assert {obs.leader_name for obs in result.observations} == {None}
    assert {obs.country_name for obs in result.observations} == {None}

    indicators = sorted({obs.indicator_code for obs in result.observations})
    assert indicators == [
        "who_gho_bcg_immunization",
        "who_gho_dtp3_immunization",
        "who_gho_hepb3_immunization",
        "who_gho_life_expectancy",
    ]

    # Spot check one observation: the life-expectancy cell is the
    # only indicator with a verbatim `Value` string with bounds
    # (`"70.8 [70.7-71.1]"`) -- the transform layer must preserve
    # that audit-trail string + the canonical attribution block.
    life = next(
        obs for obs in result.observations
        if obs.indicator_code == "who_gho_life_expectancy"
    )
    assert life.value == pytest.approx(70.83258685)
    assert life.value_type == "numeric"
    assert life.observation_family == WHO_GHO_API_OBSERVATION_FAMILY
    assert life.source_version == WHO_GHO_API_DEFAULT_VERSION
    assert life.raw_locator.path.endswith("cache/2021/WHOSIS_000001.json")
    assert life.raw_locator.column_name == "WHOSIS_000001"
    assert life.raw_locator.row_number is None
    assert life.raw_locator.asset_id == (
        f"{WHO_GHO_API_SOURCE_KEY}:cache:2021:WHOSIS_000001"
    )
    assert life.extension["source_row_reference"] == (
        f"{WHO_GHO_API_SOURCE_KEY}:WHOSIS_000001:MEX"
    )
    assert life.extension["raw_value"] == "70.8 [70.7-71.1]"
    assert life.extension["normalized_value"] == pytest.approx(70.83258685)
    assert life.extension["higher_is_better"] is True
    assert life.extension["raw_scale"] == "years"
    assert life.extension["normalized_scale_target"] == "0-10"
    assert life.extension["who_gho_api_raw_column"] == "WHOSIS_000001"
    assert life.extension["dim1_filter"] == "SEX_BTSX"
    assert life.extension["spatial_dim_type"] == "COUNTRY"
    assert life.extension["year_window"] == [2021, 2021]
    assert life.extension["attribution"] == WHO_GHO_API_ATTRIBUTION_TEXT


def test_runner_years_none_reads_all_cached_years(tmp_path: Path) -> None:
    """``years=None`` reads all complete cached fixture years (2019 + 2021)."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=None, cache_policy="offline_only")
    years = sorted({obs.year for obs in result.observations})
    assert years == [2019, 2021]
    countries = sorted({obs.country_code for obs in result.observations})
    assert countries == ["IND", "MEX", "NGA", "SWE", "USA"]
    # ``obs.indicator_code`` carries the Stage 2 catalog
    # ``variable_name`` (e.g. ``who_gho_life_expectancy``) --
    # NOT the raw WHO GHO API ``IndicatorCode``. The raw code is
    # preserved on the audit-trail ``extension.who_gho_api_raw_column``.
    indicators = sorted({obs.indicator_code for obs in result.observations})
    expected_indicators = sorted({
        "who_gho_life_expectancy",
        "who_gho_under5_mortality",
        "who_gho_dtp3_immunization",
        "who_gho_hepb3_immunization",
        "who_gho_bcg_immunization",
    })
    assert indicators == expected_indicators

    # Every observation has at most one row per (iso3, year,
    # indicator) triple -- the legacy pivot uses
    # ``aggfunc="first"`` and the unified transform preserves
    # the same first-match semantics so multiple
    # disaggregation records per (iso3, year, indicator)
    # collapse into one observation.
    triples = {
        (obs.country_code, obs.year, obs.indicator_code)
        for obs in result.observations
    }
    assert len(triples) == len(result.observations)


def test_runner_under5_mortality_first_match_wins(tmp_path: Path) -> None:
    """The first disaggregation record wins per
    ``(iso3, year, indicator)`` triple (matches legacy ``aggfunc="first"``).

    The staged NGA 2019 ``MDG_0000000007`` fixture has TWO
    COUNTRY records (WEALTHQUINTILE_WQ5 first, then
    WEALTHQUINTILE_TOTL). The legacy pivot uses
    ``aggfunc="first"`` so the unified transform must pick the
    first record's value AND raw_value, not overwrite with the
    last record (which would silently flip the audit-trail
    string to the wrong disaggregation).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2019,),
        countries=("NGA",),
        cache_policy="offline_only",
    )
    nga_u5 = [
        obs for obs in result.observations
        if obs.country_code == "NGA"
        and obs.indicator_code == "who_gho_under5_mortality"
    ]
    assert len(nga_u5) == 1
    obs = nga_u5[0]
    # First record's NumericValue is 59.3178952; the second
    # record's NumericValue is 117.471002949. The legacy
    # ``aggfunc="first"`` semantics must keep the FIRST value
    # so the audit-trail ``raw_value`` matches the numeric
    # value (both come from the same record).
    assert obs.value == pytest.approx(59.3178952)
    assert obs.extension["raw_value"] == "59.3 [45.7-78.2]"
    assert obs.extension["normalized_value"] == pytest.approx(59.3178952)


def test_runner_unknown_country_filter_emits_no_observations(
    tmp_path: Path,
) -> None:
    """``countries=("XYZ",)`` (no ISO3 match in the cache) emits zero rows."""
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("XYZ",),
        cache_policy="offline_only",
    )
    assert result.observations == ()


def test_runner_leader_filter_warns_and_is_ignored(tmp_path: Path) -> None:
    """``leaders=`` is unsupported for a country-year health source and is ignored."""
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("MEX",),
        leaders=("Some Leader",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 4
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


def test_runner_out_of_cache_year_fails_readiness(tmp_path: Path) -> None:
    """Request for a year without cache files fails readiness with
    ``missing_raw`` BEFORE ``read_raw`` / ``transform`` are
    called -- the runner short-circuits with ``RuntimeError``.

    Mirrors the WDI cache-policy contract: a supported cache
    policy + explicit-year request with a missing year directory
    is a readiness blocker, NOT a "silent zero observations"
    outcome. The orchestrator refuses to dispatch the read path
    so a developer cannot accidentally emit a wrong-year
    proxy row.
    """
    _stage_bundle(tmp_path)
    registry = InMemorySourceRegistry()
    register_who_gho_api(registry)
    runner = SourceIngestRunner(registry)
    with pytest.raises(RuntimeError):
        runner.run(
            _request(
                tmp_path,
                years=(2022,),
                countries=("MEX",),
                cache_policy="offline_only",
            ),
        )


# ---------------------------------------------------------------------------
# Readiness failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"missing_indicator": "WHOSIS_000001"}, MISSING_RAW),
        ({"with_cache": False}, NETWORK_CACHE_UNAVAILABLE),
    ],
)
def test_readiness_failures(
    tmp_path: Path, kwargs: dict[str, Any], code: str,
) -> None:
    """Each staged failure shape fires the canonical readiness error.

    The ``missing_indicator`` case drives an explicit
    ``years=(2021,)`` request so the per-year, per-indicator
    completeness check fires for the missing catalog file.
    """
    _stage_bundle(tmp_path, **kwargs)
    request_kwargs: dict[str, Any] = {}
    if kwargs.get("missing_indicator") is not None:
        request_kwargs["years"] = (2021,)
    readiness = create_who_gho_api_adapter().check_ready(
        _request(tmp_path, **request_kwargs),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_readiness_metadata_version_mismatch(tmp_path: Path) -> None:
    """Staged metadata with a non-canonical ``version`` fails readiness."""
    _stage_bundle(tmp_path, version="not-canonical")
    readiness = create_who_gho_api_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == "who_gho_api_metadata_version_mismatch"


def test_readiness_accepts_primary_source_version_field(tmp_path: Path) -> None:
    """Canonical primary ``source_version`` shape is accepted by readiness."""
    _stage_bundle(tmp_path, with_primary_version=True)
    readiness = create_who_gho_api_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_rejects_refresh_and_no_cache_policies(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` / ``"no_cache"`` is NOT supported by
    the unified WHO GHO API adapter in this slice -- readiness
    surfaces a structured ``unsupported_cache_policy`` error.
    """
    _stage_bundle(tmp_path)
    for policy in ("refresh", "no_cache"):
        readiness = create_who_gho_api_adapter().check_ready(
            _request(tmp_path, cache_policy=policy),
        )
        assert readiness.ready is False
        assert (
            readiness.errors[0].code
            == WHO_GHO_API_UNSUPPORTED_CACHE_POLICY
        )


def test_readiness_explicit_year_missing_indicator_cache_fails(
    tmp_path: Path,
) -> None:
    """Explicit-year request with one missing catalog indicator
    cache file fails readiness with ``missing_raw``.
    """
    _stage_bundle(tmp_path, missing_indicator="WHOSIS_000001")
    readiness = create_who_gho_api_adapter().check_ready(
        _request(tmp_path, years=(2021,)),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW


def test_readiness_request_version_mismatch_fails(tmp_path: Path) -> None:
    """``request.source_version`` other than the canonical default
    fails readiness with a structured ``unsupported_version``
    error per SRC-REQ-009.
    """
    _stage_bundle(tmp_path)
    readiness = create_who_gho_api_adapter().check_ready(
        _request(tmp_path, source_version="other-version"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == "unsupported_version"


# ---------------------------------------------------------------------------
# No-network contract (monkeypatched sentinels)
# ---------------------------------------------------------------------------


def _install_http_sentinels(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[str]]:
    """Patch the legacy WHO GHO API HTTP layer + ``requests.get`` to
    fail if invoked by the unified read path.

    Returns ``(fetch_calls, requests_get_calls)`` -- the lists
    record any invocation attempt so the test can prove the
    sentinels were never reached. The patches are scoped to the
    test via ``monkeypatch`` so they auto-revert at teardown.
    """
    fetch_calls: list[str] = []
    requests_get_calls: list[str] = []

    def _fetch_sentinel(*args: Any, **kwargs: Any) -> Any:
        fetch_calls.append(f"fetch_who_gho_api_payload({args!r}, {kwargs!r})")
        raise AssertionError(
            "fetch_who_gho_api_payload must NOT be called when "
            "cache_policy is 'offline_only' / 'prefer_cache' and "
            "readiness passed; the unified WHO GHO API adapter is "
            "offline / cache-only in this slice."
        )

    def _requests_get_sentinel(*args: Any, **kwargs: Any) -> Any:
        requests_get_calls.append(f"requests.get({args!r}, {kwargs!r})")
        raise AssertionError(
            "requests.get must NOT be called by the unified WHO GHO "
            "API adapter under supported cache policies; the "
            "cache-only read path never falls through to HTTP."
        )

    try:
        from leaders_db.ingest import who_gho_api_http as _http

        monkeypatch.setattr(
            _http, "fetch_who_gho_api_payload", _fetch_sentinel,
        )
    except ImportError:
        pass

    try:
        import requests as _requests

        monkeypatch.setattr(_requests, "get", _requests_get_sentinel)
    except ImportError:
        pass

    return fetch_calls, requests_get_calls


def test_offline_only_runner_does_not_invoke_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache-only run from the staged fixture cache never hits the
    network.

    The HTTP sentinels (legacy
    :func:`fetch_who_gho_api_payload` + :func:`requests.get`) are
    installed before the runner executes. If the unified adapter
    falls through to HTTP for any reason, either sentinel raises
    ``AssertionError`` and the test fails. The post-condition
    asserts the sentinel lists are empty so a regression to
    HTTP is caught immediately.
    """
    _stage_bundle(tmp_path)
    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("MEX",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 4
    assert fetch_calls == [], (
        "fetch_who_gho_api_payload was invoked under "
        f"cache_policy='offline_only'; calls={fetch_calls}"
    )
    assert requests_get_calls == [], (
        "requests.get was invoked under cache_policy='offline_only'; "
        f"calls={requests_get_calls}"
    )


def test_prefer_cache_runner_does_not_invoke_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_policy="prefer_cache"`` (the default) also never
    invokes the network in this slice -- the cache is the only
    read path.
    """
    _stage_bundle(tmp_path)
    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("MEX",),
        cache_policy="prefer_cache",
    )
    assert len(result.observations) == 4
    assert fetch_calls == []
    assert requests_get_calls == []


# ---------------------------------------------------------------------------
# Legacy-dispatch contract
# ---------------------------------------------------------------------------


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unified runner does NOT consult the legacy
    ``STAGE2_ADAPTERS`` table (mirrors the WDI / cirights / undp_hdi
    contract).
    """
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(
        legacy_ingest, "STAGE2_ADAPTERS",
        {WHO_GHO_API_SOURCE_KEY: None},
    )
    result = _run(
        tmp_path,
        years=(2021,),
        countries=("MEX",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 4


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------


def test_importing_who_gho_api_adapter_does_not_import_legacy_ingest() -> None:
    """Importing ``leaders_db.sources.adapters.who_gho_api`` MUST
    NOT import ``leaders_db.ingest`` (the package-isolation
    contract per ``docs/architecture/sources.md`` §10.1).

    The test purges every ``leaders_db.sources`` /
    ``leaders_db.ingest`` entry from ``sys.modules``, imports
    the new adapter, and asserts that no
    ``leaders_db.ingest`` module leaked into ``sys.modules``.
    """
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]
    importlib.import_module("leaders_db.sources.adapters.who_gho_api")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing leaders_db.sources.adapters.who_gho_api must not "
        f"import leaders_db.ingest (leaked modules: {leaked})"
    )


def test_legacy_ingest_who_gho_api_slot_unchanged() -> None:
    """The legacy ``STAGE2_ADAPTERS['who_gho_api']`` slot still
    resolves to the legacy orchestrator function -- the unified
    migration does not mutate legacy dispatch.
    """
    import leaders_db.ingest as legacy_ingest

    dispatch = legacy_ingest.STAGE2_ADAPTERS
    assert WHO_GHO_API_SOURCE_KEY in dispatch
    assert callable(dispatch[WHO_GHO_API_SOURCE_KEY])


__all__ = [
    "test_attribution_text_matches_doc",
    "test_descriptor_factory_register_and_protocol",
    "test_importing_who_gho_api_adapter_does_not_import_legacy_ingest",
    "test_indicator_constants_match_legacy_catalog",
    "test_legacy_ingest_who_gho_api_slot_unchanged",
    "test_offline_only_runner_does_not_invoke_network",
    "test_prefer_cache_runner_does_not_invoke_network",
    "test_readiness_accepts_primary_source_version_field",
    "test_readiness_explicit_year_missing_indicator_cache_fails",
    "test_readiness_failures",
    "test_readiness_metadata_version_mismatch",
    "test_readiness_rejects_refresh_and_no_cache_policies",
    "test_readiness_request_version_mismatch_fails",
    "test_runner_does_not_dispatch_through_legacy_stage2_adapters",
    "test_runner_leader_filter_warns_and_is_ignored",
    "test_runner_offline_only_single_year_emits_one_observation_per_indicator",
    "test_runner_out_of_cache_year_fails_readiness",
    "test_runner_under5_mortality_first_match_wins",
    "test_runner_unknown_country_filter_emits_no_observations",
    "test_runner_years_none_reads_all_cached_years",
]


# ---------------------------------------------------------------------------
# Reference static-utility symbols (defensive: keep them live so the
# static analyzer does not flag them as unused imports).
# ---------------------------------------------------------------------------

_ = (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
    WhoGhoApiAdapter,
)
