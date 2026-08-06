"""Resumable candidate-heavy research experiment across all eight chapters."""

from __future__ import annotations

from pathlib import Path

from .data import DATA_DIR, load
from .deep_artifacts import (
    atomic_text as _atomic_text,
)
from .deep_artifacts import (
    candidate_ids as _candidate_ids,
)
from .deep_artifacts import (
    candidate_inventory as _candidate_inventory,
)
from .deep_artifacts import (
    canonical_url,
)
from .deep_artifacts import (
    chapter_priors as _chapter_priors,
)
from .deep_artifacts import (
    chunks as _chunks,
)
from .deep_artifacts import (
    final_ledger_valid as _final_ledger_valid,
)
from .deep_artifacts import (
    id_number as _id_number,
)
from .deep_artifacts import (
    last_candidate_id as _last_candidate_id,
)
from .deep_artifacts import (
    load_local_priors as _load_local_priors,
)
from .deep_artifacts import (
    prior_summary as _prior_summary,
)
from .deep_artifacts import (
    urls as _urls,
)
from .deep_artifacts import (
    validate_final_ledger as _validate_final_ledger,
)
from .deep_artifacts import (
    write_profile as _write_profile,
)
from .deep_models import (
    ChapterState,
    DeepSession,
    DeepWorkflowConfig,
    PendingPhase,
    load_session,
    load_workflow,
    save_model,
)
from .researcher import CodexResearcher


def collect_deep(
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    output_dir: Path,
    local_priors_path: Path,
    *,
    researcher: str = "gpt-5.4-mini",
    workflow_path: Path | None = None,
    project_root: Path | None = None,
    conversation: CodexResearcher | None = None,
) -> Path:
    """Run or resume the experimental all-chapter workflow."""

    root = (project_root or Path.cwd()).resolve()
    output = output_dir.resolve()
    workflow = load_workflow(workflow_path or DATA_DIR / "deep-workflow.json")
    priors = _load_local_priors(local_priors_path, ruler=ruler, iso3=iso3, year=year)
    session_path = output / "session.json"
    session = _session(
        session_path,
        ruler=ruler,
        country=country,
        iso3=iso3,
        year=year,
        researcher=researcher,
        workflow=workflow,
    )
    chat = conversation or CodexResearcher(
        root,
        output / ".researcher",
        researcher,
        session.thread_id,
        timeout_seconds=workflow.turn_timeout_seconds,
    )
    prompts = load("deep-prompts.json")
    chapter_questions = _chapter_questions()

    _run_phase(
        session,
        session_path,
        chat,
        output,
        phase_key="reconnaissance",
        artifact=Path("raw/reconnaissance.md"),
        prompt=prompts["reconnaissance"].format(
            ruler=ruler,
            country=country,
            iso3=iso3.upper(),
            year=year,
            local_prior_summary=_prior_summary(priors),
        ),
    )
    for chapter_id in workflow.chapters:
        state = session.chapters.setdefault(chapter_id, ChapterState())
        guide = _chapter_guide(root, chapter_id)
        lenses = _lenses(chapter_questions[chapter_id])
        chapter_priors = _chapter_priors(priors, chapter_id)
        _discover(
            session,
            state,
            session_path,
            chat,
            output,
            prompts,
            chapter_id=chapter_id,
            guide=guide,
            lenses=lenses,
            chapter_priors=chapter_priors,
        )
        _inspect(
            session,
            state,
            session_path,
            chat,
            output,
            prompts,
            chapter_id=chapter_id,
            lenses=lenses,
        )
        _finalize(
            session,
            state,
            session_path,
            chat,
            output,
            prompts,
            chapter_id=chapter_id,
            lenses=lenses,
        )
    profile_path = _write_profile(output, session)
    return profile_path


