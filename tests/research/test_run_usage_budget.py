from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest

from leaders_db.research.model_call_budget import (
    RunUsageBudgetTracker,
    RunUsageLimits,
    approve_quota_only_continuation,
)
from leaders_db.research.model_call_coordinator import ModelCallCoordinator


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


def _preflight(path: Path, hashes: tuple[str, ...]) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "eligible",
                "config_sha256": "a" * 64,
                "request_count": len(hashes),
                "requests": [{"request_sha256": item} for item in hashes],
            }
        ),
        encoding="utf-8",
    )
    return path


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


def test_request_allowlist_rejects_unknown_and_replayed_requests(tmp_path: Path) -> None:
    allowed = "1" * 64
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "usage.json",
        limits=RunUsageLimits(
            max_calls=1,
            max_input_tokens=1_000,
            max_output_tokens=100,
        ),
        config_sha256="a" * 64,
        allowed_request_sha256s=frozenset({allowed}),
    )
    with pytest.raises(ValueError, match="absent from the authorized"):
        tracker.reserve(
            stage="question_writer",
            component="unknown",
            estimated_input_tokens=10,
            output_token_allowance=10,
            output_dir=tmp_path / "unknown",
            request_sha256="2" * 64,
        )
    tracker.reserve(
        stage="question_writer",
        component="allowed",
        estimated_input_tokens=10,
        output_token_allowance=10,
        output_dir=tmp_path / "allowed",
        request_sha256=allowed,
    )
    with pytest.raises(ValueError, match="already been reserved"):
        tracker.reserve(
            stage="question_writer",
            component="replay",
            estimated_input_tokens=10,
            output_token_allowance=10,
            output_dir=tmp_path / "replay",
            request_sha256=allowed,
        )


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


def test_explicit_quota_only_amendment_preserves_settled_calls(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path / "stage-budgets" / "run-usage.json")
    reservation = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "first",
    )
    with pytest.raises(ValueError, match="run_input_tokens"):
        tracker.reconcile(reservation, {"input_tokens": 8_100, "output_tokens": 50})
    (tmp_path / "first" / "prompt.txt").write_text("settled", encoding="utf-8")
    (tmp_path / "first" / "schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "first" / "deterministic-validation.json").write_text(
        '{"functional_gate":"pass"}', encoding="utf-8"
    )
    settled_hash = sha256(b"settled{}").hexdigest()

    amended = approve_quota_only_continuation(
        tracker,
        new_limits=RunUsageLimits(8, 16_000, 800),
        explicit_user_approval="User approved 16k input; do not rerun settled calls.",
        trusted_preflight_path=_preflight(
            tmp_path / "cohort-preflight.json", (settled_hash, "2" * 64)
        ),
        settled_artifact_root=tmp_path,
    )
    second = amended.reserve(
        stage="question_writer",
        component="1B.2",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "second",
        request_sha256="2" * 64,
    )

    saved = json.loads(amended.ledger_path.read_text(encoding="utf-8"))
    assert len(saved) == 2
    assert saved[0]["status"] == "limit_exceeded"
    assert saved[1]["reservation_id"] == second
    amendment = json.loads(amended.quota_amendment_path.read_text(encoding="utf-8"))
    assert amendment["rerun_set"] == []
    assert amendment["settled_reservation_ids"] == [reservation]

    with pytest.raises(ValueError, match="cannot replay"):
        amended.reserve(
            stage="question_writer",
            component="1B.1",
            estimated_input_tokens=100,
            output_token_allowance=100,
            output_dir=tmp_path / "replay",
            request_sha256=settled_hash,
        )


def test_quota_amendment_rejects_nonquota_failure(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path / "stage-budgets" / "run-usage.json")
    reservation = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "first",
    )
    with pytest.raises(ValueError, match="call_output_token_allowance"):
        tracker.reconcile(reservation, {"input_tokens": 100, "output_tokens": 150})
    (tmp_path / "first" / "prompt.txt").write_text("settled", encoding="utf-8")
    (tmp_path / "first" / "schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "first" / "deterministic-validation.json").write_text(
        '{"functional_gate":"pass"}', encoding="utf-8"
    )
    settled_hash = sha256(b"settled{}").hexdigest()

    with pytest.raises(ValueError, match="only for run quota exhaustion"):
        approve_quota_only_continuation(
            tracker,
            new_limits=RunUsageLimits(8, 16_000, 800),
            explicit_user_approval="approved",
            trusted_preflight_path=_preflight(
                tmp_path / "cohort-preflight.json", (settled_hash,)
            ),
            settled_artifact_root=tmp_path,
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


def test_waiting_reservation_proceeds_after_active_call_reconciles(
    tmp_path: Path,
) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    active = tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "active",
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(
            tracker.reserve,
            stage="question_writer",
            component="1B.2",
            estimated_input_tokens=100,
            output_token_allowance=200,
            output_dir=tmp_path / "waiting",
            wait_for_capacity=True,
        )
        time.sleep(0.05)
        assert not waiting.done()
        tracker.reconcile(active, {"input_tokens": 90, "output_tokens": 50})
        reservation = waiting.result(timeout=1)

    saved = json.loads((tmp_path / "run-usage.json").read_text(encoding="utf-8"))
    second = next(item for item in saved if item["reservation_id"] == reservation)
    assert second["status"] == "reserved"
    assert second["capacity_wait_seconds"] > 0
    assert not (tmp_path / "waiting" / "run-budget-stop.json").exists()


def test_waiting_reservation_times_out_if_active_call_never_reconciles(
    tmp_path: Path,
) -> None:
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(8, 8_000, 800),
        config_sha256="a" * 64,
        capacity_wait_timeout_seconds=0.02,
        capacity_poll_seconds=0.005,
    )
    tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "active",
    )

    with pytest.raises(ValueError, match="capacity_wait_timeout"):
        tracker.reserve(
            stage="question_writer",
            component="1B.2",
            estimated_input_tokens=100,
            output_token_allowance=200,
            output_dir=tmp_path / "waiting",
            wait_for_capacity=True,
        )

    stop = json.loads((tmp_path / "waiting" / "run-budget-stop.json").read_text(encoding="utf-8"))
    assert stop["stop_reasons"] == ["run_output_tokens", "capacity_wait_timeout"]


