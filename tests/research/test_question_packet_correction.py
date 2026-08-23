from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.model_call_budget import load_stage_budget_tracker
from leaders_db.research.model_profiles import load_research_model_profiles
from leaders_db.research.question_correction_authorization import (
    _valid_completed_correction_claims,
)
from leaders_db.research.question_correction_ledger import (
    _CORRECTION_PREFLIGHT_CAPABILITY,
    _FINAL_PREFLIGHT_CAPABILITY,
    CorrectionPhaseLedger,
    _authorize_corrections,
    _authorize_final_reviews,
    claim_phase_action,
    initialize_correction_ledger,
)
from leaders_db.research.question_correction_preflight import (
    _review_additions,
    build_question_correction_preflight,
)
from leaders_db.research.question_evidence_packet_models import ChapterQuestionEvidencePackage
from leaders_db.research.question_packet_correction import (
    _CORRECTION_EXECUTION_CAPABILITY,
    build_question_correction_prompt,
    experimental_review_findings,
    load_question_correction_prompts,
    residual_question_concern,
    run_question_correction,
    validate_question_correction,
)
from leaders_db.research.question_packet_quality import (
    BlindCandidateQuality,
    BlindQuestionQualityReview,
)
from leaders_db.research.question_packet_writer import (
    DiagnosticQuestionAnswer,
    _question_answer_response_model,
)


def _candidate(label: str, result: str) -> BlindCandidateQuality:
    return BlindCandidateQuality(
        candidate=label,
        factual_support=result,
        citation_entailment=result,
        material_coverage=result,
        balance_and_limits="pass",
        attribution_and_period="pass",
        judgeability="pass",
        material_regressions=(
            ("A material correction remains necessary.",) if result == "fail" else ()
        ),
        unsupported_claims=("One claim lacks support.",) if result == "fail" else (),
        missed_evidence_ids=("E-1",) if result == "fail" else (),
        rationale="A sufficiently detailed rationale for the final correction review.",
    )


def test_final_review_findings_become_confidence_input_not_stop() -> None:
    review = BlindQuestionQualityReview(
        question_id="1B.1",
        candidates=(_candidate("A", "pass"), _candidate("B", "fail")),
        preferred_candidate="A",
        strongest_omitted_evidence_ids=("E-1",),
        overall_rationale="A sufficiently detailed overall rationale for this final review.",
    )
    manifest = {"randomization": {"A": "approved", "B": "experimental"}}

    findings = experimental_review_findings(manifest, review)
    residual = residual_question_concern(manifest=manifest, review=review)

    assert findings["failed_dimensions"] == [
        "factual_support",
        "citation_entailment",
        "material_coverage",
    ]
    assert residual.final_quality_gate == "fail"
    assert residual.confidence_treatment == "lower"
    assert residual.material_regressions == ("A material correction remains necessary.",)


def test_omission_only_final_review_lowers_confidence() -> None:
    review = BlindQuestionQualityReview(
        question_id="1B.1",
        candidates=(_candidate("A", "pass"), _candidate("B", "pass")),
        preferred_candidate="A",
        strongest_omitted_evidence_ids=("E-1",),
        overall_rationale="A sufficiently detailed overall rationale for this final review.",
    )
    manifest = {"randomization": {"A": "approved", "B": "experimental"}}

    residual = residual_question_concern(manifest=manifest, review=review)

    assert residual.final_quality_gate == "fail"
    assert residual.confidence_treatment == "lower"
    assert residual.strongest_omitted_evidence_ids == ("E-1",)


def test_failed_review_without_omitted_evidence_still_enters_correction() -> None:
    root = Path.cwd()
    review_run = (
        root
        / "research/runs/five-ruler-2023-luna-sol-v8-release/model-output/ISR"
    )

    additions, sources = _review_additions(review_run, "6B", ("6B.7",))

    assert additions == {"6B.7": ()}
    assert set(sources) == {"6B.7"}


