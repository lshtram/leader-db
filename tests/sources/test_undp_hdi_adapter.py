"""UNDP HDI clean-source adapter tests."""

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
    SourceIngestRunner,
)
from leaders_db.sources.adapters.undp_hdi import (
    UNDP_HDI_ADAPTER_FACTORY,
    UNDP_HDI_ATTRIBUTION_TEXT,
    UNDP_HDI_COVERAGE_END_YEAR,
    UNDP_HDI_COVERAGE_START_YEAR,
    UNDP_HDI_CSV_NAME,
    UNDP_HDI_DEFAULT_VERSION,
    UNDP_HDI_INDICATORS,
    UNDP_HDI_OBSERVATION_FAMILY,
    UNDP_HDI_PROXY_REQUESTED_YEAR,
    UNDP_HDI_PROXY_YEAR,
    UNDP_HDI_SOURCE_KEY,
    create_undp_hdi_adapter,
    register_undp_hdi,
)
from leaders_db.sources.adapters.undp_hdi._constants import (
    UNDP_HDI_CHECKSUM_MISMATCH,
    UNDP_HDI_LOCAL_FILES_INVALID,
    UNDP_HDI_METADATA_VERSION_MISMATCH,
    UNDP_HDI_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_CSV = Path("tests/fixtures/undp_hdi/sample.csv")


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_csv: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = UNDP_HDI_DEFAULT_VERSION,
    legacy_metadata: bool = False,
) -> Path:
    bundle = raw_root / UNDP_HDI_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    csv_path = bundle / UNDP_HDI_CSV_NAME
    if with_csv:
        shutil.copy2(_FIXTURE_CSV, csv_path)
    if with_metadata:
        if checksum == "AUTO" and csv_path.is_file():
            checksum_value = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "UNDP Human Development Index",
            "source_key": UNDP_HDI_SOURCE_KEY,
            "download_date": "2026-06-20",
            "source_url": "https://hdr.undp.org/",
            "license_note": "Free public dataset; cite UNDP HDR.",
            "ingestion_status": "downloaded",
        }
        if legacy_metadata:
            payload["version"] = source_version
            if checksum_value is not None:
                payload["sha256"] = checksum_value
        else:
            payload["source_version"] = source_version
            payload["local_files"] = [UNDP_HDI_CSV_NAME] if local_files is None else local_files
            if checksum_value is not None:
                payload["checksum_sha256"] = {UNDP_HDI_CSV_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(UNDP_HDI_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_undp_hdi(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_register_and_protocol() -> None:
    adapter = create_undp_hdi_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert UNDP_HDI_ADAPTER_FACTORY().descriptor == descriptor
    assert descriptor.source_id.slug == UNDP_HDI_SOURCE_KEY
    assert descriptor.attribution_key == UNDP_HDI_SOURCE_KEY
    assert descriptor.default_version == UNDP_HDI_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (UNDP_HDI_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == UNDP_HDI_COVERAGE_START_YEAR
    assert descriptor.coverage_hint.end_year == UNDP_HDI_COVERAGE_END_YEAR
    assert "2023" in str(descriptor.coverage_hint.notes)
    assert "social_wellbeing" in str(descriptor.coverage_hint.notes)

    registry = InMemorySourceRegistry()
    returned = register_undp_hdi(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(UNDP_HDI_SOURCE_KEY)).descriptor == descriptor


def test_runner_years_none_reads_all_fixture_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path, legacy_metadata=True)
    result = _run(tmp_path)
    assert {obs.year for obs in result.observations} == {1990, 2022}
    assert len(result.observations) == 38
    assert {obs.indicator_code for obs in result.observations} == set(UNDP_HDI_INDICATORS)


def test_runner_reads_requested_2022_country_year(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022,), countries=("USA",))
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {2022}
    assert {obs.country_code for obs in result.observations} == {"USA"}
    assert {obs.country_name for obs in result.observations} == {"United States"}
    assert {obs.leader_id for obs in result.observations} == {None}
    assert {obs.leader_name for obs in result.observations} == {None}

    hdi = next(obs for obs in result.observations if obs.indicator_code == "undp_hdi_hdi")
    assert hdi.value == 0.927
    assert hdi.value_type == "numeric"
    assert hdi.unit == "index"
    assert hdi.scale == "0-1"
    assert hdi.observation_family == UNDP_HDI_OBSERVATION_FAMILY
    assert hdi.raw_locator.path.endswith(UNDP_HDI_CSV_NAME)
    assert hdi.raw_locator.row_number is None
    assert hdi.raw_locator.column_name == "hdi_2022"
    assert hdi.transform_locator.rule_id == "undp_hdi:USA:2022:undp_hdi_hdi"
    assert hdi.extension["source_row_reference"] == "undp_hdi:USA"
    assert hdi.extension["raw_value"] == "0.927"
    assert hdi.extension["normalized_value"] == 0.927
    assert hdi.extension["attribution"] == (
        "UNDP HDR 2023-24 (United Nations Development Programme 2024)."
    )
    assert hdi.extension["region"] == ""
    assert hdi.extension["hdicode"] == "Very High"
    assert hdi.extension["category"] == "social_wellbeing"
    assert hdi.extension["attribution"] == UNDP_HDI_ATTRIBUTION_TEXT


def test_proxy_2023_emits_actual_2022_rows_with_proxy_metadata(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(UNDP_HDI_PROXY_REQUESTED_YEAR,), countries=("MEX",))
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {UNDP_HDI_PROXY_YEAR}
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]
    obs = result.observations[0]
    assert obs.extension["requested_year"] == UNDP_HDI_PROXY_REQUESTED_YEAR
    assert obs.extension["proxy_year"] == UNDP_HDI_PROXY_YEAR
    assert "proxy" in str(obs.extension["proxy_year_semantics"])


def test_multi_year_2022_and_2023_deduplicates_proxy_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022, 2023), countries=("Mexico",))
    assert len(result.observations) == 5
    assert {obs.year for obs in result.observations} == {2022}
    assert len({obs.observation_id for obs in result.observations}) == 5


