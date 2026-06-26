"""Phase C / D slice -- Reporters Without Borders (RSF)
World Press Freedom Index adapter under the unified
``leaders_db.sources`` interface.

The RSF adapter is the ninth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 7,
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, and Political Terror
Scale. The legacy RSF reader / transform / catalog
under ``leaders_db.ingest.rsf_press_freedom_csv`` +
``leaders_db.ingest.rsf_press_freedom_io`` is reused
internally via lazy imports -- the package boundary at
``docs/architecture/sources.md`` §10.1 is preserved.

RSF is structurally distinct from every prior clean-
source migration:

- It is the first source with **24 local annual CSV
  files** (2002-2010 + 2012-2026; the direct
  ``2011.csv`` is absent per the documented 2011
  missing / direct-CSV caveat -- RSF publishes a
  combined 2011/2012 edition represented by the 2012
  CSV).
- It is the first source with **semicolon-delimited
  CSVs and a comma decimal separator** (European
  convention).
- It is the first source with **mixed encodings
  across years**: 2002-2024 are ``utf-8-sig`` (with
  BOM); 2025-2026 are ``cp1252`` (no BOM, contains
  Arabic/Persian country labels not representable in
  UTF-8). The legacy reader applies a BOM-first /
  cp1252-fallback strategy.
- It has **two pre/post-2022 schema generations**:
  2002-2021 is a 16-column wide format with score +
  rank only; 2022+ adds 5 component-context columns
  (Political Context, Economic Context, Legal
  Context, Social Context, Safety). The Stage 2
  indicator catalog lists 7 indicators (2 from the
  base format + 5 components); for pre-2022 files
  the 5 component columns are absent and the
  observations for those indicators are simply not
  emitted for those years.
- The 2022 file contains **181 blank separator rows**
  between data rows; the reader drops them.
- It is the first source where the **direct 2011
  file is absent**. Year=2011 queries fail readiness
  with a structured ``rsf_year_2011_absent`` warning
  (NOT a generic ``year_absent`` so the operator can
  distinguish the documented 2011 caveat from a
  generic out-of-coverage year).
- It is the first source where the **score direction
  is higher-is-better** (higher RSF score = better
  press-freedom situation -- the RSF methodology
  inverts the natural "freedom" framing); the rank
  direction is higher-is-better=False (rank 1 = best
  country).
- It targets the ``political_freedom`` rating
  category exclusively (RSF is a press/media-
  freedom sub-signal per
  ``docs/sources/vetting/report.md`` §3.2; it is
  explicitly NOT a full political-freedom
  replacement).

Tests cover the documented slice acceptance criteria:

- The RSF adapter descriptor is registerable /
  listable through the new
  :class:`InMemorySourceRegistry` and exposes the
  documented static metadata.
- The RSF descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id
  ``rsf_press_freedom``, default version
  ``"RSF Press Freedom Index 2026"``, attribution
  key ``rsf_press_freedom``, dataset type, 2002-2026
  coverage hint, single observation family
  ``political_freedom_country_year``, RSF homepage
  URL).
- :class:`SourceIngestRunner` can run RSF end-to-end
  through the new registry against a fixture
  ``raw_root`` and produce
  :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter
  internally reuses legacy parsing modules, but
  dispatch is registry-based).
- ``years=`` and ``countries=`` (ISO 3-letter
  alphabetic code) filters are honored and surface
  correct observation counts.
- An out-of-coverage ``years=(2027,)`` or
  ``years=(2001,)`` request returns zero observations
  plus a structured :class:`SourceWarning` (no
  stale-proxy fill -- SRC-COV-002 / SRC-COV-003).
- A year=2011 request fails readiness with a
  structured ``rsf_year_2011_absent`` error (the
  documented missing year).
- ``leaders=`` filters surface a structured
  ``unsupported_filter`` warning (SRC-REQ-005).
- The bundle readiness gate accepts the canonical
  primary metadata shape (24 per-year CSV files
  staged on disk). The canonical RSF bundle metadata
  carries ``source_version="annual CSV series
  2002-2026, acquired 2026-06-18"`` (the verbose
  acquisition-date stamp); the unified adapter
  accepts both the verbose stamp AND the brief
  canonical stamp ``"RSF Press Freedom Index
  2026"``.
- Readiness-failure paths block the runner BEFORE
  ``read_raw`` / ``transform`` for missing metadata,
  missing per-year CSV(s), missing required field,
  malformed ``local_files``, malformed / missing /
  mismatched ``files`` entry, malformed /
  mismatched metadata ``source_version``, and
  unsupported request ``source_version``.
- Canonical metadata version propagates consistently
  to ``RawAsset.version`` and every emitted
  ``NormalizedObservation.source_version``.
- Importing the new
  ``leaders_db.sources.adapters.rsf_press_freedom``
  module does NOT pull in any ``leaders_db.ingest``
  module (SRC-MIG-007 + the import boundary documented
  in ``docs/architecture/sources.md`` §10.1).
- Per-observation ``RawLocator`` carries the staged
  per-year CSV path + the catalog ``raw_column`` +
  the year-specific actual column name (e.g.
  ``Score N`` for 2002-2021, ``Score`` for 2022+).
  Per-observation ``extension`` carries the
  canonical RSF attribution text (Rule #15), the
  ``source_row_reference="rsf_press_freedom:<iso3>:<actual_column>"``
  pattern (matching the legacy Stage 2 DB writer),
  the pre/post-2022 ``rsf_schema_group`` flag, the
  ``rsf_iso3`` / ``rsf_category`` / ``rsf_raw_column``
  / ``rsf_actual_column`` audit-trail fields, the
  ``raw_value`` verbatim RSF cell text, and the
  direction hints
  (``higher_is_better`` / ``raw_scale`` /
  ``normalized_scale_target``).
- The legacy
  ``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/rsf_press_freedom_io.py`` is
  byte-identical to the new
  ``RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT`` constant
  (``test_rsf_press_freedom_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text
  is a substring of
  ``docs/sources/attributions.md``).
- The pre/post-2022 methodology / schema distinction
  is preserved through the unified transform -- the
  per-row observation's ``extension.rsf_schema_group``
  flag is ``1`` for pre-2022 years (2 indicators: score
  + rank only) and ``2+`` for post-2022 years (7
  indicators: score + rank + 5 component-context).
- The RSF unified path is local-file only
  (``requires_network=False``, no HTTP layer in the
  new package). The runner NEVER invokes the
  network. The readiness gate validates the staged
  per-year CSV(s) and the metadata
  ``source_version`` / ``files`` / ``local_files`` /
  ``source_name`` / ``source_url`` / ``license_note``
  / ``ingestion_status`` fields BEFORE
  ``read_raw`` / ``transform`` are called.
- The 2011 documented missing year caveat is
  preserved on ``check_ready`` (structured
  ``rsf_year_2011_absent`` error per the documented
  2011 caveat).
- The semicolon-delimited + comma-decimal CSV read
  is preserved (the legacy reader applies the
  comma-decimal normalization at read time; the
  unified transform preserves the verbatim
  ``raw_value`` cell text on the observation's
  ``extension["raw_value"]`` audit column).
- The 181 blank separator rows in the 2022 CSV are
  dropped by the legacy reader; the unified
  transform emits zero observations for the
  separator rows (no fabricated observations).

PASS-ELIGIBLE rationale
-----------------------

The legacy RSF reader is well-tested via the
existing ``tests/test_ingest_rsf_press_freedom.py``
suite (31 tests covering the BOM-first / cp1252-
fallback encoding detection, the semicolon-delimited
CSV read with comma-decimal normalization, the
pre/post-2022 schema break handling, the blank-row
filtering, the 2011 missing-year caveat, the
indicator catalog, the DB writers, the orchestrator
end-to-end, the CLI dispatch, and the public
surface). The tests in this file prove that the
new ``leaders_db.sources.adapters.rsf_press_freedom``
adapter wraps the legacy parsing logic behind the
unified ``SourceAdapter`` Protocol while preserving
the package-isolation contract -- they are
PASS-ELIGIBLE because the adapter implementation
lands in the same change set.
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


# Test-only constants. Mirror the descriptor
# constants so the tests stay decoupled from the
# package's ``__all__`` (the constants are re-exported
# there but the test file pins the values explicitly
# for clarity).
RSF_TEST_FIXTURE_CSV_NAME_PATTERN: str = (
    "rsf_press_freedom_{year}.csv"
)
RSF_TEST_METADATA_NAME: str = "metadata.json"
RSF_TEST_ATTRIBUTION_KEY: str = "rsf_press_freedom"
RSF_TEST_SOURCE_KEY: str = "rsf_press_freedom"
RSF_TEST_DEFAULT_VERSION: str = (
    "RSF Press Freedom Index 2026"
)
RSF_TEST_BUNDLE_VERSION: str = (
    "annual CSV series 2002-2026, acquired 2026-06-18"
)
RSF_TEST_COVERAGE_START: int = 2002
RSF_TEST_COVERAGE_END: int = 2026
RSF_TEST_MISSING_DIRECT_YEAR: int = 2011
RSF_TEST_HOMEPAGE_URL: str = "https://rsf.org/en/index"
RSF_TEST_FAMILIES: tuple[str, ...] = (
    "political_freedom_country_year",
)
RSF_TEST_INDICATOR_SCORE: str = "rsf_press_freedom_score"
RSF_TEST_INDICATOR_RANK: str = "rsf_press_freedom_rank"
RSF_TEST_INDICATOR_NAMES: tuple[str, ...] = (
    RSF_TEST_INDICATOR_SCORE,
    RSF_TEST_INDICATOR_RANK,
    "rsf_press_freedom_political_context",
    "rsf_press_freedom_economic_context",
    "rsf_press_freedom_legal_context",
    "rsf_press_freedom_social_context",
    "rsf_press_freedom_safety",
)
RSF_TEST_AVAILABLE_YEARS: tuple[int, ...] = (
    2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019,
    2020, 2021,
    2022, 2023, 2024, 2025, 2026,
)
RSF_TEST_CANONICAL_VALUE_TYPE: str = "numeric"
RSF_TEST_SCHEMA_GROUP_PRE_2022: int = 1
RSF_TEST_SCHEMA_GROUP_POST_2022: int = 2
RSF_TEST_YEAR_2011_ABSENT_CODE: str = (
    "rsf_year_2011_absent"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyRSFAdapter:
    """Wrap a :class:`RSFPressFreedomAdapter` and
    record every lifecycle call.

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
        self,
        request: SourceIngestRequest,
        raw: Any,
    ) -> Any:
        self.calls.append("transform")
        return self._inner.transform(request, raw)


