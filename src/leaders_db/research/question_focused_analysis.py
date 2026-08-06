"""Cache-friendly one-question-at-a-time chapter evidence analysis."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .chapter_analysis_models import (
    CorrectedLensAnswer,
    LensAnswer,
    QuestionAnalysisTrace,
    QuestionCritique,
    QuestionFocusedChapterAnalysis,
    QuestionWorkflowTurn,
)
from .chapter_evidence_analysis import _chapter_evidence
from .chapter_reading_list import _chapter_guide, _chapter_questions, _compact
from .codex_worker_command import build_codex_exec_command
from .corpus_reader_models import BoundEvidence
from .model_profiles import load_research_model_profiles


def run_question_focused_chapter_analysis(
    *,
    project_root: Path,
    judge_package_path: Path,
    chapter_id: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_questions: int = 5,
) -> Path:
    """Answer, challenge, and correct each lens with one shared prompt prefix."""

    evidence = _chapter_evidence(judge_package_path, chapter_id)
    questions = _chapter_questions(project_root, chapter_id)
    prefix = _shared_prefix(
        chapter_id,
        _chapter_guide(project_root, chapter_id),
        tuple(evidence.values()),
    )
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    _prepare_shared_schema(output_dir)
    drafts = _run_stage(
        questions=questions,
        first_sequential=True,
        parallel_questions=parallel_questions,
        worker=lambda question: _answer_question(
            project_root, profile, prefix, question, evidence, output_dir
        ),
    )
    critiques = _run_stage(
        questions=questions,
        first_sequential=False,
        parallel_questions=parallel_questions,
        worker=lambda question: _critique_question(
            project_root,
            profile,
            prefix,
            question,
            drafts[question["id"]],
            evidence,
            output_dir,
        ),
    )
    corrected = _run_stage(
        questions=questions,
        first_sequential=False,
        parallel_questions=parallel_questions,
        worker=lambda question: _correct_question(
            project_root,
            profile,
            prefix,
            question,
            drafts[question["id"]],
            critiques[question["id"]],
            evidence,
            output_dir,
        ),
    )
    used_ids = {
        evidence_id
        for answer in corrected.values()
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    traces = tuple(
        QuestionAnalysisTrace(
            question_id=question["id"],
            draft=drafts[question["id"]],
            critique=critiques[question["id"]],
            corrected=corrected[question["id"]],
        )
        for question in questions
    )
    package = QuestionFocusedChapterAnalysis(
        chapter_id=chapter_id,
        traces=traces,
        evidence=tuple(evidence[item] for item in sorted(used_ids)),
        omitted_candidate_ids=tuple(sorted(set(evidence) - used_ids)),
        shared_prefix_sha256=sha256(prefix.encode()).hexdigest(),
    )
    path = output_dir / "question-focused-chapter-analysis.json"
    path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _run_stage(
    *, questions, first_sequential: bool, parallel_questions: int, worker
) -> dict[str, object]:
    results = {}
    remaining = list(questions)
    if first_sequential:
        first = remaining.pop(0)
        results[first["id"]] = worker(first)
    if parallel_questions == 1:
        for item in remaining:
            results[item["id"]] = worker(item)
        return results
    with ThreadPoolExecutor(max_workers=parallel_questions) as executor:
        futures = {executor.submit(worker, item): item["id"] for item in remaining}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _answer_question(
    project_root, profile, prefix, question, evidence, output_dir
) -> LensAnswer:
    prompt = prefix + _answer_task(question)
    turn = _execute_turn(
        project_root,
        profile,
        prompt,
        output_dir / "answers" / question["id"],
        execution_root=output_dir,
        expected_stage="answer",
        question_id=question["id"],
        evidence_ids=set(evidence),
    )
    if turn.answer is None:
        raise ValueError("answer turn omitted answer payload")
    return turn.answer


def _critique_question(
    project_root, profile, prefix, question, draft, evidence, output_dir
) -> QuestionCritique:
    prompt = prefix + _critique_task(question, draft)
    turn = _execute_turn(
        project_root,
        profile,
        prompt,
        output_dir / "critiques" / question["id"],
        execution_root=output_dir,
        expected_stage="critique",
        question_id=question["id"],
        evidence_ids=set(evidence),
    )
    if turn.critique is None:
        raise ValueError("critique turn omitted critique payload")
    return turn.critique


def _correct_question(
    project_root, profile, prefix, question, draft, critique, evidence, output_dir
) -> CorrectedLensAnswer:
    reopen_ids = set(draft.supporting_evidence_ids)
    reopen_ids.update(draft.contrary_or_qualifying_evidence_ids)
    reopen_ids.update(
        evidence_id for issue in critique.issues for evidence_id in issue.evidence_ids
    )
    exact = [evidence[item].model_dump(mode="json") for item in sorted(reopen_ids)]
    prompt = prefix + _correction_task(question, draft, critique, exact)
    turn = _execute_turn(
        project_root,
        profile,
        prompt,
        output_dir / "corrections" / question["id"],
        execution_root=output_dir,
        expected_stage="correction",
        question_id=question["id"],
        evidence_ids=reopen_ids,
    )
    if turn.corrected is None:
        raise ValueError("correction turn omitted corrected payload")
    return turn.corrected


def _execute_turn(
    project_root,
    profile,
    prompt: str,
    output_dir: Path,
    *,
    expected_stage: str,
    question_id: str,
    evidence_ids: set[str],
    execution_root: Path,
) -> QuestionWorkflowTurn:
    feedback = ""
    for attempt in range(1, 4):
        turn = _execute_shared_context_turn(
            project_root=project_root,
            profile=profile,
            prompt=prompt + feedback,
            output_dir=output_dir,
            execution_root=execution_root,
        )
        error = _turn_error(turn, expected_stage, question_id, evidence_ids)
        if error is None:
            return turn
        if attempt == 3:
            raise ValueError(error)
        path = output_dir / "output.json"
        path.rename(output_dir / f"output.invalid-{attempt}.json")
        feedback = (
            f"\n\nCORRECTION REQUIRED: {error}. Preserve the requested stage and "
            "question ID; cite only evidence IDs present in the shared packet or, for "
            "correction, the reopened exact evidence."
        )
    raise AssertionError("unreachable")


def _prepare_shared_schema(execution_root: Path) -> Path:
    path = execution_root / "shared-turn-schema.json"
    if not path.is_file():
        schema = QuestionWorkflowTurn.model_json_schema()
        make_strict_response_schema(schema)
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return path


def _execute_shared_context_turn(
    *, project_root, profile, prompt: str, output_dir: Path, execution_root: Path
) -> QuestionWorkflowTurn:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "output.json"
    if output_path.is_file():
        return QuestionWorkflowTurn.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
    prompt_path = output_dir / "prompt.txt"
    events_path = output_dir / "events.jsonl"
    stderr_path = output_dir / "stderr.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=_prepare_shared_schema(execution_root),
        final_message_path=output_path,
        writable_dir=execution_root,
        isolated_web_research=True,
    )
    with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        subprocess.run(
            command, input=prompt, text=True, stdout=events, stderr=stderr, check=True
        )
    return QuestionWorkflowTurn.model_validate_json(
        output_path.read_text(encoding="utf-8")
    )


def _turn_error(turn, stage, question_id, evidence_ids) -> str | None:
    if turn.stage != stage or turn.question_id != question_id:
        return "turn stage or question identity changed"
    payload = {
        "answer": turn.answer,
        "critique": turn.critique,
        "correction": turn.corrected,
    }[stage]
    if payload is None or payload.question_id != question_id:
        return "turn omitted or shifted its stage payload"
    if stage == "critique":
        used = {item for issue in payload.issues for item in issue.evidence_ids}
    else:
        used = set(payload.supporting_evidence_ids) | set(
            payload.contrary_or_qualifying_evidence_ids
        )
    return None if used.issubset(evidence_ids) else "turn invented an evidence ID"


def _shared_prefix(
    chapter_id: str, guide: str, evidence: tuple[BoundEvidence, ...]
) -> str:
    candidates = [_compact(item) for item in evidence]
    return (
        "SHARED IMMUTABLE CHAPTER EVIDENCE PACKET. This exact prefix is reused for "
        "every task in the chapter. Evidence summaries are navigation aids; exact "
        "passages supplied during correction control factual wording.\n\n"
        f"CHAPTER: {chapter_id}\n\nGUIDE:\n{guide}\n\nCOMPLETE CANDIDATE INDEX:\n"
        f"{json.dumps(candidates, ensure_ascii=False, sort_keys=True)}\n\n"
        "END SHARED IMMUTABLE CHAPTER EVIDENCE PACKET.\n\n"
    )


def _answer_task(question) -> str:
    return (
        "TASK: ANSWER ONE QUESTION. Inspect every candidate, including candidates not "
        "currently mapped to this lens. Explain material favorable, adverse, mixed, and "
        "qualifying evidence. Separate target-year facts, older context, allegations, "
        "findings, ruler conduct, institutional conduct, implementation, outcomes, and "
        "unknowns. Cite IDs for each material account. Do not score. Set stage='answer'; "
        "populate only answer; set critique and corrected to null.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}"
    )


def _critique_task(question, draft) -> str:
    return (
        "TASK: CRITIQUE ONE ANSWER. Compare it against every candidate in the shared "
        "index. Identify material omissions, unsupported claims, misleading weight, "
        "period or attribution errors, missing contrary evidence, and irrelevant evidence. "
        "Do not score. Set stage='critique'; populate only critique; set answer and "
        "corrected to null.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}\n\nDRAFT:\n{draft.model_dump_json()}"
    )


def _correction_task(question, draft, critique, exact) -> str:
    return (
        "TASK: CORRECT ONE ANSWER. Second-guess draft and critique. Use exact passages "
        "below to narrow unsupported wording and incorporate material challenged evidence. "
        "Preserve uncertainty and gaps. Cite only reopened IDs. Do not score. Set "
        "stage='correction'; populate only corrected; set answer and critique to null.\n\n"
        f"QUESTION:\n{json.dumps(question, ensure_ascii=False)}\n\nDRAFT:\n"
        f"{draft.model_dump_json()}\n\nCRITIQUE:\n{critique.model_dump_json()}\n\n"
        f"REOPENED EXACT EVIDENCE:\n{json.dumps(exact, ensure_ascii=False)}"
    )


__all__ = ["run_question_focused_chapter_analysis"]
