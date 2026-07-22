"""Deduplicate question-level local priors for one ruler research prompt."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CompactLocalFact(BaseModel):
    """One unique local fact with all applicable methodology links."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    locator: str
    year: int
    field_key: str
    label: str
    value: Any
    value_type: str
    source_slugs: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    confidence: int | None
    warnings: tuple[str, ...]
    period_role: Literal["pre_accession", "tenure", "target"] = "target"
    candidate_methodology_ids: tuple[str, ...]
    chapter_ids: tuple[str, ...]


class CompactChapterPrior(BaseModel):
    """Chapter-local view over the global deduplicated fact register."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    methodology_ids: tuple[str, ...]
    status_counts: dict[str, int]
    fact_ids: tuple[str, ...]
    mapping_notes: tuple[str, ...]


class CompactMethodologyDisposition(BaseModel):
    """Status plus references to deduplicated missingness guidance."""

    model_config = ConfigDict(extra="forbid")

    status: str
    reason_id: str | None
    instruction_set_id: str | None


class CompactLocalPriorPackage(BaseModel):
    """Schema-light local-first package inlined for the researcher."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ruler_local_evidence_package_v3"] = (
        "ruler_local_evidence_package_v3"
    )
    source_prior_count: int
    unique_fact_count: int
    status_counts: dict[str, int]
    methodology_statuses: dict[str, str]
    methodology_dispositions: dict[str, CompactMethodologyDisposition]
    disposition_reasons: dict[str, str]
    disposition_instruction_sets: dict[str, tuple[str, ...]]
    no_evidence_methodology_ids: tuple[str, ...]
    not_applicable_methodology_ids: tuple[str, ...]
    error_methodology_ids: tuple[str, ...]
    facts: tuple[CompactLocalFact, ...]
    chapters: tuple[CompactChapterPrior, ...]


def compact_local_priors(
    local_priors: tuple[dict[str, Any], ...],
) -> CompactLocalPriorPackage:
    """Return a deterministic package without repeating facts for every lens."""

    statuses = Counter(str(item.get("status", "error")) for item in local_priors)
    fact_rows: list[dict[str, Any]] = []
    fact_indexes: dict[str, int] = {}
    chapter_methods: dict[str, list[str]] = {}
    chapter_statuses: dict[str, Counter[str]] = {}
    chapter_fact_ids: dict[str, list[str]] = {}
    chapter_mapping_notes: dict[str, list[str]] = {}
    disposition_reasons: dict[str, str] = {}
    disposition_reason_ids: dict[str, str] = {}
    instruction_sets: dict[str, tuple[str, ...]] = {}
    instruction_set_ids: dict[tuple[str, ...], str] = {}
    methodology_dispositions: dict[str, CompactMethodologyDisposition] = {}

    for prior in local_priors:
        methodology_id = str(prior.get("methodology_id", ""))
        chapter_id = methodology_id.partition(".")[0]
        status = str(prior.get("status", "error"))
        chapter_methods.setdefault(chapter_id, []).append(methodology_id)
        chapter_statuses.setdefault(chapter_id, Counter())[status] += 1
        chapter_fact_ids.setdefault(chapter_id, [])
        chapter_mapping_notes.setdefault(chapter_id, [])
        mapping_note = prior.get("mapping_note")
        if isinstance(mapping_note, str):
            _append_unique(chapter_mapping_notes[chapter_id], mapping_note)
        methodology_dispositions[methodology_id] = _build_disposition(
            prior=prior,
            status=status,
            reasons=disposition_reasons,
            reason_ids=disposition_reason_ids,
            instruction_sets=instruction_sets,
            instruction_set_ids=instruction_set_ids,
        )
        for raw_fact in prior.get("local_facts", []):
            if not isinstance(raw_fact, dict):
                continue
            normalized_fact = _normalize_fact(raw_fact)
            fact_key = _fact_key(normalized_fact)
            fact_index = fact_indexes.get(fact_key)
            if fact_index is None:
                fact_index = len(fact_rows)
                fact_indexes[fact_key] = fact_index
                fact_rows.append(
                    {
                        **normalized_fact,
                        "fact_id": f"LF{fact_index + 1:03d}",
                        "locator": f"local-prior:{methodology_id}",
                        "candidate_methodology_ids": [],
                        "chapter_ids": [],
                    }
                )
            row = fact_rows[fact_index]
            _append_unique(row["candidate_methodology_ids"], methodology_id)
            _append_unique(row["chapter_ids"], chapter_id)
            _append_unique(chapter_fact_ids[chapter_id], str(row["fact_id"]))

    chapters = tuple(
        CompactChapterPrior(
            chapter_id=chapter_id,
            methodology_ids=tuple(methodology_ids),
            status_counts=dict(chapter_statuses[chapter_id]),
            fact_ids=tuple(chapter_fact_ids[chapter_id]),
            mapping_notes=tuple(chapter_mapping_notes[chapter_id]),
        )
        for chapter_id, methodology_ids in chapter_methods.items()
    )
    facts = tuple(CompactLocalFact.model_validate(row) for row in fact_rows)
    return CompactLocalPriorPackage(
        source_prior_count=len(local_priors),
        unique_fact_count=len(facts),
        status_counts=dict(statuses),
        methodology_statuses={
            str(item.get("methodology_id")): str(item.get("status", "error"))
            for item in local_priors
        },
        methodology_dispositions=methodology_dispositions,
        disposition_reasons=disposition_reasons,
        disposition_instruction_sets=instruction_sets,
        no_evidence_methodology_ids=_methodology_ids_with_status(
            local_priors, "no_evidence_found"
        ),
        not_applicable_methodology_ids=_methodology_ids_with_status(
            local_priors, "not_applicable"
        ),
        error_methodology_ids=_methodology_ids_with_status(local_priors, "error"),
        facts=facts,
        chapters=chapters,
    )


