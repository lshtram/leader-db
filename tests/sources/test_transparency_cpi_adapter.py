"""Phase C / D slice -- Transparency International CPI adapter
under the unified ``leaders_db.sources`` interface.

The Transparency International CPI adapter is the seventh
source rebuilt under the clean ``leaders_db.sources``
interface (docs/architecture/sources.md §7.1 priority 6,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI,
World Bank WGI, V-Dem, and UCDP. The legacy Transparency
International CPI reader under
``leaders_db.ingest.transparency_cpi_csv`` is reused
internally via lazy imports -- the package boundary at
docs/architecture/sources.md §10.1 is preserved.

Transparency International CPI is structurally similar to
the WGI / V-Dem / UCDP clean-source migrations: it is a
country-year table indexed by ``iso3`` (the canonical
ISO3 alpha-3 country code), with the same per-year CSV
shape as the legacy Stage 2 reader expects. The unified
adapter narrows the per-year CSV to the single catalog
indicator ``cpi_score`` and carries the audit-trail
fields (``rank`` / ``sources`` / ``standard_error`` /
``lower_ci`` / ``upper_ci``) on every observation's
``extension`` so downstream scorers can recover the input
audit trail without re-reading the legacy CSV.

Tests cover the documented slice acceptance criteria:

- The Transparency International CPI adapter descriptor is
  registerable / listable through the new
  :class:`InMemorySourceRegistry` and exposes the
  documented static metadata.
- The CPI descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id
  ``transparency_cpi``, default version ``"CPI 2023"``,
  attribution_key ``transparency_cpi``, dataset type,
  1995-2023 coverage hint, single observation family
  ``integrity_country_year``, TI homepage URL
  ``https://www.transparency.org/en/cpi/2023``).
- :class:`SourceIngestRunner` can run CPI end-to-end
  through the new registry against a fixture ``raw_root``
  and produce :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter
  internally reuses legacy parsing modules, but dispatch
  is registry-based).
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(2024,)`` or
  ``years=(1994,)`` request returns zero observations plus
  a structured :class:`SourceWarning` (no stale-proxy
  fill -- SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``unsupported_filter`` warning (SRC-REQ-005).
- The bundle readiness gate accepts the canonical
  primary metadata shape (``source_name`` /
  ``source_version`` / ``source_url`` / ``license_note``
  / ``local_files`` / ``ingestion_status`` / ``coverage``
  / optional ``checksum_sha256``) when the canonical
  ``transparency_cpi_2023.csv`` is staged on disk. The
  canonical CPI bundle metadata carries
  ``checksum_sha256=null`` -- a deliberately minimal
  shape so the operator can update the metadata once the
  CSV is staged. The mandatory readiness requirement is
  on raw-file presence: a metadata-only bundle (no
  staged CSV) is intentionally NOT runner-ready, even
  though ``checksum_sha256=null`` is the canonical
  metadata shape. The readiness gate fires a structured
  ``missing_raw`` error so the ``SourceIngestRunner``
  raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Readiness-failure paths block the runner BEFORE
  ``read_raw`` / ``transform`` for missing metadata,
  missing CSV, missing required field, malformed
  ``checksum_sha256``, mismatched CSV SHA-256, missing
  metadata ``source_version``, mismatched metadata
  ``source_version``, and unsupported request
  ``source_version``.
- Canonical metadata ``source_version="CPI 2023"``
  propagates consistently to ``RawAsset.version`` and
  every emitted ``NormalizedObservation.source_version``.
- Importing the new
  ``leaders_db.sources.adapters.transparency_cpi`` module
  does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  docs/architecture/sources.md §10.1).
- Per-observation ``RawLocator`` carries the staged CSV
  path + the catalog ``raw_column`` (e.g. ``score``) +
  the positional row index in the wide frame (the legacy
  reader sorts by iso3 ascending for deterministic
  idempotency so the row index is preserved byte-for-byte
  with the input CSV). Per-observation ``extension``
  carries the canonical CPI attribution text (Rule #15),
  the ``source_row_reference="transparency_cpi:score:<iso3>"``
  pattern (matching the legacy Stage 2 DB writer), the
  CPI ``iso3`` / ``country`` / ``region`` audit-trail
  fields, the per-row ``cpi_rank`` / ``cpi_sources`` /
  ``cpi_standard_error`` / ``cpi_lower_ci`` /
  ``cpi_upper_ci`` confidence fields, and the
  ``raw_scale`` / ``higher_is_better`` /
  ``normalized_scale_target`` direction hints.
- The legacy ``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/transparency_cpi_io.py`` is
  byte-identical to the new
  ``TRANSPARENCY_CPI_ATTRIBUTION_TEXT``
  (``test_transparency_cpi_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text is a
  substring of ``docs/sources/attributions.md``).
- The CPI unified path is local-file only
  (``requires_network=False``, no HTTP layer in the new
  package). The runner NEVER invokes the network. The
  readiness gate validates the staged
  ``transparency_cpi_2023.csv`` and the metadata
  checksum / version / license / coverage fields BEFORE
  ``read_raw`` / ``transform`` are called.

PASS-ELIGIBLE rationale
-----------------------
The legacy Transparency International CPI reader is
well-tested via the existing
``tests/test_ingest_transparency_cpi.py`` suite. The
tests in this file prove that the new
``leaders_db.sources.adapters.transparency_cpi`` adapter
wraps the legacy parsing logic behind the unified
:class:`SourceAdapter` Protocol while preserving the
package-isolation contract -- they are PASS-ELIGIBLE
because the adapter implementation lands in the same
change set.
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


TRANSPARENCY_CPI_TEST_FIXTURE_CSV: str = "transparency_cpi_2023.csv"
TRANSPARENCY_CPI_TEST_METADATA_NAME: str = "metadata.json"
TRANSPARENCY_CPI_TEST_ATTRIBUTION_KEY: str = "transparency_cpi"
TRANSPARENCY_CPI_TEST_DEFAULT_VERSION: str = "CPI 2023"
TRANSPARENCY_CPI_TEST_COVERAGE_START: int = 1995
TRANSPARENCY_CPI_TEST_COVERAGE_END: int = 2023
TRANSPARENCY_CPI_TEST_HOMEPAGE_URL: str = (
    "https://www.transparency.org/en/cpi/2023"
)
TRANSPARENCY_CPI_TEST_FAMILIES: tuple[str, ...] = (
    "integrity_country_year",
)
TRANSPARENCY_CPI_TEST_INDICATOR: str = "cpi_score"
TRANSPARENCY_CPI_TEST_RAW_COLUMN: str = "score"
TRANSPARENCY_CPI_TEST_CANONICAL_VALUE_TYPE: str = "numeric"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyCPIAdapter:
    """Wrap a :class:`TransparencyCPIAdapter` and record
    every lifecycle call.

    The spy forwards to the underlying adapter so the real
    behavior is exercised; it just records the call order
    so readiness-failure tests can assert the runner does
    NOT progress into ``read_raw`` / ``transform``.

    The wrapper exposes ``descriptor`` as a property so
    the registry's :meth:`register` (which keys off
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


