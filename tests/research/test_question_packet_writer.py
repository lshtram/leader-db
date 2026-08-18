import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.chapter_analysis_models import CorrectedLensAnswer
from leaders_db.research.question_evidence_packet_models import (
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
)
from leaders_db.research.question_packet_prompts import (
    load_question_packet_prompts,
    load_versioned_question_packet_prompts,
)
from leaders_db.research.question_packet_writer import (
    AnswerEvidenceDisposition,
    DiagnosticQuestionAnswer,
    EvidenceReopenRequest,
    _canonical_question_answer,
    _question_answer_response_model,
    build_question_writer_prompt,
    load_normalized_question_answer,
    normalize_optional_reopen_requests,
    validate_question_answer,
)
from leaders_db.research.question_packet_writer_prompt import project_predecessor_answer
from tests.research.test_corpus_mapping_review import _evidence


def test_transport_schema_requires_every_evidence_id_as_an_exact_key() -> None:
    required = ("BATCH-1", "SRC:42")
    response_model = _question_answer_response_model(required)
    schema = response_model.model_json_schema()
    make_strict_response_schema(schema)
    ledger = schema["$defs"][next(key for key in schema["$defs"] if key.startswith("Required"))]

    assert ledger["required"] == ["BATCH-1", "SRC:42"]
    assert ledger["additionalProperties"] is False
    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                "question_id": "2B.3",
                "answer": "A sufficiently detailed answer cites evidence [BATCH-1].",
                "evidence_dispositions": {
                    "BATCH-1": {
                        "role": "supporting",
                        "material_point": "This record materially supports the conclusion.",
                    }
                },
            }
        )
    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                "question_id": "2B.3",
                "answer": "A sufficiently detailed answer cites all evidence.",
                "evidence_dispositions": {
                    "item_0001": {
                        "role": "supporting",
                        "material_point": "This record materially supports the conclusion.",
                    },
                    "item_0002": {
                        "role": "contrary_or_qualifying",
                        "material_point": "This record materially qualifies the conclusion.",
                    },
                },
            }
        )


def test_keyed_transport_ledger_converts_to_canonical_ordered_answer() -> None:
    required = ("BATCH-1", "SRC:42")
    response_model = _question_answer_response_model(required)
    response = response_model.model_validate(
        {
            "question_id": "2B.3",
            "answer": "A sufficiently detailed answer [BATCH-1; SRC:42].",
            "evidence_dispositions": {
                "SRC:42": {
                    "role": "contrary_or_qualifying",
                    "material_point": "This record materially qualifies the conclusion.",
                },
                "BATCH-1": {
                    "role": "supporting",
                    "material_point": "This record materially supports the conclusion.",
                },
            },
        }
    )

    answer = _canonical_question_answer(response, required)

    assert tuple(item.evidence_id for item in answer.evidence_dispositions) == required


def test_grouped_required_inline_citations_pass() -> None:
    evidence = tuple(
        _evidence(evidence_id, "Exact fact").model_copy(update={"question_ids": ("8B.9",)})
        for evidence_id in ("E-1", "SRC:42")
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
        question_id="8B.9",
        question="Did responses advance objectives?",
        priority_evidence=evidence,
        candidate_index=candidates,
        direct_evidence_count=2,
        favorable_evidence_ids=(),
        adverse_evidence_ids=(),
        mixed_or_context_evidence_ids=("E-1", "SRC:42"),
        coverage=QuestionCoverageChecklist(
            question_id="8B.9",
            items=tuple(
                EvidenceCoverageItem(
                    evidence_id=item.evidence_id,
                    requirement="must_address",
                    carries_attribution=True,
                    carries_period_fit=True,
                    carries_limitations=False,
                )
                for item in evidence
            ),
            required_evidence_ids=("E-1", "SRC:42"),
            reopenable_evidence_ids=(),
            favorable_available=False,
            adverse_available=False,
            mixed_or_context_available=True,
        ),
    )
    answer = DiagnosticQuestionAnswer(
        question_id="8B.9",
        answer="A sufficiently detailed answer with grouped evidence [E-1; SRC:42].",
        evidence_dispositions=tuple(
            AnswerEvidenceDisposition(
                evidence_id=item.evidence_id,
                role="supporting",
                material_point="The exact record supports the conclusion.",
            )
            for item in evidence
        ),
    )

    result = validate_question_answer(packet, answer)
    assert result["missing_inline_citation_ids"] == []
    assert result["unknown_inline_citation_ids"] == []
    assert result["functional_gate"] == "pass"