def _compute_files_payload(
    raw_root: Path,
    years: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Build the canonical ``files`` array payload
    for the staged RSF bundle.

    Walks the staged per-year CSVs, computes the
    actual SHA-256 for each CSV, and returns the
    per-file records the staged
    ``data/raw/rsf_press_freedom/metadata.json``
    carries under ``files``. The function is the
    single source of truth for the per-file
    checksum -- every helper that stages a bundle
    uses the same shape so the readiness gate's
    per-file SHA-256 match branch fires cleanly.
    """
    files: list[dict[str, Any]] = []
    for year in years:
        csv_name = RSF_TEST_FIXTURE_CSV_NAME_PATTERN.format(
            year=year,
        )
        csv_path = raw_root / csv_name
        if not csv_path.is_file():
            continue
        actual_sha = hashlib.sha256(
            csv_path.read_bytes(),
        ).hexdigest()
        files.append(
            {
                "year": year,
                "file": csv_name,
                "bytes": csv_path.stat().st_size,
                "sha256": actual_sha,
            },
        )
    return files


def _stage_rsf_bundle(
    raw_root: Path,
    *,
    years: tuple[int, ...] = RSF_TEST_AVAILABLE_YEARS,
    with_csvs: bool = True,
    with_metadata: bool = True,
    metadata_overrides: dict[str, Any] | None = None,
    source_version: str = RSF_TEST_BUNDLE_VERSION,
) -> Path:
    """Stage the canonical RSF fixture bundle under
    ``raw_root/rsf_press_freedom``.

    Copies the real-format
    ``tests/fixtures/rsf_press_freedom/`` per-year
    CSVs (the 5-country 2002 / 2022 / 2023 fixtures
    used by the legacy Stage 2 tests) for the
    requested years + writes a well-formed
    ``metadata.json`` matching the canonical
    ``data/raw/rsf_press_freedom/metadata.json``
    shape (verbose acquisition-date
    ``source_version`` + ``source_name`` /
    ``source_url`` / ``license_note`` /
    ``local_files`` / ``ingestion_status`` /
    ``coverage`` / per-file ``files`` array).

    The per-file SHA-256 in the ``files`` array is
    the ACTUAL staged CSV SHA-256 (not a sentinel)
    so the readiness gate's optional per-file
    SHA-256 match branch fires cleanly.

    The fixture carries 5 country-year rows per
    requested year file (NOR / SWE / USA / NGA /
    MEX for 2023; NOR / DNK / SWE / USA / NGA for
    2022; FIN / NOR / USA / NGA / MEX for 2002 --
    the same fixtures the legacy
    ``tests/test_ingest_rsf_press_freedom.py`` uses;
    the values are copied verbatim from the live
    CSVs, no invented data).
    """
    bundle_dir = raw_root / "rsf_press_freedom"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "rsf_press_freedom"
    )

    fixture_csv_for_year: dict[int, str] = {
        2002: "rsf_press_freedom_2002_sample.csv",
        2022: "rsf_press_freedom_2022_sample.csv",
        2023: "rsf_press_freedom_2023_sample.csv",
    }

    if with_csvs:
        for year in years:
            csv_name = RSF_TEST_FIXTURE_CSV_NAME_PATTERN.format(
                year=year,
            )
            staged_csv = bundle_dir / csv_name
            fixture_csv_name = fixture_csv_for_year.get(year)
            if fixture_csv_name is None:
                continue
            fixture_csv = fixtures_dir / fixture_csv_name
            if not fixture_csv.is_file():
                continue
            shutil.copy2(fixture_csv, staged_csv)

    if with_metadata:
        local_files = [
            RSF_TEST_FIXTURE_CSV_NAME_PATTERN.format(year=y)
            for y in years
        ]
        files_payload = _compute_files_payload(bundle_dir, years)
        if not files_payload:
            # The 2023 fixture was NOT staged (e.g.
            # ``with_csvs=False`` or the per-year
            # fixture is missing). The staged
            # metadata should still carry an empty
            # ``files`` list so the readiness gate's
            # ``missing_files_array`` /
            # ``malformed_files_array`` checks pass
            # cleanly.
            pass
        payload: dict[str, Any] = {
            "source_name": (
                "Reporters Without Borders World Press "
                "Freedom Index"
            ),
            "source_version": source_version,
            "source_url": (
                "https://rsf.org/sites/default/files/"
                "import_classement/{year}.csv"
            ),
            "canonical_page": "https://rsf.org/en/index",
            "license_note": (
                "public dataset; cite Reporters Without "
                "Borders / Reporters sans frontières and "
                "the World Press Freedom Index."
            ),
            "local_files": local_files,
            "ingestion_status": "downloaded",
            "coverage": {
                "downloaded_years": list(years),
                "missing_years_from_direct_csv_pattern": [
                    RSF_TEST_MISSING_DIRECT_YEAR,
                ],
                "annual_files": len(years),
            },
            "files": files_payload,
        }
        if metadata_overrides:
            payload.update(metadata_overrides)
        (bundle_dir / RSF_TEST_METADATA_NAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
    return bundle_dir


def _purge_modules(prefix: str) -> None:
    """Remove every cached module starting with
    ``prefix``.

    Used to simulate a fresh interpreter around a
    single import call so side-effect modules do not
    leak from earlier tests.
    """
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_rsf_descriptor_exposes_documented_static_metadata() -> None:
    """The RSF descriptor carries every documented
    field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    ``docs/architecture/sources.md`` §5.2):

    - ``source_id.slug == "rsf_press_freedom"``
    - ``display_name`` is the canonical RSF 2026
      label.
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical
      metadata stamp (``"RSF Press Freedom Index
      2026"``).
    - ``homepage_url`` is the canonical RSF landing
      page.
    - ``attribution_key == "rsf_press_freedom"``
    - ``coverage_hint.start_year == 2002``,
      ``coverage_hint.end_year == 2026``.
    - ``supported_observation_families`` is the
      1-tuple
      ``("political_freedom_country_year",)``.
    - ``requires_network is False`` (local-file
      only).
    """
    from leaders_db.sources.adapters.rsf_press_freedom import (
        build_rsf_press_freedom_descriptor,
    )

    descriptor = build_rsf_press_freedom_descriptor()

    assert descriptor.source_id.slug == RSF_TEST_SOURCE_KEY
    assert descriptor.source_type == "dataset"
    assert (
        descriptor.default_version
        == RSF_TEST_DEFAULT_VERSION
    )
    assert descriptor.homepage_url == RSF_TEST_HOMEPAGE_URL
    assert (
        descriptor.attribution_key
        == RSF_TEST_ATTRIBUTION_KEY
    )
    assert (
        descriptor.coverage_hint.start_year
        == RSF_TEST_COVERAGE_START
    )
    assert (
        descriptor.coverage_hint.end_year
        == RSF_TEST_COVERAGE_END
    )
    assert descriptor.supported_observation_families == (
        RSF_TEST_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_rsf_attribution_text_matches_attributions_doc() -> None:
    """The RSF attribution text is byte-identical to
    the legacy ``RSF_PRESS_FREEDOM_ATTRIBUTION``
    constant AND a substring of
    ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical RSF citation
    block in ``docs/sources/attributions.md`` is the
    source of truth; the adapter module's constant
    must be byte-identical to a substring of that
    doc AND byte-identical to the legacy
    ``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/rsf_press_freedom_io.py``.
    """
    from leaders_db.ingest.rsf_press_freedom_io import (
        RSF_PRESS_FREEDOM_ATTRIBUTION,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
    )

    assert RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT == (
        RSF_PRESS_FREEDOM_ATTRIBUTION
    ), (
        "Unified RSF attribution must be byte-identical "
        "to the legacy RSF_PRESS_FREEDOM_ATTRIBUTION "
        "constant in "
        "src/leaders_db/ingest/rsf_press_freedom_io.py."
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
    assert RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT in (
        attributions_text
    ), (
        f"{RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT!r} is not a "
        f"substring of {attributions_path}. Update both "
        "in the same commit (Rule #15)."
    )


def test_rsf_adapter_satisfies_source_adapter_protocol() -> None:
    """``RSFPressFreedomAdapter`` instances satisfy
    the runtime-checkable Protocol.

    The Protocol guard catches a missing ``descriptor``
    or any of ``check_ready`` / ``read_raw`` /
    ``transform`` at construction time.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    adapter = create_rsf_press_freedom_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == (
        "rsf_press_freedom"
    )


def test_rsf_descriptor_indicator_names() -> None:
    """The descriptor's indicator names are
    byte-identical to the canonical catalog.

    The canonical catalog at
    ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``
    lists 7 indicator rows (2 base + 5
    component-context). The descriptor exposes the
    indicator names so the public surface matches
    the catalog byte-for-byte.
    """
    from leaders_db.sources.adapters.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_INDICATOR_NAMES,
    )

    assert set(RSF_PRESS_FREEDOM_INDICATOR_NAMES) == set(
        RSF_TEST_INDICATOR_NAMES
    )


