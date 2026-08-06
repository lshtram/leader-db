from leaders_db.research.evidence_review import EvidenceReviewReport
from leaders_db.research.partitioned_evidence_review import _merge_chapter_reviews


def _report(chapter_id: str, *, continue_research: bool) -> EvidenceReviewReport:
    return EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": continue_research,
            "selected_theme_ids": [chapter_id] if continue_research else [],
            "chapter_reviews": [
                {
                    "chapter_id": chapter_id,
                    "defensible_evidence_estimate": 7,
                    "independent_source_family_estimate": 4,
                    "attribution_risk": "medium",
                    "substantive_issues": [],
                    "missing_themes": [],
                }
            ],
            "global_findings": [f"{chapter_id} reviewed"],
            "reviewer_summary": f"{chapter_id} summary.",
        }
    )


def test_merge_preserves_each_chapter_and_continuation_decision() -> None:
    merged = _merge_chapter_reviews(
        [_report("1B", continue_research=False), _report("2B", continue_research=True)]
    )

    assert tuple(review.chapter_id for review in merged.chapter_reviews) == ("1B", "2B")
    assert merged.needs_continuation is True
    assert merged.selected_theme_ids == ("2B",)
    assert merged.global_findings == ("1B reviewed", "2B reviewed")


def test_merge_terminal_chapters_does_not_request_continuation() -> None:
    merged = _merge_chapter_reviews(
        [_report("1B", continue_research=False), _report("2B", continue_research=False)]
    )

    assert merged.needs_continuation is False
    assert merged.selected_theme_ids == ()