def test_writer_validation_requires_every_exact_id_and_no_compact_citation(
    tmp_path: Path,
) -> None:
    exact = _evidence("E-1", "Exact fact").model_copy(update={"question_ids": ("8B.9",)})
    candidate = CompactEvidenceCandidate(
        evidence_id="E-2",
        fact_summary="Candidate fact",
        publisher="Publisher",
        polarity="mixed",
        period_fit="Direct",
        ruler_attribution="Institutional",
        limitations=(),
        question_ids=("8B.9",),
    )
    packet = QuestionEvidencePacket(
        question_id="8B.9",
        question="Did responses advance objectives?",
        priority_evidence=(exact,),
        candidate_index=(
            CompactEvidenceCandidate(
                evidence_id="E-1",
                fact_summary=exact.fact_summary,
                publisher=exact.publisher,
                polarity=exact.polarity,
                period_fit=exact.period_fit,
                ruler_attribution=exact.ruler_attribution,
                limitations=exact.limitations,
                question_ids=exact.question_ids,
            ),
            candidate,
        ),
        direct_evidence_count=2,
        favorable_evidence_ids=(),
        adverse_evidence_ids=(),
        mixed_or_context_evidence_ids=("E-1", "E-2"),
        coverage=QuestionCoverageChecklist(
            question_id="8B.9",
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
    valid = DiagnosticQuestionAnswer(
        question_id="8B.9",
        answer="A sufficiently detailed answer grounded in the exact evidence [E-1].",
        reopen_requests=(
            EvidenceReopenRequest(
                evidence_id="E-2",
                reason="The compact candidate may materially change the conclusion.",
            ),
        ),
        evidence_dispositions=(
            AnswerEvidenceDisposition(
                evidence_id="E-1",
                role="supporting",
                material_point="The exact record directly supports the stated conclusion.",
            ),
        ),
    )

    assert validate_question_answer(packet, valid)["functional_gate"] == "pass"
    invalid = valid.model_copy(
        update={
            "evidence_dispositions": (
                AnswerEvidenceDisposition(
                    evidence_id="E-2",
                    role="supporting",
                    material_point="The compact record cannot support the final answer.",
                ),
            )
        }
    )
    result = validate_question_answer(packet, invalid)
    assert result["functional_gate"] == "fail"
    assert result["missing_required_evidence_ids"] == ["E-1"]
    assert result["unknown_citation_ids"] == ["E-2"]

    missing_inline = valid.model_copy(
        update={"answer": "A sufficiently detailed answer without an inline evidence ID."}
    )
    inline_result = validate_question_answer(packet, missing_inline)
    assert inline_result["functional_gate"] == "pass"
    assert inline_result["missing_inline_citation_ids"] == ["E-1"]

    unknown_inline = valid.model_copy(
        update={"answer": valid.answer + " Compact-only claims [E-2; CANDIDATE-42; SRC:42]."}
    )
    unknown_inline_result = validate_question_answer(packet, unknown_inline)
    assert unknown_inline_result["functional_gate"] == "fail"
    assert unknown_inline_result["unknown_inline_citation_ids"] == [
        "CANDIDATE-42",
        "E-2",
        "SRC:42",
    ]

    bad_reopen = valid.model_copy(
        update={"reopen_requests": valid.reopen_requests + valid.reopen_requests}
    )
    reopen_result = validate_question_answer(packet, bad_reopen)
    assert reopen_result["functional_gate"] == "fail"
    assert reopen_result["duplicate_reopen_request_ids"] == ["E-2"]

    with pytest.raises(ValueError, match="non-space"):
        EvidenceReopenRequest(evidence_id="E-2", reason=" " * 20)
    with pytest.raises(ValueError, match="non-space"):
        EvidenceReopenRequest(evidence_id="E-2", reason="   too short   ")

    unknown_reopen = valid.model_copy(
        update={
            "reopen_requests": (
                EvidenceReopenRequest(
                    evidence_id="E-UNKNOWN",
                    reason="This advisory request is outside the candidate index.",
                ),
            )
        }
    )
    normalized, ledger = normalize_optional_reopen_requests(packet, unknown_reopen)
    assert normalized.reopen_requests == ()
    assert normalized.answer == unknown_reopen.answer
    assert normalized.evidence_dispositions == unknown_reopen.evidence_dispositions
    assert ledger["rejected_reopen_ids"] == ["E-UNKNOWN"]
    assert ledger["mandatory_evidence_dispositions_changed"] is False
    _assert_normalized_roundtrip(tmp_path, packet, unknown_reopen, normalized, ledger)

    prompts, _ = load_question_packet_prompts(Path.cwd() / "configs/question-packet-prompts.yaml")
    prompt = build_question_writer_prompt(packet, prompts, {"question_id": "8B.9"})
    compact_section = prompt.split("COMPACT CANDIDATE INDEX:", 1)[1]
    assert '"evidence_id": "E-2"' in compact_section
    assert '"evidence_id": "E-1"' not in compact_section

    contaminated = {
        "question_id": "8B.9",
        "answer": "A prior claim used evidence unavailable now [BATCH-9999-E999].",
        "supporting_evidence_ids": ["E-1", "BATCH-9999-E999"],
        "contrary_or_qualifying_evidence_ids": [],
    }
    current_prompt = build_question_writer_prompt(packet, prompts, contaminated)
    predecessor_section = current_prompt.split("APPROVED PREDECESSOR ANSWER:", 1)[1].split(
        "REQUIRED EXACT EVIDENCE:", 1
    )[0]
    assert predecessor_section.strip() == "{}"

    legacy_prompts, _ = load_versioned_question_packet_prompts(Path.cwd(), 11)
    legacy_prompt = build_question_writer_prompt(packet, legacy_prompts, contaminated)
    legacy_predecessor = legacy_prompt.split("APPROVED PREDECESSOR ANSWER:", 1)[1].split(
        "REQUIRED EXACT EVIDENCE:", 1
    )[0]
    assert "BATCH-9999-E999" in legacy_predecessor

    with pytest.raises(ValueError, match="version is invalid"):
        load_versioned_question_packet_prompts(Path.cwd(), True)


@pytest.mark.parametrize(
    "field",
    ("limitations_and_gaps", "corrections_made", "reasons_to_reopen_full_ledger"),
)
def test_predecessor_projection_checks_every_auxiliary_text_field(field: str) -> None:
    predecessor = CorrectedLensAnswer(
        question_id="8B.9",
        answer="A sufficiently detailed predecessor grounded in exact evidence [E-1].",
        supporting_evidence_ids=("E-1",),
        contrary_or_qualifying_evidence_ids=(),
    ).model_copy(
        update={field: ("This note refers to unavailable BATCH-9999-E999 evidence.",)}
    )
    packet = SimpleNamespace(
        coverage=SimpleNamespace(required_evidence_ids=("E-1",))
    )

    projected, excluded = project_predecessor_answer(
        packet, predecessor.model_dump(mode="json")
    )

    assert projected == {}
    assert excluded == ("BATCH-9999-E999",)


def _assert_normalized_roundtrip(
    tmp_path: Path,
    packet: QuestionEvidencePacket,
    unknown_reopen: DiagnosticQuestionAnswer,
    normalized: DiagnosticQuestionAnswer,
    ledger: dict[str, object],
) -> None:
    raw_path = tmp_path / "output.json"
    accepted_path = tmp_path / "accepted-output.json"
    response_model = _question_answer_response_model(("E-1",))
    keyed_raw = response_model.model_validate(
        {
            "question_id": unknown_reopen.question_id,
            "answer": unknown_reopen.answer,
            "limitations_and_gaps": unknown_reopen.limitations_and_gaps,
            "reopen_requests": [
                item.model_dump(mode="json") for item in unknown_reopen.reopen_requests
            ],
            "evidence_dispositions": {
                "E-1": {
                    "role": "supporting",
                    "material_point": ("The exact record directly supports the stated conclusion."),
                }
            },
        }
    )
    raw_path.write_text(keyed_raw.model_dump_json(by_alias=True), encoding="utf-8")
    accepted_path.write_text(normalized.model_dump_json(), encoding="utf-8")
    ledger["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
    ledger["accepted_output_sha256"] = sha256(accepted_path.read_bytes()).hexdigest()
    (tmp_path / "normalization-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert load_normalized_question_answer(packet, tmp_path) == normalized

    raw_path.write_text(unknown_reopen.model_dump_json(), encoding="utf-8")
    ledger["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
    (tmp_path / "normalization-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert load_normalized_question_answer(packet, tmp_path) == normalized

    accepted_path.write_text(
        normalized.model_copy(update={"answer": normalized.answer + " tampered"}).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="immutable raw output"):
        load_normalized_question_answer(packet, tmp_path)
