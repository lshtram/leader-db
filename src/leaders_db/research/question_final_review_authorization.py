"""Capability-bound execution for mandatory post-correction reviews."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .question_correction_ledger import CorrectionPhaseLedger, claim_phase_action
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_correction import (
    _FINAL_REVIEW_EXECUTION_CAPABILITY,
    run_final_question_review,
)
from .question_packet_quality import validate_blind_review_artifacts
from .question_packet_writer import DiagnosticQuestionAnswer
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

_AUTHORIZATION_CAPABILITY = object()


@dataclass(frozen=True)
class FinalReviewAuthorization:
    preflight_path: Path
    preflight_sha256: str
    target_run: Path
    question_ids: frozenset[str]
    request_sha256s: frozenset[str]
    profile_name: str
    profiles_path: Path
    profiles_sha256: str
    reasoning_effort: str
    policy_path: Path
    policy_sha256: str
    stage_budgets_path: Path
    stage_budgets_sha256: str
    limits: dict[str, int]
    _capability: object


def load_final_review_authorization(
    *,
    preflight_path: Path,
    target_run: Path,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str,
    policy_path: Path,
    stage_budgets_path: Path,
    approved_preflight_sha256: str,
    approved_limits: dict[str, int],
) -> FinalReviewAuthorization:
    """Load one exact eligible final-review inventory and transport."""

    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    stage = load_stage_budget_tracker(stage_budgets_path, "question_final_review")
    ledger = CorrectionPhaseLedger.model_validate_json(
        (target_run / "correction-phase-ledger.json").read_bytes()
    )
    preflight_hash = _sha256(preflight_path)
    hashes = {
        item["question_id"]: item["complete_request_sha256"]
        for item in saved.get("requests", ())
    }
    correction_claims = {f"{item}:correct:1" for item in ledger.question_ids}
    review_claims = {item for item in ledger.claimed_actions if ":review:" in item}
    if (
        saved.get("status") != "eligible"
        or preflight_hash != approved_preflight_sha256
        or saved.get("profile") != profile_name
        or saved.get("provider") != profile.provider
        or saved.get("model") != profile.model
        or saved.get("surface") != profile.execution_surface
        or saved.get("reasoning_effort") != reasoning_effort
        or saved.get("model_profiles_sha256") != _sha256(profiles_path)
        or saved.get("output_tokens_per_call")
        != stage.budget.output_allowance(profile.model)
        or ledger.final_review_preflight_sha256 != preflight_hash
        or ledger.final_review_request_sha256s != hashes
        or set(hashes) != set(ledger.question_ids)
        or not correction_claims.issubset(ledger.claimed_actions)
        or not review_claims.issubset(
            {f"{item}:review:1" for item in ledger.question_ids}
        )
    ):
        raise ValueError("final-review authorization differs from trusted preflight")
    saved_limits = {key: int(value) for key, value in saved["review_limits"].items()}
    if set(approved_limits) != set(saved_limits) or any(
        approved_limits[key] < value for key, value in saved_limits.items()
    ):
        raise ValueError("final-review authorization exceeds approved limits")
    return FinalReviewAuthorization(
        preflight_path=preflight_path,
        preflight_sha256=preflight_hash,
        target_run=target_run,
        question_ids=frozenset(hashes),
        request_sha256s=frozenset(hashes.values()),
        profile_name=profile_name,
        profiles_path=profiles_path,
        profiles_sha256=_sha256(profiles_path),
        reasoning_effort=reasoning_effort,
        policy_path=policy_path,
        policy_sha256=_sha256(policy_path),
        stage_budgets_path=stage_budgets_path,
        stage_budgets_sha256=_sha256(stage_budgets_path),
        limits=dict(approved_limits),
        _capability=_AUTHORIZATION_CAPABILITY,
    )


def run_authorized_final_review(
    *,
    authorization: FinalReviewAuthorization,
    project_root: Path,
    packet: QuestionEvidencePacket,
    approved_answer: dict,
    corrected_answer: DiagnosticQuestionAnswer,
    output_dir: Path,
) -> Path:
    """Run or trusted-recover one exact mandatory final review."""

    if authorization._capability is not _AUTHORIZATION_CAPABILITY:
        raise ValueError("final review lacks trusted authorization")
    if (
        _sha256(authorization.preflight_path) != authorization.preflight_sha256
        or _sha256(authorization.profiles_path) != authorization.profiles_sha256
        or _sha256(authorization.policy_path) != authorization.policy_sha256
        or _sha256(authorization.stage_budgets_path)
        != authorization.stage_budgets_sha256
        or packet.question_id not in authorization.question_ids
    ):
        raise ValueError("final-review authorization changed before execution")
    ledger_path = authorization.target_run / "correction-phase-ledger.json"
    ledger = CorrectionPhaseLedger.model_validate_json(ledger_path.read_bytes())
    claimed = f"{packet.question_id}:review:1" in ledger.claimed_actions
    if output_dir.exists() and any(output_dir.iterdir()):
        return _recover_final_review(
            authorization, project_root, packet, approved_answer, corrected_answer, output_dir
        )
    if claimed:
        raise ValueError("claimed final review lacks completed output")
    run_tracker = RunUsageBudgetTracker(
        ledger_path=authorization.target_run / "final-review-usage.json",
        limits=RunUsageLimits(
            max_calls=authorization.limits["maximum_calls"],
            max_input_tokens=authorization.limits["maximum_input_tokens"],
            max_output_tokens=authorization.limits["maximum_output_tokens"],
        ),
        config_sha256=authorization.preflight_sha256,
        allowed_request_sha256s=authorization.request_sha256s,
    )
    stage_tracker = load_stage_budget_tracker(
        authorization.stage_budgets_path,
        "question_final_review",
        ledger_path=authorization.target_run / "final-review-stage-usage.json",
    )
    return run_final_question_review(
        project_root=project_root,
        packet=packet,
        approved_answer=approved_answer,
        corrected_answer=corrected_answer,
        output_dir=output_dir,
        profile_name=authorization.profile_name,
        profiles_path=authorization.profiles_path,
        policy_path=authorization.policy_path,
        reasoning_effort=authorization.reasoning_effort,
        phase_ledger_path=ledger_path,
        budget_tracker=stage_tracker,
        run_budget_tracker=run_tracker,
        call_coordinator=ModelCallCoordinator(),
        execution_capability=_FINAL_REVIEW_EXECUTION_CAPABILITY,
    )


def _recover_final_review(
    authorization: FinalReviewAuthorization,
    project_root: Path,
    packet: QuestionEvidencePacket,
    approved_answer: dict,
    corrected_answer: DiagnosticQuestionAnswer,
    output_dir: Path,
) -> Path:
    """Recover only one trusted review backed by one completed reservation."""

    manifest = validate_blind_review_artifacts(
        packet=packet,
        approved_answer=approved_answer,
        experimental_answer=corrected_answer,
        output_dir=output_dir,
        project_root=project_root,
        profile_name=authorization.profile_name,
        profiles_path=authorization.profiles_path,
        reasoning_effort=authorization.reasoning_effort,
    )
    manifest_path = output_dir / "blind-review-manifest.json"
    ledger = CorrectionPhaseLedger.model_validate_json(
        (authorization.target_run / "correction-phase-ledger.json").read_bytes()
    )
    request_hash = ledger.final_review_request_sha256s[packet.question_id]
    usage = json.loads((authorization.target_run / "final-review-usage.json").read_text())
    completed = [
        item
        for item in usage
        if item.get("status") == "completed" and item.get("request_sha256") == request_hash
    ]
    if len(completed) != 1 or manifest.get("quality_gate") not in {"pass", "fail"}:
        raise ValueError("final-review recovery lacks one exact completed reservation")
    binding_path = output_dir / "final-review-policy-binding.json"
    expected_binding = {
        "schema_version": "question_final_review_policy_binding_v1",
        "question_id": packet.question_id,
        "final_review_ordinal": 1,
        "policy_sha256": authorization.policy_sha256,
        "review_manifest_sha256": _sha256(manifest_path),
    }
    if binding_path.exists():
        if json.loads(binding_path.read_text()) != expected_binding:
            raise ValueError("final-review policy binding differs from trusted review")
    else:
        binding_path.write_text(
            json.dumps(expected_binding, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    key = f"{packet.question_id}:review:1"
    if key not in ledger.claimed_actions:
        claim_phase_action(
            ledger_path=authorization.target_run / "correction-phase-ledger.json",
            policy_path=authorization.policy_path,
            question_id=packet.question_id,
            action="review",
            request_sha256=request_hash,
        )
    return manifest_path


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "FinalReviewAuthorization",
    "load_final_review_authorization",
    "run_authorized_final_review",
]
