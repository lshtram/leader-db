"""Stable zero-call barrier for unresolved writer evidence requests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

import tiktoken

from .chapter_analysis_models import ResolvedChapterAnalysis
from .control_flow import QuestionReviewExperimentPolicy
from .model_call_budget import StageBudget
from .model_profiles import ResearchModelProfile
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import (
    ChapterQuestionPhaseManifest,
    QuestionReviewReopenStopManifest,
    QuestionUnavailableArtifact,
    UnresolvedQuestionReopen,
)
from .question_packet_prompts import QuestionPacketPrompts
from .question_packet_quality import (
    _blind_labels,
    _review_prompt,
    build_blind_review_response_schema,
)
from .question_packet_writer import DiagnosticQuestionAnswer

_SNAPSHOT_CAPABILITY = object()


@dataclass(frozen=True)
class QuestionReviewInputSnapshot:
    writing_dir: Path
    _writing_bytes: bytes
    writing_manifest_sha256: str
    _answer_bytes: Mapping[str, bytes]
    _capability: object

    @property
    def writing(self) -> ChapterQuestionPhaseManifest:
        return ChapterQuestionPhaseManifest.model_validate_json(self._writing_bytes)

    @property
    def answers(self) -> Mapping[str, DiagnosticQuestionAnswer]:
        return MappingProxyType(
            {
                question_id: DiagnosticQuestionAnswer.model_validate_json(payload)
                for question_id, payload in self._answer_bytes.items()
            }
        )


def load_review_input_snapshot(
    writing_dir: Path, validated_writing: ChapterQuestionPhaseManifest
) -> QuestionReviewInputSnapshot:
    """Read each trusted writing artifact once and bind its parsed in-memory value."""

    manifest_bytes = (writing_dir / "writing-manifest.json").read_bytes()
    if ChapterQuestionPhaseManifest.model_validate_json(manifest_bytes) != validated_writing:
        raise ValueError("writing manifest changed before review preflight")
    answer_bytes_by_id = {}
    for artifact in validated_writing.artifacts:
        answer_path = _inside(writing_dir, artifact.artifact_path)
        answer_bytes = answer_path.read_bytes()
        if sha256(answer_bytes).hexdigest() != artifact.artifact_sha256:
            raise ValueError("written question answer changed before review preflight")
        if artifact.status == "unavailable":
            unavailable = QuestionUnavailableArtifact.model_validate_json(answer_bytes)
            if unavailable.question_id != artifact.question_id:
                raise ValueError("unavailable question artifact identity differs")
        else:
            DiagnosticQuestionAnswer.model_validate_json(answer_bytes)
            answer_bytes_by_id[artifact.question_id] = answer_bytes
    return QuestionReviewInputSnapshot(
        writing_dir=writing_dir,
        _writing_bytes=manifest_bytes,
        writing_manifest_sha256=sha256(manifest_bytes).hexdigest(),
        _answer_bytes=MappingProxyType(answer_bytes_by_id),
        _capability=_SNAPSHOT_CAPABILITY,
    )


def require_trusted_snapshot(snapshot: QuestionReviewInputSnapshot) -> None:
    if snapshot._capability is not _SNAPSHOT_CAPABILITY:
        raise ValueError("question review input snapshot was not issued by the trusted loader")


def stop_for_reopen_requests(
    output_dir: Path, snapshots: tuple[QuestionReviewInputSnapshot, ...]
) -> None:
    """Persist a zero-call stop and reject review when writing left material gaps."""

    unresolved = tuple(
        UnresolvedQuestionReopen(
            chapter_id=snapshot.writing.chapter_id,
            question_id=question_id,
            answer_artifact_sha256=next(
                item.artifact_sha256
                for item in snapshot.writing.artifacts
                if item.question_id == question_id
            ),
            evidence_ids=tuple(item.evidence_id for item in answer.reopen_requests),
        )
        for snapshot in snapshots
        for question_id, answer in snapshot.answers.items()
        if answer.reopen_requests
    )
    if not unresolved:
        return
    manifest = QuestionReviewReopenStopManifest(
        writing_manifest_sha256s={
            snapshot.writing.chapter_id: snapshot.writing_manifest_sha256
            for snapshot in snapshots
        },
        unresolved=unresolved,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "reopen-stop.json").open("x", encoding="utf-8") as handle:
        handle.write(manifest.model_dump_json(indent=2) + "\n")
    raise RuntimeError(
        f"question review stopped before model calls: {len(unresolved)} answers "
        "contain unresolved writer reopen requests"
    )


def build_question_review_preflight_manifest(
    *,
    run_dir: Path,
    packages: tuple[ChapterQuestionEvidencePackage, ...],
    approved_analyses: Mapping[str, ResolvedChapterAnalysis],
    snapshots: tuple[QuestionReviewInputSnapshot, ...],
    prompts: QuestionPacketPrompts,
    profile_name: str,
    profile: ResearchModelProfile,
    reasoning_effort: str,
    stage_budget: StageBudget,
    run_limits: Mapping[str, int],
    run_ledger: tuple[dict, ...],
    input_bindings: Mapping[str, str],
    output_path: Path,
    downstream_roots: tuple[Path, ...],
    experiment_policy: QuestionReviewExperimentPolicy | None = None,
) -> Path:
    """Measure and hash-bind every complete blind-review request without reservations."""

    _require_unused_roots(downstream_roots)
    if profile.provider != "openai" or profile.execution_surface != "codex":
        raise ValueError("question review preflight requires the OpenAI Codex subscription")
    if set(approved_analyses) != {package.chapter_id for package in packages}:
        raise ValueError("approved analyses must match review packages exactly")
    snapshots_by_chapter = {item.writing.chapter_id: item for item in snapshots}
    if set(snapshots_by_chapter) != {package.chapter_id for package in packages}:
        raise ValueError("trusted snapshots must match review packages exactly")
    carries_reopens = (
        experiment_policy is not None
        and experiment_policy.writer_reopen_behavior
        == "carry_to_review_and_bounded_correction"
    )
    raw_reopen_fields = _validate_snapshots(
        run_dir, snapshots, allow_reopen_handoff=carries_reopens
    )
    normalized_reopens = sum(
        len(answer.reopen_requests) for item in snapshots for answer in item.answers.values()
    )
    if normalized_reopens and not carries_reopens:
        raise ValueError("question review preflight found normalized reopen requests")

    encoding = tiktoken.get_encoding("o200k_base")
    requests = []
    chapter_totals: dict[str, dict[str, int]] = {}
    for package in packages:
        chapter_id = package.chapter_id
        snapshot = snapshots_by_chapter[chapter_id]
        analysis = approved_analyses[chapter_id]
        approved_by_id = {
            answer.question_id: answer.model_dump(mode="json") for answer in analysis.answers
        }
        packets = {packet.question_id: packet for packet in package.packets}
        chapter_requests = []
        for written in snapshot.writing.artifacts:
            if written.status == "unavailable":
                continue
            question_id = written.question_id
            packet = packets[question_id]
            experimental = snapshot.answers[question_id].model_dump(mode="json")
            labels = _blind_labels(question_id)
            candidates = {
                label: approved_by_id[question_id] if source == "approved" else experimental
                for label, source in labels.items()
            }
            prompt = _review_prompt(packet, candidates, prompts.review_template)
            schema = build_blind_review_response_schema(packet)
            schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
            complete = prompt + schema_text
            measurement = {
                "chapter_id": chapter_id,
                "question_id": question_id,
                "request_characters": len(complete),
                "prompt_characters": len(prompt),
                "response_schema_characters": len(schema_text),
                "estimated_input_tokens": len(encoding.encode(complete)),
                "prompt_sha256": sha256(prompt.encode()).hexdigest(),
                "response_schema_sha256": _payload_hash(schema),
                "complete_request_sha256": sha256(complete.encode()).hexdigest(),
                "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
                "approved_answer_sha256": _payload_hash(approved_by_id[question_id]),
                "experimental_answer_sha256": _payload_hash(experimental),
                "randomization": labels,
            }
            chapter_requests.append(measurement)
            requests.append(measurement)
        chapter_totals[chapter_id] = {
            "calls": len(chapter_requests),
            "request_characters": sum(item["request_characters"] for item in chapter_requests),
            "estimated_input_tokens": sum(
                item["estimated_input_tokens"] for item in chapter_requests
            ),
        }

    budget_stop_reasons = _validate_request_inventory(
        requests,
        chapter_totals,
        stage_budget,
        expected_chapters=tuple(package.chapter_id for package in packages),
    )
    observed = _observed_usage(run_ledger)
    remaining = {
        "calls": int(run_limits["max_calls"]) - observed["calls"],
        "input_tokens": int(run_limits["max_input_tokens"]) - observed["input_tokens"],
        "output_tokens": int(run_limits["max_output_tokens"]) - observed["output_tokens"],
    }
    planned_input = sum(item["estimated_input_tokens"] for item in requests)
    output_allowance = stage_budget.output_allowance(profile.model)
    required_output_capacity = len(requests) * output_allowance
    eligible = (
        not budget_stop_reasons
        and len(requests) <= remaining["calls"]
        and planned_input <= remaining["input_tokens"]
        and required_output_capacity <= remaining["output_tokens"]
    )
    payload = {
        "schema_version": "question_review_preflight_v1",
        "status": "eligible" if eligible else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "api_key_used": False,
        "provider": profile.provider,
        "model": profile.model,
        "profile": profile_name,
        "reasoning_effort": reasoning_effort,
        "surface": "codex_subscription",
        "planned_calls": len(requests),
        "planned_input_tokens": planned_input,
        "planned_request_characters": sum(item["request_characters"] for item in requests),
        "maximum_output_tokens_per_call": output_allowance,
        "required_output_capacity": required_output_capacity,
        "review_output_token_quota": remaining["output_tokens"],
        "safe_concurrency": min(
            len(packages), remaining["output_tokens"] // output_allowance
        ),
        "run_limits": dict(run_limits),
        "observed_prior_usage": observed,
        "remaining_capacity": remaining,
        "writing_artifacts_trusted_reloaded": len(requests),
        "raw_writer_outputs_checked": len(requests),
        "raw_writer_outputs_with_reopen_field": raw_reopen_fields,
        "normalized_reopen_request_count": normalized_reopens,
        "writer_reopen_behavior": (
            experiment_policy.writer_reopen_behavior if experiment_policy is not None else None
        ),
        "downstream_roots_unused": [str(path) for path in downstream_roots],
        "input_bindings": dict(input_bindings),
        "writing_manifest_sha256s": {
            item.writing.chapter_id: item.writing_manifest_sha256 for item in snapshots
        },
        "chapter_totals": chapter_totals,
        "budget_stop_reasons": budget_stop_reasons,
        "requests": requests,
        "stop_reason": (
            None
            if eligible
            else "complete review request inventory exceeds configured or remaining capacity"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def _validate_request_inventory(
    requests: list[dict],
    chapter_totals: Mapping[str, Mapping[str, int]],
    budget: StageBudget,
    *,
    expected_chapters: tuple[str, ...],
) -> list[str]:
    canonical = tuple(f"{number}B" for number in range(1, 9))
    if (
        not expected_chapters
        or expected_chapters
        != tuple(chapter for chapter in canonical if chapter in set(expected_chapters))
        or tuple(chapter_totals) != expected_chapters
    ):
        raise ValueError("question review preflight requires exact ordered chapters")
    if any(not 0 <= total["calls"] <= 10 for total in chapter_totals.values()):
        raise ValueError("question review preflight chapter inventory is invalid")
    reasons = []
    for item in requests:
        if item["request_characters"] > budget.max_request_characters:
            reasons.append(f"{item['question_id']}:request_characters")
        if item["estimated_input_tokens"] > budget.max_request_input_tokens:
            reasons.append(f"{item['question_id']}:request_input_tokens")
    for chapter_id, total in chapter_totals.items():
        if total["calls"] > budget.max_calls:
            reasons.append(f"{chapter_id}:stage_call_count")
        if total["estimated_input_tokens"] > budget.max_stage_input_tokens:
            reasons.append(f"{chapter_id}:stage_input_tokens")
    return reasons


def _validate_snapshots(
    run_dir: Path,
    snapshots: tuple[QuestionReviewInputSnapshot, ...],
    *,
    allow_reopen_handoff: bool,
) -> int:
    raw_reopen_fields = 0
    for snapshot in snapshots:
        require_trusted_snapshot(snapshot)
        if not snapshot.writing_dir.resolve().is_relative_to(run_dir.resolve()):
            raise ValueError("trusted writing snapshot is outside the integrated run")
        for artifact in snapshot.writing.artifacts:
            if artifact.status == "unavailable":
                continue
            raw_path = _inside(snapshot.writing_dir, artifact.artifact_path).parent / "output.json"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            if "reopen_requests" in raw:
                raw_reopen_fields += 1
                if raw["reopen_requests"] and not allow_reopen_handoff:
                    raise ValueError("raw writer output contains unresolved reopen requests")
    return raw_reopen_fields


def _observed_usage(ledger: tuple[dict, ...]) -> dict[str, int]:
    active = [item for item in ledger if item.get("status") in {"completed", "reserved"}]
    if any(item.get("status") != "completed" for item in active):
        raise ValueError("question review preflight requires a fully settled run ledger")
    return {
        "calls": len(active),
        "input_tokens": sum(int(item["observed_input_tokens"]) for item in active),
        "cached_input_tokens": sum(
            int(item.get("observed_cached_input_tokens", 0)) for item in active
        ),
        "output_tokens": sum(int(item["observed_output_tokens"]) for item in active),
        "reasoning_output_tokens": sum(
            int(item.get("observed_reasoning_output_tokens", 0)) for item in active
        ),
    }


def _require_unused_roots(roots: tuple[Path, ...]) -> None:
    used = [str(path) for path in roots if path.exists() and any(path.iterdir())]
    if used:
        raise ValueError(f"downstream output roots are already in use: {', '.join(used)}")


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _inside(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError("chapter artifact path escapes its phase directory")
    return path


__all__ = [
    "QuestionReviewInputSnapshot",
    "build_question_review_preflight_manifest",
    "load_review_input_snapshot",
    "require_trusted_snapshot",
    "stop_for_reopen_requests",
]
