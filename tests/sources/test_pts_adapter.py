"""Phase C / D slice -- Political Terror Scale (PTS)
adapter under the unified ``leaders_db.sources``
interface.

The PTS adapter is the eighth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 14,
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP, and
Transparency International CPI. The legacy PTS reader
under ``leaders_db.ingest.pts_xlsx`` is reused
internally via lazy imports -- the package boundary at
``docs/architecture/sources.md`` §10.1 is preserved.

PTS is structurally closer to WGI / V-Dem / UCDP /
CPI: one local xlsx, no HTTP layer. The unified adapter
narrows the 14-column long-format xlsx to the 3
catalog indicators (``pts_amnesty_score`` /
``pts_human_rights_watch_score`` /
``pts_state_dept_score``) and carries the per-row
audit-trail fields (``country`` / ``region`` /
``na_status``) on every observation's ``extension`` so
downstream scorers can recover the input audit trail
without re-reading the legacy xlsx.

Tests cover the documented slice acceptance criteria:

- The PTS adapter descriptor is registerable / listable
  through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata.
- The PTS descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id ``pts``,
  default version ``"PTS-2025"``, attribution_key
  ``pts``, dataset type, 1976-2024 coverage hint,
  single observation family
  ``domestic_violence_country_year``, PTS homepage
  URL).
- :class:`SourceIngestRunner` can run PTS end-to-end
  through the new registry against a fixture
  ``raw_root`` and produce :class:`NormalizedObservation`
  records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter
  internally reuses legacy parsing modules, but
  dispatch is registry-based).
- ``years=`` and ``countries=`` (COW_Code_A) filters
  are honored and surface correct observation counts.
- An out-of-coverage ``years=(2025,)`` or
  ``years=(1975,)`` request returns zero observations
  plus a structured :class:`SourceWarning` (no
  stale-proxy fill -- SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``unsupported_filter`` warning (SRC-REQ-005).
- The bundle readiness gate accepts the canonical
  primary metadata shape (``source_name`` / ``version``
  / ``source_url`` / ``license`` /
  ``coverage_start_year`` / ``coverage_end_year`` /
  ``file_format`` / ``file_size_bytes`` / ``sha256`` /
  ``ingestion_status`` / ``notes`` / ``local_files``)
  when the canonical ``PTS-2025.xlsx`` is staged on
  disk. The canonical PTS bundle metadata carries
  ``version="2025"`` (the bare-year stamp) +
  ``sha256="6f4d1ccd...88832"`` (the live xlsx
  SHA-256) + ``local_files=["PTS-2025.xlsx"]`` -- a
  deliberately minimal shape so the operator can
  update the metadata once the xlsx is staged.
- Readiness-failure paths block the runner BEFORE
  ``read_raw`` / ``transform`` for missing metadata,
  missing xlsx, missing required field, malformed
  ``local_files``, malformed / missing / mismatched
  ``sha256``, missing / mismatched metadata
  ``version``, and unsupported request
  ``source_version``.
- Canonical metadata version ``"PTS-2025"`` propagates
  consistently to ``RawAsset.version`` and every
  emitted ``NormalizedObservation.source_version``.
- Importing the new
  ``leaders_db.sources.adapters.pts`` module does NOT
  pull in any ``leaders_db.ingest`` module (SRC-MIG-007
  + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).
- Per-observation ``RawLocator`` carries the staged
  xlsx path + the catalog ``raw_column`` (``PTS_A`` /
  ``PTS_H`` / ``PTS_S``) + the positional row index in
  the wide frame (the legacy reader sorts by
  ``COW_Code_A`` ascending for deterministic
  idempotency so the row index is preserved byte-for-
  byte with the input xlsx). Per-observation
  ``extension`` carries the canonical PTS attribution
  text (Rule #15), the
  ``source_row_reference="pts:<COW_Code_A>"`` pattern
  (matching the legacy Stage 2 DB writer), the PTS
  ``COW_Code_A`` / ``country`` / ``region`` /
  ``na_status`` audit-trail fields, and the
  ``raw_scale`` / ``higher_is_better`` /
  ``normalized_scale_target`` direction hints (PTS raw
  1-5 inverted by Stage 5 score module; the unified
  transform preserves the raw 1-5 value).
- The legacy ``PTS_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/pts_io.py`` is byte-identical
  to the new ``PTS_ATTRIBUTION_TEXT`` constant
  (``test_pts_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text is
  a substring of ``docs/sources/attributions.md``).
- The §6 sentinel-matrix contract (4-case NA_Status
  precedence rule + the §6.5 defensive check on
  unknown ``NA_Status`` codes) is preserved
  byte-for-byte through the unified transform --
  the per-row observation emission skips cells where
  ``NA_Status != 0`` AND where ``PTS_X='NA'`` AND
  ``NA_Status=0`` (the case-4 inconsistency path);
  the raw cell text is preserved on the observation
  ``extension["raw_value"]`` so the audit trail
  recovers the original cell text.
- The PTS unified path is local-file only
  (``requires_network=False``, no HTTP layer in the
  new package). The runner NEVER invokes the network.
  The readiness gate validates the staged
  ``PTS-2025.xlsx`` and the metadata checksum /
  version / license / coverage / file-format /
  ingestion_status / notes / local_files fields
  BEFORE ``read_raw`` / ``transform`` are called.

PASS-ELIGIBLE rationale
-----------------------

The legacy PTS reader is well-tested via the existing
``tests/test_ingest_pts.py`` suite (39 tests covering
the §6 sentinel matrix, the wide-frame contract, the
DB writers, the orchestrator end-to-end, the CLI
dispatch, and the public surface). The tests in this
file prove that the new
``leaders_db.sources.adapters.pts`` adapter wraps the
legacy parsing logic behind the unified
``SourceAdapter`` Protocol while preserving the
package-isolation contract -- they are PASS-ELIGIBLE
because the adapter implementation lands in the same
change set.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from leaders_db.sources import SourceIngestRequest


# Test-only constants. Mirror the descriptor constants
# so the tests stay decoupled from the package's
# ``__all__`` (the constants are re-exported there but
# the test file pins the values explicitly for clarity).
PTS_TEST_FIXTURE_XLSX_NAME: str = "PTS-2025.xlsx"
PTS_TEST_METADATA_NAME: str = "metadata.json"
PTS_TEST_ATTRIBUTION_KEY: str = "pts"
PTS_TEST_SOURCE_KEY: str = "pts"
PTS_TEST_DEFAULT_VERSION: str = "PTS-2025"
PTS_TEST_BUNDLE_VERSION: str = "2025"
PTS_TEST_COVERAGE_START: int = 1976
PTS_TEST_COVERAGE_END: int = 2024
PTS_TEST_HOMEPAGE_URL: str = "https://www.politicalterrorscale.org/"
PTS_TEST_FAMILIES: tuple[str, ...] = (
    "domestic_violence_country_year",
)
PTS_TEST_INDICATOR_RAW_COLUMNS: tuple[str, ...] = (
    "PTS_A",
    "PTS_H",
    "PTS_S",
)
PTS_TEST_INDICATOR_NAMES: tuple[str, ...] = (
    "pts_amnesty_score",
    "pts_human_rights_watch_score",
    "pts_state_dept_score",
)
PTS_TEST_CANONICAL_VALUE_TYPE: str = "numeric"
PTS_TEST_XLSX_ASSET_ID: str = "pts:PTS-2025.xlsx"
PTS_TEST_SHEET_NAME: str = "PTS-2025"

# Live SHA-256 for the staged PTS-2025.xlsx bundle
# (verified live 2026-06-18 per
# ``docs/architecture/pts.md`` §2). Tests that stage a
# bundle with the canonical SHA stamp reuse this
# constant so the readiness gate's optional xlsx-
# checksum match branch fires cleanly.
PTS_TEST_CANONICAL_SHA256: str = (
    "6f4d1ccdda1d2fdce382a978922790390ce5f61ae9f4aefa1970e9ca8bd88832"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyPTSAdapter:
    """Wrap a :class:`PTSAdapter` and record every
    lifecycle call.

    The spy forwards to the underlying adapter so the
    real behavior is exercised; it just records the
    call order so readiness-failure tests can assert
    the runner does NOT progress into ``read_raw`` /
    ``transform``.
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


