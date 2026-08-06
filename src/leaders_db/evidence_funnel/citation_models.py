"""Typed commands and artifacts for code-owned exact citations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import EvidencePolarity, QuestionId, Sha256


class CitationModel(BaseModel):
    """Immutable strict base for citation workflow artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSegment(CitationModel):
    """One exact display segment with stable character offsets."""

    segment_id: str = Field(pattern=r"^S[0-9]{5}$")
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> SourceSegment:
        if self.start_char >= self.end_char:
            raise ValueError("segment start must precede segment end")
        if len(self.text) != self.end_char - self.start_char:
            raise ValueError("segment text length must equal its offset width")
        return self


class LocatorIndex(CitationModel):
    """Model-readable index for one frozen source locator."""

    schema_version: Literal["locator_index_v1"] = "locator_index_v1"
    source_id: str
    source_sha256: Sha256
    locator: str = Field(min_length=1)
    segments: tuple[SourceSegment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segments(self) -> LocatorIndex:
        for number, segment in enumerate(self.segments, start=1):
            if segment.segment_id != f"S{number:05d}":
                raise ValueError("locator segments must use sequential IDs")
            expected_start = 0 if number == 1 else self.segments[number - 2].end_char
            if segment.start_char != expected_start:
                raise ValueError("locator segments must be contiguous and ordered")
        return self


class CitationSelection(CitationModel):
    """Inclusive segment range selected by the model."""

    source_id: str
    source_sha256: Sha256
    locator: str = Field(min_length=1)
    start_segment_id: str = Field(pattern=r"^S[0-9]{5}$")
    end_segment_id: str = Field(pattern=r"^S[0-9]{5}$")

    @model_validator(mode="after")
    def validate_order(self) -> CitationSelection:
        if self.start_segment_id > self.end_segment_id:
            raise ValueError("citation segment range must be ordered")
        return self


class EvidenceIntent(CitationModel):
    """Semantic evidence proposal without model-authored quotation text."""

    schema_version: Literal["evidence_intent_v1"] = "evidence_intent_v1"
    draft_id: str = Field(pattern=r"^D[0-9]{4}$")
    citation: CitationSelection
    claim: str = Field(min_length=1)
    claim_type: Literal[
        "observed_fact",
        "source_assertion",
        "interpretation",
        "allegation",
        "legal_status",
        "recommendation",
    ]
    polarity: EvidencePolarity
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    dates: tuple[str, ...] = ()
    quantities: tuple[str, ...] = ()
    attribution: str = Field(min_length=1)
    period_fit: str = Field(min_length=1)
    source_limitations: tuple[str, ...] = ()
    question_ids: tuple[QuestionId, ...] = Field(min_length=1)
    premium_verification_required: bool = False

    @model_validator(mode="after")
    def validate_questions(self) -> EvidenceIntent:
        if len(self.question_ids) != len(set(self.question_ids)):
            raise ValueError("intent question IDs must be unique")
        return self


class BoundEvidenceDraft(CitationModel):
    """Exact code-bound citation returned for semantic confirmation."""

    schema_version: Literal["bound_evidence_draft_v1"] = "bound_evidence_draft_v1"
    proposal_id: str = Field(pattern=r"^EF-P[0-9a-f]{12}$")
    attempt: int = Field(ge=1)
    intent: EvidenceIntent
    exact_excerpt: str = Field(min_length=1)
    excerpt_start_char: int = Field(ge=0)
    excerpt_end_char: int = Field(gt=0)
    status: Literal["pending_confirmation"] = "pending_confirmation"

    @model_validator(mode="after")
    def validate_excerpt_offsets(self) -> BoundEvidenceDraft:
        if self.excerpt_start_char >= self.excerpt_end_char:
            raise ValueError("bound excerpt start must precede end")
        if len(self.exact_excerpt) != self.excerpt_end_char - self.excerpt_start_char:
            raise ValueError("bound excerpt length must equal its offset width")
        return self


class CitationAttemptBinding(CitationModel):
    """Hash-chain entry binding one immutable attempt artifact."""

    schema_version: Literal["citation_attempt_binding_v1"] = (
        "citation_attempt_binding_v1"
    )
    proposal_id: str = Field(pattern=r"^EF-P[0-9a-f]{12}$")
    attempt: int = Field(ge=1)
    attempt_sha256: Sha256
    previous_binding_sha256: Sha256 | None = None


class CitationDecision(CitationModel):
    """Immutable terminal decision for a bound evidence proposal."""

    schema_version: Literal["citation_decision_v1"] = "citation_decision_v1"
    proposal_id: str = Field(pattern=r"^EF-P[0-9a-f]{12}$")
    attempt: int = Field(ge=1)
    decision: Literal["confirmed", "discarded"]
    reason: str | None = None
    evidence_id: str | None = None
    candidate_sha256: Sha256 | None = None
    binding_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_reason(self) -> CitationDecision:
        if self.decision == "discarded" and not self.reason:
            raise ValueError("discarded citations require a reason")
        if self.decision == "confirmed" and (
            self.evidence_id is None
            or self.candidate_sha256 is None
            or self.binding_sha256 is None
        ):
            raise ValueError("confirmed citations require candidate and binding hashes")
        if self.decision == "discarded" and (
            self.evidence_id is not None
            or self.candidate_sha256 is not None
            or self.binding_sha256 is not None
        ):
            raise ValueError("discarded citations cannot reference a candidate")
        return self


class TranslationRecord(CitationModel):
    """Non-authoritative translation linked to an original exact excerpt."""

    schema_version: Literal["citation_translation_v1"] = "citation_translation_v1"
    evidence_id: str
    original_text_sha256: Sha256
    translated_text: str = Field(min_length=1)
    source_language: str = Field(min_length=2)
    target_language: str = Field(min_length=2)
    model_profile: str = Field(min_length=1)


__all__ = [
    "BoundEvidenceDraft",
    "CitationAttemptBinding",
    "CitationDecision",
    "CitationSelection",
    "EvidenceIntent",
    "LocatorIndex",
    "SourceSegment",
    "TranslationRecord",
]
