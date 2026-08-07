"""Contracts for question-complete chapter evidence analysis and quality review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .corpus_reader_models import BoundEvidence


class LensAnswer(BaseModel):
    """Evidence-based answer to one chapter lens without a score."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: str = Field(min_length=30)
    supporting_evidence_ids: tuple[str, ...]
    contrary_or_qualifying_evidence_ids: tuple[str, ...]
    limitations_and_gaps: tuple[str, ...] = ()


class ChapterAnalysisDraft(BaseModel):
    """Initial answers to all ten chapter lenses."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    answers: tuple[LensAnswer, ...]
    cross_lens_observations: tuple[str, ...] = ()


class AnswerCritiqueIssue(BaseModel):
    """Specific defect or omission in one drafted answer."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    issue_type: Literal[
        "unsupported_claim",
        "material_omission",
        "misleading_weight",
        "period_error",
        "attribution_error",
        "missing_contrary_evidence",
        "irrelevant_evidence",
    ]
    evidence_ids: tuple[str, ...]
    explanation: str = Field(min_length=8)


class ChapterAnalysisCritique(BaseModel):
    """Independent challenge against the complete chapter candidate index."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    issues: tuple[AnswerCritiqueIssue, ...]
    overall_assessment: str = Field(min_length=20)


class QuestionCritique(BaseModel):
    """Fresh challenge to one question answer against the full chapter index."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    issues: tuple[AnswerCritiqueIssue, ...]
    overall_assessment: str = Field(min_length=20)


class CorrectedLensAnswer(BaseModel):
    """One answer corrected after exact-passage review."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: str = Field(min_length=30)
    supporting_evidence_ids: tuple[str, ...]
    contrary_or_qualifying_evidence_ids: tuple[str, ...]
    limitations_and_gaps: tuple[str, ...] = ()
    corrections_made: tuple[str, ...] = ()
    reasons_to_reopen_full_ledger: tuple[str, ...] = ()


class ResolvedChapterAnalysis(BaseModel):
    """Question-complete analysis with code-resolved evidence and audit history."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["resolved_chapter_evidence_analysis_v1"] = (
        "resolved_chapter_evidence_analysis_v1"
    )
    chapter_id: str
    answers: tuple[CorrectedLensAnswer, ...]
    evidence: tuple[BoundEvidence, ...]
    omitted_candidate_ids: tuple[str, ...]
    draft: ChapterAnalysisDraft
    critique: ChapterAnalysisCritique


class SelfReviewedChapterAnalysis(BaseModel):
    """One-call Luna result containing its draft audit and corrected answers."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    draft: ChapterAnalysisDraft
    critique: ChapterAnalysisCritique
    corrected_answers: tuple[CorrectedLensAnswer, ...]


class ChapterEvidenceShard(BaseModel):
    """Question-organized findings from one exact-evidence context shard."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    shard_id: str
    reviewed_evidence_ids: tuple[str, ...]
    answers: tuple[LensAnswer, ...]
    cross_shard_cautions: tuple[str, ...] = ()


class QuestionAnalysisTrace(BaseModel):
    """Draft, critique, and corrected answer for one question."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    draft: LensAnswer
    critique: QuestionCritique
    corrected: CorrectedLensAnswer


class QuestionWorkflowTurn(BaseModel):
    """One fixed-schema turn so all question calls retain a cacheable prefix."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal["answer", "critique", "correction"]
    question_id: str
    answer: LensAnswer | None = None
    critique: QuestionCritique | None = None
    corrected: CorrectedLensAnswer | None = None


class QuestionFocusedChapterAnalysis(BaseModel):
    """Ten independently corrected answers sharing one complete evidence prefix."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_focused_chapter_analysis_v1"] = (
        "question_focused_chapter_analysis_v1"
    )
    chapter_id: str
    traces: tuple[QuestionAnalysisTrace, ...]
    evidence: tuple[BoundEvidence, ...]
    omitted_candidate_ids: tuple[str, ...]
    shared_prefix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LensQuality(BaseModel):
    """Independent assessment of one answer's usefulness and reliability."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    factual_support_1_to_5: int = Field(ge=1, le=5)
    completeness_1_to_5: int = Field(ge=1, le=5)
    balance_1_to_5: int = Field(ge=1, le=5)
    attribution_and_period_1_to_5: int = Field(ge=1, le=5)
    judge_usefulness_1_to_5: int = Field(ge=1, le=5)
    material_errors: tuple[str, ...] = ()
    material_omissions: tuple[str, ...] = ()


class ChapterAnalysisQuality(BaseModel):
    """Independent, non-scoring quality verdict on a produced chapter analysis."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    lens_quality: tuple[LensQuality, ...]
    overall_verdict: Literal["pass", "pass_with_corrections", "fail"]
    strengths: tuple[str, ...]
    systemic_problems: tuple[str, ...]
    concrete_corrections_required: tuple[str, ...]
    safe_for_judge_use: bool
    rationale: str = Field(min_length=30)


class ChapterAnalysisQualityShard(BaseModel):
    """Independent quality verdict for five answers with full-index access."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    question_ids: tuple[str, ...]
    lens_quality: tuple[LensQuality, ...]
    verdict: Literal["pass", "pass_with_corrections", "fail"]
    strengths: tuple[str, ...]
    systemic_problems: tuple[str, ...]
    concrete_corrections_required: tuple[str, ...]
    safe_for_judge_use: bool
    rationale: str = Field(min_length=30)


class ChapterQualityReviewBinding(BaseModel):
    """Hash-bound inputs and output recorded by the independent quality reviewer."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["independent-full-index-v1"]
    chapter_id: str
    analysis_sha256: str
    judge_package_sha256: str
    review_sha256: str


__all__ = [
    "ChapterAnalysisCritique",
    "ChapterAnalysisDraft",
    "ChapterAnalysisQuality",
    "ChapterAnalysisQualityShard",
    "ChapterEvidenceShard",
    "ChapterQualityReviewBinding",
    "CorrectedLensAnswer",
    "QuestionCritique",
    "QuestionFocusedChapterAnalysis",
    "QuestionWorkflowTurn",
    "ResolvedChapterAnalysis",
    "SelfReviewedChapterAnalysis",
]
