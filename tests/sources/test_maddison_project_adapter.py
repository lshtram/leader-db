"""Phase C / D slice -- Maddison Project Database 2023 adapter
under the unified ``leaders_db.sources``.

The Maddison Project Database 2023 adapter is the second source
rebuilt under the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 2,
docs/requirements/sources.md §12 SRC-MIG-005), after the PWT
10.01 adapter. The legacy Maddison reader / transform /
catalog loader under ``leaders_db.ingest.maddison_project*`` is
reused internally via lazy imports -- the package boundary at
docs/architecture/sources.md §10.1 is preserved.

Tests cover the documented slice acceptance criteria:

- The Maddison adapter descriptor is registerable / listable
  through the new :class:`InMemorySourceRegistry` and exposes
  the documented static metadata.
- The Maddison descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``maddison_project``,
  default version ``2023``, attribution_key ``maddison_project``,
  dataset type, 1-2022 coverage hint, ``economic_country_year``
  observation family, canonical Maddison Project homepage URL).
- :class:`SourceIngestRunner` can run Maddison end-to-end through
  the new registry against a fixture ``raw_root`` and produce
  :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter internally
  reuses legacy parsing modules, but dispatch is registry-based).
- ``years=`` and ``countries=`` filters are honored and surface
  correct observation counts.
- ``years=(2023,)`` triggers the documented 1-year-gap proxy
  mapping to 2022 data: every emitted observation carries the
  ``proxy_year`` quality flag plus the ``requested_year`` /
  ``proxy_source_year`` extension fields, and the readiness
  envelope surfaces a structured ``maddison_project_proxy_year``
  warning.
- ``years=(2024,)`` (or any year beyond the 1-2022 coverage
  envelope) emits zero observations plus a structured
  ``YEAR_ABSENT`` warning -- no multi-year stale-proxy fill
  (SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Importing the new ``leaders_db.sources.adapters.maddison_project``
  module does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  docs/architecture/sources.md §10.1).
- The readiness gate rejects the documented blockers: missing
  metadata, missing xlsx, checksum mismatch, missing /
  mismatched metadata ``source_version``, and unsupported
  request ``source_version``. The runner refuses to dispatch
  ``read_raw`` / ``transform`` for any blocker.

PASS-ELIGIBLE rationale
-----------------------
The legacy Maddison reader / transform / catalog loader are
well-tested via the existing ``tests/test_ingest_maddison_project.py``
suite. The tests in this file prove that the new
``leaders_db.sources.adapters.maddison_project`` adapter wraps
the legacy parsing logic behind the unified ``SourceAdapter``
Protocol while preserving the package-isolation contract --
they are PASS-ELIGIBLE because the adapter implementation
lands in the same change set.
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
    from leaders_db.sources.contracts import ReadinessResult

MADDIson_TEST_FIXTURE_XLSX: str = "mpd2023.xlsx"
MADDIson_TEST_METADATA_NAME: str = "metadata.json"
MADDIson_TEST_ATTRIBUTION_KEY: str = "maddison_project"
MADDIson_TEST_DEFAULT_VERSION: str = "2023"
MADDIson_TEST_COVERAGE_START: int = 1
MADDIson_TEST_COVERAGE_END: int = 2022
MADDIson_TEST_PROXY_REQUESTED_YEAR: int = 2023
MADDIson_TEST_PROXY_YEAR: int = 2022
MADDIson_TEST_FAMILY: str = "economic_country_year"
MADDIson_TEST_HOMEPAGE_URL: str = (
    "https://www.rug.nl/ggdc/historicaldevelopment/maddison/"
    "releases/maddison-project-database-2023"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyMaddisonProjectAdapter:
    """Wrap a :class:`MaddisonProjectAdapter` and record every lifecycle call.

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


