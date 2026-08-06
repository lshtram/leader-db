from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.citation_ledger import (
    CitationLedger,
    CitationLedgerError,
)
from leaders_db.evidence_funnel.citation_models import EvidenceIntent


def test_bind_and_confirm_is_idempotent(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    first = ledger.bind_and_confirm(intent)
    second = ledger.bind_and_confirm(intent)

    assert second == first


def test_bind_and_confirm_rejects_changed_resume_intent(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    ledger.bind_and_confirm(intent)
    changed = intent.model_copy(update={"claim": "Changed after persistence"})

    with pytest.raises(CitationLedgerError, match="differs from requested resume"):
        ledger.bind_and_confirm(changed)


def test_confirmed_intents_revalidates_candidate_hash(
    ledger: CitationLedger,
    intent: EvidenceIntent,
    tmp_path: Path,
) -> None:
    candidate = ledger.bind_and_confirm(intent)
    path = tmp_path / "ledger" / "confirmed" / f"{candidate.evidence_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["claim"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CitationLedgerError, match="changed or is missing"):
        ledger.confirmed_intents()


def test_confirmed_intents_returns_only_confirmed_records(
    ledger: CitationLedger,
    intent: EvidenceIntent,
) -> None:
    ledger.bind(intent.model_copy(update={"draft_id": "D0002"}))
    ledger.bind_and_confirm(intent)

    assert ledger.confirmed_intents() == (intent,)
