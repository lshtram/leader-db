from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run(
    manifest: Path,
    registry: Path,
    role: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "EVIDENCE_MANIFEST": str(manifest),
            "EVIDENCE_REGISTRY": str(registry),
            "EVIDENCE_ROLE": role,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "simple_evidence.cli", *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def test_four_command_cli_feedback_loop(manifest_path: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    shown = _run(manifest_path, registry, "extractor", "show", "DOC-1", "1", "2")
    assert shown.returncode == 0
    assert len(json.loads(shown.stdout)["entity"]["sentences"]) == 2

    added = _run(
        manifest_path,
        registry,
        "extractor",
        "add",
        "DOC-1",
        "1",
        "--summary",
        "The authority adopted Rule A.",
    )
    entity = json.loads(added.stdout)["entity"]
    fact_id = entity["fact_id"]
    assert entity["excerpt"].endswith("2022.")

    corrected = _run(
        manifest_path,
        registry,
        "extractor",
        "correct",
        fact_id,
        "--end",
        "2",
        "--summary",
        "The authority adopted Rule A and reduced the fee.",
    )
    assert json.loads(corrected.stdout)["entity"]["attempts"] == 2

    confirmed = _run(
        manifest_path, registry, "extractor", "confirm", fact_id
    )
    assert json.loads(confirmed.stdout)["entity"]["extractor_confirmed"]


def test_cli_reports_json_error_without_registry_mutation(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = tmp_path / "registry.jsonl"
    result = _run(
        manifest_path,
        registry,
        "extractor",
        "add",
        "UNKNOWN",
        "1",
        "--summary",
        "No.",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["ok"] is False
    assert not registry.exists()
