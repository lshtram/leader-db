"""Execute resumable whole-context reading and fresh passage verification batches."""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from leaders_db.conversational_evidence.judging import CODEX_INPUT_CHARACTER_LIMIT

from .codex_worker_command import build_codex_exec_command
from .control_flow import enforce_model_action
from .corpus_evidence_bind import bind_batch_evidence
from .corpus_reader_models import (
    BatchFactOutput,
    BatchVerification,
    BoundEvidence,
)
from .corpus_reader_normalize import normalize_reader_output, reconcile_reader
from .corpus_reader_prompt import build_corpus_reader_prompt, write_reader_request_manifest
from .corpus_reader_recovery import recover_batch_evidence as _recover_batch_evidence
from .corpus_reader_results import build_batch_result
from .corpus_reading_plan import CorpusReadingPlan, ReadingBatch
from .corpus_verification import (
    apply_verification as _apply_verification,
)
from .corpus_verification import (
    build_verification_candidates as _build_verification_candidates,
)
from .corpus_verification import (
    partition_verification as _partition_verification,
)
from .corpus_verification import (
    verification_prompt as _verification_prompt,
)
from .corpus_verification_request import (
    bind_verification_request,
    load_bound_verification_result,
)
from .json_model_execution import execute_json_model as _execute_json_model
from .model_call_budget import (
    RunUsageBudgetTracker,
    StageBudgetTracker,
    load_stage_budget_tracker,
)
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles


def run_corpus_reading(
    *,
    project_root: Path,
    acquisition_dir: Path,
    plan_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_batches: int = 3,
) -> Path:
    """Read, bind, and independently verify every queued reading batch."""

    enforce_model_action(project_root, "corpus_reading", role="production")
    enforce_model_action(project_root, "corpus_verification", role="independent_quality")
    plan = CorpusReadingPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    profile_config_sha256 = sha256(profiles_path.read_bytes()).hexdigest()
    if "document_reader" not in profile.roles:
        raise ValueError("selected profile does not permit document reading")
    output_dir.mkdir(parents=True, exist_ok=True)
    budget_path = project_root / "configs/research-stage-budgets.yaml"
    reader_budget = load_stage_budget_tracker(budget_path, "corpus_reader")
    verifier_budget = load_stage_budget_tracker(budget_path, "corpus_verifier")
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
        futures = {
            executor.submit(
                _run_batch,
                project_root=project_root,
                acquisition_dir=acquisition_dir,
                plan=plan,
                batch=batch,
                output_dir=output_dir,
                profile=profile,
                profile_name=profile_name,
                profile_config_sha256=profile_config_sha256,
                reader_budget=reader_budget,
                verifier_budget=verifier_budget,
            ): batch.batch_id
            for batch in plan.batches
        }
        for future in as_completed(futures):
            batch_id = futures[future]
            try:
                results[batch_id] = future.result()
            except Exception as exc:
                results[batch_id] = {
                    "batch_id": batch_id,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "evidence_count": 0,
                    "accepted_count": 0,
                }
    ordered = [results[batch.batch_id] for batch in plan.batches]
    path = output_dir / "reading-run-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "corpus_reading_run_v1",
                "profile": profile_name,
                "model": profile.model,
                "batches": ordered,
                "evidence_count": sum(item["evidence_count"] for item in ordered),
                "failed_batch_ids": [
                    item["batch_id"] for item in ordered if item.get("status") == "failed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    failed = [item["batch_id"] for item in ordered if item.get("status") == "failed"]
    if failed:
        raise RuntimeError(
            "corpus reading is incomplete; resume the same plan until every batch "
            f"succeeds: {', '.join(failed)}"
        )
    return path


def _run_batch(
    *,
    project_root: Path,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    output_dir: Path,
    profile,
    profile_name: str,
    profile_config_sha256: str,
    reader_budget: StageBudgetTracker,
    verifier_budget: StageBudgetTracker,
) -> dict[str, Any]:
    started = time.monotonic()
    batch_dir = output_dir / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = batch_dir / "verified-evidence.json"
    request_path = batch_dir / "reader-request.json"
    if not request_path.is_file():
        legacy = _recover_batch_evidence(
            acquisition_dir=acquisition_dir,
            plan=plan,
            batch=batch,
            batch_dir=batch_dir,
        )
        if legacy is not None and all(not item.citations for item in legacy):
            return build_batch_result(
                batch,
                legacy,
                batch_dir,
                resumed=True,
                elapsed_seconds=time.monotonic() - started,
                request_binding="legacy_unbound",
            )
    rendered = build_corpus_reader_prompt(
        acquisition_dir=acquisition_dir,
        plan=plan,
        batch=batch,
        prompts_path=project_root / "configs/corpus-reader-prompts.yaml",
        questions_path=(Path(__file__).parents[1] / "conversational_evidence/data/questions.json"),
    )
    if len(rendered.prompt) > int(CODEX_INPUT_CHARACTER_LIMIT * 0.9):
        raise ValueError("corpus reader request exceeds character safety margin")
    if profile.context_window is None or rendered.estimated_tokens + 12_000 > int(
        profile.context_window * 0.9
    ):
        raise ValueError("corpus reader request exceeds context safety margin")
    if request_path.is_file():
        write_reader_request_manifest(
            request_path,
            rendered,
            profile_name,
            profile_config_sha256,
            profile.model,
            BatchFactOutput,
            batch_dir / "reader",
        )
        recovered = _recover_batch_evidence(
            acquisition_dir=acquisition_dir,
            plan=plan,
            batch=batch,
            batch_dir=batch_dir,
            profile=profile,
            profile_name=profile_name,
            profile_config_sha256=profile_config_sha256,
        )
        if recovered is not None:
            return build_batch_result(
                batch,
                recovered,
                batch_dir,
                resumed=True,
                elapsed_seconds=time.monotonic() - started,
            )
    else:
        write_reader_request_manifest(
            request_path,
            rendered,
            profile_name,
            profile_config_sha256,
            profile.model,
            BatchFactOutput,
            batch_dir / "reader",
        )
    reader = _load_or_execute_json(
        project_root,
        profile,
        rendered.prompt,
        BatchFactOutput,
        batch_dir / "reader",
        expected_source_ids=set(batch.source_ids),
        budget_tracker=reader_budget,
        request_component=batch.batch_id,
    )
    reader = reconcile_reader(reader, batch)
    if any(item.citation_span_ids for item in reader.facts):
        raise ValueError("whole-unit discovery must not select paragraph citations")
    bound = bind_batch_evidence(
        acquisition_dir=acquisition_dir,
        plan=plan,
        batch=batch,
        reader_output=reader,
    )
    (batch_dir / "bound-evidence.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in bound], indent=2) + "\n",
        encoding="utf-8",
    )
    if bound:
        candidates = _build_verification_candidates(
            acquisition_dir=acquisition_dir, plan=plan, evidence=bound
        )
        verification = _load_or_execute_verification(
            project_root,
            profile,
            profile_name,
            profile_config_sha256,
            bound,
            candidates,
            batch_dir / "verification",
            verifier_budget,
        )
        evidence = _apply_verification(bound, verification, candidates)
    else:
        evidence = ()
    evidence_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in evidence], indent=2) + "\n",
        encoding="utf-8",
    )
    return build_batch_result(
        batch, evidence, batch_dir, resumed=False, elapsed_seconds=time.monotonic() - started
    )


