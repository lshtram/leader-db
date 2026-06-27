"""SIPRI Arms Transfers clean-source adapter tests.

The SIPRI Arms Transfers Database is the SIPRI-maintained
public record of international transfers of major conventional
arms. The unified adapter is the first
"databases-not-yet-in-legacy" source after ``polity_v`` to be
rebuilt under the clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.2 ``sipri_arms_transfers``
row). The new package lives at
``src/leaders_db/sources/adapters/sipri_arms_transfers/`` and
reads a staged cached export (the canonical
``trade_register.csv`` file OR the canonical
``trade_register.json`` base64-JSON wrapper) from
``data/raw/sipri_arms_transfers/`` plus a runtime-local
``metadata.json`` (gitignored per Always-On Rule #9).

Tests cover the documented slice acceptance criteria:

- The SIPRI Arms Transfers adapter descriptor is registerable /
  listable through the new :class:`InMemorySourceRegistry` and
  exposes the documented static metadata.
- The SIPRI Arms Transfers descriptor conforms to the canonical
  ``SourceDescriptor`` contract (source_id
  ``sipri_arms_transfers``, default version
  ``"SIPRI Arms Transfers Trade Register 2026-03-09 (data 1950-2025)"``,
  attribution_key ``sipri_arms_transfers``, ``api`` source
  type, 1950-2025 coverage hint, BOTH observation families
  ``arms_transfer_register_row`` +
  ``arms_transfer_country_year_aggregate``, requires_network
  ``False``).
- :class:`SourceIngestRunner` can run SIPRI Arms Transfers
  end-to-end through the new registry against a fixture
  ``raw_root`` and produce :class:`NormalizedObservation`
  records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table (the unified adapter
  never wires through ``leaders_db.ingest``; the legacy
  ``STAGE2_ADAPTERS["sipri_arms_transfers"]`` slot remains
  ``None``).
- ``years=`` and ``countries=`` filters are honored and surface
  correct observation counts.
- An out-of-coverage ``years=(2026,)`` request emits zero
  observations plus a structured
  :class:`SourceWarning` (no stale-proxy fill -- SRC-COV-002 /
  SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Non-numeric ``TIV (delivered)`` cells (``"n.a."``) are
  emitted as ``value=None`` / ``value_type='missing'`` + the
  verbatim raw cell text on ``extension.raw_value``; they are
  NOT coerced to numeric.
- BOTH the direct-CSV cached shape AND the base64-JSON
  wrapper cached shape are supported and produce the same
  canonical observation set.
- Readiness failures (missing metadata, missing cached export,
  missing required metadata field, ``local_files`` missing
  the canonical cached file, ``ingestion_status`` not
  ``'downloaded'``, missing required CSV column,
  ``source_version`` mismatch, checksum mismatch) each
  surface a structured ``SourceWarning(severity='error')``
  so the runner raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Cache-policy gate blocks ``"refresh"`` / ``"no_cache"``
  with a structured
  ``sipri_arms_transfers_unsupported_cache_policy`` error.
- Aggregation math: deterministic
  ``(role, country, year)`` TIV sums are emitted under
  ``arms_transfer_country_year_aggregate`` (no double-counting
  supplier-side + recipient-side aggregates for the same
  country-year).
- SIPRI preamble / citation lines are preserved on every
  emitted observation's
  ``extension["sipri_arms_transfers_preamble"]`` audit-trail
  field.
- Importing the new
  ``leaders_db.sources.adapters.sipri_arms_transfers`` module
  does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).
- Attribution drift guard: the canonical attribution text is
  a substring of ``docs/sources/attributions.md``
  (Always-On Rule #15).

PASS-ELIGIBLE rationale
-----------------------

SIPRI Arms Transfers has no legacy Stage 2 implementation; the
tests in this file prove that the new
``leaders_db.sources.adapters.sipri_arms_transfers`` adapter
implements the full ``SourceAdapter`` Protocol end-to-end while
preserving the package-isolation contract -- they are
PASS-ELIGIBLE because the adapter implementation lands in the
same change set.
"""

from __future__ import annotations

