"""Run the matched reader arms with automatic content-based fallback."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from leaders_db.conversational_evidence.document_reader_experiment import (
    load_document_reader_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "scripts/experiments/run_document_reader_ab.py"


def main() -> None:
    """Run Sol baseline, calibrate candidates, and select the first content pass."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    config = load_document_reader_config(experiment_dir / "frozen/document_reader_experiment.json")

    _run(experiment_dir, "baseline", full=True)
    selected: str | None = None
    calibration_results: list[dict[str, object]] = []
    for profile_name in config.reader_ladder:
        _run(
            experiment_dir,
            "candidate",
            full=False,
            candidate_profile=profile_name,
        )
        summary_path = _candidate_dir(experiment_dir, profile_name) / "calibration-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        passed = all(item["content_usable"] for item in summary["documents"])
        calibration_results.append({"profile": profile_name, "content_passed": passed})
        if passed:
            selected = profile_name
            break
    if selected is None:
        _write_json(
            experiment_dir / "candidate-selection.json",
            {
                "schema_version": "document_reader_candidate_selection_v1",
                "status": "no_content_qualified_candidate",
                "calibrations": calibration_results,
                "format_errors_considered": False,
            },
        )
        raise RuntimeError("no reader candidate passed the content calibration")
    _run(
        experiment_dir,
        "candidate",
        full=True,
        candidate_profile=selected,
    )
    _write_json(
        experiment_dir / "candidate-selection.json",
        {
            "schema_version": "document_reader_candidate_selection_v1",
            "status": "selected",
            "selected_profile": selected,
            "calibrations": calibration_results,
            "format_errors_considered": False,
        },
    )


def _run(
    experiment_dir: Path,
    arm: str,
    *,
    full: bool,
    candidate_profile: str | None = None,
) -> None:
    command = [sys.executable, str(RUNNER), str(experiment_dir), arm]
    if full:
        command.append("--full")
    if candidate_profile is not None:
        command.extend(("--candidate-profile", candidate_profile))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def _candidate_dir(experiment_dir: Path, profile_name: str) -> Path:
    suffix = re.sub(r"[^a-z0-9]+", "-", profile_name.lower()).strip("-")
    return experiment_dir / f"arm-b-{suffix}"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
