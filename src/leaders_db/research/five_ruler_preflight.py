"""Zero-call cohort freeze and writing preflight for the five-ruler gate."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .approved_ruler_package import load_approved_ruler_package
from .integrated_gate_preflight import IntegratedGateConfig, run_integrated_gate_preflight
from .model_call_budget import StageBudgets
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_writer import _question_answer_response_model
from .question_packet_writer_prompt import build_question_writer_prompt


class CohortRuler(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iso3: str
    ruler_name: str
    ruler_year_id: int
    approved_package: str
    release_config: str


class FiveRulerPreflightConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    release_id: str
    target_year: int
    profile: str
    profiles_path: str
    reasoning_effort: str
    stage_budgets: str
    rulers: tuple[CohortRuler, ...] = Field(min_length=5, max_length=5)
    maximum_calls: int = Field(gt=0)
    maximum_input_tokens: int = Field(gt=0)
    maximum_output_tokens: int = Field(gt=0)


def run_five_ruler_preflight(*, project_root: Path, config_path: Path, output_dir: Path) -> Path:
    """Freeze five trusted rulers and measure all 400 complete writer requests."""

    if output_dir.exists():
        raise FileExistsError(f"fresh cohort output already exists: {output_dir}")
    config = FiveRulerPreflightConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    if config.schema_version != "five_ruler_preflight_config_v1":
        raise ValueError("unsupported five-ruler preflight config")
    expected_iso3 = ("CHN", "ISR", "PRK", "RUS", "USA")
    if tuple(item.iso3 for item in config.rulers) != expected_iso3:
        raise ValueError("five-ruler cohort must retain the frozen ordered identities")
    profiles_path = project_root / config.profiles_path
    profile = load_research_model_profiles(profiles_path).profiles[config.profile]
    if (profile.provider, profile.model, profile.execution_surface) != (
        "openai",
        "gpt-5.6-luna",
        "codex",
    ):
        raise ValueError("five-ruler writing requires Luna on the Codex subscription")
    budgets_path = project_root / config.stage_budgets
    writer_budget = StageBudgets.model_validate(
        yaml.safe_load(budgets_path.read_text(encoding="utf-8"))
    ).stages["question_writer"]
    prompts, prompt_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    output_dir.mkdir(parents=True)
    encoding = tiktoken.get_encoding("o200k_base")
    ruler_rows: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    reasons: list[str] = []
    for ruler in config.rulers:
        row, ruler_requests, ruler_reasons = _measure_ruler(
            project_root=project_root,
            output_dir=output_dir,
            ruler=ruler,
            target_year=config.target_year,
            prompts=prompts,
            encoding=encoding,
            writer_budget=writer_budget,
        )
        ruler_rows.append(row)
        requests.extend(ruler_requests)
        reasons.extend(ruler_reasons)
    reasons.extend(
        f"{item['iso3']}:{item['question_id']}:{reason}"
        for item in requests
        for reason in item["stop_reasons"]
    )
    calls = len(requests)
    measured = [item for item in requests if item["estimated_input_tokens"] is not None]
    input_tokens = sum(int(item["estimated_input_tokens"]) for item in measured)
    output_allowance_per_call = writer_budget.output_allowance(profile.model)
    if calls > config.maximum_calls:
        reasons.append("cohort_call_limit")
    if input_tokens > config.maximum_input_tokens:
        reasons.append("cohort_input_limit")
    required_output_capacity = calls * output_allowance_per_call
    if required_output_capacity > config.maximum_output_tokens:
        reasons.append("cohort_output_limit")
    payload = {
        "schema_version": "five_ruler_writing_preflight_v1",
        "release_id": config.release_id,
        "status": "eligible" if not reasons else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "config_sha256": _digest(config_path),
        "profiles_sha256": _digest(profiles_path),
        "stage_budgets_sha256": _digest(budgets_path),
        "prompt_config_sha256": prompt_hash,
        "profile": config.profile,
        "provider": profile.provider,
        "model": profile.model,
        "surface": "codex_subscription",
        "reasoning_effort": config.reasoning_effort,
        "rulers": ruler_rows,
        "request_count": calls,
        "complete_request_count": len(measured),
        "requests": requests,
        "measured_input_tokens": input_tokens,
        "output_token_allowance_per_call": output_allowance_per_call,
        "required_output_capacity": required_output_capacity,
        "cohort_output_token_quota": config.maximum_output_tokens,
        "limits": {
            "maximum_calls": config.maximum_calls,
            "maximum_input_tokens": config.maximum_input_tokens,
            "maximum_output_tokens": config.maximum_output_tokens,
        },
        "stop_reasons": sorted(set(reasons)),
        "downstream_roots_unused": True,
    }
    manifest_path = output_dir / "cohort-preflight.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _measure_ruler(
    *, project_root, output_dir, ruler, target_year, prompts, encoding, writer_budget
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    approved_path = project_root / ruler.approved_package
    approved = load_approved_ruler_package(approved_path, project_root=project_root)
    actual_identity = (
        approved.iso3,
        approved.ruler_name,
        approved.ruler_year_id,
        approved.target_year,
    )
    expected_identity = (ruler.iso3, ruler.ruler_name, ruler.ruler_year_id, target_year)
    if actual_identity != expected_identity:
        raise ValueError(f"frozen cohort identity mismatch: {ruler.iso3}")
    release_path = project_root / ruler.release_config
    release = IntegratedGateConfig.model_validate(yaml.safe_load(release_path.read_text()))
    if (release.iso3, release.ruler_name, release.target_year) != (
        *expected_identity[:2],
        target_year,
    ):
        raise ValueError(f"release identity mismatch: {ruler.iso3}")
    integrated_path = run_integrated_gate_preflight(
        project_root=project_root,
        config_path=release_path,
        output_dir=output_dir / "rulers" / ruler.iso3,
    )
    integrated = json.loads(integrated_path.read_text())
    analyses = {item.chapter_id: item for item in approved.chapters}
    requests: list[dict[str, object]] = []
    reasons: list[str] = []
    ruler_tokens = 0
    for package_row in integrated["question_packages"]:
        chapter = package_row["chapter_id"]
        package = ChapterQuestionEvidencePackage.model_validate_json(
            Path(package_row["path"]).read_text()
        )
        analysis = json.loads((project_root / analyses[chapter].analysis_path).read_text())
        predecessors = {item["question_id"]: item for item in analysis["answers"]}
        chapter_tokens = 0
        for packet in package.packets:
            prompt = build_question_writer_prompt(packet, prompts, predecessors[packet.question_id])
            schema = _question_answer_response_model(
                packet.coverage.required_evidence_ids,
                allow_reopen=not packet.evidence_discovery_complete,
            ).model_json_schema()
            make_strict_response_schema(schema)
            complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            chars, tokens = len(complete), len(encoding.encode(complete))
            stop = []
            if chars > writer_budget.max_request_characters:
                stop.append("request_characters")
            if tokens > writer_budget.max_request_input_tokens:
                stop.append("request_input_tokens")
            chapter_tokens += tokens
            ruler_tokens += tokens
            requests.append(
                {
                    "iso3": ruler.iso3,
                    "chapter_id": chapter,
                    "question_id": packet.question_id,
                    "request_characters": chars,
                    "estimated_input_tokens": tokens,
                    "request_sha256": sha256(complete.encode()).hexdigest(),
                    "stop_reasons": stop,
                }
            )
        if chapter_tokens > writer_budget.max_stage_input_tokens:
            reasons.append(f"{ruler.iso3}:{chapter}:stage_input_tokens")
    row = {
        "iso3": ruler.iso3,
        "ruler_name": ruler.ruler_name,
        "ruler_year_id": ruler.ruler_year_id,
        "approved_package_sha256": _digest(approved_path),
        "release_config_sha256": _digest(release_path),
        "integrated_preflight_sha256": _digest(integrated_path),
        "writing_input_tokens": ruler_tokens,
    }
    return row, requests, reasons


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = ["FiveRulerPreflightConfig", "run_five_ruler_preflight"]
