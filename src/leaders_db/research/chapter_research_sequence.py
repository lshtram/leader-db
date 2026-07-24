"""Run one focused research turn per selected chapter in the same Codex thread."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from ._codex_worker_setup import WorkerAttempt
from .codex_worker_command import (
    build_codex_exec_command,
    build_codex_resume_command,
    read_codex_thread_id,
)
from .job_ledger import checkpoint_job
from .model_profiles import ResearchModelProfile
from .research_workflow import ResearchWorkflow

ResearchCheckpoint = tuple[Path, str, Path, str, str]


def run_chapter_research_sequence(
    engine: Engine,
    *,
    checkpoint: ResearchCheckpoint,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    workflow: ResearchWorkflow,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> ResearchCheckpoint:
    """Run one fresh compact researcher session for each selected chapter."""

    current = checkpoint
    reconnaissance_session_id = read_codex_thread_id(checkpoint[0])
    for chapter_id in _selected_chapters(job, workflow):
        guide_path = next(
            (project_root / "docs/methodology/chapter-guides").glob(
                f"{chapter_id.lower()}-*.md"
            )
        )
        prompt = build_chapter_research_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide_path.read_text(encoding="utf-8"),
            workflow=workflow,
            resource_index=_chapter_resource_index(attempt, chapter_id),
            reconnaissance_summary=_bounded_reconnaissance_summary(current[1]),
        )
        prompt_hash = sha256(prompt.encode()).hexdigest()
        recovered = _existing_chapter_turn(
            attempt,
            chapter_id,
            job_id=int(job["id"]),
            chapter_session_mode=workflow.chapter_session_mode,
            prompt_hash=prompt_hash,
            provider_profile=str(job["provider_profile"]),
        )
        output_path = attempt.attempt_dir / f"research-chapter-{chapter_id}.md"
        events_path = attempt.trusted_dir / f"research-chapter-{chapter_id}.events.jsonl"
        base_manifest_path = (
            attempt.trusted_dir / f"research-ledger-before-{chapter_id}.json"
        )
        if recovered is None:
            _snapshot_parent_manifest(attempt, base_manifest_path)
            (attempt.trusted_dir / f"research-chapter-{chapter_id}.prompt.txt").write_text(
                prompt, encoding="utf-8"
            )
            if workflow.chapter_session_mode == "fresh_compact_context":
                command = build_codex_exec_command(
                    profile=profile,
                    project_root=project_root,
                    schema_path=None,
                    final_message_path=output_path,
                    writable_dir=attempt.attempt_dir,
                )
            else:
                command = build_codex_resume_command(
                    profile=profile,
                    session_id=reconnaissance_session_id,
                    project_root=project_root,
                    final_message_path=output_path,
                    writable_dir=attempt.attempt_dir,
                )
            checkpoint_job(
                engine,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                checkpoint={
                    "phase": "chapter_research",
                    "chapter_id": chapter_id,
                    "reconnaissance_session_id": reconnaissance_session_id,
                    "chapter_session_mode": workflow.chapter_session_mode,
                },
            )
            (
                attempt.trusted_dir / f"research-chapter-{chapter_id}.starting.json"
            ).write_text(
                json.dumps(
                    {
                        "chapter_id": chapter_id,
                        "job_id": job["id"],
                        "chapter_session_mode": workflow.chapter_session_mode,
                        "prompt_sha256": prompt_hash,
                        "provider_profile": str(job["provider_profile"]),
                        "workflow_version": workflow.version,
                    }
                ),
                encoding="utf-8",
            )
            from .codex_worker import _run_codex

            _run_codex(
                engine,
                command=command,
                prompt=prompt,
                events_path=events_path,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
        else:
            events_path, output_path, base_manifest_path = recovered
        if not output_path.is_file() or not output_path.stat().st_size:
            from .codex_worker import WorkerOutputError

            raise WorkerOutputError(
                f"chapter researcher produced no handoff for {chapter_id}"
            )
        if output_path.stat().st_size > 5_000_000:
            from .codex_worker import WorkerOutputError

            raise WorkerOutputError(
                f"chapter researcher handoff exceeds 5 MB for {chapter_id}"
            )
        addition = output_path.read_text(encoding="utf-8")
        notebook = (
            f"{current[1]}\n\n--- CHAPTER RESEARCH {chapter_id} ---\n\n{addition}"
        )
        from .notebook_continuation import _append_current_ledger_manifest

        notebook = _append_current_ledger_manifest(
            notebook,
            attempt,
            source_attempt_dir=output_path.parent,
            base_manifest_path=base_manifest_path,
        )
        notebook_path = attempt.trusted_dir / f"research-notebook-{chapter_id}.md"
        notebook_path.write_text(notebook, encoding="utf-8")
        notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
        events_hash = sha256(events_path.read_bytes()).hexdigest()
        current = (
            events_path,
            notebook,
            notebook_path,
            notebook_hash,
            events_hash,
        )
        (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
            json.dumps(
                {
                    "job_key": job["job_key"],
                    "provider_profile": job["provider_profile"],
                    "provider": profile.provider,
                    "model": profile.model,
                    "notebook_path": str(notebook_path),
                    "notebook_sha256": notebook_hash,
                    "events_path": str(events_path),
                    "events_sha256": events_hash,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return current


def build_chapter_research_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    workflow: ResearchWorkflow,
    resource_index: tuple[dict[str, Any], ...] = (),
    reconnaissance_summary: str = "",
) -> str:
    """Build the validated natural-language deep-research prompt."""

    del workflow
    selected_lenses = [
        item
        for item in job["input"]["question_ids"]
        if str(item).startswith(f"{chapter_id}.")
    ]
    compact_guide = _compact_chapter_guide(guide)
    subject = _chapter_subject(guide, chapter_id)
    identity = (
        f'{subject} under {job["ruler_name"]} in {job["country_name"]} '
        f'during {job["period_start_year"]}-{job["period_end_year"]}'
    )
    return f"""Research {identity}.

