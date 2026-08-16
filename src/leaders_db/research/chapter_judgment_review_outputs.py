"""Aggregate outputs for independently reviewed chapter judgments."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from .chapter_judge_models import ChapterJudgmentBatch
from .chapter_judgment_review import ChapterJudgmentReview


def sum_usage(results: tuple[dict[str, Any], ...]) -> dict[str, int]:
    """Sum available usage counters across reviewed chapters."""

    fields = (
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    )
    return {
        field: sum(
            int(item["usage"][field])
            for item in results
            if item["usage"] is not None and isinstance(item["usage"].get(field), int)
        )
        for field in fields
    }


def write_reviewed_package(*, output_dir: Path, results: tuple[dict[str, Any], ...]) -> Path:
    """Assemble reviewed chapters and their immutable correction ledger."""

    chapters = []
    corrections = []
    evaluation_count = 0
    ruler_keys: set[tuple[str, int]] = set()
    expected_ruler_keys: set[tuple[str, int]] | None = None
    for item in sorted(results, key=lambda value: value["chapter_id"]):
        judgment_path = Path(item["reviewed_judgment"])
        review_path = Path(item["review"])
        judgment = ChapterJudgmentBatch.model_validate_json(
            judgment_path.read_text(encoding="utf-8")
        )
        review = ChapterJudgmentReview.model_validate_json(review_path.read_text(encoding="utf-8"))
        evaluation_count += len(judgment.evaluations)
        chapter_ruler_keys = {
            (evaluation.dossier_job_key, evaluation.ruler_year_id)
            for evaluation in judgment.evaluations
        }
        if expected_ruler_keys is None:
            expected_ruler_keys = chapter_ruler_keys
        elif chapter_ruler_keys != expected_ruler_keys:
            raise ValueError("reviewed chapters do not share one ruler cohort")
        ruler_keys.update(chapter_ruler_keys)
        corrections.extend(
            {
                "chapter_id": review.chapter_id,
                "dossier_job_key": decision.dossier_job_key,
                "original_score": decision.original_score,
                "reviewed_score": decision.reviewed_score,
                "disposition": decision.disposition,
                "review_explanation": decision.review_explanation,
            }
            for decision in review.decisions
            if decision.disposition != "retain"
        )
        chapters.append(
            {
                "chapter_id": judgment.chapter_id,
                "reviewed_artifact": str(judgment_path),
                "reviewed_sha256": sha256(judgment_path.read_bytes()).hexdigest(),
                "review_artifact": str(review_path),
                "review_sha256": sha256(review_path.read_bytes()).hexdigest(),
                "judgment": judgment.model_dump(mode="json"),
            }
        )
    expected_evaluations = len(chapters) * len(expected_ruler_keys or ())
    if len(chapters) != 8 or not expected_ruler_keys or evaluation_count != expected_evaluations:
        raise ValueError(
            "reviewed package requires eight chapters with one consistent ruler cohort"
        )
    package_path = output_dir / "reviewed-judge-package.json"
    package_path.write_text(
        json.dumps(
            {
                "schema_version": "reviewed_ruler_judge_package_v1",
                "reviewer_model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "chapter_count": len(chapters),
                "evaluation_count": evaluation_count,
                "ruler_count": len(ruler_keys),
                "score_correction_count": len(corrections),
                "score_corrections": corrections,
                "chapters": chapters,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return package_path
