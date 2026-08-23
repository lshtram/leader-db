from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from leaders_db.research.control_flow import (
    QuestionCorrectionPolicy,
    QuestionReviewExperimentPolicy,
    ResearchControlFlow,
    load_control_flow,
    load_question_correction_policy,
    load_question_review_experiment_policy,
    write_control_flow_inventory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/research-control-flow.yaml"
REVIEW_POLICY_PATH = PROJECT_ROOT / "configs/research-question-review-experiment.yaml"
CORRECTION_POLICY_PATH = PROJECT_ROOT / "configs/research-question-correction-policy.yaml"


def test_active_control_flow_is_straight_through() -> None:
    flow = load_control_flow(CONFIG_PATH)

    assert len(flow.model_actions) == 6
    assert sum(item.role == "production" for item in flow.model_actions) == 3
    assert sum(item.role == "independent_quality" for item in flow.model_actions) == 3
    assert flow.control_limits.maximum_explicit_material_defect_returns == 1
    assert flow.control_limits.automatic_retry_rounds == 0
    assert flow.control_limits.automatic_repair_rounds == 0


def test_autonomous_review_policy_collects_one_full_round_without_retries() -> None:
    policy = load_question_review_experiment_policy(REVIEW_POLICY_PATH)

    assert policy == QuestionReviewExperimentPolicy(
        schema_version="question_review_experiment_policy_v1",
        quality_failure_behavior="collect_all",
        maximum_review_rounds=1,
        maximum_material_defect_returns=0,
        maximum_automatic_reruns_per_question=0,
        maximum_infrastructure_retries=0,
        stop_on_invalid_artifact=True,
        stop_before_judging=True,
        writer_reopen_behavior="carry_to_review_and_bounded_correction",
    )


def test_correction_policy_carries_final_concerns_to_confidence() -> None:
    policy = load_question_correction_policy(CORRECTION_POLICY_PATH)

    assert policy == QuestionCorrectionPolicy(
        schema_version="question_correction_policy_v1",
        maximum_corrections_per_failed_question=1,
        maximum_final_reviews_per_corrected_question=1,
        residual_concern_behavior="carry_to_judgment_with_lower_confidence",
        stop_on_residual_quality_failure=False,
        stop_on_invalid_artifact=True,
        maximum_infrastructure_retries=0,
    )


def test_control_flow_rejects_review_chains() -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["model_actions"][1]["quality_action"] = "question_review"

    with pytest.raises(ValidationError, match="quality actions cannot chain"):
        ResearchControlFlow.model_validate(payload)


def test_control_flow_rejects_shared_quality_action() -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["model_actions"][2]["quality_action"] = "corpus_verification"

    with pytest.raises(ValidationError, match="dedicated pairs"):
        ResearchControlFlow.model_validate(payload)


def test_control_flow_rejects_orphan_quality_action() -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["model_actions"].append(
        {"id": "orphan_review", "role": "independent_quality", "quality_action": None}
    )

    with pytest.raises(ValidationError, match="dedicated pairs"):
        ResearchControlFlow.model_validate(payload)


def test_comparison_hashes_frozen_baseline(tmp_path: Path) -> None:
    output = write_control_flow_inventory(config_path=CONFIG_PATH, output_dir=tmp_path / "fresh")
    payload = json.loads(output.read_text(encoding="utf-8"))

    baseline = PROJECT_ROOT / payload["frozen_baseline"]
    assert payload["status"] == "passed"
    assert payload["model_calls"] == 0
    assert payload["baseline_controls"] == {
        "maximum_targeted_repair_rounds": 3,
        "review_after_compaction": True,
        "use_requirement_led_repairs": True,
    }
    assert len(payload["frozen_baseline_sha256"]) == 64
    assert baseline == PROJECT_ROOT / "configs/evidence-funnel/production-2023-v4.yaml"
