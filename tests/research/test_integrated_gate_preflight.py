from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from leaders_db.research.integrated_gate_preflight import (
    load_integrated_run_budget_tracker,
    run_integrated_gate_preflight,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_task6_preflight_builds_all_packets_and_stops_before_calls(tmp_path: Path) -> None:
    manifest_path = run_integrated_gate_preflight(
        project_root=PROJECT_ROOT,
        config_path=(
            PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-gate-v1.yaml"
        ),
        output_dir=tmp_path / "fresh-run",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "rejected"
    assert payload["model_calls_executed"] == 0
    assert payload["api_key_used"] is False
    assert payload["question_package_count"] == 8
    assert payload["question_count"] == 80
    assert payload["planned_calls"] == 176
    assert payload["maximum_calls_per_ruler"] == 149
    assert len(payload["stage_budgets_sha256"]) == 64
    assert len({item["chapter_id"] for item in payload["question_packages"]}) == 8
    assert all(len(item["sha256"]) == 64 for item in payload["question_packages"])


def test_task6_preflight_rejects_changed_inventory(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-gate-v1.yaml"
    changed = tmp_path / "changed.yaml"
    changed.write_text(
        source.read_text(encoding="utf-8").replace("calls: 80", "calls: 79", 1),
        encoding="utf-8",
    )

    try:
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=changed,
            output_dir=tmp_path / "output",
        )
    except ValueError as exc:
        assert "exact four-stage call inventory" in str(exc)
    else:
        raise AssertionError("changed call inventory was accepted")


def test_task6_preflight_rejects_changed_question_count(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-gate-v1.yaml"
    changed = tmp_path / "changed.yaml"
    changed.write_text(
        source.read_text(encoding="utf-8").replace(
            "questions_per_chapter: 10", "questions_per_chapter: 9"
        ),
        encoding="utf-8",
    )

    try:
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=changed,
            output_dir=tmp_path / "output",
        )
    except ValueError as exc:
        assert "exactly ten questions" in str(exc)
    else:
        raise AssertionError("changed question count was accepted")


def test_terra_writer_sol_judge_release_is_eligible_under_250_calls(
    tmp_path: Path,
) -> None:
    path = run_integrated_gate_preflight(
        project_root=PROJECT_ROOT,
        config_path=(
            PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-terra-sol-v2.yaml"
        ),
        output_dir=tmp_path / "terra-sol",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "eligible"
    assert payload["planned_calls"] == 176
    assert payload["maximum_calls_per_ruler"] == 250
    assert payload["call_inventory"]["chapter_judging"]["model"] == "gpt-5.6-sol"


def test_preflight_rejects_unapproved_judge_pairing(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-terra-sol-v2.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["call_inventory"]["chapter_judging"]["model"] = "gpt-5.6-luna"
    changed = tmp_path / "invalid-judge.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="judge model is not an approved candidate"):
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=changed,
            output_dir=tmp_path / "invalid",
        )


def test_all_sol_release_is_eligible_under_250_calls(tmp_path: Path) -> None:
    path = run_integrated_gate_preflight(
        project_root=PROJECT_ROOT,
        config_path=(
            PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-sol-v5.yaml"
        ),
        output_dir=tmp_path / "all-sol",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "eligible"
    assert payload["planned_calls"] == 176
    assert {stage["model"] for stage in payload["call_inventory"].values()} == {"gpt-5.6-sol"}
    assert set(payload["reasoning_effort"].values()) == {"high"}

    tracker = load_integrated_run_budget_tracker(
        config_path=(
            PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-sol-v5.yaml"
        ),
        run_dir=tmp_path / "all-sol",
    )
    assert tracker.limits.max_calls == 250
    assert tracker.limits.max_input_tokens == 40_000_000
    assert tracker.limits.max_output_tokens == 500_000


def test_luna_question_work_sol_judging_release_is_eligible(tmp_path: Path) -> None:
    path = run_integrated_gate_preflight(
        project_root=PROJECT_ROOT,
        config_path=(
            PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-luna-sol-v6.yaml"
        ),
        output_dir=tmp_path / "luna-sol",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "eligible"
    assert payload["planned_calls"] == 176
    assert payload["maximum_output_tokens_per_ruler"] == 1_000_000
    assert payload["call_inventory"]["question_writing"]["model"] == "gpt-5.6-luna"
    assert payload["call_inventory"]["question_review"]["model"] == "gpt-5.6-luna"
    assert payload["call_inventory"]["chapter_judging"]["model"] == "gpt-5.6-sol"
    assert payload["call_inventory"]["chapter_judgment_review"]["model"] == "gpt-5.6-sol"
    assert set(payload["reasoning_effort"].values()) == {"high"}


def test_preflight_rejects_unapproved_luna_review_pairing(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-terra-sol-v2.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["call_inventory"]["question_review"]["model"] = "gpt-5.6-luna"
    changed = tmp_path / "invalid-review.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="question-review model is not an approved candidate"):
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=changed,
            output_dir=tmp_path / "invalid-review",
        )


def test_preflight_applies_one_explicit_material_defect_return(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-luna-sol-v6.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["material_defect_return"] = "configs/research-control-flow.yaml"
    config_path = tmp_path / "release.yaml"
    config_path.write_text(yaml.safe_dump(payload))
    promoted: dict[str, tuple[str, ...]] = {}

    def additions_for(package):
        if package.chapter_id != "3B":
            return {}
        packet = next(item for item in package.packets if item.question_id == "3B.2")
        existing = {item.evidence_id for item in packet.priority_evidence}
        evidence_id = next(
            item.evidence_id for item in packet.candidate_index if item.evidence_id not in existing
        )
        promoted[packet.question_id] = (evidence_id,)
        return {packet.question_id: (evidence_id,)}

    def fake_load(*, project_root, config_path, active_chapters):
        assert project_root == PROJECT_ROOT
        assert config_path == PROJECT_ROOT / "configs/research-control-flow.yaml"
        assert active_chapters == tuple(f"{number}B" for number in range(1, 9))
        return SimpleNamespace(
            source_run=tmp_path / "source-run",
            config_sha256="a" * 64,
            source_release_id="failed-v1",
            source_preflight_sha256="b" * 64,
            additions_for=additions_for,
            verify_unchanged=lambda: None,
            manifest_details=lambda: [
                {"question_id": "3B.2", "evidence_ids": list(promoted["3B.2"])}
            ],
        )

    monkeypatch.setattr(
        "leaders_db.research.integrated_gate_preflight.load_material_defect_return",
        fake_load,
    )
    manifest_path = run_integrated_gate_preflight(
        project_root=PROJECT_ROOT,
        config_path=config_path,
        output_dir=tmp_path / "fresh-run",
    )

    manifest = json.loads(manifest_path.read_text())
    package = json.loads(
        (tmp_path / "fresh-run/question-packages/3B/package.json").read_text()
    )
    question = next(item for item in package["packets"] if item["question_id"] == "3B.2")
    assert manifest["material_defect_return"] == "configs/research-control-flow.yaml"
    assert manifest["material_defect_return_count"] == 1
    assert len(manifest["material_defect_return_sha256"]) == 64
    assert set(promoted["3B.2"]).issubset(question["coverage"]["required_evidence_ids"])


def test_preflight_rejects_return_when_control_limit_is_zero(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-luna-sol-v6.yaml"
    payload = yaml.safe_load(source.read_text())
    flow = yaml.safe_load((PROJECT_ROOT / "configs/research-control-flow.yaml").read_text())
    flow["control_limits"]["maximum_explicit_material_defect_returns"] = 0
    flow_path = tmp_path / "flow.yaml"
    flow_path.write_text(yaml.safe_dump(flow))
    payload["control_flow"] = str(flow_path)
    payload["material_defect_return"] = "configs/research-control-flow.yaml"
    config_path = tmp_path / "release.yaml"
    config_path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="does not permit"):
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=config_path,
            output_dir=tmp_path / "fresh-run",
        )


def test_preflight_rejects_output_inside_failed_source_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = PROJECT_ROOT / "configs/evidence-funnel/netanyahu-2023-integrated-luna-sol-v6.yaml"
    payload = yaml.safe_load(source.read_text())
    payload["material_defect_return"] = "configs/research-control-flow.yaml"
    config_path = tmp_path / "release.yaml"
    config_path.write_text(yaml.safe_dump(payload))
    source_run = tmp_path / "failed-run"
    source_run.mkdir()
    receipt = SimpleNamespace(source_run=source_run)
    monkeypatch.setattr(
        "leaders_db.research.integrated_gate_preflight.load_material_defect_return",
        lambda **kwargs: receipt,
    )

    with pytest.raises(ValueError, match="overlaps"):
        run_integrated_gate_preflight(
            project_root=PROJECT_ROOT,
            config_path=config_path,
            output_dir=source_run / "fresh-run",
        )
    assert not (source_run / "fresh-run").exists()
