"""Build exact phase-level token and cost profiles for the reader experiment."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


def main() -> None:
    """Aggregate provider-reported usage without double-counting reasoning tokens."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    pricing = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "configs/research-pricing.yaml").read_text(
            encoding="utf-8"
        )
    )
    rates = {item["model"]: item["usd"] for item in pricing["models"].values()}
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "cost_usd": 0.0,
        }
    )
    for path in sorted(experiment_dir.rglob("*.events.jsonl")):
        usage = read_usage(path)
        phase, model = classify_event_path(path, experiment_dir)
        cost = price_usage(usage, rates.get(model))
        row = {
            "path": str(path.relative_to(experiment_dir)),
            "phase": phase,
            "model": model,
            **usage,
            "payg_equivalent_cost_usd": cost,
        }
        rows.append(row)
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            totals[phase][field] += usage[field]
        if cost is not None:
            totals[phase]["cost_usd"] += cost
    source_tokens = unique_source_tokens(experiment_dir)
    payload = {
        "schema_version": "document_reader_token_profile_v1",
        "unique_extracted_source_tokens": source_tokens,
        "phase_totals": {
            phase: {
                key: round(value, 6) if key == "cost_usd" else int(value)
                for key, value in values.items()
            }
            for phase, values in sorted(totals.items())
        },
        "turns": rows,
        "notes": [
            "Cached input is a subset of input and is not added to total input.",
            "Reasoning output is a subset of output and is not added to total output.",
            "Unknown model prices remain null rather than inferred.",
            "Retries remain workflow usage; unique extracted source tokens count once.",
        ],
    }
    (experiment_dir / "token-profile.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_usage(path: Path) -> dict[str, int]:
    """Sum every completed-turn counter in one persisted event stream."""

    result = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage", {})
        for field in result:
            value = usage.get(field, 0)
            if isinstance(value, int):
                result[field] += value
    return result


def classify_event_path(path: Path, root: Path) -> tuple[str, str]:
    """Infer the frozen execution role and model from its attempt-scoped path."""

    relative = str(path.relative_to(root))
    routes = (
        ("reading-briefs", "reading_brief", "gpt-5.4-mini"),
        ("/evaluation/", "blind_evaluation", "gpt-5.6-sol"),
        ("/compiled/", "dossier_compilation", "gpt-5.6-sol"),
        ("normalizer-events", "normalization", "gpt-5.4-mini"),
        ("audit-events", "content_audit", "gpt-5.6-sol"),
        ("arm-a-sol", "baseline_reading", "gpt-5.6-sol"),
        ("arm-b-minimax", "candidate_reading", "MiniMax-M2.7"),
        ("arm-b-luna-fallback", "fallback_reading", "gpt-5.6-luna"),
    )
    wrapped = f"/{relative}"
    for marker, phase, model in routes:
        if marker in wrapped:
            return phase, model
    return "unclassified", "unknown"


def price_usage(usage: dict[str, int], rates: dict[str, float] | None) -> float | None:
    """Compute a standard-rate equivalent when the exact model is registered."""

    if rates is None:
        return None
    cached = usage["cached_input_tokens"]
    uncached = usage["input_tokens"] - cached
    return round(
        (
            uncached * rates["uncached_input"]
            + cached * rates["cached_input"]
            + usage["output_tokens"] * rates["output"]
        )
        / 1_000_000,
        6,
    )


def unique_source_tokens(experiment_dir: Path) -> int:
    """Count each frozen extracted source once."""

    total = 0
    for path in (experiment_dir / "frozen/extracted").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        total += int(payload["estimated_source_tokens"])
    return total


if __name__ == "__main__":
    main()
