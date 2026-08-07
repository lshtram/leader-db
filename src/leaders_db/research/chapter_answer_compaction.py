"""Compact complete chapter answers while preserving code-bound evidence."""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .chapter_analysis_models import CorrectedLensAnswer, ResolvedChapterAnalysis
from .chapter_evidence_analysis import _chapter_evidence
from .chapter_reading_list import _chapter_guide, _chapter_questions
from .corpus_reader_runner import _load_or_execute_json
from .model_profiles import load_research_model_profiles


def run_chapter_answer_compaction(
    *,
    project_root: Path,
    judge_package_path: Path,
    analysis_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_answers: int = 5,
) -> Path:
    """Edit one complete chapter into bounded, evidence-preserving answers."""

    analysis = ResolvedChapterAnalysis.model_validate_json(
        analysis_path.read_text(encoding="utf-8")
    )
    evidence = _chapter_evidence(judge_package_path, analysis.chapter_id)
    questions = _chapter_questions(project_root, analysis.chapter_id)
    question_by_id = {item["id"]: item for item in questions}
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    guide = _chapter_guide(project_root, analysis.chapter_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=parallel_answers) as executor:
        futures = {}
        for answer in analysis.answers:
            ids = set(answer.supporting_evidence_ids)
            ids.update(answer.contrary_or_qualifying_evidence_ids)
            exact = [evidence[item].model_dump(mode="json") for item in sorted(ids)]
            future = executor.submit(
                _compact_one,
                project_root,
                profile,
                _prompt(question_by_id[answer.question_id], guide, answer, exact),
                output_dir / "answers" / answer.question_id,
                answer.question_id,
                ids,
            )
            futures[future] = (answer.question_id, ids)
        for future in as_completed(futures):
            question_id, allowed = futures[future]
            result = future.result()
            _validate(result, question_id, allowed)
            results[question_id] = result
    answers = tuple(results[item["id"]] for item in questions)
    cited = {
        item
        for answer in answers
        for item in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    resolved = analysis.model_copy(
        update={
            "answers": answers,
            "evidence": tuple(evidence[item] for item in sorted(cited)),
            "omitted_candidate_ids": tuple(sorted(set(evidence) - cited)),
        }
    )
    path = output_dir / "resolved-chapter-analysis.json"
    path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _compact_one(project_root, profile, prompt, output_dir, question_id, allowed):
    feedback = ""
    for attempt in range(1, 6):
        result = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            CorrectedLensAnswer,
            output_dir,
        )
        try:
            _validate(result, question_id, allowed)
            return result
        except ValueError as exc:
            if attempt == 5:
                raise
            invalid_index = 1
            while (output_dir / f"output.invalid-{invalid_index}.json").exists():
                invalid_index += 1
            (output_dir / "output.json").rename(
                output_dir / f"output.invalid-{invalid_index}.json"
            )
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. "
                "Return a 550-900 word narrative and cite only supplied evidence IDs."
            )
    raise AssertionError("unreachable")


def _prompt(question, guide, answer, exact):
    return (
        "Edit the complete answer into a 550-900 word judge-facing account. Preserve "
        "every materially distinct actor, mechanism, outcome, contrary point, period "
        "boundary, attribution limit, allegation status, and unresolved gap already in "
        "the answer. Remove repetition and select the strongest representative, "
        "nonduplicative citations; normally retain 12-30 evidence IDs. Cite every "
        "material factual account and only supplied IDs. Do not score. Return only "
        "schema JSON.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"COMPLETE ANSWER:\n{answer.model_dump_json()}\n\nEXACT EVIDENCE:\n"
        f"{json.dumps(exact, ensure_ascii=False)}"
    )


def _validate(result, question_id, allowed):
    if result.question_id != question_id:
        raise ValueError("compaction changed question identity")
    cited = set(result.supporting_evidence_ids)
    cited.update(result.contrary_or_qualifying_evidence_ids)
    if not cited.issubset(allowed):
        raise ValueError("compaction cited evidence that was not supplied")
    minimum_citations = min(12, max(1, math.ceil(len(allowed) * 0.3)))
    if len(cited) < minimum_citations:
        raise ValueError(
            f"compaction retained {len(cited)} citations; expected {minimum_citations}"
        )
    word_count = len(result.answer.split())
    if not 450 <= word_count <= 1_100:
        raise ValueError(f"compacted answer has {word_count} words")


__all__ = ["run_chapter_answer_compaction"]