def _load_or_execute_verification(
    project_root: Path,
    profile,
    profile_name: str,
    profile_config_sha256: str,
    evidence: tuple[BoundEvidence, ...],
    candidates,
    output_dir: Path,
    budget_tracker: StageBudgetTracker,
) -> BatchVerification:
    groups = _partition_verification(evidence, candidates)
    bind_verification_request(
        output_dir=output_dir,
        groups=groups,
        candidates=candidates,
        profile_name=profile_name,
        profile_config_sha256=profile_config_sha256,
        model=profile.model,
        create=True,
    )
    output_path = output_dir / "output.json"
    recovered = load_bound_verification_result(
        output_dir=output_dir, groups=groups, require_complete=False
    )
    if recovered is not None:
        return recovered
    if len(groups) == 1:
        return _load_or_execute_json(
            project_root,
            profile,
            _verification_prompt(evidence, candidates),
            BatchVerification,
            output_dir,
            budget_tracker=budget_tracker,
            request_component="verification-complete",
        )
    verdicts = []
    for number, group in enumerate(groups, start=1):
        result = _load_or_execute_json(
            project_root,
            profile,
            _verification_prompt(group, candidates),
            BatchVerification,
            output_dir / f"part-{number:03d}",
            budget_tracker=budget_tracker,
            request_component=f"verification-part-{number:03d}",
        )
        expected_ids = {item.evidence_id for item in group}
        actual_ids = [item.evidence_id for item in result.verdicts]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            raise ValueError("verification partition evidence IDs differ from its request")
        verdicts.extend(result.verdicts)
    combined = BatchVerification(verdicts=tuple(verdicts))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(combined.model_dump_json(indent=2) + "\n", encoding="utf-8")
    validated = load_bound_verification_result(
        output_dir=output_dir, groups=groups, require_complete=True
    )
    assert validated is not None
    return validated


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
    call_coordinator: ModelCallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    response_schema: dict | None = None,
):
    return _execute_json_model(
        project_root,
        profile,
        prompt,
        model,
        output_dir,
        budget_tracker=budget_tracker,
        request_component=request_component,
        reasoning_effort=reasoning_effort,
        call_coordinator=call_coordinator,
        run_budget_tracker=run_budget_tracker,
        process_runner=subprocess.run,
        command_builder=build_codex_exec_command,
        response_schema=response_schema,
    )


def _load_or_execute_json(
    project_root: Path,
    profile,
    prompt: str,
    model: type[BaseModel],
    output_dir: Path,
    expected_source_ids: set[str] | None = None,
    budget_tracker: StageBudgetTracker | None = None,
    request_component: str = "unspecified",
):
    output_path = output_dir / "output.json"
    if output_path.is_file():
        try:
            return model.model_validate_json(output_path.read_text(encoding="utf-8"))
        except ValueError:
            if model is BatchFactOutput and expected_source_ids is not None:
                return normalize_reader_output(output_path, expected_source_ids)
            raise ValueError(
                "saved model output is invalid; unchanged requests are not retried"
            ) from None
    try:
        return execute_json_model(
            project_root,
            profile,
            prompt,
            model,
            output_dir,
            budget_tracker=budget_tracker,
            request_component=request_component,
        )
    except ValueError:
        if model is BatchFactOutput and expected_source_ids is not None:
            return normalize_reader_output(output_path, expected_source_ids)
        raise


__all__ = ["execute_json_model", "run_corpus_reading"]
