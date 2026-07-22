import pytest

from leaders_db.conversational_evidence.hybrid_experiment.review_models import (
    validate_review,
)


def _review() -> dict[str, object]:
    return {
        "overall_decision": "pass",
        "chapters": [
            {
                "chapter_id": f"{number}B",
                "decision": "pass",
                "remove_or_contextualize": [],
                "material_gaps": [],
                "reason": "The evidence can fairly present this chapter.",
            }
            for number in range(1, 9)
        ],
    }


def test_review_requires_all_chapters_in_order() -> None:
    value = _review()
    value["chapters"][0]["chapter_id"] = "2B"

    with pytest.raises(ValueError, match="Chapters 1B-8B"):
        validate_review(value)


def test_final_review_cannot_request_more_research() -> None:
    value = _review()
    value["chapters"][0]["decision"] = "targeted_follow_up"

    with pytest.raises(ValueError, match="final review"):
        validate_review(value, final=True)


def test_review_normalizes_valid_contract() -> None:
    value = validate_review(_review())

    assert value["overall_decision"] == "pass"
    assert len(value["chapters"]) == 8


def test_review_derives_overall_decision_from_chapters() -> None:
    value = _review()
    value["overall_decision"] = "manual_review"
    value["chapters"][0]["decision"] = "targeted_follow_up"
    value["chapters"][0]["material_gaps"] = [
        {
            "gap": "Missing direct evidence",
            "lenses": ["1B.1"],
            "best_source_or_query_direction": "Official archive",
            "why_it_matters": "It could change confidence",
        }
    ]

    normalized = validate_review(value)

    assert normalized["overall_decision"] == "targeted_follow_up"
