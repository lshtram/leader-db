from pathlib import Path
from types import SimpleNamespace

from leaders_db.conversational_evidence import judging
from leaders_db.conversational_evidence.judging import (
    _normalize_candidate,
    _write_summary,
    repair_saved_judgments,
    run_judges,
)
from leaders_db.conversational_evidence.luna import LunaFormatter
from leaders_db.conversational_evidence.m3 import M3Conversation
from leaders_db.conversational_evidence.researcher import (
    CodexResearcher,
    _next_turn,
    _requires_fresh_thread,
)


def test_ignore_rules_is_scoped_to_exec_for_new_and_resumed_turns(tmp_path: Path) -> None:
    fresh = M3Conversation(tmp_path, tmp_path / "m3")
    fresh_command = fresh._command(tmp_path / "fresh.md")
    assert fresh_command.index("--ignore-rules") > fresh_command.index("exec")

    resumed = M3Conversation(tmp_path, tmp_path / "m3", "thread-1")
    resumed_command = resumed._command(tmp_path / "resumed.md")
    assert resumed_command.index("--ignore-rules") > resumed_command.index("resume")


def test_luna_resume_ignores_profile_json(tmp_path: Path) -> None:
    work_dir = tmp_path / "luna"
    work_dir.mkdir()
    (work_dir / "turn-002.json").write_text("{}")
    (work_dir / "turn-002.profile.json").write_text("{}")

    formatter = LunaFormatter(tmp_path, work_dir)

    assert formatter.turn == 3


def test_researcher_starts_fresh_after_context_exhaustion(tmp_path: Path) -> None:
    work_dir = tmp_path / "researcher"
    work_dir.mkdir()
    (work_dir / "turn-001.jsonl").write_text(
        "Codex ran out of room in the model's context window."
    )

    researcher = CodexResearcher(
        tmp_path, work_dir, "gpt-5.4-mini", thread_id="exhausted-thread"
    )

    assert researcher.thread_id is None
    assert "resume" not in researcher._command(tmp_path / "answer.md")


def test_failed_turn_number_is_not_reused(tmp_path: Path) -> None:
    (tmp_path / "turn-004.profile.json").write_text("{}")
    (tmp_path / "turn-004.jsonl").write_text("{}")

    assert _next_turn(tmp_path) == 5


def test_gpt54mini_allows_long_tail_research_turns(tmp_path: Path) -> None:
    researcher = CodexResearcher(tmp_path, tmp_path / "research", "gpt-5.4-mini")

    assert researcher.timeout_seconds == 1800


def test_failed_remote_compaction_requires_fresh_thread() -> None:
    assert _requires_fresh_thread("Error running remote compact task: max_output_tokens")
    assert _requires_fresh_thread("", "Failed to run pre-sampling compact")


def test_judge_runner_rejects_unknown_or_empty_chapter_selection(tmp_path: Path) -> None:
    for chapters in ((), ("9B",)):
        try:
            run_judges(tmp_path, tmp_path / "output", chapter_ids=chapters)
        except ValueError as exc:
            assert "chapter_ids" in str(exc)
        else:
            raise AssertionError("invalid chapter selection was accepted")


def test_judge_summary_counts_only_selected_chapters(tmp_path: Path) -> None:
    summary = _write_summary(
        tmp_path,
        model="gpt-5.4-mini",
        workers=1,
        chapter_ids=("3B",),
        new_results=[],
    )

    assert summary["total"] == 1
    assert [item["chapter_id"] for item in summary["chapters"]] == ["3B"]


def test_judge_normalization_recovers_lens_id_from_descriptive_gap() -> None:
    candidate = {
        "evaluations": [
            {
                "supported_lenses": ["4B.1 elections"],
                "missing_or_weak_lenses": ["4B.8 direct transfer event", "unknown"],
            }
        ]
    }

    normalized = _normalize_candidate(candidate, "4B", ())

    assert normalized["evaluations"][0]["supported_lenses"] == ["4B.1"]
    assert normalized["evaluations"][0]["missing_or_weak_lenses"] == ["4B.8"]


def test_repair_saved_judgments_accepts_partial_chapter_run(
    tmp_path: Path, monkeypatch: object
) -> None:
    compact = tmp_path / "compact"
    output = tmp_path / "output"
    (compact / "chapters").mkdir(parents=True)
    (output / "4B").mkdir(parents=True)
    (compact / "chapters/4B.json").write_text(
        '{"projection_paths":[],"target_year":2022}', encoding="utf-8"
    )
    (output / "4B/judgment.pending.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(judging, "_normalize_candidate", lambda *args: {})
    monkeypatch.setattr(
        judging.ChapterJudgmentBatch,
        "model_validate",
        lambda value: SimpleNamespace(model_dump=lambda **kwargs: value),
    )
    monkeypatch.setattr(judging, "_validate_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(judging, "_write_json", lambda *args, **kwargs: None)

    result = repair_saved_judgments(compact, output)

    assert result == {"repaired_chapters": ["4B"], "llm_calls": 0}


def test_projection_review_can_clear_nonrecoverable_null(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(judging.ChapterJudgmentBatch, "model_validate", lambda value: value)
    output = tmp_path / "judgments"
    path = output / "1B/judgment.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"evaluations":[{"iso3":"COD","score_1_to_10":null,'
        '"manual_review_required":true,"manual_review_reason_type":"recoverable_null",'
        '"manual_review_reason":"review"}]}',
        encoding="utf-8",
    )
    review = tmp_path / "review.json"
    review.write_text(
        '{"reviews":[{"iso3":"COD","chapter_id":"1B","existing_score":null,'
        '"recommended_score":null,"decision":"clear_null_nonrecoverable"}]}',
        encoding="utf-8",
    )

    result = judging.apply_projection_review(output, review)

    assert result == {"cleared": ["COD/1B"], "remaining": 0}
    saved = judging._object(path)["evaluations"][0]
    assert saved["manual_review_required"] is False