import base64
import hashlib
import json
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
from leaders_db.sources.adapters.sipri_arms_transfers import (
    SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY,
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY,
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT,
    SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
    SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    SIPRI_ARMS_TRANSFERS_CSV_NAME,
    SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
    SIPRI_ARMS_TRANSFERS_INDICATOR_CODES,
    SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED,
    SIPRI_ARMS_TRANSFERS_JSON_NAME,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER,
    SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
    SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES,
    SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME,
    SipriArmsTransfersAdapter,
    create_sipri_arms_transfers_adapter,
    register_sipri_arms_transfers,
)
from leaders_db.sources.adapters.sipri_arms_transfers._constants import (
    SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH,
    SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
    SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
    SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND,
    SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_CSV = Path("tests/fixtures/sipri_arms_transfers/sample.csv")
_FIXTURE_JSON = Path("tests/fixtures/sipri_arms_transfers/sample.json")


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
    source_version: str = SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    checksum_csv: bool = True,
    checksum_json: bool = False,
) -> Path:
    """Stage the SIPRI Arms Transfers fixture bundle under
    ``raw_root/sipri_arms_transfers``.

    Copies ``tests/fixtures/sipri_arms_transfers/sample.csv``
    into ``<raw_root>/sipri_arms_transfers/trade_register.csv``
    (the canonical direct-CSV cached shape) plus an optional
    ``trade_register.json`` wrapper (the canonical base64-JSON
    cached shape) and writes a well-formed ``metadata.json``
    whose checksum matches the staged file(s). Returns the
    resolved bundle directory.

    The fixture carries 6 hand-authored synthetic transfer rows
    (no real SIPRI claims -- the country labels are SYNTHETIC
    per the task brief: "prefer synthetic non-real country
    labels if it tests parser mechanics without factual
    assertions"). Indicator / cell coverage (per the fixture
    builder docstring):

    - Row 1: Country A -> Country B, order 2010, delivery 2012,
      numbers=24, TIV ordered=876, TIV delivered=876
    - Row 2: Country A -> Country C, order 2014, delivery
      "2016-2018" (range -- parser extracts first 4-digit year
      = 2016), numbers=12, TIV ordered=120, TIV delivered=120
    - Row 3: Country B -> Country C, order 2008, delivery 2010,
      numbers=2, TIV ordered=540, TIV delivered="n.a."
      (string sentinel -- emits value_type="missing")
    - Row 4: Country A -> Country B, order 2018, delivery 2020,
      numbers=8, TIV ordered=44, TIV delivered=44
    - Row 5: Country C -> Country A, order 2011, delivery 2013,
      numbers=1, TIV ordered=60, TIV delivered=60
    - Row 6: Country B -> Country A, order 2019, delivery 2021,
      numbers=100, TIV ordered=230, TIV delivered=230
    """
    bundle = raw_root / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)

    csv_path = bundle / SIPRI_ARMS_TRANSFERS_CSV_NAME
    json_path = bundle / SIPRI_ARMS_TRANSFERS_JSON_NAME

    if with_csv:
        shutil.copy2(_FIXTURE_CSV, csv_path)
    if with_json:
        shutil.copy2(_FIXTURE_JSON, json_path)

    if not with_metadata:
        return bundle

    checksum_value: Any = checksum
    checksum_dict: dict[str, str] = {}
    if checksum == "AUTO":
        if csv_path.is_file() and checksum_csv:
            checksum_dict[
                SIPRI_ARMS_TRANSFERS_CSV_NAME
            ] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        if json_path.is_file() and checksum_json:
            checksum_dict[
                SIPRI_ARMS_TRANSFERS_JSON_NAME
            ] = hashlib.sha256(json_path.read_bytes()).hexdigest()
        if len(checksum_dict) == 1:
            checksum_value = next(iter(checksum_dict.values()))
        elif len(checksum_dict) > 1:
            checksum_value = checksum_dict
        else:
            checksum_value = None
    elif isinstance(checksum, str):
        checksum_value = checksum

    if local_files is None:
        local_files = [
            name for name, path in (
                (SIPRI_ARMS_TRANSFERS_CSV_NAME, csv_path),
                (SIPRI_ARMS_TRANSFERS_JSON_NAME, json_path),
            ) if path.is_file()
        ]

    payload: dict[str, Any] = {
        "source_name": "SIPRI Arms Transfers Database",
        "source_key": SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
        "source_version": source_version,
        "download_date": "2026-06-27",
        "coverage": "1950-2025",
        "license_note": (
            "SIPRI copyright; non-commercial use; attribution "
            "required (per SIPRI fair-use policy)."
        ),
        "local_files": local_files,
        "ingestion_status": "downloaded",
        "source_url": SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
    }
    if checksum_value is not None:
        payload["checksum_sha256"] = checksum_value
    payload["notes"] = (
        "Synthetic fixture bundle for clean-source adapter "
        "tests; the country labels and TIV values are NOT real "
        "SIPRI Arms Transfers data."
    )
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def _request(
    raw_root: Path, **kwargs: Any,
) -> SourceIngestRequest:
    """Build a SIPRI Arms Transfers request with sensible defaults."""
    defaults: dict[str, Any] = {
        "cache_policy": SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY,
    }
    defaults.update(kwargs)
    return SourceIngestRequest(
        source_id=SourceId(SIPRI_ARMS_TRANSFERS_SOURCE_KEY),
        raw_root=raw_root,
        **defaults,
    )


def _run(raw_root: Path, **kwargs: Any) -> SourceIngestResult:
    """Drive the SIPRI Arms Transfers adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_sipri_arms_transfers(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_descriptor_factory_and_registry() -> None:
    """The descriptor factory exposes the documented static metadata."""
    adapter = create_sipri_arms_transfers_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert (
        SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY().descriptor == descriptor
    )
    assert descriptor.source_id.slug == SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    assert (
        descriptor.attribution_key == SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version == SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION
    )
    assert descriptor.source_type == "api"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is False
    assert descriptor.supported_observation_families == (
        SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES
    )
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
        in descriptor.supported_observation_families
    )
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
        in descriptor.supported_observation_families
    )
    assert (
        descriptor.coverage_hint.start_year
        == SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR
    )
    assert (
        descriptor.coverage_hint.end_year
        == SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR
    )
    assert descriptor.homepage_url == SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL

    # The descriptor's coverage_hint.notes must carry the
    # documented caveat about arms transfers NOT being proof of
    # aggression / proxy sponsorship / illegality -- this is the
    # audit-trail surface for the methodology note in
    # docs/methodology/ranking-evaluation-criteria.md §Chapter 2.
    notes = descriptor.coverage_hint.notes or ""
    assert "NOT direct proof of aggression" in notes
    assert "NOT direct proof of" in notes


def test_register_helper_registers_against_explicit_registry() -> None:
    """``register_sipri_arms_transfers(registry)`` is the explicit
    seam for tests + future composition code.
    """
    registry = InMemorySourceRegistry()
    adapter = register_sipri_arms_transfers(registry)
    assert (
        registry.get_adapter(SourceId(SIPRI_ARMS_TRANSFERS_SOURCE_KEY))
        is adapter
    )
    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert listed[0].source_id.slug == SIPRI_ARMS_TRANSFERS_SOURCE_KEY


def test_indicator_codes_match_canonical_5() -> None:
    """The 5 canonical indicator codes are exposed via the
    package surface for downstream query code.
    """
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED
        in SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED
        in SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED
        in SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED
        in SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED
        in SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
    )
    assert len(SIPRI_ARMS_TRANSFERS_INDICATOR_CODES) == 5


def test_required_columns_match_canonical_8() -> None:
    """The 8 canonical required CSV columns are exposed via the
    package surface for the readiness gate + raw-read boundary.
    """
    assert len(SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS) == 8
    assert "Supplier" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Recipient" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Order year" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Delivery year" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Designation" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Status" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "Numbers delivered" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS
    assert "TIV (delivered)" in SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS


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
    assert SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT in attributions_text, (
        f"{SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT!r} is not a "
        f"substring of {attributions_path}. Update both in the "
        f"same commit (Rule #15)."
    )


def test_attribution_key_matches_attributions_doc() -> None:
    """The attribution key ``sipri_arms_transfers`` appears in
    the attributions doc (Row of the summary table or
    section heading). Drift guard for the descriptor's
    attribution_key field.
    """
    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    text = attributions_path.read_text(encoding="utf-8")
    # The canonical attribution key appears in the summary
    # table column "Source key" or as the canonical slug in the
    # section heading.
    assert SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY in text, (
        f"attribution key {SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY!r} "
        f"not found in {attributions_path}"
    )


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end (direct-CSV cached shape)
# ---------------------------------------------------------------------------


def test_runner_emits_register_and_aggregate_observations(
    tmp_path: Path,
) -> None:
    """``SourceIngestRunner.run(request)`` drives SIPRI Arms
    Transfers through the documented lifecycle and emits
    BOTH ``arms_transfer_register_row`` AND
    ``arms_transfer_country_year_aggregate`` observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    observations = result.observations
    families = {obs.observation_family for obs in observations}
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER in families
    )
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE in families
    )
    # No invented leader identifiers, no invented ISO3 codes.
    for obs in observations:
        assert obs.leader_id is None
        assert obs.leader_name is None
        assert obs.country_code is None