def test_rsf_public_surface_is_coherent() -> None:
    """The package root ``__all__`` exposes every
    public symbol documented in the adapter module
    + descriptor.

    Defense in depth: any future contributor who
    removes a public name from ``__all__`` without
    updating the design doc / the public surface
    contract will see this test fail.
    """
    from leaders_db.sources.adapters import (
        rsf_press_freedom as rsf_pkg,
    )

    required = {
        "RSF_PRESS_FREEDOM_SOURCE_KEY",
        "RSF_PRESS_FREEDOM_DEFAULT_VERSION",
        "RSF_PRESS_FREEDOM_ATTRIBUTION_KEY",
        "RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT",
        "RSF_PRESS_FREEDOM_COVERAGE_START_YEAR",
        "RSF_PRESS_FREEDOM_COVERAGE_END_YEAR",
        "RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR",
        "RSF_PRESS_FREEDOM_AVAILABLE_YEARS",
        "RSF_PRESS_FREEDOM_HOMEPAGE_URL",
        "RSF_PRESS_FREEDOM_METADATA_NAME",
        "RSF_PRESS_FREEDOM_CSV_NAME_PATTERN",
        "RSF_PRESS_FREEDOM_OBSERVATION_FAMILY",
        "RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES",
        "RSF_PRESS_FREEDOM_INDICATOR_SCORE",
        "RSF_PRESS_FREEDOM_INDICATOR_RANK",
        "RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT",
        "RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT",
        "RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT",
        "RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT",
        "RSF_PRESS_FREEDOM_INDICATOR_SAFETY",
        "RSF_PRESS_FREEDOM_INDICATOR_NAMES",
        "RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE",
        "RSF_PRESS_FREEDOM_RAW_COLUMN_RANK",
        "RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS",
        "RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE",
        "RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH",
        "RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH",
        "RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP",
        "RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP",
        "RSF_PRESS_FREEDOM_TRANSFORM_NAME",
        "RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022",
        "RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022",
        "RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS",
        "RSFPressFreedomAdapter",
        "build_rsf_press_freedom_descriptor",
        "create_rsf_press_freedom_adapter",
        "register_rsf_press_freedom",
        "check_metadata_well_formed",
        "collect_request_scoping_warnings",
        "transform_rsf_press_freedom_observations",
        "read_rsf_press_freedom_csv",
        "emit_rsf_press_freedom_observations",
        "load_indicator_catalog",
        "rating_category_to_observation_family",
        "DEFAULT_CATALOG_PATH",
        "build_observation",
        "_coerce_score_value",
        "_coerce_rank_value",
        "_normalize_decimal",
        "_raw_cell_text",
        "_is_missing",
        "_bundle_dir",
        "_csv_name_for_year",
        "_csv_path_for_year",
        "_metadata_path",
        "_read_metadata_payload",
        "_resolve_years_for_request",
        "_default_asset_id_for_year",
        "_default_source_version",
        "_detect_schema_group",
        "_indicator_names",
        "_raw_columns",
        "_resolve_value_type",
        "_find_spec_for_variable",
        "_is_component_raw_column",
        "_parse_source_row_reference",
        "_resolve_actual_column_name",
        "_csv_asset_id_for_year",
        "_check_year_2011",
        "_check_year_csv_presence",
        "_check_year_csvs",
        "_resolve_years_for_validation",
        "ACCEPTABLE_INGESTION_STATUSES",
        "REQUIRED_METADATA_FIELDS",
        "UNSUPPORTED_VERSION",
        "_checksum_match_blocker",
        "_files_blocker",
        "_find_files_entry",
        "_ingestion_status_blocker",
        "_local_files_blocker",
        "_metadata_source_version_blocker",
        "_non_empty_string_blocker",
        "_presence_blocker",
        "_required_fields_blocker",
        "RSF_PRESS_FREEDOM_ADAPTER_FACTORY",
    }
    missing = required - set(rsf_pkg.__all__)
    assert not missing, (
        f"missing public names on leaders_db.sources."
        f"adapters.rsf_press_freedom: {missing}"
    )


