"""REIGN clean-source adapter tests."""

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
from leaders_db.sources.adapters.reign import (
    REIGN_ATTRIBUTION_TEXT,
    REIGN_COVERAGE_END_YEAR,
    REIGN_COVERAGE_START_YEAR,
    REIGN_CSV_NAME,
    REIGN_DEFAULT_VERSION,
    REIGN_INDICATORS,
    REIGN_OBSERVATION_FAMILY,
    REIGN_SOURCE_KEY,
    create_reign_adapter,
    register_reign,
)
from leaders_db.sources.adapters.reign._constants import (
    REIGN_CHECKSUM_MISMATCH,
    REIGN_LOCAL_FILES_INVALID,
    REIGN_METADATA_VERSION_MISMATCH,
    REIGN_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_CSV = Path("tests/fixtures/reign/sample.csv")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_csv: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = REIGN_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / REIGN_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    csv_path = bundle / REIGN_CSV_NAME
    if with_csv:
        shutil.copy2(_FIXTURE_CSV, csv_path)
    if with_metadata:
        if checksum == "AUTO" and csv_path.is_file():
            checksum_value = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "REIGN",
            "source_version": source_version,
            "download_date": "2026-06-19",
            "coverage": "leader-month 1950-2021-08",
            "years_available": "1950-2021-08",
            "license_note": "Free academic; cite Bell 2016.",
            "local_files": [REIGN_CSV_NAME] if local_files is None else local_files,
            "ingestion_status": "downloaded",
            "source_url": "https://raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv",
            "row_count": 13,
            "column_count": 41,
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {REIGN_CSV_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(REIGN_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_reign(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_and_registry() -> None:
    adapter = create_reign_adapter()
    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == REIGN_SOURCE_KEY
    assert descriptor.attribution_key == REIGN_SOURCE_KEY
    assert descriptor.default_version == REIGN_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (REIGN_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == REIGN_COVERAGE_START_YEAR
    assert descriptor.coverage_hint.end_year == REIGN_COVERAGE_END_YEAR

    registry = InMemorySourceRegistry()
    returned = register_reign(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(REIGN_SOURCE_KEY)).descriptor == descriptor


def test_runner_emits_leader_month_observations(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,), countries=("USA",))
    observations = result.observations
    assert len(observations) == 16
    assert [obs.indicator_code for obs in observations[:8]] == list(REIGN_INDICATORS)
    assert {obs.observation_family for obs in observations} == {REIGN_OBSERVATION_FAMILY}
    assert {obs.year for obs in observations} == {2020}
    assert {obs.country_code for obs in observations} == {None}
    assert {obs.country_name for obs in observations} == {"USA"}
    assert {obs.leader_id for obs in observations} == {None}
    assert {obs.leader_name for obs in observations} == {"Trump"}

    leader = next(obs for obs in observations if obs.indicator_code == "reign_leader")
    assert leader.value == "Trump"
    assert leader.value_type == "text"
    assert leader.raw_locator.path.endswith(REIGN_CSV_NAME)
    assert leader.raw_locator.column_name == "leader"
    assert leader.transform_locator.rule_id == "reign:USA:Trump:2020:1:leader"
    assert leader.extension["source_row_reference"] == "reign:USA:Trump:2020:1:leader"
    assert leader.extension["reign_country"] == "USA"
    assert leader.extension["reign_ccode"] == 2
    assert leader.extension["reign_month"] == 1
    assert leader.extension["normalized_value"] is None
    assert leader.extension["attribution"] == REIGN_ATTRIBUTION_TEXT

    age = next(obs for obs in observations if obs.indicator_code == "reign_age")
    assert age.value == "74.0"
    assert age.value_type == "numeric"
    assert age.extension["normalized_value"] == 74.0
    assert age.unit == "age"

    male = next(obs for obs in observations if obs.indicator_code == "reign_male")
    assert male.value == "1"
    assert male.extension["normalized_value"] == 1
    assert male.scale == "0|1"


def test_years_none_reads_all_available_fixture_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("USA",))
    assert len(result.observations) == 40
    assert {obs.year for obs in result.observations} == {2020, 2021}
    assert {obs.extension["reign_month"] for obs in result.observations} == {1, 8}


def test_multi_year_request_reads_requested_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020, 2021), countries=("Mexico",))
    assert len(result.observations) == 32
    assert {obs.year for obs in result.observations} == {2020, 2021}
    assert {obs.leader_name for obs in result.observations} == {"Lopez Obrador"}


def test_out_of_coverage_2023_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_leader_filter_warns_but_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2020,), countries=("USA",), leaders=("Someone",))
    assert len(result.observations) == 16
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


def test_country_filter_applies_to_source_native_country_and_ccode(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    by_country = _run(tmp_path, years=(2020,), countries=("USA",))
    by_ccode = _run(tmp_path, years=(2020,), countries=("2",))
    absent = _run(tmp_path, years=(2020,), countries=("CAN",))
    assert len(by_country.observations) == 16
    assert len(by_ccode.observations) == 16
    assert absent.observations == ()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_csv": False}, MISSING_RAW),
        ({"local_files": []}, REIGN_LOCAL_FILES_INVALID),
        ({"local_files": ["wrong.csv"]}, REIGN_LOCAL_FILES_INVALID),
        ({"checksum": "0" * 64}, REIGN_CHECKSUM_MISMATCH),
        ({"source_version": "2021-7"}, REIGN_METADATA_VERSION_MISMATCH),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_reign_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_correct_checksum_passes_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_reign_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_reign_adapter().check_ready(
        _request(tmp_path, source_version="2021-7"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == REIGN_UNSUPPORTED_VERSION


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {REIGN_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2020,), countries=("USA",))
    assert len(result.observations) == 16


def test_importing_reign_adapter_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]

    __import__("leaders_db.sources.adapters.reign")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []


def test_adapter_does_not_use_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is not allowed for REIGN")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path, years=(2020,), countries=("USA",))
    assert len(result.observations) == 16


def test_attribution_text_matches_doc() -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert REIGN_ATTRIBUTION_TEXT in doc


def test_production_staged_bundle_smoke_if_present() -> None:
    root = Path("data/raw")
    bundle = root / REIGN_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (bundle / REIGN_CSV_NAME).is_file():
        pytest.skip("REIGN raw bundle is not staged locally")
    result = _run(root, years=(2021,), countries=("USA",))
    assert result.observations
    assert {obs.source_version for obs in result.observations} == {REIGN_DEFAULT_VERSION}
