"""Budgeted strict-JSON execution through the Codex subscription surface."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Protocol

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
):
    """Execute one strict-JSON request with stage and run-wide accounting."""

    schema = model.model_json_schema()
    make_strict_response_schema(schema)
    run_budget_tracker = resolve_integrated_run_budget(output_dir, run_budget_tracker)
    if call_coordinator is not None:
        call_coordinator.authorize_launch()
    run_reservation: str | None = None
    launched = False
    events_path: Path | None = None
    command, return_code = None, None
    started: tuple[str, float] | None = None
    try:
        schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        estimated_input_tokens = len(
            tiktoken.get_encoding("o200k_base").encode(prompt + schema_text)
        )
        if run_budget_tracker is not None:
            run_reservation = run_budget_tracker.reserve(
                stage=budget_tracker.stage if budget_tracker is not None else "unspecified",
                component=request_component,
                estimated_input_tokens=estimated_input_tokens,
                output_token_allowance=model_max_output_tokens(profile.model),
                output_dir=output_dir,
            )
        if budget_tracker is not None:
            budget_tracker.reserve(
                component=request_component,
                prompt=prompt,
                response_schema=schema,
                output_dir=output_dir,
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
            isolated_web_research=True,
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
        if call_coordinator is not None:
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
                    output_token_allowance=model_max_output_tokens(profile.model),
                    command=command,
                )
            )
        finalize_execution(*finalizers)
    return model.model_validate_json(output_path.read_text(encoding="utf-8"))
