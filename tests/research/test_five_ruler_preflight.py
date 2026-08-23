from __future__ import annotations

import json
from pathlib import Path

from leaders_db.research.five_ruler_preflight import run_five_ruler_preflight

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_five_ruler_preflight_measures_complete_eligible_inventory(tmp_path: Path) -> None:
    manifest_path = run_five_ruler_preflight(
        project_root=PROJECT_ROOT,
        config_path=(PROJECT_ROOT / "configs/evidence-funnel/five-ruler-2023-luna-sol-v5.yaml"),
        output_dir=tmp_path / "fresh-run",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["model_calls_executed"] == 0
    assert manifest["reservations_created"] == 0
    assert manifest["request_count"] == 400
    assert manifest["complete_request_count"] == 400
    assert manifest["output_token_allowance_per_call"] == 12_500
    assert manifest["required_output_capacity"] == 5_000_000
    assert manifest["status"] == "eligible"
    assert manifest["cohort_output_token_quota"] == 5_000_000
    assert manifest["stop_reasons"] == []


def test_fresh_cohort_binds_reviewed_prk_evidence_supplement(tmp_path: Path) -> None:
    manifest_path = run_five_ruler_preflight(
        project_root=PROJECT_ROOT,
        config_path=(PROJECT_ROOT / "configs/evidence-funnel/five-ruler-2023-luna-sol-v7.yaml"),
        output_dir=tmp_path / "fresh-supplemented-run",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    integrated = json.loads(
        (tmp_path / "fresh-supplemented-run/rulers/PRK/preflight-manifest.json").read_text()
    )
    package_row = next(
        item for item in integrated["question_packages"] if item["chapter_id"] == "7B"
    )
    package = json.loads(Path(package_row["path"]).read_text())

    assert manifest["release_id"] == "five-ruler-2023-luna-sol-v7"
    assert manifest["status"] == "eligible"
    assert manifest["limits"]["maximum_input_tokens"] == 40_000_000
    assert package["schema_version"] == "chapter_question_evidence_package_v2"
    assert integrated["evidence_supplements"]["7B"]["supplement_sha256"]
