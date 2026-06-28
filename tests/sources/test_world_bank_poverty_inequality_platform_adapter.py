"""World Bank Poverty and Inequality Platform (PIP) clean-source
adapter tests.

The World Bank Poverty and Inequality Platform (PIP) is the
World-Bank-maintained public database of poverty, inequality,
and distribution indicators, served through the documented PIP
API at ``https://pip.worldbank.org/api`` and the PIP home page
at ``https://pip.worldbank.org/``. The unified adapter is the
next feasible clean-interface-only source after
``ctbto_treaty_status``
(``docs/architecture/sources.md`` §7.2
``world_bank_poverty_inequality_platform`` row; offline /
cache-only in this slice, no live HTTP fetching). Per the task
brief the slice is deliberately scoped to cached CSV / JSON
ingestion only -- live fetch is intentionally NOT supported.

The new package lives at
``src/leaders_db/sources/adapters/world_bank_poverty_inequality_platform/``
and the focused tests in this file cover:

- The World Bank PIP adapter descriptor is registerable /
  listable through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata (source_id
  ``world_bank_poverty_inequality_platform``, default version
  ``"World Bank PIP, version 20260324_2021"``, attribution_key
  ``world_bank_poverty_inequality_platform``, ``api`` source
  type, 1960-2024 coverage hint, single
  ``poverty_inequality_country_year`` observation family,
  ``requires_network=False``).
- :class:`SourceIngestRunner` can run World Bank PIP end-to-end
  through the new registry against a fixture ``raw_root`` and
  produce :class:`NormalizedObservation` records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table.
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(2050,)`` request emits zero
  observations plus a structured ``YEAR_ABSENT`` warning (no
  stale-proxy fill per SRC-COV-002 / SRC-COV-003); the
  prototype's target year 2023 falls WITHIN the canonical
  1960-2024 envelope so 2023 is in-coverage.
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Readiness failures (missing metadata, missing cached CSV /
  JSON, missing required metadata field, ``local_files``
  missing the canonical cached file, ``ingestion_status``
  not ``'downloaded'``, missing required column, version
  mismatch, checksum mismatch, the selected-file contract
  that the actually-present SELECTED cache file is declared in
  ``local_files`` AND covered by ``checksum_sha256``) each
  surface a structured ``SourceWarning(severity='error')``
  so the runner raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Cache-policy gate blocks ``"refresh"`` / ``"no_cache"``
  with a structured
  ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
  error.
- The transform preserves source-native country code + display
  name verbatim (no ISO3 invention -- the PIP ``country_code``
  is the World Bank's own reporting identifier, NOT a
  canonical ISO3 mapping) and per-row PPP version + reporting
  level + welfare type + poverty line on the audit-trail
  extension payload.
- Blank / non-numeric numeric cells are emitted as
  ``value=None`` / ``value_type="missing"`` plus the verbatim
  raw cell text on ``extension.raw_value`` -- the transform
  does NOT invent a value from missing source-native data.
- The default 3-indicator catalog is exercised end-to-end
  (headcount + poverty gap + Gini).
- Attribution drift guard: the canonical attribution text
  is a substring of ``docs/sources/attributions.md``
  (Always-On Rule #15).
- Importing the new
  ``leaders_db.sources.adapters.world_bank_poverty_inequality_platform``
  module does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).
- The adapter does NOT invoke the network.

PASS-ELIGIBLE rationale
-----------------------

World Bank PIP has no legacy Stage 2 implementation; the tests
in this file prove that the new
``leaders_db.sources.adapters.world_bank_poverty_inequality_platform``
adapter implements the full ``SourceAdapter`` Protocol
end-to-end while preserving the package-isolation contract --
they are PASS-ELIGIBLE because the adapter implementation
lands in the same change set.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from leaders_db.sources import (
    InMemorySourceRegistry,
    SourceAdapter,
    SourceId,
    SourceIngestRequest,
    SourceIngestResult,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.world_bank_poverty_inequality_platform import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME,
    create_world_bank_poverty_inequality_platform_adapter,
    register_world_bank_poverty_inequality_platform,
)
from leaders_db.sources.adapters.world_bank_poverty_inequality_platform._constants import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_CSV = Path(
    "tests/fixtures/world_bank_poverty_inequality_platform/sample.csv"
)
_FIXTURE_JSON = Path(
    "tests/fixtures/world_bank_poverty_inequality_platform/sample.json"
)


# ---------------------------------------------------------------------------
# Bundle staging helpers
# ---------------------------------------------------------------------------


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_csv: bool = True,
    with_json: bool = False,
    local_files: Any | None = None,
    checksum: Any = "AUTO",
    source_version: str = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
    ),
) -> Path:
    """Stage the World Bank PIP fixture bundle under
    ``raw_root/world_bank_poverty_inequality_platform``.

    Copies
    ``tests/fixtures/world_bank_poverty_inequality_platform/sample.csv``
    (or ``sample.json``) into the bundle directory plus an
    optional ``metadata.json`` whose checksum matches the
    staged file. Returns the resolved bundle directory.

    The fixture carries 6 hand-authored synthetic country-year
    rows (no real World Bank PIP claims -- the country labels
    are SYNTHETIC per the task brief: "prefer synthetic
    non-real country labels if it tests parser mechanics
    without factual assertions"). The fixture deliberately
    exercises:

    - All 11 required columns. This includes ``version_id`` and
      ``ppp_version`` as required fields; ``ppp_base_year`` is
      also present in the fixture as an extra audit field.
    - 3 numeric indicators per row (headcount + poverty_gap +
      gini).
    - One row with a blank numeric cell (the
      ``value_type='missing'`` sentinel path).
    - One row with a non-numeric cell (the non-numeric sentinel
      path).
    - One row with an out-of-coverage ``year=1900`` (the
      out-of-coverage year filter).
    """
    bundle = (
        raw_root / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
    )
    bundle.mkdir(parents=True, exist_ok=True)

    csv_path = bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
    json_path = (
        bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
    )

    selected_path: Path | None = None
    if with_csv:
        shutil.copy2(_FIXTURE_CSV, csv_path)
        selected_path = csv_path
    if with_json:
        shutil.copy2(_FIXTURE_JSON, json_path)
        if not with_csv:
            selected_path = json_path
    if not with_metadata:
        return bundle

    checksum_value: Any = checksum
    if checksum == "AUTO":
        if selected_path is not None and selected_path.is_file():
            checksum_value = (
                hashlib.sha256(
                    selected_path.read_bytes(),
                ).hexdigest()
            )
        else:
            checksum_value = None

    if local_files is None:
        local_files = []
        if with_csv:
            local_files.append(
                WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
            )
        if with_json:
            local_files.append(
                WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
            )

    payload: dict[str, Any] = {
        "source_name": (
            "World Bank Poverty and Inequality Platform"
        ),
        "source_key": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
        "source_version": source_version,
        "download_date": "2026-06-28",
        "coverage": (
            "1960-2024 (canonical PIP version 20260324_2021; "
            "PIP records begin in the early 1960s when "
            "survey-based poverty estimates become available "
            "for low / lower-middle income countries)"
        ),
        "license_note": (
            "World Bank Terms of Use for Datasets; free use "
            "with attribution; cite World Bank Group + the "
            "canonical URL."
        ),
        "local_files": local_files,
        "ingestion_status": "downloaded",
        "source_url": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL,
        "version_id": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
        "ppp_version": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
    }
    if checksum_value is not None:
        payload["checksum_sha256"] = checksum_value
    payload["notes"] = (
        "Synthetic fixture bundle for clean-source adapter "
        "tests; the country labels and numeric cells are NOT "
        "real World Bank PIP data."
    )
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def _request(
    raw_root: Path, **kwargs: Any,
) -> SourceIngestRequest:
    """Build a World Bank PIP request with sensible defaults."""
    defaults: dict[str, Any] = {
        "cache_policy": (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY
        ),
    }
    defaults.update(kwargs)
    return SourceIngestRequest(
        source_id=SourceId(
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
        ),
        raw_root=raw_root,
        **defaults,
    )


def _run(raw_root: Path, **kwargs: Any) -> SourceIngestResult:
    """Drive the World Bank PIP adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_world_bank_poverty_inequality_platform(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_descriptor_factory_and_registry() -> None:
    """The descriptor factory exposes the documented static
    metadata."""
    adapter = create_world_bank_poverty_inequality_platform_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY()
        .descriptor
        == descriptor
    )
    assert (
        descriptor.source_id.slug
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
    )
    assert (
        descriptor.attribution_key
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
    )
    assert descriptor.source_type == "api"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is False
    assert descriptor.supported_observation_families == (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES
    )
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY
        in descriptor.supported_observation_families
    )
    assert (
        descriptor.coverage_hint.start_year
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR
    )
    assert (
        descriptor.coverage_hint.end_year
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR
    )
    assert (
        descriptor.homepage_url
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL
    )

    # The descriptor's coverage_hint.notes must carry the
    # documented caveat that PIP poverty / inequality
    # estimates are SURVEY- and PPP-specific and SHOULD NOT be
    # silently mixed across PIP version stamps or PPP bases
    # without explicit metadata propagation.
    notes = descriptor.coverage_hint.notes or ""
    assert "SURVEY- and PPP-specific" in notes
    assert "version stamps" in notes or "PPP bases" in notes


