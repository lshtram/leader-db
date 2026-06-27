"""Wikidata WikiProject heads-of-state-and-government clean-source adapter tests.

Covers the clean ``leaders_db.sources.adapters.wikidata_heads_of_state_government``
slice:

1. Descriptor / factory / register / protocol conformance (the
   ``SourceAdapter`` Protocol).
2. Import boundary: importing
   ``leaders_db.sources.adapters.wikidata_heads_of_state_government``
   does NOT import ``leaders_db.ingest`` (the package-isolation
   contract per ``docs/architecture/sources.md`` §10.1).
3. Runner end-to-end against the staged fixture cache:
   ``SourceIngestRunner.run(request)`` drives the new registry
   end-to-end against the fixture and produces
   ``NormalizedObservation`` records (one per SPARQL binding per
   matching catalog spec).
4. Country filter: only Wikidata QID values match (the unified
   adapter never invents ISO3 codes); non-QID inputs surface a
   structured ``wikidata_non_qid_country_filter`` warning.
5. Year filter: ``years=(2023,)`` emits one observation per
   matching binding with ``year=2023`` and the original
   ``start_date`` / ``end_date`` qualifiers preserved on the
   audit-trail extension payload; ``years=None`` reads the
   legacy current-holders cache.
6. Leader filter: ``leaders=`` is unsupported and surfaces a
   structured ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
7. Readiness failures: missing metadata, malformed cache,
   missing cache file, ``source_version`` mismatch.
8. Cache policy: ``cache_policy="refresh"`` / ``"no_cache"``
   is NOT supported and fails readiness with a structured
   ``unsupported_cache_policy`` error BEFORE the reader opens
   the cache.
9. Runner does NOT consult legacy ``STAGE2_ADAPTERS`` even when
   the legacy ``wikidata_heads_of_state_government`` slot is
   monkeypatched to a tracker.
10. The legacy ``STAGE2_ADAPTERS["wikidata_heads_of_state_government"]``
    slot remains callable for backward compatibility (the clean
    migration does not mutate legacy dispatch).
11. Attribution drift guard: the canonical
    ``"Wikidata (CC0 1.0)."`` text is byte-identical to
    ``docs/sources/attributions.md`` AND to the legacy
    ``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION`` constant
    in ``src/leaders_db/ingest/wikidata_heads_of_state_government_io.py``
    (Rule #15).
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
from leaders_db.sources.adapters.wikidata_heads_of_state_government import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_INDICATORS,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR,
    WikidataHeadsOfStateGovernmentAdapter,
    build_wikidata_heads_of_state_government_descriptor,
    create_wikidata_heads_of_state_government_adapter,
    register_wikidata_heads_of_state_government,
)
from leaders_db.sources.adapters.wikidata_heads_of_state_government._readiness import (
    cache_file as readiness_cache_file,
)
from leaders_db.sources.adapters.wikidata_heads_of_state_government._readiness import (
    cache_root,
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


_FIXTURE_CACHE_DIR = (
    Path("tests/fixtures/wikidata_heads_of_state_government/cache")
)
_YEAR_2023_FIXTURE_NAME = (
    "wd_ALL_2023_446f28aaf1_6a945a3130.json"
)
_CURRENT_ALL_FIXTURE_NAME = "wd_ALL_current_all_6a945a3130.json"


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_cache: bool = True,
    version: str | None = WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    use_primary_source_version_field: bool = False,
    primary_metadata_shape: bool = False,
) -> Path:
    """Stage the canonical Wikidata HoS/HoG bundle shape under ``raw_root``.

    Mirrors the existing
    ``data/raw/wikidata_heads_of_state_government/metadata.json``
    legacy shape (``source_key`` / ``version`` / ``source_url`` /
    ``license`` / ``ingestion_status`` / ``notes``); the readiness
    gate accepts BOTH the canonical primary shape
    (``source_version``) AND the legacy shape (``version``) so
    the existing staged bundle does not need to be rewritten as
    part of the migration.

    The staged cache mirrors the existing fixture layout under
    ``tests/fixtures/wikidata_heads_of_state_government/cache/``:
    two real-format SPARQL JSON responses (one for the 2023 +
    [Q30, Q96] parameter set; one for the current / all-countries
    parameter set).
    """
    bundle = raw_root / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    cache_root_path = bundle / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    if with_cache:
        if cache_root_path.exists():
            shutil.rmtree(cache_root_path)
        cache_root_path.mkdir(parents=True, exist_ok=True)
        for cache_file in sorted(_FIXTURE_CACHE_DIR.iterdir()):
            if not cache_file.is_file():
                continue
            shutil.copy2(cache_file, cache_root_path / cache_file.name)
    if with_metadata:
        payload: dict[str, Any] = {
            "source_key": WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
            "source_name": (
                "Wikidata WikiProject Heads of state and government"
            ),
            "source_short_name": "Wikidata HoS/HoG",
            "source_url": (
                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL
            ),
            "license": "CC0 1.0 (Public Domain Dedication)",
            "file_format": (
                "Wikidata SPARQL JSON result (no download; one JSON "
                "file per (office_qid, [year], [country_qid_set]) "
                "under data/raw/wikidata_heads_of_state_government/cache/)"
            ),
            "file_encoding": "utf-8",
            "file_size_bytes": None,
            "sha256": None,
            "ingestion_status": "available",
            "notes": (
                "test bundle; runtime-local staged cache under "
                f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME}/"
            ),
        }
        if primary_metadata_shape:
            payload["source_version"] = version
        else:
            payload["version"] = version
        if use_primary_source_version_field:
            # Add the primary key alongside the legacy one -- both
            # must point at the canonical stamp.
            payload["source_version"] = (
                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION
            )
        (bundle / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME).write_text(
            json.dumps(payload), encoding="utf-8",
        )
    return bundle


def _request(
    raw_root: Path,
    **kwargs: Any,
) -> SourceIngestRequest:
    """Build a default Wikidata HoS/HoG :class:`SourceIngestRequest`."""
    return SourceIngestRequest(
        source_id=SourceId(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    """Register + run the Wikidata HoS/HoG adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_wikidata_heads_of_state_government(registry)
    return SourceIngestRunner(registry).run(
        _request(raw_root, **kwargs),
    )