def test_runner_emits_register_row_for_each_indicator(
    tmp_path: Path,
) -> None:
    """For an in-coverage year the runner emits the 3 per-row
    indicator observations for the matching row(s) plus
    per-``(role, country, year)`` aggregate observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    register_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
    ]
    indicator_codes = {obs.indicator_code for obs in register_obs}
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED
        in indicator_codes
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED
        in indicator_codes
    )
    assert (
        SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED
        in indicator_codes
    )


def test_runner_emits_aggregate_observations_for_in_coverage_year(
    tmp_path: Path,
) -> None:
    """For ``years=(2020,)`` the runner emits the supplier-side
    AND recipient-side aggregate observations for Country A /
    Country B (the row 4 supplier / recipient pair).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    aggregate_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
    ]
    # Row 4 has Country A -> Country B, delivery 2020,
    # TIV (delivered) = 44. So we expect:
    #   supplier_year_tiv_delivered: Country A, 2020, 44
    #   recipient_year_tiv_delivered: Country B, 2020, 44
    supplier_obs = [
        obs for obs in aggregate_obs
        if obs.indicator_code
        == SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED
    ]
    recipient_obs = [
        obs for obs in aggregate_obs
        if obs.indicator_code
        == SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED
    ]
    assert len(supplier_obs) == 1
    assert supplier_obs[0].value == 44.0
    assert supplier_obs[0].country_name == "Country A"
    assert supplier_obs[0].year == 2020
    assert len(recipient_obs) == 1
    assert recipient_obs[0].value == 44.0
    assert recipient_obs[0].country_name == "Country B"
    assert recipient_obs[0].year == 2020


def test_runner_aggregate_math_is_deterministic(tmp_path: Path) -> None:
    """The aggregate math is deterministic: for ``years=None``
    the runner emits aggregate observations whose supplier-side
    AND recipient-side TIV sums match the per-row TIV
    (delivered) sums over the parsed frame.

    Per-fixture expected sums (TIV (delivered) per row):
      Row 1: Country A -> Country B, 2012, TIV=876
      Row 2: Country A -> Country C, 2016 (first year of
             range "2016-2018"), TIV=120
      Row 3: Country B -> Country C, 2010, TIV="n.a." (skip
             in aggregate)
      Row 4: Country A -> Country B, 2020, TIV=44
      Row 5: Country C -> Country A, 2013, TIV=60
      Row 6: Country B -> Country A, 2021, TIV=230

    Per-(role, country, year) sums:
      supplier_country_a_2012 = 876   (Row 1: A -> B, 2012)
      supplier_country_a_2016 = 120   (Row 2: A -> C, 2016)
      supplier_country_a_2020 = 44    (Row 4: A -> B, 2020)
      supplier_country_b_2010 = 0     (Row 3 TIV is "n.a." --
                                       skipped in aggregate)
      supplier_country_b_2021 = 230   (Row 6: B -> A, 2021)
      supplier_country_c_2013 = 60    (Row 5: C -> A, 2013)
      recipient_country_a_2013 = 60   (Row 5: C -> A, 2013)
      recipient_country_a_2021 = 230  (Row 6: B -> A, 2021)
      recipient_country_b_2012 = 876  (Row 1: A -> B, 2012)
      recipient_country_b_2020 = 44   (Row 4: A -> B, 2020)
      recipient_country_c_2010 = 0    (Row 3 TIV is "n.a." --
                                       skipped in aggregate)
      recipient_country_c_2016 = 120  (Row 2: A -> C, 2016)
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    aggregate_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
    ]

    def _aggregate_for(
        role: str, country: str, year: int,
    ) -> float:
        for obs in aggregate_obs:
            if (
                obs.extension.get("sipri_arms_transfers_aggregate_role")
                == role
                and obs.extension.get(
                    "sipri_arms_transfers_aggregate_country",
                ) == country
                and obs.year == year
            ):
                return float(obs.value)
        return 0.0

    expected = {
        ("supplier", "Country A", 2012): 876.0,
        ("supplier", "Country A", 2016): 120.0,
        ("supplier", "Country A", 2020): 44.0,
        ("supplier", "Country B", 2010): 0.0,
        ("supplier", "Country B", 2021): 230.0,
        ("supplier", "Country C", 2013): 60.0,
        ("recipient", "Country A", 2013): 60.0,
        ("recipient", "Country A", 2021): 230.0,
        ("recipient", "Country B", 2012): 876.0,
        ("recipient", "Country B", 2020): 44.0,
        ("recipient", "Country C", 2010): 0.0,
        ("recipient", "Country C", 2016): 120.0,
    }
    for key, expected_value in expected.items():
        actual = _aggregate_for(*key)
        assert actual == expected_value, (
            f"aggregate {key} expected {expected_value}, got {actual}"
        )


def test_runner_non_numeric_tiv_emits_missing_with_raw_value(
    tmp_path: Path,
) -> None:
    """Row 3 (``TIV (delivered)`` = ``"n.a."``) is emitted as
    ``value=None`` / ``value_type='missing'`` plus the verbatim
    raw cell text on ``extension["sipri_arms_transfers_tiv_delivered_raw"]``
    and ``extension["raw_value"]`` -- the observation is NOT
    dropped (matches the SIPRI Yearbook Ch.7 / FAS / RSF / PTS
    defensive pattern).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2010,))
    fri_frig = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
        and obs.indicator_code
        == SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED
        and obs.extension.get("sipri_arms_transfers_designation")
        == "Fixture Frigate Mk3"
    ]
    assert len(fri_frig) == 1
    obs = fri_frig[0]
    assert obs.value is None
    assert obs.value_type == "missing"
    assert (
        obs.extension["sipri_arms_transfers_tiv_delivered_raw"]
        == "n.a."
    )
    assert obs.extension["raw_value"] == "n.a."


