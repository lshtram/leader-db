"""Validated batch handoff for one chapter judge."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dossier_models import DossierUsage

ManualReviewReasonType = Literal[
    "identity",
    "projection_integrity",
    "decisive_source",
    "material_attribution",
    "recoverable_null",
    "calibration_inconsistency",
]


class ChapterEvidenceReference(BaseModel):
    """Reference to evidence already present in the ruler dossier."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: str = Field(pattern=r"^E[0-9]{3,}$")
    explanation: str = Field(min_length=1)


class ChapterSpecificFinding(BaseModel):
    """Guide-specific value preserved without changing the common envelope."""

    model_config = ConfigDict(extra="ignore")

    field: str = Field(min_length=1)
    value: str = Field(min_length=1)


class PlausibleScoreRange(BaseModel):
    """Uncertainty interval around a chapter judgment."""

    model_config = ConfigDict(extra="ignore")

    lower: float = Field(ge=1, le=10)
    upper: float = Field(ge=1, le=10)

    @model_validator(mode="after")
    def _ordered(self) -> PlausibleScoreRange:
        if self.lower > self.upper:
            raise ValueError("plausible score range must be ordered")
        return self


class MaterialBiasFinding(BaseModel):
    """One material evidence distortion considered by the chapter judge."""

    model_config = ConfigDict(extra="forbid")

    bias: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...] = Field(min_length=1)
    likely_direction: Literal[
        "favors_ruler", "harms_ruler", "mixed", "uncertain"
    ]
    interpretation_effect: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_support_ids(self) -> MaterialBiasFinding:
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("bias support IDs must be unique")
        if any(not item.startswith("E") for item in self.supporting_evidence_ids):
            raise ValueError("bias findings must cite dossier evidence IDs")
        return self


class BiasAssessment(BaseModel):
    """Auditable interpretation of reporting and comparison bias."""

    model_config = ConfigDict(extra="forbid")

    material_biases: tuple[MaterialBiasFinding, ...]
    confidence_and_range_effect: str = Field(min_length=1)
    remaining_uncertainty: str = Field(min_length=1)
    report_volume_not_used_as_severity: bool
    no_blanket_regime_correction: bool