# ---------------------------------------------------------------------------
# Descriptor / factory / register / protocol
# ---------------------------------------------------------------------------


def test_descriptor_factory_register_and_protocol() -> None:
    """Descriptor exposes the canonical Wikidata HoS/HoG static metadata.

    Mirrors the FAS / WHO GHO API / CIRIGHTS / UNDP HDI test
    pattern: ``create_wikidata_heads_of_state_government_adapter``
    returns a :class:`WikidataHeadsOfStateGovernmentAdapter`
    that satisfies the runtime-checkable :class:`SourceAdapter`
    Protocol, the descriptor carries the canonical source_id /
    attribution_key / default_version / source_type / coverage
    / observation family / requires_network, and the
    :func:`register_wikidata_heads_of_state_government` helper
    wires the adapter into the :class:`InMemorySourceRegistry`.
    """
    adapter = create_wikidata_heads_of_state_government_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY().descriptor
        == adapter.descriptor
    )

    descriptor = adapter.descriptor
    assert (
        descriptor.source_id.slug
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )
    assert (
        descriptor.attribution_key
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION
    )
    assert descriptor.source_type == "knowledge_base"
    assert descriptor.requires_network is False
    assert (
        descriptor.supported_observation_families
        == (
            WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
        )
    )
    assert (
        descriptor.supported_observation_families
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES
    )
    assert (
        descriptor.coverage_hint.start_year
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR
    )
    assert (
        descriptor.coverage_hint.end_year
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR
    )
    assert (
        descriptor.coverage_hint.start_year is None
        and descriptor.coverage_hint.end_year is None
    )
    assert (
        descriptor.homepage_url
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL
    )

    # Direct factory alias matches the canonical descriptor.
    assert (
        build_wikidata_heads_of_state_government_descriptor()
        .source_id.slug
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )

    registry = InMemorySourceRegistry()
    returned = register_wikidata_heads_of_state_government(registry)
    assert returned.descriptor == descriptor
    assert (
        registry.get_adapter(
            SourceId(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY)
        )
        is returned
    )


def test_indicator_constants_match_legacy_catalog() -> None:
    """The in-scope indicator codes match the canonical 2-indicator catalog."""
    assert WIKIDATA_HEADS_OF_STATE_GOVERNMENT_INDICATORS == (
        "wikidata_head_of_state_held",
        "wikidata_head_of_government_held",
    )


