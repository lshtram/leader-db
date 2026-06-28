"""Build first-slice analytical datasets from stored evidence."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from leaders_db.sources.contracts import NormalizedObservation
from leaders_db.sources.query import EvidenceRepository

from .models import (
    AnalyticalDatasetRow,
    EvidenceAcquisitionTask,
    EvidenceGap,
    EvidenceGapReport,
    InvestigationPlan,
    RowScope,
)
from .planner import expand_scope_filter
from .registry import get_concept_spec


def build_analytical_dataset(
    plan: InvestigationPlan,
    repository: EvidenceRepository,
) -> tuple[
    tuple[AnalyticalDatasetRow, ...],
    EvidenceGapReport,
    tuple[EvidenceAcquisitionTask, ...],
]:
    """Query stored evidence and build analytical rows, gaps, and planned tasks."""

    observations = tuple(repository.query_observations(plan.evidence_query))
    rows: list[AnalyticalDatasetRow] = []
    gaps: list[EvidenceGap] = []
    tasks: list[EvidenceAcquisitionTask] = []
    direct_count = 0

    for row_scope in expand_scope_filter(plan.scope_filter):
        for concept_key in plan.concept_keys:
            matches = tuple(
                obs for obs in observations if _matches_scope(obs, row_scope, concept_key)
            )
            if matches:
                direct_count += len(matches)
                rows.append(_direct_row(plan, row_scope, concept_key, matches))
                continue

            gap = _gap_for_missing(plan, row_scope, concept_key)
            gaps.append(gap)
            if plan.include_missing_rows:
                rows.append(_missing_row(plan, row_scope, concept_key))
            if plan.acquisition_policy in {"plan_only", "run_approved_tasks"}:
                tasks.append(_task_for_gap(plan, gap))

    task_ids = tuple(task.task_id for task in tasks)
    gap_report = EvidenceGapReport(
        question_id=plan.question_id,
        required_concepts=plan.concept_keys,
        available_count=direct_count,
        missing=tuple(gaps),
        can_continue=True,
        recommended_acquisition_tasks=task_ids,
    )
    return tuple(rows), gap_report, tuple(tasks)


def _matches_scope(
    observation: NormalizedObservation,
    row_scope: RowScope,
    concept_key: str,
) -> bool:
    return (
        observation.indicator_code == concept_key
        and _matches_value(
            row_scope.value_for("country"),
            observation.country_code,
            observation.country_name,
        )
        and _matches_value(row_scope.value_for("year"), observation.year)
        and _matches_value(
            row_scope.value_for("leader"),
            observation.leader_id,
            observation.leader_name,
        )
    )


def _matches_value(scope_value: object, *observation_values: object) -> bool:
    if scope_value is None:
        return True
    return scope_value in observation_values


def _direct_row(
    plan: InvestigationPlan,
    row_scope: RowScope,
    concept_key: str,
    observations: tuple[NormalizedObservation, ...],
) -> AnalyticalDatasetRow:
    primary = observations[0]
    return AnalyticalDatasetRow(
        question_id=plan.question_id,
        row_scope=row_scope,
        concept_key=concept_key,
        value=_row_value(primary),
        value_type=primary.value_type,
        unit=primary.unit,
        source_id=primary.source_id.slug,
        source_observation_ids=tuple(obs.observation_id for obs in observations),
        coverage_status="direct",
        confidence_score=None,
        warning_codes=tuple(warning.code for obs in observations for warning in obs.warnings),
        caveats=tuple(flag for obs in observations for flag in obs.quality_flags),
        provenance_json=_provenance(primary),
    )


def _missing_row(
    plan: InvestigationPlan,
    row_scope: RowScope,
    concept_key: str,
) -> AnalyticalDatasetRow:
    return AnalyticalDatasetRow(
        question_id=plan.question_id,
        row_scope=row_scope,
        concept_key=concept_key,
        value=None,
        value_type="missing",
        unit=None,
        source_id=None,
        source_observation_ids=(),
        coverage_status="missing",
        warning_codes=("missing_evidence",),
        caveats=(),
        provenance_json={},
    )


def _gap_for_missing(
    plan: InvestigationPlan,
    row_scope: RowScope,
    concept_key: str,
) -> EvidenceGap:
    gap_id = (
        f"gap-{plan.question_id}-{concept_key}-"
        f"{len(row_scope.dimensions)}-{_scope_slug(row_scope)}"
    )
    reason = (
        "qualitative_evidence_needed"
        if plan.acquisition_policy in {"plan_only", "run_approved_tasks"}
        else "indicator_missing"
    )
    return EvidenceGap(
        gap_id=gap_id,
        concept_key=concept_key,
        scope_filter=row_scope.as_filter(),
        reason=reason,
        required_evidence=(
            f"Stored evidence for concept {concept_key!r} at the requested row scope."
        ),
    )


def _task_for_gap(plan: InvestigationPlan, gap: EvidenceGap) -> EvidenceAcquisitionTask:
    concept_spec = get_concept_spec(gap.concept_key)
    required_output_schema = (
        concept_spec.required_output_schema
        if concept_spec is not None
        else "AcquiredEvidenceRecord"
    )
    allowed_source_types = (
        concept_spec.allowed_source_types
        if concept_spec is not None
        else ("official_record", "reputable_news")
    )
    return EvidenceAcquisitionTask(
        task_id=f"task-{gap.gap_id}",
        question_id=plan.question_id,
        gap_id=gap.gap_id,
        acquisition_type="manual_research",
        scope_filter=gap.scope_filter,
        evidence_need=gap.required_evidence,
        required_output_schema=required_output_schema,
        allowed_source_types=plan.source_priority or allowed_source_types,
        status="planned",
    )


def _provenance(observation: NormalizedObservation) -> dict[str, Any]:
    return {
        "source_version": observation.source_version,
        "raw_locator": asdict(observation.raw_locator),
        "transform_locator": asdict(observation.transform_locator),
        "quality_flags": observation.quality_flags,
        "raw_locator_summary": _raw_locator_summary(observation),
    }


def _row_value(observation: NormalizedObservation) -> float | int | str | bool | None:
    value = observation.value
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def _raw_locator_summary(observation: NormalizedObservation) -> str:
    locator = observation.raw_locator
    parts = [locator.asset_id]
    if locator.path:
        parts.append(locator.path)
    if locator.row_number is not None:
        parts.append(f"row {locator.row_number}")
    if locator.column_name:
        parts.append(locator.column_name)
    return ":".join(parts)


def _scope_slug(row_scope: RowScope) -> str:
    return "-".join(f"{dimension.key}-{dimension.value}" for dimension in row_scope.dimensions)
