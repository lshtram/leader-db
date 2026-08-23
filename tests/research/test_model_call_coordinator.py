from __future__ import annotations

import json
from pathlib import Path
from threading import Barrier, Thread
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from leaders_db.research.corpus_reader_runner import ModelCallCoordinator, execute_json_model
from leaders_db.research.model_call_budget import RunUsageBudgetTracker, RunUsageLimits


class _Result(BaseModel):
    value: str


class _Budget:
    def __init__(self) -> None:
        self.reservations = 0

    def reserve(self, **kwargs) -> None:
        self.reservations += 1


def test_executor_persists_caller_supplied_strict_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "constrained"
    response_schema = _Result.model_json_schema()
    response_schema["properties"]["value"]["enum"] = ["ok"]

    def fake_run(*args, **kwargs) -> None:
        (output_dir / "output.json").write_text('{"value":"ok"}', encoding="utf-8")

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.build_codex_exec_command",
        lambda **kwargs: ("codex",),
    )

    result = execute_json_model(
        tmp_path,
        SimpleNamespace(model="gpt-5.6-sol"),
        "prompt",
        _Result,
        output_dir,
        response_schema=response_schema,
    )

    assert result.value == "ok"
    saved = json.loads((output_dir / "schema.json").read_text())
    assert saved["properties"]["value"]["enum"] == ["ok"]
    assert saved["required"] == ["value"]


def test_failure_publication_blocks_late_launch_but_allows_inflight_to_settle() -> None:
    coordinator = ModelCallCoordinator()
    registered = Barrier(2)
    settle = Barrier(2)

    def in_flight_call() -> None:
        coordinator.authorize_launch()
        registered.wait()
        settle.wait()
        coordinator.complete_call()

    thread = Thread(target=in_flight_call)
    thread.start()
    registered.wait()
    assert coordinator.in_flight == 1
    coordinator.publish_failure()

    with pytest.raises(RuntimeError, match="blocked after material failure"):
        coordinator.authorize_launch()

    settle.wait()
    thread.join()
    assert coordinator.in_flight == 0


def test_blocked_executor_does_not_reserve_or_create_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    coordinator = ModelCallCoordinator()
    coordinator.publish_failure()
    budget = _Budget()
    subprocess_called = False

    def fake_run(*args, **kwargs):
        nonlocal subprocess_called
        subprocess_called = True

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)
    output_dir = tmp_path / "blocked"

    with pytest.raises(RuntimeError, match="blocked after material failure"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(),
            "prompt",
            _Result,
            output_dir,
            budget_tracker=budget,  # type: ignore[arg-type]
            call_coordinator=coordinator,
        )

    assert budget.reservations == 0
    assert not subprocess_called
    assert not output_dir.exists()
    assert coordinator.in_flight == 0


def test_executor_reconciles_run_budget_from_trusted_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "call"
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(10, 10_000, 200_000),
        config_sha256="a" * 64,
    )

    def fake_run(*args, stdout, **kwargs) -> None:
        stdout.write(
            '{"type":"turn.completed","usage":{"input_tokens":90,'
            '"cached_input_tokens":20,"output_tokens":40,'
            '"reasoning_output_tokens":10}}\n'
        )
        stdout.flush()
        (output_dir / "output.json").write_text('{"value":"ok"}', encoding="utf-8")

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.build_codex_exec_command",
        lambda **kwargs: ("codex",),
    )

    result = execute_json_model(
        tmp_path,
        SimpleNamespace(model="gpt-5.6-sol"),
        "prompt",
        _Result,
        output_dir,
        run_budget_tracker=tracker,
    )

    assert result.value == "ok"
    ledger = json.loads((tmp_path / "run-usage.json").read_text())
    assert ledger[0]["status"] == "completed"
    assert ledger[0]["observed_output_tokens"] == 40
    execution = json.loads((output_dir / "execution-profile.json").read_text())
    assert execution["model"] == "gpt-5.6-sol"
    assert execution["return_code"] == 0
    assert execution["request_characters"] == len("prompt")
    assert execution["usage"]["output_tokens"] == 40
    assert execution["elapsed_seconds"] >= 0


def test_run_budget_refusal_prevents_executor_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(10, 10_000, 100_000),
        config_sha256="a" * 64,
    )
    called = False

    def fake_run(*args, **kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)

    with pytest.raises(ValueError, match="run_output_tokens"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(model="gpt-5.6-sol"),
            "prompt",
            _Result,
            tmp_path / "blocked-by-run-budget",
            run_budget_tracker=tracker,
        )

    assert not called


