import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.research.chapter_analysis_models import (
    ChapterAnalysisQuality,
    ChapterQualityReviewBinding,
    LensQuality,
    ResolvedChapterAnalysis,
)
from leaders_db.research.question_evidence_packets import (
    ChapterQuestionEvidencePackage,
    build_chapter_question_evidence_package,
    load_trusted_chapter_question_evidence_package,
)
from tests.research.test_corpus_mapping_review import _evidence
from tests.research.test_single_pass_chapter_analysis import _result


def test_question_packets_preserve_exact_records_and_complete_dispositions(
    tmp_path: Path,
) -> None:
    evidence = [_evidence("E-1", "Favorable fact"), _evidence("E-2", "Adverse fact")]
    evidence[0] = evidence[0].model_copy(
        update={"question_ids": ("4B.1",), "polarity": "favorable"}
    )
    evidence[1] = evidence[1].model_copy(
        update={"question_ids": ("4B.2", "8B.1"), "polarity": "adverse"}
    )
    questions = [
        {
            "methodology_id": f"4B.{number}",
            "question": f"Question {number}",
            "evidence_ids": ["E-1"] if number == 1 else ["E-2"] if number == 2 else [],
        }
        for number in range(1, 11)
    ]
    source_path = tmp_path / "judge-package.json"
    source_path.write_text(
        json.dumps(
            {
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "questions": questions,
            }
        )
    )
    selected_path = tmp_path / "selected.json"
    base = _result()
    answers = tuple(
        answer.model_copy(
            update={
                "question_id": f"4B.{number}",
                "supporting_evidence_ids": ("E-1",) if number == 1 else (),
                "contrary_or_qualifying_evidence_ids": (("E-2",) if number in {1, 2} else ()),
            }
        )
        for number, answer in enumerate(base.corrected_answers, start=1)
    )
    analysis = ResolvedChapterAnalysis(
        chapter_id="4B",
        answers=answers,
        evidence=tuple(evidence),
        omitted_candidate_ids=(),
        draft=base.draft.model_copy(update={"chapter_id": "4B"}),
        critique=base.critique.model_copy(update={"chapter_id": "4B"}),
    )
    selected_path.write_text(analysis.model_dump_json())
    review_path = tmp_path / "review.json"
    review = ChapterAnalysisQuality(
        chapter_id="4B",
        lens_quality=tuple(
            LensQuality(
                question_id=f"4B.{number}",
                factual_support_1_to_5=5,
                completeness_1_to_5=5,
                balance_1_to_5=5,
                attribution_and_period_1_to_5=5,
                judge_usefulness_1_to_5=5,
            )
            for number in range(1, 11)
        ),
        overall_verdict="pass",
        strengths=(),
        systemic_problems=(),
        concrete_corrections_required=(),
        safe_for_judge_use=True,
        rationale="The complete analysis is safe for judge use after independent review.",
    )
    review_path.write_text(review.model_dump_json())
    binding_path = tmp_path / "binding.json"
    binding = ChapterQualityReviewBinding(
        contract="independent-full-index-v1",
        chapter_id="4B",
        analysis_sha256=sha256(selected_path.read_bytes()).hexdigest(),
        judge_package_sha256=sha256(source_path.read_bytes()).hexdigest(),
        review_sha256=sha256(review_path.read_bytes()).hexdigest(),
    )
    binding_path.write_text(binding.model_dump_json())
    selection_path = tmp_path / "selected-chapter-manifest.json"
    selection_path.write_text(
        json.dumps(
            {
                "complete_ruler_safe_for_judge_use": True,
                "ruler_name": "Example Ruler",
                "target_year": 2023,
                "quality_review_contract": "independent-full-index-v1",
                "chapters": [
                    {
                        "chapter_id": f"{chapter_number}B",
                        "safe_for_judge_use": True,
                        "analysis_path": selected_path.name,
                        "analysis_sha256": sha256(selected_path.read_bytes()).hexdigest(),
                        "review_path": review_path.name,
                        "review_sha256": sha256(review_path.read_bytes()).hexdigest(),
                        "review_binding_path": binding_path.name,
                        "review_binding_sha256": sha256(binding_path.read_bytes()).hexdigest(),
                    }
                    for chapter_number in range(1, 9)
                ],
            }
        )
    )
    catalogue_path = tmp_path / "src/leaders_db/conversational_evidence/data/questions.json"
    catalogue_path.parent.mkdir(parents=True)
    catalogue_path.write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "id": "4B",
                        "questions": [
                            {"id": f"4B.{number}", "text": f"Canonical {number}"}
                            for number in range(1, 11)
                        ],
                    }
                ]
            }
        )
    )

    result_path = build_chapter_question_evidence_package(
        project_root=tmp_path,
        judge_package_path=source_path,
        selection_manifest_path=selection_path,
        chapter_id="4B",
        output_path=tmp_path / "result.json",
    )
    result = ChapterQuestionEvidencePackage.model_validate_json(result_path.read_text())

    assert len(result.packets) == 10
    assert result.packets[0].priority_evidence[0] == evidence[0]
    assert result.packets[0].source_routed_priority_evidence_ids == ("E-1",)
    assert result.packets[0].selection_added_priority_evidence_ids == ("E-2",)
    assert result.packets[0].candidate_index[0].evidence_id == "E-1"
    assert result.packets[0].favorable_evidence_ids == ("E-1",)
    assert result.packets[1].adverse_evidence_ids == ("E-2",)
    assert result.packets[0].coverage.required_evidence_ids == ("E-1", "E-2")
    assert result.packets[0].coverage.reopenable_evidence_ids == ()
    assert result.packets[0].coverage.favorable_available is True
    assert result.packets[1].coverage.adverse_available is True
    assert result.packets[1].coverage.items[0].carries_attribution is True
    assert result.packets[1].coverage.items[0].carries_period_fit is True
    assert result.chapter_candidate_ids == ("E-1", "E-2")
    assert [item.evidence_id for item in result.complete_ledger_dispositions] == [
        "E-1",
        "E-2",
    ]
    _assert_tamper_resistance(
        result,
        result_path=result_path,
        project_root=tmp_path,
        judge_package_path=source_path,
        selection_manifest_path=selection_path,
    )


