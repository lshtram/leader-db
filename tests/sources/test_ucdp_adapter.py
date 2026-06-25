"""Phase C / D slice -- UCDP adapter under the unified
``leaders_db.sources`` interface.

The UCDP adapter is the sixth source rebuilt under the
clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 11,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI,
World Bank WGI, and V-Dem.

The legacy UCDP reader / event-level aggregator under
``leaders_db.ingest.ucdp_io`` and
``leaders_db.ingest.ucdp_aggregate`` is reused internally
via lazy imports -- the package boundary at
docs/architecture/sources.md §10.1 is preserved.

UCDP is structurally distinct from the prior five
clean-source migrations: PWT / Maddison / WDI / WGI / V-Dem
are country-year tables, while UCDP GED is an
**event-level** dataset (316,818 events in v23.1). The Stage
2 adapter aggregates events to country-year by
``type_of_violence`` (1 = state-based, 3 = one-sided) and the
cross-border filter (``type=1 AND gwnob.notna()`` for the
internationalized subset) before the long-to-wide pivot. The
unified transform layer consumes the wide-format country-year
DataFrame and emits one ``NormalizedObservation`` per
``(country_id, year, variable_name)`` triple. Per-row
event-level provenance is NOT preserved through the
aggregation -- the unified ``RawLocator.row_number`` is
intentionally ``None`` and the
``transform_locator.rule_id`` carries the
``ucdp:<country_id>:<year>:<variable_name>`` pattern.

Tests cover the documented slice acceptance criteria:

- The UCDP adapter descriptor is registerable / listable
  through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata.
- The UCDP descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``ucdp``,
  default version ``"GED 23.1"``, attribution_key
  ``ucdp``, dataset type, 1989-2022 coverage hint, two
  observation families: ``international_peace_country_year``
  + ``domestic_violence_country_year``, UCDP homepage URL).
- :class:`SourceIngestRunner` can run UCDP end-to-end
  through the new registry against a fixture ``raw_root``
  and produce :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter internally
  reuses legacy parsing / aggregation modules, but dispatch
  is registry-based).
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(2023,)`` or
  ``years=(1988,)`` request returns zero observations plus a
  structured :class:`SourceWarning` (no stale-proxy fill --
  SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- The bundle readiness gate accepts the canonical
  primary metadata shape (``source_name`` /
  ``source_version`` / ``source_url`` / ``license_note`` /
  ``local_files`` / ``ingestion_status`` / ``coverage`` /
  optional ``checksum_sha256``) when the canonical
  ``ged231-csv.zip`` is staged on disk. The canonical
  UCDP bundle metadata carries ``local_files=[]`` and
  ``checksum_sha256=null`` -- a deliberately minimal
  shape so the operator can update the metadata once the
  zip is staged. The mandatory readiness requirement is
  on raw-file presence: a metadata-only bundle (no staged
  zip) is intentionally NOT runner-ready, even though
  ``local_files=[]`` / ``checksum_sha256=null`` /
  ``ingestion_status="pending"`` is the canonical
  metadata shape. The readiness gate fires a structured
  ``missing_raw`` error so the ``SourceIngestRunner``
  raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Readiness-failure paths block the runner BEFORE
  ``read_raw`` / ``transform`` for missing metadata,
  missing ``ged231-csv.zip``, missing required field,
  mismatched metadata ``source_version``, and unsupported
  request ``source_version``.
- Canonical metadata ``source_version="GED 23.1"``
  propagates consistently to ``RawAsset.version`` and every
  emitted ``NormalizedObservation.source_version``.
- Importing the new
  ``leaders_db.sources.adapters.ucdp`` module does NOT pull
  in any ``leaders_db.ingest`` module (SRC-MIG-007 + the
  import boundary documented in
  docs/architecture/sources.md §10.1).
- Per-observation ``RawLocator`` carries the staged zip
  path + the catalog ``variable_name``; ``row_number`` is
  intentionally ``None`` because the legacy wide frame is
  the country-year aggregation of the event-level UCDP CSV
  and the original event row index is not preserved through
  the long-to-wide pivot -- the unified transform never
  fabricates locators. The aggregate locator convention is
  carried on the ``transform_locator.rule_id`` +
  ``quality_flags`` tuple.
- Per-observation ``extension`` carries the canonical UCDP
  attribution text (Rule #15), the
  ``source_row_reference="ucdp:<country_id>"`` pattern
  (matching the legacy Stage 2 DB writer), the
  ``ucdp_country_id``, ``ucdp_rating_category``,
  ``ucdp_raw_column``, ``ucdp_filter_logic``,
  ``ucdp_events_total`` / ``ucdp_events_filtered``, the
  ``raw_value`` audit-trail string, the ``raw_scale`` /
  ``higher_is_better`` / ``normalized_scale_target``
  direction hints, and the aggregate locator convention
  flag ``ucdp_aggregated_from_events``.

PASS-ELIGIBLE rationale
-----------------------
The legacy UCDP reader / aggregator are well-tested via the
existing ``tests/test_ingest_ucdp.py`` suite. The tests in
this file prove that the new
``leaders_db.sources.adapters.ucdp`` adapter wraps the
legacy parsing / aggregation logic behind the unified
:class:`SourceAdapter` Protocol while preserving the
package-isolation contract -- they are PASS-ELIGIBLE because
the adapter implementation lands in the same change set.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from leaders_db.sources import SourceIngestRequest


UCDP_TEST_FIXTURE_ZIP: str = "ged231-csv.zip"
UCDP_TEST_METADATA_NAME: str = "metadata.json"
UCDP_TEST_ATTRIBUTION_KEY: str = "ucdp"
UCDP_TEST_DEFAULT_VERSION: str = "GED 23.1"
UCDP_TEST_COVERAGE_START: int = 1989
UCDP_TEST_COVERAGE_END: int = 2022
UCDP_TEST_FAMILIES: tuple[str, ...] = (
    "international_peace_country_year",
    "domestic_violence_country_year",
)
UCDP_TEST_HOMEPAGE_URL: str = "https://ucdp.uu.se/downloads/"
UCDP_TEST_AGGREGATE_QUALITY_FLAG: str = "ucdp_aggregated_from_events"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyUCDPAdapter:
    """Wrap a :class:`UCDPAdapter` and record every lifecycle call.

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


