import json
from pathlib import Path

import pytest
import yaml

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.question_evidence_packet_models import (
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
)
from leaders_db.research.question_packet_quality import (
    BlindCandidateQuality,
    BlindQuestionQualityReview,
)
from leaders_db.research.question_packet_writer import (
    AnswerEvidenceDisposition,
    DiagnosticQuestionAnswer,
    EvidenceReopenRequest,
)
from leaders_db.research.question_review_verifier import (
    FocusedQuestionVerification,
    _canonical_verification,
    _contract_version,
    _proposed_blocking_findings,
    _verification_response_model,
    _verifier_prompt,
    run_focused_question_verification,
    validate_focused_question_verification,
)
from tests.research.test_corpus_mapping_review import _evidence


def _case(question_id: str = "1B.2"):
    root = Path.cwd()
    evidence = tuple(
        _evidence(evidence_id, fact).model_copy(update={"question_ids": (question_id,)})
        for evidence_id, fact in (("E-1", "An event occurred in 2023."), ("E-2", "Context."))
    )
    candidates = tuple(
        CompactEvidenceCandidate(
            evidence_id=item.evidence_id,
            fact_summary=item.fact_summary,
            publisher=item.publisher,
            polarity=item.polarity,
            period_fit=item.period_fit,
            ruler_attribution=item.ruler_attribution,
            limitations=item.limitations,
            question_ids=item.question_ids,
        )
        for item in evidence
    )
    packet = QuestionEvidencePacket(
        question_id=question_id,
        question="Did the dated conduct satisfy the governing objective?",
        priority_evidence=(evidence[0],),
        candidate_index=candidates,
        direct_evidence_count=2,
        favorable_evidence_ids=(),
        adverse_evidence_ids=(),
        mixed_or_context_evidence_ids=("E-1", "E-2"),
        coverage=QuestionCoverageChecklist(
            question_id=question_id,
            items=(
                EvidenceCoverageItem(
                    evidence_id="E-1",
                    requirement="must_address",
                    carries_attribution=True,
                    carries_period_fit=True,
                    carries_limitations=False,
                ),
                EvidenceCoverageItem(
                    evidence_id="E-2",
                    requirement="available_for_reopen",
                    carries_attribution=True,
                    carries_period_fit=True,
                    carries_limitations=False,
                ),
            ),
            required_evidence_ids=("E-1",),
            reopenable_evidence_ids=("E-2",),
            favorable_available=False,
            adverse_available=False,
            mixed_or_context_available=True,
        ),
    )
    answer = DiagnosticQuestionAnswer(
        question_id=question_id,
        answer="The event occurred during the stated period and supports the answer [E-1].",
        evidence_dispositions=(
            AnswerEvidenceDisposition(
                evidence_id="E-1",
                role="supporting",
                material_point="The dated event materially supports the answer.",
            ),
        ),
    )
    candidates_review = tuple(
        BlindCandidateQuality(
            candidate=label,
            factual_support="pass",
            citation_entailment="pass",
            material_coverage="pass",
            balance_and_limits="pass",
            attribution_and_period="pass",
            judgeability="pass",
            rationale="The answer is materially adequate for the focused synthetic case.",
        )
        for label in ("A", "B")
    )
    review = BlindQuestionQualityReview(
        question_id=question_id,
        candidates=candidates_review,
        preferred_candidate="tie",
        overall_rationale="Both candidates are materially adequate for this synthetic case.",
    )
    return root, packet, answer, review


def _valid_response(
    packet,
    review,
    *,
    chronology="pass",
    contract_version=2,
    unresolved_reopen_ids=(),
):
    findings = tuple(_proposed_blocking_findings(review, packet.question_id))
    model = _verification_response_model(
        packet,
        findings,
        contract_version=contract_version,
        unresolved_reopen_ids=unresolved_reopen_ids,
    )
    payload = {
        "question_id": packet.question_id,
        "chronology_status": chronology,
        "chronology_finding": (
            "The dated sequence was checked directly against the supplied records."
        ),
        "priority_evidence_checks": {
            evidence_id: {
                "status": "covered",
                "rationale": "The answer covers or properly qualifies this material evidence.",
            }
            for evidence_id in packet.coverage.required_evidence_ids
        },
        "proposed_finding_checks": {
            finding_id: {
                "verdict": "rejected",
                "rationale": (
                    "The supplied answer and evidence do not support this proposed defect."
                ),
            }
            for finding_id in findings
        },
        "additional_omitted_evidence_ids": [],
        "rationale": "The focused checks support the derived final result for this answer.",
    }
    if contract_version == 1:
        payload["final_gate"] = "fail" if chronology != "pass" else "pass"
    return model.model_validate(payload), findings


