import json
from pathlib import Path

import pytest
import yaml

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.question_evidence_packets import (
    load_trusted_chapter_question_evidence_package,
)
from leaders_db.research.question_packet_prompts import QuestionPacketPrompts
from leaders_db.research.question_packet_quality import (
    BlindCandidateQuality,
    BlindQuestionQualityReview,
    _blind_labels,
    _experimental_passes,
    _validate_review_conclusion,
    run_blind_question_quality_review,
    validate_blind_review_artifacts,
)
from leaders_db.research.question_packet_writer import DiagnosticQuestionAnswer


def _candidate(label: str, result: str = "pass") -> BlindCandidateQuality:
    return BlindCandidateQuality(
        candidate=label,
        factual_support=result,
        citation_entailment=result,
        material_coverage=result,
        balance_and_limits=result,
        attribution_and_period=result,
        judgeability=result,
        rationale="A sufficiently detailed rationale for deterministic review testing.",
    )


def test_review_conclusion_is_derived_from_deblinded_findings() -> None:
    failed = _candidate("B", "fail").model_copy(
        update={
            "material_regressions": ("Material regression",),
            "unsupported_claims": ("Unsupported claim",),
        }
    )
    review = BlindQuestionQualityReview(
        question_id="8B.9",
        candidates=(_candidate("A"), failed),
        preferred_candidate="A",
        overall_rationale="A sufficiently detailed overall rationale for the comparison.",
    )

    assert not _experimental_passes(review, {"A": "approved", "B": "experimental"})


def test_review_conclusion_accepts_clean_experimental_preference() -> None:
    review = BlindQuestionQualityReview(
        question_id="8B.9",
        candidates=(_candidate("A"), _candidate("B")),
        preferred_candidate="B",
        overall_rationale="A sufficiently detailed overall rationale for the comparison.",
    )

    _validate_review_conclusion(review, {"A": "approved", "B": "experimental"})
    assert _experimental_passes(review, {"A": "approved", "B": "experimental"})


def test_clean_experimental_answer_passes_when_baseline_is_preferred() -> None:
    review = BlindQuestionQualityReview(
        question_id="8B.9",
        candidates=(_candidate("A"), _candidate("B")),
        preferred_candidate="A",
        overall_rationale="The baseline is narrowly more useful to a skeptical judge.",
    )

    assert _experimental_passes(review, {"A": "approved", "B": "experimental"})


def test_explicit_material_regression_fails_despite_passing_dimensions() -> None:
    experimental = _candidate("B").model_copy(
        update={
            "material_regressions": (
                "The answer reverses the population comparison and changes the judgment.",
            )
        }
    )
    review = BlindQuestionQualityReview(
        question_id="8B.9",
        candidates=(_candidate("A"), experimental),
        preferred_candidate="B",
        overall_rationale="The experimental answer is better despite a bounded imperfection.",
    )

    assert not _experimental_passes(review, {"A": "approved", "B": "experimental"})


def test_prompt_config_rejects_missing_evidence_placeholder() -> None:
    root = Path.cwd()
    payload = yaml.safe_load((root / "configs/question-packet-prompts.yaml").read_text())
    payload["writer_template"] = payload["writer_template"].replace(
        "{exact_evidence}", "evidence omitted"
    )

    with pytest.raises(ValueError, match="required placeholder"):
        QuestionPacketPrompts.model_validate(payload)


def test_trusted_review_reload_rejects_gate_tampering(monkeypatch, tmp_path: Path) -> None:
    root = Path.cwd()
    corpus = root / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR"
    package = load_trusted_chapter_question_evidence_package(
        project_root=root,
        package_path=(
            root
            / "research/runs/netanyahu-2023-cost-opt-step03-question-packets-v1/8B"
            / "question-evidence-package.json"
        ),
        judge_package_path=corpus / "corpus-judge-package.json",
        selection_manifest_path=corpus / "selected-chapter-manifest.json",
    )
    packet = next(item for item in package.packets if item.question_id == "8B.9")
    analysis = json.loads(
        (corpus / "chapter-remediation/8B/resolved-chapter-analysis.json").read_text()
    )
    approved = next(item for item in analysis["answers"] if item["question_id"] == "8B.9")
    run = root / "research/runs/netanyahu-2023-cost-opt-step03-question-writer-v1/8B.9"
    experimental_payload = json.loads((run / "luna-writer-v4/output.json").read_text())
    experimental_payload.pop("reopen_candidate_ids", None)
    experimental_payload.pop("reopen_reasons", None)
    experimental_payload.pop("supporting_evidence_ids", None)
    experimental_payload.pop("contrary_or_qualifying_evidence_ids", None)
    experimental_payload["reopen_requests"] = []
    experimental_payload["answer"] += "\n\nEvidence: " + " ".join(
        f"[{evidence_id}]" for evidence_id in packet.coverage.required_evidence_ids
    )
    experimental = DiagnosticQuestionAnswer.model_validate(experimental_payload)
    labels = _blind_labels(packet.question_id)
    experimental_label = next(
        label for label, source_name in labels.items() if source_name == "experimental"
    )
    review = BlindQuestionQualityReview(
        question_id=packet.question_id,
        candidates=(_candidate("A"), _candidate("B")),
        preferred_candidate=experimental_label,
        overall_rationale="A sufficiently detailed overall rationale for the comparison.",
    )

    def fake_execute(project_root, profile, prompt, schema, output_dir, **kwargs):
        assert kwargs["reasoning_effort"] == "high"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "output.json").write_text(review.model_dump_json())
        (output_dir / "prompt.txt").write_text(prompt)
        strict_schema = BlindQuestionQualityReview.model_json_schema()
        make_strict_response_schema(strict_schema)
        (output_dir / "schema.json").write_text(json.dumps(strict_schema, indent=2))
        return review

    monkeypatch.setattr(
        "leaders_db.research.question_packet_quality.execute_json_model", fake_execute
    )
    run_blind_question_quality_review(
        project_root=root,
        packet=packet,
        approved_answer=approved,
        experimental_answer=experimental,
        output_dir=tmp_path,
        profile_name="openai-sol-supervisor",
        profiles_path=root / "configs/research-models.yaml",
        reasoning_effort="high",
    )
    manifest_path = tmp_path / "blind-review-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["reasoning_effort"] == "high"
    arguments = {
        "packet": packet,
        "approved_answer": approved,
        "experimental_answer": experimental,
        "output_dir": tmp_path,
        "project_root": root,
        "profile_name": "openai-sol-supervisor",
        "profiles_path": root / "configs/research-models.yaml",
        "reasoning_effort": "high",
    }
    assert validate_blind_review_artifacts(**arguments)["quality_gate"] == "pass"

    schema_path = tmp_path / "schema.json"
    strict_schema = schema_path.read_text()
    schema_path.write_text(json.dumps(BlindQuestionQualityReview.model_json_schema(), indent=2))
    with pytest.raises(ValueError, match="schema differs"):
        validate_blind_review_artifacts(**arguments)
    schema_path.write_text(strict_schema)

    manifest["quality_gate"] = "fail"
    (tmp_path / "blind-review-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="do not match"):
        validate_blind_review_artifacts(**arguments)

    (tmp_path / "blind-review-manifest.json").write_text(
        json.dumps({**manifest, "quality_gate": "pass"})
    )
    (tmp_path / "prompt.txt").write_text("tampered prompt")
    with pytest.raises(ValueError, match="saved blind-review prompt"):
        validate_blind_review_artifacts(**arguments)