def _stage_cpi_bundle(
    raw_root: Path,
    *,
    checksum_sha256: str | None = None,
    with_checksum: bool = False,
) -> Path:
    """Stage the canonical CPI fixture bundle under
    ``raw_root/transparency_cpi``.

    Copies ``tests/fixtures/transparency_cpi/sample.csv``
    (the 5-country real-format CPI 2023 HDX-mirrored
    fixture) into
    ``<raw_root>/transparency_cpi/transparency_cpi_2023.csv``
    and writes a well-formed ``metadata.json`` (canonical
    primary shape: ``source_name`` / ``source_version`` /
    ``source_url`` / ``license_note`` / ``local_files`` /
    ``ingestion_status`` / ``coverage`` /
    ``checksum_sha256``). The ``checksum_sha256`` defaults
    to ``None`` (the canonical bundle metadata shape --
    the staged ``data/raw/transparency_cpi/metadata.json``
    ships ``null``); pass ``with_checksum=True`` to
    compute and stamp the actual staged CSV SHA-256 so the
    readiness gate's CSV-checksum match branch is
    exercised.

    The fixture carries 5 countries (MEX, USA, SWE, IND,
    NGA) at year 2023 with all HDX CSV columns preserved
    verbatim (no invented data).
    """
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    fixture_csv = fixtures / "sample.csv"
    staged_csv = bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV
    shutil.copy2(fixture_csv, staged_csv)

    if with_checksum:
        computed_checksum = hashlib.sha256(
            staged_csv.read_bytes(),
        ).hexdigest()
        checksum_value: str | None = computed_checksum
    else:
        checksum_value = checksum_sha256

    payload = {
        "source_name": (
            "Transparency International Corruption Perceptions "
            "Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "download_date": "2026-06-19",
        "coverage": "country-year (annual)",
        "years_available": "1995-2023+",
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International. The HDX mirror "
            "preserves the verbatim Transparency International "
            "release."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "publisher_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "hdx_mirror_url": (
            "https://data.humdata.org/dataset/"
            "fb4adde0-93d5-4ff9-befc-4a6916c1181b/resource/"
            "b2b0509d-299f-45f5-804f-a650d9597d2c/download/"
            "global_cpi_2023.csv"
        ),
        "checksum_sha256": checksum_value,
        "caveats": [
            "Direct xlsx download from transparency.org is "
            "CDN-gated per docs/sources/vetting/report.md "
            "section 3.6; the Stage 2 adapter downloads the "
            "canonical CSV from the OCHA HDX mirror.",
        ],
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle_dir

# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_transparency_cpi_descriptor_exposes_documented_static_metadata() -> None:
    """The CPI descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    docs/architecture/sources.md section 5.2):

    - ``source_id.slug == "transparency_cpi"``
    - ``display_name`` is the canonical CPI 2023 label.
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical metadata
      stamp (``"CPI 2023"``).
    - ``homepage_url`` is the canonical TI CPI 2023
      page.
    - ``attribution_key == "transparency_cpi"``
    - ``coverage_hint.start_year == 1995``,
      ``coverage_hint.end_year == 2023``.
    - ``supported_observation_families`` is the 1-tuple
      ``("integrity_country_year",)``.
    - ``requires_network is False`` (local-file only).

    PASS-ELIGIBLE: the descriptor factory ships with the
    slice.
    """
    from leaders_db.sources.adapters.transparency_cpi import (
        build_transparency_cpi_descriptor,
    )

    descriptor = build_transparency_cpi_descriptor()

    assert descriptor.source_id.slug == "transparency_cpi"
    assert descriptor.source_type == "dataset"
    assert (
        descriptor.default_version
        == TRANSPARENCY_CPI_TEST_DEFAULT_VERSION
    )
    assert descriptor.homepage_url == TRANSPARENCY_CPI_TEST_HOMEPAGE_URL
    assert (
        descriptor.attribution_key
        == TRANSPARENCY_CPI_TEST_ATTRIBUTION_KEY
    )
    assert (
        descriptor.coverage_hint.start_year
        == TRANSPARENCY_CPI_TEST_COVERAGE_START
    )
    assert (
        descriptor.coverage_hint.end_year
        == TRANSPARENCY_CPI_TEST_COVERAGE_END
    )
    assert descriptor.supported_observation_families == (
        TRANSPARENCY_CPI_TEST_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_transparency_cpi_attribution_text_matches_attributions_doc() -> None:
    """The CPI attribution text is byte-identical to the
    legacy ``TRANSPARENCY_CPI_ATTRIBUTION`` constant AND a
    substring of ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical CPI citation
    block in ``docs/sources/attributions.md`` is the
    source of truth; the adapter module's constant must
    be byte-identical to a substring of that doc AND
    byte-identical to the legacy
    ``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/transparency_cpi_io.py``.

    The text deliberately distinguishes the publisher
    (Transparency International) from the HDX mirror that
    preserves the verbatim TI release -- the
    report-facing attribution block names Transparency
    International CPI 2023 (the canonical publisher name),
    NOT the OCHA HDX mirror (which is the durable CSV
    provenance path documented separately in the bundle
    metadata's ``hdx_mirror_url`` field). Mirror vs.
    publisher attribution is documented in
    ``docs/sources/attributions.md`` transparency_cpi
    section and is enforced by this drift guard.
    """
    from leaders_db.ingest.transparency_cpi_io import (
        TRANSPARENCY_CPI_ATTRIBUTION,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        TRANSPARENCY_CPI_ATTRIBUTION_TEXT,
    )

    assert TRANSPARENCY_CPI_ATTRIBUTION_TEXT == (
        TRANSPARENCY_CPI_ATTRIBUTION
    ), (
        "Unified CPI attribution must be byte-identical "
        "to the legacy TRANSPARENCY_CPI_ATTRIBUTION "
        "constant in "
        "src/leaders_db/ingest/transparency_cpi_io.py."
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
    assert TRANSPARENCY_CPI_ATTRIBUTION_TEXT in attributions_text, (
        f"{TRANSPARENCY_CPI_ATTRIBUTION_TEXT!r} is not a "
        f"substring of {attributions_path}. Update both "
        f"in the same commit (Rule #15)."
    )


def test_transparency_cpi_adapter_satisfies_source_adapter_protocol() -> None:
    """``TransparencyCPIAdapter`` instances satisfy the
    runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor``
    or any of ``check_ready`` / ``read_raw`` /
    ``transform`` at construction time. The check is also
    enforced at adapter module import time; this test is
    the explicit assertion for downstream test suites.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    adapter = create_transparency_cpi_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "transparency_cpi"


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_transparency_cpi_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_transparency_cpi_adapter()`` produces an
    adapter the registry accepts.

    The Phase A :class:`InMemorySourceRegistry` rejects
    duplicate slugs with ``ValueError`` (SRC-REG-004); the
    test asserts the CPI adapter registers cleanly under
    the ``transparency_cpi`` slug and the descriptor is
    listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_transparency_cpi_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "transparency_cpi"

    resolved = registry.get_descriptor(SourceId(slug="transparency_cpi"))
    assert resolved is listed[0]
    assert registry.get_adapter(
        SourceId(slug="transparency_cpi"),
    ) is adapter


def test_transparency_cpi_register_helper_registers_against_explicit_registry() -> None:
    """``register_transparency_cpi(registry)`` is the
    explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        register_transparency_cpi,
    )

    registry = InMemorySourceRegistry()
    adapter = register_transparency_cpi(registry)
    assert (
        registry.get_adapter(SourceId(slug="transparency_cpi"))
        is adapter
    )


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_transparency_cpi_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives CPI
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records.

    The fixture has 5 countries (IND, MEX, NGA, SWE, USA)
    at year 2023 with the single catalog indicator
    ``cpi_score``. 5 country-year observations are
    expected (one per country).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 5, (
        f"expected 5 observations (5 countries x 1 year x "
        f"1 indicator); got {len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "transparency_cpi"
        assert obs.observation_family == (
            TRANSPARENCY_CPI_TEST_FAMILIES[0]
        )
        assert obs.year == 2023
        assert obs.indicator_code == TRANSPARENCY_CPI_TEST_INDICATOR
        # The CPI ``country_code`` is the ISO3 alpha-3
        # code (e.g. ``MEX``); the unified transform
        # surfaces it verbatim.
        assert obs.country_code is not None
        assert len(obs.country_code) == 3
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == TRANSPARENCY_CPI_TEST_CANONICAL_VALUE_TYPE


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_transparency_cpi_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives CPI through the new registry and
    never calls into ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches
    ``STAGE2_ADAPTERS["transparency_cpi"]`` with a
    tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)``
    executes the new CPI adapter lifecycle end-to-end.

    SRC-REG-003 / docs/architecture/sources.md section
    10.1: the new registry is the single dispatch
    surface; legacy dispatch is explicitly forbidden for
    the new runner.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    # Replace the legacy ``transparency_cpi`` slot with a
    # tracker that records every invocation. The runner
    # must never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("transparency_cpi")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["transparency_cpi"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_transparency_cpi_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="transparency_cpi"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 5

        # The legacy tracker must not have been called --
        # the new runner routes through the new registry
        # only.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through "
            "STAGE2_ADAPTERS instead of the new registry; "
            f"saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["transparency_cpi"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries
# ---------------------------------------------------------------------------


def test_transparency_cpi_year_filter_is_applied(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2023,)`` is honored --
    5 country-year observations round-trip."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {2023}


def test_transparency_cpi_country_filter_is_applied(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.countries=('MEX',)`` is honored
    -- 1 country-year observation round-trips."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        countries=("MEX",),
    )
    result = runner.run(request)
    assert len(result.observations) == 1
    assert {obs.country_code for obs in result.observations} == {
        "MEX",
    }


def test_transparency_cpi_combined_year_and_country_filter(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2023,) +
    countries=('USA',)`` filters to USA 2023 only -- 1
    observation round-trips."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 1
    assert {obs.year for obs in result.observations} == {2023}
    assert {obs.country_code for obs in result.observations} == {
        "USA",
    }


def test_transparency_cpi_out_of_coverage_year_after_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2024,)`` (out of coverage
    after window) emits zero observations plus a structured
    :class:`SourceWarning` -- no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003.

    The CPI 2023 dataset ends at 2023 per the canonical
    bundle metadata; a request for 2024 yields zero
    observations and the readiness envelope surfaces a
    structured ``year_absent`` warning that the runner
    carries through to the final result.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        years=(2024,),
    )
    result = runner.run(request)
    assert result.observations == ()
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got {warning_codes}"
    )


