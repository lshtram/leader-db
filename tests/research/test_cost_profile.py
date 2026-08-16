import json
from pathlib import Path

import pytest

from leaders_db.research.cost_profile import build_cost_profile, compare_cost_profiles


def _rules(path: Path) -> Path:
    path.write_text(
        """schema_version: research_cost_stage_rules_v1
event_filename: events.jsonl
rules:
  - artifact_type: analysis
    stage: chapter-analysis
    path_pattern: chapter-analysis/*/**/events.jsonl
    selection_mode: selected_chapter_artifact
  - artifact_type: reading
    stage: reading
    path_pattern: reading/*/events.jsonl
    selection_mode: all_completed
  - artifact_type: question-writer
    stage: question-writing
    path_pattern: question-writing/*/questions/*/events.jsonl
    selection_mode: all_completed
""",
        encoding="utf-8",
    )
    return path


def _event(path: Path, *, input_tokens: int = 100, cached: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_profile_classifies_selected_superseded_shared_and_cache(tmp_path: Path) -> None:
    root = tmp_path / "run"
    _event(root / "chapter-analysis" / "4B" / "selected" / "events.jsonl")
    _event(root / "chapter-analysis" / "4B" / "old" / "events.jsonl", cached=0)
    _event(root / "reading" / "BATCH-1" / "events.jsonl", cached=90)
    (root / "selected-chapter-manifest.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "chapter_id": "4B",
                        "analysis_path": "chapter-analysis/4B/selected/result.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    selected_result = root / "chapter-analysis" / "4B" / "selected" / "result.json"
    selected_result.write_text(
        json.dumps({"answers": [{"question_id": "4B.1", "answer": "Supported."}]}),
        encoding="utf-8",
    )

    profile_path = build_cost_profile(root, tmp_path / "out", _rules(tmp_path / "rules.yaml"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    assert profile["totals"]["calls"] == 3
    assert profile["by_selection_status"]["selected"]["calls"] == 2
    assert profile["by_selection_status"]["superseded"]["calls"] == 1
    assert profile["by_chapter"]["shared"]["calls"] == 1
    assert profile["cache_distribution"] == {
        "calls_with_input": 3,
        "at_least_10_percent": 2,
        "at_least_50_percent": 2,
        "at_least_90_percent": 1,
    }


def test_profile_is_byte_stable_and_deduplicates_symlink(tmp_path: Path) -> None:
    root = tmp_path / "run"
    event = root / "reading" / "BATCH-1" / "events.jsonl"
    _event(event)
    alias = root / "reading" / "BATCH-2" / "events.jsonl"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(event)
    rules = _rules(tmp_path / "rules.yaml")

    first = build_cost_profile(root, tmp_path / "first", rules)
    second = build_cost_profile(root, tmp_path / "second", rules)

    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8"))["totals"]["calls"] == 1


@pytest.mark.parametrize(
    "line, message",
    [
        ("not json\n", "malformed JSONL"),
        ('{"type":"turn.completed"}\n', "has no usage"),
    ],
)
def test_profile_rejects_malformed_or_missing_usage(
    tmp_path: Path, line: str, message: str
) -> None:
    event = tmp_path / "run" / "reading" / "BATCH-1" / "events.jsonl"
    event.parent.mkdir(parents=True)
    event.write_text(line, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_cost_profile(tmp_path / "run", tmp_path / "out", _rules(tmp_path / "rules.yaml"))


def test_compare_requires_same_stage_rules(tmp_path: Path) -> None:
    root = tmp_path / "run"
    _event(root / "reading" / "BATCH-1" / "events.jsonl")
    rules = _rules(tmp_path / "rules.yaml")
    first = build_cost_profile(root, tmp_path / "one", rules)
    second = build_cost_profile(root, tmp_path / "two", rules)

    report = compare_cost_profiles(first, second, tmp_path / "comparison.md")

    assert "| calls | 1 | 1 | +0 |" in report.read_text(encoding="utf-8")


def test_profile_records_failed_event_logs_separately(tmp_path: Path) -> None:
    event = tmp_path / "run" / "reading" / "BATCH-1" / "events.jsonl"
    event.parent.mkdir(parents=True)
    event.write_text('{"type":"turn.started"}\n', encoding="utf-8")

    profile = json.loads(
        build_cost_profile(
            tmp_path / "run", tmp_path / "out", _rules(tmp_path / "rules.yaml")
        ).read_text(encoding="utf-8")
    )

    assert profile["totals"]["calls"] == 0
    assert profile["totals"]["failed_calls"] == 1
    assert profile["by_selection_status"]["failed"]["failed_calls"] == 1


def test_profile_rejects_unclassified_event_artifacts(tmp_path: Path) -> None:
    event = tmp_path / "run" / "unknown-stage" / "events.jsonl"
    _event(event)

    with pytest.raises(ValueError, match="has no stage rule"):
        build_cost_profile(tmp_path / "run", tmp_path / "out", _rules(tmp_path / "rules.yaml"))


def test_profile_reconciles_integrated_metadata_and_run_ledger(tmp_path: Path) -> None:
    root = tmp_path / "run"
    call = root / "question-writing" / "2B" / "questions" / "2B.3"
    _event(call / "events.jsonl", input_tokens=100, cached=50)
    (call / "prompt.txt").write_text("prompt", encoding="utf-8")
    (call / "schema.json").write_text("schema", encoding="utf-8")
    (call / "request-manifest.json").write_text(
        json.dumps(
            {
                "model": "gpt-5.6-luna",
                "profile": "openai-luna-candidate",
                "reasoning_effort": "high",
                "api_key_used": False,
            }
        ),
        encoding="utf-8",
    )
    (call / "run-budget-reservation.json").write_text(
        json.dumps(
            {
                "reservation_id": "run-call-0001",
                "estimated_input_tokens": 90,
                "output_token_allowance": 128_000,
            }
        ),
        encoding="utf-8",
    )
    (call / "execution-profile.json").write_text(
        json.dumps({"elapsed_seconds": 1.25, "return_code": 0}), encoding="utf-8"
    )
    (call / "deterministic-validation.json").write_text(
        json.dumps({"functional_gate": "pass"}), encoding="utf-8"
    )
    ledger = root / "stage-budgets" / "run-usage-reservations.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            [
                {
                    "status": "completed",
                    "observed_input_tokens": 100,
                    "observed_cached_input_tokens": 50,
                    "observed_output_tokens": 20,
                    "observed_reasoning_output_tokens": 5,
                }
            ]
        ),
        encoding="utf-8",
    )

    profile = json.loads(
        build_cost_profile(root, tmp_path / "out", _rules(tmp_path / "rules.yaml")).read_text()
    )

    assert profile["run_budget_reconciliation"]["status"] == "pass"
    assert profile["execution_metadata"] == {
        "completed_calls": 1,
        "failed_calls": 0,
        "elapsed_seconds": 1.25,
        "estimated_input_tokens": 90,
        "models": {"gpt-5.6-luna": 1},
        "reasoning_efforts": {"high": 1},
        "request_characters": 6,
        "response_schema_characters": 6,
        "timed_calls": 1,
        "timed_failed_calls": 0,
        "timing_unavailable_calls": 0,
        "validation_gate_counts": {"pass": 1},
    }


def test_profile_prices_execution_only_metadata_and_accounts_limit_breach(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    call = root / "chapter-judgment-review" / "2B"
    _event(call / "review-events.jsonl", input_tokens=100, cached=50)
    (call / "execution-profile.json").write_text(
        json.dumps(
            {
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "estimated_input_tokens": 90,
                "request_characters": 500,
                "response_schema_characters": 200,
                "output_token_allowance": 128_000,
                "elapsed_seconds": 2.5,
                "return_code": 0,
            }
        ),
        encoding="utf-8",
    )
    ledger = root / "stage-budgets" / "run-usage-reservations.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            [
                {
                    "status": "limit_exceeded",
                    "observed_input_tokens": 100,
                    "observed_cached_input_tokens": 50,
                    "observed_output_tokens": 20,
                    "observed_reasoning_output_tokens": 5,
                }
            ]
        ),
        encoding="utf-8",
    )
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        """schema_version: research_cost_stage_rules_v1
event_filename: events.jsonl
rules:
  - artifact_type: judgment-review
    stage: chapter-judgment-review
    path_pattern: chapter-judgment-review/*/review-events.jsonl
    selection_mode: all_completed
""",
        encoding="utf-8",
    )

    profile = json.loads(
        build_cost_profile(root, tmp_path / "out", rules).read_text(encoding="utf-8")
    )

    assert profile["execution_metadata"]["models"] == {"gpt-5.6-sol": 1}
    assert "gpt-5.6-sol" in profile["cost_equivalents"]["by_model"]
    assert profile["run_budget_reconciliation"]["status"] == "pass"
    assert profile["run_budget_reconciliation"]["budget_status"] == "fail"