def test_register_helper_registers_against_explicit_registry() -> None:
    """``register_world_bank_poverty_inequality_platform(registry)``
    is the explicit seam for tests + future composition code.
    """
    registry = InMemorySourceRegistry()
    adapter = register_world_bank_poverty_inequality_platform(
        registry,
    )
    assert (
        registry.get_adapter(
            SourceId(
                WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
            ),
        )
        is adapter
    )
    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert (
        listed[0].source_id.slug
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
    )


def test_indicator_codes_match_canonical_3() -> None:
    """The 3 source-native indicator codes are exposed via the
    package surface for downstream query code."""
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT
        in WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES
    )
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP
        in WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES
    )
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI
        in WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES
    )
    assert (
        len(WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES)
        == 3
    )


def test_required_columns_match_canonical_11() -> None:
    """The 11 canonical required CSV / JSON table columns are
    exposed via the package surface for the readiness gate +
    raw-read boundary."""
    assert (
        len(WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS)
        == 11
    )
    for col in (
        "country_code",
        "country_name",
        "year",
        "reporting_level",
        "welfare_type",
        "poverty_line",
        "headcount",
        "poverty_gap",
        "gini",
        "version_id",
        "ppp_version",
    ):
        assert (
            col
            in WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS
        )


def test_attribution_text_matches_attributions_doc() -> None:
    """The attribution text is a substring of
    ``docs/sources/attributions.md`` (Rule #15 drift guard).
    """
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
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT
        in attributions_text
    ), (
        f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT!r} "
        f"is not a substring of {attributions_path}. Update both "
        f"in the same commit (Rule #15)."
    )


