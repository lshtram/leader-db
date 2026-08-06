from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.calibration import (
    _batches,
    _included_locators,
    _rebase_intents,
)
from leaders_db.evidence_funnel.calibration_extraction import normalize_intent_payload
from leaders_db.evidence_funnel.calibration_review import (
    normalize_review_report,
    reconcile_complete_reviews,
)
from leaders_db.evidence_funnel.calibration_routing import normalize_routing_table
from leaders_db.evidence_funnel.citation_ledger import CitationLedger
from leaders_db.evidence_funnel.citation_models import EvidenceIntent
from leaders_db.evidence_funnel.models import SourceDescriptor


def test_routing_table_normalizer_requires_auditable_explanations(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
## Routing Table
| chunk_id | locator | Decision | Applicable 5B Lenses |
|---|---|---|---|
| U0001 | page 1 | **EXCLUDE** | — |
| U0002 | page 2 | **INCLUDE** | 5B.1, 5B.9 |
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="explanation"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


def test_routing_normalizer_rejects_include_without_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001\n"
        "**Decision:** EXCLUDE\n"
        "**Exclusion Reason:** No economic evidence.\n"
        "---\n"
        "### U0002\n"
        "**Decision:** INCLUDE\n"
        "**Applicable 5B Lenses:** 5B.3, 5B.8\n"
        "---\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="auditable explanation"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


def test_routing_ledger_uses_only_exact_decision_and_lens_fields(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001\n"
        "**Decision:** INCLUDE/EXCLUDE\n"
        "Rationale mentions 5B.1 but has no applicable-lenses field.\n"
        "### U0002\n"
        "**Decision:** INCLUDE\n"
        "**Applicable 5B Lenses:** 5B.8\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="decision"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


def test_routing_fields_do_not_consume_following_lines(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001\n"
        "**Decision:**\n"
        "INCLUDE\n"
        "**Applicable 5B Lenses:** 5B.1\n"
        "### U0002\n"
        "**Decision:** INCLUDE\n"
        "**Applicable 5B Lenses:**\n"
        "Rationale mentions 5B.3.\n"
        "### U0003\n"
        "**Decision:** INCLUDE\n"
        "**Applicable 5B Lenses:** 5B.8\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="heading-decision fields"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002", "U0003"),
        )


def test_intent_normalizer_uses_segment_selection_not_quote_text(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "intents.txt"
    raw.write_text(
        "```json\n"
        + json.dumps(
            {
                "intents": [
                    {
                        "intent_id": "D0001",
                        "question_ids": ["5B.3", "8B.1"],
                        "intent_narrative": "Government stabilized fuel prices.",
                        "actor": "Government",
                        "action": "stabilized prices",
                        "mechanism": "fuel subsidy",
                        "outcome": "lower retail prices",
                        "period_fit": "2022",
                        "limitations": "Untargeted.",
                        "polarity": "mixed",
                        "locator": "page 19",
                        "segment_id_start": "S00002",
                        "segment_id_end": "S00003",
                    }
                ]
            }
        )
        + "\n```",
        encoding="utf-8",
    )

    result = normalize_intent_payload(
        raw_path=raw,
        source=descriptor,
        routed_locators={"page 19"},
        methodology_ids=tuple(f"5B.{number}" for number in range(1, 11)),
    )

    intent = result.intents[0]
    assert intent.claim == "Government stabilized fuel prices."
    assert intent.question_ids == ("5B.3",)
    assert intent.citation.start_segment_id == "S00002"
    assert intent.citation.end_segment_id == "S00003"
    assert "excerpt" not in intent.model_dump()


def test_intent_normalizer_preserves_explicit_subject_predicate_schema(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "intents.txt"
    raw.write_text(
        json.dumps(
            {
                "intents": [
                    {
                        "intent_id": "D0001",
                        "locator_disposition": {
                            "locator": "page 19",
                            "segment_ids": ["S00002", "S00003"],
                            "sha256": descriptor.source_sha256,
                        },
                        "question_ids": ["5B.3", "6B.1"],
                        "subject": "Government",
                        "predicate_action": "stabilized",
                        "object": "retail fuel prices",
                        "mechanism": "excise adjustment",
                        "outcome": "lower price pass-through",
                        "date": "2022",
                        "limitations": "Incidence was unequal.",
                        "polarity": "mixed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = normalize_intent_payload(
        raw_path=raw,
        source=descriptor,
        routed_locators={"page 19"},
        methodology_ids=tuple(f"5B.{number}" for number in range(1, 11)),
    )

    intent = result.intents[0]
    assert intent.claim == (
        "Government stabilized retail fuel prices. lower price pass-through."
    )
    assert intent.actor == "Government"
    assert intent.action == "stabilized"
    assert intent.period_fit == "2022"
    assert intent.question_ids == ("5B.3",)


def test_intent_normalizer_preserves_sparse_claim_without_inventing_semantics(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "intents.txt"
    raw.write_text(
        json.dumps(
            {
                "intents": [
                    {
                        "draft_id": "D0001",
                        "locator_disposition": [
                            {
                                "locator": "page 19",
                                "segment_ids": ["S00002"],
                                "frozen_source_hash": descriptor.source_sha256,
                            }
                        ],
                        "intent": "The platform proposed a fuel-price measure.",
                        "applicable_questions": ["5B.3", "6B.1"],
                        "period_fit": "2018 campaign commitment.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = normalize_intent_payload(
        raw_path=raw,
        source=descriptor,
        routed_locators={"page 19"},
        methodology_ids=tuple(f"5B.{number}" for number in range(1, 11)),
    )

    intent = result.intents[0]
    assert intent.claim == "The platform proposed a fuel-price measure."
    assert intent.actor == "[not separately decomposed]"
    assert intent.mechanism == "[not separately decomposed]"
    assert intent.question_ids == ("5B.3",)
    assert "did not separately decompose" in intent.source_limitations[0]


def test_intent_normalizer_rejects_ambiguous_multiple_dispositions(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "intents.txt"
    raw.write_text(
        json.dumps(
            {
                "intents": [
                    {
                        "draft_id": "D0001",
                        "locator": "page 19",
                        "segment_ids": ["S00002"],
                        "locator_disposition": [
                            {"locator": "page 19", "segment_ids": ["S00002"]},
                            {"locator": "page 20", "segment_ids": ["S00001"]},
                        ],
                        "intent": "A tempting top-level claim.",
                        "applicable_questions": ["5B.3"],
                        "period_fit": "2022",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no in-scope intents"):
        normalize_intent_payload(
            raw_path=raw,
            source=descriptor,
            routed_locators={"page 19", "page 20"},
            methodology_ids=tuple(f"5B.{number}" for number in range(1, 11)),
        )


def test_review_normalizer_rejects_accept_label_with_unsupported_issue(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        "## Review Summary\n"
        "| evidence_id | Status | Key Issue |\n"
        "|---|---|---|\n"
        f"| {candidate.evidence_id} | **ACCEPT** | Quantity not in excerpt |\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "rejected"
    assert result.reviews[0].unsupported_elements


def test_review_normalizer_reads_fenced_object_and_rejects_partial_acceptance(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    payload = {
        "reviews": [
            {
                "evidence_id": candidate.evidence_id,
                "verdict": "accept",
                "assessment": (
                    "The first clause is confirmed, but the second is not visible "
                    "in the excerpt. Partial acceptance on the available text."
                ),
            }
        ]
    }
    raw = tmp_path / "review.md"
    raw.write_text(f"```json\n{json.dumps(payload)}\n```\n", encoding="utf-8")

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "rejected"
    assert result.reviews[0].unsupported_elements


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "accept", "verdict": "reject", "assessment": "Unsupported."},
        {
            "verdict": "accept",
            "note": "Fully supported.",
            "assessment": "The second clause is not visible; partial support.",
        },
        {"verdict": "accept", "assessment": {"result": "supported"}},
    ],
)
def test_review_normalizer_rejects_conflicting_or_non_text_aliases(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
    extra: dict[str, object],
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    row: dict[str, object] = {"evidence_id": candidate.evidence_id, **extra}
    raw = tmp_path / "review.json"
    raw.write_text(json.dumps({"reviews": [row]}), encoding="utf-8")

    with pytest.raises(ValueError):
        normalize_review_report(raw_path=raw, candidates=(candidate,))


def test_review_normalizer_rejects_explicit_partial_verdict(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id}\n\n"
        "**Assessment — PARTIAL / ATTRIBUTION OVERSTATEMENT:**\n\n"
        "The action is supported, but the characterization belongs to commentators.\n\n"
        "**Verdict:** `partial`\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "rejected"
    assert result.reviews[0].unsupported_elements


def test_review_normalizer_rejects_partial_section_verdict(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id} — **PARTIAL**\n"
        "The action is supported but its attribution is overstated.\n---\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "rejected"


def test_review_normalizer_accepts_heading_with_bare_bold_verdict(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id}\n"
        "**ACCEPT.**\n"
        "The claim, attribution, and quantity are directly supported.\n---\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "accepted"


@pytest.mark.parametrize(
    "body",
    [
        "**Assessment:** ACCEPT\nThe opening view.\n**REJECT.**\nFinal verdict.",
        "**ACCEPT.**\nFirst verdict.\n**REJECT.**\nSecond verdict.",
    ],
)
def test_review_normalizer_rejects_conflicting_section_verdicts(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
    body: str,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id}\n{body}\n---\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="verdicts conflict"):
        normalize_review_report(raw_path=raw, candidates=(candidate,))


@pytest.mark.parametrize("word", ["ACCEPTABLE", "PARTIALLY"])
def test_review_normalizer_does_not_prefix_match_verdict(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
    word: str,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id}\n\n**Verdict:** {word}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="accounting mismatch"):
        normalize_review_report(raw_path=raw, candidates=(candidate,))


def test_bounded_batches_preserve_order_without_loss() -> None:
    items = tuple(range(23))

    batches = _batches(items, 10)

    assert tuple(item for batch in batches for item in batch) == items
    assert all(len(batch) <= 10 for batch in batches)


def test_included_locators_preserve_source_order() -> None:
    units = tuple(
        {"chunk_id": f"U{number:04d}", "locator": f"page {number}", "text": ""}
        for number in (1, 2, 10, 11)
    )
    assert _included_locators(
        units,
        frozenset(str(item["chunk_id"]) for item in units),
    ) == (
        "page 1",
        "page 2",
        "page 10",
        "page 11",
    )


def test_batched_intents_receive_source_global_draft_ids(
    intent: EvidenceIntent,
) -> None:
    second_batch = _rebase_intents((intent,), 10)

    assert second_batch[0].draft_id == "D0011"


def test_review_section_rejects_unsupported_accept_label(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"### {candidate.evidence_id} — **ACCEPT**\n\n"
        "**Verdict:** The date is absent from the bound passage.\n\n"
        "---\n### Summary\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "rejected"


def test_review_attempt_disagreement_escalates(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    for number, status in enumerate(("ACCEPT", "REJECT"), start=1):
        attempt = tmp_path / f"attempt-{number:02d}-reviewer"
        attempt.mkdir()
        (attempt / "output.json").write_text(
            "## Review Summary\n"
            "| evidence_id | Status | Key Issue |\n"
            "|---|---|---|\n"
            f"| {candidate.evidence_id} | **{status}** | Explicit verdict. |\n",
            encoding="utf-8",
        )

    result = reconcile_complete_reviews(tmp_path, (candidate,))

    assert result.reviews[0].status == "escalated"


def test_review_normalizer_accepts_explicit_arrow_verdict(
    tmp_path: Path,
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    raw = tmp_path / "review.md"
    raw.write_text(
        f"**{candidate.evidence_id} → ACCEPT**\n"
        "The bound excerpt supports the complete claim.\n"
        "\n---\n",
        encoding="utf-8",
    )

    result = normalize_review_report(raw_path=raw, candidates=(candidate,))

    assert result.reviews[0].status == "accepted"
