"""Durable two-phase execution for comparative chapter judgments."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import tiktoken
from pydantic import BaseModel, ConfigDict

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .chapter_judge_models import ChapterJudgmentBatch, codex_chapter_judgment_json_schema
from .chapter_projection import RulerChapterProjection
from .json_model_execution import execute_json_model
from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

_CAPABILITY = object()
_EXECUTION_ROOT = "comparative-judgments-v4"
_INITIAL_USAGE_LEDGER = "comparative-judgment-v4-usage.json"
_STAGE_USAGE_LEDGER = "comparative-judgment-v4-stage-usage.json"
_FINAL_USAGE_LEDGER = "chapter-calibration-v4-usage.json"


class _RawJudgmentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True)
class ComparativeJudgmentAuthorization:
    preflight_path: Path
    preflight_sha256: str
    input_root: Path
    request_sha256s: frozenset[str]
    profile_name: str
    profiles_path: Path
    profiles_sha256: str
    stage_budgets_path: Path
    stage_budgets_sha256: str
    run_dir: Path
    _capability: object


def load_comparative_judgment_authorization(
    *,
    preflight_path: Path,
    approved_preflight_sha256: str,
    input_root: Path,
    profile_name: str,
    profiles_path: Path,
    stage_budgets_path: Path,
    run_dir: Path,
) -> ComparativeJudgmentAuthorization:
    """Reconstruct every initial request before issuing execution authority."""

    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    stage = load_stage_budget_tracker(stage_budgets_path, "chapter_judge").budget
    if (
        saved.get("schema_version") != "five_ruler_comparative_judgment_preflight_v7"
        or saved.get("status") != "eligible"
        or _digest(preflight_path) != approved_preflight_sha256
        or saved.get("profile") != profile_name
        or saved.get("model") != profile.model
        or saved.get("provider") != profile.provider
        or saved.get("reasoning_effort") != "high"
        or saved.get("transport_mode") != "embedded_single_ruler_then_calibrate"
        or saved.get("planned_initial_calls") != 40
        or saved.get("mandatory_final_calibration_calls") != 8
        or saved.get("required_output_capacity") != 48 * stage.output_allowance(profile.model)
    ):
        raise ValueError("comparative judgment authorization differs from approved preflight")
    requests = saved.get("requests", ())
    if len(requests) != 40 or len({item["component"] for item in requests}) != 40:
        raise ValueError("comparative judgment preflight inventory is incomplete")
    hashes = set()
    for item in requests:
        request_path = input_root / f"{item['component']}.json"
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        additional = tuple(
            _confined_projection(path, run_dir=run_dir).read_text(encoding="utf-8")
            for path in payload.get("additional_input_paths", ())
        )
        complete = (
            payload["prompt"]
            + json.dumps(payload["schema"], ensure_ascii=False, sort_keys=True)
            + "".join(additional)
        )
        request_hash = sha256(complete.encode()).hexdigest()
        if request_hash != item["complete_request_sha256"]:
            raise ValueError("comparative judgment request changed after preflight")
        chapter = item["chapter_id"]
        projection_root = run_dir / "chapter-judgment-inputs-v2" / chapter
        actual_projection_hashes = {
            path.stem: _digest(path)
            for path in projection_root.glob("*.json")
            if path.stem in item["projection_sha256s"]
        }
        if actual_projection_hashes != item["projection_sha256s"]:
            raise ValueError("comparative judgment projections changed after preflight")
        hashes.add(request_hash)
    return ComparativeJudgmentAuthorization(
        preflight_path=preflight_path,
        preflight_sha256=_digest(preflight_path),
        input_root=input_root,
        request_sha256s=frozenset(hashes),
        profile_name=profile_name,
        profiles_path=profiles_path,
        profiles_sha256=_digest(profiles_path),
        stage_budgets_path=stage_budgets_path,
        stage_budgets_sha256=_digest(stage_budgets_path),
        run_dir=run_dir,
        _capability=_CAPABILITY,
    )


def run_comparative_judgment_request(
    *,
    authorization: ComparativeJudgmentAuthorization,
    project_root: Path,
    component: str,
) -> Path:
    """Execute one exact initial request; shard results remain explicitly non-final."""

    _recheck(authorization)
    request_path = authorization.input_root / f"{component}.json"
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    additional = tuple(
        _confined_projection(path, run_dir=authorization.run_dir).read_text(encoding="utf-8")
        for path in payload.get("additional_input_paths", ())
    )
    request_hash = _request_hash(payload, additional)
    if request_hash not in authorization.request_sha256s:
        raise ValueError("comparative judgment request is not authorized")
    output_dir = authorization.run_dir / _EXECUTION_ROOT / component
    _archive_pre_call_quota_stop(output_dir, authorization=authorization, component=component)
    if output_dir.exists() and any(output_dir.iterdir()):
        return _recover_initial_result(
            authorization=authorization,
            component=component,
            payload=payload,
            output_dir=output_dir,
            request_hash=request_hash,
        )
    profile = load_research_model_profiles(authorization.profiles_path).profiles[
        authorization.profile_name
    ]
    run_tracker = RunUsageBudgetTracker(
        ledger_path=authorization.run_dir / _INITIAL_USAGE_LEDGER,
        limits=RunUsageLimits(
            max_calls=40, max_input_tokens=12_400_000, max_output_tokens=2_500_000
        ),
        config_sha256=authorization.preflight_sha256,
        allowed_request_sha256s=authorization.request_sha256s,
    )
    stage_tracker = load_stage_budget_tracker(
        authorization.stage_budgets_path,
        "chapter_judge",
        ledger_path=authorization.run_dir / _STAGE_USAGE_LEDGER,
    )
    response = execute_json_model(
        project_root,
        profile,
        payload["prompt"],
        _RawJudgmentResponse,
        output_dir,
        budget_tracker=stage_tracker,
        request_component=component,
        reasoning_effort="high",
        call_coordinator=ModelCallCoordinator(),
        run_budget_tracker=run_tracker,
        response_schema=payload["schema"],
        additional_inputs=additional,
        isolated_web_research=not additional,
    )
    if additional:
        _validate_file_read_events(
            output_dir / "events.jsonl", tuple(payload["additional_input_paths"])
        )
    else:
        _validate_no_tool_events(output_dir / "events.jsonl")
    batch = ChapterJudgmentBatch.model_validate(response.model_dump(mode="json"))
    _validate_batch(batch, payload=payload, authorization=authorization, component=component)
    result_path = output_dir / "judgment.json"
    result_path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
    status = {
        "schema_version": "comparative_judgment_result_binding_v1",
        "component": component,
        "request_sha256": request_hash,
        "result_sha256": _digest(result_path),
        "publication_eligible": False,
        "requires_final_calibration": True,
    }
    (output_dir / "result-binding.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result_path


def build_all_chapter_calibration_preflight(
    *, authorization: ComparativeJudgmentAuthorization, output_path: Path
) -> Path:
    """Trusted-reload 40 first passes and measure eight mandatory calibrations."""

    requests = []
    for chapter in ("1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B"):
        batches = []
        for iso3 in ("CHN", "ISR", "PRK", "RUS", "USA"):
            component = f"{chapter}-{iso3}"
            payload = json.loads((authorization.input_root / f"{component}.json").read_text())
            result = _recover_initial_result(
                authorization=authorization,
                component=component,
                payload=payload,
                output_dir=authorization.run_dir / _EXECUTION_ROOT / component,
                request_hash=_request_hash(payload, ()),
            )
            batch = ChapterJudgmentBatch.model_validate_json(result.read_bytes())
            if len(batch.evaluations) != 1 or batch.evaluations[0].iso3 != iso3:
                raise ValueError("single-ruler first pass differs from frozen identity")
            batches.append(batch)
        prompt = _chapter_calibration_prompt(chapter, batches)
        keys = tuple(batch.evaluations[0].dossier_job_key for batch in batches)
        schema = codex_chapter_judgment_json_schema(chapter, keys)
        make_strict_response_schema(schema)
        complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        requests.append(
            {
                "chapter_id": chapter,
                "component": f"{chapter}-final",
                "complete_request_sha256": sha256(complete.encode()).hexdigest(),
                "estimated_input_tokens": len(tiktoken.get_encoding("o200k_base").encode(complete)),
                "first_pass_sha256s": {
                    batch.evaluations[0].iso3: _digest(
                        authorization.run_dir
                        / _EXECUTION_ROOT
                        / f"{chapter}-{batch.evaluations[0].iso3}"
                        / "judgment.json"
                    )
                    for batch in batches
                },
                "dossier_job_keys": list(keys),
                "allowed_cited_evidence_ids": _cited_ids_by_dossier(batches),
                "allowed_local_evidence_ids": _local_ids_by_dossier(batches),
                "prompt": prompt,
                "schema": schema,
            }
        )
    total = sum(item["estimated_input_tokens"] for item in requests)
    reasons = [] if total <= 800_000 else ["calibration_input_capacity"]
    payload = {
        "schema_version": "all_chapter_calibration_preflight_v1",
        "status": "eligible" if not reasons else "rejected",
        "planned_calls": 8,
        "planned_input_tokens": total,
        "required_output_capacity": 500_000,
        "budget_stop_reasons": reasons,
        "model_calls_executed": 0,
        "reservations_created": 0,
        "requests": requests,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def run_chapter_calibration(
    *,
    authorization: ComparativeJudgmentAuthorization,
    project_root: Path,
    preflight_path: Path,
    approved_preflight_sha256: str,
    chapter_id: str,
) -> Path:
    """Run one exact final five-ruler calibration from trusted first passes."""

    _recheck(authorization)
    saved = json.loads(preflight_path.read_text())
    if _digest(preflight_path) != approved_preflight_sha256 or saved.get("status") != "eligible":
        raise ValueError("chapter calibration preflight is not approved")
    matches = [item for item in saved["requests"] if item["chapter_id"] == chapter_id]
    if len(matches) != 1:
        raise ValueError("chapter calibration inventory is not exact")
    item = matches[0]
    current_first_passes = {
        iso3: _digest(
            authorization.run_dir / _EXECUTION_ROOT / f"{chapter_id}-{iso3}" / "judgment.json"
        )
        for iso3 in ("CHN", "ISR", "PRK", "RUS", "USA")
    }
    if current_first_passes != item["first_pass_sha256s"]:
        raise ValueError("chapter calibration first passes changed")
    complete = item["prompt"] + json.dumps(item["schema"], ensure_ascii=False, sort_keys=True)
    request_hash = sha256(complete.encode()).hexdigest()
    if request_hash != item["complete_request_sha256"]:
        raise ValueError("chapter calibration request changed")
    profile = load_research_model_profiles(authorization.profiles_path).profiles[
        authorization.profile_name
    ]
    output_dir = authorization.run_dir / _EXECUTION_ROOT / item["component"]
    if output_dir.exists() and any(output_dir.iterdir()):
        return _recover_chapter_calibration(
            authorization=authorization,
            preflight_path=preflight_path,
            item=item,
            output_dir=output_dir,
            request_hash=request_hash,
        )
    tracker = RunUsageBudgetTracker(
        ledger_path=authorization.run_dir / _FINAL_USAGE_LEDGER,
        limits=RunUsageLimits(max_calls=8, max_input_tokens=800_000, max_output_tokens=500_000),
        config_sha256=_digest(preflight_path),
        allowed_request_sha256s=frozenset(
            request["complete_request_sha256"] for request in saved["requests"]
        ),
    )
    stage_tracker = load_stage_budget_tracker(
        authorization.stage_budgets_path,
        "chapter_judge",
        ledger_path=authorization.run_dir / _STAGE_USAGE_LEDGER,
    )
    response = execute_json_model(
        project_root,
        profile,
        item["prompt"],
        _RawJudgmentResponse,
        output_dir,
        budget_tracker=stage_tracker,
        request_component=item["component"],
        reasoning_effort="high",
        call_coordinator=ModelCallCoordinator(),
        run_budget_tracker=tracker,
        response_schema=item["schema"],
    )
    _validate_no_tool_events(output_dir / "events.jsonl")
    batch = ChapterJudgmentBatch.model_validate(response.model_dump(mode="json"))
    payload = {
        "job": {"input": {"chapter_id": chapter_id, "dossier_job_keys": item["dossier_job_keys"]}}
    }
    _validate_batch(
        batch,
        payload=payload,
        authorization=authorization,
        component=item["component"],
        allowed_cited_ids={
            key: set(value) for key, value in item["allowed_cited_evidence_ids"].items()
        },
        allowed_local_ids={
            key: set(value) for key, value in item["allowed_local_evidence_ids"].items()
        },
    )
    result = output_dir / "judgment.json"
    result.write_text(batch.model_dump_json(indent=2) + "\n")
    (output_dir / "result-binding.json").write_text(
        json.dumps(
            {
                "schema_version": "comparative_judgment_result_binding_v1",
                "component": item["component"],
                "request_sha256": request_hash,
                "result_sha256": _digest(result),
                "publication_eligible": True,
                "requires_final_calibration": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return result


def _recover_chapter_calibration(
    *,
    authorization: ComparativeJudgmentAuthorization,
    preflight_path: Path,
    item: dict,
    output_dir: Path,
    request_hash: str,
) -> Path:
    _validate_no_tool_events(output_dir / "events.jsonl")
    if (output_dir / "prompt.txt").read_text() != item["prompt"]:
        raise ValueError("saved chapter calibration prompt changed")
    if json.loads((output_dir / "schema.json").read_text()) != item["schema"]:
        raise ValueError("saved chapter calibration schema changed")
    raw = _RawJudgmentResponse.model_validate_json((output_dir / "output.json").read_bytes())
    batch = ChapterJudgmentBatch.model_validate(raw.model_dump(mode="json"))
    payload = {
        "job": {
            "input": {
                "chapter_id": item["chapter_id"],
                "dossier_job_keys": item["dossier_job_keys"],
            }
        }
    }
    _validate_batch(
        batch,
        payload=payload,
        authorization=authorization,
        component=item["component"],
        allowed_cited_ids={
            key: set(value) for key, value in item["allowed_cited_evidence_ids"].items()
        },
        allowed_local_ids={
            key: set(value) for key, value in item["allowed_local_evidence_ids"].items()
        },
    )
    usage = json.loads((authorization.run_dir / _FINAL_USAGE_LEDGER).read_text())
    completed = [
        row
        for row in usage
        if row.get("status") == "completed" and row.get("request_sha256") == request_hash
    ]
    if len(completed) != 1 or completed[0].get("config_sha256") != _digest(preflight_path):
        raise ValueError("chapter calibration recovery lacks one completed reservation")
    result = output_dir / "judgment.json"
    expected = batch.model_dump_json(indent=2) + "\n"
    if result.exists() and result.read_text() != expected:
        raise ValueError("saved chapter calibration differs from raw output")
    result.write_text(expected)
    binding = {
        "schema_version": "comparative_judgment_result_binding_v1",
        "component": item["component"],
        "request_sha256": request_hash,
        "result_sha256": _digest(result),
        "publication_eligible": True,
        "requires_final_calibration": False,
    }
    binding_path = output_dir / "result-binding.json"
    if binding_path.exists() and json.loads(binding_path.read_text()) != binding:
        raise ValueError("saved chapter calibration binding changed")
    binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    return result


def _chapter_calibration_prompt(chapter: str, batches: list[ChapterJudgmentBatch]) -> str:
    return (
        f"You are the final comparative calibrator for chapter {chapter}. Compare all five "
        "lossless single-ruler first passes below on one common absolute chapter meter. "
        "Return exactly one complete five-ruler batch. Reassess scores and confidence; first-pass "
        "scores are advisory, not binding. Do not browse, use tools, add facts, or cite an "
        "evidence "
        "ID absent from that ruler's first pass. This output alone is publication-eligible.\n\n"
        + json.dumps([batch.model_dump(mode="json") for batch in batches], indent=2, sort_keys=True)
    )


def build_cross_shard_calibration_preflight(
    *,
    authorization: ComparativeJudgmentAuthorization,
    run_dir: Path,
    output_path: Path,
) -> Path:
    """Validate both exact shards and measure the mandatory final 4B calibration."""

    shard_paths = [
        run_dir / _EXECUTION_ROOT / name / "judgment.json" for name in ("4B-shard-a", "4B-shard-b")
    ]
    shards = []
    for path in shard_paths:
        component = path.parent.name
        payload = json.loads(
            (authorization.input_root / f"{component}.json").read_text(encoding="utf-8")
        )
        additional = tuple(
            _confined_projection(path, run_dir=authorization.run_dir).read_text(encoding="utf-8")
            for path in payload["additional_input_paths"]
        )
        request_hash = _request_hash(payload, additional)
        result_path = _recover_initial_result(
            authorization=authorization,
            component=component,
            payload=payload,
            output_dir=path.parent,
            request_hash=request_hash,
        )
        shards.append(ChapterJudgmentBatch.model_validate_json(result_path.read_bytes()))
    inventories = [{item.iso3 for item in batch.evaluations} for batch in shards]
    if inventories != [{"CHN", "ISR", "PRK"}, {"PRK", "RUS", "USA"}]:
        raise ValueError("4B shard outputs differ from the frozen overlap inventory")
    prompt = _calibration_prompt(shards)
    dossier_keys = tuple(
        item.dossier_job_key
        for batch in shards
        for item in batch.evaluations
        if item.iso3 != "PRK" or batch is shards[0]
    )
    schema = codex_chapter_judgment_json_schema("4B", dossier_keys)
    make_strict_response_schema(schema)
    complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
    tokens = len(tiktoken.get_encoding("o200k_base").encode(complete))
    reasons = [] if tokens <= 150_000 else ["final_calibration_input_reservation"]
    payload = {
        "schema_version": "cross_shard_calibration_preflight_v1",
        "status": "eligible" if not reasons else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "planned_calls": 1,
        "planned_input_tokens": tokens,
        "required_output_capacity": 62_500,
        "budget_stop_reasons": reasons,
        "shard_sha256s": {path.parent.name: _digest(path) for path in shard_paths},
        "complete_request_sha256": sha256(complete.encode()).hexdigest(),
        "dossier_job_keys": list(dossier_keys),
        "allowed_cited_evidence_ids": _cited_ids_by_dossier(shards),
        "prompt": prompt,
        "schema": schema,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def _recover_initial_result(
    *,
    authorization: ComparativeJudgmentAuthorization,
    component: str,
    payload: dict,
    output_dir: Path,
    request_hash: str,
) -> Path:
    """Trusted-reload one paid initial call and repair deterministic local metadata."""

    if payload.get("additional_input_paths"):
        _validate_file_read_events(
            output_dir / "events.jsonl", tuple(payload["additional_input_paths"])
        )
    else:
        _validate_no_tool_events(output_dir / "events.jsonl")
    if (output_dir / "prompt.txt").read_text(encoding="utf-8") != payload["prompt"]:
        raise ValueError("saved comparative judgment prompt changed")
    if json.loads((output_dir / "schema.json").read_text()) != payload["schema"]:
        raise ValueError("saved comparative judgment schema changed")
    raw = _RawJudgmentResponse.model_validate_json((output_dir / "output.json").read_bytes())
    batch = ChapterJudgmentBatch.model_validate(raw.model_dump(mode="json"))
    _validate_batch(batch, payload=payload, authorization=authorization, component=component)
    usage = json.loads((authorization.run_dir / _INITIAL_USAGE_LEDGER).read_text())
    completed = [
        item
        for item in usage
        if item.get("status") == "completed" and item.get("request_sha256") == request_hash
    ]
    if len(completed) != 1:
        raise ValueError("comparative judgment recovery lacks one completed reservation")
    result_path = output_dir / "judgment.json"
    expected_result = batch.model_dump_json(indent=2) + "\n"
    if result_path.exists():
        if result_path.read_text(encoding="utf-8") != expected_result:
            raise ValueError("saved comparative judgment differs from raw output")
    else:
        result_path.write_text(expected_result, encoding="utf-8")
    binding_path = output_dir / "result-binding.json"
    expected_binding = {
        "schema_version": "comparative_judgment_result_binding_v1",
        "component": component,
        "request_sha256": request_hash,
        "result_sha256": _digest(result_path),
        "publication_eligible": False,
        "requires_final_calibration": True,
    }
    if binding_path.exists():
        if json.loads(binding_path.read_text()) != expected_binding:
            raise ValueError("comparative judgment result binding changed")
    else:
        binding_path.write_text(json.dumps(expected_binding, indent=2, sort_keys=True) + "\n")
    return result_path


def run_cross_shard_calibration(
    *,
    authorization: ComparativeJudgmentAuthorization,
    project_root: Path,
    preflight_path: Path,
    approved_preflight_sha256: str,
) -> Path:
    """Execute the sole exact final calibration and publish the final 4B batch."""

    _recheck(authorization)
    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    shard_paths = {
        name: authorization.run_dir / _EXECUTION_ROOT / name / "judgment.json"
        for name in ("4B-shard-a", "4B-shard-b")
    }
    if (
        saved.get("status") != "eligible"
        or _digest(preflight_path) != approved_preflight_sha256
        or saved.get("shard_sha256s") != {name: _digest(path) for name, path in shard_paths.items()}
    ):
        raise ValueError("cross-shard calibration differs from exact trusted shards")
    complete = saved["prompt"] + json.dumps(saved["schema"], ensure_ascii=False, sort_keys=True)
    request_hash = sha256(complete.encode()).hexdigest()
    if request_hash != saved.get("complete_request_sha256"):
        raise ValueError("cross-shard calibration request changed after preflight")
    profile = load_research_model_profiles(authorization.profiles_path).profiles[
        authorization.profile_name
    ]
    output_dir = authorization.run_dir / _EXECUTION_ROOT / "4B-final"
    if output_dir.exists() and any(output_dir.iterdir()):
        return _recover_final_result(
            authorization=authorization,
            saved=saved,
            output_dir=output_dir,
            request_hash=request_hash,
        )
    run_tracker = RunUsageBudgetTracker(
        ledger_path=authorization.run_dir / _FINAL_USAGE_LEDGER,
        limits=RunUsageLimits(max_calls=1, max_input_tokens=150_000, max_output_tokens=62_500),
        config_sha256=_digest(preflight_path),
        allowed_request_sha256s=frozenset({request_hash}),
    )
    stage_tracker = load_stage_budget_tracker(
        authorization.stage_budgets_path,
        "chapter_judge",
        ledger_path=authorization.run_dir / _STAGE_USAGE_LEDGER,
    )
    response = execute_json_model(
        project_root,
        profile,
        saved["prompt"],
        _RawJudgmentResponse,
        output_dir,
        budget_tracker=stage_tracker,
        request_component="4B-final",
        reasoning_effort="high",
        call_coordinator=ModelCallCoordinator(),
        run_budget_tracker=run_tracker,
        response_schema=saved["schema"],
    )
    batch = ChapterJudgmentBatch.model_validate(response.model_dump(mode="json"))
    payload = {
        "job": {
            "input": {
                "chapter_id": "4B",
                "dossier_job_keys": saved["dossier_job_keys"],
            }
        }
    }
    _validate_batch(
        batch,
        payload=payload,
        authorization=authorization,
        component="4B-final",
        allowed_cited_ids={
            key: set(value) for key, value in saved["allowed_cited_evidence_ids"].items()
        },
    )
    result_path = output_dir / "judgment.json"
    result_path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (output_dir / "result-binding.json").write_text(
        json.dumps(
            {
                "schema_version": "comparative_judgment_result_binding_v1",
                "component": "4B-final",
                "request_sha256": request_hash,
                "result_sha256": _digest(result_path),
                "publication_eligible": True,
                "requires_final_calibration": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return result_path


def _calibration_prompt(shards: list[ChapterJudgmentBatch]) -> str:
    return """You are the final cross-shard calibrator for chapter 4B. The two complete
