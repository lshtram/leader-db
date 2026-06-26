"""CIRIGHTS clean-source adapter tests."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from leaders_db.sources import (
    InMemorySourceRegistry,
    RawReadResult,
    SourceAdapter,
    SourceId,
    SourceIngestRequest,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.cirights import (
    CIRIGHTS_ADAPTER_FACTORY,
    CIRIGHTS_ATTRIBUTION_TEXT,
    CIRIGHTS_DEFAULT_VERSION,
    CIRIGHTS_INDICATORS,
    CIRIGHTS_OBSERVATION_FAMILY,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_XLSX_NAME,
    create_cirights_adapter,
    register_cirights,
)
from leaders_db.sources.adapters.cirights._constants import (
    CIRIGHTS_CHECKSUM_MISMATCH,
    CIRIGHTS_LOCAL_FILES_INVALID,
    CIRIGHTS_METADATA_VERSION_MISMATCH,
    CIRIGHTS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_xlsx: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = CIRIGHTS_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / CIRIGHTS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    xlsx_path = bundle / CIRIGHTS_XLSX_NAME
    if with_xlsx:
        fixture = Path("tests/fixtures/cirights/sample.xlsx")
        shutil.copy2(fixture, xlsx_path)
    if with_metadata:
        if checksum == "AUTO" and xlsx_path.is_file():
            checksum_value = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "CIRI Human Rights Data Project",
            "source_version": source_version,
            "download_date": "2026-06-17",
            "source_url": "https://www.cirights.org/",
            "license_note": "Free academic use with attribution; user-managed raw files.",
            "coverage_start_year": 1981,
            "coverage_end_year": 2022,
            "local_files": [
                CIRIGHTS_XLSX_NAME,
                "cirights_v3.12.10.24.dta.zip",
                "CIRIGHTS_Codebook_v2.8.27.23.pdf",
            ]
            if local_files is None
            else local_files,
            "ingestion_status": "downloaded",
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {
                CIRIGHTS_XLSX_NAME: checksum_value,
                "extra-file.zip": "0" * 64,
            }
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(CIRIGHTS_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_cirights(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_register_and_protocol() -> None:
    adapter = create_cirights_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert CIRIGHTS_ADAPTER_FACTORY().descriptor == descriptor
    assert descriptor.source_id.slug == CIRIGHTS_SOURCE_KEY
    assert descriptor.attribution_key == CIRIGHTS_SOURCE_KEY
    assert descriptor.default_version == CIRIGHTS_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.supported_observation_families == (CIRIGHTS_OBSERVATION_FAMILY,)
    assert descriptor.coverage_hint.start_year == 1981
    assert descriptor.coverage_hint.end_year == 2022
    assert "2023" in str(descriptor.coverage_hint.notes)

    registry = InMemorySourceRegistry()
    returned = register_cirights(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(CIRIGHTS_SOURCE_KEY)).descriptor == descriptor


def test_runner_years_none_reads_all_fixture_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert {obs.year for obs in result.observations} == {2021, 2022}
    assert len(result.observations) == 66
    assert {obs.indicator_code for obs in result.observations} == set(CIRIGHTS_INDICATORS)


def test_runner_reads_requested_2022_country_year(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022,), countries=("Norway",))
    assert len(result.observations) == 7
    assert {obs.country_name for obs in result.observations} == {"Norway"}
    assert {obs.year for obs in result.observations} == {2022}

    physint = next(obs for obs in result.observations if obs.indicator_code == "cirights_physint")
    assert physint.value == 8
    assert physint.extension["normalized_value"] == 8.0
    assert physint.extension["higher_is_better"] is True
    assert physint.observation_family == CIRIGHTS_OBSERVATION_FAMILY
    assert physint.country_code is None
    assert physint.leader_id is None
    assert physint.leader_name is None
    assert physint.raw_locator.path.endswith(CIRIGHTS_XLSX_NAME)
    assert physint.raw_locator.sheet == "Sheet1"
    assert physint.raw_locator.row_number is None
    assert physint.raw_locator.column_name == "Physical Integrity Rights Index"
    assert physint.extension["source_row_reference"] == (
        "cirights:Norway:2022:Physical Integrity Rights Index"
    )
    assert physint.transform_locator.rule_id == physint.extension["source_row_reference"]
    assert physint.extension["attribution"] == CIRIGHTS_ATTRIBUTION_TEXT


def test_filtered_locator_does_not_synthesize_row_number(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(CIRIGHTS_PROXY_REQUESTED_YEAR,), countries=("Mexico",))
    assert result.observations
    assert {obs.raw_locator.row_number for obs in result.observations} == {None}
    assert {obs.raw_locator.sheet for obs in result.observations} == {"Sheet1"}
    assert all(obs.raw_locator.path.endswith(CIRIGHTS_XLSX_NAME) for obs in result.observations)


def test_proxy_2023_emits_actual_2022_rows_with_proxy_metadata(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(CIRIGHTS_PROXY_REQUESTED_YEAR,), countries=("Mexico",))
    assert len(result.observations) == 7
    assert {obs.year for obs in result.observations} == {CIRIGHTS_PROXY_YEAR}
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]
    obs = result.observations[0]
    assert obs.extension["requested_year"] == CIRIGHTS_PROXY_REQUESTED_YEAR
    assert obs.extension["proxy_year"] == CIRIGHTS_PROXY_YEAR
    assert "proxy" in str(obs.extension["proxy_year_semantics"])


def test_multi_year_2022_and_2023_deduplicates_proxy_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022, 2023), countries=("Mexico",))
    assert len(result.observations) == 7
    assert {obs.year for obs in result.observations} == {2022}
    assert len({obs.observation_id for obs in result.observations}) == 7


def test_country_filter_matches_source_native_display_name(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022,), countries=("United States of America",))
    assert len(result.observations) == 5
    assert {obs.country_name for obs in result.observations} == {"United States of America"}
    assert all("United_States_of_America" in obs.observation_id for obs in result.observations)


def test_leader_filter_warns_and_is_ignored(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022,), countries=("Norway",), leaders=("Someone",))
    assert len(result.observations) == 7
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_xlsx": False}, MISSING_RAW),
        ({"local_files": None}, CIRIGHTS_LOCAL_FILES_INVALID),
        ({"local_files": []}, CIRIGHTS_LOCAL_FILES_INVALID),
        ({"local_files": ["other.xlsx"]}, CIRIGHTS_LOCAL_FILES_INVALID),
        ({"source_version": "v3.12.10.24"}, CIRIGHTS_METADATA_VERSION_MISMATCH),
        ({"checksum": "0" * 64}, CIRIGHTS_CHECKSUM_MISMATCH),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    if kwargs.get("local_files") is None and "local_files" in kwargs:
        kwargs["local_files"] = {"bad": CIRIGHTS_XLSX_NAME}
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_cirights_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_request_version_mismatch_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_cirights_adapter().check_ready(_request(tmp_path, source_version="other"))
    assert readiness.ready is False
    assert readiness.errors[0].code == CIRIGHTS_UNSUPPORTED_VERSION


def test_checksum_passes_with_extra_local_files_and_checksum_entries(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_cirights_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True


def test_out_of_coverage_year_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1980,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_adapter_import_does_not_import_legacy_ingest() -> None:
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith("leaders_db.sources."):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest."):
            del sys.modules[name]
    importlib.import_module("leaders_db.sources.adapters.cirights")
    leaked = sorted(
        name
        for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == []


def test_runner_does_not_dispatch_through_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {CIRIGHTS_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2022,), countries=("Norway",))
    assert len(result.observations) == 7


def test_missing_cells_are_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _stage_bundle(tmp_path)

    from leaders_db.ingest.cirights_io import IndicatorSpec

    specs = [
        IndicatorSpec(
            variable_name="cirights_physint",
            raw_column="Physical Integrity Rights Index",
            category="domestic_violence",
            raw_scale="0-8",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_sum",
            description="Physical Integrity Rights Index",
        ),
        IndicatorSpec(
            variable_name="cirights_tort",
            raw_column="Torture",
            category="domestic_violence",
            raw_scale="0-2",
            normalized_scale_target="0-10",
            higher_is_better=True,
            unit="cirights_ordinal",
            description="Torture",
        ),
    ]
    frame = pd.DataFrame(
        {
            "country": ["Testland"],
            "year": [2022],
            "cirights_physint": [5],
            "cirights_tort": [pd.NA],
        },
    )
    frame.attrs["_cirights_raw_lookup"] = {("Testland", 2022, "cirights_physint"): "5"}
    frame.attrs["year_window"] = (2022, 2022)

    def fake_read_raw(request: SourceIngestRequest) -> RawReadResult:
        return RawReadResult(source_id=request.source_id, payload={"frame": frame, "specs": specs})

    monkeypatch.setattr(
        create_cirights_adapter().__class__,
        "read_raw",
        lambda self, request: fake_read_raw(request),
    )
    result = _run(tmp_path, years=(2022,))
    assert [obs.indicator_code for obs in result.observations] == ["cirights_physint"]


def test_attribution_text_matches_doc() -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert CIRIGHTS_ATTRIBUTION_TEXT in doc
