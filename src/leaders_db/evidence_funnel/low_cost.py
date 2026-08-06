"""Strict low-cost model payloads and execution controls for the funnel."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .citation_models import EvidenceIntent
from .config import EvidenceFunnelConfig
from .models import ChunkRoutingDecision, DocumentSectionMap, QuestionId

LOW_COST_PROFILES = frozenset(
    {
        "minimax-m3-long-context",
        "minimax-m2.7-researcher",
    }
)


class EvidenceIntentBatch(BaseModel):
    """Complete extraction response containing no model-authored quotations."""

    model_config = ConfigDict(extra="forbid")

    intents: tuple[EvidenceIntent, ...]
    inspected_locator_count: int = Field(ge=0)
    locator_dispositions: tuple[LocatorDisposition, ...]
    material_omissions: tuple[str, ...] = ()
    unresolved_gaps: tuple[ScopedGap, ...] = ()

    @model_validator(mode="after")
    def validate_candidate_identity(self) -> EvidenceIntentBatch:
        draft_ids = [item.draft_id for item in self.intents]
        if len(draft_ids) != len(set(draft_ids)):
            raise ValueError("candidate batch contains duplicate draft IDs")
        return self


class SemanticReview(BaseModel):
    """Fresh semantic review after code has bound an exact citation."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^EF-E[0-9a-f]{12}$")
    status: Literal["accepted", "rejected", "escalated"]
    explanation: str = Field(min_length=1)
    unsupported_elements: tuple[str, ...] = ()
    attribution_corrections: tuple[str, ...] = ()


class SemanticReviewBatch(BaseModel):
    """Fresh semantic dispositions for every bound candidate in one batch."""

    model_config = ConfigDict(extra="forbid")

    reviews: tuple[SemanticReview, ...]

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> SemanticReviewBatch:
        evidence_ids = [item.evidence_id for item in self.reviews]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("semantic reviews must have unique evidence IDs")
        return self


class LocatorDisposition(BaseModel):
    """Extractor accounting for one routed locator."""

    model_config = ConfigDict(extra="forbid")

    locator: str = Field(min_length=1)
    disposition: Literal["evidence_extracted", "no_material_evidence"]
    explanation: str = Field(
        min_length=1,
        validation_alias=AliasChoices("explanation", "displanation"),
    )


class ScopedGap(BaseModel):
    """Unresolved research gap attached only to applicable question lenses."""

    model_config = ConfigDict(extra="forbid")

    question_ids: tuple[QuestionId, ...] = Field(min_length=1)
    gap: str = Field(min_length=1)


class DocumentMapBatch(BaseModel):
    """One navigation map response."""

    model_config = ConfigDict(extra="forbid")

    document_map: DocumentSectionMap


class RoutingDecisionBatch(BaseModel):
    """Complete routing ledger for every supplied chunk."""

    model_config = ConfigDict(extra="forbid")

    decisions: tuple[ChunkRoutingDecision, ...]

    @model_validator(mode="after")
    def validate_unique_chunks(self) -> RoutingDecisionBatch:
        chunk_ids = [item.chunk_id for item in self.decisions]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("routing decisions must have unique chunk IDs")
        return self


def assert_low_cost_stage_profiles(config: EvidenceFunnelConfig) -> None:
    """Reject a runner configuration that could send corpus stages to premium models."""

    for stage in ("mapping", "routing", "extraction", "verification"):
        profile = config.stages[stage]
        configured = (profile.model, *profile.fallbacks)
        pair = ("minimax-m3-long-context", "minimax-m2.7-researcher")
        required = pair * (2 if stage == "routing" else 1)
        if configured != required or profile.max_attempts != len(required):
            raise ValueError(
                f"{stage} must use the configured repeated M3/M2.7 content ladder"
            )


__all__ = [
    "LOW_COST_PROFILES",
    "DocumentMapBatch",
    "EvidenceIntentBatch",
    "LocatorDisposition",
    "RoutingDecisionBatch",
    "ScopedGap",
    "SemanticReview",
    "SemanticReviewBatch",
    "assert_low_cost_stage_profiles",
]
