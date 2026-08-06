"""Compile and blindly evaluate matched document-reader evidence dossiers."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from leaders_db.conversational_evidence.document_reader_experiment import (
    ReaderSummaryEnvelope,
    load_document_reader_config,
)
from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import (
    ResearchModelProfile,
    load_research_model_profiles,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PROFILES = PROJECT_ROOT / "configs/research-models.yaml"

EVALUATOR_RUBRIC = """Compare dossier X with dossier Y without researching or scoring
the ruler. Judge content, not JSON or prose style. Audit unique supported material
facts, material omissions, locator usability, preservation of qualifications,
period fit, ruler attribution, contrary evidence, source independence and incentives,
official-source corroboration, duplication, and downstream judgeability. Counts are
diagnostic only. Report material regressions, unique gains, unsupported claims, repair
burden, and whether Y preserves evidence quality relative to X."""


def main() -> None:
    """Compile both arms with one model, then run order-reversed blind evaluations."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    config = load_document_reader_config(experiment_dir / "frozen/document_reader_experiment.json")
    profiles = load_research_model_profiles(MODEL_PROFILES).profiles
    compiler = profiles[config.compiler]
    selection = _read_json(experiment_dir / "candidate-selection.json")
    candidate_profile = str(selection["selected_profile"])
    candidate_dir = _candidate_dir(experiment_dir, candidate_profile, config.reader_ladder[0])

    dossier_paths = {
        "baseline": compile_arm(
            experiment_dir,
            experiment_dir / "arm-a-sol",
            compiler,
            config.compiler_prompt,
        ),
        "candidate": compile_arm(
            experiment_dir,
            candidate_dir,
            compiler,
            config.compiler_prompt,
        ),
    }
    for order, labels in (
        ("forward", {"X": "baseline", "Y": "candidate"}),
        ("reverse", {"X": "candidate", "Y": "baseline"}),
    ):
        output_dir = experiment_dir / "evaluation" / order
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "label-map.json", labels)
        prompt = EVALUATOR_RUBRIC
        for label in ("X", "Y"):
            prompt += f"\n\n# Dossier {label}\n\n" + dossier_paths[labels[label]].read_text(
                encoding="utf-8"
            )
        (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        execute_prompt(
            compiler,
            prompt,
            output_path=output_dir / "evaluation.md",
            events_path=output_dir / "events.jsonl",
            stderr_path=output_dir / "stderr.txt",
            writable_dir=output_dir,
        )


def compile_arm(
    experiment_dir: Path,
    arm_dir: Path,
    compiler: ResearchModelProfile,
    compiler_prompt: str,
) -> Path:
    """Compile one arm from maps plus locator-targeted underlying passages."""

    summary = _read_json(arm_dir / "full-run-summary.json")
    maps = [
        ReaderSummaryEnvelope.model_validate_json(
            (experiment_dir / map_path).read_text(encoding="utf-8")
        )
        for document in summary["documents"]
        for map_path in document["map_paths"]
    ]
    verification = build_verification_packet(experiment_dir, maps)
    output_dir = arm_dir / "compiled"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = "\n\n".join(
        (
            compiler_prompt,
            "Return a human-readable complete evidence dossier followed by one "
            "`SOURCE_CLAIM_JSON:` line per accepted or context claim. Do not score.",
            "SOURCE MAPS:\n"
            + json.dumps(
                [item.model_dump(mode="json") for item in maps],
                ensure_ascii=False,
            ),
            "UNDERLYING VERIFICATION PASSAGES:\n" + json.dumps(verification, ensure_ascii=False),
        )
    )
    output_path = output_dir / "dossier.md"
    (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    execute_prompt(
        compiler,
        prompt,
        output_path=output_path,
        events_path=output_dir / "events.jsonl",
        stderr_path=output_dir / "stderr.txt",
        writable_dir=output_dir,
    )
    return output_path


def build_verification_packet(
    experiment_dir: Path,
    maps: list[ReaderSummaryEnvelope],
) -> list[dict[str, object]]:
    """Reopen claim locator units from the immutable extracted document."""

    manifest = _read_json(experiment_dir / "manifest.json")
    by_requested = {
        str(item["requested_source_id"]): item for item in manifest["acquired_documents"]
    }
    packet: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for source_map in maps:
        document = by_requested[source_map.source_id]
        extraction = _read_json(experiment_dir / str(document["extracted_path"]))
        units = {int(item["unit"]): item for item in extraction["units"]}
        locator_numbers = source_map.claimed_locator_numbers or (1,)
        for unit_number in locator_numbers:
            selected_unit = unit_number if unit_number in units else 1
            key = (source_map.source_id, selected_unit)
            if key in seen:
                continue
            seen.add(key)
            unit = units[selected_unit]
            packet.append(
                {
                    "source_id": source_map.source_id,
                    "source_sha256": source_map.source_sha256,
                    "locator": unit["locator"],
                    "text": unit["text"],
                }
            )
    return packet


def execute_prompt(
    profile: ResearchModelProfile,
    prompt: str,
    *,
    output_path: Path,
    events_path: Path,
    stderr_path: Path,
    writable_dir: Path,
) -> None:
    """Run one isolated no-search compiler or evaluator turn."""

    command = build_codex_exec_command(
        profile=profile,
        project_root=PROJECT_ROOT,
        schema_path=None,
        final_message_path=output_path,
        writable_dir=writable_dir,
        isolated_web_research=True,
    )
    with (
        events_path.open("w", encoding="utf-8") as events,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=events,
            stderr=stderr,
            check=True,
        )


def _candidate_dir(experiment_dir: Path, selected: str, primary: str) -> Path:
    suffix = "minimax" if selected == primary else "luna-fallback"
    return experiment_dir / f"arm-b-{suffix}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