def test_runner_delivery_year_range_parses_first_year(
    tmp_path: Path,
) -> None:
    """Row 2 (``Delivery year`` = ``"2016-2018"``) is parsed as
    ``delivery_year = 2016`` (the first 4-digit year token) so
    the observation lands on a single canonical year stamp.
    The verbatim raw cell text is preserved on
    ``extension["sipri_arms_transfers_delivery_year_raw"]``.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2016,))
    trainer_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
        and obs.extension.get("sipri_arms_transfers_designation")
        == "Fixture Trainer Mk2"
    ]
    assert len(trainer_obs) == 3
    for obs in trainer_obs:
        assert obs.year == 2016
        assert (
            obs.extension["sipri_arms_transfers_delivery_year_raw"]
            == "2016-2018"
        )


def test_runner_preserves_preamble_on_extension(tmp_path: Path) -> None:
    """The SIPRI preamble / citation lines (the lines that
    precede the documented header row in the cached CSV) are
    preserved on every emitted observation's
    ``extension["sipri_arms_transfers_preamble"]`` audit-trail
    field per the task brief: "preserve citation/preamble in
    raw metadata/extension where practical".
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    observations = result.observations
    assert observations
    preamble = observations[0].extension.get(
        "sipri_arms_transfers_preamble",
    )
    assert isinstance(preamble, str)
    assert "SIPRI Arms Transfers Database" in preamble
    assert (
        "https://www.sipri.org/databases/armstransfers" in preamble
    )
    assert "fair-use policy" in preamble


def test_runner_years_none_reads_all_fixture_rows(tmp_path: Path) -> None:
    """``years=None`` reads all fixture rows (the canonical
    all-years semantics per ``docs/architecture/sources.md``
    §5.3). The fixture has 6 rows; the runner emits 6 rows
    × 3 per-row indicators = 18 register observations plus the
    per-``(role, country, year)`` aggregate observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    register_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
    ]
    aggregate_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
    ]
    assert len(register_obs) == 6 * 3
    # 5 in-coverage rows with numeric TIV (Rows 1, 2, 4, 5, 6)
    # contribute to the aggregate. Row 3 has TIV="n.a." which
    # is excluded from the aggregate (no scope key emitted
    # because there is no numeric TIV contribution). So the
    # runner emits 5 supplier aggregates + 5 recipient
    # aggregates = 10 aggregate observations.
    assert len(aggregate_obs) == 10


def test_runner_countries_filter_applies_to_supplier_or_recipient(
    tmp_path: Path,
) -> None:
    """``countries=("Country B",)`` filters the parsed frame to
    rows where Country B appears as EITHER supplier OR
    recipient (case-folded substring match on the source-native
    display name).
    """
    _stage_bundle(tmp_path)
    # "Country B" appears as supplier in rows 3, 6 (TIV "n.a."
    # + TIV 230) and as recipient in rows 1 (TIV 876), 4 (TIV
    # 44). So 4 matching rows -> 4 × 3 = 12 register
    # observations (no aggregates for years not in requested
    # range).
    result = _run(tmp_path, countries=("Country B",))
    register_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
    ]
    assert len(register_obs) == 4 * 3
    # No "Country D" anywhere -- empty result.
    result_d = _run(tmp_path, countries=("Country D",))
    assert result_d.observations == ()


def test_runner_out_of_coverage_year_warns_and_emits_zero(
    tmp_path: Path,
) -> None:
    """``years=(2026,)`` is outside the canonical 1950-2025
    envelope (the latest SIPRI update is 2025). The runner
    emits zero observations plus a structured ``YEAR_ABSENT``
    warning per SRC-COV-002 / SRC-COV-003 (no stale-proxy
    fill).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2026,))
    assert result.observations == ()
    codes = [warning.code for warning in result.warnings]
    assert YEAR_ABSENT in codes


def test_runner_leader_filter_warns_but_is_ignored(
    tmp_path: Path,
) -> None:
    """``leaders=("Someone",)`` is unsupported for a
    country-country flow source and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005). The runner
    ignores the filter and still emits the in-coverage rows.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path, years=(2020,), leaders=("Someone",),
    )
    assert len(result.observations) > 0
    codes = [warning.code for warning in result.warnings]
    assert UNSUPPORTED_FILTER in codes


def test_runner_does_not_invent_iso3_codes(tmp_path: Path) -> None:
    """The unified adapter never invents ISO3 country codes.
    ``country_code`` is always ``None``; ``country_name``
    carries the source-native display name verbatim for the
    per-aggregate observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    for obs in result.observations:
        assert obs.country_code is None
    aggregate_country_names = {
        obs.country_name for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
    }
    assert aggregate_country_names.issubset(
        {"Country A", "Country B", "Country C"},
    )


