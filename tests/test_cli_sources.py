"""CLI tests for clean source-registry inspection commands."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import pytest
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.sources import (
    CoverageHint,
    EvidenceQuery,
    InMemorySourceRegistry,
    NormalizedObservation,
    RawLocator,
    RawReadResult,
    ReadinessResult,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceWarning,
    TransformLocator,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _refresh_cli_and_source_contracts_after_import_boundary_tests() -> None:
    """Keep CLI tests isolated from source-boundary sys.modules purges.

    Several source import-boundary tests intentionally delete and re-import
    ``leaders_db`` / ``leaders_db.sources`` modules. When pytest collects this
    file before those tests run, the module-level ``app`` and source contract
    classes below can otherwise point at stale module objects while later
    monkeypatches target the re-imported modules. Refreshing these globals before
    each test preserves the same runtime CLI path while making test order
    irrelevant.
    """

    from leaders_db import cli as current_cli
    from leaders_db import sources as current_sources
    from leaders_db.cli import commands_sources as current_commands_sources

    current_contracts = {
        "CoverageHint": current_sources.CoverageHint,
        "EvidenceQuery": current_sources.EvidenceQuery,
        "InMemorySourceRegistry": current_sources.InMemorySourceRegistry,
        "NormalizedObservation": current_sources.NormalizedObservation,
        "RawLocator": current_sources.RawLocator,
        "RawReadResult": current_sources.RawReadResult,
        "ReadinessResult": current_sources.ReadinessResult,
        "SourceDescriptor": current_sources.SourceDescriptor,
        "SourceId": current_sources.SourceId,
        "SourceIngestRequest": current_sources.SourceIngestRequest,
        "SourceWarning": current_sources.SourceWarning,
        "TransformLocator": current_sources.TransformLocator,
    }
    globals().update({"app": current_cli.app, **current_contracts})
    current_commands_sources.__dict__.update(current_contracts)

    for group_info in current_cli.app.registered_groups:
        if group_info.name != "sources":
            continue
        for command_info in group_info.typer_instance.registered_commands:
            if command_info.callback is not None:
                command_info.callback.__globals__.update(current_contracts)


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


class _IngestAdapter(_ReadinessAdapter):
    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        self.transform_called = True
        return (
            NormalizedObservation(
                source_id=request.source_id,
                observation_id="fake-obs-1",
                observation_family="fixture",
                indicator_code="fixture_indicator",
                value=7,
                value_type="numeric",
                year=2023,
                country_code="ISR",
                country_name="Israel",
                leader_id="leader-1",
                leader_name=None,
                unit=None,
                scale=None,
                source_version="fixture-v1",
                raw_locator=RawLocator(asset_id="fake-raw"),
                transform_locator=TransformLocator(adapter_version="fixture-adapter-v1"),
            ),
        )


class _QueryRepository:
    def __init__(self, observations: tuple[NormalizedObservation, ...]) -> None:
        self.observations = observations
        self.queries: list[EvidenceQuery] = []

    def query_observations(self, query: EvidenceQuery) -> tuple[NormalizedObservation, ...]:
        self.queries.append(query)
        return self.observations

    def get_manifest(self, source_id: SourceId, run_id: str | None = None) -> object:
        raise AssertionError("CLI query should not request manifests")

    def get_attributions(self, source_ids: tuple[SourceId, ...]) -> tuple[object, ...]:
        raise AssertionError("CLI query should not request attributions")


def _query_observation(
    *,
    source_slug: str = "fake_source",
    observation_id: str = "obs-1",
    family: str = "fixture",
    indicator: str = "fixture_indicator",
    year: int | None = 2023,
    country_code: str | None = "ISR",
    country_name: str | None = "Israel",
    leader_id: str | None = "leader-1",
    leader_name: str | None = "Leader One",
    value: object = 7,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(source_slug),
        observation_id=observation_id,
        observation_family=family,
        indicator_code=indicator,
        value=value,
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=leader_id,
        leader_name=leader_name,
        unit=None,
        scale=None,
        source_version="fixture-v1",
        raw_locator=RawLocator(asset_id="fake-raw"),
        transform_locator=TransformLocator(adapter_version="fixture-adapter-v1"),
    )


def _patch_registry(monkeypatch: Any, adapter: _ReadinessAdapter) -> None:
    from leaders_db.cli import commands_sources

    registry = InMemorySourceRegistry()
    registry.register(adapter)
    monkeypatch.setattr(commands_sources, "build_default_source_registry", lambda: registry)


def _patch_query_repository(monkeypatch: Any, repository: _QueryRepository) -> None:
    from leaders_db.cli import commands_sources

    monkeypatch.setattr(commands_sources, "_build_evidence_repository", lambda db_url: repository)


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


def test_sources_ingest_success_uses_clean_runner_path(monkeypatch, tmp_path) -> None:
    adapter = _IngestAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(
        app,
        [
            "sources",
            "ingest",
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
            "--overwrite",
            "--dry-run",
            "--output-format",
            "csv",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "source_id: fake_source" in result.stdout
    assert "ready: True" in result.stdout
    assert "validation_valid: True" in result.stdout
    assert "observation_count: 1" in result.stdout
    assert adapter.read_raw_called is True
    assert adapter.transform_called is True
    request = adapter.requests[0]
    assert request.years == (2023,)
    assert request.countries == ("ISR",)
    assert request.leaders == ("leader-1",)
    assert request.raw_root == tmp_path / "raw"
    assert request.processed_root == tmp_path / "processed"
    assert request.metadata_root == tmp_path / "metadata"
    assert request.cache_policy == "offline_only"
    assert request.overwrite is True
    assert request.dry_run is True
    assert request.output_formats == ("csv",)


def test_sources_ingest_not_ready_fails_before_reading_raw(
    monkeypatch,
    database_url: str,
) -> None:
    from leaders_db.db.engine import init_database

    init_database(database_url)
    adapter = _ReadinessAdapter(
        ReadinessResult(
            ready=False,
            errors=(SourceWarning(code="MISSING_RAW", message="raw file absent"),),
        )
    )
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(app, ["sources", "ingest", "fake_source", "--output-format", "csv"])

    assert result.exit_code == 1
    assert "ready: False" in result.stdout
    assert "INGEST_FAILED" in result.stdout
    assert "not ready" in result.stdout
    assert adapter.read_raw_called is False
    assert adapter.transform_called is False


def test_sources_ingest_unknown_source_fails_clearly() -> None:
    result = runner.invoke(app, ["sources", "ingest", "not_a_source"])

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "not_a_source" in combined
    assert "sources list" in combined


def test_sources_ingest_uses_clean_registry_not_legacy_stage2_dispatch(
    monkeypatch,
    database_url: str,
) -> None:
    from leaders_db import ingest as legacy_ingest
    from leaders_db.db.engine import init_database

    init_database(database_url)
    adapter = _IngestAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)
    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", _ExplodingStage2Dispatch())

    result = runner.invoke(
        app,
        ["sources", "ingest", "fake_source", "--output-format", "csv"],
    )

    assert result.exit_code == 0, result.stdout
    assert adapter.requests


def test_sources_ingest_persists_to_default_db_idempotently(
    monkeypatch,
    database_url: str,
) -> None:
    from sqlalchemy import text

    from leaders_db.db.engine import build_engine, init_database

    init_database(database_url)
    adapter = _IngestAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)

    first = runner.invoke(app, ["sources", "ingest", "fake_source", "--output-format", "csv"])
    second = runner.invoke(app, ["sources", "ingest", "fake_source", "--output-format", "csv"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    assert "manifest_run_id: fake_source-" in first.stdout
    engine = build_engine(database_url)
    with engine.connect() as conn:
        row_count = conn.execute(text("SELECT COUNT(*) FROM normalized_observations")).scalar_one()
        raw_locator = conn.execute(
            text("SELECT raw_locator_json FROM normalized_observations")
        ).scalar_one()
    assert row_count == 1
    assert "fake-raw" in raw_locator


def test_sources_ingest_json_output(monkeypatch) -> None:
    adapter = _IngestAdapter(
        ReadinessResult(
            ready=True,
            warnings=(SourceWarning(code="OPTIONAL", message="optional warning"),),
        )
    )
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(
        app,
        ["sources", "ingest", "fake_source", "--dry-run", "--output", "json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["source_id"] == "fake_source"
    assert payload["ready"] is True
    assert payload["validation_valid"] is True
    assert payload["observation_count"] == 1
    assert payload["manifest_run_id"] is None
    assert payload["warnings"][0]["code"] == "OPTIONAL"


def test_sources_ingest_missing_default_db_fails_with_readiness_message(
    monkeypatch,
    isolated_data_lake,
) -> None:
    adapter = _IngestAdapter(ReadinessResult(ready=True))
    _patch_registry(monkeypatch, adapter)

    result = runner.invoke(app, ["sources", "ingest", "fake_source", "--output-format", "csv"])

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout
    assert "leaders-db init-db" in result.stdout
    assert adapter.read_raw_called is False


def test_sources_query_returns_filtered_observations_from_clean_repository(monkeypatch) -> None:
    repository = _QueryRepository(
        (
            _query_observation(observation_id="obs-1", value=7),
            _query_observation(
                source_slug="other_source",
                observation_id="obs-2",
                indicator="other_indicator",
                value=3,
            ),
        )
    )
    _patch_query_repository(monkeypatch, repository)

    result = runner.invoke(app, ["sources", "query"])

    assert result.exit_code == 0, result.stdout
    assert (
        "source_id\tobservation_id\tfamily\tindicator\tyear\tcountry\tleader\tvalue"
        in result.stdout
    )
    assert (
        "fake_source\tobs-1\tfixture\tfixture_indicator\t2023\tISR\tleader-1\t7"
        in result.stdout
    )
    assert (
        "other_source\tobs-2\tfixture\tother_indicator\t2023\tISR\tleader-1\t3"
        in result.stdout
    )
    assert repository.queries == [EvidenceQuery()]


def test_sources_query_missing_default_db_fails_with_readiness_message(
    isolated_data_lake,
) -> None:
    result = runner.invoke(app, ["sources", "query"])

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout
    assert "leaders-db init-db" in result.stdout
    assert "no such table" not in result.stdout.lower()


def test_sources_query_maps_filters_to_evidence_query(monkeypatch) -> None:
    repository = _QueryRepository(())
    _patch_query_repository(monkeypatch, repository)

    result = runner.invoke(
        app,
        [
            "sources",
            "query",
            "--source",
            "fake_source",
            "--source",
            "other_source",
            "--family",
            "fixture",
            "--indicator",
            "fixture_indicator",
            "--year",
            "2023",
            "--country",
            "ISR",
            "--leader",
            "leader-1",
            "--db-url",
            "sqlite:///fixture.sqlite",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert repository.queries == [
        EvidenceQuery(
            source_ids=(SourceId("fake_source"), SourceId("other_source")),
            observation_families=("fixture",),
            indicator_codes=("fixture_indicator",),
            years=(2023,),
            countries=("ISR",),
            leaders=("leader-1",),
        )
    ]


def test_sources_query_json_output_is_deterministic_and_parseable(monkeypatch) -> None:
    repository = _QueryRepository(
        (
            _query_observation(observation_id="obs-1", value={"score": 7}),
            _query_observation(observation_id="obs-2", value=3),
        )
    )
    _patch_query_repository(monkeypatch, repository)

    result = runner.invoke(app, ["sources", "query", "--output", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert [item["observation_id"] for item in payload] == ["obs-1", "obs-2"]
    assert payload[0] == {
        "country_code": "ISR",
        "country_name": "Israel",
        "indicator_code": "fixture_indicator",
        "leader_id": "leader-1",
        "leader_name": "Leader One",
        "observation_family": "fixture",
        "observation_id": "obs-1",
        "quality_flags": [],
        "scale": None,
        "source_id": "fake_source",
        "source_version": "fixture-v1",
        "unit": None,
        "value": {"score": 7},
        "value_type": "numeric",
        "warnings": [],
        "year": 2023,
    }


def test_sources_query_empty_results_exit_zero_with_clear_output(monkeypatch) -> None:
    repository = _QueryRepository(())
    _patch_query_repository(monkeypatch, repository)

    table_result = runner.invoke(app, ["sources", "query"])
    json_result = runner.invoke(app, ["sources", "query", "--output", "json"])

    assert table_result.exit_code == 0, table_result.stdout
    assert table_result.stdout.strip() == "no observations matched"
    assert json_result.exit_code == 0, json_result.stdout
    assert json.loads(json_result.stdout) == []


def test_sources_coverage_reports_db_group_counts_and_statuses(
    monkeypatch,
    database_url: str,
) -> None:
    from leaders_db.cli import commands_sources
    from leaders_db.db.engine import build_engine, init_database
    from leaders_db.research.sql_repository import write_observations

    init_database(database_url)
    engine = build_engine(database_url)
    write_observations(
        engine,
        (
            _query_observation(observation_id="obs-1", year=2020, country_code="ISR"),
            _query_observation(observation_id="obs-2", year=2023, country_code="USA"),
            _query_observation(
                source_slug="other_source",
                observation_id="obs-3",
                family="other_family",
                indicator="other_indicator",
                year=None,
                country_code=None,
                country_name="Atlantis",
            ),
        ),
    )
    adapter = _IngestAdapter(ReadinessResult(ready=True))
    manual_adapter = _ReadinessAdapter(ReadinessResult(ready=False))
    manual_adapter.descriptor = SourceDescriptor(
        source_id=SourceId("manual_source"),
        display_name="Manual Source",
        source_type="manual",
        supported_observation_families=("manual",),
        default_version=None,
        homepage_url=None,
        attribution_key="manual_source",
        coverage_hint=adapter.descriptor.coverage_hint,
        requires_manual_approval=True,
    )
    registry = InMemorySourceRegistry()
    registry.register(adapter)
    registry.register(manual_adapter)
    monkeypatch.setattr(commands_sources, "build_default_source_registry", lambda: registry)

    result = runner.invoke(app, ["sources", "coverage", "--output", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["rows"] == [
        {
            "country_count": 2,
            "indicator_code": "fixture_indicator",
            "max_year": 2023,
            "min_year": 2020,
            "missing_raw_locator_count": 0,
            "observation_family": "fixture",
            "row_count": 2,
            "source_slug": "fake_source",
        },
        {
            "country_count": 1,
            "indicator_code": "other_indicator",
            "max_year": None,
            "min_year": None,
            "missing_raw_locator_count": 0,
            "observation_family": "other_family",
            "row_count": 1,
            "source_slug": "other_source",
        },
    ]
    statuses = {item["source_slug"]: item for item in payload["source_statuses"]}
    assert statuses["fake_source"]["status"] == "loaded"
    assert statuses["other_source"]["status"] == "loaded"
    assert statuses["manual_source"]["status"] == "blocked_user_managed"


def test_sources_coverage_table_output_is_deterministic(database_url: str) -> None:
    from leaders_db.db.engine import build_engine, init_database
    from leaders_db.research.sql_repository import write_observations

    init_database(database_url)
    write_observations(build_engine(database_url), (_query_observation(),))

    result = runner.invoke(app, ["sources", "coverage", "--db-only"])

    assert result.exit_code == 0, result.stdout
    assert (
        "source_id\tfamily\tindicator\trow_count\tmin_year\tmax_year\t"
        "country_count\tmissing_raw_locator_count"
    ) in result.stdout
    assert "fake_source\tfixture\tfixture_indicator\t1\t2023\t2023\t1\t0" in result.stdout
    assert "source_statuses:\n  - fake_source\tloaded\trow_count=1" in result.stdout


def test_sources_coverage_missing_default_db_fails_with_readiness_message(
    isolated_data_lake,
) -> None:
    result = runner.invoke(app, ["sources", "coverage"])

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout
    assert "leaders-db init-db" in result.stdout
    assert "no such table" not in result.stdout.lower()


def test_sources_query_uses_clean_repository_not_legacy_stage2_dispatch(monkeypatch) -> None:
    from leaders_db import ingest as legacy_ingest

    repository = _QueryRepository((_query_observation(),))
    _patch_query_repository(monkeypatch, repository)
    monkeypatch.setattr(legacy_ingest, "STAGE2_ADAPTERS", _ExplodingStage2Dispatch())

    result = runner.invoke(app, ["sources", "query", "--source", "fake_source"])

    assert result.exit_code == 0, result.stdout
    assert repository.queries[0].source_ids == (SourceId("fake_source"),)
