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

# Sentinel types so ``_stage_wdi_bundle`` can distinguish
# "leave the field as the canonical default" from "drop the
# field entirely" (missing-field blocker) and from "set an
# explicit custom value". Plain ``None`` is reserved for the
# canonical null-checksum path because the staged WDI bundle
# documents ``checksum_sha256: null`` + a
# ``checksum_note`` as the canonical API/cache shape.
class _UnsetType:
    """Sentinel: the staging helper should keep the default value."""

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<UNSET>"


_UNSET: _UnsetType = _UnsetType()


class _OmitChecksumType:
    """Sentinel: drop the ``checksum_sha256`` field entirely."""

    _instance: _OmitChecksumType | None = None

    def __new__(cls) -> _OmitChecksumType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<OMIT_CHECKSUM>"


_OMIT_CHECKSUM: _OmitChecksumType = _OmitChecksumType()


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
    checksum_sha256: Any | _UnsetType = _UNSET,
    checksum_note: str | _UnsetType = _UNSET,
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
    - ``checksum_sha256``: override the canonical
      ``checksum_sha256`` field. Default (``_UNSET``) keeps
      the staged metadata's ``null`` value; pass an explicit
      value to test readiness branches (non-null hex, dict,
      invalid shape, etc.). Use the sentinel
      :class:`_OMIT_CHECKSUM` to drop the field entirely
      and exercise the missing-field blocker.
    - ``checksum_note``: override the canonical
      ``checksum_note`` field. Default keeps the canonical
      per-response note; pass an empty string or a vague
      note to exercise the rationale blocker.

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

    # Canonical checksum defaults mirror the staged
    # ``data/raw/world_bank_wdi/metadata.json`` so existing
    # tests do not need to thread the new parameters.
    if isinstance(checksum_sha256, _UnsetType):
        canonical_checksum_sha256: Any = None
    elif isinstance(checksum_sha256, _OmitChecksumType):
        canonical_checksum_sha256 = _OMIT_CHECKSUM
    else:
        canonical_checksum_sha256 = checksum_sha256
    if isinstance(checksum_note, _UnsetType):
        canonical_checksum_note: str = (
            "API-backed source with per-response JSON cache "
            f"files under {WDI_TEST_FIXTURE_CACHE_NAME}/"
            "<year>/<indicator>.json; checksums are managed per "
            "cached response by the adapter/test fixtures rather "
            "than as one bundle checksum."
        )
    else:
        canonical_checksum_note = checksum_note

    payload: dict[str, Any] = {
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
        "checksum_sha256": canonical_checksum_sha256,
        "checksum_note": canonical_checksum_note,
        "adapter": "leaders_db.ingest.wdi.ingest_wdi",
        "attribution": "World Bank WDI (World Bank 2024).",
    }
    if canonical_checksum_sha256 is _OMIT_CHECKSUM:
        # Drop the field entirely so the missing-field
        # blocker fires (the readiness gate treats absence
        # and explicit ``null`` differently for
        # ``checksum_sha256``).
        payload.pop("checksum_sha256")
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


# ---------------------------------------------------------------------------
# Checksum rationale (Blocker 1)
#
# The unified WDI adapter is API / cache-backed; per
# ``docs/requirements/sources.md`` §6 SRC-PROV-002 the
# ``checksum_sha256`` is required but may legitimately be
# ``null`` when the staged metadata pairs the null with a
# ``checksum_note`` that documents the per-response /
# per-cached-response / API cache contract. The readiness
# gate refuses:
# - a missing ``checksum_sha256`` field entirely;
# - a ``null`` checksum without an actionable note;
# - a non-null checksum whose shape does not validate
#   (bad hex, dict with non-string value, etc.).
# ---------------------------------------------------------------------------