def _fact_key(raw_fact: dict[str, Any]) -> str:
    return json.dumps(raw_fact, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_fact(raw_fact: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw_fact)
    for key in ("source_slugs", "source_observation_ids", "warnings"):
        value = normalized.get(key, [])
        if isinstance(value, (list, tuple)):
            normalized[key] = sorted({str(item) for item in value})
    return normalized


def _build_disposition(
    *,
    prior: dict[str, Any],
    status: str,
    reasons: dict[str, str],
    reason_ids: dict[str, str],
    instruction_sets: dict[str, tuple[str, ...]],
    instruction_set_ids: dict[tuple[str, ...], str],
) -> CompactMethodologyDisposition:
    reason = prior.get("missing_or_empty_reason")
    reason_id = None
    if isinstance(reason, str) and reason:
        reason_id = reason_ids.setdefault(reason, f"R{len(reason_ids) + 1:03d}")
        reasons.setdefault(reason_id, reason)
    instructions = tuple(
        str(item)
        for item in prior.get("recommended_research_instructions", [])
        if isinstance(item, str) and item
    )
    instruction_set_id = None
    if instructions:
        instruction_set_id = instruction_set_ids.setdefault(
            instructions, f"I{len(instruction_set_ids) + 1:03d}"
        )
        instruction_sets.setdefault(instruction_set_id, instructions)
    return CompactMethodologyDisposition(
        status=status,
        reason_id=reason_id,
        instruction_set_id=instruction_set_id,
    )


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _methodology_ids_with_status(
    local_priors: tuple[dict[str, Any], ...], status: str
) -> tuple[str, ...]:
    return tuple(
        str(item.get("methodology_id"))
        for item in local_priors
        if item.get("status") == status
    )


__all__ = [
    "CompactChapterPrior",
    "CompactLocalFact",
    "CompactLocalPriorPackage",
    "CompactMethodologyDisposition",
    "compact_local_priors",
]