def test_phase_ledger_enforces_one_correction_then_one_review(tmp_path: Path) -> None:
    root = Path.cwd()
    policy = root / "configs/research-question-correction-policy.yaml"
    source = tmp_path / "source.json"
    source.write_text("{}\n")
    ledger = tmp_path / "ledger.json"
    initialize_correction_ledger(
        ledger_path=ledger,
        policy_path=policy,
        run_result_path=source,
        question_ids=("1B.1",),
    )
    correction_preflight = tmp_path / "correction-preflight.json"
    correction_preflight.write_text(
        json.dumps(
            {
                "status": "eligible_for_corrections",
                "requests": [
                    {"question_id": "1B.1", "complete_request_sha256": "correction-hash"}
                ],
            }
        )
    )
    _authorize_corrections(
        ledger_path=ledger,
        preflight_path=correction_preflight,
        capability=_CORRECTION_PREFLIGHT_CAPABILITY,
    )
    claim_phase_action(
        ledger_path=ledger,
        policy_path=policy,
        question_id="1B.1",
        action="correct",
        request_sha256="correction-hash",
    )
    with pytest.raises(ValueError, match="already consumed"):
        claim_phase_action(
            ledger_path=ledger, policy_path=policy, question_id="1B.1", action="correct"
        )
    preflight = tmp_path / "final-preflight.json"
    preflight.write_text(
        json.dumps(
            {
                "status": "eligible",
                "requests": [
                    {"question_id": "1B.1", "complete_request_sha256": "request-hash"}
                ],
            }
        )
    )
    _authorize_final_reviews(
        ledger_path=ledger,
        preflight_path=preflight,
        capability=_FINAL_PREFLIGHT_CAPABILITY,
    )
    claim_phase_action(
        ledger_path=ledger,
        policy_path=policy,
        question_id="1B.1",
        action="review",
        request_sha256="request-hash",
    )
    with pytest.raises(ValueError, match="already consumed"):
        claim_phase_action(
            ledger_path=ledger,
            policy_path=policy,
            question_id="1B.1",
            action="review",
            request_sha256="request-hash",
        )


def test_correction_authorization_can_reload_after_exact_partial_claims() -> None:
    ledger = CorrectionPhaseLedger(
        schema_version="question_correction_phase_ledger_v1",
        policy_sha256="a" * 64,
        source_run_result_sha256="b" * 64,
        question_ids=("1B.1", "1B.2"),
        claimed_actions=("1B.1:correct:1",),
    )

    assert _valid_completed_correction_claims(ledger)
    assert not _valid_completed_correction_claims(
        ledger.model_copy(update={"claimed_actions": ("1B.1:review:1",)})
    )


