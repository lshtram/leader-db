"""Tests for evidence identity controls in mapping review."""

from leaders_db.research.corpus_mapping_review import (
    MappingReviewOutput,
    MappingVerdict,
    _evidence_digest,
    _identity_matches,
    _partition_identity,
)
from leaders_db.research.corpus_reader_models import BoundEvidence


def _evidence(evidence_id: str, summary: str) -> BoundEvidence:
    return BoundEvidence(
        evidence_id=evidence_id,
        source_id="SRC-1",
        url="https://example.test/source",
        title="Source",
        publisher="Publisher",
        raw_sha256="a" * 64,
        fact_summary=summary,
        question_ids=("1B.1",),
        polarity="context",
        period_fit="2023",
        ruler_attribution="direct",
        limitations=(),
        start_unit=1,
        end_unit=1,
        locator="unit 1",
        exact_excerpt="Exact passage.",
        excerpt_sha256="b" * 64,
        verification_status="accepted",
    )


def test_identity_match_rejects_shifted_digest() -> None:
    first = _evidence("E-1", "First material fact")
    second = _evidence("E-2", "Second material fact")
    shifted = MappingReviewOutput(
        verdicts=(
            MappingVerdict(
                evidence_id=first.evidence_id,
                evidence_digest=_evidence_digest(second),
                question_ids=("1B.1",),
                underlying_fact_key="first fact",
            ),
            MappingVerdict(
                evidence_id=second.evidence_id,
                evidence_digest=_evidence_digest(first),
                question_ids=("1B.2",),
                underlying_fact_key="second fact",
            ),
        )
    )

    assert not _identity_matches((first, second), shifted)


def test_identity_match_accepts_exact_id_digest_pairs() -> None:
    evidence = _evidence("E-1", "One material fact")
    output = MappingReviewOutput(
        verdicts=(
            MappingVerdict(
                evidence_id=evidence.evidence_id,
                evidence_digest=_evidence_digest(evidence),
                question_ids=("1B.1",),
                underlying_fact_key="one fact",
            ),
        )
    )

    assert _identity_matches((evidence,), output)


def test_partial_identity_repair_retains_valid_verdicts() -> None:
    first = _evidence("E-1", "First material fact")
    second = _evidence("E-2", "Second material fact")
    output = MappingReviewOutput(
        verdicts=(
            MappingVerdict(
                evidence_id=first.evidence_id,
                evidence_digest=_evidence_digest(first),
                question_ids=("1B.1",),
                underlying_fact_key="first fact",
            ),
            MappingVerdict(
                evidence_id=second.evidence_id,
                evidence_digest=_evidence_digest(first),
                question_ids=("1B.2",),
                underlying_fact_key="shifted second fact",
            ),
        )
    )

    valid, repair = _partition_identity((first, second), output)

    assert tuple(valid) == ("E-1",)
    assert repair == (second,)
