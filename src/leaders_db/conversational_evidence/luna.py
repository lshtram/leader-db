"""Use Luna only to transcribe M3 research into strict JSON."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .data import DATA_DIR
from .researcher import _event_profile


class LunaFormatter:
    """Stateless, no-search JSON formatter."""

    def __init__(self, project_root: Path, work_dir: Path):
        self.project_root = project_root
        self.work_dir = work_dir
        numbers = [
            int(path.stem.split("-")[-1]) for path in work_dir.glob("turn-[0-9][0-9][0-9].json")
        ]
        self.turn = max(numbers, default=0) + 1

    def format(self, prompt: str) -> dict[str, object]:
        """Format one M3 note and validate the narrow output contract."""

        self.work_dir.mkdir(parents=True, exist_ok=True)
        answer = self.work_dir / f"turn-{self.turn:03d}.json"
        events = self.work_dir / f"turn-{self.turn:03d}.jsonl"
        profile = self.work_dir / f"turn-{self.turn:03d}.profile.json"
        self.turn += 1
        command = [
            "codex",
            "exec",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "goals",
            "--model",
            "gpt-5.6-luna",
            "--ignore-rules",
            "-",
            "--json",
            "--color",
            "never",
            "--cd",
            str(self.project_root),
            "--sandbox",
            "read-only",
            "--add-dir",
            str(self.work_dir),
            "--output-schema",
            str(DATA_DIR / "result.schema.json"),
            "--output-last-message",
            str(answer),
        ]
        started_at = datetime.now(UTC)
        started = time.monotonic()
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        duration = time.monotonic() - started
        events.write_text(result.stdout, encoding="utf-8")
        profile.write_text(
            json.dumps(
                {
                    "provider": "openai",
                    "model": "gpt-5.6-luna",
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat(),
                    "duration_seconds": round(duration, 3),
                    "return_code": result.returncode,
                    **_event_profile(result.stdout),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Luna invocation failed")
        value = json.loads(answer.read_text(encoding="utf-8"))
        _validate(value)
        return value


def _validate(value: object) -> None:
    """Reject incomplete formatter output."""

    if not isinstance(value, dict) or set(value) != {"evidence", "search_note"}:
        raise ValueError("Luna response does not match the evidence contract")
    evidence = value["evidence"]
    if not isinstance(value["search_note"], str) or not isinstance(evidence, list):
        raise ValueError("Luna response has invalid top-level values")
    fields = {"title", "publisher", "date", "url", "summary", "question_ids"}
    for item in evidence:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("Luna evidence item has invalid fields")
        if not all(isinstance(item[key], str) for key in fields - {"question_ids"}):
            raise ValueError("Luna evidence text fields must be strings")
        if not isinstance(item["question_ids"], list) or not all(
            isinstance(question_id, str) for question_id in item["question_ids"]
        ):
            raise ValueError("Luna question_ids must be strings")