def test_constants_match_documented_values() -> None:
    """Module-level constants are byte-identical to documented values."""
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
        == "wikidata_heads_of_state_government"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL
        == "https://query.wikidata.org/sparql"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL
        == (
            "https://www.wikidata.org/wiki/"
            "Wikidata:WikiProject_Heads_of_state_and_government"
        )
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION == "SPARQL"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS
        == "SPARQL endpoint (no version)"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_CACHE_POLICY
        == "offline_only"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME == "cache"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME == "metadata.json"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME
        == "wikidata_heads_of_state_government_country_year_v1"
    )
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY
        == "leader_identity_country_year"
    )


def test_attribution_text_matches_doc_and_legacy_constant() -> None:
    """Attribution text is byte-identical to ``docs/sources/attributions.md``
    AND to the legacy constant (Rule #15 drift guard).

    Mirrors the FAS / WHO GHO API / CIRIGHTS / UNDP HDI test
    pattern: the unified adapter's attribution text is the
    canonical ``docs/sources/attributions.md`` wording,
    byte-for-byte, AND is byte-identical to the legacy
    ``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION`` constant
    in
    ``src/leaders_db/ingest/wikidata_heads_of_state_government_io.py``.
    """
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT in doc
    ), (
        "Wikidata HoS/HoG attribution text must be a substring of "
        "docs/sources/attributions.md (Rule #15)."
    )
    from leaders_db.ingest.wikidata_heads_of_state_government_io import (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION as legacy_text,
    )
    assert legacy_text == (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT
    ), (
        "Wikidata HoS/HoG legacy attribution constant must be "
        "byte-identical to the unified "
        "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT constant."
    )


# ---------------------------------------------------------------------------
# Runner end-to-end
# ---------------------------------------------------------------------------