def _assert_tamper_resistance(
    result: ChapterQuestionEvidencePackage,
    *,
    result_path: Path,
    project_root: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
) -> None:
    tampered = result.model_dump(mode="json")
    tampered["packets"][0]["coverage"]["question_id"] = "4B.2"
    with pytest.raises(ValidationError, match="identities differ"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["complete_ledger_dispositions"].pop()
    with pytest.raises(ValidationError, match="ledger count"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["packets"][0]["coverage"]["favorable_available"] = False
    with pytest.raises(ValidationError, match="polarity availability"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["packets"][1]["adverse_evidence_ids"] = []
    tampered["packets"][1]["favorable_evidence_ids"] = ["E-2"]
    with pytest.raises(ValidationError, match="polarity partitions"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["packets"][0]["source_routed_priority_evidence_ids"] = []
    with pytest.raises(ValidationError, match="source-routed priority"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["packets"][0]["selection_added_priority_evidence_ids"] = []
    with pytest.raises(ValidationError, match="selection-added priority"):
        ChapterQuestionEvidencePackage.model_validate(tampered)

    trusted = load_trusted_chapter_question_evidence_package(
        project_root=project_root,
        package_path=result_path,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
    )
    assert trusted == result

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["source_package_sha256"] = "0" * 64
    result_path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="provenance hashes"):
        load_trusted_chapter_question_evidence_package(
            project_root=project_root,
            package_path=result_path,
            judge_package_path=judge_package_path,
            selection_manifest_path=selection_manifest_path,
        )

    tampered = deepcopy(result.model_dump(mode="json"))
    tampered["packets"][0]["question"] = "Altered but structurally valid question"
    result_path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="differs from its approved sources"):
        load_trusted_chapter_question_evidence_package(
            project_root=project_root,
            package_path=result_path,
            judge_package_path=judge_package_path,
            selection_manifest_path=selection_manifest_path,
        )