def test_correction_round_trips_and_rejects_prompt_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = Path.cwd()
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (
            root
            / "research/runs/netanyahu-2023-integrated-luna-sol-v17"
            / "question-packages/8B/package.json"
        ).read_bytes()
    )
    packet = next(item for item in package.packets if item.question_id == "8B.9")
    source = (
        root
        / "research/runs/netanyahu-2023-integrated-luna-sol-v17"
        / "question-writing/8B/questions/8B.9"
    )
    predecessor = DiagnosticQuestionAnswer.model_validate_json(
        (source / "accepted-output.json").read_bytes()
    )
    raw_output = (source / "output.json").read_text(encoding="utf-8")
    findings = {
        "failed_dimensions": ["material_coverage"],
        "material_regressions": ["Address one material omission."],
        "unsupported_claims": [],
        "missed_evidence_ids": [],
        "candidate_rationale": "A sufficiently detailed correction rationale for testing.",
        "strongest_omitted_evidence_ids": [],
        "overall_rationale": "A sufficiently detailed overall rationale for correction testing.",
    }
    run_result = tmp_path / "source-run-result.json"
    run_result.write_text('{"quality_failures":["8B.9"]}\n')
    ledger = tmp_path / "phase-ledger.json"
    initialize_correction_ledger(
        ledger_path=ledger,
        policy_path=root / "configs/research-question-correction-policy.yaml",
        run_result_path=run_result,
        question_ids=("8B.9",),
    )

    def fake_execute(project_root, profile, prompt, model, output_dir, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        schema = model.model_json_schema()
        make_strict_response_schema(schema)
        (output_dir / "schema.json").write_text(json.dumps(schema, indent=2))
        (output_dir / "output.json").write_text(raw_output, encoding="utf-8")
        return model.model_validate_json(raw_output)

    monkeypatch.setattr(
        "leaders_db.research.question_packet_correction.execute_json_model", fake_execute
    )
    arguments = {
        "packet": packet,
        "predecessor": predecessor,
        "findings": findings,
        "output_dir": tmp_path / "correction",
        "profile_name": "openai-luna-candidate",
        "profiles_path": root / "configs/research-models.yaml",
        "prompts_path": root / "configs/question-answer-correction-prompts.yaml",
        "reasoning_effort": "high",
        "policy_path": root / "configs/research-question-correction-policy.yaml",
        "phase_ledger_path": ledger,
        "run_budget_tracker": object(),
        "execution_capability": _CORRECTION_EXECUTION_CAPABILITY,
    }
    prompts, _ = load_question_correction_prompts(arguments["prompts_path"])
    prompt = build_question_correction_prompt(
        packet=packet, predecessor=predecessor, findings=findings, prompts=prompts
    )
    schema = _question_answer_response_model(
        packet.coverage.required_evidence_ids, allow_reopen=False
    ).model_json_schema()
    request_hash = sha256(
        (prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)).encode()
    ).hexdigest()
    correction_preflight = tmp_path / "correction-preflight.json"
    correction_preflight.write_text(
        json.dumps(
            {
                "status": "eligible_for_corrections",
                "requests": [
                    {
                        "question_id": packet.question_id,
                        "complete_request_sha256": request_hash,
                    }
                ],
            }
        )
    )
    _authorize_corrections(
        ledger_path=ledger,
        preflight_path=correction_preflight,
        capability=_CORRECTION_PREFLIGHT_CAPABILITY,
    )
    run_question_correction(project_root=root, **arguments)

    validation_arguments = {
        key: value
        for key, value in arguments.items()
        if key not in {"run_budget_tracker", "execution_capability"}
    }
    answer, manifest = validate_question_correction(**validation_arguments)
    assert answer.question_id == "8B.9"
    assert manifest["functional_gate"] == "pass"

    (tmp_path / "correction/prompt.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="saved correction prompt"):
        validate_question_correction(**validation_arguments)


def test_v20_correction_preflight_promotes_exact_review_evidence_without_calls(
    tmp_path: Path,
) -> None:
    root = Path.cwd()
    writing = root / "research/runs/netanyahu-2023-integrated-luna-sol-v17"
    review = root / "research/runs/netanyahu-2023-integrated-luna-sol-v20-constrained-review"
    target = tmp_path / "v21"
    profiles_path = root / "configs/research-models.yaml"
    profile = load_research_model_profiles(profiles_path).profiles[
        "openai-luna-candidate"
    ]

    output = build_question_correction_preflight(
        project_root=root,
        writing_run=writing,
        review_run=review,
        target_run=target,
        judge_package_path=(
            root
            / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR"
            / "corpus-judge-package.json"
        ),
        policy_path=root / "configs/research-question-correction-policy.yaml",
        prompts_path=root / "configs/question-answer-correction-prompts.yaml",
        profile_name="openai-luna-candidate",
        profile=profile,
        profiles_path=profiles_path,
        stage_budget=load_stage_budget_tracker(
            root / "configs/research-stage-budgets.yaml", "question_correction"
        ).budget,
        final_review_stage_budget=load_stage_budget_tracker(
            root / "configs/research-stage-budgets.yaml", "question_review"
        ).budget,
        final_review_profile=profile,
        run_result_path=review / "run-result.json",
        output_path=target / "question-correction-preflight.json",
    )

    manifest = json.loads(output.read_text())
    assert manifest["status"] == "eligible_for_corrections"
    assert manifest["phase_status"] == "pending_exact_final_review_preflight"
    assert manifest["planned_calls"] == 16
    assert manifest["exact_correction_calls"] == 8
    assert manifest["mandatory_final_review_calls"] == 8
    assert manifest["model_calls_executed"] == 0
    assert manifest["reservations_created"] == 0
    assert {item["question_id"] for item in manifest["requests"]} == {
        "2B.6",
        "3B.4",
        "4B.1",
        "4B.5",
        "5B.10",
        "6B.4",
        "6B.9",
        "7B.9",
    }
    assert all(item["promoted_evidence_ids"] for item in manifest["requests"])
    assert not (target / "question-corrections").exists()
