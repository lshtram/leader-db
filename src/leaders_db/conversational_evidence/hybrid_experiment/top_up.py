"""Resume one full-ruler thread for generic post-curation evidence top-ups."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leaders_db.conversational_evidence.researcher import CodexResearcher
from leaders_db.research.chapter_guides import load_chapter_guide

from .artifacts import CHAPTERS, write_json
from .claims import build_ledger, dossier, ledger_quality, parse_follow_up
from .prompts import saturation_top_up
from .runner import (
    _check_budget,
    _compact_claim_index,
    _existing_notes,
    _profile,
    _read_json,
    _write_state,
)


def run_top_ups(
    *,
    project_root: Path,
    output_dir: Path,
    researcher_name: str = "gpt-5.4-mini",
    cost_ceiling_usd: float = 7.5,
) -> dict[str, object]:
    """Run one new wave for every chapter failing the curated quality floor."""

    summary = _read_json(output_dir / "curation-summary.json")
    chapters = chapters_needing_top_up(summary)
    state = _read_json(output_dir / "session.json")
    researcher = CodexResearcher(
        project_root,
        output_dir / ".researcher",
        researcher_name,
        thread_id=str(state["research_thread_id"]),
    )
    reviewer_follow_up = output_dir / "follow-up-reviewer.md"
    follow_up = output_dir / "follow-up.md"
    if follow_up.exists() and not reviewer_follow_up.exists():
        reviewer_follow_up.write_bytes(follow_up.read_bytes())
    completed = []
    for chapter_id in chapters:
        chapter_dir = output_dir / "top-ups" / chapter_id
        existing = sorted(chapter_dir.glob("wave-*.md"))
        wave = len(existing) + 1
        path = chapter_dir / f"wave-{wave:02d}.md"
        _check_budget(output_dir, researcher_name, cost_ceiling_usd)
        records = build_ledger(output_dir)
        guide = load_chapter_guide(chapter_id, project_root=project_root)[0]
        curation = _read_json(
            _active_curation_path(output_dir / "chapter-curation" / chapter_id)
        )
        note = researcher.ask(
            saturation_top_up(
                str(_read_json(output_dir / "inputs" / "identity.json")["ruler"]),
                int(_read_json(output_dir / "inputs" / "identity.json")["year"]),
                chapter_id,
                guide,
                _compact_claim_index(records),
                curation,
                wave=wave,
            )
        )
        parse_follow_up(note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note + "\n", encoding="utf-8")
        _compile_follow_ups(output_dir)
        _write_state(output_dir, researcher.thread_id, f"top-up-{chapter_id}-{wave}")
        completed.append(chapter_id)
    records = build_ledger(output_dir)
    quality = ledger_quality(records)
    write_json(
        output_dir / "evidence-ledger.json",
        [record.model_dump(mode="json") for record in records],
    )
    write_json(output_dir / "quality-summary.json", quality)
    _rebuild_raw_dossier(output_dir, records)
    profile = _profile(output_dir, researcher_name, records, quality)
    write_json(output_dir / "profile.json", profile)
    _write_state(output_dir, researcher.thread_id, "top-ups-complete")
    report = {
        "schema_version": "full-ruler-top-up-report-v1",
        "chapters_requested": list(chapters),
        "chapters_completed": completed,
        "quality_after_top_up": quality,
        "profile": profile,
    }
    write_json(output_dir / "top-up-report.json", report)
    return report


def chapters_needing_top_up(summary: dict[str, Any]) -> tuple[str, ...]:
    """Select material failures, treating 20 URLs/10 families as soft targets."""

    selected = []
    for chapter_id in CHAPTERS:
        chapter = summary["chapters"][chapter_id]
        if (
            int(chapter["distinct_urls"]) < 15
            or int(chapter["source_families"]) < 8
            or len(chapter["mapped_lenses"]) < 10
        ):
            selected.append(chapter_id)
    return tuple(selected)


def _compile_follow_ups(output: Path) -> None:
    parts = []
    reviewer = output / "follow-up-reviewer.md"
    if reviewer.exists():
        parts.append(reviewer.read_text(encoding="utf-8").strip())
    parts.extend(
        path.read_text(encoding="utf-8").strip()
        for path in sorted((output / "top-ups").glob("*/*.md"))
    )
    (output / "follow-up.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def _active_curation_path(chapter_dir: Path) -> Path:
    candidates = (
        chapter_dir / "curation-updated-final.json",
        chapter_dir / "curation-updated.json",
        chapter_dir / "curation-final.json",
        chapter_dir / "curation.json",
    )
    return next(path for path in candidates if path.exists())


def _rebuild_raw_dossier(output: Path, records: Any) -> None:
    identity = _read_json(output / "inputs" / "identity.json")
    review_path = (
        output / "review-final.json"
        if (output / "review-final.json").exists()
        else output / "review.json"
    )
    rebuilt = dossier(
        ruler=str(identity["ruler"]),
        country=str(identity["country"]),
        iso3=str(identity["iso3"]),
        year=int(identity["year"]),
        records=records,
        review=_read_json(review_path),
        notes={key: note for key, note in _existing_notes(output)},
    )
    value = rebuilt
    write_json(output / "dossier-uncurated.json", value)
    write_json(output / "dossier.json", value)


__all__ = ["chapters_needing_top_up", "run_top_ups"]
