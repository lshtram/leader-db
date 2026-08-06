"""One-context, self-reviewed Luna chapter analysis."""

from __future__ import annotations

import json
from pathlib import Path

from .chapter_analysis_models import (
    ChapterEvidenceShard,
    ResolvedChapterAnalysis,
    SelfReviewedChapterAnalysis,
)
from .chapter_evidence_analysis import (
    _chapter_evidence,
    _validate_analysis,
    _validate_critique,
)
from .chapter_reading_list import _chapter_guide, _chapter_questions
from .corpus_reader_runner import _load_or_execute_json
from .model_profiles import load_research_model_profiles


def run_single_pass_chapter_analysis(
    *,
    project_root: Path,
    judge_package_path: Path,
    chapter_id: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Read exact chapter evidence once and return internally audited answers."""

    evidence = _chapter_evidence(judge_package_path, chapter_id)
    questions = _chapter_questions(project_root, chapter_id)
    expected_questions = {item["id"] for item in questions}
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    guide = _chapter_guide(project_root, chapter_id)
    prompt = _prompt(chapter_id, questions, guide, evidence)
    if len(prompt) <= 950_000:
        result = _load_or_execute_json(
            project_root,
            profile,
            prompt,
            SelfReviewedChapterAnalysis,
            output_dir / "luna-turn",
        )
    else:
        shards = _analyze_shards(
            project_root, profile, chapter_id, questions, guide, evidence, output_dir
        )
        result = _load_or_execute_json(
            project_root,
            profile,
            _synthesis_prompt(chapter_id, questions, guide, shards),
            SelfReviewedChapterAnalysis,
            output_dir / "luna-synthesis",
        )
    evidence_ids = set(evidence)
    _validate_result(
        result,
        chapter_id=chapter_id,
        expected_questions=expected_questions,
        evidence_ids=evidence_ids,
    )
    used_ids = {
        evidence_id
        for answer in result.corrected_answers
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    resolved = ResolvedChapterAnalysis(
        chapter_id=chapter_id,
        answers=tuple(
            sorted(result.corrected_answers, key=lambda item: item.question_id)
        ),
        evidence=tuple(evidence[item] for item in sorted(used_ids)),
        omitted_candidate_ids=tuple(sorted(evidence_ids - used_ids)),
        draft=result.draft,
        critique=result.critique,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "resolved-chapter-analysis.json"
    path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _validate_result(
    result: SelfReviewedChapterAnalysis,
    *,
    chapter_id: str,
    expected_questions: set[str],
    evidence_ids: set[str],
) -> None:
    if result.chapter_id != chapter_id:
        raise ValueError("self-reviewed analysis changed chapter identity")
    _validate_analysis(
        chapter_id, expected_questions, evidence_ids, result.draft
    )
    _validate_critique(
        chapter_id, expected_questions, evidence_ids, result.critique
    )
    received = {item.question_id for item in result.corrected_answers}
    if received != expected_questions or len(result.corrected_answers) != 10:
        raise ValueError("corrected analysis does not contain exactly ten lenses")
    used = {
        evidence_id
        for answer in result.corrected_answers
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    if not used.issubset(evidence_ids):
        raise ValueError("corrected analysis invented an evidence ID")


def _prompt(chapter_id, questions, guide, evidence) -> str:
    exact = [item.model_dump(mode="json") for item in evidence.values()]
    return (
        f"Analyze chapter {chapter_id} in one complete pass. The final consumer is a "
        "skeptical judge, but you do not score. Read every exact evidence record before "
        "writing. First draft answers to exactly the ten supplied questions. Then audit "
        "those drafts against the complete evidence packet for unsupported wording, "
        "material omissions, misleading weight, contrary evidence, source dependence, "
        "period errors, attribution errors, allegations presented as findings, and causal "
        "overstatement. Finally return corrected answers that resolve the audit. Preserve "
        "uncertainty and explicitly request reopening where the packet cannot settle a "
        "material issue. Cite evidence IDs for every factual account; use only supplied "
        "IDs. Include favorable, adverse, mixed, and exculpatory material when present. "
        "Keep ruler conduct distinct from institutional conduct and implementation from "
        "announced policy. Return only schema JSON.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        f"CHAPTER GUIDE:\n{guide}\n\n"
        "COMPLETE CODE-BOUND EVIDENCE PACKET (exact_excerpt and locator control):\n"
        f"{json.dumps(exact, ensure_ascii=False)}"
    )


def _analyze_shards(
    project_root, profile, chapter_id, questions, guide, evidence, output_dir
) -> tuple[ChapterEvidenceShard, ...]:
    shards = _partition_evidence(evidence, max_chars=800_000)
    results = []
    for number, shard in enumerate(shards, start=1):
        shard_id = f"{chapter_id}-S{number:02d}"
        result = _load_or_execute_json(
            project_root,
            profile,
            _shard_prompt(chapter_id, shard_id, questions, guide, shard),
            ChapterEvidenceShard,
            output_dir / "shards" / shard_id,
        )
        allowed = set(shard)
        if result.chapter_id != chapter_id or result.shard_id != shard_id:
            raise ValueError("shard analysis changed identity or evidence scope")
        result = _normalize_shard_registry(result, allowed)
        results.append(result)
    return tuple(results)


def _normalize_shard_registry(
    result: ChapterEvidenceShard, allowed: set[str]
) -> ChapterEvidenceShard:
    removed = sorted(
        {
            evidence_id
            for answer in result.answers
            for evidence_id in (
                answer.supporting_evidence_ids
                + answer.contrary_or_qualifying_evidence_ids
            )
            if evidence_id not in allowed
        }
    )
    answers = tuple(
        answer.model_copy(
            update={
                "supporting_evidence_ids": tuple(
                    item for item in answer.supporting_evidence_ids if item in allowed
                ),
                "contrary_or_qualifying_evidence_ids": tuple(
                    item
                    for item in answer.contrary_or_qualifying_evidence_ids
                    if item in allowed
                ),
            }
        )
        for answer in result.answers
    )
    supplied_mismatch = set(result.reviewed_evidence_ids) != allowed
    cautions = list(result.cross_shard_cautions)
    if removed:
        cautions.append("Code removed out-of-shard evidence IDs: " + ", ".join(removed))
    if supplied_mismatch:
        cautions.append("Code replaced the model-echoed reviewed-ID list with the registry.")
    return result.model_copy(
        update={
            "answers": answers,
            "reviewed_evidence_ids": tuple(sorted(allowed)),
            "cross_shard_cautions": tuple(cautions),
        }
    )


def _partition_evidence(evidence, *, max_chars: int) -> tuple[dict, ...]:
    shards = []
    current = {}
    size = 0
    for evidence_id, item in evidence.items():
        item_size = len(item.model_dump_json())
        if current and size + item_size > max_chars:
            shards.append(current)
            current = {}
            size = 0
        if item_size > max_chars:
            raise ValueError(f"one evidence record exceeds shard limit: {evidence_id}")
        current[evidence_id] = item
        size += item_size
    if current:
        shards.append(current)
    return tuple(shards)


def _shard_prompt(chapter_id, shard_id, questions, guide, evidence) -> str:
    exact = [item.model_dump(mode="json") for item in evidence.values()]
    return (
        f"Read every exact record in evidence shard {shard_id} for chapter {chapter_id}. "
        "Organize only this shard's material findings under applicable supplied questions; "
        "questions with no material shard evidence may be omitted. Preserve favorable, "
        "adverse, contrary, mixed, and exculpatory evidence, attribution, target-period "
        "fit, allegations versus findings, causal limits, and gaps. Cite only supplied "
        "evidence IDs. reviewed_evidence_ids must list every supplied ID exactly once. "
        "Do not score. Return only schema JSON.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"EXACT SHARD:\n{json.dumps(exact, ensure_ascii=False)}"
    )


def _synthesis_prompt(chapter_id, questions, guide, shards) -> str:
    payload = [item.model_dump(mode="json") for item in shards]
    return (
        f"Synthesize chapter {chapter_id} from all question-organized shard findings below. "
        "Every exact source record was read once upstream. First draft answers to exactly "
        "the ten questions. Then skeptically audit the drafts across all shards for omitted "
        "or contrary evidence, source dependence, misleading weight, period and attribution "
        "errors, allegations presented as findings, and causal overstatement. Finally return "
        "ten corrected answers resolving that audit. Cite only evidence IDs present below. "
        "Preserve unresolved gaps and request reopening where shard findings cannot settle a "
        "material issue. Do not score. Return only schema JSON.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"ALL SHARD FINDINGS:\n{json.dumps(payload, ensure_ascii=False)}"
    )


__all__ = ["run_single_pass_chapter_analysis"]
