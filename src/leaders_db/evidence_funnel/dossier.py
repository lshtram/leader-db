"""Deterministic conversion from the verified funnel ledger to dossier v2."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from leaders_db.research.dossier_models import (
    DossierEvidence,
    DossierLocalPrior,
    DossierRunProfile,
    EvidenceEnvironmentAssessment,
    EvidenceQuestionMapping,
    QuestionCoverage,
    RulerEvidenceDossier,
)

from .models import ClaimCluster, EvidenceCandidate, FunnelEvidenceEnvironment

_RELATION_BY_POLARITY = {
    "favorable": "supports",
    "adverse": "contradicts",
    "mixed": "context",
    "exculpatory": "mitigates",
    "context": "context",
}


def to_ruler_evidence_dossier(
    *,
    candidates: Sequence[EvidenceCandidate],
    clusters: Sequence[ClaimCluster],
    methodology_ids: Sequence[str],
    job_key: str,
    run_key: str,
    iso3: str,
    country_name: str,
    ruler_id: str,
    ruler_year_id: int,
    ruler_name: str,
    period_start_year: int,
    period_end_year: int,
    local_priors: Sequence[DossierLocalPrior],
    evidence_environment: FunnelEvidenceEnvironment,
    run_profile: DossierRunProfile,
    unresolved_gaps: Sequence[str] = (),
) -> RulerEvidenceDossier:
    """Convert accepted candidates once, then link them to every applicable question."""

    accepted = tuple(
        item for item in candidates if item.verification_status in {"accepted", "corrected"}
    )
    id_map = {
        candidate.evidence_id: f"E{index:03d}"
        for index, candidate in enumerate(accepted, start=1)
    }
    cluster_by_member = _cluster_members(clusters)
    missing_clusters = sorted(set(id_map) - set(cluster_by_member))
    if missing_clusters:
        raise ValueError(f"accepted evidence is missing from clusters: {missing_clusters}")
    evidence = tuple(
        _to_dossier_evidence(item, id_map[item.evidence_id], cluster_by_member[item.evidence_id])
        for item in accepted
    )
    mappings = tuple(
        EvidenceQuestionMapping(
            evidence_id=id_map[item.evidence_id],
            methodology_id=methodology_id,
            relation=_RELATION_BY_POLARITY[item.polarity],
            relevance=(
                f"Atomic funnel evidence mapped to {methodology_id}; "
                f"cluster {cluster_by_member[item.evidence_id].cluster_id}."
            ),
        )
        for item in accepted
        for methodology_id in item.question_ids
        if methodology_id in methodology_ids
    )
    evidence_by_question: dict[str, list[str]] = defaultdict(list)
    for mapping in mappings:
        evidence_by_question[mapping.methodology_id].append(mapping.evidence_id)
    coverage = tuple(
        QuestionCoverage(
            methodology_id=methodology_id,
            status=("covered" if evidence_by_question[methodology_id] else "no_evidence_found"),
            evidence_ids=tuple(dict.fromkeys(evidence_by_question[methodology_id])),
            reason=(
                "Verified funnel evidence is linked to this methodology question."
                if evidence_by_question[methodology_id]
                else "No verified accepted evidence currently maps to this question."
            ),
        )
        for methodology_id in methodology_ids
    )
    translated_environment = _translate_environment_support(evidence_environment, id_map)
    return RulerEvidenceDossier(
        schema_version="ruler_evidence_dossier_v2",
        job_key=job_key,
        run_key=run_key,
        iso3=iso3,
        country_name=country_name,
        ruler_id=ruler_id,
        ruler_year_id=ruler_year_id,
        ruler_name=ruler_name,
        period_start_year=period_start_year,
        period_end_year=period_end_year,
        methodology_ids=tuple(methodology_ids),
        evidence=evidence,
        mappings=mappings,
        coverage=coverage,
        unresolved_gaps=tuple(unresolved_gaps),
        completed_queries=(),
        normalization_warnings=(),
        local_priors=tuple(local_priors),
        evidence_environment=translated_environment,
        run_profile=run_profile,
    )


def _cluster_members(clusters: Sequence[ClaimCluster]) -> Mapping[str, ClaimCluster]:
    result: dict[str, ClaimCluster] = {}
    for cluster in clusters:
        for evidence_id in cluster.member_evidence_ids:
            if evidence_id in result:
                raise ValueError(f"evidence belongs to several clusters: {evidence_id}")
            result[evidence_id] = cluster
    return result


def _to_dossier_evidence(
    candidate: EvidenceCandidate, dossier_id: str, cluster: ClaimCluster
) -> DossierEvidence:
    limitations = "; ".join(candidate.source_limitations) or "No additional limitation recorded."
    notes = "; ".join(candidate.verification_notes) or "Fresh-passage verification accepted."
    return DossierEvidence(
        evidence_id=dossier_id,
        claim=candidate.claim,
        url=candidate.url,
        title=candidate.title,
        publisher=candidate.publisher,
        publication_date=candidate.publication_date,
        excerpt=candidate.excerpt,
        source_locator=candidate.locator,
        canonical_fact_key=f"{cluster.canonical_fact_key}:{candidate.evidence_id}",
        source_type=candidate.source_type,
        source_confidence=(
            "verified_with_premium_escalation"
            if candidate.premium_verification_required
            else "verified_against_original_passage"
        ),
        source_confidence_reason=f"{notes} Source limitations: {limitations}",
        final_evidence_use="final_evidence",
        period_fit=candidate.period_fit,
        ruler_attribution=candidate.attribution,
        contrary_evidence=cluster.unresolved_conflicts,
    )


def _translate_environment_support(
    environment: FunnelEvidenceEnvironment, id_map: Mapping[str, str]
) -> EvidenceEnvironmentAssessment:
    unknown = sorted(set(environment.supporting_evidence_ids) - set(id_map))
    if unknown:
        raise ValueError(f"evidence environment references unknown funnel IDs: {unknown}")
    translated = tuple(id_map[value] for value in environment.supporting_evidence_ids)
    return EvidenceEnvironmentAssessment.model_validate(
        {
            **environment.model_dump(mode="json"),
            "supporting_evidence_ids": translated,
        }
    )


__all__ = ["to_ruler_evidence_dossier"]
