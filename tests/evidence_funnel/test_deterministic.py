from __future__ import annotations

import pytest

from leaders_db.evidence_funnel.deterministic import (
    build_deterministic_clusters,
    build_question_briefs,
    stable_evidence_id,
)
from leaders_db.evidence_funnel.models import EvidenceCandidate


def _candidate(
    *,
    source_id: str,
    claim: str,
    question_ids: tuple[str, ...],
    source_family: str = "family",
    dependencies: tuple[str, ...] = (),
) -> EvidenceCandidate:
    locator = "page 1"
    excerpt = f"Exact source passage for {claim}"
    return EvidenceCandidate(
        schema_version="evidence_candidate_v1",
        evidence_id=stable_evidence_id(source_id, locator, excerpt, claim),
        source_id=source_id,
        source_sha256="a" * 64,
        source_family=source_family,
        source_dependencies=dependencies,
        claim=claim,
        claim_type="observed_fact",
        polarity="mixed",
        actor="Government",
        action="implemented policy",
        mechanism="administrative action",
        outcome="reported result",
        excerpt=excerpt,
        locator=locator,
        url="https://example.test",
        title="Report",
        publisher="Publisher",
        publication_date="2022",
        source_type="report",
        attribution="Report",
        period_fit="Target year",
        question_ids=question_ids,
        verification_status="accepted",
    )


def test_clusters_require_explicit_typed_relations() -> None:
    candidate = _candidate(
        source_id="LAW-005",
        claim="Policy account",
        question_ids=("5B.1",),
    )

    with pytest.raises(ValueError, match="lacks typed cluster relations"):
        build_deterministic_clusters(
            (candidate,),
            source_roles={"LAW-005": "official_primary"},
            explicit_relations={},
        )


def test_brief_account_comes_from_member_applicable_to_question() -> None:
    first = _candidate(
        source_id="LAW-005",
        claim="Account applicable only to question one",
        question_ids=("5B.1",),
    )
    second = _candidate(
        source_id="MAC-010",
        claim="Account applicable only to question two",
        question_ids=("5B.2",),
    )
    second = second.model_copy(
        update={
            "action": first.action,
            "mechanism": first.mechanism,
            "outcome": first.outcome,
            "actor": first.actor,
        }
    )
    clusters = build_deterministic_clusters(
        (first, second),
        source_roles={"LAW-005": "official_primary", "MAC-010": "independent_analysis"},
        explicit_relations={
            first.evidence_id: "supports",
            second.evidence_id: "qualifies",
        },
    )

    briefs = build_question_briefs(("5B.1", "5B.2"), (first, second), clusters)

    assert briefs[0].evidence[0].account == first.claim
    assert briefs[1].evidence[0].account == second.claim
    assert briefs[1].evidence[0].evidence_ids == (second.evidence_id,)


def test_official_concentration_counts_independent_units_not_rows() -> None:
    official_one = _candidate(
        source_id="LAW-005",
        claim="Same official event section one",
        question_ids=("5B.1",),
        source_family="official",
    )
    official_two = _candidate(
        source_id="LAW-005",
        claim="Same official event section two",
        question_ids=("5B.1",),
        source_family="official",
    )
    independent = _candidate(
        source_id="MAC-010",
        claim="Independent account of event",
        question_ids=("5B.1",),
        source_family="analysis",
    )
    shared = {"actor": "Government", "action": "implemented policy"}
    candidates = tuple(
        item.model_copy(update=shared)
        for item in (official_one, official_two, independent)
    )
    clusters = build_deterministic_clusters(
        candidates,
        source_roles={
            "LAW-005": "executive_legislative_record",
            "MAC-010": "independent_analysis",
        },
        explicit_relations={item.evidence_id: "supports" for item in candidates},
    )

    assert clusters[0].official_source_concentration == 0.5


def test_official_concentration_follows_dependency_root_without_primary_member() -> None:
    restatement = _candidate(
        source_id="NEWS-010",
        claim="News restated the official legal record",
        question_ids=("5B.1",),
        source_family="news",
        dependencies=("LAW-005",),
    )

    clusters = build_deterministic_clusters(
        (restatement,),
        source_roles={
            "NEWS-010": "independent_reporting",
            "LAW-005": "executive_legislative_record",
        },
        explicit_relations={restatement.evidence_id: "supports"},
    )

    assert clusters[0].official_source_concentration == 1.0
