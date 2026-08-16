from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from leaders_db.research.model_call_budget import (
    RunUsageBudgetTracker,
    RunUsageLimits,
)


def _tracker(path: Path) -> RunUsageBudgetTracker:
    return RunUsageBudgetTracker(
        ledger_path=path,
        limits=RunUsageLimits(
            max_calls=8,
            max_input_tokens=8_000,
            max_output_tokens=800,
        ),
        config_sha256="a" * 64,
    )


def test_concurrent_reservations_cannot_oversubscribe_output(tmp_path: Path) -> None:
    ledger = tmp_path / "run-usage.json"

    def reserve(number: int) -> str:
        return _tracker(ledger).reserve(
            stage="question_writer",
            component=str(number),
            estimated_input_tokens=100,
            output_token_allowance=100,
            output_dir=tmp_path / str(number),
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(reserve, number) for number in range(16)]
    results = [future.exception() or future.result() for future in futures]

    assert sum(isinstance(item, str) for item in results) == 8
    assert sum(isinstance(item, ValueError) for item in results) == 8
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert len(saved) == 8
    assert {item["status"] for item in saved} == {"reserved"}


def test_reconciliation_releases_unused_allowance_but_not_missing_usage(
    tmp_path: Path,
) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    first = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "first",
    )
    tracker.reconcile(
        first,
        {
            "input_tokens": 90,
            "cached_input_tokens": 20,
            "output_tokens": 50,
            "reasoning_output_tokens": 10,
        },
    )
    second = tracker.reserve(
        stage="question_review",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "second",
    )
    tracker.reconcile(second, None)

    with pytest.raises(ValueError, match="run_output_tokens"):
        tracker.reserve(
            stage="question_review",
            component="1B.2",
            estimated_input_tokens=100,
            output_token_allowance=100,
            output_dir=tmp_path / "third",
        )


def test_only_unlaunched_reservation_can_be_cancelled(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    reservation = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "first",
    )
    tracker.cancel_unlaunched(reservation)
    replacement = tracker.reserve(
        stage="question_writer",
        component="1B.2",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "second",
    )
    tracker.reconcile(replacement, None)

    with pytest.raises(ValueError, match="pending"):
        tracker.cancel_unlaunched(replacement)


def test_observed_overage_is_persisted_and_stops_reconciliation(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    reservation = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "call",
    )

    with pytest.raises(ValueError, match="run_output_tokens"):
        tracker.reconcile(
            reservation,
            {"input_tokens": 100, "output_tokens": 900},
        )

    saved = json.loads((tmp_path / "run-usage.json").read_text(encoding="utf-8"))
    assert saved[0]["status"] == "limit_exceeded"
    assert saved[0]["observed_output_tokens"] == 900


def test_ledger_rejects_different_release_identity(tmp_path: Path) -> None:
    ledger = tmp_path / "run-usage.json"
    _tracker(ledger).reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "first",
    )
    changed = RunUsageBudgetTracker(
        ledger_path=ledger,
        limits=RunUsageLimits(9, 9_000, 900),
        config_sha256="b" * 64,
    )

    with pytest.raises(ValueError, match="ledger identity"):
        changed.reserve(
            stage="question_writer",
            component="1B.2",
            estimated_input_tokens=100,
            output_token_allowance=100,
            output_dir=tmp_path / "second",
        )


def test_per_call_allowance_overage_is_terminal_below_global_limit(
    tmp_path: Path,
) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    reservation = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "call",
    )

    with pytest.raises(ValueError, match="call_output_token_allowance"):
        tracker.reconcile(
            reservation,
            {"input_tokens": 100, "output_tokens": 150},
        )


def test_safe_parallel_calls_reserves_each_models_full_maximum(tmp_path: Path) -> None:
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(250, 40_000_000, 1_000_000),
        config_sha256="a" * 64,
    )

    assert tracker.safe_parallel_calls("gpt-5.6-luna") == 7
