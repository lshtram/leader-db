import pytest

from leaders_db.research.models import DimensionFilter, QuestionClassification, ScopeFilter
from leaders_db.research.planner import (
    QuestionSpecReviewNeeded,
    question_from_classification,
    validate_question_classification,
)


def test_valid_classification_maps_to_registered_question() -> None:
    classification = QuestionClassification(
        question_key="leader_legal_cases_qualitative",
        concept_keys=("leader_open_criminal_or_corruption_case",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("ISR",), role="entity"),
                DimensionFilter(key="leader", values=("leader-1",), role="entity"),
                DimensionFilter(key="year", values=(2023,), role="time"),
            )
        ),
    )

    spec = validate_question_classification(classification)
    question = question_from_classification(
        question_id="classified-legal-case",
        display_text="Does the ruler have open corruption lawsuits?",
        classification=classification,
    )

    assert spec.question_key == "leader_legal_cases_qualitative"
    assert question.concepts == ("leader_open_criminal_or_corruption_case",)
    assert question.analyses == ("coverage", "human_review_queue")


def test_invalid_classification_is_rejected_before_execution() -> None:
    classification = QuestionClassification(
        question_key="new_unreviewed_question",
        concept_keys=("leader_open_criminal_or_corruption_case",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("ISR",), role="entity"),
                DimensionFilter(key="leader", values=("leader-1",), role="entity"),
                DimensionFilter(key="year", values=(2023,), role="time"),
            )
        ),
    )

    with pytest.raises(QuestionSpecReviewNeeded, match="needs_question_spec_review"):
        validate_question_classification(classification)
