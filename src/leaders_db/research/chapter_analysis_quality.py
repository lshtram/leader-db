"""Independent quality evaluation of produced chapter evidence analyses."""

from __future__ import annotations

import json
from pathlib import Path

from .chapter_analysis_models import (
    ChapterAnalysisQuality,
    ChapterAnalysisQualityShard,
    ResolvedChapterAnalysis,
)
from .chapter_evidence_analysis import _chapter_evidence
from .chapter_reading_list import _chapter_questions
from .corpus_reader_runner import _load_or_execute_json
from .model_profiles import load_research_model_profiles


def run_chapter_analysis_quality_review(
    *,
    project_root: Path,
    judge_package_path: Path,
    analysis_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Assess analysis quality in two full-index shards without scoring the ruler."""

    analysis = ResolvedChapterAnalysis.model_validate_json(
        analysis_path.read_text(encoding="utf-8")
    )
    evidence = _chapter_evidence(judge_package_path, analysis.chapter_id)
    questions = _chapter_questions(project_root, analysis.chapter_id)
    candidates = [_quality_candidate(item) for item in evidence.values()]
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    shards = []
    evidence_by_id = {item.evidence_id: item for item in analysis.evidence}
    groups = _quality_groups(analysis, questions, candidates, evidence_by_id)
    for selected_questions, answers, cited in groups:
        question_ids = {item["id"] for item in selected_questions}
        first = selected_questions[0]["id"].split(".")[-1].zfill(2)
        last = selected_questions[-1]["id"].split(".")[-1].zfill(2)
        shard = _load_or_execute_json(
            project_root,
            profile,
            _quality_prompt(
                analysis.chapter_id,
                answers,
                selected_questions,
                candidates,
                cited,
            ),
            ChapterAnalysisQualityShard,
            output_dir / f"questions-{first}-{last}",
        )
        _validate_quality_shard(analysis.chapter_id, question_ids, shard)
        shards.append(shard)
    quality = _combine_quality_shards(analysis.chapter_id, tuple(shards))
    path = output_dir / "quality-review.json"
    path.write_text(quality.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _quality_groups(analysis, questions, candidates, evidence_by_id):
    answer_by_id = {item.question_id: item for item in analysis.answers}
    groups = []
    pending_questions = []
    for question in questions:
        proposal = [*pending_questions, question]
        answers, cited = _quality_payload(proposal, answer_by_id, evidence_by_id)
        prompt = _quality_prompt(
            analysis.chapter_id, answers, proposal, candidates, cited
        )
        if pending_questions and len(prompt) > 850_000:
            packed_answers, packed_cited = _quality_payload(
                pending_questions, answer_by_id, evidence_by_id
            )
            groups.append((tuple(pending_questions), packed_answers, packed_cited))
            pending_questions = [question]
        else:
            pending_questions = proposal
    answers, cited = _quality_payload(
        pending_questions, answer_by_id, evidence_by_id
    )
    groups.append((tuple(pending_questions), answers, cited))
    return tuple(groups)


def _quality_payload(questions, answer_by_id, evidence_by_id):
    question_ids = {item["id"] for item in questions}
    answers = tuple(
        item for qid, item in answer_by_id.items() if qid in question_ids
    )
    cited_ids = {
        evidence_id
        for answer in answers
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    cited = [
        evidence_by_id[item].model_dump(mode="json") for item in sorted(cited_ids)
    ]
    return answers, cited


def _validate_quality_shard(chapter_id, question_ids, shard) -> None:
    received = {item.question_id for item in shard.lens_quality}
    if (
        shard.chapter_id != chapter_id
        or set(shard.question_ids) != question_ids
        or received != question_ids
    ):
        raise ValueError("quality shard does not reconcile with selected questions")


def _combine_quality_shards(chapter_id, shards) -> ChapterAnalysisQuality:
    verdicts = {item.verdict for item in shards}
    verdict = (
        "fail"
        if "fail" in verdicts
        else "pass_with_corrections"
        if "pass_with_corrections" in verdicts
        else "pass"
    )
    return ChapterAnalysisQuality(
        chapter_id=chapter_id,
        lens_quality=tuple(item for shard in shards for item in shard.lens_quality),
        overall_verdict=verdict,
        strengths=tuple(item for shard in shards for item in shard.strengths),
        systemic_problems=tuple(
            item for shard in shards for item in shard.systemic_problems
        ),
        concrete_corrections_required=tuple(
            item for shard in shards for item in shard.concrete_corrections_required
        ),
        safe_for_judge_use=all(item.safe_for_judge_use for item in shards),
        rationale=" ".join(item.rationale for item in shards),
    )


def _quality_prompt(chapter_id, answers, questions, candidates, cited) -> str:
    answer_payload = [item.model_dump(mode="json") for item in answers]
    return (
        "You are an independent quality evaluator, not the producing analyst and not a "
        "ruler scorer. Judge each answer for factual support, completeness against the "
        "full candidate index, balance, period and attribution handling, and usefulness "
        "to a skeptical future judge. Verify material claims against exact cited passages. "
        "Give concrete errors and omissions; do not reward polish or citation volume. "
        "Return only schema JSON.\n\n"
        f"CHAPTER: {chapter_id}\n\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}\n\nANSWERS:\n"
        f"{json.dumps(answer_payload, ensure_ascii=False)}\n\nEXACT CITED EVIDENCE:\n"
        f"{json.dumps(cited, ensure_ascii=False)}\n\nCOMPLETE CANDIDATE INDEX:\n"
        f"{json.dumps(candidates, ensure_ascii=False)}"
    )


def _quality_candidate(item) -> dict[str, object]:
    return {
        "evidence_id": item.evidence_id,
        "fact_summary": item.fact_summary,
        "publisher": item.publisher,
        "period_fit": item.period_fit,
    }


__all__ = ["run_chapter_analysis_quality_review"]
