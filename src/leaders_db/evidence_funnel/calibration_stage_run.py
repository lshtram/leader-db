"""Resumable model-stage adapters for the bounded calibration."""

from __future__ import annotations

from pathlib import Path

from .artifacts import ArtifactStore
from .calibration_extraction import normalize_latest_intents
from .calibration_prompts import routing_prompt, verification_prompt
from .calibration_review import reconcile_complete_reviews
from .calibration_routing import (
    normalize_routing_table,
    stage_tokens,
)
from .citation_models import LocatorIndex
from .cli_extraction import run_cli_extraction
from .config import EvidenceFunnelConfig
from .execution_resume import (
    execute_or_resume_bound_stage,
    validate_stage_resume_binding,
)
from .low_cost import EvidenceIntentBatch, RoutingDecisionBatch, SemanticReviewBatch
from .models import (
    ChunkRoutingDecision,
    DocumentSectionMap,
    EvidenceCandidate,
    SourceDescriptor,
)


def deterministic_complete_source_routing(
    *,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    question_ids: tuple[str, ...],
) -> RoutingDecisionBatch:
    """Forward every unit when the configured short-record rule applies."""

    return RoutingDecisionBatch(
        decisions=tuple(
            ChunkRoutingDecision(
                schema_version="chunk_routing_decision_v1",
                source_id=source.source_id,
                source_sha256=source.source_sha256,
                chunk_id=str(unit["chunk_id"]),
                included=True,
                relevant_question_ids=question_ids,
                relevance_strength="weak",
                explanation="Complete short source forwarded deterministically.",
            )
            for unit in units
        )
    )


def run_routing_stage(
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    questions: str,
    document_map: DocumentSectionMap,
    profiles_path: Path,
    source_root: Path,
) -> tuple[RoutingDecisionBatch, str, int]:
    """Execute or resume routing, normalizing M2.7's explicit table when needed."""

    root = source_root / "02-routing"
    prompt = routing_prompt(
        instruction=config.prompts["routing"],
        source=source,
        units=units,
        questions=questions,
        document_map=document_map.model_dump_json(indent=2),
    )
    if _has_attempt_content(root):
        validate_stage_resume_binding(
            project_root=project_root,
            config=config,
            stage="routing",
            prompt=prompt,
            output_model=RoutingDecisionBatch,
            output_dir=root,
            profiles_path=profiles_path,
        )
        try:
            return _normalize_routing(root, source, units, source_root, config)
        except ValueError:
            if _exhausted(root, config, "routing"):
                raise
    if _exhausted(root, config, "routing"):
        validate_stage_resume_binding(
            project_root=project_root,
            config=config,
            stage="routing",
            prompt=prompt,
            output_model=RoutingDecisionBatch,
            output_dir=root,
            profiles_path=profiles_path,
        )
        return _normalize_routing(root, source, units, source_root, config)
    return _execute_routing_until_valid(
        project_root=project_root,
        config=config,
        prompt=prompt,
        profiles_path=profiles_path,
        root=root,
        source=source,
        units=units,
        source_root=source_root,
    )


def _execute_routing_until_valid(
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    prompt: str,
    profiles_path: Path,
    root: Path,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    source_root: Path,
) -> tuple[RoutingDecisionBatch, str, int]:
    while True:
        execution = None
        try:
            execution = execute_or_resume_bound_stage(
                project_root=project_root,
                config=config,
                stage="routing",
                prompt=prompt,
                output_model=RoutingDecisionBatch,
                output_dir=root,
                profiles_path=profiles_path,
                defer_invalid_content_to_stage_adapter=True,
                accept_result=lambda path: _validate_routing_result(
                    path, source, units, config
                ),
            )
        except ValueError:
            if (root / "resume-completion.json").exists():
                raise
        except RuntimeError:
            pass
        if execution is not None:
            routing = RoutingDecisionBatch.model_validate_json(
                execution.output_path.read_text(encoding="utf-8")
            )
            return routing, execution.model_profile, execution.total_tokens
        try:
            return _normalize_routing(root, source, units, source_root, config)
        except ValueError:
            if _exhausted(root, config, "routing"):
                raise


def _validate_routing_result(
    path: Path,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    config: EvidenceFunnelConfig,
) -> None:
    routing = RoutingDecisionBatch.model_validate_json(path.read_text(encoding="utf-8"))
    _validate_routing_batch(routing, source, units, config)


def _validate_routing_batch(
    routing: RoutingDecisionBatch,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    config: EvidenceFunnelConfig,
) -> None:
    expected = tuple(str(item["chunk_id"]) for item in units)
    actual = tuple(item.chunk_id for item in routing.decisions)
    if actual != expected:
        raise ValueError("routing result does not exactly match supplied chunk order")
    allowed_questions = set(config.methodology_ids)
    expected_chunks = set(expected)
    for decision in routing.decisions:
        if (
            decision.source_id != source.source_id
            or decision.source_sha256 != source.source_sha256
        ):
            raise ValueError("routing result source binding mismatch")
        if not set(decision.relevant_question_ids).issubset(allowed_questions):
            raise ValueError("routing result contains an out-of-chapter question ID")
        if not set(decision.adjacent_chunk_ids).issubset(expected_chunks):
            raise ValueError("routing result contains an unknown adjacent chunk ID")


