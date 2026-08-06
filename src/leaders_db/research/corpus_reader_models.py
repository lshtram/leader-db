"""Contracts for whole-context corpus reading and code-bound evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FactIntent(BaseModel):
    """Simple semantic intent emitted by a document reader."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    start_unit: int = Field(ge=1)
    end_unit: int = Field(ge=1)
    fact_summary: str = Field(min_length=10)
    question_ids: tuple[str, ...]
    polarity: Literal["favorable", "adverse", "mixed", "exculpatory", "context"]
    period_fit: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unit_range(self) -> FactIntent:
        if self.end_unit < self.start_unit:
            raise ValueError("fact intent unit range must be ordered")
        return self

    @field_validator("question_ids")
    @classmethod
    def validate_questions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {
            f"{chapter}B.{question}"
            for chapter in range(1, 9)
            for question in range(1, 11)
        }
        if not value or not set(value).issubset(allowed):
            raise ValueError("fact intent must map to valid 1B.1 through 8B.10 IDs")
        return tuple(sorted(set(value)))


class BatchFactOutput(BaseModel):
    """Reader output for one context-bounded batch."""

    model_config = ConfigDict(extra="forbid")

    facts: tuple[FactIntent, ...]
    documents_with_no_material_fact: tuple[str, ...]
    batch_limitations: tuple[str, ...] = ()


class BoundEvidence(BaseModel):
    """Code-owned evidence record resolved from a reader's semantic intent."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_id: str
    url: str
    title: str
    publisher: str
    raw_sha256: str
    fact_summary: str
    question_ids: tuple[str, ...]
    polarity: str
    period_fit: str
    ruler_attribution: str
    limitations: tuple[str, ...]
    start_unit: int
    end_unit: int
    locator: str
    exact_excerpt: str
    excerpt_sha256: str
    verification_status: Literal["pending", "accepted", "corrected", "rejected"] = (
        "pending"
    )
    verification_notes: tuple[str, ...] = ()


class EvidenceVerdict(BaseModel):
    """One factual comparison against the code-bound passage."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    status: Literal["accepted", "corrected", "rejected"]
    corrected_fact_summary: str | None = None
    notes: tuple[str, ...] = ()


class BatchVerification(BaseModel):
    """Fresh review verdicts for one reader batch."""

    model_config = ConfigDict(extra="forbid")

    verdicts: tuple[EvidenceVerdict, ...]


__all__ = [
    "BatchFactOutput",
    "BatchVerification",
    "BoundEvidence",
    "EvidenceVerdict",
    "FactIntent",
]
