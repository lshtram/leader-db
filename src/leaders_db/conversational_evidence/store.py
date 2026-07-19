"""Two-output evidence store with a small resume checkpoint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class Store:
    """Merge evidence and write evidence-to-question mappings."""

    def __init__(
        self, output_dir: Path, ruler: str, country: str, year: int, valid_questions: set[str]
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.meta = {"ruler": ruler, "country": country, "year": year}
        self.valid_questions = valid_questions
        self.evidence = self._read("evidence.json", {**self.meta, "evidence": []})
        self.mappings = self._read("mappings.json", {**self.meta, "questions": {}})
        self.state = self._read(
            "session.json",
            {**self.meta, "thread_id": None, "completed": [], "pending": None},
        )

    def merge(self, result: dict[str, Any], current_question: str | None) -> None:
        """Deduplicate one response and map its claims to valid questions."""

        known = {
            (item["url"].strip(), item["summary"].strip().casefold()): item["id"]
            for item in self.evidence["evidence"]
        }
        for raw in result.get("evidence", []):
            summary = str(raw["summary"]).strip()[:600]
            url = str(raw["url"]).strip()
            if not url.startswith(("http://", "https://")) or not summary:
                continue
            key = (url, summary.casefold())
            evidence_id = known.get(key)
            if evidence_id is None:
                evidence_id = f"E{len(self.evidence['evidence']) + 1:04d}"
                item = {
                    "id": evidence_id,
                    **{k: str(raw[k]).strip() for k in ("title", "publisher", "date")},
                    "url": url,
                    "summary": summary,
                }
                self.evidence["evidence"].append(item)
                known[key] = evidence_id
            question_ids = {str(q) for q in raw.get("question_ids", [])} & self.valid_questions
            if current_question:
                question_ids.add(current_question)
            for question_id in question_ids:
                mapping = self.mappings["questions"].setdefault(
                    question_id, {"evidence_ids": [], "search_note": ""}
                )
                if evidence_id not in mapping["evidence_ids"]:
                    mapping["evidence_ids"].append(evidence_id)
        if current_question:
            mapping = self.mappings["questions"].setdefault(
                current_question, {"evidence_ids": [], "search_note": ""}
            )
            mapping["search_note"] = str(result.get("search_note", "")).strip()
        self.save()

    def complete(self, step: str, thread_id: str | None) -> None:
        """Checkpoint one completed conversational step."""

        if step not in self.state["completed"]:
            self.state["completed"].append(step)
        self.state["thread_id"] = thread_id
        self.state["pending"] = None
        self.save()

    def reopen_unexplained_empty(self, step: str) -> None:
        """Reopen a committed lens that has neither evidence nor a search note."""

        mapping = self.mappings["questions"].get(step, {})
        search_note = str(mapping.get("search_note", "")).strip()
        if mapping.get("evidence_ids") or len(search_note.split()) >= 5:
            raise ValueError(f"{step} is not an unexplained empty mapping")
        self.state["completed"] = [item for item in self.state["completed"] if item != step]
        self.state["pending"] = None
        self.save()

    def checkpoint_writeup(self, step: str, thread_id: str | None, writeup: str) -> Path:
        """Preserve costly M3 work before the formatter runs."""

        raw_dir = self.output_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        path = raw_dir / f"{step.replace('.', '-')}.md"
        path.write_text(writeup.rstrip() + "\n", encoding="utf-8")
        self.state["thread_id"] = thread_id
        self.state["pending"] = {"step": step, "path": str(path.relative_to(self.output_dir))}
        self.save()
        return path

    def index(self, template: str, empty: str) -> str:
        """Build the compact evidence index included in the next prompt."""

        lines = [template.format(**item) for item in self.evidence["evidence"]]
        return "\n".join(lines) if lines else empty

    def save(self) -> None:
        """Atomically write both outputs and the checkpoint."""

        self._write("evidence.json", self.evidence)
        self._write("mappings.json", self.mappings)
        self._write("session.json", self.state)

    def _read(self, name: str, default: dict[str, Any]) -> dict[str, Any]:
        path = self.output_dir / name
        if not path.exists():
            return default
        value = json.loads(path.read_text(encoding="utf-8"))
        if any(value.get(key) != expected for key, expected in self.meta.items()):
            raise ValueError(f"{name} belongs to a different ruler-period")
        return value

    def _write(self, name: str, value: dict[str, Any]) -> None:
        path = self.output_dir / name
        pending = path.with_suffix(path.suffix + ".pending")
        pending.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(pending, path)