class RulerChapterJudgment(BaseModel):
    """One holistic chapter score for one ruler-period dossier."""

    model_config = ConfigDict(extra="ignore")

    dossier_job_key: str = Field(min_length=1)
    iso3: str = Field(min_length=3, max_length=3)
    ruler_id: str
    ruler_year_id: int
    ruler_name: str = Field(min_length=1)
    period_start_year: int
    period_end_year: int
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    rubric_version: str = Field(min_length=1)
    calibration_batch_id: str = Field(min_length=1)
    calibrated_against: tuple[str, ...]
    score_1_to_10: float | None = Field(default=None, ge=1, le=10, multiple_of=0.5)
    insufficient_evidence_reason: str | None = None
    confidence_score: float = Field(ge=0, le=100)
    plausible_score_range: PlausibleScoreRange
    decisive_positive_evidence: tuple[ChapterEvidenceReference, ...] = ()
    decisive_negative_evidence: tuple[ChapterEvidenceReference, ...] = ()
    inherited_baseline_and_constraints: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    supported_lenses: tuple[str, ...] = ()
    missing_or_weak_lenses: tuple[str, ...] = ()
    contrary_evidence: tuple[ChapterEvidenceReference, ...] = ()
    source_mix: str = Field(min_length=1)
    structured_prior_summary: str = Field(min_length=1)
    bias_assessment: BiasAssessment
    chapter_rationale: str = Field(min_length=1)
    lower_anchor_rejected: str = Field(min_length=1)
    higher_anchor_rejected: str = Field(min_length=1)
    manual_review_required: bool
    manual_review_reason_type: ManualReviewReasonType | None = None
    manual_review_reason: str | None = None
    chapter_specific: tuple[ChapterSpecificFinding, ...] = ()

    @model_validator(mode="after")
    def _score_and_review_are_coherent(self) -> RulerChapterJudgment:
        if self.score_1_to_10 is None and not self.insufficient_evidence_reason:
            raise ValueError("a missing score requires insufficient_evidence_reason")
        if self.score_1_to_10 is None and (
            self.plausible_score_range.lower != 1
            or self.plausible_score_range.upper != 10
        ):
            raise ValueError("a missing score requires the full 1-10 uncertainty range")
        if self.score_1_to_10 is not None and self.insufficient_evidence_reason:
            raise ValueError("a scored judgment cannot claim insufficient evidence")
        if self.score_1_to_10 is not None and not (
            self.decisive_positive_evidence or self.decisive_negative_evidence
        ):
            raise ValueError("a scored judgment requires decisive evidence")
        if (
            self.score_1_to_10 is not None
            and self.manual_review_reason_type == "recoverable_null"
        ):
            raise ValueError("a scored judgment cannot use recoverable_null")
        if self.score_1_to_10 is not None and not (
            self.plausible_score_range.lower
            <= self.score_1_to_10
            <= self.plausible_score_range.upper
        ):
            raise ValueError("score must fall inside its plausible range")
        if self.manual_review_required and not self.manual_review_reason:
            raise ValueError("manual review requires a reason")
        if self.manual_review_required and not self.manual_review_reason_type:
            raise ValueError("manual review requires a reason type")
        if not self.manual_review_required and self.manual_review_reason_type:
            raise ValueError("manual review reason type requires manual review")
        supported = list(self.supported_lenses)
        missing = list(self.missing_or_weak_lenses)
        expected = {f"{self.chapter_id}.{index}" for index in range(1, 11)}
        if len(supported) != len(set(supported)) or len(missing) != len(set(missing)):
            raise ValueError("lens lists must not contain duplicates")
        if not set(supported + missing).issubset(expected):
            raise ValueError("lens lists must contain only the judged chapter's lenses")
        if set(supported).intersection(missing):
            raise ValueError("supported and missing/weak lenses must be disjoint")
        return self


class ChapterJudgeRunProfile(BaseModel):
    """Auditable provider and usage metadata for the judge batch."""

    model_config = ConfigDict(extra="ignore")

    provider_profile: str
    provider: str
    model: str
    dossier_count: int = Field(ge=1)
    unavailable_dossier_count: int = Field(ge=0)
    usage: DossierUsage


class UnavailableDossier(BaseModel):
    """Explicit terminal dossier omission carried into the judge result."""

    model_config = ConfigDict(extra="ignore")

    job_key: str
    status: str
    iso3: str | None = None
    ruler_name: str | None = None


class ChapterJudgmentBatch(BaseModel):
    """Complete output from one chapter judge job."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["ruler_chapter_judgment_v1"]
    job_key: str
    run_key: str
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    target_year: int
    rubric_version: str
    calibration_batch_id: str
    evaluations: tuple[RulerChapterJudgment, ...] = Field(min_length=1)
    unavailable_dossiers: tuple[UnavailableDossier, ...] = ()
    batch_notes: tuple[str, ...] = ()
    run_profile: ChapterJudgeRunProfile


def codex_chapter_judgment_json_schema() -> dict[str, Any]:
    """Return a Codex-compatible schema with every property required."""

    schema = ChapterJudgmentBatch.model_json_schema()
    _remove_server_owned_usage_fields(schema)
    _require_every_property(schema)
    return schema


def _remove_server_owned_usage_fields(schema: dict[str, Any]) -> None:
    usage = schema.get("$defs", {}).get("DossierUsage", {})
    properties = usage.get("properties")
    if not isinstance(properties, dict):
        return
    model_fields = {"input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd"}
    for field_name in tuple(properties):
        if field_name not in model_fields:
            properties.pop(field_name)


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
    "ChapterJudgmentBatch",
    "RulerChapterJudgment",
    "codex_chapter_judgment_json_schema",
]
