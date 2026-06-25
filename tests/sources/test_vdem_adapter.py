"""Phase C / D slice -- V-Dem adapter under the unified
``leaders_db.sources`` interface.

V-Dem (Varieties of Democracy) v16 is the fifth source
rebuilt under the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 5,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI, and
World Bank WGI. The legacy V-Dem reader / transform under
``leaders_db.ingest.vdem`` and ``leaders_db.ingest.vdem_io``
is reused internally via lazy imports -- the package
boundary at docs/architecture/sources.md §10.1 is preserved.

Tests cover the documented slice acceptance criteria:

- The V-Dem adapter descriptor is registerable / listable
  through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata.
- The V-Dem descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``vdem``, default
  version ``"v16"``, DOI homepage URL, attribution_key
  ``vdem``, dataset type, 1789-2025 coverage hint, five
  observation families: ``political_country_year``,
  ``governance_country_year``, ``corruption_country_year``,
  ``repression_country_year``, ``social_country_year``).
- :class:`SourceIngestRunner` can run V-Dem end-to-end
  through the new registry against a fixture ``raw_root``
  and produce :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter internally
  reuses legacy parsing modules, but dispatch is
  registry-based).
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(1788,)`` request returns zero
  observations plus a structured :class:`SourceWarning` (no
  stale-proxy fill -- SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- The readiness gate validates the bundle's metadata
  ``checksum_sha256`` SHAPE (64-char hex) and, if the staged
  zip is present, verifies the ZIP SHA-256 (NOT the 388MB
  CSV). The CSV is NEVER hashed by the unified adapter.
- Readiness-failure paths block the runner BEFORE
  ``read_raw`` / ``transform`` for missing metadata,
  missing CSV, missing required metadata field, malformed
  checksum, mismatched zip checksum, missing metadata
  ``source_version``, mismatched metadata ``source_version``,
  and unsupported request ``source_version``.
- Canonical metadata ``source_version="v16"`` propagates
  consistently to ``RawAsset.version`` and every emitted
  ``NormalizedObservation.source_version``.
- Importing the new ``leaders_db.sources.adapters.vdem``
  module does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  docs/architecture/sources.md §10.1).
- Per-observation ``extension`` preserves the audit trail
  (V-Dem column, raw value as string, rating category,
  country_id, country_text_id, source_row_reference, raw
  scale, higher_is_better, normalized_scale_target, unit,
  attribution).
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from leaders_db.sources import SourceIngestRequest
    from leaders_db.sources.contracts import ReadinessResult


VDEM_TEST_FIXTURE_CSV: str = "V-Dem-CY-Full+Others-v16.csv"
VDEM_TEST_FIXTURE_ZIP: str = "V-Dem-CY-FullOthers-v16_csv.zip"
VDEM_TEST_METADATA_NAME: str = "metadata.json"
VDEM_TEST_ATTRIBUTION_KEY: str = "vdem"
VDEM_TEST_DEFAULT_VERSION: str = "v16"
VDEM_TEST_COVERAGE_START: int = 1789
VDEM_TEST_COVERAGE_END: int = 2025
VDEM_TEST_HOMEPAGE_URL: str = "https://doi.org/10.23696/vdemds26"
VDEM_TEST_FAMILIES: tuple[str, ...] = (
    "political_country_year",
    "governance_country_year",
    "corruption_country_year",
    "repression_country_year",
    "social_country_year",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyVDemAdapter:
    """Wrap a :class:`VDemAdapter` and record every lifecycle call.

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


