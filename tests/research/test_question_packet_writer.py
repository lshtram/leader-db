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
                "answer_sections": [
                    {
                        "text": "A sufficiently detailed answer cites the evidence.",
                        "citation_ids": ["BATCH-1"],
                    }
                ],
                "limitation_sections": [],
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
                "answer_sections": [
                    {
                        "text": "A sufficiently detailed answer cites all evidence.",
                        "citation_ids": ["BATCH-1", "SRC:42"],
                    }
                ],
                "limitation_sections": [],
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


def test_post_completion_transport_cannot_request_more_evidence() -> None:
    response_model = _question_answer_response_model(("E-1",), allow_reopen=False)
    schema = response_model.model_json_schema()
    make_strict_response_schema(schema)

    assert "reopen_requests" not in schema["properties"]
    payload = {
        "question_id": "4B.1",
        "answer_sections": [
            {
                "text": "The final answer is grounded in completed exact evidence.",
                "citation_ids": ["E-1"],
            }
        ],
        "limitation_sections": [],
        "evidence_dispositions": {
            "E-1": {
                "role": "supporting",
                "material_point": "The exact record supports the final conclusion.",
            }
        },
    }
    response_model.model_validate(payload)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        response_model.model_validate({**payload, "reopen_requests": []})


def test_evidence_empty_transport_records_uncertainty_without_citations() -> None:
    response_model = _question_answer_response_model((), allow_reopen=False)
    schema = response_model.model_json_schema()
    make_strict_response_schema(schema)
    response = response_model.model_validate(
        {
            "question_id": "7B.3",
            "answer": "The supplied record is insufficient to assess this question.",
            "limitations_and_gaps": (
                "No question-specific evidence was available in the frozen packet.",
            ),
            "evidence_dispositions": {},
        }
    )

    canonical = _canonical_question_answer(response, ())
    assert canonical.evidence_dispositions == ()
    assert canonical.reopen_requests == ()
    with pytest.raises(ValidationError, match="must not contain evidence IDs"):
        response_model.model_validate(
            {
                **response.model_dump(mode="json", by_alias=True),
                "answer": "The empty record BATCH-FAKE proves the conclusion is adverse.",
            }
        )


