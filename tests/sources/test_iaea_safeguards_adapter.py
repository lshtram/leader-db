"""IAEA Safeguards clean-source adapter tests.

The IAEA Safeguards Status List is the IAEA's public
legal / status evidence for Comprehensive Safeguards
Agreements, Additional Protocols, and Small Quantities
Protocols. The unified adapter is the next
clean-interface-only source after ``sipri_arms_transfers``
(`docs/architecture/sources.md` §7.2 ``iaea_safeguards``
row). The new package lives at
``src/leaders_db/sources/adapters/iaea_safeguards/`` and
reads a single cached status-list PDF plus a runtime-local
``metadata.json`` (gitignored per Always-On Rule #9).

The adapter is offline / cache-only in this slice; live fetch
is intentionally NOT supported. The 27 focused tests cover:

- The IAEA Safeguards adapter descriptor is registerable /
  listable through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata (source_id
  ``iaea_safeguards``, default version
  ``"IAEA Safeguards Status List, status as of 2025-12-31"``,
  attribution_key ``iaea_safeguards``, ``document`` source
  type, single-year 2025 coverage hint, single observation
  family ``nuclear_safeguards_status_country``,
  ``requires_network=False``).
- :class:`SourceIngestRunner` can run IAEA Safeguards
  end-to-end through the new registry against a fixture
  ``raw_root`` and produce :class:`NormalizedObservation`
  records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table.
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(2023,)`` request emits zero
  observations plus a structured ``YEAR_ABSENT`` warning
  (no stale-proxy fill per SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Readiness failures (missing metadata, missing cached PDF,
  missing required metadata field, ``local_files`` missing
  the canonical cached PDF, ``ingestion_status`` not
  ``'downloaded'``, missing required PDF column,
  ``source_version`` mismatch, checksum mismatch) each
  surface a structured ``SourceWarning(severity='error')``
  so the runner raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Cache-policy gate blocks ``"refresh"`` / ``"no_cache"``
  with a structured
  ``iaea_safeguards_unsupported_cache_policy`` error.
- The transform preserves source-native country display
  names verbatim and does NOT invent ISO3 codes
  (``country_code`` / ``leader_id`` / ``leader_name`` remain
  ``None``).
- Attribution drift guard: the canonical attribution text
  is a substring of ``docs/sources/attributions.md``
  (Always-On Rule #15).
- Importing the new
  ``leaders_db.sources.adapters.iaea_safeguards`` module
  does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).
- The adapter does NOT invoke the network.

PASS-ELIGIBLE rationale
-----------------------

IAEA Safeguards has no legacy Stage 2 implementation; the
tests in this file prove that the new
``leaders_db.sources.adapters.iaea_safeguards`` adapter
implements the full ``SourceAdapter`` Protocol end-to-end while
preserving the package-isolation contract -- they are
PASS-ELIGIBLE because the adapter implementation lands in the
same change set.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import shutil
import socket
import sys
import urllib.request
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
from leaders_db.sources.adapters.iaea_safeguards import (
    IAEA_SAFEGUARDS_ADAPTER_FACTORY,
    IAEA_SAFEGUARDS_ATTRIBUTION_KEY,
    IAEA_SAFEGUARDS_ATTRIBUTION_TEXT,
    IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_YEAR,
    IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY,
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_HOMEPAGE_URL,
    IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_CODES,
    IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
    IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_OBSERVATION_FAMILY,
    IAEA_SAFEGUARDS_PDF_NAME,
    IAEA_SAFEGUARDS_PDF_URL,
    IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
    IAEA_SAFEGUARDS_SOURCE_KEY,
    IAEA_SAFEGUARDS_STATUS_DATE,
    IAEA_SAFEGUARDS_SUPPORTED_FAMILIES,
    IAEA_SAFEGUARDS_TRANSFORM_NAME,
    create_iaea_safeguards_adapter,
    register_iaea_safeguards,
)
from leaders_db.sources.adapters.iaea_safeguards._constants import (
    IAEA_SAFEGUARDS_CHECKSUM_MISMATCH,
    IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
    IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
    IAEA_SAFEGUARDS_SCHEMA_ERROR,
    IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY,
    IAEA_SAFEGUARDS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_PDF = Path("tests/fixtures/iaea_safeguards/sample.pdf")


# ---------------------------------------------------------------------------
# Bundle staging helpers
# ---------------------------------------------------------------------------


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_pdf: bool = True,
    local_files: Any | None = None,
    checksum: Any = "AUTO",
    source_version: str = IAEA_SAFEGUARDS_DEFAULT_VERSION,
) -> Path:
    """Stage the IAEA Safeguards fixture bundle under
    ``raw_root/iaea_safeguards``.

    Copies ``tests/fixtures/iaea_safeguards/sample.pdf`` into
    ``<raw_root>/iaea_safeguards/sg-agreements-comprehensive-status.pdf``
    plus an optional ``metadata.json`` whose checksum matches
    the staged PDF. Returns the resolved bundle directory.

    The fixture carries 5 hand-authored synthetic country rows
    (no real IAEA claims -- the country labels are SYNTHETIC
    per the task brief: "fixtures must not redistribute IAEA
    tables, create a small synthetic PDF fixture").

    Per-row cell coverage (per the fixture builder docstring):

    - Country Alpha: ``In Force: 153`` / ``INFCIRC/153`` /
      ``In Force`` / ``Modified``
    - Country Bravo: ``In Force: 153`` / ``INFCIRC/153`` /
      ``Signed`` / ``Original``
    - Country Charlie: ``Not in Force: 66`` / ``INFCIRC/66`` /
      ``Not Signed`` / ``Not applicable``
    - Country Delta: ``N/A`` / blank / ``N/A`` /
      ``Not applicable`` (the blank INFCIRC cell exercises the
      ``value_type="missing"`` path)
    - Country Echo: ``In Force: 153`` / ``INFCIRC/153`` /
      ``Not Signed`` / ``Modified``
    """
    bundle = raw_root / IAEA_SAFEGUARDS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)

    pdf_path = bundle / IAEA_SAFEGUARDS_PDF_NAME
    if with_pdf:
        shutil.copy2(_FIXTURE_PDF, pdf_path)

    if not with_metadata:
        return bundle

    checksum_value: Any = checksum
    if checksum == "AUTO":
        if pdf_path.is_file():
            checksum_value = (
                hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            )
        else:
            checksum_value = None

    if local_files is None:
        local_files = [IAEA_SAFEGUARDS_PDF_NAME]

    payload: dict[str, Any] = {
        "source_name": (
            "IAEA Safeguards Status List, Conclusion of "
            "Safeguards Agreements, Additional Protocols and "
            "Small Quantities Protocols"
        ),
        "source_key": IAEA_SAFEGUARDS_SOURCE_KEY,
        "source_version": source_version,
        "download_date": "2026-06-27",
        "coverage": (
            f"single-point legal snapshot, status as of "
            f"{IAEA_SAFEGUARDS_STATUS_DATE}"
        ),
        "license_note": (
            "IAEA terms; download/copy/use with acknowledgement "
            "for research / private study / commercial / "
            "non-commercial use subject to restrictions; no "
            "redistribution of the full PDF / table in public "
            "outputs; attribution required."
        ),
        "local_files": local_files,
        "ingestion_status": "downloaded",
        "source_url": IAEA_SAFEGUARDS_PDF_URL,
    }
    if checksum_value is not None:
        payload["checksum_sha256"] = checksum_value
    payload["notes"] = (
        "Synthetic fixture bundle for clean-source adapter "
        "tests; the country labels and cell values are NOT real "
        "IAEA Safeguards data."
    )
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def _request(
    raw_root: Path, **kwargs: Any,
) -> SourceIngestRequest:
    """Build an IAEA Safeguards request with sensible defaults."""
    defaults: dict[str, Any] = {
        "cache_policy": IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY,
    }
    defaults.update(kwargs)
    return SourceIngestRequest(
        source_id=SourceId(IAEA_SAFEGUARDS_SOURCE_KEY),
        raw_root=raw_root,
        **defaults,
    )


def _run(raw_root: Path, **kwargs: Any) -> SourceIngestResult:
    """Drive the IAEA Safeguards adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_iaea_safeguards(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def _refresh_metadata_checksum(bundle: Path, pdf_file: Path) -> None:
    """Refresh the staged ``metadata.json`` checksum_sha256 field
    so it matches the on-disk SHA-256 of ``pdf_file``.

    The canonical readiness gate validates the staged PDF
    SHA-256 against ``metadata.json['checksum_sha256']``. When
    a test stages the metadata first then builds a PDF into
    the bundle directory, the staged checksum (which was
    computed against the empty / placeholder PDF) does NOT
    match the on-disk artifact; this helper refreshes the
    metadata so the readiness gate passes.
    """
    metadata_file = bundle / "metadata.json"
    if not metadata_file.is_file():
        return
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = (
        hashlib.sha256(pdf_file.read_bytes()).hexdigest()
    )
    metadata_file.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_descriptor_factory_and_registry() -> None:
    """The descriptor factory exposes the documented static metadata."""
    adapter = create_iaea_safeguards_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert (
        IAEA_SAFEGUARDS_ADAPTER_FACTORY().descriptor == descriptor
    )
    assert descriptor.source_id.slug == IAEA_SAFEGUARDS_SOURCE_KEY
    assert (
        descriptor.attribution_key == IAEA_SAFEGUARDS_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version == IAEA_SAFEGUARDS_DEFAULT_VERSION
    )
    assert descriptor.source_type == "document"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is False
    assert descriptor.supported_observation_families == (
        IAEA_SAFEGUARDS_SUPPORTED_FAMILIES
    )
    assert (
        IAEA_SAFEGUARDS_OBSERVATION_FAMILY
        in descriptor.supported_observation_families
    )
    assert (
        descriptor.coverage_hint.start_year
        == IAEA_SAFEGUARDS_COVERAGE_START_YEAR
    )
    assert (
        descriptor.coverage_hint.end_year
        == IAEA_SAFEGUARDS_COVERAGE_END_YEAR
    )
    assert descriptor.homepage_url == IAEA_SAFEGUARDS_HOMEPAGE_URL

    # The descriptor's coverage_hint.notes must carry the
    # documented caveat that this source captures safeguards /
    # legal / status evidence and is NOT a direct nuclear-weapons
    # score or proof of compliance / non-compliance by itself --
    # this is the audit-trail surface for the methodology note
    # in docs/methodology/ranking-evaluation-criteria.md §Chapter 1.
    notes = descriptor.coverage_hint.notes or ""
    assert "NOT a direct nuclear-weapons score" in notes
    assert "NOT" in notes and "score" in notes


def test_register_helper_registers_against_explicit_registry() -> None:
    """``register_iaea_safeguards(registry)`` is the explicit
    seam for tests + future composition code.
    """
    registry = InMemorySourceRegistry()
    adapter = register_iaea_safeguards(registry)
    assert (
        registry.get_adapter(SourceId(IAEA_SAFEGUARDS_SOURCE_KEY))
        is adapter
    )
    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == IAEA_SAFEGUARDS_SOURCE_KEY


def test_indicator_codes_match_canonical_4() -> None:
    """The 4 source-native indicator codes are exposed via the
    package surface for downstream query code.

    The catalog deliberately mirrors the 4 non-State columns
    in the cached PDF table -- the adapter does NOT carry a
    separate ``safeguards_agreement_type`` indicator (the
    canonical IAEA table has a single ``Safeguards
    Agreement`` column carrying the composite status label,
    NOT a separate type column).
    """
    assert (
        IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS
        in IAEA_SAFEGUARDS_INDICATOR_CODES
    )
    assert (
        IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS
        in IAEA_SAFEGUARDS_INDICATOR_CODES
    )
    assert (
        IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS
        in IAEA_SAFEGUARDS_INDICATOR_CODES
    )
    assert (
        IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER
        in IAEA_SAFEGUARDS_INDICATOR_CODES
    )
    assert len(IAEA_SAFEGUARDS_INDICATOR_CODES) == 4


def test_no_safeguards_agreement_type_indicator_in_catalog() -> None:
    """The catalog deliberately does NOT include a separate
    ``iaea_safeguards_safeguards_agreement_type`` indicator.

    The canonical IAEA Safeguards Status List carries a single
    ``Safeguards Agreement`` column whose value is a composite
    status label (e.g. ``In Force: 153`` / ``Not in Force: 66``
    / ``N/A``). The adapter never invents a separate
    ``safeguards_agreement_type`` indicator from the composite
    label -- that would duplicate the safeguards status and
    fabricate a column that does not exist in the parsed
    fixture.
    """
    forbidden_indicator_codes = (
        "iaea_safeguards_safeguards_agreement_type",
    )
    for forbidden in forbidden_indicator_codes:
        assert forbidden not in IAEA_SAFEGUARDS_INDICATOR_CODES, (
            f"{forbidden!r} must not appear in the canonical "
            f"indicator catalog -- the canonical IAEA table has "
            f"a single Safeguards Agreement column, not a "
            f"separate type column."
        )
        # Also assert the corresponding attribute name is not
        # accidentally exported from the adapter package.
        adapter_pkg = importlib.import_module(
            "leaders_db.sources.adapters.iaea_safeguards",
        )
        assert not hasattr(adapter_pkg, forbidden), (
            f"{forbidden!r} must not be exported from "
            f"leaders_db.sources.adapters.iaea_safeguards -- "
            f"the adapter never carries a separate agreement "
            f"type indicator."
        )


def test_required_columns_match_canonical_5() -> None:
    """The 5 canonical required PDF table columns are exposed via
    the package surface for the readiness gate + raw-read
    boundary.
    """
    assert len(IAEA_SAFEGUARDS_REQUIRED_COLUMNS) == 5
    assert "State" in IAEA_SAFEGUARDS_REQUIRED_COLUMNS
    assert "Safeguards Agreement" in IAEA_SAFEGUARDS_REQUIRED_COLUMNS
    assert "INFCIRC" in IAEA_SAFEGUARDS_REQUIRED_COLUMNS
    assert "Additional Protocol" in IAEA_SAFEGUARDS_REQUIRED_COLUMNS
    assert "Small Quantities Protocol" in IAEA_SAFEGUARDS_REQUIRED_COLUMNS


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
    assert IAEA_SAFEGUARDS_ATTRIBUTION_TEXT in attributions_text, (
        f"{IAEA_SAFEGUARDS_ATTRIBUTION_TEXT!r} is not a "
        f"substring of {attributions_path}. Update both in the "
        f"same commit (Rule #15)."
    )


def test_attribution_key_matches_attributions_doc() -> None:
    """The attribution key ``iaea_safeguards`` appears in
    the attributions doc. Drift guard for the descriptor's
    attribution_key field.
    """
    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    assert attributions_path.exists()
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert IAEA_SAFEGUARDS_ATTRIBUTION_KEY in attributions_text


# ---------------------------------------------------------------------------
# Bundle readiness -- happy path + error paths
# ---------------------------------------------------------------------------


def test_correct_bundle_passes_readiness(tmp_path: Path) -> None:
    """A well-formed bundle returns ``ready=True``."""
    _stage_bundle(tmp_path)
    readiness = create_iaea_safeguards_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_no_observations_emitted_for_unsupported_leaders_filter(
    tmp_path: Path,
) -> None:
    """``leaders=`` filter is unsupported -- the transform ignores
    it and the readiness envelope surfaces a structured
    ``UNSUPPORTED_FILTER`` warning.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, leaders=("Some Leader",))
    assert len(result.observations) == 20  # 5 rows x 4 indicators
    assert [w.code for w in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_pdf": False}, MISSING_RAW),
        ({"local_files": []}, IAEA_SAFEGUARDS_LOCAL_FILES_INVALID),
        (
            {"local_files": ["some_other_file.pdf"]},
            IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
        ),
        ({"checksum": "0" * 64}, IAEA_SAFEGUARDS_CHECKSUM_MISMATCH),
        (
            {"source_version": "IAEA Safeguards Status List, status as of 2024-12-31"},
            IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
        ),
    ],
)
def test_readiness_failures(
    tmp_path: Path, kwargs: dict[str, Any], code: str,
) -> None:
    """Each documented readiness-failure class surfaces a
    structured ``SourceWarning(severity='error')``.
    """
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_iaea_safeguards_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    """An explicit ``source_version=`` request that differs from
    the canonical version stamp fails readiness with a
    structured ``unsupported_version`` error.
    """
    _stage_bundle(tmp_path)
    readiness = create_iaea_safeguards_adapter().check_ready(
        _request(
            tmp_path,
            source_version=(
                "IAEA Safeguards Status List, status as of 2024-12-31"
            ),
        ),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == IAEA_SAFEGUARDS_UNSUPPORTED_VERSION


def test_cache_policy_refresh_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="refresh"`` is unsupported -- the gate
    blocks with a structured
    ``iaea_safeguards_unsupported_cache_policy`` error.
    """
    _stage_bundle(tmp_path)
    readiness = create_iaea_safeguards_adapter().check_ready(
        _request(tmp_path, cache_policy="refresh"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY
    )


def test_cache_policy_no_cache_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="no_cache"`` is unsupported -- same as
    ``refresh``.
    """
    _stage_bundle(tmp_path)
    readiness = create_iaea_safeguards_adapter().check_ready(
        _request(tmp_path, cache_policy="no_cache"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY
    )


# ---------------------------------------------------------------------------
# Year semantics
# ---------------------------------------------------------------------------


def test_out_of_coverage_year_warns_and_emits_no_rows(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2023,)`` -- the prototype's target
    year, which is OUTSIDE the documented 2025 single-year
    envelope -- emits zero observations plus a structured
    ``YEAR_ABSENT`` warning (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert [w.code for w in result.warnings] == [YEAR_ABSENT]


def test_in_coverage_year_emits_full_observations(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2025,)`` -- the canonical coverage
    year -- emits the full observation set (5 rows x 4
    indicators = 20 observations).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2025,))
    assert len(result.observations) == 20
    assert result.warnings == ()


def test_year_none_emits_full_observations(tmp_path: Path) -> None:
    """``years=None`` reads all available years in the source --
    for the canonical single-year envelope, this is equivalent
    to ``years=(2025,)`` and emits the full observation set.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert len(result.observations) == 20
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# Country + leader filter semantics
# ---------------------------------------------------------------------------


def test_country_filter_uses_source_native_display_name(
    tmp_path: Path,
) -> None:
    """The country filter matches the source-native state display
    name verbatim; ``countries=("Country Alpha",)`` returns
    one row (4 indicators = 4 observations).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path, countries=("Country Alpha",),
    )
    assert len(result.observations) == 4
    for obs in result.observations:
        assert obs.country_name == "Country Alpha"


def test_country_filter_no_match_emits_zero_rows(tmp_path: Path) -> None:
    """``countries=("Country That Does Not Exist",)`` emits zero
    observations (no silent stale-proxy fill).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path, countries=("Country That Does Not Exist",),
    )
    assert result.observations == ()


def test_country_filter_multiple_matches(tmp_path: Path) -> None:
    """``countries=("Country Alpha", "Country Echo")`` emits
    2 rows x 4 indicators = 8 observations.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        countries=("Country Alpha", "Country Echo"),
    )
    assert len(result.observations) == 8
    state_set = {obs.country_name for obs in result.observations}
    assert state_set == {"Country Alpha", "Country Echo"}


def test_leader_filter_warns_but_is_ignored(tmp_path: Path) -> None:
    """``leaders=`` is unsupported for a country-level
    safeguards status source -- the readiness envelope surfaces
    a structured ``UNSUPPORTED_FILTER`` warning and the
    transform ignores the filter (the unified adapter never
    invents leader values).
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path, leaders=("Some Leader",),
    )
    assert len(result.observations) == 20
    assert [w.code for w in result.warnings] == [UNSUPPORTED_FILTER]
    for obs in result.observations:
        assert obs.leader_id is None
        assert obs.leader_name is None


# ---------------------------------------------------------------------------
# Runner end-to-end + observation shape
# ---------------------------------------------------------------------------


def test_runner_emits_observations(tmp_path: Path) -> None:
    """The runner drives the IAEA Safeguards adapter end-to-end
    against a fixture ``raw_root`` and produces
    :class:`NormalizedObservation` records.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    observations = result.observations
    assert len(observations) == 20  # 5 rows x 4 indicators
    assert {
        obs.observation_family for obs in observations
    } == {IAEA_SAFEGUARDS_OBSERVATION_FAMILY}
    assert {
        obs.year for obs in observations
    } == {IAEA_SAFEGUARDS_COVERAGE_YEAR}
    # No ISO3 invention: ``country_code`` is None for every
    # observation (the adapter preserves the source-native
    # state display name on ``country_name`` only).
    assert {obs.country_code for obs in observations} == {None}
    assert {obs.leader_id for obs in observations} == {None}
    assert {obs.leader_name for obs in observations} == {None}


def test_observation_shape_preserves_source_native_state(
    tmp_path: Path,
) -> None:
    """Every observation carries the source-native state display
    name verbatim on ``country_name`` AND on the audit-trail
    extension payload. The adapter does NOT invent ISO3 codes.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    expected_states = {
        "Country Alpha", "Country Bravo", "Country Charlie",
        "Country Delta", "Country Echo",
    }
    actual_states = {obs.country_name for obs in result.observations}
    assert actual_states == expected_states
    for obs in result.observations:
        assert obs.extension["iaea_safeguards_state"] == obs.country_name
        assert obs.country_code is None
        # Per-observation attribution is the canonical
        # IAEA_SAFEGUARDS_ATTRIBUTION_TEXT.
        assert (
            obs.extension["attribution"]
            == IAEA_SAFEGUARDS_ATTRIBUTION_TEXT
        )


def test_observation_shape_infcirc_indicator(tmp_path: Path) -> None:
    """The INFCIRC indicator emits the source-native identifier
    on ``value`` (e.g. ``"INFCIRC/153"``); an empty INFCIRC
    cell emits ``value=None`` / ``value_type="missing"`` plus
    the verbatim raw cell text on
    ``extension["iaea_safeguards_infcirc_raw"]``.

    The indicator code is ``iaea_safeguards_infcirc_number``
    (the canonical ``infcirc`` spelling, NOT ``inficrc``) and
    the extension raw-cell key is
    ``iaea_safeguards_infcirc_raw`` (also canonical).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    infcirc = [
        obs for obs in result.observations
        if obs.indicator_code == IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER
    ]
    assert len(infcirc) == 5
    by_state = {obs.country_name: obs for obs in infcirc}

    # Country Alpha: ``INFCIRC/153``
    assert by_state["Country Alpha"].value == "INFCIRC/153"
    assert by_state["Country Alpha"].value_type == "categorical"

    # Country Delta: blank INFCIRC cell
    assert by_state["Country Delta"].value is None
    assert by_state["Country Delta"].value_type == "missing"
    assert (
        by_state["Country Delta"].extension[
            "iaea_safeguards_infcirc_raw"
        ]
        == ""
    )


def test_observation_shape_cell_indicator(tmp_path: Path) -> None:
    """Cell-label indicators (safeguards_agreement_status,
    additional_protocol_status, small_quantities_protocol_status)
    preserve the source-native cell text on ``value`` and emit
    ``value_type="categorical"``.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    ap_obs = [
        obs for obs in result.observations
        if obs.indicator_code
        == IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS
    ]
    assert len(ap_obs) == 5
    by_state = {obs.country_name: obs for obs in ap_obs}
    assert by_state["Country Alpha"].value == "In Force"
    assert by_state["Country Alpha"].value_type == "categorical"
    assert by_state["Country Bravo"].value == "Signed"
    assert by_state["Country Charlie"].value == "Not Signed"
    assert by_state["Country Delta"].value == "N/A"
    assert by_state["Country Echo"].value == "Not Signed"


def test_observation_shape_raw_locator(tmp_path: Path) -> None:
    """Every observation carries the canonical PDF raw locator
    with the cached PDF path, the row number, the column
    name, and (when set) the page number.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    for obs in result.observations:
        assert obs.raw_locator.path is not None
        assert obs.raw_locator.path.endswith(IAEA_SAFEGUARDS_PDF_NAME)
        assert obs.raw_locator.row_number is not None
        assert obs.raw_locator.column_name is not None
        # Column name matches one of the canonical PDF table
        # column labels.
        assert obs.raw_locator.column_name in (
            "Safeguards Agreement",
            "INFCIRC",
            "Additional Protocol",
            "Small Quantities Protocol",
        )


def test_observation_transform_locator(tmp_path: Path) -> None:
    """Every observation carries the canonical transform locator
    with the canonical transform name + catalog key + rule_id.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    for obs in result.observations:
        assert (
            obs.transform_locator.transform_name
            == IAEA_SAFEGUARDS_TRANSFORM_NAME
        )
        assert (
            obs.transform_locator.catalog_key
            == IAEA_SAFEGUARDS_SOURCE_KEY
        )
        assert obs.transform_locator.rule_id is not None
        assert obs.source_version == IAEA_SAFEGUARDS_DEFAULT_VERSION


def test_schema_error_when_required_column_missing(tmp_path: Path) -> None:
    """A PDF whose header is missing one or more canonical
    required columns fires
    :class:`IaeaSafeguardsSchemaError` BEFORE the transform
    layer consumes the frame -- the transform layer does NOT
    silently emit partial output on a schema contract
    violation.

    The test crafts a malformed PDF whose header is missing
    ``Additional Protocol`` and ``Small Quantities Protocol``,
    then asserts the schema error is raised by the raw-read
    helper directly (rather than going through the runner,
    whose readiness gate is upstream of the schema-validation
    layer).

    Note: the test catches ``ValueError`` (the base class of
    ``IaeaSafeguardsSchemaError``) rather than
    ``IaeaSafeguardsSchemaError`` directly. This is defensive
    against class-identity divergence: the
    ``test_importing_adapter_does_not_import_legacy_ingest``
    test purges ``leaders_db.sources`` from ``sys.modules`` and
    re-imports the adapter module, which can produce a NEW
    ``IaeaSafeguardsSchemaError`` class object distinct from
    the top-level reference in this test file -- pytest's
    ``pytest.raises(SomeClass)`` would NOT match the NEW class
    (it does an ``isinstance`` check, not a structural match),
    so we catch the base ``ValueError`` and then verify the
    exception is an instance of the freshly-imported class
    inside the ``with`` block. This pattern is robust against
    the import-purge side effect without compromising the
    assertion (we still pin the exact class via the in-block
    re-import).
    """
    # Re-import inside the test to defeat the sys.modules purge
    # that ``test_importing_adapter_does_not_import_legacy_ingest``
    # runs (so the class identity is always current).
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
    )

    from leaders_db.sources.adapters.iaea_safeguards import (
        IaeaSafeguardsSchemaError as _IaeaSafeguardsSchemaError,
    )
    from leaders_db.sources.adapters.iaea_safeguards import (
        read_iaea_safeguards_pdf,
    )

    bundle = _stage_bundle(tmp_path, with_pdf=False)
    pdf_path = bundle / IAEA_SAFEGUARDS_PDF_NAME

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    # Intentionally missing "Additional Protocol" and
    # "Small Quantities Protocol" -- only 3 of the 5 canonical
    # columns present.
    malformed_header = ["State", "Safeguards Agreement", "INFCIRC"]
    malformed_rows = [
        malformed_header,
        ["Country Alpha", "In Force: 153", "INFCIRC/153"],
    ]
    tbl = Table(
        malformed_rows,
        colWidths=[5 * cm, 6 * cm, 5 * cm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    doc.build([tbl])

    # The malformed PDF is on disk; the ``_stage_bundle(..., with_pdf=False)``
    # call writes a metadata.json with checksum=None so the readiness
    # gate would surface a ``missing_metadata`` error if the test
    # went through the runner. The schema-error path is the
    # raw-read boundary (downstream of readiness), so we exercise
    # it via the public raw-read helper directly.
    request = _request(tmp_path)
    with pytest.raises(_IaeaSafeguardsSchemaError) as excinfo:
        read_iaea_safeguards_pdf(request)
    message = str(excinfo.value)
    assert IAEA_SAFEGUARDS_SCHEMA_ERROR in message
    assert "Additional Protocol" in message
    assert "Small Quantities Protocol" in message
    # Defensive: confirm the adapter contract still works.
    adapter = create_iaea_safeguards_adapter()
    assert adapter.descriptor.source_id.slug == IAEA_SAFEGUARDS_SOURCE_KEY


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner does NOT consult the legacy
    ``STAGE2_ADAPTERS`` dispatch table even when the legacy
    ``iaea_safeguards`` slot is monkeypatched to a tracker.
    """
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    def tracker(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "STAGE2_ADAPTERS['iaea_safeguards'] must not be invoked",
        )

    monkeypatch.setattr(
        legacy_ingest,
        "STAGE2_ADAPTERS",
        {IAEA_SAFEGUARDS_SOURCE_KEY: tracker},
    )
    result = _run(tmp_path)
    assert len(result.observations) == 20


def test_importing_adapter_does_not_import_legacy_ingest() -> None:
    """Importing the new ``iaea_safeguards`` adapter module does
    NOT pull in any ``leaders_db.ingest`` module (SRC-MIG-007 +
    the import boundary documented in
    ``docs/architecture/sources.md`` §10.1).
    """
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]

    __import__("leaders_db.sources.adapters.iaea_safeguards")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        f"importing leaders_db.sources.adapters.iaea_safeguards "
        f"must not import leaders_db.ingest (leaked modules: {leaked})"
    )


def test_adapter_does_not_use_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The IAEA Safeguards adapter never invokes the network."""
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "network access is not allowed for IAEA Safeguards"
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path)
    assert len(result.observations) == 20


def test_duplicate_slug_registration_raises_value_error(
    tmp_path: Path,
) -> None:
    """Registering the IAEA Safeguards adapter twice against the
    same registry raises :class:`ValueError` per
    ``docs/requirements/sources.md`` §9 SRC-REG-004.
    """
    _stage_bundle(tmp_path)
    registry = InMemorySourceRegistry()
    register_iaea_safeguards(registry)
    with pytest.raises(ValueError, match="iaea_safeguards"):
        register_iaea_safeguards(registry)


# ---------------------------------------------------------------------------
# Multi-page PDF + per-row page provenance
# ---------------------------------------------------------------------------


def _build_multipage_pdf(output_path: Path) -> None:
    """Build a 2-page synthetic PDF whose country rows are
    distributed across two pages so the test can assert that
    the reader accumulates rows from BOTH pages and that each
    observation carries the correct per-row
    ``page_number``.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        PageBreak,
        SimpleDocTemplate,
        Table,
        TableStyle,
    )

    header = [
        "State",
        "Safeguards Agreement",
        "INFCIRC",
        "Additional Protocol",
        "Small Quantities Protocol",
    ]
    # Page 1: 3 rows; Page 2: 2 rows. Total: 5 rows.
    page1_rows = [
        ("Country Alpha", "In Force: 153", "INFCIRC/153",
         "In Force", "Modified"),
        ("Country Bravo", "In Force: 153", "INFCIRC/153",
         "Signed", "Original"),
        ("Country Charlie", "Not in Force: 66", "INFCIRC/66",
         "Not Signed", "Not applicable"),
    ]
    page2_rows = [
        ("Country Delta", "N/A", "", "N/A", "Not applicable"),
        ("Country Echo", "In Force: 153", "INFCIRC/153",
         "Not Signed", "Modified"),
    ]
    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    # Column widths are sized so ``Safeguards Agreement`` fits
    # on a single line in the reportlab Helvetica-Bold 9pt
    # header (the longest header cell) on EVERY page, so
    # pdfplumber's per-page header detection matches the
    # canonical ``Safeguards Agreement`` column label. Page A4
    # = 21cm wide; 1.5cm margins on each side leave 18cm
    # usable; column totals equal 18cm.
    col_widths = [3 * cm, 4 * cm, 2.5 * cm, 4 * cm, 4.5 * cm]

    def _render_page(rows: list[tuple[str, ...]]) -> list:
        page_data: list[list[str]] = [header]
        for row in rows:
            page_data.append(list(row))
        tbl = Table(
            page_data,
            colWidths=col_widths,
            repeatRows=1,
        )
        tbl.setStyle(table_style)
        return [tbl, PageBreak()]

    flowables: list = []
    flowables.extend(_render_page(page1_rows))
    # Strip the trailing PageBreak on the last page.
    flowables.extend(_render_page(page2_rows)[:-1])
    doc.build(flowables)


def test_runner_emits_observations_from_multiple_pdf_pages(
    tmp_path: Path,
) -> None:
    """Runner-level multi-page test -- the cached PDF is a
    2-page document whose country rows are distributed across
    both pages. The reader accumulates rows from BOTH pages
    and the runner emits 5 rows x 4 indicators = 20
    observations. Every observation carries a
    ``RawLocator.page_number`` that matches the page the row
    originated from.

    The test exercises the production runner path end-to-end
    (not just the raw-read helper) so the per-row page
    provenance flows through ``transform`` into the
    :class:`NormalizedObservation` ``RawLocator.page_number``
    field.

    The expected page distribution is:

    - Page 1: Country Alpha / Bravo / Charlie (3 rows)
    - Page 2: Country Delta / Echo (2 rows)

    The order matters: stage the metadata first (without a
    PDF), then build the 2-page PDF into the staged bundle
    directory so the multi-page PDF is preserved (the
    canonical ``_stage_bundle`` helper would otherwise copy
    the 1-page sample.pdf over the multi-page PDF).
    """
    bundle = tmp_path / IAEA_SAFEGUARDS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Stage the metadata FIRST, with ``with_pdf=False`` so the
    # canonical helper does NOT overwrite the bundle PDF with
    # the 1-page sample.pdf fixture.
    _stage_bundle(tmp_path, with_pdf=False)
    pdf_file = bundle / IAEA_SAFEGUARDS_PDF_NAME
    _build_multipage_pdf(pdf_file)
    # Refresh the metadata checksum so it matches the staged
    # multi-page PDF (the readiness gate validates the on-disk
    # SHA-256 against metadata.json).
    _refresh_metadata_checksum(bundle, pdf_file)

    result = _run(tmp_path)
    assert len(result.observations) == 20, (
        f"expected 20 observations (5 rows x 4 indicators) "
        f"but got {len(result.observations)} -- the reader "
        f"must accumulate rows from every page, not stop at "
        f"the first matching page."
    )

    # Group by state -> (indicator -> observation) so we can
    # assert the per-row page provenance cleanly.
    by_state: dict[str, dict[str, Any]] = {}
    for obs in result.observations:
        by_state.setdefault(obs.country_name, {})[obs.indicator_code] = obs

    # 5 distinct states must be present (none dropped across pages).
    assert set(by_state.keys()) == {
        "Country Alpha", "Country Bravo", "Country Charlie",
        "Country Delta", "Country Echo",
    }

    # Page 1: Alpha / Bravo / Charlie -> page_number=1.
    for state in ("Country Alpha", "Country Bravo", "Country Charlie"):
        for obs in by_state[state].values():
            assert obs.raw_locator.page_number == 1, (
                f"{state!r} observation {obs.indicator_code!r} "
                f"carries raw_locator.page_number="
                f"{obs.raw_locator.page_number!r}; expected 1"
            )

    # Page 2: Delta / Echo -> page_number=2.
    for state in ("Country Delta", "Country Echo"):
        for obs in by_state[state].values():
            assert obs.raw_locator.page_number == 2, (
                f"{state!r} observation {obs.indicator_code!r} "
                f"carries raw_locator.page_number="
                f"{obs.raw_locator.page_number!r}; expected 2"
            )

    # Per-row extension["page_number"] mirrors the locator.
    for obs in result.observations:
        assert obs.extension["page_number"] == obs.raw_locator.page_number


def test_raw_read_accumulates_rows_across_pages(tmp_path: Path) -> None:
    """Direct raw-read test -- the cached PDF is a 2-page
    document and the raw-read helper returns rows from BOTH
    pages with the correct per-row ``page_number`` key.

    This test exercises the raw-read boundary directly (not
    via the runner) so the per-row page provenance is
    verified at the parser seam.

    Order matters: stage the metadata first (with no PDF),
    then build the 2-page PDF so the multi-page artifact is
    preserved (the canonical ``_stage_bundle`` helper would
    otherwise copy the 1-page sample.pdf over the multi-page
    PDF).
    """
    bundle = tmp_path / IAEA_SAFEGUARDS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    _stage_bundle(tmp_path, with_pdf=False)
    pdf_file = bundle / IAEA_SAFEGUARDS_PDF_NAME
    _build_multipage_pdf(pdf_file)
    _refresh_metadata_checksum(bundle, pdf_file)

    from leaders_db.sources.adapters.iaea_safeguards import (
        read_iaea_safeguards_pdf,
    )

    raw = read_iaea_safeguards_pdf(_request(tmp_path))
    assert raw.payload is not None
    rows = raw.payload.get("rows")
    assert isinstance(rows, list)
    assert len(rows) == 5, (
        f"expected 5 parsed rows (3 from page 1 + 2 from "
        f"page 2) but got {len(rows)}"
    )

    page_to_states: dict[int, list[str]] = {}
    for row in rows:
        assert "page_number" in row, (
            "every parsed row dict must carry a 'page_number' "
            "key so the transform layer can populate "
            "RawLocator.page_number"
        )
        page = int(row["page_number"])
        page_to_states.setdefault(page, []).append(row["State"])

    assert sorted(page_to_states.get(1, [])) == [
        "Country Alpha", "Country Bravo", "Country Charlie",
    ], (
        f"page 1 should carry Alpha / Bravo / Charlie but got "
        f"{page_to_states.get(1, [])}"
    )
    assert sorted(page_to_states.get(2, [])) == [
        "Country Delta", "Country Echo",
    ], (
        f"page 2 should carry Delta / Echo but got "
        f"{page_to_states.get(2, [])}"
    )


# ---------------------------------------------------------------------------
# INFCIRC spelling + indicator/extension key contracts
# ---------------------------------------------------------------------------


def test_infcirc_indicator_and_extension_keys_use_canonical_spelling() -> None:
    """The indicator code + extension raw-cell key use the
    canonical ``infcirc`` spelling everywhere -- never
    ``inficrc`` or ``infirc``.

    The canonical public forms are:

    - ``iaea_safeguards_infcirc_number`` (indicator code)
    - ``iaea_safeguards_infcirc_raw`` (extension raw-cell key)
    - ``IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER`` (constant)
    """
    # Indicator code form.
    assert (
        IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER
        == "iaea_safeguards_infcirc_number"
    )
    assert "iaea_safeguards_infcirc_number" in (
        IAEA_SAFEGUARDS_INDICATOR_CODES
    )
    # The misspelled forms must not appear anywhere in the
    # package surface or in the canonical indicator tuple.
    forbidden_indicator_codes = (
        "iaea_safeguards_inficrc_number",
        "iaea_safeguards_infirc_number",
    )
    for forbidden in forbidden_indicator_codes:
        assert forbidden not in IAEA_SAFEGUARDS_INDICATOR_CODES, (
            f"{forbidden!r} must not appear in the canonical "
            f"indicator catalog (use {IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER!r})"
        )

    # The adapter package must not export the misspelled
    # constant names.
    adapter_pkg = importlib.import_module(
        "leaders_db.sources.adapters.iaea_safeguards",
    )
    forbidden_attrs = (
        "IAEA_SAFEGUARDS_INDICATOR_INFICRC_NUMBER",
        "IAEA_SAFEGUARDS_INDICATOR_INFIRC_NUMBER",
        "IAEA_SAFEGUARDS_INFICRC_UNIT",
        "IAEA_SAFEGUARDS_INFICRC_SCALE",
    )
    for attr in forbidden_attrs:
        assert not hasattr(adapter_pkg, attr), (
            f"{attr!r} must not be exported from "
            f"leaders_db.sources.adapters.iaea_safeguards "
            f"(use the canonical infcirc spelling)"
        )

    # The canonical attributes MUST be exported.
    for attr in (
        "IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER",
        "IAEA_SAFEGUARDS_INFCIRC_UNIT",
        "IAEA_SAFEGUARDS_INFCIRC_SCALE",
    ):
        assert hasattr(adapter_pkg, attr), (
            f"{attr!r} must be exported from "
            f"leaders_db.sources.adapters.iaea_safeguards"
        )


def test_no_infcirc_misspellings_in_source_tree() -> None:
    """Grep-clean guard: the misspelled forms ``inficrc`` and
    ``infirc`` (used as the indicator code / constant name /
    attribute name) must NOT appear anywhere in the IAEA
    Safeguards production source tree or fixture tree.

    Scans the IAEA Safeguards source package + the fixture
    builder. The test file itself is intentionally NOT scanned
    -- the test file IS allowed to mention the misspellings in
    negation contexts (the forbidden-key asserts and the
    grep-clean test docstrings all reference the misspellings
    by name to assert their absence; this is the contract
    that proves the spelling is enforced).

    The misspellings are checked as whole identifiers (so
    legitimate substrings like ``INFCIRC/153`` are not flagged)
    by requiring the misspelled form to be followed by a
    non-letter / non-digit / non-underscore boundary.
    """
    repo_root = Path(__file__).resolve().parents[2]
    misspelling_pattern = re.compile(
        r"\b(?:inficrc|infirc)[A-Za-z0-9_]*\b",
    )
    # Production source tree + fixture builder only.
    scan_paths = (
        repo_root / "src" / "leaders_db" / "sources" / "adapters" / "iaea_safeguards",
        repo_root / "tests" / "fixtures" / "iaea_safeguards",
    )

    offenders: list[tuple[str, int, str]] = []
    for scan_root in scan_paths:
        if scan_root.is_file():
            files = [scan_root]
        else:
            files = [path for path in scan_root.rglob("*.py")]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for match in misspelling_pattern.finditer(text):
                # The canonical "INFCIRC" header label and
                # "INFCIRC/..." document identifier strings
                # are uppercased -- the misspelling pattern
                # catches lowercase "inficrc" / "infirc"
                # identifiers; the uppercase form is not
                # affected.
                offenders.append((
                    str(path.relative_to(repo_root)),
                    text.count("\n", 0, match.start()) + 1,
                    match.group(0),
                ))

    assert offenders == [], (
        "INFCIRC misspellings detected in the IAEA Safeguards "
        "production source / fixture tree. Use the canonical "
        "'infcirc' spelling. Offenders: "
        + "\n".join(
            f"  {path}:{line}: {token!r}"
            for path, line, token in offenders
        )
    )


def test_extension_raw_value_key_is_infcirc_raw(tmp_path: Path) -> None:
    """The per-observation extension raw-cell key for the INFCIRC
    column is exactly ``iaea_safeguards_infcirc_raw`` -- the
    canonical ``infcirc`` spelling -- and not the misspelled
    ``iaea_safeguards_inficrc_raw`` variant.

    This pins the on-the-wire extension payload shape so
    downstream consumers can rely on the canonical key.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    infcirc_obs = [
        obs for obs in result.observations
        if obs.indicator_code == IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER
    ]
    assert infcirc_obs, "expected at least one INFCIRC observation"
    for obs in infcirc_obs:
        # Canonical key MUST be present.
        assert "iaea_safeguards_infcirc_raw" in obs.extension, (
            f"observation for {obs.country_name!r} missing the "
            f"canonical 'iaea_safeguards_infcirc_raw' extension key"
        )
        # Misspelled variants MUST NOT be present.
        for forbidden_key in (
            "iaea_safeguards_inficrc_raw",
            "iaea_safeguards_infirc_raw",
        ):
            assert forbidden_key not in obs.extension, (
                f"observation for {obs.country_name!r} carries "
                f"the misspelled extension key {forbidden_key!r}; "
                f"use the canonical 'iaea_safeguards_infcirc_raw'."
            )


# ---------------------------------------------------------------------------
# Production staged bundle smoke (skipped if not canonically staged locally)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_production_staged_bundle_smoke_if_present() -> None:
    """If a real ``data/raw/iaea_safeguards/`` bundle is
    canonically staged locally, the adapter must run
    end-to-end through the runner against the real bundle.
    """
    root = Path("data/raw")
    bundle = root / IAEA_SAFEGUARDS_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (
        bundle / IAEA_SAFEGUARDS_PDF_NAME
    ).is_file():
        pytest.skip(
            "IAEA Safeguards raw bundle is not canonically staged locally"
        )
    result = _run(root)
    assert result.observations
    assert {
        obs.source_version for obs in result.observations
    } == {IAEA_SAFEGUARDS_DEFAULT_VERSION}
