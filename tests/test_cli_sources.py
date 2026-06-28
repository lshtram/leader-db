"""CLI tests for clean source-registry inspection commands."""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from leaders_db.cli import app

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