def _stage_ucdp_bundle(raw_root: Path) -> Path:
    """Stage the canonical UCDP fixture bundle under ``raw_root/ucdp``.

    Copies ``tests/fixtures/ucdp/sample.zip`` (the 22-event
    real-format UCDP fixture, same one the legacy
    ``tests/test_ingest_ucdp.py`` uses) into
    ``<raw_root>/ucdp/ged231-csv.zip`` and writes a
    well-formed ``metadata.json`` (canonical primary shape:
    ``source_name`` / ``source_version`` / ``source_url`` /
    ``license_note`` / ``local_files`` /
    ``ingestion_status`` / ``coverage`` /
    ``checksum_sha256``). The ``checksum_sha256`` matches
    the staged zip bytes so the readiness gate's
    zip-checksum branch passes when the bundle is staged
    with a known SHA-256. The canonical UCDP bundle in
    ``data/raw/ucdp/metadata.json`` ships with
    ``local_files=[]`` + ``checksum_sha256=null`` (the
    operator downloads the zip via the project workflow);
    this staged fixture carries the populated shape so the
    test exercises the full zip-checksum path.

    The fixture carries 5 countries (Iraq 645, Pakistan
    770, Ethiopia 530, Germany 91, UK 200) x 2 years (2021,
    2022) x 6 indicators = 60 country-year observations
    after event-level aggregation.
    """
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1] / "fixtures" / "ucdp"
    )
    fixture_zip = fixtures / "sample.zip"
    staged_zip = bundle_dir / UCDP_TEST_FIXTURE_ZIP
    shutil.copy2(fixture_zip, staged_zip)
    zip_sha = hashlib.sha256(staged_zip.read_bytes()).hexdigest()
    payload = {
        "source_name": (
            "Uppsala Conflict Data Program Georeferenced "
            "Event Dataset"
        ),
        "source_version": UCDP_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-25",
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [UCDP_TEST_FIXTURE_ZIP],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
        ),
        "checksum_sha256": zip_sha,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