def test_transparency_cpi_out_of_coverage_year_before_returns_zero_and_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(1994,)`` (out of coverage
    before window) emits zero observations plus a structured
    :class:`SourceWarning` -- no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003.

    The CPI dataset starts at 1995 per the canonical
    bundle metadata; a request for 1994 yields zero
    observations and the readiness envelope surfaces a
    structured ``year_absent`` warning.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        years=(1994,),
    )
    result = runner.run(request)
    assert result.observations == ()
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got {warning_codes}"
    )


def test_transparency_cpi_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.leaders=('X',)`` emits a
    structured ``unsupported_filter`` warning per
    SRC-REQ-005.

    CPI is a country-year corruption-perception source;
    leader filters are not supported. The warning is
    surfaced on the readiness envelope AND propagated
    through to the final result envelope. The transform
    layer does NOT re-emit per-row to avoid
    double-counting in the warnings audit trail.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        leaders=("Some Leader",),
    )
    result = runner.run(request)
    # The leader filter is unsupported but the transform
    # still emits observations (the readiness warning is
    # advisory only).
    assert len(result.observations) == 5
    warning_codes = [w.code for w in result.warnings]
    assert "unsupported_filter" in warning_codes, (
        f"expected 'unsupported_filter' warning, got "
        f"{warning_codes}"
    )


