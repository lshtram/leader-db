"""Phase C / D slice -- PWT adapter under the unified ``leaders_db.sources``.

The Penn World Table 10.01 adapter is the first source rebuilt under
the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 1, docs/requirements/sources.md
§12 SRC-MIG-005). The legacy PWT reader / transform under
``leaders_db.ingest.sources.pwt`` is reused internally via lazy
imports -- the package boundary at docs/architecture/sources.md
§10.1 is preserved.

Tests cover the documented slice acceptance criteria:

- The PWT adapter descriptor is registerable / listable through the
  new :class:`InMemorySourceRegistry` and exposes the documented
  static metadata.
- The PWT descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``pwt``, default version
  ``10.01``, attribution_key ``pwt``, dataset type, 1950-2019
  coverage hint, ``economic_country_year`` observation family,
  CC BY 4.0 homepage URL).
- :class:`SourceIngestRunner` can run PWT end-to-end through the
  new registry against a fixture ``raw_root`` and produce
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
- Importing the new ``leaders_db.sources.adapters.pwt`` module
  does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  docs/architecture/sources.md §10.1).

PASS-ELIGIBLE rationale
-----------------------
The legacy PWT reader / transform are well-tested via the existing
``tests/ingest/sources/pwt/`` suite. The tests in this file prove
that the new ``leaders_db.sources.adapters.pwt`` adapter wraps the
legacy parsing logic behind the unified :class:`SourceAdapter`
Protocol while preserving the package-isolation contract -- they
are PASS-ELIGIBLE because the adapter implementation lands in the
same change set.
"""

from __future__ import annotations

import hashlib
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