Prepare a complete, carefully sourced account for researchers who will assess this part
of the ruler's record. Research the subject without assigning a score.

Use the questions below as different angles on the same subject. They identify important
evidence; they are not separate ratings, search quotas, or an arithmetic checklist.

{compact_guide}

Earlier web reconnaissance produced this short briefing about authority, reporting
conditions, statistics, source concentration, and possible distortions:

{reconnaissance_summary}

The structured local-data package is prepared and retained separately by the parent
workflow. It is not reproduced here and does not need to be rebuilt or re-fetched.

These web resources were found in earlier research and may be useful:

{json.dumps(resource_index, separators=(",", ":"), sort_keys=True)}

Build the factual record through six observable evidence channels:

1. formal acts and law: bills, enacted laws, votes, vetoes, decrees, regulations,
   treaties, pardons, directives, and official strategy;
2. resources: authorized and executed budgets, transfers, procurement, contracts,
   staffing, equipment, and infrastructure;
3. personnel: appointments, removals, qualifications, conflicts, tenure, and practical
   autonomy;
4. implementation and operational conduct: rules issued, delivery, inspections,
   enforcement, deployments, compliance, correction, and remedy;
5. public communications and representations: speeches, testimony, promises,
   explanations, threats, denials, propaganda, admissions, and corrections; and
6. outcomes: observable chapter-relevant changes without assuming that outcomes alone
   prove ruler credit or blame.

Use the channels that materially fit this chapter; they are not quotas or separate
scores. Keep the evidence source type separate from the observed fact. For example, an
audit or court record may verify a resource, formal-act, implementation, communication,
or outcome claim. Authority, baseline, constraints, distribution, exposure, causation,
durability, and source bias are questions for interpreting the evidence rather than
additional evidence channels.

Start by forming a working account of the ruler's formal and practical authority, the
inherited baseline, external shocks and constraints, and the important favorable,
adverse, disputed, and exculpatory possibilities raised by every selected question.

