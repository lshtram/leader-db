"""Phase C / D slice -- World Bank WGI adapter under the unified
``leaders_db.sources`` interface.

The World Bank WGI adapter is the fourth source rebuilt under
the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 4,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT 10.01,
Maddison Project Database 2023, and World Bank WDI.

The legacy WGI reader / transform under ``leaders_db.ingest.wgi``
and ``leaders_db.ingest.wgi_io`` is reused internally via lazy
imports -- the package boundary at docs/architecture/sources.md
§10.1 is preserved.

Tests cover the documented slice acceptance criteria:

- The WGI adapter descriptor is registerable / listable through
  the new :class:`InMemorySourceRegistry` and exposes the
  documented static metadata.
- The WGI descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``world_bank_wgi``,
  default version ``"Worldwide Governance Indicators 2023
  Update (data through 2022)"``, attribution_key
  ``world_bank_wgi``, dataset type, 1996-2022 coverage hint,
  ``governance_country_year`` observation family, WGI
  homepage URL).
- :class:`SourceIngestRunner` can run WGI end-to-end through
  the new registry against a fixture ``raw_root`` and produce
  :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter internally
  reuses legacy parsing modules, but dispatch is registry-based).
- ``years=`` and ``countries=`` filters are honored and surface
  correct observation counts.
- An out-of-coverage ``years=(2023,)`` request returns zero
  observations plus a structured :class:`SourceWarning` (no
  stale-proxy fill -- SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- The bundle readiness gate accepts BOTH the canonical primary
  metadata shape (PWT / Maddison / WDI convention:
  ``source_version`` / ``checksum_sha256`` / ``local_files`` /
  ``license_note`` / ``coverage``) AND the legacy WGI shape
  (``version`` / ``sha256`` / ``local_file`` / ``license`` /
  ``coverage_start_year`` + ``coverage_end_year``).
- Readiness-failure paths block the runner BEFORE ``read_raw``
  / ``transform`` for missing metadata, missing xlsx, checksum
  mismatch, missing metadata ``source_version``, mismatched
  metadata ``source_version``, and unsupported request
  ``source_version``.
- Canonical metadata ``source_version`` propagates consistently
  to ``RawAsset.version`` and every emitted
  ``NormalizedObservation.source_version``.
- Importing the new ``leaders_db.sources.adapters.world_bank_wgi``
  module does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  docs/architecture/sources.md §10.1).

PASS-ELIGIBLE rationale
-----------------------
The legacy WGI reader / transform are well-tested via the
existing ``tests/test_ingest_wgi.py`` suite. The tests in this
file prove that the new ``leaders_db.sources.adapters.world_bank_wgi``
adapter wraps the legacy parsing logic behind the unified
:class:`SourceAdapter` Protocol while preserving the
package-isolation contract -- they are PASS-ELIGIBLE because the
adapter implementation lands in the same change set.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from leaders_db.sources import SourceIngestRequest
    from leaders_db.sources.contracts import ReadinessResult


WGI_TEST_FIXTURE_XLSX: str = "wgidataset.xlsx"
WGI_TEST_METADATA_NAME: str = "metadata.json"
WGI_TEST_ATTRIBUTION_KEY: str = "world_bank_wgi"
WGI_TEST_DEFAULT_VERSION: str = (
    "Worldwide Governance Indicators 2023 Update (data through 2022)"
)
WGI_TEST_COVERAGE_START: int = 1996
WGI_TEST_COVERAGE_END: int = 2022
WGI_TEST_FAMILY: str = "governance_country_year"
WGI_TEST_HOMEPAGE_URL: str = "https://info.worldbank.org/governance/wgi/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyWGIAdapter:
    """Wrap a :class:`WGIAdapter` and record every lifecycle call.

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

    def transform(
        self, request: SourceIngestRequest, raw: Any,
    ) -> Any:
        self.calls.append("transform")
        return self._inner.transform(request, raw)