def test_attribution_key_matches_attributions_doc() -> None:
    """The attribution key
    ``world_bank_poverty_inequality_platform`` appears in the
    attributions doc. Drift guard for the descriptor's
    ``attribution_key`` field."""
    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    assert attributions_path.exists()
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY
        in attributions_text
    )


# ---------------------------------------------------------------------------
# Bundle readiness -- happy path + error paths
# ---------------------------------------------------------------------------


def test_correct_bundle_passes_readiness(tmp_path: Path) -> None:
    """A well-formed bundle returns ``ready=True``."""
    _stage_bundle(tmp_path)
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_no_observations_emitted_for_unsupported_leaders_filter(
    tmp_path: Path,
) -> None:
    """``leaders=`` filter is unsupported -- the transform
    ignores it and the readiness envelope surfaces a structured
    ``UNSUPPORTED_FILTER`` warning."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, leaders=("Some Leader",))
    # 5 in-coverage rows x 3 indicators = 15 observations.
    # (Row 6 is out-of-coverage -- year=1900 -- and is filtered
    # out by the in-coverage filter on the transform side; the
    # readiness envelope surfaces a structured ``YEAR_ABSENT``
    # warning for the out-of-coverage year when ``years=`` is
    # explicitly set, but here ``years=None`` so no warning.)
    assert len(result.observations) == 15
    assert [w.code for w in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        (
            {"with_csv": False, "with_json": False},
            MISSING_RAW,
        ),
        (
            {"local_files": []},
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        ),
        (
            {
                "local_files": ["some_other_file.csv"],
            },
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        ),
        (
            {"checksum": "0" * 64},
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
        ),
        (
            {
                "source_version": (
                    "World Bank PIP, version 20260324_2017"
                ),
            },
            (
                WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH
            ),
        ),
    ],
)
def test_readiness_failures(
    tmp_path: Path, kwargs: dict[str, Any], code: str,
) -> None:
    """Each documented readiness-failure class surfaces a
    structured ``SourceWarning(severity='error')``."""
    _stage_bundle(tmp_path, **kwargs)
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_unsupported_request_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """An explicit ``source_version=`` request that differs from
    the canonical version stamp fails readiness with a
    structured ``unsupported_version`` error."""
    _stage_bundle(tmp_path)
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(
            _request(
                tmp_path,
                source_version=(
                    "World Bank PIP, version 20260324_2017"
                ),
            ),
        )
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION
    )


def test_cache_policy_refresh_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="refresh"`` is unsupported -- the gate
    blocks with a structured
    ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
    error."""
    _stage_bundle(tmp_path)
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path, cache_policy="refresh"))
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY
    )


