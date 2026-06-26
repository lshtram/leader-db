"""Phase C / D slice -- Bertelsmann Transformation Index
(BTI) adapter under the unified ``leaders_db.sources``
interface.

The BTI adapter is the tenth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 8 and
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, Political Terror
Scale, and Reporters Without Borders (RSF). The
legacy BTI reader / transform / catalog under
``leaders_db.ingest.bti`` /
``leaders_db.ingest.bti_io`` /
``leaders_db.ingest.bti_xlsx`` is reused internally
via lazy imports -- the package boundary at
``docs/architecture/sources.md`` §10.1 is preserved.

BTI is structurally close to PTS / WGI / V-Dem: a
single local file, no HTTP layer, but it carries the
distinct **biennial sheet/year mapping** contract --
each BTI edition covers the ~2-year period preceding
publication, so for the prototype target year 2023
the adapter reads the ``BTI 2024`` sheet (covers
2022-2023). The legacy catalog at
``src/leaders_db/ingest/catalogs/bti.csv`` lists 12
indicator rows across 3 categories (effectiveness /
political_freedom / economic_wellbeing). The 5-country
fixture at ``tests/fixtures/bti/sample.xlsx`` (real
BTI-format xlsx, real values from the cumulative BTI
xlsx, no invented data) covers the ``BTI 2024`` and
``BTI 2022`` sheets with 12 catalog indicator columns
populated from the live BTI xlsx values.

Tests cover the documented slice acceptance criteria:

- The BTI adapter descriptor is registerable /
  listable through the new
  :class:`InMemorySourceRegistry` and exposes the
  documented static metadata (source_id ``bti``,
  default version ``"BTI 2026"``, attribution_key
  ``bti``, dataset type, 2002-2025 coverage hint,
  3 observation families
  (``effectiveness_country_year`` /
  ``political_freedom_country_year`` /
  ``economic_wellbeing_country_year``), BTI homepage
  URL).
- :class:`SourceIngestRunner` can run BTI
  end-to-end through the new registry against a
  fixture ``raw_root`` and produce
  :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the adapter
  internally reuses legacy parsing modules, but
  dispatch is registry-based).
- The biennial sheet/year mapping is preserved on
  the ``SourceIngestRunner.run(request)`` end-to-end
  path (target year 2023 -> ``BTI 2024`` sheet;
  target year 2021 -> ``BTI 2022`` sheet;
  target year 2025 -> ``BTI 2026`` sheet).
- The 12 emitted indicator codes / categories /
  families / value types /
  ``source_row_reference`` (``"bti:<country_name>"``)
  pattern / raw locators are byte-identical to the
  legacy Stage 2 contract.
- The BTI canonical version stamp
  (``"BTI 2026"``) propagates consistently to
  ``RawAsset.version`` and every emitted
  ``NormalizedObservation.source_version``.
- A ``checksum_sha256`` mismatch between the staged
  xlsx and the metadata fires the structured
  ``bti_checksum_mismatch`` error and short-circuits
  the runner BEFORE ``read_raw`` / ``transform``.
- A mismatched / malformed / absent metadata
  ``source_version`` fires the structured
  ``bti_metadata_version_mismatch`` error and
  short-circuits the runner BEFORE ``read_raw`` /
  ``transform``.
- An unsupported request ``source_version`` (e.g.
  ``"BTI 2024"`` against the canonical ``"BTI
  2026"``) fails readiness with a structured
  ``unsupported_version`` error and short-circuits
  the runner BEFORE ``read_raw`` / ``transform``.
- Missing-cell behavior: blank cells become NaN
  (no silent conversion per SRC-OBS-007); the
  transform skips ``None`` / ``NaN`` cells so no
  fabricated observations are emitted.
- Importing the new
  ``leaders_db.sources.adapters.bti`` module does NOT
  pull in any ``leaders_db.ingest`` module at import
  time (SRC-MIG-007 + the import boundary documented
  in ``docs/architecture/sources.md`` §10.1).
- The BTI unified path is local-file only
  (``requires_network=False``, no HTTP layer in the
  new package). The runner NEVER invokes the network.
  A network tripwire test monkeypatches the canonical
  Python network surfaces
  (``requests.get`` / ``requests.post`` /
  ``urllib.request.urlopen`` / ``socket.socket``) to
  raise on call, then drives the production
  ``SourceIngestRunner.run(request)`` end-to-end
  from a staged local xlsx and asserts the 60
  observations round-trip without invoking any
  network tripwire.
- The legacy ``BTI_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/bti_io.py`` is
  byte-identical to the new
  ``BTI_ATTRIBUTION_TEXT`` constant
  (``test_bti_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text is
  a substring of ``docs/sources/attributions.md``).
- The clean package ``__all__`` exposes every public
  symbol documented in the adapter module +
  descriptor (``test_bti_public_surface_is_coherent``
  enforces the public surface contract).

PASS-ELIGIBLE rationale
-----------------------

The legacy BTI reader is well-tested via the
existing ``tests/test_ingest_bti.py`` suite (50 tests
covering the biennial sheet-to-year resolution, the
xlsx read with per-indicator column resolution, the
long-to-wide pivot, the DB writers, the orchestrator
end-to-end, the CLI dispatch, and the public
surface). The tests in this file prove that the new
``leaders_db.sources.adapters.bti`` adapter wraps
the legacy parsing logic behind the unified
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


# Test-only constants. Mirror the descriptor
# constants so the tests stay decoupled from the
# package's ``__all__`` (the constants are re-exported
# there but the test file pins the values explicitly
# for clarity).
BTI_TEST_FIXTURE_XLSX_NAME: str = "BTI_2006-2026_Scores.xlsx"
BTI_TEST_METADATA_NAME: str = "metadata.json"
BTI_TEST_ATTRIBUTION_KEY: str = "bti"
BTI_TEST_SOURCE_KEY: str = "bti"
BTI_TEST_DEFAULT_VERSION: str = "BTI 2026"
BTI_TEST_BUNDLE_VERSION_VERBOSE: str = (
    "BTI 2026 (covers 2024-2025); cumulative file "
    "covers 2006-2026 (biennial, 12 editions)"
)
BTI_TEST_COVERAGE_START: int = 2002
BTI_TEST_COVERAGE_END: int = 2025
BTI_TEST_HOMEPAGE_URL: str = "https://bti-project.org/"
BTI_TEST_FAMILIES: tuple[str, ...] = (
    "effectiveness_country_year",
    "political_freedom_country_year",
    "economic_wellbeing_country_year",
)
BTI_TEST_INDICATOR_NAMES: tuple[str, ...] = (
    "bti_governance_index",
    "bti_governance_performance",
    "bti_status_index",
    "bti_democracy_status",
    "bti_q1_stateness",
    "bti_q2_political_participation",
    "bti_q3_rule_of_law",
    "bti_q4_democratic_institutions",
    "bti_q5_political_social_integration",
    "bti_q6_socioeconomic_development",
    "bti_q7_market_competition",
    "bti_q11_economic_performance",
)
BTI_TEST_INDICATOR_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "effectiveness_country_year": (
        "bti_governance_index",
        "bti_governance_performance",
    ),
    "political_freedom_country_year": (
        "bti_status_index",
        "bti_democracy_status",
        "bti_q1_stateness",
        "bti_q2_political_participation",
        "bti_q3_rule_of_law",
        "bti_q4_democratic_institutions",
        "bti_q5_political_social_integration",
    ),
    "economic_wellbeing_country_year": (
        "bti_q6_socioeconomic_development",
        "bti_q7_market_competition",
        "bti_q11_economic_performance",
    ),
}
BTI_TEST_RAW_COLUMNS: tuple[str, ...] = (
    "  G | Governance Index",
    "  GII | Governance Performance",
    "  S | Status Index",
    "  SI | Democracy Status",
    "  Q1 | Stateness",
    "  Q2 | Political Participation",
    "  Q3 | Rule of Law",
    "  Q4 | Stability of Democratic Institutions",
    "  Q5 | Political and Social Integration",
    "  Q6 | Level of Socioeconomic Development",
    "  Q7 | Organization of the Market and Competition",
    "  Q11 | Economic Performance",
)
BTI_TEST_CANONICAL_VALUE_TYPE: str = "numeric"
BTI_TEST_XLSX_ASSET_ID: str = "bti:BTI_2006-2026_Scores.xlsx"

# Live SHA-256 for the canonical BTI cumulative xlsx
# (verified live 2026-06-17 per
# ``data/raw/bti/metadata.json``). Tests that stage a
# bundle with the canonical SHA stamp reuse this
# constant so the readiness gate's optional
# xlsx-checksum match branch fires cleanly.
BTI_TEST_CANONICAL_SHA256: str = (
    "599cb7301d3c82cb3b73d2b69c7476ea357016a56a1d328092bbd2af9d5cc37b"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SpyBTIAdapter:
    """Wrap a :class:`BTIAdapter` and record every
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
        self,
        request: SourceIngestRequest,
        raw: Any,
    ) -> Any:
        self.calls.append("transform")
        return self._inner.transform(request, raw)


