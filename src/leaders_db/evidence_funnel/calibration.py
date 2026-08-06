"""Bounded end-to-end execution for the frozen three-source calibration gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .artifacts import ArtifactStore
from .calibration_prompts import question_text
from .calibration_routing_stage import run_batched_routing
from .calibration_stage_run import (
    deterministic_complete_source_routing,
    run_extraction_stage,
    run_verification_stage,
)
from .calibration_validation import (
    mechanical_failures,
    validate_intents,
    validate_reviews,
    validate_routing,
)
from .citation_ledger import CitationLedger
from .citation_models import EvidenceIntent
from .config import EvidenceFunnelConfig
from .ingest import FrozenExtraction
from .models import (
    DocumentSectionMap,
    EvidenceCandidate,
    SectionBoundary,
    SourceDescriptor,
)

_Item = TypeVar("_Item")


class CalibrationSourceResult(BaseModel):
    """Traceable outcome for one frozen calibration source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    mapped_sections: int = Field(ge=0)
    routed_units: int = Field(ge=0)
    excluded_units: int = Field(ge=0)
    extracted_intents: int = Field(ge=0)
    confirmed_candidates: int = Field(ge=0)
    accepted_candidates: int = Field(ge=0)
    rejected_candidates: int = Field(ge=0)
    escalated_candidates: int = Field(ge=0)
    model_profiles: dict[str, str]
    total_model_tokens: int = Field(ge=0)


