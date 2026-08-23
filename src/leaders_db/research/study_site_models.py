"""Validated public projection for one approved ruler-study website."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    url: str
    title: str
    publisher: str
    fact_summary: str
    question_ids: list[str]
    polarity: str
    exact_excerpt: str
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str
    start_unit: int
    end_unit: int
    period_fit: str
    ruler_attribution: str
    limitations: list[str]
    verification_status: str
    verification_notes: list[str]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(pattern=r"^[1-8]B\.10?$|^[1-8]B\.[1-9]$")
    question: str
    answer: str
    supporting_evidence_ids: list[str]
    qualifying_evidence_ids: list[str]
    limitations_and_gaps: list[str]


class PublicChapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    title: str
    score: float = Field(ge=1, le=10)
    confidence: float = Field(ge=0, le=100)
    plausible_lower: float = Field(ge=1, le=10)
    plausible_upper: float = Field(ge=1, le=10)
    rationale: str
    summary: str | None = None
    exposition: str | None = None
    ruler_attribution: str
    inherited_baseline_and_constraints: str
    lower_anchor_rejected: str
    higher_anchor_rejected: str
    missing_or_weak_lenses: list[str]
    manual_review_required: bool
    manual_review_reason: str | None
    questions: list[PublicQuestion]


class PublicRuler(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    ruler_name: str
    target_year: int
    chapters: list[PublicChapter]
    evidence: list[PublicEvidence]
    overall_mean: float
    shared_rank: int


class StudySiteProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["study_site_projection_v1"] = "study_site_projection_v1"
    run_id: str
    target_year: int
    audit_decision: str
    audit_path: str | None = None
    audit_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pipeline_version_id: str
    methodology_version_id: str
    rulers: list[PublicRuler]


__all__ = [
    "PublicChapter",
    "PublicEvidence",
    "PublicQuestion",
    "PublicRuler",
    "StudySiteProjection",
]
