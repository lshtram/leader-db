"""Deduplicate question-level local priors for one ruler research prompt."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .local_longitudinal import LocalLongitudinalSignal, derive_longitudinal_signals
from .local_prior_schema import LocalPriorFact


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
    confidence: int | None = None
    warnings: tuple[str, ...]
    period_role: Literal[
        "pre_accession", "tenure", "interregnum", "target", "post_target"
    ] = "target"
    ruler_in_office: bool | None = None
    unit: str | None = None
    scale: str | None = None
    uncertainty: dict[str, Any] | None = None
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

    schema_version: Literal["ruler_local_evidence_package_v4"] = "ruler_local_evidence_package_v4"
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
    longitudinal_signals: tuple[LocalLongitudinalSignal, ...]
    chapters: tuple[CompactChapterPrior, ...]


class JudgeLocalEvidencePackage(BaseModel):
    """Parent-built chapter-local evidence supplied directly to the judge."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ruler_local_judge_package_v1"] = (
        "ruler_local_judge_package_v1"
    )
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    methodology_ids: tuple[str, ...] = Field(min_length=10, max_length=10)
    methodology_statuses: dict[str, str]
    facts: tuple[CompactLocalFact, ...]
    facts_included: int = Field(ge=0)
    facts_omitted: int = Field(ge=0)
    fact_selection: str
    longitudinal_signals: tuple[LocalLongitudinalSignal, ...]
    mapping_notes: tuple[str, ...]
    attribution_policy: str = (
        "Local facts and derived signals are country-level structured context. "
        "They establish ruler credit or blame only when separate cited evidence "
        "supports attribution."
    )

    @model_validator(mode="after")
    def _validate_local_package(self) -> JudgeLocalEvidencePackage:
        expected = tuple(f"{self.chapter_id}.{index}" for index in range(1, 11))
        if self.methodology_ids != expected:
            raise ValueError(
                "judge local evidence must contain all ten chapter lenses in order"
            )
        if set(self.methodology_statuses) != set(expected):
            raise ValueError(
                "judge local evidence statuses must cover the complete chapter"
            )
        if self.facts_included != len(self.facts):
            raise ValueError("judge local evidence fact count does not reconcile")
        if any(
            self.chapter_id not in fact.chapter_ids
            or not set(fact.candidate_methodology_ids).intersection(expected)
            for fact in self.facts
        ):
            raise ValueError("judge local evidence fact is routed outside the chapter")
        return self


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
    signal_inputs = [
        {key: value for key, value in row.items() if key in LocalPriorFact.model_fields}
        for row in fact_rows
    ]
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
        no_evidence_methodology_ids=_methodology_ids_with_status(local_priors, "no_evidence_found"),
        not_applicable_methodology_ids=_methodology_ids_with_status(local_priors, "not_applicable"),
        error_methodology_ids=_methodology_ids_with_status(local_priors, "error"),
        facts=facts,
        longitudinal_signals=derive_longitudinal_signals(signal_inputs),
        chapters=chapters,
    )


