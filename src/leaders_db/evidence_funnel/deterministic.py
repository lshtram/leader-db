"""Deterministic funnel transformations around model-assisted boundaries."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from .models import (
    BriefEvidenceReference,
    ClaimCluster,
    ClusterRelationship,
    EvidenceCandidate,
    QuestionEvidenceBrief,
    SourceDescriptor,
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_OFFICIAL_ROLES = {
    "executive_official_report",
    "executive_legislative_record",
    "executive_oversight_body",
    "executive_self_report",
    "domestic_regulator",
    "official_statistical_body",
    "state_owned_enterprise",
}


def stable_evidence_id(
    source_id: str, locator: str, excerpt: str, claim: str
) -> str:
    """Derive a stable evidence ID from its source passage and factual account."""

    key = "\x1f".join(
        (
            source_id.strip(),
            _normalize(locator),
            _normalize(excerpt),
            _normalize(claim),
        )
    )
    return f"EF-E{hashlib.sha256(key.encode()).hexdigest()[:12]}"


def stable_cluster_id(canonical_fact_key: str) -> str:
    """Derive a stable cluster ID from the normalized underlying fact."""

    return f"EF-C{hashlib.sha256(_normalize(canonical_fact_key).encode()).hexdigest()[:12]}"


def deterministic_cluster_key(candidate: EvidenceCandidate) -> str:
    """Generate a conservative duplicate key from entities, dates, action, and outcome."""

    components = (
        candidate.actor,
        candidate.action,
        candidate.mechanism,
        candidate.outcome,
        "|".join(candidate.dates),
        "|".join(candidate.quantities),
    )
    return "|".join(_normalize(value) for value in components)


def build_deterministic_clusters(
    candidates: Iterable[EvidenceCandidate],
    *,
    source_roles: Mapping[str, str],
    explicit_relations: Mapping[str, str],
) -> tuple[ClaimCluster, ...]:
    """Cluster verified candidates while preserving contradictions and dependencies."""

    accepted = tuple(
        item for item in candidates if item.verification_status in {"accepted", "corrected"}
    )
    grouped: dict[str, list[EvidenceCandidate]] = defaultdict(list)
    for candidate in accepted:
        grouped[deterministic_cluster_key(candidate)].append(candidate)
    missing_relations = sorted(
        item.evidence_id for item in accepted if item.evidence_id not in explicit_relations
    )
    if missing_relations:
        raise ValueError(
            f"accepted evidence lacks typed cluster relations: {missing_relations}"
        )
    clusters: list[ClaimCluster] = []
    for key, members in sorted(grouped.items()):
        member_ids = tuple(item.evidence_id for item in members)
        independent_families = {
            item.source_family for item in members if not item.source_dependencies
        }
        dependent_families = {
            item.source_family for item in members if item.source_dependencies
        }
        independence_units = {
            tuple(sorted(item.source_dependencies)) or (item.source_id,)
            for item in members
        }
        official_units = {
            unit
            for unit in independence_units
            if all(source_roles.get(source_id) in _OFFICIAL_ROLES for source_id in unit)
        }
        relationships = tuple(
            ClusterRelationship(
                evidence_id=item.evidence_id,
                relation=explicit_relations[item.evidence_id],
            )
            for item in members
        )
        unresolved = tuple(
            item.claim
            for item, relation in zip(members, relationships, strict=True)
            if relation.relation == "contradicts"
        )
        clusters.append(
            ClaimCluster(
                schema_version="claim_cluster_v1",
                cluster_id=stable_cluster_id(key),
                canonical_fact=members[0].claim,
                canonical_fact_key=key,
                member_evidence_ids=member_ids,
                relationships=relationships,
                independent_source_families=tuple(sorted(independent_families)),
                dependent_source_families=tuple(sorted(dependent_families)),
                official_source_concentration=(
                    len(official_units) / len(independence_units)
                ),
                unresolved_conflicts=unresolved,
            )
        )
    return tuple(clusters)


def build_question_briefs(
    methodology_ids: Sequence[str],
    candidates: Sequence[EvidenceCandidate],
    clusters: Sequence[ClaimCluster],
    *,
    unresolved_gaps: Mapping[str, Sequence[str]] | None = None,
) -> tuple[QuestionEvidenceBrief, ...]:
    """Build one brief per question from verified cluster relationships."""

    by_id = {item.evidence_id: item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate evidence IDs must be unique")
    cluster_references = {
        evidence_id for cluster in clusters for evidence_id in cluster.member_evidence_ids
    }
    unknown = sorted(cluster_references - set(by_id))
    if unknown:
        raise ValueError(f"clusters reference unknown evidence IDs: {unknown}")
    accepted_ids = {
        item.evidence_id
        for item in candidates
        if item.verification_status in {"accepted", "corrected"}
    }
    missing = sorted(accepted_ids - cluster_references)
    if missing:
        raise ValueError(f"accepted evidence is missing from clusters: {missing}")
    membership_counts: dict[str, int] = defaultdict(int)
    for cluster in clusters:
        for evidence_id in cluster.member_evidence_ids:
            membership_counts[evidence_id] += 1
    repeated = sorted(
        evidence_id for evidence_id, count in membership_counts.items() if count != 1
    )
    if repeated:
        raise ValueError(f"evidence must belong to exactly one cluster: {repeated}")
    ineligible = sorted(cluster_references - accepted_ids)
    if ineligible:
        raise ValueError(f"clusters contain unaccepted evidence IDs: {ineligible}")
    gaps = unresolved_gaps or {}
    briefs: list[QuestionEvidenceBrief] = []
    for methodology_id in methodology_ids:
        references: list[BriefEvidenceReference] = []
        chronology: set[str] = set()
        authority: set[str] = set()
        implementation: set[str] = set()
        families: set[str] = set()
        for cluster in clusters:
            applicable = tuple(
                evidence_id
                for evidence_id in cluster.member_evidence_ids
                if methodology_id in by_id[evidence_id].question_ids
            )
            if not applicable:
                continue
            items = tuple(by_id[evidence_id] for evidence_id in applicable)
            polarity = _cluster_polarity(items)
            references.append(
                BriefEvidenceReference(
                    cluster_id=cluster.cluster_id,
                    evidence_ids=applicable,
                    polarity=polarity,
                    account=items[0].claim,
                    competing_interpretations=cluster.unresolved_conflicts,
                )
            )
            for item in items:
                chronology.update(item.dates)
                authority.add(item.attribution)
                implementation.add(
                    f"{item.actor}: {item.action}; mechanism: {item.mechanism}; "
                    f"outcome: {item.outcome}"
                )
                families.add(item.source_family)
        source_note = (
            f"{len(families)} source families represented: {', '.join(sorted(families))}."
            if families
            else "No verified source family currently informs this question."
        )
        briefs.append(
            QuestionEvidenceBrief(
                schema_version="question_evidence_brief_v1",
                methodology_id=methodology_id,
                evidence=tuple(references),
                chronology=tuple(sorted(chronology)),
                authority_and_constraints=tuple(sorted(authority)),
                implementation_status=tuple(sorted(implementation)),
                unresolved_gaps=tuple(gaps.get(methodology_id, ())),
                source_family_assessment=source_note,
            )
        )
    return tuple(briefs)


def source_role_map(sources: Iterable[SourceDescriptor]) -> dict[str, str]:
    """Return the source-role lookup required for official concentration."""

    return {source.source_id: source.source_role for source in sources}


def _cluster_polarity(items: Sequence[EvidenceCandidate]) -> str:
    polarities = {item.polarity for item in items}
    if len(polarities) == 1:
        return next(iter(polarities))
    return "mixed"


def _normalize(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold()))


__all__ = [
    "build_deterministic_clusters",
    "build_question_briefs",
    "deterministic_cluster_key",
    "source_role_map",
    "stable_cluster_id",
    "stable_evidence_id",
]
