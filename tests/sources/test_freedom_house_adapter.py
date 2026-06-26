"""Freedom House FIW clean-source adapter tests."""

from __future__ import annotations

import hashlib
import json
import socket
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from leaders_db.sources import (
    InMemorySourceRegistry,
    SourceId,
    SourceIngestRequest,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.freedom_house import (
    FREEDOM_HOUSE_ATTRIBUTION_TEXT,
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_INDICATORS,
    FREEDOM_HOUSE_OBSERVATION_FAMILY,
    FREEDOM_HOUSE_RATINGS_XLSX_NAME,
    FREEDOM_HOUSE_SOURCE_KEY,
    create_freedom_house_adapter,
    register_freedom_house,
)
from leaders_db.sources.adapters.freedom_house._constants import (
    FREEDOM_HOUSE_CHECKSUM_MISMATCH,
    FREEDOM_HOUSE_LOCAL_FILES_INVALID,
    FREEDOM_HOUSE_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)


def _write_ratings_workbook(path: Path) -> None:
    header = [
        ["Survey Edition", "Jan.-Feb. 1973", None, None, 2026, None, None],
        ["Year(s) Under Review", 1972, None, None, 2025, None, None],
        [None, "PR", "CL", "Status", "PR", "CL", "Status"],
        ["Freedonia", 2, 3, "F", 4, 5, "PF"],
        ["Nowhere", "-", "-", "-", 7, 7, "NF"],
    ]
    territories = [
        ["Survey Edition", "Jan.-Feb. 1973", None, None, 2026, None, None],
        ["Year(s) Under Review", 1972, None, None, 2026, None, None],
        [None, "PR", "CL", "Status", "PR", "CL", "Status"],
        ["Territoria", "-", "-", "-", 5, 6, "PF"],
    ]
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(header).to_excel(
            writer,
            sheet_name="Country Ratings, Statuses ",
            header=False,
            index=False,
        )
        pd.DataFrame(territories).to_excel(
            writer,
            sheet_name="Territory Ratings, Statuses",
            header=False,
            index=False,
        )


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_xlsx: bool = True,
    local_files: Any | None = None,
    checksum: str | None = "AUTO",
    source_version: str = FREEDOM_HOUSE_DEFAULT_VERSION,
) -> Path:
    bundle = raw_root / FREEDOM_HOUSE_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    xlsx_path = bundle / FREEDOM_HOUSE_RATINGS_XLSX_NAME
    if with_xlsx:
        _write_ratings_workbook(xlsx_path)
    if with_metadata:
        if checksum == "AUTO" and xlsx_path.is_file():
            checksum_value = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
        else:
            checksum_value = checksum
        payload: dict[str, Any] = {
            "source_name": "Freedom House Freedom in the World (FIW)",
            "source_version": source_version,
            "download_date": "2026-06-25",
            "coverage": "country/territory-year political rights and civil liberties ratings",
            "years_available": "1973-2026 for country/territory ratings",
            "license_note": "User-managed FIW files; do not redistribute raw workbooks.",
            "local_files": [FREEDOM_HOUSE_RATINGS_XLSX_NAME]
            if local_files is None
            else local_files,
            "ingestion_status": "downloaded",
            "source_url": "https://freedomhouse.org/report/freedom-world",
        }
        if checksum_value is not None:
            payload["checksum_sha256"] = {FREEDOM_HOUSE_RATINGS_XLSX_NAME: checksum_value}
        (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(FREEDOM_HOUSE_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def _run(raw_root: Path, **kwargs: Any):
    registry = InMemorySourceRegistry()
    register_freedom_house(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


def test_descriptor_factory_and_registry() -> None:
    adapter = create_freedom_house_adapter()
    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == FREEDOM_HOUSE_SOURCE_KEY
    assert descriptor.attribution_key == FREEDOM_HOUSE_SOURCE_KEY
    assert descriptor.default_version == FREEDOM_HOUSE_DEFAULT_VERSION
    assert descriptor.source_type == "dataset"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is True
    assert descriptor.supported_observation_families == (FREEDOM_HOUSE_OBSERVATION_FAMILY,)

    registry = InMemorySourceRegistry()
    returned = register_freedom_house(registry)
    assert returned.descriptor == descriptor
    assert registry.get_adapter(SourceId(FREEDOM_HOUSE_SOURCE_KEY)).descriptor == descriptor


def test_runner_emits_core_fiw_observations(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2026,), countries=("Freedonia",))
    observations = result.observations
    assert [obs.indicator_code for obs in observations] == list(FREEDOM_HOUSE_INDICATORS)
    assert {obs.country_name for obs in observations} == {"Freedonia"}
    assert {obs.year for obs in observations} == {2026}
    assert {obs.observation_family for obs in observations} == {FREEDOM_HOUSE_OBSERVATION_FAMILY}

    pr = next(obs for obs in observations if obs.indicator_code == "freedom_house_political_rights")
    assert pr.value == 4
    assert pr.value_type == "numeric"
    assert pr.scale == "1-7"
    assert pr.extension["normalized_value"] == 0.5
    assert pr.extension["higher_is_better"] is False
    assert pr.country_code is None
    assert pr.raw_locator.path.endswith(FREEDOM_HOUSE_RATINGS_XLSX_NAME)
    assert pr.raw_locator.sheet == "Country Ratings, Statuses "
    assert pr.raw_locator.column_name == "2026:PR"
    assert pr.raw_locator.row_number == 4
    assert pr.extension["freedom_house_years_under_review"] == "2025"
    assert FREEDOM_HOUSE_ATTRIBUTION_TEXT == pr.extension["attribution"]

    status = next(obs for obs in observations if obs.indicator_code == "freedom_house_status")
    assert status.value == "PF"
    assert status.value_type == "categorical"
    assert status.extension["normalized_value"] is None


def test_years_none_reads_all_available_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Freedonia",))
    assert {obs.year for obs in result.observations} == {1973, 2026}
    assert len(result.observations) == 6


def test_multi_year_request_reads_all_requested_years(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1973, 2026), countries=("Freedonia",))
    assert {obs.year for obs in result.observations} == {1973, 2026}
    assert len(result.observations) == 6


def test_out_of_coverage_year_warns_and_emits_no_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(1972,))
    assert result.observations == ()
    assert [warning.code for warning in result.warnings] == [YEAR_ABSENT]