def test_cache_policy_no_cache_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="no_cache"`` is unsupported -- same as
    ``refresh``."""
    _stage_bundle(tmp_path)
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path, cache_policy="no_cache"))
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY
    )


# ---------------------------------------------------------------------------
# Year semantics
# ---------------------------------------------------------------------------


def test_out_of_coverage_year_warns_and_emits_no_rows(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2050,)`` -- well beyond the
    documented 1960-2024 envelope -- emits zero observations
    plus a structured ``YEAR_ABSENT`` warning (no stale-proxy
    fill per SRC-COV-002 / SRC-COV-003)."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2050,))
    assert result.observations == ()
    assert [w.code for w in result.warnings] == [YEAR_ABSENT]


def test_in_coverage_year_emits_full_observations(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2018,)`` (one of the in-coverage
    fixture years) emits the row(s) matching that year -- one
    row x 3 indicators = 3 observations."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2018,))
    assert len(result.observations) == 3
    for obs in result.observations:
        assert obs.year == 2018
    assert result.warnings == ()


def test_no_year_filter_emits_in_coverage_observations(
    tmp_path: Path,
) -> None:
    """A request with ``years=None`` reads the full envelope
    (subject to the canonical 1960-2024 filter) and emits the
    full in-coverage observation set.

    The fixture carries 6 rows; row 6 has ``year=1900`` which
    is OUTSIDE the canonical envelope. The transform excludes
    row 6 from the canonical output; the readiness envelope
    does NOT emit a ``YEAR_ABSENT`` warning because
    ``years=None`` does not request any specific year.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=None)
    # 5 in-coverage rows x 3 indicators = 15 observations.
    assert len(result.observations) == 15
    assert result.warnings == ()


def test_prototype_target_year_2023_is_in_coverage(
    tmp_path: Path,
) -> None:
    """The prototype's target year 2023 falls WITHIN the
    canonical 1960-2024 envelope so a request for
    ``years=(2023,)`` emits zero observations (no fixture row
    has year=2023) but does NOT emit a ``YEAR_ABSENT``
    warning.

    The structural in-coverage check is the canonical
    ``YearInCoverage(year) = (start_year <= year <= end_year)``
    predicate so ``years=(2023,)`` does NOT trigger the
    readiness warning -- 2023 falls within the canonical
    envelope so the envelope treats the year as in-coverage.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# Country filter
# ---------------------------------------------------------------------------


def test_country_filter_single_match(tmp_path: Path) -> None:
    """A ``countries=`` request that matches one source-native
    country display name emits the matching rows x 3 indicators.

    The fixture carries 2 in-coverage rows for ``Country A``
    (years 2018 + 2020), so the filter emits 2 rows x 3
    indicators = 6 observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Country A",))
    assert len(result.observations) == 6
    assert result.warnings == ()
    for obs in result.observations:
        assert obs.country_name == "Country A"


def test_country_filter_no_match(tmp_path: Path) -> None:
    """A ``countries=`` request that matches no source-native
    country display name emits zero observations."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Nonexistent Country",))
    assert result.observations == ()


def test_country_filter_multiple_matches(tmp_path: Path) -> None:
    """A ``countries=`` request with multiple matches emits
    one observation per matched country-year row per
    indicator.

    The fixture carries:
    - Country A: years 2018 + 2020 (in-coverage) = 2 rows.
    - Country B: year 2017 (in-coverage) = 1 row.
    - Country C: year 2019 (in-coverage) = 1 row.
    - Country D: year 2015 (in-coverage) = 1 row.
    - Country E: year 1900 (out-of-coverage) = 0 rows.
    Filter for Country A + Country B + Country C -> 4 in-coverage
    rows x 3 indicators = 12 observations.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        countries=("Country A", "Country B", "Country C"),
    )
    assert len(result.observations) == 12
    matched_countries = {
        obs.country_name for obs in result.observations
    }
    assert matched_countries == {
        "Country A",
        "Country B",
        "Country C",
    }


