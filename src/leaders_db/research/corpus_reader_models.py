"""Contracts for whole-context corpus reading and code-bound evidence."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .citation_spans import CitationSpan
from .citation_table_rows import TableLineSpan


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
    citation_span_ids: tuple[str, ...] = ()

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

    @field_validator("citation_span_ids")
    @classmethod
    def validate_span_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fact intent citation span IDs must be unique")
        return value


class BatchFactOutput(BaseModel):
    """Reader output for one context-bounded batch."""

    model_config = ConfigDict(extra="forbid")

    facts: tuple[FactIntent, ...]
    documents_with_no_material_fact: tuple[str, ...]
    batch_limitations: tuple[str, ...] = ()


class EvidenceCitation(BaseModel):
    """One exact, independently hash-bound source substring supporting a fact."""

    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(min_length=1)
    span: CitationSpan | TableLineSpan
    exact_excerpt: str = Field(min_length=1)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity_and_hashes(self) -> EvidenceCitation:
        suffix = "P" if isinstance(self.span, CitationSpan) else "L"
        match = re.fullmatch(rf"U([1-9][0-9]*)-{suffix}([1-9][0-9]*)", self.span_id)
        if match is None or int(match.group(1)) != self.span.unit:
            raise ValueError("evidence citation span ID and unit must agree")
        if isinstance(self.span, TableLineSpan) and (
            int(match.group(2)) != self.span.line_number
        ):
            raise ValueError("evidence table citation line ID and line number must agree")
        actual = sha256(self.exact_excerpt.encode("utf-8")).hexdigest()
        if actual != self.excerpt_sha256 or actual != self.span.text_sha256:
            raise ValueError("evidence citation hashes must match its exact excerpt")
        if self.span.end_char - self.span.start_char != len(self.exact_excerpt):
            raise ValueError("evidence citation offsets must match its exact excerpt length")
        return self


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
    citations: tuple[EvidenceCitation, ...] = ()
    verification_status: Literal["pending", "accepted", "corrected", "rejected"] = (
        "pending"
    )
    verification_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_citation_collection(self) -> BoundEvidence:
        if self.start_unit < 1 or self.end_unit < self.start_unit:
            raise ValueError("bound evidence unit range must be ordered and positive")
        span_ids = [item.span_id for item in self.citations]
        addresses = [
            (
                item.span.unit,
                item.span.start_char,
                item.span.end_char,
            )
            for item in self.citations
        ]
        if len(span_ids) != len(set(span_ids)) or len(addresses) != len(set(addresses)):
            raise ValueError("bound evidence citations must be unique")
        if any(
            item.span.unit < self.start_unit or item.span.unit > self.end_unit
            for item in self.citations
        ):
            raise ValueError("bound evidence citation lies outside its unit range")
        if any(
            isinstance(item.span, TableLineSpan) and item.span.source_id != self.source_id
            for item in self.citations
        ):
            raise ValueError("bound evidence table citation source identity differs")
        return self


class EvidenceVerdict(BaseModel):
    """One factual comparison against the code-bound passage."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    status: Literal["accepted", "corrected", "rejected"]
    corrected_fact_summary: str | None = None
    notes: tuple[str, ...] = ()
    citation_span_ids: tuple[str, ...] = ()

    @field_validator("citation_span_ids")
    @classmethod
    def validate_citation_span_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("verification citation span IDs must be unique")
        return value


class BatchVerification(BaseModel):
    """Fresh review verdicts for one reader batch."""

    model_config = ConfigDict(extra="forbid")

    verdicts: tuple[EvidenceVerdict, ...]


__all__ = [
    "BatchFactOutput",
    "BatchVerification",
    "BoundEvidence",
    "EvidenceCitation",
    "EvidenceVerdict",
    "FactIntent",
]
