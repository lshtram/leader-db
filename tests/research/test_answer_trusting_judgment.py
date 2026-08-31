"""Answer-trusting diagnostic judgment tests."""

import json
from pathlib import Path

from leaders_db.research.answer_trusting_judgment import build_preflight


def test_live_preflight_measures_exact_eight_answer_only_batches(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    baseline = root / "research/runs/five-ruler-2023-luna-sol-v8-release"
    baseline_preflight = baseline / "comparative-judgment-preflight-v8.json"
    if not baseline_preflight.exists():
        return
    import hashlib

    approved_hash = hashlib.sha256(baseline_preflight.read_bytes()).hexdigest()
    output = build_preflight(
        baseline_run=baseline,
        baseline_preflight_path=baseline_preflight,
        approved_baseline_sha256=approved_hash,
        guides_root=root / "docs/methodology/chapter-guides",
        profiles_path=root / "configs/research-models.yaml",
        stage_budgets_path=root / "configs/research-stage-budgets.yaml",
        output_root=tmp_path / "outputs",
        output_path=tmp_path / "preflight.json",
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "eligible"
    assert saved["planned_calls"] == 8
    assert len(saved["requests"]) == 8
    assert sum(item["estimated_input_tokens"] for item in saved["requests"]) == 652_434
    assert all(len(item["dossier_job_keys"]) == 5 for item in saved["requests"])
    assert saved["required_output_capacity"] == 500_000
