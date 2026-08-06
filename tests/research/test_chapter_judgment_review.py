"""Bounded score-and-rationale review contract tests."""

from __future__ import annotations

from hashlib import sha256

import pytest

from leaders_db.research.chapter_judge_models import (
    ChapterJudgmentBatch,
    PlausibleScoreRange,
    RulerChapterJudgment,
)
from leaders_db.research.chapter_judgment_review import (
    ChapterJudgmentReview,
    JudgmentReviewDecision,
    apply_review,
    validate_review,
)


def _judgment() -> ChapterJudgmentBatch:
    evaluation = RulerChapterJudgment.model_construct(
        dossier_job_key="dossier:test:2023:AAA:1",
        score_1_to_10=6.0,
        plausible_score_range=PlausibleScoreRange(lower=5.5, upper=6.5),
        chapter_rationale="Original rationale.",
        lower_anchor_rejected="Original lower anchor.",
        higher_anchor_rejected="Original higher anchor.",
    )
    return ChapterJudgmentBatch.model_construct(
        job_key="chapter-judge:test:2023:1B",
        chapter_id="1B",
        evaluations=(evaluation,),
        batch_notes=(),
    )


def _review(*, reviewed_score: float = 5.0) -> ChapterJudgmentReview:
    return ChapterJudgmentReview(
        schema_version="chapter_judgment_review_v1",
        chapter_id="1B",
        source_job_key="chapter-judge:test:2023:1B",
        source_sha256=sha256(b"source").hexdigest(),
        reviewer_model="gpt-5.6-sol",
        reasoning_effort="high",
        decisions=(
            JudgmentReviewDecision(
                dossier_job_key="dossier:test:2023:AAA:1",
                original_score=6.0,
                reviewed_score=reviewed_score,
                disposition="decrease",
                review_explanation="The original over-credited inherited capacity.",
                supporting_evidence_ids=("E001",),
                revised_chapter_rationale="Revised evidence-balanced rationale.",
                revised_lower_anchor_rejected="A lower score is too severe.",
                revised_higher_anchor_rejected="A higher score over-credits the baseline.",
            ),
        ),
        chapter_review_summary="One score was corrected.",
    )


def test_review_rejects_score_change_greater_than_one() -> None:
    with pytest.raises(ValueError, match="plus or minus 1"):
        _review(reviewed_score=4.5)


def test_validated_review_updates_score_and_rationale() -> None:
    judgment = _judgment()
    review = _review()
    validate_review(
        review,
        judgment=judgment,
        source_sha256=sha256(b"source").hexdigest(),
        evidence_ids_by_job={"dossier:test:2023:AAA:1": {"E001"}},
    )

    revised = apply_review(judgment, review)

    evaluation = revised.evaluations[0]
    assert evaluation.score_1_to_10 == 5.0
    assert evaluation.plausible_score_range.lower == 5.0
    assert evaluation.chapter_rationale == "Revised evidence-balanced rationale."
    assert "bounded to ±1" in revised.batch_notes[-2]


def test_review_rejects_evidence_from_another_projection() -> None:
    with pytest.raises(ValueError, match="outside the ruler projection"):
        validate_review(
            _review(),
            judgment=_judgment(),
            source_sha256=sha256(b"source").hexdigest(),
            evidence_ids_by_job={"dossier:test:2023:AAA:1": {"E999"}},
        )