def _stage_maddison_project_bundle(raw_root: Path) -> Path:
    """Stage the canonical Maddison fixture bundle under ``raw_root/maddison_project``.

    Copies ``tests/fixtures/maddison_project/sample.xlsx`` into
    ``<raw_root>/maddison_project/mpd2023.xlsx`` and writes a
    well-formed ``metadata.json`` whose ``checksum_sha256``
    matches the staged xlsx bytes. Returns the resolved bundle
    directory.

    The xlsx carries 4 countries (IND, MEX, SWE, USA) over
    2021-2022 (SWE is only present for 2021); per-row non-blank
    catalog cell counts are documented in
    ``tests/fixtures/maddison_project/build_sample_xlsx.py``.
    The fixture emits 7 country-years x 3 indicators = 21 long
    rows when both ``gdppc`` and ``pop`` are present, and
    ``country=USA, year=2021`` carries 3 observations (gdppc +
    pop + derived total).
    """
    bundle_dir = raw_root / "maddison_project"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "maddison_project"
    fixture_xlsx = fixtures / "sample.xlsx"
    shutil.copy2(fixture_xlsx, bundle_dir / MADDIson_TEST_FIXTURE_XLSX)
    sha = hashlib.sha256(
        (bundle_dir / MADDIson_TEST_FIXTURE_XLSX).read_bytes(),
    ).hexdigest()
    payload = {
        "source_name": "Maddison Project Database 2023",
        "source_version": MADDIson_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-24",
        "coverage": (
            "country-year (one row per (countrycode, year) in the "
            "'Full data' sheet; 169 countries; years 1-2022)"
        ),
        "years_available": (
            "1-2022 (no 2023 data in the 2023 release; 2023 "
            "target-year requests are proxied to 2022 per the "
            "CIRIGHTS / UNDP HDI / Leader Survival 1-year-gap "
            "pattern)"
        ),
        "license_note": (
            "CC BY 4.0 International. Cite Bolt and van Zanden "
            "(2024) verbatim; see docs/sources/attributions.md "
            "for the canonical citation text."
        ),
        "local_files": [MADDIson_TEST_FIXTURE_XLSX],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://dataverse.nl/api/access/datafile/421302"
        ),
        # Per-file dict shape (the Maddison bundle's canonical
        # checksum format); the readiness gate also accepts the
        # flat-string PWT-compatible shape.
        "checksum_sha256": {
            MADDIson_TEST_FIXTURE_XLSX: sha,
        },
    }
    (bundle_dir / MADDIson_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_maddison_project_descriptor_exposes_documented_static_metadata() -> None:
    """The Maddison Project descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "maddison_project"``
    - ``display_name == "Maddison Project Database 2023"``
    - ``source_type == "dataset"``
    - ``default_version == "2023"``
    - ``homepage_url`` is the canonical Maddison Project 2023
      release URL.
    - ``attribution_key == "maddison_project"``
    - ``coverage_hint.start_year == 1``,
      ``coverage_hint.end_year == 2022``.
    - ``supported_observation_families == ("economic_country_year",)``.

    PASS-ELIGIBLE: the descriptor factory ships with the slice.
    """
    from leaders_db.sources.adapters.maddison_project import (
        build_maddison_project_descriptor,
    )

    descriptor = build_maddison_project_descriptor()

    assert descriptor.source_id.slug == "maddison_project"
    assert descriptor.display_name == "Maddison Project Database 2023"
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == MADDIson_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == MADDIson_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == MADDIson_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == MADDIson_TEST_COVERAGE_START
    assert descriptor.coverage_hint.end_year == MADDIson_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == (MADDIson_TEST_FAMILY,)
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_maddison_project_attribution_text_matches_attributions_doc() -> None:
    """The Maddison Project attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical Maddison citation block
    in ``docs/sources/attributions.md`` is the source of truth;
    the adapter module's constant must be byte-identical to a
    substring of that doc.
    """
    from leaders_db.sources.adapters.maddison_project import (
        MADDISON_PROJECT_ATTRIBUTION_TEXT,
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
    assert MADDISON_PROJECT_ATTRIBUTION_TEXT in attributions_text, (
        f"{MADDISON_PROJECT_ATTRIBUTION_TEXT!r} is not a substring "
        f"of {attributions_path}. Update both in the same commit "
        f"(Rule #15)."
    )


def test_maddison_project_adapter_satisfies_source_adapter_protocol() -> None:
    """``MaddisonProjectAdapter`` instances satisfy the runtime-checkable Protocol."""
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    adapter = create_maddison_project_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "maddison_project"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_maddison_project_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_maddison_project_adapter()`` produces an adapter the registry accepts."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_maddison_project_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "maddison_project"

    resolved = registry.get_descriptor(SourceId(slug="maddison_project"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="maddison_project")) is adapter


def test_maddison_project_register_helper_registers_against_explicit_registry() -> None:
    """``register_maddison_project(registry)`` is the explicit seam."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.maddison_project import (
        register_maddison_project,
    )

    registry = InMemorySourceRegistry()
    adapter = register_maddison_project(registry)
    assert registry.get_adapter(SourceId(slug="maddison_project")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_maddison_project_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives Maddison through the
    documented lifecycle and emits :class:`NormalizedObservation`
    records.

    The fixture has 4 countries (IND, MEX, SWE, USA) x 2 years
    (2021-2022, SWE only has 2021) x 3 indicators (gdppc, pop,
    derived total). The full no-filter run yields:

    - IND 2021, IND 2022, MEX 2021, MEX 2022, SWE 2021,
      USA 2021, USA 2022 = 7 country-years
    - 7 country-years x 3 indicators = 21 observations when
      both gdppc and pop are present for the same row.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 21, (
        f"expected 21 observations (7 country-years x 3 indicators); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "maddison_project"
        assert obs.observation_family == MADDIson_TEST_FAMILY
        assert obs.year is not None
        assert obs.country_code is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        assert obs.raw_locator.sheet == "Full data"
        # No 2023 proxy on the unfiltered full run: the fixture
        # does NOT include year=2023 in the request, so the
        # proxy_year quality flag must NOT be present.
        assert "proxy_year" not in obs.quality_flags


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_maddison_project_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives Maddison through the new registry and
    never calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["maddison_project"]``
    with a tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)`` executes
    the new Maddison adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("maddison_project")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["maddison_project"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_maddison_project_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="maddison_project"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 21

        # The legacy tracker must not have been called -- the
        # new runner routes through the new registry only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["maddison_project"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_maddison_project_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2022,)`` filters to 2022 rows only.

    The fixture has 3 country-years in 2022 (IND, MEX, USA --
    SWE is 2021 only). 3 country-years x 3 indicators = 9
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        years=(2022,),
    )
    result = runner.run(request)
    assert len(result.observations) == 9
    assert {obs.year for obs in result.observations} == {2022}


def test_maddison_project_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` filters to USA rows only.

    USA has 2 country-years (2021, 2022). 2 x 3 indicators = 6
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 6
    assert {obs.country_code for obs in result.observations} == {"USA"}


def test_maddison_project_combined_year_and_country_filter(
    tmp_path: Path,
) -> None:
    """``years=(2022,) + countries=('USA',)`` filters to USA 2022 only.

    USA 2022 x 3 indicators = 3 observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        years=(2022,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 3
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.year for obs in result.observations} == {2022}


# ---------------------------------------------------------------------------
# Documented 2023 -> 2022 proxy mapping + out-of-coverage behavior
# ---------------------------------------------------------------------------


def test_maddison_project_2023_request_proxies_to_2022_with_warning(
    tmp_path: Path,
) -> None:
    """``years=(2023,)`` triggers the documented 1-year-gap
    proxy mapping: 2023 -> 2022.

    The fixture has 3 country-years in 2022 (IND, MEX, USA --
    SWE is 2021 only). The proxy emits 9 observations (3
    country-years x 3 indicators) and surfaces:

    - A ``maddison_project_proxy_year`` structured warning on
      the result envelope.
    - A ``proxy_year`` quality flag on every emitted observation.
    - ``requested_year=2023`` and ``proxy_source_year=2022`` in
      every observation's ``extension`` payload.
    - The canonical ``attribution`` text in every observation's
      ``extension`` payload (Rule #15).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.maddison_project import (
        MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
        MADDISON_PROJECT_PROXY_YEAR,
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        years=(MADDISON_PROJECT_PROXY_REQUESTED_YEAR,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert len(result.observations) == 9, (
        f"expected 9 proxy observations (3 country-years x 3 "
        f"indicators); got {len(result.observations)}"
    )
    # Every observation is a 2022 source-year row carrying the
    # proxy_year quality flag + the requested/proxy year pair
    # in its extension payload.
    for obs in result.observations:
        assert obs.year == MADDISON_PROJECT_PROXY_YEAR
        assert "proxy_year" in obs.quality_flags
        ext = obs.extension
        assert ext.get("requested_year") == (
            MADDISON_PROJECT_PROXY_REQUESTED_YEAR
        )
        assert ext.get("proxy_source_year") == MADDISON_PROJECT_PROXY_YEAR
        # Attribution must be carried forward (Rule #15).
        assert "Bolt" in str(ext.get("attribution", ""))
        assert "van Zanden" in str(ext.get("attribution", ""))

    # The readiness envelope surfaces the proxy warning so
    # the proxy mapping is never silent.
    proxy_warnings = [
        w for w in result.warnings
        if isinstance(w, SourceWarning)
        and w.code == "maddison_project_proxy_year"
    ]
    assert proxy_warnings, (
        "request envelope must carry a structured "
        "maddison_project_proxy_year warning naming the 2023 -> "
        f"2022 mapping; got {result.warnings!r}"
    )
    warning = proxy_warnings[0]
    assert warning.context.get("requested_year") == (
        MADDISON_PROJECT_PROXY_REQUESTED_YEAR
    )
    assert warning.context.get("proxy_source_year") == (
        MADDISON_PROJECT_PROXY_YEAR
    )


def test_maddison_project_2024_request_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``years=(2024,)`` emits zero observations + a structured
    ``YEAR_ABSENT`` warning -- no multi-year stale-proxy fill.

    Maddison Project Database 2023 ends at year 2022. A
    request for 2024 falls outside the coverage envelope
    (SRC-COV-002) and MUST emit zero rows plus a structured
    warning (SRC-COV-003: no silent stale-proxy fill). The
    documented 2023 -> 2022 proxy is a SINGLE-YEAR exception;
    multi-year stale-proxy fills are forbidden.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        years=(2024,),
    )
    result = runner.run(request)

    assert result.readiness.ready is True
    assert result.observations == (), (
        "Maddison Project Database 2023 covers 1-2022; "
        "year=2024 must yield zero observations (no multi-year "
        "stale-proxy fill)."
    )
    year_absent_warnings = [
        w for w in result.warnings
        if isinstance(w, SourceWarning) and w.code == "year_absent"
    ]
    assert year_absent_warnings, (
        "result envelope must carry a YEAR_ABSENT warning "
        f"naming the out-of-coverage year; got {result.warnings!r}"
    )
    # The 2024 warning must name 2024 + the coverage envelope so
    # the developer can act on it.
    warning = year_absent_warnings[0]
    assert warning.context.get("year") == 2024
    assert warning.context.get("coverage_end_year") == 2022


def test_maddison_project_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``leaders=('Lopez Obrador',)`` surfaces a structured
    ``UNSUPPORTED_FILTER`` warning rather than silently
    ignoring the filter (SRC-REQ-005).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_maddison_project_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        leaders=("Lopez Obrador",),
    )
    result = runner.run(request)

    # All 21 fixture rows are still emitted (the filter does
    # not alter the row set; it just emits the warning).
    assert len(result.observations) == 21
    assert any(
        isinstance(w, SourceWarning) and w.code == "unsupported_filter"
        for w in result.warnings
    ), (
        "leaders filter must surface an UNSUPPORTED_FILTER "
        f"warning; got {result.warnings!r}"
    )


# ---------------------------------------------------------------------------
# Readiness failure path (Blocker 1 + Blocker 2)
# ---------------------------------------------------------------------------


def _assert_readiness_error_envelope(
    readiness: ReadinessResult,
    *,
    expected_code: str,
    expected_substring: str,
) -> None:
    """Assert the readiness-error contract shared by all blocker tests."""
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
    assert err.source_id == SourceId(slug="maddison_project"), (
        f"blocker must carry the source id; got {err.source_id!r}"
    )
    assert expected_substring.lower() in err.message.lower(), (
        f"blocker message must mention {expected_substring!r} so a "
        f"developer can act on it; got {err.message!r}"
    )


def _assert_runner_does_not_progress(
    registry: Any,
    request: SourceIngestRequest,
    spy: _SpyMaddisonProjectAdapter,
) -> None:
    """Assert ``runner.run(request)`` raises and skips
    ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import SourceIngestRunner

    runner = SourceIngestRunner(registry=registry)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run(request)

    assert "maddison_project" in str(exc_info.value).lower(), (
        f"runner RuntimeError must name the failing source slug; "
        f"got {exc_info.value!r}"
    )

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


def test_maddison_project_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest(source_version='9999')`` against a
    canonical Maddison Project 2023 bundle MUST fail readiness
    with a structured error -- not a warning.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." The legacy bundle does not encode
    a per-version stamp beyond ``metadata.json['source_version']``;
    silently propagating an unsupported version into
    ``RawAsset.version`` / ``NormalizedObservation.source_version``
    would lie to downstream scorers (Rule #6 / Rule #15).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.maddison_project import (
        MADDISON_PROJECT_DEFAULT_VERSION,
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        source_version="9999",
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    err = readiness.errors[0]
    assert MADDISON_PROJECT_DEFAULT_VERSION in err.message, (
        f"error message must name the canonical version "
        f"{MADDISON_PROJECT_DEFAULT_VERSION!r}; got {err.message!r}"
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_missing_metadata_fails_readiness_and_blocks_runner(
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
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the xlsx (no ``metadata.json``).
    bundle_dir = raw_root / "maddison_project"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "maddison_project"
    shutil.copy2(fixtures / "sample.xlsx", bundle_dir / "mpd2023.xlsx")

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="metadata",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_missing_xlsx_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """``mpd2023.xlsx`` missing from the bundle => readiness
    blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage a valid ``metadata.json`` but omit the xlsx.
    bundle_dir = raw_root / "maddison_project"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    metadata_payload = {
        "source_name": "Maddison Project Database 2023",
        "source_version": MADDIson_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-24",
        "coverage": "country-year",
        "license_note": "CC BY 4.0",
        "local_files": [MADDIson_TEST_FIXTURE_XLSX],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://dataverse.nl/api/access/datafile/421302"
        ),
        "checksum_sha256": {
            MADDIson_TEST_FIXTURE_XLSX: "0" * 64,
        },
    }
    (bundle_dir / MADDIson_TEST_METADATA_NAME).write_text(
        json.dumps(metadata_payload, indent=2), encoding="utf-8",
    )

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_raw",
        expected_substring="mpd2023.xlsx",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_checksum_mismatch_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """A wrong ``checksum_sha256`` in ``metadata.json`` =>
    readiness blocker; runner does not progress.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)
    # Mutate the well-formed bundle's ``checksum_sha256`` to a
    # value that does not match the staged xlsx bytes.
    bad_path = raw_root / "maddison_project" / MADDIson_TEST_METADATA_NAME
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = {MADDIson_TEST_FIXTURE_XLSX: "0" * 64}
    bad_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)

    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="checksum",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_missing_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing metadata ``source_version`` is a readiness blocker."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)
    metadata_path = (
        raw_root / "maddison_project" / MADDIson_TEST_METADATA_NAME
    )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("source_version")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="missing_metadata",
        expected_substring="source_version",
    )

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_mismatched_metadata_source_version_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Metadata ``source_version`` must match canonical Maddison ``2023``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.maddison_project import (
        MADDISON_PROJECT_DEFAULT_VERSION,
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)
    metadata_path = (
        raw_root / "maddison_project" / MADDIson_TEST_METADATA_NAME
    )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["source_version"] = "9999"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    real_adapter = create_maddison_project_adapter()
    spy = _SpyMaddisonProjectAdapter(real_adapter)
    registry = InMemorySourceRegistry()
    registry.register(spy)
    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
    )

    readiness = spy.check_ready(request)
    _assert_readiness_error_envelope(
        readiness,
        expected_code="unsupported_version",
        expected_substring="9999",
    )
    assert MADDISON_PROJECT_DEFAULT_VERSION in readiness.errors[0].message

    _assert_runner_does_not_progress(registry, request, spy)


def test_maddison_project_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata version labels raw assets and observations."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        MADDISON_PROJECT_DEFAULT_VERSION,
        create_maddison_project_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_maddison_project_bundle(raw_root)
    adapter = create_maddison_project_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="maddison_project"),
        raw_root=raw_root,
        years=(2022,),
        countries=("USA",),
    )

    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)
    assert raw.assets[0].version == MADDISON_PROJECT_DEFAULT_VERSION

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    result = SourceIngestRunner(registry).run(request)
    assert result.observations
    assert {
        observation.source_version for observation in result.observations
    } == {MADDISON_PROJECT_DEFAULT_VERSION}


