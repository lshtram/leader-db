"""Tests for corpus duplicate-group integrity controls."""

import pytest

from leaders_db.research.corpus_cluster_review import (
    ClusterMember,
    ClusterReviewOutput,
    DuplicateGroup,
    _retain_valid_groups,
    _validate_groups,
)
from leaders_db.research.corpus_mapping_review import _evidence_digest
from tests.research.test_corpus_mapping_review import _evidence


def test_cluster_review_rejects_reused_evidence() -> None:
    first = _evidence("E-1", "First material fact")
    second = _evidence("E-2", "Second material fact")
    first_member = ClusterMember(
        evidence_id=first.evidence_id,
        evidence_digest=_evidence_digest(first),
    )
    result = ClusterReviewOutput(
        duplicate_groups=(
            DuplicateGroup(
                canonical_fact_key="first group",
                members=(
                    first_member,
                    ClusterMember(
                        evidence_id=second.evidence_id,
                        evidence_digest=_evidence_digest(second),
                    ),
                ),
            ),
            DuplicateGroup(
                canonical_fact_key="invalid repeated membership",
                members=(first_member, first_member),
            ),
        )
    )

    with pytest.raises(ValueError, match="more than one"):
        _validate_groups((first, second), result)


def test_cluster_review_rejects_altered_digest() -> None:
    first = _evidence("E-1", "First material fact")
    second = _evidence("E-2", "Second material fact")
    result = ClusterReviewOutput(
        duplicate_groups=(
            DuplicateGroup(
                canonical_fact_key="same fact",
                members=(
                    ClusterMember(evidence_id="E-1", evidence_digest="0" * 12),
                    ClusterMember(
                        evidence_id="E-2",
                        evidence_digest=_evidence_digest(second),
                    ),
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="altered evidence identity"):
        _validate_groups((first, second), result)


def test_cluster_review_retains_only_identity_exact_groups() -> None:
    first = _evidence("E-1", "First material fact")
    second = _evidence("E-2", "Second material fact")
    result = ClusterReviewOutput(
        duplicate_groups=(
            DuplicateGroup(
                canonical_fact_key="valid group",
                members=tuple(
                    ClusterMember(
                        evidence_id=item.evidence_id,
                        evidence_digest=_evidence_digest(item),
                    )
                    for item in (first, second)
                ),
            ),
            DuplicateGroup(
                canonical_fact_key="altered group",
                members=(
                    ClusterMember(evidence_id="E-1", evidence_digest="0" * 12),
                    ClusterMember(evidence_id="E-2", evidence_digest="0" * 12),
                ),
            ),
        )
    )

    retained, rejected = _retain_valid_groups((first, second), result)

    assert retained.duplicate_groups == (result.duplicate_groups[0],)
    assert rejected == 1