def _stage_vdem_bundle(raw_root: Path) -> Path:
    """Stage the canonical V-Dem fixture bundle under ``raw_root/vdem``.

    Copies ``tests/fixtures/vdem/sample.csv`` into
    ``<raw_root>/vdem/V-Dem-CY-Full+Others-v16.csv`` and
    writes a well-formed ``metadata.json`` (canonical primary
    shape: ``source_name`` / ``source_version`` /
    ``source_url`` / ``license_note`` / ``local_files`` /
    ``ingestion_status`` / ``coverage`` /
    ``checksum_sha256``). The placeholder ``checksum_sha256``
    is a 64-char hex string so the readiness gate's
    shape check passes; the gate does NOT hash the 388MB
    CSV (the zip is not staged so the zip-checksum branch
    is bypassed). Returns the resolved bundle directory.

    The fixture carries 5 countries (MEX, USA, SWE, IND, NGA)
    x 2 years (2022, 2023) x 22 indicators = 220 observations.
    """
    bundle_dir = raw_root / "vdem"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "vdem"
    fixture_csv = fixtures / "sample.csv"
    shutil.copy2(fixture_csv, bundle_dir / VDEM_TEST_FIXTURE_CSV)
    payload = {
        "source_name": "V-Dem (Varieties of Democracy)",
        "source_version": VDEM_TEST_DEFAULT_VERSION,
        "download_date": "2026-03-10",
        "coverage": "1789-2025",
        "license_note": (
            "Free for academic and non-commercial use with "
            "attribution. Cite Coppedge et al. 2026."
        ),
        "local_files": [VDEM_TEST_FIXTURE_CSV],
        "ingestion_status": "ingested",
        "source_url": "https://v-dem.net/data/the-v-dem-dataset/",
        "checksum_sha256": "0" * 64,
    }
    (bundle_dir / VDEM_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


def _stage_vdem_bundle_with_zip(raw_root: Path) -> Path:
    """Stage a V-Dem bundle with a real staged zip + matching checksum.

    Used by tests that exercise the zip-checksum verification
    branch. The fixture zip is a tiny synthetic zip with
    predictable content so the SHA-256 can be computed
    deterministically in the test (the canonical 26 MB V-Dem
    zip is never read or staged by tests).
    """
    bundle_dir = _stage_vdem_bundle(raw_root)
    zip_path = bundle_dir / VDEM_TEST_FIXTURE_ZIP
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("fake_vdem.csv", "country_name,country_text_id,year\n")
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    metadata_path = bundle_dir / VDEM_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = zip_sha
    payload["local_files"] = [
        VDEM_TEST_FIXTURE_ZIP,
        VDEM_TEST_FIXTURE_CSV,
    ]
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_vdem_descriptor_exposes_documented_static_metadata() -> None:
    """The V-Dem descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "vdem"``
    - ``display_name == "Varieties of Democracy (V-Dem) v16"``
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical metadata stamp.
    - ``homepage_url`` is the canonical V-Dem DOI.
    - ``attribution_key == "vdem"``
    - ``coverage_hint.start_year == 1789``,
      ``coverage_hint.end_year == 2025``.
    - ``supported_observation_families`` is the 5-tuple
      of V-Dem observation families.
    - ``requires_network is False`` (local-file only).
    """
    from leaders_db.sources.adapters.vdem import (
        build_vdem_descriptor,
    )

    descriptor = build_vdem_descriptor()

    assert descriptor.source_id.slug == "vdem"
    assert descriptor.display_name == "Varieties of Democracy (V-Dem) v16"
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == VDEM_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == VDEM_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == VDEM_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == VDEM_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year == VDEM_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == VDEM_TEST_FAMILIES
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_vdem_attribution_text_matches_attributions_doc() -> None:
    """The V-Dem attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical V-Dem citation block
    in ``docs/sources/attributions.md`` is the source of
    truth; the unified adapter constant must be
    byte-identical to a substring of that doc AND to the
    legacy ``VDEM_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/vdem_io.py``.
    """
    from leaders_db.ingest.vdem_io import VDEM_ATTRIBUTION
    from leaders_db.sources.adapters.vdem import (
        VDEM_ATTRIBUTION_TEXT,
    )

    assert VDEM_ATTRIBUTION_TEXT == VDEM_ATTRIBUTION, (
        "Unified V-Dem attribution must be byte-identical to "
        "the legacy VDEM_ATTRIBUTION constant in "
        "src/leaders_db/ingest/vdem_io.py."
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
    assert VDEM_ATTRIBUTION_TEXT in attributions_text, (
        f"{VDEM_ATTRIBUTION_TEXT!r} is not a substring "
        f"of {attributions_path}. Update both in the same "
        f"commit (Rule #15)."
    )


def test_vdem_adapter_satisfies_source_adapter_protocol() -> None:
    """``VDemAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or
    any of ``check_ready`` / ``read_raw`` / ``transform`` at
    construction time. The check is also enforced at adapter
    module import time; this test is the explicit assertion
    for downstream test suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    adapter = create_vdem_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "vdem"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_vdem_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_vdem_adapter()`` produces an adapter the registry accepts.

    The :class:`InMemorySourceRegistry` rejects duplicate
    slugs with ``ValueError`` (SRC-REG-004); the test asserts
    the V-Dem adapter registers cleanly under the ``vdem``
    slug and the descriptor is listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_vdem_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "vdem"

    resolved = registry.get_descriptor(SourceId(slug="vdem"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="vdem")) is adapter


def test_vdem_register_helper_registers_against_explicit_registry() -> None:
    """``register_vdem(registry)`` is the explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.vdem import (
        register_vdem,
    )

    registry = InMemorySourceRegistry()
    adapter = register_vdem(registry)
    assert registry.get_adapter(SourceId(slug="vdem")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_vdem_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives V-Dem through
    the documented lifecycle and emits
    :class:`NormalizedObservation` records.

    The fixture has 5 countries x 2 years x 22 indicators =
    220 observations (no ``#N/A`` cells; the legacy narrow
    frame carries every cell as a real number for this
    fixture).

    Per-country totals:

    - MEX 2022 + 2023: 44 (2*22)
    - USA 2022 + 2023: 44
    - SWE 2022 + 2023: 44
    - IND 2022 + 2023: 44
    - NGA 2022 + 2023: 44

    Total: 5 * 44 = 220.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 220, (
        f"expected 220 observations (5*2*22); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "vdem"
        assert obs.year in (2022, 2023)
        assert obs.country_code in ("MEX", "USA", "SWE", "IND", "NGA")
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        # Every observation's raw_locator carries the CSV
        # path + the raw V-Dem column name.
        assert obs.raw_locator.path is not None
        assert obs.raw_locator.column_name is not None
        # The narrow frame loses the original CSV row
        # index through the long-to-wide pivot (no
        # fabricated locators).
        assert obs.raw_locator.row_number is None
        # The attribution text is carried on every
        # observation's extension payload (Rule #15).
        assert "attribution" in obs.extension

    # Per-country totals.
    by_country: dict[str, int] = {}
    for obs in result.observations:
        by_country[obs.country_code] = (
            by_country.get(obs.country_code, 0) + 1
        )
    assert by_country == {
        "MEX": 44,
        "USA": 44,
        "SWE": 44,
        "IND": 44,
        "NGA": 44,
    }


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_vdem_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives V-Dem through the new registry and
    never calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["vdem"]`` with
    a tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)``
    executes the new V-Dem adapter lifecycle end-to-end.

    SRC-REG-003 / docs/architecture/sources.md §10.1: the
    new registry is the single dispatch surface; legacy
    dispatch is explicitly forbidden for the new runner.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    # Replace the legacy ``vdem`` slot with a tracker that
    # records every invocation. The runner must never call
    # it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("vdem")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["vdem"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_vdem_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="vdem"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 220

        # The legacy tracker must not have been called --
        # the new runner routes through the new registry
        # only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["vdem"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_vdem_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2023,)`` filters to 2023 rows only.

    Per-row 2023 totals: 5 countries x 22 indicators = 110
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 110
    assert {obs.year for obs in result.observations} == {2023}


def test_vdem_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    Per-country USA totals: 2 years x 22 indicators = 44
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 44
    assert {obs.country_code for obs in result.observations} == {"USA"}


def test_vdem_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``years=(2023,) + countries=('USA',)`` filters to USA 2023 only.

    Per-row USA 2023 totals: 22 cells (one per V-Dem
    indicator).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 22
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.year for obs in result.observations} == {2023}


# ---------------------------------------------------------------------------
# Out-of-coverage + unsupported filter
# ---------------------------------------------------------------------------


def test_vdem_out_of_coverage_year_before_window_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(1788,)`` returns zero observations + a structured
    :class:`SourceWarning` -- no stale-proxy fill.

    V-Dem covers 1789-2025 (SRC-COV-001). A request for 1788
    falls outside the coverage envelope (SRC-COV-002) and
    MUST emit zero rows plus a structured warning
    (SRC-COV-003: no silent stale-proxy fill).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(1788,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "V-Dem covers 1789-2025; year=1788 must yield zero "
        "observations (no stale-proxy fill)."
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    ), (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )


def test_vdem_out_of_coverage_year_after_window_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(2026,)`` returns zero observations + YEAR_ABSENT warning.

    Same out-of-coverage contract as the pre-coverage branch:
    years > 2025 (the V-Dem coverage end) emit zero rows plus
    a structured YEAR_ABSENT warning. No stale-proxy fill.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(2026,),
    )
    result = runner.run(request)

    assert result.observations == ()
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    )


