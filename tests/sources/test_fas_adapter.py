"""FAS (Federation of American Scientists) Nuclear Notebook clean-source adapter tests.

Covers the clean ``leaders_db.sources.adapters.fas`` slice:

1. Descriptor / factory / register / protocol conformance (the
   ``SourceAdapter`` Protocol).
2. Import boundary: importing ``leaders_db.sources.adapters.fas``
   does NOT import ``leaders_db.ingest`` (the package-isolation
   contract per ``docs/architecture/sources.md`` §10.1).
3. Runner end-to-end against the staged fixture HTML cache:
   ``SourceIngestRunner.run(request)`` drives the new registry
   end-to-end against the fixture and produces
   ``NormalizedObservation`` records (5 indicators per country).
4. Snapshot-year / temporal-fit semantics: a requested 2023
   emits 2014 rows labeled with the snapshot year plus
   ``requested_year=2023`` / ``proxy_snapshot_semantics`` audit
   metadata; the readiness envelope surfaces a structured
   ``YEAR_ABSENT`` warning per SRC-COV-002 / SRC-COV-003 (no
   silent stale-proxy fill).
5. Country filter honors source-native FAS display names only
   (the FAS table does NOT carry ISO3 codes).
6. Leader filter warns and is ignored (FAS is country-year
   nuclear evidence).
7. Sentinel handling: ``n.a.`` / ``?`` cells are represented
   consistently with the legacy DB writer (``value=None``,
   ``raw_value="n.a."`` / ``"?"``); ``<10`` cells map to 10 with
   the raw literal preserved; numeric cells like ``"1,600"`` /
   ``"8,000"`` are coerced correctly; the legacy parser strips
   ``<sup>`` footnote markers before populating ``_raw_value``,
   so audit ``raw_value`` is the post-strip cell text.
8. Readiness failures: missing metadata, missing HTML,
   ``source_version`` mismatch, malformed ``local_files``,
   checksum mismatch.
9. Cache policy: ``cache_policy="refresh"`` / ``"no_cache"``
   is NOT supported and fails readiness with a structured
   ``unsupported_cache_policy`` error before the reader opens
   the cache.
10. Runner does NOT consult legacy ``STAGE2_ADAPTERS`` even
    when the legacy ``fas`` slot is monkeypatched to a tracker.
11. The legacy ``STAGE2_ADAPTERS["fas"]`` slot remains callable
    for backward compatibility (the clean migration does not
    mutate legacy dispatch).
"""

from __future__ import annotations

