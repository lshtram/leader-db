"""Zero-call preflight for one bounded post-review correction round."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import tiktoken

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .control_flow import load_question_correction_policy
from .model_call_budget import StageBudget
from .model_profiles import ResearchModelProfile
from .question_correction_ledger import (
    _CORRECTION_PREFLIGHT_CAPABILITY,
    _FINAL_PREFLIGHT_CAPABILITY,
    _authorize_corrections,
    _authorize_final_reviews,
    initialize_correction_ledger,
)
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_correction import (
    build_question_correction_prompt,
    experimental_review_findings,
    load_question_correction_prompts,
    validate_question_correction,
)
from .question_packet_expansion import expand_question_evidence_package
from .question_packet_phase_validation import (
    validate_chapter_question_review,
    validate_chapter_question_writing,
)
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_quality import (
    BlindQuestionQualityReview,
    _blind_labels,
    _review_prompt,
    build_blind_review_response_schema,
)
from .question_packet_writer import DiagnosticQuestionAnswer, _question_answer_response_model
from .question_review_preflight import load_review_input_snapshot


def build_question_correction_preflight(
    *,
    project_root: Path,
    writing_run: Path,
    review_run: Path,
    target_run: Path,
    judge_package_path: Path,
    policy_path: Path,
    prompts_path: Path,
    profile_name: str,
    profile: ResearchModelProfile,
    profiles_path: Path,
    stage_budget: StageBudget,
    final_review_stage_budget: StageBudget,
    final_review_profile: ResearchModelProfile,
    run_result_path: Path,
    output_path: Path,
    corpus_root: Path | None = None,
    writing_profile_name: str = "openai-luna-candidate",
    review_profile_name: str = "openai-luna-candidate",
    review_reasoning_effort: str = "high",
    remaining_call_capacity: int = 10_000,
    remaining_input_capacity: int = 10_000_000,
    remaining_output_capacity: int = 1_000_000,
    phase_output_quota: int = 250_000,
    final_review_input_reservation: int = 1_200_000,
    package_run: Path | None = None,
    writing_output_run: Path | None = None,
) -> Path:
    """Build expanded inputs and measure every failed-answer correction without calls."""

    if target_run.exists() and any(target_run.iterdir()):
        raise ValueError("question correction target run is already in use")
    load_question_correction_policy(policy_path)
    prompts, prompts_hash = load_question_correction_prompts(prompts_path)
    run_result = json.loads(run_result_path.read_text(encoding="utf-8"))
    failed = tuple(run_result.get("quality_failures", ()))
    if not failed or len(failed) != len(set(failed)):
        raise ValueError("correction preflight requires unique failed review questions")
    if profile.provider != "openai" or profile.execution_surface != "codex":
        raise ValueError("question correction preflight requires OpenAI Codex")
    package_run = package_run or writing_run
    writing_output_run = writing_output_run or writing_run
    source_preflight = json.loads(
        (package_run / "preflight-manifest.json").read_text(encoding="utf-8")
    )
    package_hashes = {
        item["chapter_id"]: item["sha256"] for item in source_preflight["question_packages"]
    }
    encoding = tiktoken.get_encoding("o200k_base")
    trusted_failed = _trusted_review_failures(
        project_root=project_root,
        package_run=package_run,
        writing_output_run=writing_output_run,
        review_run=review_run,
        package_hashes=package_hashes,
        corpus_root=corpus_root or judge_package_path.parent,
        profiles_path=profiles_path,
        writing_profile_name=writing_profile_name,
        review_profile_name=review_profile_name,
        review_reasoning_effort=review_reasoning_effort,
    )
    if tuple(sorted(failed)) != trusted_failed:
        raise ValueError("correction failure inventory differs from trusted review reload")
    expanded_by_chapter, requests = _build_correction_inputs(
        failed=failed,
        package_run=package_run,
        writing_output_run=writing_output_run,
        review_run=review_run,
        judge_package_path=judge_package_path,
        package_hashes=package_hashes,
        prompts=prompts,
        encoding=encoding,
        project_root=project_root,
        corpus_root=corpus_root or judge_package_path.parent,
        profiles_path=profiles_path,
        writing_profile_name=writing_profile_name,
        review_profile_name=review_profile_name,
        review_reasoning_effort=review_reasoning_effort,
    )
    reasons = _budget_reasons(requests, stage_budget)
    exact_input = sum(item["estimated_input_tokens"] for item in requests)
    correction_output_allowance = stage_budget.output_allowance(profile.model)
    final_review_output_allowance = final_review_stage_budget.output_allowance(
        final_review_profile.model
    )
    required_output_capacity = len(requests) * (
        correction_output_allowance + final_review_output_allowance
    )
    if len(requests) * 2 > remaining_call_capacity:
        reasons.append("run_call_capacity")
    if exact_input + final_review_input_reservation > remaining_input_capacity:
        reasons.append("run_input_capacity")
    if phase_output_quota < required_output_capacity:
        reasons.append("phase_output_quota")
    if required_output_capacity > remaining_output_capacity:
        reasons.append("run_output_capacity")
    target_run.mkdir(parents=True, exist_ok=False)
    initialize_correction_ledger(
        ledger_path=target_run / "correction-phase-ledger.json",
        policy_path=policy_path,
        run_result_path=run_result_path,
        question_ids=failed,
    )
    package_dir = target_run / "correction-packages"
    for chapter_id, package in expanded_by_chapter.items():
        path = package_dir / chapter_id / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {
        "schema_version": "question_correction_preflight_v1",
        "status": "eligible_for_corrections" if not reasons else "rejected",
        "phase_status": "pending_exact_final_review_preflight" if not reasons else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "api_key_used": False,
        "provider": profile.provider,
        "model": profile.model,
        "profile": profile_name,
        "surface": "codex_subscription",
        "reasoning_effort": "high",
        "planned_calls": len(requests) * 2,
        "exact_correction_calls": len(requests),
        "mandatory_final_review_calls": len(requests),
        "final_review_measurement_status": "required_after_corrections_before_calls",
        "correction_output_tokens_per_call": correction_output_allowance,
        "final_review_output_tokens_per_call": final_review_output_allowance,
        "maximum_phase_output_tokens": required_output_capacity,
        "phase_output_quota": phase_output_quota,
        "correction_limits": {
            "maximum_calls": len(requests),
            "maximum_input_tokens": remaining_input_capacity
            - final_review_input_reservation,
            "maximum_output_tokens": len(requests) * correction_output_allowance,
        },
        "final_review_input_reservation": final_review_input_reservation,
        "remaining_run_capacity": {
            "calls": remaining_call_capacity,
            "input_tokens": remaining_input_capacity,
            "output_tokens": remaining_output_capacity,
        },
        "execution_contract": {
            "correction_ordinal": 1,
            "final_review_ordinal": 1,
            "further_corrections_permitted": 0,
            "residual_quality_failure_blocks_judgment": False,
            "structural_failure_blocks_judgment": True,
        },
        "planned_input_tokens": sum(item["estimated_input_tokens"] for item in requests),
        "planned_request_characters": sum(item["request_characters"] for item in requests),
        "policy_sha256": _sha256(policy_path),
        "prompt_config_sha256": prompts_hash,
        "model_profiles_sha256": _sha256(profiles_path),
        "source_run_result_sha256": _sha256(run_result_path),
        "judge_package_sha256": _sha256(judge_package_path),
        "expanded_package_sha256s": {
            chapter_id: _payload_hash(package.model_dump(mode="json"))
            for chapter_id, package in expanded_by_chapter.items()
        },
        "budget_stop_reasons": reasons,
        "requests": sorted(requests, key=lambda item: item["question_id"]),
        "output_roots_unused": [
            str(target_run / "question-corrections"),
            str(target_run / "final-question-review"),
            str(target_run / "chapter-judgments"),
        ],
        "source_evidence_count": len(
            json.loads(judge_package_path.read_text(encoding="utf-8")).get("evidence", ())
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not reasons:
        _authorize_corrections(
            ledger_path=target_run / "correction-phase-ledger.json",
            preflight_path=output_path,
            capability=_CORRECTION_PREFLIGHT_CAPABILITY,
        )
    return output_path


def _trusted_review_failures(
    *,
    project_root: Path,
    package_run: Path,
    writing_output_run: Path,
    review_run: Path,
    package_hashes: dict[str, str],
    corpus_root: Path,
    profiles_path: Path,
    writing_profile_name: str,
    review_profile_name: str,
    review_reasoning_effort: str,
) -> tuple[str, ...]:
    failures = []
    for chapter_id in tuple(f"{number}B" for number in range(1, 9)):
        package_path = package_run / f"question-packages/{chapter_id}/package.json"
        if _sha256(package_path) != package_hashes.get(chapter_id):
            raise ValueError(f"writing package hash mismatch: {chapter_id}")
        package = ChapterQuestionEvidencePackage.model_validate_json(
            package_path.read_bytes()
        )
        approved_path = _find_by_sha256(corpus_root, package.selected_analysis_sha256)
        manifest = validate_chapter_question_review(
            project_root=project_root,
            package=package,
            approved_analysis_path=approved_path,
            writing_dir=writing_output_run / f"question-writing/{chapter_id}",
            output_dir=review_run / f"question-review/{chapter_id}",
            profile_name=review_profile_name,
            writing_profile_name=writing_profile_name,
            profiles_path=profiles_path,
            reasoning_effort=review_reasoning_effort,
            experiment_policy_path=project_root
            / "configs/research-question-review-experiment.yaml",
        )
        failures.extend(
            artifact.question_id for artifact in manifest.artifacts if artifact.status == "fail"
        )
    return tuple(sorted(failures))


def _build_correction_inputs(
    *,
    failed: tuple[str, ...],
    package_run: Path,
    writing_output_run: Path,
    review_run: Path,
    judge_package_path: Path,
    package_hashes: dict[str, str],
    prompts,
    encoding,
    project_root: Path,
    corpus_root: Path,
    profiles_path: Path,
    writing_profile_name: str,
    review_profile_name: str,
    review_reasoning_effort: str,
) -> tuple[dict[str, ChapterQuestionEvidencePackage], list[dict]]:
    expanded_by_chapter = {}
    requests = []
    for chapter_id in sorted({question_id.split(".")[0] for question_id in failed}):
        package_path = package_run / f"question-packages/{chapter_id}/package.json"
        if _sha256(package_path) != package_hashes[chapter_id]:
            raise ValueError(f"writing package hash mismatch: {chapter_id}")
        package = ChapterQuestionEvidencePackage.model_validate_json(package_path.read_bytes())
        approved_path = _find_by_sha256(corpus_root, package.selected_analysis_sha256)
        writing_dir = writing_output_run / f"question-writing/{chapter_id}"
        writing = validate_chapter_question_writing(
            project_root=project_root,
            package=package,
            output_dir=writing_dir,
            approved_analysis_path=approved_path,
            profile_name=writing_profile_name,
            profiles_path=profiles_path,
        )
        snapshot = load_review_input_snapshot(writing_dir, writing)
        validate_chapter_question_review(
            project_root=project_root,
            package=package,
            approved_analysis_path=approved_path,
            writing_dir=writing_dir,
            output_dir=review_run / f"question-review/{chapter_id}",
            profile_name=review_profile_name,
            writing_profile_name=writing_profile_name,
            profiles_path=profiles_path,
            reasoning_effort=review_reasoning_effort,
            experiment_policy_path=project_root
            / "configs/research-question-review-experiment.yaml",
        )
        additions, sources = _review_additions(review_run, chapter_id, failed)
        expanded = expand_question_evidence_package(
            package=package,
            judge_package_path=judge_package_path,
            additions_by_question=additions,
            close_evidence_discovery=True,
        )
        expanded_by_chapter[chapter_id] = expanded
        for question_id, source in sources.items():
            packet = next(item for item in expanded.packets if item.question_id == question_id)
            predecessor_path = writing_dir / f"questions/{question_id}/accepted-output.json"
            predecessor = snapshot.answers[question_id]
            manifest_path, review_path, manifest, review = source
            findings = experimental_review_findings(manifest, review)
            prompt = build_question_correction_prompt(
                packet=packet,
                predecessor=predecessor,
                findings=findings,
                prompts=prompts,
            )
            schema = _question_answer_response_model(
                packet.coverage.required_evidence_ids, allow_reopen=False
            ).model_json_schema()
            make_strict_response_schema(schema)
            schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
            complete = prompt + schema_text
            requests.append(
                _request_measurement(
                    chapter_id=chapter_id,
                    question_id=question_id,
                    prompt=prompt,
                    schema=schema,
                    complete=complete,
                    packet=packet,
                    predecessor_path=predecessor_path,
                    manifest_path=manifest_path,
                    review_path=review_path,
                    evidence_ids=additions[question_id],
                    findings=findings,
                    encoding=encoding,
                )
            )
    return expanded_by_chapter, requests


def build_final_review_preflight(
    *,
    packets: dict[str, object],
    corrected_answers: dict[str, DiagnosticQuestionAnswer],
    correction_validation_arguments: dict[str, dict],
    approved_answers: dict[str, dict],
    profile: ResearchModelProfile,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str,
    stage_budget: StageBudget,
    remaining_call_capacity: int,
    remaining_input_capacity: int,
    remaining_output_capacity: int,
    phase_output_quota: int,
    prompts_path: Path,
    phase_ledger_path: Path,
    output_root: Path,
    output_path: Path,
) -> Path:
    """Exactly measure every mandatory post-correction review before any review call."""

    question_ids = set(packets)
    if question_ids != set(corrected_answers) or question_ids != set(approved_answers):
        raise ValueError("final-review preflight inputs must have identical question IDs")
    if question_ids != set(correction_validation_arguments):
        raise ValueError("final-review preflight requires every trusted correction input")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("final-review output root is already in use")
    encoding = tiktoken.get_encoding("o200k_base")
    requests = []
    prompts, prompt_hash = load_question_packet_prompts(prompts_path)
    for question_id in sorted(question_ids):
        trusted_answer, _ = validate_question_correction(
            **correction_validation_arguments[question_id]
        )
        if trusted_answer != corrected_answers[question_id]:
            raise ValueError("final-review answer differs from trusted correction reload")
        packet = packets[question_id]
        labels = _blind_labels(question_id)
        prompt = _review_prompt(
            packet,
            {
                label: (
                    approved_answers[question_id]
                    if source == "approved"
                    else corrected_answers[question_id].model_dump(mode="json")
                )
                for label, source in labels.items()
            },
            prompts.review_template,
        )
        schema = build_blind_review_response_schema(packet)
        complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        requests.append(
            {
                "question_id": question_id,
                "request_characters": len(complete),
                "estimated_input_tokens": len(encoding.encode(complete)),
                "complete_request_sha256": sha256(complete.encode()).hexdigest(),
            }
        )
    reasons = _budget_reasons(requests, stage_budget)
    total_input = sum(item["estimated_input_tokens"] for item in requests)
    required_output = len(requests) * stage_budget.output_allowance(profile.model)
    if len(requests) > remaining_call_capacity:
        reasons.append("run_call_capacity")
    if total_input > remaining_input_capacity:
        reasons.append("run_input_capacity")
    if required_output > phase_output_quota:
        reasons.append("phase_output_quota")
    if required_output > remaining_output_capacity:
        reasons.append("run_output_capacity")
    payload = {
        "schema_version": "question_final_review_preflight_v1",
        "status": "eligible" if not reasons else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "planned_calls": len(requests),
        "planned_input_tokens": total_input,
        "profile": profile_name,
        "provider": profile.provider,
        "model": profile.model,
        "surface": profile.execution_surface,
        "reasoning_effort": reasoning_effort,
        "model_profiles_sha256": _sha256(profiles_path),
        "output_tokens_per_call": stage_budget.output_allowance(profile.model),
        "review_limits": {
            "maximum_calls": remaining_call_capacity,
            "maximum_input_tokens": remaining_input_capacity,
            "maximum_output_tokens": phase_output_quota,
        },
        "phase_output_quota": phase_output_quota,
        "required_output_capacity": required_output,
        "prompt_config_sha256": prompt_hash,
        "budget_stop_reasons": reasons,
        "requests": requests,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not reasons:
        _authorize_final_reviews(
            ledger_path=phase_ledger_path,
            preflight_path=output_path,
            capability=_FINAL_PREFLIGHT_CAPABILITY,
        )
    return output_path


def _review_additions(
    review_run: Path, chapter_id: str, failed: tuple[str, ...]
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple]]:
    additions = {}
    sources = {}
    for question_id in sorted(item for item in failed if item.startswith(f"{chapter_id}.")):
        review_dir = review_run / f"question-review/{chapter_id}/questions/{question_id}"
        manifest_path = review_dir / "blind-review-manifest.json"
        output_file = review_dir / "output.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        review = BlindQuestionQualityReview.model_validate_json(output_file.read_bytes())
        if manifest.get("quality_gate") != "fail" or review.question_id != question_id:
            raise ValueError(f"correction source is not a failed review: {question_id}")
        evidence_ids = tuple(review.strongest_omitted_evidence_ids)
        additions[question_id] = evidence_ids
        sources[question_id] = (manifest_path, output_file, manifest, review)
    return additions, sources


def _request_measurement(**values) -> dict:
    prompt = values["prompt"]
    schema = values["schema"]
    complete = values["complete"]
    packet = values["packet"]
    return {
        "chapter_id": values["chapter_id"],
        "question_id": values["question_id"],
        "request_characters": len(complete),
        "estimated_input_tokens": len(values["encoding"].encode(complete)),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "response_schema_sha256": _payload_hash(schema),
        "complete_request_sha256": sha256(complete.encode()).hexdigest(),
        "expanded_packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "predecessor_sha256": _sha256(values["predecessor_path"]),
        "source_review_manifest_sha256": _sha256(values["manifest_path"]),
        "source_review_output_sha256": _sha256(values["review_path"]),
        "promoted_evidence_ids": list(values["evidence_ids"]),
        "review_findings_sha256": _payload_hash(values["findings"]),
    }


def _budget_reasons(requests: list[dict], budget: StageBudget) -> list[str]:
    reasons = []
    if len(requests) > budget.max_calls:
        reasons.append("stage_call_count")
    if sum(item["estimated_input_tokens"] for item in requests) > budget.max_stage_input_tokens:
        reasons.append("stage_input_tokens")
    for item in requests:
        if item["request_characters"] > budget.max_request_characters:
            reasons.append(f"{item['question_id']}:request_characters")
        if item["estimated_input_tokens"] > budget.max_request_input_tokens:
            reasons.append(f"{item['question_id']}:request_input_tokens")
    return reasons


def _find_by_sha256(root: Path, expected: str) -> Path:
    matches = [
        path
        for path in root.rglob("resolved-chapter-analysis.json")
        if _sha256(path) == expected
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one approved analysis for hash {expected}, found {len(matches)}"
        )
    return matches[0]


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = ["build_final_review_preflight", "build_question_correction_preflight"]
