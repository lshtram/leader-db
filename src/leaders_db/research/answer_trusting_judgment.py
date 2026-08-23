"""Bounded diagnostic judging from reviewed answers without source excerpts."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

import tiktoken
from pydantic import BaseModel, ConfigDict

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .chapter_judge_models import ChapterJudgmentBatch, codex_chapter_judgment_json_schema
from .chapter_projection import RulerChapterProjection
from .comparative_judgment_phase import _evaluation_web_evidence_ids, _validate_no_tool_events
from .json_model_execution import execute_json_model
from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

CHAPTERS = ("1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B")
RULERS = ("CHN", "ISR", "PRK", "RUS", "USA")


class _RawResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


def build_preflight(
    *, baseline_run: Path, baseline_preflight_path: Path, approved_baseline_sha256: str,
    guides_root: Path, profiles_path: Path, stage_budgets_path: Path, output_root: Path,
    output_path: Path,
) -> Path:
    """Build eight complete answer-only five-ruler requests without model calls."""

    if output_path.exists():
        raise FileExistsError(output_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("answer-trusting output root is already in use")
    if _digest(baseline_preflight_path) != approved_baseline_sha256:
        raise ValueError("baseline preflight differs from its approved hash")
    baseline = json.loads(baseline_preflight_path.read_text(encoding="utf-8"))
    if baseline.get("status") != "eligible" or len(baseline.get("requests", ())) != 40:
        raise ValueError("baseline comparative preflight is not complete and eligible")
    profile = load_research_model_profiles(profiles_path).profiles["openai-sol-supervisor"]
    stage = load_stage_budget_tracker(stage_budgets_path, "chapter_judge").budget
    baseline_hashes = {
        (row["chapter_id"], iso3): digest
        for row in baseline["requests"]
        for iso3, digest in row["projection_sha256s"].items()
    }
    requests = []
    for chapter in CHAPTERS:
        projections = tuple(
            RulerChapterProjection.model_validate_json(
                (baseline_run / f"chapter-judgment-inputs-v2/{chapter}/{iso3}.json").read_bytes()
            )
            for iso3 in RULERS
        )
        for projection in projections:
            path = baseline_run / f"chapter-judgment-inputs-v2/{chapter}/{projection.iso3}.json"
            if _digest(path) != baseline_hashes[(chapter, projection.iso3)]:
                raise ValueError("answer-only input projection differs from baseline preflight")
        guide_path = next(guides_root.glob(f"{chapter.lower()}-*.md"))
        prompt = _prompt(chapter, projections, guide_path.read_text(encoding="utf-8"))
        keys = tuple(item.job_key for item in projections)
        schema = codex_chapter_judgment_json_schema(chapter, keys)
        identities = {
            item.job_key: {
                "iso3": item.iso3, "ruler_id": item.ruler_id,
                "ruler_year_id": item.ruler_year_id, "ruler_name": item.ruler_name,
                "period_start_year": item.period_start_year,
                "period_end_year": item.period_end_year,
            }
            for item in projections
        }
        allowed = {item.job_key: sorted(_answer_ids(item)) for item in projections}
        chapter_ids = sorted({value for ids in allowed.values() for value in ids})
        _constrain_schema(schema, keys, chapter_ids)
        make_strict_response_schema(schema)
        complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        tokens = len(tiktoken.get_encoding("o200k_base").encode(complete))
        requests.append({
            "chapter_id": chapter,
            "component": f"{chapter}-answer-trusting",
            "complete_request_sha256": sha256(complete.encode()).hexdigest(),
            "estimated_input_tokens": tokens,
            "prompt": prompt,
            "schema": schema,
            "dossier_job_keys": list(keys),
            "allowed_evidence_ids": allowed,
            "identities": identities,
            "projection_sha256s": {
                item.iso3: baseline_hashes[(chapter, item.iso3)] for item in projections
            },
        })
    planned = sum(item["estimated_input_tokens"] for item in requests)
    output_capacity = len(requests) * stage.output_allowance(profile.model)
    reasons = []
    if any(item["estimated_input_tokens"] > stage.max_request_input_tokens for item in requests):
        reasons.append("request_input_tokens")
    if planned > 2_500_000:
        reasons.append("run_input_tokens")
    if output_capacity > 500_000:
        reasons.append("run_output_tokens")
    payload = {
        "schema_version": "answer_trusting_judgment_preflight_v2",
        "status": "eligible" if not reasons else "rejected",
        "purpose": "non_production_answer_trusting_comparison",
        "provider": profile.provider,
        "model": profile.model,
        "profile": "openai-sol-supervisor",
        "reasoning_effort": "high",
        "surface": "codex_subscription",
        "web_search": "disabled",
        "planned_calls": 8,
        "planned_input_tokens": planned,
        "required_output_capacity": output_capacity,
        "limits": {"maximum_calls": 8, "maximum_input_tokens": 2_500_000,
                   "maximum_output_tokens": 500_000},
        "baseline_preflight_path": str(baseline_preflight_path),
        "baseline_preflight_sha256": approved_baseline_sha256,
        "profiles_sha256": _digest(profiles_path),
        "stage_budgets_sha256": _digest(stage_budgets_path),
        "output_root": str(output_root.resolve()),
        "budget_stop_reasons": reasons,
        "model_calls_executed": 0,
        "reservations_created": 0,
        "requests": requests,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def run_all(*, project_root: Path, preflight_path: Path, approved_preflight_sha256: str,
            profiles_path: Path,
            stage_budgets_path: Path, output_root: Path) -> tuple[Path, ...]:
    """Execute or trusted-reload the exact eight diagnostic requests."""

    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    if (
        _digest(preflight_path) != approved_preflight_sha256
        or saved.get("schema_version") != "answer_trusting_judgment_preflight_v2"
        or saved.get("status") != "eligible"
        or saved.get("planned_calls") != 8
        or saved.get("provider") != "openai"
        or saved.get("model") != "gpt-5.6-sol"
        or saved.get("reasoning_effort") != "high"
        or saved.get("surface") != "codex_subscription"
        or saved.get("web_search") != "disabled"
        or saved.get("limits") != {"maximum_calls": 8, "maximum_input_tokens": 2_500_000,
                                   "maximum_output_tokens": 500_000}
        or Path(saved.get("output_root", "")).resolve() != output_root.resolve()
    ):
        raise ValueError("answer-trusting preflight is not eligible")
    if (
        _digest(profiles_path) != saved["profiles_sha256"]
        or _digest(stage_budgets_path) != saved["stage_budgets_sha256"]
    ):
        raise ValueError("answer-trusting transport configuration changed")
    profile = load_research_model_profiles(profiles_path).profiles[saved["profile"]]
    if profile.provider != saved["provider"] or profile.model != saved["model"]:
        raise ValueError("answer-trusting model profile changed")
    requests = saved["requests"]
    if (
        [item["chapter_id"] for item in requests] != list(CHAPTERS)
        or len({item["component"] for item in requests}) != 8
        or len({item["complete_request_sha256"] for item in requests}) != 8
    ):
        raise ValueError("answer-trusting request inventory is incomplete")
    allowed_hashes = frozenset(item["complete_request_sha256"] for item in saved["requests"])
    run_tracker = RunUsageBudgetTracker(
        ledger_path=output_root / "usage.json",
        limits=RunUsageLimits(max_calls=8, max_input_tokens=2_500_000, max_output_tokens=500_000),
        config_sha256=_digest(preflight_path), allowed_request_sha256s=allowed_hashes,
    )
    stage_tracker = load_stage_budget_tracker(
        stage_budgets_path, "chapter_judge", ledger_path=output_root / "stage-usage.json"
    )
    results = []
    for request in requests:
        output_dir = output_root / request["component"]
        if output_dir.exists() and any(output_dir.iterdir()):
            results.append(_recover(output_dir, request, preflight_path, output_root))
            continue
        response = execute_json_model(
            project_root, profile, request["prompt"], _RawResponse, output_dir,
            budget_tracker=stage_tracker, request_component=request["component"],
            reasoning_effort="high", call_coordinator=ModelCallCoordinator(),
            run_budget_tracker=run_tracker, response_schema=request["schema"],
            isolated_web_research=True,
            disable_web_search=True,
        )
        _validate_no_tool_events(output_dir / "events.jsonl")
        batch = ChapterJudgmentBatch.model_validate(response.model_dump(mode="json"))
        _validate(batch, request)
        result_path = output_dir / "judgment.json"
        result_path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _write_binding(output_dir, request, result_path)
        results.append(result_path)
    return tuple(results)


def _prompt(chapter: str, projections: tuple[RulerChapterProjection, ...], guide: str) -> str:
    inputs = []
    for item in projections:
        inputs.append({
            "dossier_job_key": item.job_key, "iso3": item.iso3, "ruler_id": item.ruler_id,
            "ruler_year_id": item.ruler_year_id, "ruler_name": item.ruler_name,
            "period_start_year": item.period_start_year, "period_end_year": item.period_end_year,
            "reviewed_answers": [
                answer.model_dump(mode="json") for answer in item.approved_question_answers
            ],
            "evidence_environment": item.evidence_environment.model_dump(mode="json"),
            "unresolved_gaps": item.unresolved_gaps,
        })
    return f"""You are running a non-production answer-trusting comparison for chapter {chapter}.
