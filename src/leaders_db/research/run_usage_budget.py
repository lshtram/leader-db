"""Atomic run-wide model usage reservations for integrated research runs."""

from __future__ import annotations

import fcntl
import json
import math
import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
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
    capacity_wait_timeout_seconds: float = 1_800.0
    capacity_poll_seconds: float = 0.1
    allowed_request_sha256s: frozenset[str] = frozenset()
    _lock: Lock = field(default_factory=Lock, repr=False)

    @property
    def quota_amendment_path(self) -> Path:
        """Return the append-only authorization beside this run ledger."""

        return self.ledger_path.with_name(f"{self.ledger_path.stem}.quota-amendment.json")

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.capacity_wait_timeout_seconds)
            or self.capacity_wait_timeout_seconds < 0
        ):
            raise ValueError("capacity wait timeout must be finite and nonnegative")
        if not math.isfinite(self.capacity_poll_seconds) or self.capacity_poll_seconds <= 0:
            raise ValueError("capacity poll interval must be finite and positive")

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
        wait_for_capacity: bool = False,
        capacity_check: Callable[[], None] | None = None,
        request_sha256: str | None = None,
    ) -> str:
        """Reserve capacity, optionally waiting for active calls to reconcile."""

        if min(estimated_input_tokens, output_token_allowance) < 0:
            raise ValueError("run usage reservations cannot be negative")
        if self.allowed_request_sha256s and request_sha256 not in self.allowed_request_sha256s:
            raise ValueError("model request is absent from the authorized frozen inventory")
        started = time.monotonic()
        while True:
            if capacity_check is not None:
                capacity_check()
            with self._lock, _locked_json_list(self.ledger_path) as (handle, ledger):
                _validate_run_ledger_identity(
                    ledger, self.config_sha256, self.limits, self.ledger_path
                )
                _validate_continuation_request(
                    self.quota_amendment_path, request_sha256=request_sha256
                )
                if self.allowed_request_sha256s and any(
                    item.get("request_sha256") == request_sha256
                    and item.get("status") in {"reserved", "completed"}
                    for item in ledger
                ):
                    raise ValueError("authorized model request has already been reserved")
                totals = _reserved_or_observed_totals(ledger)
                reasons = _reservation_stop_reasons(
                    totals,
                    estimated_input_tokens=estimated_input_tokens,
                    output_token_allowance=output_token_allowance,
                    limits=self.limits,
                )
                pending = any(item.get("status") == "reserved" for item in ledger)
                best_case_totals = _settled_totals(ledger)
                could_fit_after_pending = not _reservation_stop_reasons(
                    best_case_totals,
                    estimated_input_tokens=estimated_input_tokens,
                    output_token_allowance=output_token_allowance,
                    limits=self.limits,
                )
                timed_out = time.monotonic() - started >= self.capacity_wait_timeout_seconds
                if not reasons:
                    entry = self._reservation_entry(
                        ledger=ledger,
                        stage=stage,
                        component=component,
                        estimated_input_tokens=estimated_input_tokens,
                        output_token_allowance=output_token_allowance,
                        totals=totals,
                        waited_seconds=time.monotonic() - started,
                        request_sha256=request_sha256,
                    )
                    ledger.append(entry)
                    _write_locked_json(handle, ledger)
                    break
                if not (
                    wait_for_capacity and pending and could_fit_after_pending and not timed_out
                ):
                    if timed_out and wait_for_capacity and pending:
                        reasons.append("capacity_wait_timeout")
                    entry = self._reservation_entry(
                        ledger=ledger,
                        stage=stage,
                        component=component,
                        estimated_input_tokens=estimated_input_tokens,
                        output_token_allowance=output_token_allowance,
                        totals=totals,
                        waited_seconds=time.monotonic() - started,
                        reasons=reasons,
                    )
                    _write_stop(output_dir, entry)
                    raise ValueError(
                        f"run usage budget stopped stage={stage} component={component}: "
                        + ", ".join(reasons)
                    )
            time.sleep(self.capacity_poll_seconds)
        reservation_id = str(entry["reservation_id"])
        try:
            return _write_reservation(output_dir, entry)
        except Exception:
            self.cancel_unlaunched(reservation_id)
            raise

    def _reservation_entry(
        self,
        *,
        ledger: list[dict[str, Any]],
        stage: str,
        component: str,
        estimated_input_tokens: int,
        output_token_allowance: int,
        totals: dict[str, int],
        waited_seconds: float,
        reasons: list[str] | None = None,
        request_sha256: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "run_usage_reservation_v1",
            "reservation_id": f"run-call-{len(ledger) + 1:04d}",
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
            "capacity_wait_seconds": round(waited_seconds, 6),
            "stop_reasons": reasons or [],
            "request_sha256": request_sha256,
        }

    def reconcile(self, reservation_id: str, usage: dict[str, int] | None) -> None:
        """Replace a reservation with observed usage, retaining it when unavailable."""

        with self._lock, _locked_json_list(self.ledger_path) as (handle, ledger):
            _validate_run_ledger_identity(
                ledger, self.config_sha256, self.limits, self.ledger_path
            )
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
            _validate_run_ledger_identity(
                ledger, self.config_sha256, self.limits, self.ledger_path
            )
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


