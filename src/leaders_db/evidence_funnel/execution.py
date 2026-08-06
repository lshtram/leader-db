"""Configured Codex-model execution boundary for evidence-funnel stages."""

from __future__ import annotations

import json
import re
import subprocess
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

from pydantic import BaseModel

from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import load_research_model_profiles

from .artifacts import sha256_file
from .config import EvidenceFunnelConfig
from .execution_models import (
    DiscardedAttemptTrace,
    OutputNormalizationTrace,
    StageExecutionResult,
    ValidationRetryTrace,
)
from .execution_schema import make_strict_response_schema
from .process import run_isolated_process

_LOW_COST_STAGES = frozenset({"mapping", "routing", "extraction", "verification"})
_SAFE_PROFILE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def execute_stage(  # noqa: PLR0912, PLR0915
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    stage: str,
    prompt: str,
    output_model: type[BaseModel],
    output_dir: Path,
    profiles_path: Path,
    allowed_profiles: frozenset[str] | None = None,
    defer_invalid_content_to_stage_adapter: bool = False,
) -> StageExecutionResult:
    """Execute one configured, no-search stage and persist its complete trace."""

    stage_profile = config.stages[stage]
    if stage in _LOW_COST_STAGES:
        from .low_cost import LOW_COST_PROFILES, assert_low_cost_stage_profiles

        assert_low_cost_stage_profiles(config)
        allowed_profiles = LOW_COST_PROFILES
    profiles = load_research_model_profiles(profiles_path).profiles
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "prompt.txt"
    schema_path = output_dir / "schema.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    schema = output_model.model_json_schema()
    make_strict_response_schema(schema)
    schema_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    profile_names = (stage_profile.model, *stage_profile.fallbacks)
    unsafe = [name for name in profile_names if not _SAFE_PROFILE.fullmatch(name)]
    if unsafe:
        raise ValueError(f"unsafe model profile names: {unsafe}")
    if allowed_profiles is not None:
        forbidden = sorted(set(profile_names) - allowed_profiles)
        if forbidden:
            raise ValueError(f"{stage} cannot use model profiles: {forbidden}")
    failures: list[str] = []
    discarded_attempts: list[DiscardedAttemptTrace] = []
    for attempt, profile_name in enumerate(profile_names[: stage_profile.max_attempts], start=1):
        attempt_dir = output_dir / f"attempt-{attempt:02d}-{profile_name}"
        if attempt_dir.exists():
            output_path = attempt_dir / "output.json"
            events_path = attempt_dir / "events.jsonl"
            stderr_path = attempt_dir / "stderr.txt"
            reason = f"{profile_name}: prior output required stage-adapter retry"
            failures.append(reason)
            discarded_attempts.append(
                _discarded_attempt_trace(
                    attempt_dir,
                    profile_name,
                    attempt,
                    output_path,
                    events_path,
                    stderr_path,
                    reason,
                )
            )
            continue
        attempt_dir.mkdir(parents=True, exist_ok=True)
        output_path = attempt_dir / "output.json"
        events_path = attempt_dir / "events.jsonl"
        stderr_path = attempt_dir / "stderr.txt"
        command = build_codex_exec_command(
            profile=profiles[profile_name],
            project_root=project_root,
            schema_path=schema_path,
            final_message_path=output_path,
            writable_dir=attempt_dir,
            isolated_web_research=True,
        )
        command = _without_optional_m3_servers(command, profile_name)
        try:
            with (
                events_path.open("w", encoding="utf-8") as events,
                stderr_path.open("w", encoding="utf-8") as stderr,
            ):
                result = run_isolated_process(
                    command,
                    input_text=prompt,
                    stdout=events,
                    stderr=stderr,
                    timeout=stage_profile.attempt_timeout_seconds,
                )
        except subprocess.TimeoutExpired:
            reason = (
                f"{profile_name}: attempt exceeded configured "
                f"{stage_profile.attempt_timeout_seconds}-second timeout"
            )
            failures.append(reason)
            discarded_attempts.append(
                _discarded_attempt_trace(
                    attempt_dir,
                    profile_name,
                    attempt,
                    output_path,
                    events_path,
                    stderr_path,
                    reason,
                )
            )
            continue
        if result.returncode:
            reason = _failure_summary(profile_name, events_path, stderr_path)
            failures.append(reason)
            discarded_attempts.append(
                _discarded_attempt_trace(
                    attempt_dir,
                    profile_name,
                    attempt,
                    output_path,
                    events_path,
                    stderr_path,
                    reason,
                )
            )
            continue
        try:
            output_model.model_validate_json(output_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            try:
                from .routing import extract_json_object_with_trace

                if output_model.model_config.get("extra") != "forbid":
                    raise ValueError("envelope normalization requires extra='forbid'")
                raw_output = output_path.read_text(encoding="utf-8")
                payload, normalization_kind = extract_json_object_with_trace(raw_output)
                output_model.model_validate(payload)
            except (ValueError, OSError) as normalization_exc:
                failures.append(
                    f"{profile_name}: invalid structured output: {exc}; "
                    f"deterministic envelope normalization failed: {normalization_exc}"
                )
                discarded_attempts.append(
                    _discarded_attempt_trace(
                        attempt_dir,
                        profile_name,
                        attempt,
                        output_path,
                        events_path,
                        stderr_path,
                        failures[-1],
                    )
                )
                if defer_invalid_content_to_stage_adapter:
                    raise RuntimeError(failures[-1]) from normalization_exc
                continue
            raw_output_path = attempt_dir / "raw-output.txt"
            raw_output_path.write_text(raw_output, encoding="utf-8")
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            normalization = OutputNormalizationTrace(
                kind=normalization_kind,
                library_version=(
                    version("json-repair") if normalization_kind.endswith("json-repair") else None
                ),
                raw_sha256=sha256(raw_output.encode()).hexdigest(),
                normalized_sha256=sha256_file(output_path),
            )
        else:
            raw_output_path = None
            normalization = None
        usage = read_stage_usage(events_path)
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        reported_total = usage.get("total_tokens", 0)
        discarded_input = sum(item.input_tokens for item in discarded_attempts)
        discarded_output = sum(item.output_tokens for item in discarded_attempts)
        discarded_total = sum(item.total_tokens for item in discarded_attempts)
        return StageExecutionResult(
            output_path=output_path,
            events_path=events_path,
            stderr_path=stderr_path,
            raw_output_path=raw_output_path,
            input_tokens=input_tokens + discarded_input,
            output_tokens=output_tokens + discarded_output,
            total_tokens=((reported_total or input_tokens + output_tokens) + discarded_total),
            model_profile=profile_name,
            attempt=attempt,
            prior_failures=tuple(failures),
            normalization=normalization,
            discarded_attempts=tuple(discarded_attempts),
        )
    raise RuntimeError(f"{stage} exhausted configured attempts: {' | '.join(failures)}")


def _without_optional_m3_servers(
    command: tuple[str, ...],
    profile_name: str,
) -> tuple[str, ...]:
    if profile_name != "minimax-m3-long-context":
        return command
    overrides = tuple(
        item
        for name in ("minimax", "fetch", "brave", "parallel")
        for item in ("-c", f"mcp_servers.{name}.enabled=false")
    )
    return (*command[:2], *overrides, *command[2:])


def read_stage_usage(events_path: Path) -> dict[str, int]:
    """Read the final provider-reported usage record from a stage event log."""

    usage: dict[str, int] = {}
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = {
                key: int(value) for key, value in event["usage"].items() if isinstance(value, int)
            }
    return usage


def _discarded_attempt_trace(
    attempt_dir: Path,
    profile_name: str,
    attempt: int,
    output_path: Path,
    events_path: Path,
    stderr_path: Path,
    reason: str,
) -> DiscardedAttemptTrace:
    usage = read_stage_usage(events_path)
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    reported_total = usage.get("total_tokens", 0)
    return DiscardedAttemptTrace(
        attempt_dir=attempt_dir.name,
        model_profile=profile_name,
        attempt=attempt,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=reported_total or input_tokens + output_tokens,
        reason=reason,
        output_sha256=sha256_file(output_path) if output_path.exists() else None,
        events_sha256=sha256_file(events_path),
        stderr_sha256=sha256_file(stderr_path),
    )


def _failure_summary(profile_name: str, events_path: Path, stderr_path: Path) -> str:
    error = stderr_path.read_text(encoding="utf-8").strip()
    if not error:
        for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") in {"error", "turn.failed"}:
                error = str(event.get("message") or event.get("error"))
                break
    return f"{profile_name}: {error or 'execution failed without an error message'}"


__all__ = [
    "DiscardedAttemptTrace",
    "OutputNormalizationTrace",
    "StageExecutionResult",
    "ValidationRetryTrace",
    "execute_stage",
    "read_stage_usage",
]
