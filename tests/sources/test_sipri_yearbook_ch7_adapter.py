"""SIPRI Yearbook Ch.7 clean-source adapter tests."""

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
    SourceAdapter,
    SourceId,
    SourceIngestRequest,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.sipri_yearbook_ch7 import (
    SIPRI_YEARBOOK_CH7_ADAPTER_FACTORY,
    SIPRI_YEARBOOK_CH7_ATTRIBUTION_TEXT,
    SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
    SIPRI_YEARBOOK_CH7_INDICATORS,
    SIPRI_YEARBOOK_CH7_OBSERVATION_FAMILY,
    SIPRI_YEARBOOK_CH7_PDF_NAME,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    create_sipri_yearbook_ch7_adapter,
    register_sipri_yearbook_ch7,
)
from leaders_db.sources.adapters.sipri_yearbook_ch7._constants import (
    SIPRI_YEARBOOK_CH7_CHECKSUM_MISMATCH,
    SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID,
    SIPRI_YEARBOOK_CH7_METADATA_VERSION_MISMATCH,
    SIPRI_YEARBOOK_CH7_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_PDF = Path("tests/fixtures/sipri_yearbook_ch7/sample.pdf")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_pdf: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / SIPRI_YEARBOOK_CH7_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    pdf_path = bundle / SIPRI_YEARBOOK_CH7_PDF_NAME
    if with_pdf:
        shutil.copy2(_FIXTURE_PDF, pdf_path)
    if with_metadata:
        if checksum == "AUTO" and pdf_path.is_file():
            checksum_value = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "SIPRI Yearbook Chapter 7 (World Nuclear Forces)",
            "source_key": SIPRI_YEARBOOK_CH7_SOURCE_KEY,
            "source_version": source_version,
            "download_date": "2026-06-18",
            "coverage": "nuclear country-year facts from a Yearbook PDF snapshot",
            "years_available": "2024",
            "license_note": "Free academic with attribution; cite SIPRI Yearbook.",
            "local_files": [SIPRI_YEARBOOK_CH7_PDF_NAME] if local_files is None else local_files,
            "ingestion_status": "downloaded",
            "source_url": "https://www.sipri.org/sites/default/files/YB24%2007%20WNF.pdf",
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {SIPRI_YEARBOOK_CH7_PDF_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(SIPRI_YEARBOOK_CH7_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_sipri_yearbook_ch7(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_register_and_protocol() -> None:
    adapter = create_sipri_yearbook_ch7_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert SIPRI_YEARBOOK_CH7_ADAPTER_FACTORY().descriptor == descriptor
    assert descriptor.source_id.slug == SIPRI_YEARBOOK_CH7_SOURCE_KEY
    assert descriptor.attribution_key == SIPRI_YEARBOOK_CH7_SOURCE_KEY
    assert descriptor.default_version == SIPRI_YEARBOOK_CH7_DEFAULT_VERSION
    assert descriptor.source_type == "document"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (SIPRI_YEARBOOK_CH7_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == 2024
    assert descriptor.coverage_hint.end_year == 2024

    registry = InMemorySourceRegistry()
    returned = register_sipri_yearbook_ch7(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(SIPRI_YEARBOOK_CH7_SOURCE_KEY)).descriptor == descriptor


def test_runner_emits_nuclear_country_year_observations(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2024,), countries=("United States",))
    observations = result.observations
    assert [obs.indicator_code for obs in observations] == list(SIPRI_YEARBOOK_CH7_INDICATORS)
    assert {obs.observation_family for obs in observations} == {
        SIPRI_YEARBOOK_CH7_OBSERVATION_FAMILY,
    }
    assert {obs.year for obs in observations} == {2024}
    assert {obs.country_code for obs in observations} == {None}
    assert {obs.country_name for obs in observations} == {"United States"}
    assert {obs.leader_id for obs in observations} == {None}
    assert {obs.leader_name for obs in observations} == {None}

    total = next(
        obs for obs in observations
        if obs.indicator_code == "sipri_yearbook_ch7_nuclear_warheads_total_inventory"
    )
    assert total.value == 5044
    assert total.value_type == "numeric"
    assert total.unit == "warheads"
    assert total.scale == "count"
    assert total.raw_locator.path.endswith(SIPRI_YEARBOOK_CH7_PDF_NAME)
    assert total.raw_locator.page_number == 1
    assert total.raw_locator.column_name == "total_inventory"
    assert total.transform_locator.rule_id == (
        "sipri_yearbook_ch7:United States:2024:"
        "sipri_yearbook_ch7_nuclear_warheads_total_inventory"
    )
    assert total.extension["source_row_reference"] == "sipri_yearbook_ch7:United States"
    assert total.extension["raw_value"] == "5 044"
    assert total.extension["normalized_value"] == 5044
    assert total.extension["pdf_pages_total"] == 1
    assert total.extension["snapshot_year"] == 2024
    assert total.extension["attribution"] == SIPRI_YEARBOOK_CH7_ATTRIBUTION_TEXT


def test_missing_values_are_represented_not_fabricated(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2024,), countries=("United Kingdom", "France"))
    retired = {
        obs.country_name: obs for obs in result.observations
        if obs.indicator_code == "sipri_yearbook_ch7_nuclear_warheads_retired"
    }
    assert retired["United Kingdom"].value == 0
    assert retired["United Kingdom"].value_type == "numeric"
    assert retired["United Kingdom"].extension["raw_value"] == "–"
    assert retired["France"].value is None
    assert retired["France"].value_type == "missing"
    assert retired["France"].extension["raw_value"] == ".."


def test_years_none_and_multi_year_requests(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    all_years = _run(tmp_path, countries=("China",))
    multi = _run(tmp_path, years=(2023, 2024), countries=("China",))
    assert len(all_years.observations) == 3
    assert len(multi.observations) == 3
    assert {obs.year for obs in all_years.observations} == {2024}
    assert [warning.code for warning in multi.warnings] == [YEAR_ABSENT]


def test_out_of_snapshot_year_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_country_filter_uses_source_native_display_name(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    present = _run(tmp_path, years=(2024,), countries=("United States",))
    absent = _run(tmp_path, years=(2024,), countries=("USA",))
    assert len(present.observations) == 3
    assert absent.observations == ()


def test_leader_filter_warns_but_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2024,), countries=("China",), leaders=("Someone",))
    assert len(result.observations) == 3
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_pdf": False}, MISSING_RAW),
        ({"local_files": []}, SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID),
        ({"local_files": ["YB24_07_WNF.pdf"]}, SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID),
        ({"checksum": "0" * 64}, SIPRI_YEARBOOK_CH7_CHECKSUM_MISMATCH),
        (
            {"source_version": "YB2023 (data: January 2023)"},
            SIPRI_YEARBOOK_CH7_METADATA_VERSION_MISMATCH,
        ),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_sipri_yearbook_ch7_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_correct_checksum_passes_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_sipri_yearbook_ch7_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_sipri_yearbook_ch7_adapter().check_ready(
        _request(tmp_path, source_version="YB2023 (data: January 2023)"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == SIPRI_YEARBOOK_CH7_UNSUPPORTED_VERSION


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {SIPRI_YEARBOOK_CH7_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2024,), countries=("United States",))
    assert len(result.observations) == 3


def test_importing_adapter_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]

    __import__("leaders_db.sources.adapters.sipri_yearbook_ch7")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []


def test_adapter_does_not_use_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is not allowed for SIPRI Yearbook Ch.7")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path, years=(2024,), countries=("United States",))
    assert len(result.observations) == 3


def test_attribution_text_matches_doc_and_no_invented_identity_fields(tmp_path: Path) -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert SIPRI_YEARBOOK_CH7_ATTRIBUTION_TEXT in doc
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2024,), countries=("China",))
    assert {obs.country_code for obs in result.observations} == {None}
    assert {obs.leader_id for obs in result.observations} == {None}
    assert {obs.leader_name for obs in result.observations} == {None}


def test_production_staged_bundle_smoke_if_present() -> None:
    root = Path("data/raw")
    bundle = root / SIPRI_YEARBOOK_CH7_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (
        bundle / SIPRI_YEARBOOK_CH7_PDF_NAME
    ).is_file():
        pytest.skip("SIPRI Yearbook Ch.7 raw bundle is not canonically staged locally")
    result = _run(root, years=(2024,), countries=("United States",))
    assert result.observations
    assert {obs.source_version for obs in result.observations} == {
        SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
    }
