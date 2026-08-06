from pathlib import Path

from leaders_db.evidence_funnel.cli_attempts import (
    plan_cli_attempts,
    select_cli_attempt,
)


def _select(stage_root: Path):
    return select_cli_attempt(
        stage_root=stage_root,
        attempt=1,
        profile_name="minimax-m3-long-context",
        interruption_retries=1,
    )


def test_selects_new_base_attempt(tmp_path: Path) -> None:
    selection = _select(tmp_path)

    assert selection.root.name == "cli-attempt-01-minimax-m3-long-context"
    assert selection.prior_roots == ()
    assert not selection.exhausted


def test_preserves_interrupted_attempt_and_selects_retry(tmp_path: Path) -> None:
    base = tmp_path / "cli-attempt-01-minimax-m3-long-context"
    base.mkdir()

    selection = _select(tmp_path)

    assert selection.root.name.endswith("-retry-01")
    assert selection.prior_roots == (base,)
    assert not selection.exhausted


def test_resumes_completed_retry(tmp_path: Path) -> None:
    base = tmp_path / "cli-attempt-01-minimax-m3-long-context"
    retry = tmp_path / f"{base.name}-retry-01"
    base.mkdir()
    retry.mkdir()
    (retry / "completion.json").write_text("{}", encoding="utf-8")

    selection = _select(tmp_path)

    assert selection.root == retry
    assert selection.prior_roots == (base, retry)
    assert not selection.exhausted


def test_reports_exhausted_interruption_retries(tmp_path: Path) -> None:
    base = tmp_path / "cli-attempt-01-minimax-m3-long-context"
    base.mkdir()
    (tmp_path / f"{base.name}-retry-01").mkdir()

    selection = _select(tmp_path)

    assert selection.exhausted


def test_plan_prefers_completed_fallback_and_accounts_all_roots(
    tmp_path: Path,
) -> None:
    first = tmp_path / "cli-attempt-01-minimax-m3-long-context"
    second = tmp_path / "cli-attempt-02-minimax-m2.7-researcher"
    first.mkdir()
    second.mkdir()
    (second / "completion.json").write_text("{}", encoding="utf-8")
    (first / "events.jsonl").write_text("first", encoding="utf-8")
    (second / "events.jsonl").write_text("second", encoding="utf-8")

    plan = plan_cli_attempts(
        stage_root=tmp_path,
        profile_names=("minimax-m3-long-context", "minimax-m2.7-researcher"),
        interruption_retries=1,
    )

    assert [(attempt, profile) for attempt, profile, _ in plan.attempts] == [
        (2, "minimax-m2.7-researcher")
    ]
    assert plan.prior_roots == (first, second)
    assert sum((root / "events.jsonl").stat().st_size for root in plan.prior_roots) == 11