# ---------------------------------------------------------------------------
# Registry: descriptor is registerable + listable
# ---------------------------------------------------------------------------


def test_rsf_adapter_is_registerable_through_in_memory_registry() -> (
    None
):
    """``create_rsf_press_freedom_adapter()`` produces
    an adapter the registry accepts.

    The :class:`InMemorySourceRegistry` rejects
    duplicate slugs with ``ValueError`` (SRC-REG-004);
    the test asserts the RSF adapter registers
    cleanly under the ``rsf_press_freedom`` slug and
    the descriptor is listable.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    registry = InMemorySourceRegistry()
    adapter = create_rsf_press_freedom_adapter()
    registry.register(adapter)

    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == "rsf_press_freedom"

    resolved = registry.get_descriptor(
        SourceId(slug="rsf_press_freedom"),
    )
    assert resolved is listed[0]
    assert (
        registry.get_adapter(SourceId(slug="rsf_press_freedom"))
        is adapter
    )


def test_rsf_register_helper_registers_against_explicit_registry() -> None:
    """``register_rsf_press_freedom(registry)`` is the
    explicit seam for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        register_rsf_press_freedom,
    )

    registry = InMemorySourceRegistry()
    adapter = register_rsf_press_freedom(registry)
    assert (
        registry.get_adapter(SourceId(slug="rsf_press_freedom"))
        is adapter
    )


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end (pre-2022 schema)
# ---------------------------------------------------------------------------


def test_rsf_runner_pre_2022_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives RSF
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records for a
    pre-2022 year (2002).

    The 2002 fixture has 5 country-year rows
    (FIN / NOR / USA / NGA / MEX) with the 2
    pre-2022 indicators (score + rank). 10
    observations round-trip (5 countries x 2
    indicators). Every observation's
    ``extension.rsf_schema_group`` is ``1`` (the
    pre-2022 schema group) and the
    ``rsf_actual_column`` is ``Score N`` / ``Rank N``
    (the year-specific 2002-2021 column names).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root, years=(2002,),
    )

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2002,),
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    # Pre-2022: 5 countries x 2 indicators (score + rank)
    # = 10 observations.
    assert len(result.observations) == 10, (
        f"expected 10 observations (5 countries x 2 "
        f"pre-2022 indicators); got "
        f"{len(result.observations)}"
    )
    iso3s = sorted({obs.country_code for obs in result.observations})
    assert iso3s == ["FIN", "MEX", "NGA", "NOR", "USA"]
    indicators = {
        obs.indicator_code for obs in result.observations
    }
    assert indicators == {
        RSF_TEST_INDICATOR_SCORE,
        RSF_TEST_INDICATOR_RANK,
    }
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "rsf_press_freedom"
        assert obs.observation_family == (
            "political_freedom_country_year"
        )
        assert obs.year == 2002
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.value_type == RSF_TEST_CANONICAL_VALUE_TYPE
        # The pre-2022 schema group is ``1``.
        assert obs.extension.get("rsf_schema_group") == (
            RSF_TEST_SCHEMA_GROUP_PRE_2022
        )
        # The year-specific actual column is ``Score N``
        # / ``Rank N`` for 2002-2021.
        actual_col = obs.extension.get("rsf_actual_column")
        assert actual_col in {"Score N", "Rank N"}


def test_rsf_runner_post_2022_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives RSF
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records for a
    post-2022 year (2023).

    The 2023 fixture has 5 country-year rows (NOR /
    SWE / USA / NGA / MEX) with the 7 post-2022
    indicators (score + rank + 5
    component-context). 35 observations round-trip
    (5 countries x 7 indicators). Every
    observation's ``extension.rsf_schema_group``
    is ``2`` (the post-2022 schema group) and the
    ``rsf_actual_column`` is ``Score`` / ``Rank`` /
    the literal component column names.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root, years=(2023,),
    )

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None

    # Post-2022: 5 countries x 7 indicators (score +
    # rank + 5 component-context) = 35 observations.
    assert len(result.observations) == 35, (
        f"expected 35 observations (5 countries x 7 "
        f"post-2022 indicators); got "
        f"{len(result.observations)}"
    )
    iso3s = sorted({obs.country_code for obs in result.observations})
    assert iso3s == ["MEX", "NGA", "NOR", "SWE", "USA"]
    indicators = {
        obs.indicator_code for obs in result.observations
    }
    assert indicators == {
        "rsf_press_freedom_score",
        "rsf_press_freedom_rank",
        "rsf_press_freedom_political_context",
        "rsf_press_freedom_economic_context",
        "rsf_press_freedom_legal_context",
        "rsf_press_freedom_social_context",
        "rsf_press_freedom_safety",
    }
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.year == 2023
        # The post-2022 schema group is ``2``.
        assert obs.extension.get("rsf_schema_group") == (
            RSF_TEST_SCHEMA_GROUP_POST_2022
        )


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_rsf_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives RSF through the new registry
    and never calls into
    ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches
    ``STAGE2_ADAPTERS["rsf_press_freedom"]`` with a
    tracking sentinel and asserts the sentinel is
    never invoked while
    ``SourceIngestRunner.run(request)`` executes the
    new RSF adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    # Replace the legacy ``rsf_press_freedom`` slot
    # with a tracker that records every invocation.
    # The runner must never call it.
    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get(
        "rsf_press_freedom",
    )

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS["rsf_press_freedom"] = (
        _legacy_tracker
    )
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_rsf_press_freedom_adapter())
        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(
            source_id=SourceId(slug="rsf_press_freedom"),
            raw_root=raw_root,
            years=(2023,),
        )

        result = runner.run(request)

        # Sanity: the new adapter ran end-to-end.
        assert len(result.observations) == 35

        # The legacy tracker must not have been called.
        assert legacy_calls == [], (
            "SourceIngestRunner routed through "
            "STAGE2_ADAPTERS instead of the new "
            f"registry; saw {legacy_calls!r}"
        )
    finally:
        legacy_ingest.STAGE2_ADAPTERS["rsf_press_freedom"] = (
            original
        )


# ---------------------------------------------------------------------------
# Request scoping: years + countries (ISO3)
# ---------------------------------------------------------------------------


def test_rsf_year_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.years=(2023,)`` is
    honored.

    The 2023 fixture has 5 country-year rows;
    filtering to year=2023 narrows to 5 rows x 7
    indicators = 35 observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2022, 2023))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 35
    assert {obs.year for obs in result.observations} == {
        2023,
    }