PWT_TEST_FIXTURE_XLSX: str = "pwt1001.xlsx"
PWT_TEST_METADATA_NAME: str = "metadata.json"
PWT_TEST_ATTRIBUTION_KEY: str = "pwt"
PWT_TEST_DEFAULT_VERSION: str = "10.01"
PWT_TEST_COVERAGE_START: int = 1950
PWT_TEST_COVERAGE_END: int = 2019
PWT_TEST_FAMILY: str = "economic_country_year"
PWT_TEST_HOMEPAGE_URL: str = (
    "https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt1001"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyPWTAdapter:
    """Wrap a :class:`PWTAdapter` and record every lifecycle call.

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


def _stage_pwt_bundle(raw_root: Path) -> Path:
    """Stage the canonical PWT fixture bundle under ``raw_root/pwt``.

    Copies ``tests/fixtures/pwt/sample.xlsx`` into
    ``<raw_root>/pwt/pwt1001.xlsx`` and writes a well-formed
    ``metadata.json`` whose ``checksum_sha256`` matches the staged
    xlsx bytes. Returns the resolved bundle directory.

    The xlsx carries 3 countries (USA, MEX, SWE) x 2 years
    (2018, 2019); per-row non-blank catalog cell counts are
    documented in ``tests/fixtures/pwt/build_sample_xlsx.py``.
    """
    bundle_dir = raw_root / "pwt"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "pwt"
    fixture_xlsx = fixtures / "sample.xlsx"
    shutil.copy2(fixture_xlsx, bundle_dir / PWT_TEST_FIXTURE_XLSX)
    sha = hashlib.sha256(
        (bundle_dir / PWT_TEST_FIXTURE_XLSX).read_bytes(),
    ).hexdigest()
    payload = {
        "source_name": "Penn World Table",
        "source_version": PWT_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-22",
        "coverage": "country-year economic accounts",
        "years_available": "1950-2019",
        "license_note": (
            "Creative Commons Attribution 4.0 International "
            "(CC BY 4.0); cite Feenstra, Inklaar, Timmer 2015."
        ),
        "local_files": [PWT_TEST_FIXTURE_XLSX],
        "ingestion_status": "downloaded",
        "source_url": PWT_TEST_HOMEPAGE_URL,
        "checksum_sha256": sha,
    }
    (bundle_dir / PWT_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_pwt_descriptor_exposes_documented_static_metadata() -> None:
    """The PWT descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "pwt"``
    - ``display_name == "Penn World Table 10.01"``
    - ``source_type == "dataset"``
    - ``default_version == "10.01"``
    - ``homepage_url`` is the canonical PWT 10.01 release URL.
    - ``attribution_key == "pwt"``
    - ``coverage_hint.start_year == 1950``,
      ``coverage_hint.end_year == 2019``.
    - ``supported_observation_families == ("economic_country_year",)``.

    PASS-ELIGIBLE: the descriptor factory ships with the slice.
    """
    from leaders_db.sources.adapters.pwt import build_pwt_descriptor

    descriptor = build_pwt_descriptor()

    assert descriptor.source_id.slug == "pwt"
    assert descriptor.display_name == "Penn World Table 10.01"
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == PWT_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == PWT_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == PWT_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == PWT_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year == PWT_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == (PWT_TEST_FAMILY,)
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_pwt_attribution_text_matches_attributions_doc() -> None:
    """The PWT attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical PWT citation block in
    ``docs/sources/attributions.md`` is the source of truth; the
    adapter module's constant must be byte-identical to a
    substring of that doc.
    """
    from leaders_db.sources.adapters.pwt import PWT_ATTRIBUTION_TEXT

    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    # ``parents[2]`` from ``tests/sources/test_pwt_adapter.py``
    # resolves to the repo root, so ``docs/sources/attributions.md``
    # is the right path.
    assert attributions_path.exists(), (
        f"expected attributions doc at {attributions_path}"
    )
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert PWT_ATTRIBUTION_TEXT in attributions_text, (
        f"{PWT_ATTRIBUTION_TEXT!r} is not a substring of "
        f"{attributions_path}. Update both in the same commit "
        f"(Rule #15)."
    )


def test_pwt_adapter_satisfies_source_adapter_protocol() -> None:
    """``PWTAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or any of
    ``check_ready`` / ``read_raw`` / ``transform`` at construction
    time. The check is also enforced at adapter module import
    time; this test is the explicit assertion for downstream test
    suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    adapter = create_pwt_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "pwt"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_pwt_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_pwt_adapter()`` produces an adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects duplicate
    slugs with ``ValueError`` (SRC-REG-004); the test asserts the
    PWT adapter registers cleanly under the ``pwt`` slug and the
    descriptor is listable.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceId
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    registry = InMemorySourceRegistry()
    adapter = create_pwt_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "pwt"

    resolved = registry.get_descriptor(SourceId(slug="pwt"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="pwt")) is adapter


def test_pwt_register_helper_registers_against_explicit_registry() -> None:
    """``register_pwt(registry)`` is the explicit seam for tests + CLI."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId
    from leaders_db.sources.adapters.pwt import (
        register_pwt,
    )

    registry = InMemorySourceRegistry()
    adapter = register_pwt(registry)
    assert registry.get_adapter(SourceId(slug="pwt")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_pwt_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives PWT through the
    documented lifecycle and emits :class:`NormalizedObservation`
    records.

    The fixture has 3 countries x 2 years x 15 columns; the
    per-row non-blank catalog cell counts are:

    - USA 2018: 2 cells (rgdpe, pop)
    - USA 2019: 6 cells (rgdpe, rgdpo, pop, emp, avh, hc)
    - MEX 2018: 0 cells
    - MEX 2019: 6 cells (rgdpe, rgdpo, pop, emp, avh, hc)
    - SWE 2018: 0 cells
    - SWE 2019: 3 cells (rgdpe, rgdpo, pop)

    Per-country totals: USA 8, MEX 6, SWE 3 -> 17 observations
    when no filter is applied.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 17, (
        f"expected 17 observations (USA 8 + MEX 6 + SWE 3); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "pwt"
        assert obs.observation_family == PWT_TEST_FAMILY
        assert obs.year is not None
        assert obs.country_code is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        assert obs.raw_locator.sheet == "Data"

    # Per-country totals.
    by_country: dict[str, int] = {}
    for obs in result.observations:
        by_country[obs.country_code] = (
            by_country.get(obs.country_code, 0) + 1
        )
    assert by_country == {"USA": 8, "MEX": 6, "SWE": 3}


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_pwt_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives PWT through the new registry and never
    calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["pwt"]`` with a
    tracking sentinel and asserts the sentinel is never invoked
    while ``SourceIngestRunner.run(request)`` executes the new
    PWT adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    # Replace the legacy pwt slot with a tracker that records
    # every invocation. The runner must never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("pwt")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["pwt"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_pwt_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="pwt"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 17

        # The legacy tracker must not have been called -- the
        # new runner routes through the new registry only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["pwt"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_pwt_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2019,)`` filters to 2019 rows only.

    Per-row 2019 totals: USA 6 + MEX 6 + SWE 3 = 15 observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        years=(2019,),
    )
    result = runner.run(request)
    assert len(result.observations) == 15
    assert {obs.year for obs in result.observations} == {2019}


def test_pwt_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    Per-country USA totals: 8 observations (USA 2018: 2 + USA 2019: 6).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 8
    assert {obs.country_code for obs in result.observations} == {"USA"}


def test_pwt_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``years=(2019,) + countries=('USA',)`` filters to USA 2019 only.

    Per-row USA 2019 totals: 6 cells (rgdpe, rgdpo, pop, emp, avh, hc).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        years=(2019,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 6
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.year for obs in result.observations} == {2019}


# ---------------------------------------------------------------------------
# Out-of-coverage + unsupported filter
# ---------------------------------------------------------------------------


def test_pwt_out_of_coverage_year_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(2023,)`` returns zero observations + a structured
    :class:`SourceWarning` -- no stale-proxy fill.

    PWT 10.01 covers 1950-2019 (SRC-COV-001). A request for
    2023 falls outside the coverage envelope (SRC-COV-002) and
    MUST emit zero rows plus a structured warning (SRC-COV-003:
    no silent stale-proxy fill).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "PWT 10.01 covers 1950-2019; year=2023 must yield zero "
        "observations (no stale-proxy fill)."
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    ), (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )


def test_pwt_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Biden',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently ignoring
    the filter (SRC-REQ-005).

    The PWT transform does not consume leader identity; the
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
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        leaders=("Biden",),
    )
    result = runner.run(request)

    # All 17 fixture rows are still emitted (the filter does not
    # alter the row set; it just emits the warning).
    assert len(result.observations) == 17
    assert any(
        isinstance(w, SourceWarning) and w.code == "unsupported_filter"
        for w in result.warnings
    ), (
        "leaders filter must surface an UNSUPPORTED_FILTER "
        f"warning; got {result.warnings!r}"
    )


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
#
# The shared ``_SpyPWTAdapter`` wrapper provides the call
# tracking without monkey-patching the registry's lookup
# mechanism.
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
    assert err.source_id == SourceId(slug="pwt"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyPWTAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips ``read_raw`` / ``transform``.

    The runner's contract (docs/architecture/sources.md §5.6) is
    to raise ``RuntimeError`` when ``check_ready`` returns
    ``ready=False``. The spy records every adapter call so the
    test can prove ``read_raw`` / ``transform`` are NEVER
    invoked on the failing path.
    """
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    # The error names the source slug so callers can act on it
    # without reading source code.
    assert "pwt" in str(exc_info.value).lower(), (
        f"runner RuntimeError must name the failing source slug; "
        f"got {exc_info.value!r}"
    )

    # Lifecycle ordering proof: ``check_ready`` ran (and
    # blocked); ``read_raw`` and ``transform`` did NOT. The
    # test invokes ``spy.check_ready(request)`` once
    # explicitly (Phase 1 of the test) and the runner invokes
    # it again, so we assert by exclusion rather than exact
    # equality.
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


def test_pwt_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='9.99')`` against a
    canonical PWT 10.01 bundle MUST fail readiness with a
    structured error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." The legacy bundle has no per-version
    stamp beyond ``metadata.json['source_version']``; silently
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
    from leaders_db.sources.adapters.pwt import (
        PWT_DEFAULT_VERSION,
        create_pwt_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        source_version="9.99",
    )

    # Phase 1: the gate itself returns ready=False with a
    # structured error (severity='error', code='unsupported_version').
    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9.99",
    )
    # The error message must name both the requested version and
    # the canonical version so the developer can re-run without
    # having to read source code.
    err = readiness.errors[0]
    assert PWT_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{PWT_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    # Phase 2: the runner refuses to dispatch.
    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_missing_metadata_fails_readiness_and_blocks_runner(
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
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    # Stage only the xlsx (no ``metadata.json``) -- mirrors the
    # legacy ``pwt_xlsx_no_metadata`` fixture contract.
    bundle_dir = raw_root / "pwt"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "pwt"
    shutil.copy2(fixtures / "sample.xlsx", bundle_dir / "pwt1001.xlsx")

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_missing_xlsx_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``pwt1001.xlsx`` missing from the bundle => readiness
    blocker; runner does not progress.

    The error message must mention ``pwt1001.xlsx`` so a
    developer can fix the upstream issue without reading source
    code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    # Stage a valid ``metadata.json`` but omit the xlsx.
    bundle_dir = raw_root / "pwt"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    metadata_payload = {
        "source_name": "Penn World Table",
        "source_version": "10.01",
        "download_date": "2026-06-22",
        "coverage": "country-year economic accounts",
        "years_available": "1950-2019",
        "license_note": (
            "Creative Commons Attribution 4.0 International "
            "(CC BY 4.0); cite Feenstra, Inklaar, Timmer 2015."
        ),
        "local_files": ["pwt1001.xlsx"],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://www.rug.nl/ggdc/productivity/pwt/"
            "pwt-releases/pwt1001"
        ),
        "checksum_sha256": "0" * 64,  # placeholder; not verified since xlsx is absent
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(metadata_payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_raw",
        expected_substring="pwt1001.xlsx",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_checksum_mismatch_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A wrong ``checksum_sha256`` in ``metadata.json`` => readiness
    blocker; runner does not progress.

    The error message must mention ``checksum`` so a developer
    can re-stage the xlsx without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)

    # Mutate the well-formed bundle's ``checksum_sha256`` to a
    # value that does not match the staged xlsx bytes. The
    # readiness gate recomputes the SHA-256 on the xlsx and
    # must reject the request.
    bad_path = raw_root / "pwt" / "metadata.json"
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = "0" * 64
    bad_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_missing_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing metadata ``source_version`` is a readiness blocker.

    The unified PWT adapter must validate the bundle version before
    parsing so raw assets and observations cannot be labeled with an
    unknown or unsupported source version.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)
    metadata_path = raw_root / "pwt" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("source_version")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_mismatched_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Metadata ``source_version`` must match canonical PWT 10.01."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pwt import (
        PWT_DEFAULT_VERSION,
        create_pwt_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)
    metadata_path = raw_root / "pwt" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["source_version"] = "9.99"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_pwt_adapter()
    spy = _SpyPWTAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9.99",
    )
    assert PWT_DEFAULT_VERSION in readiness.errors[0].message

    _assert_runner_does_not_progress(registry, request, spy)