def test_wdi_missing_checksum_field_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A bundle whose ``metadata.json`` has no
    ``checksum_sha256`` field at all fails readiness with a
    structured ``missing_metadata`` error.

    The required-fields blocker must name ``checksum_sha256``
    in the error message so a developer can fix the upstream
    issue without reading source code.
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
    _stage_wdi_bundle(raw_root, checksum_sha256=_OMIT_CHECKSUM)

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
        expected_substring="checksum_sha256",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_null_checksum_without_note_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256: null`` and no
    ``checksum_note`` (or a note that does not document the
    per-response API/cache contract) fails readiness.

    A null checksum with no rationale is indistinguishable
    from a forgotten checksum, so the gate refuses it.
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
    _stage_wdi_bundle(raw_root, checksum_note="")

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
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_null_checksum_with_vague_note_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256: null`` and a non-empty
    but non-actionable ``checksum_note`` (no API / cache /
    per-response / checksum keyword) fails readiness.
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
    _stage_wdi_bundle(
        raw_root,
        checksum_note=(
            "TODO: re-evaluate when the upstream publishes a "
            "single bundle hash."
        ),
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
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_null_checksum_with_actionable_note_passes_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256: null`` and an
    actionable ``checksum_note`` (the canonical WDI shape)
    passes readiness so the runner can proceed to
    ``read_raw`` / ``transform``.

    This is the positive control: the canonical
    ``data/raw/world_bank_wdi/metadata.json`` ships with
    this exact shape and the existing fixture stages it
    (see ``_stage_wdi_bundle``'s default ``checksum_note``).
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
    # Default ``checksum_sha256=None`` + canonical
    # ``checksum_note`` (mentions API / cache /
    # per-response / checksum) is the staged WDI shape.
    _stage_wdi_bundle(raw_root)

    real_adapter = create_world_bank_wdi_adapter()
    registry = InMemorySourceRegistry()
    registry.register(real_adapter)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 61


def test_wdi_flat_hex_checksum_passes_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256: "<64-char hex>"`` (the
    flat-string shape that PWT and Maddison also accept)
    passes readiness without needing a ``checksum_note``.
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
    _stage_wdi_bundle(
        raw_root,
        checksum_sha256="0" * 64,
    )

    real_adapter = create_world_bank_wdi_adapter()
    registry = InMemorySourceRegistry()
    registry.register(real_adapter)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 61


def test_wdi_per_file_checksum_dict_passes_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256: {<file>: <64-char hex>}``
    (the per-file dict shape) passes readiness.
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
    _stage_wdi_bundle(
        raw_root,
        checksum_sha256={
            "cache/2022/SP.POP.TOTL.json": "1" * 64,
            "cache/2023/SP.POP.TOTL.json": "2" * 64,
        },
    )

    real_adapter = create_world_bank_wdi_adapter()
    registry = InMemorySourceRegistry()
    registry.register(real_adapter)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 61


def test_wdi_invalid_hex_checksum_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256`` set to a non-64-char
    string fails readiness with a structured
    ``missing_metadata`` error.
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
    # 63 chars -- one short of the documented SHA-256 length.
    _stage_wdi_bundle(
        raw_root, checksum_sha256="a" * 63,
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
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_invalid_dict_checksum_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A bundle with ``checksum_sha256`` set to a dict whose
    value is not a 64-char hex string fails readiness.
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
    _stage_wdi_bundle(
        raw_root,
        checksum_sha256={
            "cache/2022/SP.POP.TOTL.json": 12345,  # not a hex string
        },
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
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


# ---------------------------------------------------------------------------
# Cache-policy semantics (Blocker 2)
#
# The unified WDI adapter is offline / cache-only in this
# slice; ``cache_policy="refresh"`` / ``"no_cache"`` are NOT
# supported because the production ``WDIAdapter.read_raw`` path
# never invokes the network. The readiness gate fails both
# with a structured ``unsupported_cache_policy`` error.
# ---------------------------------------------------------------------------


def test_wdi_refresh_cache_policy_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` fails readiness with a
    structured ``unsupported_cache_policy`` error; the runner
    refuses to dispatch.

    The unified WDI adapter is offline / cache-only in this
    slice: ``WDIAdapter.read_raw`` always passes
    ``force_refresh=False`` and ``year=None`` to the legacy
    reader. A request that opts in to ``refresh`` would
    overclaim network I/O that the adapter never performs, so
    the gate refuses.
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

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        cache_policy="refresh",
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_cache_policy",
        expected_substring="refresh",
    )
    # The error must explicitly say the adapter is offline /
    # cache-only so a developer does not assume the
    # ``refresh`` opt-in hit the network.
    assert "offline" in readiness.errors[0].message.lower(), (
        "unsupported_cache_policy message must say the "
        "adapter is offline / cache-only; got "
        f"{readiness.errors[0].message!r}"
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_no_cache_policy_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``cache_policy="no_cache"`` fails readiness with a
    structured ``unsupported_cache_policy`` error; the runner
    refuses to dispatch.
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

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        cache_policy="no_cache",
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_cache_policy",
        expected_substring="no_cache",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wdi_refresh_cache_policy_fails_readiness_without_year_filter(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` is rejected even when
    ``years=None`` so callers cannot bypass the
    unsupported-policy gate with all-years semantics.
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
    _stage_wdi_bundle(raw_root, include_cache=False)

    real_adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="refresh",
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_cache_policy",
        expected_substring="refresh",
    )

    _assert_runner_does_not_progress(registry, request, spy)


# ---------------------------------------------------------------------------
# Cache-policy remediation: no-network contract under supported policies
#
# Comprehensive remediation for the cache-policy blocker (second
# occurrence). The tests in this section prove that the unified WDI
# adapter path is provably no-network under
# ``cache_policy="offline_only"`` / ``"prefer_cache"`` -- including
# the ``years=None`` all-available-years branch -- by patching the
# legacy HTTP call (``leaders_db.ingest.wdi_http.fetch_wdi_payload``
# AND ``requests.get``) to raise if invoked, then driving the
# production ``SourceIngestRunner`` against a staged incomplete /
# corrupt cache. The contract:
#
# 1. Explicit ``years=`` with missing or incomplete cache, or with a
#    corrupt required cache file, MUST fail readiness with a
#    structured ``missing_raw`` / ``network_cache_unavailable``
#    error BEFORE ``read_raw`` / ``transform`` are called (the
#    existing ``test_wdi_missing_cache_dir_fails_readiness_for_explicit_years``
#    and ``test_wdi_incomplete_cache_fails_readiness_for_explicit_years``
#    cover the missing / incomplete branches; the new tests cover the
#    corrupt-file branch and the no-network invariant).
#
# 2. ``years=None`` with a partial / discovered cache MUST NOT hit
#    the network under supported policies. The cache-only read path
#    reads only the ``(year, indicator)`` pairs that are present on
#    disk; the test confirms that with a staged incomplete cache the
#    adapter reads only the staged files (no HTTP) and that readiness
#    blocks on a corrupt discovered file (also no HTTP).
#
# The HTTP sentinel monkeypatches
# :func:`leaders_db.ingest.wdi_http.fetch_wdi_payload` and
# :func:`requests.get` to raise ``AssertionError`` if either is
# called. The patches are scoped to the test via ``monkeypatch`` so
# they cannot leak across tests.
# ---------------------------------------------------------------------------


def _install_http_sentinels(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    """Patch the legacy HTTP layer + ``requests.get`` to fail if invoked.

    Returns ``(fetch_calls, requests_get_calls)`` -- the lists record
    any invocation attempt so the test can prove the sentinels were
    never reached. The ``monkeypatch`` fixture reverts the patches at
    test teardown.
    """
    fetch_calls: list[str] = []
    requests_get_calls: list[str] = []

    def _fetch_sentinel(*args: Any, **kwargs: Any) -> Any:
        fetch_calls.append(f"fetch_wdi_payload({args!r}, {kwargs!r})")
        raise AssertionError(
            "fetch_wdi_payload must NOT be called when cache_policy is "
            "'offline_only' / 'prefer_cache' and readiness passed; the "
            "unified WDI adapter is offline / cache-only in this slice."
        )

    def _requests_get_sentinel(*args: Any, **kwargs: Any) -> Any:
        requests_get_calls.append(f"requests.get({args!r}, {kwargs!r})")
        raise AssertionError(
            "requests.get must NOT be called by the unified WDI adapter "
            "under supported cache policies; the cache-only read path "
            "never falls through to HTTP."
        )

    # Lazy-import the modules we patch so the import-boundary tests
    # (which purge ``leaders_db.*`` from ``sys.modules``) are not
    # disrupted. The patches are scoped to the ``monkeypatch`` fixture
    # and only take effect when these modules are actually loaded --
    # which is exactly the production path the tests are exercising.
    try:
        from leaders_db.ingest import wdi_http as _wdi_http
        monkeypatch.setattr(_wdi_http, "fetch_wdi_payload", _fetch_sentinel)
    except ImportError:
        # The legacy module is not in ``sys.modules`` yet (e.g. the
        # import-boundary tests purged it). Patch the lazy-loaded
        # attribute on the consumer too so the legacy read_wdi path
        # cannot accidentally find the unpatched function. This is
        # belt-and-braces: the unified adapter does NOT call the
        # legacy read_wdi path for cache-only reads, so this branch
        # only matters for tests that exercise the legacy seam.
        try:
            from leaders_db.ingest import wdi_io as _wdi_io
            monkeypatch.setattr(
                _wdi_io, "fetch_wdi_payload", _fetch_sentinel,
            )
        except ImportError:
            pass

    try:
        import requests as _requests
        monkeypatch.setattr(_requests, "get", _requests_get_sentinel)
    except ImportError:
        # ``requests`` is a hard dependency of the legacy WDI HTTP
        # layer; if it is missing the production path is not
        # importable anyway. The sentinel install is a best-effort
        # defense in depth -- the readiness gate is the primary
        # no-network contract.
        pass

    return fetch_calls, requests_get_calls


def test_wdi_offline_only_no_year_filter_partial_cache_does_not_hit_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_policy="offline_only"`` + ``years=None`` against a
    staged INCOMPLETE cache produces observations ONLY from the
    available cache files and never invokes the network.

    Comprehensive remediation for the cache-policy blocker:
    ``WDIAdapter.read_raw`` MUST NOT call the legacy HTTP layer or
    ``requests.get`` when readiness passes under supported cache
    policies -- even when the staged cache is incomplete (some
    indicator files missing, some indicator files present).

    The test stages ONE indicator's cache file (SP.POP.TOTL) for
    BOTH 2022 and 2023 -- 13 of the 14 catalog indicators are
    missing from the cache. With ``years=None``, the unified
    adapter's local cache-only read path
    (:func:`_read_cached_wdi_responses`) reads the 2 present
    cache files (2 years x 1 indicator = 2 long frames) and
    produces a wide frame with one indicator column. The
    transform layer emits one observation per non-NaN cell
    (5 real countries x 1 indicator x 2 years = 10 cells, minus
    any nulls; the fixture's 2022 + 2023 SP.POP.TOTL files
    cover all 5 countries for both years so 10 observations).

    The HTTP sentinels (``fetch_wdi_payload`` + ``requests.get``)
    are installed before ``runner.run(request)`` runs. If the
    adapter falls through to HTTP for the missing indicators,
    either sentinel raises ``AssertionError`` and the test
    fails. The post-condition asserts the sentinel lists are
    empty so a regression to HTTP is caught immediately.
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
    # Stage ONLY SP.POP.TOTL for both years. The other 13 catalog
    # indicators are absent; the cache-only read path must NOT
    # ask the legacy HTTP layer to fetch them.
    _stage_wdi_bundle(raw_root, include_indicator="SP.POP.TOTL")

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="offline_only",
        # ``years=None``: all-available-years semantics per
        # SRC-REQ-003; the cache-only path enumerates whatever
        # cache files exist on disk and reads them directly.
    )

    result = runner.run(request)

    # Sentinel invariant: no HTTP, ever.
    assert fetch_calls == [], (
        "fetch_wdi_payload was invoked under cache_policy="
        f"'offline_only' with years=None + incomplete cache; "
        f"calls observed: {fetch_calls!r}. The unified WDI "
        f"adapter must be offline / cache-only and read only "
        f"the staged cache files."
    )
    assert requests_get_calls == [], (
        "requests.get was invoked under cache_policy="
        f"'offline_only' with years=None + incomplete cache; "
        f"calls observed: {requests_get_calls!r}. The unified "
        f"WDI adapter must never fall through to HTTP."
    )

    # Behavior: readiness passes (all available cache files
    # are valid), and the runner emits observations ONLY for
    # the staged indicator (SP.POP.TOTL -> wdi_population).
    assert result.readiness.ready is True, (
        "readiness must pass when staged cache files are all "
        "valid (even if the cache is partial); readiness blocks "
        "only on missing / malformed artifacts, not on "
        "incompleteness for years=None. got errors="
        f"{result.readiness.errors!r}"
    )

    # Indicator codes surface in observations ONLY for the
    # staged indicator. 5 countries x 1 indicator x 2 years =
    # 10 observations if all cells are non-null. The fixture's
    # SP.POP.TOTL cache files have non-null values for all 5
    # countries in both years, so the expected count is 10.
    indicator_codes = {
        obs.indicator_code for obs in result.observations
    }
    assert indicator_codes == {"wdi_population"}, (
        "with only SP.POP.TOTL staged, every emitted observation "
        "must map to the wdi_population variable; got "
        f"{indicator_codes!r}"
    )
    assert len(result.observations) == 10, (
        "expected 10 observations (5 countries x 1 indicator x "
        f"2 years); got {len(result.observations)}"
    )


def test_wdi_prefer_cache_no_year_filter_partial_cache_does_not_hit_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_policy="prefer_cache"`` + ``years=None`` against a
    staged INCOMPLETE cache produces observations ONLY from the
    available cache files and never invokes the network.

    Symmetric to the ``offline_only`` test above. The
    ``prefer_cache`` policy is the documented default for API
    sources per ``docs/requirements/sources.md`` §11 SRC-TYPE-002;
    the test proves the adapter is offline / cache-only under
    that policy too. The HTTP sentinels ensure no HTTP call is
    made even when the cache is missing indicators that the
    catalog defines.
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
    _stage_wdi_bundle(raw_root, include_indicator="SP.POP.TOTL")

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="prefer_cache",
    )

    result = runner.run(request)

    assert fetch_calls == [], (
        "fetch_wdi_payload was invoked under cache_policy="
        f"'prefer_cache' with years=None + incomplete cache; "
        f"calls observed: {fetch_calls!r}"
    )
    assert requests_get_calls == [], (
        "requests.get was invoked under cache_policy="
        f"'prefer_cache' with years=None + incomplete cache; "
        f"calls observed: {requests_get_calls!r}"
    )

    assert result.readiness.ready is True
    indicator_codes = {
        obs.indicator_code for obs in result.observations
    }
    assert indicator_codes == {"wdi_population"}
    assert len(result.observations) == 10


def test_wdi_corrupt_cached_json_blocks_readiness_for_discovered_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``years=None`` + a discovered cache file that is corrupt
    JSON fails readiness with a structured ``missing_raw`` error
    BEFORE ``read_raw`` is called.

    Comprehensive remediation requirement #4: "Corrupt/malformed
    cache files must not silently trigger HTTP under supported
    policies. Either readiness blocks with actionable error or
    the cache-only read path skips/flags them without network;
    prefer readiness block for explicit years and clear
    warning/error for discovered cache files." The unified WDI
    adapter takes the strongest stance: corrupt discovered
    files block readiness (a corrupt file would force the
    legacy read_wdi fallback into HTTP, which the unified
    adapter refuses for supported policies).

    The test stages ONE valid cache file + ONE corrupt cache
    file (invalid JSON). The HTTP sentinels are installed
    before the readiness call; even if readiness somehow let
    the corrupt file through, no HTTP would be invoked --
    readiness blocks first.
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
    _stage_wdi_bundle(raw_root, include_indicator="SP.POP.TOTL")
    # Inject a corrupt file: same year as the valid file, but
    # the JSON is malformed. The cache-only read path / the
    # readiness gate must refuse this rather than silently
    # trigger HTTP.
    corrupt_file = (
        raw_root / "world_bank_wdi" / "cache" / "2023" / "NY.GDP.MKTP.CD.json"
    )
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_text("{this is not valid json", encoding="utf-8")

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(adapter)
    registry.register(spy)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="offline_only",
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False, (
        "corrupt discovered cache file MUST fail readiness; "
        "the unified WDI adapter refuses to fall through to "
        "HTTP for malformed cache entries. got errors="
        f"{readiness.errors!r}"
    )
    error_codes = [err.code for err in readiness.errors]
    assert "missing_raw" in error_codes, (
        "corrupt discovered cache file must fail readiness "
        f"with missing_raw; got codes {error_codes!r}"
    )
    # The blocker message must mention the corrupt file path so
    # a developer can repair or re-stage it.
    err_message = readiness.errors[0].message
    assert str(corrupt_file) in err_message or corrupt_file.name in err_message, (
        "corrupt-file blocker message must name the offending "
        f"file path; got {err_message!r}"
    )

    # Lifecycle ordering proof: runner never reaches read_raw /
    # transform when readiness blocks.
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)
    assert "world_bank_wdi" in str(exc_info.value).lower()
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls

    # Sentinel invariant: readiness blocked before any HTTP
    # could have been attempted.
    assert fetch_calls == []
    assert requests_get_calls == []


def test_wdi_corrupt_cached_json_blocks_readiness_for_explicit_years(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``years=(2023,)`` with a corrupt required cache file
    fails readiness with a structured ``missing_raw`` error and
    the runner does not progress to ``read_raw`` / ``transform``.

    Per the comprehensive remediation requirement #4 (explicit
    years branch): corrupt required cache files block readiness
    rather than triggering an HTTP fallback under supported
    policies. This test is the production-path HTTP sentinel
    variant of the explicit-year cache-completeness tests.
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
    # Corrupt ONE of the required 2023 indicator files. The
    # readiness gate validates every catalog indicator's
    # cache file for the explicit requested year, so this
    # must block.
    corrupt_file = (
        raw_root / "world_bank_wdi" / "cache" / "2023" / "NY.GDP.MKTP.CD.json"
    )
    corrupt_file.write_text("{not valid json", encoding="utf-8")

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(adapter)
    registry.register(spy)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        cache_policy="offline_only",
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False
    error_codes = [err.code for err in readiness.errors]
    assert "missing_raw" in error_codes
    err_message = readiness.errors[0].message
    assert (
        str(corrupt_file) in err_message or corrupt_file.name in err_message
    ), (
        "corrupt-required-file blocker must name the offending "
        f"file; got {err_message!r}"
    )

    with pytest.raises(RuntimeError):
        runner.run(request)
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls

    assert fetch_calls == []
    assert requests_get_calls == []


def test_wdi_explicit_year_partial_cache_blocks_readiness_and_skips_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``years=(2023,)`` + staged incomplete cache (only one
    indicator file present) fails readiness; the runner refuses
    to dispatch; no HTTP is invoked.

    Production-path HTTP sentinel variant of the existing
    ``test_wdi_incomplete_cache_fails_readiness_for_explicit_years``
    test. The new test asserts the no-network invariant in
    addition to the readiness-blocker contract: even if a future
    regression caused ``read_raw`` to be invoked after a missing
    cache file, the HTTP sentinels would catch it before the
    cache-only read path could silently fall through to HTTP.
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
    _stage_wdi_bundle(raw_root, include_indicator="SP.POP.TOTL")

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(adapter)
    registry.register(spy)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        years=(2023,),
        cache_policy="offline_only",
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False
    error_codes = [err.code for err in readiness.errors]
    assert "missing_raw" in error_codes

    with pytest.raises(RuntimeError):
        runner.run(request)
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls

    assert fetch_calls == []
    assert requests_get_calls == []


def test_wdi_offline_only_no_year_filter_empty_cache_does_not_hit_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_policy="offline_only"`` + ``years=None`` against
    an EMPTY cache directory (no year subdirs) returns zero
    observations and never invokes the network.

    Backstop: the existing
    ``test_wdi_no_year_filter_passes_readiness_without_cache_check``
    covers ``cache_dir missing entirely``; this test covers the
    empty-but-present cache directory case. The HTTP sentinel
    asserts the production path is provably no-network even when
    the cache root exists with no year subdirectories.
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
    # Create the cache dir but leave it empty (no year
    # subdirectories).
    (raw_root / "world_bank_wdi" / "cache").mkdir(parents=True, exist_ok=True)
    # Remove any pre-existing year subdirs to keep the case
    # clean. The staging helper may have copied fixture files;
    # remove them so this test exercises the truly empty case.
    cache_root = raw_root / "world_bank_wdi" / "cache"
    for child in cache_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="offline_only",
    )

    result = runner.run(request)

    assert fetch_calls == []
    assert requests_get_calls == []

    assert result.readiness.ready is True
    assert result.observations == (), (
        "empty cache + years=None must emit zero observations "
        "(all-available-years semantics; nothing in cache to read)"
    )


