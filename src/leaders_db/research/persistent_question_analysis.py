"""Question-focused analysis using persistent Luna threads for context reuse."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .chapter_analysis_models import (
    LensAnswer,
    QuestionAnalysisTrace,
    QuestionCritique,
    QuestionFocusedChapterAnalysis,
    QuestionWorkflowTurn,
)
from .chapter_evidence_analysis import _chapter_evidence
from .chapter_reading_list import _chapter_guide, _chapter_questions, _compact
from .codex_worker_command import (
    build_codex_exec_command,
    build_codex_resume_command,
    read_codex_thread_id,
)
from .model_profiles import load_research_model_profiles


def run_persistent_question_analysis(
    *,
    project_root: Path,
    judge_package_path: Path,
    chapter_id: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Load chapter evidence once per role and resume exact threads across questions."""

    evidence = _chapter_evidence(judge_package_path, chapter_id)
    questions = _chapter_questions(project_root, chapter_id)
    prefix = _evidence_context(
        chapter_id,
        _chapter_guide(project_root, chapter_id),
        tuple(evidence.values()),
    )
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    drafts = _run_role_thread(
        project_root=project_root,
        profile=profile,
        output_dir=output_dir / "analyst-thread",
        first_prompt=prefix + _analyst_instruction(questions[0]),
        later_prompts=[_analyst_instruction(item) for item in questions[1:]],
        questions=questions,
        expected_stage="answer",
        allowed_ids=set(evidence),
    )
    critiques = _run_role_thread(
        project_root=project_root,
        profile=profile,
        output_dir=output_dir / "reviewer-thread",
        first_prompt=prefix + _reviewer_instruction(questions[0], drafts[questions[0]["id"]]),
        later_prompts=[
            _reviewer_instruction(item, drafts[item["id"]]) for item in questions[1:]
        ],
        questions=questions,
        expected_stage="critique",
        allowed_ids=set(evidence),
    )
    correction_prompts = [
        _corrector_instruction(
            question,
            drafts[question["id"]],
            critiques[question["id"]],
            evidence,
        )
        for question in questions
    ]
    corrected = _run_role_thread(
        project_root=project_root,
        profile=profile,
        output_dir=output_dir / "corrector-thread",
        first_prompt=_corrector_context(chapter_id) + correction_prompts[0],
        later_prompts=correction_prompts[1:],
        questions=questions,
        expected_stage="correction",
        allowed_ids_by_question={
            question["id"]: _reopened_ids(
                drafts[question["id"]], critiques[question["id"]]
            )
            for question in questions
        },
    )
    used_ids = {
        evidence_id
        for answer in corrected.values()
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    package = QuestionFocusedChapterAnalysis(
        chapter_id=chapter_id,
        traces=tuple(
            QuestionAnalysisTrace(
                question_id=item["id"],
                draft=drafts[item["id"]],
                critique=critiques[item["id"]],
                corrected=corrected[item["id"]],
            )
            for item in questions
        ),
        evidence=tuple(evidence[item] for item in sorted(used_ids)),
        omitted_candidate_ids=tuple(sorted(set(evidence) - used_ids)),
        shared_prefix_sha256=sha256(prefix.encode()).hexdigest(),
    )
    path = output_dir / "persistent-question-analysis.json"
    path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _run_role_thread(
    *,
    project_root,
    profile,
    output_dir,
    first_prompt,
    later_prompts,
    questions,
    expected_stage,
    allowed_ids=None,
    allowed_ids_by_question=None,
):
    prompts = [first_prompt, *later_prompts]
    results = {}
    session_id = None
    for number, (question, prompt) in enumerate(
        zip(questions, prompts, strict=True), start=1
    ):
        turn_dir = output_dir / f"turn-{number:02d}-{question['id']}"
        turn = _execute_persistent_turn(
            project_root=project_root,
            profile=profile,
            prompt=prompt,
            output_dir=turn_dir,
            session_id=session_id,
        )
        if session_id is None:
            session_id = read_codex_thread_id(turn_dir / "events.jsonl")
            (output_dir / "thread-id.txt").write_text(session_id + "\n", encoding="utf-8")
        permitted = (
            allowed_ids_by_question[question["id"]]
            if allowed_ids_by_question is not None
            else allowed_ids
        )
        error = _turn_error(turn, expected_stage, question["id"], permitted)
        if error is not None:
            raise ValueError(f"{question['id']}: {error}")
        results[question["id"]] = _stage_payload(turn, expected_stage)
    return results


def _execute_persistent_turn(
    *, project_root, profile, prompt: str, output_dir: Path, session_id: str | None
) -> QuestionWorkflowTurn:
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "prompt.txt"
    output_path = output_dir / "output.json"
    events_path = output_dir / "events.jsonl"
    stderr_path = output_dir / "stderr.txt"
    if output_path.is_file():
        return _parse_turn(output_path)
    prompt_path.write_text(prompt, encoding="utf-8")
    if session_id is None:
        schema_path = output_dir / "schema.json"
        schema = QuestionWorkflowTurn.model_json_schema()
        make_strict_response_schema(schema)
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        command = build_codex_exec_command(
            profile=profile,
            project_root=project_root,
            schema_path=schema_path,
            final_message_path=output_path,
            writable_dir=output_dir,
            isolated_web_research=True,
        )
    else:
        command = build_codex_resume_command(
            profile=profile,
            session_id=session_id,
            project_root=project_root,
            final_message_path=output_path,
            writable_dir=output_dir,
        )
    with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        subprocess.run(
            command, input=prompt, text=True, stdout=events, stderr=stderr, check=True
        )
    return _parse_turn(output_path)


def _parse_turn(path: Path) -> QuestionWorkflowTurn:
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return QuestionWorkflowTurn.model_validate_json(text)


def _turn_error(turn, stage, question_id, evidence_ids) -> str | None:
    if turn.stage != stage or turn.question_id != question_id:
        return "turn stage or question identity changed"
    payload = _stage_payload(turn, stage)
    if payload is None or payload.question_id != question_id:
        return "turn omitted or shifted its payload"
    if stage == "critique":
        used = {item for issue in payload.issues for item in issue.evidence_ids}
    else:
        used = set(payload.supporting_evidence_ids) | set(
            payload.contrary_or_qualifying_evidence_ids
        )
    return None if used.issubset(evidence_ids) else "turn invented an evidence ID"


def _stage_payload(turn, stage):
    return {
        "answer": turn.answer,
        "critique": turn.critique,
        "correction": turn.corrected,
    }[stage]


def _reopened_ids(draft: LensAnswer, critique: QuestionCritique) -> set[str]:
    ids = set(draft.supporting_evidence_ids)
    ids.update(draft.contrary_or_qualifying_evidence_ids)
    ids.update(item for issue in critique.issues for item in issue.evidence_ids)
    return ids


def _evidence_context(chapter_id, guide, evidence) -> str:
    return (
        "You are the chapter evidence analyst. Retain the following immutable evidence "
        "packet throughout this thread and answer later tasks only from it. Evidence "
        "summaries are navigation aids; preserve uncertainty and cite exact IDs.\n\n"
        f"CHAPTER: {chapter_id}\n\nGUIDE:\n{guide}\n\nCOMPLETE EVIDENCE INDEX:\n"
        f"{json.dumps([_compact(item) for item in evidence], ensure_ascii=False)}\n\n"
        "END IMMUTABLE EVIDENCE INDEX.\n\n"
    )


def _analyst_instruction(question) -> str:
    return (
        "Answer this one question after checking the complete retained index. Include "
        "material favorable, adverse, mixed, and qualifying evidence; distinguish period, "
        "attribution, allegations, findings, implementation, outcomes, and unknowns. Cite "
        "IDs for material accounts. Do not score. Return raw JSON matching the established "
        "turn schema: stage answer, only answer populated.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}"
    )


def _reviewer_instruction(question, draft) -> str:
    return (
        "Critique this answer against the complete retained index. Identify material "
        "omissions, unsupported claims, misleading weight, period or attribution errors, "
        "missing contrary evidence, and irrelevant evidence. Do not score. Return raw JSON "
        "matching the established turn schema: stage critique, only critique populated.\n\n"
        f"QUESTION:\n{json.dumps(question, ensure_ascii=False)}\n\nDRAFT:\n"
        f"{draft.model_dump_json()}"
    )


def _corrector_context(chapter_id) -> str:
    return (
        f"You are the exact-passage corrector for chapter {chapter_id}. Each turn supplies "
        "one draft, critique, and the only exact evidence you may cite. Narrow unsupported "
        "wording, incorporate material corrections, preserve uncertainty, and do not score. "
        "Return raw JSON matching the established turn schema: stage correction, only "
        "corrected populated.\n\n"
    )


def _corrector_instruction(question, draft, critique, evidence) -> str:
    ids = _reopened_ids(draft, critique)
    exact = [evidence[item].model_dump(mode="json") for item in sorted(ids)]
    return (
        f"QUESTION:\n{json.dumps(question, ensure_ascii=False)}\n\nDRAFT:\n"
        f"{draft.model_dump_json()}\n\nCRITIQUE:\n{critique.model_dump_json()}\n\n"
        f"EXACT REOPENED EVIDENCE:\n{json.dumps(exact, ensure_ascii=False)}"
    )


__all__ = ["run_persistent_question_analysis"]
