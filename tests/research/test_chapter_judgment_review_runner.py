from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from leaders_db.research.chapter_judgment_review_runner import (
    _reserve_review_request,
    _review_one,
)
from leaders_db.research.model_call_budget import load_stage_budget_tracker


class CapturingBudget:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def reserve(self, **kwargs: object) -> dict[str, object]:
        self.arguments = kwargs
        return {"decision": "reserved"}


def test_reservation_includes_exact_judgment_and_projection_text(tmp_path: Path) -> None:
    judgment = tmp_path / "judgment.json"
    projection = tmp_path / "projection.json"
    judgment.write_text("judgment: שלום", encoding="utf-8")
    projection.write_text("projection: α", encoding="utf-8")
    budget = CapturingBudget()

    _reserve_review_request(
        budget=budget,  # type: ignore[arg-type]
        chapter_id="1B",
        chapter_dir=tmp_path,
        prompt="prompt",
        input_paths=(judgment, projection),
    )

    assert budget.arguments["additional_inputs"] == (
        "judgment: שלום",
        "projection: α",
    )


def test_shared_review_budget_stops_ninth_call(tmp_path: Path) -> None:
    config = Path("configs/research-stage-budgets.yaml")
    ledger = tmp_path / "reservations.json"
    source = tmp_path / "input.json"
    source.write_text("{}", encoding="utf-8")
    for number in range(8):
        tracker = load_stage_budget_tracker(config, "chapter_judgment_review", ledger_path=ledger)
        _reserve_review_request(
            budget=tracker,
            chapter_id=f"{number + 1}B",
            chapter_dir=tmp_path / f"accepted-{number}",
            prompt="prompt",
            input_paths=(source,),
        )
    tracker = load_stage_budget_tracker(config, "chapter_judgment_review", ledger_path=ledger)

    with pytest.raises(ValueError, match="stage_call_count"):
        _reserve_review_request(
            budget=tracker,
            chapter_id="1B",
            chapter_dir=tmp_path / "refused",
            prompt="prompt",
            input_paths=(source,),
        )


def test_concurrent_first_reservations_preserve_eight_call_limit(tmp_path: Path) -> None:
    config = Path("configs/research-stage-budgets.yaml")
    ledger = tmp_path / "concurrent-reservations.json"
    source = tmp_path / "input.json"
    source.write_text("{}", encoding="utf-8")

    def reserve(number: int) -> str:
        tracker = load_stage_budget_tracker(config, "chapter_judgment_review", ledger_path=ledger)
        try:
            _reserve_review_request(
                budget=tracker,
                chapter_id=f"{number % 8 + 1}B",
                chapter_dir=tmp_path / f"concurrent-{number}",
                prompt="prompt",
                input_paths=(source,),
            )
        except ValueError as exc:
            assert "stage_call_count" in str(exc)
            return "stopped"
        return "reserved"

    with ThreadPoolExecutor(max_workers=16) as executor:
        outcomes = tuple(executor.map(reserve, range(16)))

    assert outcomes.count("reserved") == 8
    assert outcomes.count("stopped") == 8
    assert len(json.loads(ledger.read_text(encoding="utf-8"))) == 8
    tracker = load_stage_budget_tracker(config, "chapter_judgment_review", ledger_path=ledger)

    with pytest.raises(ValueError, match="stage_call_count"):
        _reserve_review_request(
            budget=tracker,
            chapter_id="1B",
            chapter_dir=tmp_path / "refused",
            prompt="prompt",
            input_paths=(source,),
        )


def test_refused_reservation_prevents_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    judgment_path = tmp_path / "judgment.json"
    judgment_path.write_text("{}", encoding="utf-8")
    projection_path = tmp_path / "projection.json"
    projection_path.write_text("{}", encoding="utf-8")
    (tmp_path / "review").mkdir()
    judgment = SimpleNamespace(chapter_id="1B", job_key="judge:1B", evaluations=(1,))
    monkeypatch.setattr(
        "leaders_db.research.chapter_judgment_review_runner."
        "ChapterJudgmentBatch.model_validate_json",
        lambda _text: judgment,
    )
    monkeypatch.setattr(
        "leaders_db.research.chapter_judgment_review_runner._projection_paths",
        lambda *_args: (projection_path,),
    )
    monkeypatch.setattr(
        "leaders_db.research.chapter_judgment_review_runner._reserve_review_request",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("budget refused")),
    )
    called = False

    def forbidden_subprocess(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "leaders_db.research.chapter_judgment_review_runner.subprocess.run",
        forbidden_subprocess,
    )

    with pytest.raises(ValueError, match="budget refused"):
        _review_one(
            project_root=tmp_path,
            judgment_path=judgment_path,
            output_dir=tmp_path / "review",
            profile=SimpleNamespace(),
            budget=SimpleNamespace(),  # type: ignore[arg-type]
            timeout_seconds=10,
        )
    assert called is False
