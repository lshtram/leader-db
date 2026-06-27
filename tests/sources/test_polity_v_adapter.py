"""Phase D.10 slice -- Polity V adapter under the unified
``leaders_db.sources``.

Polity V (Polity5 v2018) is the first source from the
"databases not yet in legacy" list rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.2 ``polity_v`` row;
``docs/requirements/sources.md`` §12 SRC-MIG-005). Polity V
has no legacy Stage 2 implementation in
``src/leaders_db/ingest/`` -- the ``STAGE2_ADAPTERS["polity_v"]``
slot is ``None`` per the workplan Done History ("blocked on
source hygiene / raw file placement"). The unified adapter reads
the staged ``p5v2018.sav`` directly via ``pyreadstat.read_sav``
and emits the canonical ``NormalizedObservation`` records
end-to-end through the new registry.

Tests cover the documented slice acceptance criteria:

- The Polity V adapter descriptor is registerable / listable
  through the new :class:`InMemorySourceRegistry` and exposes
  the documented static metadata.
- The Polity V descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``polity_v``,
  default version ``p5v2018``, attribution_key ``polity_v``,
  dataset type, 1800-2018 coverage hint,
  ``political_freedom_country_year`` observation family, free
  academic Polity V homepage URL).
- :class:`SourceIngestRunner` can run Polity V end-to-end
  through the new registry against a fixture ``raw_root`` and
  produce :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (Polity V is the first
  clean source with no legacy Stage 2 implementation; the
  adapter MUST NOT touch ``STAGE2_ADAPTERS["polity_v"]``).
- ``years=`` and ``countries=`` filters are honored and surface
  correct observation counts.
- An out-of-coverage ``years=(2023,)`` request (the prototype's
  target year) returns zero observations plus a structured
  :class:`SourceWarning` (no stale-proxy fill -- SRC-COV-002 /
  SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Valid negative scores (``polity=-10``) on ``polity`` /
  ``polity2`` are preserved as numeric observations -- they
  are NOT special codes.
- Special codes (``polity=-66`` / ``-77`` / ``-88``) are
  emitted as ``value=None`` / ``value_type='missing'`` + the
  verbatim raw cell text on ``extension.raw_value``; they are
  NOT coerced to numeric.
- Readiness failures (missing metadata, missing .sav,
  ingestion_status not 'downloaded', missing required field,
  ``local_files`` missing ``p5v2018.sav``, checksum
  mismatch, source_version mismatch) each surface a
  structured ``SourceWarning(severity='error')`` so the runner
  raises ``RuntimeError`` BEFORE ``read_raw`` / ``transform``.
- Importing the new ``leaders_db.sources.adapters.polity_v``
  module does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).

PASS-ELIGIBLE rationale
-----------------------

Polity V has no legacy Stage 2 implementation; the tests in
this file prove that the new ``leaders_db.sources.adapters
.polity_v`` adapter implements the full ``SourceAdapter``
Protocol end-to-end while preserving the package-isolation
contract -- they are PASS-ELIGIBLE because the adapter
implementation lands in the same change set.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from leaders_db.sources import SourceIngestRequest
    from leaders_db.sources.contracts import (
        ReadinessResult,
    )

POLITY_V_TEST_FIXTURE_SAV: str = "sample.sav"
POLITY_V_TEST_METADATA_NAME: str = "metadata.json"
POLITY_V_TEST_ATTRIBUTION_KEY: str = "polity_v"
POLITY_V_TEST_DEFAULT_VERSION: str = "p5v2018"
POLITY_V_TEST_COVERAGE_START: int = 1800
POLITY_V_TEST_COVERAGE_END: int = 2018
POLITY_V_TEST_FAMILY: str = "political_freedom_country_year"
POLITY_V_TEST_HOMEPAGE_URL: str = (
    "https://www.systemicpeace.org/polityproject.html"
)
# SHA-256 of the staged test fixture ``sample.sav`` (computed by
# ``tests/fixtures/polity_v/build_sample_sav.py``; the test
# file uses this constant to validate the metadata
# ``checksum_sha256`` field).
POLITY_V_TEST_FIXTURE_SAV_SHA256: str = (
    "32c7a9a24ce75859d08f67df13ccb9711f8897403dbbc0f12561d8afebbc77b2"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyPolityVAdapter:
    """Wrap a :class:`PolityVAdapter` and record every lifecycle call.

    The spy forwards to the underlying adapter so the real
    behavior is exercised; it just records the call order so
    readiness-failure tests can assert the runner does NOT
    progress into ``read_raw`` / ``transform``.
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