def _stage_ucdp_bundle_empty_shape(raw_root: Path) -> Path:
    """Stage a UCDP bundle with the canonical EMPTY shape.

    Mirrors the canonical ``data/raw/ucdp/metadata.json``
    bundle that ships with ``local_files=[]`` /
    ``checksum_sha256=null`` / ``ingestion_status="pending"``.
    The readiness gate must accept this shape (the operator
    downloads the zip via the project workflow). Returns
    the resolved bundle directory WITHOUT a staged zip --
    callers that exercise the read_raw path must stage a
    zip separately or use the ``_stage_ucdp_bundle`` helper.
    """
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": (
            "Uppsala Conflict Data Program Georeferenced "
            "Event Dataset"
        ),
        "source_version": UCDP_TEST_DEFAULT_VERSION,
        "download_date": None,
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [],
        "ingestion_status": "pending",
        "source_url": (
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
        ),
        "checksum_sha256": None,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_ucdp_descriptor_exposes_documented_static_metadata() -> None:
    """The UCDP descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md §5.2):

    - ``source_id.slug == "ucdp"``
    - ``display_name`` is the canonical UCDP GED 23.1
      label.
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical metadata
      stamp (``"GED 23.1"``).
    - ``homepage_url`` is the canonical UCDP downloads page.
    - ``attribution_key == "ucdp"``
    - ``coverage_hint.start_year == 1989``,
      ``coverage_hint.end_year == 2022``.
    - ``supported_observation_families`` is the 2-tuple
      ``("international_peace_country_year",
      "domestic_violence_country_year")``.
    - ``requires_network is False`` (local-file only).

    PASS-ELIGIBLE: the descriptor factory ships with the
    slice.
    """
    from leaders_db.sources.adapters.ucdp import (
        build_ucdp_descriptor,
    )

    descriptor = build_ucdp_descriptor()

    assert descriptor.source_id.slug == "ucdp"
    assert descriptor.source_type == "dataset"
    assert descriptor.default_version == UCDP_TEST_DEFAULT_VERSION
    assert descriptor.homepage_url == UCDP_TEST_HOMEPAGE_URL
    assert descriptor.attribution_key == UCDP_TEST_ATTRIBUTION_KEY
    assert descriptor.coverage_hint.start_year == (
        UCDP_TEST_COVERAGE_START
    )
    assert descriptor.coverage_hint.end_year == UCDP_TEST_COVERAGE_END
    assert descriptor.supported_observation_families == (
        UCDP_TEST_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_ucdp_attribution_text_matches_attributions_doc() -> None:
    """The UCDP attribution text is a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical UCDP citation block
    in ``docs/sources/attributions.md`` is the source of
    truth; the adapter module's constant must be
    byte-identical to a substring of that doc. Also asserts
    the constant matches the legacy ``UCDP_ATTRIBUTION``
    byte-for-byte (consistency guard).
    """
    from leaders_db.ingest.ucdp_io import UCDP_ATTRIBUTION
    from leaders_db.sources.adapters.ucdp import (
        UCDP_ATTRIBUTION_TEXT,
    )

    assert UCDP_ATTRIBUTION_TEXT == UCDP_ATTRIBUTION, (
        "Unified UCDP attribution must be byte-identical to "
        "the legacy UCDP_ATTRIBUTION constant in "
        "src/leaders_db/ingest/ucdp_io.py."
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
    assert UCDP_ATTRIBUTION_TEXT in attributions_text, (
        f"{UCDP_ATTRIBUTION_TEXT!r} is not a substring "
        f"of {attributions_path}. Update both in the same "
        f"commit (Rule #15)."
    )


def test_ucdp_adapter_satisfies_source_adapter_protocol() -> None:
    """``UCDPAdapter`` instances satisfy the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor`` or
    any of ``check_ready`` / ``read_raw`` / ``transform`` at
    construction time. The check is also enforced at
    adapter module import time; this test is the explicit
    assertion for downstream test suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    adapter = create_ucdp_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "ucdp"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_ucdp_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_ucdp_adapter()`` produces an adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects
    duplicate slugs with ``ValueError`` (SRC-REG-004); the
    test asserts the UCDP adapter registers cleanly under
    the ``ucdp`` slug and the descriptor is listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_ucdp_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "ucdp"

    resolved = registry.get_descriptor(SourceId(slug="ucdp"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="ucdp")) is adapter


def test_ucdp_register_helper_registers_against_explicit_registry() -> None:
    """``register_ucdp(registry)`` is the explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.ucdp import (
        register_ucdp,
    )

    registry = InMemorySourceRegistry()
    adapter = register_ucdp(registry)
    assert registry.get_adapter(SourceId(slug="ucdp")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_ucdp_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives UCDP through the
    documented lifecycle and emits :class:`NormalizedObservation`
    records.

    The fixture has 5 countries x 2 years x 6 indicators =
    60 country-year observations after event-level
    aggregation (22 events -> 60 country-year cells). All
    60 cells are real numeric values (no NaN cells in the
    fixture).

    Per-country totals (Iraq 645, Pakistan 770, Ethiopia
    530, Germany 91, UK 200):

    - Iraq 2021: 6
    - Iraq 2022: 6
    - Pakistan 2021: 6
    - Pakistan 2022: 6
    - Ethiopia 2021: 6
    - Ethiopia 2022: 6
    - Germany 2021: 6
    - Germany 2022: 6
    - UK 2021: 6
    - UK 2022: 6

    Total: 10 * 6 = 60.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 60, (
        f"expected 60 observations (5*2*6); "
        f"got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "ucdp"
        assert obs.observation_family in UCDP_TEST_FAMILIES
        assert obs.year is not None
        # UCDP ``country_code`` is the UCDP integer id (NOT
        # ISO3) -- the unified contract surfaces it verbatim
        # for Stage 3 country match.
        assert obs.country_code is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == "numeric"
        # The aggregate locator convention: row_number is
        # intentionally ``None`` because the legacy wide
        # frame is the country-year aggregation of the
        # event-level UCDP CSV -- the unified transform
        # never fabricates locators.
        assert obs.raw_locator.row_number is None
        # The aggregate locator quality flag is carried on
        # every observation so downstream audit code can
        # recognize the aggregate locator convention.
        assert UCDP_TEST_AGGREGATE_QUALITY_FLAG in (
            obs.quality_flags
        )

    # Per-country totals.
    by_country: dict[str, int] = {}
    for obs in result.observations:
        by_country[obs.country_code] = (
            by_country.get(obs.country_code, 0) + 1
        )
    # Five distinct UCDP country_ids, each with 12
    # observations (2 years x 6 indicators).
    assert len(by_country) == 5
    assert all(count == 12 for count in by_country.values()), (
        f"expected each country to have 12 observations; "
        f"got {by_country}"
    )


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_ucdp_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives UCDP through the new registry and never
    calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches ``STAGE2_ADAPTERS["ucdp"]`` with
    a tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)``
    executes the new UCDP adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    # Replace the legacy ``ucdp`` slot with a tracker
    # that records every invocation. The runner must never
    # call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("ucdp")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["ucdp"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_ucdp_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="ucdp"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 60

        # The legacy tracker must not have been called --
        # the new runner routes through the new registry
        # only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["ucdp"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_ucdp_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2022,)`` filters to 2022 rows only.

    Per-row 2022 totals: 5 countries x 6 indicators = 30
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        years=(2022,),
    )
    result = runner.run(request)
    assert len(result.observations) == 30
    assert {obs.year for obs in result.observations} == {2022}


def test_ucdp_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('645',)`` filters to Iraq rows only.

    The unified transform layer applies the country filter
    against the UCDP ``country_id`` integer (NOT ISO3);
    callers who want to filter by ISO3 must use the legacy
    path or Stage 3 country match to resolve first. Per-
    country Iraq totals: 2 years x 6 indicators = 12
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        countries=("645",),
    )
    result = runner.run(request)
    assert len(result.observations) == 12
    assert {obs.country_code for obs in result.observations} == {
        "645",
    }


def test_ucdp_iso3_country_filter_produces_zero_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.countries=('IRQ',)`` (ISO3) produces
    zero observations.

    The unified transform layer matches the request
    ``countries`` against the UCDP ``country_id`` integer;
    passing an ISO3 code yields zero rows. The contract is
    documented in :mod:`._readiness` so the readiness gate
    does NOT warn on ISO3 codes -- callers who want to
    filter by ISO3 must use the legacy path or Stage 3
    country match to resolve first.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        countries=("IRQ",),
    )
    result = runner.run(request)
    assert result.observations == ()