Judge all five rulers on one common absolute meter. Treat the ten reviewed answers, their
limitations, and their cited evidence IDs as the complete trusted factual record. Do not
reassess source excerpts, browse, use tools, add facts from memory, or infer facts absent from
the answers. Evidence IDs are opaque provenance handles: cite only IDs visible in that ruler's
answers. Leave decisive_local_evidence and contextual_local_evidence empty because no local
records are supplied. Missingness lowers confidence rather than mechanically lowering score.
Use half-point scores and the guide's absolute anchors. Return exactly five unique evaluations,
with the exact identities below. `calibrated_against` must use other listed dossier keys.
Report `confidence_score` on the required 0-100 percentage scale, never as a 0-1 fraction.
For each ruler, classify every lens at most once: `supported_lenses` and
`missing_or_weak_lenses` must be disjoint, contain no duplicates, and use only the ten IDs for
chapter {chapter}. Before returning, explicitly check that their intersection is empty.
This diagnostic is never publication-eligible.

Trusted answer-only inputs:
{json.dumps(inputs, indent=2, sort_keys=True)}

Active chapter guide:
---
{guide}
---
Return only the requested JSON batch with chapter_id {chapter}, target_year 2023,
schema_version ruler_chapter_judgment_v1, job_key answer-trusting-{chapter}-v1,
run_key five-ruler-2023-answer-trusting-v1, calibration_batch_id answer-trusting-{chapter}-v1,
and a substantive comparison rationale for every ruler."""


def _answer_ids(projection: RulerChapterProjection) -> set[str]:
    ids = {
        evidence_id
        for answer in projection.approved_question_answers
        for evidence_id in (
            *answer.supporting_evidence_ids, *answer.contrary_or_qualifying_evidence_ids
        )
    }
    for answer in projection.approved_question_answers:
        text = answer.answer + "\n" + "\n".join(answer.limitations_and_gaps)
        ids.update(re.findall(r"E\d{3,}", text))
    return ids


def _validate(batch: ChapterJudgmentBatch, request: dict) -> None:
    if batch.chapter_id != request["chapter_id"] or batch.target_year != 2023:
        raise ValueError("answer-trusting result has the wrong chapter or year")
    keys = [item.dossier_job_key for item in batch.evaluations]
    if len(keys) != 5 or len(set(keys)) != 5 or set(keys) != set(request["dossier_job_keys"]):
        raise ValueError("answer-trusting result differs from the exact five-ruler cohort")
    for item in batch.evaluations:
        identity = request["identities"][item.dossier_job_key]
        if any(
            getattr(item, field) != value
            for field, value in identity.items()
        ):
            raise ValueError("answer-trusting result identity differs from its bound input")
        allowed = set(request["allowed_evidence_ids"][item.dossier_job_key])
        if _evaluation_web_evidence_ids(item) - allowed:
            raise ValueError("answer-trusting result cites evidence absent from reviewed answers")
        if item.decisive_local_evidence or item.contextual_local_evidence:
            raise ValueError("answer-trusting result invented unavailable local evidence")
        if item.confidence_score < 10:
            raise ValueError("answer-trusting confidence is not on the 0-100 scale")


def _constrain_schema(schema: dict, keys: tuple[str, ...], evidence_ids: list[str]) -> None:
    evaluation = schema["$defs"]["RulerChapterJudgment"]["properties"]
    evaluation["dossier_job_key"] = {"type": "string", "enum": list(keys)}
    evaluation["confidence_score"]["minimum"] = 10
    schema["$defs"]["ChapterEvidenceReference"]["properties"]["evidence_id"] = {
        "type": "string", "enum": evidence_ids
    }
    bias = schema["$defs"]["MaterialBiasFinding"]["properties"]
    bias["supporting_evidence_ids"]["items"] = {"type": "string", "enum": evidence_ids}


def _recover(output_dir: Path, request: dict, preflight_path: Path, output_root: Path) -> Path:
    prompt_path, schema_path = output_dir / "prompt.txt", output_dir / "schema.json"
    raw_path, events_path = output_dir / "output.json", output_dir / "events.jsonl"
    if not all(path.is_file() for path in (prompt_path, schema_path, raw_path, events_path)):
        raise ValueError("answer-trusting output is nonempty but lacks a complete paid result")
    complete = prompt_path.read_text() + json.dumps(
        json.loads(schema_path.read_text()), ensure_ascii=False, sort_keys=True
    )
    if (
        prompt_path.read_text() != request["prompt"]
        or json.loads(schema_path.read_text()) != request["schema"]
        or sha256(complete.encode()).hexdigest() != request["complete_request_sha256"]
    ):
        raise ValueError("answer-trusting paid request differs from its preflight")
    _validate_no_tool_events(events_path)
    ledger = json.loads((output_root / "usage.json").read_text())
    completed = [
        row for row in ledger
        if row.get("status") == "completed"
        and row.get("request_sha256") == request["complete_request_sha256"]
        and row.get("config_sha256") == _digest(preflight_path)
    ]
    if len(completed) != 1:
        raise ValueError("answer-trusting paid result lacks one exact completed reservation")
    batch = ChapterJudgmentBatch.model_validate_json(raw_path.read_bytes())
    _validate(batch, request)
    result_path = output_dir / "judgment.json"
    canonical = batch.model_dump_json(indent=2) + "\n"
    if result_path.exists() and result_path.read_text() != canonical:
        raise ValueError("answer-trusting derived judgment changed")
    result_path.write_text(canonical, encoding="utf-8")
    _write_binding(output_dir, request, result_path)
    return result_path


def _write_binding(output_dir: Path, request: dict, result_path: Path) -> None:
    path = output_dir / "result-binding.json"
    expected = {
        "schema_version": "answer_trusting_result_binding_v1",
        "component": request["component"],
        "request_sha256": request["complete_request_sha256"],
        "result_sha256": _digest(result_path),
        "production_eligible": False,
    }
    if path.exists() and json.loads(path.read_text()) != expected:
        raise ValueError("answer-trusting result binding changed")
    path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = ["build_preflight", "run_all"]