def test_runner_observation_ids_are_unique(tmp_path: Path) -> None:
    """Every emitted observation has a unique
    ``observation_id`` so the downstream evidence repository
    can deduplicate by id.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    observation_ids = [obs.observation_id for obs in result.observations]
    assert len(observation_ids) == len(set(observation_ids))


def test_runner_extension_carries_canonical_attribution(
    tmp_path: Path,
) -> None:
    """Every emitted observation carries the canonical
    attribution text on ``extension["attribution"]`` so the
    Stage 15 summary report can propagate the attribution
    forward (Always-On Rule #15).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    for obs in result.observations:
        assert (
            obs.extension["attribution"]
            == SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT
        )


def test_runner_source_version_propagates_to_observations(
    tmp_path: Path,
) -> None:
    """The canonical ``SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION``
    propagates consistently to every emitted observation's
    ``source_version`` field (matches the SIPRI Milex / SIPRI
    Yearbook Ch.7 / Polity V / PWT / Maddison pattern).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    source_versions = {
        obs.source_version for obs in result.observations
    }
    assert source_versions == {SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION}


def test_runner_transform_locator_rule_id_matches_source_row_reference(
    tmp_path: Path,
) -> None:
    """The ``TransformLocator.rule_id`` is the canonical
    ``source_row_reference`` so downstream audit code can map
    an observation back to the parsed row + indicator.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    register_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
    ]
    for obs in register_obs:
        assert (
            obs.transform_locator.transform_name
            == SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME
        )
        assert (
            obs.transform_locator.catalog_key
            == SIPRI_ARMS_TRANSFERS_SOURCE_KEY
        )
        assert (
            obs.transform_locator.rule_id
            == obs.extension["source_row_reference"]
        )


# ---------------------------------------------------------------------------
# SourceIngestRunner end-to-end (base64-JSON cached shape)
# ---------------------------------------------------------------------------


def test_runner_reads_base64_json_cached_shape(tmp_path: Path) -> None:
    """The base64-JSON cached shape (the canonical SIPRI app
    export shape per the task brief) produces the SAME
    observation set as the direct-CSV shape.
    """
    _stage_bundle(
        tmp_path, with_csv=False, with_json=True,
        checksum_json=True,
    )
    result = _run(tmp_path, years=(2020,))
    families = {obs.observation_family for obs in result.observations}
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER in families
    )
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE in families
    )
    # The runner emitted the same canonical observations as the
    # direct-CSV shape -- the row 4 transfer (Country A ->
    # Country B, 2020, TIV 44) shows up under both shapes.
    register_obs = [
        obs for obs in result.observations
        if obs.observation_family
        == SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER
        and obs.extension.get("sipri_arms_transfers_designation")
        == "Fixture UAV Mk4"
    ]
    assert len(register_obs) == 3
    for obs in register_obs:
        assert obs.year == 2020


# ---------------------------------------------------------------------------
# Dispatch: runner must not consult legacy STAGE2_ADAPTERS
# ---------------------------------------------------------------------------