def test_pwt_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pwt import (
        PWT_DEFAULT_VERSION,
        create_pwt_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pwt_bundle(raw_root)
    adapter = create_pwt_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pwt"),
        raw_root=raw_root,
        years=(2019,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == PWT_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version for observation in result.observations
    } == {PWT_DEFAULT_VERSION}


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.pwt must not import legacy
# ---------------------------------------------------------------------------


def test_pwt_adapter_module_does_not_import_legacy_ingest_at_import(
) -> None:
    """``import leaders_db.sources.adapters.pwt`` MUST NOT import
    ``leaders_db.ingest`` at any depth (SRC-MIG-007 +
    docs/architecture/sources.md §10.1).

    The test inspects the new module's source AST and asserts
    that the only ``leaders_db.ingest.*`` import statements are
    scoped inside function bodies (lazy imports), NOT at module
    top level. Module-level eager imports of ``leaders_db.ingest``
    are forbidden because they would pull the legacy ingest
    package into ``sys.modules`` at package import time and
    break the documented boundary.

    The adapter MAY import legacy code lazily inside its
    methods; that path is exercised by the runner tests above
    and is the documented migration pattern. The AST check is
    deliberately non-destructive (no ``sys.modules`` purge) so
    the test does not disturb SQLAlchemy ORM mapper state that
    later tests depend on.

    The full purge-and-reimport package-isolation check lives
    in ``tests/sources/test_import_boundary.py`` and now
    iterates ``leaders_db.sources.adapters.pwt`` as part of its
    canonical submodule list -- that test owns the
    ``sys.modules``-purge contract for the whole package.
    """
    import ast

    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "pwt"
        / "adapter.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    legacy_top_level: list[str] = []
    legacy_nested: list[str] = []

    # Top-level imports: only those that live directly under
    # ``tree.body``. Imports nested inside a class or function
    # are method-level lazy imports.
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("leaders_db.ingest"):
                    legacy_top_level.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("leaders_db.ingest"):
                legacy_top_level.append(f"from {module} import ...")

    # Walk into every class / function body for nested (lazy)
    # imports. These are the documented migration pattern.
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
        f"imports; the new PWT adapter must import legacy code "
        f"lazily inside methods only (SRC-MIG-007). Found: "
        f"{legacy_top_level}"
    )
    # Sanity: at least one nested lazy import must exist (else
    # the adapter would not work; the legacy reader / transform
    # are reused).
    assert any(
        "from leaders_db.ingest.sources.pwt" in entry
        for entry in legacy_nested
    ), (
        f"{module_path} must contain at least one nested lazy "
        f"import from leaders_db.ingest.sources.pwt.*; got "
        f"{legacy_nested}"
    )


