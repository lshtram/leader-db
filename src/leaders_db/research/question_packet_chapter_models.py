"""Manifest schemas for straight-through chapter question phases."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChapterQuestionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["pass", "fail", "unavailable"]


class QuestionUnavailableArtifact(BaseModel):
    """Deterministic non-answer for a lens with no admissible evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_unavailable_v1"] = "question_unavailable_v1"
    question_id: str
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjudication_path: str = Field(min_length=1)
    adjudication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["no_admissible_evidence"] = "no_admissible_evidence"
    model_call_created: Literal[False] = False
    review_required: Literal[False] = False
    confidence_effect: Literal["missing_lens_lowers_confidence"] = (
        "missing_lens_lowers_confidence"
    )


class QuestionEvidenceUnavailableAdjudication(BaseModel):
    """Trusted proof that targeted research found no admissible lens evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_evidence_unavailable_adjudication_v1"] = (
        "question_evidence_unavailable_adjudication_v1"
    )
    question_id: str
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    research_inventory_path: str = Field(min_length=1)
    research_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    targeted_search_manifest_path: str = Field(min_length=1)
    targeted_search_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_review_path: str = Field(min_length=1)
    independent_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    targeted_query_count: int = Field(ge=1)
    inspected_source_count: int = Field(ge=1)
    admissible_evidence_count: Literal[0] = 0
    saturation_review: Literal["pass"] = "pass"
    decision: Literal["no_admissible_evidence"] = "no_admissible_evidence"


class QuestionResearchInventory(BaseModel):
    """Machine-readable inventory reviewed before a no-evidence adjudication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_research_inventory_v1"] = (
        "question_research_inventory_v1"
    )
    question_id: str
    source_ids: tuple[str, ...] = Field(min_length=1)
    admissible_evidence_ids: tuple[()] = ()


class QuestionTargetedSearchManifest(BaseModel):
    """Search saturation record for a single unresolved question lens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_targeted_search_manifest_v1"] = (
        "question_targeted_search_manifest_v1"
    )
    question_id: str
    queries: tuple[str, ...] = Field(min_length=1)
    inspected_urls: tuple[str, ...] = Field(min_length=1)
    saturation_review: Literal["pass"] = "pass"


class QuestionUnavailableIndependentReview(BaseModel):
    """Independent no-search review of the exact search and evidence inventories."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_unavailable_independent_review_v1"] = (
        "question_unavailable_independent_review_v1"
    )
    question_id: str
    research_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    targeted_search_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    admissible_evidence_count: Literal[0] = 0
    review_gate: Literal["pass"] = "pass"


class UnresolvedQuestionReopen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    question_id: str
    answer_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class QuestionReviewReopenStopManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_review_reopen_stop_v1"] = (
        "question_review_reopen_stop_v1"
    )
    production_status: Literal["diagnostic_only"] = "diagnostic_only"
    api_key_used: Literal[False] = False
    writing_manifest_sha256s: dict[str, str]
    unresolved: tuple[UnresolvedQuestionReopen, ...] = Field(min_length=1)
    review_calls_launched: Literal[0] = 0
    phase_gate: Literal["fail"] = "fail"

    @model_validator(mode="after")
    def validate_bindings(self) -> QuestionReviewReopenStopManifest:
        chapters = {item.chapter_id for item in self.unresolved}
        if not chapters.issubset(self.writing_manifest_sha256s) or any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in self.writing_manifest_sha256s.values()
        ):
            raise ValueError("reopen stop must hash-bind every affected writing manifest")
        question_ids = [item.question_id for item in self.unresolved]
        if len(question_ids) != len(set(question_ids)) or any(
            not item.question_id.startswith(f"{item.chapter_id}.")
            or len(item.evidence_ids) != len(set(item.evidence_ids))
            for item in self.unresolved
        ):
            raise ValueError("reopen stop contains inconsistent or duplicate identities")
        return self


class ChapterQuestionPhaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "diagnostic_chapter_question_writing_v1",
        "diagnostic_chapter_question_review_v1",
    ]
    production_status: Literal["diagnostic_only"] = "diagnostic_only"
    api_key_used: Literal[False] = False
    chapter_id: str
    profile: str
    model: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_analysis_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    writing_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    experiment_policy_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    question_count: int = Field(ge=1)
    artifacts: tuple[ChapterQuestionArtifact, ...]
    phase_gate: Literal["pass", "fail"]

    @model_validator(mode="after")
    def validate_artifacts(self) -> ChapterQuestionPhaseManifest:
        if (
            self.schema_version == "diagnostic_chapter_question_writing_v1"
            and self.experiment_policy_sha256 is not None
        ):
            raise ValueError("question writing cannot bind a review experiment policy")
        ids = [item.question_id for item in self.artifacts]
        expected = [f"{self.chapter_id}.{number}" for number in range(1, 11)]
        if ids != expected or self.question_count != 10:
            raise ValueError("chapter phase must contain questions 1 through 10 once")
        expected_gate = (
            "pass"
            if all(item.status in {"pass", "unavailable"} for item in self.artifacts)
            else "fail"
        )
        if self.phase_gate != expected_gate:
            raise ValueError("chapter phase gate contradicts question statuses")
        return self


__all__ = [
    "ChapterQuestionArtifact",
    "ChapterQuestionPhaseManifest",
    "QuestionEvidenceUnavailableAdjudication",
    "QuestionResearchInventory",
    "QuestionReviewReopenStopManifest",
    "QuestionTargetedSearchManifest",
    "QuestionUnavailableArtifact",
    "QuestionUnavailableIndependentReview",
    "UnresolvedQuestionReopen",
]
