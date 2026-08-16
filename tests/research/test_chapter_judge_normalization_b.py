from __future__ import annotations

import pytest

from leaders_db.research.chapter_judge_models import RulerChapterJudgment
from leaders_db.research.chapter_judge_worker import (
    _normalize_calibration_references,
    _normalize_confidence_scale,
    _normalize_judgment_envelope,
    _normalize_local_evidence_reference_lists,
)
from tests.research.test_chapter_judge_worker import _evaluation


@pytest.mark.parametrize(
    "malformed",
    (None, "LF001", [None, "LF001", {"local_evidence_id": "LF999"}]),
)
def test_local_reference_normalization_tolerates_malformed_values(
    malformed: object,
) -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["contextual_local_evidence"] = malformed

    _normalize_local_evidence_reference_lists(
        evaluation,
        valid_local_evidence_ids={"LF001"},
    )

    assert evaluation["contextual_local_evidence"] == []
    if malformed is None:
        assert evaluation["manual_review_required"] is False
    else:
        assert evaluation["manual_review_required"] is True
        assert evaluation["manual_review_reason_type"] == "projection_integrity"


def test_null_judgment_requires_full_uncertainty_range() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["score_1_to_10"] = None
    evaluation["insufficient_evidence_reason"] = "No discriminating opportunity."
    evaluation["plausible_score_range"] = {"lower": 4, "upper": 6}

    with pytest.raises(ValueError, match="full 1-10 uncertainty range"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.score_1_to_10 is None


def test_judgment_requires_explicit_bias_safeguards() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    del evaluation["bias_assessment"]["report_volume_not_used_as_severity"]

    with pytest.raises(ValueError, match="report_volume_not_used_as_severity"):
        RulerChapterJudgment.model_validate(evaluation)


def test_normalize_judgment_envelope_repairs_only_explicit_contract_fields() -> None:
    evaluation: dict[str, object] = {
        "score_1_to_10": None,
        "insufficient_evidence_reason": None,
        "plausible_score_range": {"lower": 4, "upper": 6},
        "chapter_rationale": "Only contextual evidence was available.",
    }

    _normalize_judgment_envelope(evaluation)

    assert evaluation["insufficient_evidence_reason"] == (
        "The judge returned no defensible score; see the chapter rationale."
    )
    assert evaluation["plausible_score_range"] == {"lower": 1, "upper": 10}

    scored = {
        "score_1_to_10": 5,
        "insufficient_evidence_reason": None,
        "plausible_score_range": {"lower": 4, "upper": 6},
    }
    _normalize_judgment_envelope(scored)

    assert scored["plausible_score_range"] == {"lower": 4, "upper": 6}

    scored_recoverable = {
        "score_1_to_10": 4,
        "plausible_score_range": {"lower": 3, "upper": 5},
        "insufficient_evidence_reason": None,
        "decisive_positive_evidence": [{"evidence_id": "E001"}],
        "decisive_negative_evidence": [{"evidence_id": "E002"}],
        "manual_review_required": True,
        "manual_review_reason_type": "recoverable_null",
        "manual_review_reason": "More decisive evidence could materially move the score.",
    }
    expected = scored_recoverable | {"manual_review_reason_type": "decisive_source"}
    _normalize_judgment_envelope(scored_recoverable)

    assert scored_recoverable == expected

    unreviewed_scored = {
        "score_1_to_10": 4,
        "manual_review_required": False,
        "manual_review_reason_type": "recoverable_null",
    }
    _normalize_judgment_envelope(unreviewed_scored)

    assert unreviewed_scored["manual_review_reason_type"] == "recoverable_null"

    missing_score = {"chapter_rationale": "Malformed candidate."}
    _normalize_judgment_envelope(missing_score)

    assert missing_score == {"chapter_rationale": "Malformed candidate."}


def test_normalize_confidence_scale_repairs_only_unambiguous_fraction_batch() -> None:
    evaluations: list[object] = [
        {"confidence_score": 0.72},
        {"confidence_score": 0.4},
        {"confidence_score": 0},
    ]
    candidate: dict[str, object] = {"batch_notes": ["Existing note."]}

    _normalize_confidence_scale(evaluations, candidate=candidate)

    assert [item["confidence_score"] for item in evaluations] == [72.0, 40.0, 0.0]
    assert "0-1 scale to 0-100" in candidate["batch_notes"][-1]

    mixed: list[object] = [{"confidence_score": 0.8}, {"confidence_score": 65}]
    _normalize_confidence_scale(mixed, candidate={})
    assert [item["confidence_score"] for item in mixed] == [0.8, 65]

    all_zero: list[object] = [{"confidence_score": 0}, {"confidence_score": 0}]
    all_zero_candidate: dict[str, object] = {}
    _normalize_confidence_scale(all_zero, candidate=all_zero_candidate)
    assert [item["confidence_score"] for item in all_zero] == [0, 0]
    assert all_zero_candidate == {}


def test_normalize_calibration_references_repairs_only_unique_ruler_year_suffix() -> None:
    available = {
        "dossier:first:2023:USA:15811",
        "dossier:second:2023:MEX:15802",
    }
    evaluation = {
        "calibrated_against": [
            "dossier:stale:2023:USA:15811",
            "dossier:second:2023:MEX:15802",
            "dossier:unknown:2023:XXX:99999",
        ]
    }

    _normalize_calibration_references(
        evaluation,
        available_dossier_keys=available,
    )

    assert evaluation["calibrated_against"] == [
        "dossier:first:2023:USA:15811",
        "dossier:second:2023:MEX:15802",
        "dossier:unknown:2023:XXX:99999",
    ]