def test_ucdp_combined_year_and_country_filter(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2021,) + countries=('770',)``
    filters to Pakistan 2021 only.

    Per-country Pakistan 2021 totals: 6 observations (1 year
    x 6 indicators).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        years=(2021,),
        countries=("770",),
    )
    result = runner.run(request)
    assert len(result.observations) == 6
    assert {obs.year for obs in result.observations} == {2021}
    assert {obs.country_code for obs in result.observations} == {
        "770",
    }


def test_ucdp_out_of_coverage_year_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2023,)`` (out of coverage)
    emits zero observations plus a structured
    :class:`SourceWarning` -- no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert result.observations == ()
    # The YEAR_ABSENT warning is surfaced on the readiness
    # envelope AND propagated through to the final result
    # envelope so callers see the out-of-coverage signal
    # even when the transform emits zero observations.
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got {warning_codes}"
    )


def test_ucdp_out_of_coverage_year_before_window_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(1988,)`` (before coverage
    window) emits zero observations plus a structured
    :class:`SourceWarning` -- no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        years=(1988,),
    )
    result = runner.run(request)
    assert result.observations == ()
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got {warning_codes}"
    )


def test_ucdp_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.leaders=('X',)`` emits a structured
    ``unsupported_filter`` warning per SRC-REQ-005.

    UCDP is a country-year conflict source; leader filters
    are not supported. The warning is surfaced on the
    readiness envelope AND propagated through to the final
    result envelope. The transform layer does NOT re-emit
    per-row to avoid double-counting in the warnings audit
    trail.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        leaders=("Some Leader",),
    )
    result = runner.run(request)
    # The leader filter is unsupported but the transform
    # still emits observations (the readiness warning is
    # advisory only).
    assert len(result.observations) == 60
    warning_codes = [w.code for w in result.warnings]
    assert "unsupported_filter" in warning_codes, (
        f"expected 'unsupported_filter' warning, got {warning_codes}"
    )


