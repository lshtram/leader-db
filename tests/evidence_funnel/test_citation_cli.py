from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_cli_inspect_record_revise_finish_round_trip(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    ledger = tmp_path / "ledger"
    base = [
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
        str(ledger),
    ]
    index = _run(
        root,
        [
            *base,
            "inspect",
            "LAW-005",
            "extracted HTML block 2",
        ],
    )
    first_segment = index["segments"][0]
    second_segment = index["segments"][1]
    intent = json.dumps(
        {
            "schema_version": "evidence_intent_v1",
            "draft_id": "D0001",
            "citation": {
                "source_id": "LAW-005",
                "source_sha256": index["source_sha256"],
                "locator": index["locator"],
                "start_segment_id": first_segment["segment_id"],
                "end_segment_id": first_segment["segment_id"],
            },
            "claim": "The agreement published weekly fuel-tax rates.",
            "claim_type": "legal_status",
            "polarity": "context",
            "actor": "Finance ministry",
            "action": "published fuel-tax rates",
            "mechanism": "official agreement",
            "outcome": "weekly rates took legal form",
            "dates": [],
            "quantities": [],
            "attribution": "Official gazette",
            "period_fit": "Target year",
            "source_limitations": [],
            "question_ids": ["5B.3"],
            "premium_verification_required": False,
        }
    )

    bound = _run(root, [*base, "record", "--json", intent])
    corrected = _run(
        root,
        [
            *base,
            "revise",
            bound["proposal_id"],
            first_segment["segment_id"],
            second_segment["segment_id"],
        ],
    )
    confirmed = _run(root, [*base, "finish", bound["proposal_id"]])

    assert corrected["attempt"] == 2
    assert corrected["intent"]["citation"]["source_id"] == "LAW-005"
    assert corrected["intent"]["citation"]["source_sha256"] == index["source_sha256"]
    assert corrected["intent"]["citation"]["locator"] == index["locator"]
    assert confirmed["excerpt"] == first_segment["text"] + second_segment["text"]
    assert confirmed["excerpt_start_char"] == first_segment["start_char"]
    assert confirmed["excerpt_end_char"] == second_segment["end_char"]
    assert confirmed["verification_status"] == "pending"


def _run(root: Path, command: list[str]) -> dict:
    result = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)