Treat the resource list as a starting point. Open an underlying source before using it
as evidence, including a source found earlier. Search primary and legal records,
independent monitoring, scholarship, reputable reporting, archives, relevant
local-language material, and credible favorable, adverse, and contrary interpretations.
Look for direct ruler statements, decisions, implementation, outcomes, correction or
remedy, and evidence that challenges an initially plausible conclusion.

Continue while research produces a materially new fact, a stronger underlying source,
credible contrary evidence, an important missing perspective, or a necessary
correction. Conclude when additional searching mostly repeats what is already known.
There is no document or evidence-record quota.

Write one machine record for one source supporting one material claim. Give records
about the same underlying fact or event a shared `underlying_fact_key`, while keeping
their distinct URLs, locators, publication dates, and evidentiary status. State when
apparently independent reports depend on the same investigation, dataset, wire story,
official claim, or event.
A report that contains materially distinct audit rows, programs, decisions, events,
findings, or remedies needs a separate source-claim record and precise locator for each
one you intend downstream users to reason from. Do not bundle them into an omnibus
record merely because they share a PDF or publisher.

Each developed record contains:

- a short name and one precise factual claim;
- why the fact matters to the selected questions;
- source title, publisher, date, direct URL, and stable locator;
- target-period, inherited, or later-retrospective status;
- direct, authority-based, institutional, shared, limited, or unknown attribution;
- credible contrary or limiting evidence;
- source limitations and dependencies;
- exact question IDs supported; and
- separately identified independent corroboration.

Keep fully extracted evidence, opened corroboration, reused evidence, uninspected leads,
rejected sources, and access-blocked sources separate. An unanswered question gets an
honest source-landscape summary.

Return:

1. a concise authority, baseline, shock, and information-environment orientation;
2. a compact evidence index listing each record ID, fact name, and why it matters;
3. a disposition for every selected question, citing records or explaining the gap;
4. separate corroboration, reused-source, uninspected-lead, rejected, and blocked lists;
5. counts of sources discovered, opened, accepted, reused, rejected, and blocked;
6. remaining questions and whether more research is likely to add material information;
7. the machine records below.

Keep the compact index short and put each complete record only in its machine line.

For every developed record, include one physical line outside code fences beginning
`SOURCE_CLAIM_JSON:`. The remainder is a valid JSON object containing `title`,
`publisher`, `publication_date`, `url`, `claim`, `locator`, `provisional_id`,
`canonical_fact_key`, `disposition`, `chapter_ids`, `methodology_ids`, `source_type`,
`source_confidence`, `source_confidence_reason`, `final_evidence_use`, `period_fit`,
`ruler_attribution`, `contrary_evidence`, `underlying_fact_key`, and `lenses`.

Use only `final_evidence`, `context`, or `discovery_only` for both `disposition` and
`final_evidence_use`. Put rejected and uninspected sources in their separate lists
rather than emitting them as accepted machine records.

Use unique IDs beginning `WEB-{chapter_id}-`, use `{chapter_id}` as the chapter label,
and include the exact supported question IDs from
{json.dumps(selected_lenses)}. The parent workflow merges these append-only records into
the complete ledger.
"""


def _chapter_subject(guide: str, chapter_id: str) -> str:
    """Return the chapter's plain-language subject from its title."""

    first_line = next(
        (
            line.removeprefix("# ").strip()
            for line in guide.splitlines()
            if line.startswith("# ")
        ),
        f"Chapter {chapter_id}",
    )
    subject = first_line.replace(f"Chapter {chapter_id}", "").strip(" —-:")
    return subject or f"Chapter {chapter_id}"


