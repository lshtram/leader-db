"""Tests for trusted research usage and rate-card equivalents."""

import json
from pathlib import Path

import pytest

from leaders_db.research._codex_worker_artifacts import read_codex_usage
from leaders_db.research.costing import (
    combine_priced_usage,
    load_research_pricing,
    price_usage,
)

PRICING_PATH = Path(__file__).parents[2] / "configs" / "research-pricing.yaml"


def _events(tmp_path: Path, usage: dict[str, int]) -> Path:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"type":"turn.completed","usage":' + json.dumps(usage) + "}\n",
        encoding="utf-8",
    )
    return path


def test_reads_cached_and_reasoning_without_double_counting(tmp_path: Path) -> None:
    usage = read_codex_usage(
        _events(
            tmp_path,
            {
                "input_tokens": 1000,
                "cached_input_tokens": 800,
                "output_tokens": 100,
                "reasoning_output_tokens": 60,
            },
        )
    )

    assert usage is not None
    assert usage.uncached_input_tokens == 200
    assert usage.total_tokens == 1100
    assert usage.reasoning_output_tokens == 60


def test_rejects_impossible_provider_counters(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cached input"):
        read_codex_usage(
            _events(
                tmp_path,
                {
                    "input_tokens": 100,
                    "cached_input_tokens": 101,
                    "output_tokens": 10,
                },
            )
        )


def test_prices_exact_standard_tier_and_search(tmp_path: Path) -> None:
    pricing = load_research_pricing(PRICING_PATH)
    usage = read_codex_usage(
        _events(
            tmp_path,
            {
                "input_tokens": 10_000,
                "cached_input_tokens": 8_000,
                "output_tokens": 1_000,
            },
        )
    )
    assert usage is not None

    priced = price_usage(
        usage,
        provider="openai",
        model="gpt-5.6-luna",
        pricing=pricing,
        parallel_searches=1,
    )

    assert priced.cost_certainty == "range"
    assert priced.parallel_search_cost_usd == 0.005
    assert priced.payg_equivalent_cost_usd_lower == 0.0138
    assert priced.payg_equivalent_cost_usd_upper == 0.0143
    assert priced.actual_billed_cost_usd == "unknown_not_exposed_by_tool"


def test_reports_range_when_aggregate_crosses_long_threshold(tmp_path: Path) -> None:
    usage = read_codex_usage(
        _events(
            tmp_path,
            {
                "input_tokens": 300_000,
                "cached_input_tokens": 200_000,
                "output_tokens": 10_000,
                "reasoning_output_tokens": 5_000,
            },
        )
    )
    assert usage is not None

    priced = price_usage(
        usage,
        provider="openai",
        model="gpt-5.6-luna",
        pricing=load_research_pricing(PRICING_PATH),
    )

    assert priced.cost_certainty == "range"
    assert priced.payg_equivalent_cost_usd_lower == 0.18
    assert priced.payg_equivalent_cost_usd_upper == 0.38
    assert priced.codex_equivalent_credits_lower == 4.5


def test_unknown_model_does_not_invent_model_cost(tmp_path: Path) -> None:
    usage = read_codex_usage(
        _events(tmp_path, {"input_tokens": 100, "output_tokens": 10})
    )
    assert usage is not None

    priced = price_usage(
        usage,
        provider="openai",
        model="session_default",
        pricing=load_research_pricing(PRICING_PATH),
        parallel_searches=2,
    )

    assert priced.cost_certainty == "unknown"
    assert priced.payg_equivalent_cost_usd_lower == "unknown_not_exposed_by_tool"
    assert priced.parallel_search_cost_usd == 0.01


@pytest.mark.parametrize(
    ("provider", "model", "expected_lower", "expected_upper"),
    [
        ("openai", "gpt-5.6-terra", 0.0065, 0.007125),
        ("minimax", "MiniMax-M2.7", 0.00066, 0.000735),
        ("minimax", "MiniMax-M3", 0.00066, 0.000735),
    ],
)
def test_standard_model_rates_are_numeric(
    tmp_path: Path,
    provider: str,
    model: str,
    expected_lower: float,
    expected_upper: float,
) -> None:
    usage = read_codex_usage(
        _events(
            tmp_path,
            {
                "input_tokens": 2000,
                "cached_input_tokens": 1000,
                "output_tokens": 250,
            },
        )
    )
    assert usage is not None

    priced = price_usage(
        usage,
        provider=provider,
        model=model,
        pricing=load_research_pricing(PRICING_PATH),
    )

    assert priced.payg_equivalent_cost_usd_lower == expected_lower
    assert priced.payg_equivalent_cost_usd_upper == expected_upper


def test_rejects_negative_counters_and_search_counts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="negative"):
        read_codex_usage(
            _events(tmp_path, {"input_tokens": -1, "output_tokens": 0})
        )
    usage = read_codex_usage(
        _events(tmp_path, {"input_tokens": 1, "output_tokens": 0})
    )
    assert usage is not None
    with pytest.raises(ValueError, match="parallel_searches"):
        price_usage(
            usage,
            provider="openai",
            model="gpt-5.6-luna",
            pricing=load_research_pricing(PRICING_PATH),
            parallel_searches=-1,
        )


def test_combines_separately_priced_mixed_model_passes(tmp_path: Path) -> None:
    pricing = load_research_pricing(PRICING_PATH)
    research = read_codex_usage(
        _events(tmp_path, {"input_tokens": 2000, "output_tokens": 200})
    )
    formatter = read_codex_usage(
        _events(tmp_path, {"input_tokens": 1000, "output_tokens": 100})
    )
    assert research is not None and formatter is not None

    priced_research = price_usage(
        research,
        provider="minimax",
        model="MiniMax-M3",
        pricing=pricing,
        parallel_searches=8,
    )
    priced_formatter = price_usage(
        formatter,
        provider="openai",
        model="gpt-5.6-luna",
        pricing=pricing,
    )
    priced_research = priced_research.model_copy(
        update={"pricing_sha256": "a" * 64, "pricing_effective_date": "2026-07-13"}
    )
    priced_formatter = priced_formatter.model_copy(
        update={"pricing_sha256": "a" * 64, "pricing_effective_date": "2026-07-13"}
    )
    combined = combine_priced_usage((priced_research, priced_formatter))

    assert priced_research.payg_equivalent_cost_usd_lower == 0.04084
    assert priced_research.payg_equivalent_cost_usd_upper == 0.04099
    assert priced_research.parallel_search_cost_usd == 0.04
    assert priced_research.codex_equivalent_credits_lower == "unknown_not_exposed_by_tool"
    assert priced_formatter.payg_equivalent_cost_usd_lower == 0.0016
    assert priced_formatter.payg_equivalent_cost_usd_upper == 0.00185
    assert priced_formatter.parallel_search_cost_usd == 0.0
    assert priced_formatter.codex_equivalent_credits_lower == 0.04
    assert combined.total_tokens == 3300
    assert combined.parallel_search_cost_usd == 0.04
    assert combined.payg_equivalent_cost_usd_lower == 0.04244
    assert combined.payg_equivalent_cost_usd_upper == 0.04284
    assert combined.pricing_sha256 == "a" * 64
    assert combined.pricing_effective_date == "2026-07-13"
