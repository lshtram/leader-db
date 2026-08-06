"""Question-complete, self-correcting chapter evidence analysis experiment."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .chapter_analysis_integrity import (
    revision_context,
    strip_invalid_corrected_ids,
    strip_invalid_critique_ids,
    strip_invalid_draft_ids,
)
from .chapter_analysis_models import (
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    CorrectedLensAnswer,
    ResolvedChapterAnalysis,
)
from .chapter_reading_list import _chapter_guide, _chapter_questions, _compact
from .corpus_reader_models import BoundEvidence
from .corpus_reader_runner import _load_or_execute_json
from .model_profiles import load_research_model_profiles


def run_chapter_evidence_analysis(
    *,
    project_root: Path,
    judge_package_path: Path,
    chapter_id: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_answers: int = 5,
    prior_analysis_path: Path | None = None,
    quality_review_path: Path | None = None,
) -> Path:
    """Answer, challenge, and passage-check all ten questions for one chapter."""

    evidence = _chapter_evidence(judge_package_path, chapter_id)
    questions = _chapter_questions(project_root, chapter_id)
    guide = _chapter_guide(project_root, chapter_id)
    candidates = [_compact(item) for item in evidence.values()]
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    expected_questions = {item["id"] for item in questions}
    revision_notes = revision_context(
        chapter_id,
        prior_analysis_path=prior_analysis_path,
        quality_review_path=quality_review_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    draft = _draft_with_retries(
        project_root=project_root,
        profile=profile,
        prompt=_draft_prompt(
            chapter_id, questions, guide, candidates, revision_notes
        ),
        output_dir=output_dir / "draft",
        chapter_id=chapter_id,
        expected_questions=expected_questions,
        evidence_ids=set(evidence),
    )
    critique = _critique_with_retries(
        project_root=project_root,
        profile=profile,
        prompt=_critique_prompt(
            chapter_id, questions, guide, candidates, draft, revision_notes
        ),
        output_dir=output_dir / "critique",
        chapter_id=chapter_id,
        expected_questions=expected_questions,
        evidence_ids=set(evidence),
    )
    corrected = _correct_answers(
        project_root=project_root,
        profile=profile,
        chapter_id=chapter_id,
        questions=questions,
        guide=guide,
        evidence=evidence,
        draft=draft,
        critique=critique,
        output_dir=output_dir / "corrections",
        parallel_answers=parallel_answers,
    )
    used_ids = {
        evidence_id
        for answer in corrected
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    resolved = ResolvedChapterAnalysis(
        chapter_id=chapter_id,
        answers=tuple(sorted(corrected, key=lambda item: item.question_id)),
        evidence=tuple(evidence[item] for item in sorted(used_ids)),
        omitted_candidate_ids=tuple(sorted(set(evidence) - used_ids)),
        draft=draft,
        critique=critique,
    )
    path = output_dir / "resolved-chapter-analysis.json"
    path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _draft_with_retries(
    *, project_root, profile, prompt, output_dir, chapter_id, expected_questions, evidence_ids
) -> ChapterAnalysisDraft:
    feedback = ""
    for attempt in range(1, 4):
        draft = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            ChapterAnalysisDraft,
            output_dir,
        )
        try:
            _validate_analysis(chapter_id, expected_questions, evidence_ids, draft)
            return draft
        except ValueError as exc:
            prior_failures = len(tuple(output_dir.glob("output.invalid-*.json")))
            if attempt == 3 or prior_failures >= 2:
                repaired = strip_invalid_draft_ids(draft, evidence_ids)
                _validate_analysis(
                    chapter_id, expected_questions, evidence_ids, repaired
                )
                return repaired
            _invalidate_output(output_dir, attempt)
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. "
                "Use only exact evidence IDs present in the candidate index and return "
                "exactly the supplied ten question IDs."
            )
    raise AssertionError("unreachable")


def _critique_with_retries(
    *, project_root, profile, prompt, output_dir, chapter_id, expected_questions, evidence_ids
) -> ChapterAnalysisCritique:
    feedback = ""
    for attempt in range(1, 4):
        critique = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            ChapterAnalysisCritique,
            output_dir,
        )
        try:
            _validate_critique(
                chapter_id, expected_questions, evidence_ids, critique
            )
            return critique
        except ValueError as exc:
            if attempt == 3:
                repaired = strip_invalid_critique_ids(critique, evidence_ids)
                _validate_critique(
                    chapter_id, expected_questions, evidence_ids, repaired
                )
                return repaired
            _invalidate_output(output_dir, attempt)
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. "
                "Use only the supplied chapter, question IDs, and candidate evidence IDs."
            )
    raise AssertionError("unreachable")


def _invalidate_output(output_dir: Path, attempt: int) -> None:
    path = output_dir / "output.json"
    path.rename(output_dir / f"output.invalid-{attempt}.json")


def _chapter_evidence(path: Path, chapter_id: str) -> dict[str, BoundEvidence]:
    """Return the complete ruler ledger so chapter analysis can challenge routing."""

    del chapter_id
    package = json.loads(path.read_text(encoding="utf-8"))
    return {
        item.evidence_id: item
        for raw in package["evidence"]
        for item in (BoundEvidence.model_validate(raw),)
    }


def _correct_answers(
    *,
    project_root: Path,
    profile,
    chapter_id: str,
    questions: list[dict[str, str]],
    guide: str,
    evidence: dict[str, BoundEvidence],
    draft: ChapterAnalysisDraft,
    critique: ChapterAnalysisCritique,
    output_dir: Path,
    parallel_answers: int,
) -> tuple[CorrectedLensAnswer, ...]:
    question_by_id = {item["id"]: item for item in questions}
    answer_by_id = {item.question_id: item for item in draft.answers}
    issues_by_id = {
        qid: tuple(item for item in critique.issues if item.question_id == qid)
        for qid in question_by_id
    }
    with ThreadPoolExecutor(max_workers=parallel_answers) as executor:
        futures = {}
        for question_id, question in question_by_id.items():
            answer = answer_by_id[question_id]
            issues = issues_by_id[question_id]
            ids = set(answer.supporting_evidence_ids)
            ids.update(answer.contrary_or_qualifying_evidence_ids)
            ids.update(evidence_id for issue in issues for evidence_id in issue.evidence_ids)
            exact = [evidence[item].model_dump(mode="json") for item in sorted(ids)]
            futures[
                executor.submit(
                    _correct_one_answer,
                    project_root=project_root,
                    profile=profile,
                    prompt=_correction_prompt(
                        chapter_id, question, guide, answer, issues, exact
                    ),
                    output_dir=output_dir / question_id,
                    question_id=question_id,
                    allowed_ids=ids,
                )
            ] = (question_id, ids)
        results = []
        for future in as_completed(futures):
            result = future.result()
            question_id, allowed_ids = futures[future]
            _validate_corrected_answer(result, question_id, allowed_ids)
            results.append(result)
    return tuple(results)


def _correct_one_answer(
    *, project_root, profile, prompt, output_dir, question_id, allowed_ids
) -> CorrectedLensAnswer:
    feedback = ""
    for attempt in range(1, 4):
        result = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            CorrectedLensAnswer,
            output_dir,
        )
        try:
            _validate_corrected_answer(result, question_id, allowed_ids)
            return result
        except ValueError as exc:
            if attempt == 3:
                repaired = strip_invalid_corrected_ids(result, allowed_ids)
                _validate_corrected_answer(repaired, question_id, allowed_ids)
                return repaired
            _invalidate_output(output_dir, attempt)
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. "
                "Cite only the exact evidence IDs supplied in this correction prompt."
            )
    raise AssertionError("unreachable")


def _validate_corrected_answer(result, question_id, allowed_ids) -> None:
    if result.question_id != question_id:
        raise ValueError("corrected answer changed question identity")
    ids = set(result.supporting_evidence_ids) | set(
        result.contrary_or_qualifying_evidence_ids
    )
    if not ids.issubset(allowed_ids):
        raise ValueError("corrected answer cited evidence not reopened")


def _validate_analysis(chapter_id, questions, evidence_ids, draft) -> None:
    received = {item.question_id for item in draft.answers}
    if draft.chapter_id != chapter_id or received != questions or len(draft.answers) != 10:
        raise ValueError("draft does not answer exactly the ten chapter questions")
    used = {
        item
        for answer in draft.answers
        for item in answer.supporting_evidence_ids + answer.contrary_or_qualifying_evidence_ids
    }
    if not used.issubset(evidence_ids):
        raise ValueError("draft invented an evidence ID")


def _validate_critique(chapter_id, questions, evidence_ids, critique) -> None:
    if critique.chapter_id != chapter_id:
        raise ValueError("critique changed chapter identity")
    if any(item.question_id not in questions for item in critique.issues):
        raise ValueError("critique referenced an unknown question")
    if any(not set(item.evidence_ids).issubset(evidence_ids) for item in critique.issues):
        raise ValueError("critique invented an evidence ID")


def _draft_prompt(chapter_id, questions, guide, candidates, revision_context="") -> str:
    return (
        f"Answer all ten {chapter_id} evidence questions from the complete candidate "
        "index. Do not score. Each answer must synthesize material favorable, adverse, "
        "mixed, and qualifying evidence; distinguish conduct, implementation, outcomes, "
        "period, attribution, causation, and uncertainty; and cite evidence IDs for every "
        "material factual account. Do not merely enumerate sources. Return exactly ten "
        "answers and only schema JSON.\n\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"COMPLETE CANDIDATE INDEX:\n{json.dumps(candidates, ensure_ascii=False)}"
        f"{revision_context}"
    )


def _critique_prompt(
    chapter_id, questions, guide, candidates, draft, revision_context=""
) -> str:
    return (
        f"Independently audit all ten {chapter_id} answers against every candidate. "
        "Name unsupported claims, decisive omissions, misleading weight, period or "
        "attribution errors, missing contrary evidence, and irrelevant citations. Be "
        "specific and cite evidence IDs. Do not score. Return only schema JSON.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"DRAFT:\n{draft.model_dump_json()}\n\nCOMPLETE CANDIDATE INDEX:\n"
        f"{json.dumps(candidates, ensure_ascii=False)}{revision_context}"
    )


def _correction_prompt(chapter_id, question, guide, answer, issues, exact) -> str:
    return (
        f"Correct this one {chapter_id} answer after skeptical review. Use the exact "
        "code-bound passages below. Second-guess both draft and critic. Preserve material "
        "support, contrary evidence, uncertainty, period, attribution, and causal limits. "
        "Cite only supplied IDs. Do not score. Return only schema JSON.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\nDRAFT:\n"
        f"{answer.model_dump_json()}\n\nCRITIQUE:\n"
        f"{json.dumps([item.model_dump(mode='json') for item in issues], ensure_ascii=False)}"
        f"\n\nEXACT EVIDENCE:\n{json.dumps(exact, ensure_ascii=False)}"
    )


__all__ = ["run_chapter_evidence_analysis"]