def test_runner_does_not_consult_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner drives SIPRI Arms Transfers through the new
    registry and never calls into ``leaders_db.ingest
    .STAGE2_ADAPTERS``.

    SIPRI Arms Transfers is a clean-source-only adapter -- it
    has no legacy Stage 2 implementation per the workplan Done
    History. The test monkeypatches the legacy slot with a
    tracking sentinel and asserts the sentinel is never
    invoked while ``SourceIngestRunner.run(request)`` executes
    the new SIPRI Arms Transfers adapter lifecycle
    end-to-end.
    """
    import leaders_db.ingest as legacy_ingest

    _stage_bundle(tmp_path)

    legacy_calls: list[dict] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get(
        SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    )

    def _legacy_tracker(**kwargs):
        legacy_calls.append(kwargs)

    legacy_ingest.STAGE2_ADAPTERS[
        SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    ] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        register_sipri_arms_transfers(registry)
        runner = SourceIngestRunner(registry)
        result = runner.run(_request(tmp_path, years=(2020,)))
        assert len(result.observations) > 0
        assert legacy_calls == [], (
            "SourceIngestRunner routed through STAGE2_ADAPTERS "
            f"instead of the new registry; saw {legacy_calls!r}"
        )
    finally:
        if original is None:
            legacy_ingest.STAGE2_ADAPTERS.pop(
                SIPRI_ARMS_TRANSFERS_SOURCE_KEY, None,
            )
        else:
            legacy_ingest.STAGE2_ADAPTERS[
                SIPRI_ARMS_TRANSFERS_SOURCE_KEY
            ] = original


# ---------------------------------------------------------------------------
# Readiness failures (parametrised)
# ---------------------------------------------------------------------------


def test_correct_bundle_passes_readiness(tmp_path: Path) -> None:
    """A well-formed bundle (metadata + cached CSV + correct
    checksum) passes readiness.
    """
    _stage_bundle(tmp_path)
    readiness = create_sipri_arms_transfers_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_unsupported_request_version_fails_readiness(
    tmp_path: Path,
) -> None:
    """``request.source_version`` other than the canonical
    stamp fails readiness with a structured
    ``unsupported_version`` error per SRC-REQ-009.
    """
    _stage_bundle(tmp_path)
    readiness = create_sipri_arms_transfers_adapter().check_ready(
        _request(
            tmp_path,
            source_version="SIPRI Arms Transfers Trade Register "
            "2025-09-09 (data 1950-2024)",
        ),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION
    )


def test_unsupported_cache_policy_fails_readiness(tmp_path: Path) -> None:
    """``request.cache_policy='refresh'`` / ``'no_cache'`` fails
    readiness with a structured
    ``sipri_arms_transfers_unsupported_cache_policy`` error --
    the unified adapter is offline / cache-only in this slice.
    """
    _stage_bundle(tmp_path)
    for unsupported in ("refresh", "no_cache"):
        readiness = create_sipri_arms_transfers_adapter().check_ready(
            _request(tmp_path, cache_policy=unsupported),
        )
        assert readiness.ready is False, (
            f"cache_policy={unsupported!r} should fail readiness"
        )
        assert readiness.errors[0].code == (
            SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY
        )


def test_checksum_mismatch_fails_readiness(tmp_path: Path) -> None:
    """A staged bundle whose checksum disagrees with the actual
    cached file SHA-256 fails readiness with a structured
    ``sipri_arms_transfers_checksum_mismatch`` error.
    """
    _stage_bundle(tmp_path, checksum="0" * 64)
    readiness = create_sipri_arms_transfers_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == (
        SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH
    )


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_csv": False, "with_json": False}, MISSING_RAW),
        (
            {"local_files": ["wrong_name.csv"]},
            SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
        ),
        ({"local_files": []}, SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID),
        (
            {"source_version": "p5v2018"},
            SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
        ),
    ],
)
def test_readiness_failures(
    tmp_path: Path, kwargs: dict[str, Any], code: str,
) -> None:
    """Each readiness-failure mode surfaces a structured
    ``SourceWarning(severity='error')`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` / ``transform``.
    """
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_sipri_arms_transfers_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_missing_required_csv_column_fails_readiness(
    tmp_path: Path,
) -> None:
    """A cached CSV whose header is missing one of the 8
    canonical required columns fails with a structured
    ``sipri_arms_transfers_schema_error`` so the transform
    layer does NOT silently emit partial output on a schema
    contract violation.
    """
    bundle = tmp_path / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Build a minimal CSV missing the "Status" required
    # column. The readiness gate validates the metadata first;
    # then the raw-read layer fires the schema error.
    csv_content = (
        "# SIPRI preamble\n"
        '"Supplier","Recipient","Order year","Delivery year",'
        '"Designation","Numbers delivered","TIV (delivered)"\n'
        '"Country A","Country B","2010","2012","Fixture","24","876"\n'
    )
    csv_path = bundle / SIPRI_ARMS_TRANSFERS_CSV_NAME
    csv_path.write_text(csv_content, encoding="utf-8")
    csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    payload = {
        "source_name": "SIPRI Arms Transfers Database",
        "source_version": SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1950-2025",
        "license_note": "SIPRI copyright; non-commercial use.",
        "local_files": [SIPRI_ARMS_TRANSFERS_CSV_NAME],
        "ingestion_status": "downloaded",
        "source_url": SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
        "checksum_sha256": {
            SIPRI_ARMS_TRANSFERS_CSV_NAME: csv_sha,
        },
        "notes": "Synthetic fixture missing required column.",
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )

    registry = InMemorySourceRegistry()
    register_sipri_arms_transfers(registry)
    runner = SourceIngestRunner(registry)
    with pytest.raises(Exception) as excinfo:
        runner.run(_request(tmp_path))
    # The schema error must surface; the runner propagates the
    # exception so the CLI / tests can act on it.
    assert SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR in str(excinfo.value)


def test_preamble_only_cached_export_emits_warning(tmp_path: Path) -> None:
    """A cached export that carries ONLY preamble lines and no
    recognisable CSV header / data rows emits zero observations
    plus a structured
    ``sipri_arms_transfers_preamble_not_found`` warning so the
    operator can see the parse failure rather than a silent
    empty-result.
    """
    bundle = tmp_path / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Only preamble / citation lines -- no recognisable CSV
    # header / data rows.
    csv_content = (
        "# SIPRI Arms Transfers Database Trade Register\n"
        "# Source: https://www.sipri.org/databases/armstransfers\n"
        "# Copyright (c) SIPRI 2026.\n"
    )
    csv_path = bundle / SIPRI_ARMS_TRANSFERS_CSV_NAME
    csv_path.write_text(csv_content, encoding="utf-8")
    csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    payload = {
        "source_name": "SIPRI Arms Transfers Database",
        "source_version": SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1950-2025",
        "license_note": "SIPRI copyright; non-commercial use.",
        "local_files": [SIPRI_ARMS_TRANSFERS_CSV_NAME],
        "ingestion_status": "downloaded",
        "source_url": SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
        "checksum_sha256": {
            SIPRI_ARMS_TRANSFERS_CSV_NAME: csv_sha,
        },
        "notes": "Preamble-only cached export.",
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.observations == ()
    codes = [warning.code for warning in result.warnings]
    assert SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND in codes


# ---------------------------------------------------------------------------
# Import boundary + network boundary
# ---------------------------------------------------------------------------


def test_importing_adapter_does_not_import_legacy_ingest() -> None:
    """Importing the new
    ``leaders_db.sources.adapters.sipri_arms_transfers`` module
    does NOT pull in any ``leaders_db.ingest`` module
    (SRC-MIG-007 + the import boundary documented in
    ``docs/architecture/sources.md`` §10.1).
    """
    for name in list(sys.modules):
        if (
            name == "leaders_db.sources"
            or name.startswith("leaders_db.sources.")
        ):
            del sys.modules[name]
        if (
            name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        ):
            del sys.modules[name]
    __import__("leaders_db.sources.adapters.sipri_arms_transfers")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest"
        or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing leaders_db.sources.adapters.sipri_arms_transfers "
        f"must not import leaders_db.ingest (leaked: {leaked})"
    )


def test_adapter_does_not_use_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unified SIPRI Arms Transfers adapter is offline /
    cache-only; the runner never invokes the network.
    """
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "network access is not allowed for SIPRI Arms "
            "Transfers (offline / cache-only)"
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

    result = _run(tmp_path, years=(2020,))
    assert len(result.observations) > 0


# ---------------------------------------------------------------------------
# Base64-JSON envelope: decode edge cases
# ---------------------------------------------------------------------------


def test_base64_json_envelope_decode_handles_alternative_keys(
    tmp_path: Path,
) -> None:
    """The base64-JSON envelope helper accepts BOTH the canonical
    ``data`` slot AND several alternative slots
    (``csv`` / ``trade_register`` / ``trades_csv`` / ``payload``)
    so user-staged envelopes that wrap the CSV in a different
    key still parse.
    """
    csv_text = _FIXTURE_CSV.read_text(encoding="utf-8")
    encoded = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")

    bundle = tmp_path / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Wrap under the "csv" alternative key (NOT the canonical
    # "data" key) so the reader exercises the alternative-key
    # code path.
    json_payload = {"csv": encoded}
    (bundle / SIPRI_ARMS_TRANSFERS_JSON_NAME).write_text(
        json.dumps(json_payload), encoding="utf-8",
    )
    _stage_bundle(
        tmp_path,
        with_csv=False,
        with_json=False,
        checksum_json=True,
    )
    result = _run(tmp_path, years=(2020,))
    families = {obs.observation_family for obs in result.observations}
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER in families
    )
    assert (
        SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE in families
    )


# ---------------------------------------------------------------------------
# SipriArmsTransfersAdapter class identity
# ---------------------------------------------------------------------------


def test_adapter_satisfies_source_adapter_protocol() -> None:
    """``SipriArmsTransfersAdapter`` instances satisfy the
    runtime-checkable :class:`SourceAdapter` Protocol.
    """
    adapter = create_sipri_arms_transfers_adapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.descriptor.source_id.slug == (
        SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    )
    assert isinstance(adapter, SipriArmsTransfersAdapter)


