"""Cross-stage accounting checks for the bounded calibration."""

from __future__ import annotations

from .config import EvidenceFunnelConfig
from .low_cost import EvidenceIntentBatch, RoutingDecisionBatch, SemanticReviewBatch
from .models import EvidenceCandidate, SourceDescriptor


def validate_routing(
    routing: RoutingDecisionBatch,
    units: tuple[dict[str, object], ...],
) -> None:
    expected = {str(item["chunk_id"]) for item in units}
    actual = {item.chunk_id for item in routing.decisions}
    if actual != expected:
        raise ValueError(
            f"router chunk accounting mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def validate_intents(
    batch: EvidenceIntentBatch,
    locators: set[object],
    source: SourceDescriptor,
) -> None:
    expected_locators = {str(item) for item in locators}
    dispositions = {item.locator for item in batch.locator_dispositions}
    if dispositions != expected_locators:
        raise ValueError("extractor locator accounting mismatch")
    if batch.inspected_locator_count != len(expected_locators):
        raise ValueError("extractor inspected locator count mismatch")
    for intent in batch.intents:
        if (
            intent.citation.source_id != source.source_id
            or intent.citation.source_sha256 != source.source_sha256
            or intent.citation.locator not in expected_locators
        ):
            raise ValueError("extractor citation escapes routed frozen source")


def validate_reviews(
    reviews: SemanticReviewBatch,
    candidates: tuple[EvidenceCandidate, ...],
) -> None:
    expected = {item.evidence_id for item in candidates}
    actual = {item.evidence_id for item in reviews.reviews}
    if actual != expected:
        raise ValueError("semantic reviewer evidence accounting mismatch")


def mechanical_failures(
    *,
    config: EvidenceFunnelConfig,
    accepted: list[EvidenceCandidate],
    rejected: list[str],
    escalated: list[str],
    coverage: dict[str, int],
) -> list[str]:
    failures: list[str] = []
    total = len(accepted) + len(rejected) + len(escalated)
    rejection_rate = len(rejected) / total if total else 1.0
    if not accepted:
        failures.append("no evidence survived semantic verification")
    if rejection_rate > config.verification.maximum_semantic_rejection_rate:
        failures.append(f"semantic rejection rate {rejection_rate:.3f} exceeds threshold")
    return failures


__all__ = [
    "mechanical_failures",
    "validate_intents",
    "validate_reviews",
    "validate_routing",
]
