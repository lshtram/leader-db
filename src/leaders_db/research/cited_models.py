"""Pydantic models for cited manual/internet evaluations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cited_calibration import validate_score_calibration

Verdict = Literal[
    "supported",
    "partially_supported",
    "mixed_or_contested",
    "insufficient_evidence",
    "not_applicable",
]
EvidenceQuality = Literal["high", "medium", "low", "manual_review_required"]
ConfidenceBand = Literal["high", "medium", "low", "manual_review_required"]


def normalize_confidence_score(value: Any) -> Any:
    """Accept either 0-100 confidence percentages or 0-1 fractions."""

    if isinstance(value, float) and 0 <= value <= 1:
        return round(value * 100)
    return value


class CitedEvaluationCitation(BaseModel):
    """One cited source supporting a qualitative evaluation."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    title: str | None = None
    quote: str | None = None
    evidence_role: str = "citation"


class CitedEvaluation(BaseModel):
    """Source-backed output from a manual/internet evaluator."""

    model_config = ConfigDict(extra="forbid")

    methodology_id: str
    year: int
    iso3: str = Field(min_length=3, max_length=3)
    country_name: str = Field(min_length=1)
    leader_name: str | None = None
    leader_id: str | None = None
    leader_resolution: str | None = None
    period_start_year: int | None = None
    period_end_year: int | None = None
    period_label: str | None = None
    prompt_context: str | None = None
    verdict: Verdict
    evidence_quality: EvidenceQuality
    confidence: ConfidenceBand
    manual_review_reason: str | None = None
    score_1_to_10: int | None = Field(default=None, ge=1, le=10)
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    claims: tuple[dict[str, Any], ...] = ()
    answer_payload: dict[str, Any] = Field(default_factory=dict)
    candidate_structured_observation: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[CitedEvaluationCitation, ...] = Field(min_length=1)
    caveats: tuple[str, ...] = ()

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _normalize_confidence_score(cls, value: Any) -> Any:
        return normalize_confidence_score(value)

    @model_validator(mode="after")
    def _validate_record(self) -> CitedEvaluation:
        if self.evidence_quality == "manual_review_required" and not self.manual_review_reason:
            raise ValueError("manual_review_reason is required when manual review is flagged")
        validate_score_calibration(
            methodology_id=self.methodology_id,
            score_1_to_10=self.score_1_to_10,
            answer_payload=self.answer_payload,
        )
        return self


def cited_evaluation_json_schema() -> dict[str, Any]:
    """Return the JSON Schema that researcher/subagent outputs must satisfy."""

    return CitedEvaluation.model_json_schema()


__all__ = [
    "CitedEvaluation",
    "CitedEvaluationCitation",
    "cited_evaluation_json_schema",
    "normalize_confidence_score",
]