def test_reconciliation_failure_still_profiles_and_releases_coordinator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "call"
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(10, 500, 200_000),
        config_sha256="a" * 64,
    )
    coordinator = ModelCallCoordinator()

    def fake_run(*args, stdout, **kwargs) -> None:
        stdout.write(
            '{"type":"turn.completed","usage":{"input_tokens":10000,'
            '"cached_input_tokens":20,"output_tokens":40,'
            '"reasoning_output_tokens":10}}\n'
        )
        stdout.flush()
        (output_dir / "output.json").write_text('{"value":"ok"}', encoding="utf-8")

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.build_codex_exec_command",
        lambda **kwargs: ("codex", "--api-key", "sk-secret", "https://u:p@example.test"),
    )

    with pytest.raises(ValueError, match="observed model usage exceeded"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(model="gpt-5.6-sol"),
            "prompt",
            _Result,
            output_dir,
            run_budget_tracker=tracker,
            call_coordinator=coordinator,
        )

    profile = json.loads((output_dir / "execution-profile.json").read_text())
    assert coordinator.in_flight == 0
    assert profile["sanitized_argv"] == [
        "codex",
        "--api-key",
        "<redacted>",
        "https://<redacted>@example.test",
    ]


def test_integrated_executor_automatically_uses_preflight_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = tmp_path / "integrated"
    run_dir.mkdir()
    (run_dir / "preflight-manifest.json").write_text(
        json.dumps(
            {
                "status": "eligible",
                "config_sha256": "a" * 64,
                "maximum_calls_per_ruler": 250,
                "maximum_input_tokens_per_ruler": 10_000,
                "maximum_output_tokens_per_ruler": 100_000,
            }
        ),
        encoding="utf-8",
    )
    called = False

    def fake_run(*args, **kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)

    with pytest.raises(ValueError, match="run_output_tokens"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(model="gpt-5.6-sol"),
            "prompt",
            _Result,
            run_dir / "question-writing" / "1B.1",
        )

    assert not called
    ledger_path = run_dir / "stage-budgets" / "run-usage-reservations.json"
    assert ledger_path.read_text(encoding="utf-8") == ""


def test_integrated_executor_rejects_mismatched_explicit_tracker(tmp_path: Path) -> None:
    run_dir = tmp_path / "integrated"
    run_dir.mkdir()
    (run_dir / "preflight-manifest.json").write_text(
        json.dumps(
            {
                "status": "eligible",
                "config_sha256": "a" * 64,
                "maximum_calls_per_ruler": 250,
                "maximum_input_tokens_per_ruler": 10_000,
                "maximum_output_tokens_per_ruler": 500_000,
            }
        ),
        encoding="utf-8",
    )
    tracker = RunUsageBudgetTracker(
        ledger_path=run_dir / "wrong.json",
        limits=RunUsageLimits(250, 10_000, 500_000),
        config_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="differs from its preflight"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(model="gpt-5.6-sol"),
            "prompt",
            _Result,
            run_dir / "question-writing" / "1B.1",
            run_budget_tracker=tracker,
        )


def test_malformed_usage_still_persists_execution_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "call"
    tracker = RunUsageBudgetTracker(
        ledger_path=tmp_path / "run-usage.json",
        limits=RunUsageLimits(10, 10_000, 200_000),
        config_sha256="a" * 64,
    )

    def fake_run(*args, stdout, **kwargs) -> None:
        stdout.write(
            '{"type":"turn.completed","usage":{"input_tokens":-1,'
            '"cached_input_tokens":0,"output_tokens":1,'
            '"reasoning_output_tokens":0}}\n'
        )
        stdout.flush()
        (output_dir / "output.json").write_text('{"value":"ok"}', encoding="utf-8")

    monkeypatch.setattr("leaders_db.research.corpus_reader_runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.build_codex_exec_command",
        lambda **kwargs: ("codex",),
    )

    with pytest.raises(ValueError, match="token counters cannot be negative"):
        execute_json_model(
            tmp_path,
            SimpleNamespace(model="gpt-5.6-sol"),
            "prompt",
            _Result,
            output_dir,
            run_budget_tracker=tracker,
        )

    profile = json.loads((output_dir / "execution-profile.json").read_text())
    assert profile["usage"] is None
    assert profile["usage_status"] == "invalid"
    assert profile["usage_error"]["error_type"] == "ValueError"
