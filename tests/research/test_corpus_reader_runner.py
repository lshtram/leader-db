"""Tests for corpus-reader transport partitioning."""

from leaders_db.research.corpus_reader_models import BoundEvidence
from leaders_db.research.corpus_reader_runner import _partition_verification


def _evidence(evidence_id: str, excerpt: str) -> BoundEvidence:
    return BoundEvidence(
        evidence_id=evidence_id,
        source_id="SRC-1",
        url="https://example.test/source",
        title="Source",
        publisher="Publisher",
        raw_sha256="a" * 64,
        fact_summary="One material factual account.",
        question_ids=("1B.1",),
        polarity="context",
        period_fit="2023",
        ruler_attribution="direct",
        limitations=(),
        start_unit=1,
        end_unit=1,
        locator="unit 1",
        exact_excerpt=excerpt,
        excerpt_sha256="b" * 64,
    )


def test_verification_partition_preserves_every_record_once() -> None:
    evidence = tuple(
        _evidence(f"E-{number}", "x" * 80_000) for number in range(1, 6)
    )

    groups = _partition_verification(evidence)

    assert len(groups) == 3
    assert tuple(item for group in groups for item in group) == evidence