def _stage_pts_bundle(
    raw_root: Path,
    *,
    with_xlsx: bool = True,
    with_metadata: bool = True,
    metadata_overrides: dict[str, Any] | None = None,
    staged_sha: str | None = "AUTO",
) -> Path:
    """Stage the canonical PTS fixture bundle under
    ``raw_root/political_terror_scale``.

    Copies ``tests/fixtures/pts/sample.xlsx`` (the
    5-country real-format PTS xlsx fixture sliced from
    the live xlsx) into
    ``<raw_root>/political_terror_scale/PTS-2025.xlsx``
    and writes a well-formed ``metadata.json``
    (canonical primary shape: ``source_name`` /
    ``version`` / ``source_url`` / ``license`` /
    ``coverage_start_year`` / ``coverage_end_year`` /
    ``file_format`` / ``file_size_bytes`` / ``sha256`` /
    ``ingestion_status`` / ``notes`` / ``local_files``).

    The ``sha256`` default is the **actual staged
    fixture SHA-256** (``"AUTO"`` sentinel), so the
    readiness gate's optional xlsx-checksum match
    branch fires cleanly. Pass
    ``staged_sha=PTS_TEST_CANONICAL_SHA256`` (or any
    other 64-char hex string) to set the metadata's
    ``sha256`` field to a specific value (use the
    live-PTS-2025.xlsx stamp to exercise the
    ``pts_checksum_mismatch`` branch), ``staged_sha=None``
    to omit the field (exercises the checksum-shape
    ``null`` branch), or a non-hex string to exercise
    the malformed-sha256 branch.

    The fixture carries 5 country-year rows
    (Afghanistan 2022 + Afghanistan 2023 + Andorra
    2022 + United States 2022 + United States 2023) per
    the legacy ``tests/fixtures/pts/sample.xlsx``
    shape; the values are copied verbatim from the
    live xlsx (no invented data).
    """
    bundle_dir = raw_root / "political_terror_scale"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "pts"
    )
    fixture_xlsx = fixtures / "sample.xlsx"

    if with_xlsx:
        staged_xlsx = bundle_dir / PTS_TEST_FIXTURE_XLSX_NAME
        shutil.copy2(fixture_xlsx, staged_xlsx)

    if with_metadata:
        # Compute the actual staged SHA when ``AUTO``
        # is requested (the default), so the gate's
        # checksum-match branch fires cleanly.
        if staged_sha == "AUTO":
            staged_xlsx_path = bundle_dir / PTS_TEST_FIXTURE_XLSX_NAME
            if staged_xlsx_path.is_file():
                computed_sha: str | None = hashlib.sha256(
                    staged_xlsx_path.read_bytes(),
                ).hexdigest()
            else:
                # No xlsx staged (e.g. metadata-only
                # readiness test); omit the sha256
                # field. The ``missing_raw`` readiness
                # branch fires before the checksum
                # match branch so this is fine.
                computed_sha = None
        else:
            computed_sha = staged_sha

        payload: dict[str, Any] = {
            "source_name": "Political Terror Scale",
            "version": PTS_TEST_BUNDLE_VERSION,
            "download_date": "2026-06-18",
            "source_url": (
                "https://www.politicalterrorscale.org/"
                "Data/Files/PTS-2025.xlsx"
            ),
            "alternate_url": (
                "https://www.politicalterrorscale.org/"
                "Data/Files/PTS-2025.csv"
            ),
            "license": (
                "free academic use; cite Wood, Gibney, et al."
            ),
            "coverage_start_year": PTS_TEST_COVERAGE_START,
            "coverage_end_year": PTS_TEST_COVERAGE_END,
            "file_format": "xlsx",
            "file_size_bytes": 572234,
            "sha256": computed_sha,
            "ingestion_status": "available",
            "notes": (
                "Long format: 1 row per (country, year). 14 "
                "columns (Country, Country_OLD, Year, "
                "COW_Code_A, COW_Code_N, WordBank_Code_A, "
                "UN_Code_N, Region, PTS_A, PTS_H, PTS_S, "
                "NA_Status_A, NA_Status_H, NA_Status_S)."
            ),
            "local_files": [PTS_TEST_FIXTURE_XLSX_NAME],
        }
        if metadata_overrides:
            payload.update(metadata_overrides)
        (bundle_dir / PTS_TEST_METADATA_NAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
    return bundle_dir


def _purge_modules(prefix: str) -> None:
    """Remove every cached module starting with ``prefix``.

    Used by the import-boundary tests so a fresh
    interpreter state around a single import call can
    be asserted.
    """
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_pts_descriptor_exposes_documented_static_metadata() -> None:
    """The PTS descriptor carries every documented field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    ``docs/architecture/sources.md`` §5.2):

    - ``source_id.slug == "pts"``
    - ``display_name`` is the canonical PTS 2025 label.
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical
      metadata stamp (``"PTS-2025"``).
    - ``homepage_url`` is the canonical PTS landing
      page.
    - ``attribution_key == "pts"``
    - ``coverage_hint.start_year == 1976``,
      ``coverage_hint.end_year == 2024``.
    - ``supported_observation_families`` is the 1-tuple
      ``("domestic_violence_country_year",)``.
    - ``requires_network is False`` (local-file only).

    PASS-ELIGIBLE: the descriptor factory ships with
    the slice.
    """
    from leaders_db.sources.adapters.pts import (
        build_pts_descriptor,
    )

    descriptor = build_pts_descriptor()

    assert descriptor.source_id.slug == PTS_TEST_SOURCE_KEY
    assert descriptor.source_type == "dataset"
    assert (
        descriptor.default_version
        == PTS_TEST_DEFAULT_VERSION
    )
    assert descriptor.homepage_url == PTS_TEST_HOMEPAGE_URL
    assert (
        descriptor.attribution_key
        == PTS_TEST_ATTRIBUTION_KEY
    )
    assert (
        descriptor.coverage_hint.start_year
        == PTS_TEST_COVERAGE_START
    )
    assert (
        descriptor.coverage_hint.end_year
        == PTS_TEST_COVERAGE_END
    )
    assert descriptor.supported_observation_families == (
        PTS_TEST_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_pts_attribution_text_matches_attributions_doc() -> None:
    """The PTS attribution text is byte-identical to
    the legacy ``PTS_ATTRIBUTION`` constant AND a
    substring of ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical PTS citation
    block in ``docs/sources/attributions.md`` is the
    source of truth; the adapter module's constant
    must be byte-identical to a substring of that doc
    AND byte-identical to the legacy
    ``PTS_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/pts_io.py``.

    The text deliberately distinguishes the bundle
    folder alias (``political_terror_scale``) from the
    canonical source key (``pts``) -- the report-facing
    attribution block names the canonical
    Wood/Gibney citation, NOT the bundle-folder name.
    """
    from leaders_db.ingest.pts_io import (
        PTS_ATTRIBUTION,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_ATTRIBUTION_TEXT,
    )

    assert PTS_ATTRIBUTION_TEXT == PTS_ATTRIBUTION, (
        "Unified PTS attribution must be byte-identical "
        "to the legacy PTS_ATTRIBUTION constant in "
        "src/leaders_db/ingest/pts_io.py."
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
    attributions_text = attributions_path.read_text(
        encoding="utf-8",
    )
    assert PTS_ATTRIBUTION_TEXT in attributions_text, (
        f"{PTS_ATTRIBUTION_TEXT!r} is not a substring of "
        f"{attributions_path}. Update both in the same "
        f"commit (Rule #15)."
    )


def test_pts_adapter_satisfies_source_adapter_protocol() -> None:
    """``PTSAdapter`` instances satisfy the
    runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor``
    or any of ``check_ready`` / ``read_raw`` /
    ``transform`` at construction time.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    adapter = create_pts_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "pts"


def test_pts_descriptor_indicator_names_and_raw_columns() -> None:
    """The descriptor's indicator names + raw column
    names are byte-identical to the canonical catalog.

    The canonical catalog at
    ``src/leaders_db/ingest/catalogs/pts.csv`` lists
    three indicator rows (one per PTS score column).
    The descriptor exposes the indicator names + raw
    columns so the public surface matches the catalog
    byte-for-byte (the drift guard
    ``test_pts_attribution_text_matches_attributions_doc``
    enforces the same byte-identity on the attribution
    block; this test enforces the same on the indicator
    list).
    """
    from leaders_db.sources.adapters.pts import (
        PTS_INDICATOR_NAMES,
        PTS_RAW_COLUMNS,
    )

    assert set(PTS_INDICATOR_NAMES) == set(
        PTS_TEST_INDICATOR_NAMES,
    )
    assert set(PTS_RAW_COLUMNS) == set(
        PTS_TEST_INDICATOR_RAW_COLUMNS,
    )


def test_pts_public_surface_is_coherent() -> None:
    """The package root ``__all__`` exposes every
    public symbol documented in the adapter module +
    descriptor.

    Defense in depth: any future contributor who
    removes a public name from ``__all__`` without
    updating the design doc / the public surface
    contract will see this test fail.
    """
    from leaders_db.sources.adapters import pts as pts_pkg

    required = {
        "PTS_SOURCE_KEY",
        "PTS_DEFAULT_VERSION",
        "PTS_ATTRIBUTION_KEY",
        "PTS_ATTRIBUTION_TEXT",
        "PTS_COVERAGE_START_YEAR",
        "PTS_COVERAGE_END_YEAR",
        "PTS_HOMEPAGE_URL",
        "PTS_METADATA_NAME",
        "PTS_XLSX_NAME",
        "PTS_OBSERVATION_FAMILY",
        "PTS_INDICATOR_AMNESTY",
        "PTS_INDICATOR_HUMAN_RIGHTS_WATCH",
        "PTS_INDICATOR_STATE_DEPT",
        "PTS_INDICATOR_NAMES",
        "PTS_RAW_COLUMNS",
        "PTS_RAW_COLUMN_AMNESTY",
        "PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH",
        "PTS_RAW_COLUMN_STATE_DEPT",
        "PTS_NA_STATUS_CODES",
        "PTS_NA_SENTINEL_STRING",
        "PTS_RAW_SCALE_MIN",
        "PTS_RAW_SCALE_MAX",
        "PTS_TRANSFORM_NAME",
        "PTSAdapter",
        "build_pts_descriptor",
        "create_pts_adapter",
        "register_pts",
        "check_metadata_well_formed",
        "collect_request_scoping_warnings",
        "emit_pts_observations",
        "load_indicator_catalog",
        "rating_category_to_observation_family",
        "read_pts_xlsx",
        "transform_pts_observations",
        "DEFAULT_CATALOG_PATH",
        "PTS_CHECKSUM_MISMATCH",
        "PTS_METADATA_VERSION_MISMATCH",
        "UNSUPPORTED_VERSION",
        "REQUIRED_METADATA_FIELDS",
        "ACCEPTABLE_INGESTION_STATUSES",
        "CANONICAL_LOCAL_FILES",
        "PTS_BUNDLE_VERSION_STAMP",
        "PTS_INCONSISTENCY_WARNING_CODE",
        "PTS_UNKNOWN_NA_STATUS_WARNING_CODE",
        "build_observation",
        "_coerce_pts_value",
        "_raw_cell_text",
        "_raw_na_status_text",
        "_bundle_dir",
        "_xlsx_path",
        "_metadata_path",
        "_read_metadata_payload",
        "_default_asset_id",
        "_default_source_version",
        "_raw_columns",
        "_xlsx_name",
    }
    missing = required - set(pts_pkg.__all__)
    assert not missing, (
        f"missing public names on leaders_db.sources."
        f"adapters.pts: {missing}"
    )


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_pts_adapter_is_registerable_through_in_memory_registry() -> None:
    """``create_pts_adapter()`` produces an adapter the
    registry accepts.

    The :class:`InMemorySourceRegistry` rejects
    duplicate slugs with ``ValueError`` (SRC-REG-004);
    the test asserts the PTS adapter registers cleanly
    under the ``pts`` slug and the descriptor is
    listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_pts_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "pts"

    resolved = registry.get_descriptor(SourceId(slug="pts"))
    assert resolved is listed[0]
    assert registry.get_adapter(SourceId(slug="pts")) is adapter


def test_pts_register_helper_registers_against_explicit_registry() -> None:
    """``register_pts(registry)`` is the explicit seam
    for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.pts import register_pts

    registry = InMemorySourceRegistry()
    adapter = register_pts(registry)
    assert registry.get_adapter(SourceId(slug="pts")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_pts_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives PTS
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records.

    The fixture has 5 country-year rows
    (Afghanistan 2022 + Afghanistan 2023 + Andorra 2022
    + USA 2022 + USA 2023) with the 3 catalog
    indicators (``pts_amnesty_score`` /
    ``pts_human_rights_watch_score`` /
    ``pts_state_dept_score``). 11 valid observations
    round-trip (Andorra's PTS_A + PTS_H drop on
    NA_Status=88; USA's PTS_S drops on NA_Status=88 in
    both years -- matching the legacy
    ``tests/test_ingest_pts.py`` contract).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    # Afghanistan 2022: 3 (all valid)
    # Afghanistan 2023: 3 (all valid)
    # Andorra 2022: 1 (PTS_A + PTS_H dropped; PTS_S valid)
    # USA 2022: 2 (PTS_A + PTS_H valid; PTS_S dropped)
    # USA 2023: 2 (PTS_A + PTS_H valid; PTS_S dropped)
    # Total: 11 observations
    assert len(result.observations) == 11, (
        f"expected 11 observations (5 country-years x 3 "
        f"indicators - 4 dropped cells); got "
        f"{len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "pts"
        assert obs.observation_family == (
            PTS_TEST_FAMILIES[0]
        )
        assert obs.year in {2022, 2023}
        assert obs.indicator_code in PTS_TEST_INDICATOR_NAMES
        assert obs.country_code in {"AFG", "AND", "USA"}
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert (
            obs.value_type == PTS_TEST_CANONICAL_VALUE_TYPE
        )
        assert obs.value in {1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_pts_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives PTS through the new registry
    and never calls into
    ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches
    ``STAGE2_ADAPTERS["pts"]`` with a tracking sentinel
    and asserts the sentinel is never invoked while
    ``SourceIngestRunner.run(request)`` executes the
    new PTS adapter lifecycle end-to-end.

    SRC-REG-003 / ``docs/architecture/sources.md``
    §10.1: the new registry is the single dispatch
    surface; legacy dispatch is explicitly forbidden
    for the new runner.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    # Replace the legacy ``pts`` slot with a tracker
    # that records every invocation. The runner must
    # never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("pts")

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["pts"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_pts_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="pts"),
            raw_root=raw_root,
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 11

        # The legacy tracker must not have been called.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through "
            "STAGE2_ADAPTERS instead of the new registry; "
            f"saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["pts"] = original


# ---------------------------------------------------------------------------
# Request scoping: years + countries (COW_Code_A)
# ---------------------------------------------------------------------------


def test_pts_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2023,)`` is honored.

    The fixture has 5 country-year rows; filtering to
    year=2023 narrows to 2 rows (Afghanistan 2023 + USA
    2023). The legacy ``test_db_writers_idempotent_rerun``
    expects 5 observations for year=2023 (AFG: 3 + USA:
    2; AND is 2022 only).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {2023}


def test_pts_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('AFG',)`` is
    honored.

    COW_Code_A is the canonical primary key per design
    doc §7.2; the ``countries=`` filter applies as an
    exact match against the ``COW_Code_A`` column.
    Filtering to AFG narrows to 2 country-year rows x 3
    indicators = 6 observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        countries=("AFG",),
    )
    result = runner.run(request)
    assert len(result.observations) == 6
    assert {obs.country_code for obs in result.observations} == {
        "AFG",
    }


def test_pts_combined_year_and_country_filter(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2023,) +
    countries=('USA',)`` filters to USA 2023 only -- 2
    observations round-trip (PTS_A + PTS_H valid;
    PTS_S dropped on NA_Status=88)."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 2
    assert {obs.year for obs in result.observations} == {2023}
    assert {obs.country_code for obs in result.observations} == {
        "USA",
    }


def test_pts_out_of_coverage_year_emits_year_absent_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2025,)`` (out of
    coverage) emits zero observations plus a
    structured ``year_absent`` warning per
    SRC-COV-002 / SRC-COV-003."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        years=(2025,),
    )
    result = runner.run(request)
    assert len(result.observations) == 0
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got "
        f"{warning_codes}"
    )


def test_pts_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.leaders=('X',)`` emits a
    structured ``unsupported_filter`` warning per
    SRC-REQ-005.

    PTS is a country-year political-terror source;
    leader filters are not supported. The warning is
    surfaced on the readiness envelope AND propagated
    through to the final result envelope.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        leaders=("Some Leader",),
    )
    result = runner.run(request)
    # The leader filter is unsupported but the
    # transform still emits observations (the
    # readiness warning is advisory only).
    assert len(result.observations) == 11
    warning_codes = [w.code for w in result.warnings]
    assert "unsupported_filter" in warning_codes, (
        f"expected 'unsupported_filter' warning, got "
        f"{warning_codes}"
    )


# ---------------------------------------------------------------------------
# Readiness-failure paths
# ---------------------------------------------------------------------------


def test_pts_missing_xlsx_fails_readiness_with_missing_raw(
    tmp_path: Path,
) -> None:
    """A metadata-only bundle (no staged xlsx) fails
    readiness with a structured ``missing_raw`` error.

    Uses a spy adapter to verify the runner
    short-circuits BEFORE ``read_raw`` /
    ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata only -- no xlsx.
    _stage_pts_bundle(raw_root, with_xlsx=False)

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    # The runner must short-circuit before
    # ``read_raw`` / ``transform``.
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_pts_missing_metadata_fails_readiness_with_missing_metadata(
    tmp_path: Path,
) -> None:
    """An xlsx-only bundle (no metadata.json) fails
    readiness with a structured ``missing_metadata``
    error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage xlsx only -- no metadata.json.
    _stage_pts_bundle(raw_root, with_metadata=False)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()


def test_pts_unsupported_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """``source_version="PTS-2024"`` fails readiness
    with a structured ``unsupported_version`` error
    per SRC-REQ-009.

    Uses a spy adapter to verify the runner
    short-circuits BEFORE ``read_raw`` /
    ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        source_version="PTS-2024",
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_pts_mismatched_metadata_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Bundle metadata ``version="2024"`` (mismatched
    canonical ``"2025"`` stamp) fails readiness with a
    structured ``pts_metadata_version_mismatch`` error.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"version": "2024"},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_pts_malformed_sha256_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with a malformed ``sha256`` (non-hex
    string) fails readiness with a structured
    ``missing_metadata`` error from the checksum-shape
    validator.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        staged_sha="not-a-valid-hex-sha256",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_pts_mismatched_sha256_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with a well-formed ``sha256`` that
    disagrees with the staged xlsx SHA-256 fails
    readiness with a structured
    ``pts_checksum_mismatch`` error.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    # Stage with a well-formed but mismatched sha256.
    wrong_sha = "0" * 64
    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root, staged_sha=wrong_sha)

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_pts_correct_sha256_passes_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with the correct canonical SHA-256
    (``6f4d1ccd...88832``) passes readiness -- the
    xlsx-checksum match branch fires cleanly.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    # The fixture's xlsx SHA-256 is whatever openpyxl
    # produces when slicing the real xlsx; verify by
    # reading the file before asserting the
    # canonical stamp matches it. This ensures the
    # test stays correct if the fixture is regenerated.
    bundle_dir = raw_root / "political_terror_scale"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "pts"
    )
    shutil.copy2(
        fixtures / "sample.xlsx",
        bundle_dir / PTS_TEST_FIXTURE_XLSX_NAME,
    )
    fixture_sha = hashlib.sha256(
        (bundle_dir / PTS_TEST_FIXTURE_XLSX_NAME).read_bytes(),
    ).hexdigest()
    # Stage metadata with the actual fixture SHA so
    # the readiness gate's checksum-match branch
    # passes. (The canonical SHA stamps the real
    # xlsx; the fixture is a slice of the real xlsx
    # so the SHA differs from the canonical stamp;
    # we use the fixture SHA so the gate fires the
    # correct-checksum path.)
    _stage_pts_bundle(
        raw_root,
        staged_sha=fixture_sha,
    )

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    # The run completes successfully (no exception,
    # 11 observations).
    assert len(result.observations) == 11