def _session(
    path: Path,
    *,
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    researcher: str,
    workflow: DeepWorkflowConfig,
) -> DeepSession:
    existing = load_session(path)
    if existing is not None:
        expected = (ruler, country, iso3.upper(), year, researcher)
        actual = (
            existing.ruler,
            existing.country,
            existing.iso3,
            existing.year,
            existing.researcher,
        )
        if actual != expected or existing.workflow != workflow:
            raise ValueError("output directory belongs to a different deep run")
        return existing
    session = DeepSession(
        ruler=ruler,
        country=country,
        iso3=iso3.upper(),
        year=year,
        researcher=researcher,
        workflow=workflow,
    )
    save_model(path, session)
    return session


def _discover(
    session: DeepSession,
    state: ChapterState,
    session_path: Path,
    chat: CodexResearcher,
    output: Path,
    prompts: dict[str, object],
    *,
    chapter_id: str,
    guide: str,
    lenses: str,
    chapter_priors: str,
) -> None:
    config = session.workflow
    while (
        len(state.verified_candidate_urls) < config.candidate_target
        and state.discovery_rounds < config.discovery_max_rounds
    ):
        round_number = state.discovery_rounds + 1
        artifact = Path(f"chapters/{chapter_id}/discovery-{round_number:02d}.md")
        if round_number == 1:
            prompt = str(prompts["discovery"]).format(
                chapter_id=chapter_id,
                ruler=session.ruler,
                year=session.year,
                candidate_target=config.candidate_target,
                chapter_guide=guide,
                lenses=lenses,
                chapter_local_priors=chapter_priors,
            )
        else:
            prompt = str(prompts["discovery_continue"]).format(
                chapter_id=chapter_id,
                ruler=session.ruler,
                last_candidate_id=_last_candidate_id(state.candidate_ids, chapter_id),
                verified_count=len(state.verified_candidate_urls),
                candidate_target=config.candidate_target,
                existing_urls="\n".join(state.verified_candidate_urls),
                lenses=lenses,
            )
        _run_phase(
            session,
            session_path,
            chat,
            output,
            phase_key=f"{chapter_id}:discovery:{round_number:02d}",
            artifact=artifact,
            prompt=prompt,
        )
        state.discovery_rounds = round_number
        notes = _artifacts(output / "chapters" / chapter_id, "discovery-*.md")
        state.verified_candidate_urls = tuple(sorted(_urls(notes)))
        state.candidate_ids = tuple(sorted(_candidate_ids(notes, chapter_id), key=_id_number))
        save_model(session_path, session)


def _inspect(
    session: DeepSession,
    state: ChapterState,
    session_path: Path,
    chat: CodexResearcher,
    output: Path,
    prompts: dict[str, object],
    *,
    chapter_id: str,
    lenses: str,
) -> None:
    if not state.candidate_ids:
        raise ValueError(f"{chapter_id} discovery produced no candidate IDs")
    discovery = _artifacts(output / "chapters" / chapter_id, "discovery-*.md")
    waves = tuple(_chunks(state.candidate_ids, session.workflow.inspection_wave_size))
    for index, candidate_ids in enumerate(waves, start=1):
        if index <= state.inspection_waves_completed:
            continue
        _run_phase(
            session,
            session_path,
            chat,
            output,
            phase_key=f"{chapter_id}:inspection:{index:02d}",
            artifact=Path(f"chapters/{chapter_id}/inspection-{index:02d}.md"),
            prompt=str(prompts["inspection"]).format(
                chapter_id=chapter_id,
                ruler=session.ruler,
                candidate_ids=", ".join(candidate_ids),
                lenses=lenses,
                candidate_inventory=_candidate_inventory(discovery, candidate_ids),
            ),
        )
        state.inspection_waves_completed = index
        save_model(session_path, session)


