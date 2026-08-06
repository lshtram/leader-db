"""Tests for the controlled Luna explicit-cache probe."""

import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path("scripts/experiments/run_luna_cache_probe.py")
    spec = importlib.util.spec_from_file_location("run_luna_cache_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cost_separates_fresh_cached_and_cache_write_tokens() -> None:
    module = _module()

    cost = module._cost(3_000_000, 1_000_000, 1_000_000, 100_000)

    assert cost == 2.95


def test_preflight_uses_conservative_one_character_per_token_bound() -> None:
    module = _module()

    cost = module._worst_case_cost(360_000, requests=2)

    assert cost < 1.0


def test_cache_key_shape_stays_within_api_limit() -> None:
    digest = "a" * 40
    cache_key = "leaders-db:cache-proof:" + digest

    assert len(cache_key) <= 64


def test_cost_ledger_accumulates_across_calls(tmp_path) -> None:
    module = _module()
    ledger = tmp_path / "ledger.jsonl"
    module._append_ledger(
        ledger,
        {"estimated_cost_usd": 0.1, "output_text": "not persisted"},
    )
    module._append_ledger(ledger, {"estimated_cost_usd": 0.2})

    assert module._ledger_total(ledger) == pytest.approx(0.3)
    assert "not persisted" not in ledger.read_text(encoding="utf-8")


def test_output_text_is_read_from_response_blocks() -> None:
    module = _module()
    response = {
        "output": [
            {"content": [{"type": "output_text", "text": "cache works"}]}
        ]
    }

    assert module._output_text(response) == "cache works"
