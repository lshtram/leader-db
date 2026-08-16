"""Deterministic Task 6 eligibility preflight before any model execution."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .control_flow import ResearchControlFlow, load_control_flow
from .model_call_budget import RunUsageBudgetTracker, RunUsageLimits, StageBudgets
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_evidence_packets import build_chapter_question_evidence_package
from .question_packet_expansion import (
    MaterialDefectReturnReceipt,
    expand_question_evidence_package,
    load_material_defect_return,
)


class CallStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    surface: str
    calls: int = Field(gt=0)


class PromotionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maximum_calls_per_ruler: int = Field(gt=0)
    maximum_input_tokens_per_ruler: int = Field(gt=0)
    maximum_output_tokens_per_ruler: int = Field(gt=0)


class IntegratedGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    release_id: str
    status: str
    target_year: int
    iso3: str
    ruler_name: str
    frozen_release: str
    control_flow: str
    stage_budgets: str
    frozen_corpus_package: str
    frozen_selection_manifest: str
    chapters: tuple[str, ...]
    questions_per_chapter: int = Field(gt=0)
    call_inventory: dict[str, CallStage]
    reasoning_effort: dict[str, str] | None = None
    material_defect_return: str | None = None
    promotion_limits: PromotionLimits


def run_integrated_gate_preflight(
    *, project_root: Path, config_path: Path, output_dir: Path
) -> Path:
    """Bind inputs, build all packets, and stop an ineligible run before calls."""

    config = IntegratedGateConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    if config.chapters != tuple(f"{number}B" for number in range(1, 9)):
        raise ValueError("integrated gate must include chapters 1B through 8B")
    if config.questions_per_chapter != 10:
        raise ValueError("integrated gate requires exactly ten questions per chapter")
    flow_path = project_root / config.control_flow
    flow = load_control_flow(flow_path)
    return_receipt = _load_return_receipt(project_root, config, flow)
    _reject_output_overlap(output_dir, return_receipt)
    budget_path = project_root / config.stage_budgets
    budgets = StageBudgets.model_validate(yaml.safe_load(budget_path.read_text(encoding="utf-8")))
    expected_actions = {
        "question_writing",
        "question_review",
        "chapter_judging",
        "chapter_judgment_review",
    }
    if not expected_actions.issubset({item.id for item in flow.model_actions}):
        raise ValueError("integrated call inventory is absent from the control contract")
    production_model = config.call_inventory["question_writing"].model
    if production_model not in {"gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"}:
        raise ValueError("integrated gate production model is not an approved candidate")
    review_model = config.call_inventory["question_review"].model
    if review_model not in {production_model, "gpt-5.6-sol"}:
        raise ValueError("integrated gate question-review model is not an approved candidate")
    judge_model = config.call_inventory["chapter_judging"].model
    if judge_model not in {production_model, "gpt-5.6-sol"}:
        raise ValueError("integrated gate judge model is not an approved candidate")
    expected_inventory = {
        "question_writing": (production_model, "codex_subscription", 80),
        "question_review": (review_model, "codex_subscription", 80),
        "chapter_judging": (judge_model, "codex_subscription", 8),
        "chapter_judgment_review": ("gpt-5.6-sol", "codex_subscription", 8),
    }
    actual_inventory = {
        key: (value.model, value.surface, value.calls)
        for key, value in config.call_inventory.items()
    }
    if actual_inventory != expected_inventory:
        raise ValueError("integrated gate requires the exact four-stage call inventory")
    expected_effort = {
        "question_writing": (
            "high" if production_model in {"gpt-5.6-luna", "gpt-5.6-sol"} else "medium"
        ),
        "question_review": "high" if review_model in {"gpt-5.6-luna", "gpt-5.6-sol"} else "medium",
        "chapter_judging": "high",
        "chapter_judgment_review": "high",
    }
    modern_effort = config.reasoning_effort is not None and set(config.reasoning_effort) == set(
        expected_effort
    )
    if (production_model == "gpt-5.6-sol" or modern_effort) and (
        config.reasoning_effort != expected_effort
    ):
        raise ValueError("integrated gate reasoning effort differs from the approved inventory")
    required_budgets = {
        "question_writer",
        "question_review",
        "chapter_judge",
        "chapter_judgment_review",
    }
    if not required_budgets.issubset(budgets.stages):
        raise ValueError("integrated gate stages are missing configured budgets")
    corpus_path = project_root / config.frozen_corpus_package
    selection_path = project_root / config.frozen_selection_manifest
    output_dir.mkdir(parents=True, exist_ok=False)
    packages = _build_question_packages(
        project_root=project_root,
        config=config,
        return_receipt=return_receipt,
        judge_package_path=corpus_path,
        selection_manifest_path=selection_path,
        output_dir=output_dir,
    )
    planned_calls = sum(stage.calls for stage in config.call_inventory.values())
    eligible = planned_calls <= config.promotion_limits.maximum_calls_per_ruler
    payload = {
        "schema_version": "integrated_gate_preflight_v1",
        "implementation_id": "integrated-gate-preflight-v1",
        "implementation_sha256": _sha256(Path(__file__)),
        "release_id": config.release_id,
        "status": "eligible" if eligible else "rejected",
        "model_calls_executed": 0,
        "api_key_used": False,
        "config_sha256": _sha256(config_path),
        "control_flow_sha256": _sha256(flow_path),
        "stage_budgets_sha256": _sha256(budget_path),
        "frozen_release_sha256": _sha256(project_root / config.frozen_release),
        "frozen_corpus_package_sha256": _sha256(corpus_path),
        "frozen_selection_manifest_sha256": _sha256(selection_path),
        "question_package_count": len(packages),
        "question_count": sum(
            len(
                ChapterQuestionEvidencePackage.model_validate_json(
                    Path(item["path"]).read_text(encoding="utf-8")
                ).packets
            )
            for item in packages
        ),
        "question_packages": packages,
        "call_inventory": {
            key: value.model_dump(mode="json") for key, value in config.call_inventory.items()
        },
        "reasoning_effort": config.reasoning_effort,
        "material_defect_return": config.material_defect_return,
        "material_defect_return_count": 1 if return_receipt is not None else 0,
        "material_defect_return_sha256": (
            return_receipt.config_sha256 if return_receipt is not None else None
        ),
        "material_defect_return_source_release_id": (
            return_receipt.source_release_id if return_receipt is not None else None
        ),
        "material_defect_return_source_preflight_sha256": (
            return_receipt.source_preflight_sha256 if return_receipt is not None else None
        ),
        "material_defect_return_details": (
            return_receipt.manifest_details()
            if return_receipt is not None
            else None
        ),
        "planned_calls": planned_calls,
        "maximum_calls_per_ruler": config.promotion_limits.maximum_calls_per_ruler,
        "maximum_input_tokens_per_ruler": (config.promotion_limits.maximum_input_tokens_per_ruler),
        "maximum_output_tokens_per_ruler": (
            config.promotion_limits.maximum_output_tokens_per_ruler
        ),
        "stop_reason": (
            None
            if eligible
            else (
                f"planned straight-through run requires {planned_calls} calls, exceeding "
                f"the promotion ceiling of {config.promotion_limits.maximum_calls_per_ruler}"
            )
        ),
    }
    path = output_dir / "preflight-manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _build_question_packages(
    *,
    project_root: Path,
    config: IntegratedGateConfig,
    return_receipt: MaterialDefectReturnReceipt | None,
    judge_package_path: Path,
    selection_manifest_path: Path,
    output_dir: Path,
) -> list[dict]:
    packages = []
    for chapter_id in config.chapters:
        package_path = output_dir / "question-packages" / chapter_id / "package.json"
        package = _prepare_question_package(
            project_root=project_root,
            return_receipt=return_receipt,
            judge_package_path=judge_package_path,
            selection_manifest_path=selection_manifest_path,
            chapter_id=chapter_id,
            output_path=package_path,
        )
        expected = tuple(f"{chapter_id}.{number}" for number in range(1, 11))
        if tuple(item.question_id for item in package.packets) != expected:
            raise ValueError(f"question package is incomplete or unordered: {chapter_id}")
        packages.append(
            {
                "chapter_id": chapter_id,
                "path": str(package_path),
                "sha256": _sha256(package_path),
            }
        )
    if return_receipt is not None:
        return_receipt.verify_unchanged()
    return packages


def _prepare_question_package(
    *,
    project_root: Path,
    return_receipt: MaterialDefectReturnReceipt | None,
    judge_package_path: Path,
    selection_manifest_path: Path,
    chapter_id: str,
    output_path: Path,
) -> ChapterQuestionEvidencePackage:
    build_chapter_question_evidence_package(
        project_root=project_root,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
        chapter_id=chapter_id,
        output_path=output_path,
    )
    package = ChapterQuestionEvidencePackage.model_validate_json(output_path.read_text())
    if return_receipt is None:
        return package
    additions = return_receipt.additions_for(package)
    expanded = expand_question_evidence_package(
        package=package,
        judge_package_path=judge_package_path,
        additions_by_question=additions,
    )
    output_path.write_text(expanded.model_dump_json(indent=2) + "\n")
    return expanded


def _load_return_receipt(
    project_root: Path, config: IntegratedGateConfig, flow: ResearchControlFlow
) -> MaterialDefectReturnReceipt | None:
    return_path = config.material_defect_return
    if return_path is None:
        return None
    if flow.control_limits.maximum_explicit_material_defect_returns != 1:
        raise ValueError("control flow does not permit a material-defect return")
    return load_material_defect_return(
        project_root=project_root,
        config_path=project_root / return_path,
        active_chapters=config.chapters,
    )


def _reject_output_overlap(
    output_dir: Path, receipt: MaterialDefectReturnReceipt | None
) -> None:
    if receipt is None:
        return
    output = output_dir.resolve()
    source = receipt.source_run.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("fresh output overlaps the immutable material-defect source run")


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_integrated_run_budget_tracker(
    *, config_path: Path, run_dir: Path
) -> RunUsageBudgetTracker:
    """Load one cross-stage tracker from a hash-bound integrated release config."""

    raw = config_path.read_bytes()
    config = IntegratedGateConfig.model_validate(yaml.safe_load(raw))
    return RunUsageBudgetTracker(
        ledger_path=run_dir / "stage-budgets" / "run-usage-reservations.json",
        limits=RunUsageLimits(
            max_calls=config.promotion_limits.maximum_calls_per_ruler,
            max_input_tokens=config.promotion_limits.maximum_input_tokens_per_ruler,
            max_output_tokens=config.promotion_limits.maximum_output_tokens_per_ruler,
        ),
        config_sha256=sha256(raw).hexdigest(),
    )


__all__ = [
    "IntegratedGateConfig",
    "load_integrated_run_budget_tracker",
    "run_integrated_gate_preflight",
]
