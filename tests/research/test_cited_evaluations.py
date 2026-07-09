from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.cited_evaluations import (
    CITED_EVALUATION_METHOD_VERSION,
    CitedEvaluation,
    CitedEvaluationCitation,
    build_cited_evaluation_template,
    cited_evaluation_json_schema,
    persist_cited_evaluations,
)


def test_persist_cited_evaluation_writes_non_8b_manual_question(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    persist_cited_evaluations(engine, (_evaluation(),))

    with engine.connect() as conn:
        question = conn.execute(text("SELECT * FROM research_questions")).mappings().one()
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()

    assert question["question_id"] == "1B.1"
    assert question["chapter_id"] == "1B"
    assert question["answer_type"] == "evidence_bundle"
    assert question["method_version"] == CITED_EVALUATION_METHOD_VERSION
    assert answer["question_id"] == "1B.1"
    assert answer["year"] == 1967
    assert answer["iso3"] == "TZA"
    assert answer["ruler_name"] == "Julius Nyerere"
    assert answer["answer_text"] == "supported"
    assert answer["coverage_status"] == "manual_cited"
    payload = json.loads(answer["answer_json"])
    assert payload["claims"] == [{"claim": "limited nuclear risk exposure"}]
    assert payload["period_start_year"] == 1967
    assert link["source_slug"] == "manual_web"
    assert link["source_observation_id"] == "https://example.test/source"


def test_persist_cited_evaluation_rejects_structured_question(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    with pytest.raises(ValueError, match="unsupported cited methodology_id"):
        persist_cited_evaluations(engine, (_evaluation(methodology_id="5.1"),))


def test_persist_cited_evaluation_rejects_unregistered_question(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    with pytest.raises(ValueError, match="unsupported cited methodology_id"):
        persist_cited_evaluations(engine, (_evaluation(methodology_id="NOT_REGISTERED"),))


def test_cited_evaluation_requires_manual_review_reason_when_flagged() -> None:
    with pytest.raises(ValueError, match="manual_review_reason"):
        _evaluation(evidence_quality="manual_review_required", manual_review_reason=None)


def test_cited_evaluation_requires_at_least_one_citation() -> None:
    with pytest.raises(ValueError, match="citations"):
        _evaluation(citations=())


def test_cited_evaluation_requires_calibration_when_scored() -> None:
    with pytest.raises(ValueError, match=r"answer_payload\.calibration"):
        _evaluation(answer_payload={})


def test_cited_evaluation_rejects_invalid_calibration_enum() -> None:
    calibration = _calibration() | {"severity_band": "newsworthy"}

    with pytest.raises(ValueError, match="severity_band"):
        _evaluation(answer_payload={"calibration": calibration})


def test_cited_evaluation_accepts_fractional_confidence_score() -> None:
    evaluation = _evaluation(confidence_score=0.94)

    assert evaluation.confidence_score == 94


def test_persist_cited_evaluation_stores_fractional_confidence_as_percent(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    persist_cited_evaluations(engine, (_evaluation(confidence_score=0.72),))

    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()

    assert answer["confidence_score"] == 72


def test_cited_evaluation_schema_exposes_required_research_fields() -> None:
    schema = cited_evaluation_json_schema()

    assert "citations" in schema["required"]
    assert "methodology_id" in schema["required"]
    assert schema["properties"]["citations"]["minItems"] == 1
    citation_schema = schema["$defs"]["CitedEvaluationCitation"]
    for field in (
        "source_confidence",
        "source_confidence_reason",
        "source_type",
        "final_evidence_use",
    ):
        assert field in citation_schema["required"]


def test_build_cited_evaluation_template_returns_valid_record() -> None:
    template = build_cited_evaluation_template(
        methodology_id="1B.1",
        year=1967,
        iso3="tza",
        country_name="Tanzania",
        leader_name="Julius Nyerere",
        period_label="1967-1985",
    )

    record = CitedEvaluation.model_validate(template)
    assert record.methodology_id == "1B.1"
    assert record.iso3 == "TZA"
    assert record.leader_name == "Julius Nyerere"
    assert record.prompt_context
    assert record.answer_payload["calibration"]["rubric_version"] == "1b1_v1"
    assert record.citations[0].url == "https://example.test/source"
    assert record.citations[0].source_confidence == "medium_high"
    assert record.citations[0].source_type == "media"


def test_build_cited_evaluation_template_uses_4b1_question_guide_rubric() -> None:
    template = build_cited_evaluation_template(
        methodology_id="4B.1",
        year=2020,
        iso3="nzl",
        country_name="New Zealand",
        leader_name="Jacinda Ardern",
    )

    record = CitedEvaluation.model_validate(template)
    assert record.methodology_id == "4B.1"
    assert record.iso3 == "NZL"
    assert record.answer_payload["calibration"]["rubric_version"] == (
        "4b1_electoral_contestability_v1"
    )
    assert record.answer_payload["calibration"]["electoral_system_status"] == "unclear"
    assert record.answer_payload["calibration"]["incumbent_acceptance_of_loss"] == "unclear"
    assert record.answer_payload["calibration"]["contestability_constraints"] == ["none_found"]


def test_build_cited_evaluation_template_uses_4b2_question_guide_rubric() -> None:
    template = build_cited_evaluation_template(
        methodology_id="4B.2",
        year=2020,
        iso3="blr",
        country_name="Belarus",
        leader_name="Alexander Lukashenka",
    )

    record = CitedEvaluation.model_validate(template)
    calibration = record.answer_payload["calibration"]
    assert record.methodology_id == "4B.2"
    assert record.iso3 == "BLR"
    assert calibration["rubric_version"] == "4b2_entrenchment_manipulation_v1"
    assert calibration["manipulation_status"] == "unclear"
    assert calibration["entrenchment_channels"] == ["unclear"]
    assert calibration["institutional_remedy_status"] == "unclear"


def test_build_cited_evaluation_template_uses_4b3_question_guide_rubric() -> None:
    template = build_cited_evaluation_template(
        methodology_id="4B.3",
        year=2020,
        iso3="chn",
        country_name="China",
        leader_name="Xi Jinping",
    )

    record = CitedEvaluation.model_validate(template)
    calibration = record.answer_payload["calibration"]
    assert record.methodology_id == "4B.3"
    assert record.iso3 == "CHN"
    assert calibration["rubric_version"] == "4b3_opposition_tolerance_v1"
    assert calibration["tolerance_status"] == "unclear"
    assert calibration["opposition_tolerance_channels"] == ["unclear"]
    assert calibration["remedy_or_accountability_status"] == "unclear"


def test_4b1_scored_evaluation_requires_question_specific_calibration_fields() -> None:
    calibration = _calibration() | {"rubric_version": "4b1_electoral_contestability_v1"}

    with pytest.raises(ValueError, match="electoral_system_status"):
        _evaluation(
            methodology_id="4B.1",
            answer_payload={"calibration": calibration},
        )


def test_4b1_scored_evaluation_rejects_invalid_question_specific_calibration() -> None:
    calibration = _calibration() | {
        "rubric_version": "4b1_electoral_contestability_v1",
        "electoral_system_status": "nominally_ok",
        "incumbent_acceptance_of_loss": "not_tested",
        "contestability_constraints": ["none_found"],
    }
    with pytest.raises(ValueError, match="electoral_system_status"):
        _evaluation(
            methodology_id="4B.1",
            answer_payload={"calibration": calibration},
        )


def test_4b1_scored_evaluation_rejects_invalid_contestability_constraints() -> None:
    calibration = _calibration() | {
        "rubric_version": "4b1_electoral_contestability_v1",
        "electoral_system_status": "free_and_fair",
        "incumbent_acceptance_of_loss": "not_tested",
        "contestability_constraints": ["unknown_constraint"],
    }

    with pytest.raises(ValueError, match="contestability_constraints"):
        _evaluation(
            methodology_id="4B.1",
            answer_payload={"calibration": calibration},
        )


def test_4b2_scored_evaluation_requires_question_specific_calibration_fields() -> None:
    calibration = _calibration() | {"rubric_version": "4b2_entrenchment_manipulation_v1"}

    with pytest.raises(ValueError, match="manipulation_status"):
        _evaluation(
            methodology_id="4B.2",
            answer_payload={"calibration": calibration},
        )


def test_4b2_scored_evaluation_rejects_invalid_entrenchment_channels() -> None:
    calibration = _calibration() | {
        "rubric_version": "4b2_entrenchment_manipulation_v1",
        "manipulation_status": "recurring_advantage",
        "entrenchment_channels": ["mystery_channel"],
        "institutional_remedy_status": "partial",
    }

    with pytest.raises(ValueError, match="entrenchment_channels"):
        _evaluation(
            methodology_id="4B.2",
            answer_payload={"calibration": calibration},
        )


def test_4b3_scored_evaluation_requires_question_specific_calibration_fields() -> None:
    calibration = _calibration() | {"rubric_version": "4b3_opposition_tolerance_v1"}

    with pytest.raises(ValueError, match="tolerance_status"):
        _evaluation(
            methodology_id="4B.3",
            answer_payload={"calibration": calibration},
        )


def test_4b3_scored_evaluation_rejects_invalid_rubric_version() -> None:
    calibration = _calibration() | {
        "rubric_version": "4b2_entrenchment_manipulation_v1",
        "tolerance_status": "mostly_tolerated",
        "opposition_tolerance_channels": ["protest"],
        "remedy_or_accountability_status": "partial",
    }

    with pytest.raises(ValueError, match="4b3_opposition_tolerance_v1"):
        _evaluation(
            methodology_id="4B.3",
            answer_payload={"calibration": calibration},
        )


def test_4b3_scored_evaluation_rejects_invalid_tolerance_channels() -> None:
    calibration = _calibration() | {
        "rubric_version": "4b3_opposition_tolerance_v1",
        "tolerance_status": "mostly_tolerated",
        "opposition_tolerance_channels": ["mystery_channel"],
        "remedy_or_accountability_status": "partial",
    }

    with pytest.raises(ValueError, match="opposition_tolerance_channels"):
        _evaluation(
            methodology_id="4B.3",
            answer_payload={"calibration": calibration},
        )


def test_persist_4b1_score_revalidates_constructed_record_missing_fields(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    payload = _evaluation(
        methodology_id="4B.1",
        answer_payload={
            "calibration": _calibration()
            | {
                "rubric_version": "4b1_electoral_contestability_v1",
                "electoral_system_status": "free_and_fair",
                "incumbent_acceptance_of_loss": "not_tested",
                "contestability_constraints": ["none_found"],
            }
        },
    ).model_dump()
    del payload["answer_payload"]["calibration"]["electoral_system_status"]
    evaluation = CitedEvaluation.model_construct(
        **payload
    )

    with pytest.raises(ValueError, match="electoral_system_status"):
        persist_cited_evaluations(engine, (evaluation,))


def test_persist_4b1_score_preserves_question_specific_calibration_fields(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    payload = {
        "calibration": _calibration()
        | {
            "rubric_version": "4b1_electoral_contestability_v1",
            "electoral_system_status": "free_and_fair",
            "incumbent_acceptance_of_loss": "not_tested",
            "contestability_constraints": ["none_found"],
        }
    }

    persist_cited_evaluations(
        engine,
        (
            _evaluation(
                methodology_id="4B.1",
                answer_payload=payload,
            ),
        ),
    )

    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()

    answer_json = json.loads(answer["answer_json"])
    assert answer["question_id"] == "4B.1"
    assert answer["score_1_to_10"] == 7
    assert answer_json["calibration"]["rubric_version"] == (
        "4b1_electoral_contestability_v1"
    )
    assert answer_json["calibration"]["electoral_system_status"] == "free_and_fair"


def test_build_cited_evaluation_template_rejects_structured_question() -> None:
    with pytest.raises(ValueError, match="unsupported cited methodology_id"):
        build_cited_evaluation_template(
            methodology_id="5.1",
            year=2023,
            iso3="USA",
            country_name="United States",
        )


def _evaluation(
    *,
    methodology_id: str = "1B.1",
    evidence_quality: str = "medium",
    manual_review_reason: str | None = "Needs cross-check.",
    confidence_score: int | float | None = 72,
    answer_payload: dict[str, object] | None = None,
    citations: tuple[CitedEvaluationCitation, ...] = (
        CitedEvaluationCitation(
            url="https://example.test/source",
            source_confidence="medium_high",
            source_confidence_reason="Fixture reputable source.",
            source_type="media",
            final_evidence_use="final_evidence",
        ),
    ),
) -> CitedEvaluation:
    return CitedEvaluation(
        methodology_id=methodology_id,
        year=1967,
        iso3="TZA",
        country_name="Tanzania",
        leader_name="Julius Nyerere",
        leader_resolution="Julius Nyerere / TANU government",
        period_start_year=1967,
        period_end_year=1985,
        period_label="1967-1985",
        prompt_context="Nuclear-risk ruler-quality question.",
        verdict="supported",
        evidence_quality=evidence_quality,
        confidence="medium",
        manual_review_reason=manual_review_reason,
        score_1_to_10=7,
        confidence_score=confidence_score,
        answer_payload=answer_payload
        if answer_payload is not None
        else {"calibration": _calibration()},
        claims=({"claim": "limited nuclear risk exposure"},),
        citations=citations,
        caveats=("Fixture caveat.",),
    )


def _calibration() -> dict[str, object]:
    return {
        "rubric_version": "1b1_nuclear_responsibility_v1",
        "calibration_batch_id": "1b1_1967_test_batch",
        "calibrated_against": ["Tanzania / Julius Nyerere / 1967"],
        "severity_band": "isolated",
        "state_responsibility": "unclear",
        "accountability_level": "partial",
        "information_environment": "partly_restricted",
        "period_fit": "ruler_period",
        "source_mix": ["media"],
        "structured_prior_summary": "not_available",
        "contrary_evidence": [],
        "score_rationale": "Fixture score uses limited cited evidence.",
        "lower_anchor_rejected": "Lower anchor would overstate risk in this fixture.",
        "higher_anchor_rejected": "Higher anchor would overstate confidence in this fixture.",
        "visibility_bias_check": "Fixture does not use article volume as severity.",
        "repression_silence_check": "Fixture records information limits.",
        "population_scale_check": "Fixture distinguishes case evidence from population scale.",
        "source_type_check": "Fixture source mix is narrow.",
        "recency_check": "Fixture uses ruler-period evidence.",
        "subagent_calibration_check": "Fixture has one comparison case only.",
    }