def _stage_wgi_bundle(raw_root: Path) -> Path:
    """Stage the canonical WGI fixture bundle under ``raw_root/world_bank_wgi``.

    Copies ``tests/fixtures/world_bank_wgi/sample.xlsx`` into
    ``<raw_root>/world_bank_wgi/wgidataset.xlsx`` and writes a
    well-formed ``metadata.json`` (LEGACY shape: ``version`` /
    ``sha256`` / ``local_file`` / ``license`` /
    ``coverage_start_year`` + ``coverage_end_year``) whose
    ``sha256`` matches the staged xlsx bytes. Returns the
    resolved bundle directory.

    The fixture carries 5 countries (MEX, USA, SWE, IND, NGA)
    x 2 years (2021, 2022) x 6 indicators. The single
    ``#N/A`` cell is MEX 2021 ``wgi_political_stability``;
    the remaining 59 cells are real WGI values.
    """
    bundle_dir = raw_root / "world_bank_wgi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "world_bank_wgi"
    fixture_xlsx = fixtures / "sample.xlsx"
    shutil.copy2(fixture_xlsx, bundle_dir / WGI_TEST_FIXTURE_XLSX)
    sha = hashlib.sha256(
        (bundle_dir / WGI_TEST_FIXTURE_XLSX).read_bytes(),
    ).hexdigest()
    # Legacy-shape metadata: matches the staged
    # ``data/raw/world_bank_wgi/metadata.json`` so we exercise
    # the legacy-key codepath documented in
    # ``docs/architecture/sources.md`` §3.
    payload = {
        "source_key": "world_bank_wgi",
        "source_name": "World Bank Worldwide Governance Indicators",
        "source_url": (
            "https://www.worldbank.org/content/dam/sites/"
            "govindicators/doc/wgidataset.xlsx"
        ),
        "canonical_page": WGI_TEST_HOMEPAGE_URL,
        "local_file": WGI_TEST_FIXTURE_XLSX,
        "download_date": "2026-06-18",
        "version": WGI_TEST_DEFAULT_VERSION,
        "license": "CC BY 4.0 International",
        "coverage_start_year": WGI_TEST_COVERAGE_START,
        "coverage_end_year": WGI_TEST_COVERAGE_END,
        "sha256": sha,
        "bytes": (bundle_dir / WGI_TEST_FIXTURE_XLSX).stat().st_size,
        "ingestion_status": "downloaded",
    }
    (bundle_dir / WGI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


def _stage_wgi_bundle_primary_shape(raw_root: Path) -> Path:
    """Stage a WGI bundle with the canonical PRIMARY metadata shape.

    Used by tests that explicitly exercise the primary shape
    (``source_version`` / ``checksum_sha256`` / ``local_files``
    / ``license_note`` / ``coverage``). The readiness gate
    must accept BOTH shapes (canonical + legacy) without
    rewriting the existing staged bundle metadata.
    """
    bundle_dir = raw_root / "world_bank_wgi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "world_bank_wgi"
    fixture_xlsx = fixtures / "sample.xlsx"
    shutil.copy2(fixture_xlsx, bundle_dir / WGI_TEST_FIXTURE_XLSX)
    sha = hashlib.sha256(
        (bundle_dir / WGI_TEST_FIXTURE_XLSX).read_bytes(),
    ).hexdigest()
    payload = {
        "source_name": "World Bank Worldwide Governance Indicators",
        "source_version": WGI_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-18",
        "coverage": "1996-2022",
        "years_available": "1996-2022",
        "license_note": "CC BY 4.0 International",
        "local_files": [WGI_TEST_FIXTURE_XLSX],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://www.worldbank.org/content/dam/sites/"
            "govindicators/doc/wgidataset.xlsx"
        ),
        "checksum_sha256": sha,
    }
    (bundle_dir / WGI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_wgi_descriptor_exposes_documented_static_metadata() -> None:
    """The WGI descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "world_bank_wgi"``
    - ``display_name == "World Bank Worldwide Governance Indicators"``
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical metadata stamp.
    - ``homepage_url`` is the canonical WGI governance page.
    - ``attribution_key == "world_bank_wgi"``
    - ``coverage_hint.start_year == 1996``,
      ``coverage_hint.end_year == 2022``.
    - ``supported_observation_families == ("governance_country_year",)``.
    - ``requires_network is False`` (local-file only).

    PASS-ELIGIBLE: the descriptor factory ships with the slice.
    """
    from leaders_db.sources.adapters.world_bank_wgi import (
        build_world_bank_wgi_descriptor,
    )

    descriptor = build_world_bank_wgi_descriptor()

    assert descriptor.source_id.slug == "world_bank_wgi"
    assert descriptor.display_name == (
        "World Bank Worldwide Governance Indicators"
    )
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == WGI_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == WGI_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == WGI_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == WGI_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year == WGI_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == (WGI_TEST_FAMILY,)
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_wgi_attribution_text_matches_attributions_doc() -> None:
    """The WGI attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical WGI citation block in
    ``docs/sources/attributions.md`` is the source of truth; the
    adapter module's constant must be byte-identical to a
    substring of that doc. Also asserts the constant matches the
    legacy ``WGI_ATTRIBUTION`` byte-for-byte (consistency guard).
    """
    from leaders_db.ingest.wgi_io import WGI_ATTRIBUTION
    from leaders_db.sources.adapters.world_bank_wgi import (
        WORLD_BANK_WGI_ATTRIBUTION_TEXT,
    )

    assert WORLD_BANK_WGI_ATTRIBUTION_TEXT == WGI_ATTRIBUTION, (
        "Unified WGI attribution must be byte-identical to the "
        "legacy WGI_ATTRIBUTION constant in "
        "src/leaders_db/ingest/wgi_io.py."
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
    assert WORLD_BANK_WGI_ATTRIBUTION_TEXT in attributions_text, (
        f"{WORLD_BANK_WGI_ATTRIBUTION_TEXT!r} is not a substring "
        f"of {attributions_path}. Update both in the same commit "
        f"(Rule #15)."
    )


def test_wgi_adapter_satisfies_source_adapter_protocol() -> None:
    """``WGIAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or any of
    ``check_ready`` / ``read_raw`` / ``transform`` at construction
    time. The check is also enforced at adapter module import
    time; this test is the explicit assertion for downstream test
    suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    adapter = create_world_bank_wgi_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "world_bank_wgi"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_wgi_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_world_bank_wgi_adapter()`` produces an adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects duplicate
    slugs with ``ValueError`` (SRC-REG-004); the test asserts the
    WGI adapter registers cleanly under the ``world_bank_wgi``
    slug and the descriptor is listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_world_bank_wgi_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "world_bank_wgi"

    resolved = registry.get_descriptor(SourceId(slug="world_bank_wgi"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="world_bank_wgi")) is adapter


def test_wgi_register_helper_registers_against_explicit_registry() -> None:
    """``register_world_bank_wgi(registry)`` is the explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        register_world_bank_wgi,
    )

    registry = InMemorySourceRegistry()
    adapter = register_world_bank_wgi(registry)
    assert registry.get_adapter(SourceId(slug="world_bank_wgi")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_wgi_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives WGI through the
    documented lifecycle and emits :class:`NormalizedObservation`
    records.

    The fixture has 5 countries x 2 years x 6 indicators, with
    one ``#N/A`` cell at MEX 2021 ``wgi_political_stability``.
    The unfiltered run emits 60 - 1 = 59 observations.

    Per-country totals (after the MEX 2021 #N/A skip):

    - MEX 2021: 5 (6 indicators - 1 #N/A)
    - MEX 2022: 6
    - USA 2021: 6
    - USA 2022: 6
    - SWE 2021: 6
    - SWE 2022: 6
    - IND 2021: 6
    - IND 2022: 6
    - NGA 2021: 6
    - NGA 2022: 6

    Total: 5 + 6*9 = 59.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 59, (
        f"expected 59 observations (5*2*6 - 1 #N/A); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "world_bank_wgi"
        assert obs.observation_family == WGI_TEST_FAMILY
        assert obs.year is not None
        assert obs.country_code is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        # Every observation's raw_locator carries the per-
        # indicator sheet name (canonical xlsx sheet name).
        assert obs.raw_locator.sheet is not None
        # row_number is intentionally None because the legacy
        # wide frame loses the xlsx row index through the
        # long-to-wide pivot (no fabricated locators).
        assert obs.raw_locator.row_number is None

    # Per-country totals.
    by_country: dict[str, int] = {}
    for obs in result.observations:
        by_country[obs.country_code] = (
            by_country.get(obs.country_code, 0) + 1
        )
    assert by_country == {
        "MEX": 11,  # 5 + 6
        "USA": 12,
        "SWE": 12,
        "IND": 12,
        "NGA": 12,
    }


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_wgi_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives WGI through the new registry and never
    calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["world_bank_wgi"]``
    with a tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)`` executes
    the new WGI adapter lifecycle end-to-end.

    SRC-REG-003 / docs/architecture/sources.md §10.1: the new
    registry is the single dispatch surface; legacy dispatch is
    explicitly forbidden for the new runner.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    # Replace the legacy ``world_bank_wgi`` slot with a
    # tracker that records every invocation. The runner must
    # never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wgi")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["world_bank_wgi"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_world_bank_wgi_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="world_bank_wgi"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 59

        # The legacy tracker must not have been called -- the
        # new runner routes through the new registry only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["world_bank_wgi"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_wgi_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2022,)`` filters to 2022 rows only.

    Per-row 2022 totals: 5 countries x 6 indicators = 30 observations
    (no #N/A cells in 2022).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(2022,),
    )
    result = runner.run(request)
    assert len(result.observations) == 30
    assert {obs.year for obs in result.observations} == {2022}


def test_wgi_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    Per-country USA totals: 2 years x 6 indicators = 12 observations
    (no #N/A cells for USA).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 12
    assert {obs.country_code for obs in result.observations} == {"USA"}


def test_wgi_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``years=(2022,) + countries=('USA',)`` filters to USA 2022 only.

    Per-row USA 2022 totals: 6 cells (one per WGI indicator).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(2022,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 6
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.year for obs in result.observations} == {2022}


# ---------------------------------------------------------------------------
# Out-of-coverage + unsupported filter
# ---------------------------------------------------------------------------


def test_wgi_out_of_coverage_year_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(2023,)`` returns zero observations + a structured
    :class:`SourceWarning` -- no stale-proxy fill.

    WGI covers 1996-2022 (SRC-COV-001). A request for 2023
    falls outside the coverage envelope (SRC-COV-002) and MUST
    emit zero rows plus a structured warning (SRC-COV-003: no
    silent stale-proxy fill).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "WGI covers 1996-2022; year=2023 must yield zero "
        "observations (no stale-proxy fill)."
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    ), (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )


def test_wgi_out_of_coverage_year_before_window_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(1995,)`` returns zero observations + YEAR_ABSENT
    warning (pre-coverage year).

    Same out-of-coverage contract as the post-coverage branch:
    years < 1996 (the WGI coverage start) emit zero rows plus
    a structured YEAR_ABSENT warning. No stale-proxy fill.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(1995,),
    )
    result = runner.run(request)

    assert result.observations == ()
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    )


def test_wgi_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Biden',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently ignoring
    the filter (SRC-REQ-005).

    The WGI transform does not consume leader identity; the
    filter is rejected explicitly so a developer can act on it
    without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        leaders=("Biden",),
    )
    result = runner.run(request)

    # All 59 fixture rows are still emitted (the filter does not
    # alter the row set; it just emits the warning).
    assert len(result.observations) == 59
    assert any(
        isinstance(w, SourceWarning) and w.code == "unsupported_filter"
        for w in result.warnings
    ), (
        "leaders filter must surface an UNSUPPORTED_FILTER "
        f"warning; got {result.warnings!r}"
    )


# ---------------------------------------------------------------------------
# Readiness failure paths (every blocker names the missing field)
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
    from leaders_db.sources import SourceId
    from leaders_db.sources.contracts import SourceWarning as _SW

    assert readiness.ready is False, (
        f"check_ready() must return ready=False for a blocker; "
        f"got {readiness!r}"
    )
    assert len(readiness.errors) == 1, (
        "exactly one structured error is expected; "
        f"got errors={readiness.errors!r}, warnings={readiness.warnings!r}"
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
    assert err.source_id == SourceId(slug="world_bank_wgi"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyWGIAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips ``read_raw`` / ``transform``."""
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    # The error names the source slug so callers can act on it
    # without reading source code.
    assert "world_bank_wgi" in str(exc_info.value).lower(), (
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


def test_wgi_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='9999')`` against a
    canonical WGI bundle MUST fail readiness with a structured
    error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." The legacy bundle has no per-version
    stamp beyond ``metadata.json['version']``; silently
    propagating an unsupported version into
    ``RawAsset.version`` / ``NormalizedObservation.source_version``
    would lie to downstream scorers (Rule #6 / Rule #15).

    The test also asserts the runner raises ``RuntimeError``
    before invoking ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        WORLD_BANK_WGI_DEFAULT_VERSION,
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        source_version="9999",
    )

    # Phase 1: the gate itself returns ready=False with a
    # structured error (severity='error', code='unsupported_version').
    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    # The error message must name both the requested version and
    # the canonical version so the developer can re-run without
    # having to read source code.
    err = readiness.errors[0]
    assert WORLD_BANK_WGI_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{WORLD_BANK_WGI_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    # Phase 2: the runner refuses to dispatch.
    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_missing_metadata_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``metadata.json`` missing from the bundle => readiness
    blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the xlsx (no ``metadata.json``) -- mirrors
    # the legacy missing-metadata contract.
    bundle_dir = raw_root / "world_bank_wgi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "world_bank_wgi"
    shutil.copy2(fixtures / "sample.xlsx", bundle_dir / WGI_TEST_FIXTURE_XLSX)

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_missing_xlsx_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``wgidataset.xlsx`` missing from the bundle => readiness
    blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage a valid legacy-shape ``metadata.json`` but omit the xlsx.
    bundle_dir = raw_root / "world_bank_wgi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_key": "world_bank_wgi",
        "source_name": "World Bank Worldwide Governance Indicators",
        "source_url": (
            "https://www.worldbank.org/content/dam/sites/"
            "govindicators/doc/wgidataset.xlsx"
        ),
        "canonical_page": WGI_TEST_HOMEPAGE_URL,
        "local_file": WGI_TEST_FIXTURE_XLSX,
        "download_date": "2026-06-18",
        "version": WGI_TEST_DEFAULT_VERSION,
        "license": "CC BY 4.0 International",
        "coverage": "1996-2022",
        "sha256": "0" * 64,  # placeholder; not verified since xlsx is absent
        "ingestion_status": "downloaded",
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_raw",
        expected_substring="wgidataset.xlsx",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_checksum_mismatch_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A wrong ``sha256`` in ``metadata.json`` => readiness
    blocker; runner does not progress.

    The test mutates the legacy ``sha256`` field (NOT the
    canonical ``checksum_sha256``) so we explicitly exercise
    the legacy-key codepath.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)

    # Mutate the well-formed bundle's ``sha256`` (legacy
    # key) to a value that does not match the staged xlsx
    # bytes. The readiness gate recomputes the SHA-256 on
    # the xlsx and must reject the request.
    bad_path = raw_root / "world_bank_wgi" / "metadata.json"
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    payload["sha256"] = "0" * 64
    bad_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_missing_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing metadata ``version`` (legacy) is a readiness blocker.

    The unified WGI adapter must validate the bundle version before
    parsing so raw assets and observations cannot be labeled with an
    unknown or unsupported source version.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)
    metadata_path = raw_root / "world_bank_wgi" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("version")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_mismatched_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Metadata ``version`` must match the canonical WGI stamp."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        WORLD_BANK_WGI_DEFAULT_VERSION,
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)
    metadata_path = raw_root / "world_bank_wgi" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["version"] = "9999"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_world_bank_wgi_adapter()
    spy = _SpyWGIAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    assert WORLD_BANK_WGI_DEFAULT_VERSION in readiness.errors[0].message

    _assert_runner_does_not_progress(registry, request, spy)


def test_wgi_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations.

    The unified WGI adapter must label every RawAsset.version
    and every NormalizedObservation.source_version with the
    validated canonical version stamp
    (``"Worldwide Governance Indicators 2023 Update (data
    through 2022)"``), not arbitrary metadata / request text.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        WORLD_BANK_WGI_DEFAULT_VERSION,
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle(raw_root)
    adapter = create_world_bank_wgi_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(2022,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == WORLD_BANK_WGI_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version for observation in result.observations
    } == {WORLD_BANK_WGI_DEFAULT_VERSION}


def test_wgi_primary_shape_bundle_is_accepted_by_readiness(
    tmp_path: Path,
) -> None:
    """The readiness gate accepts the canonical PRIMARY metadata shape.

    The staged ``data/raw/world_bank_wgi/metadata.json`` uses
    the legacy shape (``version`` / ``sha256`` / ``local_file``
    / ``license``); this test stages the canonical primary
    shape (``source_version`` / ``checksum_sha256`` /
    ``local_files`` / ``license_note`` / ``coverage``) and
    asserts the readiness gate accepts both. This guards
    against future bundle migrations to the primary shape.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_wgi_bundle_primary_shape(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wgi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="world_bank_wgi"),
        raw_root=raw_root,
        years=(2022,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 30


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.world_bank_wgi must not
# import legacy
# ---------------------------------------------------------------------------


def test_wgi_adapter_module_does_not_import_legacy_ingest_at_import() -> None:
    """``import leaders_db.sources.adapters.world_bank_wgi`` MUST
    NOT import ``leaders_db.ingest`` at any depth (SRC-MIG-007 +
    docs/architecture/sources.md §10.1).

    The test inspects every WGI adapter source module's AST
    and asserts that the only ``leaders_db.ingest.*`` import
    statements are scoped inside function bodies (lazy
    imports), NOT at module top level. Module-level eager
    imports of ``leaders_db.ingest`` are forbidden because they
    would pull the legacy ingest package into ``sys.modules``
    at package import time and break the documented boundary.

    The adapter MAY import legacy code lazily inside its
    methods; that path is exercised by the runner tests above
    and is the documented migration pattern. The AST check is
    deliberately non-destructive (no ``sys.modules`` purge) so
    the test does not disturb SQLAlchemy ORM mapper state that
    later tests depend on.

    The full purge-and-reimport package-isolation check lives
    in ``tests/sources/test_import_boundary.py`` and now
    iterates ``leaders_db.sources.adapters.world_bank_wgi`` as
    part of its canonical submodule list -- that test owns the
    ``sys.modules``-purge contract for the whole package.
    """
    legacy_top_level, legacy_nested = (
        _scan_wgi_package_for_legacy_ingest_imports(
            _wgi_adapter_package_dir(),
        )
    )

    assert legacy_top_level == [], (
        f"{_wgi_adapter_package_dir()} has eager top-level "
        f"legacy ingest imports; the new WGI adapter must "
        f"import legacy code lazily inside methods only "
        f"(SRC-MIG-007). Found: {legacy_top_level}"
    )
    # Sanity: at least one nested lazy import must exist (else
    # the adapter would not work; the legacy reader / transform
    # are reused).
    assert any(
        "from leaders_db.ingest.wgi_xlsx" in entry
        for _, entry in legacy_nested
    ), (
        f"{_wgi_adapter_package_dir()} must contain at least "
        f"one nested lazy import from leaders_db.ingest.wgi_xlsx; "
        f"got {legacy_nested}"
    )


def _wgi_adapter_package_dir() -> Path:
    """Return the resolved WGI adapter package directory."""
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "world_bank_wgi"
    )


def _scan_wgi_package_for_legacy_ingest_imports(
    package_dir: Path,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Walk every .py file in the WGI adapter package and return
    ``(legacy_top_level, legacy_nested)`` import pairs.

    The lazy-import location (currently in ``_raw_read.py``,
    NOT in ``adapter.py``) is detected regardless of the
    module split. Each tuple carries ``(module_path_str,
    import_label)`` so a failure message names the file.
    """
    legacy_top_level: list[tuple[str, str]] = []
    legacy_nested: list[tuple[str, str]] = []

    for module_path in sorted(package_dir.glob("*.py")):
        module_path_str = str(module_path)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        _record_top_level_legacy_ingest_imports(
            tree.body,
            module_path_str,
            legacy_top_level,
        )
        _record_nested_legacy_ingest_imports(
            tree.body,
            module_path_str,
            legacy_nested,
        )

    return legacy_top_level, legacy_nested


def _record_top_level_legacy_ingest_imports(
    body: list[ast.stmt],
    module_path_str: str,
    legacy_top_level: list[tuple[str, str]],
) -> None:
    """Scan top-level ``body`` for module-scope legacy ingest imports."""
    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("leaders_db.ingest"):
                    legacy_top_level.append(
                        (
                            module_path_str,
                            f"import {alias.name}",
                        ),
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("leaders_db.ingest"):
                legacy_top_level.append(
                    (
                        module_path_str,
                        f"from {module} import ...",
                    ),
                )


def _record_nested_legacy_ingest_imports(
    body: list[ast.stmt],
    module_path_str: str,
    legacy_nested: list[tuple[str, str]],
) -> None:
    """Scan class / function bodies for lazy legacy ingest imports."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            _scan_class_body(
                node,
                module_path_str,
                legacy_nested,
            )
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            _scan_class_function_body(
                node.body,
                f"def {node.name}",
                module_path_str,
                legacy_nested,
            )


def _scan_class_body(
    class_node: ast.ClassDef,
    module_path_str: str,
    legacy_nested: list[tuple[str, str]],
) -> None:
    """Scan every item in a class body for nested legacy imports."""
    for item in class_node.body:
        scope = f"class {class_node.name}"
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_class_function_body(
                item.body,
                f"{scope}.{item.name}",
                module_path_str,
                legacy_nested,
            )
        else:
            _scan_class_function_body(
                [item],
                scope,
                module_path_str,
                legacy_nested,
            )


def _scan_class_function_body(
    body: list[ast.stmt],
    scope: str,
    module_path_str: str,
    legacy_nested: list[tuple[str, str]],
) -> None:
    """Walk a single function / class body for legacy ingest imports.

    Pass ``module_path_str`` explicitly so the closure does
    not depend on the surrounding loop variable (avoids the
    ruff ``B023`` false-positive at lint time).
    """
    for stmt in body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name.startswith("leaders_db.ingest"):
                    legacy_nested.append(
                        (
                            module_path_str,
                            f"{scope}: import {alias.name}",
                        ),
                    )
        elif isinstance(stmt, ast.ImportFrom):
            module = stmt.module or ""
            if module.startswith("leaders_db.ingest"):
                legacy_nested.append(
                    (
                        module_path_str,
                        f"{scope}: from {module} import ...",
                    ),
                )


def test_wgi_package_import_does_not_register_legacy_wgi() -> None:
    """``import leaders_db.sources.adapters.world_bank_wgi``
    MUST NOT touch ``STAGE2_ADAPTERS["world_bank_wgi"]``.

    The legacy dispatch table is the legacy CLI's
    responsibility. Importing the new adapter module must leave
    the legacy registry untouched. This is the
    package-isolation guarantee for the legacy ``ingest`` seam.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import InMemorySourceRegistry
    from leaders_db.sources.adapters.world_bank_wgi import (
        create_world_bank_wgi_adapter,
        register_world_bank_wgi,
    )

    sentinel_before = object()
    original = legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wgi")
    legacy_ingest.STAGE2_ADAPTERS["world_bank_wgi"] = sentinel_before
    try:
        adapter = create_world_bank_wgi_adapter()
        new_registry = InMemorySourceRegistry()
        register_world_bank_wgi(new_registry)

        assert (
            legacy_ingest.STAGE2_ADAPTERS.get("world_bank_wgi")
            is sentinel_before
        ), (
            "the new WGI adapter module must not mutate the "
            "legacy STAGE2_ADAPTERS table on import or factory call"
        )
        assert (
            new_registry.list_descriptors()[0].source_id.slug
            == "world_bank_wgi"
        )
        assert (
            legacy_ingest.STAGE2_ADAPTERS["world_bank_wgi"]
            is sentinel_before
        )
        assert adapter.descriptor.source_id.slug == "world_bank_wgi"
    finally:
        legacy_ingest.STAGE2_ADAPTERS["world_bank_wgi"] = original


__all__ = [
    "WGI_TEST_ATTRIBUTION_KEY",
    "WGI_TEST_COVERAGE_END",
    "WGI_TEST_COVERAGE_START",
    "WGI_TEST_DEFAULT_VERSION",
    "WGI_TEST_FAMILY",
    "WGI_TEST_FIXTURE_XLSX",
    "WGI_TEST_HOMEPAGE_URL",
    "WGI_TEST_METADATA_NAME",
    "test_wgi_adapter_is_registerable_through_in_memory_registry",
    "test_wgi_adapter_module_does_not_import_legacy_ingest_at_import",
    "test_wgi_adapter_satisfies_source_adapter_protocol",
    "test_wgi_attribution_text_matches_attributions_doc",
    "test_wgi_checksum_mismatch_fails_readiness_and_blocks_runner",
    "test_wgi_combined_year_and_country_filter",
    "test_wgi_country_filter_is_applied",
    "test_wgi_descriptor_exposes_documented_static_metadata",
    "test_wgi_leader_filter_emits_unsupported_filter_warning",
    "test_wgi_mismatched_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wgi_missing_metadata_fails_readiness_and_blocks_runner",
    "test_wgi_missing_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_wgi_missing_xlsx_fails_readiness_and_blocks_runner",
    "test_wgi_out_of_coverage_year_before_window_returns_zero_and_warning",
    "test_wgi_out_of_coverage_year_returns_zero_and_warning",
    "test_wgi_package_import_does_not_register_legacy_wgi",
    "test_wgi_primary_shape_bundle_is_accepted_by_readiness",
    "test_wgi_register_helper_registers_against_explicit_registry",
    "test_wgi_runner_does_not_consult_legacy_stage2_adapters",
    "test_wgi_runner_produces_normalized_observations",
    "test_wgi_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_wgi_year_filter_is_applied",
]
