"""Capability-bound execution for one preflighted correction inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .control_flow import load_question_correction_policy
from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .question_correction_ledger import CorrectionPhaseLedger, claim_phase_action
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_correction import (
    _CORRECTION_EXECUTION_CAPABILITY,
    load_question_correction_prompts,
    run_question_correction,
    validate_question_correction,
)
from .question_packet_writer import DiagnosticQuestionAnswer
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

_AUTHORIZATION_CAPABILITY = object()


@dataclass(frozen=True)
class QuestionCorrectionAuthorization:
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
    prompts_path: Path
    prompts_sha256: str
    limits: dict[str, int]
    stage_budgets_path: Path
    stage_budgets_sha256: str
    _capability: object


def load_question_correction_authorization(
    *,
    preflight_path: Path,
    target_run: Path,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str,
    policy_path: Path,
    prompts_path: Path,
    stage_budgets_path: Path,
    approved_preflight_sha256: str,
    approved_limits: dict[str, int],
) -> QuestionCorrectionAuthorization:
    """Validate immutable transport, inventory, and ledger bindings."""

    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    stage = load_stage_budget_tracker(stage_budgets_path, "question_correction")
    load_question_correction_policy(policy_path)
    _, prompts_hash = load_question_correction_prompts(prompts_path)
    ledger = CorrectionPhaseLedger.model_validate_json(
        (target_run / "correction-phase-ledger.json").read_bytes()
    )
    preflight_hash = _sha256(preflight_path)
    requests = saved.get("requests", ())
    hashes = {item["question_id"]: item["complete_request_sha256"] for item in requests}
    if (
        saved.get("status") != "eligible_for_corrections"
        or preflight_hash != approved_preflight_sha256
        or saved.get("profile") != profile_name
        or saved.get("provider") != profile.provider
        or saved.get("model") != profile.model
        or saved.get("reasoning_effort") != reasoning_effort
        or saved.get("model_profiles_sha256") != _sha256(profiles_path)
        or saved.get("policy_sha256") != _sha256(policy_path)
        or saved.get("prompt_config_sha256") != prompts_hash
        or saved.get("correction_output_tokens_per_call")
        != stage.budget.output_allowance(profile.model)
        or ledger.correction_preflight_sha256 != preflight_hash
        or ledger.correction_request_sha256s != hashes
        or set(hashes) != set(ledger.question_ids)
        or not _valid_completed_correction_claims(ledger)
    ):
        raise ValueError("correction authorization differs from trusted preflight")
    limits = saved.get("correction_limits", {})
    if set(limits) != {
        "maximum_calls",
        "maximum_input_tokens",
        "maximum_output_tokens",
    }:
        raise ValueError("correction authorization lacks exact limits")
    saved_limits = {key: int(value) for key, value in limits.items()}
    if set(approved_limits) != set(saved_limits) or any(
        approved_limits[key] < value for key, value in saved_limits.items()
    ):
        raise ValueError("correction authorization exceeds approved limits")
    return QuestionCorrectionAuthorization(
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
        prompts_path=prompts_path,
        prompts_sha256=_sha256(prompts_path),
        limits=dict(approved_limits),
        stage_budgets_path=stage_budgets_path,
        stage_budgets_sha256=_sha256(stage_budgets_path),
        _capability=_AUTHORIZATION_CAPABILITY,
    )


def _valid_completed_correction_claims(ledger: CorrectionPhaseLedger) -> bool:
    """Allow durable restart after any exact subset of correction claims."""

    permitted = {f"{question_id}:correct:1" for question_id in ledger.question_ids}
    claims = tuple(ledger.claimed_actions)
    return len(claims) == len(set(claims)) and set(claims).issubset(permitted)


def run_authorized_question_correction(
    *,
    authorization: QuestionCorrectionAuthorization,
    project_root: Path,
    packet: QuestionEvidencePacket,
    predecessor: DiagnosticQuestionAnswer,
    findings: dict,
    output_dir: Path,
) -> Path:
    """Execute one exact correction under the shared durable allowlist."""

    if authorization._capability is not _AUTHORIZATION_CAPABILITY:
        raise ValueError("question correction lacks trusted authorization")
    if (
        _sha256(authorization.preflight_path) != authorization.preflight_sha256
        or _sha256(authorization.profiles_path) != authorization.profiles_sha256
        or _sha256(authorization.policy_path) != authorization.policy_sha256
        or _sha256(authorization.prompts_path) != authorization.prompts_sha256
        or _sha256(authorization.stage_budgets_path)
        != authorization.stage_budgets_sha256
        or packet.question_id not in authorization.question_ids
    ):
        raise ValueError("question correction authorization changed before execution")
    phase = CorrectionPhaseLedger.model_validate_json(
        (authorization.target_run / "correction-phase-ledger.json").read_bytes()
    )
    already_claimed = f"{packet.question_id}:correct:1" in phase.claimed_actions
    if already_claimed and (not output_dir.exists() or not any(output_dir.iterdir())):
        raise ValueError("claimed correction lacks its completed output for trusted recovery")
    if output_dir.exists() and any(output_dir.iterdir()):
        if {path.name for path in output_dir.iterdir()} == {"run-budget-stop.json"}:
            if already_claimed:
                raise ValueError("claimed correction cannot be a pre-call quota stop")
            _preserve_quota_stop(authorization, packet.question_id, output_dir)
        else:
            return _recover_completed_claim(
                authorization=authorization,
                packet=packet,
                predecessor=predecessor,
                findings=findings,
                output_dir=output_dir,
            )
    tracker = RunUsageBudgetTracker(
        ledger_path=authorization.target_run / "correction-usage.json",
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
        "question_correction",
        ledger_path=authorization.target_run / "correction-stage-usage.json",
    )
    return run_question_correction(
        project_root=project_root,
        packet=packet,
        predecessor=predecessor,
        findings=findings,
        output_dir=output_dir,
        profile_name=authorization.profile_name,
        profiles_path=authorization.profiles_path,
        prompts_path=authorization.prompts_path,
        reasoning_effort=authorization.reasoning_effort,
        policy_path=authorization.policy_path,
        phase_ledger_path=authorization.target_run / "correction-phase-ledger.json",
        budget_tracker=stage_tracker,
        run_budget_tracker=tracker,
        call_coordinator=ModelCallCoordinator(),
        execution_capability=_CORRECTION_EXECUTION_CAPABILITY,
    )


def _recover_completed_claim(
    *,
    authorization: QuestionCorrectionAuthorization,
    packet: QuestionEvidencePacket,
    predecessor: DiagnosticQuestionAnswer,
    findings: dict,
    output_dir: Path,
) -> Path:
    """Finish only a paid, validated correction whose phase claim was interrupted."""

    phase_ledger_path = authorization.target_run / "correction-phase-ledger.json"
    phase = CorrectionPhaseLedger.model_validate_json(phase_ledger_path.read_bytes())
    request_hash = phase.correction_request_sha256s.get(packet.question_id)
    usage_path = authorization.target_run / "correction-usage.json"
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    completed = [
        item
        for item in usage
        if item.get("status") == "completed" and item.get("request_sha256") == request_hash
    ]
    validate_question_correction(
        packet=packet,
        predecessor=predecessor,
        findings=findings,
        output_dir=output_dir,
        profile_name=authorization.profile_name,
        profiles_path=authorization.profiles_path,
        prompts_path=authorization.prompts_path,
        reasoning_effort=authorization.reasoning_effort,
        policy_path=authorization.policy_path,
        phase_ledger_path=phase_ledger_path,
    )
    key = f"{packet.question_id}:correct:1"
    if len(completed) != 1:
        raise ValueError("correction recovery lacks one exact completed reservation")
    if key not in phase.claimed_actions:
        claim_phase_action(
            ledger_path=phase_ledger_path,
            policy_path=authorization.policy_path,
            question_id=packet.question_id,
            action="correct",
            request_sha256=request_hash,
        )
    return output_dir / "correction-manifest.json"


def _preserve_quota_stop(
    authorization: QuestionCorrectionAuthorization,
    question_id: str,
    output_dir: Path,
) -> None:
    """Archive an exact pre-call quota stop before an amended reservation attempt."""

    source = output_dir / "run-budget-stop.json"
    digest = _sha256(source)
    destination = (
        authorization.target_run
        / "quota-stop-diagnostics"
        / question_id
        / f"{digest}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != source.read_bytes():
            raise ValueError("quota-stop diagnostic hash collision")
        source.unlink()
    else:
        source.replace(destination)
    output_dir.rmdir()


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "QuestionCorrectionAuthorization",
    "load_question_correction_authorization",
    "run_authorized_question_correction",
]
