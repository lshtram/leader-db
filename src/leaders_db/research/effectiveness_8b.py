"""Persist cited 8B ruler-effectiveness evaluations.

This module does not run web research or score leaders by itself. It accepts an
already-produced, source-backed 8B evaluation record and writes it through the
generic D24-D27 research answer store.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .registry import get_question_spec_by_methodology_id
from .results_store import (
    ResearchAnswerEvidence,
    ResearchAnswerRow,
    ResearchQuestionMetadata,
    persist_research_answers,
)

EFFECTIVENESS_8B_METHOD_VERSION = "8b_cited_evaluation_v1"
EFFECTIVENESS_8B_SOURCE_SLUG = "manual_web"

Verdict = Literal[
    "supported",
    "partially_supported",
    "mixed_or_contested",
    "insufficient_evidence",
    "not_applicable",
]
EvidenceQuality = Literal["high", "medium", "low", "manual_review_required"]
ConfidenceBand = Literal["high", "medium", "low", "manual_review_required"]


class EffectivenessCitation(BaseModel):
    """One cited source supporting an 8B evaluation."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    title: str | None = None
    quote: str | None = None
    evidence_role: str = "citation"


class Effectiveness8BEvaluation(BaseModel):
    """Source-backed output from an 8B manual/internet evaluator."""

    model_config = ConfigDict(extra="forbid")

    methodology_id: str
    year: int
    iso3: str = Field(min_length=3, max_length=3)
    country_name: str = Field(min_length=1)
    leader_name: str = Field(min_length=1)
    leader_id: str | None = None
    leader_resolution: str = Field(min_length=1)
    program_source: str | None = None
    implementation_or_outcome_window: str | None = None
    verdict: Verdict
    evidence_quality: EvidenceQuality
    confidence: ConfidenceBand
    manual_review_reason: str | None = None
    score_1_to_10: int | None = Field(default=None, ge=1, le=10)
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    goal_coverage: tuple[dict[str, Any], ...] = ()
    candidate_structured_observation: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[EffectivenessCitation, ...]
    caveats: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _manual_review_reason_required_when_flagged(self) -> Effectiveness8BEvaluation:
        if self.evidence_quality == "manual_review_required" and not self.manual_review_reason:
            raise ValueError("manual_review_reason is required when manual review is flagged")
        return self


def persist_effectiveness_8b_evaluations(
    bind: Engine | Session,
    evaluations: Sequence[Effectiveness8BEvaluation],
    *,
    method_version: str = EFFECTIVENESS_8B_METHOD_VERSION,
) -> None:
    """Persist already-cited 8B evaluations into generic answer tables."""

    grouped: dict[str, list[ResearchAnswerRow]] = {}
    questions: dict[str, ResearchQuestionMetadata] = {}
    for evaluation in evaluations:
        spec = get_question_spec_by_methodology_id(evaluation.methodology_id)
        if spec is None or not evaluation.methodology_id.startswith("8B."):
            raise ValueError(f"unsupported 8B methodology_id: {evaluation.methodology_id!r}")
        questions[evaluation.methodology_id] = ResearchQuestionMetadata(
            question_id=evaluation.methodology_id,
            chapter_id="8B",
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
    evaluation: Effectiveness8BEvaluation,
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
            "program_source": evaluation.program_source,
            "implementation_or_outcome_window": evaluation.implementation_or_outcome_window,
            "verdict": evaluation.verdict,
            "evidence_quality": evaluation.evidence_quality,
            "confidence": evaluation.confidence,
            "manual_review_reason": evaluation.manual_review_reason,
            "goal_coverage": list(evaluation.goal_coverage),
            "candidate_structured_observation": evaluation.candidate_structured_observation,
            "citations": [citation.model_dump() for citation in evaluation.citations],
        },
        score_1_to_10=evaluation.score_1_to_10,
        confidence_score=evaluation.confidence_score,
        coverage_status=_coverage_status(evaluation),
        evidence_year=evaluation.year,
        method_version=method_version,
        warning_codes=_warning_codes(evaluation),
        caveats=evaluation.caveats,
        evidence_links=tuple(
            ResearchAnswerEvidence(
                source_slug=EFFECTIVENESS_8B_SOURCE_SLUG,
                source_observation_id=citation.url,
                evidence_role=citation.evidence_role,
            )
            for citation in evaluation.citations
        ),
    )


def _coverage_status(evaluation: Effectiveness8BEvaluation) -> str:
    if evaluation.evidence_quality == "manual_review_required":
        return "needs_review"
    if evaluation.verdict == "insufficient_evidence":
        return "insufficient_evidence"
    return "manual_cited"


def _warning_codes(evaluation: Effectiveness8BEvaluation) -> tuple[str, ...]:
    warnings: list[str] = []
    if evaluation.evidence_quality == "manual_review_required":
        warnings.append("manual_review_required")
    if evaluation.verdict in {"mixed_or_contested", "insufficient_evidence"}:
        warnings.append(evaluation.verdict)
    return tuple(warnings)


__all__ = [
    "EFFECTIVENESS_8B_METHOD_VERSION",
    "Effectiveness8BEvaluation",
    "EffectivenessCitation",
    "persist_effectiveness_8b_evaluations",
]
