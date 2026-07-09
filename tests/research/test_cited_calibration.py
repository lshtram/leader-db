from __future__ import annotations

import pytest

from leaders_db.research.cited_evaluations import CitedEvaluation, CitedEvaluationCitation


def test_4b1_scored_evaluation_rejects_wrong_rubric_version() -> None:
    calibration = _calibration_4b1() | {"rubric_version": "wrong_4b1_v1"}

    with pytest.raises(ValueError, match="rubric_version"):
        _evaluation(methodology_id="4B.1", answer_payload={"calibration": calibration})


def test_4b1_scored_evaluation_accepts_expected_rubric_version() -> None:
    evaluation = _evaluation(
        methodology_id="4B.1",
        answer_payload={"calibration": _calibration_4b1()},
    )

    assert evaluation.answer_payload["calibration"]["rubric_version"] == (
        "4b1_electoral_contestability_v1"
    )


def test_4b2_scored_evaluation_rejects_wrong_rubric_version() -> None:
    calibration = _calibration_4b2() | {"rubric_version": "4b1_electoral_contestability_v1"}

    with pytest.raises(ValueError, match="rubric_version"):
        _evaluation(methodology_id="4B.2", answer_payload={"calibration": calibration})


def test_4b2_scored_evaluation_accepts_expected_rubric_version() -> None:
    evaluation = _evaluation(
        methodology_id="4B.2",
        answer_payload={"calibration": _calibration_4b2()},
    )

    assert evaluation.answer_payload["calibration"]["rubric_version"] == (
        "4b2_entrenchment_manipulation_v1"
    )


def _evaluation(
    *,
    methodology_id: str,
    answer_payload: dict[str, object],
) -> CitedEvaluation:
    return CitedEvaluation(
        methodology_id=methodology_id,
        year=1967,
        iso3="TZA",
        country_name="Tanzania",
        verdict="supported",
        evidence_quality="medium",
        confidence="medium",
        manual_review_reason="Needs cross-check.",
        score_1_to_10=7,
        confidence_score=72,
        answer_payload=answer_payload,
        citations=(
            CitedEvaluationCitation(
                url="https://example.test/source",
                source_confidence="medium_high",
                source_confidence_reason="Fixture reputable source.",
                source_type="media",
                final_evidence_use="final_evidence",
            ),
        ),
    )


def _base_calibration() -> dict[str, object]:
    return {
        "rubric_version": "fixture_v1",
        "calibration_batch_id": "fixture_batch",
        "calibrated_against": ["Tanzania / 1967"],
        "severity_band": "isolated",
        "state_responsibility": "unclear",
        "accountability_level": "partial",
        "information_environment": "partly_restricted",
        "period_fit": "ruler_period",
        "source_mix": ["media"],
        "structured_prior_summary": "not_available",
        "contrary_evidence": [],
        "score_rationale": "Fixture score rationale.",
        "lower_anchor_rejected": "Fixture lower anchor rejection.",
        "higher_anchor_rejected": "Fixture higher anchor rejection.",
        "visibility_bias_check": "Fixture visibility check.",
        "repression_silence_check": "Fixture repression silence check.",
        "population_scale_check": "Fixture population scale check.",
        "source_type_check": "Fixture source type check.",
        "recency_check": "Fixture recency check.",
        "subagent_calibration_check": "Fixture calibration check.",
    }


def _calibration_4b1() -> dict[str, object]:
    return _base_calibration() | {
        "rubric_version": "4b1_electoral_contestability_v1",
        "electoral_system_status": "free_and_fair",
        "incumbent_acceptance_of_loss": "not_tested",
        "contestability_constraints": ["none_found"],
    }


def _calibration_4b2() -> dict[str, object]:
    return _base_calibration() | {
        "rubric_version": "4b2_entrenchment_manipulation_v1",
        "manipulation_status": "recurring_advantage",
        "entrenchment_channels": ["media"],
        "institutional_remedy_status": "partial",
    }