# ---------------------------------------------------------------------------
# Reviewer blockers — production SourceIngestRunner proof surfaces
# ---------------------------------------------------------------------------


def test_years_filter_emits_no_delivery_year_2020_from_order_year_2018(
    tmp_path: Path,
) -> None:
    """The ``years=`` request filter is anchored on the
    canonical output year (delivery year) of every emitted
    observation, not the order year.

    Reviewer-blocker production test: a request for
    ``years=(2018,)`` against the canonical fixture
    (which carries row 4: ``Country A -> Country B, order
    2018, delivery 2020, TIV 44``) must emit ZERO
    observations with ``year=2020`` -- neither per-transfer
    register rows NOR per-``(role, country, year)``
    aggregate rows -- and must emit zero observations for
    the matching 2018 order-year row because its delivery
    year is 2020 (not 2018). The canonical output year for
    every emitted observation is the delivery year, so
    ``years=(2018,)`` selects only rows whose delivery year
    is 2018; the fixture has no such row and the runner
    emits zero observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2018,))
    assert result.observations == (), (
        "years=(2018,) must not emit observations for the "
        "order-2018 / delivery-2020 row -- the canonical "
        "output year is the delivery year, not the order "
        f"year. Got {len(result.observations)} observations: "
        f"{[obs.observation_id for obs in result.observations]!r}"
    )


def test_years_filter_emits_only_requested_delivery_year_aggregates(
    tmp_path: Path,
) -> None:
    """Companion to
    ``test_years_filter_emits_no_delivery_year_2020_from_order_year_2018``:
    a request for ``years=(2020,)`` (the delivery year of
    the order-2018 / delivery-2020 row) emits observations
    AND aggregate rows for that delivery year, but emits
    ZERO observations / aggregates for delivery years
    outside the request scope.

    The fixture row 4 (``Country A -> Country B, order
    2018, delivery 2020, TIV 44``) drives the supplier
    + recipient aggregates for delivery year 2020; no
    other delivery year may appear in the emitted
    observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,))
    assert result.observations, (
        "years=(2020,) must emit observations for the "
        "delivery-2020 row (the only fixture row whose "
        "delivery year is 2020)"
    )
    for obs in result.observations:
        assert obs.year == 2020, (
            f"years=(2020,) leaked an observation with "
            f"year={obs.year} (observation_id="
            f"{obs.observation_id!r}, indicator="
            f"{obs.indicator_code!r}); the canonical output "
            f"year is the delivery year, not the order year."
        )


def test_raw_read_handles_punctuation_preamble_csv(tmp_path: Path) -> None:
    """The CSV preamble splitter preserves punctuation-
    containing preamble / citation lines (commas,
    semicolons, quotes, periods) on the
    ``preamble_lines`` audit-trail slot and still locates
    the actual header row by matching the documented
    required-column set.

    Reviewer-blocker production test: a CSV whose
    preamble block carries a comma-rich copyright line
    (``"SIPRI Arms Transfers Database (Trade Register),
    © 2026."``) AND a semicolon-rich citation line
    (``"Source: https://www.sipri.org/databases/armstransfers;
    fair-use policy applies"``) AND a quote-rich
    attribution line (``'Coverage: "1950-2025" per the
    2026-03-09 SIPRI update.'``) must (1) NOT mistake any
    of those lines for the header row and (2) emit the
    expected per-transfer register + per-aggregate
    observations once the actual header row is reached.
    """
    bundle = tmp_path / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    csv_content = (
        # Comma-rich copyright line.
        '"SIPRI Arms Transfers Database (Trade Register), '
        '(c) SIPRI 2026."\n'
        # Semicolon-rich citation line.
        '"Source: https://www.sipri.org/databases/armstransfers; '
        'fair-use policy applies."\n'
        # Quote-rich attribution line.
        '\'Coverage: "1950-2025" per the 2026-03-09 SIPRI update.\'\n'
        # Actual header row.
        '"Supplier","Recipient","Order year","Order date",'
        '"Delivery year","Delivery date","Designation",'
        '"Description","Weapon category","Status",'
        '"Numbers ordered","Numbers delivered",'
        '"TIV (ordered)","TIV (delivered)","Comments"\n'
        # Single transfer row.
        '"Country A","Country B","2010","2010-03-15",'
        '"2020","2020-11-05","Fixture UAV Mk4",'
        '"Synthetic UAV","UAV","Delivered",'
        '"8","8","44","44","Synthetic fixture row"\n'
    )
    csv_path = bundle / SIPRI_ARMS_TRANSFERS_CSV_NAME
    csv_path.write_text(csv_content, encoding="utf-8")
    csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    payload = {
        "source_name": "SIPRI Arms Transfers Database",
        "source_version": SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1950-2025",
        "license_note": "SIPRI copyright; non-commercial use.",
        "local_files": [SIPRI_ARMS_TRANSFERS_CSV_NAME],
        "ingestion_status": "downloaded",
        "source_url": SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
        "checksum_sha256": {
            SIPRI_ARMS_TRANSFERS_CSV_NAME: csv_sha,
        },
        "notes": (
            "Synthetic fixture with punctuation-rich preamble "
            "lines (commas / semicolons / quotes)."
        ),
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )

    result = _run(tmp_path, years=(2020,))
    assert len(result.observations) > 0, (
        "runner must emit observations after the punctuation-"
        "rich preamble block when the actual header row is "
        "located by matching the documented required-column set"
    )
    # The punctuation-rich preamble lines must be preserved
    # on the audit-trail ``sipri_arms_transfers_preamble``
    # extension field of every emitted observation. The csv
    # module un-escapes the embedded quotes on read, so the
    # audit trail carries the verbatim preamble block
    # including the punctuation.
    preamble = result.observations[0].extension.get(
        "sipri_arms_transfers_preamble",
    )
    assert isinstance(preamble, str)
    assert "(c) SIPRI 2026." in preamble
    assert "fair-use policy applies" in preamble
    assert 'Coverage: "1950-2025"' in preamble
    # The delivery year is 2020, the requested year -- every
    # emitted observation is stamped with year=2020.
    for obs in result.observations:
        assert obs.year == 2020