def summarize_local_priors_for_formatter(
    local_priors: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Return the disposition index needed by the no-search formatter.

    Research receives the complete compact package. The formatter receives the
    completed notebook, whose manifest already records every accepted local fact,
    while the parent deterministically restores the full hashed prior provenance.
    Repeating every raw yearly fact here consumes output room without adding a
    formatting decision.
    """

    package = compact_local_priors(local_priors)
    return {
        "schema_version": package.schema_version,
        "source_prior_count": package.source_prior_count,
        "unique_fact_count": package.unique_fact_count,
        "status_counts": package.status_counts,
        "methodology_statuses": package.methodology_statuses,
        "methodology_dispositions": {
            key: value.model_dump(mode="json")
            for key, value in package.methodology_dispositions.items()
        },
        "disposition_reasons": package.disposition_reasons,
        "disposition_instruction_sets": package.disposition_instruction_sets,
        "no_evidence_methodology_ids": package.no_evidence_methodology_ids,
        "not_applicable_methodology_ids": package.not_applicable_methodology_ids,
        "error_methodology_ids": package.error_methodology_ids,
        "chapters": [
            {
                "chapter_id": chapter.chapter_id,
                "methodology_ids": chapter.methodology_ids,
                "status_counts": chapter.status_counts,
                "unique_fact_count": len(chapter.fact_ids),
                "mapping_notes": chapter.mapping_notes,
            }
            for chapter in package.chapters
        ],
        "fact_payload": "omitted_after_research_use_parent_restores_hashed_provenance",
    }


def summarize_local_priors_for_research(
    local_priors: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Bound a large time-series package while retaining audited decision points."""

    package = compact_local_priors(local_priors)
    selected_ids = _research_fact_ids(package.facts)
    facts = [
        fact.model_dump(mode="json")
        for fact in package.facts
        if fact.fact_id in selected_ids
    ]
    signals = []
    for signal in package.longitudinal_signals:
        payload = signal.model_dump(mode="json")
        observed_years = payload.pop("observed_years")
        source_ids = payload.pop("source_observation_ids")
        payload["observed_year_range"] = (
            [min(observed_years), max(observed_years)] if observed_years else []
        )
        payload["source_observation_id_count"] = len(source_ids)
        signals.append(payload)
    summary = summarize_local_priors_for_formatter(local_priors)
    summary |= {
        "facts": facts,
        "facts_included": len(facts),
        "facts_omitted": len(package.facts) - len(facts),
        "fact_selection": (
            "all target-year facts plus earliest/latest facts for each temporal role "
            "per indicator; full provenance is restored by the parent"
        ),
        "longitudinal_signals": signals,
        "fact_payload": "bounded_research_view_parent_retains_full_hashed_provenance",
    }
    return summary


def build_local_judge_package(
    local_priors: tuple[dict[str, Any], ...],
    *,
    chapter_id: str,
) -> JudgeLocalEvidencePackage:
    """Build the bounded local package that bypasses web research and formatting."""

    normalized_chapter = chapter_id.strip().upper()
    methodology_ids = tuple(
        f"{normalized_chapter}.{index}" for index in range(1, 11)
    )
    package = compact_local_priors(local_priors)
    chapter = next(
        (
            item
            for item in package.chapters
            if item.chapter_id == normalized_chapter
        ),
        None,
    )
    if (
        chapter is None
        or len(chapter.methodology_ids) != len(methodology_ids)
        or set(chapter.methodology_ids) != set(methodology_ids)
    ):
        raise ValueError(
            f"local evidence does not cover the complete {normalized_chapter} chapter"
        )
    chapter_fact_ids = set(chapter.fact_ids)
    chapter_facts = tuple(
        fact for fact in package.facts if fact.fact_id in chapter_fact_ids
    )
    selected_ids = _research_fact_ids(chapter_facts)
    selected_facts = tuple(
        fact for fact in chapter_facts if fact.fact_id in selected_ids
    )
    chapter_fields = {fact.field_key for fact in chapter_facts}
    signals = tuple(
        signal
        for signal in package.longitudinal_signals
        if signal.field_key in chapter_fields
    )
    return JudgeLocalEvidencePackage(
        chapter_id=normalized_chapter,
        methodology_ids=methodology_ids,
        methodology_statuses={
            methodology_id: package.methodology_statuses.get(
                methodology_id, "error"
            )
            for methodology_id in methodology_ids
        },
        facts=selected_facts,
        facts_included=len(selected_facts),
        facts_omitted=len(chapter_facts) - len(selected_facts),
        fact_selection=(
            "All target-year facts plus earliest/latest facts for each temporal role "
            "per indicator; complete hashed source package remains parent-owned."
        ),
        longitudinal_signals=signals,
        mapping_notes=chapter.mapping_notes,
    )


def build_local_research_briefing(
    local_priors: tuple[dict[str, Any], ...],
    *,
    facts_per_chapter: int = 2,
) -> dict[str, Any]:
    """Return a deliberately small orientation briefing for internet research."""

    package = compact_local_priors(local_priors)
    facts_by_id = {fact.fact_id: fact for fact in package.facts}
    chapter_briefs: list[dict[str, Any]] = []
    source_families = {
        source
        for fact in package.facts
        for source in fact.source_slugs
    }
    for chapter in package.chapters:
        candidates = [
            facts_by_id[fact_id]
            for fact_id in chapter.fact_ids
            if fact_id in facts_by_id
        ]
        candidates.sort(
            key=lambda fact: (
                fact.period_role != "target",
                -fact.year,
                fact.fact_id,
            )
        )
        highlights = []
        for fact in candidates[:facts_per_chapter]:
            highlights.append(
                {
                    "fact_id": fact.fact_id,
                    "year": fact.year,
                    "label": fact.label,
                    "value": fact.value,
                    "unit": fact.unit,
                    "sources": fact.source_slugs,
                    "warnings": fact.warnings[:2],
                }
            )
        chapter_briefs.append(
            {
                "chapter_id": chapter.chapter_id,
                "status_counts": chapter.status_counts,
                "local_fact_count": len(chapter.fact_ids),
                "highlights": highlights,
            }
        )
    return {
        "purpose": (
            "orientation only; verify claims independently and do not treat national "
            "indicators as ruler attribution"
        ),
        "complete_local_package_retained_by_parent": True,
        "unique_local_fact_count": package.unique_fact_count,
        "source_family_index": sorted(source_families),
        "chapter_briefs": chapter_briefs,
        "error_methodology_ids": package.error_methodology_ids,
    }


def _research_fact_ids(facts: tuple[CompactLocalFact, ...]) -> set[str]:
    selected = {fact.fact_id for fact in facts if fact.period_role == "target"}
    grouped: dict[tuple[str, str], list[CompactLocalFact]] = {}
    for fact in facts:
        grouped.setdefault((fact.field_key, fact.period_role), []).append(fact)
    for rows in grouped.values():
        rows.sort(key=lambda item: (item.year, item.fact_id))
        selected.add(rows[0].fact_id)
        selected.add(rows[-1].fact_id)
    return selected


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
        str(item.get("methodology_id")) for item in local_priors if item.get("status") == status
    )


__all__ = [
    "CompactChapterPrior",
    "CompactLocalFact",
    "CompactLocalPriorPackage",
    "CompactMethodologyDisposition",
    "JudgeLocalEvidencePackage",
    "build_local_judge_package",
    "build_local_research_briefing",
    "compact_local_priors",
    "summarize_local_priors_for_formatter",
    "summarize_local_priors_for_research",
]
