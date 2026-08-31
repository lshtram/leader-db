"""Run high-reasoning Sol reviews over completed chapter judgments."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

import tiktoken

from ._codex_worker_artifacts import read_codex_usage
from .chapter_judge_models import ChapterJudgmentBatch
from .chapter_judgment_review import (
    ChapterJudgmentReview,
    apply_review,
    codex_chapter_review_json_schema,
    validate_review,
)
from .chapter_judgment_review_outputs import sum_usage, write_reviewed_package
from .chapter_projection import RulerChapterProjection
from .codex_worker_command import build_codex_exec_command
from .control_flow import enforce_model_action
from .execution_profile import (
    finalize_execution,
    start_execution_profile,
    write_execution_profile,
)
from .model_call_budget import (
    RunUsageBudgetTracker,
    StageBudgetTracker,
    load_stage_budget_tracker,
    model_max_output_tokens,
    resolve_integrated_run_budget,
)
from .model_profiles import load_research_model_profiles


def review_chapter_judgments(
    *,
    project_root: Path,
    judgment_paths: tuple[Path, ...],
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    timeout_seconds: int = 10_800,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
) -> Path:
    """Review and revise each chapter artifact, then write a profiled manifest."""

    enforce_model_action(project_root, "chapter_judgment_review", role="independent_quality")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.model != "gpt-5.6-sol" or "chapter_judge" not in profile.roles:
        raise ValueError("judgment review requires a Sol chapter-judge profile")
    output_dir.mkdir(parents=True, exist_ok=False)
    run_budget_tracker = resolve_integrated_run_budget(output_dir, run_budget_tracker)
    budget = load_stage_budget_tracker(
        project_root / "configs/research-stage-budgets.yaml",
        "chapter_judgment_review",
        ledger_path=output_dir / "stage-budget-reservations.json",
    )
    results = tuple(
        _review_one(
            project_root=project_root,
            judgment_path=path.resolve(),
            output_dir=output_dir,
            profile=profile,
            budget=budget,
            timeout_seconds=timeout_seconds,
            run_budget_tracker=run_budget_tracker,
        )
        for path in judgment_paths
    )
    manifest_path = output_dir / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "chapter_judgment_review_run_v1",
                "profile": profile_name,
                "model": profile.model,
                "reasoning_effort": "high",
                "chapter_count": len(results),
                "chapters": results,
                "usage": sum_usage(results),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_reviewed_package(output_dir=output_dir, results=results)
    return manifest_path


def _review_one(
    *,
    project_root: Path,
    judgment_path: Path,
    output_dir: Path,
    profile: Any,
    budget: StageBudgetTracker,
    timeout_seconds: int,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
) -> dict[str, Any]:
    judgment = ChapterJudgmentBatch.model_validate_json(judgment_path.read_text(encoding="utf-8"))
    chapter_dir = output_dir / judgment.chapter_id
    chapter_dir.mkdir()
    projection_paths = _projection_paths(judgment_path, judgment)
    source_digest = sha256(judgment_path.read_bytes()).hexdigest()
    prompt_path, schema_path, pending_path, events_path = (
        chapter_dir / "review-prompt.txt",
        chapter_dir / "review-schema.json",
        chapter_dir / "review.pending.json",
        chapter_dir / "review-events.jsonl",
    )
    prompt_path.write_text(
        _review_prompt(judgment_path, judgment, projection_paths, source_digest),
        encoding="utf-8",
    )
    protected_hashes = {
        path: sha256(path.read_bytes()).hexdigest() for path in (judgment_path, *projection_paths)
    }
    schema_path.write_text(
        json.dumps(codex_chapter_review_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    input_paths = (judgment_path, *projection_paths)
    additional_inputs = tuple(path.read_text(encoding="utf-8") for path in input_paths)
    run_reservation, started, completed, launched = None, None, None, False
    try:
        if run_budget_tracker is not None:
            complete = (
                prompt
                + json.dumps(
                    codex_chapter_review_json_schema(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "".join(additional_inputs)
            )
            run_reservation = run_budget_tracker.reserve(
                stage="chapter_judgment_review",
                component=judgment.chapter_id,
                estimated_input_tokens=len(tiktoken.get_encoding("o200k_base").encode(complete)),
                output_token_allowance=model_max_output_tokens(profile.model),
                output_dir=chapter_dir,
            )
        _reserve_review_request(
            budget=budget,
            chapter_id=judgment.chapter_id,
            chapter_dir=chapter_dir,
            prompt=prompt,
            input_paths=input_paths,
        )
        command = build_codex_exec_command(
            profile=profile,
            project_root=project_root,
            schema_path=schema_path,
            final_message_path=pending_path,
            writable_dir=chapter_dir,
            sandbox_mode="danger-full-access",
            reasoning_effort="high",
        )
        launched = True
        started = start_execution_profile()
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        events_path.write_text(completed.stdout, encoding="utf-8")
    finally:
        finalizers = []
        if run_budget_tracker is not None and run_reservation is not None:
            if launched:
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
        if launched and started is not None:
            finalizers.append(
                lambda: _profile_review_execution(
                    chapter_dir=chapter_dir,
                    events_path=events_path,
                    profile=profile,
                    started=started,
                    completed=completed,
                    prompt=prompt,
                    additional_inputs=additional_inputs,
                    command=command,
                    chapter_id=judgment.chapter_id,
                )
            )
        finalize_execution(*finalizers)
    if any(
        not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest
        for path, digest in protected_hashes.items()
    ):
        raise RuntimeError("Sol review modified a hash-bound source artifact")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Sol review failed for {judgment.chapter_id} with exit {completed.returncode}"
        )
    review = ChapterJudgmentReview.model_validate_json(pending_path.read_text(encoding="utf-8"))
    projections = tuple(
        RulerChapterProjection.model_validate_json(path.read_text(encoding="utf-8"))
        for path in projection_paths
    )
    evidence_ids = {
        item.job_key: {evidence.evidence_id for evidence in item.evidence} for item in projections
    }
    validate_review(
        review,
        judgment=judgment,
        source_sha256=source_digest,
        evidence_ids_by_job=evidence_ids,
    )
    reviewed = apply_review(judgment, review)
    review_path = chapter_dir / "review.json"
    reviewed_path = chapter_dir / "reviewed-chapter-judgment.json"
    review_path.write_text(review.model_dump_json(indent=2) + "\n", encoding="utf-8")
    reviewed_path.write_text(reviewed.model_dump_json(indent=2) + "\n", encoding="utf-8")
    usage = read_codex_usage(events_path)
    changes = sum(item.disposition != "retain" for item in review.decisions)
    return {
        "chapter_id": judgment.chapter_id,
        "source_judgment": str(judgment_path),
        "source_sha256": source_digest,
        "review": str(review_path),
        "reviewed_judgment": str(reviewed_path),
        "score_change_count": changes,
        "usage": usage.model_dump(mode="json") if usage is not None else None,
    }


def _profile_review_execution(
    *,
    chapter_dir: Path,
    events_path: Path,
    profile: Any,
    started: tuple[str, float],
    completed: subprocess.CompletedProcess[str] | None,
    prompt: str,
    additional_inputs: tuple[str, ...],
    command: tuple[str, ...],
    chapter_id: str,
) -> None:
    schema_text = json.dumps(codex_chapter_review_json_schema(), ensure_ascii=False, sort_keys=True)
    complete = prompt + schema_text + "".join(additional_inputs)
    write_execution_profile(
        output_dir=chapter_dir,
        events_path=events_path,
        model=profile.model,
        reasoning_effort="high",
        started=started,
        return_code=completed.returncode if completed is not None else None,
        request_characters=len(prompt) + sum(map(len, additional_inputs)),
        response_schema_characters=len(schema_text),
        estimated_input_tokens=len(tiktoken.get_encoding("o200k_base").encode(complete)),
        output_token_allowance=model_max_output_tokens(profile.model),
        command=command,
        extra={"stage": "chapter_judgment_review", "component": chapter_id},
    )


def _projection_paths(judgment_path: Path, judgment: ChapterJudgmentBatch) -> tuple[Path, ...]:
    directory = judgment_path.parent / "chapter-inputs"
    paths = tuple(sorted(directory.glob("*.json")))
    if len(paths) != len(judgment.evaluations):
        raise ValueError("source judgment does not have one sibling projection per ruler")
    return paths


def _reserve_review_request(
    *,
    budget: StageBudgetTracker,
    chapter_id: str,
    chapter_dir: Path,
    prompt: str,
    input_paths: tuple[Path, ...],
) -> dict[str, object]:
    """Reserve the exact review request before its model subprocess starts."""

    return budget.reserve(
        component=chapter_id,
        prompt=prompt,
        response_schema=codex_chapter_review_json_schema(),
        output_dir=chapter_dir,
        additional_inputs=tuple(path.read_text(encoding="utf-8") for path in input_paths),
    )


def _review_prompt(
    judgment_path: Path,
    judgment: ChapterJudgmentBatch,
    projection_paths: tuple[Path, ...],
    source_digest: str,
) -> str:
    sources = [
        {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
        for path in projection_paths
    ]
    identity = {
        "schema_version": "chapter_judgment_review_v1",
        "chapter_id": judgment.chapter_id,
        "source_job_key": judgment.job_key,
        "source_sha256": source_digest,
        "reviewer_model": "gpt-5.6-sol",
        "reasoning_effort": "high",
    }
    return f"""Act as the independent final score-and-rationale reviewer for one