def test_dynamic_schema_requires_every_priority_id_and_rejects_unknown_omission() -> None:
    _, packet, _, review = _case()
    response, findings = _valid_response(packet, review)
    model = type(response)
    payload = response.model_dump(mode="json", by_alias=True)
    payload["priority_evidence_checks"].pop(packet.coverage.required_evidence_ids[0])
    with pytest.raises(ValueError):
        model.model_validate(payload)
    payload = response.model_dump(mode="json", by_alias=True)
    payload["additional_omitted_evidence_ids"] = ["INVENTED-EVIDENCE"]
    with pytest.raises(ValueError):
        model.model_validate(payload)
    assert _canonical_verification(response, packet, findings).final_gate == "pass"


def test_omission_schema_allows_only_reopenable_ids_and_closes_empty_case() -> None:
    _, packet, _, review = _case()
    response, _ = _valid_response(packet, review)
    model = type(response)
    payload = response.model_dump(mode="json", by_alias=True)
    payload["additional_omitted_evidence_ids"] = [
        packet.coverage.required_evidence_ids[0]
    ]
    with pytest.raises(ValueError):
        model.model_validate(payload)
    if packet.coverage.reopenable_evidence_ids:
        payload["additional_omitted_evidence_ids"] = [
            packet.coverage.reopenable_evidence_ids[0]
        ]
        assert model.model_validate(payload)
    empty_packet = packet.model_copy(
        update={
            "coverage": packet.coverage.model_copy(
                update={"reopenable_evidence_ids": ()}
            )
        }
    )
    empty_model = _verification_response_model(empty_packet, ())
    empty_payload = _valid_response(empty_packet, review)[0].model_dump(
        mode="json", by_alias=True
    )
    empty_payload["additional_omitted_evidence_ids"] = ["INVENTED-EVIDENCE"]
    with pytest.raises(ValueError):
        empty_model.model_validate(empty_payload)


def test_prompt_candidate_index_contains_only_reopenable_ids() -> None:
    root, packet, answer, review = _case()
    findings = _proposed_blocking_findings(review, packet.question_id)
    template = yaml.safe_load(
        (root / "configs/question-review-verifier-prompts.yaml").read_text()
    )["verifier_template"]
    prompt = _verifier_prompt(packet, answer, findings, template)
    candidate_section = prompt.split("COMPACT CANDIDATE INDEX:", maxsplit=1)[1]
    candidate_section = candidate_section.split(
        "PASS-ONE PROPOSED BLOCKING FINDINGS:", maxsplit=1
    )[0]
    assert "E-2" in candidate_section
    assert "E-1" not in candidate_section


def test_derived_gate_rejects_contradictory_chronology_pass() -> None:
    _, packet, _, review = _case()
    response, findings = _valid_response(packet, review, chronology="fail")
    payload = _canonical_verification(response, packet, findings).model_dump()
    assert payload["final_gate"] == "fail"
    payload["final_gate"] = "pass"
    with pytest.raises(ValueError, match="contradicts"):
        FocusedQuestionVerification.model_validate(payload)


