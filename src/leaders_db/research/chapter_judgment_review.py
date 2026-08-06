"""Validated bounded review of one comparative chapter judgment."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .chapter_judge_models import ChapterJudgmentBatch, RulerChapterJudgment


class JudgmentReviewDecision(BaseModel):
    """One independent decision that preserves or narrowly corrects a judgment."""

    model_config = ConfigDict(extra="forbid")

    dossier_job_key: str = Field(min_length=1)
    original_score: float | None = Field(default=None, ge=1, le=10, multiple_of=0.5)
    reviewed_score: float | None = Field(default=None, ge=1, le=10, multiple_of=0.5)
    disposition: Literal["retain", "increase", "decrease"]
    review_explanation: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...]
    revised_chapter_rationale: str = Field(min_length=1)
    revised_lower_anchor_rejected: str = Field(min_length=1)
    revised_higher_anchor_rejected: str = Field(min_length=1)

    @model_validator(mode="after")
    def _bounded_score_change(self) -> JudgmentReviewDecision:
        if self.original_score is None or self.reviewed_score is None:
            if self.original_score is not None or self.reviewed_score is not None:
                raise ValueError("review cannot convert between null and numeric scores")
            if self.disposition != "retain":
                raise ValueError("a null judgment must be retained")
            return self
        delta = self.reviewed_score - self.original_score
        if abs(delta) > 1:
            raise ValueError("review score correction must remain within plus or minus 1")
        expected = "increase" if delta > 0 else "decrease" if delta < 0 else "retain"
        if self.disposition != expected:
            raise ValueError("review disposition contradicts the score change")
        return self


class ChapterJudgmentReview(BaseModel):
    """Complete independent review of every evaluation in one chapter batch."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["chapter_judgment_review_v1"]
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    source_job_key: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_model: Literal["gpt-5.6-sol"]
    reasoning_effort: Literal["high"]
    decisions: tuple[JudgmentReviewDecision, ...] = Field(min_length=1)
    chapter_review_summary: str = Field(min_length=1)


def validate_review(
    review: ChapterJudgmentReview,
    *,
    judgment: ChapterJudgmentBatch,
    source_sha256: str,
    evidence_ids_by_job: dict[str, set[str]],
) -> None:
    """Validate identity, score bounds, and cited evidence before application."""

    if review.chapter_id != judgment.chapter_id:
        raise ValueError("review chapter differs from source judgment")
    if review.source_job_key != judgment.job_key or review.source_sha256 != source_sha256:
        raise ValueError("review is not bound to the supplied source judgment")
    originals = {item.dossier_job_key: item for item in judgment.evaluations}
    decisions = {item.dossier_job_key: item for item in review.decisions}
    if len(decisions) != len(review.decisions) or decisions.keys() != originals.keys():
        raise ValueError("review must contain exactly one decision per source evaluation")
    for job_key, decision in decisions.items():
        original = originals[job_key]
        if decision.original_score != original.score_1_to_10:
            raise ValueError("review original score does not match source judgment")
        if not set(decision.supporting_evidence_ids).issubset(
            evidence_ids_by_job.get(job_key, set())
        ):
            raise ValueError("review cites evidence outside the ruler projection")


def apply_review(
    judgment: ChapterJudgmentBatch, review: ChapterJudgmentReview
) -> ChapterJudgmentBatch:
    """Return a revised batch while preserving all evidence and audit fields."""

    decisions = {item.dossier_job_key: item for item in review.decisions}
    evaluations = tuple(
        _apply_decision(evaluation, decisions[evaluation.dossier_job_key])
        for evaluation in judgment.evaluations
    )
    return judgment.model_copy(
        update={
            "evaluations": evaluations,
            "batch_notes": (
                *judgment.batch_notes,
                "Independent high-reasoning Sol review applied; numeric corrections "
                "were bounded to ±1.",
                review.chapter_review_summary,
            ),
        }
    )


def _apply_decision(
    evaluation: RulerChapterJudgment, decision: JudgmentReviewDecision
) -> RulerChapterJudgment:
    score = decision.reviewed_score
    score_range = evaluation.plausible_score_range
    if score is not None:
        score_range = score_range.model_copy(
            update={
                "lower": min(score_range.lower, score),
                "upper": max(score_range.upper, score),
            }
        )
    return evaluation.model_copy(
        update={
            "score_1_to_10": score,
            "plausible_score_range": score_range,
            "chapter_rationale": decision.revised_chapter_rationale,
            "lower_anchor_rejected": decision.revised_lower_anchor_rejected,
            "higher_anchor_rejected": decision.revised_higher_anchor_rejected,
        }
    )


def codex_chapter_review_json_schema() -> dict[str, Any]:
    """Return the strict JSON schema accepted by Codex structured output."""

    schema = ChapterJudgmentReview.model_json_schema()
    _require_every_property(schema)
    return schema


def _require_every_property(node: Any) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
            node["additionalProperties"] = False
        for value in node.values():
            _require_every_property(value)
    elif isinstance(node, list):
        for value in node:
            _require_every_property(value)


__all__ = [
    "ChapterJudgmentReview",
    "JudgmentReviewDecision",
    "apply_review",
    "codex_chapter_review_json_schema",
    "validate_review",
]