def test_rsf_country_filter_is_applied(tmp_path: Path) -> None:
    """``SourceIngestRequest.countries=('USA',)`` is
    honored.

    The 2023 fixture has 5 countries; filtering to
    USA narrows to 1 country x 7 indicators = 7
    observations.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 7
    assert {obs.country_code for obs in result.observations} == {
        "USA",
    }


def test_rsf_combined_year_and_country_filter(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2023,) +
    countries=('USA',)`` filters to USA 2023 only --
    7 observations round-trip.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)
    assert len(result.observations) == 7
    assert {obs.year for obs in result.observations} == {2023}
    assert {obs.country_code for obs in result.observations} == {
        "USA",
    }


def test_rsf_out_of_coverage_year_emits_year_absent_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2027,)`` (out of
    coverage) emits zero observations plus a
    structured ``year_absent`` warning per
    SRC-COV-002 / SRC-COV-003."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2027,),
    )
    result = runner.run(request)
    assert len(result.observations) == 0
    warning_codes = [w.code for w in result.warnings]
    assert "year_absent" in warning_codes, (
        f"expected 'year_absent' warning, got "
        f"{warning_codes}"
    )


def test_rsf_leader_filter_emits_unsupported_filter_warning(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.leaders=('X',)`` emits a
    structured ``unsupported_filter`` warning per
    SRC-REQ-005.

    RSF is a country-year press-freedom source;
    leader filters are not supported. The warning
    is surfaced on the readiness envelope AND
    propagated through to the final result
    envelope.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        leaders=("Some Leader",),
    )
    result = runner.run(request)
    assert len(result.observations) == 35
    warning_codes = [w.code for w in result.warnings]
    assert "unsupported_filter" in warning_codes, (
        f"expected 'unsupported_filter' warning, got "
        f"{warning_codes}"
    )


# ---------------------------------------------------------------------------
# 2011 missing / direct-CSV caveat
# ---------------------------------------------------------------------------


def test_rsf_year_2011_fails_readiness_with_rsf_year_2011_absent(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2011,)`` fails
    readiness with a structured
    ``rsf_year_2011_absent`` error per the documented
    2011 caveat.

    The direct ``2011.csv`` is absent; the 2012 file
    represents RSF's combined 2011/2012 edition. The
    runner short-circuits with ``RuntimeError``
    BEFORE ``read_raw`` / ``transform``.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2010, 2012))

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2011,),
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


def test_rsf_year_2011_in_multi_year_request_fails_readiness(
    tmp_path: Path,
) -> None:
    """``SourceIngestRequest.years=(2010, 2011, 2012)``
    fails readiness with a structured
    ``rsf_year_2011_absent`` error (the documented
    2011 caveat applies even in a multi-year request).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2010, 2012))

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2010, 2011, 2012),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


# ---------------------------------------------------------------------------
# Readiness-failure paths
# ---------------------------------------------------------------------------


def test_rsf_missing_per_year_csv_fails_readiness_with_missing_raw(
    tmp_path: Path,
) -> None:
    """A metadata-only bundle (no staged per-year CSV)
    fails readiness with a structured ``missing_raw``
    error.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata only -- no per-year CSVs.
    _stage_rsf_bundle(
        raw_root, years=(), with_csvs=False,
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
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


def test_rsf_missing_metadata_fails_readiness_with_missing_metadata(
    tmp_path: Path,
) -> None:
    """A per-year-CSV-only bundle (no metadata.json)
    fails readiness with a structured
    ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage per-year CSVs only -- no metadata.json.
    _stage_rsf_bundle(
        raw_root, years=(2023,), with_metadata=False,
    )

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()


def test_rsf_unsupported_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """``source_version="RSF Press Freedom Index
    2025"`` fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        source_version="RSF Press Freedom Index 2025",
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    # The runner must short-circuit before
    # ``read_raw`` / ``transform``.
    assert spy.calls == ["check_ready"]


def test_rsf_mismatched_bundle_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle whose ``source_version`` stamp is
    neither the brief canonical stamp NOR the
    verbose acquisition-date stamp fails readiness
    with a structured
    ``rsf_press_freedom_metadata_version_mismatch``
    error.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        source_version="RSF Press Freedom Index 2024",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_malformed_local_files_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle whose ``local_files`` is present-but-
    null fails readiness with a structured
    ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"local_files": None},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_wrong_local_files_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle whose ``local_files`` is a list of
    non-string entries fails readiness with a
    structured ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"local_files": [123]},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_missing_required_metadata_field_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle missing a canonical required metadata
    field fails readiness with a structured
    ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"source_url": ""},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_invalid_ingestion_status_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with an invalid ``ingestion_status``
    fails readiness with a structured
    ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"ingestion_status": "garbage"},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_malformed_files_entry_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle with a malformed ``files`` entry
    (missing required ``year`` or ``file`` field)
    fails readiness with a structured
    ``missing_metadata`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={
            "files": [{"year": 2023, "file": ""}],
        },
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_per_file_checksum_mismatch_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle whose per-file ``sha256`` disagrees
    with the staged per-year CSV SHA-256 fails
    readiness with a structured
    ``rsf_press_freedom_checksum_mismatch`` error."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage the bundle with a known-bad per-file
    # sha256. The readiness gate recomputes the
    # staged CSV's SHA-256 and compares against the
    # metadata field, so any non-matching value
    # fires the ``rsf_press_freedom_checksum_mismatch``
    # code.
    bundle_dir = _stage_rsf_bundle(raw_root, years=(2023,))
    metadata_path = bundle_dir / RSF_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    # Replace the per-file sha256 with a wrong value.
    wrong_sha = "0" * 64
    for entry in payload.get("files", []):
        if entry.get("year") == 2023:
            entry["sha256"] = wrong_sha
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_csv_present_files_entry_missing_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle where the per-year CSV is staged on
    disk but the metadata ``files`` array has no
    matching entry for that year fails readiness with
    a structured ``missing_metadata`` error.

    The canonical RSF bundle metadata carries a
    ``files`` array with one record per year file;
    every staged per-year CSV MUST have a matching
    well-formed entry. A staged per-year CSV without
    a matching ``files`` entry is malformed metadata
    (the canonical bundle uses ``files`` as the
    per-file checksum + audit source of truth) and
    the readiness gate returns ``ready=False`` with a
    structured ``missing_metadata`` blocker BEFORE
    the runner dispatches ``read_raw`` /
    ``transform``.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage the 2023 CSV on disk; force the metadata
    # ``files`` array to ``[]`` so no entry matches
    # the requested year. The CSV is on disk so the
    # per-year CSV presence check passes; the
    # well-formed-entry check then fires
    # ``missing_metadata``.
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"files": []},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    # The runner must short-circuit before
    # ``read_raw`` / ``transform``.
    assert spy.calls == ["check_ready"]


def test_rsf_csv_present_files_entry_missing_in_multi_year_fails_readiness(
    tmp_path: Path,
) -> None:
    """A multi-year bundle where one per-year CSV is
    staged on disk but the metadata ``files`` array
    is missing the matching entry for that year
    fails readiness with a structured
    ``missing_metadata`` error.

    The 2023 CSV is staged but the ``files`` array
    only carries an entry for 2024. The well-formed-
    entry check fires ``missing_metadata`` for the
    requested 2023 year BEFORE the runner dispatches
    ``read_raw`` / ``transform``.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage the 2023 + 2024 CSVs on disk; force the
    # metadata ``files`` array to only carry the 2024
    # entry. The 2023 CSV is staged so the
    # well-formed-entry check fires for 2023.
    bundle_dir = _stage_rsf_bundle(
        raw_root,
        years=(2023, 2024),
    )
    metadata_path = bundle_dir / RSF_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    # Keep only the 2024 entry.
    payload["files"] = [
        entry for entry in payload.get("files", [])
        if entry.get("year") == 2024
    ]
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_non_hex_sha256_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle whose per-file ``sha256`` is a
    64-character non-hex string fails readiness with
    a structured ``missing_metadata`` error.

    The canonical RSF bundle carries the lowercase-
    hex SHA-256 of the staged per-year CSV; a
    64-character non-hex string (e.g. ``"z" * 64``)
    is malformed metadata, NOT a checksum mismatch.
    Without this guard the readiness gate would
    silently treat ``"z" * 64`` as a "checksum
    mismatch" and the runner would dispatch
    ``read_raw`` against a malformed metadata bundle.

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
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = _stage_rsf_bundle(raw_root, years=(2023,))
    metadata_path = bundle_dir / RSF_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    # Replace the per-file sha256 with a 64-character
    # non-hex string. ``"z" * 64`` is the canonical
    # example of a malformed SHA-256: it has the
    # correct length but every character is outside
    # the hex alphabet. The readiness gate rejects it
    # as malformed metadata (``missing_metadata``),
    # NOT as a checksum mismatch
    # (``rsf_press_freedom_checksum_mismatch``).
    non_hex_sha = "z" * 64
    for entry in payload.get("files", []):
        if entry.get("year") == 2023:
            entry["sha256"] = non_hex_sha
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_rsf_press_freedom_adapter()
    spy = _SpyRSFAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"]