def _stage_polity_v_bundle(raw_root: Path) -> Path:
    """Stage the canonical Polity V fixture bundle under ``raw_root/polity_v``.

    Copies ``tests/fixtures/polity_v/sample.sav`` into
    ``<raw_root>/polity_v/p5v2018.sav`` and writes a well-formed
    ``metadata.json`` whose ``checksum_sha256`` matches the staged
    .sav bytes. Returns the resolved bundle directory.

    The fixture carries 9 real rows extracted from the live
    ``data/raw/polity_v/p5v2018.sav`` (verified live 2026-06-27).
    Indicator cell coverage (per the fixture builder docstring):

    - USA 1945  (polity=9)
    - USA 2018  (polity=8)
    - AFG 1945  (polity=-10, valid negative)
    - AFG 1978  (polity=-77, special code)
    - AFG 1979  (polity=-66, special code)
    - ALB 1945  (polity=-88, special code)
    - ALB 1991  (polity=-88, special code)
    - MEX 2018  (polity=8)
    - RUS 2018  (polity=4)

    The fixture deliberately uses real Polity V rows so the
    SPSS schema + the documented special-code matrix are
    exercised against real data (per the task brief: "derive
    it from actual local raw rows only, not invented").
    """
    bundle_dir = raw_root / "polity_v"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "polity_v"
    fixture_sav = fixtures / POLITY_V_TEST_FIXTURE_SAV
    staged_sav = bundle_dir / "p5v2018.sav"
    shutil.copy2(fixture_sav, staged_sav)
    payload = {
        "source_name": (
            "Polity5: Political Regime Characteristics and "
            "Transitions, 1800-2018"
        ),
        "source_version": POLITY_V_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1800-2018, ~167 countries",
        "years_available": "1800-2018",
        "license_note": (
            "Free academic use; cite Marshall, Jaggers, "
            "Gleditsch 2018."
        ),
        "local_files": ["p5v2018.sav"],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://www.systemicpeace.org/inscr/p5v2018.sav"
        ),
        "checksum_sha256": POLITY_V_TEST_FIXTURE_SAV_SHA256,
        "notes": (
            "Polity V (Polity5 v2018) staged for unified-source "
            "Phase D.10 adapter; raw .sav is gitignored per "
            "Always-On Rule #9; metadata is a runtime-local "
            "requirement beside the user-staged bundle."
        ),
    }
    (bundle_dir / POLITY_V_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_polity_v_descriptor_exposes_documented_static_metadata() -> None:
    """The Polity V descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    ``docs/architecture/sources.md`` §5.2):

    - ``source_id.slug == "polity_v"``
    - ``display_name == "Polity V (Polity5 v2018)"``
    - ``source_type == "dataset"``
    - ``default_version == "p5v2018"``
    - ``homepage_url`` is the canonical Polity V project page.
    - ``attribution_key == "polity_v"``
    - ``coverage_hint.start_year == 1800``,
      ``coverage_hint.end_year == 2018``.
    - ``supported_observation_families == ("political_freedom_country_year",)``.

    PASS-ELIGIBLE: the descriptor factory ships with the slice.
    """
    from leaders_db.sources.adapters.polity_v import (
        build_polity_v_descriptor,
    )

    descriptor = build_polity_v_descriptor()

    assert descriptor.source_id.slug == "polity_v"
    assert descriptor.display_name == "Polity V (Polity5 v2018)"
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == POLITY_V_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == POLITY_V_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == POLITY_V_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == POLITY_V_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year == POLITY_V_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == (
        POLITY_V_TEST_FAMILY,
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_polity_v_attribution_text_matches_attributions_doc() -> None:
    """The Polity V attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical Polity V citation block
    in ``docs/sources/attributions.md`` is the source of truth;
    the adapter module's constant must be byte-identical to a
    substring of that doc.
    """
    from leaders_db.sources.adapters.polity_v import (
        POLITY_V_ATTRIBUTION_TEXT,
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
    assert POLITY_V_ATTRIBUTION_TEXT in attributions_text, (
        f"{POLITY_V_ATTRIBUTION_TEXT!r} is not a substring of "
        f"{attributions_path}. Update both in the same commit "
        f"(Rule #15)."
    )


def test_polity_v_adapter_satisfies_source_adapter_protocol() -> None:
    """``PolityVAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or any of
    ``check_ready`` / ``read_raw`` / ``transform`` at construction
    time. The check is also enforced at adapter module import
    time; this test is the explicit assertion for downstream test
    suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    adapter = create_polity_v_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "polity_v"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_polity_v_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_polity_v_adapter()`` produces an adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects duplicate
    slugs with ``ValueError`` (SRC-REG-004); the test asserts the
    Polity V adapter registers cleanly under the ``polity_v``
    slug and the descriptor is listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_polity_v_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "polity_v"

    resolved = registry.get_descriptor(SourceId(slug="polity_v"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="polity_v")) is adapter


def test_polity_v_register_helper_registers_against_explicit_registry() -> None:
    """``register_polity_v(registry)`` is the explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.polity_v import register_polity_v

    registry = InMemorySourceRegistry()
    adapter = register_polity_v(registry)
    assert registry.get_adapter(SourceId(slug="polity_v")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def _expected_observation_count_for_fixture() -> int:
    """Return the canonical fixture observation count.

    9 fixture rows x 11 catalog indicator columns = 99 cells
    (the per-cell coercion preserves every row as one
    observation per cell -- including NaN + special-code
    cells which become ``value_type='missing'`` observations).
    """
    return 9 * 11


def test_polity_v_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives Polity V
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records.

    The fixture has 9 real rows x 11 catalog indicator columns
    = 99 cells; every cell becomes one observation
    (numeric OR missing) so the runner emits 99 observations
    for an unfiltered request. The valid negatives
    (``AFG 1945: polity=-10``) are preserved as numeric; the
    special codes (``AFG 1978: polity=-77`` etc.) are emitted as
    ``value_type='missing'`` with the verbatim raw cell text
    on ``extension.raw_value``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    expected = _expected_observation_count_for_fixture()
    assert len(result.observations) == expected, (
        f"expected {expected} observations "
        f"(9 fixture rows x 11 catalog indicator columns); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "polity_v"
        assert obs.observation_family == POLITY_V_TEST_FAMILY
        assert obs.year is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type in ("numeric", "missing")
        # Raw locator must carry the canonical asset id + the
        # canonical SPSS raw column name.
        assert obs.raw_locator.asset_id == "polity_v:p5v2018.sav"


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_polity_v_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives Polity V through the new registry and
    never calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    Polity V is the first clean source with no legacy Stage 2
    implementation -- ``STAGE2_ADAPTERS["polity_v"]`` is
    ``None`` per the workplan Done History ("blocked on source
    hygiene"). The test monkeypatches the legacy slot with a
    tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)`` executes
    the new Polity V adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    # Replace the legacy polity_v slot with a tracker that
    # records every invocation. The runner must never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("polity_v")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["polity_v"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_polity_v_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="polity_v"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == (
            _expected_observation_count_for_fixture()
        )

        # The legacy tracker must not have been called -- the
        # new runner routes through the new registry only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["polity_v"] = original


# ---------------------------------------------------------------------------
# Special-code vs valid-negative handling
# ---------------------------------------------------------------------------


def test_polity_v_valid_negative_polity_score_preserved_as_numeric(
    tmp_path: Path,
) -> None:
    """Valid negative ``polity`` scores (``-10..-1``) are preserved
    as numeric observations, NOT coerced to special codes.

    The fixture carries ``AFG 1945: polity=-10`` which is the
    minimum valid score per the Polity V codebook. The unified
    transform MUST emit this as ``value=-10`` /
    ``value_type='numeric'`` so the Stage 5 score module can
    use the value; treating it as a special code would
    silently drop a real political-freedom observation.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(1945,),
    )
    result = runner.run(request)

    # Find the AFG 1945 ``polity`` observation.
    afg_1945_polity = [
        obs for obs in result.observations
        if obs.indicator_code == "polity_v_polity"
        and obs.year == 1945
        and (obs.extension.get("polity_v_scode") == "AFG")
    ]
    assert len(afg_1945_polity) == 1, (
        f"expected exactly 1 AFG 1945 polity observation; "
        f"got {len(afg_1945_polity)}"
    )
    obs = afg_1945_polity[0]
    assert obs.value == -10, (
        f"valid negative score polity=-10 must be preserved as "
        f"numeric; got value={obs.value!r}, "
        f"value_type={obs.value_type!r}"
    )
    assert obs.value_type == "numeric", (
        f"valid negative score polity=-10 must be numeric; "
        f"got value_type={obs.value_type!r}"
    )
    # The raw_value audit must preserve the verbatim raw cell text.
    assert obs.extension.get("raw_value") == "-10", (
        f"raw_value audit must preserve '-10'; got "
        f"{obs.extension.get('raw_value')!r}"
    )


def test_polity_v_special_code_minus_77_emitted_as_missing(
    tmp_path: Path,
) -> None:
    """The documented ``-77`` special code is emitted as
    ``value=None`` / ``value_type='missing'`` with the verbatim
    raw cell text on ``extension.raw_value``.

    The fixture carries ``AFG 1978: polity=-77`` which per the
    Polity V codebook encodes "foreign occupation / interrupted
    polity". The unified transform MUST emit this as missing
    (NOT numeric) so the analyst can see the upstream gap
    without losing the observation id / locator.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(1978,),
    )
    result = runner.run(request)

    # Find the AFG 1978 ``polity`` observation.
    afg_1978_polity = [
        obs for obs in result.observations
        if obs.indicator_code == "polity_v_polity"
        and obs.year == 1978
        and (obs.extension.get("polity_v_scode") == "AFG")
    ]
    assert len(afg_1978_polity) == 1
    obs = afg_1978_polity[0]
    assert obs.value is None, (
        f"special code polity=-77 must be value=None; got "
        f"value={obs.value!r}"
    )
    assert obs.value_type == "missing", (
        f"special code polity=-77 must be value_type='missing'; "
        f"got value_type={obs.value_type!r}"
    )
    # The raw_value audit must preserve the verbatim raw cell text.
    assert obs.extension.get("raw_value") == "-77", (
        f"raw_value audit must preserve '-77'; got "
        f"{obs.extension.get('raw_value')!r}"
    )


def test_polity_v_special_code_minus_66_emitted_as_missing(
    tmp_path: Path,
) -> None:
    """The documented ``-66`` special code is emitted as missing."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(1979,),
    )
    result = runner.run(request)

    afg_1979_polity = [
        obs for obs in result.observations
        if obs.indicator_code == "polity_v_polity"
        and obs.year == 1979
        and (obs.extension.get("polity_v_scode") == "AFG")
    ]
    assert len(afg_1979_polity) == 1
    obs = afg_1979_polity[0]
    assert obs.value is None
    assert obs.value_type == "missing"
    assert obs.extension.get("raw_value") == "-66"


def test_polity_v_special_code_minus_88_emitted_as_missing(
    tmp_path: Path,
) -> None:
    """The documented ``-88`` special code is emitted as missing."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("ALB",),
        years=(1945,),
    )
    result = runner.run(request)

    alb_1945_polity = [
        obs for obs in result.observations
        if obs.indicator_code == "polity_v_polity"
        and obs.year == 1945
        and (obs.extension.get("polity_v_scode") == "ALB")
    ]
    assert len(alb_1945_polity) == 1
    obs = alb_1945_polity[0]
    assert obs.value is None
    assert obs.value_type == "missing"
    assert obs.extension.get("raw_value") == "-88"


# ---------------------------------------------------------------------------
# Per-indicator valid-range semantics: durable > 10 preservation
# ---------------------------------------------------------------------------


def test_polity_v_durable_value_above_10_preserved_as_numeric(
    tmp_path: Path,
) -> None:
    """The ``durable`` indicator is the regime-durability YEARS
    counter; valid numeric observations are preserved when the
    value is greater than 10 (the documented Polity V sub-
    component upper bound).

    The fixture carries ``RUS 2018: durable=19`` which would have
    been silently dropped by the generic non-composite range
    logic (composite: ``-10..+10``; sub-component: ``0..10``);
    the live ``p5v2018.sav`` carries ``durable`` values up to
    170 and 8937 rows > 10. The indicator-specific ``durable``
    rule (valid ``>= 0``, NO upper cap) MUST preserve this
    observation as ``value=19`` / ``value_type='numeric'`` so
    the Stage 5 score module receives the real regime-
    durability evidence rather than a synthetic missing
    placeholder.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("RUS",),
        years=(2018,),
    )
    result = runner.run(request)

    # Find the RUS 2018 ``durable`` observation.
    rus_2018_durable = [
        obs for obs in result.observations
        if obs.indicator_code == "polity_v_durable"
        and obs.year == 2018
        and (obs.extension.get("polity_v_scode") == "RUS")
    ]
    assert len(rus_2018_durable) == 1, (
        f"expected exactly 1 RUS 2018 durable observation; "
        f"got {len(rus_2018_durable)}"
    )
    obs = rus_2018_durable[0]
    assert obs.value == 19, (
        f"durable=19 (regime-durability years > 10) must be "
        f"preserved as numeric; got value={obs.value!r}, "
        f"value_type={obs.value_type!r}. The durable indicator "
        f"is the regime-durability YEARS counter with a valid "
        f"range of >= 0 (no upper cap); generic sub-component "
        f"rules (0..10) MUST NOT silently drop long-running-"
        f"regime durability observations."
    )
    assert obs.value_type == "numeric", (
        f"durable=19 must be value_type='numeric'; got "
        f"{obs.value_type!r}"
    )
    # The audit-trail must preserve the verbatim raw cell text.
    assert obs.extension.get("raw_value") == "19", (
        f"raw_value audit must preserve '19'; got "
        f"{obs.extension.get('raw_value')!r}"
    )
    # The scale label on durable observations is
    # ``polity_durable_years`` (not ``polity_subcomponent``) so
    # Stage 5 score code does not mistakenly treat durable as
    # a 0-10 sub-component.
    assert obs.scale == "polity_durable_years", (
        f"durable observation scale must be "
        f"'polity_durable_years'; got {obs.scale!r}"
    )


def test_polity_v_durable_value_zero_preserved_as_numeric(
    tmp_path: Path,
) -> None:
    """``durable=0`` (a regime with zero years of durability) is
    a valid numeric observation; the indicator-specific lower
    bound is 0 (not 1).
    """
    # The fixture is canonical so we cannot re-stage a custom
    # ``durable=0`` row without re-building the fixture. Instead,
    # we exercise the helper directly via the in-process coercion
    # matrix so the indicator-specific lower bound is asserted
    # without depending on a custom fixture.
    from leaders_db.sources.adapters.polity_v._missing_values import (
        _coerce_polity_value,
    )

    assert (
        _coerce_polity_value(0.0, indicator="durable")
        == 0
    ), (
        "durable=0 must be preserved as numeric (lower bound "
        "is 0, not 1); got None."
    )
    assert (
        _coerce_polity_value(0, indicator="durable")
        == 0
    ), (
        "durable=0 (int) must be preserved as numeric; got None."
    )


def test_polity_v_durable_negative_value_emitted_as_missing() -> None:
    """Negative ``durable`` values that are NOT special codes
    (e.g. ``durable=-1``) are emitted as missing per the
    indicator-specific lower bound of 0.
    """
    from leaders_db.sources.adapters.polity_v._missing_values import (
        _coerce_polity_value,
    )

    assert (
        _coerce_polity_value(-1, indicator="durable")
        is None
    ), (
        "durable=-1 (non-special, below the lower bound of 0) "
        "must be coerced to None (missing); got a numeric value."
    )
    assert (
        _coerce_polity_value(-10, indicator="durable")
        is None
    ), (
        "durable=-10 (non-special, below the lower bound) must "
        "be coerced to None (missing); got a numeric value."
    )


def test_polity_v_durable_special_code_emitted_as_missing() -> None:
    """``durable=-66`` / ``-77`` / ``-88`` are emitted as missing
    via the global special-code set; the indicator-specific
    ``durable`` rule does NOT bypass the special-code gate.
    """
    from leaders_db.sources.adapters.polity_v._missing_values import (
        _coerce_polity_value,
    )

    for special in (-66, -77, -88):
        assert (
            _coerce_polity_value(special, indicator="durable")
            is None
        ), (
            f"durable={special} (documented Polity V special "
            f"code) must be coerced to None (missing) via the "
            f"global special-code gate; got a numeric value."
        )


def test_polity_v_durable_large_value_preserved_as_numeric() -> None:
    """The ``durable`` indicator carries regime-durability YEARS
    counts; long-running regimes produce values well above 10.
    The live ``p5v2018.sav`` carries ``durable`` values up to
    170; the indicator-specific rule (valid ``>= 0``, NO upper
    cap) MUST preserve them as numeric so the Stage 5 score
    module receives the real regime-durability evidence.
    """
    from leaders_db.sources.adapters.polity_v._missing_values import (
        _coerce_polity_value,
    )

    for durable_value in (15, 50, 100, 170):
        assert (
            _coerce_polity_value(durable_value, indicator="durable")
            == durable_value
        ), (
            f"durable={durable_value} (regime-durability YEARS "
            f"counter) must be preserved as numeric per the "
            f"indicator-specific rule (>= 0, no upper cap); "
            f"got None. Generic sub-component rules (0..10) "
            f"MUST NOT silently drop long-running-regime "
            f"durability observations."
        )


# ---------------------------------------------------------------------------
# Schema contract: PolityVSchemaError on missing required columns
# ---------------------------------------------------------------------------


def _build_custom_column_sav(
    out_sav: Path,
    *,
    columns: tuple[str, ...],
    rows: tuple[tuple, ...],
) -> Path:
    """Build a one-off ``.sav`` with the requested columns + rows.

    Used by the missing-column schema-contract tests to stage
    a malformed ``.sav`` whose header does NOT include every
    canonical indicator + identity column. The helper mirrors
    :func:`tests.fixtures.polity_v.build_sample_sav.build_sample_sav`
    but lets each test pick which columns + values to emit.
    """
    import pandas as pd
    import pyreadstat

    out_sav = Path(out_sav)
    out_sav.parent.mkdir(parents=True, exist_ok=True)
    if out_sav.exists():
        out_sav.unlink()

    df = pd.DataFrame(list(rows), columns=list(columns))
    pyreadstat.write_sav(df, str(out_sav))
    return out_sav


def _stage_custom_column_bundle(
    raw_root: Path,
    *,
    columns: tuple[str, ...],
    rows: tuple[tuple, ...],
) -> Path:
    """Stage a Polity V bundle whose ``.sav`` carries only the
    caller-specified columns.

    Mirrors :func:`_stage_polity_v_bundle` but writes a custom
    .sav via :func:`_build_custom_column_sav`. The
    ``metadata.json`` is otherwise identical (canonical version
    + canonical primary shape) so the readiness gate passes
    -- the missing-column failure MUST fire at the raw-read
    schema boundary, NOT at the metadata-presence boundary.
    """
    import hashlib

    bundle_dir = raw_root / "polity_v"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    staged_sav = bundle_dir / "p5v2018.sav"
    _build_custom_column_sav(staged_sav, columns=columns, rows=rows)
    payload = {
        "source_name": (
            "Polity5: Political Regime Characteristics and "
            "Transitions, 1800-2018"
        ),
        "source_version": POLITY_V_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1800-2018, ~167 countries",
        "years_available": "1800-2018",
        "license_note": (
            "Free academic use; cite Marshall, Jaggers, "
            "Gleditsch 2018."
        ),
        "local_files": ["p5v2018.sav"],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://www.systemicpeace.org/inscr/p5v2018.sav"
        ),
        # Compute the SHA-256 of the just-written .sav so the
        # readiness gate's checksum match fires (the schema
        # violation must surface AT the raw-read schema
        # boundary, not as a checksum mismatch or a missing-
        # metadata blocker).
        "checksum_sha256": (
            hashlib.sha256(staged_sav.read_bytes()).hexdigest()
        ),
        "notes": (
            "Polity V (Polity5 v2018) staged for unified-source "
            "schema-contract test; this .sav carries a custom "
            "column subset so the raw-read boundary raises "
            "PolityVSchemaError."
        ),
    }
    (bundle_dir / POLITY_V_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


def test_polity_v_missing_indicator_column_raises_schema_error(
    tmp_path: Path,
) -> None:
    """A ``.sav`` missing a catalog indicator column (here
    ``durable``) MUST raise :class:`PolityVSchemaError` at the
    raw-read boundary -- the transform layer MUST NOT silently
    emit partial output on a schema violation.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        PolityVSchemaError,
        create_polity_v_adapter,
    )

    # Build a malformed ``.sav`` with all identity + indicator
    # columns EXCEPT ``durable``. One row is enough to trigger
    # the schema check.
    raw_root = tmp_path / "raw"
    columns = (
        "p5", "cyear", "ccode", "scode", "country", "year",
        "flag", "fragment",
        "democ", "autoc",
        "polity", "polity2",
        # NOTE: ``durable`` intentionally OMITTED.
        "xrreg", "xrcomp", "xropen", "xconst", "parreg", "parcomp",
        "exrec", "exconst", "polcomp", "prior",
        "emonth", "eday", "eyear", "eprec", "interim",
        "bmonth", "bday", "byear", "bprec", "post",
        "change", "d5", "sf", "regtrans",
    )
    rows = (
        (
            1.0, 22018.0, 2.0, "USA", "United States", 2018.0,
            0.0, 0.0, 8.0, 0.0,
            8.0, 8.0,
            3.0, 3.0, 4.0, 7.0, 2.0, 3.0,
            8.0, 7.0, 7.0, None,
            None, None, None, None, 8.0,
            None, None, None, None, None,
            None, None, None, -1.0,
        ),
    )
    _stage_custom_column_bundle(
        raw_root, columns=columns, rows=rows,
    )

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    # The runner propagates the structured failure -- the
    # transform layer MUST NOT silently emit partial output.
    with pytest.raises(PolityVSchemaError) as exc_info:
        runner.run(request)

    err = exc_info.value
    # The structured failure MUST name the missing column so a
    # developer can act on it without reading source code.
    assert "durable" in err.missing_columns, (
        f"PolityVSchemaError.missing_columns must include "
        f"'durable'; got {err.missing_columns!r}"
    )
    assert err.code == "polity_v_schema_error", (
        f"PolityVSchemaError.code must be the structured "
        f"'polity_v_schema_error' code; got {err.code!r}"
    )
    assert err.source_id == SourceId(slug="polity_v"), (
        f"PolityVSchemaError.source_id must carry the failing "
        f"source slug 'polity_v'; got {err.source_id!r}"
    )
    # The diagnostic message must mention the missing column
    # by name + the expected column set so a CLI / log line is
    # self-describing.
    assert "durable" in str(err), (
        f"PolityVSchemaError message must mention the missing "
        f"column 'durable'; got {str(err)!r}"
    )


def test_polity_v_missing_identity_column_raises_schema_error(
    tmp_path: Path,
) -> None:
    """A ``.sav`` missing an identity column (here ``scode``)
    MUST raise :class:`PolityVSchemaError` -- the transform
    layer builds the per-row ``source_row_reference`` from
    identity columns and MUST NOT silently emit partial output
    when an identity column is missing.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        PolityVSchemaError,
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    # Build a malformed ``.sav`` with all 11 catalog indicator
    # columns but missing the ``scode`` identity column.
    columns = (
        "p5", "cyear", "ccode", "country", "year",  # NOTE: scode OMITTED
        "flag", "fragment",
        "democ", "autoc", "polity", "polity2", "durable",
        "xrreg", "xrcomp", "xropen", "xconst", "parreg", "parcomp",
        "exrec", "exconst", "polcomp", "prior",
        "emonth", "eday", "eyear", "eprec", "interim",
        "bmonth", "bday", "byear", "bprec", "post",
        "change", "d5", "sf", "regtrans",
    )
    rows = (
        (
            1.0, 22018.0, 2.0, "United States", 2018.0,
            0.0, 0.0, 8.0, 0.0,
            8.0, 8.0, None,
            3.0, 3.0, 4.0, 7.0, 2.0, 3.0,
            8.0, 7.0, 7.0, None,
            None, None, None, None, 8.0,
            None, None, None, None, None,
            None, None, None, -1.0,
        ),
    )
    _stage_custom_column_bundle(
        raw_root, columns=columns, rows=rows,
    )

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    with pytest.raises(PolityVSchemaError) as exc_info:
        runner.run(request)

    err = exc_info.value
    assert "scode" in err.missing_columns, (
        f"PolityVSchemaError.missing_columns must include "
        f"'scode'; got {err.missing_columns!r}"
    )
    assert err.code == "polity_v_schema_error"
    assert err.source_id == SourceId(slug="polity_v")
    assert "scode" in str(err)


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_polity_v_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    USA rows in the fixture: USA 1945 + USA 2018 = 2 rows.
    Per-row observation count: 2 x 11 indicators = 22.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 22
    assert all(
        obs.extension.get("polity_v_scode") == "USA"
        for obs in result.observations
    )


def test_polity_v_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2018,)`` filters to 2018 rows only.

    2018 rows in the fixture: USA 2018 + MEX 2018 + RUS 2018 = 3 rows.
    Per-row observation count: 3 x 11 indicators = 33.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        years=(2018,),
    )
    result = runner.run(request)
    assert len(result.observations) == 33
    assert {obs.year for obs in result.observations} == {2018}


def test_polity_v_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``years=(2018,) + countries=('USA',)`` filters to USA 2018 only.

    USA 2018 only: 1 row x 11 indicators = 11 observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        years=(2018,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 11
    assert {obs.year for obs in result.observations} == {2018}
    assert all(
        obs.extension.get("polity_v_scode") == "USA"
        for obs in result.observations
    )


# ---------------------------------------------------------------------------
# Out-of-coverage + unsupported filter
# ---------------------------------------------------------------------------


def test_polity_v_out_of_coverage_year_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(2023,)`` returns zero observations + a structured
    :class:`SourceWarning` -- no stale-proxy fill.

    Polity V covers 1800-2018 (SRC-COV-001). A request for the
    prototype's target year 2023 falls outside the coverage
    envelope (SRC-COV-002) and MUST emit zero rows plus a
    structured warning (SRC-COV-003: no silent stale-proxy
    fill).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "Polity V covers 1800-2018; year=2023 must yield zero "
        "observations (no stale-proxy fill)."
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "year_absent"
        for w in result.warnings
    ), (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )


def test_polity_v_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Biden',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently ignoring
    the filter (SRC-REQ-005).

    The Polity V transform does not consume leader identity;
    the filter is rejected explicitly so a developer can act on
    it without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_polity_v_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        leaders=("Biden",),
    )
    result = runner.run(request)

    # The fixture rows are still emitted (the filter does not
    # alter the row set; it just emits the warning).
    assert len(result.observations) == (
        _expected_observation_count_for_fixture()
    )
    assert any(
        isinstance(w, SourceWarning) and w.code == "unsupported_filter"
        for w in result.warnings
    ), (
        "leaders filter must surface an UNSUPPORTED_FILTER "
        f"warning; got {result.warnings!r}"
    )


# ---------------------------------------------------------------------------
# Readiness failure paths
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
    assert err.source_id == SourceId(slug="polity_v"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyPolityVAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips ``read_raw`` / ``transform``."""
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    # The error names the source slug so callers can act on it
    # without reading source code.
    assert "polity_v" in str(exc_info.value).lower(), (
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
        "check_ready must have been called at least once; "
        f"actual spy calls: {spy.calls!r}"
    )


def test_polity_v_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='p5v2017')`` against a
    canonical Polity V bundle MUST fail readiness with a
    structured error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error."
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        POLITY_V_DEFAULT_VERSION,
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        source_version="p5v2017",
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="p5v2017",
    )
    err = readiness.errors[0]
    assert POLITY_V_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{POLITY_V_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_missing_metadata_fails_readiness_and_blocks_runner(
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
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the .sav (no ``metadata.json``) -- mirrors the
    # legacy ``p5v2018_no_metadata`` fixture contract.
    bundle_dir = raw_root / "polity_v"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "polity_v"
    shutil.copy2(fixtures / POLITY_V_TEST_FIXTURE_SAV, bundle_dir / "p5v2018.sav")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_missing_sav_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``p5v2018.sav`` missing from the bundle => readiness
    blocker; runner does not progress.

    The error message must mention ``p5v2018.sav`` so a
    developer can fix the upstream issue without reading source
    code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage a valid ``metadata.json`` but omit the .sav.
    bundle_dir = raw_root / "polity_v"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    metadata_payload = {
        "source_name": (
            "Polity5: Political Regime Characteristics and "
            "Transitions, 1800-2018"
        ),
        "source_version": "p5v2018",
        "download_date": "2026-06-27",
        "coverage": "1800-2018, ~167 countries",
        "years_available": "1800-2018",
        "license_note": "Free academic use.",
        "local_files": ["p5v2018.sav"],
        "ingestion_status": "downloaded",
        "source_url": "https://www.systemicpeace.org/inscr/p5v2018.sav",
        "checksum_sha256": "0" * 64,  # placeholder; not verified since .sav is absent
        "notes": "test fixture",
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(metadata_payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_raw",
        expected_substring="p5v2018.sav",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_checksum_mismatch_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A wrong ``checksum_sha256`` in ``metadata.json`` => readiness
    blocker; runner does not progress.

    The error message must mention ``checksum`` so a developer
    can re-stage the .sav without reading source code.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)

    # Mutate the well-formed bundle's ``checksum_sha256`` to a
    # value that does not match the staged .sav bytes.
    bad_path = raw_root / "polity_v" / "metadata.json"
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = "0" * 64
    bad_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_ingestion_status_not_downloaded_fails_readiness(
    tmp_path: Path,
) -> None:
    """``ingestion_status`` not ``'downloaded'`` => readiness blocker."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)
    metadata_path = raw_root / "polity_v" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["ingestion_status"] = "pending"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="ingestion_status",
    )
    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_local_files_missing_sav_fails_readiness(
    tmp_path: Path,
) -> None:
    """``local_files`` does not include ``p5v2018.sav`` => readiness blocker."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)
    metadata_path = raw_root / "polity_v" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["local_files"] = ["some_other_file.sav"]
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="local_files",
    )
    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_missing_metadata_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Missing metadata ``source_version`` is a readiness blocker.

    The unified Polity V adapter's required-fields check fires
    first; a missing ``source_version`` field surfaces as a
    ``missing_metadata`` error (the canonical required-fields
    contract) so the runner refuses to dispatch. Mirrors the
    PWT / WGI / V-Dem / UCDP / CPI / PTS pattern.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)
    metadata_path = raw_root / "polity_v" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("source_version")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )
    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_mismatched_metadata_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Metadata ``source_version`` must match canonical ``p5v2018``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.polity_v import (
        POLITY_V_DEFAULT_VERSION,
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)
    metadata_path = raw_root / "polity_v" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["source_version"] = "p5v2017"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_polity_v_adapter()
    spy = _SpyPolityVAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="p5v2017",
    )
    assert POLITY_V_DEFAULT_VERSION in readiness.errors[0].message
    _assert_runner_does_not_progress(registry, request, spy)