# ---------------------------------------------------------------------------
# Import boundary: leaders_db.sources.adapters.maddison_project must not
# import legacy
# ---------------------------------------------------------------------------


def test_maddison_project_adapter_module_does_not_import_legacy_ingest_at_import() -> (
    None
):
    """``import leaders_db.sources.adapters.maddison_project`` MUST
    NOT import ``leaders_db.ingest`` at any depth (SRC-MIG-007 +
    docs/architecture/sources.md §10.1).

    The test inspects the new module's source AST and asserts
    that the only ``leaders_db.ingest.*`` import statements are
    scoped inside function bodies (lazy imports), NOT at module
    top level. Module-level eager imports of ``leaders_db.ingest``
    are forbidden because they would pull the legacy ingest
    package into ``sys.modules`` at package import time and
    break the documented boundary.
    """
    import ast

    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "leaders_db"
        / "sources"
        / "adapters"
        / "maddison_project"
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
        f"imports; the new Maddison Project adapter must import "
        f"legacy code lazily inside methods only (SRC-MIG-007). "
        f"Found: {legacy_top_level}"
    )
    # Sanity: at least one nested lazy import must exist (else
    # the adapter would not work; the legacy reader / transform
    # are reused).
    assert any(
        "from leaders_db.ingest.maddison_project" in entry
        for entry in legacy_nested
    ), (
        f"{module_path} must contain at least one nested lazy "
        f"import from leaders_db.ingest.maddison_project.*; got "
        f"{legacy_nested}"
    )


