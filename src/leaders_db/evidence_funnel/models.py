"""Validated artifacts exchanged by evidence-funnel stages."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionId = Annotated[str, Field(pattern=r"^[1-8]B\.(?:10|[1-9])$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EvidenceId = Annotated[str, Field(pattern=r"^EF-E[0-9a-f]{12}$")]
ClusterId = Annotated[str, Field(pattern=r"^EF-C[0-9a-f]{12}$")]

AccessState = Literal[
    "open_machine_readable",
    "open_browser_only",
    "metadata_only",
    "paywall_or_login",
    "bot_or_javascript_challenge",
    "robots_denied",
    "transient_failure",
    "unavailable",
]
PhaseStatus = Literal["pending", "running", "completed", "failed", "blocked"]
VerificationStatus = Literal["pending", "accepted", "corrected", "rejected", "escalated"]
EvidencePolarity = Literal["favorable", "adverse", "mixed", "exculpatory", "context"]


class StrictModel(BaseModel):
    """Base contract for immutable cross-stage payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDescriptor(StrictModel):
    """Frozen source identity and access state."""

    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    publication_date: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    source_sha256: Sha256
    access_state: AccessState
    dependencies: tuple[str, ...] = ()


class SectionBoundary(StrictModel):
    """Natural source boundary used only for navigation and routing."""

    section_id: str = Field(min_length=1)
    start_locator: str = Field(min_length=1)
    end_locator: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    topics: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    periods: tuple[str, ...] = ()
    table_locators: tuple[str, ...] = ()
    likely_question_ids: tuple[QuestionId, ...] = ()
    reading_priority: Literal["low", "medium", "high", "pivotal"]


class DocumentSectionMap(StrictModel):
    """Navigation-only map of one source; never itself accepted as evidence."""

    schema_version: Literal["document_section_map_v1"]
    source: SourceDescriptor
    deterministic_complete_source_forward: bool
    sections: tuple[SectionBoundary, ...]
    generated_by: str = Field(min_length=1)


class ChunkRoutingDecision(StrictModel):
    """Auditable include/exclude decision for one source chunk."""

    schema_version: Literal["chunk_routing_decision_v1"]
    source_id: str
    source_sha256: Sha256
    chunk_id: str = Field(min_length=1)
    included: bool
    relevant_question_ids: tuple[QuestionId, ...] = ()
    relevance_strength: Literal["none", "weak", "material", "pivotal"]
    adjacent_chunk_ids: tuple[str, ...] = ()
    explanation: str = Field(min_length=1)
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> ChunkRoutingDecision:
        if self.included and not self.relevant_question_ids:
            raise ValueError("included chunks require at least one relevant question")
        if self.included and self.exclusion_reason is not None:
            raise ValueError("included chunks cannot carry an exclusion reason")
        if not self.included and not self.exclusion_reason:
            raise ValueError("excluded chunks require an auditable exclusion reason")
        if self.included and self.relevance_strength == "none":
            raise ValueError("included chunks cannot have zero relevance")
        if not self.included and (
            self.relevant_question_ids or self.adjacent_chunk_ids
        ):
            raise ValueError("excluded chunks cannot route questions or adjacent context")
        return self


class EvidenceCandidate(StrictModel):
    """One atomic factual account, stored once and mapped to all relevant questions."""

    schema_version: Literal["evidence_candidate_v1", "evidence_candidate_v2"]
    evidence_id: EvidenceId
    source_id: str
    source_sha256: Sha256
    source_family: str = Field(min_length=1)
    source_dependencies: tuple[str, ...] = ()
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
    excerpt: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    excerpt_start_char: int | None = Field(default=None, ge=0)
    excerpt_end_char: int | None = Field(default=None, gt=0)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    publication_date: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    period_fit: str = Field(min_length=1)
    source_limitations: tuple[str, ...] = ()
    question_ids: tuple[QuestionId, ...] = Field(min_length=1)
    verification_status: VerificationStatus
    verification_notes: tuple[str, ...] = ()
    premium_verification_required: bool = False

    @model_validator(mode="after")
    def validate_unique_questions(self) -> EvidenceCandidate:
        if len(self.question_ids) != len(set(self.question_ids)):
            raise ValueError("candidate question IDs must be unique")
        offsets = (self.excerpt_start_char, self.excerpt_end_char)
        if self.schema_version == "evidence_candidate_v2" and None in offsets:
            raise ValueError("v2 candidates require exact source character offsets")
        if self.schema_version == "evidence_candidate_v1" and any(
            value is not None for value in offsets
        ):
            raise ValueError("v1 candidates cannot carry v2 character offsets")
        if (
            self.excerpt_start_char is not None
            and self.excerpt_end_char is not None
            and self.excerpt_start_char >= self.excerpt_end_char
        ):
            raise ValueError("citation start offset must precede end offset")
        return self


class ClusterRelationship(StrictModel):
    """Relationship from a member item to the canonical underlying fact."""

    evidence_id: EvidenceId
    relation: Literal["supports", "contradicts", "qualifies"]


class ClaimCluster(StrictModel):
    """Repeated coverage grouped without deleting individual evidence records."""

    schema_version: Literal["claim_cluster_v1"]
    cluster_id: ClusterId
    canonical_fact: str = Field(min_length=1)
    canonical_fact_key: str = Field(min_length=1)
    member_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)
    relationships: tuple[ClusterRelationship, ...] = Field(min_length=1)
    independent_source_families: tuple[str, ...]
    dependent_source_families: tuple[str, ...] = ()
    official_source_concentration: float = Field(ge=0, le=1)
    unresolved_conflicts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_members(self) -> ClaimCluster:
        members = set(self.member_evidence_ids)
        if len(members) != len(self.member_evidence_ids):
            raise ValueError("cluster members must be unique")
        relationship_ids = [item.evidence_id for item in self.relationships]
        if len(relationship_ids) != len(set(relationship_ids)):
            raise ValueError("cluster relationships must have unique evidence IDs")
        if set(relationship_ids) != members:
            raise ValueError("cluster relationships must cover every member exactly once")
        return self