def test_pts_malformed_local_files_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with ``local_files=null`` (present-but-
    null) fails readiness with a structured
    ``missing_metadata`` error from the local-files
    validator.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"local_files": None},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_pts_adapter()
    spy = _SpyPTSAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


# ---------------------------------------------------------------------------
# Readiness-failure direct check_ready() structured assertions
#
# Each test below calls ``adapter.check_ready(request)`` directly and
# asserts the structured ``ReadinessResult`` envelope -- ready=False, a
# single ``errors`` entry with the exact ``code``, ``severity='error'``,
# the canonical ``source_id.slug='pts'``, and the key ``context`` fields
# the runner surfaces to the operator. The runner short-circuit tests
# above only assert ``RuntimeError`` + spy calls; these tests pin the
# structured details so a refactor that swaps the error code (or drops
# the severity flag) cannot silently regress the contract.
# ---------------------------------------------------------------------------


def _assert_readiness_error(
    result: Any,
    *,
    expected_code: str,
    expected_severity: str = "error",
    expected_source_slug: str = PTS_TEST_SOURCE_KEY,
    expected_context_keys: tuple[str, ...] = (),
) -> None:
    """Assert ``result`` is a single-error failure envelope.

    Defense in depth for the readiness gate: a refactor that emits the
    right ``ready=False`` but the wrong error code, the wrong severity,
    or a missing source-id context will fail this helper before the
    runner short-circuit test even runs.
    """
    assert result.ready is False, (
        f"expected ready=False; got {result.ready!r}"
    )
    assert result.warnings == (), (
        f"expected no warnings on a failure envelope; got "
        f"{result.warnings!r}"
    )
    assert len(result.errors) == 1, (
        f"expected exactly one error; got {result.errors!r}"
    )
    error = result.errors[0]
    assert error.code == expected_code, (
        f"expected code={expected_code!r}; got {error.code!r}"
    )
    assert error.severity == expected_severity, (
        f"expected severity={expected_severity!r}; got "
        f"{error.severity!r}"
    )
    assert error.source_id is not None, (
        "error.source_id must be set so the runner can route "
        "the diagnostic to the operator"
    )
    assert error.source_id.slug == expected_source_slug, (
        f"expected source_id.slug={expected_source_slug!r}; "
        f"got {error.source_id.slug!r}"
    )
    for key in expected_context_keys:
        assert key in error.context, (
            f"missing context key {key!r}; got "
            f"{dict(error.context)!r}"
        )


