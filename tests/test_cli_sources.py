"""CLI tests for clean source-registry inspection commands."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.sources import (
    CoverageHint,
    InMemorySourceRegistry,
    RawReadResult,
    ReadinessResult,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceWarning,
)

runner = CliRunner()


class _ExplodingStage2Dispatch:
    """Sentinel that fails any attempted legacy Stage 2 dispatch-table use."""

    def __contains__(self, key: object) -> bool:
        raise AssertionError(f"legacy Stage 2 dispatch consulted for {key!r}")

    def __getitem__(self, key: str) -> Any:
        raise AssertionError(f"legacy Stage 2 dispatch consulted for {key!r}")

    def get(self, key: str, default: Any = None) -> Any:
        raise AssertionError(f"legacy Stage 2 dispatch consulted for {key!r}")

    def keys(self) -> Any:
        raise AssertionError("legacy Stage 2 dispatch keys consulted")

    def items(self) -> Any:
        raise AssertionError("legacy Stage 2 dispatch items consulted")


class _ReadinessAdapter:
    def __init__(self, readiness: ReadinessResult) -> None:
        self.descriptor = SourceDescriptor(
            source_id=SourceId("fake_source"),
            display_name="Fake Source",
            source_type="dataset",
            supported_observation_families=("fixture",),
            default_version="fixture-v1",
            homepage_url=None,
            attribution_key="fake_source",
            coverage_hint=CoverageHint(start_year=2023, end_year=2023),
        )
        self.readiness = readiness
        self.requests: list[SourceIngestRequest] = []
        self.read_raw_called = False
        self.transform_called = False

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        self.requests.append(request)
        return self.readiness

    def read_raw(self, request: SourceIngestRequest) -> RawReadResult:
        self.read_raw_called = True
        return RawReadResult(source_id=request.source_id)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[Any]:
        self.transform_called = True
        return ()


def _patch_registry(monkeypatch: Any, adapter: _ReadinessAdapter) -> None:
    from leaders_db.cli import commands_sources

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    monkeypatch.setattr(commands_sources, "build_default_source_registry", lambda: registry)


def test_sources_list_uses_clean_registry_not_legacy_stage2_dispatch(monkeypatch) -> None:
    """``sources list`` must enumerate clean adapters even if Stage 2 is unusable."""
    from leaders_db import ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", _ExplodingStage2Dispatch())

    result = runner.invoke(app, ["sources", "list"])

    assert result.exit_code == 0, result.stdout
    assert "world_bank_wdi" in result.stdout
    assert "ctbto_treaty_status" in result.stdout


def test_sources_list_json_is_deterministic_and_contains_metadata() -> None:
    result = runner.invoke(app, ["sources", "list", "--output", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    source_ids = [item["source_id"] for item in payload]
    assert source_ids == sorted(source_ids)
    wdi = next(item for item in payload if item["source_id"] == "world_bank_wdi")
    assert wdi["source_type"] == "api"
    assert "economic_country_year" in wdi["supported_observation_families"]


def test_sources_describe_uses_clean_registry_not_legacy_stage2_dispatch(monkeypatch) -> None:
    """``sources describe`` must read descriptors from the clean source registry."""
    from leaders_db import ingest as legacy_ingest

    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", _ExplodingStage2Dispatch())

    result = runner.invoke(app, ["sources", "describe", "ctbto_treaty_status"])

    assert result.exit_code == 0, result.stdout
    assert "source_id: ctbto_treaty_status" in result.stdout
    assert "attribution_key: ctbto_treaty_status" in result.stdout


def test_sources_describe_unknown_source_fails_clearly() -> None:
    result = runner.invoke(app, ["sources", "describe", "not_a_source"])

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "not_a_source" in combined
    assert "sources list" in combined


def test_sources_check_ready_ready_source_exits_zero(monkeypatch, tmp_path) -> None:
    adapter = _ReadinessAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(
        app,
        [
            "sources",
            "check-ready",
            "fake_source",
            "--year",
            "2023",
            "--country",
            "ISR",
            "--leader",
            "leader-1",
            "--raw-root",
            str(tmp_path / "raw"),
            "--processed-root",
            str(tmp_path / "processed"),
            "--metadata-root",
            str(tmp_path / "metadata"),
            "--cache-policy",
            "offline_only",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "source_id: fake_source" in result.stdout
    assert "ready: True" in result.stdout
    assert adapter.requests[0].years == (2023,)
    assert adapter.requests[0].countries == ("ISR",)
    assert adapter.requests[0].leaders == ("leader-1",)
    assert adapter.requests[0].raw_root == tmp_path / "raw"
    assert adapter.requests[0].cache_policy == "offline_only"
    assert adapter.requests[0].dry_run is True
    assert adapter.read_raw_called is False
    assert adapter.transform_called is False


def test_sources_check_ready_not_ready_shows_errors_and_warnings(monkeypatch) -> None:
    adapter = _ReadinessAdapter(
        ReadinessResult(
            ready=False,
            warnings=(SourceWarning(code="MISSING_OPTIONAL", message="optional file absent"),),
            errors=(
                SourceWarning(
                    code="MISSING_RAW",
                    message="raw file absent",
                    severity="error",
                    source_id=SourceId("fake_source"),
                ),
            ),
        )
    )
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(app, ["sources", "check-ready", "fake_source"])

    assert result.exit_code == 1
    assert "ready: False" in result.stdout
    assert "MISSING_OPTIONAL" in result.stdout
    assert "optional file absent" in result.stdout
    assert "MISSING_RAW" in result.stdout
    assert "raw file absent" in result.stdout
    assert adapter.read_raw_called is False
    assert adapter.transform_called is False


def test_sources_check_ready_unknown_source_fails_clearly() -> None:
    result = runner.invoke(app, ["sources", "check-ready", "not_a_source"])

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "not_a_source" in combined
    assert "sources list" in combined


def test_sources_check_ready_uses_clean_registry_not_legacy_stage2_dispatch(
    monkeypatch,
) -> None:
    from leaders_db import ingest as legacy_ingest

    adapter = _ReadinessAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)
    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", _ExplodingStage2Dispatch())

    result = runner.invoke(app, ["sources", "check-ready", "fake_source"])

    assert result.exit_code == 0, result.stdout
    assert adapter.requests


def test_sources_check_ready_json_output(monkeypatch) -> None:
    adapter = _ReadinessAdapter(
        ReadinessResult(
            ready=False,
            warnings=(SourceWarning(code="OPTIONAL", message="optional warning"),),
            errors=(SourceWarning(code="BLOCKER", message="blocking error", severity="error"),),
        )
    )
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(
        app,
        ["sources", "check-ready", "fake_source", "--output", "json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "errors": [
            {
                "code": "BLOCKER",
                "context": {},
                "message": "blocking error",
                "severity": "error",
                "source_id": None,
            }
        ],
        "ready": False,
        "source_id": "fake_source",
        "warnings": [
            {
                "code": "OPTIONAL",
                "context": {},
                "message": "optional warning",
                "severity": "warning",
                "source_id": None,
            }
        ],
    }