def _compact_chapter_guide(guide: str) -> str:
    """Keep researcher-facing questions while excluding judge-only instructions."""

    headings = ("## Ten Evidence Lenses", "## Researcher Evidence Plan")
    stop_headings = (
        "## Baseline, Attribution, and Sparse Evidence",
        "## Chapter Judge",
    )
    sections: list[str] = []
    for heading in headings:
        start = guide.find(heading)
        if start < 0:
            continue
        possible_ends = [
            index
            for stop in stop_headings
            if (index := guide.find(stop, start + len(heading))) >= 0
        ]
        next_section = guide.find("\n## ", start + len(heading))
        if next_section >= 0:
            possible_ends.append(next_section)
        end = min(possible_ends) if possible_ends else len(guide)
        sections.append(guide[start:end].strip())
    return "\n\n".join(sections) if sections else guide[:4_000].strip()


def _bounded_reconnaissance_summary(notebook: str) -> str:
    """Return a few paragraphs without carrying the evidence ledger or tool history."""

    marker = "--- RESEARCH LEDGER MANIFEST ---"
    text = notebook.rsplit(marker, maxsplit=1)[0]
    anchors = (
        "Evidence-environment",
        "Evidence environment",
        "Identity, authority",
        "Identity and authority",
    )
    starts = [index for anchor in anchors if (index := text.find(anchor)) >= 0]
    start = min(starts) if starts else 0
    summary = text[start : start + 3_000].strip()
    return summary or "No reconnaissance prose was recoverable; verify authority directly."


def _snapshot_parent_manifest(attempt: WorkerAttempt, destination: Path) -> None:
    """Freeze the parent ledger before a model can write a chapter delta."""

    current = attempt.attempt_dir / "research-ledger-manifest.json"
    if current.is_file():
        payload = current.read_text(encoding="utf-8")
    else:
        payload = json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [],
            },
            sort_keys=True,
        )
    destination.write_text(payload, encoding="utf-8")


def _selected_chapters(
    job: dict[str, Any], workflow: ResearchWorkflow
) -> tuple[str, ...]:
    selected = {
        str(item).split(".", maxsplit=1)[0]
        for item in job["input"]["question_ids"]
    }
    return tuple(chapter for chapter in workflow.chapter_order if chapter in selected)


def _existing_chapter_turn(
    attempt: WorkerAttempt,
    chapter_id: str,
    *,
    job_id: int,
    chapter_session_mode: str,
    prompt_hash: str,
    provider_profile: str,
) -> tuple[Path, Path, Path] | None:
    """Recover a completed chapter turn from any prior worker attempt."""

    job_dir = attempt.attempt_dir.parent.parent
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        events_path = trusted / f"research-chapter-{chapter_id}.events.jsonl"
        output_path = (
            job_dir
            / "attempts"
            / trusted.name
            / f"research-chapter-{chapter_id}.md"
        )
        if not events_path.is_file() or not output_path.is_file():
            continue
        starting_path = trusted / f"research-chapter-{chapter_id}.starting.json"
        base_manifest_path = trusted / f"research-ledger-before-{chapter_id}.json"
        try:
            starting = json.loads(starting_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            starting.get("job_id") != job_id
            or starting.get("chapter_session_mode") != chapter_session_mode
            or starting.get("prompt_sha256") != prompt_hash
            or starting.get("provider_profile") != provider_profile
            or not base_manifest_path.is_file()
        ):
            continue
        from .codex_worker import _events_show_completed_turn

        if _events_show_completed_turn(events_path):
            return events_path, output_path, base_manifest_path
    return None


def _chapter_resource_index(
    attempt: WorkerAttempt, chapter_id: str
) -> tuple[dict[str, Any], ...]:
    """Expose a small list of already found chapter-relevant resources."""

    path = attempt.attempt_dir / "research-ledger-manifest.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return ()
    relevant = []
    cross_chapter = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        compact = {
            key: entry[key]
            for key in (
                "provisional_id",
                "url",
                "claim",
                "locator",
                "disposition",
            )
            if entry.get(key)
        }
        chapter_ids = entry.get("chapter_ids", [])
        if chapter_id in chapter_ids:
            relevant.append(compact)
        elif len(chapter_ids) >= 3:
            cross_chapter.append(compact)
    return tuple((relevant[:15] + cross_chapter[:5])[:20])


__all__ = ["build_chapter_research_prompt", "run_chapter_research_sequence"]
