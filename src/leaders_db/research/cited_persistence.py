"""Persistence mapping for cited manual/internet evaluations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .cited_calibration import validate_score_calibration
from .cited_models import CitedEvaluation
from .registry import get_question_spec_by_methodology_id
from .results_store import (
    ResearchAnswerEvidence,
    ResearchAnswerRow,
    ResearchQuestionMetadata,
    persist_research_answers,
)

CITED_EVALUATION_METHOD_VERSION = "cited_manual_evaluation_v1"
CITED_EVALUATION_SOURCE_SLUG = "manual_web"


def persist_cited_evaluations(
    bind: Engine | Session,
    evaluations: Sequence[CitedEvaluation],
    *,
    method_version: str = CITED_EVALUATION_METHOD_VERSION,
) -> None:
    """Persist already-cited qualitative evaluations into generic answer tables."""

    grouped: dict[str, list[ResearchAnswerRow]] = {}
    questions: dict[str, ResearchQuestionMetadata] = {}
    for evaluation in evaluations:
        validate_score_calibration(
            methodology_id=evaluation.methodology_id,
            score_1_to_10=evaluation.score_1_to_10,
            answer_payload=evaluation.answer_payload,
        )
        spec = get_question_spec_by_methodology_id(evaluation.methodology_id)
        if spec is None or spec.evidence_strategy != "internet_manual":
            raise ValueError(f"unsupported cited methodology_id: {evaluation.methodology_id!r}")
        questions[evaluation.methodology_id] = ResearchQuestionMetadata(
            question_id=evaluation.methodology_id,
            chapter_id=evaluation.methodology_id.split(".", maxsplit=1)[0],
            question_text=spec.text,
            answer_type=spec.answer_type,
            category_key=spec.category,
            method_version=method_version,
        )
        grouped.setdefault(evaluation.methodology_id, []).append(
            _to_answer_row(evaluation, method_version=method_version)
        )

    for methodology_id, rows in grouped.items():
        persist_research_answers(bind, questions[methodology_id], tuple(rows))


def _to_answer_row(
    evaluation: CitedEvaluation,
    *,
    method_version: str,
) -> ResearchAnswerRow:
    return ResearchAnswerRow(
        question_id=evaluation.methodology_id,
        year=evaluation.year,
        iso3=evaluation.iso3.upper(),
        country_name=evaluation.country_name,
        ruler_id=evaluation.leader_id,
        ruler_name=evaluation.leader_name,
        answer_text=evaluation.verdict,
        answer_json={
            "leader_resolution": evaluation.leader_resolution,
            "period_start_year": evaluation.period_start_year,
            "period_end_year": evaluation.period_end_year,
            "period_label": evaluation.period_label,
            "prompt_context": evaluation.prompt_context,
            "verdict": evaluation.verdict,
            "evidence_quality": evaluation.evidence_quality,
            "confidence": evaluation.confidence,
            "manual_review_reason": evaluation.manual_review_reason,
            "claims": list(evaluation.claims),
            "candidate_structured_observation": evaluation.candidate_structured_observation,
            "citations": [citation.model_dump() for citation in evaluation.citations],
        }
        | evaluation.answer_payload,
        score_1_to_10=evaluation.score_1_to_10,
        confidence_score=evaluation.confidence_score,
        coverage_status=_coverage_status(evaluation),
        evidence_year=evaluation.year,
        method_version=method_version,
        warning_codes=_warning_codes(evaluation),
        caveats=evaluation.caveats,
        evidence_links=tuple(
            ResearchAnswerEvidence(
                source_slug=CITED_EVALUATION_SOURCE_SLUG,
                source_observation_id=citation.url,
                evidence_role=citation.evidence_role,
            )
            for citation in evaluation.citations
        ),
    )


def _coverage_status(evaluation: CitedEvaluation) -> str:
    if evaluation.evidence_quality == "manual_review_required":
        return "needs_review"
    if evaluation.verdict == "insufficient_evidence":
        return "insufficient_evidence"
    return "manual_cited"


def _warning_codes(evaluation: CitedEvaluation) -> tuple[str, ...]:
    warnings: list[str] = []
    if evaluation.evidence_quality == "manual_review_required":
        warnings.append("manual_review_required")
    if evaluation.verdict in {"mixed_or_contested", "insufficient_evidence"}:
        warnings.append(evaluation.verdict)
    return tuple(warnings)


__all__ = [
    "CITED_EVALUATION_METHOD_VERSION",
    "CITED_EVALUATION_SOURCE_SLUG",
    "persist_cited_evaluations",
]