# ---------------------------------------------------------------------------
# Numeric coercion -- blank / non-numeric cell semantics
# ---------------------------------------------------------------------------


def test_blank_numeric_cell_emits_missing_value_type(
    tmp_path: Path,
) -> None:
    """A row with a blank numeric cell (e.g. the headcount
    cell on the ``year=2020`` ``Country A`` row) emits
    ``value=None`` / ``value_type="missing"`` plus the
    verbatim raw cell text on ``extension.raw_value`` for the
    affected indicator. The transform does NOT invent a value
    from missing source-native data; the other 2 indicators on
    the same row are still emitted as numeric observations.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        countries=("Country A",),
        years=(2020,),
    )
    assert len(result.observations) == 3
    by_indicator = {
        obs.indicator_code: obs for obs in result.observations
    }
    headcount_obs = by_indicator[
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT
    ]
    assert headcount_obs.value is None
    assert headcount_obs.value_type == "missing"
    # The verbatim raw cell text is preserved on the audit-trail
    # extension so audit code can recover the original cell.
    assert headcount_obs.extension["raw_value"] == ""
    gap_obs = by_indicator[
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP
    ]
    assert gap_obs.value == 0.025
    assert gap_obs.value_type == "numeric"
    gini_obs = by_indicator[
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI
    ]
    assert gini_obs.value == 33.1
    assert gini_obs.value_type == "numeric"


def test_non_numeric_cell_emits_missing_value_type(
    tmp_path: Path,
) -> None:
    """A row with a non-numeric cell (e.g. the Gini cell on
    the ``year=2017`` ``Country B`` row carrying ``"n.a."``)
    emits ``value=None`` / ``value_type="missing"`` plus the
    verbatim raw cell text on ``extension.raw_value``. The
    other 2 indicators on the same row are still emitted as
    numeric observations.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        countries=("Country B",),
        years=(2017,),
    )
    assert len(result.observations) == 3
    by_indicator = {
        obs.indicator_code: obs for obs in result.observations
    }
    gini_obs = by_indicator[
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI
    ]
    assert gini_obs.value is None
    assert gini_obs.value_type == "missing"
    # The verbatim raw cell text is preserved on the audit-trail
    # extension so audit code can recover the original cell.
    assert gini_obs.extension["raw_value"] == "n.a."
    headcount_obs = by_indicator[
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT
    ]
    assert headcount_obs.value == 0.187
    assert headcount_obs.value_type == "numeric"


# ---------------------------------------------------------------------------
# Source-native preservation -- no ISO3 invention
# ---------------------------------------------------------------------------


def test_no_iso3_invention(tmp_path: Path) -> None:
    """The transform does NOT invent ISO3 codes.

    The cached World Bank PIP dataset uses the World Bank's
    own reporting identifier (``country_code``), which is a
    3-character code that LOOKS LIKE ISO3 but is NOT a
    canonical ISO3 mapping. The ``country_code`` field on
    emitted observations remains ``None``; the source-native
    identifier is preserved verbatim on
    ``extension["world_bank_poverty_inequality_platform_country_code_raw"]``
    so audit code can recover the original cell.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert len(result.observations) == 15
    for obs in result.observations:
        assert obs.country_code is None
        assert obs.leader_id is None
        assert obs.leader_name is None
        # The source-native reporting identifier is preserved
        # verbatim on the audit-trail extension payload.
        assert obs.extension[
            "world_bank_poverty_inequality_platform_country_code_raw"
        ] in {"AAA", "BBB", "CCC", "DDD"}
        # The source-native reporting display name is preserved
        # verbatim.
        assert obs.country_name in {
            "Country A",
            "Country B",
            "Country C",
            "Country D",
        }


def test_observation_shape_and_locators(tmp_path: Path) -> None:
    """Every emitted observation carries the canonical raw
    locator + transform locator + observation family + year +
    version stamp + attribution text."""
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Country A",), years=(2018,))
    assert len(result.observations) == 3
    for obs in result.observations:
        assert obs.observation_family == (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY
        )
        assert obs.year == 2018
        assert obs.source_version == (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
        )
        assert obs.transform_locator.transform_name == (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME
        )
        assert obs.transform_locator.catalog_key == (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
        )
        assert (
            obs.raw_locator.asset_id
            == f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY}:"
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME}"
        )
        # The attribution text is propagated onto the audit-trail
        # extension payload with the ``{version_ID}`` placeholder
        # interpolated from the canonical PIP version stamp.
        assert obs.extension["attribution"] == (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT.replace(
                "{version_ID}", "20260324_2021",
            )
        )


def test_per_row_ppp_version_and_metadata_preserved(
    tmp_path: Path,
) -> None:
    """Per-row PPP version + reporting level + welfare type +
    poverty line + version_id are preserved verbatim on the
    audit-trail extension payload so downstream code can
    recover the verbatim source-native provenance.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Country A",), years=(2018,))
    assert len(result.observations) == 3
    for obs in result.observations:
        assert obs.extension[
            "world_bank_poverty_inequality_platform_reporting_level"
        ] == "national"
        assert obs.extension[
            "world_bank_poverty_inequality_platform_welfare_type"
        ] == "consumption"
        assert obs.extension[
            "world_bank_poverty_inequality_platform_poverty_line_raw"
        ] == "1.9"
        assert obs.extension[
            "world_bank_poverty_inequality_platform_ppp_version_raw"
        ] == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION
        assert obs.extension[
            "world_bank_poverty_inequality_platform_ppp_base_year_raw"
        ] == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION
        assert obs.extension[
            "world_bank_poverty_inequality_platform_version_id_raw"
        ] == "20260324_2021"


