"""First-slice research engine models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from leaders_db.sources.contracts import EvidenceQuery, SourceId

DimensionValue: TypeAlias = str | int | float | bool | None
DimensionValueType: TypeAlias = Literal["string", "integer", "number", "boolean", "date", "missing"]
DimensionRole: TypeAlias = Literal["entity", "time", "category", "filter", "grouping"]


class _StrictModel(BaseModel):
    """Shared strict JSON-facing Pydantic settings."""

    model_config = ConfigDict(extra="forbid")


class DimensionBinding(_StrictModel):
    """Concrete value for one row-scope dimension."""

    key: str
    value: DimensionValue
    value_type: DimensionValueType
    role: DimensionRole = "filter"
    label: str | None = None


class RowScope(_StrictModel):
    """Concrete identity for one analytical or evidence row."""

    dimensions: tuple[DimensionBinding, ...]

    def value_for(self, key: str) -> DimensionValue:
        """Return the value bound to ``key``, or ``None`` when absent."""

        for dimension in self.dimensions:
            if dimension.key == key:
                return dimension.value
        return None

    def as_filter(self) -> ScopeFilter:
        """Return a single-value filter representing this concrete scope."""

        return ScopeFilter(
            filters=tuple(
                DimensionFilter(
                    key=d.key,
                    values=() if d.value is None else (d.value,),
                    role=d.role,
                )
                for d in self.dimensions
            )
        )


class DimensionFilter(_StrictModel):
    """Query/request filter for one dimension."""

    key: str
    values: tuple[str | int | float | bool, ...] = ()
    start: str | int | float | None = None
    end: str | int | float | None = None
    role: DimensionRole = "filter"


class ScopeFilter(_StrictModel):
    """Multi-dimension query/request filter."""

    filters: tuple[DimensionFilter, ...]


class ResearchQuestion(_StrictModel):
    """Explicit research request accepted by the first-slice planner."""

    question_id: str
    question_key: str
    display_text: str
    concepts: tuple[str, ...]
    scope_filter: ScopeFilter
    analyses: tuple[str, ...]
    preferred_sources: tuple[str, ...] = ()


class InvestigationPlan(_StrictModel):
    """Machine-executable research recipe."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    question_id: str
    concept_keys: tuple[str, ...]
    evidence_query: EvidenceQuery
    source_priority: tuple[str, ...]
    scope_filter: ScopeFilter
    output_grain: Literal["dimensioned_concept", "category_bundle", "evidence_record"]
    analyses: tuple[str, ...]
    include_missing_rows: bool = True
    acquisition_policy: Literal["none", "plan_only", "run_approved_tasks"] = "none"

    @field_serializer("evidence_query")
    def _serialize_evidence_query(self, query: EvidenceQuery) -> dict[str, Any]:
        return evidence_query_to_dict(query)


class EvidenceGap(_StrictModel):
    """Missing evidence needed for one concept/scope."""

    gap_id: str
    concept_key: str
    scope_filter: ScopeFilter
    reason: Literal[
        "source_not_ingested",
        "country_absent",
        "year_absent",
        "indicator_missing",
        "qualitative_evidence_needed",
        "insufficient_source_quality",
    ]
    required_evidence: str


class EvidenceGapReport(_StrictModel):
    """Summary of evidence needed but unavailable in stored observations."""

    question_id: str
    required_concepts: tuple[str, ...]
    available_count: int
    missing: tuple[EvidenceGap, ...]
    can_continue: bool
    recommended_acquisition_tasks: tuple[str, ...]


class EvidenceAcquisitionTask(_StrictModel):
    """Planned controlled acquisition task; it does not perform acquisition."""

    task_id: str
    question_id: str
    gap_id: str
    acquisition_type: Literal[
        "source_ingestion", "targeted_web_research", "manual_research", "document_review"
    ]
    scope_filter: ScopeFilter
    evidence_need: str
    required_output_schema: str
    allowed_source_types: tuple[str, ...]
    status: Literal["planned", "approved", "running", "completed", "failed"] = "planned"


class AnalyticalDatasetRow(_StrictModel):
    """One question-specific analytical row with evidence traceability."""

    question_id: str
    row_scope: RowScope
    concept_key: str
    value: float | int | str | bool | None
    value_type: Literal["numeric", "categorical", "text", "boolean", "json", "missing"]
    unit: str | None
    source_id: str | None
    source_observation_ids: tuple[str, ...]
    coverage_status: Literal["direct", "derived", "proxy", "stale", "missing", "not_applicable"]
    confidence_score: int | None = None
    warning_codes: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    provenance_json: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(_StrictModel):
    """Structured analysis output over analytical dataset rows."""

    question_id: str
    analysis_type: str
    result_id: str
    rows: tuple[dict[str, Any], ...]
    warning_codes: tuple[str, ...]
    caveats: tuple[str, ...]


class Finding(_StrictModel):
    """Report-ready claim linked to evidence or analysis results."""

    finding_id: str
    question_id: str
    claim: str
    support: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    analysis_result_ids: tuple[str, ...]
    confidence_score: int | None
    caveats: tuple[str, ...]
    warning_codes: tuple[str, ...]


class ResearchRunResult(_StrictModel):
    """Summary of a completed first-slice research run."""

    run_id: str
    question_id: str
    status: Literal["success", "partial", "failed"]
    output_dir: Path
    dataset_path: Path | None
    findings_path: Path | None
    report_path: Path | None = None
    manifest_path: Path | None
    warning_codes: tuple[str, ...]


def evidence_query_to_dict(query: EvidenceQuery) -> dict[str, Any]:
    """Return a stable JSON-practical representation of an evidence query."""

    return {
        "source_ids": None
        if query.source_ids is None
        else [source_id.slug for source_id in query.source_ids],
        "observation_families": query.observation_families,
        "indicator_codes": query.indicator_codes,
        "years": query.years,
        "countries": query.countries,
        "leaders": query.leaders,
        "include_raw_locators": query.include_raw_locators,
        "include_attribution": query.include_attribution,
        "include_warnings": query.include_warnings,
        "include_quality_flags": query.include_quality_flags,
        "include_manifests": query.include_manifests,
    }


def source_ids_from_slugs(slugs: tuple[str, ...]) -> tuple[SourceId, ...] | None:
    """Convert preferred source slugs to existing ``SourceId`` contracts."""

    return None if not slugs else tuple(SourceId(slug=slug) for slug in slugs)
