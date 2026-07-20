"""Strict contract for no-search whole-ruler evidence review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewRemoval(BaseModel):
    """One exact ledger item to remove or treat only as context."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^E[0-9]{4,}$")
    reason: str = Field(min_length=1)


class ReviewGap(BaseModel):
    """One material evidence gap and a recoverable source direction."""

    model_config = ConfigDict(extra="forbid")

    gap: str = Field(min_length=1)
    lenses: tuple[str, ...]
    best_source_or_query_direction: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)


class ChapterReview(BaseModel):
    """Reviewer disposition for one complete chapter."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: Literal["1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B"]
    decision: Literal["pass", "targeted_follow_up", "credible_gap", "manual_review"]
    remove_or_contextualize: tuple[ReviewRemoval, ...]
    material_gaps: tuple[ReviewGap, ...]
    reason: str = Field(min_length=1)


class EvidenceReview(BaseModel):
    """Complete eight-chapter reviewer output."""

    model_config = ConfigDict(extra="forbid")

    overall_decision: Literal["pass", "targeted_follow_up", "manual_review"]
    chapters: tuple[ChapterReview, ...] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def _all_chapters_once(self) -> EvidenceReview:
        chapters = [item.chapter_id for item in self.chapters]
        expected = [f"{number}B" for number in range(1, 9)]
        if chapters != expected:
            raise ValueError("review must contain Chapters 1B-8B in order")
        return self


def validate_review(value: object, *, final: bool = False) -> dict[str, object]:
    """Validate and normalize one initial or final no-search review."""

    review = EvidenceReview.model_validate(value)
    if final and review.overall_decision == "targeted_follow_up":
        raise ValueError("final review may not request another follow-up")
    return review.model_dump(mode="json")


__all__ = [
    "ChapterReview", "EvidenceReview", "ReviewGap", "ReviewRemoval", "validate_review",
]