def test_pwt_package_import_does_not_register_legacy_pwt() -> None:
    """``import leaders_db.sources.adapters.pwt`` MUST NOT touch
    ``STAGE2_ADAPTERS["pwt"]``.

    The legacy dispatch table is the legacy CLI's responsibility.
    Importing the new adapter module must leave the legacy
    registry untouched. This is the package-isolation guarantee
    for the legacy ``ingest`` seam.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import InMemorySourceRegistry
    from leaders_db.sources.adapters.pwt import (
        create_pwt_adapter,
        register_pwt,
    )

    # Snapshot the legacy slot BEFORE we touch the new package.
    sentinel_before = object()
    original = legacy_ingest.STAGE2_ADAPTERS.get("pwt")
    legacy_ingest.STAGE2_ADAPTERS["pwt"] = sentinel_before
    try:
        # Create / register against the NEW registry -- this
        # must not mutate the legacy table.
        adapter = create_pwt_adapter()
        new_registry = InMemorySourceRegistry()
        register_pwt(new_registry)

        assert legacy_ingest.STAGE2_ADAPTERS.get("pwt") is sentinel_before, (
            "the new PWT adapter module must not mutate the "
            "legacy STAGE2_ADAPTERS table on import or factory call"
        )
        # The new registry carries pwt; the legacy table does
        # NOT see the new adapter.
        assert new_registry.list_descriptors()[0].source_id.slug == "pwt"
        assert legacy_ingest.STAGE2_ADAPTERS["pwt"] is sentinel_before
        assert adapter.descriptor.source_id.slug == "pwt"
    finally:
        legacy_ingest.STAGE2_ADAPTERS["pwt"] = original


__all__ = [
    "PWT_TEST_ATTRIBUTION_KEY",
    "PWT_TEST_COVERAGE_END",
    "PWT_TEST_COVERAGE_START",
    "PWT_TEST_DEFAULT_VERSION",
    "PWT_TEST_FAMILY",
    "PWT_TEST_FIXTURE_XLSX",
    "PWT_TEST_HOMEPAGE_URL",
    "PWT_TEST_METADATA_NAME",
    "test_pwt_adapter_is_registerable_through_in_memory_registry",
    "test_pwt_adapter_satisfies_source_adapter_protocol",
    "test_pwt_attribution_text_matches_attributions_doc",
    "test_pwt_checksum_mismatch_fails_readiness_and_blocks_runner",
    "test_pwt_combined_year_and_country_filter",
    "test_pwt_country_filter_is_applied",
    "test_pwt_descriptor_exposes_documented_static_metadata",
    "test_pwt_leader_filter_emits_unsupported_filter_warning",
    "test_pwt_missing_metadata_fails_readiness_and_blocks_runner",
    "test_pwt_missing_xlsx_fails_readiness_and_blocks_runner",
    "test_pwt_out_of_coverage_year_returns_zero_and_warning",
    "test_pwt_package_import_does_not_register_legacy_pwt",
    "test_pwt_register_helper_registers_against_explicit_registry",
    "test_pwt_runner_does_not_consult_legacy_stage2_adapters",
    "test_pwt_runner_produces_normalized_observations",
    "test_pwt_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_pwt_year_filter_is_applied",
]
