"""Approval-boundary loading for deterministic question evidence packets."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .approved_ruler_package import ApprovedSelectionManifest
from .chapter_analysis_models import (
    ChapterAnalysisQuality,
    ChapterQualityReviewBinding,
    ResolvedChapterAnalysis,
)


def load_approved_selection(
    project_root: Path,
    manifest_path: Path,
    judge_package_path: Path,
    chapter_id: str,
) -> tuple[bytes, bytes, dict]:
    """Validate and load one chapter through the complete approval boundary."""

    manifest_bytes = manifest_path.read_bytes()
    selection = ApprovedSelectionManifest.model_validate_json(manifest_bytes)
    if not selection.complete_ruler_safe_for_judge_use or (
        selection.quality_review_contract != "independent-full-index-v1"
    ):
        raise ValueError("selection manifest is not approved for full-index judge use")
    chapter_ids = [item.chapter_id for item in selection.chapters]
    if len(chapter_ids) != len(set(chapter_ids)) or set(chapter_ids) != {
        f"{number}B" for number in range(1, 9)
    }:
        raise ValueError("approved selection must contain chapters 1B through 8B")
    reference = next(item for item in selection.chapters if item.chapter_id == chapter_id)
    analysis_bytes = _inside(
        project_root, manifest_path.parent / reference.analysis_path
    ).read_bytes()
    review_bytes = _inside(
        project_root, manifest_path.parent / reference.review_path
    ).read_bytes()
    binding_bytes = _inside(
        project_root, manifest_path.parent / reference.review_binding_path
    ).read_bytes()
    for payload, expected, label in (
        (analysis_bytes, reference.analysis_sha256, "analysis"),
        (review_bytes, reference.review_sha256, "review"),
        (binding_bytes, reference.review_binding_sha256, "review binding"),
    ):
        if sha256(payload).hexdigest() != expected:
            raise ValueError(f"selected {label} hash does not match approval manifest")
    analysis = ResolvedChapterAnalysis.model_validate_json(analysis_bytes)
    review = ChapterAnalysisQuality.model_validate_json(review_bytes)
    binding = ChapterQualityReviewBinding.model_validate_json(binding_bytes)
    if analysis.chapter_id != chapter_id or review.chapter_id != chapter_id:
        raise ValueError("approved artifact chapter identity mismatch")
    lens_ids = [item.question_id for item in review.lens_quality]
    if len(lens_ids) != 10 or set(lens_ids) != {
        f"{chapter_id}.{number}" for number in range(1, 11)
    }:
        raise ValueError("approved review must cover the chapter's ten questions once")
    current_corpus_hash = sha256(judge_package_path.read_bytes()).hexdigest()
    if not review.safe_for_judge_use or (
        binding.contract != "independent-full-index-v1"
        or binding.chapter_id != chapter_id
        or binding.analysis_sha256 != reference.analysis_sha256
        or binding.review_sha256 != reference.review_sha256
        or binding.judge_package_sha256 != current_corpus_hash
    ):
        raise ValueError("review binding does not match current approved artifacts")
    return manifest_bytes, analysis_bytes, analysis.model_dump(mode="json")


def _inside(project_root: Path, path: Path) -> Path:
    root = project_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("approved artifact path escapes the project root")
    return resolved


__all__ = ["load_approved_selection"]
