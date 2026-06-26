"""SIPRI Milex clean-source adapter tests."""

from __future__ import annotations

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
    SourceId,
    SourceIngestRequest,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.sipri_milex import (
    SIPRI_MILEX_ATTRIBUTION_TEXT,
    SIPRI_MILEX_COVERAGE_END_YEAR,
    SIPRI_MILEX_COVERAGE_START_YEAR,
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_INDICATORS,
    SIPRI_MILEX_OBSERVATION_FAMILY,
    SIPRI_MILEX_SOURCE_KEY,
    SIPRI_MILEX_XLSX_NAME,
    create_sipri_milex_adapter,
    register_sipri_milex,
)
from leaders_db.sources.adapters.sipri_milex._constants import (
    SIPRI_MILEX_CHECKSUM_MISMATCH,
    SIPRI_MILEX_LOCAL_FILES_INVALID,
    SIPRI_MILEX_METADATA_VERSION_MISMATCH,
    SIPRI_MILEX_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_XLSX = Path("tests/fixtures/sipri_milex/sample.xlsx")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_xlsx: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = SIPRI_MILEX_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / SIPRI_MILEX_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    xlsx_path = bundle / SIPRI_MILEX_XLSX_NAME
    if with_xlsx:
        shutil.copy2(_FIXTURE_XLSX, xlsx_path)
    if with_metadata:
        if checksum == "AUTO" and xlsx_path.is_file():
            checksum_value = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "SIPRI Military Expenditure Database",
            "source_key": SIPRI_MILEX_SOURCE_KEY,
            "source_version": source_version,
            "download_date": "2026-06-18",
            "coverage": "country-year military expenditure indicators",
            "years_available": "1949-2025",
            "license_note": "Free public dataset; cite SIPRI milex.",
            "local_files": [SIPRI_MILEX_XLSX_NAME] if local_files is None else local_files,
            "ingestion_status": "downloaded",
            "source_url": "https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx",
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {SIPRI_MILEX_XLSX_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(SIPRI_MILEX_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_sipri_milex(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_and_registry() -> None:
    adapter = create_sipri_milex_adapter()
    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == SIPRI_MILEX_SOURCE_KEY
    assert descriptor.attribution_key == SIPRI_MILEX_SOURCE_KEY
    assert descriptor.default_version == SIPRI_MILEX_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (SIPRI_MILEX_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == SIPRI_MILEX_COVERAGE_START_YEAR
    assert descriptor.coverage_hint.end_year == SIPRI_MILEX_COVERAGE_END_YEAR

    registry = InMemorySourceRegistry()
    returned = register_sipri_milex(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(SIPRI_MILEX_SOURCE_KEY)).descriptor == descriptor


def test_runner_emits_country_year_milex_observations(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,), countries=("United States of America",))
    observations = result.observations
    assert len(observations) == 4
    assert [obs.indicator_code for obs in observations] == list(SIPRI_MILEX_INDICATORS)
    assert {obs.observation_family for obs in observations} == {SIPRI_MILEX_OBSERVATION_FAMILY}
    assert {obs.year for obs in observations} == {2023}
    assert {obs.country_code for obs in observations} == {None}
    assert {obs.country_name for obs in observations} == {"United States of America"}
    assert {obs.leader_id for obs in observations} == {None}
    assert {obs.leader_name for obs in observations} == {None}

    constant_usd = next(
        obs for obs in observations
        if obs.indicator_code == "sipri_milex_constant_usd"
    )
    assert constant_usd.value == 834000.0
    assert constant_usd.value_type == "numeric"
    assert constant_usd.unit == "usd_millions_2024"
    assert constant_usd.scale == "usd_millions"
    assert constant_usd.raw_locator.path.endswith(SIPRI_MILEX_XLSX_NAME)
    assert constant_usd.raw_locator.sheet == "Constant (2024) US$"
    assert constant_usd.raw_locator.column_name == "2023"
    assert constant_usd.transform_locator.rule_id == (
        "sipri_milex:United States of America:2023:sipri_milex_constant_usd"
    )
    assert constant_usd.extension["source_row_reference"] == (
        "sipri_milex:United States of America"
    )
    assert constant_usd.extension["raw_value"] == 834000
    assert constant_usd.extension["normalized_value"] == 834000.0
    assert constant_usd.extension["regions_covered"] == ["Africa", "Americas"]
    assert constant_usd.extension["country_count"] == 5
    assert constant_usd.extension["attribution"] == SIPRI_MILEX_ATTRIBUTION_TEXT


def test_missing_values_are_skipped_not_fabricated(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,), countries=("Mexico", "Nigeria"))
    indicators_by_country = {
        obs.country_name: {
            item.indicator_code for item in result.observations
            if item.country_name == obs.country_name
        }
        for obs in result.observations
    }
    assert "sipri_milex_share_of_govt_spending" not in indicators_by_country["Mexico"]
    assert "sipri_milex_share_of_gdp" not in indicators_by_country["Nigeria"]
    assert len(result.observations) == 6


def test_years_none_reads_all_available_fixture_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Mexico",))
    assert len(result.observations) == 7
    assert {obs.year for obs in result.observations} == {2022, 2023}


def test_multi_year_request_reads_requested_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022, 2023), countries=("Sweden",))
    assert len(result.observations) == 8
    assert {obs.year for obs in result.observations} == {2022, 2023}


def test_out_of_coverage_year_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1948,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_leader_filter_warns_but_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        years=(2023,),
        countries=("United States of America",),
        leaders=("Someone",),
    )
    assert len(result.observations) == 4
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


def test_country_filter_applies_to_source_native_display_name(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    present = _run(tmp_path, years=(2023,), countries=("United States of America",))
    absent = _run(tmp_path, years=(2023,), countries=("USA",))
    assert len(present.observations) == 4
    assert absent.observations == ()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_xlsx": False}, MISSING_RAW),
        ({"local_files": []}, SIPRI_MILEX_LOCAL_FILES_INVALID),
        ({"local_files": ["wrong.xlsx"]}, SIPRI_MILEX_LOCAL_FILES_INVALID),
        ({"checksum": "0" * 64}, SIPRI_MILEX_CHECKSUM_MISMATCH),
        ({"source_version": "v1.2 (1949-2025)"}, SIPRI_MILEX_METADATA_VERSION_MISMATCH),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_sipri_milex_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_correct_checksum_passes_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_sipri_milex_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_sipri_milex_adapter().check_ready(
        _request(tmp_path, source_version="v1.2 (1949-2025)"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == SIPRI_MILEX_UNSUPPORTED_VERSION


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {SIPRI_MILEX_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2023,), countries=("United States of America",))
    assert len(result.observations) == 4


def test_importing_sipri_milex_adapter_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]

    __import__("leaders_db.sources.adapters.sipri_milex")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []


def test_adapter_does_not_use_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is not allowed for SIPRI Milex")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path, years=(2023,), countries=("United States of America",))
    assert len(result.observations) == 4


def test_attribution_text_matches_doc() -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert SIPRI_MILEX_ATTRIBUTION_TEXT in doc


def test_production_staged_bundle_smoke_if_present() -> None:
    root = Path("data/raw")
    bundle = root / SIPRI_MILEX_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (bundle / SIPRI_MILEX_XLSX_NAME).is_file():
        pytest.skip("SIPRI Milex raw bundle is not staged locally")
    result = _run(root, years=(2023,), countries=("United States of America",))
    assert result.observations
    assert {obs.source_version for obs in result.observations} == {SIPRI_MILEX_DEFAULT_VERSION}
