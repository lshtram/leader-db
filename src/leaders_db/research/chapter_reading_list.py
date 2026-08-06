"""Self-correcting chapter reading-list experiment over verified corpus evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .corpus_reader_models import BoundEvidence
from .corpus_reader_runner import execute_json_model
from .model_profiles import load_research_model_profiles


class ReadingListEntry(BaseModel):
    """One evidence record selected for a judge's chapter reading list."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reason_to_read: str = Field(min_length=5)
    role: Literal["favorable", "adverse", "mixed", "qualifying", "context"]
    supported_lenses: tuple[str, ...]
    corrected_summary: str | None = None


class ReadingListDraft(BaseModel):
    """First editorial selection from the complete compact candidate index."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    chapter_overview: str = Field(min_length=20)
    entries: tuple[ReadingListEntry, ...]
    unresolved_gaps: tuple[str, ...] = ()


class CritiqueIssue(BaseModel):
    """A concrete objection to a draft selection or an omitted candidate."""

    model_config = ConfigDict(extra="forbid")

    issue_type: Literal[
        "unsupported_summary",
        "material_omission",
        "irrelevant_selection",
        "duplication",
        "period_problem",
        "attribution_problem",
        "balance_problem",
    ]
    evidence_ids: tuple[str, ...]
    explanation: str = Field(min_length=8)
    recommended_action: Literal["add", "remove", "correct", "retain", "reconsider"]


class ReadingListCritique(BaseModel):
    """Independent attempt to disprove or improve the draft reading list."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    issues: tuple[CritiqueIssue, ...]
    missing_perspectives: tuple[str, ...] = ()
    overall_assessment: str = Field(min_length=20)