def run_extraction_stage(
    *,
    project_root: Path,
    config_path: Path,
    frozen_root: Path,
    ledger_root: Path,
    config: EvidenceFunnelConfig,
    source: SourceDescriptor,
    locator_indexes: tuple[LocatorIndex, ...],
    questions: str,
    profiles_path: Path,
    stage_root: Path,
) -> tuple[EvidenceIntentBatch, str, int]:
    """Extract through the four-action citation CLI and its validated ledger."""

    root = stage_root
    return run_cli_extraction(
        project_root=project_root,
        config_path=config_path,
        frozen_root=frozen_root,
        ledger_root=ledger_root,
        config=config,
        source=source,
        locator_indexes=locator_indexes,
        questions=questions,
        profiles_path=profiles_path,
        stage_root=root,
    )


def run_verification_stage(
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    candidates: tuple[EvidenceCandidate, ...],
    questions: str,
    profiles_path: Path,
    stage_root: Path,
) -> tuple[SemanticReviewBatch, str, int]:
    """Execute or resume fresh semantic review with strict verdict normalization."""

    root = stage_root
    prompt = verification_prompt(
        instruction=config.prompts["verification"],
        candidates=candidates,
        questions=questions,
    )
    if _has_attempt_content(root):
        validate_stage_resume_binding(
            project_root=project_root,
            config=config,
            stage="verification",
            prompt=prompt,
            output_model=SemanticReviewBatch,
            output_dir=root,
            profiles_path=profiles_path,
        )
        try:
            return _normalize_review(root, candidates)
        except ValueError:
            if _exhausted(root, config, "verification"):
                raise
    if _exhausted(root, config, "verification"):
        validate_stage_resume_binding(
            project_root=project_root,
            config=config,
            stage="verification",
            prompt=prompt,
            output_model=SemanticReviewBatch,
            output_dir=root,
            profiles_path=profiles_path,
        )
        return _normalize_review(root, candidates)
    try:
        execution = execute_or_resume_bound_stage(
            project_root=project_root,
            config=config,
            stage="verification",
            prompt=prompt,
            output_model=SemanticReviewBatch,
            output_dir=root,
            profiles_path=profiles_path,
            defer_invalid_content_to_stage_adapter=True,
        )
    except RuntimeError:
        try:
            return _normalize_review(root, candidates)
        except ValueError:
            try:
                execute_or_resume_bound_stage(
                    project_root=project_root,
                    config=config,
                    stage="verification",
                    prompt=prompt,
                    output_model=SemanticReviewBatch,
                    output_dir=root,
                    profiles_path=profiles_path,
                    defer_invalid_content_to_stage_adapter=True,
                )
            except RuntimeError:
                pass
            return _normalize_review(root, candidates)
    return (
        SemanticReviewBatch.model_validate_json(execution.output_path.read_text(encoding="utf-8")),
        execution.model_profile,
        execution.total_tokens,
    )


def _normalize_routing(
    root: Path,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    source_root: Path,
    config: EvidenceFunnelConfig,
) -> tuple[RoutingDecisionBatch, str, int]:
    chunk_ids = tuple(str(item["chunk_id"]) for item in units)
    error: ValueError | None = None
    for raw_path in reversed(sorted(root.glob("attempt-*/output.json"))):
        try:
            routing = normalize_routing_table(
                raw_path=raw_path,
                source=source,
                chunk_ids=chunk_ids,
            )
        except ValueError as exc:
            error = exc
            continue
        break
    else:
        raise error or ValueError("routing stage has no model output")
    _validate_routing_batch(routing, source, units, config)
    ArtifactStore(source_root).write_immutable(
        "02-routing/normalized-output.json",
        routing,
    )
    return routing, "minimax-content+deterministic-table-normalizer", stage_tokens(root)


def _normalize_extraction(
    root: Path,
    source: SourceDescriptor,
    routed_locators: set[str],
    config: EvidenceFunnelConfig,
) -> tuple[EvidenceIntentBatch, str, int]:
    intents = normalize_latest_intents(
        stage_root=root,
        source=source,
        routed_locators=routed_locators,
        methodology_ids=config.methodology_ids,
    )
    ArtifactStore(root).write_immutable("normalized-output.json", intents)
    return intents, "minimax-content+deterministic-intent-normalizer", stage_tokens(root)


def _normalize_review(
    root: Path,
    candidates: tuple[EvidenceCandidate, ...],
) -> tuple[SemanticReviewBatch, str, int]:
    reviews = reconcile_complete_reviews(root, candidates)
    ArtifactStore(root).write_immutable("normalized-output.json", reviews)
    return reviews, "minimax-review+deterministic-verdict-normalizer", stage_tokens(root)


def _exhausted(root: Path, config: EvidenceFunnelConfig, stage: str) -> bool:
    return (
        not (root / "resume-completion.json").exists()
        and len(tuple(root.glob("attempt-*"))) >= config.stages[stage].max_attempts
    )


def _has_attempt_content(root: Path) -> bool:
    """Return whether an immutable model handoff exists for stage adaptation."""

    return any(
        path.stat().st_size
        for pattern in ("attempt-*/output.json", "attempt-*/events.jsonl")
        for path in root.glob(pattern)
    )


__all__ = [
    "run_extraction_stage",
    "run_routing_stage",
    "run_verification_stage",
]