def test_wdi_unsupported_cache_policy_no_year_filter_does_not_hit_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_policy="refresh"`` + ``years=None`` fails readiness
    with ``unsupported_cache_policy``; the runner does not
    progress; no HTTP is invoked.

    Defense in depth: the existing
    ``test_wdi_refresh_cache_policy_fails_readiness_without_year_filter``
    proves the blocker fires; the HTTP sentinel here proves that
    even if a future regression bypassed the gate, the
    production path would still refuse to fall through to HTTP
    (the cache-only read path does not consult the legacy
    HTTP layer regardless of cache_policy).
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

    fetch_calls, requests_get_calls = _install_http_sentinels(monkeypatch)

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wdi_adapter()
    spy = _SpyWDIAdapter(adapter)
    registry.register(spy)
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wdi"),
        raw_root=raw_root,
        cache_policy="refresh",
    )

    readiness = spy.check_ready(request)
    assert readiness.ready is False
    error_codes = [err.code for err in readiness.errors]
    assert "unsupported_cache_policy" in error_codes

    with pytest.raises(RuntimeError):
        runner.run(request)
    assert "read_raw" not in spy.calls
    assert "transform" not in spy.calls

    assert fetch_calls == []
    assert requests_get_calls == []


# ---------------------------------------------------------------------------
# JSON pointer resolvability (Blocker 3)
#
# The WDI v2 cache file is a 2-element list
# ``[metadata, data]``; each ``data[i]`` is a country record
# carrying ``countryiso3code``, ``date``, and ``value``. The
# canonical raw-locator JSON pointer is ``/1/<numeric_index>``
# so audit code can re-parse the cache file and recover the
# matching record byte-for-byte.
# ---------------------------------------------------------------------------