class BriefEvidenceReference(StrictModel):
    """Cluster-level reference under one question and interpretive polarity."""

    cluster_id: ClusterId
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)
    polarity: EvidencePolarity
    account: str = Field(min_length=1)
    competing_interpretations: tuple[str, ...] = ()


class QuestionEvidenceBrief(StrictModel):
    """Fact-rich, cluster-based package for one methodology question."""

    schema_version: Literal["question_evidence_brief_v1"]
    methodology_id: QuestionId
    evidence: tuple[BriefEvidenceReference, ...]
    chronology: tuple[str, ...]
    authority_and_constraints: tuple[str, ...]
    implementation_status: tuple[str, ...]
    unresolved_gaps: tuple[str, ...]
    source_family_assessment: str = Field(min_length=1)


class FunnelTelemetry(StrictModel):
    """Actual token counts at each transition; no target compression ratio."""

    acquired_source_tokens: int = Field(ge=0)
    routed_tokens: int = Field(ge=0)
    closely_read_tokens: int = Field(ge=0)
    evidence_ledger_tokens: int = Field(ge=0)
    clustered_tokens: int = Field(ge=0)
    question_brief_tokens: int = Field(ge=0)
    premium_verification_tokens: int = Field(ge=0)
    final_judge_tokens: int = Field(ge=0)


class PhaseRecord(StrictModel):
    """Durable status and telemetry for one resumable phase."""

    status: PhaseStatus
    input_hash: Sha256
    config_hash: Sha256
    output_paths: tuple[str, ...] = ()
    output_hashes: tuple[Sha256, ...] = ()
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int = Field(default=0, ge=0)
    failures: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_completion(self) -> PhaseRecord:
        if self.status == "completed":
            if self.completed_at is None or not self.output_paths:
                raise ValueError("completed phases require completion time and outputs")
            if len(self.output_paths) != len(self.output_hashes):
                raise ValueError("completed phase output paths and hashes must align")
        return self


class FunnelRunManifest(StrictModel):
    """Hash-bound execution state for an interrupted or completed funnel run."""

    schema_version: Literal["evidence_funnel_manifest_v1"]
    run_id: str = Field(min_length=1)
    gate_id: str = Field(min_length=1)
    experimental_non_publication: Literal[True]
    config_path: str = Field(min_length=1)
    config_sha256: Sha256
    frozen_inputs: dict[str, Sha256]
    frozen_inputs_sha256: Sha256
    model_profile: dict[str, str]
    prompt_hashes: dict[str, Sha256]
    phases: dict[str, PhaseRecord]
    telemetry: FunnelTelemetry
    gap_round: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def validate_frozen_input_binding(self) -> FunnelRunManifest:
        serialized = (
            json.dumps(
                dict(sorted(self.frozen_inputs.items())),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        if hashlib.sha256(serialized).hexdigest() != self.frozen_inputs_sha256:
            raise ValueError("frozen_inputs_sha256 does not bind the frozen input map")
        return self


class FunnelEvidenceEnvironment(StrictModel):
    """Evidence-environment assessment using funnel-native evidence IDs."""

    criticism_possible: str = Field(min_length=1)
    censorship_and_self_censorship: str = Field(min_length=1)
    safe_reporting_channels: str = Field(min_length=1)
    official_statistics_reliability: str = Field(min_length=1)
    languages_and_archives_searched: tuple[str, ...] = Field(min_length=1)
    source_concentration: str = Field(min_length=1)
    duplicate_event_risk: str = Field(min_length=1)
    complaint_volume_interpretation: str = Field(min_length=1)
    relevant_denominators: str = Field(min_length=1)
    inherited_conditions_shocks_and_authority: str = Field(min_length=1)
    chapter_specific_biases: tuple[str, ...] = Field(min_length=1)
    supporting_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_support(self) -> FunnelEvidenceEnvironment:
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("environment support IDs must be unique")
        return self


class ExperimentalJudgePacket(StrictModel):
    """Non-publication packet consumed by matched diagnostic judgments."""

    schema_version: Literal["experimental_judge_packet_v1"]
    run_id: str
    chapter_id: Literal["5B"]
    ruler_name: str
    country_name: str
    period: str
    experimental_non_publication: Literal[True]
    briefs: tuple[QuestionEvidenceBrief, ...]
    clusters: tuple[ClaimCluster, ...]
    evidence_ledger_path: str
    evidence_ledger_sha256: Sha256
    source_family_assessment: str = Field(min_length=1)
    telemetry: FunnelTelemetry
    diagnostic_arms: tuple[
        Literal["closed_book_funnel_packet", "reference_full_frozen_extracts"], ...
    ]
    audit_required: Literal[True]

    @model_validator(mode="after")
    def validate_question_packet(self) -> ExperimentalJudgePacket:
        ids = [brief.methodology_id for brief in self.briefs]
        if len(ids) != len(set(ids)):
            raise ValueError("judge packet briefs must have unique methodology IDs")
        return self


__all__ = [
    "AccessState",
    "BriefEvidenceReference",
    "ChunkRoutingDecision",
    "ClaimCluster",
    "ClusterRelationship",
    "DocumentSectionMap",
    "EvidenceCandidate",
    "ExperimentalJudgePacket",
    "FunnelEvidenceEnvironment",
    "FunnelRunManifest",
    "FunnelTelemetry",
    "PhaseRecord",
    "QuestionEvidenceBrief",
    "SectionBoundary",
    "SourceDescriptor",
]