def test_vdem_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Biden',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently
    ignoring the filter (SRC-REQ-005).

    The V-Dem transform does not consume leader identity;
    the filter is rejected explicitly so a developer can act
    on it without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        leaders=("Biden",),
    )
    result = runner.run(request)

    # All 220 fixture rows are still emitted (the filter
    # does not alter the row set; it just emits the
    # warning).
    assert len(result.observations) == 220
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
      ``errors`` (NOT ``warnings``) with
      ``severity == "error"``;
    - carry the configured source id;
    - mention the missing / invalid artifact in the message
      so the developer can act on it.
    """
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
    assert err.source_id == SourceId(slug="vdem"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyVDemAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips
    ``read_raw`` / ``transform``."""
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    # The error names the source slug so callers can act on
    # it without reading source code.
    assert "vdem" in str(exc_info.value).lower(), (
        f"runner RuntimeError must name the failing source "
        f"slug; got {exc_info.value!r}"
    )

    # Lifecycle ordering proof: ``check_ready`` ran (and
    # blocked); ``read_raw`` and ``transform`` did NOT.
    assert "read_raw" not in spy.calls, (
        "runner must short-circuit on ready=False before "
        f"calling read_raw; actual spy calls: {spy.calls!r}"
    )
    assert "transform" not in spy.calls, (
        "runner must short-circuit on ready=False before "
        f"calling transform; actual spy calls: {spy.calls!r}"
    )
    assert "check_ready" in spy.calls, (
        "check_ready must have been called at least once "
        "(either by the test directly or by the runner); "
        f"actual spy calls: {spy.calls!r}"
    )


