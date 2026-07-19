from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.conversational_evidence.collector import _unexplained_empty, collect
from leaders_db.conversational_evidence.data import questions
from leaders_db.conversational_evidence.luna import _validate
from leaders_db.conversational_evidence.store import Store


class FakeConversation:
    def __init__(self, stop_after: int | None = None):
        self.thread_id = "thread-1"
        self.prompts: list[str] = []
        self.stop_after = stop_after

    def ask(self, prompt: str) -> str:
        if self.stop_after is not None and len(self.prompts) == self.stop_after:
            raise RuntimeError("interrupted")
        self.prompts.append(prompt)
        question_id = next((q["id"] for q in questions() if f"{q['id']}:" in prompt), "4B.2")
        return f"M3 researched and summarized [{question_id}]."


class FakeFormatter:
    def __init__(self):
        self.prompts: list[str] = []

    def format(self, prompt: str) -> dict[str, object]:
        self.prompts.append(prompt)
        question_id = next(
            (q["id"] for q in questions() if f"summarized [{q['id']}]" in prompt),
            "4B.2",
        )
        return {
            "search_note": f"searched {question_id}",
            "evidence": [
                {
                    "title": f"Source for {question_id}",
                    "publisher": "Example Institution",
                    "date": "2023-06-01",
                    "url": f"https://example.org/{question_id}",
                    "summary": f"Compact evidence for {question_id}.",
                    "question_ids": [question_id, "9B.1"],
                }
            ],
        }


class BrokenFormatter:
    def format(self, prompt: str) -> dict[str, object]:
        raise RuntimeError("formatter failed")


@pytest.mark.parametrize(
    ("ruler", "country"),
    [("Joe Biden", "United States"), ("Vladimir Putin", "Russia"), ("Xi Jinping", "China")],
)
def test_complete_outputs_for_example_rulers(tmp_path: Path, ruler: str, country: str) -> None:
    output = tmp_path / ruler
    chat = FakeConversation()
    formatter = FakeFormatter()

    evidence_path, mappings_path = collect(
        ruler, country, 2023, output, conversation=chat, formatter=formatter
    )

    evidence = json.loads(evidence_path.read_text())
    mappings = json.loads(mappings_path.read_text())
    assert len(chat.prompts) == 81
    assert len(formatter.prompts) == 81
    assert len(evidence["evidence"]) == 80
    assert set(mappings["questions"]) == {q["id"] for q in questions()}
    assert all(item["evidence_ids"] for item in mappings["questions"].values())
    assert "9B.1" not in mappings["questions"]
    assert all(len(item["summary"]) <= 600 for item in evidence["evidence"])


def test_resume_continues_after_last_saved_question(tmp_path: Path) -> None:
    output = tmp_path / "biden"
    first = FakeConversation(stop_after=3)
    with pytest.raises(RuntimeError, match="interrupted"):
        collect(
            "Joe Biden",
            "United States",
            2023,
            output,
            conversation=first,
            formatter=FakeFormatter(),
        )

    second = FakeConversation()
    collect(
        "Joe Biden",
        "United States",
        2023,
        output,
        conversation=second,
        formatter=FakeFormatter(),
    )

    state = json.loads((output / "session.json").read_text())
    assert len(state["completed"]) == 81
    assert len(second.prompts) == 78


def test_formatter_failure_does_not_repeat_m3_research(tmp_path: Path) -> None:
    output = tmp_path / "biden"
    first = FakeConversation()
    with pytest.raises(RuntimeError, match="formatter failed"):
        collect(
            "Joe Biden",
            "United States",
            2023,
            output,
            conversation=first,
            formatter=BrokenFormatter(),
        )
    assert len(first.prompts) == 1
    assert (output / "raw" / "study.md").is_file()

    second = FakeConversation()
    collect(
        "Joe Biden",
        "United States",
        2023,
        output,
        conversation=second,
        formatter=FakeFormatter(),
    )
    assert len(second.prompts) == 80


def test_question_data_contains_exactly_eight_chapters_and_eighty_lenses() -> None:
    configured = questions()
    assert len(configured) == 80
    assert len({q["id"] for q in configured}) == 80
    assert [q["id"] for q in configured[::10]] == [f"{chapter}B.1" for chapter in range(1, 9)]


def test_legacy_dossier_output_is_rejected_by_luna_boundary() -> None:
    with pytest.raises(ValueError, match="evidence contract"):
        _validate({"ruler": {}, "evidence_items": []})


def test_only_explained_search_gap_may_commit_without_evidence() -> None:
    assert _unexplained_empty({"evidence": [], "search_note": ""})
    assert _unexplained_empty({"evidence": [], "search_note": "Completed."})
    assert not _unexplained_empty(
        {"evidence": [], "search_note": "Searched official archives; no record found."}
    )


def test_unexplained_empty_mapping_can_be_reopened(tmp_path: Path) -> None:
    store = Store(tmp_path, "A Person", "Alpha", 2024, {"2B.5"})
    store.mappings["questions"]["2B.5"] = {"evidence_ids": [], "search_note": ""}
    store.state["completed"] = ["study", "2B.5"]
    store.reopen_unexplained_empty("2B.5")

    assert store.state["completed"] == ["study"]
