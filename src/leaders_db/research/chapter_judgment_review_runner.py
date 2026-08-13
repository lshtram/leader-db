"""Run high-reasoning Sol reviews over completed chapter judgments."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

from ._codex_worker_artifacts import read_codex_usage
from .chapter_judge_models import ChapterJudgmentBatch
from .chapter_judgment_review import (
    ChapterJudgmentReview,
    apply_review,
    codex_chapter_review_json_schema,
    validate_review,
)
from .chapter_projection import RulerChapterProjection
from .codex_worker_command import build_codex_exec_command
from .model_profiles import load_research_model_profiles


def review_chapter_judgments(
    *,
    project_root: Path,
    judgment_paths: tuple[Path, ...],
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    timeout_seconds: int = 10_800,
) -> Path:
    """Review and revise each chapter artifact, then write a profiled manifest."""

    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.model != "gpt-5.6-sol" or "chapter_judge" not in profile.roles:
        raise ValueError("judgment review requires a Sol chapter-judge profile")
    output_dir.mkdir(parents=True, exist_ok=False)
    results = tuple(
        _review_one(
            project_root=project_root,
            judgment_path=path.resolve(),
            output_dir=output_dir,
            profile=profile,
            timeout_seconds=timeout_seconds,
        )
        for path in judgment_paths
    )
    manifest_path = output_dir / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "chapter_judgment_review_run_v1",
                "profile": profile_name,
                "model": profile.model,
                "reasoning_effort": "high",
                "chapter_count": len(results),
                "chapters": results,
                "usage": _sum_usage(results),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_reviewed_package(output_dir=output_dir, results=results)
    return manifest_path


def _review_one(
    *,
    project_root: Path,
    judgment_path: Path,
    output_dir: Path,
    profile: Any,
    timeout_seconds: int,
) -> dict[str, Any]:
    judgment = ChapterJudgmentBatch.model_validate_json(
        judgment_path.read_text(encoding="utf-8")
    )
    chapter_dir = output_dir / judgment.chapter_id
    chapter_dir.mkdir()
    projection_paths = _projection_paths(judgment_path, judgment)
    source_digest = sha256(judgment_path.read_bytes()).hexdigest()
    prompt_path = chapter_dir / "review-prompt.txt"
    schema_path = chapter_dir / "review-schema.json"
    pending_path = chapter_dir / "review.pending.json"
    events_path = chapter_dir / "review-events.jsonl"
    prompt_path.write_text(
        _review_prompt(judgment_path, judgment, projection_paths, source_digest),
        encoding="utf-8",
    )
    protected_hashes = {
        path: sha256(path.read_bytes()).hexdigest()
        for path in (judgment_path, *projection_paths)
    }
    schema_path.write_text(
        json.dumps(codex_chapter_review_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=schema_path,
        final_message_path=pending_path,
        writable_dir=chapter_dir,
        sandbox_mode="danger-full-access",
        reasoning_effort="high",
    )
    completed = subprocess.run(
        command,
        input=prompt_path.read_text(encoding="utf-8"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    events_path.write_text(completed.stdout, encoding="utf-8")
    if any(
        not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest
        for path, digest in protected_hashes.items()
    ):
        raise RuntimeError("Sol review modified a hash-bound source artifact")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Sol review failed for {judgment.chapter_id} with exit {completed.returncode}"
        )
    review = ChapterJudgmentReview.model_validate_json(
        pending_path.read_text(encoding="utf-8")
    )
    projections = tuple(
        RulerChapterProjection.model_validate_json(path.read_text(encoding="utf-8"))
        for path in projection_paths
    )
    evidence_ids = {
        item.job_key: {evidence.evidence_id for evidence in item.evidence}
        for item in projections
    }
    validate_review(
        review,
        judgment=judgment,
        source_sha256=source_digest,
        evidence_ids_by_job=evidence_ids,
    )
    reviewed = apply_review(judgment, review)
    review_path = chapter_dir / "review.json"
    reviewed_path = chapter_dir / "reviewed-chapter-judgment.json"
    review_path.write_text(review.model_dump_json(indent=2) + "\n", encoding="utf-8")
    reviewed_path.write_text(reviewed.model_dump_json(indent=2) + "\n", encoding="utf-8")
    usage = read_codex_usage(events_path)
    changes = sum(item.disposition != "retain" for item in review.decisions)
    return {
        "chapter_id": judgment.chapter_id,
        "source_judgment": str(judgment_path),
        "source_sha256": source_digest,
        "review": str(review_path),
        "reviewed_judgment": str(reviewed_path),
        "score_change_count": changes,
        "usage": usage.model_dump(mode="json") if usage is not None else None,
    }


def _projection_paths(
    judgment_path: Path, judgment: ChapterJudgmentBatch
) -> tuple[Path, ...]:
    directory = judgment_path.parent / "chapter-inputs"
    paths = tuple(sorted(directory.glob("*.json")))
    if len(paths) != len(judgment.evaluations):
        raise ValueError("source judgment does not have one sibling projection per ruler")
    return paths


def _review_prompt(
    judgment_path: Path,
    judgment: ChapterJudgmentBatch,
    projection_paths: tuple[Path, ...],
    source_digest: str,
) -> str:
    sources = [
        {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
        for path in projection_paths
    ]
    identity = {
        "schema_version": "chapter_judgment_review_v1",
        "chapter_id": judgment.chapter_id,
        "source_job_key": judgment.job_key,
        "source_sha256": source_digest,
        "reviewer_model": "gpt-5.6-sol",
        "reasoning_effort": "high",
    }
    return f"""Act as the independent final score-and-rationale reviewer for one
Leaders Database chapter. Use high reasoning and no external discovery. Read the
source judgment and every hash-bound ruler projection listed below in full.
Do not edit, patch, move, or rewrite any file. Filesystem tools are available only
to read the listed JSON inputs; your sole output is the structured final response.

For every ruler, independently test evidence relevance, ruler attribution, inherited
baseline, contrary evidence, source limitations, absolute chapter anchors, and cohort
ordering. Do not reward evidence volume and do not compare against client scores.

You may retain the score or correct it by at most 1 point upward or downward, using
half-point increments. Never convert a null to a number or a number to null. Make a
change only when the original judge was materially too generous or too severe. For
every ruler, return a self-contained revised rationale and revised lower/higher-anchor
explanations, even when retaining the score. Cite only evidence IDs in that ruler's
projection. The revised prose must reflect the reviewed score and explicitly resolve
the weakness identified in `review_explanation`.

Immutable review identity:
{json.dumps(identity, indent=2)}

Source judgment:
{json.dumps({"path": str(judgment_path), "sha256": source_digest}, indent=2)}

Ruler projections:
{json.dumps(sources, indent=2)}

Return only the requested JSON. Include exactly one decision for each of the
{len(judgment.evaluations)} source evaluations.
"""


def _sum_usage(results: tuple[dict[str, Any], ...]) -> dict[str, int]:
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


def _write_reviewed_package(
    *, output_dir: Path, results: tuple[dict[str, Any], ...]
) -> Path:
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
        review = ChapterJudgmentReview.model_validate_json(
            review_path.read_text(encoding="utf-8")
        )
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
    if (
        len(chapters) != 8
        or not expected_ruler_keys
        or evaluation_count != expected_evaluations
    ):
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


__all__ = ["review_chapter_judgments"]
