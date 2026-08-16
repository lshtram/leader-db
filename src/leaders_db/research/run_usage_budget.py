"""Atomic run-wide model usage reservations for integrated research runs."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

MODEL_MAX_OUTPUT_TOKENS = {
    "gpt-5.6-luna": 128_000,
    "gpt-5.6-terra": 128_000,
    "gpt-5.6-sol": 128_000,
}


@dataclass(frozen=True)
class RunUsageLimits:
    max_calls: int
    max_input_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        if min(self.max_calls, self.max_input_tokens, self.max_output_tokens) <= 0:
            raise ValueError("run usage limits must be positive")


@dataclass
class RunUsageBudgetTracker:
    """Atomically reserve and reconcile capacity across every model stage."""

    ledger_path: Path
    limits: RunUsageLimits
    config_sha256: str
    _lock: Lock = field(default_factory=Lock, repr=False)

    def safe_parallel_calls(self, model: str) -> int:
        """Return the maximum initially safe in-flight calls for one model."""

        return max(1, self.limits.max_output_tokens // model_max_output_tokens(model))

    def reserve(
        self,
        *,
        stage: str,
        component: str,
        estimated_input_tokens: int,
        output_token_allowance: int,
        output_dir: Path,
    ) -> str:
        """Reserve worst-case run capacity before a model subprocess starts."""

        if min(estimated_input_tokens, output_token_allowance) < 0:
            raise ValueError("run usage reservations cannot be negative")
        with self._lock, _locked_json_list(self.ledger_path) as (handle, ledger):
            _validate_run_ledger_identity(ledger, self.config_sha256, self.limits)
            totals = _reserved_or_observed_totals(ledger)
            reasons = []
            if totals["calls"] + 1 > self.limits.max_calls:
                reasons.append("run_call_count")
            if totals["input_tokens"] + estimated_input_tokens > self.limits.max_input_tokens:
                reasons.append("run_input_tokens")
            if totals["output_tokens"] + output_token_allowance > self.limits.max_output_tokens:
                reasons.append("run_output_tokens")
            reservation_id = f"run-call-{len(ledger) + 1:04d}"
            entry: dict[str, Any] = {
                "schema_version": "run_usage_reservation_v1",
                "reservation_id": reservation_id,
                "stage": stage,
                "component": component,
                "config_sha256": self.config_sha256,
                "run_limits": {
                    "max_calls": self.limits.max_calls,
                    "max_input_tokens": self.limits.max_input_tokens,
                    "max_output_tokens": self.limits.max_output_tokens,
                },
                "status": "stopped" if reasons else "reserved",
                "estimated_input_tokens": estimated_input_tokens,
                "output_token_allowance": output_token_allowance,
                "totals_before": totals,
                "stop_reasons": reasons,
            }
            if reasons:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "run-budget-stop.json").write_text(
                    json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                raise ValueError(
                    f"run usage budget stopped stage={stage} component={component}: "
                    + ", ".join(reasons)
                )
            ledger.append(entry)
            _write_locked_json(handle, ledger)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "run-budget-reservation.json").write_text(
                json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return reservation_id

    def reconcile(self, reservation_id: str, usage: dict[str, int] | None) -> None:
        """Replace a reservation with observed usage, retaining it when unavailable."""

        with self._lock, _locked_json_list(self.ledger_path) as (handle, ledger):
            _validate_run_ledger_identity(ledger, self.config_sha256, self.limits)
            entry = _unique_reservation(ledger, reservation_id)
            if entry["status"] != "reserved":
                raise ValueError("run usage reservation is not pending reconciliation")
            if usage is None:
                entry["status"] = "usage_unavailable"
            else:
                input_tokens = int(usage["input_tokens"])
                output_tokens = int(usage["output_tokens"])
                if min(input_tokens, output_tokens) < 0:
                    raise ValueError("observed run usage cannot be negative")
                entry.update(
                    {
                        "status": "completed",
                        "observed_input_tokens": input_tokens,
                        "observed_output_tokens": output_tokens,
                        "observed_cached_input_tokens": int(usage.get("cached_input_tokens", 0)),
                        "observed_reasoning_output_tokens": int(
                            usage.get("reasoning_output_tokens", 0)
                        ),
                    }
                )
                exceeded = _reconciliation_overages(ledger, entry, output_tokens, self.limits)
                if exceeded:
                    entry["status"] = "limit_exceeded"
                    entry["reconciliation_stop_reasons"] = exceeded
            _write_locked_json(handle, ledger)
            if entry["status"] == "limit_exceeded":
                raise ValueError(
                    "observed model usage exceeded its run reservation: "
                    + ", ".join(entry["reconciliation_stop_reasons"])
                )

    def cancel_unlaunched(self, reservation_id: str) -> None:
        """Release capacity only when the model subprocess never started."""

        with self._lock, _locked_json_list(self.ledger_path) as (handle, ledger):
            _validate_run_ledger_identity(ledger, self.config_sha256, self.limits)
            entry = _unique_reservation(ledger, reservation_id)
            if entry["status"] != "reserved":
                raise ValueError("only a pending run usage reservation can be cancelled")
            entry["status"] = "cancelled_unlaunched"
            _write_locked_json(handle, ledger)


def model_max_output_tokens(model: str) -> int:
    """Return the configured provider maximum used for hard reservations."""

    try:
        return MODEL_MAX_OUTPUT_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"model maximum output tokens are not configured: {model}") from exc


def resolve_integrated_run_budget(
    output_dir: Path, tracker: RunUsageBudgetTracker | None
) -> RunUsageBudgetTracker | None:
    """Resolve and validate the mandatory tracker for an integrated run."""

    manifest_path = next(
        (
            directory / "preflight-manifest.json"
            for directory in (output_dir, *output_dir.parents)
            if (directory / "preflight-manifest.json").is_file()
        ),
        None,
    )
    if manifest_path is None:
        return tracker
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "eligible":
        raise ValueError("integrated model execution requires an eligible preflight")
    limits = RunUsageLimits(
        max_calls=int(manifest["maximum_calls_per_ruler"]),
        max_input_tokens=int(manifest["maximum_input_tokens_per_ruler"]),
        max_output_tokens=int(manifest["maximum_output_tokens_per_ruler"]),
    )
    config_sha256 = str(manifest["config_sha256"])
    expected_ledger = manifest_path.parent / "stage-budgets" / "run-usage-reservations.json"
    if tracker is None:
        return RunUsageBudgetTracker(expected_ledger, limits, config_sha256)
    if (
        tracker.ledger_path != expected_ledger
        or tracker.limits != limits
        or tracker.config_sha256 != config_sha256
    ):
        raise ValueError("integrated run usage tracker differs from its preflight")
    return tracker


def _reconciliation_overages(
    ledger: list[dict[str, Any]],
    entry: dict[str, Any],
    output_tokens: int,
    limits: RunUsageLimits,
) -> list[str]:
    totals = _reserved_or_observed_totals(ledger)
    exceeded = [
        name
        for name, actual, limit in (
            ("run_call_count", totals["calls"], limits.max_calls),
            ("run_input_tokens", totals["input_tokens"], limits.max_input_tokens),
            ("run_output_tokens", totals["output_tokens"], limits.max_output_tokens),
        )
        if actual > limit
    ]
    if output_tokens > int(entry["output_token_allowance"]):
        exceeded.append("call_output_token_allowance")
    return exceeded


@contextmanager
def _locked_json_list(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read()
        ledger = json.loads(text) if text else []
        if not isinstance(ledger, list):
            raise ValueError("run usage budget ledger is malformed")
        yield handle, ledger
        fcntl.flock(handle, fcntl.LOCK_UN)


def _write_locked_json(handle, payload: list[dict[str, Any]]) -> None:
    handle.seek(0)
    handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _reserved_or_observed_totals(ledger: list[dict[str, Any]]) -> dict[str, int]:
    active = [
        item
        for item in ledger
        if item.get("status") in {"reserved", "usage_unavailable", "completed", "limit_exceeded"}
    ]
    return {
        "calls": len(active),
        "input_tokens": sum(
            int(item.get("observed_input_tokens", item["estimated_input_tokens"]))
            for item in active
        ),
        "output_tokens": sum(
            int(item.get("observed_output_tokens", item["output_token_allowance"]))
            for item in active
        ),
    }


def _unique_reservation(ledger: list[dict[str, Any]], reservation_id: str) -> dict[str, Any]:
    matches = [item for item in ledger if item.get("reservation_id") == reservation_id]
    if len(matches) != 1:
        raise ValueError("run usage reservation identity is missing or ambiguous")
    return matches[0]


def _validate_run_ledger_identity(
    ledger: list[dict[str, Any]], config_sha256: str, limits: RunUsageLimits
) -> None:
    expected_limits = {
        "max_calls": limits.max_calls,
        "max_input_tokens": limits.max_input_tokens,
        "max_output_tokens": limits.max_output_tokens,
    }
    if any(
        item.get("config_sha256") != config_sha256
        or item.get("run_limits") != expected_limits
        for item in ledger
    ):
        raise ValueError("run usage ledger identity differs from the active release")


__all__ = [
    "RunUsageBudgetTracker",
    "RunUsageLimits",
    "model_max_output_tokens",
    "resolve_integrated_run_budget",
]