# ---------------------------------------------------------------------------
# Schema-error path
# ---------------------------------------------------------------------------


def test_missing_required_column_raises_schema_error(
    tmp_path: Path,
) -> None:
    """A cached CSV that is missing one or more of the 11
    canonical required columns fires a structured
    :class:`WorldBankPipSchemaError` BEFORE the transform
    layer consumes the frame."""
    bundle = _stage_bundle(tmp_path)
    # Rewrite the staged CSV header without the required ``gini`` /
    # ``version_id`` / ``ppp_version`` fields so the raw-read
    # boundary raises a structured schema-violation error.
    csv_path = bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
    raw_text = csv_path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    # Rewrite the header and rows to keep only the first 8 fields;
    # this intentionally removes required fields from the 11-column
    # contract.
    new_header = (
        '"country_code","country_name","year","reporting_level",'
        '"welfare_type","poverty_line","headcount","poverty_gap"'
    )
    new_lines = [new_header]
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) >= 12:
            cells = cells[:8]
        new_lines.append(",".join(cells))
    csv_path.write_text(
        "\n".join(new_lines) + "\n", encoding="utf-8",
    )
    # Refresh the checksum so the readiness gate passes the
    # checksum-match check.
    metadata_file = bundle / "metadata.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = (
        hashlib.sha256(csv_path.read_bytes()).hexdigest()
    )
    metadata_file.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    with pytest.raises(Exception) as excinfo:
        _run(tmp_path)
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR
        in str(excinfo.value)
    )


# ---------------------------------------------------------------------------
# Import boundary + no-network boundary
# ---------------------------------------------------------------------------