def test_leader_filter_warns_but_does_not_filter(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2026,), countries=("Freedonia",), leaders=("Someone",))
    assert len(result.observations) == 3
    assert [warning.code for warning in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_xlsx": False}, MISSING_RAW),
        ({"local_files": []}, FREEDOM_HOUSE_LOCAL_FILES_INVALID),
        (
            {
                "local_files": [
                    "Country_and_Territory_Ratings_and_Statuses_FIW_1973-2024.xlsx",
                ],
            },
            FREEDOM_HOUSE_LOCAL_FILES_INVALID,
        ),
        ({"checksum": "0" * 64}, FREEDOM_HOUSE_CHECKSUM_MISMATCH),
        ({"source_version": "2024"}, "freedom_house_metadata_version_mismatch"),
    ],
)
def test_readiness_failures(tmp_path: Path, kwargs: dict[str, Any], code: str) -> None:
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_freedom_house_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    readiness = create_freedom_house_adapter().check_ready(
        _request(tmp_path, source_version="2024"),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == FREEDOM_HOUSE_UNSUPPORTED_VERSION


def test_runner_does_not_dispatch_through_legacy_stage2_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_bundle(tmp_path)
    import leaders_db.ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", {FREEDOM_HOUSE_SOURCE_KEY: None})
    result = _run(tmp_path, years=(2026,), countries=("Freedonia",))
    assert len(result.observations) == 3


def test_adapter_does_not_use_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_bundle(tmp_path)

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is not allowed for Freedom House FIW")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "socket", fail_network)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", fail_network)
        monkeypatch.setattr(requests, "post", fail_network)

    result = _run(tmp_path, years=(2026,), countries=("Freedonia",))
    assert len(result.observations) == 3


def test_attribution_text_matches_doc() -> None:
    doc = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert FREEDOM_HOUSE_ATTRIBUTION_TEXT in doc


def test_production_staged_bundle_smoke_if_present() -> None:
    root = Path("data/raw")
    bundle = root / FREEDOM_HOUSE_SOURCE_KEY
    if not (bundle / "metadata.json").is_file() or not (
        bundle / FREEDOM_HOUSE_RATINGS_XLSX_NAME
    ).is_file():
        pytest.skip("Freedom House raw bundle is not staged locally")
    result = _run(root, years=(2026,), countries=("Afghanistan",))
    assert {obs.indicator_code for obs in result.observations} == set(FREEDOM_HOUSE_INDICATORS)
    assert {obs.country_name for obs in result.observations} == {"Afghanistan"}