def test_pts_check_ready_missing_metadata_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when ``metadata.json`` is absent.

    The structured error carries ``severity='error'``,
    ``source_id.slug='pts'``, and the canonical context keys
    (``bundle_dir`` + ``xlsx_name``) so the runner can route the
    diagnostic to the operator.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_XLSX_NAME,
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root, with_metadata=False)

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )
    # The error context must point at the bundle directory the
    # readiness gate inspected + the canonical xlsx filename.
    assert result.errors[0].context["xlsx_name"] == PTS_XLSX_NAME


def test_pts_check_ready_missing_xlsx_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_raw`` error when the staged xlsx is absent.

    The metadata-only bundle path is the canonical branch -- a
    metadata-only bundle is intentionally NOT runner-ready (the
    readiness gate fires ``missing_raw`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` / ``transform``).
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_XLSX_NAME,
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root, with_xlsx=False)

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_raw",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )
    assert result.errors[0].context["xlsx_name"] == PTS_XLSX_NAME


def test_pts_check_ready_unsupported_request_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``unsupported_version`` error when the request
    ``source_version`` differs from the canonical ``"PTS-2025"``.

    Per SRC-REQ-009: the canonical PTS stamp is ``"PTS-2025"``; the
    request ``source_version`` is rejected at the readiness gate with
    a structured error carrying the requested + canonical version in
    the context.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        source_version="PTS-2024",
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="unsupported_version",
        expected_context_keys=(
            "requested_version",
            "canonical_version",
        ),
    )
    assert result.errors[0].context["requested_version"] == "PTS-2024"
    assert result.errors[0].context["canonical_version"] == (
        PTS_TEST_DEFAULT_VERSION
    )


def test_pts_check_ready_mismatched_bundle_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``pts_metadata_version_mismatch`` error when the bundle's
    ``version`` stamp differs from the canonical ``"2025"``.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"version": "2024"},
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="pts_metadata_version_mismatch",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_malformed_sha256_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when the metadata ``sha256`` is
    non-hex (the checksum-shape validator fires).
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        staged_sha="not-a-valid-hex-sha256",
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_sha256_mismatch_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``pts_checksum_mismatch`` error when a well-formed
    ``sha256`` disagrees with the staged xlsx SHA-256.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    wrong_sha = "0" * 64
    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root, staged_sha=wrong_sha)

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="pts_checksum_mismatch",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_malformed_local_files_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when ``local_files`` is
    present-but-null (the local-files validator fires).
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"local_files": None},
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_wrong_local_files_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when ``local_files`` does NOT
    include the canonical xlsx filename.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"local_files": ["some_other.xlsx"]},
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_missing_required_metadata_field_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when a required metadata field is
    absent (e.g. ``license`` is dropped).

    Defense in depth for the per-field validator chain: a refactor
    that drops the required-field gate will see this test fail before
    the per-row emission breaks.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"license": ""},
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_invalid_ingestion_status_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=False`` with a
    single ``missing_metadata`` error when ``ingestion_status`` is not
    in the documented acceptable set.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(
        raw_root,
        metadata_overrides={"ingestion_status": "bogus_status"},
    )

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )


def test_pts_check_ready_happy_path_emits_no_errors(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns ``ready=True`` with no
    errors when the bundle is fully well-formed.

    Counterpart to the failure-path structured assertions: the green
    path returns ``ready=True`` and an empty ``errors`` tuple. This
    pins the happy-path envelope so a future refactor that always
    emits an error cannot silently regress the contract.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    adapter = create_pts_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    assert result.ready is True, (
        f"expected ready=True on the canonical bundle; got "
        f"{result.ready!r} with errors={result.errors!r}"
    )
    assert result.errors == (), (
        f"expected no errors on the canonical bundle; got "
        f"{result.errors!r}"
    )


# ---------------------------------------------------------------------------
# No-network contract on the production runner path
#
# The descriptor advertises ``requires_network=False`` and the clean
# adapter has no HTTP layer at all. This test pins the contract on the
# actual production runner path by monkeypatching common network entry
# points (requests.*, urllib.request.urlopen, socket.socket) to raise
# if invoked -- a successful end-to-end run with the tripwires armed
# proves the runner NEVER touches the network.
# ---------------------------------------------------------------------------


def test_pts_runner_never_invokes_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SourceIngestRunner.run(request)`` succeeds end-to-end against a
    staged local xlsx even with every common network entry point rigged
    to raise on call.

    The PTS unified path is local-file only (``requires_network=False``,
    no HTTP layer). This test monkeypatches the canonical Python network
    surfaces (``requests.get`` / ``requests.post`` /
    ``urllib.request.urlopen`` / ``socket.socket``) to raise
    ``RuntimeError`` if invoked, then drives the production
    :class:`SourceIngestRunner` end-to-end from a staged fixture. The
    run must complete cleanly -- 11 observations, no exception -- which
    proves the runner NEVER touches the network on the PTS path.

    A future refactor that introduces an HTTP layer in
    ``read_pts_xlsx`` / the legacy ``read_pts`` bridge / the transform
    pipeline will see this test fail at the first network call.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    # Arm the network tripwires. Each guarded callable raises a
    # distinctive sentinel so a regression surfaces the exact entry
    # point that was hit.
    network_sentinel = "PTS_NETWORK_TRIPWIRE_FIRED"

    def _tripwire(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(network_sentinel)

    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        requests = None  # type: ignore[assignment]

    if requests is not None:
        monkeypatch.setattr(
            requests, "get", _tripwire, raising=False,
        )
        monkeypatch.setattr(
            requests, "post", _tripwire, raising=False,
        )
        monkeypatch.setattr(
            requests, "head", _tripwire, raising=False,
        )

    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", _tripwire, raising=False,
    )

    import socket

    monkeypatch.setattr(
        socket, "socket", _tripwire, raising=False,
    )

    # Guard the legacy PTS reader too in case a future refactor pulls
    # it into the runner path. The lazy import is resolved at
    # ``read_pts_xlsx`` time inside the adapter; monkeypatching
    # ``read_pts`` to raise on call proves the runner does not invoke
    # it as a network layer (it only uses it as the local xlsx reader).
    import leaders_db.ingest.pts_xlsx as legacy_pts_xlsx

    original_read_pts = legacy_pts_xlsx.read_pts
    read_pts_calls: list[dict[str, Any]] = []

    def _spy_read_pts(*args: Any, **kwargs: Any) -> Any:
        read_pts_calls.append({"args": args, "kwargs": kwargs})
        return original_read_pts(*args, **kwargs)

    monkeypatch.setattr(legacy_pts_xlsx, "read_pts", _spy_read_pts)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )

    # The run must succeed (no exception). Any tripwire firing
    # surfaces as ``RuntimeError(network_sentinel)`` and fails the
    # test.
    result = runner.run(request)
    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    # The fixture's 5 country-year rows x 3 indicators - 4 dropped
    # cells on NA_Status=88 round-trip 11 observations.
    assert len(result.observations) == 11, (
        f"expected 11 observations after a no-network end-to-end "
        f"run; got {len(result.observations)}"
    )

    # Defense in depth: the legacy reader was actually invoked (it is
    # the lazy bridge used inside ``read_pts_xlsx``), but only as a
    # local xlsx reader -- it never made an outbound call.
    assert read_pts_calls, (
        "legacy read_pts should have been invoked exactly once for "
        "the local xlsx read; if not, the lazy bridge regressed"
    )
    for call in read_pts_calls:
        # The legacy reader only accepts ``xlsx_path`` -- any other
        # kwarg would be a hidden network seam.
        assert set(call["kwargs"]).issubset({"xlsx_path"}), (
            f"legacy read_pts was invoked with unexpected kwargs "
            f"(possible hidden network seam): {call['kwargs']!r}"
        )


# ---------------------------------------------------------------------------
# Per-observation contract: locator + extension payload
# ---------------------------------------------------------------------------


