"""Compact, deterministic chapter inputs derived from validated ruler dossiers.

Token estimates use three UTF-8 bytes per token. This intentionally produces a
more conservative estimate than the common four-bytes-per-token approximation;
it is a planning guard, not provider billing telemetry or an exact tokenizer.
"""

from __future__ import annotations

import json
from hashlib import sha256
from math import ceil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dossier_models import (
    DossierEvidence,
    DossierLocalPrior,
    EvidenceEnvironmentAssessment,
    EvidenceQuestionMapping,
    QuestionCoverage,
    RulerEvidenceDossier,
)
from .local_prior_package import (
    JudgeLocalEvidencePackage,
    build_local_judge_package,
)

CONSERVATIVE_BYTES_PER_TOKEN = 3


class ChapterRunProvenance(BaseModel):
    """Compact model and artifact provenance needed to audit a judge input."""

    model_config = ConfigDict(extra="forbid")

    provider_profile: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    workflow_mode: str = Field(min_length=1)
    formatter_provider_profile: str | None
    formatter_provider: str | None
    formatter_model: str | None
    research_notebook_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    source_mix_note: str = Field(min_length=1)


class ChapterLocalEvidenceInput(BaseModel):
    """Hash-verified local evidence routed directly from its parent artifact."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "unavailable", "invalid"]
    artifact_path: str | None
    artifact_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    package: JudgeLocalEvidencePackage | None
    error: str | None

    @model_validator(mode="after")
    def _coherent_status(self) -> ChapterLocalEvidenceInput:
        if self.status == "available" and (
            self.package is None
            or self.artifact_path is None
            or self.artifact_sha256 is None
            or self.error is not None
        ):
            raise ValueError("available local evidence requires a verified package")
        if self.status != "available" and (
            self.package is not None or not self.error
        ):
            raise ValueError("unavailable local evidence requires an explicit error")
        return self


def _legacy_unavailable_local_evidence() -> ChapterLocalEvidenceInput:
    """Keep preserved v1 projections readable without inventing local facts."""

    return ChapterLocalEvidenceInput(
        status="unavailable",
        artifact_path=None,
        artifact_sha256=None,
        package=None,
        error="legacy projection does not embed a direct local-evidence package",
    )


class RulerChapterProjection(BaseModel):
    """One chapter-only, non-score-bearing projection of a ruler dossier."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ruler_chapter_projection_v1"]
    source_dossier_schema_version: Literal["ruler_evidence_dossier_v2"]
    source_dossier_path: str = Field(min_length=1)
    source_dossier_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_key: str
    run_key: str
    iso3: str = Field(min_length=3, max_length=3)
    country_name: str
    ruler_id: str
    ruler_year_id: int
    ruler_name: str
    period_start_year: int
    period_end_year: int
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    methodology_ids: tuple[str, ...] = Field(min_length=10, max_length=10)
    evidence: tuple[DossierEvidence, ...]
    mappings: tuple[EvidenceQuestionMapping, ...]
    coverage: tuple[QuestionCoverage, ...] = Field(min_length=10, max_length=10)
    local_priors: tuple[DossierLocalPrior, ...] = Field(min_length=10, max_length=10)
    local_evidence: ChapterLocalEvidenceInput = Field(
        default_factory=_legacy_unavailable_local_evidence
    )
    evidence_environment: EvidenceEnvironmentAssessment
    unresolved_gaps: tuple[str, ...]
    contextual_discovery_only_evidence_ids: tuple[str, ...] = ()
    run_provenance: ChapterRunProvenance
    estimated_input_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_projection_references(self) -> RulerChapterProjection:
        expected = _chapter_methodology_ids(self.chapter_id)
        if self.methodology_ids != expected:
            raise ValueError("projection must contain all ten chapter lenses in order")
        if tuple(item.methodology_id for item in self.coverage) != expected:
            raise ValueError("projection coverage must contain all ten chapter lenses in order")
        if tuple(item.methodology_id for item in self.local_priors) != expected:
            raise ValueError("projection local priors must contain all ten lenses in order")
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        known = set(evidence_by_id)
        if len(known) != len(self.evidence):
            raise ValueError("projection evidence IDs must be unique")
        if any(
            item.methodology_id not in expected or item.evidence_id not in known
            for item in self.mappings
        ):
            raise ValueError("projection mapping references evidence outside the chapter")
        if any(
            item.methodology_id not in expected
            or not set(item.evidence_ids).issubset(known)
            for item in self.coverage
        ):
            raise ValueError("projection coverage references evidence outside the chapter")
        referenced = {item.evidence_id for item in self.mappings} | {
            evidence_id for item in self.coverage for evidence_id in item.evidence_ids
        }
        if known != referenced:
            raise ValueError("projection evidence must be mapped or covered by the chapter")
        contextual = set(self.contextual_discovery_only_evidence_ids)
        actual_discovery_only = {
            item.evidence_id
            for item in self.evidence
            if item.final_evidence_use == "discovery_only"
        }
        if contextual != actual_discovery_only:
            raise ValueError("every included discovery-only item must be explicitly contextual")
        relations_by_evidence = {
            evidence_id: {
                mapping.relation
                for mapping in self.mappings
                if mapping.evidence_id == evidence_id
            }
            for evidence_id in contextual
        }
        if any(relations != {"context"} for relations in relations_by_evidence.values()):
            raise ValueError("discovery-only evidence may have only contextual chapter mappings")
        return self