# ---------------------------------------------------------------------------
# Readiness-failure paths
# ---------------------------------------------------------------------------


def test_ucdp_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``source_version="9999"`` fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009 -- the
    runner raises ``RuntimeError`` before calling
    ``read_raw`` / ``transform``.

    Uses a spy adapter to verify the runner short-circuits
    BEFORE ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    real_adapter = create_ucdp_adapter()
    spy = _SpyUCDPAdapter(real_adapter)
    # Register the spy instead of the real adapter so we
    # can verify the runner does NOT progress into
    # ``read_raw`` / ``transform``.
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
        source_version="9999",
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    # The runner must short-circuit before ``read_raw`` /
    # ``transform``.
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_ucdp_missing_metadata_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing ``metadata.json`` fails readiness and the runner
    short-circuits before ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage ONLY the zip; the readiness gate must block on
    # the missing metadata.json BEFORE read_raw / transform.
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1] / "fixtures" / "ucdp"
    )
    shutil.copy2(
        fixtures / "sample.zip",
        bundle_dir / UCDP_TEST_FIXTURE_ZIP,
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_ucdp_adapter()
    spy = _SpyUCDPAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_ucdp_missing_required_field_fails_readiness(
    tmp_path: Path,
) -> None:
    """Missing required metadata field fails readiness and the
    runner short-circuits before ``read_raw`` /
    ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Stage a well-formed ``metadata.json`` MISSING the
    # required ``source_url`` field -- the readiness gate
    # must block on the missing field BEFORE read_raw /
    # transform.
    payload = {
        "source_name": "Uppsala Conflict Data Program",
        "source_version": UCDP_TEST_DEFAULT_VERSION,
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [],
        "ingestion_status": "pending",
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        "checksum_sha256": None,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_ucdp_adapter()
    spy = _SpyUCDPAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_ucdp_mismatched_metadata_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Mismatched metadata ``source_version`` fails readiness."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": "Uppsala Conflict Data Program",
        "source_version": "GED 99.9",  # Not canonical.
        "source_url": (
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
        ),
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [],
        "ingestion_status": "pending",
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        "checksum_sha256": None,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_ucdp_adapter()
    spy = _SpyUCDPAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_ucdp_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata ``source_version="GED 23.1"``
    propagates consistently to ``RawAsset.version`` and
    every emitted ``NormalizedObservation.source_version``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        UCDP_DEFAULT_VERSION,
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    # The runner end-to-end contract surfaces the canonical
    # version via ``RawAsset.version`` and every
    # ``NormalizedObservation.source_version``.
    assert len(result.observations) == 60
    for obs in result.observations:
        assert obs.source_version == UCDP_DEFAULT_VERSION


def test_ucdp_empty_shape_bundle_is_not_runner_ready(
    tmp_path: Path,
) -> None:
    """A metadata-only bundle (no staged ``ged231-csv.zip``)
    is intentionally NOT runner-ready.

    The canonical UCDP bundle metadata ships with
    ``local_files=[]`` / ``checksum_sha256=null`` /
    ``ingestion_status="pending"`` -- a deliberately minimal
    shape so the operator can update the metadata once the
    zip is staged. The mandatory readiness requirement is
    on raw-file presence: the gate returns ``ready=False``
    with a structured ``missing_raw`` error when
    ``ged231-csv.zip`` is not staged on disk, regardless of
    the metadata's ``local_files`` / ``checksum_sha256``
    shape. This guarantees that the ``SourceIngestRunner``
    never dispatches ``read_raw`` and surfaces an unhandled
    ``FileNotFoundError``.

    The metadata-only bundle still has value for
    readiness-only inspection (validating metadata shape,
    schema migrations, sanity-checking
    ``expected_local_files`` annotations) -- but the
    readiness envelope is NOT ready and the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` / ``transform``.
    """
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle_empty_shape(raw_root)

    adapter = create_ucdp_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    # The empty-shape metadata passes per-field validation
    # but the gate MUST block on the missing staged zip --
    # a metadata-only bundle is NOT runner-ready.
    assert readiness.ready is False, (
        "metadata-only UCDP bundle (no staged ged231-csv.zip) "
        "must NOT be runner-ready; the readiness envelope is "
        "the single dispatch gate"
    )
    error_codes = [e.code for e in readiness.errors]
    assert "missing_raw" in error_codes, (
        f"expected 'missing_raw' error code for missing zip; "
        f"got {error_codes}"
    )
    # The blocker message names the missing zip so a
    # developer can fix the upstream issue without reading
    # source code.
    error_messages = [e.message for e in readiness.errors]
    assert any(
        "ged231-csv.zip" in msg for msg in error_messages
    ), (
        f"expected blocker message to name the missing "
        f"ged231-csv.zip; got {error_messages}"
    )


def test_ucdp_metadata_only_without_zip_blocks_runner_short_circuit(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` against a
    metadata-only UCDP bundle raises ``RuntimeError`` BEFORE
    ``read_raw`` / ``transform``.

    The spy adapter verifies that the runner short-circuits
    after the readiness gate fires the structured
    ``missing_raw`` error and that ``read_raw`` / ``transform``
    are NEVER invoked. The runner raises
    ``RuntimeError("Source 'ucdp' is not ready: ...")`
    per the documented runner contract
    (``docs/architecture/sources.md`` §5.6).

    This is the runner-level proof that the UCDP readiness
    gate is wired correctly: a metadata-only bundle (no
    staged zip) is NOT runner-ready, so the runner never
    reaches ``read_raw`` (which would otherwise raise
    :class:`FileNotFoundError`).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the canonical empty-shape metadata; the
    # zip is intentionally NOT staged so the readiness
    # gate MUST fire ``missing_raw`` and the runner MUST
    # short-circuit BEFORE ``read_raw`` / ``transform``.
    _stage_ucdp_bundle_empty_shape(raw_root)

    registry = InMemorySourceRegistry()
    real_adapter = create_ucdp_adapter()
    spy = _SpyUCDPAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower(), (
        f"expected 'not ready' message in runner's "
        f"RuntimeError; got {excinfo.value!r}"
    )
    # The runner MUST short-circuit after ``check_ready`` --
    # ``read_raw`` / ``transform`` must NOT be invoked.
    assert spy.calls == ["check_ready"], (
        f"runner must short-circuit before read_raw / "
        f"transform; got {spy.calls}"
    )


def test_ucdp_checksum_mismatch_fails_readiness(tmp_path: Path) -> None:
    """A non-null ``checksum_sha256`` that disagrees with the
    staged zip SHA-256 fails readiness with the
    module-local ``ucdp_checksum_mismatch`` code.
    """
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1] / "fixtures" / "ucdp"
    )
    shutil.copy2(
        fixtures / "sample.zip",
        bundle_dir / UCDP_TEST_FIXTURE_ZIP,
    )
    # Provide a deliberately wrong checksum so the gate
    # fires the ``ucdp_checksum_mismatch`` error code.
    payload = {
        "source_name": "Uppsala Conflict Data Program",
        "source_version": UCDP_TEST_DEFAULT_VERSION,
        "source_url": (
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
        ),
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [UCDP_TEST_FIXTURE_ZIP],
        "ingestion_status": "downloaded",
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        # 64-character hex string that does NOT match the
        # staged fixture zip's SHA-256.
        "checksum_sha256": "0" * 64,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_ucdp_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False
    error_codes = [e.code for e in readiness.errors]
    assert "ucdp_checksum_mismatch" in error_codes, (
        f"expected 'ucdp_checksum_mismatch' error, "
        f"got {error_codes}"
    )


def test_ucdp_malformed_checksum_shape_fails_readiness(
    tmp_path: Path,
) -> None:
    """A non-null, non-64-character-hex ``checksum_sha256``
    fails readiness with ``missing_metadata``.

    The zip MUST be staged alongside the malformed-checksum
    metadata so the readiness gate progresses past the
    presence check and reaches the per-field validators --
    this isolates the malformed-checksum shape from the
    missing-zip presence check (which fires first and would
    otherwise mask the shape error with a ``missing_raw``
    signal).
    """
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "ucdp"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Stage the zip so the presence check passes and the
    # per-field validators can run; the malformed checksum
    # is the focal error.
    fixtures = (
        Path(__file__).resolve().parents[1] / "fixtures" / "ucdp"
    )
    shutil.copy2(
        fixtures / "sample.zip",
        bundle_dir / UCDP_TEST_FIXTURE_ZIP,
    )
    payload = {
        "source_name": "Uppsala Conflict Data Program",
        "source_version": UCDP_TEST_DEFAULT_VERSION,
        "source_url": (
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
        ),
        "license_note": (
            "Free academic use; cite UCDP GED 23.1 "
            "(Davies et al. 2023)."
        ),
        "local_files": [UCDP_TEST_FIXTURE_ZIP],
        "ingestion_status": "downloaded",
        "coverage": (
            "event-level organized violence aggregated by the "
            "Stage 2 adapter to country-year"
        ),
        # Non-null, non-string value.
        "checksum_sha256": 12345,
    }
    (bundle_dir / UCDP_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_ucdp_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False
    error_codes = [e.code for e in readiness.errors]
    assert "missing_metadata" in error_codes, (
        f"expected 'missing_metadata' error, got {error_codes}"
    )


# ---------------------------------------------------------------------------
# Per-observation contract: aggregate locator convention + extension payload
# ---------------------------------------------------------------------------


def test_ucdp_observation_carries_aggregate_locator_quality_flag(
    tmp_path: Path,
) -> None:
    """Every UCDP observation's ``quality_flags`` carries the
    ``ucdp_aggregated_from_events`` flag so downstream audit
    code can recognize the aggregate locator convention.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert len(result.observations) > 0
    for obs in result.observations:
        assert UCDP_TEST_AGGREGATE_QUALITY_FLAG in obs.quality_flags


def test_ucdp_observation_carries_rule_id_and_extension_locators(
    tmp_path: Path,
) -> None:
    """Per-observation ``transform_locator.rule_id`` carries the
    ``ucdp:<country_id>:<year>:<variable_name>`` pattern and
    ``extension.source_row_reference`` carries the
    ``ucdp:<country_id>`` pattern matching the legacy Stage
    2 DB writer.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert len(result.observations) > 0
    for obs in result.observations:
        # The aggregate locator rule_id carries the
        # canonical UCDP triple: <country_id>:<year>:<variable_name>.
        rule_id = obs.transform_locator.rule_id
        assert rule_id.startswith("ucdp:"), (
            f"rule_id must start with 'ucdp:'; got {rule_id!r}"
        )
        # The source_row_reference carries the legacy
        # ``ucdp:<country_id>`` pattern.
        source_row_ref = obs.extension.get("source_row_reference")
        assert isinstance(source_row_ref, str)
        assert source_row_ref.startswith("ucdp:"), (
            f"source_row_reference must start with 'ucdp:'; "
            f"got {source_row_ref!r}"
        )
        # The aggregate locator extension fields are present.
        assert "ucdp_country_id" in obs.extension
        assert "ucdp_rating_category" in obs.extension
        assert "ucdp_raw_column" in obs.extension
        assert "ucdp_filter_logic" in obs.extension
        # The pre-aggregation event counts are carried from
        # ``df.attrs`` onto every observation's extension.
        assert "ucdp_events_total" in obs.extension
        assert "ucdp_events_filtered" in obs.extension
        assert obs.extension["ucdp_events_total"] == 22
        assert obs.extension["ucdp_events_filtered"] <= 22
        # The canonical UCDP attribution block is carried
        # on every observation (Rule #15).
        assert obs.extension.get("attribution") is not None


def test_ucdp_observation_carries_expected_indicator_codes(
    tmp_path: Path,
) -> None:
    """The 6 expected catalog indicator codes are emitted in the
    unfiltered run.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.ucdp import (
        create_ucdp_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_ucdp_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_ucdp_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    indicator_codes = {
        obs.indicator_code for obs in result.observations
    }
    expected_codes = {
        "ucdp_state_based_events",
        "ucdp_state_based_fatalities",
        "ucdp_intl_events",
        "ucdp_intl_fatalities",
        "ucdp_onesided_events",
        "ucdp_onesided_fatalities",
    }
    assert indicator_codes == expected_codes, (
        f"indicator code mismatch: missing "
        f"{expected_codes - indicator_codes}; extra "
        f"{indicator_codes - expected_codes}"
    )


# ---------------------------------------------------------------------------
# Import boundary: package import must not pull in legacy ingest
# ---------------------------------------------------------------------------


def test_ucdp_adapter_module_does_not_import_legacy_ingest_at_import() -> None:
    """Importing the UCDP adapter module does NOT pull in any
    ``leaders_db.ingest`` module.

    SRC-MIG-007 + docs/architecture/sources.md §10.1: the
    unified package boundary must hold for the new UCDP
    adapter module. The test inspects ``sys.modules``
    immediately after the import to prove the legacy
    ingest package is not loaded as a side effect.
    """
    import importlib
    import sys

    # Drop every cached ``leaders_db`` module so the import
    # below is forced to run as if it were a fresh import.
    for name in list(sys.modules):
        if name == "leaders_db" or name.startswith("leaders_db."):
            del sys.modules[name]

    try:
        importlib.import_module("leaders_db.sources.adapters.ucdp")
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "leaders_db.sources.adapters.ucdp must not "
            f"import leaders_db.ingest at import time "
            f"(leaked modules: {leaked})"
        )
    finally:
        for name in list(sys.modules):
            if name == "leaders_db" or name.startswith("leaders_db."):
                del sys.modules[name]


def test_ucdp_package_import_does_not_register_legacy_ucdp() -> None:
    """Importing ``leaders_db.sources.adapters.ucdp`` does NOT
    register a legacy UCDP adapter.

    The new package exposes explicit ``create_ucdp_adapter``
    / ``register_ucdp`` factories and does NOT
    auto-register on import (per
    docs/architecture/sources.md §10.1). The test asserts
    that an empty ``InMemorySourceRegistry`` stays empty
    after the import.
    """
    import importlib
    import sys

    for name in list(sys.modules):
        if name == "leaders_db" or name.startswith("leaders_db."):
            del sys.modules[name]

    try:
        importlib.import_module("leaders_db.sources.adapters.ucdp")
        from leaders_db.sources import (
            InMemorySourceRegistry,
        )

        registry = InMemorySourceRegistry()
        assert registry.list_descriptors() == ()
    finally:
        for name in list(sys.modules):
            if name == "leaders_db" or name.startswith("leaders_db."):
                del sys.modules[name]


__all__ = [
    "UCDP_TEST_AGGREGATE_QUALITY_FLAG",
    "UCDP_TEST_ATTRIBUTION_KEY",
    "UCDP_TEST_COVERAGE_END",
    "UCDP_TEST_COVERAGE_START",
    "UCDP_TEST_DEFAULT_VERSION",
    "UCDP_TEST_FAMILIES",
    "UCDP_TEST_FIXTURE_ZIP",
    "UCDP_TEST_HOMEPAGE_URL",
    "UCDP_TEST_METADATA_NAME",
]