def test_waiting_reservation_stops_promptly_after_coordinator_failure(
    tmp_path: Path,
) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")
    coordinator = ModelCallCoordinator()
    tracker.reserve(
        stage="question_writer",
        component="1B.1",
        estimated_input_tokens=100,
        output_token_allowance=700,
        output_dir=tmp_path / "active",
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(
            tracker.reserve,
            stage="question_writer",
            component="1B.2",
            estimated_input_tokens=100,
            output_token_allowance=200,
            output_dir=tmp_path / "waiting",
            wait_for_capacity=True,
            capacity_check=coordinator.ensure_open,
        )
        time.sleep(0.05)
        coordinator.publish_failure()
        with pytest.raises(RuntimeError, match="blocked after material failure"):
            waiting.result(timeout=1)

    saved = json.loads((tmp_path / "run-usage.json").read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert not (tmp_path / "waiting").exists()


@pytest.mark.parametrize(
    ("limits", "estimated_input", "output_allowance", "reason"),
    (
        (RunUsageLimits(2, 8_000, 800), 100, 100, "run_call_count"),
        (RunUsageLimits(8, 150, 800), 100, 100, "run_input_tokens"),
        (RunUsageLimits(8, 8_000, 150), 100, 100, "run_output_tokens"),
    ),
)
def test_permanent_exhaustion_does_not_wait_for_unrelated_pending_call(
    tmp_path: Path,
    limits: RunUsageLimits,
    estimated_input: int,
    output_allowance: int,
    reason: str,
) -> None:
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=limits,
        config_sha256="a" * 64,
        capacity_wait_timeout_seconds=10,
        capacity_poll_seconds=0.01,
    )
    completed = tracker.reserve(
        stage="question_writer",
        component="completed",
        estimated_input_tokens=100,
        output_token_allowance=100,
        output_dir=tmp_path / "completed",
    )
    tracker.reconcile(completed, {"input_tokens": 100, "output_tokens": 100})
    tracker.reserve(
        stage="question_writer",
        component="pending",
        estimated_input_tokens=1,
        output_token_allowance=1,
        output_dir=tmp_path / "pending",
    )

    started = time.monotonic()
    with pytest.raises(ValueError, match=reason):
        tracker.reserve(
            stage="question_writer",
            component="blocked",
            estimated_input_tokens=estimated_input,
            output_token_allowance=output_allowance,
            output_dir=tmp_path / "blocked",
            wait_for_capacity=True,
        )

    assert time.monotonic() - started < 1
    stop = json.loads((tmp_path / "blocked" / "run-budget-stop.json").read_text(encoding="utf-8"))
    assert "capacity_wait_timeout" not in stop["stop_reasons"]


def test_reservation_artifact_failure_cancels_ledger_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tracker = _tracker(tmp_path / "run-usage.json")

    def fail_write(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("leaders_db.research.run_usage_budget._write_reservation", fail_write)
    with pytest.raises(OSError, match="disk unavailable"):
        tracker.reserve(
            stage="question_writer",
            component="1B.1",
            estimated_input_tokens=100,
            output_token_allowance=100,
            output_dir=tmp_path / "call",
        )

    saved = json.loads((tmp_path / "run-usage.json").read_text(encoding="utf-8"))
    assert saved[0]["status"] == "cancelled_unlaunched"


@pytest.mark.parametrize(
    ("timeout", "poll"),
    ((-1, 0.1), (float("inf"), 0.1), (1, 0), (1, float("nan"))),
)
def test_wait_configuration_must_be_finite_and_safe(
    tmp_path: Path, timeout: float, poll: float
) -> None:
    with pytest.raises(ValueError, match="capacity"):
        RunUsageBudgetTracker(
            ledger_path=tmp_path / "run-usage.json",
            limits=RunUsageLimits(8, 8_000, 800),
            config_sha256="a" * 64,
            capacity_wait_timeout_seconds=timeout,
            capacity_poll_seconds=poll,
        )
