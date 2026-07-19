"""Generic persistent Codex researcher with per-turn profiling."""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .data import load

DISABLED = ("apps", "plugins", "multi_agent", "goals")


class CodexResearcher:
    """Run any configured Codex model in one persistent research thread."""

    def __init__(
        self,
        project_root: Path,
        work_dir: Path,
        config_name: str,
        thread_id: str | None = None,
    ):
        configs = load("researchers.json")
        if config_name not in configs:
            raise ValueError(f"unknown researcher: {config_name}")
        self.config_name = config_name
        self.config = configs[config_name]
        self.project_root = project_root
        self.work_dir = work_dir
        self.thread_id = None if _last_turn_exhausted(work_dir) else thread_id
        self.turn = _next_turn(work_dir)

    def ask(self, prompt: str) -> str:
        """Run one turn, preserve events, and record timing, usage, and tools."""

        self.work_dir.mkdir(parents=True, exist_ok=True)
        number = self.turn
        self.turn += 1
        answer = self.work_dir / f"turn-{number:03d}.md"
        events = self.work_dir / f"turn-{number:03d}.jsonl"
        profile = self.work_dir / f"turn-{number:03d}.profile.json"
        started_at = datetime.now(UTC)
        started = time.monotonic()
        result = subprocess.run(
            self._command(answer),
            input=prompt,
            text=True,
            capture_output=True,
            timeout=int(self.config["timeout_seconds"]),
            check=False,
        )
        duration = time.monotonic() - started
        events.write_text(result.stdout, encoding="utf-8")
        event_profile = _event_profile(result.stdout)
        profile.write_text(
            json.dumps(
                {
                    "researcher": self.config_name,
                    "provider": self.config["provider"],
                    "model": self.config["model"],
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat(),
                    "duration_seconds": round(duration, 3),
                    "return_code": result.returncode,
                    **event_profile,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        needs_fresh_thread = _requires_fresh_thread(result.stdout, result.stderr)
        if result.returncode and needs_fresh_thread and self.thread_id:
            self.thread_id = None
            return self.ask(prompt)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "researcher invocation failed")
        if self.thread_id is None:
            self.thread_id = _thread_id(result.stdout)
        writeup = answer.read_text(encoding="utf-8").strip()
        if not writeup:
            raise ValueError("researcher returned an empty research note")
        return writeup

    def _command(self, answer: Path) -> list[str]:
        common = [item for feature in DISABLED for item in ("--disable", feature)]
        common += ["--model", str(self.config["model"])]
        if self.config["codex_profile"]:
            common += ["--profile", str(self.config["codex_profile"])]
        workspace = [
            "--cd",
            str(self.project_root),
            "--sandbox",
            "read-only",
            "--add-dir",
            str(self.work_dir),
        ]
        if self.thread_id:
            return [
                "codex",
                *common,
                *workspace,
                "exec",
                "resume",
                self.thread_id,
                "-",
                "--json",
                "--ignore-rules",
                "--output-last-message",
                str(answer),
            ]
        return [
            "codex",
            "exec",
            *common,
            "--ignore-rules",
            "-",
            "--json",
            "--color",
            "never",
            *workspace,
            "--output-last-message",
            str(answer),
        ]


def _event_profile(output: str) -> dict[str, Any]:
    usage: dict[str, int] = {}
    tools: Counter[str] = Counter()
    errors = 0
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") in {"mcp_tool_call", "web_search"}:
                name = ".".join(str(x) for x in (item.get("server"), item.get("tool")) if x)
                tools[name or str(item.get("type"))] += 1
                errors += int(bool(item.get("error")))
    return {"usage": usage, "tool_calls": dict(tools), "tool_errors": errors}


def _thread_id(output: str) -> str:
    ids: set[str] = set()
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started":
            ids.add(str(event["thread_id"]))
    if len(ids) != 1:
        raise ValueError("researcher did not emit exactly one thread ID")
    return ids.pop()


def _next_turn(work_dir: Path) -> int:
    numbers = [
        int(path.name.split(".")[0].split("-")[-1])
        for path in work_dir.glob("turn-*.*")
    ]
    return max(numbers, default=0) + 1


def _requires_fresh_thread(output: str, error: str = "") -> bool:
    combined = output + "\n" + error
    markers = (
        "ran out of room in the model's context window",
        "Error running remote compact task",
        "Failed to run pre-sampling compact",
    )
    return any(marker in combined for marker in markers)


def _last_turn_exhausted(work_dir: Path) -> bool:
    events = sorted(work_dir.glob("turn-*.jsonl"))
    return bool(events and _requires_fresh_thread(events[-1].read_text(encoding="utf-8")))
