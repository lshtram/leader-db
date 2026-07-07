from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.effectiveness_8b import (
    EFFECTIVENESS_8B_METHOD_VERSION,
    Effectiveness8BEvaluation,
    EffectivenessCitation,
    persist_effectiveness_8b_evaluations,
)


def test_persist_effectiveness_8b_evaluation_writes_generic_answer_tables(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    persist_effectiveness_8b_evaluations(engine, (_evaluation(),))

    with engine.connect() as conn:
        question = conn.execute(text("SELECT * FROM research_questions")).mappings().one()
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        links = (
            conn.execute(
                text("SELECT * FROM research_answer_evidence_links ORDER BY source_observation_id")
            )
            .mappings()
            .all()
        )

    assert question["question_id"] == "8B.3"
    assert question["chapter_id"] == "8B"
    assert question["answer_type"] == "evidence_bundle"
    assert question["category_key"] == "effectiveness"
    assert question["method_version"] == EFFECTIVENESS_8B_METHOD_VERSION
    assert answer["question_id"] == "8B.3"
    assert answer["year"] == 1967
    assert answer["iso3"] == "TZA"
    assert answer["ruler_name"] == "Julius Nyerere"
    assert answer["answer_text"] == "partially_supported"
    assert answer["score_1_to_10"] == 6
    assert answer["confidence_score"] == 70
    assert answer["coverage_status"] == "manual_cited"
    payload = json.loads(answer["answer_json"])
    assert payload["leader_resolution"] == "Julius Nyerere / TANU government"
    assert payload["confidence"] == "medium"
    assert payload["goal_coverage"] == [{"goal": "ujamaa villages", "score_1_10": 5}]
    assert [link["source_slug"] for link in links] == ["manual_web", "manual_web"]
    assert [link["evidence_role"] for link in links] == ["citation", "citation"]


def test_persist_effectiveness_8b_evaluation_rerun_refreshes_links(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    persist_effectiveness_8b_evaluations(engine, (_evaluation(),))
    persist_effectiveness_8b_evaluations(
        engine,
        (
            _evaluation(
                verdict="supported",
                citations=(EffectivenessCitation(url="https://example.test/new-source"),),
            ),
        ),
    )

    with engine.connect() as conn:
        answer_count = conn.execute(
            text("SELECT COUNT(*) FROM research_question_answers")
        ).scalar_one()
        link_rows = (
            conn.execute(text("SELECT source_observation_id FROM research_answer_evidence_links"))
            .scalars()
            .all()
        )
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()

    assert answer_count == 1
    assert link_rows == ["https://example.test/new-source"]
    assert answer["answer_text"] == "supported"


def test_persist_effectiveness_8b_evaluation_rejects_unregistered_question(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    with pytest.raises(ValueError, match="unsupported 8B methodology_id"):
        persist_effectiveness_8b_evaluations(
            engine,
            (_evaluation(methodology_id="7B.1"),),
        )


def test_effectiveness_8b_requires_manual_review_reason_when_flagged() -> None:
    with pytest.raises(ValueError, match="manual_review_reason"):
        _evaluation(evidence_quality="manual_review_required", manual_review_reason=None)


def test_effectiveness_8b_requires_at_least_one_citation() -> None:
    with pytest.raises(ValueError, match="citations"):
        _evaluation(citations=())


def test_effectiveness_8b_requires_calibration_when_scored() -> None:
    with pytest.raises(ValueError, match=r"answer_payload\.calibration"):
        _evaluation(calibration={})


def test_effectiveness_8b_accepts_fractional_confidence_score() -> None:
    evaluation = _evaluation(confidence_score=0.7)

    assert evaluation.confidence_score == 70


def _evaluation(
    *,
    methodology_id: str = "8B.3",
    verdict: str = "partially_supported",
    evidence_quality: str = "medium",
    manual_review_reason: str | None = "Outcome side effects require review.",
    confidence_score: int | float | None = 70,
    calibration: dict[str, object] | None = None,
    citations: tuple[EffectivenessCitation, ...] = (
        EffectivenessCitation(url="https://example.test/program", title="Program source"),
        EffectivenessCitation(url="https://example.test/implementation", title="Implementation"),
    ),
) -> Effectiveness8BEvaluation:
    return Effectiveness8BEvaluation(
        methodology_id=methodology_id,
        year=1967,
        iso3="TZA",
        country_name="Tanzania",
        leader_name="Julius Nyerere",
        leader_resolution="Julius Nyerere / TANU government",
        program_source="Arusha Declaration and TANU program sources",
        implementation_or_outcome_window="1967-1975",
        verdict=verdict,
        evidence_quality=evidence_quality,
        confidence="medium",
        manual_review_reason=manual_review_reason,
        score_1_to_10=6,
        confidence_score=confidence_score,
        goal_coverage=({"goal": "ujamaa villages", "score_1_10": 5},),
        calibration=calibration if calibration is not None else _calibration(),
        candidate_structured_observation={"support_status": verdict},
        citations=citations,
        caveats=("Broad mobilization question; not a binary promise-delivery claim.",),
    )


def _calibration() -> dict[str, object]:
    return {
        "rubric_version": "8b_effectiveness_v1",
        "calibration_batch_id": "8b_1967_test_batch",
        "calibrated_against": ["Tanzania / Julius Nyerere / 1967"],
        "severity_band": "recurring",
        "state_responsibility": "direct",
        "accountability_level": "partial",
        "information_environment": "partly_restricted",
        "period_fit": "ruler_period",
        "source_mix": ["academic", "official"],
        "structured_prior_summary": "not_available",
        "contrary_evidence": [],
        "score_rationale": "Fixture score reflects mixed program delivery.",
        "lower_anchor_rejected": "Lower anchor would overstate policy failure.",
        "higher_anchor_rejected": "Higher anchor would understate side effects.",
        "visibility_bias_check": "Fixture does not use source volume as severity.",
        "repression_silence_check": "Fixture records information limits.",
        "population_scale_check": "Fixture separates national program scope from harm scale.",
        "source_type_check": "Fixture includes official and secondary sources.",
        "recency_check": "Fixture uses ruler-period evidence.",
        "subagent_calibration_check": "Fixture has one comparison case only.",
    }
