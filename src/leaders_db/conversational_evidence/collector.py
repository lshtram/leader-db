"""Simple reconnaissance-then-one-question-at-a-time collection loop."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .data import load, questions
from .profile import write_profile
from .researcher import CodexResearcher
from .store import Store


class Conversation(Protocol):
    """The only model behavior the collector needs."""

    thread_id: str | None

    def ask(self, prompt: str) -> str: ...


class Formatter(Protocol):
    """The no-search formatting behavior the collector needs."""

    def format(self, prompt: str) -> dict[str, object]: ...


def collect(
    ruler: str,
    country: str,
    year: int,
    output_dir: Path,
    *,
    conversation: Conversation | None = None,
    formatter: Formatter | None = None,
    researcher: str = "minimax-m3",
    project_root: Path | None = None,
) -> tuple[Path, Path]:
    """Collect reusable evidence and mappings, safely resuming after each turn."""

    root = project_root or Path.cwd()
    configured_questions = questions()
    store = Store(output_dir, ruler, country, year, {q["id"] for q in configured_questions})
    configured_researcher = store.state.setdefault("researcher", researcher)
    if configured_researcher != researcher:
        raise ValueError("output directory belongs to a different researcher")
    store.save()
    chat = conversation or CodexResearcher(
        root, output_dir / ".researcher", researcher, store.state["thread_id"]
    )
    if formatter is None:
        from .luna import LunaFormatter

        formatter = LunaFormatter(root, output_dir / ".luna")
    prompts = load("prompts.json")
    values = {"ruler": ruler, "country": country, "year": year}
    allowed = ", ".join(q["id"] for q in configured_questions)
    if "study" not in store.state["completed"]:
        writeup = _writeup(
            store,
            chat,
            "study",
            prompts["study"].format(**values),
            prompts["empty_retry"],
        )
        formatted = formatter.format(
            prompts["format_study"].format(allowed_question_ids=allowed, writeup=writeup)
        )
        store.merge(formatted, None)
        store.complete("study", chat.thread_id)
        write_profile(output_dir)
    for question in configured_questions:
        if question["id"] in store.state["completed"]:
            continue
        prompt = prompts["lens"].format(
            **values,
            question_id=question["id"],
            question=question["text"],
            evidence_index=store.index(
                prompts["evidence_index_item"], prompts["evidence_index_empty"]
            ),
        )
        writeup = _writeup(store, chat, question["id"], prompt, prompts["empty_retry"])
        format_prompt = prompts["format"].format(
            question_id=question["id"],
            allowed_question_ids=allowed,
            writeup=writeup,
        )
        formatted = formatter.format(format_prompt)
        if _unexplained_empty(formatted):
            writeup = chat.ask(prompts["empty_lens_repair"].format(prompt=prompt))
            store.checkpoint_writeup(question["id"], chat.thread_id, writeup)
            formatted = formatter.format(
                prompts["format"].format(
                    question_id=question["id"],
                    allowed_question_ids=allowed,
                    writeup=writeup,
                )
            )
            if _unexplained_empty(formatted):
                raise ValueError(f"{question['id']} has neither evidence nor a search note")
        store.merge(formatted, question["id"])
        store.complete(question["id"], chat.thread_id)
        write_profile(output_dir)
    return output_dir / "evidence.json", output_dir / "mappings.json"


def _writeup(store: Store, chat: Conversation, step: str, prompt: str, retry_template: str) -> str:
    """Reuse an unformatted M3 checkpoint, or run and preserve one turn."""

    pending = store.state.get("pending")
    if isinstance(pending, dict) and pending.get("step") == step:
        return (store.output_dir / str(pending["path"])).read_text(encoding="utf-8")
    try:
        writeup = chat.ask(prompt)
    except ValueError as exc:
        if str(exc) != "researcher returned an empty research note":
            raise
        writeup = chat.ask(retry_template.format(prompt=prompt))
    store.checkpoint_writeup(step, chat.thread_id, writeup)
    return writeup


def _unexplained_empty(formatted: dict[str, object]) -> bool:
    evidence = formatted.get("evidence")
    search_note = str(formatted.get("search_note") or "").strip()
    return not evidence and len(search_note.split()) < 5