class ChapterProjectionBatchEstimate(BaseModel):
    """Pre-claim context estimate for one comparative chapter batch."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    projection_count: int = Field(gt=0)
    projection_tokens: int = Field(gt=0)
    prompt_overhead_tokens: int = Field(ge=0)
    estimated_input_tokens: int = Field(gt=0)
    context_ceiling: int = Field(gt=0)
    remaining_tokens: int = Field(ge=0)
    bytes_per_token: int = CONSERVATIVE_BYTES_PER_TOKEN


def build_ruler_chapter_projection(
    dossier: RulerEvidenceDossier,
    *,
    chapter_id: str,
    source_dossier_path: Path,
    source_dossier_sha256: str,
) -> RulerChapterProjection:
    """Project one validated dossier to one complete ten-lens chapter input."""

    normalized_chapter = chapter_id.strip().upper()
    methodology_ids = _chapter_methodology_ids(normalized_chapter)
    selected = set(methodology_ids)
    if not selected.issubset(dossier.methodology_ids):
        raise ValueError(f"dossier does not cover the complete {normalized_chapter} chapter")

    mappings = tuple(
        sorted(
            (item for item in dossier.mappings if item.methodology_id in selected),
            key=lambda item: (
                methodology_ids.index(item.methodology_id),
                item.evidence_id,
                item.relation,
                item.relevance,
            ),
        )
    )
    coverage_by_id = {
        item.methodology_id: item
        for item in dossier.coverage
        if item.methodology_id in selected
    }
    coverage = tuple(coverage_by_id[item] for item in methodology_ids)
    referenced_ids = {
        item.evidence_id for item in mappings
    } | {evidence_id for item in coverage for evidence_id in item.evidence_ids}
    evidence_by_id = {item.evidence_id: item for item in dossier.evidence}
    discovery_relations = {
        evidence_id: {item.relation for item in mappings if item.evidence_id == evidence_id}
        for evidence_id in referenced_ids
        if evidence_by_id[evidence_id].final_evidence_use == "discovery_only"
    }
    non_contextual = {
        evidence_id
        for evidence_id, relations in discovery_relations.items()
        if relations != {"context"}
    }
    if non_contextual:
        joined = ", ".join(sorted(non_contextual))
        raise ValueError(f"discovery-only evidence is not explicitly contextual: {joined}")
    evidence = tuple(
        sorted(
            (evidence_by_id[item] for item in referenced_ids),
            key=lambda item: item.evidence_id,
        )
    )
    local_prior_by_id = {
        item.methodology_id: item
        for item in dossier.local_priors
        if item.methodology_id in selected
    }
    local_priors = tuple(local_prior_by_id[item] for item in methodology_ids)
    local_evidence = _load_local_evidence(
        local_priors=local_priors,
        chapter_id=normalized_chapter,
    )
    run_profile = dossier.run_profile
    payload = {
        "schema_version": "ruler_chapter_projection_v1",
        "source_dossier_schema_version": dossier.schema_version,
        "source_dossier_path": str(source_dossier_path),
        "source_dossier_sha256": source_dossier_sha256,
        "job_key": dossier.job_key,
        "run_key": dossier.run_key,
        "iso3": dossier.iso3,
        "country_name": dossier.country_name,
        "ruler_id": dossier.ruler_id,
        "ruler_year_id": dossier.ruler_year_id,
        "ruler_name": dossier.ruler_name,
        "period_start_year": dossier.period_start_year,
        "period_end_year": dossier.period_end_year,
        "chapter_id": normalized_chapter,
        "methodology_ids": methodology_ids,
        "evidence": evidence,
        "mappings": mappings,
        "coverage": coverage,
        "local_priors": local_priors,
        "local_evidence": local_evidence,
        "evidence_environment": dossier.evidence_environment,
        "unresolved_gaps": dossier.unresolved_gaps,
        "contextual_discovery_only_evidence_ids": tuple(sorted(discovery_relations)),
        "run_provenance": ChapterRunProvenance(
            provider_profile=run_profile.provider_profile,
            provider=run_profile.provider,
            model=run_profile.model,
            workflow_mode=run_profile.workflow_mode,
            formatter_provider_profile=run_profile.formatter_provider_profile,
            formatter_provider=run_profile.formatter_provider,
            formatter_model=run_profile.formatter_model,
            research_notebook_sha256=run_profile.research_notebook_sha256,
            source_mix_note=run_profile.source_mix_note,
        ),
    }
    payload["estimated_input_tokens"] = _estimate_json_tokens(payload)
    return RulerChapterProjection.model_validate(payload)


def _load_local_evidence(
    *,
    local_priors: tuple[DossierLocalPrior, ...],
    chapter_id: str,
) -> ChapterLocalEvidenceInput:
    """Load and compact one hash-bound parent artifact without using web output."""

    artifact_pairs = {
        (item.artifact_path, item.artifact_sha256) for item in local_priors
    }
    if len(artifact_pairs) != 1:
        return ChapterLocalEvidenceInput(
            status="invalid",
            artifact_path=None,
            artifact_sha256=None,
            package=None,
            error="chapter local-prior provenance references multiple artifacts",
        )
    artifact_path, expected_sha256 = next(iter(artifact_pairs))
    path = Path(artifact_path)
    if not path.is_file():
        return ChapterLocalEvidenceInput(
            status="unavailable",
            artifact_path=artifact_path,
            artifact_sha256=expected_sha256,
            package=None,
            error="parent local-evidence artifact is unavailable",
        )
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        return ChapterLocalEvidenceInput(
            status="unavailable",
            artifact_path=artifact_path,
            artifact_sha256=expected_sha256,
            package=None,
            error=f"parent local-evidence artifact could not be read: {exc}",
        )
    if sha256(encoded).hexdigest() != expected_sha256:
        return ChapterLocalEvidenceInput(
            status="invalid",
            artifact_path=artifact_path,
            artifact_sha256=expected_sha256,
            package=None,
            error="parent local-evidence artifact hash does not match provenance",
        )
    try:
        payload = json.loads(encoded)
        if not isinstance(payload, list):
            raise ValueError("local-evidence artifact must contain a list")
        package = build_local_judge_package(
            tuple(_require_mapping(item) for item in payload),
            chapter_id=chapter_id,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return ChapterLocalEvidenceInput(
            status="invalid",
            artifact_path=artifact_path,
            artifact_sha256=expected_sha256,
            package=None,
            error=f"parent local-evidence artifact is invalid: {exc}",
        )
    return ChapterLocalEvidenceInput(
        status="available",
        artifact_path=artifact_path,
        artifact_sha256=expected_sha256,
        package=package,
        error=None,
    )


def _require_mapping(value: Any) -> dict[str, Any]:
    """Return one local-prior object or reject malformed artifact content."""

    if not isinstance(value, dict):
        raise ValueError("local-evidence artifact entries must be objects")
    return value


def estimate_chapter_projection_batch_context(
    projections: tuple[RulerChapterProjection, ...],
    *,
    context_ceiling: int,
    prompt_overhead_tokens: int = 0,
) -> ChapterProjectionBatchEstimate:
    """Estimate batch input size and fail before claim when it exceeds the ceiling."""

    if not projections:
        raise ValueError("at least one chapter projection is required")
    if context_ceiling < 1:
        raise ValueError("context_ceiling must be positive")
    if prompt_overhead_tokens < 0:
        raise ValueError("prompt_overhead_tokens cannot be negative")
    chapter_ids = {item.chapter_id for item in projections}
    if len(chapter_ids) != 1:
        raise ValueError("batch projections must all use the same chapter")
    job_keys = [item.job_key for item in projections]
    if len(job_keys) != len(set(job_keys)):
        raise ValueError("batch projections must have unique dossier job keys")
    projection_tokens = _estimate_json_tokens(
        [item.model_dump(mode="json") for item in projections]
    )
    estimated = projection_tokens + prompt_overhead_tokens
    if estimated > context_ceiling:
        raise ValueError(
            "chapter projection batch exceeds context ceiling: "
            f"estimated {estimated} tokens > {context_ceiling}"
        )
    return ChapterProjectionBatchEstimate(
        chapter_id=next(iter(chapter_ids)),
        projection_count=len(projections),
        projection_tokens=projection_tokens,
        prompt_overhead_tokens=prompt_overhead_tokens,
        estimated_input_tokens=estimated,
        context_ceiling=context_ceiling,
        remaining_tokens=context_ceiling - estimated,
    )


def _chapter_methodology_ids(chapter_id: str) -> tuple[str, ...]:
    if chapter_id not in {f"{index}B" for index in range(1, 9)}:
        raise ValueError(f"unsupported chapter_id: {chapter_id!r}")
    return tuple(f"{chapter_id}.{index}" for index in range(1, 11))


def _estimate_json_tokens(payload: object) -> int:
    encoded = json.dumps(
        payload,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return max(1, ceil(len(encoded) / CONSERVATIVE_BYTES_PER_TOKEN))


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported projection value: {type(value).__name__}")


__all__ = [
    "CONSERVATIVE_BYTES_PER_TOKEN",
    "ChapterLocalEvidenceInput",
    "ChapterProjectionBatchEstimate",
    "ChapterRunProvenance",
    "RulerChapterProjection",
    "build_ruler_chapter_projection",
    "estimate_chapter_projection_batch_context",
]
