"""Integrated-run accounting helpers for canonical cost profiles."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from ._codex_worker_artifacts import price_codex_usage
from .cost_profile_events import totals
from .costing import combine_priced_usage
from .dossier_models import DossierUsage


def execution_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize measured execution characteristics across all launched calls."""

    completed = [row for row in rows if row["call_status"] == "completed"]
    failed = [row for row in rows if row["call_status"] == "failed"]
    recorded = [row for row in rows if row["elapsed_seconds"] is not None]
    return {
        "completed_calls": len(completed),
        "failed_calls": len(failed),
        "timed_calls": len(recorded),
        "timed_failed_calls": sum(row["call_status"] == "failed" for row in recorded),
        "timing_unavailable_calls": len(rows) - len(recorded),
        "elapsed_seconds": round(sum(float(row["elapsed_seconds"]) for row in recorded), 6),
        "estimated_input_tokens": sum(int(row["estimated_input_tokens"] or 0) for row in rows),
        "request_characters": sum(
            int(row["request_characters"] or row["prompt_characters"] or 0) for row in rows
        ),
        "response_schema_characters": sum(
            int(row["response_schema_characters"] or 0) for row in rows
        ),
        "validation_gate_counts": dict(
            sorted(Counter(str(row["validation_gate"] or "unavailable") for row in rows).items())
        ),
        "models": dict(sorted(Counter(str(row["model"] or "unavailable") for row in rows).items())),
        "reasoning_efforts": dict(
            sorted(Counter(str(row["reasoning_effort"] or "unavailable") for row in rows).items())
        ),
    }


def run_budget_reconciliation(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile trusted event counters against the durable run ledger."""

    path = root / "stage-budgets" / "run-usage-reservations.json"
    if not path.is_file():
        return {"status": "unavailable", "ledger_path": None}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("run-wide usage ledger must contain reservation objects")
    token_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    accounted = [
        item
        for item in payload
        if all(isinstance(item.get(f"observed_{key}"), int) for key in token_fields)
    ]
    ledger_totals = {
        key: sum(int(item[f"observed_{key}"]) for item in accounted) for key in token_fields
    }
    event_totals = totals(rows)
    differences = {key: int(event_totals[key]) - ledger_totals[key] for key in ledger_totals}
    unresolved = [
        item for item in payload if item.get("status") in {"reserved", "usage_unavailable"}
    ]
    reconciliation_status = (
        "incomplete"
        if unresolved
        else "pass"
        if all(value == 0 for value in differences.values())
        else "fail"
    )
    return {
        "status": reconciliation_status,
        "budget_status": (
            "fail" if any(item.get("status") == "limit_exceeded" for item in payload) else "pass"
        ),
        "ledger_path": str(path.relative_to(root)),
        "reservation_count": len(payload),
        "accounted_reservation_count": len(accounted),
        "unresolved_reservation_count": len(unresolved),
        "status_counts": dict(
            sorted(Counter(str(item.get("status", "unknown")) for item in payload).items())
        ),
        "ledger_observed_totals": ledger_totals,
        "event_totals": {key: event_totals[key] for key in ledger_totals},
        "differences": differences,
    }


def integrated_preflight(root: Path) -> dict[str, Any] | None:
    """Return the immutable integrated-run preflight summary, when present."""

    path = root / "preflight-manifest.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return {
        "path": str(path.relative_to(root)),
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "status": payload.get("status"),
        "release_id": payload.get("release_id"),
        "planned_calls": payload.get("planned_calls"),
        "maximum_calls_per_ruler": payload.get("maximum_calls_per_ruler"),
        "maximum_input_tokens_per_ruler": payload.get("maximum_input_tokens_per_ruler"),
        "maximum_output_tokens_per_ruler": payload.get("maximum_output_tokens_per_ruler"),
        "call_inventory": payload.get("call_inventory"),
        "reasoning_effort": payload.get("reasoning_effort"),
    }


def cost_equivalents(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Price completed calls by model without claiming subscription billing."""

    completed = [row for row in rows if row["call_status"] == "completed"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in completed:
        grouped.setdefault(str(row["model"] or "unavailable"), []).append(row)
    priced = []
    by_model = {}
    for model, model_rows in sorted(grouped.items()):
        if model == "unavailable":
            by_model[model] = {
                "status": "pricing_unavailable",
                "calls": len(model_rows),
            }
            continue
        call_usage = tuple(
            price_codex_usage(_row_usage(row), provider="openai", model=model) for row in model_rows
        )
        item = combine_priced_usage(call_usage)
        priced.append(item)
        by_model[model] = {"calls": len(model_rows), **item.model_dump(mode="json")}
    combined = combine_priced_usage(tuple(priced)) if priced else None
    return {
        "subscription_billing": "unknown_not_exposed_by_tool",
        "by_model": by_model,
        "combined": combined.model_dump(mode="json") if combined is not None else None,
    }


def _row_usage(row: dict[str, Any]) -> DossierUsage:
    input_tokens = int(row["input_tokens"])
    output_tokens = int(row["output_tokens"])
    return DossierUsage(
        input_tokens=input_tokens,
        cached_input_tokens=int(row["cached_input_tokens"]),
        uncached_input_tokens=int(row["uncached_input_tokens"]),
        output_tokens=output_tokens,
        reasoning_output_tokens=int(row["reasoning_output_tokens"]),
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd="unknown_not_exposed_by_tool",
    )
