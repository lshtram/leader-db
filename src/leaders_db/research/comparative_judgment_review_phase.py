"""Safe embedded reviews of calibrated comparative chapter judgments."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import tiktoken
from pydantic import BaseModel, ConfigDict

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .chapter_judgment_review import (
    ChapterJudgmentReview,
    apply_review,
    codex_chapter_review_json_schema,
    validate_review,
)
from .comparative_judgment_phase import (
    ComparativeJudgmentAuthorization,
    _recover_chapter_calibration,
    _recover_initial_result,
    _request_hash,
    _validate_no_tool_events,
)
from .json_model_execution import execute_json_model
from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits


class _RawReview(BaseModel):
    model_config = ConfigDict(extra="allow")


_READER_FACING_REVIEW_SCHEMA = "comparative_judgment_review_preflight_v5"
_READER_FACING_POLICY = "reader_summary_and_exposition_v1"


def build_review_preflight(
    *,
    authorization: ComparativeJudgmentAuthorization,
    calibration_preflight_path: Path,
    approved_calibration_sha256: str,
    output_path: Path,
) -> Path:
    """Measure eight exact reviews from calibrated and first-pass judgments."""

    run_dir = authorization.run_dir
    project_root = Path.cwd()
    calibration_preflight = json.loads(calibration_preflight_path.read_text())
    if (
        _digest(calibration_preflight_path) != approved_calibration_sha256
        or calibration_preflight.get("status") != "eligible"
    ):
        raise ValueError("review source calibration preflight is not approved")
    requests = []
    for chapter in ("1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B"):
        final = run_dir / "comparative-judgments-v4" / f"{chapter}-final" / "judgment.json"
        first = [
            run_dir / "comparative-judgments-v4" / f"{chapter}-{iso3}" / "judgment.json"
            for iso3 in ("CHN", "ISR", "PRK", "RUS", "USA")
        ]
        calibration_item = next(
            item for item in calibration_preflight["requests"] if item["chapter_id"] == chapter
        )
        _recover_chapter_calibration(
            authorization=authorization,
            preflight_path=calibration_preflight_path,
            item=calibration_item,
            output_dir=final.parent,
            request_hash=calibration_item["complete_request_sha256"],
        )
        for path in first:
            payload = json.loads(
                (authorization.input_root / f"{path.parent.name}.json").read_text()
            )
            _recover_initial_result(
                authorization=authorization,
                component=path.parent.name,
                payload=payload,
                output_dir=path.parent,
                request_hash=_request_hash(payload, ()),
            )
        visible = _visible_evidence_ids(final, first)
        prompt = _prompt(chapter, final, first, visible)
        schema = codex_chapter_review_json_schema()
        _constrain_review_schema(schema, visible)
        make_strict_response_schema(schema)
        complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        requests.append(
            {
                "chapter_id": chapter,
                "prompt": prompt,
                "schema": schema,
                "complete_request_sha256": sha256(complete.encode()).hexdigest(),
                "estimated_input_tokens": len(tiktoken.get_encoding("o200k_base").encode(complete)),
                "source_judgment_sha256": _digest(final),
                "first_pass_sha256s": {path.parent.name: _digest(path) for path in first},
                "visible_evidence_ids": visible,
                "application_policy": _READER_FACING_POLICY,
            }
        )
    total = sum(item["estimated_input_tokens"] for item in requests)
    reasons = [] if total <= 800_000 else ["review_input_capacity"]
    output_path.write_text(
        json.dumps(
            {
                "schema_version": _READER_FACING_REVIEW_SCHEMA,
                "status": "eligible" if not reasons else "rejected",
                "planned_calls": 8,
                "planned_input_tokens": total,
                "required_output_capacity": 500_000,
                "budget_stop_reasons": reasons,
                "model_calls_executed": 0,
                "reservations_created": 0,
                "profile": "openai-sol-supervisor",
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "surface": "codex_subscription",
                "reasoning_effort": "high",
                "profiles_sha256": _digest(project_root / "configs/research-models.yaml"),
                "stage_budgets_sha256": _digest(
                    project_root / "configs/research-stage-budgets.yaml"
                ),
                "source_initial_preflight_sha256": authorization.preflight_sha256,
                "source_calibration_preflight_sha256": approved_calibration_sha256,
                "requests": requests,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return output_path


def run_review(
    *,
    run_dir: Path,
    project_root: Path,
    preflight_path: Path,
    approved_sha256: str,
    chapter_id: str,
) -> Path:
    """Execute one exact no-tool chapter review and apply its bounded decisions."""

    saved = json.loads(preflight_path.read_text())
    review_root, usage_name, stage_usage_name, preserve_prose, reader_exposition = (
        _review_contract(saved)
    )
    if (
        saved.get("status") != "eligible"
        or _digest(preflight_path) != approved_sha256
        or saved.get("profile") != "openai-sol-supervisor"
        or saved.get("provider") != "openai"
        or saved.get("model") != "gpt-5.6-sol"
        or saved.get("surface") != "codex_subscription"
        or saved.get("reasoning_effort") != "high"
    ):
        raise ValueError("comparative review preflight is not approved")
    matches = [item for item in saved["requests"] if item["chapter_id"] == chapter_id]
    if len(matches) != 1:
        raise ValueError("comparative review request inventory is not exact")
    item = matches[0]
    complete = item["prompt"] + json.dumps(item["schema"], ensure_ascii=False, sort_keys=True)
    request_hash = sha256(complete.encode()).hexdigest()
    if request_hash != item["complete_request_sha256"]:
        raise ValueError("comparative review request changed")
    final = run_dir / "comparative-judgments-v4" / f"{chapter_id}-final" / "judgment.json"
    if _digest(final) != item["source_judgment_sha256"]:
        raise ValueError("calibrated judgment changed before review")
    for component, digest in item["first_pass_sha256s"].items():
        path = run_dir / "comparative-judgments-v4" / component / "judgment.json"
        if _digest(path) != digest:
            raise ValueError("first-pass judgment changed before review")
    if (
        _digest(project_root / "configs/research-models.yaml") != saved["profiles_sha256"]
        or _digest(project_root / "configs/research-stage-budgets.yaml")
        != saved["stage_budgets_sha256"]
    ):
        raise ValueError("comparative review transport changed")
    output_dir = run_dir / review_root / chapter_id
    profile = load_research_model_profiles(project_root / "configs/research-models.yaml").profiles[
        "openai-sol-supervisor"
    ]
    tracker = RunUsageBudgetTracker(
        ledger_path=run_dir / usage_name,
        limits=RunUsageLimits(max_calls=8, max_input_tokens=800_000, max_output_tokens=500_000),
        config_sha256=_digest(preflight_path),
        allowed_request_sha256s=frozenset(
            request["complete_request_sha256"] for request in saved["requests"]
        ),
    )
    stage = load_stage_budget_tracker(
        project_root / "configs/research-stage-budgets.yaml",
        "chapter_judgment_review",
        ledger_path=run_dir / stage_usage_name,
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        return _recover_review(
            run_dir=run_dir,
            preflight_path=preflight_path,
            item=item,
            output_dir=output_dir,
            request_hash=request_hash,
            usage_name=usage_name,
            preserve_prose=preserve_prose,
            reader_exposition=reader_exposition,
        )
    response = execute_json_model(
        project_root,
        profile,
        item["prompt"],
        _RawReview,
        output_dir,
        budget_tracker=stage,
        request_component=chapter_id,
        reasoning_effort="high",
        call_coordinator=ModelCallCoordinator(),
        run_budget_tracker=tracker,
        response_schema=item["schema"],
    )
    _validate_no_tool_events(output_dir / "events.jsonl")
    review = ChapterJudgmentReview.model_validate(response.model_dump(mode="json"))
    return _apply_review_output(
        run_dir=run_dir,
        item=item,
        output_dir=output_dir,
        review=review,
        preserve_prose=preserve_prose,
        reader_exposition=reader_exposition,
    )


def _apply_review_output(
    *,
    run_dir: Path,
    item: dict,
    output_dir: Path,
    review: ChapterJudgmentReview,
    preserve_prose: bool,
    reader_exposition: bool,
) -> Path:
    from .chapter_judge_models import ChapterJudgmentBatch

    chapter_id = item["chapter_id"]
    if reader_exposition and review.schema_version != "chapter_judgment_review_v2":
        raise ValueError("reader exposition requires chapter judgment review v2")
    if not reader_exposition and review.schema_version != "chapter_judgment_review_v1":
        raise ValueError("historical review policy requires chapter judgment review v1")
    final = run_dir / "comparative-judgments-v4" / f"{chapter_id}-final" / "judgment.json"
    judgment = ChapterJudgmentBatch.model_validate_json(final.read_bytes())
    validate_review(
        review,
        judgment=judgment,
        source_sha256=_digest(final),
        evidence_ids_by_job={
            key: set(value) for key, value in item["visible_evidence_ids"].items()
        },
    )
    reviewed = apply_review(
        judgment,
        review,
        preserve_prose_on_retain=preserve_prose,
        apply_reader_exposition=reader_exposition,
    )
    review_path = output_dir / "review.json"
    expected_review = review.model_dump_json(indent=2, exclude_none=True) + "\n"
    if review_path.exists() and review_path.read_text() != expected_review:
        raise ValueError("saved review differs from raw output")
    review_path.write_text(expected_review)
    reviewed_path = output_dir / "reviewed-chapter-judgment.json"
    expected_reviewed = reviewed.model_dump_json(indent=2) + "\n"
    if reviewed_path.exists() and reviewed_path.read_text() != expected_reviewed:
        raise ValueError("saved reviewed judgment differs from reconstructed output")
    reviewed_path.write_text(expected_reviewed)
    return reviewed_path


def _recover_review(
    *,
    run_dir: Path,
    preflight_path: Path,
    item: dict,
    output_dir: Path,
    request_hash: str,
    usage_name: str,
    preserve_prose: bool,
    reader_exposition: bool,
) -> Path:
    if (output_dir / "prompt.txt").read_text() != item["prompt"]:
        raise ValueError("saved review prompt changed")
    if json.loads((output_dir / "schema.json").read_text()) != item["schema"]:
        raise ValueError("saved review schema changed")
    _validate_no_tool_events(output_dir / "events.jsonl")
    usage = json.loads((run_dir / usage_name).read_text())
    completed = [
        row
        for row in usage
        if row.get("status") == "completed" and row.get("request_sha256") == request_hash
    ]
    if len(completed) != 1 or completed[0].get("config_sha256") != _digest(preflight_path):
        raise ValueError("review recovery lacks one completed reservation")
    raw = _RawReview.model_validate_json((output_dir / "output.json").read_bytes())
    review = ChapterJudgmentReview.model_validate(raw.model_dump(mode="json"))
    return _apply_review_output(
        run_dir=run_dir,
        item=item,
        output_dir=output_dir,
        review=review,
        preserve_prose=preserve_prose,
        reader_exposition=reader_exposition,
    )


def _review_contract(saved: dict) -> tuple[str, str, str, bool, bool]:
    schema_version = saved.get("schema_version")
    if schema_version == "comparative_judgment_review_preflight_v3":
        if any("application_policy" in item for item in saved.get("requests", ())):
            raise ValueError("historical review preflight cannot select a prose policy")
        return (
            "comparative-judgment-reviews-v3",
            "comparative-judgment-review-v3-usage.json",
            "comparative-judgment-review-v3-stage-usage.json",
            False,
            False,
        )
    if schema_version == "comparative_judgment_review_preflight_v4":
        requests = saved.get("requests", ())
        if not requests or any(
            item.get("application_policy")
            != "preserve_calibrated_prose_on_retain_v1"
            for item in requests
        ):
            raise ValueError("reader-facing review preflight has an unknown application policy")
        return (
            "comparative-judgment-reviews-v4",
            "comparative-judgment-review-v4-usage.json",
            "comparative-judgment-review-v4-stage-usage.json",
            True,
            False,
        )
    if schema_version == _READER_FACING_REVIEW_SCHEMA:
        requests = saved.get("requests", ())
        if not requests or any(
            item.get("application_policy") != _READER_FACING_POLICY for item in requests
        ):
            raise ValueError("reader-facing review preflight has an unknown application policy")
        return (
            "comparative-judgment-reviews-v5",
            "comparative-judgment-review-v5-usage.json",
            "comparative-judgment-review-v5-stage-usage.json",
            False,
            True,
        )
    raise ValueError("unsupported comparative review preflight schema")


def _prompt(chapter: str, final: Path, first: list[Path], visible: dict[str, list[str]]) -> str:
    return (
        f"Act as the independent final reviewer for Leaders Database chapter {chapter}. "
        "Use only the embedded calibrated judgment and its five trusted evidence-reading first "
        "passes. Do not browse, use tools, or add facts. Test attribution, internal evidence "
        "references, confidence, absolute anchors, and five-ruler ordering. Retain each score or "
        "change it by at most one point in half-point increments. Preserve the numeric result when "
        "it remains justified, but rewrite every public explanation. Provide reader_summary as one "
        "short paragraph stating the score and central reason. Provide reader_exposition as four "
        "to seven plain-language paragraphs for a reader unfamiliar with the country: establish "
        "the 2023 setting, describe the important events and affected people, explain the ruler's "
        "decisions and omissions, and connect those facts to the score. Distinguish conditions the "
        "ruler inherited from actions the ruler personally directed, supported, tolerated, "
        "resisted, or failed to correct. Do not credit the ruler for a country's institutions as "
        "if the ruler created them. Also do not ignore the real limits those institutions placed "
        "on the ruler. Describe attempts to weaken courts, elections, protest, media, or civil "
        "society as ruler conduct, while avoiding speculation about what the ruler would have done "
        "without those constraints. Use complete sentences and define unfamiliar institutions or "
        "events. Evidence IDs belong only in supporting_evidence_ids; never place them in either "
        "reader-facing text field. Return exactly one decision per ruler under "
        "chapter_judgment_review_v2. Source SHA-256: "
        f"{_digest(final)}. Use only the following per-ruler supporting evidence IDs: "
        f"{json.dumps(visible, sort_keys=True)}.\n\nCALIBRATED:\n{final.read_text()}"
        "\n\nFIRST PASSES:\n"
        + json.dumps([json.loads(path.read_text()) for path in first], indent=2, sort_keys=True)
    )


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _visible_evidence_ids(final: Path, first: list[Path]) -> dict[str, list[str]]:
    from .chapter_judge_models import ChapterJudgmentBatch

    routed: dict[str, set[str]] = {}
    for path in (final, *first):
        batch = ChapterJudgmentBatch.model_validate_json(path.read_bytes())
        for evaluation in batch.evaluations:
            ids = {
                reference.evidence_id
                for field in (
                    evaluation.decisive_positive_evidence,
                    evaluation.decisive_negative_evidence,
                    evaluation.contrary_evidence,
                )
                for reference in field
            }
            ids.update(
                evidence_id
                for finding in evaluation.bias_assessment.material_biases
                for evidence_id in finding.supporting_evidence_ids
            )
            routed.setdefault(evaluation.dossier_job_key, set()).update(ids)
    return {key: sorted(value) for key, value in sorted(routed.items())}


def _constrain_review_schema(schema: dict, visible: dict[str, list[str]]) -> None:
    schema["properties"]["schema_version"] = {
        "type": "string",
        "const": "chapter_judgment_review_v2",
    }
    decision = schema["$defs"]["JudgmentReviewDecision"]
    decision["properties"]["dossier_job_key"] = {
        "type": "string",
        "enum": list(visible),
    }
    decision["properties"]["supporting_evidence_ids"]["items"] = {
        "type": "string",
        "enum": sorted({item for values in visible.values() for item in values}),
    }
    for field_name in ("reader_summary", "reader_exposition"):
        decision["properties"][field_name] = {"type": "string", "minLength": 1}
    decision["properties"]["reader_summary"]["pattern"] = r"^[^\r\n]+$"


__all__ = ["build_review_preflight", "run_review"]
