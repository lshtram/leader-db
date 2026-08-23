"""Budgeted strict-JSON execution through the Codex subscription surface."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

import tiktoken
from pydantic import BaseModel

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from ._codex_worker_artifacts import read_codex_usage
from .codex_worker_command import build_codex_exec_command
from .execution_profile import (
    finalize_execution,
    start_execution_profile,
    write_execution_profile,
)
from .model_call_budget import (
    RunUsageBudgetTracker,
    StageBudgetTracker,
    model_max_output_tokens,
    resolve_integrated_run_budget,
)


class CallCoordinator(Protocol):
    """Coordination operations needed around a model launch."""

    def authorize_launch(self) -> None: ...

    def complete_call(self) -> None: ...

    def ensure_open(self) -> None: ...


def execute_json_model(
    project_root: Path,
    profile,
    prompt: str,
    model: type[BaseModel],
    output_dir: Path,
    *,
    budget_tracker: StageBudgetTracker | None = None,
    request_component: str = "unspecified",
    reasoning_effort: str | None = None,
    call_coordinator: CallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    process_runner=subprocess.run,
    command_builder=build_codex_exec_command,
    response_schema: dict | None = None,
    additional_inputs: tuple[str, ...] = (),
    isolated_web_research: bool = True,
    disable_web_search: bool = False,
    sandbox_mode: Literal["read-only", "danger-full-access"] = "read-only",
):
    """Execute one strict-JSON request with stage and run-wide accounting."""

    schema = deepcopy(response_schema) if response_schema is not None else model.model_json_schema()
    make_strict_response_schema(schema)
    run_budget_tracker = resolve_integrated_run_budget(output_dir, run_budget_tracker)
    run_reservation: str | None = None
    call_authorized = False
    launched = False
    events_path: Path | None = None
    command, return_code = None, None
    started: tuple[str, float] | None = None
    try:
        schema_text, complete_input, estimated_input_tokens = _measure_request(
            prompt, schema, additional_inputs
        )
        if run_budget_tracker is not None:
            capacity_check = call_coordinator.ensure_open if call_coordinator is not None else None
            run_reservation = run_budget_tracker.reserve(
                stage=budget_tracker.stage if budget_tracker is not None else "unspecified",
                component=request_component,
                estimated_input_tokens=estimated_input_tokens,
                output_token_allowance=_output_allowance(budget_tracker, profile.model),
                output_dir=output_dir,
                wait_for_capacity=True,
                capacity_check=capacity_check,
                request_sha256=sha256(complete_input.encode()).hexdigest(),
            )
        call_authorized = _authorize_call(call_coordinator)
        if budget_tracker is not None:
            budget_tracker.reserve(
                component=request_component,
                prompt=prompt,
                response_schema=schema,
                output_dir=output_dir,
                additional_inputs=additional_inputs,
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = output_dir / "prompt.txt"
        schema_path = output_dir / "schema.json"
        output_path = output_dir / "output.json"
        events_path = output_dir / "events.jsonl"
        stderr_path = output_dir / "stderr.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        command = command_builder(
            profile=profile,
            project_root=project_root,
            schema_path=schema_path,
            final_message_path=output_path,
            writable_dir=output_dir,
            isolated_web_research=isolated_web_research,
            disable_web_search=disable_web_search,
            sandbox_mode=sandbox_mode,
            reasoning_effort=reasoning_effort,
        )
        with (
            events_path.open("w", encoding="utf-8") as events,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            launched = True
            started = start_execution_profile()
            try:
                completed = process_runner(
                    command,
                    input=prompt,
                    text=True,
                    stdout=events,
                    stderr=stderr,
                    check=True,
                    timeout=1_800,
                )
                return_code = getattr(completed, "returncode", 0)
            except subprocess.CalledProcessError as exc:
                return_code = exc.returncode
                raise
    finally:
        finalizers = []
        if run_budget_tracker is not None and run_reservation is not None:
            if launched and events_path is not None:
                finalizers.append(
                    lambda: run_budget_tracker.reconcile(
                        run_reservation,
                        (
                            usage.model_dump(mode="json")
                            if (usage := read_codex_usage(events_path)) is not None
                            else None
                        ),
                    )
                )
            else:
                finalizers.append(lambda: run_budget_tracker.cancel_unlaunched(run_reservation))
        if call_coordinator is not None and call_authorized:
            finalizers.append(call_coordinator.complete_call)
        if launched and started is not None and events_path is not None:
            finalizers.append(
                lambda: write_execution_profile(
                    output_dir=output_dir,
                    events_path=events_path,
                    model=profile.model,
                    reasoning_effort=reasoning_effort,
                    started=started,
                    return_code=return_code,
                    request_characters=len(prompt),
                    response_schema_characters=len(schema_text),
                    estimated_input_tokens=estimated_input_tokens,
                    output_token_allowance=_output_allowance(budget_tracker, profile.model),
                    command=command,
                )
            )
        finalize_execution(*finalizers)
    return model.model_validate_json(output_path.read_text(encoding="utf-8"))


def _authorize_call(call_coordinator: CallCoordinator | None) -> bool:
    if call_coordinator is None:
        return False
    call_coordinator.authorize_launch()
    return True


def _output_allowance(budget_tracker: StageBudgetTracker | None, model: str) -> int:
    return (
        budget_tracker.budget.output_allowance(model)
        if budget_tracker is not None
        else model_max_output_tokens(model)
    )


def _measure_request(
    prompt: str, schema: dict, additional_inputs: tuple[str, ...]
) -> tuple[str, str, int]:
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    complete_input = prompt + schema_text + "".join(additional_inputs)
    token_count = len(tiktoken.get_encoding("o200k_base").encode(complete_input))
    return schema_text, complete_input, token_count