def test_evidence_empty_v16_transport_trusted_reloads(tmp_path: Path) -> None:
    packet = QuestionEvidencePacket.model_validate(
        {
            "question_id": "7B.3",
            "question": "Synthetic sparse-evidence question",
            "priority_evidence": [],
            "source_routed_priority_evidence_ids": [],
            "selection_added_priority_evidence_ids": [],
            "candidate_index": [],
            "direct_evidence_count": 0,
            "favorable_evidence_ids": [],
            "adverse_evidence_ids": [],
            "mixed_or_context_evidence_ids": [],
            "coverage": {
                "question_id": "7B.3",
                "items": [],
                "required_evidence_ids": [],
                "reopenable_evidence_ids": [],
                "adjudicated_nonmaterial_evidence_ids": [],
                "favorable_available": False,
                "adverse_available": False,
                "mixed_or_context_available": False,
            },
            "evidence_discovery_complete": True,
        }
    )
    response = _question_answer_response_model((), allow_reopen=False).model_validate(
        {
            "question_id": "7B.3",
            "answer": "The supplied record is insufficient to assess this question.",
            "limitations_and_gaps": [
                "No question-specific evidence was available in the frozen packet."
            ],
            "evidence_dispositions": {},
        }
    )
    raw_path = tmp_path / "output.json"
    raw_path.write_text(response.model_dump_json(by_alias=True), encoding="utf-8")
    accepted = _canonical_question_answer(response, ())
    accepted_path = tmp_path / "accepted-output.json"
    accepted_path.write_text(accepted.model_dump_json(), encoding="utf-8")
    (tmp_path / "request-manifest.json").write_text(
        json.dumps({"prompt_config_version": 16}), encoding="utf-8"
    )
    _, ledger = normalize_optional_reopen_requests(packet, accepted)
    ledger["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
    ledger["accepted_output_sha256"] = sha256(accepted_path.read_bytes()).hexdigest()
    (tmp_path / "normalization-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    assert load_normalized_question_answer(packet, tmp_path) == accepted


def test_keyed_transport_ledger_converts_to_canonical_ordered_answer() -> None:
    required = ("BATCH-1", "SRC:42")
    response_model = _question_answer_response_model(required)
    response = response_model.model_validate(
        {
            "question_id": "2B.3",
            "answer_sections": [
                {
                    "text": "A sufficiently detailed answer.",
                    "citation_ids": ["BATCH-1", "SRC:42"],
                }
            ],
            "limitation_sections": [],
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
    assert answer.answer == "A sufficiently detailed answer [BATCH-1; SRC:42]."

    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                "question_id": "2B.3",
                "answer_sections": [
                    {
                        "text": "A section cannot contain manual [FOREIGN] citations.",
                        "citation_ids": ["BATCH-1"],
                    }
                ],
                "limitation_sections": [],
                "evidence_dispositions": response.model_dump(mode="json", by_alias=True)[
                    "evidence_dispositions"
                ],
            }
        )
    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                **response.model_dump(mode="json", by_alias=True),
                "limitation_sections": [
                    {
                        "text": "A limitation cannot contain a manual [FOREIGN] citation.",
                        "citation_ids": ["BATCH-1"],
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                "question_id": "2B.3",
                "answer_sections": [
                    {
                        "text": "A sufficiently detailed answer cites exact evidence.",
                        "citation_ids": ["FOREIGN-1"],
                    }
                ],
                "limitation_sections": [],
                "evidence_dispositions": response.model_dump(mode="json", by_alias=True)[
                    "evidence_dispositions"
                ],
            }
        )
    for field, foreign_text in (
        ("answer", "A foreign prose citation BATCH-9999-E999 supports this claim."),
        ("limitation", "A foreign limitation E-999 would qualify this claim."),
        ("material_point", "A foreign SRC:999 record supposedly supports this claim."),
        ("reopen_reason", "Unavailable BATCH-9999-E999 evidence could change this claim."),
    ):
        payload = response.model_dump(mode="json", by_alias=True)
        if field == "answer":
            payload["answer_sections"][0]["text"] = foreign_text
        elif field == "limitation":
            payload["limitation_sections"] = [{"text": foreign_text, "citation_ids": ["BATCH-1"]}]
        elif field == "material_point":
            payload["evidence_dispositions"]["BATCH-1"]["material_point"] = foreign_text
        else:
            payload["reopen_requests"] = [{"evidence_id": "E-2", "reason": foreign_text}]
        with pytest.raises(ValidationError, match="must not contain evidence IDs"):
            response_model.model_validate(payload)


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
    ).model_copy(update={field: ("This note refers to unavailable BATCH-9999-E999 evidence.",)})
    packet = SimpleNamespace(coverage=SimpleNamespace(required_evidence_ids=("E-1",)))

    projected, excluded = project_predecessor_answer(packet, predecessor.model_dump(mode="json"))

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
    request_path = tmp_path / "request-manifest.json"
    request_path.write_text(json.dumps({"prompt_config_version": 13}), encoding="utf-8")
    keyed_raw = response_model.model_validate(
        {
            "question_id": unknown_reopen.question_id,
            "answer_sections": [
                {
                    "text": "A sufficiently detailed answer grounded in the exact evidence.",
                    "citation_ids": ["E-1"],
                }
            ],
            "limitation_sections": [],
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

    raw_path.write_text(
        json.dumps(
            {
                "question_id": unknown_reopen.question_id,
                "answer": unknown_reopen.answer,
                "limitations_and_gaps": list(unknown_reopen.limitations_and_gaps),
                "reopen_requests": [
                    item.model_dump(mode="json") for item in unknown_reopen.reopen_requests
                ],
                "evidence_dispositions": {
                    "E-1": {
                        "role": "supporting",
                        "material_point": (
                            "The exact record directly supports the stated conclusion."
                        ),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="legacy transport"):
        load_normalized_question_answer(packet, tmp_path)
    request_path.write_text(json.dumps({"prompt_config_version": 12}), encoding="utf-8")
    ledger["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
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
