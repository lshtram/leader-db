"""Configured complete-request budgets with explicit pre-call stops."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Lock

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field

from .run_usage_budget import (
    RunUsageBudgetTracker,
    RunUsageLimits,
    model_max_output_tokens,
    resolve_integrated_run_budget,
)


class StageBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_calls: int = Field(gt=0)
    max_request_characters: int = Field(gt=0)
    max_request_input_tokens: int = Field(gt=0)
    max_stage_input_tokens: int = Field(gt=0)


class StageBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(gt=0)
    stages: dict[str, StageBudget]


@dataclass
class StageBudgetTracker:
    """Reserve configured stage capacity before each model invocation."""

    stage: str
    budget: StageBudget
    config_sha256: str
    calls_reserved: int = 0
    input_tokens_reserved: int = 0
    reservations: list[dict[str, object]] = field(default_factory=list)
    ledger_path: Path | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def reserve(
        self,
        *,
        component: str,
        prompt: str,
        response_schema: dict,
        output_dir: Path,
        additional_inputs: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Measure prompt plus schema and stop before an unsafe reservation."""

        with self._lock:
            with self._locked_ledger() as (handle, ledger):
                schema_text = json.dumps(response_schema, ensure_ascii=False, sort_keys=True)
                complete_input = prompt + schema_text + "".join(additional_inputs)
                characters = len(complete_input)
                tokens = len(tiktoken.get_encoding("o200k_base").encode(complete_input))
                calls_before = len(ledger) if handle is not None else self.calls_reserved
                tokens_before = (
                    sum(int(item["estimated_input_tokens"]) for item in ledger)
                    if handle is not None
                    else self.input_tokens_reserved
                )
                reasons = []
                if characters > self.budget.max_request_characters:
                    reasons.append("request_characters")
                if tokens > self.budget.max_request_input_tokens:
                    reasons.append("request_input_tokens")
                if calls_before + 1 > self.budget.max_calls:
                    reasons.append("stage_call_count")
                if tokens_before + tokens > self.budget.max_stage_input_tokens:
                    reasons.append("stage_input_tokens")
                measurement = {
                    "schema_version": "model_call_budget_reservation_v1",
                    "stage": self.stage,
                    "component": component,
                    "config_sha256": self.config_sha256,
                    "request_characters": characters,
                    "estimated_input_tokens": tokens,
                    "calls_before": calls_before,
                    "stage_input_tokens_before": tokens_before,
                    "stop_reasons": reasons,
                    "decision": "stop" if reasons else "reserved",
                }
                if reasons:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "budget-stop.json").write_text(
                        json.dumps(measurement, indent=2, sort_keys=True) + "\n"
                    )
                    raise ValueError(
                        f"model budget stopped stage={self.stage} component={component}: "
                        + ", ".join(reasons)
                    )
                if handle is not None:
                    ledger.append(measurement)
                    handle.seek(0)
                    handle.write(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
                    handle.truncate()
                self.calls_reserved += 1
                self.input_tokens_reserved += tokens
                self.reservations.append(measurement)
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "budget-reservation.json").write_text(
                    json.dumps(measurement, indent=2, sort_keys=True) + "\n"
                )
                return measurement

    @contextmanager
    def _locked_ledger(self):
        if self.ledger_path is None:
            yield None, []
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.ledger_path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            text = handle.read()
            ledger = json.loads(text) if text else []
            if not isinstance(ledger, list):
                raise ValueError("model stage budget ledger is malformed")
            yield handle, ledger
            fcntl.flock(handle, fcntl.LOCK_UN)


def load_stage_budget_tracker(
    config_path: Path, stage: str, *, ledger_path: Path | None = None
) -> StageBudgetTracker:
    """Load one named stage budget with its reproducibility binding."""

    raw = config_path.read_bytes()
    config = StageBudgets.model_validate(yaml.safe_load(raw))
    if stage not in config.stages:
        raise ValueError(f"model stage budget is not configured: {stage}")
    return StageBudgetTracker(
        stage=stage,
        budget=config.stages[stage],
        config_sha256=sha256(raw).hexdigest(),
        ledger_path=ledger_path,
    )


__all__ = [
    "RunUsageBudgetTracker",
    "RunUsageLimits",
    "StageBudgetTracker",
    "load_stage_budget_tracker",
    "model_max_output_tokens",
    "resolve_integrated_run_budget",
]
