"""Controlled chapter saturation pilot; production research remains unchanged."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from leaders_db.conversational_evidence.researcher import CodexResearcher
from leaders_db.research.chapter_guides import load_chapter_guide

from .artifacts import write_json
from .claims import LedgerClaim, build_ledger, ledger_quality, parse_chapter_note
from .prompts import saturation_chapter
from .runner import _check_budget, _compact_claim_index, _read_json, prepare_inputs


@dataclass(frozen=True)
class SaturationPolicy:
    """Model-independent breadth targets and stopping controls."""

    candidate_target_per_wave: int = 35
    opened_target_per_wave: int = 20
    accepted_url_min: int = 20
    accepted_url_max: int = 35
    domain_min: int = 10
    marginal_url_stop: int = 2
    max_waves: int = 4

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(value <= 0 for value in values.values()):
            raise ValueError("saturation policy values must all be positive")
        if self.accepted_url_min > self.accepted_url_max:
            raise ValueError("accepted_url_min may not exceed accepted_url_max")


def run_chapter_saturation(
    *,
    project_root: Path,
    output_dir: Path,
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    chapter_id: str,
    researcher_name: str = "gpt-5.4-mini",
    cost_ceiling_usd: float = 3.0,
    policy: SaturationPolicy = SaturationPolicy(),
) -> dict[str, object]:
    """Run generic search waves until measurable saturation or a hard cap."""

    if chapter_id not in {f"{number}B" for number in range(1, 9)}:
        raise ValueError(f"invalid chapter_id: {chapter_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    prepare_inputs(project_root, output_dir, ruler, country, iso3, year, "")
    raw_priors = _read_json(output_dir / "inputs" / "local-priors.json")
    chapter_priors = [
        row
        for row in raw_priors
        if str(row.get("methodology_id", "")).startswith(chapter_id)
    ]
    guide = load_chapter_guide(chapter_id, project_root=project_root)[0]
    state_path = output_dir / "saturation-state.json"
    state = _read_json(state_path) if state_path.exists() else {}
    researcher = CodexResearcher(
        project_root,
        output_dir / ".researcher",
        researcher_name,
        thread_id=(
            str(state["research_thread_id"])
            if state.get("research_thread_id")
            else None
        ),
    )
    wave_dir = output_dir / "waves"
    wave_dir.mkdir(exist_ok=True)
    previous_urls = 0
    history: list[dict[str, object]] = []
    for wave in range(1, policy.max_waves + 1):
        wave_path = wave_dir / f"wave-{wave:02d}.md"
        if not wave_path.exists():
            _check_budget(output_dir, researcher_name, cost_ceiling_usd)
            records = _records(output_dir, chapter_id)
            note = researcher.ask(
                saturation_chapter(
                    ruler,
                    country,
                    year,
                    chapter_id,
                    guide,
                    chapter_priors,
                    _compact_claim_index(records),
                    wave=wave,
                    candidate_target=policy.candidate_target_per_wave,
                    opened_target=policy.opened_target_per_wave,
                    accepted_min=policy.accepted_url_min,
                    accepted_max=policy.accepted_url_max,
                    domain_min=policy.domain_min,
                )
            )
            parse_chapter_note(note, chapter_id)
            wave_path.write_text(note + "\n", encoding="utf-8")
            _compile_waves(output_dir, chapter_id)
        records = _records(output_dir, chapter_id)
        metrics = ledger_quality(records)["chapters"][chapter_id]
        metrics.update(_composition_metrics(records, chapter_id))
        current_urls = int(metrics["distinct_urls"])
        marginal_urls = current_urls - previous_urls
        history.append(
            {"wave": wave, **metrics, "marginal_distinct_urls": marginal_urls}
        )
        previous_urls = current_urls
        reached_floor = (
            current_urls >= policy.accepted_url_min
            and int(metrics["domains"]) >= policy.domain_min
        )
        confirmed_saturation = (
            wave > 1
            and marginal_urls < policy.marginal_url_stop
            and not metrics["composition_warnings"]
        )
        reached_ceiling = (
            current_urls >= policy.accepted_url_max
            and not metrics["composition_warnings"]
        )
        state = {
            "schema_version": "chapter-saturation-state-v1",
            "research_thread_id": researcher.thread_id,
            "chapter_id": chapter_id,
            "policy": asdict(policy),
            "history": history,
            "status": "running",
        }
        write_json(state_path, state)
        if reached_ceiling or (reached_floor and confirmed_saturation):
            break
    records = _records(output_dir, chapter_id)
    final_metrics = ledger_quality(records)["chapters"][chapter_id]
    final_metrics.update(_composition_metrics(records, chapter_id))
    met_floor = (
        int(final_metrics["distinct_urls"]) >= policy.accepted_url_min
        and int(final_metrics["domains"]) >= policy.domain_min
    )
    met_quality_target = met_floor and not final_metrics["composition_warnings"]
    state["status"] = (
        "quality_target_reached"
        if met_quality_target
        else "quality_target_unmet_after_max_waves"
    )
    state["final_metrics"] = final_metrics
    write_json(state_path, state)
    write_json(
        output_dir / "evidence-ledger.json",
        [record.model_dump(mode="json") for record in records],
    )
    return state


def _compile_waves(output: Path, chapter_id: str) -> None:
    notes = [
        path.read_text(encoding="utf-8")
        for path in sorted((output / "waves").glob("wave-*.md"))
    ]
    chapter_path = output / "chapters" / f"{chapter_id}.md"
    if not notes:
        if chapter_path.exists() and not chapter_path.read_text(encoding="utf-8").strip():
            chapter_path.unlink()
        return
    chapter_path.parent.mkdir(exist_ok=True)
    chapter_path.write_text("\n\n".join(notes) + "\n", encoding="utf-8")


def _records(output: Path, chapter_id: str) -> tuple[LedgerClaim, ...]:
    _compile_waves(output, chapter_id)
    if not (output / "chapters" / f"{chapter_id}.md").exists():
        return ()
    return build_ledger(output)


def _composition_metrics(
    records: tuple[LedgerClaim, ...], chapter_id: str
) -> dict[str, object]:
    selected = [
        record
        for record in records
        if chapter_id in record.chapters
        and record.final_evidence_use != "discovery_only"
    ]
    official = sum(record.source_type in {"official", "primary", "legal"} for record in selected)
    share = official / len(selected) if selected else 0.0
    warnings = ["official_or_primary_share_above_67_percent"] if share > 0.67 else []
    return {
        "official_or_primary_claims": official,
        "official_or_primary_share": round(share, 4),
        "composition_warnings": warnings,
    }


__all__ = ["SaturationPolicy", "run_chapter_saturation"]