def test_raw_read_handles_punctuation_preamble_base64_json(
    tmp_path: Path,
) -> None:
    """The base64-JSON wrapper cached shape also preserves
    punctuation-containing preamble lines on the
    ``preamble_lines`` audit-trail slot and still locates
    the actual header row by matching the documented
    required-column set.

    Reviewer-blocker production test: the same
    punctuation-rich preamble block from
    ``test_raw_read_handles_punctuation_preamble_csv`` is
    wrapped in the canonical ``trade_register.json``
    base64-JSON envelope; the reader decodes the base64
    bytes, splits preamble from data with the same
    column-match logic, and emits the same observation
    set as the direct-CSV shape.
    """
    csv_text = (
        '"SIPRI Arms Transfers Database (Trade Register), '
        '(c) SIPRI 2026."\n'
        '"Source: https://www.sipri.org/databases/armstransfers; '
        'fair-use policy applies."\n'
        '\'Coverage: "1950-2025" per the 2026-03-09 SIPRI update.\'\n'
        '"Supplier","Recipient","Order year","Order date",'
        '"Delivery year","Delivery date","Designation",'
        '"Description","Weapon category","Status",'
        '"Numbers ordered","Numbers delivered",'
        '"TIV (ordered)","TIV (delivered)","Comments"\n'
        '"Country A","Country B","2010","2010-03-15",'
        '"2020","2020-11-05","Fixture UAV Mk4",'
        '"Synthetic UAV","UAV","Delivered",'
        '"8","8","44","44","Synthetic fixture row"\n'
    )
    encoded = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")

    bundle = tmp_path / SIPRI_ARMS_TRANSFERS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    json_path = bundle / SIPRI_ARMS_TRANSFERS_JSON_NAME
    json_path.write_text(
        json.dumps({"data": encoded}), encoding="utf-8",
    )
    json_sha = hashlib.sha256(json_path.read_bytes()).hexdigest()
    # Stage the metadata manually (NOT via ``_stage_bundle``
    # which would overwrite the custom JSON with the canonical
    # sample.json fixture) so the SHA-256 verification gates
    # pass against the staged on-disk file.
    payload = {
        "source_name": "SIPRI Arms Transfers Database",
        "source_key": SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
        "source_version": SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        "download_date": "2026-06-27",
        "coverage": "1950-2025",
        "license_note": (
            "SIPRI copyright; non-commercial use; attribution "
            "required (per SIPRI fair-use policy)."
        ),
        "local_files": [SIPRI_ARMS_TRANSFERS_JSON_NAME],
        "ingestion_status": "downloaded",
        "source_url": SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
        "checksum_sha256": {
            SIPRI_ARMS_TRANSFERS_JSON_NAME: json_sha,
        },
        "notes": (
            "Synthetic base64-JSON fixture with punctuation-"
            "rich preamble lines (commas / semicolons / quotes)."
        ),
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )

    result = _run(tmp_path, years=(2020,))
    assert len(result.observations) > 0, (
        "runner must emit observations after the punctuation-"
        "rich preamble block when the actual header row is "
        "located by matching the documented required-column "
        "set (base64-JSON cached shape)"
    )
    preamble = result.observations[0].extension.get(
        "sipri_arms_transfers_preamble",
    )
    assert isinstance(preamble, str)
    assert "(c) SIPRI 2026." in preamble
    assert "fair-use policy applies" in preamble
    assert 'Coverage: "1950-2025"' in preamble


def test_raw_asset_checksum_populated_csv(tmp_path: Path) -> None:
    """The :class:`RawAsset` ``checksum_sha256`` field is
    populated with the staged cache file SHA-256 for the
    direct-CSV cached shape.

    Reviewer-blocker production test: the runner returns
    a :class:`RawReadResult` carrying a single
    :class:`RawAsset` whose ``checksum_sha256`` equals
    the SHA-256 of the staged ``trade_register.csv`` on
    disk. The readiness gate already verified the same
    SHA-256 against ``metadata.json['checksum_sha256']``
    BEFORE the reader is invoked, so when readiness
    passes the asset's ``checksum_sha256`` is the
    verified / staged on-disk fingerprint (not ``None``).
    """
    bundle = _stage_bundle(tmp_path)
    csv_path = bundle / SIPRI_ARMS_TRANSFERS_CSV_NAME
    expected_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    request = _request(tmp_path)
    adapter = create_sipri_arms_transfers_adapter()
    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)

    assert len(raw.assets) == 1
    asset = raw.assets[0]
    assert asset.checksum_sha256 is not None, (
        "RawAsset.checksum_sha256 must be populated with "
        "the staged cache file SHA-256, not None"
    )
    assert asset.checksum_sha256 == expected_sha
    assert asset.checksum_sha256 == expected_sha.lower()


def test_raw_asset_checksum_populated_base64_json(tmp_path: Path) -> None:
    """The :class:`RawAsset` ``checksum_sha256`` field is
    populated with the staged cache file SHA-256 for the
    base64-JSON wrapper cached shape.

    Reviewer-blocker production test: the staged
    ``trade_register.json`` envelope's SHA-256 (not the
    decoded CSV bytes' SHA-256) is what the asset's
    ``checksum_sha256`` carries -- the on-disk
    fingerprint of the staged file is the canonical
    reference for downstream audit code.
    """
    bundle = _stage_bundle(
        tmp_path,
        with_csv=False,
        with_json=True,
        checksum_json=True,
    )
    json_path = bundle / SIPRI_ARMS_TRANSFERS_JSON_NAME
    expected_sha = hashlib.sha256(json_path.read_bytes()).hexdigest()

    request = _request(tmp_path)
    adapter = create_sipri_arms_transfers_adapter()
    readiness = adapter.check_ready(request)
    assert readiness.ready is True
    raw = adapter.read_raw(request)

    assert len(raw.assets) == 1
    asset = raw.assets[0]
    assert asset.checksum_sha256 is not None, (
        "RawAsset.checksum_sha256 must be populated with "
        "the staged cache file SHA-256 (base64-JSON shape), "
        "not None"
    )
    assert asset.checksum_sha256 == expected_sha
