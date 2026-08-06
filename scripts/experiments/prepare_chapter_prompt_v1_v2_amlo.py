"""Freeze the AMLO 2022 5B chapter-research prompt v1/v2 quality gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from leaders_db.research import chapter_research_sequence as sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = (
    PROJECT_ROOT
    / "research/conversational-evidence/chapter-prompt-ad-2022-v1/amlo-5b/inputs.json"
)
V1_COMMIT = "8d40df0"
V1_CONFIG_PATH = (
    "src/leaders_db/conversational_evidence/data/chapter_research_prompt.json"
)
MODEL = "gpt-5.4-mini"
REASONING = "default_not_overridden"

EVALUATOR_RUBRIC = """# Blind Deep-Chapter Research Quality Rubric

Compare artifact X with artifact Y without searching and without scoring the ruler.
Counts are diagnostics, not quality targets. Evaluate the evidence, not prose length.

For each artifact assess:

1. unique material underlying facts and independent source families;
2. depth for every selected lens and importance of unresolved gaps;
3. source authority, independence, method, proximity, and temporal fit;
4. opened underlying sources and precise page, section, paragraph, table, or record locators;
5. direct conduct, formal responsibility, shared authority, and contextual attribution;
6. favorable, adverse, disputed, contrary, and exculpatory evidence;
7. contemporaneous versus later-retrospective evidence;
8. atomic claims, dependency clustering, and duplication;
9. laws, resources, personnel, implementation, rhetoric, and outcomes where relevant; and
10. machine validity plus downstream reviewer and formatter usability.

Report component assessments, overall quality, the better artifact or a tie, material
regressions, unique gains, padding or weak inspection, and a promotion recommendation.
A candidate cannot advance with a material regression in source validity, locators,
attribution, atomicity, or contrary-evidence treatment.
"""


def main() -> None:
    """Write frozen prompts, evaluator inputs, manifest, and checksums."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs = json.loads(args.inputs.read_text(encoding="utf-8"))
    guide_path = PROJECT_ROOT / inputs["guide_path"]
    guide = guide_path.read_text(encoding="utf-8")
    v1_config = sequence.ChapterResearchPromptConfig.model_validate(
        json.loads(_git_show(V1_COMMIT, V1_CONFIG_PATH))
    )
    v2_config = sequence.load_chapter_research_prompt()
    prompts = {
        "v1": _render_prompt(inputs, guide, v1_config),
        "v2": _render_prompt(inputs, guide, v2_config),
    }

    frozen_dir = output_dir / "frozen"
    frozen_dir.mkdir()
    files: dict[str, str] = {}
    files["case-inputs.json"] = _write_json(frozen_dir / "case-inputs.json", inputs)
    files["chapter-guide.md"] = _write_text(frozen_dir / "chapter-guide.md", guide)
    for relative in (
        "src/leaders_db/conversational_evidence/data/questions.json",
        "src/leaders_db/conversational_evidence/data/question_lens_presentation.json",
        "configs/research-workflow.yaml",
        ".agents/skills/ruler-evidence-researcher/SKILL.md",
    ):
        source = PROJECT_ROOT / relative
        files[Path(relative).name] = _write_text(
            frozen_dir / Path(relative).name,
            source.read_text(encoding="utf-8"),
        )
    files["chapter-research-prompt-v1.json"] = _write_json(
        frozen_dir / "chapter-research-prompt-v1.json", v1_config.model_dump()
    )
    files["chapter-research-prompt-v2.json"] = _write_json(
        frozen_dir / "chapter-research-prompt-v2.json", v2_config.model_dump()
    )
    files["evaluator-rubric.md"] = _write_text(
        frozen_dir / "evaluator-rubric.md", EVALUATOR_RUBRIC
    )

    for version, prompt in prompts.items():
        run_dir = output_dir / version / "run-01"
        run_dir.mkdir(parents=True)
        files[f"{version}/run-01/prompt.txt"] = _write_text(
            run_dir / "prompt.txt", prompt
        )
        (run_dir / "PENDING").write_text(
            "Fresh isolated researcher execution has not run.\n", encoding="utf-8"
        )
    for order, labels in (
        ("forward", {"X": "v1", "Y": "v2"}),
        ("reverse", {"X": "v2", "Y": "v1"}),
    ):
        eval_dir = output_dir / "evaluation" / order
        eval_dir.mkdir(parents=True)
        files[f"evaluation/{order}/label-map.json"] = _write_json(
            eval_dir / "label-map.json", labels
        )
        (eval_dir / "PENDING").write_text(
            "Blind no-search evaluation has not run.\n", encoding="utf-8"
        )

    repo_status = _git(["status", "--porcelain=v1"])
    manifest: dict[str, Any] = {
        "schema_version": "deep_chapter_prompt_quality_experiment_v1",
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
        "prompt_versions": {
            "baseline": v1_config.version,
            "candidate": v2_config.version,
            "baseline_commit": V1_COMMIT,
        },
        "execution": {
            "model": MODEL,
            "reasoning": REASONING,
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
            "blind_runs": 2,
            "orders": ["forward", "reverse"],
            "internet_access": "disabled",
            "record_count_role": "diagnostic_only",
        },
        "repository": {
            "commit": _git(["rev-parse", "HEAD"]).strip(),
            "dirty": bool(repo_status),
            "dirty_status_sha256": _sha256(repo_status),
        },
        "frozen_file_sha256": files,
    }
    _write_json(output_dir / "manifest.json", manifest)
    checksum_paths = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name not in {"PENDING", "checksums.sha256"}
    )
    checksum_text = "".join(
        f"{_sha256(path.read_text(encoding='utf-8'))}  "
        f"{path.relative_to(output_dir)}\n"
        for path in checksum_paths
    )
    (output_dir / "checksums.sha256").write_text(checksum_text, encoding="utf-8")


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


def _git_show(commit: str, path: str) -> str:
    return _git(["show", f"{commit}:{path}"])


def _git(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


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
