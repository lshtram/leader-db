"""Per-call timing and transport profiles for Codex subscription execution."""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._codex_worker_artifacts import read_codex_usage


def start_execution_profile() -> tuple[str, float]:
    """Capture stable wall-clock provenance and a monotonic duration origin."""

    return datetime.now(UTC).isoformat(), time.monotonic()


def write_execution_profile(
    *,
    output_dir: Path,
    events_path: Path,
    model: str,
    reasoning_effort: str | None,
    started: tuple[str, float],
    return_code: int | None,
    request_characters: int,
    response_schema_characters: int,
    estimated_input_tokens: int,
    output_token_allowance: int | None,
    command: tuple[str, ...] | list[str],
    extra: dict[str, Any] | None = None,
) -> Path:
    """Persist measured execution metadata without claiming subscription billing."""

    started_at, monotonic_start = started
    usage = None
    usage_status = "unavailable"
    usage_error = None
    try:
        usage = read_codex_usage(events_path)
        usage_status = "recorded" if usage is not None else "unavailable"
    except (OSError, UnicodeError, ValueError) as exc:
        usage_status = "invalid"
        usage_error = {"error_type": type(exc).__name__, "message": str(exc)}
    payload = {
        "schema_version": "codex_execution_profile_v1",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(time.monotonic() - monotonic_start, 6),
        "return_code": return_code,
        "request_characters": request_characters,
        "response_schema_characters": response_schema_characters,
        "estimated_input_tokens": estimated_input_tokens,
        "output_token_allowance": output_token_allowance,
        "sanitized_argv": _sanitize_argv(command),
        "usage": usage.model_dump(mode="json") if usage is not None else None,
        "usage_status": usage_status,
        "usage_error": usage_error,
        "subscription_billing": "unknown_not_exposed_by_tool",
        **(extra or {}),
    }
    path = output_dir / "execution-profile.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def finalize_execution(*actions: Callable[[], None]) -> None:
    """Run every finalizer and preserve an already-active execution exception."""

    active_error = sys.exception()
    errors: list[Exception] = []
    for action in actions:
        try:
            action()
        except Exception as exc:  # every cleanup must still be attempted
            errors.append(exc)
    if active_error is None and errors:
        raise errors[0]


def _sanitize_argv(command: tuple[str, ...] | list[str]) -> list[str]:
    sensitive = re.compile(
        r"(?:api[-_]?key|token|password|passwd|secret|authorization|credential)", re.I
    )
    credential_url = re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@", re.I)
    result: list[str] = []
    redact_next = False
    for value in command:
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        if value.startswith("-") and "=" in value:
            flag, _ = value.split("=", 1)
            result.append(f"{flag}=<redacted>" if sensitive.search(flag) else value)
            continue
        if value.startswith("-") and sensitive.search(value):
            result.append(value)
            redact_next = True
            continue
        if sensitive.search(value) and not value.startswith("-"):
            result.append("<redacted>")
            continue
        result.append(credential_url.sub(r"\1<redacted>@", value))
    return result


__all__ = ["finalize_execution", "start_execution_profile", "write_execution_profile"]