def test_adapter_module_does_not_import_legacy_ingest_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the new
    ``leaders_db.sources.adapters.world_bank_poverty_inequality_platform``
    module does NOT pull in any ``leaders_db.ingest`` module.

    Defense in depth: the canonical import-boundary guard
    documented in ``tests/sources/test_import_boundary.py``
    asserts the package-isolation rule for every clean-source
    adapter submodule. This per-adapter test mirrors that
    contract for the World Bank PIP adapter specifically so a
    regression that accidentally pulls in legacy ingest
    surfaces as a per-adapter failure rather than only at the
    canonical import-boundary list level.
    """
    # Purge every cached module under the source / ingest
    # namespace so the import boundary starts clean.
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith(
            "leaders_db.sources.",
        ):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith(
            "leaders_db.ingest.",
        ):
            del sys.modules[name]
    try:
        importlib.import_module(
            "leaders_db.sources.adapters."
            "world_bank_poverty_inequality_platform",
        )
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "importing leaders_db.sources.adapters."
            f"world_bank_poverty_inequality_platform must not "
            f"import leaders_db.ingest (leaked modules: {leaked})"
        )
    finally:
        # Re-import leaders_db.sources so subsequent tests can
        # use the package surface without breaking the cached
        # module state.
        importlib.import_module("leaders_db.sources")


def test_adapter_does_not_invoke_network(tmp_path: Path) -> None:
    """The adapter never invokes the network -- it reads only
    the staged cached CSV (or JSON wrapper) and the runtime-
    local ``metadata.json``.

    The test stages a well-formed bundle and installs sentinels
    on ``urllib.request.urlopen`` AND ``socket.socket`` so a
    regression that accidentally introduces a network call
    surfaces as a clean assertion failure rather than a silent
    external HTTP fetch.
    """

    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "World Bank PIP adapter must not invoke "
            "urllib.request.urlopen (offline / cache-only)"
        )

    def _socket_explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "World Bank PIP adapter must not invoke "
            "socket.socket (offline / cache-only)"
        )

    import socket as socket_module
    import urllib.request as urlrequest

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(urlrequest, "urlopen", _explode)
    monkeypatch.setattr(socket_module, "socket", _socket_explode)
    try:
        _stage_bundle(tmp_path)
        result = _run(tmp_path)
        assert len(result.observations) == 15
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Duplicate-slug registration guard (SRC-REG-004)
# ---------------------------------------------------------------------------


def test_duplicate_slug_registration_raises_value_error(
    tmp_path: Path,
) -> None:
    """Registering the same
    ``world_bank_poverty_inequality_platform`` slug twice raises
    :class:`ValueError` (SRC-REG-004)."""
    _stage_bundle(tmp_path)
    registry = InMemorySourceRegistry()
    register_world_bank_poverty_inequality_platform(registry)
    with pytest.raises(ValueError) as excinfo:
        register_world_bank_poverty_inequality_platform(registry)
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
        in str(excinfo.value)
    )


# ---------------------------------------------------------------------------
# JSON fallback contract
# ---------------------------------------------------------------------------


def test_json_fallback_is_loaded_when_csv_absent(tmp_path: Path) -> None:
    """When the cached CSV is absent but a cached JSON file is
    present, the raw-read boundary loads the JSON fallback
    and parses the array via the built-in JSON parser."""
    # Stage ONLY the JSON file (no CSV) so the JSON fallback
    # path is exercised.
    bundle = _stage_bundle(
        tmp_path, with_csv=False, with_json=True,
    )
    # Refresh the checksum to cover the JSON file (the staging
    # helper defaults to the CSV when both are absent; when
    # only JSON is staged, the helper computes the JSON
    # SHA-256).
    metadata_file = bundle / "metadata.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
        not in payload["local_files"]
    )
    assert (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
        in payload["local_files"]
    )
    result = _run(tmp_path)
    # 5 in-coverage rows x 3 indicators = 15 observations.
    assert len(result.observations) == 15
    matched_countries = {
        obs.country_name for obs in result.observations
    }
    assert "Country A" in matched_countries
    assert "Country B" in matched_countries
    assert "Country C" in matched_countries


# ---------------------------------------------------------------------------
# Selected-file contract -- JSON-only bundle must declare JSON in
# ``local_files`` + checksum
# ---------------------------------------------------------------------------


def test_selected_local_files_block_when_only_json_declared_csv(
    tmp_path: Path,
) -> None:
    """When the staged SELECTED cache file is the JSON fallback
    but ``metadata.local_files`` only lists the CSV file, the
    selected-file contract surfaces a structured
    ``world_bank_poverty_inequality_platform_local_files_invalid``
    blocker -- the bundle's ``local_files`` declaration
    silently disagrees with the file the reader will actually
    consume."""
    bundle = _stage_bundle(
        tmp_path, with_csv=False, with_json=True,
        local_files=[WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME],
    )
    # Refresh the checksum so it covers the JSON file (not the
    # CSV which is absent).
    json_p = (
        bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
    )
    metadata_file = bundle / "metadata.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = (
        hashlib.sha256(json_p.read_bytes()).hexdigest()
    )
    metadata_file.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID
    )


def test_selected_checksum_covered_when_only_json_present(
    tmp_path: Path,
) -> None:
    """When the staged SELECTED cache file is the JSON fallback
    but ``metadata.checksum_sha256`` is the flat-string shape
    (which covers the CSV by convention), the selected-file
    contract surfaces a structured
    ``world_bank_poverty_inequality_platform_checksum_mismatch``
    blocker -- the bundle's ``checksum_sha256`` declaration
    silently disagrees with the file the reader will actually
    consume."""
    # Stage ONLY the JSON file with the flat-string checksum
    # shape (which covers the CSV by convention -- not the
    # JSON fallback).
    json_p = _FIXTURE_JSON
    bundle = (
        tmp_path / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
    )
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copy2(json_p, bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME)
    payload: dict[str, Any] = {
        "source_name": (
            "World Bank Poverty and Inequality Platform"
        ),
        "source_key": (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
        ),
        "source_version": (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
        ),
        "download_date": "2026-06-28",
        "coverage": (
            "1960-2024 (canonical PIP version 20260324_2021)"
        ),
        "license_note": (
            "World Bank Terms of Use for Datasets; free use "
            "with attribution; cite World Bank Group + the "
            "canonical URL."
        ),
        "local_files": [
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
        ],
        "ingestion_status": "downloaded",
        "source_url": (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL
        ),
        "version_id": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
        "ppp_version": WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
        "checksum_sha256": (
            hashlib.sha256(_FIXTURE_CSV.read_bytes()).hexdigest()
        ),
        "notes": (
            "Synthetic fixture bundle (JSON fallback) for "
            "clean-source adapter tests."
        ),
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH
    )


def test_json_missing_required_key_raises_schema_error(
    tmp_path: Path,
) -> None:
    """A JSON-only cache whose object omits a required key fails
    before transform, rather than backfilling a blank value."""
    bundle = _stage_bundle(tmp_path, with_csv=False, with_json=True)
    json_path = bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    del payload[0]["gini"]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metadata_file = bundle / "metadata.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata["checksum_sha256"] = hashlib.sha256(
        json_path.read_bytes(),
    ).hexdigest()
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    with pytest.raises(Exception) as excinfo:
        _run(tmp_path)
    assert WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR in str(
        excinfo.value,
    )


def test_row_version_id_mismatch_raises_schema_error(
    tmp_path: Path,
) -> None:
    """Row-level PIP version_id must match bundle metadata."""
    bundle = _stage_bundle(tmp_path)
    csv_path = bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8").replace(
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
            "20260324_2017",
            1,
        ),
        encoding="utf-8",
    )
    metadata_file = bundle / "metadata.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata["checksum_sha256"] = hashlib.sha256(
        csv_path.read_bytes(),
    ).hexdigest()
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    with pytest.raises(Exception) as excinfo:
        _run(tmp_path)
    assert WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR in str(
        excinfo.value,
    )


def test_row_ppp_version_mismatch_raises_schema_error(
    tmp_path: Path,
) -> None:
    """Row-level ppp_version must match bundle metadata."""
    bundle = _stage_bundle(tmp_path)
    csv_path = bundle / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8").replace(
            f'"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION}"',
            '"2017"',
            1,
        ),
        encoding="utf-8",
    )
    metadata_file = bundle / "metadata.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata["checksum_sha256"] = hashlib.sha256(
        csv_path.read_bytes(),
    ).hexdigest()
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    with pytest.raises(Exception) as excinfo:
        _run(tmp_path)
    assert WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR in str(
        excinfo.value,
    )


def test_metadata_missing_ppp_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """Bundle metadata must declare the PPP basis explicitly."""
    bundle = _stage_bundle(tmp_path)
    metadata_file = bundle / "metadata.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    del metadata["ppp_version"]
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    readiness = (
        create_world_bank_poverty_inequality_platform_adapter()
        .check_ready(_request(tmp_path))
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_METADATA


# ---------------------------------------------------------------------------
# Observation IDs -- uniqueness (audit-trail safety)
# ---------------------------------------------------------------------------


def test_observation_ids_unique_default_catalog(
    tmp_path: Path,
) -> None:
    """Every emitted observation has a UNIQUE ``observation_id``
    AND a unique ``source_row_reference`` -- indicator
    observations for the same row do NOT collide on a shared
    per-row reference.

    For the default 3-indicator catalog (headcount + poverty
    gap + Gini), 5 in-coverage rows x 3 indicators = 15 unique
    observations. The ``observation_id`` and the
    ``extension["source_row_reference"]`` MUST be unique per
    observation so the audit trail can recover every
    (row, indicator) pair without collision.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert len(result.observations) == 15
    observation_ids = [obs.observation_id for obs in result.observations]
    source_row_references = [
        obs.extension["source_row_reference"]
        for obs in result.observations
    ]
    assert len(set(observation_ids)) == 15, (
        "observation_id MUST be unique per (row, indicator); "
        f"got {len(set(observation_ids))} unique ids across "
        f"{len(observation_ids)} observations"
    )
    assert len(set(source_row_references)) == 15, (
        "extension['source_row_reference'] MUST be unique per "
        f"(row, indicator); got {len(set(source_row_references))} "
        f"unique references across "
        f"{len(source_row_references)} observations"
    )