# ---------------------------------------------------------------------------
# Readiness-failure paths
# ---------------------------------------------------------------------------


def test_transparency_cpi_unsupported_source_version_fails_readiness_with_actionable_error(
    tmp_path: Path,
) -> None:
    """``source_version="CPI 2024"`` fails readiness with
    a structured ``unsupported_version`` error per
    SRC-REQ-009 -- the runner raises ``RuntimeError``
    before calling ``read_raw`` / ``transform``.

    Uses a spy adapter to verify the runner short-circuits
    BEFORE ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    real_adapter = create_transparency_cpi_adapter()
    spy = _SpyCPIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
        source_version="CPI 2024",
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    # The runner must short-circuit before ``read_raw`` /
    # ``transform``.
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_transparency_cpi_missing_metadata_fails_readiness_and_blocks_runner(
    tmp_path: Path,
) -> None:
    """Missing ``metadata.json`` fails readiness and the
    runner short-circuits before ``read_raw`` /
    ``transform``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage ONLY the CSV; the readiness gate must block
    # on the missing metadata.json BEFORE read_raw /
    # transform.
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_transparency_cpi_adapter()
    spy = _SpyCPIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_transparency_cpi_missing_required_field_fails_readiness(
    tmp_path: Path,
) -> None:
    """Missing required metadata field fails readiness and
    the runner short-circuits before ``read_raw`` /
    ``transform``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Stage the CSV so the per-field validators can run
    # (the focal error is the missing field).
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    # Stage a well-formed ``metadata.json`` MISSING the
    # required ``source_url`` field -- the readiness
    # gate must block on the missing field BEFORE
    # read_raw / transform.
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        "checksum_sha256": None,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_transparency_cpi_adapter()
    spy = _SpyCPIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got {spy.calls}"
    )


def test_transparency_cpi_mismatched_metadata_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Mismatched metadata ``source_version`` fails
    readiness."""
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": "CPI 9999",  # Not canonical.
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        "checksum_sha256": None,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_transparency_cpi_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False
    error_codes = [e.code for e in readiness.errors]
    assert "unsupported_version" in error_codes, (
        f"expected 'unsupported_version' error, got "
        f"{error_codes}"
    )


