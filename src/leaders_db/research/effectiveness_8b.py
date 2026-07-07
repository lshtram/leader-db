"""Persist cited 8B ruler-effectiveness evaluations.

This module does not run web research or score leaders by itself. It accepts an
already-produced, source-backed 8B evaluation record and writes it through the
generic D24-D27 research answer store.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .cited_evaluations import (
    CitedEvaluation,
    CitedEvaluationCitation,
    normalize_confidence_score,
    persist_cited_evaluations,
    validate_score_calibration,
)
from .registry import get_question_spec_by_methodology_id

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
    calibration: dict[str, Any] = Field(default_factory=dict)
    candidate_structured_observation: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[EffectivenessCitation, ...] = Field(min_length=1)
    caveats: tuple[str, ...] = ()

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _normalize_confidence_score(cls, value: Any) -> Any:
        return normalize_confidence_score(value)

    @model_validator(mode="after")
    def _validate_record(self) -> Effectiveness8BEvaluation:
        if self.evidence_quality == "manual_review_required" and not self.manual_review_reason:
            raise ValueError("manual_review_reason is required when manual review is flagged")
        validate_score_calibration(
            score_1_to_10=self.score_1_to_10,
            answer_payload={"calibration": self.calibration},
        )
        return self


def persist_effectiveness_8b_evaluations(
    bind: Engine | Session,
    evaluations: Sequence[Effectiveness8BEvaluation],
    *,
    method_version: str = EFFECTIVENESS_8B_METHOD_VERSION,
) -> None:
    """Persist already-cited 8B evaluations into generic answer tables."""

    for evaluation in evaluations:
        spec = get_question_spec_by_methodology_id(evaluation.methodology_id)
        if spec is None or not evaluation.methodology_id.startswith("8B."):
            raise ValueError(f"unsupported 8B methodology_id: {evaluation.methodology_id!r}")
    persist_cited_evaluations(
        bind,
        tuple(_to_cited_evaluation(evaluation) for evaluation in evaluations),
        method_version=method_version,
    )


def _to_cited_evaluation(evaluation: Effectiveness8BEvaluation) -> CitedEvaluation:
    return CitedEvaluation(
        methodology_id=evaluation.methodology_id,
        year=evaluation.year,
        iso3=evaluation.iso3,
        country_name=evaluation.country_name,
        leader_name=evaluation.leader_name,
        leader_id=evaluation.leader_id,
        leader_resolution=evaluation.leader_resolution,
        period_label=evaluation.implementation_or_outcome_window,
        prompt_context=evaluation.program_source,
        verdict=evaluation.verdict,
        evidence_quality=evaluation.evidence_quality,
        confidence=evaluation.confidence,
        manual_review_reason=evaluation.manual_review_reason,
        score_1_to_10=evaluation.score_1_to_10,
        confidence_score=evaluation.confidence_score,
        claims=evaluation.goal_coverage,
        answer_payload={
            "program_source": evaluation.program_source,
            "implementation_or_outcome_window": evaluation.implementation_or_outcome_window,
            "goal_coverage": list(evaluation.goal_coverage),
            "calibration": evaluation.calibration,
        },
        candidate_structured_observation=evaluation.candidate_structured_observation,
        citations=tuple(
            CitedEvaluationCitation(**citation.model_dump()) for citation in evaluation.citations
        ),
        caveats=evaluation.caveats,
    )


__all__ = [
    "EFFECTIVENESS_8B_METHOD_VERSION",
    "Effectiveness8BEvaluation",
    "EffectivenessCitation",
    "persist_effectiveness_8b_evaluations",
]