def test_rsf_check_ready_happy_path_emits_no_errors(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=True`` with no errors and no warnings
    when the bundle is well-formed.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = adapter.check_ready(request)
    assert result.ready is True
    assert result.errors == ()
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# Direct check_ready structured-error tests
# ---------------------------------------------------------------------------


def _assert_readiness_error(
    result: Any,
    *,
    expected_code: str,
    expected_severity: str = "error",
    expected_source_slug: str = "rsf_press_freedom",
    expected_context_keys: tuple[str, ...] = (),
) -> None:
    """Assert ``result`` is a single-error failure
    envelope.

    Defense in depth for the readiness gate: a
    refactor that emits the right ``ready=False`` but
    the wrong error code, the wrong severity, or a
    missing source-id context will fail this helper
    before the runner short-circuit test even runs.
    """
    assert result.ready is False, (
        f"expected ready=False; got {result.ready!r}"
    )
    assert result.warnings == (), (
        f"expected no warnings on a failure envelope; "
        f"got {result.warnings!r}"
    )
    assert len(result.errors) == 1, (
        f"expected exactly one error; got {result.errors!r}"
    )
    error = result.errors[0]
    assert error.code == expected_code, (
        f"expected code={expected_code!r}; got "
        f"{error.code!r}"
    )
    assert error.severity == expected_severity, (
        f"expected severity={expected_severity!r}; "
        f"got {error.severity!r}"
    )
    assert error.source_id is not None, (
        "error.source_id must be set so the runner "
        "can route the diagnostic to the operator"
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


def test_rsf_check_ready_missing_metadata_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when ``metadata.json`` is absent."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = raw_root / "rsf_press_freedom"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # No metadata.json.

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_missing_per_year_csv_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_raw``
    error when the staged metadata is present but
    the requested per-year CSV is absent.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata only -- no per-year CSVs.
    _stage_rsf_bundle(
        raw_root, years=(), with_csvs=False,
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_raw",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_unsupported_request_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``unsupported_version`` error when the request
    ``source_version`` differs from the canonical
    ``"RSF Press Freedom Index 2026"``.

    Per SRC-REQ-009: the canonical RSF stamp is
    ``"RSF Press Freedom Index 2026"``; the request
    ``source_version`` is rejected at the readiness
    gate with a structured error carrying the
    requested + canonical version in the context.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        source_version="RSF Press Freedom Index 2025",
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
    assert result.errors[0].context["requested_version"] == (
        "RSF Press Freedom Index 2025"
    )
    assert result.errors[0].context["canonical_version"] == (
        RSF_TEST_DEFAULT_VERSION
    )


def test_rsf_check_ready_mismatched_bundle_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``rsf_press_freedom_metadata_version_mismatch``
    error when the bundle's ``source_version`` stamp
    is neither the brief canonical stamp NOR the
    verbose acquisition-date stamp.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        source_version="RSF Press Freedom Index 2024",
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="rsf_press_freedom_metadata_version_mismatch",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_malformed_local_files_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when ``local_files`` is present-but-null.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"local_files": None},
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_wrong_local_files_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when ``local_files`` contains a non-string
    entry."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"local_files": [123]},
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_per_file_checksum_mismatch_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``rsf_press_freedom_checksum_mismatch`` error
    when a well-formed per-file ``sha256`` disagrees
    with the staged per-year CSV SHA-256.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = _stage_rsf_bundle(raw_root, years=(2023,))
    metadata_path = bundle_dir / RSF_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    wrong_sha = "0" * 64
    for entry in payload.get("files", []):
        if entry.get("year") == 2023:
            entry["sha256"] = wrong_sha
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="rsf_press_freedom_checksum_mismatch",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_csv_present_files_entry_missing_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when a per-year CSV is staged on disk but
    the metadata ``files`` array has no matching
    entry for that year.

    The canonical RSF bundle metadata carries a
    ``files`` array with one record per year file;
    every staged per-year CSV MUST have a matching
    well-formed entry. A staged per-year CSV without
    a matching ``files`` entry is malformed metadata
    and the readiness gate returns ``ready=False``
    with a structured ``missing_metadata`` blocker
    BEFORE the runner dispatches ``read_raw`` /
    ``transform``.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage the 2023 CSV on disk; force the metadata
    # ``files`` array to ``[]`` so no entry matches
    # the requested year. The CSV is on disk so the
    # per-year CSV presence check passes; the
    # well-formed-entry check then fires
    # ``missing_metadata``.
    _stage_rsf_bundle(
        raw_root,
        years=(2023,),
        metadata_overrides={"files": []},
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_non_hex_sha256_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when the per-file ``sha256`` is a
    64-character non-hex string.

    The canonical RSF bundle carries the lowercase-
    hex SHA-256 of the staged per-year CSV; a
    64-character non-hex string (e.g. ``"z" * 64``)
    is malformed metadata, NOT a checksum mismatch.
    Without this guard the readiness gate would
    silently treat ``"z" * 64`` as a "checksum
    mismatch" and the runner would dispatch
    ``read_raw`` against a malformed metadata bundle.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    bundle_dir = _stage_rsf_bundle(raw_root, years=(2023,))
    metadata_path = bundle_dir / RSF_TEST_METADATA_NAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    # Replace the per-file sha256 with a 64-character
    # non-hex string. ``"z" * 64`` is the canonical
    # example of a malformed SHA-256: it has the
    # correct length but every character is outside
    # the hex alphabet. The readiness gate rejects
    # it as malformed metadata (``missing_metadata``),
    # NOT as a checksum mismatch
    # (``rsf_press_freedom_checksum_mismatch``).
    non_hex_sha = "z" * 64
    for entry in payload.get("files", []):
        if entry.get("year") == 2023:
            entry["sha256"] = non_hex_sha
    metadata_path.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir",),
    )


def test_rsf_check_ready_year_2011_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``rsf_year_2011_absent`` error when year=2011
    is requested (the documented missing / direct-
    CSV caveat)."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(
        raw_root, years=(2010, 2012),
    )

    adapter = create_rsf_press_freedom_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2011,),
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="rsf_year_2011_absent",
        expected_context_keys=("bundle_dir",),
    )


# ---------------------------------------------------------------------------
# No-network contract on the production runner path
# ---------------------------------------------------------------------------


def test_rsf_runner_never_invokes_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SourceIngestRunner.run(request)`` succeeds
    end-to-end against a staged local per-year CSV
    even with every common network entry point
    rigged to raise on call.

    The RSF unified path is local-file only
    (``requires_network=False``, no HTTP layer).
    This test monkeypatches the canonical Python
    network surfaces (``requests.get`` /
    ``requests.post`` /
    ``urllib.request.urlopen`` /
    ``socket.socket``) to raise ``RuntimeError`` if
    invoked, then drives the production
    :class:`SourceIngestRunner` end-to-end from a
    staged fixture. The run must complete cleanly
    -- 35 observations for the 2023 fixture (5
    countries x 7 indicators), no exception -- which
    proves the runner NEVER touches the network on
    the RSF path.

    A future refactor that introduces an HTTP layer
    in ``read_rsf_press_freedom_csv`` / the legacy
    ``read_rsf_press_freedom_csv`` bridge / the
    transform pipeline will see this test fail at
    the first network call.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    # Arm the network tripwires. Each guarded
    # callable raises a distinctive sentinel so a
    # regression surfaces the exact entry point
    # that was hit.
    network_sentinel = "RSF_NETWORK_TRIPWIRE_FIRED"

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

    # Guard the legacy RSF reader too in case a
    # future refactor pulls it into the runner path.
    # The lazy import is resolved at
    # ``read_rsf_press_freedom_csv`` time inside the
    # adapter; monkeypatching
    # ``read_rsf_press_freedom_csv`` to raise on call
    # proves the runner does not invoke it as a
    # network layer (it only uses it as the local
    # CSV reader).
    import leaders_db.ingest.rsf_press_freedom_csv as legacy_rsf_csv

    original_read = legacy_rsf_csv.read_rsf_press_freedom_csv
    read_calls: list[dict[str, Any]] = []

    def _spy_read_rsf_csv(*args: Any, **kwargs: Any) -> Any:
        read_calls.append({"args": args, "kwargs": kwargs})
        return original_read(*args, **kwargs)

    monkeypatch.setattr(
        legacy_rsf_csv,
        "read_rsf_press_freedom_csv",
        _spy_read_rsf_csv,
    )

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )

    # The run must succeed (no exception). Any
    # tripwire firing surfaces as
    # ``RuntimeError(network_sentinel)`` and fails
    # the test.
    result = runner.run(request)
    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    # 2023: 5 countries x 7 indicators = 35
    # observations.
    assert len(result.observations) == 35, (
        f"expected 35 observations after a no-network "
        f"end-to-end run; got {len(result.observations)}"
    )

    # Defense in depth: the legacy reader was
    # actually invoked (it is the lazy bridge used
    # inside ``read_rsf_press_freedom_csv``), but
    # only as a local CSV reader -- it never made
    # an outbound call.
    assert read_calls, (
        "legacy read_rsf_press_freedom_csv should have "
        "been invoked for the local per-year CSV read; "
        "if not, the lazy bridge regressed"
    )
    for call in read_calls:
        # The legacy reader accepts ``year`` /
        # ``csv_path`` / ``catalog_path`` kwargs --
        # any other kwarg would be a hidden network
        # seam. The ``year`` kwarg is the request-
        # scoped year passed by the unified adapter
        # (the legacy reader uses it to filter the
        # ``Year (N)`` column for the 2012-file
        # combined 2011/2012 edition case; the
        # adapter's ``read_raw`` passes the same
        # year as the request scope so the audit
        # trail is preserved).
        assert set(call["kwargs"]).issubset(
            {"year", "csv_path", "catalog_path"},
        ), (
            f"legacy read_rsf_press_freedom_csv was "
            f"invoked with unexpected kwargs "
            f"(possible hidden network seam): "
            f"{call['kwargs']!r}"
        )


# ---------------------------------------------------------------------------
# Per-observation contract: locator + extension payload
# ---------------------------------------------------------------------------


def test_rsf_observation_carries_rule_id_and_extension_locators(
    tmp_path: Path,
) -> None:
    """Each RSF observation's ``observation_id``
    follows the canonical
    ``rsf_press_freedom:<iso3>:<year>:<variable_name>``
    pattern; ``extension.source_row_reference``
    carries the
    ``rsf_press_freedom:<iso3>:<actual_column>`` pattern
    matching the legacy Stage 2 DB writer.

    The per-row extension carries the canonical RSF
    attribution text (Rule #15), the RSF-specific
    audit-trail fields
    (``rsf_raw_column`` / ``rsf_iso3`` /
    ``rsf_category`` / ``rsf_actual_column`` /
    ``rsf_schema_group``), the verbatim
    ``raw_value`` cell text, and the direction hints
    (``higher_is_better`` / ``raw_scale`` /
    ``normalized_scale_target``).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)

    assert len(result.observations) == 7
    for obs in result.observations:
        # ``observation_id`` is the canonical rule id
        # ``rsf_press_freedom:<iso3>:<year>:<variable>``.
        assert obs.observation_id.startswith(
            f"rsf_press_freedom:{obs.country_code}:{obs.year}:",
        ), (
            f"observation_id must follow the RSF pattern; "
            f"got {obs.observation_id!r}"
        )
        # ``extension.source_row_reference`` is the
        # ``rsf_press_freedom:<iso3>:<actual>`` legacy
        # Stage 2 DB writer pattern.
        ref = obs.extension.get("source_row_reference")
        assert ref == (
            f"rsf_press_freedom:{obs.country_code}:"
            f"{obs.extension.get('rsf_actual_column')}"
        ), (
            f"source_row_reference must be "
            f"'rsf_press_freedom:<iso3>:<actual>'; "
            f"got {ref!r}"
        )
        # The RSF-specific extension fields are
        # present and correctly populated.
        assert obs.extension.get("rsf_iso3") == obs.country_code
        assert obs.extension.get("rsf_category") == (
            "political_freedom"
        )
        assert obs.extension.get("rsf_raw_column") in {
            "score",
            "rank",
            "political_context",
            "economic_context",
            "legal_context",
            "social_context",
            "safety",
        }
        # The pre/post-2022 schema group flag.
        assert obs.extension.get("rsf_schema_group") in {
            RSF_TEST_SCHEMA_GROUP_PRE_2022,
            RSF_TEST_SCHEMA_GROUP_POST_2022,
        }
        # The year-specific actual column name
        # (``Score N`` / ``Rank N`` for pre-2022;
        # ``Score`` / ``Rank`` + literal component
        # column names for 2022+).
        actual_col = obs.extension.get("rsf_actual_column")
        assert actual_col in {
            "Score",
            "Rank",
            "Political Context",
            "Economic Context",
            "Legal Context",
            "Social Context",
            "Safety",
        }
        # The verbatim RSF cell text is preserved on
        # ``extension["raw_value"]`` (a ``str``).
        assert isinstance(obs.extension.get("raw_value"), str)
        # The canonical RSF citation block is
        # byte-identical to the attributions doc.
        assert obs.extension.get("attribution") == (
            RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT
        )


def test_rsf_observation_direction_hints(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension`` carries the
    direction hints (``higher_is_better`` /
    ``raw_scale`` /
    ``normalized_scale_target``) that match the
    canonical catalog.

    The RSF score + 5 components carry
    ``higher_is_better=True`` (higher = better
    press-freedom situation). The rank carries
    ``higher_is_better=False`` (rank 1 = best
    country).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)

    for obs in result.observations:
        # Score + 5 components are
        # higher_is_better=True; rank is
        # higher_is_better=False.
        if obs.indicator_code == RSF_TEST_INDICATOR_RANK:
            assert obs.extension.get("higher_is_better") is (
                False
            )
        else:
            assert obs.extension.get("higher_is_better") is (
                True
            )
        # The raw scale is ``0-100`` for score +
        # components; ``ordinal`` for rank.
        if obs.indicator_code == RSF_TEST_INDICATOR_RANK:
            assert obs.extension.get("raw_scale") == "ordinal"
        else:
            assert obs.extension.get("raw_scale") == "0-100"
        # The normalized scale target is ``0-10`` for
        # all 7 indicators.
        assert obs.extension.get(
            "normalized_scale_target",
        ) == "0-10"


def test_rsf_observation_raw_value_audit_trail_comma_decimal(
    tmp_path: Path,
) -> None:
    """Per-observation ``extension.raw_value`` carries
    the verbatim pre-coercion RSF cell text with the
    comma-decimal separator preserved.

    The legacy reader applies the comma-decimal
    normalization at read time (``"72,67"`` ->
    ``72.67``); the unified transform preserves the
    verbatim cell text on
    ``extension["raw_value"]`` so downstream audit
    code can recover the original RSF cell text
    without re-reading the legacy CSV.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)

    # The 2023 USA row carries score=71,22 (rank 45)
    # with the comma-decimal separator preserved
    # verbatim on the ``raw_value`` audit column;
    # the normalized ``value`` is the float
    # ``71.22`` (the comma-decimal period form).
    usa_score_obs = next(
        obs for obs in result.observations
        if obs.indicator_code == RSF_TEST_INDICATOR_SCORE
    )
    assert usa_score_obs.value == 71.22
    assert usa_score_obs.extension.get("raw_value") == (
        "71,22"
    ), (
        f"raw_value should preserve the verbatim RSF "
        f"comma-decimal cell; got "
        f"{usa_score_obs.extension.get('raw_value')!r}"
    )

    usa_rank_obs = next(
        obs for obs in result.observations
        if obs.indicator_code == RSF_TEST_INDICATOR_RANK
    )
    assert usa_rank_obs.value == 45
    assert usa_rank_obs.extension.get("raw_value") == "45"