def _stage_bti_bundle(
    raw_root: Path,
    *,
    with_xlsx: bool = True,
    with_metadata: bool = True,
    metadata_overrides: dict[str, Any] | None = None,
    staged_sha: str | None = "AUTO",
    source_version: str = BTI_TEST_BUNDLE_VERSION_VERBOSE,
) -> Path:
    """Stage the canonical BTI fixture bundle under
    ``raw_root/bti``.

    Copies ``tests/fixtures/bti/sample.xlsx`` (the
    5-country real-format BTI xlsx fixture sliced
    from the live cumulative xlsx) into
    ``<raw_root>/bti/BTI_2006-2026_Scores.xlsx`` and
    writes a well-formed ``metadata.json`` (canonical
    primary shape mirroring the staged
    ``data/raw/bti/metadata.json``).

    The ``checksum_sha256`` default is the actual
    staged fixture SHA-256 (``"AUTO"`` sentinel), so
    the readiness gate's optional xlsx-checksum match
    branch fires cleanly. Pass a specific 64-char hex
    string to set the metadata's ``checksum_sha256``
    field; pass ``staged_sha=None`` to omit the field
    (the readiness gate tolerates a missing checksum
    for backward compatibility with the legacy
    Stage 2 adapter); pass a non-hex 64-char string to
    exercise the malformed-checksum branch.

    The fixture carries 5 countries (Mexico / Brazil
    / India / Nigeria / Kenya) on 2 edition sheets
    (``BTI 2024`` for year=2023; ``BTI 2022`` for
    year=2021) with the 12 catalog indicator columns
    populated from the live BTI xlsx values (no
    invented data).
    """
    bundle_dir = raw_root / "bti"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "bti"
    )
    fixture_xlsx = fixtures / "sample.xlsx"

    if with_xlsx:
        staged_xlsx = bundle_dir / BTI_TEST_FIXTURE_XLSX_NAME
        shutil.copy2(fixture_xlsx, staged_xlsx)

    if with_metadata:
        # Compute the actual staged SHA when
        # ``AUTO`` is requested (the default), so
        # the gate's checksum-match branch fires
        # cleanly.
        if staged_sha == "AUTO":
            staged_xlsx_path = (
                bundle_dir / BTI_TEST_FIXTURE_XLSX_NAME
            )
            if staged_xlsx_path.is_file():
                computed_sha: str | None = hashlib.sha256(
                    staged_xlsx_path.read_bytes(),
                ).hexdigest()
            else:
                # No xlsx staged (e.g. metadata-only
                # readiness test); omit the
                # checksum_sha256 field. The
                # ``missing_raw`` readiness branch
                # fires before the checksum match
                # branch so this is fine.
                computed_sha = None
        else:
            computed_sha = staged_sha

        payload: dict[str, Any] = {
            "source_name": (
                "Bertelsmann Transformation Index (BTI)"
            ),
            "source_version": source_version,
            "download_date": "2026-06-17",
            "coverage": (
                "country-edition (biennial snapshot, "
                "not time series)"
            ),
            "years_available": (
                "BTI 2006 (old methodology), 2006, 2008, "
                "2010, 2012, 2014, 2016, 2018, 2020, "
                "2022, 2024, 2026 -- 12 editions total"
            ),
            "license_note": (
                "Free; cite Bertelsmann Stiftung. "
                "Reprinted with permission."
            ),
            "local_files": [
                BTI_TEST_FIXTURE_XLSX_NAME,
                "BTI2026_Codebook.pdf",
            ],
            "ingestion_status": "downloaded",
            "source_url": (
                "https://bti-project.org/en/downloads"
            ),
            "checksum_sha256": (
                {
                    BTI_TEST_FIXTURE_XLSX_NAME: (
                        computed_sha
                    ),
                    "BTI2026_Codebook.pdf": (
                        "706e497ad3d92b53afaa25baa2a42bd1"
                        "39b5450b84f43f8b5ca50e016e74cea2"
                    ),
                }
                if computed_sha is not None
                else None
            ),
            "edition_count": 12,
            "countries_per_edition": (
                "137-159 (varies by edition)"
            ),
            "column_count": 123,
            "format": (
                "xlsx with one sheet per BTI edition "
                "(BTI 2026, 2024, 2022, ..., 2006, "
                "2006_old); each sheet has Region + "
                "Ranking + Status Index + Q1-Q17 "
                "questions + composite indices (S, SI, "
                "E, EI, G, GII) + categories"
            ),
            "notes": (
                "Biennial expert-coded assessment of "
                "political and economic transformation "
                "plus governance performance. For the "
                "2023 target year, the BTI 2024 edition "
                "(sheet 'BTI 2024') is the relevant "
                "snapshot -- BTI 2024 was published in "
                "2024 and covers the 2022-2023 period. "
                "Key columns for our pipeline: G | "
                "Governance Index (effectiveness "
                "category), S | Status Index, SI | "
                "Democracy Status, Q1-Q5 (stateness/"
                "political participation/rule of law/"
                "integration), Q6-Q12 (socioeconomic/"
                "economic transformation), GII | "
                "Governance Performance."
            ),
        }
        if metadata_overrides:
            payload.update(metadata_overrides)
        (bundle_dir / BTI_TEST_METADATA_NAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
    return bundle_dir


def _stage_bti_bundle_with_2026_sheet(raw_root: Path) -> Path:
    """Stage a temp-only workbook with a ``BTI 2026`` sheet."""
    bundle_dir = _stage_bti_bundle(raw_root, staged_sha=None)
    import openpyxl

    xlsx_path = bundle_dir / BTI_TEST_FIXTURE_XLSX_NAME
    wb = openpyxl.load_workbook(xlsx_path)
    try:
        copied = wb.copy_worksheet(wb["BTI 2024"])
        copied.title = "BTI 2026"
        wb.save(xlsx_path)
    finally:
        wb.close()
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


def test_bti_descriptor_exposes_documented_static_metadata() -> None:
    """The BTI descriptor carries every documented
    field.

    Contract (SRC-ID-001 through SRC-ID-004 +
    ``docs/architecture/sources.md`` §5.2):

    - ``source_id.slug == "bti"``
    - ``display_name`` is the canonical BTI 2026
      label.
    - ``source_type == "dataset"``
    - ``default_version`` matches the canonical
      metadata stamp (``"BTI 2026"``).
    - ``homepage_url`` is the canonical BTI landing
      page.
    - ``attribution_key == "bti"``
    - ``coverage_hint.start_year == 2002``,
      ``coverage_hint.end_year == 2025``.
    - ``supported_observation_families`` is the
      3-tuple of canonical families.
    - ``requires_network is False`` (local-file
      only).
    """
    from leaders_db.sources.adapters.bti import (
        build_bti_descriptor,
    )

    descriptor = build_bti_descriptor()

    assert descriptor.source_id.slug == BTI_TEST_SOURCE_KEY
    assert descriptor.source_type == "dataset"
    assert (
        descriptor.default_version
        == BTI_TEST_DEFAULT_VERSION
    )
    assert descriptor.homepage_url == BTI_TEST_HOMEPAGE_URL
    assert (
        descriptor.attribution_key
        == BTI_TEST_ATTRIBUTION_KEY
    )
    assert (
        descriptor.coverage_hint.start_year
        == BTI_TEST_COVERAGE_START
    )
    assert (
        descriptor.coverage_hint.end_year
        == BTI_TEST_COVERAGE_END
    )
    assert descriptor.supported_observation_families == (
        BTI_TEST_FAMILIES
    )
    assert descriptor.requires_manual_approval is False
    assert descriptor.requires_network is False


def test_bti_attribution_text_matches_attributions_doc() -> None:
    """The BTI attribution text is byte-identical to
    the legacy ``BTI_ATTRIBUTION`` constant AND a
    substring of ``docs/sources/attributions.md``.

    Rule #15 drift guard: the canonical BTI citation
    block in ``docs/sources/attributions.md`` is the
    source of truth; the adapter module's constant
    must be byte-identical to a substring of that
    doc AND byte-identical to the legacy
    ``BTI_ATTRIBUTION`` constant in
    ``src/leaders_db/ingest/bti_io.py``.

    The unified text is the "short form"
    ``"BTI 2026 (Bertelsmann Stiftung 2026)."`` --
    the canonical "Attribution text in reports" line
    in ``docs/sources/attributions.md`` (NOT the
    long citation form). The long citation block
    follows in the same doc.
    """
    from leaders_db.ingest.bti_io import BTI_ATTRIBUTION
    from leaders_db.sources.adapters.bti import (
        BTI_ATTRIBUTION_TEXT,
    )

    assert BTI_ATTRIBUTION_TEXT == BTI_ATTRIBUTION, (
        "Unified BTI attribution must be byte-identical "
        "to the legacy BTI_ATTRIBUTION constant in "
        "src/leaders_db/ingest/bti_io.py."
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
    assert BTI_ATTRIBUTION_TEXT in attributions_text, (
        f"{BTI_ATTRIBUTION_TEXT!r} is not a substring of "
        f"{attributions_path}. Update both in the same "
        "commit (Rule #15)."
    )
    assert "Bertelsmann Stiftung 2026" in BTI_ATTRIBUTION_TEXT
    assert "BTI 2026" in BTI_ATTRIBUTION_TEXT


def test_bti_adapter_satisfies_source_adapter_protocol() -> None:
    """``BTIAdapter`` instances satisfy the
    runtime-checkable Protocol.

    The Protocol guard catches a missing
    ``descriptor`` or any of ``check_ready`` /
    ``read_raw`` / ``transform`` at construction
    time.
    """
    from leaders_db.sources import SourceAdapter
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    adapter = create_bti_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == "bti"


def test_bti_descriptor_indicator_names_and_raw_columns() -> None:
    """The descriptor's indicator names + raw column
    names are byte-identical to the canonical catalog.

    The canonical catalog at
    ``src/leaders_db/ingest/catalogs/bti.csv`` lists
    12 indicator rows (4 governance/effectiveness +
    political-freedom composites + Q1-Q12
    representative questions). The descriptor exposes
    the indicator names + raw columns so the public
    surface matches the catalog byte-for-byte (the
    drift guard
    ``test_bti_attribution_text_matches_attributions_doc``
    enforces the same byte-identity on the
    attribution block; this test enforces the same on
    the indicator list).
    """
    from leaders_db.sources.adapters.bti import (
        BTI_INDICATOR_NAMES,
        BTI_RAW_COLUMNS,
    )

    assert set(BTI_INDICATOR_NAMES) == set(
        BTI_TEST_INDICATOR_NAMES,
    )
    assert set(BTI_RAW_COLUMNS) == set(
        BTI_TEST_RAW_COLUMNS,
    )


def test_bti_public_surface_is_coherent() -> None:
    """The package root ``__all__`` exposes every
    public symbol documented in the adapter module +
    descriptor.

    Defense in depth: any future contributor who
    removes a public name from ``__all__`` without
    updating the design doc / the public surface
    contract will see this test fail.
    """
    from leaders_db.sources.adapters import bti as bti_pkg

    required = {
        "BTI_SOURCE_KEY",
        "BTI_DEFAULT_VERSION",
        "BTI_ATTRIBUTION_KEY",
        "BTI_ATTRIBUTION_TEXT",
        "BTI_COVERAGE_START_YEAR",
        "BTI_COVERAGE_END_YEAR",
        "BTI_HOMEPAGE_URL",
        "BTI_METADATA_NAME",
        "BTI_XLSX_NAME",
        "BTI_OBSERVATION_FAMILY_EFFECTIVENESS",
        "BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
        "BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING",
        "BTI_SUPPORTED_FAMILIES",
        "BTI_INDICATOR_GOVERNANCE_INDEX",
        "BTI_INDICATOR_GOVERNANCE_PERFORMANCE",
        "BTI_INDICATOR_STATUS_INDEX",
        "BTI_INDICATOR_DEMOCRACY_STATUS",
        "BTI_INDICATOR_Q1_STATENESS",
        "BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION",
        "BTI_INDICATOR_Q3_RULE_OF_LAW",
        "BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS",
        "BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION",
        "BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT",
        "BTI_INDICATOR_Q7_MARKET_COMPETITION",
        "BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE",
        "BTI_INDICATOR_NAMES",
        "BTI_RAW_COLUMNS",
        "BTI_RAW_COLUMN_GOVERNANCE_INDEX",
        "BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE",
        "BTI_RAW_COLUMN_STATUS_INDEX",
        "BTI_RAW_COLUMN_DEMOCRACY_STATUS",
        "BTI_RAW_COLUMN_Q1_STATENESS",
        "BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION",
        "BTI_RAW_COLUMN_Q3_RULE_OF_LAW",
        "BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS",
        "BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION",
        "BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT",
        "BTI_RAW_COLUMN_Q7_MARKET_COMPETITION",
        "BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE",
        "BTI_XLSX_ASSET_ID",
        "BTI_METADATA_VERSION_MISMATCH",
        "BTI_CHECKSUM_MISMATCH",
        "UNSUPPORTED_VERSION",
        "BTI_TRANSFORM_NAME",
        "BTIAdapter",
        "build_bti_descriptor",
        "create_bti_adapter",
        "register_bti",
        "check_metadata_well_formed",
        "check_source_version",
        "collect_request_scoping_warnings",
        "transform_bti_observations",
        "read_bti_xlsx",
        "emit_bti_observations",
        "load_indicator_catalog",
        "rating_category_to_observation_family",
        "DEFAULT_CATALOG_PATH",
        "_canonical_source_version",
        "_canonical_asset_id",
        "_resolve_sheet_name",
        "_resolve_target_year",
        "_build_raw_long_lookup",
        "_locate_row_index",
        "_coerce_float",
        "_raw_value_to_string",
        "_resolve_value_type",
        "_bundle_dir",
        "_metadata_path",
        "_read_metadata_payload",
        "_xlsx_path",
        "_checksum_match_blocker",
        "_checksum_shape_blocker",
        "_ingestion_status_blocker",
        "_local_files_blocker",
        "_metadata_source_version_blocker",
        "_non_empty_string_blocker",
        "_positive_int_blocker",
        "_presence_blocker",
        "_required_fields_blocker",
        "build_observation",
        "_default_asset_id",
        "_default_source_version",
        "_xlsx_name",
    }
    missing = required - set(bti_pkg.__all__)
    assert not missing, (
        f"missing public names on "
        f"leaders_db.sources.adapters.bti: {missing}"
    )


def test_bti_register_helper_registers_against_explicit_registry() -> None:
    """``register_bti(registry)`` is the explicit seam
    for tests + CLI."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
    )
    from leaders_db.sources.adapters.bti import register_bti

    registry = InMemorySourceRegistry()
    adapter = register_bti(registry)
    assert registry.get_adapter(SourceId(slug="bti")) is adapter


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end
# ---------------------------------------------------------------------------


def test_bti_runner_produces_normalized_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives BTI
    through the documented lifecycle and emits
    :class:`NormalizedObservation` records.

    The fixture has 5 country-edition rows on
    ``BTI 2024`` (year=2023) with the 12 catalog
    indicators. 5 countries x 12 indicators = 60
    observations round-trip. The unified transform
    carries the resolved sheet name + covered
    interval on every observation's ``extension``
    (``bti_sheet_name`` = ``"BTI 2024"``;
    ``bti_target_year`` = ``2023``).
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        NormalizedObservation,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)

    assert isinstance(result, SourceIngestResult)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()
    assert result.manifest is None  # Phase B runner contract

    assert len(result.observations) == 60, (
        f"expected 60 observations (5 country-edition "
        f"rows x 12 indicators); got "
        f"{len(result.observations)}"
    )
    for obs in result.observations:
        assert isinstance(obs, NormalizedObservation)
        assert obs.source_id.slug == "bti"
        assert obs.observation_family in BTI_TEST_FAMILIES
        assert obs.indicator_code in BTI_TEST_INDICATOR_NAMES
        assert obs.year == 2023
        # BTI does not carry ISO3 codes; the unified
        # transform carries the BTI display name on
        # ``country_name`` + ``None`` on
        # ``country_code``.
        assert obs.country_code is None
        assert obs.country_name is not None
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert (
            obs.value_type == BTI_TEST_CANONICAL_VALUE_TYPE
        )
        # The raw 1-10 value is preserved verbatim
        # (no inversion needed; BTI is
        # higher-is-better).
        assert isinstance(obs.value, (int, float))
        assert 1 <= float(obs.value) <= 10
        # The resolved sheet name + covered interval
        # are carried on every observation's
        # ``extension`` so downstream Stage 5 score
        # modules can apply the biennial proxy /
        # source-edition semantics without re-reading
        # the parquet metadata.
        assert obs.extension["bti_target_year"] == obs.year


def test_bti_runner_target_year_maps_to_correct_biennial_sheet(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` resolves
    the BTI edition sheet for the requested target
    year.

    - ``years=(2023,)`` -> ``BTI 2024`` (covers
      2022-2023; the canonical mapping for the
      prototype target year).
    - ``years=(2021,)`` -> ``BTI 2022`` (covers
      2020-2021).
    - ``years=(2025,)`` -> ``BTI 2026`` (covers
      2024-2025; the latest edition).

    The end-to-end runner drives the legacy reader
    via ``BTI 2026`` (the latest edition) by
    default, then narrows the wide frame to the
    requested year. The biennial mapping proof is
    that ``years=(2023,)`` surfaces
    ``bti_sheet_name="BTI 2024"`` on every
    observation.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    # Target year 2023 -> BTI 2024.
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 60  # 5x12
    for obs in result.observations:
        assert obs.year == 2023
        assert obs.extension["bti_sheet_name"] == "BTI 2024"
        assert obs.extension["bti_target_year"] == 2023

    # Target year 2021 -> BTI 2022.
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2021,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 60  # 5x12
    for obs in result.observations:
        assert obs.year == 2021
        assert obs.extension["bti_sheet_name"] == "BTI 2022"
        assert obs.extension["bti_target_year"] == 2021

    # Target year 2025 -> BTI 2026. The base fixture
    # carries only BTI 2022 + BTI 2024; stage a
    # temp-only workbook with BTI 2026 to exercise the
    # production sheet dispatch path without altering
    # checked-in raw fixture data.
    raw_root_2026 = tmp_path / "raw-2026"
    _stage_bti_bundle_with_2026_sheet(raw_root_2026)
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root_2026,
        years=(2025,),
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert len(result.observations) == 60  # 5x12
    for obs in result.observations:
        assert obs.year == 2025
        assert obs.extension["bti_sheet_name"] == "BTI 2026"
        assert obs.extension["bti_target_year"] == 2025


def test_bti_runner_years_none_emits_all_available_fixture_sheets(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    result = runner.run(
        SourceIngestRequest(
            source_id=SourceId(slug="bti"),
            raw_root=raw_root,
            years=None,
        ),
    )

    assert result.readiness.ready is True
    assert len(result.observations) == 120  # 2 sheets x 5 rows x 12
    observed = {
        (obs.year, obs.extension["bti_sheet_name"])
        for obs in result.observations
    }
    assert observed == {(2021, "BTI 2022"), (2023, "BTI 2024")}


def test_bti_runner_multi_year_request_emits_each_requested_sheet(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    result = runner.run(
        SourceIngestRequest(
            source_id=SourceId(slug="bti"),
            raw_root=raw_root,
            years=(2021, 2023),
        ),
    )

    assert result.readiness.ready is True
    assert len(result.observations) == 120  # 2 sheets x 5 rows x 12
    observed = {
        (obs.year, obs.extension["bti_sheet_name"])
        for obs in result.observations
    }
    assert observed == {(2021, "BTI 2022"), (2023, "BTI 2024")}


def test_bti_runner_out_of_coverage_year_warns_and_emits_zero(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    result = runner.run(
        SourceIngestRequest(
            source_id=SourceId(slug="bti"),
            raw_root=raw_root,
            years=(2026,),
        ),
    )

    assert result.readiness.ready is True
    assert result.observations == ()
    warnings = [
        w for w in result.warnings
        if isinstance(w, SourceWarning) and w.code == "year_absent"
    ]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.severity == "warning"
    assert warning.source_id == SourceId(slug="bti")
    assert warning.context == {
        "year": 2026,
        "coverage_start_year": BTI_TEST_COVERAGE_START,
        "coverage_end_year": BTI_TEST_COVERAGE_END,
    }


def test_bti_runner_leader_filter_warns_and_keeps_country_rows(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
        SourceWarning,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    result = runner.run(
        SourceIngestRequest(
            source_id=SourceId(slug="bti"),
            raw_root=raw_root,
            years=(2023,),
            leaders=("Example Leader",),
        ),
    )

    assert result.readiness.ready is True
    assert len(result.observations) == 60
    warnings = [
        w for w in result.warnings
        if isinstance(w, SourceWarning)
        and w.code == "unsupported_filter"
    ]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.severity == "warning"
    assert warning.source_id == SourceId(slug="bti")
    assert warning.context == {
        "requested_leaders": ["Example Leader"],
    }


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_bti_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives BTI through the new registry
    and never calls into
    ``leaders_db.ingest.STAGE2_ADAPTERS``.

    The test monkeypatches
    ``STAGE2_ADAPTERS["bti"]`` with a tracking
    sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)``
    executes the new BTI adapter lifecycle end-to-end.

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
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    legacy_calls: list[tuple[str, dict]] = []
    original_bti = legacy_ingest.STAGE2_ADAPTERS.get("bti")

    def _legacy_tracker(**kwargs: Any) -> None:
        legacy_calls.append(("bti", kwargs))

    legacy_ingest.STAGE2_ADAPTERS["bti"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        registry.register(create_bti_adapter())
        runner = SourceIngestRunner(registry=registry)

        request = SourceIngestRequest(
            source_id=SourceId(slug="bti"),
            raw_root=raw_root,
        )
        runner.run(request)

        assert legacy_calls == [], (
            f"runner must not route through "
            f"STAGE2_ADAPTERS['bti']; saw {legacy_calls}"
        )
    finally:
        # Restore the legacy dispatch table.
        legacy_ingest.STAGE2_ADAPTERS["bti"] = original_bti


# ---------------------------------------------------------------------------
# Runner-short-circuit readiness-failure paths
# ---------------------------------------------------------------------------


def test_bti_missing_xlsx_fails_readiness_with_missing_raw(
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
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage metadata only -- no xlsx.
    _stage_bti_bundle(raw_root, with_xlsx=False)

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
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


def test_bti_missing_metadata_fails_readiness_with_missing_metadata(
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
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    # Stage xlsx only -- no metadata.json.
    _stage_bti_bundle(raw_root, with_metadata=False)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()


def test_bti_unsupported_source_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """``source_version="BTI 2024"`` fails readiness
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
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        source_version="BTI 2024",
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.run(request)
    assert "not ready" in str(excinfo.value).lower()
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_mismatched_bundle_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """A bundle ``source_version`` stamp that differs
    from the canonical stamps (brief ``"BTI 2026"``
    + verbose
    ``"BTI 2026 (covers 2024-2025); cumulative file
    covers 2006-2026 (biennial, 12 editions)"``)
    fails readiness with a structured
    ``bti_metadata_version_mismatch`` error.

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
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        source_version="BTI 2024",
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_malformed_checksum_fails_readiness(
    tmp_path: Path,
) -> None:
    """A non-hex 64-char string under
    ``checksum_sha256`` fires ``missing_metadata``
    (NOT ``bti_checksum_mismatch`` -- mismatch is
    reserved for well-formed values that disagree
    with the staged file)."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, staged_sha="z" * 64)

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_checksum_mismatch_fails_readiness(
    tmp_path: Path,
) -> None:
    """A well-formed 64-char checksum that disagrees
    with the staged xlsx fires
    ``bti_checksum_mismatch``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    wrong_sha = "0" * 64
    _stage_bti_bundle(raw_root, staged_sha=wrong_sha)

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_correct_checksum_passes_readiness(
    tmp_path: Path,
) -> None:
    """A well-formed checksum matching the staged
    xlsx's actual SHA-256 passes readiness without
    errors."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = runner.run(request)
    assert result.readiness.ready is True
    assert result.readiness.errors == ()


def test_bti_malformed_local_files_fails_readiness(
    tmp_path: Path,
) -> None:
    """A ``local_files`` field whose entries are not
    non-empty strings fires ``missing_metadata``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"local_files": [123]},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_empty_local_files_fails_readiness_envelope(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import SourceId, SourceIngestRequest
    from leaders_db.sources.adapters.bti import create_bti_adapter

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"local_files": []},
    )

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    readiness = create_bti_adapter().check_ready(request)

    assert readiness.ready is False
    assert len(readiness.errors) == 1
    error = readiness.errors[0]
    assert error.code == "missing_metadata"
    assert error.severity == "error"
    assert error.source_id == SourceId(slug="bti")
    assert error.context == {
        "bundle_dir": str(raw_root / "bti"),
        "xlsx_name": BTI_TEST_FIXTURE_XLSX_NAME,
    }


def test_bti_empty_local_files_runner_short_circuits(
    tmp_path: Path,
) -> None:
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import create_bti_adapter

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"local_files": []},
    )

    registry = InMemorySourceRegistry()
    spy = _SpyBTIAdapter(create_bti_adapter())
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    with pytest.raises(RuntimeError):
        runner.run(
            SourceIngestRequest(
                source_id=SourceId(slug="bti"),
                raw_root=raw_root,
            ),
        )
    assert spy.calls == ["check_ready"]


def test_bti_wrong_local_files_fails_readiness(
    tmp_path: Path,
) -> None:
    """A ``local_files`` field that omits the canonical
    xlsx filename fires ``missing_metadata``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"local_files": ["other.xlsx"]},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_missing_required_field_fails_readiness(
    tmp_path: Path,
) -> None:
    """A metadata.json missing a required field fires
    ``missing_metadata``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"source_name": None},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


def test_bti_invalid_ingestion_status_fails_readiness(
    tmp_path: Path,
) -> None:
    """A metadata.json ``ingestion_status`` outside
    the acceptable set fires ``missing_metadata``."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(
        raw_root,
        metadata_overrides={"ingestion_status": "bogus"},
    )

    registry = InMemorySourceRegistry()
    real_adapter = create_bti_adapter()
    spy = _SpyBTIAdapter(real_adapter)
    registry.register(spy)  # type: ignore[arg-type]
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    with pytest.raises(RuntimeError):
        runner.run(request)
    assert spy.calls == ["check_ready"], (
        f"expected only 'check_ready' call; got "
        f"{spy.calls}"
    )