def test_polity_v_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.polity_v import (
        POLITY_V_DEFAULT_VERSION,
        create_polity_v_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_polity_v_bundle(raw_root)
    adapter = create_polity_v_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="polity_v"),
        raw_root=raw_root,
        years=(2018,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == POLITY_V_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version for observation in result.observations
    } == {POLITY_V_DEFAULT_VERSION}


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.polity_v must not import legacy
# ---------------------------------------------------------------------------


def test_polity_v_adapter_module_does_not_import_legacy_ingest_at_import() -> None:
    """``import leaders_db.sources.adapters.polity_v`` MUST NOT
    import ``leaders_db.ingest`` at any depth (SRC-MIG-007 +
    ``docs/architecture/sources.md`` §10.1).

    Polity V is the first source from the "databases not yet in
    legacy" list -- there is no legacy Stage 2 module to reuse
    (Polity V has no ``leaders_db.ingest.polity_v`` module). The
    adapter reads the staged ``p5v2018.sav`` directly via
    ``pyreadstat.read_sav`` (lazy-imported inside the raw-read
    function), so the package boundary is preserved.

    The test inspects the new module's source AST and asserts
    that the only ``leaders_db.ingest.*`` import statements are
    scoped inside function bodies (lazy imports), NOT at module
    top level. Module-level eager imports of ``leaders_db.ingest``
    are forbidden because they would pull the legacy ingest
    package into ``sys.modules`` at package import time and
    break the documented boundary.
    """
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "polity_v"
        / "adapter.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    legacy_top_level: list[str] = []

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

    assert legacy_top_level == [], (
        f"{module_path} has eager top-level legacy ingest "
        f"imports; the new Polity V adapter must import legacy "
        f"code lazily inside methods only (SRC-MIG-007). Found: "
        f"{legacy_top_level}"
    )