def test_country_filter_matches_iso3_or_source_display(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    by_iso3 = _run(tmp_path, years=(2022,), countries=("CIV",))
    by_display = _run(tmp_path, years=(2022,), countries=("Côte d'Ivoire",))
    absent = _run(tmp_path, years=(2022,), countries=("Ivory Coast",))
    assert len(by_iso3.observations) == 5
    assert len(by_display.observations) == 5
    assert absent.observations == ()


def test_leader_filter_warns_and_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022,), countries=("MEX",), leaders=("Someone",))
    assert len(result.observations) == 5
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


def test_missing_cells_are_skipped_not_fabricated(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1990,), countries=("NGA",))
    assert len(result.observations) == 3
    assert {obs.indicator_code for obs in result.observations} == {
        "undp_hdi_life_expectancy",
        "undp_hdi_expected_years_schooling",
        "undp_hdi_gni_per_capita",
    }


def test_out_of_coverage_year_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1989,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_csv": False}, MISSING_RAW),
        ({"local_files": []}, UNDP_HDI_LOCAL_FILES_INVALID),
        ({"local_files": ["wrong.csv"]}, UNDP_HDI_LOCAL_FILES_INVALID),
        ({"source_version": "2022"}, UNDP_HDI_METADATA_VERSION_MISMATCH),
        ({"checksum": "0" * 64}, UNDP_HDI_CHECKSUM_MISMATCH),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_legacy_metadata_without_local_files_requires_source_key_and_sha256(tmp_path: Path) -> None:
    _stage_bundle(tmp_path, legacy_metadata=True)
    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True

    payload = json.loads((tmp_path / UNDP_HDI_SOURCE_KEY / "metadata.json").read_text())
    payload["source_key"] = "other"
    (tmp_path / UNDP_HDI_SOURCE_KEY / "metadata.json").write_text(json.dumps(payload))
    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == UNDP_HDI_LOCAL_FILES_INVALID


def test_request_version_mismatch_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path, source_version="other"))
    assert readiness.ready is False
    assert readiness.errors[0].code == UNDP_HDI_UNSUPPORTED_VERSION


def test_new_metadata_checksum_passes_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_new_metadata_without_local_files_passes_when_checksum_dict_present(
    tmp_path: Path,
) -> None:
    _stage_bundle(tmp_path)
    metadata_path = tmp_path / UNDP_HDI_SOURCE_KEY / "metadata.json"
    payload = json.loads(metadata_path.read_text())
    payload.pop("local_files")
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    readiness = create_undp_hdi_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {UNDP_HDI_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2022,), countries=("MEX",))
    assert len(result.observations) == 5


def test_importing_undp_hdi_adapter_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]
    importlib.import_module("leaders_db.sources.adapters.undp_hdi")
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []
