from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from leaders_db.evidence_funnel.artifacts import ArtifactStore
from leaders_db.evidence_funnel.config import load_evidence_funnel_config
from leaders_db.evidence_funnel.execution_models import StageExecutionResult
from leaders_db.evidence_funnel.execution_resume import execute_or_resume_bound_stage


class TinyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


def test_config_owns_citation_segmentation_and_attempt_limit() -> None:
    config = load_evidence_funnel_config()

    assert config.citations.segment_characters == 240
    assert config.citations.maximum_binding_attempts == 3
    assert "exact excerpt" not in config.prompts["extraction"]
    assert "Do not reproduce or author quotation text" in config.prompts["extraction"]
    assert config.phase_order[3:7] == (
        "intent_extraction",
        "citation_binding",
        "citation_confirmation",
        "semantic_verification",
    )


def test_immutable_write_recovers_from_stale_pending_file(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    pending = tmp_path / "records" / "item.json.pending"
    pending.parent.mkdir(parents=True)
    pending.write_text('{"partial":', encoding="utf-8")

    store.write_immutable("records/item.json", {"complete": True})

    assert (tmp_path / "records" / "item.json").read_text(encoding="utf-8") == (
        '{"complete":true}\n'
    )


def test_bound_resume_is_atomic_and_rejects_changed_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "stage"
    profiles_path = root / "configs/research-models.yaml"
    calls = 0

    def fake_execute_stage(**_: object) -> StageExecutionResult:
        nonlocal calls
        calls += 1
        attempt = output_dir / "attempt-01-minimax-m3-long-context"
        attempt.mkdir(parents=True)
        output = attempt / "output.json"
        events = attempt / "events.jsonl"
        stderr = attempt / "stderr.txt"
        output.write_text('{"value":"stored"}', encoding="utf-8")
        events.write_text(
            '{"type":"turn.completed","usage":{"input_tokens":2,'
            '"output_tokens":1,"total_tokens":3}}\n',
            encoding="utf-8",
        )
        stderr.write_text("", encoding="utf-8")
        return StageExecutionResult(
            output_path=output,
            events_path=events,
            stderr_path=stderr,
            input_tokens=2,
            output_tokens=1,
            total_tokens=3,
            model_profile="minimax-m3-long-context",
            attempt=1,
        )

    monkeypatch.setattr(
        "leaders_db.evidence_funnel.execution.execute_stage",
        fake_execute_stage,
    )
    config = load_evidence_funnel_config()
    arguments = {
        "project_root": root,
        "config": config,
        "stage": "extraction",
        "prompt": "original",
        "output_model": TinyOutput,
        "output_dir": output_dir,
        "profiles_path": profiles_path,
    }

    first = execute_or_resume_bound_stage(**arguments)
    second = execute_or_resume_bound_stage(**arguments)

    assert first.output_path == second.output_path
    assert calls == 1
    with pytest.raises(ValueError, match="resume binding mismatch"):
        execute_or_resume_bound_stage(**{**arguments, "prompt": "changed"})