def _finalize(
    session: DeepSession,
    state: ChapterState,
    session_path: Path,
    chat: CodexResearcher,
    output: Path,
    prompts: dict[str, object],
    *,
    chapter_id: str,
    lenses: str,
) -> None:
    initial_artifact = Path(f"chapters/{chapter_id}/final.md")
    if state.finalized and state.final_artifact:
        _validate_final_ledger(
            output / state.final_artifact,
            chapter_id,
            session.workflow,
        )
        return
    inspections = _artifacts(output / "chapters" / chapter_id, "inspection-*.md")
    if not initial_artifact.is_file():
        _run_phase(
            session,
            session_path,
            chat,
            output,
            phase_key=f"{chapter_id}:final",
            artifact=initial_artifact,
            prompt=str(prompts["finalize"]).format(
                chapter_id=chapter_id,
                ruler=session.ruler,
                year=session.year,
                verified_candidates=len(state.verified_candidate_urls),
                accepted_minimum=session.workflow.accepted_minimum,
                accepted_maximum=session.workflow.accepted_maximum,
                lenses=lenses,
                inspection_notebook=inspections,
            ),
        )
    selected_artifact = initial_artifact
    if not _final_ledger_valid(output / initial_artifact, chapter_id, session.workflow):
        selected_artifact = Path(f"chapters/{chapter_id}/final-selected.md")
        _run_phase(
            session,
            session_path,
            chat,
            output,
            phase_key=f"{chapter_id}:final-selection",
            artifact=selected_artifact,
            prompt=str(prompts["finalize_selection"]).format(
                chapter_id=chapter_id,
                ruler=session.ruler,
                year=session.year,
                accepted_minimum=session.workflow.accepted_minimum,
                accepted_maximum=session.workflow.accepted_maximum,
                oversized_ledger=(output / initial_artifact).read_text(encoding="utf-8"),
            ),
        )
    _validate_final_ledger(output / selected_artifact, chapter_id, session.workflow)
    state.finalized = True
    state.final_artifact = str(selected_artifact)
    save_model(session_path, session)


def _run_phase(
    session: DeepSession,
    session_path: Path,
    chat: CodexResearcher,
    output: Path,
    *,
    phase_key: str,
    artifact: Path,
    prompt: str,
) -> str:
    artifact_path = output / artifact
    if phase_key in session.completed_phases:
        if not artifact_path.is_file():
            raise ValueError(f"completed phase is missing artifact: {phase_key}")
        return artifact_path.read_text(encoding="utf-8")
    if session.pending is not None and session.pending.phase_key != phase_key:
        raise ValueError(f"unresolved pending phase: {session.pending.phase_key}")
    if session.pending is None:
        session.pending = PendingPhase(
            phase_key=phase_key,
            turn_number=chat.turn,
            artifact_path=str(artifact),
        )
        save_model(session_path, session)
    researcher_note = chat.work_dir / f"turn-{session.pending.turn_number:03d}.md"
    if artifact_path.is_file():
        note = artifact_path.read_text(encoding="utf-8")
    elif researcher_note.is_file():
        note = researcher_note.read_text(encoding="utf-8")
        _atomic_text(artifact_path, note)
    else:
        note = chat.ask(prompt)
        _atomic_text(artifact_path, note)
    session.thread_id = chat.thread_id
    session.completed_phases = (*session.completed_phases, phase_key)
    session.pending = None
    save_model(session_path, session)
    return note


def _artifacts(directory: Path, pattern: str) -> str:
    return "\n\n".join(path.read_text(encoding="utf-8") for path in sorted(directory.glob(pattern)))


def _chapter_questions() -> dict[str, list[dict[str, str]]]:
    chapters = load("questions.json")["chapters"]
    return {str(chapter["id"]): list(chapter["questions"]) for chapter in chapters}


def _lenses(questions: list[dict[str, str]]) -> str:
    return "\n".join(f"{item['id']}: {item['text']}" for item in questions)


def _chapter_guide(root: Path, chapter_id: str) -> str:
    matches = tuple((root / "docs/methodology/chapter-guides").glob(f"{chapter_id.lower()}-*.md"))
    if len(matches) != 1:
        raise ValueError(f"expected one chapter guide for {chapter_id}")
    return matches[0].read_text(encoding="utf-8")


__all__ = ["canonical_url", "collect_deep"]