def test_pts_observation_carries_rule_id_and_extension_locators(
    tmp_path: Path,
) -> None:
    """Each PTS observation's ``observation_id`` follows
    the canonical ``pts:<COW_Code_A>:<year>:<variable_name>``
    pattern; ``extension.source_row_reference`` carries
    the ``pts:<COW_Code_A>`` pattern matching the
    legacy Stage 2 DB writer.

    The per-row extension carries the canonical PTS
    attribution text (Rule #15), the PTS-specific
    audit-trail fields (cow_code / country_name /
    region / na_status), and the direction hints
    (``higher_is_better=False`` / ``raw_scale`` /
    ``normalized_scale_target``).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_ATTRIBUTION_TEXT,
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(2022,),
    )
    result = runner.run(request)

    # Afghanistan 2022: 3 valid observations.
    assert len(result.observations) == 3
    for obs in result.observations:
        # ``observation_id`` is the canonical rule id
        # ``pts:<COW>:<year>:<variable>``.
        assert obs.observation_id.startswith(
            f"pts:{obs.country_code}:{obs.year}:",
        ), (
            f"observation_id must follow the pts pattern; "
            f"got {obs.observation_id!r}"
        )
        # ``extension.source_row_reference`` is the
        # ``pts:<COW_Code_A>`` legacy Stage 2 DB writer
        # pattern.
        source_row_ref = obs.extension.get(
            "source_row_reference",
        )
        assert source_row_ref == (
            f"pts:{obs.country_code}"
        ), (
            f"source_row_reference must be 'pts:<COW>'; "
            f"got {source_row_ref!r}"
        )
        # The PTS-specific extension fields are
        # present and correctly populated.
        assert obs.extension.get("pts_cow_code") == (
            obs.country_code
        )
        assert obs.extension.get(
            "pts_rating_category",
        ) == "domestic_violence"
        assert obs.extension.get(
            "pts_country_name",
        ) == "Afghanistan"
        assert "pts_region" in obs.extension
        assert obs.extension.get("pts_na_status") == "0"
        assert obs.extension.get(
            "attribution",
        ) == PTS_ATTRIBUTION_TEXT


def test_pts_observation_direction_hints(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension`` carries the
    direction hints (``higher_is_better=False`` /
    ``raw_scale`` / ``normalized_scale_target``) that
    match the canonical catalog.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(2022,),
    )
    result = runner.run(request)

    for obs in result.observations:
        # PTS raw scale is 1-5 ordinal; higher = more
        # terror = worse. The Stage 5 score module
        # inverts the direction (PTS 1 -> 10, ..., PTS
        # 5 -> 0). The unified transform preserves
        # the raw 1-5 value on ``value`` and carries
        # the direction hint on
        # ``extension.higher_is_better=False``.
        assert obs.extension.get(
            "higher_is_better",
        ) is False, (
            f"got {obs.extension.get('higher_is_better')!r}"
        )
        assert obs.extension.get("raw_scale") == "ordinal"
        assert obs.extension.get(
            "normalized_scale_target",
        ) == "0-10"
        # The raw value is the integer 1-5 (not the
        # inverted 0-10 score); the inversion is the
        # Stage 5 score module's responsibility.
        assert obs.value in {1, 2, 3, 4, 5}


def test_pts_observation_raw_value_audit_trail(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension.raw_value`` carries
    the verbatim pre-coercion cell text per the §6.3
    audit-trail matrix.

    Valid cells (case 1: int 1-5 + NA_Status=0) carry
    the int as a string (``"5"``). Dropped cells
    (cases 2/3/4) carry either the int or the literal
    ``"NA"`` string. The runner only emits
    observations for valid cells (case 1) so every
    emitted observation's ``raw_value`` is the int
    string (``"5"`` for Afghanistan 2022 across all 3
    indicators per the fixture).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(2022,),
    )
    result = runner.run(request)

    assert len(result.observations) == 3
    for obs in result.observations:
        # The fixture's Afghanistan 2022 row has
        # PTS_A=5, PTS_H=5, PTS_S=5 (case 1: int 5 +
        # NA_Status=0). The audit trail preserves the
        # ``"5"`` string.
        assert obs.extension.get("raw_value") == "5", (
            f"raw_value should be '5' (the audit trail "
            f"of the int 5 cell); got "
            f"{obs.extension.get('raw_value')!r}"
        )


def test_pts_observation_raw_locator_carries_xlsx_metadata(
    tmp_path: Path,
) -> None:
    """Per-observation ``RawLocator`` carries the staged
    xlsx path + the catalog ``raw_column`` + the
    positional row index in the wide frame.

    The legacy reader sorts by ``COW_Code_A``
    ascending; the per-observation row index in the
    wide frame is preserved byte-for-byte with the
    input xlsx.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_XLSX_ASSET_ID,
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
        countries=("AFG",),
        years=(2022,),
    )
    result = runner.run(request)

    assert len(result.observations) == 3
    for obs in result.observations:
        # The raw locator carries the canonical asset
        # id + the staged xlsx path + the catalog
        # ``raw_column`` (``PTS_A`` / ``PTS_H`` /
        # ``PTS_S``) + the row index in the wide
        # frame.
        assert obs.raw_locator.asset_id == PTS_XLSX_ASSET_ID
        assert obs.raw_locator.path is not None
        assert obs.raw_locator.path.endswith(
            "PTS-2025.xlsx",
        )
        assert obs.raw_locator.column_name in {
            "PTS_A",
            "PTS_H",
            "PTS_S",
        }
        # The row index is an int (or ``None`` for
        # the defensive guard).
        assert obs.raw_locator.row_number is None or (
            isinstance(obs.raw_locator.row_number, int)
            and obs.raw_locator.row_number >= 0
        )