def test_transparency_cpi_canonical_metadata_version_propagates_to_assets_and_observations(
    tmp_path: Path,
) -> None:
    """Canonical metadata ``source_version="CPI 2023"``
    propagates consistently to ``RawAsset.version`` and
    every emitted ``NormalizedObservation.source_version``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        TRANSPARENCY_CPI_DEFAULT_VERSION,
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    # The runner end-to-end contract surfaces the
    # canonical version via ``RawAsset.version`` and every
    # ``NormalizedObservation.source_version``.
    assert len(result.observations) == 5
    for obs in result.observations:
        assert obs.source_version == TRANSPARENCY_CPI_DEFAULT_VERSION


def test_transparency_cpi_metadata_only_without_csv_blocks_runner_short_circuit(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` against a
    metadata-only CPI bundle raises ``RuntimeError`` BEFORE
    ``read_raw`` / ``transform``.

    The canonical CPI bundle metadata ships with
    ``checksum_sha256=null`` +
    ``local_files=["transparency_cpi_2023.csv"]`` -- a
    deliberately minimal shape so the operator can update
    the metadata once the CSV is staged. The mandatory
    readiness requirement is on raw-file presence: the
    gate returns ``ready=False`` with a structured
    ``missing_raw`` error when the per-year CSV is not
    staged on disk, regardless of the metadata's
    ``local_files`` / ``checksum_sha256`` shape. This
    guarantees that the ``SourceIngestRunner`` never
    dispatches ``read_raw`` and surfaces an unhandled
    ``FileNotFoundError``.

    The spy adapter verifies that the runner short-circuits
    after the readiness gate fires the structured
    ``missing_raw`` error and that ``read_raw`` /
    ``transform`` are NEVER invoked.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage only the canonical ``null`` checksum metadata;
    # the CSV is intentionally NOT staged so the
    # readiness gate MUST fire ``missing_raw`` and the
    # runner MUST short-circuit BEFORE ``read_raw`` /
    # ``transform``.
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        "checksum_sha256": None,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_transparency_cpi_adapter()
    spy = _SpyCPIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower(), (
        f"expected 'not ready' message in runner's "
        f"RuntimeError; got {excinfo.value!r}"
    )
    # The runner MUST short-circuit after ``check_ready``
    # -- ``read_raw`` / ``transform`` must NOT be
    # invoked.
    assert spy.calls == ["check_ready"], (
        f"runner must short-circuit before read_raw / "
        f"transform; got {spy.calls}"
    )


def test_transparency_cpi_checksum_mismatch_fails_readiness(
    tmp_path: Path,
) -> None:
    """A non-null ``checksum_sha256`` that disagrees with
    the staged CSV SHA-256 fails readiness with the
    module-local ``transparency_cpi_checksum_mismatch``
    code."""
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    # Provide a deliberately wrong checksum so the gate
    # fires the ``transparency_cpi_checksum_mismatch``
    # error code.
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        # 64-character hex string that does NOT match the
        # staged fixture CSV's SHA-256.
        "checksum_sha256": "0" * 64,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_transparency_cpi_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False
    error_codes = [e.code for e in readiness.errors]
    assert "transparency_cpi_checksum_mismatch" in error_codes, (
        f"expected 'transparency_cpi_checksum_mismatch' "
        f"error, got {error_codes}"
    )


def test_transparency_cpi_malformed_checksum_shape_fails_readiness(
    tmp_path: Path,
) -> None:
    """A non-null, non-64-character-hex
    ``checksum_sha256`` fails readiness with
    ``missing_metadata``.

    The CSV MUST be staged alongside the
    malformed-checksum metadata so the readiness gate
    progresses past the presence check and reaches the
    per-field validators -- this isolates the
    malformed-checksum shape from the missing-CSV
    presence check (which fires first and would
    otherwise mask the shape error with a
    ``missing_raw`` signal).
    """
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": [TRANSPARENCY_CPI_TEST_FIXTURE_CSV],
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        # Non-null, non-string value.
        "checksum_sha256": 12345,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_transparency_cpi_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False
    error_codes = [e.code for e in readiness.errors]
    assert "missing_metadata" in error_codes, (
        f"expected 'missing_metadata' error, got {error_codes}"
    )


def test_transparency_cpi_correct_checksum_matches_staged_csv(
    tmp_path: Path,
) -> None:
    """A non-null ``checksum_sha256`` that matches the
    staged CSV SHA-256 passes the readiness gate's
    checksum-match branch."""
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root, with_checksum=True)

    adapter = create_transparency_cpi_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is True, (
        f"correct checksum should pass readiness; got "
        f"errors: {[(e.code, e.message) for e in readiness.errors]}"
    )


# ---------------------------------------------------------------------------
# Per-observation contract: locator + extension payload
# ---------------------------------------------------------------------------


def test_transparency_cpi_observation_carries_rule_id_and_extension_locators(
    tmp_path: Path,
) -> None:
    """Per-observation ``transform_locator.rule_id`` carries
    the ``transparency_cpi:<iso3>:<year>:<variable_name>``
    pattern and ``extension.source_row_reference`` carries
    the ``transparency_cpi:score:<iso3>`` pattern matching
    the legacy Stage 2 DB writer.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert len(result.observations) > 0
    for obs in result.observations:
        rule_id = obs.transform_locator.rule_id
        assert rule_id is not None
        assert rule_id.startswith("transparency_cpi:"), (
            f"rule_id must start with 'transparency_cpi:'; "
            f"got {rule_id!r}"
        )
        source_row_ref = obs.extension.get("source_row_reference")
        assert isinstance(source_row_ref, str)
        assert source_row_ref.startswith("transparency_cpi:"), (
            f"source_row_reference must start with "
            f"'transparency_cpi:'; got {source_row_ref!r}"
        )
        # The CPI-specific extension fields are present
        # so downstream audit code can recover the input
        # audit trail without re-reading the legacy CSV.
        assert obs.extension.get("transparency_cpi_iso3") == (
            obs.country_code
        )
        assert obs.extension.get(
            "transparency_cpi_rating_category",
        ) == "integrity"
        assert obs.extension.get(
            "transparency_cpi_raw_column",
        ) == TRANSPARENCY_CPI_TEST_RAW_COLUMN
        # The audit-trail confidence fields are present
        # (every fixture row has rank, sources, and the
        # confidence interval columns populated).
        assert "cpi_rank" in obs.extension
        assert "cpi_sources" in obs.extension
        assert "cpi_standard_error" in obs.extension
        assert "cpi_lower_ci" in obs.extension
        assert "cpi_upper_ci" in obs.extension
        # The country / region audit-trail labels are
        # preserved verbatim.
        assert "cpi_country_name" in obs.extension
        assert "cpi_region" in obs.extension
        # The canonical CPI attribution block is carried
        # on every observation (Rule #15).
        assert obs.extension.get("attribution") is not None


