"""Phase C / D slice -- World Bank WDI adapter under the unified
``leaders_db.sources``.

The World Bank WDI adapter is the third source rebuilt under the
clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 3,
docs/requirements/sources.md §12 SRC-MIG-005), after the PWT
10.01 and Maddison Project Database 2023 adapters. The legacy
WDI reader / catalog loader under ``leaders_db.ingest.wdi_io``
is reused internally via lazy imports -- the package boundary
at docs/architecture/sources.md §10.1 is preserved.

Tests cover the documented slice acceptance criteria:

- The WDI adapter descriptor is registerable / listable through
  the new :class:`InMemorySourceRegistry` and exposes the
  documented static metadata (source_id ``world_bank_wdi``,
  default version ``"World Bank API v2; cached indicator
  responses"``, attribution_key ``world_bank_wdi``, api type,
  1960+ coverage hint, both ``economic_country_year`` and
  ``social_country_year`` observation families, WDI v2 API
  homepage URL, requires_network=True).
- :class:`SourceIngestRunner` can run WDI end-to-end through the
  new registry against a fixture ``raw_root`` and produce
  :class:`NormalizedObservation` records (125 fixture
  observations round-tripped for the unfiltered run; 61 for
  ``years=(2023,)``; 24 for ``countries=('USA',)``; 12 for
  ``years=(2023,) + countries=('USA',)``).
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter internally
  reuses legacy parsing modules, but dispatch is registry-based).
- ``years=`` and ``countries=`` filters are honored and surface
  correct observation counts.
- ``years=(<1960,)`` returns zero observations plus a structured
  :class:`SourceWarning` (no stale-proxy fill -- SRC-COV-002 /
  SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- ``cache_policy="offline_only"`` / ``"prefer_cache"`` with
  explicit years and missing / incomplete cache fail readiness
  before ``read_raw`` / ``transform`` are called -- the new
  runner never silently hits the network.
- The readiness gate rejects the documented blockers: missing
  metadata, missing cache directory, missing / mismatched
  metadata ``source_version``, and unsupported request
  ``source_version``. The runner refuses to dispatch
  ``read_raw`` / ``transform`` for any blocker.
- Importing the new
  ``leaders_db.sources.adapters.world_bank_wdi`` module does NOT
  pull in any ``leaders_db.ingest`` module (SRC-MIG-007 +
  the import boundary documented in
  docs/architecture/sources.md §10.1).
- Canonical metadata version propagates consistently to
  ``RawAsset.version`` and every emitted
  ``NormalizedObservation.source_version``.

PASS-ELIGIBLE rationale
-----------------------
The legacy WDI reader / catalog loader are well-tested via the
existing ``tests/test_ingest_wdi.py`` suite. The tests in this
file prove that the new ``leaders_db.sources.adapters.world_bank_wdi``
adapter wraps the legacy parsing logic behind the unified
``SourceAdapter`` Protocol while preserving the
package-isolation contract -- they are PASS-ELIGIBLE because the
adapter implementation lands in the same change set.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    # Imported under TYPE_CHECKING so the annotations resolve
    # without binding module-level class references; tests that
    # need ``isinstance`` checks rebind ``SourceWarning`` /
    # ``ReadinessResult`` locally to dodge the
    # ``test_legacy_compatibility.py::fresh_legacy_import``
    # ``sys.modules`` purge that re-creates these classes.
    from leaders_db.sources import SourceIngestRequest
    from leaders_db.sources.contracts import (
        ReadinessResult,
    )

# Test-local constants. Mirrors the Maddison / PWT test files
# for consistency so future maintainers can read both slices
# side-by-side.
WDI_TEST_FIXTURE_CACHE_NAME: str = "cache"
WDI_TEST_METADATA_NAME: str = "metadata.json"
WDI_TEST_ATTRIBUTION_KEY: str = "world_bank_wdi"
WDI_TEST_DEFAULT_VERSION: str = (
    "World Bank API v2; cached indicator responses"
)
WDI_TEST_COVERAGE_START: int = 1960
WDI_TEST_HOMEPAGE_URL: str = "https://api.worldbank.org/v2/"
WDI_TEST_FAMILY_ECONOMIC: str = "economic_country_year"
WDI_TEST_FAMILY_SOCIAL: str = "social_country_year"
WDI_TEST_SUPPORTED_FAMILIES: tuple[str, ...] = (
    WDI_TEST_FAMILY_ECONOMIC,
    WDI_TEST_FAMILY_SOCIAL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyWDIAdapter:
    """Wrap a :class:`WDIAdapter` and record every lifecycle call.

    The spy forwards to the underlying adapter so the real
    behavior is exercised; it just records the call order so
    readiness-failure tests can assert the runner does NOT
    progress into ``read_raw`` / ``transform``.

    The wrapper exposes ``descriptor`` as a property so the
    registry's :meth:`register` (which keys off
    ``adapter.descriptor.source_id.slug``) works without
    touching the wrapped instance.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[str] = []

    @property
    def descriptor(self) -> Any:
        return self._inner.descriptor

    def check_ready(self, request: SourceIngestRequest) -> Any:
        self.calls.append("check_ready")
        return self._inner.check_ready(request)

    def read_raw(self, request: SourceIngestRequest) -> Any:
        self.calls.append("read_raw")
        return self._inner.read_raw(request)

    def transform(self, request: SourceIngestRequest, raw: Any) -> Any:
        self.calls.append("transform")
        return self._inner.transform(request, raw)