class CalibrationResult(BaseModel):
    """Aggregate result of the experimental, non-publication calibration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "evidence_funnel_calibration_result_v1"
    experimental_non_publication: bool = True
    source_results: tuple[CalibrationSourceResult, ...]
    accepted_evidence: tuple[EvidenceCandidate, ...]
    rejected_evidence_ids: tuple[str, ...]
    escalated_evidence_ids: tuple[str, ...]
    question_coverage: dict[str, int]
    passed_mechanical_gate: bool
    gate_failures: tuple[str, ...]
    total_model_tokens: int = Field(ge=0)


def run_calibration(
    *,
    project_root: Path,
    config_path: Path,
    frozen_root: Path,
    config: EvidenceFunnelConfig,
    extractions: tuple[FrozenExtraction, ...],
    sources: dict[str, SourceDescriptor],
    questions_payload: object,
    profiles_path: Path,
    output_root: Path,
    document_ids: tuple[str, ...] | None = None,
) -> CalibrationResult:
    """Run map, route, extract, bind, and fresh-review over a configured source set."""

    requested_ids = (
        config.calibration_document_ids if document_ids is None else document_ids
    )
    if not requested_ids:
        raise ValueError("requested document set cannot be empty")
    if not set(requested_ids).issubset(config.frozen_document_ids):
        raise ValueError("requested documents must belong to the frozen pack")
    selected = tuple(
        extraction
        for source_id in requested_ids
        for extraction in extractions
        if extraction.source_id == source_id
    )
    if tuple(item.source_id for item in selected) != requested_ids:
        raise ValueError("requested extraction set is incomplete")
    store = ArtifactStore(output_root)
    ledger = CitationLedger(
        root=output_root / "citation-ledger",
        extractions=selected,
        sources=sources,
        segment_characters=config.citations.segment_characters,
        maximum_attempts=config.citations.maximum_binding_attempts,
    )
    questions = question_text(questions_payload, config.methodology_ids)
    source_results: list[CalibrationSourceResult] = []
    accepted: list[EvidenceCandidate] = []
    rejected: list[str] = []
    escalated: list[str] = []
    for extraction in selected:
        result, source_accepted, source_rejected, source_escalated = _run_source(
            project_root=project_root,
            config_path=config_path,
            frozen_root=frozen_root,
            config=config,
            extraction=extraction,
            source=sources[extraction.source_id],
            questions=questions,
            profiles_path=profiles_path,
            output_root=output_root,
            ledger=ledger,
        )
        source_results.append(result)
        accepted.extend(source_accepted)
        rejected.extend(source_rejected)
        escalated.extend(source_escalated)
    coverage = {
        question_id: sum(question_id in item.question_ids for item in accepted)
        for question_id in config.methodology_ids
    }
    failures = mechanical_failures(
        config=config,
        accepted=accepted,
        rejected=rejected,
        escalated=escalated,
        coverage=coverage,
    )
    result = CalibrationResult(
        source_results=tuple(source_results),
        accepted_evidence=tuple(accepted),
        rejected_evidence_ids=tuple(rejected),
        escalated_evidence_ids=tuple(escalated),
        question_coverage=coverage,
        passed_mechanical_gate=not failures,
        gate_failures=tuple(failures),
        total_model_tokens=sum(item.total_model_tokens for item in source_results),
    )
    store.write_immutable("calibration-result.json", result)
    return result


def _run_source(
    *,
    project_root: Path,
    config_path: Path,
    frozen_root: Path,
    config: EvidenceFunnelConfig,
    extraction: FrozenExtraction,
    source: SourceDescriptor,
    questions: str,
    profiles_path: Path,
    output_root: Path,
    ledger: CitationLedger,
) -> tuple[
    CalibrationSourceResult,
    list[EvidenceCandidate],
    list[str],
    list[str],
]:
    source_root = output_root / "sources" / source.source_id
    units = tuple(
        {
            "chunk_id": f"U{unit.unit:04d}",
            "locator": unit.locator,
            "text": unit.text,
        }
        for unit in extraction.units
    )
    document_map = _deterministic_navigation_map(source, extraction)
    ArtifactStore(source_root).write_immutable(
        "01-mapping/deterministic-map.json",
        document_map,
    )
    mapping_profile = "deterministic-frozen-unit-map-v1"
    profiles = {"mapping": mapping_profile}
    total_tokens = 0
    source_tokens = sum(len(str(unit["text"]).split()) for unit in units)
    if source_tokens <= config.routing.short_record_max_tokens:
        routing = deterministic_complete_source_routing(
            source=source,
            units=units,
            question_ids=config.methodology_ids,
        )
        profiles["routing"] = "deterministic-complete-short-source-v1"
        routing_tokens = 0
        ArtifactStore(source_root).write_immutable(
            "02-routing/deterministic-routing.json",
            routing,
        )
    else:
        routing, profiles["routing"], routing_tokens = run_batched_routing(
            project_root=project_root,
            config=config,
            source=source,
            units=units,
            questions=questions,
            document_map=document_map,
            profiles_path=profiles_path,
            source_root=source_root,
        )
    total_tokens += routing_tokens
    validate_routing(routing, units)
    included_locators = _included_locators(
        units,
        frozenset(item.chunk_id for item in routing.decisions if item.included),
    )
    indexes = tuple(
        ledger.index_locator(source.source_id, locator)
        for locator in included_locators
    )
    intent_items = []
    for batch_number, index_batch in enumerate(
        _batches(indexes, config.routing.extraction_batch_max_units),
        start=1,
    ):
        batch_locators = {item.locator for item in index_batch}
        intents, profile, extraction_tokens = run_extraction_stage(
            project_root=project_root,
            config_path=config_path,
            frozen_root=frozen_root,
            ledger_root=(
                source_root / "03-extraction" / f"batch-{batch_number:03d}" / "ledger"
            ),
            config=config,
            source=source,
            locator_indexes=index_batch,
            questions=questions,
            profiles_path=profiles_path,
            stage_root=source_root / "03-extraction" / f"batch-{batch_number:03d}",
        )
        profiles[f"extraction_{batch_number:03d}"] = profile
        total_tokens += extraction_tokens
        validate_intents(intents, batch_locators, source)
        intent_items.extend(_rebase_intents(intents.intents, len(intent_items)))
    candidates = tuple(ledger.bind_and_confirm(intent) for intent in intent_items)
    review_items = []
    for batch_number, candidate_batch in enumerate(
        _batches(candidates, config.verification.batch_max_candidates),
        start=1,
    ):
        reviews, profile, verification_tokens = run_verification_stage(
            project_root=project_root,
            config=config,
            candidates=candidate_batch,
            questions=questions,
            profiles_path=profiles_path,
            stage_root=source_root / "04-verification" / f"batch-{batch_number:03d}",
        )
        profiles[f"verification_{batch_number:03d}"] = profile
        total_tokens += verification_tokens
        validate_reviews(reviews, candidate_batch)
        review_items.extend(reviews.reviews)
    reviews_by_id = {item.evidence_id: item for item in review_items}
    accepted = [
        item.model_copy(
            update={
                "verification_status": "accepted",
                "verification_notes": (reviews_by_id[item.evidence_id].explanation,),
            }
        )
        for item in candidates
        if reviews_by_id[item.evidence_id].status == "accepted"
    ]
    rejected = [
        item.evidence_id
        for item in candidates
        if reviews_by_id[item.evidence_id].status == "rejected"
    ]
    escalated = [
        item.evidence_id
        for item in candidates
        if reviews_by_id[item.evidence_id].status == "escalated"
    ]
    result = CalibrationSourceResult(
        source_id=source.source_id,
        mapped_sections=len(document_map.sections),
        routed_units=len(included_locators),
        excluded_units=len(units) - len(included_locators),
        extracted_intents=len(intent_items),
        confirmed_candidates=len(candidates),
        accepted_candidates=len(accepted),
        rejected_candidates=len(rejected),
        escalated_candidates=len(escalated),
        model_profiles=profiles,
        total_model_tokens=total_tokens,
    )
    return result, accepted, rejected, escalated


def _batches(
    items: tuple[_Item, ...],
    maximum: int,
) -> tuple[tuple[_Item, ...], ...]:
    """Split an immutable sequence into deterministic bounded batches."""

    return tuple(
        items[start : start + maximum]
        for start in range(0, len(items), maximum)
    )


def _included_locators(
    units: tuple[dict[str, object], ...],
    included_chunk_ids: frozenset[str],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(item["locator"])
            for item in units
            if item["chunk_id"] in included_chunk_ids
        )
    )


def _rebase_intents(
    intents: tuple[EvidenceIntent, ...],
    prior_count: int,
) -> tuple[EvidenceIntent, ...]:
    """Give batched source intents globally unique sequential draft IDs."""

    return tuple(
        intent.model_copy(update={"draft_id": f"D{prior_count + offset:04d}"})
        for offset, intent in enumerate(intents, start=1)
    )


def load_questions(path: Path) -> Any:
    """Load the frozen question payload used by every model stage."""

    return json.loads(path.read_text(encoding="utf-8"))


def _deterministic_navigation_map(
    source: SourceDescriptor,
    extraction: FrozenExtraction,
) -> DocumentSectionMap:
    return DocumentSectionMap(
        schema_version="document_section_map_v1",
        source=source,
        deterministic_complete_source_forward=True,
        sections=tuple(
            SectionBoundary(
                section_id=f"U{unit.unit:04d}",
                start_locator=unit.locator,
                end_locator=unit.locator,
                heading=f"Frozen extraction unit {unit.unit}",
                reading_priority="medium",
            )
            for unit in extraction.units
        ),
        generated_by="deterministic-frozen-unit-map-v1",
    )


__all__ = [
    "CalibrationResult",
    "CalibrationSourceResult",
    "load_questions",
    "run_calibration",
]