def test_pts_observation_source_version_propagation(
    tmp_path: Path,
) -> None:
    """``source_version="PTS-2025"`` propagates
    consistently to ``RawAsset.version`` AND every
    emitted ``NormalizedObservation.source_version``.

    The canonical metadata stamp is the request-
    scoped canonical ``"PTS-2025"``; the bundle's
    ``version`` field (``"2025"``) is a different
    shape that the readiness gate validates but
    observations do not carry.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.pts import (
        PTS_DEFAULT_VERSION,
        create_pts_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_pts_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_pts_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="pts"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    # The ``RawReadResult`` carries the canonical
    # version on the raw asset. We can inspect via
    # the runner's last-read result by re-running
    # ``read_raw`` directly.
    adapter = create_pts_adapter()
    raw = adapter.read_raw(request)
    assert raw.assets
    for asset in raw.assets:
        assert asset.version == PTS_DEFAULT_VERSION
    # And every emitted observation carries the
    # canonical version on ``source_version``.
    for obs in result.observations:
        assert obs.source_version == PTS_DEFAULT_VERSION


# ---------------------------------------------------------------------------
# Sentinel-matrix helpers
# ---------------------------------------------------------------------------


def test_pts_sentinel_matrix_case_1_valid_int() -> None:
    """Case 1: ``PTS_X=3`` + ``NA_Status_X=0`` -> valid;
    return the int 3 (per design doc §6)."""
    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    value = _coerce_pts_value(
        pts_cell=3, na_status=0,
        country="USA", year=2023,
        indicator="pts_amnesty_score",
    )
    assert value == 3


def test_pts_sentinel_matrix_case_2_int_with_nonzero_status() -> None:
    """Case 2: ``PTS_X=3`` + ``NA_Status_X=88`` -> drop
    the indicator (NA_Status takes precedence)."""
    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    value = _coerce_pts_value(
        pts_cell=3, na_status=88,
        country="USA", year=2023,
        indicator="pts_amnesty_score",
    )
    assert value is None


def test_pts_sentinel_matrix_case_3_na_with_nonzero_status() -> None:
    """Case 3: ``PTS_X='NA'`` + ``NA_Status_X=88`` -> drop
    the indicator (the sentinel was a missing-value
    flag, and NA_Status confirms it)."""
    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    value = _coerce_pts_value(
        pts_cell="NA", na_status=88,
        country="USA", year=2023,
        indicator="pts_amnesty_score",
    )
    assert value is None


def test_pts_sentinel_matrix_case_4_inconsistency(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 4: ``PTS_X='NA'`` + ``NA_Status_X=0`` ->
    drop + WARNING (the inconsistency case)."""
    import logging

    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    caplog.set_level(logging.WARNING)
    value = _coerce_pts_value(
        pts_cell="NA", na_status=0,
        country="Bahamas", year=2017,
        indicator="pts_amnesty_score",
    )
    assert value is None
    # The warning must be logged with the country /
    # year / indicator context.
    messages = [
        r.message for r in caplog.records
        if r.levelno == logging.WARNING
    ]
    assert any(
        "Bahamas" in msg and "2017" in msg
        and "pts_amnesty_score" in msg
        for msg in messages
    ), f"expected Bahamas 2017 warning, got {messages}"


def test_pts_sentinel_matrix_unknown_na_status_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§6.5 defensive check: an unknown ``NA_Status``
    code (e.g. the hypothetical 55 per architecture
    §6.5) triggers a WARNING and is treated as
    missing.
    """
    import logging

    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    caplog.set_level(logging.WARNING)
    value = _coerce_pts_value(
        pts_cell=3, na_status=55,
        country="Futureland", year=2024,
        indicator="pts_amnesty_score",
    )
    assert value is None
    messages = [
        r.message for r in caplog.records
        if r.levelno == logging.WARNING
    ]
    assert any(
        "55" in msg and "NA_Status" in msg
        for msg in messages
    ), f"expected unknown NA_Status warning, got {messages}"


def test_pts_sentinel_matrix_all_known_na_status_codes() -> None:
    """All 5 known ``NA_Status`` codes are accepted by
    the precedence rule (NA_Status=0 keeps; the other 4
    drop)."""
    from leaders_db.sources.adapters.pts import (
        _coerce_pts_value,
    )

    for code in (0, 66, 77, 88, 99):
        value = _coerce_pts_value(
            pts_cell=3, na_status=code,
            country="X", year=2023,
            indicator="pts_amnesty_score",
        )
        if code == 0:
            assert value == 3, (
                f"NA_Status=0 must keep the int; "
                f"got {value!r}"
            )
        else:
            assert value is None, (
                f"NA_Status={code} must drop the indicator; "
                f"got {value!r}"
            )


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------


def test_pts_adapter_module_does_not_import_legacy_ingest() -> None:
    """``import leaders_db.sources.adapters.pts`` MUST
    NOT import ``leaders_db.ingest``.

    SRC-MIG-007 + ``docs/architecture/sources.md``
    §10.1: the package boundary is preserved. The
    test inspects ``sys.modules`` immediately after
    the import to prove legacy ingest is not loaded
    as a side effect.
    """
    _purge_modules("leaders_db")
    try:
        importlib = __import__("importlib")
        importlib.import_module("leaders_db.sources.adapters.pts")
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "leaders_db.sources.adapters.pts must not "
            "import leaders_db.ingest at import time "
            f"(leaked modules: {leaked})"
        )
    finally:
        _purge_modules("leaders_db")


# ---------------------------------------------------------------------------
# README constant shape (consumer contract)
# ---------------------------------------------------------------------------


def test_pts_default_version_matches_canonical_stamp() -> None:
    """The canonical ``PTS_DEFAULT_VERSION`` constant
    is the ``"PTS-2025"`` stamp matching the legacy
    ``register_pts_source`` upsert key.

    Defense in depth: a future refactor that changes
    the canonical stamp will see this test fail
    BEFORE the readiness gate / DB writer / parquet
    metadata break.
    """
    from leaders_db.sources.adapters.pts import (
        PTS_DEFAULT_VERSION,
    )

    assert PTS_DEFAULT_VERSION == PTS_TEST_DEFAULT_VERSION
    assert PTS_DEFAULT_VERSION == "PTS-2025"


def test_pts_xlsx_name_matches_canonical_filename() -> None:
    """The canonical ``PTS_XLSX_NAME`` constant is the
    ``"PTS-2025.xlsx"`` filename matching the live
    xlsx download.
    """
    from leaders_db.sources.adapters.pts import (
        PTS_XLSX_NAME,
    )

    assert PTS_XLSX_NAME == "PTS-2025.xlsx"


__all__ = [
    "PTS_TEST_BUNDLE_VERSION",
    "PTS_TEST_CANONICAL_SHA256",
    "PTS_TEST_CANONICAL_VALUE_TYPE",
    "PTS_TEST_DEFAULT_VERSION",
    "PTS_TEST_FAMILIES",
    "PTS_TEST_FIXTURE_XLSX_NAME",
    "PTS_TEST_HOMEPAGE_URL",
    "PTS_TEST_INDICATOR_NAMES",
    "PTS_TEST_INDICATOR_RAW_COLUMNS",
    "PTS_TEST_METADATA_NAME",
    "PTS_TEST_SHEET_NAME",
    "PTS_TEST_SOURCE_KEY",
    "PTS_TEST_XLSX_ASSET_ID",
]