Leaders Database chapter. Use high reasoning and no external discovery. Read the
source judgment and every hash-bound ruler projection listed below in full.
Do not edit, patch, move, or rewrite any file. Filesystem tools are available only
to read the listed JSON inputs; your sole output is the structured final response.

For every ruler, independently test evidence relevance, ruler attribution, inherited
baseline, contrary evidence, source limitations, absolute chapter anchors, and cohort
ordering. Do not reward evidence volume and do not compare against client scores.

You may retain the score or correct it by at most 1 point upward or downward, using
half-point increments. Never convert a null to a number or a number to null. Make a
change only when the original judge was materially too generous or too severe. For
every ruler, return a self-contained revised rationale and revised lower/higher-anchor
explanations, even when retaining the score. Cite only evidence IDs in that ruler's
projection. The revised prose must reflect the reviewed score and explicitly resolve
the weakness identified in `review_explanation`.

Immutable review identity:
{json.dumps(identity, indent=2)}

Source judgment:
{json.dumps({"path": str(judgment_path), "sha256": source_digest}, indent=2)}

Ruler projections:
{json.dumps(sources, indent=2)}

Return only the requested JSON. Include exactly one decision for each of the
{len(judgment.evaluations)} source evaluations.
"""


__all__ = ["review_chapter_judgments"]