def test_runner_offline_only_year_2023_emits_one_observation_per_binding(
    tmp_path: Path,
) -> None:
    """``cache_policy="offline_only"`` + ``years=(2023,)`` +
    ``countries=("Q30", "Q96")`` emits exactly the 3 fixture bindings
    for the year-2023 / [USA, MEX] parameter set.

    The fixture has 3 USA head-of-state bindings for 2023 (the
    inverse-P39 SPARQL query picks up the people whose P39
    statement was active during 2023 with end >= 2023 or null).
    All 3 bindings match the catalog spec for ``Q30461``
    (``wikidata_head_of_state_held``). The transform stamps
    ``year=2023`` on every observation and preserves the original
    ``start_date`` qualifiers on the audit-trail extension
    payload.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 3
    assert {obs.year for obs in result.observations} == {2023}
    assert {obs.country_code for obs in result.observations} == {None}
    assert {obs.country_name for obs in result.observations} == {
        "United States",
    }
    assert {obs.leader_id for obs in result.observations} == {None}
    # Person labels for the 3 fixture bindings (whatever
    # Wikidata returned for the live query at fixture capture
    # time).
    person_names = {obs.leader_name for obs in result.observations}
    assert person_names == {"Alain Elkann", "Ken Levine", "Jennifer Clement"}
    assert {obs.indicator_code for obs in result.observations} == {
        "wikidata_head_of_state_held",
    }
    assert {
        obs.observation_family
        for obs in result.observations
    } == {WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY}
    assert {
        obs.source_version
        for obs in result.observations
    } == {WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION}

    # Per-observation contract spot check.
    obs = result.observations[0]
    assert obs.value == "Q1065346"  # person QID as text
    assert obs.value_type == "categorical"
    assert obs.raw_locator.path.endswith(_YEAR_2023_FIXTURE_NAME)
    assert (
        obs.raw_locator.url
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL
    )
    assert obs.raw_locator.row_number is None
    assert obs.raw_locator.column_name == "Q30461"
    assert obs.raw_locator.asset_id == (
        f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}:cache:"
        "wd_ALL_2023_446f28aaf1_6a945a3130"
    )
    assert obs.extension["source_row_reference"] == (
        "wikidata:Q30:Q30461:Q1065346:3bcfebe96e"
    )
    assert obs.extension["person_qid"] == "Q1065346"
    assert obs.extension["person_label"] == "Alain Elkann"
    assert obs.extension["country_qid"] == "Q30"
    assert obs.extension["country_label"] == "United States"
    assert obs.extension["office_qid"] == "Q30461"
    assert obs.extension["office_label"] == "president"
    assert obs.extension["start_date"] == "2007-01-01T00:00:00Z"
    assert obs.extension["end_date"] is None
    assert (
        obs.extension["statement_uri"]
        == (
            "http://www.wikidata.org/entity/statement/"
            "Q1065346-73b31c2e-44f0-ba4a-1d75-cd3bb9a896a4"
        )
    )
    assert obs.extension["statement_hash"] == "3bcfebe96e"
    assert obs.extension["requested_year"] == 2023
    assert obs.extension["value_type"] == "categorical"
    assert obs.extension["raw_scale"] == "qid_list"
    assert obs.extension["normalized_scale_target"] == "qid_list"
    assert obs.extension["higher_is_better"] is True
    assert (
        obs.extension["attribution"]
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT
    )
    # Audit-trail verbatim SPARQL binding JSON.
    assert isinstance(obs.extension["raw_binding"], dict)
    assert obs.extension["raw_binding"]["country"]["value"].endswith("/Q30")
    assert obs.extension["raw_binding"]["person"]["value"].endswith(
        "/Q1065346"
    )
    # Transform locator uses the canonical source_row_reference.
    assert (
        obs.transform_locator.transform_name
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME
    )
    assert (
        obs.transform_locator.catalog_key
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )
    assert (
        obs.transform_locator.rule_id
        == "wikidata:Q30:Q30461:Q1065346:3bcfebe96e"
    )


def test_runner_years_none_reads_current_holders_fixture(
    tmp_path: Path,
) -> None:
    """``years=None`` reads the legacy current-holders cache (3 bindings).

    The fixture's current-holders cache has 3 bindings: Monaco
    (Albert II), France x 2 (Mistral, Laplace) -- all Q30461
    (head of state). The transform emits one observation per
    binding with ``year`` taken from the parsed row's
    ``start_date`` year (1994, 1899, 1822). ``country_name``
    carries the Wikidata English label verbatim.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path, years=None, cache_policy="offline_only",
    )
    assert len(result.observations) == 3
    years = sorted({obs.year for obs in result.observations})
    assert years == [1822, 1899, 1994]
    countries = sorted({obs.country_name for obs in result.observations})
    assert countries == ["France", "Monaco"]
    # All Q30461 (head of state) bindings.
    assert {obs.indicator_code for obs in result.observations} == {
        "wikidata_head_of_state_held",
    }
    # The runner warns nothing for an empty filter on a clean
    # cache hit.
    codes = [w.code for w in result.warnings]
    assert UNSUPPORTED_FILTER not in codes
    assert WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY not in codes


def test_runner_country_filter_qid_matches_only_matching_observations(
    tmp_path: Path,
) -> None:
    """``countries=("Q30", "Q96")`` filters to the Q30 USA bindings only.

    Mirrors the FAS country-filter test pattern: the filter is
    a Wikidata QID match against the ``country_qid`` column
    (the source-native identifier); the year-2023 cache contains
    only Q30 bindings (Q96 has zero hits in the fixture); the
    current-holders cache contains Q235 (Monaco) + Q142 (France)
    bindings.
    """
    _stage_bundle(tmp_path)
    usa_2023 = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        cache_policy="offline_only",
    )
    assert len(usa_2023.observations) == 3
    assert {
        obs.extension["country_qid"] for obs in usa_2023.observations
    } == {"Q30"}

    # Q235 (Monaco) is in the current-holders fixture but not
    # in the year-2023 fixture. The years=None + Q235 request
    # reads the current-holders cache and emits 1 binding.
    monaco = _run(
        tmp_path,
        years=None,
        countries=("Q235",),
        cache_policy="offline_only",
    )
    assert len(monaco.observations) == 1
    assert monaco.observations[0].country_name == "Monaco"
    assert monaco.observations[0].extension["country_qid"] == "Q235"
    assert monaco.observations[0].extension["person_qid"] == "Q3910"
    assert monaco.observations[0].year == 1994


