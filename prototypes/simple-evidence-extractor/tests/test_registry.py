from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from simple_evidence.registry import Registry
from simple_evidence.source import load_sources


def test_feedback_lifecycle_and_materialization(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1",
        start=1,
        end=1,
        summary="Rule A was adopted in 2022.",
    )
    corrected = registry.correct(
        proposed.fact_id,
        end=2,
        summary="The authority adopted Rule A and reduced the fee to 3 percent.",
        chapters=["5B", "8B"],
        fact_type="observed_fact",
        period_fit="target",
    )

    assert corrected.excerpt.endswith("3 percent.")
    extractor = registry.confirm(proposed.fact_id, "extractor")
    assert extractor.disposition == "ready_for_review"
    accepted = registry.confirm(proposed.fact_id, "reviewer")
    assert accepted.disposition == "accepted"

    counts = registry.materialize(tmp_path / "output")
    row = json.loads((tmp_path / "output/evidence.jsonl").read_text())
    assert counts == {"accepted": 1, "rejected": 0, "pending": 0}
    assert row["chapters"] == ["5B", "8B"]
    assert row["excerpt"] == corrected.excerpt
    assert row["proposal_id"] == proposed.fact_id
    assert row["evidence_id"].startswith("E-")
    assert row["source"]["publisher"] == "Example Publisher"


def test_reviewer_can_reject_with_auditable_reason(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1",
        start=1,
        end=None,
        summary="Unsupported causal conclusion.",
    )
    registry.confirm(proposed.fact_id, "extractor")
    registry.correct(
        proposed.fact_id,
        fact_type="rejected",
        summary="The excerpt does not support causation.",
    )
    rejected = registry.confirm(proposed.fact_id, "reviewer")

    assert rejected.disposition == "rejected"


def test_stops_after_three_binding_attempts(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1", start=1, end=None, summary="First summary."
    )
    registry.correct(proposed.fact_id, summary="Second summary.")
    registry.correct(proposed.fact_id, summary="Third summary.")

    with pytest.raises(ValueError, match="3-attempt"):
        registry.correct(proposed.fact_id, summary="Fourth summary.")

    reviewed = registry.correct(
        proposed.fact_id,
        role="reviewer",
        summary="Reviewer correction.",
    )
    assert reviewed.reviewer_attempts == 1


def test_command_error_does_not_damage_prior_events(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1", start=1, end=None, summary="Stored fact."
    )

    with pytest.raises(ValueError, match="unknown manifest"):
        registry.add(source_id="../escape", start=1, end=None, summary="Bad")

    assert registry.states()[proposed.fact_id].summary == "Stored fact."


def test_finalized_confirmation_is_idempotent_across_overlap(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1",
        start=1,
        end=None,
        summary="Stored fact.",
        window_id="window-1",
    )
    registry.confirm(proposed.fact_id, "extractor")
    registry.confirm(proposed.fact_id, "reviewer")
    duplicate = registry.add(
        source_id="DOC-1",
        start=1,
        end=None,
        summary="Stored fact.",
        window_id="window-2",
    )

    result = registry.confirm(duplicate.fact_id, "extractor")
    assert result.disposition == "accepted"
    assert registry.facts_for_window("window-2") == {proposed.fact_id}


def test_window_ownership_retains_interrupted_pending_fact(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    proposed = registry.add(
        source_id="DOC-1",
        start=1,
        end=None,
        summary="Interrupted fact.",
        window_id="window-1",
    )

    assert registry.facts_for_window("window-1") == {proposed.fact_id}
    assert not registry.states()[proposed.fact_id].extractor_confirmed


def test_concurrent_adds_are_serialized(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.jsonl"
    sources = load_sources(manifest_path)

    def add_fact(_: int) -> str:
        return Registry(registry_path, sources).add(
            source_id="DOC-1",
            start=1,
            end=None,
            summary="Concurrent fact.",
            window_id="window-1",
        ).fact_id

    with ThreadPoolExecutor(max_workers=6) as executor:
        fact_ids = list(executor.map(add_fact, range(12)))

    registry = Registry(registry_path, sources)
    assert len(set(fact_ids)) == 1
    assert len(registry.states()) == 1
    assert len(registry.events()) == 12


def test_registry_detects_tampered_excerpt(
    manifest_path: Path, tmp_path: Path
) -> None:
    path = tmp_path / "registry.jsonl"
    registry = Registry(path, load_sources(manifest_path))
    registry.add(source_id="DOC-1", start=1, end=None, summary="Fact.")
    event = json.loads(path.read_text())
    event["state"]["excerpt"] = "fabricated"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source binding changed"):
        registry.states()


def test_registry_detects_changed_source(
    manifest_path: Path, tmp_path: Path
) -> None:
    path = tmp_path / "registry.jsonl"
    registry = Registry(path, load_sources(manifest_path))
    registry.add(source_id="DOC-1", start=1, end=None, summary="Fact.")
    (manifest_path.parent / "source.json").write_text(
        json.dumps({"units": [{"locator": "page 1", "text": "Changed."}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source binding changed"):
        Registry(path, load_sources(manifest_path)).states()


def test_add_rejects_numbers_absent_from_exact_excerpt(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    with pytest.raises(ValueError, match="numbers absent"):
        registry.add(
            source_id="DOC-1",
            start=1,
            end=None,
            summary="The source reports 99 percent.",
        )


def test_add_rejects_unsupported_signature_claim(
    manifest_path: Path, tmp_path: Path
) -> None:
    registry = Registry(tmp_path / "registry.jsonl", load_sources(manifest_path))
    with pytest.raises(ValueError, match="legal-action terms"):
        registry.add(
            source_id="DOC-1",
            start=1,
            end=None,
            summary="The official signed Rule A.",
        )

    assigned = registry.add(
        source_id="DOC-1",
        start=1,
        end=None,
        summary="The authority assigned Rule A.",
    )
    assert assigned.summary.startswith("The authority assigned")