def test_vdem_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='9999')`` against a
    canonical V-Dem bundle MUST fail readiness with a
    structured error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail
    readiness with actionable error." The legacy bundle has
    no per-version stamp beyond
    ``metadata.json['source_version']``; silently
    propagating an unsupported version into
    ``RawAsset.version`` /
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
    from leaders_db.sources.adapters.vdem import (
        VDEM_DEFAULT_VERSION,
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        source_version="9999",
    )

    # Phase 1: the gate itself returns ready=False with a
    # structured error (severity='error',
    # code='unsupported_version').
    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    # The error message must name both the requested
    # version and the canonical version so the developer
    # can re-run without reading source code.
    err = readiness.errors[0]
    assert VDEM_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{VDEM_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    # Phase 2: the runner refuses to dispatch.
    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_missing_metadata_fails_readiness_and_blocks_runner(
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
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the CSV (no ``metadata.json``) -- mirrors
    # the legacy missing-metadata contract.
    bundle_dir = raw_root / "vdem"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "vdem"
    shutil.copy2(fixtures / "sample.csv", bundle_dir / VDEM_TEST_FIXTURE_CSV)

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_missing_csv_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``V-Dem-CY-Full+Others-v16.csv`` missing from the bundle
    => readiness blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage a valid ``metadata.json`` but omit the CSV.
    bundle_dir = raw_root / "vdem"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": "V-Dem (Varieties of Democracy)",
        "source_version": VDEM_TEST_DEFAULT_VERSION,
        "coverage": "1789-2025",
        "license_note": "Free academic",
        "local_files": [VDEM_TEST_FIXTURE_CSV],
        "ingestion_status": "ingested",
        "source_url": "https://v-dem.net/",
        "checksum_sha256": "0" * 64,
    }
    (bundle_dir / VDEM_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_raw",
        expected_substring=VDEM_TEST_FIXTURE_CSV,
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_missing_local_files_reference_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``local_files`` does not include the canonical CSV =>
    readiness blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "vdem"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "vdem"
    shutil.copy2(fixtures / "sample.csv", bundle_dir / VDEM_TEST_FIXTURE_CSV)
    payload = {
        "source_name": "V-Dem (Varieties of Democracy)",
        "source_version": VDEM_TEST_DEFAULT_VERSION,
        "coverage": "1789-2025",
        "license_note": "Free academic",
        "local_files": ["some_other_file.csv"],  # missing the canonical CSV
        "ingestion_status": "ingested",
        "source_url": "https://v-dem.net/",
        "checksum_sha256": "0" * 64,
    }
    (bundle_dir / VDEM_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring=VDEM_TEST_FIXTURE_CSV,
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_malformed_checksum_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Malformed ``checksum_sha256`` (not a 64-char hex string)
    => readiness blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "vdem"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "vdem"
    shutil.copy2(fixtures / "sample.csv", bundle_dir / VDEM_TEST_FIXTURE_CSV)
    payload = {
        "source_name": "V-Dem (Varieties of Democracy)",
        "source_version": VDEM_TEST_DEFAULT_VERSION,
        "coverage": "1789-2025",
        "license_note": "Free academic",
        "local_files": [VDEM_TEST_FIXTURE_CSV],
        "ingestion_status": "ingested",
        "source_url": "https://v-dem.net/",
        "checksum_sha256": "not-a-hex-string",
    }
    (bundle_dir / VDEM_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_mismatched_zip_checksum_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Mismatched zip SHA-256 (when the zip is staged) =>
    readiness blocker with the V-Dem-specific
    ``vdem_checksum_mismatch`` code; runner does not progress.

    The 388MB CSV is NEVER hashed by the unified adapter.
    Only the staged zip is hashed when the zip is present;
    the readiness gate's checksum-mismatch code is the
    V-Dem-specific ``vdem_checksum_mismatch`` (NOT
    ``missing_metadata``) so audit code can distinguish a
    zip-checksum failure from a missing-metadata failure.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = _stage_vdem_bundle_with_zip(raw_root)
    # Mutate the well-formed bundle's ``checksum_sha256`` to
    # a value that does not match the staged zip bytes.
    metadata_path = bundle_dir / VDEM_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = "0" * 64
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="vdem_checksum_mismatch",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_correct_zip_checksum_passes_readiness(
    tmp_path: Path,
) -> None:
    """A correct staged-zip SHA-256 passes readiness.

    When the staged zip is present AND its SHA-256 matches
    the metadata ``checksum_sha256``, the readiness gate
    accepts the bundle. (The 388MB CSV is still not hashed
    -- the audit chain is preserved via the zip-checksum
    match.)
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle_with_zip(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 220


def test_vdem_missing_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing metadata ``source_version`` is a readiness blocker.

    The required-fields check fires first (per the canonical
    primary-shape contract); the blocker code is
    ``missing_metadata`` (matching the WGI / WDI /
    Maddison convention) and the message names the missing
    ``source_version`` field.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)
    metadata_path = raw_root / "vdem" / VDEM_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("source_version")
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_mismatched_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Metadata ``source_version`` must match the canonical V-Dem stamp."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.vdem import (
        VDEM_DEFAULT_VERSION,
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)
    metadata_path = raw_root / "vdem" / VDEM_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["source_version"] = "9999"
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_vdem_adapter()
    spy = _SpyVDemAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    assert VDEM_DEFAULT_VERSION in readiness.errors[0].message

    _assert_runner_does_not_progress(registry, request, spy)


def test_vdem_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations.

    The unified V-Dem adapter must label every
    ``RawAsset.version`` and every
    ``NormalizedObservation.source_version`` with the
    validated canonical version stamp (``"v16"``), not
    arbitrary metadata / request text.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        VDEM_DEFAULT_VERSION,
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)
    adapter = create_vdem_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == VDEM_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version
        for observation in result.observations
    } == {VDEM_DEFAULT_VERSION}


def test_vdem_observation_carries_vdem_specific_extension_fields(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension`` carries the V-Dem-specific
    audit fields documented in
    :mod:`_transform`.

    The extension payload preserves the catalog ``raw_column``
    (e.g. ``v2x_polyarchy``), the V-Dem ``country_text_id``
    and ``country_id``, the catalog ``rating_category``, the
    legacy ``source_row_reference`` pattern
    (``"vdem:<country_text_id>"``), the audit ``raw_value``
    as a string, the ``raw_scale`` + ``higher_is_better`` +
    ``normalized_scale_target`` direction hints, the
    ``unit``, and the canonical attribution text (Rule #15).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.vdem import (
        VDEM_ATTRIBUTION_TEXT,
        create_vdem_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_vdem_bundle(raw_root)
    registry = InMemorySourceRegistry()
    registry.register(create_vdem_adapter())
    runner = SourceIngestRunner(registry=registry)
    request = SourceIngestRequest(
        source_id=SourceId(slug="vdem"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert result.observations
    obs = result.observations[0]

    expected_extension_keys = {
        "vdem_raw_column",
        "vdem_country_text_id",
        "vdem_rating_category",
        "source_row_reference",
        "raw_value",
        "raw_scale",
        "higher_is_better",
        "normalized_scale_target",
        "unit",
        "attribution",
        "vdem_country_id",
    }
    assert expected_extension_keys.issubset(obs.extension.keys())

    # Audit field values.
    assert obs.extension["vdem_country_text_id"] == "USA"
    assert obs.extension["source_row_reference"] == "vdem:USA"
    assert obs.extension["vdem_rating_category"] in {
        "political_freedom",
        "integrity",
        "effectiveness",
        "domestic_violence",
        "social_wellbeing",
    }
    assert obs.extension["attribution"] == VDEM_ATTRIBUTION_TEXT
    # raw_value is preserved verbatim (a non-empty string for
    # a real cell).
    assert isinstance(obs.extension["raw_value"], str)
    assert obs.extension["raw_value"] != ""


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.vdem must not import legacy
# ---------------------------------------------------------------------------


def test_vdem_adapter_module_does_not_import_legacy_ingest_at_import() -> None:
    """``import leaders_db.sources.adapters.vdem`` MUST NOT
    import ``leaders_db.ingest`` at any depth (SRC-MIG-007 +
    docs/architecture/sources.md §10.1).

    The test inspects every V-Dem adapter source module's
    AST and asserts that the only ``leaders_db.ingest.*``
    import statements are scoped inside function bodies
    (lazy imports), NOT at module top level. Module-level
    eager imports of ``leaders_db.ingest`` are forbidden
    because they would pull the legacy ingest package into
    ``sys.modules`` at package import time and break the
    documented boundary.

    The adapter MAY import legacy code lazily inside its
    methods; that path is exercised by the runner tests
    above and is the documented migration pattern. The AST
    check is deliberately non-destructive (no
    ``sys.modules`` purge) so the test does not disturb
    SQLAlchemy ORM mapper state that later tests depend on.

    The full purge-and-reimport package-isolation check
    lives in ``tests/sources/test_import_boundary.py`` and
    iterates ``leaders_db.sources.adapters.vdem`` as part
    of its canonical submodule list -- that test owns the
    ``sys.modules``-purge contract for the whole package.
    """
    legacy_top_level, legacy_nested = (
        _scan_vdem_package_for_legacy_ingest_imports(
            _vdem_adapter_package_dir(),
        )
    )

    assert legacy_top_level == [], (
        f"{_vdem_adapter_package_dir()} has eager top-level "
        f"legacy ingest imports; the new V-Dem adapter must "
        f"import legacy code lazily inside methods only "
        f"(SRC-MIG-007). Found: {legacy_top_level}"
    )
    # Sanity: at least one nested lazy import must exist
    # (else the adapter would not work; the legacy reader /
    # transform / catalog are reused).
    assert any(
        "from leaders_db.ingest.vdem_io" in entry
        for _, entry in legacy_nested
    ), (
        f"{_vdem_adapter_package_dir()} must contain at "
        f"least one nested lazy import from "
        f"leaders_db.ingest.vdem_io; got {legacy_nested}"
    )


def _vdem_adapter_package_dir() -> Path:
    """Return the resolved V-Dem adapter package directory."""
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "vdem"
    )


def _scan_vdem_package_for_legacy_ingest_imports(
    package_dir: Path,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Walk every .py file in the V-Dem adapter package and
    return ``(legacy_top_level, legacy_nested)`` import pairs.

    The lazy-import locations (currently in ``_raw_read.py``
    + ``_catalog.py``, NOT in ``adapter.py``) are detected
    regardless of the module split. Each tuple carries
    ``(module_path_str, import_label)`` so a failure message
    names the file.
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