def _stage_wdi_bundle(
    raw_root: Path,
    *,
    source_version: str = WDI_TEST_DEFAULT_VERSION,
    include_cache: bool = True,
    omit_cache_dir: bool = False,
    include_indicator: str | None = None,
) -> Path:
    """Stage the canonical WDI fixture bundle under ``raw_root/world_bank_wdi``.

    Copies ``tests/fixtures/world_bank_wdi/cache/{2022,2023}/``
    into ``<raw_root>/world_bank_wdi/cache/`` and writes a
    well-formed ``metadata.json`` whose ``source_version``
    matches the canonical version stamp.

    Options:

    - ``source_version``: override the canonical version stamp
      in ``metadata.json``. Use to test mismatched-version
      blockers.
    - ``include_cache``: when False, omit the ``cache/``
      directory entirely. Use to test missing-cache blockers.
    - ``omit_cache_dir``: when True, stage the metadata but
      omit the cache directory (alias of ``include_cache=False``
      for clarity at call sites).
    - ``include_indicator``: when set, copy ONLY the named
      indicator's cache file (used to test incomplete-cache
      blockers).

    The fixture has 14 indicators x 2 years (2022, 2023); the
    legacy Stage 2 tests document the full set in
    ``src/leaders_db/ingest/catalogs/wdi.csv``. After
    aggregate filtering (AFE, ARB, WLD, etc.) the wide frame
    has 5 real countries x 14 indicators x 2 years = 140
    cells; 125 of those carry non-NaN values (some indicators
    miss countries, e.g. literacy rate has gaps for USA, SWE,
    NGA in 2023). The unfiltered runner produces 125
    :class:`NormalizedObservation` records.
    """
    bundle_dir = raw_root / WDI_TEST_ATTRIBUTION_KEY
    bundle_dir.mkdir(parents=True, exist_ok=True)
    cache_dst = bundle_dir / WDI_TEST_FIXTURE_CACHE_NAME

    copy_cache = include_cache and not omit_cache_dir
    if copy_cache:
        fixtures_cache = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / WDI_TEST_ATTRIBUTION_KEY
            / WDI_TEST_FIXTURE_CACHE_NAME
        )
        for year in ("2022", "2023"):
            src_year_dir = fixtures_cache / year
            dst_year_dir = cache_dst / year
            if include_indicator is not None:
                # Copy only the named indicator's cache file.
                dst_year_dir.mkdir(parents=True, exist_ok=True)
                src_file = src_year_dir / f"{include_indicator}.json"
                if src_file.exists():
                    shutil.copy2(src_file, dst_year_dir / src_file.name)
            elif src_year_dir.exists():
                shutil.copytree(src_year_dir, dst_year_dir)

    payload = {
        "source_name": "World Bank WDI",
        "source_version": source_version,
        "download_date": "2026-06-24",
        "coverage": (
            "Country-year economic + social indicators; "
            "1960-present (varies by indicator and country); "
            "API-backed with per-(year, indicator) JSON cache."
        ),
        "years_available": (
            "1960-2023+ (varies by indicator and country); "
            "local cache currently contains fixture/smoke years only"
        ),
        "license_note": (
            "CC BY 4.0 International; attribute World Bank "
            "WDI (World Bank 2024)."
        ),
        "local_files": [f"{WDI_TEST_FIXTURE_CACHE_NAME}/"],
        "ingestion_status": "downloaded",
        "source_url": WDI_TEST_HOMEPAGE_URL,
        # API source: per-response cache, not bundle checksum.
        "checksum_sha256": None,
        "checksum_note": (
            "API-backed source with per-response JSON cache "
            f"files under {WDI_TEST_FIXTURE_CACHE_NAME}/"
            "<year>/<indicator>.json; checksums are managed per "
            "cached response by the adapter/test fixtures rather "
            "than as one bundle checksum."
        ),
        "adapter": "leaders_db.ingest.wdi.ingest_wdi",
        "attribution": "World Bank WDI (World Bank 2024).",
    }
    (bundle_dir / WDI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_wdi_descriptor_exposes_documented_static_metadata() -> None:
    """The WDI descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "world_bank_wdi"``
    - ``display_name == "World Bank World Development Indicators"``
    - ``source_type == "api"``
    - ``default_version == "World Bank API v2; cached indicator responses"``
    - ``homepage_url`` is the canonical WDI v2 API base URL.
    - ``attribution_key == "world_bank_wdi"``
    - ``coverage_hint.start_year == 1960``,
      ``coverage_hint.end_year`` is None (open-ended 1960+).
    - ``supported_observation_families == ("economic_country_year",
      "social_country_year")``.
    - ``requires_manual_approval is False``,
      ``requires_network is True``.
    """
    from leaders_db.sources.adapters.world_bank_wdi import (
        build_world_bank_wdi_descriptor,
    )

    descriptor = build_world_bank_wdi_descriptor()

    assert descriptor.source_id.slug == WDI_TEST_ATTRIBUTION_KEY
    assert descriptor.display_name == (
        "World Bank World Development Indicators"
    )
    assert descriptor.source_type == "api"
    assert descriptor.default_version == WDI_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == WDI_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == WDI_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == WDI_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year is None
    assert descriptor.supported_observation_families == (
        WDI_TEST_SUPPORTED_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is True


def test_wdi_attribution_text_matches_attributions_doc() -> None:
    """The WDI attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical WDI citation block in
    ``docs/sources/attributions.md`` is the source of truth;
    the adapter module's constant must be byte-identical to a
    substring of that doc.
    """
    from leaders_db.sources.adapters.world_bank_wdi import (
        WORLD_BANK_WDI_ATTRIBUTION_TEXT,
    )

    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    assert attributions_path.exists(), (
        f"expected attributions doc at {attributions_path}"
    )
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert WORLD_BANK_WDI_ATTRIBUTION_TEXT in attributions_text, (
        f"{WORLD_BANK_WDI_ATTRIBUTION_TEXT!r} is not a substring "
        f"of {attributions_path}. Update both in the same "
        f"commit (Rule #15)."
    )


def test_wdi_attribution_text_matches_legacy_constant() -> None:
    """The WDI attribution text matches the legacy
    ``WDI_ATTRIBUTION`` constant byte-for-byte.

    Both constants are pulled from
    ``docs/sources/attributions.md`` (Rule #15); the legacy
    ``WDI_ATTRIBUTION`` lives in ``leaders_db.ingest.wdi_io``
    so callers can keep importing it from the legacy path.
    Drift between the new constant and the legacy constant
    would silently break Rule #15.
    """
    from leaders_db.ingest.wdi import WDI_ATTRIBUTION
    from leaders_db.sources.adapters.world_bank_wdi import (
        WORLD_BANK_WDI_ATTRIBUTION_TEXT,
    )

    assert WORLD_BANK_WDI_ATTRIBUTION_TEXT == WDI_ATTRIBUTION, (
        "the new WORLD_BANK_WDI_ATTRIBUTION_TEXT must be "
        "byte-identical to the legacy leaders_db.ingest.wdi."
        "WDI_ATTRIBUTION constant; both are pulled from "
        "docs/sources/attributions.md (Rule #15)."
    )


def test_wdi_adapter_satisfies_source_adapter_protocol() -> None:
    """``WDIAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or any
    of ``check_ready`` / ``read_raw`` / ``transform`` at
    construction time. The check is also enforced at adapter
    module import time; this test is the explicit assertion
    for downstream test suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    adapter = create_world_bank_wdi_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "world_bank_wdi"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_wdi_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_world_bank_wdi_adapter()`` produces an adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects duplicate
    slugs with ``ValueError`` (SRC-REG-004); the test asserts
    the WDI adapter registers cleanly under the
    ``world_bank_wdi`` slug and the descriptor is listable.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceId
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wdi_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "world_bank_wdi"

    resolved = registry.get_descriptor(SourceId(slug="world_bank_wdi"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="world_bank_wdi")) is adapter


def test_wdi_register_helper_registers_against_explicit_registry() -> None:
    """``register_world_bank_wdi(registry)`` is the explicit seam."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId
    from leaders_db.sources.adapters.world_bank_wdi import (
        register_world_bank_wdi,
    )

    registry = InMemorySourceRegistry()
    adapter = register_world_bank_wdi(registry)
    assert registry.get_adapter(SourceId(slug="world_bank_wdi")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_wdi_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives WDI through the
    documented lifecycle and emits :class:`NormalizedObservation`
    records.

    The fixture has 5 real countries (MEX, USA, SWE, IND, NGA)
    x 14 indicators x 2 years (2022, 2023). After aggregate
    filtering, the wide frame has 10 country-year rows;
    125 of the 140 (5 x 14 x 2) indicator cells carry
    non-NaN values (literacy rate, secondary enrollment, and a
    few others have data gaps for some countries). The
    unfiltered runner produces 125
    :class:`NormalizedObservation` records.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 125, (
        f"expected 125 observations (5 countries x 14 "
        f"indicators x 2 years minus null cells); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "world_bank_wdi"
        # Both supported families must be represented in the
        # 125-row fixture: economic_wellbeing has 10
        # indicators, social_wellbeing has 4.
        assert obs.observation_family in WDI_TEST_SUPPORTED_FAMILIES
        assert obs.year is not None
        assert obs.country_code is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        # Raw locator points at the staged cache file path.
        assert obs.raw_locator.path is not None
        assert WDI_TEST_FIXTURE_CACHE_NAME in obs.raw_locator.path
        # API endpoint template is set on the raw locator so
        # downstream audit code can resolve the canonical
        # WDI v2 URL for each indicator.
        assert obs.raw_locator.api_endpoint is not None
        assert obs.raw_locator.api_endpoint.startswith(
            WDI_TEST_HOMEPAGE_URL,
        )
        # The raw WDI indicator code is preserved as an
        # extension field (e.g. "NY.GDP.MKTP.CD").
        assert "wdi_raw_indicator_code" in obs.extension
        # Attribution is carried forward (Rule #15).
        assert obs.extension.get("attribution") is not None
        assert "World Bank" in str(
            obs.extension.get("attribution", ""),
        )


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_wdi_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives WDI through the new registry and never
    calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["world_bank_wdi"]``
    with a tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)`` executes
    the new WDI adapter lifecycle end-to-end.

    SRC-REG-003 / docs/architecture/sources.md §10.1: the new
    registry is the single dispatch surface; legacy dispatch
    is explicitly forbidden for the new runner.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wdi")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["world_bank_wdi"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_world_bank_wdi_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="world_bank_wdi"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 125

        # The legacy tracker must not have been called -- the
        # new runner routes through the new registry only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["world_bank_wdi"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_wdi_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2023,)`` filters to 2023 rows only.

    The 2023 fixture has 61 non-null observations across 5
    countries x 14 indicators (some indicators miss countries).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 61
    assert {obs.year for obs in result.observations} == {2023}


def test_wdi_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    USA has 13 non-null observations in 2022 + 12 in 2023
    (literacy rate and a few other indicators miss USA), so
    the USA-only total across both cached years is 25
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 25
    assert {obs.country_code for obs in result.observations} == {"USA"}


def test_wdi_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``years=(2023,) + countries=('USA',)`` filters to USA 2023 only.

    USA 2023 has 12 non-null indicator cells.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 12
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.year for obs in result.observations} == {2023}


# ---------------------------------------------------------------------------
# Out-of-coverage + unsupported filter
# ---------------------------------------------------------------------------


def test_wdi_out_of_coverage_year_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(1900,)`` returns zero observations + a structured
    :class:`SourceWarning` -- no stale-proxy fill.

    WDI covers 1960+ (SRC-COV-001). A request for 1900 falls
    outside the coverage envelope (SRC-COV-002) and MUST emit
    zero rows plus a structured warning (SRC-COV-003: no
    silent stale-proxy fill).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(1900,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "World Bank WDI covers 1960+; year=1900 must yield zero "
        "observations (no stale-proxy fill)."
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    ), (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )


def test_wdi_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Biden',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently
    ignoring the filter (SRC-REQ-005).

    The WDI transform does not consume leader identity; the
    filter is rejected explicitly so a developer can act on
    it without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        leaders=("Biden",),
    )
    result = runner.run(request)

    # All 125 fixture rows are still emitted (the filter does
    # not alter the row set; it just emits the warning).
    assert len(result.observations) == 125
    assert any(
        isinstance(w, SourceWarning) and w.code == "unsupported_filter"
        for w in result.warnings
    ), (
        "leaders filter must surface an UNSUPPORTED_FILTER "
        f"warning; got {result.warnings!r}"
    )


# ---------------------------------------------------------------------------
# Cache-policy behavior (offline-first contract)
# ---------------------------------------------------------------------------


def test_wdi_missing_cache_dir_fails_readiness_for_explicit_years(
    tmp_path: Path,
) -> None:
    """Missing ``cache/`` directory + explicit ``years=`` =>
    readiness blocker; runner does not progress.

    The new runner is offline / cache-first by default.
    For ``cache_policy="offline_only"`` / ``"prefer_cache"``
    with explicit years, missing cache fails readiness
    BEFORE ``read_raw`` / ``transform`` are called.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata but NO cache directory.
    _stage_wdi_bundle(raw_root, include_cache=False)

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False
    error_codes = [err.code for err in readiness.errors]
    assert "network_cache_unavailable" in error_codes, (
        "missing cache + explicit years + offline/cache policy "
        "must fail readiness with NETWORK_CACHE_UNAVAILABLE; "
        f"got {error_codes!r}"
    )

    # Runner does not progress past check_ready.
    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)
    assert "world_bank_wdi" in str(exc_info.value).lower()
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls


def test_wdi_incomplete_cache_fails_readiness_for_explicit_years(
    tmp_path: Path,
) -> None:
    """Incomplete cache (some indicator files missing) + explicit
    ``years=`` => readiness blocker; runner does not progress.

    The canonical WDI bundle has 14 indicator JSON files per
    year dir; staging only one indicator's cache file makes
    the cache incomplete and the readiness gate must refuse to
    dispatch.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the population cache file; the rest of the
    # 14 indicator cache files are missing.
    _stage_wdi_bundle(
        raw_root, include_indicator="SP.POP.TOTL",
    )

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False
    error_codes = [err.code for err in readiness.errors]
    assert "missing_raw" in error_codes, (
        "incomplete cache + explicit years must fail readiness "
        f"with MISSING_RAW; got {error_codes!r}"
    )

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls


def test_wdi_cache_complete_passes_readiness_with_explicit_years(
    tmp_path: Path,
) -> None:
    """Complete cache (all 14 indicators x explicit years) =>
    readiness passes.

    The full fixture stages all 14 indicator cache files for
    both 2022 and 2023, so ``years=(2023,)`` with the default
    ``offline_only`` policy passes readiness.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    real_adapter = create_world_bank_wdi_adapter()
    registry = InMemorySourceRegistry()
    registry.register(real_adapter)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        cache_policy="offline_only",
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 61


def test_wdi_no_year_filter_passes_readiness_without_cache_check(
    tmp_path: Path,
) -> None:
    """``years=None`` (all-years semantics) skips the cache gate.

    Per SRC-REQ-003, ``years=None`` means all available years
    in the source -- the runner enumerates the cache root at
    read time. The readiness gate does not gate the cache
    directory in that branch; the user accepts whatever the
    cache contains. We assert that a missing cache directory
    with ``years=None`` still passes readiness so the runner
    can emit zero observations (the cache read returns an
    empty wide frame).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata only -- no cache directory. With
    # ``years=None`` the runner should still pass readiness
    # and emit zero observations.
    _stage_wdi_bundle(raw_root, include_cache=False)

    real_adapter = create_world_bank_wdi_adapter()
    registry = InMemorySourceRegistry()
    registry.register(real_adapter)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="offline_only",
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert result.observations == ()


# ---------------------------------------------------------------------------
# Readiness failure path (Blocker 1 + Blocker 2)
#
# Each test below exercises one readiness blocker and asserts:
# 1. ``check_ready`` returns ``ready=False`` with a structured
#    ``SourceWarning`` whose ``severity == "error"`` lives in
#    ``ReadinessResult.errors`` (NOT ``warnings``).
# 2. The error message names the specific missing / invalid
#    artifact so a developer can act on it.
# 3. ``SourceIngestRunner.run(request)`` raises ``RuntimeError``
#    AND never invokes ``read_raw`` / ``transform`` on the
#    registered adapter (the spy records the call order).
# ---------------------------------------------------------------------------


def _assert_readiness_error_envelope(
    readiness: ReadinessResult,
    *,
    expected_code: str,
    expected_substring: str,
) -> None:
    """Assert the readiness-error contract shared by all blocker tests.

    A readiness blocker MUST:
    - return ``ready=False``;
    - surface exactly one structured ``SourceWarning`` in
      ``errors`` (NOT ``warnings``) with ``severity == "error"``;
    - carry the configured source id;
    - mention the missing / invalid artifact in the message so
      the developer can act on it.
    """
    # Local imports (not module-level) so the class identity
    # matches the ``SourceWarning`` instance the adapter just
    # produced -- ``test_legacy_compatibility.py``'s
    # ``fresh_legacy_import`` fixture purges ``leaders_db.*``
    # from ``sys.modules`` and re-imports everything, so
    # module-level imports here can point at stale class
    # objects.
    from leaders_db.sources import SourceId
    from leaders_db.sources.contracts import SourceWarning as _SW

    assert readiness.ready is False, (
        f"check_ready() must return ready=False for a blocker; "
        f"got {readiness!r}"
    )
    assert len(readiness.errors) == 1, (
        "exactly one structured error is expected; "
        f"got errors={readiness.errors!r}, "
        f"warnings={readiness.warnings!r}"
    )
    err = readiness.errors[0]
    assert isinstance(err, _SW), (
        f"expected SourceWarning; got {type(err).__name__}: {err!r}"
    )
    assert err.severity == "error", (
        f"blocker must have severity='error'; got {err.severity!r}"
    )
    assert err.code == expected_code, (
        f"blocker code must be {expected_code!r}; got {err.code!r}"
    )
    assert err.source_id == SourceId(slug="world_bank_wdi"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyWDIAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips ``read_raw`` / ``transform``."""
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    # The error names the source slug so callers can act on
    # it without reading source code.
    assert "world_bank_wdi" in str(exc_info.value).lower(), (
        f"runner RuntimeError must name the failing source slug; "
        f"got {exc_info.value!r}"
    )

    # Lifecycle ordering proof: ``check_ready`` ran (and
    # blocked); ``read_raw`` and ``transform`` did NOT.
    assert "read_raw" not in spy.calls, (
        "runner must short-circuit on ready=False before "
        "calling read_raw; "
        f"actual spy calls: {spy.calls!r}"
    )
    assert "transform" not in spy.calls, (
        "runner must short-circuit on ready=False before "
        "calling transform; "
        f"actual spy calls: {spy.calls!r}"
    )
    assert "check_ready" in spy.calls, (
        "check_ready must have been called at least once "
        "(either by the test directly or by the runner); "
        f"actual spy calls: {spy.calls!r}"
    )


def test_wdi_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='World Bank API v1')``
    against a canonical WDI bundle MUST fail readiness with a
    structured error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." The legacy bundle does not encode
    a per-version stamp beyond
    ``metadata.json['source_version']``; silently propagating
    an unsupported version into ``RawAsset.version`` /
    ``NormalizedObservation.source_version`` would lie to
    downstream scorers (Rule #6 / Rule #15).

    The test also asserts the runner raises ``RuntimeError``
    before invoking ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        WORLD_BANK_WDI_DEFAULT_VERSION,
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        source_version="World Bank API v1",
    )

    # Phase 1: the gate itself returns ready=False with a
    # structured error (severity='error', code='unsupported_version').
    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="World Bank API v1",
    )
    # The error message must name both the requested version
    # and the canonical version so the developer can re-run
    # without having to read source code.
    err = readiness.errors[0]
    assert WORLD_BANK_WDI_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{WORLD_BANK_WDI_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    # Phase 2: the runner refuses to dispatch.
    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_missing_metadata_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``metadata.json`` missing from the bundle => readiness
    blocker; runner does not progress.

    The error message must mention ``metadata`` so a developer
    can fix the upstream issue without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage the cache but no ``metadata.json`` -- mirrors a
    # bundle that has been copied but not yet documented.
    bundle_dir = raw_root / "world_bank_wdi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures_cache = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "world_bank_wdi"
        / "cache"
    )
    for year in ("2022", "2023"):
        src_year_dir = fixtures_cache / year
        if src_year_dir.exists():
            shutil.copytree(src_year_dir, bundle_dir / "cache" / year)

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_missing_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing metadata ``source_version`` is a readiness blocker.

    The unified WDI adapter must validate the bundle version
    before parsing so raw assets and observations cannot be
    labeled with an unknown or unsupported source version.
    The blocker carries the ``missing_metadata`` warning code
    (the legacy ``source_version`` is a required field; if it
    is absent, the required-fields blocker fires before the
    source-version mismatch check). The error message still
    names ``source_version`` so a developer can act on it.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)
    metadata_path = raw_root / "world_bank_wdi" / WDI_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("source_version")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_mismatched_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Metadata ``source_version`` must match the canonical
    ``"World Bank API v2; cached indicator responses"``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        WORLD_BANK_WDI_DEFAULT_VERSION,
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)
    metadata_path = raw_root / "world_bank_wdi" / WDI_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["source_version"] = "World Bank API v1"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="World Bank API v1",
    )
    assert WORLD_BANK_WDI_DEFAULT_VERSION in readiness.errors[0].message

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wdi import (
        WORLD_BANK_WDI_DEFAULT_VERSION,
        create_world_bank_wdi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle(raw_root)
    adapter = create_world_bank_wdi_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == WORLD_BANK_WDI_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version for observation in result.observations
    } == {WORLD_BANK_WDI_DEFAULT_VERSION}


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.world_bank_wdi must not
# import legacy
# ---------------------------------------------------------------------------


def test_wdi_adapter_module_does_not_import_legacy_ingest_at_import(
) -> None:
    """``import leaders_db.sources.adapters.world_bank_wdi`` MUST
    NOT import ``leaders_db.ingest`` at any depth (SRC-MIG-007
    + docs/architecture/sources.md §10.1).

    The test inspects the new module's source AST and asserts
    that the only ``leaders_db.ingest.*`` import statements
    are scoped inside function bodies (lazy imports), NOT at
    module top level. Module-level eager imports of
    ``leaders_db.ingest`` are forbidden because they would
    pull the legacy ingest package into ``sys.modules`` at
    package import time and break the documented boundary.

    The adapter MAY import legacy code lazily inside its
    methods; that path is exercised by the runner tests
    above and is the documented migration pattern. The AST
    check is deliberately non-destructive (no ``sys.modules``
    purge) so the test does not disturb SQLAlchemy ORM mapper
    state that later tests depend on.

    The full purge-and-reimport package-isolation check lives
    in ``tests/sources/test_import_boundary.py`` and now
    iterates ``leaders_db.sources.adapters.world_bank_wdi``
    as part of its canonical submodule list -- that test
    owns the ``sys.modules``-purge contract for the whole
    package.
    """
    import ast

    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "world_bank_wdi"
        / "adapter.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    legacy_top_level: list[str] = []
    legacy_nested: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("leaders_db.ingest"):
                    legacy_top_level.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("leaders_db.ingest"):
                legacy_top_level.append(f"from {module} import ...")

    def _scan_for_lazy(body: list[ast.stmt], scope: str) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name.startswith("leaders_db.ingest"):
                        legacy_nested.append(
                            f"{scope}: import {alias.name}",
                        )
            elif isinstance(stmt, ast.ImportFrom):
                module = stmt.module or ""
                if module.startswith("leaders_db.ingest"):
                    legacy_nested.append(
                        f"{scope}: from {module} import ...",
                    )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                scope = f"class {node.name}"
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    _scan_for_lazy(
                        item.body, f"{scope}.{item.name}",
                    )
                else:
                    _scan_for_lazy([item], scope)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            _scan_for_lazy(node.body, f"def {node.name}")

    assert legacy_top_level == [], (
        f"{module_path} has eager top-level legacy ingest "
        f"imports; the new WDI adapter must import legacy "
        f"code lazily inside methods only (SRC-MIG-007). "
        f"Found: {legacy_top_level}"
    )
    # Sanity: at least one nested lazy import must exist
    # (else the adapter would not work; the legacy reader /
    # catalog loader are reused).
    assert any(
        "from leaders_db.ingest.wdi_io" in entry
        for entry in legacy_nested
    ), (
        f"{module_path} must contain at least one nested lazy "
        f"import from leaders_db.ingest.wdi_io.*; got "
        f"{legacy_nested}"
    )


def test_wdi_package_import_does_not_register_legacy_wdi() -> None:
    """``import leaders_db.sources.adapters.world_bank_wdi``
    MUST NOT touch ``STAGE2_ADAPTERS["world_bank_wdi"]``.

    The legacy dispatch table is the legacy CLI's
    responsibility. Importing the new adapter module must
    leave the legacy registry untouched. This is the
    package-isolation guarantee for the legacy ``ingest`` seam.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import InMemorySourceRegistry
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
        register_world_bank_wdi,
    )

    # Snapshot the legacy slot BEFORE we touch the new package.
    sentinel_before = object()
    original = legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wdi")
    legacy_ingest.STAGE2_ADAPTERS["world_bank_wdi"] = sentinel_before
    try:
        # Create / register against the NEW registry -- this
        # must not mutate the legacy table.
        adapter = create_world_bank_wdi_adapter()
        new_registry = InMemorySourceRegistry()
        register_world_bank_wdi(new_registry)

        assert (
            legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wdi")
            is sentinel_before
        ), (
            "the new WDI adapter module must not mutate the "
            "legacy STAGE2_ADAPTERS table on import or factory call"
        )
        # The new registry carries world_bank_wdi; the legacy
        # table does NOT see the new adapter.
        assert (
            new_registry.list_descriptors()[0].source_id.slug
            == "world_bank_wdi"
        )
        assert (
            legacy_ingest.STAGE2_ADAPTERS["world_bank_wdi"]
            is sentinel_before
        )
        assert adapter.descriptor.source_id.slug == "world_bank_wdi"
    finally:
        legacy_ingest.STAGE2_ADAPTERS["world_bank_wdi"] = original


__all__ = [
    "WDI_TEST_ATTRIBUTION_KEY",
    "WDI_TEST_COVERAGE_START",
    "WDI_TEST_DEFAULT_VERSION",
    "WDI_TEST_FAMILY_ECONOMIC",
    "WDI_TEST_FAMILY_SOCIAL",
    "WDI_TEST_HOMEPAGE_URL",
    "WDI_TEST_METADATA_NAME",
    "WDI_TEST_SUPPORTED_FAMILIES",
    "test_wdi_adapter_is_registerable_through_in_memory_registry",
    "test_wdi_adapter_module_does_not_import_legacy_ingest_at_import",
    "test_wdi_adapter_satisfies_source_adapter_protocol",
    "test_wdi_attribution_text_matches_attributions_doc",
    "test_wdi_attribution_text_matches_legacy_constant",
    "test_wdi_cache_complete_passes_readiness_with_explicit_years",
    "test_wdi_combined_year_and_country_filter",
    "test_wdi_country_filter_is_applied",
    "test_wdi_descriptor_exposes_documented_static_metadata",
    "test_wdi_incomplete_cache_fails_readiness_for_explicit_years",
    "test_wdi_leader_filter_emits_unsupported_filter_warning",
    "test_wdi_mismatched_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wdi_missing_cache_dir_fails_readiness_for_explicit_years",
    "test_wdi_missing_metadata_fails_readiness_and_blocks_runner",
    "test_wdi_missing_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wdi_no_year_filter_passes_readiness_without_cache_check",
    "test_wdi_out_of_coverage_year_returns_zero_and_warning",
    "test_wdi_package_import_does_not_register_legacy_wdi",
    "test_wdi_register_helper_registers_against_explicit_registry",
    "test_wdi_runner_does_not_consult_legacy_stage2_adapters",
    "test_wdi_runner_produces_normalized_observations",
    "test_wdi_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_wdi_year_filter_is_applied",
]
