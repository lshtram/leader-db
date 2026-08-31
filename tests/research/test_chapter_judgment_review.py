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
from leaders_db.research.comparative_judgment_review_phase import _review_contract


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

    revised = apply_review(judgment, review, preserve_prose_on_retain=True)

    evaluation = revised.evaluations[0]
    assert evaluation.score_1_to_10 == 5.0
    assert evaluation.plausible_score_range.lower == 5.0
    assert evaluation.chapter_rationale == "Revised evidence-balanced rationale."
    assert "bounded to ±1" in revised.batch_notes[-2]


def test_retained_score_preserves_calibrated_reader_facing_prose() -> None:
    judgment = _judgment()
    decision = _review().decisions[0].model_copy(
        update={
            "reviewed_score": 6.0,
            "disposition": "retain",
            "revised_chapter_rationale": "Compressed finding under E001.",
            "revised_lower_anchor_rejected": "Compressed lower anchor.",
            "revised_higher_anchor_rejected": "Compressed higher anchor.",
        }
    )
    review = _review().model_copy(update={"decisions": (decision,)})

    revised = apply_review(judgment, review, preserve_prose_on_retain=True)

    evaluation = revised.evaluations[0]
    assert evaluation.chapter_rationale == "Original rationale."
    assert evaluation.lower_anchor_rejected == "Original lower anchor."
    assert evaluation.higher_anchor_rejected == "Original higher anchor."


def test_legacy_retained_review_reconstructs_reviewer_prose() -> None:
    judgment = _judgment()
    decision = _review().decisions[0].model_copy(
        update={"reviewed_score": 6.0, "disposition": "retain"}
    )
    review = _review().model_copy(update={"decisions": (decision,)})

    revised = apply_review(judgment, review)

    assert revised.evaluations[0].chapter_rationale == "Revised evidence-balanced rationale."


def test_reader_exposition_policy_applies_two_level_prose_on_retain() -> None:
    judgment = _judgment()
    decision = _review().decisions[0].model_copy(
        update={
            "reviewed_score": 6.0,
            "disposition": "retain",
            "reader_summary": "A short answer for a new reader.",
            "reader_exposition": (
                "The year began under inherited conditions.\n\n"
                "A major event affected the public.\n\n"
                "The ruler made an attributable choice.\n\n"
                "That record explains the score."
            ),
        }
    )
    review = _review().model_copy(
        update={"schema_version": "chapter_judgment_review_v2", "decisions": (decision,)}
    )

    revised = apply_review(judgment, review, apply_reader_exposition=True)

    assert revised.evaluations[0].chapter_rationale == (
        "[[reader_summary_and_exposition_v1]]\n"
        "A short answer for a new reader.\n\n"
        "The year began under inherited conditions.\n\n"
        "A major event affected the public.\n\n"
        "The ruler made an attributable choice.\n\n"
        "That record explains the score."
    )


def test_reader_exposition_changed_score_updates_calibration_anchors() -> None:
    decision = _review().decisions[0].model_copy(
        update={
            "reader_summary": "A short answer.",
            "reader_exposition": "Context.\n\nEvent.\n\nConduct.\n\nScoring consequence.",
        }
    )
    review = _review().model_copy(
        update={"schema_version": "chapter_judgment_review_v2", "decisions": (decision,)}
    )

    revised = apply_review(_judgment(), review, apply_reader_exposition=True)

    evaluation = revised.evaluations[0]
    assert evaluation.lower_anchor_rejected == "A lower score is too severe."
    assert evaluation.higher_anchor_rejected == "A higher score over-credits the baseline."


def test_reader_facing_policy_uses_fresh_roots_and_fails_closed() -> None:
    request = {"application_policy": "preserve_calibrated_prose_on_retain_v1"}
    contract = _review_contract(
        {
            "schema_version": "comparative_judgment_review_preflight_v4",
            "requests": [request],
        }
    )
    assert contract == (
        "comparative-judgment-reviews-v4",
        "comparative-judgment-review-v4-usage.json",
        "comparative-judgment-review-v4-stage-usage.json",
        True,
        False,
    )

    reader_contract = _review_contract(
        {
            "schema_version": "comparative_judgment_review_preflight_v5",
            "requests": [{"application_policy": "reader_summary_and_exposition_v1"}],
        }
    )
    assert reader_contract == (
        "comparative-judgment-reviews-v5",
        "comparative-judgment-review-v5-usage.json",
        "comparative-judgment-review-v5-stage-usage.json",
        False,
        True,
    )

    request["application_policy"] = "unknown"
    with pytest.raises(ValueError, match="unknown application policy"):
        _review_contract(
            {
                "schema_version": "comparative_judgment_review_preflight_v4",
                "requests": [request],
            }
        )


def test_review_rejects_evidence_from_another_projection() -> None:
    with pytest.raises(ValueError, match="outside the ruler projection"):
        validate_review(
            _review(),
            judgment=_judgment(),
            source_sha256=sha256(b"source").hexdigest(),
            evidence_ids_by_job={"dossier:test:2023:AAA:1": {"E999"}},
        )
