"""Versioned scientific and operational configuration for the evidence funnel."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "evidence-funnel" / "amlo-2022-5b-v2.json"
)
REQUIRED_PHASE_ORDER = (
    "catalogue",
    "mapping",
    "routing",
    "intent_extraction",
    "citation_binding",
    "citation_confirmation",
    "semantic_verification",
    "clustering",
    "gap_research",
    "briefing",
    "dossier",
    "diagnostic_judgment",
    "score_audit",
)
REQUIRED_STAGES = {
    "mapping",
    "routing",
    "extraction",
    "verification",
    "cluster_adjudication",
    "gap_management",
    "diagnostic_judge",
    "score_audit",
}
REQUIRED_PROMPTS = {"mapping", "routing", "extraction", "verification", "gap_management"}


class StageProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fallbacks: tuple[str, ...] = ()
    max_attempts: int = Field(ge=1, le=5)
    attempt_timeout_seconds: int = Field(ge=60, le=1800)


class RoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    short_record_max_tokens: int = Field(gt=0)
    minimum_relevance: str = Field(pattern=r"^(weak|material|pivotal)$")
    adjacent_context_chunks: int = Field(ge=0, le=3)
    routing_batch_max_units: int = Field(gt=0, le=100)
    extraction_batch_max_units: int = Field(gt=0, le=100)
    extraction_validation_retries: int = Field(ge=0, le=2)


class VerificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    random_premium_sample_rate: float = Field(ge=0, le=1)
    escalate_pivotal: bool
    escalate_legal_or_technical: bool
    escalate_reviewer_disagreement: bool
    batch_max_candidates: int = Field(gt=0, le=100)
    validation_retries: int = Field(ge=0, le=2)
    maximum_locator_audit_rejection_rate: float = Field(ge=0, le=1)
    maximum_invalid_extractor_locator_rate: float = Field(ge=0, le=1)
    maximum_semantic_rejection_rate: float = Field(ge=0, le=1)


class CitationPolicy(BaseModel):
    """Deterministic source-span selection and correction limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    segment_characters: int = Field(ge=80, le=500)
    maximum_binding_attempts: int = Field(ge=1, le=5)


class EvidenceFunnelConfig(BaseModel):
    """Single authoritative configuration for a funnel run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^evidence_funnel_config_v[0-9]+$")
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    methodology_ids: tuple[str, ...] = Field(min_length=1)
    calibration_document_ids: tuple[str, ...] = Field(min_length=1)
    frozen_document_ids: tuple[str, ...] = Field(min_length=1)
    expanded_catalogue_gate_enabled: bool
    maximum_gap_rounds: int = Field(ge=0, le=3)
    diagnostic_score_tolerance: float = Field(ge=0, le=9)
    stages: dict[str, StageProfile]
    routing: RoutingPolicy
    verification: VerificationPolicy
    citations: CitationPolicy
    prompts: dict[str, str]
    phase_order: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cross_references(self) -> EvidenceFunnelConfig:
        expected_questions = tuple(f"{self.chapter_id}.{number}" for number in range(1, 11))
        if self.methodology_ids != expected_questions:
            raise ValueError("methodology IDs must be the ordered ten-lens chapter grid")
        if len(self.frozen_document_ids) != len(set(self.frozen_document_ids)):
            raise ValueError("frozen document IDs must be unique")
        if len(self.calibration_document_ids) != len(set(self.calibration_document_ids)):
            raise ValueError("calibration document IDs must be unique")
        frozen = set(self.frozen_document_ids)
        if not set(self.calibration_document_ids).issubset(frozen):
            raise ValueError("calibration documents must belong to the frozen pack")
        if set(self.stages) != REQUIRED_STAGES:
            raise ValueError("stage profiles must exactly match required evidence-funnel roles")
        if set(self.prompts) != REQUIRED_PROMPTS or any(
            not value.strip() for value in self.prompts.values()
        ):
            raise ValueError("prompts must exactly cover every model-assisted low-cost stage")
        if self.phase_order != REQUIRED_PHASE_ORDER:
            raise ValueError("phase order must match the evidence-funnel dependency sequence")
        return self


def load_evidence_funnel_config(path: Path = DEFAULT_CONFIG_PATH) -> EvidenceFunnelConfig:
    """Load and validate one evidence-funnel config."""

    return EvidenceFunnelConfig.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "CitationPolicy",
    "EvidenceFunnelConfig",
    "load_evidence_funnel_config",
]