def test_runner_country_filter_unknown_qid_emits_zero_observations(
    tmp_path: Path,
) -> None:
    """An unknown Wikidata QID filter emits zero observations.

    The unified adapter never invents ISO3 codes. An unknown QID
    is a legitimate filter (no binding matches), so the result
    is zero observations and zero warnings -- the request did
    not pass any non-QID values to the country filter so the
    non-QID warning does not fire.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("Q9999999",),
        cache_policy="offline_only",
    )
    assert result.observations == ()
    codes = [w.code for w in result.warnings]
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY not in codes
    )


def test_runner_country_filter_non_qid_warns_and_emits_zero(
    tmp_path: Path,
) -> None:
    """Non-QID ``countries=`` values surface a structured
    ``wikidata_non_qid_country_filter`` warning and emit zero
    observations.

    Mirrors the FAS country-filter test pattern but adapted for
    the Wikidata source-native identifier: the unified adapter
    never invents ISO3 codes, so a non-QID filter (e.g.
    ``"USA"``) silently emits zero rows AND the readiness
    envelope surfaces a structured warning naming the offending
    values so the caller can switch to QIDs.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("USA",),
        cache_policy="offline_only",
    )
    assert result.observations == ()
    codes = [w.code for w in result.warnings]
    assert (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY in codes
    )
    non_qid_warning = next(
        w for w in result.warnings
        if w.code
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY
    )
    assert non_qid_warning.context["non_qid_countries"] == ["USA"]


def test_runner_explicit_year_non_qid_country_filter_warns_and_emits_zero(
    tmp_path: Path,
) -> None:
    """Explicit-year non-QID filters warn and do not require a fake cache.

    Regression coverage for the readiness gate: ``countries=("USA",)``
    is not a Wikidata QID, so the clean adapter must not invent an
    ISO3-to-QID mapping or look for a synthetic empty-QID cache file.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("USA",),
        cache_policy="offline_only",
    )

    assert result.observations == ()
    non_qid_warning = next(
        w for w in result.warnings
        if w.code
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY
    )
    assert non_qid_warning.context["non_qid_countries"] == ["USA"]


def test_runner_country_filter_wd_prefixed_qid_matches(tmp_path: Path) -> None:
    """``wd:Q30`` prefixed QIDs match the same as bare ``Q30``.

    Mirrors the legacy parser's defensive ``wd:`` prefix
    stripping: the unified transform strips the ``wd:`` prefix
    before the QID regex match so ``wd:Q30`` works the same
    way as ``Q30``.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("wd:Q30", "wd:Q96"),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 3
    assert {obs.extension["country_qid"] for obs in result.observations} == {
        "Q30",
    }