# ---------------------------------------------------------------------------
# Direct check_ready() structured error assertions
# ---------------------------------------------------------------------------


def _assert_readiness_error(
    result: Any,
    *,
    expected_code: str,
    expected_severity: str = "error",
    expected_source_slug: str = BTI_TEST_SOURCE_KEY,
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
        f"expected severity={expected_severity!r}; got "
        f"{error.severity!r}"
    )
    assert error.source_id is not None, (
        "error.source_id must be set so the runner can "
        "route the diagnostic to the operator"
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


def test_bti_check_ready_missing_metadata_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when ``metadata.json`` is absent.

    The structured error carries
    ``severity='error'``,
    ``source_id.slug='bti'``, and the canonical
    context keys (``bundle_dir`` + ``xlsx_name``)
    so the runner can route the diagnostic to the
    operator.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        BTI_XLSX_NAME,
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, with_metadata=False)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )
    assert result.errors[0].context["xlsx_name"] == (
        BTI_XLSX_NAME
    )


def test_bti_check_ready_missing_xlsx_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_raw``
    error when the staged xlsx is absent.

    The metadata-only bundle path is the canonical
    branch -- a metadata-only bundle is intentionally
    NOT runner-ready (the readiness gate fires
    ``missing_raw`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform``).
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        BTI_XLSX_NAME,
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, with_xlsx=False)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_raw",
        expected_context_keys=("bundle_dir", "xlsx_name"),
    )
    assert result.errors[0].context["xlsx_name"] == (
        BTI_XLSX_NAME
    )


def test_bti_check_ready_unsupported_request_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``unsupported_version`` error when the request
    ``source_version`` differs from the canonical
    ``"BTI 2026"``.

    Per SRC-REQ-009: the canonical BTI stamp is
    ``"BTI 2026"``; the request ``source_version`` is
    rejected at the readiness gate with a structured
    error carrying the requested + canonical version
    in the context.
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        source_version="BTI 2024",
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
        "BTI 2024"
    )
    assert result.errors[0].context["canonical_version"] == (
        "BTI 2026"
    )


def test_bti_check_ready_mismatched_bundle_version_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``bti_metadata_version_mismatch`` error when the
    bundle ``source_version`` differs from both the
    brief canonical stamp (``"BTI 2026"``) AND the
    verbose acquisition stamp
    (``"BTI 2026 (covers 2024-2025); cumulative file
    covers 2006-2026 (biennial, 12 editions)"``)."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, source_version="BTI 2024")

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="bti_metadata_version_mismatch",
    )


def test_bti_check_ready_malformed_checksum_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single ``missing_metadata``
    error when the staged xlsx's
    ``checksum_sha256`` is a non-hex 64-char string.

    Distinct from ``bti_checksum_mismatch`` (which is
    reserved for well-formed values that disagree
    with the staged file).
    """
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, staged_sha="z" * 64)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="missing_metadata",
    )


def test_bti_check_ready_checksum_mismatch_emits_structured_error(
    tmp_path: Path,
) -> None:
    """``adapter.check_ready(request)`` returns
    ``ready=False`` with a single
    ``bti_checksum_mismatch`` error when the staged
    xlsx's actual SHA-256 disagrees with the
    metadata's well-formed
    ``checksum_sha256["BTI_2006-2026_Scores.xlsx"]``
    value."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root, staged_sha="0" * 64)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    _assert_readiness_error(
        result,
        expected_code="bti_checksum_mismatch",
    )


def test_bti_check_ready_happy_path_returns_ready_true(
    tmp_path: Path,
) -> None:
    """A well-formed staged bundle returns
    ``ready=True`` with no errors."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    adapter = create_bti_adapter()
    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
    )
    result = adapter.check_ready(request)
    assert result.ready is True
    assert result.errors == ()


# ---------------------------------------------------------------------------
# Per-observation contract
# ---------------------------------------------------------------------------


def test_bti_per_observation_emits_documented_extension_fields(
    tmp_path: Path,
) -> None:
    """Every emitted BTI observation carries the
    canonical extension fields + RawLocator
    contract.

    Per-observation contract:

    - ``extension["bti_sheet_name"]`` -- the resolved
      BTI edition sheet name (``"BTI 2024"`` for
      year=2023).
    - ``extension["bti_target_year"]`` -- the
      canonical in-coverage year the sheet
      represents (``2023``).
    - ``extension["bti_raw_column"]`` -- the catalog
      ``raw_column`` (whitespace-padded BTI xlsx
      header).
    - ``extension["bti_country_name"]`` -- the BTI
      display name (e.g. ``"Mexico"``).
    - ``extension["bti_rating_category"]`` -- the
      catalog ``category`` value
      (``effectiveness`` / ``political_freedom`` /
      ``economic_wellbeing``).
    - ``extension["source_row_reference"]`` --
      ``"bti:<country_name>"``.
    - ``extension["raw_value"]`` -- the verbatim BTI
      xlsx cell text (preserved for the audit
      trail).
    - ``extension["higher_is_better"]`` is ``True``
      (BTI raw 1-10; 10 = best per the canonical
      catalog).
    - ``extension["raw_scale"]`` is ``"1-10"``.
    - ``extension["normalized_scale_target"]`` is
      ``"0-10"``.
    - ``extension["attribution"]`` is the canonical
      BTI citation block (Rule #15).
    - ``RawLocator.path`` carries the staged xlsx
      path; ``RawLocator.sheet`` carries the resolved
      BTI edition sheet name; ``RawLocator.column_name``
      carries the catalog ``raw_column``.
    - ``source_version`` is the canonical
      ``"BTI 2026"`` stamp.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        BTI_ATTRIBUTION_TEXT,
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 60

    seen_country_names: set[str] = set()
    for obs in result.observations:
        # Direction hint + scale (BTI raw 1-10; 10 =
        # best).
        assert obs.extension["higher_is_better"] is True
        assert obs.extension["raw_scale"] == "1-10"
        assert (
            obs.extension["normalized_scale_target"]
            == "0-10"
        )
        # Attribution (Rule #15).
        assert (
            obs.extension["attribution"]
            == BTI_ATTRIBUTION_TEXT
        )
        # Source row reference pattern.
        assert obs.extension["source_row_reference"] == (
            f"bti:{obs.country_name}"
        )
        # Raw value audit trail is preserved verbatim.
        assert obs.extension["raw_value"] != ""
        # Raw column + sheet name + covered interval.
        assert obs.extension["bti_raw_column"] in (
            BTI_TEST_RAW_COLUMNS
        )
        assert obs.extension["bti_sheet_name"] == "BTI 2024"
        assert obs.extension["bti_target_year"] == 2023
        # Rating category is one of the 3 BTI catalog
        # categories.
        assert obs.extension["bti_rating_category"] in {
            "effectiveness",
            "political_freedom",
            "economic_wellbeing",
        }
        # Raw locator carries the staged xlsx path +
        # sheet + column.
        assert obs.raw_locator.path is not None
        assert obs.raw_locator.path.endswith(
            BTI_TEST_FIXTURE_XLSX_NAME
        )
        assert obs.raw_locator.sheet == "BTI 2024"
        assert obs.raw_locator.column_name in (
            BTI_TEST_RAW_COLUMNS
        )
        # Canonical source version propagates to every
        # observation.
        assert obs.source_version == "BTI 2026"
        # BTI does not carry ISO3 codes; the unified
        # transform carries the BTI display name on
        # ``country_name`` + ``None`` on
        # ``country_code``.
        assert obs.country_code is None
        assert obs.country_name is not None
        seen_country_names.add(obs.country_name)
    # All 5 fixture countries round-trip.
    assert seen_country_names == {
        "Mexico",
        "Brazil",
        "India",
        "Nigeria",
        "Kenya",
    }


def test_bti_per_observation_emits_correct_observation_family(
    tmp_path: Path,
) -> None:
    """Every emitted BTI observation's
    ``observation_family`` matches the catalog
    category for the indicator (the
    rating_category -> observation_family mapping
    drives downstream query filtering)."""
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
        raw_root=raw_root,
        years=(2023,),
    )
    result = runner.run(request)
    assert len(result.observations) == 60

    family_by_indicator: dict[str, str] = {}
    for obs in result.observations:
        # Each indicator must be mapped to exactly one
        # observation family (the family is derived
        # from the catalog's category column; the
        # same indicator observed across multiple
        # country-year rows maps to the same family).
        if obs.indicator_code not in family_by_indicator:
            family_by_indicator[obs.indicator_code] = (
                obs.observation_family
            )
        else:
            assert (
                family_by_indicator[obs.indicator_code]
                == obs.observation_family
            ), (
                f"indicator {obs.indicator_code!r} mapped "
                f"to multiple families: "
                f"{family_by_indicator[obs.indicator_code]!r} "
                f"vs {obs.observation_family!r}"
            )

    # Verify the canonical rating_category ->
    # observation_family mapping.
    for family, indicators in BTI_TEST_INDICATOR_BY_FAMILY.items():
        for indicator in indicators:
            assert family_by_indicator[indicator] == family, (
                f"indicator {indicator!r} should map to "
                f"family {family!r}; got "
                f"{family_by_indicator[indicator]!r}"
            )


# ---------------------------------------------------------------------------
# Import-boundary contract
# ---------------------------------------------------------------------------
#
# Note: the import-boundary contract for
# ``leaders_db.sources.adapters.bti`` is enforced by the
# canonical ``tests/sources/test_import_boundary.py``
# (the ``test_sources_submodules_do_not_import_legacy_ingest``
# test iterates a canonical list of submodules that
# includes ``"leaders_db.sources.adapters.bti"``). An
# adapter-local purge-based import boundary test is NOT
# added here because the purge pattern interacts with
# the legacy BTI Stage 2 tests' SQLAlchemy mapper state
# (the legacy ``bti_db`` module imports ``db.models``;
# purging + re-importing the ``leaders_db`` package can
# leave the mapper's ``Country`` forward reference
# unresolved for subsequent tests). The canonical
# import-boundary test in
# ``tests/sources/test_import_boundary.py`` runs the
# purge + import cycle on a single thread, in isolation
# from the legacy DB-layer tests, and asserts the BTI
# submodule specifically.


# ---------------------------------------------------------------------------
# No-network contract on the production runner path
# ---------------------------------------------------------------------------


def test_bti_runner_never_invokes_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SourceIngestRunner.run(request)`` succeeds
    end-to-end against a staged local xlsx even with
    every common network entry point rigged to raise
    on call.

    The BTI unified path is local-file only
    (``requires_network=False``, no HTTP layer).
    This test monkeypatches the canonical Python
    network surfaces (``requests.get`` /
    ``requests.post`` / ``urllib.request.urlopen` /
    ``socket.socket``) to raise ``RuntimeError`` if
    invoked, then drives the production
    :class:`SourceIngestRunner` end-to-end from a
    staged fixture. The run must complete cleanly --
    60 observations, no exception -- which proves
    the runner NEVER touches the network on the BTI
    path.

    A future refactor that introduces an HTTP layer
    in ``read_bti_xlsx`` / the legacy ``read_bti``
    bridge / the transform pipeline will see this
    test fail at the first network call.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.bti import (
        create_bti_adapter,
    )

    raw_root = tmp_path / "raw"
    _stage_bti_bundle(raw_root)

    # Arm the network tripwires. Each guarded
    # callable raises a distinctive sentinel so a
    # regression surfaces the exact entry point
    # that was hit.
    network_sentinel = "BTI_NETWORK_TRIPWIRE_FIRED"

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

    # Guard the legacy BTI reader too in case a
    # future refactor pulls it into the runner path
    # as a network layer (it only uses it as the
    # local xlsx reader).
    import leaders_db.ingest.bti_xlsx as legacy_bti_xlsx

    original_read_bti = legacy_bti_xlsx.read_bti
    read_bti_calls: list[dict[str, Any]] = []

    def _spy_read_bti(*args: Any, **kwargs: Any) -> Any:
        read_bti_calls.append({"args": args, "kwargs": kwargs})
        return original_read_bti(*args, **kwargs)

    monkeypatch.setattr(legacy_bti_xlsx, "read_bti", _spy_read_bti)

    registry = InMemorySourceRegistry()
    registry.register(create_bti_adapter())
    runner = SourceIngestRunner(registry=registry)

    request = SourceIngestRequest(
        source_id=SourceId(slug="bti"),
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
    # The fixture's 5 country-edition rows x 12
    # indicators round-trip 60 observations.
    assert len(result.observations) == 60, (
        f"expected 60 observations after a no-network "
        f"end-to-end run; got {len(result.observations)}"
    )

    # Defense in depth: the legacy reader was
    # actually invoked (it is the lazy bridge used
    # inside ``read_bti_xlsx``), but only as a local
    # xlsx reader -- it never made an outbound call.
    assert read_bti_calls, (
        "legacy read_bti should have been invoked "
        "exactly once for the local xlsx read; if "
        "not, the lazy bridge regressed"
    )
    for call in read_bti_calls:
        # The legacy reader accepts ``xlsx_path`` /
        # ``year`` / ``sheet_name`` / ``catalog_path``
        # -- any other kwarg would be a hidden network
        # seam. ``xlsx_path`` must always be the
        # staged local xlsx.
        allowed_kwargs = {"xlsx_path", "year", "sheet_name", "catalog_path"}
        assert set(call["kwargs"]).issubset(allowed_kwargs), (
            f"legacy read_bti was invoked with "
            f"unexpected kwargs (possible hidden "
            f"network seam): {call['kwargs']!r}"
        )


# ---------------------------------------------------------------------------
# Consumer-constant shape + module-internal helpers
# ---------------------------------------------------------------------------


def test_bti_load_indicator_catalog_returns_12_specs(
    tmp_path: Path,
) -> None:
    """The lazy catalog loader returns 12
    :class:`IndicatorSpec` records from the canonical
    checked-in catalog at
    ``src/leaders_db/ingest/catalogs/bti.csv``."""
    from leaders_db.sources.adapters.bti import (
        DEFAULT_CATALOG_PATH,
        load_indicator_catalog,
    )

    assert DEFAULT_CATALOG_PATH.is_file(), (
        f"expected checked-in catalog at "
        f"{DEFAULT_CATALOG_PATH}"
    )
    specs = load_indicator_catalog()
    assert len(specs) == 12, (
        f"expected 12 indicator specs; got {len(specs)}"
    )
    assert {s.variable_name for s in specs} == set(
        BTI_TEST_INDICATOR_NAMES
    )


def test_bti_rating_category_to_observation_family() -> None:
    """The rating_category -> observation_family
    mapping covers all 3 BTI catalog categories."""
    from leaders_db.sources.adapters.bti import (
        rating_category_to_observation_family,
    )

    assert rating_category_to_observation_family(
        "effectiveness",
    ) == "effectiveness_country_year"
    assert rating_category_to_observation_family(
        "political_freedom",
    ) == "political_freedom_country_year"
    assert rating_category_to_observation_family(
        "economic_wellbeing",
    ) == "economic_wellbeing_country_year"
    # Unknown categories fall back to the default
    # BTI family (``effectiveness_country_year``).
    assert rating_category_to_observation_family(
        "unknown_category",
    ) == "effectiveness_country_year"


def test_bti_coerce_float_handles_missing_sentinels() -> None:
    """The legacy BTI missing-value coercion handles
    pandas ``NaN`` + ``None`` + string sentinels
    (``""`` / ``"NA"`` / ``"NaN"`` / ``"nan"`` /
    ``"null"`` / ``"None"`` / ``"-999"`` /
    ``"-999.0"`` / ``"#N/A"`` / ``"n/a"``) as
    ``None``."""
    from leaders_db.sources.adapters.bti import _coerce_float

    assert _coerce_float(None) is None
    assert _coerce_float(float("nan")) is None
    assert _coerce_float(7) == 7.0
    assert _coerce_float(10) == 10.0
    assert _coerce_float("") is None
    assert _coerce_float("NA") is None
    assert _coerce_float("NaN") is None
    assert _coerce_float("nan") is None
    assert _coerce_float("null") is None
    assert _coerce_float("None") is None
    assert _coerce_float("-999") is None
    assert _coerce_float("-999.0") is None
    assert _coerce_float("#N/A") is None
    assert _coerce_float("n/a") is None
    # Numeric strings coerce to float.
    assert _coerce_float("7.5") == 7.5
    assert _coerce_float("10") == 10.0


def test_bti_raw_value_to_string_handles_missing_sentinels() -> None:
    """The legacy BTI raw-cell-text renderer handles
    ``None`` -> ``""`` and pandas ``NaN`` ->
    ``"nan"`` for the audit trail."""
    from leaders_db.sources.adapters.bti import _raw_value_to_string

    assert _raw_value_to_string(None) == ""
    assert _raw_value_to_string(float("nan")) == "nan"
    assert _raw_value_to_string(7.5) == "7.5"
    assert _raw_value_to_string(10) == "10"


def test_bti_resolve_value_type_returns_numeric_for_valid_cells() -> None:
    """``_resolve_value_type`` returns ``"numeric"``
    for valid BTI cells + ``"missing"`` for None /
    pandas NaN cells."""
    from leaders_db.sources.adapters.bti import _resolve_value_type

    assert _resolve_value_type(7) == "numeric"
    assert _resolve_value_type(10.0) == "numeric"
    assert _resolve_value_type(None) == "missing"
    assert _resolve_value_type(float("nan")) == "missing"


__all__ = [
    "_assert_readiness_error",
    "_purge_modules",
    "_stage_bti_bundle",
    "test_bti_adapter_satisfies_source_adapter_protocol",
    "test_bti_attribution_text_matches_attributions_doc",
    "test_bti_check_ready_checksum_mismatch_emits_structured_error",
    "test_bti_check_ready_happy_path_returns_ready_true",
    "test_bti_check_ready_malformed_checksum_emits_structured_error",
    "test_bti_check_ready_mismatched_bundle_version_emits_structured_error",
    "test_bti_check_ready_missing_metadata_emits_structured_error",
    "test_bti_check_ready_missing_xlsx_emits_structured_error",
    "test_bti_check_ready_unsupported_request_version_emits_structured_error",
    "test_bti_checksum_mismatch_fails_readiness",
    "test_bti_coerce_float_handles_missing_sentinels",
    "test_bti_correct_checksum_passes_readiness",
    "test_bti_descriptor_exposes_documented_static_metadata",
    "test_bti_descriptor_indicator_names_and_raw_columns",
    "test_bti_invalid_ingestion_status_fails_readiness",
    "test_bti_load_indicator_catalog_returns_12_specs",
    "test_bti_malformed_checksum_fails_readiness",
    "test_bti_malformed_local_files_fails_readiness",
    "test_bti_mismatched_bundle_version_fails_readiness",
    "test_bti_missing_metadata_fails_readiness_with_missing_metadata",
    "test_bti_missing_required_field_fails_readiness",
    "test_bti_missing_xlsx_fails_readiness_with_missing_raw",
    "test_bti_per_observation_emits_correct_observation_family",
    "test_bti_per_observation_emits_documented_extension_fields",
    "test_bti_public_surface_is_coherent",
    "test_bti_rating_category_to_observation_family",
    "test_bti_raw_value_to_string_handles_missing_sentinels",
    "test_bti_register_helper_registers_against_explicit_registry",
    "test_bti_resolve_value_type_returns_numeric_for_valid_cells",
    "test_bti_runner_does_not_consult_legacy_stage2_adapters",
    "test_bti_runner_never_invokes_network",
    "test_bti_runner_produces_normalized_observations",
    "test_bti_runner_target_year_maps_to_correct_biennial_sheet",
    "test_bti_unsupported_source_version_fails_readiness",
    "test_bti_wrong_local_files_fails_readiness",
]
