"""Minimal Codex subprocess boundary for MiniMax workers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .docker_runner import cleanup_runtime, docker_command, start_runtime
from .models import WorkerConfig


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    runner_backend: str
    docker_image: str


def configured_profiles(config: WorkerConfig) -> tuple[ModelProfile, ...]:
    return tuple(
        ModelProfile(
            name=item.name,
            model=item.model,
            runner_backend=config.runner_backend,
            docker_image=config.docker_image,
        )
        for item in config.profiles
    )


def invoke_model(
    *,
    profile: ModelProfile,
    prompt: str,
    role: str,
    manifest_path: Path,
    registry_path: Path,
    output_dir: Path,
    worker_dir: Path,
    socket_path: Path,
    capability: str,
    label: str,
    timeout: int,
) -> dict[str, Any]:
    call_dir = output_dir / "calls" / label
    call_dir.mkdir(parents=True, exist_ok=True)
    events_path = call_dir / "events.jsonl"
    stderr_path = call_dir / "stderr.txt"
    final_path = call_dir / "final.txt"
    worker_final_path = worker_dir / f".{label}-final.txt"
    runtime = None
    if profile.runner_backend == "docker":
        runtime = start_runtime(image=profile.docker_image, label=label)
        command = docker_command(
            profile_name=profile.name,
            model=profile.model,
            image=profile.docker_image,
            worker_dir=worker_dir,
            final_path=worker_final_path,
            runtime=runtime,
        )
    else:
        command = _codex_command(profile, worker_dir, worker_final_path)
    environment = os.environ.copy()
    environment.update(
        {
            "EVIDENCE_SOCKET": str(socket_path.resolve()),
            "EVIDENCE_CAPABILITY": capability,
            "SIMPLE_EVIDENCE_PYTHON": sys.executable,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
    )
    started = time.monotonic()
    result: subprocess.CompletedProcess[str] | None = None
    try:
        with (
            events_path.open("w", encoding="utf-8") as events,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=events,
                stderr=stderr,
                env=environment,
                timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{profile.name} exceeded {timeout} seconds") from exc
    finally:
        if runtime is not None:
            cleanup_runtime(runtime)
        if worker_final_path.exists():
            final_path.write_text(
                worker_final_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            worker_final_path.unlink()
    if result is None:
        raise RuntimeError(f"{profile.name} did not return a process result")
    return {
        "label": label,
        "profile": profile.name,
        "model": profile.model,
        "returncode": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **read_usage(events_path),
    }


def _codex_command(
    profile: ModelProfile,
    worker_dir: Path,
    final_path: Path,
) -> list[str]:
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
    ]
    if profile.model == "MiniMax-M3":
        for server in ("minimax", "fetch", "brave", "parallel"):
            command.extend(("-c", f"mcp_servers.{server}.enabled=false"))
    command.extend(
        (
            "-",
            "--json",
            "--color",
            "never",
            "--cd",
            str(worker_dir),
            "--output-last-message",
            str(final_path),
            "--profile",
            profile.name,
            "--model",
            profile.model,
        )
    )
    command.extend(("--sandbox", "workspace-write"))
    return command


def read_usage(path: Path) -> dict[str, int]:
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "turn.completed" or not isinstance(
            event.get("usage"), dict
        ):
            continue
        for key in usage:
            usage[key] += int(event["usage"].get(key, 0) or 0)
    if not usage["total_tokens"]:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


__all__ = ["ModelProfile", "configured_profiles", "invoke_model"]
