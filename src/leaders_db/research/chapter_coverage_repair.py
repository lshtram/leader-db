"""Repair reviewed chapter answers without dropping reviewer requirements."""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .chapter_analysis_models import (
    ChapterAnalysisQuality,
    ResolvedChapterAnalysis,
)
from .chapter_analysis_quality import _quality_candidate
from .chapter_coverage_models import (
    CoveragePlan,
    CoverageRequirement,
    RepairedLensAnswer,
    RoutedRequirementDisposition,
    validate_routed_dispositions,
)
from .chapter_evidence_analysis import _chapter_evidence
from .chapter_reading_list import _chapter_guide, _chapter_questions
from .corpus_reader_runner import _load_or_execute_json
from .model_profiles import load_research_model_profiles


def run_chapter_coverage_repair(
    *,
    project_root: Path,
    judge_package_path: Path,
    analysis_path: Path,
    quality_review_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_answers: int = 5,
) -> Path:
    """Repair one chapter while proving every review requirement was handled."""

    analysis = ResolvedChapterAnalysis.model_validate_json(
        analysis_path.read_text(encoding="utf-8")
    )
    quality = ChapterAnalysisQuality.model_validate_json(
        quality_review_path.read_text(encoding="utf-8")
    )
    if quality.chapter_id != analysis.chapter_id:
        raise ValueError("analysis and quality review identify different chapters")
    evidence = _chapter_evidence(judge_package_path, analysis.chapter_id)
    questions = _chapter_questions(project_root, analysis.chapter_id)
    requirements = _requirements(analysis.chapter_id, quality)
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = [_quality_candidate(item) for item in evidence.values()]
    plan = _plan_with_retries(
        project_root,
        profile,
        _planning_prompt(analysis.chapter_id, requirements, questions, candidates),
        output_dir / "coverage-plan",
        analysis.chapter_id,
        requirements,
        questions,
        evidence,
    )
    repaired, dispositions = _repair_answers(
        project_root,
        profile,
        analysis,
        requirements,
        plan,
        questions,
        _chapter_guide(project_root, analysis.chapter_id),
        evidence,
        output_dir,
        parallel_answers,
    )
    cited_ids = {
        evidence_id
        for answer in repaired
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    resolved = analysis.model_copy(
        update={
            "answers": repaired,
            "evidence": tuple(evidence[item] for item in sorted(cited_ids)),
            "omitted_candidate_ids": tuple(sorted(set(evidence) - cited_ids)),
        }
    )
    path = output_dir / "resolved-chapter-analysis.json"
    path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (output_dir / "coverage-repair-audit.json").write_text(
        json.dumps(
            {
                "chapter_id": analysis.chapter_id,
                "requirements": [item.model_dump() for item in requirements],
                "plan": plan.model_dump(),
                "dispositions": [item.model_dump() for item in dispositions],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _plan_with_retries(
    project_root,
    profile,
    prompt,
    output_dir,
    chapter_id,
    requirements,
    questions,
    evidence,
):
    feedback = ""
    for attempt in range(1, 4):
        plan = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            CoveragePlan,
            output_dir,
        )
        plan = _drop_unknown_evidence_ids(plan, evidence)
        try:
            _validate_plan(chapter_id, requirements, questions, evidence, plan)
            return plan
        except ValueError as exc:
            if attempt == 3:
                raise
            invalid_index = 1
            while (output_dir / f"output.invalid-{invalid_index}.json").exists():
                invalid_index += 1
            (output_dir / "output.json").rename(
                output_dir / f"output.invalid-{invalid_index}.json"
            )
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. Every "
                "chapter-wide requirement must be assigned to at least one question, "
                "and every immutable question route must be preserved."
            )
    raise AssertionError("unreachable")


def _drop_unknown_evidence_ids(plan: CoveragePlan, evidence) -> CoveragePlan:
    """Remove model-invented IDs while preserving the immutable repair routing."""

    valid_ids = set(evidence)
    return plan.model_copy(
        update={
            "mappings": tuple(
                mapping.model_copy(
                    update={
                        "evidence_ids": tuple(
                            evidence_id
                            for evidence_id in mapping.evidence_ids
                            if evidence_id in valid_ids
                        )
                    }
                )
                for mapping in plan.mappings
            )
        }
    )


def _requirements(chapter_id: str, quality: ChapterAnalysisQuality):
    rows = []
    for lens in quality.lens_quality:
        for omission in lens.material_omissions:
            rows.append(((lens.question_id,), omission))
        for error in lens.material_errors:
            rows.append(((lens.question_id,), error))
    for correction in quality.concrete_corrections_required:
        ids = tuple(sorted(set(re.findall(rf"{re.escape(chapter_id)}\.\d+", correction))))
        rows.append((ids, correction))
    return tuple(
        CoverageRequirement(
            requirement_id=f"REQ-{index:03d}", question_ids=ids, instruction=text
        )
        for index, (ids, text) in enumerate(rows, 1)
    )


def _planning_prompt(chapter_id, requirements, questions, candidates):
    return (
        f"Map every immutable {chapter_id} review requirement to its applicable question "
        "IDs and the complete candidate-index evidence IDs needed to address it. Keep an "
        "empty evidence_ids list only when the index contains no support. Select the one "
        "to four strongest direct, nonduplicative evidence IDs per requirement; do not "
        "map broad background merely because it is related. Do not rewrite or omit "
        "requirements. Return only schema JSON.\n\nREQUIREMENTS:\n"
        f"{json.dumps([x.model_dump() for x in requirements], ensure_ascii=False)}"
        f"\n\nQUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}"
        f"\n\nCOMPLETE CANDIDATE INDEX:\n{json.dumps(candidates, ensure_ascii=False)}"
    )


def _validate_plan(chapter_id, requirements, questions, evidence, plan):
    expected = {item.requirement_id for item in requirements}
    received = {item.requirement_id for item in plan.mappings}
    question_ids = {item["id"] for item in questions}
    if plan.chapter_id != chapter_id or received != expected:
        raise ValueError("coverage plan did not preserve every requirement")
    if len(plan.mappings) != len(expected):
        raise ValueError("coverage plan duplicated a requirement")
    for item in plan.mappings:
        if not set(item.question_ids).issubset(question_ids):
            raise ValueError("coverage plan invented a question ID")
        if not set(item.evidence_ids).issubset(evidence):
            raise ValueError("coverage plan invented an evidence ID")
        requirement = next(
            row for row in requirements if row.requirement_id == item.requirement_id
        )
        if requirement.question_ids and not set(requirement.question_ids).issubset(
            item.question_ids
        ):
            raise ValueError("coverage plan dropped an immutable question route")
        if not requirement.question_ids and not item.question_ids:
            raise ValueError("coverage plan left a chapter-wide requirement unrouted")


def _repair_answers(
    project_root,
    profile,
    analysis,
    requirements,
    plan,
    questions,
    guide,
    evidence,
    output_dir,
    parallel_answers,
):
    answer_by_id = {item.question_id: item for item in analysis.answers}
    question_by_id = {item["id"]: item for item in questions}
    mapping_by_id = {item.requirement_id: item for item in plan.mappings}
    assigned = {qid: [] for qid in question_by_id}
    for requirement in requirements:
        mapping = mapping_by_id[requirement.requirement_id]
        targets = tuple(sorted(set(mapping.question_ids) | set(requirement.question_ids)))
        for qid in targets:
            assigned[qid].append((requirement, mapping))
    results = {}
    with ThreadPoolExecutor(max_workers=parallel_answers) as executor:
        futures = {}
        for qid, question in question_by_id.items():
            current = answer_by_id[qid]
            rows = assigned[qid]
            allowed = set(current.supporting_evidence_ids)
            allowed.update(current.contrary_or_qualifying_evidence_ids)
            allowed.update(eid for _, mapping in rows for eid in mapping.evidence_ids)
            exact = [evidence[eid].model_dump(mode="json") for eid in sorted(allowed)]
            future = executor.submit(
                _repair_one,
                project_root,
                profile,
                question,
                guide,
                current,
                rows,
                exact,
                evidence,
                output_dir / "answers" / qid,
            )
            futures[future] = (qid, allowed, {r.requirement_id for r, _ in rows})
        for future in as_completed(futures):
            qid, allowed, required = futures[future]
            result = future.result()
            _validate_repair(result, qid, allowed, required)
            results[qid] = result
    ordered = tuple(results[item["id"]] for item in questions)
    answers = tuple(item.answer for item in ordered)
    dispositions = tuple(
        RoutedRequirementDisposition(question_id=question["id"], disposition=disposition)
        for question, item in zip(questions, ordered, strict=True)
        for disposition in item.dispositions
    )
    expected_routes = {
        (requirement.requirement_id, question_id)
        for question_id, rows in assigned.items()
        for requirement, _ in rows
    }
    validate_routed_dispositions(expected_routes, dispositions)
    return answers, dispositions


def _repair_one(
    project_root, profile, question, guide, current, rows, exact, evidence, output_dir
):
    prompt = _repair_prompt(question, guide, current, rows, exact)
    allowed = set(current.supporting_evidence_ids)
    allowed.update(current.contrary_or_qualifying_evidence_ids)
    allowed.update(eid for _, mapping in rows for eid in mapping.evidence_ids)
    required = {item.requirement_id for item, _ in rows}
    try:
        return _load_validated_repair(
            project_root,
            profile,
            prompt,
            output_dir,
            question["id"],
            allowed,
            required,
        )
    except subprocess.CalledProcessError:
        if len(prompt) <= 1_000_000 or len(rows) < 2:
            raise
    answer = current
    dispositions = []
    for index, group in enumerate(_repair_groups(question, guide, current, rows, evidence), 1):
        allowed = set(answer.supporting_evidence_ids)
        allowed.update(answer.contrary_or_qualifying_evidence_ids)
        allowed.update(eid for _, mapping in group for eid in mapping.evidence_ids)
        required = {item.requirement_id for item, _ in group}
        passages = [evidence[eid].model_dump(mode="json") for eid in sorted(allowed)]
        result = _load_validated_repair(
            project_root,
            profile,
            _repair_prompt(question, guide, answer, group, passages),
            output_dir / f"batch-{index:03d}",
            question["id"],
            allowed,
            required,
        )
        answer = result.answer
        dispositions.extend(result.dispositions)
    return RepairedLensAnswer(answer=answer, dispositions=tuple(dispositions))


def _load_validated_repair(
    project_root, profile, prompt, output_dir, question_id, allowed, required
):
    feedback = ""
    for attempt in range(1, 4):
        result = _load_or_execute_json(
            project_root,
            profile,
            prompt + feedback,
            RepairedLensAnswer,
            output_dir,
        )
        try:
            _validate_repair(result, question_id, allowed, required)
            return result
        except ValueError as exc:
            if attempt == 3:
                raise
            (output_dir / "output.json").rename(
                output_dir / f"output.invalid-{attempt}.json"
            )
            feedback = (
                f"\n\nCORRECTION REQUIRED AFTER ATTEMPT {attempt}: {exc}. "
                "Preserve the question ID, cite only supplied evidence IDs, and return "
                "exactly one disposition for every listed requirement."
            )
    raise AssertionError("unreachable")


def _repair_groups(question, guide, current, rows, evidence):
    groups = []
    pending = []
    for row in rows:
        proposal = [*pending, row]
        ids = set(current.supporting_evidence_ids)
        ids.update(current.contrary_or_qualifying_evidence_ids)
        ids.update(eid for _, mapping in proposal for eid in mapping.evidence_ids)
        exact = [evidence[eid].model_dump(mode="json") for eid in sorted(ids)]
        if pending and len(_repair_prompt(question, guide, current, proposal, exact)) > 850_000:
            groups.append(tuple(pending))
            pending = [row]
        else:
            pending = proposal
    groups.append(tuple(pending))
    return tuple(groups)


def _repair_prompt(question, guide, current, rows, exact):
    requirements = [
        {"requirement": req.model_dump(), "mapped_evidence_ids": mapping.evidence_ids}
        for req, mapping in rows
    ]
    return (
        "Repair this answer against every listed reviewer requirement in 550-1,100 "
        "words. Produce a detailed, judge-usable narrative, cite every material factual "
        "account, and "
        "preserve attribution, period, allegation status, contrary evidence, and gaps. "
        "Return one disposition for every requirement; code rejects omissions. Cite only "
        "the supplied exact evidence IDs. Return only schema JSON.\n\nQUESTION:\n"
        f"{json.dumps(question, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"CURRENT ANSWER:\n{current.model_dump_json()}\n\nREQUIREMENTS:\n"
        f"{json.dumps(requirements, ensure_ascii=False)}\n\nEXACT EVIDENCE:\n"
        f"{json.dumps(exact, ensure_ascii=False)}"
    )


def _validate_repair(result, question_id, allowed_ids, required_ids):
    if result.answer.question_id != question_id:
        raise ValueError("coverage repair changed question identity")
    cited = set(result.answer.supporting_evidence_ids)
    cited.update(result.answer.contrary_or_qualifying_evidence_ids)
    if not cited.issubset(allowed_ids):
        raise ValueError("coverage repair cited evidence that was not reopened")
    received = {item.requirement_id for item in result.dispositions}
    if received != required_ids or len(result.dispositions) != len(required_ids):
        raise ValueError("coverage repair did not disposition every requirement once")
    word_count = len(result.answer.answer.split())
    if not 450 <= word_count <= 1_300:
        raise ValueError(f"coverage repair answer has {word_count} words")


__all__ = ["run_chapter_coverage_repair"]
