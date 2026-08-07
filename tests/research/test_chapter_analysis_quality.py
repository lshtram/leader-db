"""Tests for independent chapter-analysis quality aggregation."""

import hashlib

from leaders_db.research.chapter_analysis_models import (
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    ChapterAnalysisQualityShard,
    ChapterQualityReviewBinding,
    LensQuality,
    ResolvedChapterAnalysis,
)
from leaders_db.research.chapter_analysis_quality import (
    _combine_quality_shards,
    _quality_candidate,
    _write_review_binding,
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


def test_quality_review_producer_binds_exact_analysis_review_and_package(tmp_path) -> None:
    analysis_path = tmp_path / "analysis.json"
    review_path = tmp_path / "review.json"
    package_path = tmp_path / "package.json"
    analysis = ResolvedChapterAnalysis(
        chapter_id="1B",
        answers=(),
        evidence=(),
        omitted_candidate_ids=(),
        draft=ChapterAnalysisDraft(chapter_id="1B", answers=()),
        critique=ChapterAnalysisCritique(
            chapter_id="1B",
            issues=(),
            overall_assessment="No issues in this synthetic boundary fixture.",
        ),
    )
    analysis_path.write_text(analysis.model_dump_json(), encoding="utf-8")
    review_path.write_text("review output", encoding="utf-8")
    package_path.write_text("full candidate index", encoding="utf-8")

    binding_path = _write_review_binding(
        analysis_path, package_path, review_path, tmp_path
    )
    binding = ChapterQualityReviewBinding.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )

    assert binding.contract == "independent-full-index-v1"
    assert binding.analysis_sha256 == hashlib.sha256(
        analysis_path.read_bytes()
    ).hexdigest()
    assert binding.review_sha256 == hashlib.sha256(review_path.read_bytes()).hexdigest()
    assert binding.judge_package_sha256 == hashlib.sha256(
        package_path.read_bytes()
    ).hexdigest()
