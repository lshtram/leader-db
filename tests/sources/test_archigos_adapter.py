"""Archigos clean-source adapter tests."""

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
from leaders_db.sources.adapters.archigos import (
    ARCHIGOS_ATTRIBUTION_TEXT,
    ARCHIGOS_DEFAULT_VERSION,
    ARCHIGOS_DTA_NAME,
    ARCHIGOS_INDICATORS,
    ARCHIGOS_OBSERVATION_FAMILY,
    ARCHIGOS_SOURCE_KEY,
    create_archigos_adapter,
    register_archigos,
)
from leaders_db.sources.adapters.archigos._constants import (
    ARCHIGOS_CHECKSUM_MISMATCH,
    ARCHIGOS_LOCAL_FILES_INVALID,
    ARCHIGOS_METADATA_VERSION_MISMATCH,
    ARCHIGOS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_DTA = Path("tests/fixtures/archigos/sample.dta")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_dta: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = ARCHIGOS_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / ARCHIGOS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    dta = bundle / ARCHIGOS_DTA_NAME
    if with_dta:
        shutil.copy2(_FIXTURE_DTA, dta)
    if with_metadata:
        if checksum == "AUTO" and dta.is_file():
            checksum_value = hashlib.sha256(dta.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "Archigos",
            "source_version": source_version,
            "download_date": "2026-06-19",
            "coverage": "leader-spell",
            "years_available": "1840-2015",
            "license_note": "Free academic; cite Goemans et al. 2009.",
            "local_files": [ARCHIGOS_DTA_NAME] if local_files is None else local_files,
            "ingestion_status": "downloaded",
            "source_url": "https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta",
            "row_count": 5,
            "column_count": 28,
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {ARCHIGOS_DTA_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(ARCHIGOS_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_archigos(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_and_registry() -> None:
    adapter = create_archigos_adapter()
    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == ARCHIGOS_SOURCE_KEY
    assert descriptor.attribution_key == ARCHIGOS_SOURCE_KEY
    assert descriptor.default_version == ARCHIGOS_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (ARCHIGOS_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == 1840
    assert descriptor.coverage_hint.end_year == 2015

    registry = InMemorySourceRegistry()
    returned = register_archigos(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(ARCHIGOS_SOURCE_KEY)).descriptor == descriptor


def test_runner_emits_leader_spell_observations(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1869,), countries=("USA",))
    observations = result.observations
    assert [obs.indicator_code for obs in observations] == list(ARCHIGOS_INDICATORS)
    assert {obs.observation_family for obs in observations} == {ARCHIGOS_OBSERVATION_FAMILY}
    assert {obs.year for obs in observations} == {1869}
    assert {obs.country_code for obs in observations} == {None}
    assert {obs.leader_id for obs in observations} == {None}
    assert {obs.leader_name for obs in observations} == {"Grant"}

    leader = next(obs for obs in observations if obs.indicator_code == "archigos_leader_name")
    assert leader.value == "Grant"
    assert leader.value_type == "text"
    assert leader.raw_locator.path.endswith(ARCHIGOS_DTA_NAME)
    assert leader.raw_locator.column_name == "leader"
    assert leader.transform_locator.rule_id == "archigos:USA-1869:1869:leader"
    assert leader.extension["source_row_reference"] == "archigos:USA-1869:1869:leader"
    assert leader.extension["archigos_obsid"] == "USA-1869"
    assert leader.extension["archigos_idacr"] == "USA"
    assert leader.extension["archigos_ccode"] == 2
    assert leader.extension["normalized_value"] is None
    assert leader.extension["attribution"] == ARCHIGOS_ATTRIBUTION_TEXT

    start = next(obs for obs in observations if obs.indicator_code == "archigos_tenure_start_date")
    assert start.value == "1869-03-04"
    assert start.unit == "date"
    assert start.scale == "YYYY-MM-DD"
    assert abs(float(start.extension["normalized_value"]) - 1869.170) < 0.01

    entry = next(obs for obs in observations if obs.indicator_code == "archigos_entry_type")
    assert entry.value == "Regular"
    assert entry.value_type == "categorical"
    assert entry.extension["normalized_value"] == 1
    assert entry.extension["higher_is_better"] is False


def test_years_none_reads_all_available_start_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("USA",))
    assert len(result.observations) == 30
    assert {obs.year for obs in result.observations} == {1869, 1877, 1881, 1885}


def test_multi_year_request_reads_requested_start_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1869, 1881), countries=("USA",))
    assert len(result.observations) == 18
    assert {obs.year for obs in result.observations} == {1869, 1881}
    assert {obs.extension["archigos_obsid"] for obs in result.observations} == {
        "USA-1869",
        "USA-1881-1",
        "USA-1881-2",
    }


def test_out_of_coverage_2023_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_leader_filter_warns_but_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1869,), countries=("USA",), leaders=("Someone",))
    assert len(result.observations) == 6
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


def test_country_filter_applies_to_source_native_idacr_and_ccode(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    by_idacr = _run(tmp_path, years=(1881,), countries=("USA",))
    by_ccode = _run(tmp_path, years=(1881,), countries=("2",))
    absent = _run(tmp_path, years=(1881,), countries=("CAN",))
    assert len(by_idacr.observations) == 12
    assert len(by_ccode.observations) == 12
    assert absent.observations == ()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_dta": False}, MISSING_RAW),
        ({"local_files": []}, ARCHIGOS_LOCAL_FILES_INVALID),
        ({"local_files": ["wrong.dta"]}, ARCHIGOS_LOCAL_FILES_INVALID),
        ({"checksum": "0" * 64}, ARCHIGOS_CHECKSUM_MISMATCH),
        ({"source_version": "v4.0"}, ARCHIGOS_METADATA_VERSION_MISMATCH),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_archigos_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_correct_checksum_passes_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_archigos_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_archigos_adapter().check_ready(
        _request(tmp_path, source_version="v4.0"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == ARCHIGOS_UNSUPPORTED_VERSION


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {ARCHIGOS_SOURCE_KEY: None})
    result = _run(tmp_path, years=(1869,), countries=("USA",))
    assert len(result.observations) == 6


def test_importing_archigos_adapter_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]

    __import__("leaders_db.sources.adapters.archigos")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []


def test_adapter_does_not_use_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is not allowed for Archigos")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path, years=(1869,), countries=("USA",))
    assert len(result.observations) == 6


def test_attribution_text_matches_doc() -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert ARCHIGOS_ATTRIBUTION_TEXT in doc


def test_production_staged_bundle_smoke_if_present() -> None:
    root = Path("data/raw")
    bundle = root / ARCHIGOS_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (bundle / ARCHIGOS_DTA_NAME).is_file():
        pytest.skip("Archigos raw bundle is not staged locally")
    result = _run(root, years=(1881,), countries=("USA",))
    assert len(result.observations) == 12
    assert {obs.extension["archigos_idacr"] for obs in result.observations} == {"USA"}