def approve_quota_only_continuation(
    tracker: RunUsageBudgetTracker,
    *,
    new_limits: RunUsageLimits,
    explicit_user_approval: str,
    trusted_preflight_path: Path,
    settled_artifact_root: Path,
) -> RunUsageBudgetTracker:
    """Authorize one same-run continuation after a quota-only terminal stop.

    Settled calls remain immutable and count against the amended limits. The amendment
    binds the exact ledger prefix, so it cannot authorize a changed or replayed history.
    """

    _validate_quota_approval_inputs(
        tracker, new_limits, explicit_user_approval, trusted_preflight_path
    )
    frozen_request_sha256s = _trusted_preflight_request_hashes(
        trusted_preflight_path, tracker.config_sha256
    )
    non_quota_failure_inventory = _non_quota_failure_inventory(settled_artifact_root)
    if non_quota_failure_inventory:
        raise ValueError(
            "quota continuation is blocked by a non-quota failure: "
            + ", ".join(non_quota_failure_inventory)
        )
    if len(frozen_request_sha256s) != len(set(frozen_request_sha256s)):
        raise ValueError("frozen continuation request inventory is ambiguous")
    settled_request_sha256s = _trusted_settled_request_hashes(
        settled_artifact_root, tracker.ledger_path
    )
    if not set(settled_request_sha256s).issubset(frozen_request_sha256s):
        raise ValueError("settled requests differ from the frozen request inventory")
    with tracker._lock, _locked_json_list(tracker.ledger_path) as (_, ledger):
        _validate_run_ledger_identity(
            ledger, tracker.config_sha256, tracker.limits, tracker.ledger_path
        )
        if any(item.get("status") in {"reserved", "usage_unavailable"} for item in ledger):
            raise ValueError("quota continuation requires every launched call to be settled")
        exceeded = [item for item in ledger if item.get("status") == "limit_exceeded"]
        if len(settled_request_sha256s) != len(ledger):
            raise ValueError("every launched call needs one settled frozen request hash")
        allowed = {"run_input_tokens", "run_output_tokens"}
        if not exceeded or any(
            not set(item.get("reconciliation_stop_reasons", ())).issubset(allowed)
            or not item.get("reconciliation_stop_reasons")
            for item in exceeded
        ):
            raise ValueError("same-run continuation is allowed only for run quota exhaustion")
        prefix_hash = _ledger_prefix_sha256(ledger)
        amendment = {
            "schema_version": "run_quota_amendment_v1",
            "config_sha256": tracker.config_sha256,
            "approval_kind": "explicit_user_approval",
            "approval_record": explicit_user_approval.strip(),
            "ledger_entry_count": len(ledger),
            "ledger_prefix_sha256": prefix_hash,
            "prior_limits": _limits_payload(tracker.limits),
            "amended_limits": _limits_payload(new_limits),
            "settled_reservation_ids": [str(item["reservation_id"]) for item in ledger],
            "rerun_set": [],
            "frozen_request_sha256s": list(frozen_request_sha256s),
            "settled_request_sha256s": list(settled_request_sha256s),
        }
        path = tracker.quota_amendment_path
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != amendment:
                raise ValueError("quota continuation amendment is immutable")
        else:
            path.write_text(
                json.dumps(amendment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    return RunUsageBudgetTracker(
        ledger_path=tracker.ledger_path,
        limits=new_limits,
        config_sha256=tracker.config_sha256,
        capacity_wait_timeout_seconds=tracker.capacity_wait_timeout_seconds,
        capacity_poll_seconds=tracker.capacity_poll_seconds,
    )


def _validate_quota_approval_inputs(
    tracker: RunUsageBudgetTracker,
    new_limits: RunUsageLimits,
    approval: str,
    preflight_path: Path,
) -> None:
    if not approval.strip():
        raise ValueError("quota continuation requires explicit user approval")
    canonical_preflight = tracker.ledger_path.parent.parent / "cohort-preflight.json"
    if preflight_path.resolve() != canonical_preflight.resolve():
        raise ValueError("quota continuation requires the canonical run preflight")
    if new_limits.max_calls != tracker.limits.max_calls:
        raise ValueError("quota continuation cannot change the planned call inventory")
    if (
        new_limits.max_input_tokens < tracker.limits.max_input_tokens
        or new_limits.max_output_tokens < tracker.limits.max_output_tokens
        or new_limits == tracker.limits
    ):
        raise ValueError("quota continuation may only increase token quotas")


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
    amendment = (
        json.loads(tracker.quota_amendment_path.read_text(encoding="utf-8"))
        if tracker.quota_amendment_path.is_file()
        else None
    )
    limits_match = tracker.limits == limits or (
        amendment is not None
        and amendment.get("prior_limits") == _limits_payload(limits)
        and amendment.get("amended_limits") == _limits_payload(tracker.limits)
    )
    if (
        tracker.ledger_path != expected_ledger
        or not limits_match
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


def _reservation_stop_reasons(
    totals: dict[str, int],
    *,
    estimated_input_tokens: int,
    output_token_allowance: int,
    limits: RunUsageLimits,
) -> list[str]:
    reasons = []
    if totals["calls"] + 1 > limits.max_calls:
        reasons.append("run_call_count")
    if totals["input_tokens"] + estimated_input_tokens > limits.max_input_tokens:
        reasons.append("run_input_tokens")
    if totals["output_tokens"] + output_token_allowance > limits.max_output_tokens:
        reasons.append("run_output_tokens")
    return reasons


def _write_reservation(output_dir: Path, entry: dict[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-budget-reservation.json").write_text(
        json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return str(entry["reservation_id"])


def _write_stop(output_dir: Path, entry: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-budget-stop.json").write_text(
        json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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


def _settled_totals(ledger: list[dict[str, Any]]) -> dict[str, int]:
    totals = _reserved_or_observed_totals(ledger)
    settled = _reserved_or_observed_totals(
        [item for item in ledger if item.get("status") != "reserved"]
    )
    settled["calls"] = totals["calls"]
    return settled


def _unique_reservation(ledger: list[dict[str, Any]], reservation_id: str) -> dict[str, Any]:
    matches = [item for item in ledger if item.get("reservation_id") == reservation_id]
    if len(matches) != 1:
        raise ValueError("run usage reservation identity is missing or ambiguous")
    return matches[0]


def _validate_run_ledger_identity(
    ledger: list[dict[str, Any]],
    config_sha256: str,
    limits: RunUsageLimits,
    ledger_path: Path,
) -> None:
    expected_limits = {
        "max_calls": limits.max_calls,
        "max_input_tokens": limits.max_input_tokens,
        "max_output_tokens": limits.max_output_tokens,
    }
    if all(
        item.get("config_sha256") == config_sha256 and item.get("run_limits") == expected_limits
        for item in ledger
    ):
        return
    if not ledger:
        return
    amendment_path = ledger_path.with_name(
        f"{ledger_path.stem}.quota-amendment.json"
    )
    if not amendment_path.is_file():
        raise ValueError("run usage ledger identity differs from the active release")
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    count = int(amendment.get("ledger_entry_count", -1))
    prefix = ledger[:count]
    valid = (
        amendment.get("schema_version") == "run_quota_amendment_v1"
        and amendment.get("config_sha256") == config_sha256
        and amendment.get("amended_limits") == expected_limits
        and amendment.get("ledger_prefix_sha256") == _ledger_prefix_sha256(prefix)
        and amendment.get("settled_reservation_ids")
        == [str(item.get("reservation_id")) for item in prefix]
        and all(
            item.get("config_sha256") == config_sha256
            and item.get("run_limits") == amendment.get("prior_limits")
            for item in prefix
        )
        and all(
            item.get("config_sha256") == config_sha256
            and item.get("run_limits") == expected_limits
            for item in ledger[count:]
        )
    )
    if not valid:
        raise ValueError("run usage ledger identity differs from its quota amendment")


def _limits_payload(limits: RunUsageLimits) -> dict[str, int]:
    return {
        "max_calls": limits.max_calls,
        "max_input_tokens": limits.max_input_tokens,
        "max_output_tokens": limits.max_output_tokens,
    }


def _validate_continuation_request(
    amendment_path: Path, *, request_sha256: str | None
) -> None:
    if not amendment_path.is_file():
        return
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    if request_sha256 is None:
        raise ValueError("quota continuation requires an exact frozen request hash")
    frozen = set(amendment.get("frozen_request_sha256s", ()))
    settled = set(amendment.get("settled_request_sha256s", ()))
    ledger_path = amendment_path.with_name(
        amendment_path.name.removesuffix(".quota-amendment.json") + ".json"
    )
    if ledger_path.is_file():
        live = json.loads(ledger_path.read_text(encoding="utf-8"))
        settled.update(
            str(item["request_sha256"])
            for item in live
            if item.get("status") in {"completed", "limit_exceeded", "usage_unavailable"}
            and item.get("request_sha256")
        )
    if request_sha256 not in frozen:
        raise ValueError("quota continuation request is outside the frozen inventory")
    if request_sha256 in settled:
        raise ValueError("quota continuation cannot replay a settled request")


def _trusted_settled_request_hashes(root: Path, ledger_path: Path) -> tuple[str, ...]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    artifacts: dict[str, Path] = {}
    for path in root.rglob("run-budget-reservation.json"):
        saved = json.loads(path.read_text(encoding="utf-8"))
        reservation_id = str(saved.get("reservation_id", ""))
        if not reservation_id or reservation_id in artifacts:
            raise ValueError("settled reservation artifacts are missing or ambiguous")
        artifacts[reservation_id] = path.parent
    hashes = []
    for entry in ledger:
        directory = artifacts.get(str(entry.get("reservation_id")))
        if directory is None:
            raise ValueError("every settled ledger entry requires its reservation artifact")
        prompt_path, schema_path = directory / "prompt.txt", directory / "schema.json"
        if not prompt_path.is_file() or not schema_path.is_file():
            raise ValueError("settled request prompt or schema is missing")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        complete = prompt_path.read_text(encoding="utf-8") + json.dumps(
            schema, ensure_ascii=False, sort_keys=True
        )
        hashes.append(sha256(complete.encode()).hexdigest())
    return tuple(hashes)


def _trusted_preflight_request_hashes(path: Path, config_sha256: str) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "eligible" or payload.get("config_sha256") != config_sha256:
        raise ValueError("quota continuation preflight is not eligible for this release")
    requests = payload.get("requests")
    if not isinstance(requests, list) or int(payload.get("request_count", -1)) != len(requests):
        raise ValueError("quota continuation preflight request inventory is malformed")
    hashes = tuple(str(item.get("request_sha256", "")) for item in requests)
    if any(len(item) != 64 for item in hashes) or len(hashes) != len(set(hashes)):
        raise ValueError("quota continuation preflight request hashes are invalid")
    return hashes


def _non_quota_failure_inventory(root: Path) -> tuple[str, ...]:
    failures = []
    for path in root.rglob("execution-profile.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("return_code", -1)) != 0:
            failures.append(str(path.relative_to(root)))
    for path in root.rglob("deterministic-validation.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("functional_gate") != "pass":
            failures.append(str(path.relative_to(root)))
    for path in root.rglob("budget-stop.json"):
        failures.append(str(path.relative_to(root)))
    for path in root.rglob("run-budget-reservation.json"):
        validation_path = path.parent / "deterministic-validation.json"
        if not validation_path.is_file():
            failures.append(f"{path.parent.relative_to(root)}:missing_validation")
    return tuple(sorted(failures))


def _ledger_prefix_sha256(ledger: list[dict[str, Any]]) -> str:
    payload = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


__all__ = [
    "RunUsageBudgetTracker",
    "RunUsageLimits",
    "approve_quota_only_continuation",
    "model_max_output_tokens",
    "resolve_integrated_run_budget",
]
