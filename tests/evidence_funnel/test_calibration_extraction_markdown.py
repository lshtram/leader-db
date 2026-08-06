from __future__ import annotations

from pathlib import Path

import pytest

from leaders_db.evidence_funnel.calibration_extraction_markdown import (
    normalize_m3_markdown,
)
from leaders_db.evidence_funnel.models import SourceDescriptor


def test_normalizes_explicit_m3_locator_handoff(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "output.md"
    raw.write_text(
        "### D0001 — Authorities set a deficit target\n"
        "- **actor**: Government\n"
        "- **action**: set a deficit target\n"
        "- **mechanism**: annual budget\n"
        "- **outcome**: deficit target was published\n"
        "- **dates**: 2022\n"
        "- **quantities**: 3.8 percent of GDP\n"
        "- **attribution**: IMF staff\n"
        "- **period fit**: target year\n"
        "- **limitations**: target, not realized\n"
        "- **polarity**: mixed\n"
        "- **methodology IDs**: 5B.3, 8B.1\n"
        "- **source**: LAW-005\n"
        "- **locator**: page 1\n"
        "- **inclusive segments**: S00001–S00003\n",
        encoding="utf-8",
    )

    result = normalize_m3_markdown(
        raw_path=raw,
        source=descriptor,
        routed_locators={"page 1"},
        methodology_ids=tuple(f"5B.{number}" for number in range(1, 11)),
    )

    assert result is not None
    assert len(result.intents) == 1
    intent = result.intents[0]
    assert intent.claim == "Authorities set a deficit target"
    assert intent.question_ids == ("5B.3",)
    assert intent.citation.start_segment_id == "S00001"
    assert intent.citation.end_segment_id == "S00003"


def test_rejects_m3_handoff_outside_routed_locators(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "output.md"
    raw.write_text(
        "### D0001 — Claim\n"
        "- **actor**: Government\n"
        "- **action**: acted\n"
        "- **mechanism**: policy\n"
        "- **outcome**: result\n"
        "- **dates**: 2022\n"
        "- **quantities**: none\n"
        "- **attribution**: IMF\n"
        "- **period fit**: 2022\n"
        "- **limitations**: none\n"
        "- **polarity**: neutral\n"
        "- **methodology IDs**: 5B.3\n"
        "- **source**: LAW-005\n"
        "- **locator**: page 9\n"
        "- **inclusive segments**: S00001-S00001\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside the routed batch"):
        normalize_m3_markdown(
            raw_path=raw,
            source=descriptor,
            routed_locators={"page 1"},
            methodology_ids=("5B.3",),
        )


def test_normalizes_loose_m3_draft_handoff(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "output.md"
    raw.write_text(
        "<drafts>\n\n"
        "**D0001**\n"
        "- chapter_id: 5B\n"
        "- question_id: 5B.3\n"
        "- actor: Government\n"
        "- action: Set a target\n"
        "- mechanism: Annual budget\n"
        "- outcome: Target published\n"
        "- dates: 2022\n"
        "- quantities: 3.8 percent\n"
        "- attribution: IMF staff\n"
        "- period_fit: 2022\n"
        "- limitations: Target, not outturn\n"
        "- polarity: Mixed\n"
        "- locator: page 1\n"
        "- segment_range: S00001–S00003\n"
        f"- source_sha256: {descriptor.source_sha256}\n\n"
        "</drafts>\n",
        encoding="utf-8",
    )

    result = normalize_m3_markdown(
        raw_path=raw,
        source=descriptor,
        routed_locators={"page 1"},
        methodology_ids=("5B.3",),
    )

    assert result is not None
    assert result.intents[0].question_ids == ("5B.3",)
    assert result.intents[0].citation.start_segment_id == "S00001"
