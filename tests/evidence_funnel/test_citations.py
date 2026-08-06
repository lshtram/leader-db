from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.artifacts import canonical_json_bytes, sha256_bytes
from leaders_db.evidence_funnel.citation_index import (
    CitationIndexError,
    FrozenCitationIndex,
)
from leaders_db.evidence_funnel.citation_ledger import (
    CitationLedger,
    CitationLedgerError,
)
from leaders_db.evidence_funnel.citation_models import (
    CitationAttemptBinding,
    CitationSelection,
    EvidenceIntent,
)
from leaders_db.evidence_funnel.ingest import FrozenExtraction


def test_index_segments_preserve_source_bytes(extraction: FrozenExtraction) -> None:
    index = FrozenCitationIndex((extraction,), segment_characters=80)

    locator = index.locator_index("LAW-005", "page 1")

    assert "".join(item.text for item in locator.segments) == extraction.units[0].text
    assert all(
        extraction.units[0].text[item.start_char : item.end_char] == item.text
        for item in locator.segments
    )


def test_span_binding_includes_intervening_text_instead_of_splicing(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    draft = ledger.bind(intent)

    assert "Untargeted subsidies mitigated living costs." in draft.exact_excerpt
    assert draft.exact_excerpt == (
        "The deficit target was 3.8 percent of GDP. "
        "Untargeted subsidies mitigated living costs. "
        "Gross debt was about 56 percent of GDP."
    )


def test_bound_record_is_exactly_what_the_ledger_returns(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    draft = ledger.bind(intent)

    stored = json.loads(
        (
            tmp_path
            / "ledger"
            / "proposals"
            / draft.proposal_id
            / "attempt-01.json"
        ).read_text(encoding="utf-8")
    )

    assert stored == draft.model_dump(mode="json")


def test_correction_is_bounded_to_three_attempts(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    first = ledger.bind(intent)
    ledger.bind(intent, proposal_id=first.proposal_id)
    ledger.bind(intent, proposal_id=first.proposal_id)

    with pytest.raises(CitationLedgerError, match="3-attempt limit"):
        ledger.bind(intent, proposal_id=first.proposal_id)


def test_correction_cannot_change_source_identity(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    first = ledger.bind(intent)
    changed = intent.model_copy(
        update={
            "citation": intent.citation.model_copy(update={"source_id": "BOOK-013"})
        }
    )

    with pytest.raises(CitationLedgerError, match="cannot change source"):
        ledger.bind(changed, proposal_id=first.proposal_id)


def test_span_correction_cannot_change_claim_or_question_mapping(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    first = ledger.bind(intent)
    changed = intent.model_copy(
        update={"claim": "Different claim", "question_ids": ("5B.9",)}
    )

    with pytest.raises(CitationLedgerError, match="cannot change the semantic"):
        ledger.bind(changed, proposal_id=first.proposal_id)


def test_confirmation_creates_v2_candidate_with_exact_offsets(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    extraction: FrozenExtraction,
) -> None:
    draft = ledger.bind(intent)

    candidate = ledger.confirm(draft.proposal_id)

    assert candidate.schema_version == "evidence_candidate_v2"
    assert candidate.excerpt == extraction.units[0].text
    assert candidate.excerpt_start_char == 0
    assert candidate.excerpt_end_char == len(extraction.units[0].text)
    assert candidate.verification_status == "pending"


def test_confirmation_is_idempotent_after_terminal_decision(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    draft = ledger.bind(intent)
    first = ledger.confirm(draft.proposal_id)

    second = ledger.confirm(draft.proposal_id)

    assert second == first


def test_confirmation_writes_candidate_before_terminal_decision_and_can_retry(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = ledger.bind(intent)
    original = ledger._store.write_immutable
    failed = False

    def fail_decision_once(relative_path, value):
        nonlocal failed
        if relative_path.endswith("decision.json") and not failed:
            failed = True
            raise OSError("simulated decision write failure")
        return original(relative_path, value)

    monkeypatch.setattr(ledger._store, "write_immutable", fail_decision_once)
    with pytest.raises(OSError, match="simulated"):
        ledger.confirm(draft.proposal_id)

    assert list((tmp_path / "ledger" / "confirmed").glob("*.json"))
    candidate = ledger.confirm(draft.proposal_id)
    assert candidate.evidence_id


def test_binding_write_failure_can_retry_without_stranding_proposal(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ledger._store.write_immutable
    failed = False

    def fail_binding_once(relative_path, value):
        nonlocal failed
        if relative_path.endswith(".binding.json") and not failed:
            failed = True
            raise OSError("simulated binding write failure")
        return original(relative_path, value)

    monkeypatch.setattr(ledger._store, "write_immutable", fail_binding_once)
    with pytest.raises(OSError, match="simulated"):
        ledger.bind(intent)

    draft = ledger.bind(intent)
    assert draft.attempt == 1


def test_attempt_write_failure_blocks_decision_and_same_intent_recovers(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ledger.bind(intent)
    original = ledger._store.write_immutable
    failed = False

    def fail_attempt_once(relative_path, value):
        nonlocal failed
        if relative_path.endswith("attempt-02.json") and not failed:
            failed = True
            raise OSError("simulated attempt write failure")
        return original(relative_path, value)

    monkeypatch.setattr(ledger._store, "write_immutable", fail_attempt_once)
    with pytest.raises(OSError, match="simulated"):
        ledger.bind(intent, proposal_id=first.proposal_id)
    with pytest.raises(CitationLedgerError, match="incomplete attempt"):
        ledger.confirm(first.proposal_id)
    with pytest.raises(CitationLedgerError, match="incomplete attempt"):
        ledger.discard(first.proposal_id, "must not discard stale attempt")

    recovered = ledger.bind(intent, proposal_id=first.proposal_id)
    assert recovered.attempt == 2
    assert ledger.confirm(first.proposal_id).excerpt == recovered.exact_excerpt


def test_confirmation_rejects_semantically_tampered_attempt(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    draft = ledger.bind(intent)
    attempt_path = (
        tmp_path
        / "ledger"
        / "proposals"
        / draft.proposal_id
        / "attempt-01.json"
    )
    payload = json.loads(attempt_path.read_text(encoding="utf-8"))
    payload["intent"]["claim"] = "A substituted claim"
    attempt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CitationLedgerError, match="hash chain is invalid"):
        ledger.confirm(draft.proposal_id)


def test_confirmation_rejects_tampered_or_injected_attempt(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    draft = ledger.bind(intent)
    attempt_path = (
        tmp_path
        / "ledger"
        / "proposals"
        / draft.proposal_id
        / "attempt-01.json"
    )
    payload = json.loads(attempt_path.read_text(encoding="utf-8"))
    payload["exact_excerpt"] = "X" + payload["exact_excerpt"][1:]
    attempt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CitationLedgerError, match="differs from the frozen"):
        ledger.confirm(draft.proposal_id)


def test_confirmation_rejects_nonsequential_injected_attempt(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    draft = ledger.bind(intent)
    proposal_dir = tmp_path / "ledger" / "proposals" / draft.proposal_id
    injected = draft.model_copy(update={"attempt": 99})
    (proposal_dir / "attempt-99.json").write_text(
        injected.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(CitationLedgerError, match="not sequential"):
        ledger.confirm(draft.proposal_id)


def test_confirmed_or_discarded_proposal_cannot_be_redecided(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    confirmed = ledger.bind(intent)
    ledger.confirm(confirmed.proposal_id)
    with pytest.raises(CitationLedgerError, match="already has a decision"):
        ledger.discard(confirmed.proposal_id, "late reversal")
    with pytest.raises(CitationLedgerError, match="already has a decision"):
        ledger.bind(intent, proposal_id=confirmed.proposal_id)


def test_discarded_proposal_cannot_be_confirmed(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    draft = ledger.bind(intent)
    ledger.discard(draft.proposal_id, "not material")

    with pytest.raises(CitationLedgerError, match="was discarded"):
        ledger.confirm(draft.proposal_id)


def test_confirmation_rejects_decision_copied_from_another_proposal(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    first = ledger.bind(intent)
    ledger.confirm(first.proposal_id)
    second_intent = intent.model_copy(update={"draft_id": "D0002"})
    second = ledger.bind(second_intent)
    proposals = tmp_path / "ledger" / "proposals"
    shutil.copyfile(
        proposals / first.proposal_id / "decision.json",
        proposals / second.proposal_id / "decision.json",
    )

    with pytest.raises(CitationLedgerError, match="does not match latest attempt"):
        ledger.confirm(second.proposal_id)


def test_idempotent_confirmation_checks_complete_candidate_semantics(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    draft = ledger.bind(intent)
    ledger.confirm(draft.proposal_id)
    proposal_dir = tmp_path / "ledger" / "proposals" / draft.proposal_id
    attempt_path = proposal_dir / "attempt-01.json"
    attempt_payload = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt_payload["intent"]["actor"] = "Substituted actor"
    attempt_path.write_bytes(canonical_json_bytes(attempt_payload))
    binding = CitationAttemptBinding(
        proposal_id=draft.proposal_id,
        attempt=1,
        attempt_sha256=sha256_bytes(attempt_path.read_bytes()),
    )
    binding_path = proposal_dir / "attempt-01.binding.json"
    binding_path.write_bytes(canonical_json_bytes(binding))
    decision_path = proposal_dir / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["binding_sha256"] = sha256_bytes(binding_path.read_bytes())
    decision_path.write_bytes(canonical_json_bytes(decision))

    with pytest.raises(CitationLedgerError, match="differs from bound attempt"):
        ledger.confirm(draft.proposal_id)


def test_proposal_id_cannot_escape_ledger_root(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    with pytest.raises(CitationLedgerError, match="invalid proposal ID"):
        ledger.bind(intent, proposal_id="../../outside")


def test_invalid_source_hash_or_segment_is_rejected(
    extraction: FrozenExtraction,
) -> None:
    index = FrozenCitationIndex((extraction,), segment_characters=80)
    selection = CitationSelection(
        source_id="LAW-005",
        source_sha256="b" * 64,
        locator="page 1",
        start_segment_id="S00001",
        end_segment_id="S00001",
    )
    with pytest.raises(CitationIndexError, match="source hash changed"):
        index.resolve(selection)


@pytest.mark.slow
def test_cli_can_return_a_real_frozen_locator_index(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/experiments/run_citation_writer.py",
            "--config",
            "configs/evidence-funnel/amlo-2022-5b-v2.json",
            "--frozen-root",
            (
                "research/conversational-evidence/"
                "amlo-2022-5b-document-reader-ab-v1/run-13/frozen"
            ),
            "--ledger",
            str(tmp_path / "ledger"),
                "inspect",
            "LAW-005",
            "extracted HTML block 2",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["source_id"] == "LAW-005"
    assert payload["segments"]