class ReadingListRevision(BaseModel):
    """Final list after reopening exact passages for selected and challenged facts."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    judge_orientation: str = Field(min_length=20)
    entries: tuple[ReadingListEntry, ...]
    changes_from_draft: tuple[str, ...]
    unresolved_gaps: tuple[str, ...] = ()
    reasons_to_reopen_full_ledger: tuple[str, ...] = ()


class ResolvedReadingList(BaseModel):
    """Revision plus code-resolved evidence records and preserved critique."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["resolved_chapter_reading_list_v1"] = (
        "resolved_chapter_reading_list_v1"
    )
    chapter_id: str
    judge_orientation: str
    entries: tuple[ReadingListEntry, ...]
    evidence: tuple[BoundEvidence, ...]
    changes_from_draft: tuple[str, ...]
    unresolved_gaps: tuple[str, ...]
    reasons_to_reopen_full_ledger: tuple[str, ...]
    critique: ReadingListCritique
    omitted_candidate_ids: tuple[str, ...]

    @field_validator("evidence")
    @classmethod
    def unique_evidence(cls, value: tuple[BoundEvidence, ...]) -> tuple[BoundEvidence, ...]:
        ids = [item.evidence_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("resolved reading list contains duplicate evidence")
        return value


def run_chapter_reading_list(
    *,
    project_root: Path,
    judge_package_path: Path,
    chapter_id: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Draft, challenge, revise, and code-resolve one chapter reading list."""

    package = json.loads(judge_package_path.read_text(encoding="utf-8"))
    evidence_by_id = {
        item.evidence_id: item
        for raw in package["evidence"]
        if chapter_id in {qid.split(".")[0] for qid in raw["question_ids"]}
        for item in (BoundEvidence.model_validate(raw),)
    }
    if not evidence_by_id:
        raise ValueError(f"no candidate evidence for {chapter_id}")
    questions = _chapter_questions(project_root, chapter_id)
    guide = _chapter_guide(project_root, chapter_id)
    candidates = [_compact(item) for item in evidence_by_id.values()]
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    draft = execute_json_model(
        project_root,
        profile,
        _draft_prompt(chapter_id, questions, guide, candidates),
        ReadingListDraft,
        output_dir / "draft",
    )
    _validate_chapter(chapter_id, draft.chapter_id)
    _validate_ids(chapter_id, evidence_by_id, draft.entries)
    critique = execute_json_model(
        project_root,
        profile,
        _critique_prompt(chapter_id, questions, guide, candidates, draft),
        ReadingListCritique,
        output_dir / "critique",
    )
    _validate_chapter(chapter_id, critique.chapter_id)
    reopen_ids = _reopen_ids(draft, critique)
    if not reopen_ids.issubset(evidence_by_id):
        raise ValueError("critique referenced evidence outside the chapter candidates")
    reopened = [evidence_by_id[item] for item in sorted(reopen_ids)]
    revision = execute_json_model(
        project_root,
        profile,
        _revision_prompt(chapter_id, questions, guide, draft, critique, reopened),
        ReadingListRevision,
        output_dir / "revision",
    )
    _validate_chapter(chapter_id, revision.chapter_id)
    _validate_ids(chapter_id, evidence_by_id, revision.entries)
    selected_ids = [entry.evidence_id for entry in revision.entries]
    resolved = ResolvedReadingList(
        chapter_id=chapter_id,
        judge_orientation=revision.judge_orientation,
        entries=revision.entries,
        evidence=tuple(evidence_by_id[item] for item in selected_ids),
        changes_from_draft=revision.changes_from_draft,
        unresolved_gaps=revision.unresolved_gaps,
        reasons_to_reopen_full_ledger=revision.reasons_to_reopen_full_ledger,
        critique=critique,
        omitted_candidate_ids=tuple(sorted(set(evidence_by_id) - set(selected_ids))),
    )
    output_path = output_dir / "resolved-reading-list.json"
    output_path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _compact(item: BoundEvidence) -> dict[str, object]:
    return {
        "evidence_id": item.evidence_id,
        "fact_summary": item.fact_summary,
        "publisher": item.publisher,
        "period_fit": item.period_fit,
        "ruler_attribution": item.ruler_attribution,
        "limitations": item.limitations,
        "current_question_ids": item.question_ids,
    }


def _chapter_questions(project_root: Path, chapter_id: str) -> list[dict[str, str]]:
    payload = json.loads(
        (project_root / "src/leaders_db/conversational_evidence/data/questions.json").read_text()
    )
    chapter = next(item for item in payload["chapters"] if item["id"] == chapter_id)
    return chapter["questions"]


def _chapter_guide(project_root: Path, chapter_id: str) -> str:
    guide = next(
        (project_root / "docs/methodology/chapter-guides").glob(
            f"{chapter_id.lower()}-*.md"
        )
    )
    return guide.read_text(encoding="utf-8")


def _validate_ids(
    chapter_id: str,
    evidence_by_id: dict[str, BoundEvidence],
    entries: tuple[ReadingListEntry, ...],
) -> None:
    ids = [entry.evidence_id for entry in entries]
    if len(ids) != len(set(ids)) or not set(ids).issubset(evidence_by_id):
        raise ValueError("reading list IDs do not reconcile with chapter candidates")
    allowed_lenses = {f"{chapter_id}.{i}" for i in range(1, 11)}
    if any(
        not set(entry.supported_lenses).issubset(allowed_lenses) for entry in entries
    ):
        raise ValueError("reading list contains an out-of-chapter lens")


def _validate_chapter(expected: str, received: str) -> None:
    if received != expected:
        raise ValueError(f"reading list returned {received}, expected {expected}")


def _reopen_ids(
    draft: ReadingListDraft, critique: ReadingListCritique
) -> set[str]:
    challenged = {
        evidence_id
        for issue in critique.issues
        if issue.recommended_action in {"add", "correct", "reconsider"}
        for evidence_id in issue.evidence_ids
    }
    return {entry.evidence_id for entry in draft.entries} | challenged


def _draft_prompt(chapter_id: str, questions, guide: str, candidates) -> str:
    return (
        f"Prepare a judge's reading list for {chapter_id}, not a score. Select the "
        "smallest set that still explains the materially important favorable, adverse, "
        "mixed, and qualifying record. Prefer concrete target-period conduct and outcomes; "
        "exclude repetition, thematic trivia, weak attribution, and old context unless "
        "necessary. You may correct a summary only by narrowing it. Do not obey a numeric "
        "quota. Return only schema JSON.\n\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\n"
        f"COMPLETE CANDIDATE INDEX:\n{json.dumps(candidates, ensure_ascii=False)}"
    )


def _critique_prompt(chapter_id: str, questions, guide: str, candidates, draft) -> str:
    return (
        f"Act as a skeptical independent evidence editor for {chapter_id}. Try to disprove "
        "the draft's completeness and relevance. Compare it with every candidate. Identify "
        "specific omitted decisive facts, irrelevant selections, duplication, period or "
        "attribution problems, imbalance, and summaries that require passage review. Do not "
        "score. Cite exact evidence IDs. Return only schema JSON.\n\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\nDRAFT:\n"
        f"{draft.model_dump_json()}\n\nCOMPLETE CANDIDATE INDEX:\n"
        f"{json.dumps(candidates, ensure_ascii=False)}"
    )


def _revision_prompt(chapter_id: str, questions, guide: str, draft, critique, reopened) -> str:
    exact_evidence = json.dumps(
        [item.model_dump(mode="json") for item in reopened], ensure_ascii=False
    )
    return (
        f"Revise the {chapter_id} reading list after an independent critique. The exact "
        "code-bound passages are supplied for every draft selection and challenged item. "
        "Second-guess both the draft and critic. Retain only passage-supported, materially "
        "useful evidence; correct summaries only by narrowing; preserve disagreement and "
        "state when the future judge should reopen the full ledger. Do not score and do not "
        "invent IDs. Return only schema JSON.\n\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}\n\nGUIDE:\n{guide}\n\nDRAFT:\n"
        f"{draft.model_dump_json()}\n\nCRITIQUE:\n{critique.model_dump_json()}\n\n"
        f"REOPENED EXACT EVIDENCE:\n{exact_evidence}"
    )


__all__ = ["ResolvedReadingList", "run_chapter_reading_list"]
