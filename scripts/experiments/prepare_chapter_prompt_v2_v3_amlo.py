"""Freeze the AMLO 2022 5B prompt v2/v3 source-ecology experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from leaders_db.research import chapter_research_sequence as sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIOR_EXPERIMENT = (
    PROJECT_ROOT
    / "research/conversational-evidence/chapter-prompt-v1-v2-amlo-5b-2022-v1"
)
V3_VERSION = "chapter_research_prompt_v3_source_ecology"
SOURCE_ECOLOGY_STEP = (
    "2. **Plan coverage and source ecology.** For every selected lens, identify the "
    "important favorable, adverse, disputed, and exculpatory possibilities that "
    "research should test. Build a compact working coverage matrix with the material "
    "fact still needed, the best source families for it, whether an underlying source "
    "was opened, what evidence was found, and the remaining gap. Check the source "
    "routes that fit the case: laws and legislative records; enacted and executed "
    "budgets; procurement and contract records; appointments and personnel records; "
    "audits and responses; judgments and regulators; official statistics and "
    "administrative data; program evaluations; scholarship and policy research; "
    "international or independent monitoring; credible local, investigative, and "
    "specialist reporting; relevant local-language material; and credible contrary "
    "accounts. These are search routes, not quotas or a preferred-source hierarchy."
)


def main() -> None:
    """Write the frozen v2/v3 prompts and experiment manifest."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs = json.loads(
        (PRIOR_EXPERIMENT / "frozen/case-inputs.json").read_text(encoding="utf-8")
    )
    guide = (PROJECT_ROOT / inputs["guide_path"]).read_text(encoding="utf-8")
    v2 = sequence.load_chapter_research_prompt()
    v3 = sequence.ChapterResearchPromptConfig(
        version=V3_VERSION,
        template=_v3_template(v2.template),
    )

    frozen_dir = output_dir / "frozen"
    frozen_dir.mkdir()
    frozen_files = {
        "case-inputs.json": _write_json(frozen_dir / "case-inputs.json", inputs),
        "chapter-guide.md": _write_text(frozen_dir / "chapter-guide.md", guide),
        "chapter-research-prompt-v2.json": _write_json(
            frozen_dir / "chapter-research-prompt-v2.json", v2.model_dump()
        ),
        "chapter-research-prompt-v3.json": _write_json(
            frozen_dir / "chapter-research-prompt-v3.json", v3.model_dump()
        ),
    }
    for relative in (
        "src/leaders_db/conversational_evidence/data/questions.json",
        "src/leaders_db/conversational_evidence/data/question_lens_presentation.json",
        "configs/research-workflow.yaml",
        ".agents/skills/ruler-evidence-researcher/SKILL.md",
    ):
        source = PROJECT_ROOT / relative
        frozen_files[Path(relative).name] = _write_text(
            frozen_dir / Path(relative).name,
            source.read_text(encoding="utf-8"),
        )

    for version, config in (("v2", v2), ("v3", v3)):
        run_dir = output_dir / version / "run-01"
        run_dir.mkdir(parents=True)
        frozen_files[f"{version}/run-01/prompt.txt"] = _write_text(
            run_dir / "prompt.txt", _render_prompt(inputs, guide, config)
        )

    status = _git(["status", "--porcelain=v1"])
    manifest: dict[str, Any] = {
        "schema_version": "deep_chapter_prompt_source_ecology_experiment_v1",
        "status": "frozen_inputs_execution_pending",
        "case": {
            "ruler": inputs["job"]["ruler_name"],
            "country": inputs["job"]["country_name"],
            "period": [
                inputs["job"]["period_start_year"],
                inputs["job"]["period_end_year"],
            ],
            "chapter_id": "5B",
            "question_ids": inputs["job"]["input"]["question_ids"],
        },
        "single_changed_feature": {
            "name": "source_ecology_coverage_pass",
            "text": SOURCE_ECOLOGY_STEP,
        },
        "prompt_versions": {
            "baseline": v2.version,
            "candidate": v3.version,
        },
        "execution": {
            "model": "gpt-5.4-mini",
            "reasoning": "default_not_overridden",
            "web_search": "enabled",
            "fresh_ephemeral_session": True,
            "repository_access": "disabled",
            "filesystem_access": "disabled",
            "project_rules": "not_loaded",
            "plugins": "disabled",
            "subagents": "disabled",
            "client_scores": "excluded",
            "judge_scores": "excluded",
            "record_quota": None,
        },
        "evaluation": {
            "record_order": "deterministically_interleaved_blind_labels",
            "narrative_order": ["candidate_first", "baseline_first"],
            "record_count_role": "diagnostic_only",
            "internet_access": "disabled",
        },
        "repository": {
            "commit": _git(["rev-parse", "HEAD"]).strip(),
            "dirty": bool(status),
            "dirty_status_sha256": _sha256(status),
        },
        "frozen_file_sha256": frozen_files,
    }
    _write_json(output_dir / "manifest.json", manifest)


def _v3_template(v2_template: str) -> str:
    old = (
        "2. **Plan coverage.** For every selected lens, identify the important favorable, "
        "adverse, disputed, and exculpatory possibilities that research should test."
    )
    if v2_template.count(old) != 1:
        raise ValueError("v2 plan-coverage step was not found exactly once")
    return v2_template.replace(old, SOURCE_ECOLOGY_STEP)


def _render_prompt(
    inputs: dict[str, Any],
    guide: str,
    config: sequence.ChapterResearchPromptConfig,
) -> str:
    job = inputs["job"]
    chapter_id = "5B"
    selected_lenses = job["input"]["question_ids"]
    subject = sequence._chapter_subject(guide, chapter_id)
    identity = (
        f'{subject} under {job["ruler_name"]} in {job["country_name"]} '
        f'during {job["period_start_year"]}-{job["period_end_year"]}'
    )
    return config.template.format(
        identity=identity,
        prompt_config_version=config.version,
        lens_presentation_version=(
            sequence.load_question_lens_presentation().version
        ),
        evidence_category_key=sequence.render_evidence_category_key(),
        layered_lenses=sequence.render_lens_table(selected_lenses),
        compact_guide=sequence._compact_chapter_guide(guide),
        reconnaissance_summary=json.dumps(
            inputs["reconnaissance_summary"], separators=(",", ":"), sort_keys=True
        ),
        resource_index_json=json.dumps(
            inputs["resource_index"], separators=(",", ":"), sort_keys=True
        ),
        chapter_id=chapter_id,
        selected_lenses_json=json.dumps(selected_lenses),
    )


def _git(arguments: list[str]) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _write_text(path: Path, value: str) -> str:
    path.write_text(value, encoding="utf-8")
    return _sha256(value)


def _write_json(path: Path, value: Any) -> str:
    return _write_text(
        path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


if __name__ == "__main__":
    main()