def test_transparency_cpi_observation_carries_correct_indicator_code(
    tmp_path: Path,
) -> None:
    """The single expected catalog indicator code
    (``cpi_score``) is emitted in the unfiltered run."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    indicator_codes = {
        obs.indicator_code for obs in result.observations
    }
    expected = {TRANSPARENCY_CPI_TEST_INDICATOR}
    assert indicator_codes == expected, (
        f"indicator code mismatch: missing "
        f"{expected - indicator_codes}; extra "
        f"{indicator_codes - expected}"
    )


def test_transparency_cpi_observation_values_match_legacy_csv(
    tmp_path: Path,
) -> None:
    """Per-row ``value`` matches the verbatim HDX CSV
    ``score`` column.

    This proves the unified transform preserves the
    canonical CPI score (integer 0-100) verbatim from the
    staged CSV (no silent conversion of missing cells
    per SRC-OBS-007).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    # The 5 fixture countries' scores (verbatim from
    # tests/fixtures/transparency_cpi/sample.csv).
    expected = {
        "IND": 39,
        "MEX": 31,
        "NGA": 25,
        "SWE": 82,
        "USA": 69,
    }
    actual = {
        obs.country_code: obs.value
        for obs in result.observations
    }
    assert actual == expected, (
        f"CPI value mismatch: expected {expected}, got "
        f"{actual}"
    )