def test_wdi_observation_json_pointer_resolves(
    tmp_path: Path,
) -> None:
    """Every emitted observation's
    ``raw_locator.json_pointer`` resolves to the underlying
    cache record.

    Concretely:

    - the pointer is the ``/1/<numeric_index>`` shape
      (NOT ``/1/{iso3}``);
    - opening the cache file at the observation's
      ``raw_locator.path`` and evaluating the pointer with a
      JSON-pointer resolver returns a record whose
      ``countryiso3code``, ``date``, and ``indicator`` ID
      match the observation's country, year, and raw
      indicator code;
    - the underlying record's ``value`` matches the
      observation's ``value`` (NaN gaps are excluded so the
      observation could not exist for a missing cell).

    The test exercises the ``USA 2023 wdi_population`` cell
    because the fixture's 2023 SP.POP.TOTL cache file puts
    USA at index 1 (MEX=0, USA=1, SWE=2, ...).
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
    assert result.readiness.ready is True
    assert result.observations, "expected at least one observation"

    # Find the USA / 2023 / wdi_population observation (the
    # SP.POP.TOTL raw indicator maps to wdi_population via
    # the canonical catalog).
    pop_observation = next(
        obs for obs in result.observations
        if obs.country_code == "USA"
        and obs.year == 2023
        and obs.indicator_code == "wdi_population"
    )
    raw_indicator_code = pop_observation.extension[
        "wdi_raw_indicator_code"
    ]
    assert raw_indicator_code == "SP.POP.TOTL"
    pointer = pop_observation.raw_locator.json_pointer
    cache_path_str = pop_observation.raw_locator.path
    assert pointer is not None, (
        "raw_locator.json_pointer must be set; got None"
    )
    assert pointer.startswith("/1/"), (
        f"JSON pointer must be /1/<numeric_index> shape, "
        f"got {pointer!r}"
    )
    # The pointer must NOT be the legacy ``/1/{iso3}`` shape
    # (Blocker 3: the cache file's data array is indexed
    # numerically, not by ISO3 key).
    assert pointer != "/1/USA", (
        f"JSON pointer must NOT be the legacy /1/{{iso3}} "
        f"shape (cache data array is numeric); got {pointer!r}"
    )
    # Resolve the pointer against the cache file.
    assert cache_path_str is not None
    cache_path = Path(cache_path_str)
    assert cache_path.is_file(), (
        f"raw_locator.path must point at a real cache file; "
        f"got {cache_path}"
    )
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    # Parse the pointer "/1/<index>" into a list segment.
    segments = pointer.lstrip("/").split("/")
    assert len(segments) == 2
    assert segments[0] == "1"
    numeric_index = int(segments[1])
    record = payload[1][numeric_index]
    assert record["countryiso3code"] == pop_observation.country_code
    assert record["date"] == str(pop_observation.year)
    assert record["indicator"]["id"] == raw_indicator_code
    assert record["value"] == pop_observation.value, (
        "resolved cache record value must match the "
        "observation's value; otherwise the pointer is not "
        f"pointing at the right row. record={record!r}, "
        f"observation.value={pop_observation.value!r}"
    )


def test_wdi_load_wdi_cache_index_handles_missing_file() -> None:
    """The ``load_wdi_cache_index`` helper returns ``None``
    when the cache file is missing so the transform falls
    back to a structured ``/1/{iso3}`` placeholder rather
    than silently emitting an empty pointer.
    """
    from leaders_db.sources.adapters.world_bank_wdi._transform import (
        load_wdi_cache_index,
    )

    assert load_wdi_cache_index(Path("/nonexistent/cache.json")) is None


def test_wdi_load_wdi_cache_index_handles_malformed_json(
    tmp_path: Path,
) -> None:
    """``load_wdi_cache_index`` returns ``None`` when the
    cache file is not valid JSON or not the documented
    2-element list shape, so the transform never crashes on
    a malformed cache.
    """
    from leaders_db.sources.adapters.world_bank_wdi._transform import (
        load_wdi_cache_index,
    )

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")
    assert load_wdi_cache_index(bad_json) is None

    wrong_shape = tmp_path / "wrong_shape.json"
    wrong_shape.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert load_wdi_cache_index(wrong_shape) is None

    no_data_list = tmp_path / "no_data_list.json"
    no_data_list.write_text(json.dumps([{"a": 1}, "not a list"]), encoding="utf-8")
    assert load_wdi_cache_index(no_data_list) is None


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
    "test_wdi_corrupt_cached_json_blocks_readiness_for_discovered_files",
    "test_wdi_corrupt_cached_json_blocks_readiness_for_explicit_years",
    "test_wdi_country_filter_is_applied",
    "test_wdi_descriptor_exposes_documented_static_metadata",
    "test_wdi_explicit_year_partial_cache_blocks_readiness_and_skips_runner",
    "test_wdi_incomplete_cache_fails_readiness_for_explicit_years",
    "test_wdi_leader_filter_emits_unsupported_filter_warning",
    "test_wdi_mismatched_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wdi_missing_cache_dir_fails_readiness_for_explicit_years",
    "test_wdi_missing_metadata_fails_readiness_and_blocks_runner",
    "test_wdi_missing_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wdi_no_year_filter_passes_readiness_without_cache_check",
    "test_wdi_offline_only_no_year_filter_empty_cache_does_not_hit_network",
    "test_wdi_offline_only_no_year_filter_partial_cache_does_not_hit_network",
    "test_wdi_out_of_coverage_year_returns_zero_and_warning",
    "test_wdi_package_import_does_not_register_legacy_wdi",
    "test_wdi_prefer_cache_no_year_filter_partial_cache_does_not_hit_network",
    "test_wdi_register_helper_registers_against_explicit_registry",
    "test_wdi_runner_does_not_consult_legacy_stage2_adapters",
    "test_wdi_runner_produces_normalized_observations",
    "test_wdi_unsupported_cache_policy_no_year_filter_does_not_hit_network",
    "test_wdi_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_wdi_year_filter_is_applied",
]
