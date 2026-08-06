from __future__ import annotations

import json
from pathlib import Path

from leaders_db.evidence_funnel.calibration_extraction import normalize_latest_intents
from leaders_db.evidence_funnel.models import SourceDescriptor


def test_recovers_explicit_registry_from_agent_event(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    attempt = tmp_path / "attempt-01-minimax-m3"
    attempt.mkdir()
    (attempt / "output.json").write_text("Completed eight intents.", encoding="utf-8")
    registry = {
        "drafts": [
            {
                "draft_id": "D0001",
                "intent": "Authorities set a deficit target.",
                "question_ids": ["5B.3"],
                "methodology_ids": ["5B.fiscal_rules"],
                "actor": "Government",
                "action": "set a target",
                "mechanism": "annual budget",
                "outcome": "target published",
                "dates": ["2022"],
                "quantities": ["3.8 percent"],
                "attribution": "IMF staff",
                "period_fit": "2022",
                "limitations": "Target, not outturn.",
                "polarity": "neutral",
                "locator_disposition": {
                    "source_id": "LAW-005",
                    "locator": "page 1",
                    "start_segment_id": "S00001",
                    "end_segment_id": "S00003",
                },
            }
        ]
    }
    events = (
        json.dumps({"type": "item.completed", "item": {"type": "reasoning"}})
        + "\n"
        + json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "```json\n" + json.dumps(registry) + "\n```",
                },
            }
        )
        + "\n"
    )
    (attempt / "events.jsonl").write_text(events, encoding="utf-8")

    result = normalize_latest_intents(
        stage_root=tmp_path,
        source=descriptor,
        routed_locators={"page 1"},
        methodology_ids=("5B.3",),
    )

    assert len(result.intents) == 1
    assert result.intents[0].citation.locator == "page 1"
    assert result.intents[0].question_ids == ("5B.3",)


def test_normalizes_m3_draft_intents_dialect(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    attempt = tmp_path / "attempt-01-minimax-m3"
    attempt.mkdir()
    payload = {
        "draft_intents": [
            {
                "draft_id": "D0001",
                "actor": "Government",
                "action": "set a target",
                "mechanism": "annual budget",
                "outcome": "target published",
                "dates": "2022",
                "quantities": None,
                "attribution": "IMF staff",
                "period_fit": "2022",
                "limitations": "Target, not outturn.",
                "polarity": "mixed",
                "methodology_ids": ["5B.3"],
                "citation": {
                    "locator": "page 1",
                    "start_segment_id": "S00001",
                    "end_segment_id": "S00003",
                },
            }
        ]
    }
    (attempt / "output.json").write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_latest_intents(
        stage_root=tmp_path,
        source=descriptor,
        routed_locators={"page 1"},
        methodology_ids=("5B.3",),
    )

    assert result.intents[0].claim.startswith("Government set a target")
    assert result.intents[0].citation.end_segment_id == "S00003"