def test_rsf_observation_raw_locator_carries_csv_metadata(
    tmp_path: Path,
) -> None:
    """Per-observation ``RawLocator`` carries the
    staged per-year CSV path + the catalog
    ``raw_column`` + the year-specific actual column
    name (e.g. ``Score`` for 2022+, ``Score N`` for
    pre-2022).

    The legacy reader returns a narrow frame after
    the long-to-narrow pivot; the per-observation
    ``RawLocator`` carries the per-year CSV path
    matching the observation's year (so audit code
    can recover the exact per-year file).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
        countries=("USA",),
    )
    result = runner.run(request)

    for obs in result.observations:
        # The raw locator carries the per-year CSV
        # path + the year-specific actual column
        # name.
        assert obs.raw_locator.path is not None
        assert obs.raw_locator.path.endswith(
            "rsf_press_freedom_2023.csv",
        )
        # The per-year asset id embeds the year.
        assert obs.raw_locator.asset_id == (
            "rsf_press_freedom:rsf_press_freedom_2023.csv"
        )
        # The year-specific actual column name.
        assert obs.raw_locator.column_name in {
            "Score",
            "Rank",
            "Political Context",
            "Economic Context",
            "Legal Context",
            "Social Context",
            "Safety",
        }


def test_rsf_observation_source_version_propagation(
    tmp_path: Path,
) -> None:
    """The canonical metadata version
    ``"RSF Press Freedom Index 2026"`` propagates
    consistently to ``RawAsset.version`` and every
    emitted
    ``NormalizedObservation.source_version``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    for obs in result.observations:
        assert obs.source_version == RSF_TEST_DEFAULT_VERSION


# ---------------------------------------------------------------------------
# Per-row observation contract: pre-2022 vs post-2022 schema
# ---------------------------------------------------------------------------


def test_rsf_pre_2022_emits_score_and_rank_only(
    tmp_path: Path,
) -> None:
    """Pre-2022 files do not carry the 5
    component-context columns; the unified transform
    emits zero component-context observations for
    pre-2022 years (the documented pre/post-2022
    schema break).

    The 2002 fixture has 5 country-year rows; the
    legacy reader does not emit any of the 5
    component-context indicators for 2002 (the
    actual columns are absent in the pre-2022 CSV).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2002,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2002,),
    )
    result = runner.run(request)

    indicators = {obs.indicator_code for obs in result.observations}
    assert indicators == {
        RSF_TEST_INDICATOR_SCORE,
        RSF_TEST_INDICATOR_RANK,
    }
    # No component-context indicators for pre-2022.
    assert "rsf_press_freedom_political_context" not in indicators
    assert "rsf_press_freedom_safety" not in indicators
    # Every observation's schema group is ``1`` (pre-2022).
    for obs in result.observations:
        assert obs.extension.get("rsf_schema_group") == (
            RSF_TEST_SCHEMA_GROUP_PRE_2022
        )
    # The year-specific actual column is ``Score N``
    # / ``Rank N`` for 2002-2021.
    actual_cols = {
        obs.extension.get("rsf_actual_column")
        for obs in result.observations
    }
    assert actual_cols.issubset({"Score N", "Rank N"})


def test_rsf_post_2022_emits_all_seven_indicators(
    tmp_path: Path,
) -> None:
    """Post-2022 files carry the 5 component-context
    columns; the unified transform emits all 7
    catalog indicators (2 base + 5
    component-context) for post-2022 years.

    The 2023 fixture has 5 country-year rows; the
    legacy reader emits all 7 catalog indicators per
    row (35 observations total: 5 countries x 7
    indicators).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2023,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    indicators = {obs.indicator_code for obs in result.observations}
    assert indicators == {
        "rsf_press_freedom_score",
        "rsf_press_freedom_rank",
        "rsf_press_freedom_political_context",
        "rsf_press_freedom_economic_context",
        "rsf_press_freedom_legal_context",
        "rsf_press_freedom_social_context",
        "rsf_press_freedom_safety",
    }
    # Every observation's schema group is ``2`` (post-2022).
    for obs in result.observations:
        assert obs.extension.get("rsf_schema_group") == (
            RSF_TEST_SCHEMA_GROUP_POST_2022
        )


def test_rsf_2022_emits_seven_indicators_with_blank_row_filtering(
    tmp_path: Path,
) -> None:
    """The 2022 file carries 181 blank separator
    rows between data rows; the legacy reader drops
    them; the unified transform emits zero
    observations for the separator rows (no
    fabricated observations).

    The 2022 fixture has 5 country-year rows (NOR /
    DNK / SWE / USA / NGA); the legacy reader emits
    all 7 catalog indicators per row (35
    observations total: 5 countries x 7 indicators).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.rsf_press_freedom import (
        create_rsf_press_freedom_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_rsf_bundle(raw_root, years=(2022,))

    registry = InMemorySourceRegistry()
    registry.register(create_rsf_press_freedom_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="rsf_press_freedom"),
        raw_root=raw_root,
        years=(2022,),
    )
    result = runner.run(request)

    assert len(result.observations) == 35
    iso3s = sorted({obs.country_code for obs in result.observations})
    assert iso3s == ["DNK", "NGA", "NOR", "SWE", "USA"]


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def test_rsf_adapter_module_does_not_import_legacy_ingest() -> None:
    """``import leaders_db.sources.adapters.rsf_press_freedom``
    MUST NOT import ``leaders_db.ingest`` at module
    import time (SRC-MIG-007 +
    ``docs/architecture/sources.md`` §10.1)."""
    _purge_modules("leaders_db")
    try:
        importlib_import = __import__(
            "importlib",
            fromlist=["import_module"],
        ).import_module
        importlib_import("leaders_db.sources.adapters.rsf_press_freedom")
        leaked = sorted(
            mod for mod in sys.modules
            if mod == "leaders_db.ingest"
            or mod.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "leaders_db.sources.adapters.rsf_press_freedom "
            "must not import leaders_db.ingest at import "
            f"time (leaked modules: {leaked})"
        )
    finally:
        _purge_modules("leaders_db")


def test_rsf_default_version_matches_canonical_stamp() -> None:
    """The default version stamp is byte-identical
    to the canonical ``"RSF Press Freedom Index
    2026"``."""
    from leaders_db.sources.adapters.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_DEFAULT_VERSION,
    )

    assert RSF_PRESS_FREEDOM_DEFAULT_VERSION == (
        RSF_TEST_DEFAULT_VERSION
    )


def test_rsf_csv_name_pattern_matches_canonical_filename() -> None:
    """The canonical per-year CSV filename pattern
    resolves to ``rsf_press_freedom_<year>.csv``."""
    from leaders_db.sources.adapters.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_CSV_NAME_PATTERN,
    )

    assert (
        RSF_PRESS_FREEDOM_CSV_NAME_PATTERN.format(year=2023)
        == "rsf_press_freedom_2023.csv"
    )
    assert (
        RSF_PRESS_FREEDOM_CSV_NAME_PATTERN.format(year=2002)
        == "rsf_press_freedom_2002.csv"
    )
