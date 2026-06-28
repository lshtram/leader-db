"""Fixture-only acquired-evidence helpers for research Increment 3."""

from __future__ import annotations

from leaders_db.sources.contracts import (
    NormalizedObservation,
    ObservationValueType,
    RawLocator,
    SourceId,
    TransformLocator,
)

from .models import AcquiredEvidenceRecord


def acquired_evidence_to_observation(
    record: AcquiredEvidenceRecord,
    *,
    source_id: SourceId | None = None,
    source_version: str = "fixture",
) -> NormalizedObservation:
    """Convert reviewed fixture evidence into a stored observation shape.

    This helper does not fetch, approve, or persist evidence. It lets tests and
    later controlled loaders prove that generated qualitative evidence can re-enter
    the normal evidence path with URL/quote/retrieval provenance intact.
    """

    generated_source_id = source_id or SourceId(slug="generated_acquired_evidence")
    return NormalizedObservation(
        source_id=generated_source_id,
        observation_id=f"{record.task_id}:{record.claim_key}",
        observation_family="leader_legal_case",
        indicator_code=record.claim_key,
        value=record.value,
        value_type=_observation_value_type(record.value_type),
        year=_int_scope_value(record, "year"),
        country_code=_str_scope_value(record, "country"),
        country_name=None,
        leader_id=_str_scope_value(record, "leader"),
        leader_name=None,
        unit=None,
        scale=None,
        source_version=source_version,
        raw_locator=RawLocator(asset_id=record.task_id, url=record.source_url),
        transform_locator=TransformLocator(
            transform_name="acquired_evidence_fixture",
            rule_id="research_increment_3_fixture_conversion",
        ),
        quality_flags=("human_review_required",)
        if record.human_review_required
        else (),
        extension={
            "source_title": record.source_title,
            "source_type": record.source_type,
            "quote": record.quote,
            "retrieved_at": record.retrieved_at,
            "confidence_score": record.confidence_score,
            "human_review_required": record.human_review_required,
            "caveats": record.caveats,
        },
    )


def _observation_value_type(value_type: str) -> ObservationValueType:
    if value_type == "boolean":
        return "boolean"
    if value_type == "numeric":
        return "numeric"
    if value_type == "categorical":
        return "categorical"
    if value_type == "text":
        return "text"
    return "missing"


def _str_scope_value(record: AcquiredEvidenceRecord, key: str) -> str | None:
    value = record.subject_scope.value_for(key)
    return value if isinstance(value, str) else None


def _int_scope_value(record: AcquiredEvidenceRecord, key: str) -> int | None:
    value = record.subject_scope.value_for(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