lossless shard judgments below used PRK as their shared anchor. Reconcile the PRK
assessment, compare all five rulers on one absolute chapter_4b_v4 meter, and return one
complete ruler_chapter_judgment_v1 batch with exactly CHN, ISR, PRK, RUS, and USA.
Do not add facts, browse, or treat shard scores as binding. Preserve cited evidence IDs
within each ruler. This output alone can become the final 4B judgment; shard outputs are
non-publication intermediates.\n\n""" + json.dumps(
        [item.model_dump(mode="json") for item in shards], indent=2, sort_keys=True
    )


def _recover_final_result(
    *,
    authorization: ComparativeJudgmentAuthorization,
    saved: dict,
    output_dir: Path,
    request_hash: str,
) -> Path:
    """Trusted-reload the paid final calibration and repair local metadata."""

    if (output_dir / "prompt.txt").read_text(encoding="utf-8") != saved["prompt"]:
        raise ValueError("saved cross-shard prompt changed")
    if json.loads((output_dir / "schema.json").read_text()) != saved["schema"]:
        raise ValueError("saved cross-shard schema changed")
    raw = _RawJudgmentResponse.model_validate_json((output_dir / "output.json").read_bytes())
    batch = ChapterJudgmentBatch.model_validate(raw.model_dump(mode="json"))
    payload = {
        "job": {
            "input": {
                "chapter_id": "4B",
                "dossier_job_keys": saved["dossier_job_keys"],
            }
        }
    }
    _validate_batch(
        batch,
        payload=payload,
        authorization=authorization,
        component="4B-final",
        allowed_cited_ids={
            key: set(value) for key, value in saved["allowed_cited_evidence_ids"].items()
        },
    )
    usage = json.loads((authorization.run_dir / _FINAL_USAGE_LEDGER).read_text())
    completed = [
        item
        for item in usage
        if item.get("status") == "completed" and item.get("request_sha256") == request_hash
    ]
    if len(completed) != 1:
        raise ValueError("cross-shard recovery lacks one completed reservation")
    result_path = output_dir / "judgment.json"
    expected_result = batch.model_dump_json(indent=2) + "\n"
    if result_path.exists():
        if result_path.read_text(encoding="utf-8") != expected_result:
            raise ValueError("saved cross-shard result differs from raw output")
    else:
        result_path.write_text(expected_result, encoding="utf-8")
    binding_path = output_dir / "result-binding.json"
    expected_binding = {
        "schema_version": "comparative_judgment_result_binding_v1",
        "component": "4B-final",
        "request_sha256": request_hash,
        "result_sha256": _digest(result_path),
        "publication_eligible": True,
        "requires_final_calibration": False,
    }
    if binding_path.exists():
        if json.loads(binding_path.read_text()) != expected_binding:
            raise ValueError("cross-shard result binding changed")
    else:
        binding_path.write_text(json.dumps(expected_binding, indent=2, sort_keys=True) + "\n")
    return result_path


def _validate_batch(
    batch: ChapterJudgmentBatch,
    *,
    payload: dict,
    authorization: ComparativeJudgmentAuthorization,
    component: str,
    allowed_cited_ids: dict[str, set[str]] | None = None,
    allowed_local_ids: dict[str, set[str]] | None = None,
) -> None:
    """Apply identity and evidence-reference checks beyond transport schema."""

    job = payload["job"]
    expected_keys = set(job["input"]["dossier_job_keys"])
    evaluation_keys = [item.dossier_job_key for item in batch.evaluations]
    if (
        batch.chapter_id != job["input"]["chapter_id"]
        or batch.target_year != 2023
        or len(evaluation_keys) != len(expected_keys)
        or len(evaluation_keys) != len(set(evaluation_keys))
        or set(evaluation_keys) != expected_keys
    ):
        raise ValueError("comparative judgment output differs from its exact cohort")
    chapter = job["input"]["chapter_id"]
    projection_dir = authorization.run_dir / "chapter-judgment-inputs-v2" / chapter
    projections = {
        item.job_key: item
        for path in projection_dir.glob("*.json")
        for item in (RulerChapterProjection.model_validate_json(path.read_bytes()),)
        if item.job_key in expected_keys
    }
    if set(projections) != expected_keys:
        raise ValueError(f"{component} lacks its exact trusted projections")
    for evaluation in batch.evaluations:
        projection = projections[evaluation.dossier_job_key]
        if (
            evaluation.iso3 != projection.iso3
            or evaluation.ruler_id != projection.ruler_id
            or evaluation.ruler_year_id != projection.ruler_year_id
            or evaluation.ruler_name != projection.ruler_name
            or evaluation.period_start_year != projection.period_start_year
            or evaluation.period_end_year != projection.period_end_year
        ):
            raise ValueError("comparative judgment identity differs from its projection")
        allowed = {item.evidence_id for item in projection.evidence}
        cited = _evaluation_web_evidence_ids(evaluation)
        if not cited.issubset(allowed):
            raise ValueError("comparative judgment cites evidence outside its projection")
        if allowed_cited_ids is not None and not cited.issubset(
            allowed_cited_ids[evaluation.dossier_job_key]
        ):
            raise ValueError("final calibration cites evidence absent from trusted shards")
        package = projection.local_evidence.package
        allowed_local = (
            {
                *(fact.fact_id for fact in package.facts),
                *(signal.signal_id for signal in package.longitudinal_signals),
            }
            if package is not None
            else set()
        )
        cited_local = {
            item.local_evidence_id
            for field in (
                evaluation.decisive_local_evidence,
                evaluation.contextual_local_evidence,
            )
            for item in field
        }
        if not cited_local.issubset(allowed_local):
            raise ValueError("comparative judgment cites local evidence outside its projection")
        if allowed_local_ids is not None and not cited_local.issubset(
            allowed_local_ids[evaluation.dossier_job_key]
        ):
            raise ValueError("final calibration cites local evidence absent from first pass")


def _cited_ids_by_dossier(shards: list[ChapterJudgmentBatch]) -> dict[str, list[str]]:
    routed: dict[str, set[str]] = {}
    for batch in shards:
        for evaluation in batch.evaluations:
            routed.setdefault(evaluation.dossier_job_key, set()).update(
                _evaluation_web_evidence_ids(evaluation)
            )
    return {key: sorted(value) for key, value in sorted(routed.items())}


def _evaluation_web_evidence_ids(evaluation) -> set[str]:
    cited = {
        item.evidence_id
        for field in (
            evaluation.decisive_positive_evidence,
            evaluation.decisive_negative_evidence,
            evaluation.contrary_evidence,
        )
        for item in field
    }
    cited.update(
        evidence_id
        for finding in evaluation.bias_assessment.material_biases
        for evidence_id in finding.supporting_evidence_ids
    )
    return cited


def _local_ids_by_dossier(batches: list[ChapterJudgmentBatch]) -> dict[str, list[str]]:
    return {
        evaluation.dossier_job_key: sorted(
            item.local_evidence_id
            for field in (
                evaluation.decisive_local_evidence,
                evaluation.contextual_local_evidence,
            )
            for item in field
        )
        for batch in batches
        for evaluation in batch.evaluations
    }


def _recheck(authorization: ComparativeJudgmentAuthorization) -> None:
    if (
        authorization._capability is not _CAPABILITY
        or _digest(authorization.preflight_path) != authorization.preflight_sha256
        or _digest(authorization.profiles_path) != authorization.profiles_sha256
        or _digest(authorization.stage_budgets_path) != authorization.stage_budgets_sha256
    ):
        raise ValueError("comparative judgment authorization changed before execution")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _archive_pre_call_quota_stop(
    output_dir: Path,
    *,
    authorization: ComparativeJudgmentAuthorization,
    component: str,
) -> None:
    """Preserve an exact pre-call stop while allowing an approved quota continuation."""

    if not output_dir.is_dir() or {path.name for path in output_dir.iterdir()} != {
        "run-budget-stop.json"
    }:
        return
    source = output_dir / "run-budget-stop.json"
    saved = json.loads(source.read_text())
    ledger = json.loads((authorization.run_dir / _INITIAL_USAGE_LEDGER).read_text())
    completed = [item for item in ledger if item.get("status") == "completed"]
    totals = {
        "calls": len(completed),
        "input_tokens": sum(
            int(item.get("observed_input_tokens") or item["estimated_input_tokens"])
            for item in completed
        ),
        "output_tokens": sum(int(item.get("observed_output_tokens") or 0) for item in completed),
    }
    prior_limits = {
        "max_calls": 40,
        "max_input_tokens": 6_200_000,
        "max_output_tokens": 2_500_000,
    }
    if (
        saved.get("schema_version") != "run_usage_reservation_v1"
        or saved.get("status") != "stopped"
        or saved.get("component") != component
        or saved.get("stage") != "chapter_judge"
        or saved.get("config_sha256") != authorization.preflight_sha256
        or saved.get("run_limits") != prior_limits
        or saved.get("totals_before") != totals
        or saved.get("stop_reasons") != ["run_input_tokens"]
    ):
        raise ValueError("pre-call quota stop differs from the approved amendment")
    archive = (
        authorization.run_dir / "comparative-quota-stops" / f"{component}-{_digest(source)}.json"
    )
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and archive.read_bytes() != source.read_bytes():
        raise ValueError("quota-stop archive collision")
    if not archive.exists():
        archive.write_bytes(source.read_bytes())
    source.unlink()
    output_dir.rmdir()


def _request_hash(payload: dict, additional_inputs: tuple[str, ...]) -> str:
    complete = (
        payload["prompt"]
        + json.dumps(payload["schema"], ensure_ascii=False, sort_keys=True)
        + "".join(additional_inputs)
    )
    return sha256(complete.encode()).hexdigest()


def _validate_file_read_events(events_path: Path, allowed_paths: tuple[str, ...]) -> None:
    """Require exactly one local read command and reject every other tool action."""

    commands, forbidden_types = _collect_file_read_events(events_path)
    if forbidden_types or len(commands) != 1:
        raise ValueError("comparative judgment used an unauthorized tool action")
    tokens = shlex.split(commands[0])
    if tokens[:2] == ["/bin/bash", "-lc"] and len(tokens) == 3:
        tokens = shlex.split(tokens[2])
    if tokens[:2] == ["cat", "--"]:
        read_paths = tokens[2:]
    elif tokens[:1] == ["cat"]:
        read_paths = tokens[1:]
    else:
        raise ValueError("comparative judgment used an unauthorized shell command")
    if read_paths != list(allowed_paths):
        raise ValueError("comparative judgment read outside its exact file inventory")


def _validate_no_tool_events(events_path: Path) -> None:
    """Accept only lifecycle, reasoning, and final-message events."""

    lifecycle = {"thread.started", "turn.started", "turn.completed"}
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        item = event.get("item")
        if isinstance(item, dict):
            if item.get("type") not in {"reasoning", "agent_message"}:
                raise ValueError("embedded comparative judgment used a tool")
        elif event.get("type") not in lifecycle:
            raise ValueError("embedded comparative judgment emitted an unknown event")


def _collect_file_read_events(events_path: Path) -> tuple[list[str], set[str]]:
    started: dict[str, str] = {}
    completed: list[tuple[str, str]] = []
    forbidden: set[str] = set()
    lifecycle = {"thread.started", "turn.started", "turn.completed"}
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        item = event.get("item")
        if not isinstance(item, dict):
            if event.get("type") not in lifecycle:
                forbidden.add(str(event.get("type")))
            continue
        item_type = item.get("type")
        if item_type != "command_execution":
            if item_type not in {"reasoning", "agent_message"}:
                forbidden.add(str(item_type))
            continue
        if event.get("type") == "item.started":
            item_id = str(item.get("id", ""))
            if not item_id or item.get("status") != "in_progress" or item_id in started:
                forbidden.add("command_execution")
            else:
                started[item_id] = str(item.get("command", ""))
            continue
        if event.get("type") != "item.completed":
            forbidden.add(str(item_type))
            continue
        if item.get("status") != "completed" or item.get("exit_code") != 0:
            raise ValueError("comparative judgment input read did not complete")
        completed.append((str(item.get("id", "")), str(item.get("command", ""))))
    if len(started) != 1 or len(completed) != 1 or completed[0] not in started.items():
        forbidden.add("unmatched_command_execution")
    return [command for _, command in completed], forbidden


def _confined_projection(path_value: str, *, run_dir: Path) -> Path:
    path = Path(path_value).resolve()
    root = (run_dir / "comparative-file-inputs-v1").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("file-backed projection path escapes its trusted input root")
    return path


__all__ = [
    "ComparativeJudgmentAuthorization",
    "build_cross_shard_calibration_preflight",
    "load_comparative_judgment_authorization",
    "run_comparative_judgment_request",
    "run_cross_shard_calibration",
]