def test_runner_leader_filter_warns_and_is_ignored(tmp_path: Path) -> None:
    """``leaders=`` is unsupported for a per-binding leader-identity
    source and is ignored; the runner still emits the matching
    bindings.

    Stage 4 is the resolver for leader-identity evidence; the
    Stage 2 layer does not filter by leader -- per
    SRC-REQ-005 the readiness envelope surfaces a structured
    ``UNSUPPORTED_FILTER`` warning.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        leaders=("Some Leader",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 3
    codes = [w.code for w in result.warnings]
    assert UNSUPPORTED_FILTER in codes


# ---------------------------------------------------------------------------
# Cache-file availability / readiness failures
# ---------------------------------------------------------------------------


def test_readiness_missing_metadata_fails(tmp_path: Path) -> None:
    """Missing ``metadata.json`` fails readiness with
    ``MISSING_METADATA`` BEFORE ``read_raw`` is called.
    """
    _stage_bundle(tmp_path, with_metadata=False)
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_METADATA


def test_readiness_missing_cache_directory_fails(tmp_path: Path) -> None:
    """Explicit-year request with no cache directory fails readiness.

    The canonical SPARQL query is parameterised by (year,
    country_qids); without a cache directory the runner cannot
    enumerate any cache files for the explicit-year request and
    the readiness gate surfaces a structured ``NETWORK_CACHE_UNAVAILABLE``
    blocker BEFORE ``read_raw`` is called.
    """
    _stage_bundle(tmp_path, with_cache=False)
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(
            _request(tmp_path, years=(2023,), countries=("Q30", "Q96")),
        )
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == NETWORK_CACHE_UNAVAILABLE


def test_readiness_missing_cache_file_for_explicit_year_fails(
    tmp_path: Path,
) -> None:
    """Explicit-year request with a missing cache file fails readiness.

    The cache root exists but the per-(year, country_qids) file
    is missing; the readiness gate surfaces a structured
    ``missing_raw`` blocker BEFORE ``read_raw`` is called.
    """
    _stage_bundle(tmp_path, with_cache=False)
    bundle = (
        tmp_path / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )
    cache_root_path = (
        bundle / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    )
    cache_root_path.mkdir(parents=True, exist_ok=True)
    # Write an unrelated cache file so the cache directory
    # exists but the request's cache file is missing.
    (cache_root_path / "wd_ALL_2023_other_<hash>_ALL.json").write_text(
        json.dumps(
            {
                "head": {"vars": []},
                "results": {"bindings": []},
            }
        ),
        encoding="utf-8",
    )
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(
            _request(
                tmp_path, years=(2023,), countries=("Q30", "Q96"),
            ),
        )
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW


def test_readiness_malformed_cache_file_fails(tmp_path: Path) -> None:
    """A malformed cache file fails readiness with ``MISSING_RAW``.

    The cache file is not a JSON object with a list
    ``results.bindings`` slot; the readiness gate refuses to
    silently fall through to HTTP for the cache-only read path.
    """
    _stage_bundle(tmp_path, with_cache=False)
    bundle = (
        tmp_path / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )
    cache_root_path = (
        bundle / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    )
    cache_root_path.mkdir(parents=True, exist_ok=True)
    target_path = readiness_cache_file(
        _request(tmp_path),
        year=2023,
        country_qids=("Q30", "Q96"),
    )
    target_path.write_text('{"results": "not-a-dict"}', encoding="utf-8")
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(
            _request(
                tmp_path, years=(2023,), countries=("Q30", "Q96"),
            ),
        )
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW


def test_readiness_missing_results_bindings_slot_fails(
    tmp_path: Path,
) -> None:
    """A cache file missing the ``results.bindings`` slot fails readiness."""
    _stage_bundle(tmp_path, with_cache=False)
    bundle = (
        tmp_path / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
    )
    cache_root_path = (
        bundle / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    )
    cache_root_path.mkdir(parents=True, exist_ok=True)
    target_path = readiness_cache_file(
        _request(tmp_path),
        year=2023,
        country_qids=("Q30", "Q96"),
    )
    target_path.write_text(
        json.dumps({"head": {"vars": []}}), encoding="utf-8",
    )
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(
            _request(
                tmp_path, years=(2023,), countries=("Q30", "Q96"),
            ),
        )
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW


def test_readiness_metadata_version_mismatch_fails(tmp_path: Path) -> None:
    """Staged metadata with a non-canonical ``version`` fails readiness.

    Both the canonical ``"SPARQL"`` stamp AND the legacy alias
    ``"SPARQL endpoint (no version)"`` are accepted by the
    readiness gate. Any other value fails with the
    source-specific metadata-version mismatch error.
    """
    _stage_bundle(tmp_path, version="some-other-version")
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH
    )


def test_readiness_accepts_legacy_version_alias(tmp_path: Path) -> None:
    """Canonical metadata ``version="SPARQL endpoint (no version)"``
    is accepted by the readiness gate (backward compatibility).
    """
    _stage_bundle(
        tmp_path,
        version=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS,
    )
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_rejects_refresh_and_no_cache_policies(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` / ``"no_cache"`` is NOT supported
    by the unified adapter in this slice -- readiness surfaces a
    structured ``unsupported_cache_policy`` error.
    """
    _stage_bundle(tmp_path)
    for policy in ("refresh", "no_cache"):
        readiness = (
            create_wikidata_heads_of_state_government_adapter()
            .check_ready(_request(tmp_path, cache_policy=policy))
        )
        assert readiness.ready is False
        assert (
            readiness.errors[0].code
            == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY
        )
        assert (
            readiness.errors[0].code == UNSUPPORTED_CACHE_POLICY
        )


