"""Tests for independent chapter-analysis quality aggregation."""

from leaders_db.research.chapter_analysis_models import (
    ChapterAnalysisQualityShard,
    LensQuality,
)
from leaders_db.research.chapter_analysis_quality import (
    _combine_quality_shards,
    _quality_candidate,
)
from tests.research.test_corpus_mapping_review import _evidence


def _shard(question_id: str, verdict: str, safe: bool) -> ChapterAnalysisQualityShard:
    return ChapterAnalysisQualityShard(
        chapter_id="8B",
        question_ids=(question_id,),
        lens_quality=(
            LensQuality(
                question_id=question_id,
                factual_support_1_to_5=4,
                completeness_1_to_5=3,
                balance_1_to_5=4,
                attribution_and_period_1_to_5=4,
                judge_usefulness_1_to_5=3,
            ),
        ),
        verdict=verdict,
        strengths=("Passage-supported synthesis",),
        systemic_problems=(),
        concrete_corrections_required=(),
        safe_for_judge_use=safe,
        rationale="A sufficiently detailed independent quality rationale.",
    )


def test_quality_combination_uses_conservative_verdict() -> None:
    quality = _combine_quality_shards(
        "8B",
        (
            _shard("8B.1", "pass", True),
            _shard("8B.2", "fail", False),
        ),
    )

    assert quality.overall_verdict == "fail"
    assert not quality.safe_for_judge_use


def test_quality_candidate_is_compact_but_period_aware() -> None:
    evidence = _evidence("E-1", "One material fact")

    candidate = _quality_candidate(evidence)

    assert set(candidate) == {"evidence_id", "fact_summary", "publisher", "period_fit"}