def test_polity_v_package_import_does_not_register_legacy_polity_v() -> None:
    """``import leaders_db.sources.adapters.polity_v`` MUST NOT
    touch ``STAGE2_ADAPTERS["polity_v"]``.

    Polity V is the first clean source with no legacy Stage 2
    implementation -- ``STAGE2_ADAPTERS["polity_v"]`` is
    ``None`` per the workplan Done History ("blocked on source
    hygiene"). The new adapter must not mutate this slot on
    import or factory call.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import InMemorySourceRegistry
    from leaders_db.sources.adapters.polity_v import (
        create_polity_v_adapter,
        register_polity_v,
    )

    # Snapshot the legacy slot BEFORE we touch the new package.
    sentinel_before = object()
    original = legacy_ingest.STAGE2_ADAPTERS.get("polity_v")
    legacy_ingest.STAGE2_ADAPTERS["polity_v"] = sentinel_before
    try:
        # Create / register against the NEW registry -- this
        # must not mutate the legacy table.
        adapter = create_polity_v_adapter()
        new_registry = InMemorySourceRegistry()
        register_polity_v(new_registry)

        assert legacy_ingest.STAGE2_ADAPTERS.get("polity_v") is (
            sentinel_before
        ), (
            "the new Polity V adapter module must not mutate "
            "the legacy STAGE2_ADAPTERS table on import or "
            "factory call"
        )
        # The new registry carries polity_v; the legacy table
        # does NOT see the new adapter.
        assert (
            new_registry.list_descriptors()[0].source_id.slug
            == "polity_v"
        )
        assert legacy_ingest.STAGE2_ADAPTERS["polity_v"] is sentinel_before
        assert adapter.descriptor.source_id.slug == "polity_v"
    finally:
        legacy_ingest.STAGE2_ADAPTERS["polity_v"] = original


__all__ = [
    "POLITY_V_TEST_ATTRIBUTION_KEY",
    "POLITY_V_TEST_COVERAGE_END",
    "POLITY_V_TEST_COVERAGE_START",
    "POLITY_V_TEST_DEFAULT_VERSION",
    "POLITY_V_TEST_FAMILY",
    "POLITY_V_TEST_FIXTURE_SAV",
    "POLITY_V_TEST_FIXTURE_SAV_SHA256",
    "POLITY_V_TEST_HOMEPAGE_URL",
    "POLITY_V_TEST_METADATA_NAME",
    "test_polity_v_adapter_is_registerable_through_in_memory_registry",
    "test_polity_v_adapter_module_does_not_import_legacy_ingest_at_import",
    "test_polity_v_adapter_satisfies_source_adapter_protocol",
    "test_polity_v_attribution_text_matches_attributions_doc",
    "test_polity_v_canonical_metadata_version_propagates_to_assets_and_observations",
    "test_polity_v_checksum_mismatch_fails_readiness_and_blocks_runner",
    "test_polity_v_combined_year_and_country_filter",
    "test_polity_v_country_filter_is_applied",
    "test_polity_v_descriptor_exposes_documented_static_metadata",
    "test_polity_v_durable_large_value_preserved_as_numeric",
    "test_polity_v_durable_negative_value_emitted_as_missing",
    "test_polity_v_durable_special_code_emitted_as_missing",
    "test_polity_v_durable_value_above_10_preserved_as_numeric",
    "test_polity_v_durable_value_zero_preserved_as_numeric",
    "test_polity_v_ingestion_status_not_downloaded_fails_readiness",
    "test_polity_v_leader_filter_emits_unsupported_filter_warning",
    "test_polity_v_local_files_missing_sav_fails_readiness",
    "test_polity_v_mismatched_metadata_source_version_fails_readiness",
    "test_polity_v_missing_identity_column_raises_schema_error",
    "test_polity_v_missing_indicator_column_raises_schema_error",
    "test_polity_v_missing_metadata_fails_readiness_and_blocks_runner",
    "test_polity_v_missing_metadata_source_version_fails_readiness",
    "test_polity_v_missing_sav_fails_readiness_and_blocks_runner",
    "test_polity_v_out_of_coverage_year_returns_zero_and_warning",
    "test_polity_v_package_import_does_not_register_legacy_polity_v",
    "test_polity_v_register_helper_registers_against_explicit_registry",
    "test_polity_v_runner_does_not_consult_legacy_stage2_adapters",
    "test_polity_v_runner_produces_normalized_observations",
    "test_polity_v_special_code_minus_66_emitted_as_missing",
    "test_polity_v_special_code_minus_77_emitted_as_missing",
    "test_polity_v_special_code_minus_88_emitted_as_missing",
    "test_polity_v_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_polity_v_valid_negative_polity_score_preserved_as_numeric",
    "test_polity_v_year_filter_is_applied",
]