def test_maddison_project_package_import_does_not_register_legacy_maddison_project() -> (
    None
):
    """``import leaders_db.sources.adapters.maddison_project``
    MUST NOT touch ``STAGE2_ADAPTERS["maddison_project"]``.

    The legacy dispatch table is the legacy CLI's
    responsibility. Importing the new adapter module must leave
    the legacy registry untouched. This is the
    package-isolation guarantee for the legacy ``ingest`` seam.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import InMemorySourceRegistry
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
        register_maddison_project,
    )

    sentinel_before = object()
    original = legacy_ingest.STAGE2_ADAPTERS.get("maddison_project")
    legacy_ingest.STAGE2_ADAPTERS["maddison_project"] = sentinel_before
    try:
        adapter = create_maddison_project_adapter()
        new_registry = InMemorySourceRegistry()
        register_maddison_project(new_registry)

        assert legacy_ingest.STAGE2_ADAPTERS.get("maddison_project") is sentinel_before, (
            "the new Maddison Project adapter module must not "
            "mutate the legacy STAGE2_ADAPTERS table on import or "
            "factory call"
        )
        assert (
            new_registry.list_descriptors()[0].source_id.slug
            == "maddison_project"
        )
        assert (
            legacy_ingest.STAGE2_ADAPTERS["maddison_project"]
            is sentinel_before
        )
        assert adapter.descriptor.source_id.slug == "maddison_project"
    finally:
        legacy_ingest.STAGE2_ADAPTERS["maddison_project"] = original


__all__ = [
    "MADDIson_TEST_ATTRIBUTION_KEY",
    "MADDIson_TEST_COVERAGE_END",
    "MADDIson_TEST_COVERAGE_START",
    "MADDIson_TEST_DEFAULT_VERSION",
    "MADDIson_TEST_FAMILY",
    "MADDIson_TEST_FIXTURE_XLSX",
    "MADDIson_TEST_HOMEPAGE_URL",
    "MADDIson_TEST_METADATA_NAME",
    "MADDIson_TEST_PROXY_REQUESTED_YEAR",
    "MADDIson_TEST_PROXY_YEAR",
    "test_maddison_project_2023_request_proxies_to_2022_with_warning",
    "test_maddison_project_2024_request_returns_zero_and_warning",
    "test_maddison_project_adapter_is_registerable_through_in_memory_registry",
    "test_maddison_project_adapter_module_does_not_import_legacy_ingest_at_import",
    "test_maddison_project_adapter_satisfies_source_adapter_protocol",
    "test_maddison_project_attribution_text_matches_attributions_doc",
    "test_maddison_project_checksum_mismatch_fails_readiness_and_blocks_runner",
    "test_maddison_project_combined_year_and_country_filter",
    "test_maddison_project_country_filter_is_applied",
    "test_maddison_project_descriptor_exposes_documented_static_metadata",
    "test_maddison_project_leader_filter_emits_unsupported_filter_warning",
    "test_maddison_project_mismatched_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_maddison_project_missing_metadata_fails_readiness_and_blocks_runner",
    "test_maddison_project_missing_metadata_source_version_fails_readiness_and_blocks_runner",
    "test_maddison_project_missing_xlsx_fails_readiness_and_blocks_runner",
    "test_maddison_project_package_import_does_not_register_legacy_maddison_project",
    "test_maddison_project_register_helper_registers_against_explicit_registry",
    "test_maddison_project_runner_does_not_consult_legacy_stage2_adapters",
    "test_maddison_project_runner_produces_normalized_observations",
    "test_maddison_project_unsupported_source_version_fails_readiness_with_actionable_error",
    "test_maddison_project_year_filter_is_applied",
]