import hashlib
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
from leaders_db.sources.adapters.fas import (
    FAS_ADAPTER_FACTORY,
    FAS_ATTRIBUTION_KEY,
    FAS_ATTRIBUTION_TEXT,
    FAS_CHECKSUM_MISMATCH,
    FAS_COVERAGE_END_YEAR,
    FAS_COVERAGE_START_YEAR,
    FAS_DEFAULT_CACHE_POLICY,
    FAS_DEFAULT_VERSION,
    FAS_HOMEPAGE_URL,
    FAS_HTML_NAME,
    FAS_INDICATORS,
    FAS_LOCAL_FILES_INVALID,
    FAS_METADATA_VERSION_MISMATCH,
    FAS_OBSERVATION_FAMILY,
    FAS_PUBLISHER_URL,
    FAS_RAW_COLUMNS,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
    FAS_SUPPORTED_FAMILIES,
    FAS_TRANSFORM_NAME,
    FAS_UNSUPPORTED_CACHE_POLICY,
    FasAdapter,
    build_fas_descriptor,
    create_fas_adapter,
    register_fas,
)
from leaders_db.sources.adapters.fas._constants import (
    FAS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------

_FIXTURE_HTML = Path("tests/fixtures/fas/sample.html")
_FAS_FIXTURE_COUNTRIES: tuple[str, ...] = (
    "China",
    "North Korea",
    "Russia",
    "United Kingdom",
    "United States",
)


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_html: bool = True,
    with_local_files: bool = True,
    with_checksum: bool = True,
    local_files: list[str] | None = None,
    source_version: str | None = FAS_DEFAULT_VERSION,
    checksum_value: str | None = None,
) -> Path:
    """Stage the canonical FAS bundle shape under ``raw_root``.

    Mirrors the existing ``data/raw/fas/metadata.json`` shape
    (``source_name`` / ``source_version`` / ``source_url`` /
    ``publisher_url`` / ``local_files`` / ``checksum_sha256`` /
    ``caveats`` / ``coverage`` / ``years_available`` /
    ``ingestion_status`` / ``download_date`` /
    ``license_note``). The fixture HTML is the real-format FAS
    consolidated status page fixture; the staged checksum is
    auto-computed against the fixture bytes by default.
    """
    bundle = raw_root / FAS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    html_path = bundle / FAS_HTML_NAME
    if with_html:
        shutil.copy2(_FIXTURE_HTML, html_path)
    if with_metadata:
        if checksum_value is None and with_checksum and html_path.is_file():
            checksum_value = hashlib.sha256(
                html_path.read_bytes()
            ).hexdigest()
        payload: dict[str, Any] = {
            "source_name": (
                "Federation of American Scientists Nuclear Notebook"
            ),
            "source_version": source_version,
            "download_date": "2026-06-19",
            "coverage": "9 nuclear-armed states, single snapshot year",
            "years_available": (
                f"snapshot-only (consolidated snapshot is "
                f"{FAS_SNAPSHOT_YEAR})"
            ),
            "license_note": "Free; cite Federation of American Scientists.",
            "local_files": (
                [FAS_HTML_NAME]
                if with_local_files and local_files is None
                else local_files
            ),
            "ingestion_status": "downloaded",
            "source_url": FAS_STATUS_PAGE_URL,
            "publisher_url": FAS_PUBLISHER_URL,
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = checksum_value
        (bundle / "metadata.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    """Build a default FAS :class:`SourceIngestRequest`."""
    return SourceIngestRequest(
        source_id=SourceId(FAS_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    """Register + run the FAS adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_fas(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor / factory / register / protocol
# ---------------------------------------------------------------------------


def test_descriptor_factory_register_and_protocol() -> None:
    """Descriptor exposes the canonical FAS static metadata.

    Mirrors the WHO GHO API / CIRIGHTS / UNDP HDI test pattern:
    ``create_fas_adapter`` returns a :class:`FasAdapter` that
    satisfies the runtime-checkable :class:`SourceAdapter`
    Protocol, the descriptor carries the canonical source_id /
    attribution_key / default_version / source_type / coverage /
    observation family / requires_network, and the
    :func:`register_fas` helper wires the adapter into the
    :class:`InMemorySourceRegistry`.
    """
    adapter = create_fas_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert FAS_ADAPTER_FACTORY().descriptor == adapter.descriptor

    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == FAS_SOURCE_KEY
    assert descriptor.attribution_key == FAS_ATTRIBUTION_KEY
    assert descriptor.default_version == FAS_DEFAULT_VERSION
    assert descriptor.source_type == "document"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (
        FAS_OBSERVATION_FAMILY,
    )
    assert descriptor.supported_observation_families == FAS_SUPPORTED_FAMILIES
    assert descriptor.coverage_hint.start_year == FAS_COVERAGE_START_YEAR
    assert descriptor.coverage_hint.end_year == FAS_COVERAGE_END_YEAR
    assert descriptor.coverage_hint.start_year == FAS_SNAPSHOT_YEAR
    assert descriptor.coverage_hint.end_year == FAS_SNAPSHOT_YEAR
    assert descriptor.homepage_url == FAS_HOMEPAGE_URL

    # Direct factory alias matches the canonical descriptor.
    assert (
        build_fas_descriptor().source_id.slug == FAS_SOURCE_KEY
    )

    registry = InMemorySourceRegistry()
    returned = register_fas(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(FAS_SOURCE_KEY)) is returned


def test_indicator_and_raw_column_constants_match_legacy_catalog() -> None:
    """The in-scope indicators + raw columns match the canonical 5-indicator catalog."""
    assert FAS_INDICATORS == (
        "fas_operational_strategic",
        "fas_operational_nonstrategic",
        "fas_reserve_nondeployed",
        "fas_military_stockpile",
        "fas_total_inventory",
    )
    assert FAS_RAW_COLUMNS == (
        "Operational Strategic",
        "Operational Nonstrategic",
        "Reserve/Nondeployed",
        "Military Stockpile",
        "Total Inventory",
    )


def test_attribution_text_matches_doc() -> None:
    """Attribution text is byte-identical to ``docs/sources/attributions.md``.

    Drift guard per Always-On Rule #15: the attribution block
    embedded in the unified adapter is the canonical
    ``docs/sources/attributions.md`` wording, byte-for-byte.
    """
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert FAS_ATTRIBUTION_TEXT in doc, (
        "FAS attribution text must be a substring of "
        "docs/sources/attributions.md (Rule #15)."
    )
    # Also pin the legacy constant in ``src/leaders_db/ingest/fas_io.py``
    # to the unified adapter constant (the legacy code re-exports the
    # same string under ``FAS_ATTRIBUTION``).
    from leaders_db.ingest.fas_io import FAS_ATTRIBUTION as legacy_text
    assert legacy_text == FAS_ATTRIBUTION_TEXT, (
        "FAS legacy attribution constant must be byte-identical to the "
        "unified FAS_ATTRIBUTION_TEXT constant."
    )


def test_constants_match_documented_values() -> None:
    """Module-level constants are byte-identical to documented values."""
    assert FAS_SOURCE_KEY == "fas"
    assert FAS_STATUS_PAGE_URL == (
        "https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html"
    )
    assert FAS_PUBLISHER_URL == "https://fas.org/issues/nuclear-weapons/"
    assert FAS_HOMEPAGE_URL == FAS_PUBLISHER_URL
    assert FAS_HTML_NAME == "fas_status.html"
    assert FAS_DEFAULT_CACHE_POLICY == "offline_only"
    assert FAS_TRANSFORM_NAME == "fas_country_year_v1"


# ---------------------------------------------------------------------------
# Runner end-to-end
# ---------------------------------------------------------------------------


def test_runner_offline_only_requested_2023_emits_snapshot_year_rows(
    tmp_path: Path,
) -> None:
    """``cache_policy="offline_only"`` + ``years=(2023,)`` +
    ``countries=("Russia",)`` emits exactly the 5 Russia
    snapshot-2014 observations with a ``YEAR_ABSENT`` warning
    AND every observation tagged with the proxy_snapshot
    audit metadata (no silent relabeling to 2023).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {FAS_SNAPSHOT_YEAR}
    assert {obs.country_code for obs in result.observations} == {None}
    assert {obs.leader_id for obs in result.observations} == {None}
    assert {obs.leader_name for obs in result.observations} == {None}
    assert {obs.country_name for obs in result.observations} == {"Russia"}
    assert {obs.source_version for obs in result.observations} == {
        FAS_DEFAULT_VERSION,
    }
    indicators = sorted({obs.indicator_code for obs in result.observations})
    assert indicators == sorted(FAS_INDICATORS)
    assert {obs.observation_family for obs in result.observations} == {
        FAS_OBSERVATION_FAMILY,
    }
    # Year warning surfaces so the caller can branch on the gap.
    codes = [w.code for w in result.warnings]
    assert YEAR_ABSENT in codes

    # Spot check Russia's total inventory: value=8000, raw_value="8,000".
    total = next(
        obs for obs in result.observations
        if obs.indicator_code == "fas_total_inventory"
    )
    assert total.value == pytest.approx(8000.0)
    assert total.value_type == "numeric"
    assert total.unit == "warheads"
    assert total.scale == "warhead_count"
    assert total.raw_locator.path.endswith(FAS_HTML_NAME)
    assert total.raw_locator.column_name == "Total Inventory"
    assert total.raw_locator.url == FAS_STATUS_PAGE_URL
    assert total.raw_locator.row_number is None
    assert total.raw_locator.asset_id == (
        f"{FAS_SOURCE_KEY}:{FAS_HTML_NAME}"
    )
    assert total.extension["source_row_reference"] == (
        "fas:Total Inventory:Russia"
    )
    assert total.extension["raw_value"] == "8,000"
    assert total.extension["normalized_value"] == pytest.approx(8000.0)
    assert total.extension["higher_is_better"] is False
    assert total.extension["raw_scale"] == "warhead_count"
    assert total.extension["normalized_scale_target"] == "0-10"
    assert total.extension["fas_raw_column"] == "Total Inventory"
    assert total.extension["snapshot_year"] == FAS_SNAPSHOT_YEAR
    assert total.extension["year_window"] == [
        FAS_SNAPSHOT_YEAR, FAS_SNAPSHOT_YEAR,
    ]
    assert total.extension["source_row_url"] == FAS_STATUS_PAGE_URL
    assert total.extension["attribution"] == FAS_ATTRIBUTION_TEXT
    # Proxy audit metadata per the temporal-fit contract.
    assert total.extension["requested_year"] == 2023
    assert total.extension["proxy_snapshot_semantics"].startswith(
        "requested 2023 uses actual FAS 2014 snapshot data",
    )
    # Transform locator uses the canonical source_row_reference.
    assert total.transform_locator.transform_name == FAS_TRANSFORM_NAME
    assert total.transform_locator.catalog_key == FAS_SOURCE_KEY
    assert total.transform_locator.rule_id == (
        "fas:Total Inventory:Russia"
    )


def test_runner_requested_snapshot_year_emits_no_year_warning(
    tmp_path: Path,
) -> None:
    """``years=(2014,)`` (the canonical snapshot year) emits no
    ``YEAR_ABSENT`` warning and every observation is labeled
    with the snapshot year.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 5
    codes = [w.code for w in result.warnings]
    assert YEAR_ABSENT not in codes
    # No requested_year audit metadata when the requested year
    # matches the snapshot year exactly.
    for obs in result.observations:
        assert "requested_year" not in obs.extension
        assert "proxy_snapshot_semantics" not in obs.extension
        assert obs.year == FAS_SNAPSHOT_YEAR


def test_readiness_year_warning_uses_parsed_html_snapshot_year(
    tmp_path: Path,
) -> None:
    """Readiness warnings compare against the staged HTML snapshot year.

    This protects the clean adapter from drifting if FAS updates the
    consolidated page: ``check_ready`` must use the same parsed year
    as ``read_raw`` / ``transform``, not the historical 2014 fallback
    constant.
    """
    bundle = _stage_bundle(tmp_path, with_checksum=False)
    staged_html = bundle / FAS_HTML_NAME
    html = staged_html.read_text(encoding="utf-8")
    staged_html.write_text(
        html.replace(
            '<meta content="Wed, 30 Apr 2014 12:42:33 -0380" name="date">',
            '<meta name="date" content="Wed, 30 Apr 2020 12:42:33 -0380">',
        ),
        encoding="utf-8",
    )

    snapshot_hit = create_fas_adapter().check_ready(
        _request(tmp_path, years=(2020,), cache_policy="offline_only"),
    )
    assert snapshot_hit.ready is True
    assert [warning.code for warning in snapshot_hit.warnings] == []

    snapshot_miss = _run(
        tmp_path,
        years=(2023,),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    year_warnings = [
        warning for warning in snapshot_miss.warnings
        if warning.code == YEAR_ABSENT
    ]
    assert len(year_warnings) == 1
    assert year_warnings[0].context["snapshot_year"] == 2020
    assert {obs.year for obs in snapshot_miss.observations} == {2020}
    assert {
        obs.extension["snapshot_year"] for obs in snapshot_miss.observations
    } == {2020}
    assert {
        obs.extension["requested_year"] for obs in snapshot_miss.observations
    } == {2023}


def test_runner_years_none_reads_all_fixture_snapshot_observations(
    tmp_path: Path,
) -> None:
    """``years=None`` reads every available fixture snapshot
    observation (5 fixture countries x 5 indicators -- with
    sentinels preserved on the audit trail).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=None, cache_policy="offline_only")
    countries = sorted({obs.country_name for obs in result.observations})
    assert countries == sorted(_FAS_FIXTURE_COUNTRIES)
    indicators = sorted({obs.indicator_code for obs in result.observations})
    assert indicators == sorted(FAS_INDICATORS)
    triples = {
        (obs.country_name, obs.year, obs.indicator_code)
        for obs in result.observations
    }
    # 5 countries x 5 indicators = 25 observations (sentinels are
    # represented with ``value=None`` + audit ``raw_value`` per
    # legacy DB writer semantics).
    assert len(triples) == len(result.observations) == 25
    codes = [w.code for w in result.warnings]
    assert YEAR_ABSENT not in codes


def test_runner_country_filter_matches_source_native_display_name(
    tmp_path: Path,
) -> None:
    """``countries=("Russia",)`` matches the FAS source-native
    display name and emits the 5 Russia rows; ISO3 / unknown
    country emits zero rows.
    """
    _stage_bundle(tmp_path)
    present = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    assert len(present.observations) == 5
    assert {obs.country_name for obs in present.observations} == {"Russia"}

    # ISO3 filter (which the FAS source does NOT carry) silently
    # emits zero rows -- the unified adapter never invents ISO3.
    iso3 = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("RUS",),
        cache_policy="offline_only",
    )
    assert iso3.observations == ()

    # Unknown country emits zero rows.
    unknown = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("Atlantis",),
        cache_policy="offline_only",
    )
    assert unknown.observations == ()


def test_runner_leader_filter_warns_and_is_ignored(tmp_path: Path) -> None:
    """``leaders=`` is unsupported for a country-year nuclear
    source and is ignored; the runner still emits the
    snapshot-year rows.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("Russia",),
        leaders=("Some Leader",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 5
    codes = [w.code for w in result.warnings]
    assert UNSUPPORTED_FILTER in codes


def test_runner_dedupes_multi_year_request_with_snapshot_year(
    tmp_path: Path,
) -> None:
    """``years=(2014, 2023)`` emits a single 2014 observation set
    (no duplicate 2014 observations even though both years map
    to the same snapshot).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR, 2023),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 5
    triples = {
        (obs.country_name, obs.year, obs.indicator_code)
        for obs in result.observations
    }
    assert len(triples) == 5
    codes = [w.code for w in result.warnings]
    assert YEAR_ABSENT in codes


# ---------------------------------------------------------------------------
# Sentinel handling
# ---------------------------------------------------------------------------


def test_sentinel_lt_10_maps_to_upper_bound(tmp_path: Path) -> None:
    """North Korea's ``<10`` cells (``&lt;10`` HTML-encoded)
    map to the upper bound ``10`` while preserving the raw
    literal ``"&lt;10"`` on the audit trail.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("North Korea",),
        cache_policy="offline_only",
    )
    nk = {obs.indicator_code: obs for obs in result.observations}
    assert nk["fas_reserve_nondeployed"].value == pytest.approx(10.0)
    assert nk["fas_reserve_nondeployed"].extension["raw_value"] == "&lt;10"
    assert nk["fas_military_stockpile"].value == pytest.approx(10.0)
    assert nk["fas_military_stockpile"].extension["raw_value"] == "&lt;10"
    assert nk["fas_total_inventory"].value == pytest.approx(10.0)
    assert nk["fas_total_inventory"].extension["raw_value"] == "&lt;10"


def test_sentinel_n_a_represented_with_raw_literal(tmp_path: Path) -> None:
    """UK ``n.a.`` cells are represented consistently with the
    legacy DB writer semantics: the observation IS emitted
    with ``value=None`` and the audit ``raw_value`` preserves
    the literal ``"n.a."``.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("United Kingdom",),
        cache_policy="offline_only",
    )
    uk = {obs.indicator_code: obs for obs in result.observations}
    assert "fas_operational_nonstrategic" in uk
    obs = uk["fas_operational_nonstrategic"]
    assert obs.value is None
    assert obs.value_type == "missing"
    assert obs.extension["raw_value"] == "n.a."


def test_sentinel_question_mark_represented_with_raw_literal(
    tmp_path: Path,
) -> None:
    """China ``?`` cells are represented consistently: ``value=None``,
    ``raw_value="?"``.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("China",),
        cache_policy="offline_only",
    )
    cn = {obs.indicator_code: obs for obs in result.observations}
    assert "fas_operational_nonstrategic" in cn
    obs = cn["fas_operational_nonstrategic"]
    assert obs.value is None
    assert obs.value_type == "missing"
    assert obs.extension["raw_value"] == "?"


def test_real_numeric_values_with_commas_and_footnote_letter(
    tmp_path: Path,
) -> None:
    """Russia's ``"1,600"`` (operational strategic), ``"2,700"``
    (reserve), ``"4,300"`` (stockpile), and ``"8,000"`` (total)
    are coerced to numeric values. The legacy reader strips the
    ``<sup>`` footnote marker before populating the ``_raw_value``
    sibling column, so the clean adapter's audit ``raw_value`` is
    the post-strip legacy cell text (``"1,600"``), not the original
    footnote-bearing HTML/text.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=None,
        countries=("Russia",),
        cache_policy="offline_only",
    )
    russia = {obs.indicator_code: obs for obs in result.observations}
    assert russia["fas_operational_strategic"].value == pytest.approx(1600.0)
    assert russia["fas_operational_strategic"].extension["raw_value"] == "1,600"
    assert russia["fas_reserve_nondeployed"].value == pytest.approx(2700.0)
    assert russia["fas_reserve_nondeployed"].extension["raw_value"] == "2,700"
    assert russia["fas_military_stockpile"].value == pytest.approx(4300.0)
    assert russia["fas_military_stockpile"].extension["raw_value"] == "4,300"
    assert russia["fas_total_inventory"].value == pytest.approx(8000.0)
    assert russia["fas_total_inventory"].extension["raw_value"] == "8,000"


# ---------------------------------------------------------------------------
# Readiness failures
# ---------------------------------------------------------------------------


def test_readiness_missing_metadata_fails(tmp_path: Path) -> None:
    """Missing ``metadata.json`` fails readiness with
    ``MISSING_METADATA`` BEFORE ``read_raw`` is called.
    """
    _stage_bundle(tmp_path, with_metadata=False)
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_METADATA


def test_readiness_missing_html_fails(tmp_path: Path) -> None:
    """Missing ``fas_status.html`` fails readiness with
    ``MISSING_RAW`` BEFORE ``read_raw`` is called.
    """
    _stage_bundle(tmp_path, with_html=False)
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW


def test_readiness_metadata_version_mismatch_fails(tmp_path: Path) -> None:
    """Staged metadata with a non-canonical ``source_version``
    fails readiness with ``fas_metadata_version_mismatch``.
    """
    _stage_bundle(tmp_path, source_version="not-canonical")
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == FAS_METADATA_VERSION_MISMATCH


def test_readiness_local_files_wrong_fails(tmp_path: Path) -> None:
    """Staged metadata whose ``local_files`` does not include
    the canonical ``fas_status.html`` filename fails readiness
    with ``fas_local_files_invalid``.
    """
    _stage_bundle(tmp_path, local_files=["some_other_file.html"])
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == FAS_LOCAL_FILES_INVALID


def test_readiness_checksum_mismatch_fails(tmp_path: Path) -> None:
    """Staged metadata whose ``checksum_sha256`` does not match
    the live re-hash of ``fas_status.html`` fails readiness
    with ``fas_checksum_mismatch``.
    """
    wrong_sha = "0" * 64
    _stage_bundle(tmp_path, checksum_value=wrong_sha)
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == FAS_CHECKSUM_MISMATCH


def test_readiness_correct_checksum_passes(tmp_path: Path) -> None:
    """Staged metadata whose ``checksum_sha256`` matches the
    live re-hash of ``fas_status.html`` passes readiness.
    """
    _stage_bundle(tmp_path)
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_missing_local_files_field_passes(tmp_path: Path) -> None:
    """``local_files`` is optional in the FAS metadata shape;
    when absent, the gate accepts the bundle as long as the
    HTML is staged and the metadata ``source_version`` is
    canonical.
    """
    _stage_bundle(tmp_path, with_local_files=False)
    readiness = create_fas_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_rejects_refresh_and_no_cache_policies(tmp_path: Path) -> None:
    """``cache_policy="refresh"`` / ``"no_cache"`` is NOT
    supported by the unified FAS adapter in this slice --
    readiness surfaces a structured
    ``fas_unsupported_cache_policy`` error BEFORE
    ``read_raw`` is called.
    """
    _stage_bundle(tmp_path)
    for policy in ("refresh", "no_cache"):
        readiness = create_fas_adapter().check_ready(
            _request(tmp_path, cache_policy=policy),
        )
        assert readiness.ready is False
        assert readiness.errors[0].code == FAS_UNSUPPORTED_CACHE_POLICY
        assert readiness.errors[0].code == UNSUPPORTED_CACHE_POLICY


def test_readiness_unsupported_request_version_fails(tmp_path: Path) -> None:
    """``request.source_version`` other than the canonical
    default fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009.
    """
    _stage_bundle(tmp_path)
    readiness = create_fas_adapter().check_ready(
        _request(tmp_path, source_version="some-other-version"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == FAS_UNSUPPORTED_VERSION


# ---------------------------------------------------------------------------
# Legacy-dispatch contract
# ---------------------------------------------------------------------------


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unified runner does NOT consult the legacy
    ``STAGE2_ADAPTERS`` table (mirrors the WHO GHO API /
    CIRIGHTS / UNDP HDI contract).
    """
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(
        legacy_ingest, "STAGE2_ADAPTERS", {FAS_SOURCE_KEY: None},
    )
    result = _run(
        tmp_path,
        years=(FAS_SNAPSHOT_YEAR,),
        countries=("Russia",),
        cache_policy="offline_only",
    )
    assert len(result.observations) == 5


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------


def test_importing_fas_adapter_does_not_import_legacy_ingest() -> None:
    """Importing ``leaders_db.sources.adapters.fas`` MUST NOT
    import ``leaders_db.ingest`` (the package-isolation
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
    importlib.import_module("leaders_db.sources.adapters.fas")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing leaders_db.sources.adapters.fas must not import "
        f"leaders_db.ingest (leaked modules: {leaked})"
    )


def test_legacy_ingest_fas_slot_unchanged() -> None:
    """The legacy ``STAGE2_ADAPTERS['fas']`` slot still
    resolves to the legacy orchestrator function -- the
    unified migration does not mutate legacy dispatch.
    """
    import leaders_db.ingest as legacy_ingest

    dispatch = legacy_ingest.STAGE2_ADAPTERS
    assert FAS_SOURCE_KEY in dispatch
    assert callable(dispatch[FAS_SOURCE_KEY])


# Reference static-utility symbols (defensive: keep them live so the
# static analyzer does not flag them as unused imports).
_ = (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
    FAS_UNSUPPORTED_VERSION,
    FasAdapter,
)