def test_readiness_rejects_multi_year_request(tmp_path: Path) -> None:
    """Multi-year requests fail explicitly instead of dropping years.

    The cache-only slice maps one request to one legacy SPARQL cache
    key. A tuple such as ``years=(2023, 2024)`` would otherwise read
    only the first year, so readiness blocks before ``read_raw`` /
    ``transform``.
    """
    _stage_bundle(tmp_path)
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(_request(tmp_path, years=(2023, 2024)))
    )

    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR
    )
    with pytest.raises(RuntimeError):
        _run(tmp_path, years=(2023, 2024))


def test_readiness_unsupported_request_version_fails(
    tmp_path: Path,
) -> None:
    """``request.source_version`` other than the canonical
    ``"SPARQL"`` fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009.
    """
    _stage_bundle(tmp_path)
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(_request(tmp_path, source_version="other-version"))
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == "unsupported_version"


def test_readiness_correct_metadata_passes(tmp_path: Path) -> None:
    """A canonical metadata version + a complete cache passes readiness."""
    _stage_bundle(tmp_path)
    readiness = (
        create_wikidata_heads_of_state_government_adapter()
        .check_ready(
            _request(
                tmp_path,
                years=(2023,),
                countries=("Q30", "Q96"),
                cache_policy="offline_only",
            ),
        )
    )
    assert readiness.ready is True
    assert readiness.errors == ()


# ---------------------------------------------------------------------------
# No-network contract (monkeypatched sentinels)
# ---------------------------------------------------------------------------


