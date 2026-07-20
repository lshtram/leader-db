"""Resumable orchestration for the isolated v2 full-ruler experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.conversational_evidence.deep_artifacts import (
    _cumulative_usage,
    _estimated_cost,
)
from leaders_db.conversational_evidence.researcher import CodexResearcher
from leaders_db.db.engine import build_engine
from leaders_db.research._codex_worker_setup import collect_local_priors
from leaders_db.research.chapter_guides import load_chapter_guide
from leaders_db.research.local_prior_package import compact_local_priors

from . import prompts
from .artifacts import (
    CHAPTERS,
    baseline_manifest,
    write_json,
)
from .claims import (
    LedgerClaim,
    build_ledger,
    dossier,
    ledger_quality,
    parse_chapter_note,
    parse_follow_up,
)
from .review_models import validate_review


def run_experiment(
    *,
    project_root: Path,
    output_dir: Path,
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    ruler_id: str = "",
    researcher_name: str = "gpt-5.4-mini",
    cost_ceiling_usd: float = 7.0,
) -> dict[str, object]:
    """Run or resume reconnaissance, eight chapters, review, follow-up, and format."""

    output_dir.mkdir(parents=True, exist_ok=True)
    prepare_inputs(
        project_root, output_dir, ruler, country, iso3, year, ruler_id
    )
    prior_package = _read_json(output_dir / "inputs" / "local-prior-package.json")
    raw_priors = _read_json(output_dir / "inputs" / "local-priors.json")
    thread_id = _read_state(output_dir).get("research_thread_id")
    researcher = CodexResearcher(
        project_root,
        output_dir / ".researcher",
        researcher_name,
        thread_id=str(thread_id) if thread_id else None,
    )
    guides = _run_research(
        project_root=project_root,
        output=output_dir,
        researcher=researcher,
        researcher_name=researcher_name,
        ruler=ruler,
        country=country,
        year=year,
        prior_package=prior_package,
        raw_priors=raw_priors,
        cost_ceiling_usd=cost_ceiling_usd,
    )
    records = build_ledger(output_dir)
    warnings = ledger_quality(records)
    write_json(
        output_dir / "evidence-ledger.json",
        [item.model_dump(mode="json") for item in records],
    )
    write_json(output_dir / "quality-summary.json", warnings)
    package = _package(output_dir, records)
    review_path = output_dir / "review.json"
    if not review_path.exists():
        review_value = validate_review(
            _no_search_turn(
                project_root,
                output_dir / ".reviewer",
                researcher_name,
                prompts.review(
                    ruler,
                    year,
                    "\n\n".join(guides.values()),
                    warnings,
                    package,
                ),
            )
        )
        write_json(review_path, review_value)

    review_value = _read_json(review_path)
    gaps = _recoverable_gaps(review_value)
    follow_path = output_dir / "follow-up.md"
    if gaps and not follow_path.exists():
        _check_budget(output_dir, researcher_name, cost_ceiling_usd)
        note = researcher.ask(
            prompts.follow_up(ruler, year, _compact_claim_index(records), gaps)
        )
        parse_follow_up(note)
        follow_path.write_text(note + "\n", encoding="utf-8")
        _write_state(output_dir, researcher.thread_id, "follow-up")
        records = build_ledger(output_dir)
        warnings = ledger_quality(records)
        write_json(
            output_dir / "evidence-ledger.json",
            [item.model_dump(mode="json") for item in records],
        )
        write_json(output_dir / "quality-summary.json", warnings)
        package = _package(output_dir, records)
        final_review = validate_review(
            _no_search_turn(
                project_root,
                output_dir / ".reviewer-final",
                researcher_name,
                prompts.review(
                    ruler,
                    year,
                    "\n\n".join(guides.values()),
                    warnings,
                    package,
                    final=True,
                ),
            ),
            final=True,
        )
        write_json(output_dir / "review-final.json", final_review)
        review_value = final_review

    dossier_path = output_dir / "dossier.json"
    if not dossier_path.exists():
        formatted = dossier(
            ruler=ruler,
            country=country,
            iso3=iso3.upper(),
            year=year,
            records=records,
            review=review_value,
            notes={key: note for key, note in _existing_notes(output_dir)},
        )
        write_json(dossier_path, formatted)

    profile = _profile(output_dir, researcher_name, records, warnings)
    write_json(output_dir / "profile.json", profile)
    _write_state(output_dir, researcher.thread_id, "complete")
    return profile


def _run_research(
    *,
    project_root: Path,
    output: Path,
    researcher: CodexResearcher,
    researcher_name: str,
    ruler: str,
    country: str,
    year: int,
    prior_package: object,
    raw_priors: list[dict[str, Any]],
    cost_ceiling_usd: float,
) -> dict[str, str]:
    recon_path = output / "reconnaissance.md"
    if not recon_path.exists():
        _check_budget(output, researcher_name, cost_ceiling_usd)
        note = researcher.ask(prompts.reconnaissance(ruler, country, year, prior_package))
        recon_path.write_text(note + "\n", encoding="utf-8")
        _write_state(output, researcher.thread_id, "reconnaissance")
    guides = {
        chapter_id: load_chapter_guide(chapter_id, project_root=project_root)[0]
        for chapter_id in CHAPTERS
    }
    for chapter_id, guide in guides.items():
        chapter_path = output / "chapters" / f"{chapter_id}.md"
        if chapter_path.exists():
            continue
        _check_budget(output, researcher_name, cost_ceiling_usd)
        records = build_ledger(output)
        chapter_priors = [
            item
            for item in raw_priors
            if str(item.get("methodology_id", "")).startswith(chapter_id)
        ]
        note = researcher.ask(
            prompts.chapter(
                ruler,
                year,
                chapter_id,
                guide,
                chapter_priors,
                _compact_claim_index(records),
            )
        )
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        parse_chapter_note(note, chapter_id)
        chapter_path.write_text(note + "\n", encoding="utf-8")
        _write_state(output, researcher.thread_id, chapter_id)
    return guides


def prepare_inputs(
    root: Path,
    output: Path,
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    ruler_id: str,
) -> None:
    inputs = output / "inputs"
    baseline = inputs / "production-baseline.json"
    if not baseline.exists():
        write_json(baseline, baseline_manifest(root))
    raw_path = inputs / "local-priors.json"
    if raw_path.exists():
        expected = {"ruler": ruler, "country": country, "iso3": iso3.upper(), "year": year}
        if _read_json(inputs / "identity.json") != expected:
            raise ValueError("saved experiment identity does not match requested identity")
        return
    engine = build_engine(f"sqlite:///{root / 'data/catalog/leaders_db.sqlite'}")
    job = {
        "ruler_id": ruler_id,
        "ruler_name": ruler,
        "iso3": iso3.upper(),
        "period_start_year": year,
        "period_end_year": year,
        "input": {
            "question_ids": [
                f"{chapter}.{lens}"
                for chapter in CHAPTERS
                for lens in range(1, 11)
            ]
        },
    }
    rows = collect_local_priors(engine, job)
    for row in rows:
        leader = row.get("leader", {})
        country_value = row.get("country", {})
        if leader.get("name") != ruler or country_value.get("iso3") != iso3.upper():
            raise ValueError("generated local priors do not match the locked identity")
        if row.get("client_matrix_policy") != "excluded_as_evidence":
            raise ValueError("local priors did not exclude client-matrix evidence")
    write_json(raw_path, rows)
    write_json(
        inputs / "local-prior-package.json",
        compact_local_priors(rows).model_dump(mode="json"),
    )
    write_json(
        inputs / "identity.json",
        {"ruler": ruler, "country": country, "iso3": iso3.upper(), "year": year},
    )


def _existing_notes(output: Path) -> list[tuple[str, str]]:
    notes = []
    recon = output / "reconnaissance.md"
    if recon.exists():
        notes.append(("RECON", recon.read_text(encoding="utf-8")))
    for chapter_id in CHAPTERS:
        path = output / "chapters" / f"{chapter_id}.md"
        if path.exists():
            notes.append((chapter_id, path.read_text(encoding="utf-8")))
    follow = output / "follow-up.md"
    if follow.exists():
        notes.append(("FOLLOW_UP", follow.read_text(encoding="utf-8")))
    return notes


def _package(output: Path, records: tuple[LedgerClaim, ...]) -> dict[str, object]:
    return {
        "evidence_ledger": [item.model_dump(mode="json") for item in records],
        "notes": {key: note for key, note in _existing_notes(output)},
    }


def _no_search_turn(root: Path, work: Path, researcher: str, prompt: str) -> dict[str, Any]:
    agent = CodexResearcher(root, work, researcher)
    answer = agent.ask(prompt)
    profile = _read_json(sorted(work.glob("turn-*.profile.json"))[-1])
    if profile.get("tool_calls"):
        raise ValueError("no-search turn used a tool")
    return _json_answer(answer)


def _json_answer(answer: str) -> dict[str, Any]:
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        if cleaned.startswith("json\n"):
            cleaned = cleaned[5:]
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _recoverable_gaps(review: dict[str, Any]) -> list[dict[str, Any]]:
    if review.get("overall_decision") != "targeted_follow_up":
        return []
    return [
        {"chapter_id": chapter.get("chapter_id"), **gap}
        for chapter in review.get("chapters", [])
        if chapter.get("decision") == "targeted_follow_up"
        for gap in chapter.get("material_gaps", [])
    ]


def _profile(
    output: Path,
    researcher: str,
    records: tuple[LedgerClaim, ...],
    warnings: dict[str, object],
) -> dict[str, object]:
    work_dirs = [
        output / name
        for name in (".researcher", ".reviewer", ".reviewer-final", ".formatter")
    ]
    profiles = [
        _read_json(path)
        for work in work_dirs
        for path in sorted(work.glob("turn-*.profile.json"))
    ]
    usage: dict[str, int] = {}
    for work in work_dirs:
        for key, value in _cumulative_usage(work).items():
            usage[key] = usage.get(key, 0) + value
    pricing = CodexResearcher(output.parent, output, researcher).config["pricing_per_million"]
    return {
        "schema_version": "hybrid-experiment-profile-v1",
        "turns": len(profiles),
        "duration_seconds": round(
            sum(float(item.get("duration_seconds", 0)) for item in profiles), 3
        ),
        "tool_calls": sum(sum(item.get("tool_calls", {}).values()) for item in profiles),
        "usage": usage,
        "estimated_cost_usd": _estimated_cost(usage, pricing),
        "evidence": warnings,
        "quality_summary": warnings,
    }


def _check_budget(output: Path, researcher: str, ceiling: float) -> None:
    usage = _cumulative_usage(output / ".researcher")
    config = CodexResearcher(output.parent, output, researcher).config
    cost = _estimated_cost(usage, config["pricing_per_million"]) or 0.0
    if cost >= ceiling:
        raise RuntimeError(f"research cost ceiling reached: ${cost:.2f} >= ${ceiling:.2f}")


def _read_state(output: Path) -> dict[str, Any]:
    path = output / "session.json"
    return _read_json(path) if path.exists() else {}


def _write_state(output: Path, thread_id: str | None, completed: str) -> None:
    write_json(
        output / "session.json",
        {"research_thread_id": thread_id, "last_completed": completed},
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_claim_index(records: tuple[LedgerClaim, ...], limit: int = 180) -> str:
    rows = []
    for item in records[-limit:]:
        value = item.model_dump(mode="json")
        rows.append(
            f"{value['evidence_id']} | {value['publisher']} | {value['canonical_url']} | "
            f"{','.join(value['lenses'])} | {value['claim'][:180]}"
        )
    return "\n".join(rows) or "No accepted web evidence yet."


__all__ = ["prepare_inputs", "run_experiment"]