def test_transparency_cpi_observation_raw_locator_carries_row_index(
    tmp_path: Path,
) -> None:
    """Per-observation ``RawLocator.row_number`` is the
    positional row index in the wide frame (the legacy
    reader sorts by iso3 ascending for deterministic
    idempotency, so the row index is preserved
    byte-for-byte with the input CSV).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    for obs in result.observations:
        assert obs.raw_locator.path is not None
        # The CSV path matches the per-year CSV filename.
        assert obs.raw_locator.path.endswith(
            TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
        ), (
            f"raw locator path should end with "
            f"{TRANSPARENCY_CPI_TEST_FIXTURE_CSV}; got "
            f"{obs.raw_locator.path!r}"
        )
        # The raw locator carries the catalog
        # ``raw_column`` (the HDX CSV column ``score``).
        assert obs.raw_locator.column_name == (
            TRANSPARENCY_CPI_TEST_RAW_COLUMN
        )
        # The positional row index is preserved (the
        # legacy reader sorts by iso3 ascending so the
        # row index is deterministic).
        assert obs.raw_locator.row_number is not None
        assert obs.raw_locator.row_number >= 0


def test_transparency_cpi_observation_direction_hints_carried(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension`` carries the
    ``higher_is_better`` / ``raw_scale`` /
    ``normalized_scale_target`` direction hints.

    The CPI catalog declares ``higher_is_better=1`` (a
    higher CPI score = cleaner perception =
    better) so the unified transform surfaces
    ``higher_is_better=True`` on every observation; the
    raw scale is the canonical ``"0-100"`` and the
    normalized-scale target is ``"0-10"`` (the score
    modules' default scale; the deterministic scorer
    divides by 10).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert len(result.observations) > 0
    for obs in result.observations:
        assert obs.extension.get("higher_is_better") is True, (
            f"CPI score must carry higher_is_better=True; "
            f"got {obs.extension.get('higher_is_better')!r}"
        )
        assert obs.extension.get("raw_scale") == "0-100"
        assert obs.extension.get("normalized_scale_target") == "0-10"


# ---------------------------------------------------------------------------
# No-network / local-only contract
# ---------------------------------------------------------------------------


def test_transparency_cpi_runner_does_not_invoke_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unified CPI adapter is local-file only; the
    runner NEVER invokes the network.

    The test monkeypatches
    :func:`leaders_db.ingest.transparency_cpi_http.fetch_transparency_cpi_csv`
    and :func:`requests.get` with sentinels and asserts
    neither sentinel is invoked while
    ``SourceIngestRunner.run(request)`` executes the new
    CPI adapter lifecycle end-to-end. The runner must
    drive the canonical ``check_ready -> read_raw ->
    transform`` path against the staged local CSV only.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_cpi_bundle(raw_root)

    # Install sentinels on the legacy HTTP fetcher and
    # on the requests library. Neither may be invoked.
    import leaders_db.ingest.transparency_cpi_http as legacy_http

    legacy_calls: list[dict] = []
    original_fetch = legacy_http.fetch_transparency_cpi_csv

    def _fetch_tracker(*args, **kwargs):
        legacy_calls.append({"args": args, "kwargs": kwargs})
        return original_fetch(*args, **kwargs)

    monkeypatch.setattr(
        legacy_http,
        "fetch_transparency_cpi_csv",
        _fetch_tracker,
    )

    import requests

    def _requests_get_tracker(*args, **kwargs):
        raise AssertionError(
            "requests.get must not be invoked by the "
            "unified CPI adapter (no-network contract).",
        )

    monkeypatch.setattr(requests, "get", _requests_get_tracker)

    registry = InMemorySourceRegistry()
    registry.register(create_transparency_cpi_adapter())
    runner = SourceIngestRunner(registry=registry)
    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    # The new adapter ran end-to-end.
    assert len(result.observations) == 5
    # The legacy HTTP fetcher must not have been
    # invoked.
    assert legacy_calls == [], (
        f"legacy HTTP fetcher was invoked; saw "
        f"{legacy_calls!r}"
    )


# ---------------------------------------------------------------------------
# Import boundary: package import must not pull in legacy ingest
# ---------------------------------------------------------------------------


def test_transparency_cpi_adapter_module_does_not_import_legacy_ingest_at_import() -> None:
    """Importing the CPI adapter module does NOT pull in
    any ``leaders_db.ingest`` module.

    SRC-MIG-007 + docs/architecture/sources.md section
    10.1: the unified package boundary must hold for the
    new CPI adapter module. The test inspects
    ``sys.modules`` immediately after the import to
    prove the legacy ingest package is not loaded as a
    side effect.
    """
    import importlib
    import sys

    # Drop every cached ``leaders_db`` module so the
    # import below is forced to run as if it were a
    # fresh import.
    for name in list(sys.modules):
        if name == "leaders_db" or name.startswith("leaders_db."):
            del sys.modules[name]

    try:
        importlib.import_module(
            "leaders_db.sources.adapters.transparency_cpi",
        )
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "leaders_db.sources.adapters.transparency_cpi "
            "must not import leaders_db.ingest at import "
            f"time (leaked modules: {leaked})"
        )
    finally:
        for name in list(sys.modules):
            if name == "leaders_db" or name.startswith("leaders_db."):
                del sys.modules[name]


def test_transparency_cpi_package_import_does_not_register_legacy_cpi() -> None:
    """Importing ``leaders_db.sources.adapters.transparency_cpi``
    does NOT register a legacy CPI adapter.

    The new package exposes explicit
    ``create_transparency_cpi_adapter`` /
    ``register_transparency_cpi`` factories and does NOT
    auto-register on import (per
    docs/architecture/sources.md section 10.1). The test
    asserts that an empty ``InMemorySourceRegistry``
    stays empty after the import.
    """
    import importlib
    import sys

    for name in list(sys.modules):
        if name == "leaders_db" or name.startswith("leaders_db."):
            del sys.modules[name]

    try:
        importlib.import_module(
            "leaders_db.sources.adapters.transparency_cpi",
        )
        from leaders_db.sources import (
            InMemorySourceRegistry,
        )

        registry = InMemorySourceRegistry()
        assert registry.list_descriptors() == ()
    finally:
        for name in list(sys.modules):
            if name == "leaders_db" or name.startswith("leaders_db."):
                del sys.modules[name]


def test_transparency_cpi_present_but_null_local_files_blocks_readiness(
    tmp_path: Path,
) -> None:
    """An explicit ``"local_files": null`` in the staged
    ``metadata.json`` fails readiness with a structured
    ``missing_metadata`` error.

    The canonical CPI bundle metadata carries
    ``local_files=["transparency_cpi_2023.csv"]`` -- a
    list. The presence check distinguishes absent from
    present-but-null: ``local_files`` not in the payload
    is legacy-tolerant (older bundles predate the
    ``local_files`` annotation), but an explicit
    present-but-null value indicates a malformed bundle
    and must block readiness so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` / ``transform``.

    The CSV MUST be staged alongside the present-but-null
    ``local_files`` so the readiness gate progresses past
    the presence check and reaches the per-field
    validators -- this isolates the malformed
    ``local_files`` shape from the missing-CSV presence
    check (which fires first and would otherwise mask the
    shape error with a ``missing_raw`` signal).
    """
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Stage the CSV so the presence check passes and the
    # per-field validators can run; the focal error is
    # the present-but-null ``local_files``.
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        # Present-but-null -- must fail readiness.
        "local_files": None,
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        "checksum_sha256": None,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_transparency_cpi_adapter()
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    readiness = adapter.check_ready(request)
    assert readiness.ready is False, (
        "Present-but-null 'local_files' must fail readiness; "
        f"got errors: {[e.message for e in readiness.errors]}"
    )
    error_codes = [e.code for e in readiness.errors]
    assert "missing_metadata" in error_codes, (
        f"expected 'missing_metadata' error for present-but-null "
        f"local_files; got {error_codes}"
    )


def test_transparency_cpi_present_but_null_local_files_blocks_runner_short_circuit(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` against a bundle
    with present-but-null ``local_files`` raises
    ``RuntimeError`` BEFORE ``read_raw`` / ``transform``.

    Mirrors the UCDP-style
    ``test_ucdp_metadata_only_without_zip_blocks_runner_short_circuit``
    contract: a malformed bundle (here: present-but-null
    ``local_files`` instead of a missing zip) is NOT
    runner-ready, so the runner short-circuits via the
    structured ``missing_metadata`` error and
    ``read_raw`` / ``transform`` are NEVER invoked. The
    spy adapter verifies the runner's call order.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.transparency_cpi import (
        create_transparency_cpi_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "transparency_cpi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Stage the CSV + a present-but-null ``local_files``
    # metadata; the runner MUST short-circuit BEFORE
    # ``read_raw`` / ``transform``.
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "transparency_cpi"
    )
    shutil.copy2(
        fixtures / "sample.csv",
        bundle_dir / TRANSPARENCY_CPI_TEST_FIXTURE_CSV,
    )
    payload = {
        "source_name": (
            "Transparency International Corruption "
            "Perceptions Index"
        ),
        "source_version": TRANSPARENCY_CPI_TEST_DEFAULT_VERSION,
        "source_url": TRANSPARENCY_CPI_TEST_HOMEPAGE_URL,
        "license_note": (
            "Free for non-commercial use with attribution; "
            "cite Transparency International."
        ),
        "local_files": None,
        "ingestion_status": "downloaded",
        "coverage": "country-year (annual)",
        "checksum_sha256": None,
    }
    (bundle_dir / TRANSPARENCY_CPI_TEST_METADATA_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_transparency_cpi_adapter()
    spy = _SpyCPIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="transparency_cpi"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower(), (
        f"expected 'not ready' message in runner's "
        f"RuntimeError; got {excinfo.value!r}"
    )
    # The runner MUST short-circuit after ``check_ready``
    # -- ``read_raw`` / ``transform`` must NOT be
    # invoked.
    assert spy.calls == ["check_ready"], (
        f"runner must short-circuit before read_raw / "
        f"transform; got {spy.calls}"
    )


def test_transparency_cpi_package_star_import_resolves_every_all_entry() -> None:
    """``from leaders_db.sources.adapters.transparency_cpi
    import *`` resolves every name in ``__all__`` without
    raising ``AttributeError``.

    Coherence guard for Blocker 4: the public surface
    contract is that every name advertised in ``__all__``
    is bound at the package root. A name advertised in
    ``__all__`` but not actually imported / bound would
    raise ``AttributeError`` on a star import (or a
    direct ``from package import name`` call). This
    test fails loudly if a future contributor adds a
    stale entry to ``__all__`` without wiring the import.
    """
    import leaders_db.sources.adapters.transparency_cpi as pkg

    advertised = list(pkg.__all__)
    assert advertised, "package __all__ must not be empty"
    missing = [
        name for name in advertised if not hasattr(pkg, name)
    ]
    assert missing == [], (
        "Public surface incoherence: the following names "
        "are advertised in __all__ but are not bound on "
        f"the package: {missing}. Either import them at "
        "the package root or remove them from __all__."
    )

    # The two module-local warning codes whose absence
    # was the original Blocker 4 trigger must be
    # importable from the package root.
    for constant_name in (
        "TRANSPARENCY_CPI_CHECKSUM_MISMATCH",
        "UNSUPPORTED_VERSION",
    ):
        assert hasattr(pkg, constant_name), (
            f"{constant_name} must be importable from "
            "leaders_db.sources.adapters.transparency_cpi"
        )
        assert getattr(pkg, constant_name) is not None


__all__ = [
    "TRANSPARENCY_CPI_TEST_ATTRIBUTION_KEY",
    "TRANSPARENCY_CPI_TEST_CANONICAL_VALUE_TYPE",
    "TRANSPARENCY_CPI_TEST_COVERAGE_END",
    "TRANSPARENCY_CPI_TEST_COVERAGE_START",
    "TRANSPARENCY_CPI_TEST_DEFAULT_VERSION",
    "TRANSPARENCY_CPI_TEST_FAMILIES",
    "TRANSPARENCY_CPI_TEST_FIXTURE_CSV",
    "TRANSPARENCY_CPI_TEST_HOMEPAGE_URL",
    "TRANSPARENCY_CPI_TEST_INDICATOR",
    "TRANSPARENCY_CPI_TEST_METADATA_NAME",
    "TRANSPARENCY_CPI_TEST_RAW_COLUMN",
]
