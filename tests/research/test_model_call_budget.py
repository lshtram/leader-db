from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from leaders_db.research.corpus_reader_runner import (
    _load_or_execute_json,
    execute_json_model,
)
from leaders_db.research.model_call_budget import StageBudget, StageBudgetTracker


class _FixtureOutput(BaseModel):
    value: str


def _tracker(**overrides: int) -> StageBudgetTracker:
    values = {
        "max_calls": 2,
        "max_request_characters": 10_000,
        "max_request_input_tokens": 10_000,
        "max_stage_input_tokens": 10_000,
    }
    values.update(overrides)
    return StageBudgetTracker(
        stage="fixture_stage",
        budget=StageBudget(**values),
        config_sha256="a" * 64,
    )


def test_budget_measures_complete_request_and_reserves_normal_call(tmp_path: Path) -> None:
    tracker = _tracker()
    schema = _FixtureOutput.model_json_schema()

    reservation = tracker.reserve(
        component="normal",
        prompt="A short prompt",
        response_schema=schema,
        output_dir=tmp_path,
    )

    assert reservation["decision"] == "reserved"
    assert reservation["request_characters"] == len("A short prompt") + len(
        json.dumps(schema, ensure_ascii=False, sort_keys=True)
    )
    assert tracker.calls_reserved == 1
    assert not (tmp_path / "budget-stop.json").exists()
    assert json.loads((tmp_path / "budget-reservation.json").read_text()) == reservation


def test_stage_specific_output_allowance_overrides_model_maximum() -> None:
    budget = StageBudget(
        max_calls=1,
        max_request_characters=1_000,
        max_request_input_tokens=1_000,
        max_stage_input_tokens=1_000,
        max_request_output_tokens=12_500,
    )

    assert budget.output_allowance("gpt-5.6-luna") == 12_500


@pytest.mark.parametrize(
    ("overrides", "prompt", "reason"),
    [
        ({"max_request_characters": 1}, "oversized", "request_characters"),
        ({"max_request_input_tokens": 1}, "oversized", "request_input_tokens"),
        ({"max_stage_input_tokens": 1}, "oversized", "stage_input_tokens"),
    ],
)
def test_budget_stops_before_unsafe_request(
    tmp_path: Path, overrides: dict[str, int], prompt: str, reason: str
) -> None:
    tracker = _tracker(**overrides)

    with pytest.raises(ValueError, match=f"stage=fixture_stage component=part-001.*{reason}"):
        tracker.reserve(
            component="part-001",
            prompt=prompt,
            response_schema=_FixtureOutput.model_json_schema(),
            output_dir=tmp_path,
        )

    stop = json.loads((tmp_path / "budget-stop.json").read_text())
    assert stop["stage"] == "fixture_stage"
    assert stop["component"] == "part-001"
    assert reason in stop["stop_reasons"]
    assert tracker.calls_reserved == 0


def test_call_count_stop_prevents_execution(tmp_path: Path, monkeypatch) -> None:
    tracker = _tracker(max_calls=1)
    tracker.reserve(
        component="first",
        prompt="first",
        response_schema=_FixtureOutput.model_json_schema(),
        output_dir=tmp_path / "first",
    )
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.subprocess.run",
        lambda *args, **kwargs: pytest.fail("model process must not start"),
    )

    with pytest.raises(ValueError, match="stage_call_count"):
        execute_json_model(
            Path.cwd(),
            object(),
            "second",
            _FixtureOutput,
            tmp_path / "second",
            budget_tracker=tracker,
            request_component="second",
        )


def test_invalid_saved_output_stops_without_automatic_repeat(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "saved"
    output_dir.mkdir()
    (output_dir / "output.json").write_text('{"wrong":"shape"}')
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.execute_json_model",
        lambda *args, **kwargs: pytest.fail("unchanged request must not repeat"),
    )

    with pytest.raises(ValueError, match="unchanged requests are not retried"):
        _load_or_execute_json(Path.cwd(), object(), "same prompt", _FixtureOutput, output_dir)
    assert not (output_dir / "output.invalid.json").exists()


def test_persistent_stage_ledger_enforces_budget_across_trackers(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "stage-ledger.json"
    first = _tracker(max_calls=1)
    first.ledger_path = ledger
    second = _tracker(max_calls=1)
    second.ledger_path = ledger
    schema = _FixtureOutput.model_json_schema()
    first.reserve(
        component="4B",
        prompt="first judge",
        response_schema=schema,
        output_dir=tmp_path / "first",
    )

    with pytest.raises(ValueError, match="stage_call_count"):
        second.reserve(
            component="5B",
            prompt="second judge",
            response_schema=schema,
            output_dir=tmp_path / "second",
        )

    persisted = json.loads(ledger.read_text())
    assert len(persisted) == 1
    stop = json.loads((tmp_path / "second/budget-stop.json").read_text())
    assert stop["calls_before"] == 1


def test_budget_measures_exact_additional_file_text(tmp_path: Path) -> None:
    tracker = _tracker()
    schema = _FixtureOutput.model_json_schema()
    prompt = "judge prompt"
    projection = json.dumps({"pretty": ["projection", "text"]}, indent=2)

    reservation = tracker.reserve(
        component="4B",
        prompt=prompt,
        response_schema=schema,
        output_dir=tmp_path,
        additional_inputs=(projection,),
    )

    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    assert reservation["request_characters"] == len(prompt + schema_text + projection)
