"""Validated straight-through model control flow and comparison inventory."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: Literal["production", "independent_quality"]
    quality_action: str | None


class ControlLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automatic_retry_rounds: Literal[0]
    automatic_repair_rounds: Literal[0]
    automatic_rereview_rounds: Literal[0]
    automatic_supervisor_takeovers: Literal[0]
    maximum_explicit_material_defect_returns: int = Field(ge=0, le=1)
    defect_return_requires_user_authorization: Literal[True]
    defect_return_runs_automatically: Literal[False]


class ResearchControlFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research_control_flow_v1"]
    release_status: Literal["candidate"]
    baseline_release: str
    model_actions: tuple[ModelAction, ...]
    deterministic_actions: tuple[str, ...]
    control_limits: ControlLimits
    retired_from_baseline: tuple[str, ...]

    @model_validator(mode="after")
    def validate_pairs(self) -> ResearchControlFlow:
        by_id = {action.id: action for action in self.model_actions}
        if len(by_id) != len(self.model_actions):
            raise ValueError("model action IDs must be unique")
        quality_targets = {
            action.quality_action for action in self.model_actions if action.role == "production"
        }
        if None in quality_targets:
            raise ValueError("every production action requires one quality action")
        production_count = sum(action.role == "production" for action in self.model_actions)
        quality_actions = {
            action.id for action in self.model_actions if action.role == "independent_quality"
        }
        if len(quality_targets) != production_count or quality_targets != quality_actions:
            raise ValueError("production and quality actions must form dedicated pairs")
        for target in quality_targets:
            if target not in by_id or by_id[target].role != "independent_quality":
                raise ValueError(f"invalid independent quality action: {target}")
        for action in self.model_actions:
            if action.role == "independent_quality" and action.quality_action is not None:
                raise ValueError("quality actions cannot chain to another model action")
        return self

    def require_action(
        self, action_id: str, *, role: Literal["production", "independent_quality"]
    ) -> None:
        """Stop an executor that is absent or misclassified in the active contract."""

        actions = {action.id: action for action in self.model_actions}
        if action_id not in actions or actions[action_id].role != role:
            raise ValueError(f"control flow does not permit {role} action: {action_id}")


def load_control_flow(path: Path) -> ResearchControlFlow:
    """Load and validate one candidate control-flow contract."""

    return ResearchControlFlow.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def enforce_model_action(
    project_root: Path,
    action_id: str,
    *,
    role: Literal["production", "independent_quality"],
) -> None:
    """Load the active candidate contract at an executor's pre-call boundary."""

    load_control_flow(project_root / "configs/research-control-flow.yaml").require_action(
        action_id, role=role
    )


def write_control_flow_inventory(*, config_path: Path, output_dir: Path) -> Path:
    """Persist a reproducible no-model inventory against the frozen release."""

    flow = load_control_flow(config_path)
    baseline_path = config_path.parents[1] / flow.baseline_release
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    quality = baseline["quality_contract"]
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": "research_control_flow_comparison_v1",
        "status": "passed",
        "model_calls": 0,
        "candidate_config": str(config_path),
        "candidate_config_sha256": sha256(config_path.read_bytes()).hexdigest(),
        "frozen_baseline": str(baseline_path),
        "frozen_baseline_sha256": sha256(baseline_path.read_bytes()).hexdigest(),
        "baseline_controls": {
            "maximum_targeted_repair_rounds": quality["maximum_targeted_repair_rounds"],
            "use_requirement_led_repairs": quality["use_requirement_led_repairs"],
            "review_after_compaction": quality["review_after_compaction"],
        },
        "candidate_controls": flow.control_limits.model_dump(mode="json"),
        "model_actions": [item.model_dump(mode="json") for item in flow.model_actions],
        "deterministic_actions": list(flow.deterministic_actions),
        "retired_from_baseline": list(flow.retired_from_baseline),
        "decision": (
            "Use the candidate straight-through contract for Task 6; preserve v4 as the "
            "immutable comparison release."
        ),
    }
    output_path = output_dir / "control-flow-comparison.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


__all__ = [
    "ResearchControlFlow",
    "enforce_model_action",
    "load_control_flow",
    "write_control_flow_inventory",
]