def test_profile_marks_unknown_usage_incomplete_and_times_failed_call(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    call = root / "question-writing" / "2B" / "questions" / "2B.3"
    call.mkdir(parents=True)
    (call / "events.jsonl").write_text('{"type":"turn.started"}\n', encoding="utf-8")
    (call / "execution-profile.json").write_text(
        json.dumps(
            {
                "model": "gpt-5.6-luna",
                "reasoning_effort": "high",
                "elapsed_seconds": 3.5,
                "estimated_input_tokens": 90,
                "request_characters": 500,
                "response_schema_characters": 200,
                "return_code": None,
            }
        ),
        encoding="utf-8",
    )
    ledger = root / "stage-budgets" / "run-usage-reservations.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps([{"status": "usage_unavailable"}]), encoding="utf-8")

    profile = json.loads(
        build_cost_profile(root, tmp_path / "out", _rules(tmp_path / "rules.yaml")).read_text()
    )

    assert profile["run_budget_reconciliation"]["status"] == "incomplete"
    assert profile["run_budget_reconciliation"]["unresolved_reservation_count"] == 1
    assert profile["execution_metadata"]["failed_calls"] == 1
    assert profile["execution_metadata"]["timed_failed_calls"] == 1
    assert profile["execution_metadata"]["elapsed_seconds"] == 3.5