def test_run_persists_canonical_verification_and_manifest(monkeypatch, tmp_path: Path) -> None:
    root, packet, answer, review = _case()
    response, _ = _valid_response(packet, review)

    def fake_execute(project_root, profile, prompt, model, output_dir, **kwargs):
        assert kwargs["reasoning_effort"] == "high"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "output.json").write_text(
            response.model_dump_json(by_alias=True), encoding="utf-8"
        )
        (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        schema = model.model_json_schema()
        make_strict_response_schema(schema)
        (output_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
        return response

    monkeypatch.setattr(
        "leaders_db.research.question_review_verifier.execute_json_model", fake_execute
    )
    path = run_focused_question_verification(
        project_root=root,
        packet=packet,
        experimental_answer=answer,
        first_review=review,
        output_dir=tmp_path,
        profile_name="openai-luna-candidate",
        profiles_path=root / "configs/research-models.yaml",
        reasoning_effort="high",
    )

    manifest = json.loads(path.read_text())
    accepted = FocusedQuestionVerification.model_validate_json(
        (tmp_path / "accepted-verification.json").read_text()
    )
    assert manifest["quality_gate"] == accepted.final_gate == "pass"
    assert [item.evidence_id for item in accepted.priority_evidence_checks] == list(
        packet.coverage.required_evidence_ids
    )
    arguments = {
        "project_root": root,
        "packet": packet,
        "experimental_answer": answer,
        "first_review": review,
        "output_dir": tmp_path,
        "profile_name": "openai-luna-candidate",
        "profiles_path": root / "configs/research-models.yaml",
        "reasoning_effort": "high",
    }
    assert validate_focused_question_verification(**arguments) == manifest
    invalid_answer = answer.model_copy(update={"question_id": "changed"})
    with pytest.raises(ValueError, match="valid experimental answer"):
        validate_focused_question_verification(
            **{**arguments, "experimental_answer": invalid_answer}
        )
    mismatched_review = review.model_copy(update={"question_id": "changed"})
    with pytest.raises(ValueError, match="identity differs"):
        validate_focused_question_verification(
            **{**arguments, "first_review": mismatched_review}
        )
    profiles = yaml.safe_load((root / "configs/research-models.yaml").read_text())
    profiles["profiles"]["openai-luna-candidate"]["provider"] = "not-openai"
    wrong_profiles = tmp_path / "wrong-profiles.yaml"
    wrong_profiles.write_text(yaml.safe_dump(profiles), encoding="utf-8")
    with pytest.raises(ValueError, match="requires Luna"):
        validate_focused_question_verification(
            **{**arguments, "profiles_path": wrong_profiles}
        )
    (tmp_path / "accepted-verification.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from raw"):
        validate_focused_question_verification(**arguments)


def test_run_requires_luna_profile(monkeypatch, tmp_path: Path) -> None:
    root, packet, answer, review = _case()
    with pytest.raises(ValueError, match="requires Luna"):
        run_focused_question_verification(
            project_root=root,
            packet=packet,
            experimental_answer=answer,
            first_review=review,
            output_dir=tmp_path,
            profile_name="openai-sol-supervisor",
            profiles_path=root / "configs/research-models.yaml",
            reasoning_effort="high",
        )


def test_run_threads_coordinator_and_publishes_canonical_failure(
    monkeypatch, tmp_path: Path
) -> None:
    root, packet, answer, review = _case()
    response, _ = _valid_response(packet, review)
    response = response.model_copy(update={"question_id": "changed"})

    class Coordinator:
        failures = 0

        def publish_failure(self) -> None:
            self.failures += 1

    coordinator = Coordinator()

    def fake_execute(project_root, profile, prompt, model, output_dir, **kwargs):
        assert kwargs["call_coordinator"] is coordinator
        return response

    monkeypatch.setattr(
        "leaders_db.research.question_review_verifier.execute_json_model", fake_execute
    )
    with pytest.raises(ValueError, match="changed question identity"):
        run_focused_question_verification(
            project_root=root,
            packet=packet,
            experimental_answer=answer,
            first_review=review,
            output_dir=tmp_path,
            profile_name="openai-luna-candidate",
            profiles_path=root / "configs/research-models.yaml",
            reasoning_effort="high",
            call_coordinator=coordinator,
        )
    assert coordinator.failures == 1


def test_reopen_requests_block_deterministically_and_leave_only_new_candidates() -> None:
    root, packet, answer, review = _case()
    answer = answer.model_copy(
        update={
            "reopen_requests": (
                EvidenceReopenRequest(
                    evidence_id="E-2",
                    reason="This candidate may materially change the final interpretation.",
                ),
            )
        }
    )
    unresolved = tuple(item.evidence_id for item in answer.reopen_requests)
    response, findings = _valid_response(
        packet, review, unresolved_reopen_ids=unresolved
    )
    verification = _canonical_verification(
        response,
        packet,
        findings,
        unresolved_reopen_ids=unresolved,
    )
    assert verification.unresolved_reopen_request_ids == ("E-2",)
    assert verification.additional_omitted_evidence_ids == ()
    assert verification.final_gate == "fail"
    payload = response.model_dump(mode="json", by_alias=True)
    payload["additional_omitted_evidence_ids"] = ["E-2"]
    with pytest.raises(ValueError):
        type(response).model_validate(payload)
    template = yaml.safe_load(
        (root / "configs/question-review-verifier-prompts.yaml").read_text()
    )["verifier_template"]
    prompt = _verifier_prompt(packet, answer, findings, template)
    candidate_section = prompt.split("COMPACT CANDIDATE INDEX:", maxsplit=1)[1]
    candidate_section = candidate_section.split(
        "PASS-ONE PROPOSED BLOCKING FINDINGS:", maxsplit=1
    )[0]
    assert "E-2" not in candidate_section


def test_v1_transport_and_canonical_contract_remain_reconstructable() -> None:
    _, packet, answer, review = _case()
    answer = answer.model_copy(
        update={
            "reopen_requests": (
                EvidenceReopenRequest(
                    evidence_id="E-2",
                    reason="This historical request remained advisory in contract version one.",
                ),
            )
        }
    )
    response, findings = _valid_response(packet, review, contract_version=1)
    verification = _canonical_verification(
        response,
        packet,
        findings,
        contract_version=1,
        unresolved_reopen_ids=tuple(item.evidence_id for item in answer.reopen_requests),
    )
    assert verification.unresolved_reopen_request_ids == ()
    assert verification.final_gate == "pass"


@pytest.mark.parametrize("tampered_version", [True, 1.0])
def test_manifest_contract_version_rejects_boolean_and_float(tampered_version) -> None:
    with pytest.raises(ValueError, match="unsupported prompt version"):
        _contract_version({"prompt_config_version": tampered_version})