def _install_http_sentinels(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[str]]:
    """Patch the legacy Wikidata HTTP layer + ``requests.get`` to
    fail if invoked by the unified read path.

    Mirrors the FAS / WHO GHO API no-network contract test
    pattern. Returns ``(fetch_calls, requests_get_calls)`` --
    the lists record any invocation attempt so the test can
    prove the sentinels were never reached. The patches are
    scoped to the test via ``monkeypatch`` so they auto-revert
    at teardown.
    """
    fetch_calls: list[str] = []
    requests_get_calls: list[str] = []

    def _fetch_sentinel(*args: Any, **kwargs: Any) -> Any:
        fetch_calls.append(
            f"fetch_wikidata_sparql_payload({args!r}, {kwargs!r})"
        )
        raise AssertionError(
            "fetch_wikidata_sparql_payload must NOT be called when "
            "cache_policy is 'offline_only' / 'prefer_cache' and "
            "readiness passed; the unified Wikidata HoS/HoG "
            "adapter is offline / cache-only in this slice."
        )

    def _requests_get_sentinel(*args: Any, **kwargs: Any) -> Any:
        requests_get_calls.append(
            f"requests.get({args!r}, {kwargs!r})"
        )
        raise AssertionError(
            "requests.get must NOT be called by the unified "
            "Wikidata HoS/HoG adapter under supported cache "
            "policies; the cache-only read path never falls "
            "through to HTTP."
        )

    try:
        from leaders_db.ingest import (
            wikidata_heads_of_state_government_http as _http,
        )

        monkeypatch.setattr(
            _http,
            "fetch_wikidata_sparql_payload",
            _fetch_sentinel,
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

    Mirrors the WHO GHO API no-network contract test: the HTTP
    sentinels (legacy
    :func:`fetch_wikidata_sparql_payload` + :func:`requests.get`)
    are installed before the runner executes. If the unified
    adapter falls through to HTTP for any reason, either
    sentinel raises ``AssertionError`` and the test fails. The
    post-condition asserts the sentinel lists are empty so a
    regression to HTTP is caught immediately.
    """
    _stage_bundle(tmp_path)
    fetch_calls, requests_get_calls = _install_http_sentinels(
        monkeypatch,
    )
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 3
    assert fetch_calls == [], (
        "fetch_wikidata_sparql_payload was invoked under "
        f"cache_policy='offline_only'; calls={fetch_calls}"
    )
    assert requests_get_calls == [], (
        "requests.get was invoked under "
        f"cache_policy='offline_only'; calls={requests_get_calls}"
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
    fetch_calls, requests_get_calls = _install_http_sentinels(
        monkeypatch,
    )
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        cache_policy="prefer_cache",
    )
    assert len(result.observations) == 3
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
    ``STAGE2_ADAPTERS`` table (mirrors the FAS / WHO GHO API /
    CIRIGHTS / UNDP HDI contract).
    """
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(
        legacy_ingest,
        "STAGE2_ADAPTERS",
        {WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY: None},
    )
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Q30", "Q96"),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 3


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------


def test_importing_wikidata_heads_of_state_government_adapter_does_not_import_legacy_ingest() -> None:  # noqa: E501
    """Importing
    ``leaders_db.sources.adapters.wikidata_heads_of_state_government``
    MUST NOT import ``leaders_db.ingest`` (the package-isolation
    contract per ``docs/architecture/sources.md`` §10.1).

    Mirrors the FAS / WHO GHO API import-boundary test: the
    test purges every ``leaders_db.sources`` /
    ``leaders_db.ingest`` entry from ``sys.modules``, imports
    the new adapter, and asserts that no ``leaders_db.ingest``
    module leaked into ``sys.modules``.
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
        "leaders_db.sources.adapters.wikidata_heads_of_state_government"
    )
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest"
        or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing "
        "leaders_db.sources.adapters.wikidata_heads_of_state_government "
        f"must not import leaders_db.ingest (leaked modules: {leaked})"
    )


def test_legacy_ingest_wikidata_heads_of_state_government_slot_unchanged() -> (
    None
):
    """The legacy
    ``STAGE2_ADAPTERS['wikidata_heads_of_state_government']`` slot
    still resolves to the legacy orchestrator function -- the
    unified migration does not mutate legacy dispatch.

    Mirrors the FAS / WHO GHO API / CIRIGHTS / UNDP HDI test
    pattern: the clean adapter does not touch the legacy
    dispatch table; the legacy slot remains callable for
    backward compatibility.
    """
    import leaders_db.ingest as legacy_ingest

    dispatch = legacy_ingest.STAGE2_ADAPTERS
    assert WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY in dispatch
    assert callable(
        dispatch[WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY]
    )


# ---------------------------------------------------------------------------
# Path-helper + cache-root layout
# ---------------------------------------------------------------------------


def test_cache_root_helper_returns_canonical_layout(
    tmp_path: Path,
) -> None:
    """``cache_root(request)`` returns
    ``<raw_root>/wikidata_heads_of_state_government/cache/``.

    Mirrors the FAS / WHO GHO API path-helper test: the
    canonical cache layout is documented and pinned.
    """
    expected = (
        tmp_path
        / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY
        / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    )
    assert cache_root(_request(tmp_path)) == expected


__all__ = [
    "test_attribution_text_matches_doc_and_legacy_constant",
    "test_cache_root_helper_returns_canonical_layout",
    "test_constants_match_documented_values",
    "test_descriptor_factory_register_and_protocol",
    "test_importing_wikidata_heads_of_state_government_adapter_does_not_import_legacy_ingest",
    "test_indicator_constants_match_legacy_catalog",
    "test_legacy_ingest_wikidata_heads_of_state_government_slot_unchanged",
    "test_offline_only_runner_does_not_invoke_network",
    "test_prefer_cache_runner_does_not_invoke_network",
    "test_readiness_accepts_legacy_version_alias",
    "test_readiness_correct_metadata_passes",
    "test_readiness_malformed_cache_file_fails",
    "test_readiness_metadata_version_mismatch_fails",
    "test_readiness_missing_cache_directory_fails",
    "test_readiness_missing_cache_file_for_explicit_year_fails",
    "test_readiness_missing_metadata_fails",
    "test_readiness_missing_results_bindings_slot_fails",
    "test_readiness_rejects_refresh_and_no_cache_policies",
    "test_readiness_unsupported_request_version_fails",
    "test_runner_country_filter_non_qid_warns_and_emits_zero",
    "test_runner_country_filter_qid_matches_only_matching_observations",
    "test_runner_country_filter_unknown_qid_emits_zero_observations",
    "test_runner_country_filter_wd_prefixed_qid_matches",
    "test_runner_does_not_dispatch_through_legacy_stage2_adapters",
    "test_runner_explicit_year_non_qid_country_filter_warns_and_emits_zero",
    "test_runner_leader_filter_warns_and_is_ignored",
    "test_runner_offline_only_year_2023_emits_one_observation_per_binding",
    "test_runner_years_none_reads_current_holders_fixture",
]

# Reference static-utility symbols (defensive: keep them live so the
# static analyzer does not flag them as unused imports).
_ = (
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
    WikidataHeadsOfStateGovernmentAdapter,
)
