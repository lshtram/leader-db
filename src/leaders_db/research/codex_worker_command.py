"""Construct non-interactive Codex commands for configured research models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .model_profiles import ResearchModelProfile


def build_codex_exec_command(
    *,
    profile: ResearchModelProfile,
    project_root: Path,
    schema_path: Path | None,
    final_message_path: Path,
    writable_dir: Path,
    isolated_web_research: bool = False,
    sandbox_mode: Literal["read-only", "danger-full-access"] = "read-only",
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] | None = None,
) -> tuple[str, ...]:
    """Return an argv-only Codex invocation without shell interpolation."""

    if profile.execution_surface != "codex":
        raise ValueError("research worker requires the Codex execution surface")
    command = [
        "codex",
        "exec",
        *(item for feature in profile.disabled_features for item in ("--disable", feature)),
        "-",
        "--json",
        "--color",
        "never",
        "--cd",
        str(project_root),
        "--sandbox",
        sandbox_mode,
        "--add-dir",
        str(writable_dir),
        "--output-last-message",
        str(final_message_path),
    ]
    if isolated_web_research:
        command[2:2] = [
            "--ignore-rules",
            "--disable",
            "shell_tool",
            "--disable",
            "unified_exec",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "goals",
        ]
    if schema_path is not None:
        command.extend(("--output-schema", str(schema_path)))
    config_path = Path(profile.codex_config_path).expanduser()
    if profile.provider != "openai":
        expected_home = Path.home() / ".codex"
        if config_path.parent != expected_home or not config_path.name.endswith(".config.toml"):
            raise ValueError("non-OpenAI Codex profile must be a named CODEX_HOME config layer")
        command.extend(("--profile", config_path.name.removesuffix(".config.toml")))
    if profile.model != "session_default":
        command.extend(("--model", profile.model))
    if reasoning_effort is not None:
        command.extend(("--config", f'model_reasoning_effort="{reasoning_effort}"'))
    return tuple(command)


def build_codex_resume_command(
    *,
    profile: ResearchModelProfile,
    session_id: str,
    project_root: Path,
    final_message_path: Path,
    writable_dir: Path,
) -> tuple[str, ...]:
    """Return an argv-only resume invocation for one exact persisted session."""

    if profile.execution_surface != "codex":
        raise ValueError("research worker requires the Codex execution surface")
    if not session_id.strip() or session_id == "--last":
        raise ValueError("an exact Codex session ID is required for safe resume")
    command = ["codex"]
    command.extend(
        item
        for feature in profile.disabled_features
        for item in ("--disable", feature)
    )
    command.extend(
        (
            "--cd",
            str(project_root),
            "--sandbox",
            "read-only",
            "--add-dir",
            str(writable_dir),
        )
    )
    config_path = Path(profile.codex_config_path).expanduser()
    if profile.provider != "openai":
        expected_home = Path.home() / ".codex"
        if config_path.parent != expected_home or not config_path.name.endswith(
            ".config.toml"
        ):
            raise ValueError(
                "non-OpenAI Codex profile must be a named CODEX_HOME config layer"
            )
        command.extend(("--profile", config_path.name.removesuffix(".config.toml")))
    if profile.model != "session_default":
        command.extend(("--model", profile.model))
    command.extend(
        (
            "exec",
            "resume",
            session_id,
            "-",
            "--json",
            "--output-last-message",
            str(final_message_path),
        )
    )
    return tuple(command)


def read_codex_thread_id(events_path: Path) -> str:
    """Read the one exact thread ID emitted by a successful JSONL invocation."""

    thread_ids: set[str] = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "thread.started":
            continue
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            thread_ids.add(thread_id)
    if len(thread_ids) != 1:
        raise ValueError("Codex event log must contain exactly one thread.started ID")
    return next(iter(thread_ids))


def validate_worker_timing(
    *, lease_seconds: int, heartbeat_seconds: int, timeout_seconds: int
) -> None:
    """Require heartbeats frequent enough to protect a running worker."""

    if lease_seconds < 240:
        raise ValueError("lease_seconds must be at least 240 for long research sessions")
    if heartbeat_seconds < 1 or timeout_seconds < 1:
        raise ValueError("heartbeat and timeout values must be positive")
    if heartbeat_seconds * 2 >= lease_seconds:
        raise ValueError("heartbeat_seconds must be less than half the lease duration")


__all__ = [
    "build_codex_exec_command",
    "build_codex_resume_command",
    "read_codex_thread_id",
    "validate_worker_timing",
]
