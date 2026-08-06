"""Deterministic integrity and revision controls for chapter analyses."""

from __future__ import annotations

import json
from pathlib import Path

from .chapter_analysis_models import (
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    ChapterAnalysisQuality,
    CorrectedLensAnswer,
    ResolvedChapterAnalysis,
)


def strip_invalid_draft_ids(
    draft: ChapterAnalysisDraft, evidence_ids: set[str]
) -> ChapterAnalysisDraft:
    removed = sorted(
        {
            evidence_id
            for answer in draft.answers
            for evidence_id in (
                answer.supporting_evidence_ids
                + answer.contrary_or_qualifying_evidence_ids
            )
            if evidence_id not in evidence_ids
        }
    )
    answers = tuple(
        answer.model_copy(
            update={
                "supporting_evidence_ids": tuple(
                    item for item in answer.supporting_evidence_ids if item in evidence_ids
                ),
                "contrary_or_qualifying_evidence_ids": tuple(
                    item
                    for item in answer.contrary_or_qualifying_evidence_ids
                    if item in evidence_ids
                ),
            }
        )
        for answer in draft.answers
    )
    observation = (
        "Code removed invalid evidence references after three failed identity retries: "
        + ", ".join(removed)
    )
    return draft.model_copy(
        update={
            "answers": answers,
            "cross_lens_observations": (
                *draft.cross_lens_observations,
                observation,
            ),
        }
    )


def strip_invalid_critique_ids(
    critique: ChapterAnalysisCritique, evidence_ids: set[str]
) -> ChapterAnalysisCritique:
    removed = sorted(
        {
            evidence_id
            for issue in critique.issues
            for evidence_id in issue.evidence_ids
            if evidence_id not in evidence_ids
        }
    )
    issues = tuple(
        issue.model_copy(
            update={
                "evidence_ids": tuple(
                    item for item in issue.evidence_ids if item in evidence_ids
                )
            }
        )
        for issue in critique.issues
    )
    assessment = critique.overall_assessment
    if removed:
        assessment += " Code removed invalid evidence references: " + ", ".join(
            removed
        )
    return critique.model_copy(
        update={"issues": issues, "overall_assessment": assessment}
    )


def strip_invalid_corrected_ids(
    answer: CorrectedLensAnswer, evidence_ids: set[str]
) -> CorrectedLensAnswer:
    removed = sorted(
        (
            set(answer.supporting_evidence_ids)
            | set(answer.contrary_or_qualifying_evidence_ids)
        )
        - evidence_ids
    )
    return answer.model_copy(
        update={
            "supporting_evidence_ids": tuple(
                item for item in answer.supporting_evidence_ids if item in evidence_ids
            ),
            "contrary_or_qualifying_evidence_ids": tuple(
                item
                for item in answer.contrary_or_qualifying_evidence_ids
                if item in evidence_ids
            ),
            "corrections_made": (
                *answer.corrections_made,
                "Code removed evidence IDs not reopened for exact-passage correction: "
                + ", ".join(removed),
            ),
        }
    )


def revision_context(
    chapter_id: str,
    *,
    prior_analysis_path: Path | None,
    quality_review_path: Path | None,
) -> str:
    if prior_analysis_path is None and quality_review_path is None:
        return ""
    if prior_analysis_path is None or quality_review_path is None:
        raise ValueError("chapter revision requires both prior analysis and quality review")
    prior = ResolvedChapterAnalysis.model_validate_json(
        prior_analysis_path.read_text(encoding="utf-8")
    )
    review = ChapterAnalysisQuality.model_validate_json(
        quality_review_path.read_text(encoding="utf-8")
    )
    if prior.chapter_id != chapter_id or review.chapter_id != chapter_id:
        raise ValueError("chapter revision inputs do not match the requested chapter")
    prior_answers = [item.model_dump(mode="json") for item in prior.answers]
    return (
        "\n\nPRIOR ATTEMPT AND INDEPENDENT QUALITY REVIEW. Produce a fresh answer, "
        "correct every supported finding, and do not repeat identified errors.\n"
        f"PRIOR ANSWERS:\n{json.dumps(prior_answers, ensure_ascii=False)}\n"
        f"QUALITY REVIEW:\n{review.model_dump_json()}"
    )


__all__ = [
    "revision_context",
    "strip_invalid_corrected_ids",
    "strip_invalid_critique_ids",
    "strip_invalid_draft_ids",
]
