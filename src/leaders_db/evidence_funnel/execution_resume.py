"""Hash-bound, atomic resumption for model-assisted stages."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from .artifacts import ArtifactStore, sha256_file
from .config import EvidenceFunnelConfig
from .execution_models import (
    DiscardedAttemptTrace,
    ResumeBinding,
    ResumeCompletion,
    StageExecutionResult,
)

_LOW_COST_STAGES = frozenset({"mapping", "routing", "extraction", "verification"})


def validate_stage_resume_binding(
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    stage: str,
    prompt: str,
    output_model: type[BaseModel],
    output_dir: Path,
    profiles_path: Path,
    allowed_profiles: frozenset[str] | None = None,
) -> None:
    """Write or validate scientific inputs before consuming failed attempts."""

    from .execution_schema import make_strict_response_schema

    stage_profile = config.stages[stage]
    if stage in _LOW_COST_STAGES:
        from .low_cost import LOW_COST_PROFILES, assert_low_cost_stage_profiles

        assert_low_cost_stage_profiles(config)
        allowed_profiles = LOW_COST_PROFILES
    schema = output_model.model_json_schema()
    make_strict_response_schema(schema)
    binding = _binding(
        project_root=project_root,
        stage=stage,
        prompt=prompt,
        schema=schema,
        stage_profile=stage_profile,
        profiles_path=profiles_path,
        allowed_profiles=allowed_profiles,
    )
    _write_or_validate_binding(
        ArtifactStore(output_dir),
        output_dir / "resume-binding.json",
        output_dir / "resume-completion.json",
        binding,
    )


def execute_or_resume_bound_stage(
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
    accept_result: Callable[[Path], None] | None = None,
) -> StageExecutionResult:
    """Reuse a result only when every scientific and execution input matches."""

    from .execution import execute_stage
    from .execution_schema import make_strict_response_schema

    stage_profile = config.stages[stage]
    if stage in _LOW_COST_STAGES:
        from .low_cost import LOW_COST_PROFILES, assert_low_cost_stage_profiles

        assert_low_cost_stage_profiles(config)
        allowed_profiles = LOW_COST_PROFILES
    schema = output_model.model_json_schema()
    make_strict_response_schema(schema)
    binding = _binding(
        project_root=project_root,
        stage=stage,
        prompt=prompt,
        schema=schema,
        stage_profile=stage_profile,
        profiles_path=profiles_path,
        allowed_profiles=allowed_profiles,
    )
    store = ArtifactStore(output_dir)
    binding_path = output_dir / "resume-binding.json"
    completion_path = output_dir / "resume-completion.json"
    _write_or_validate_binding(store, binding_path, completion_path, binding)
    if completion_path.exists():
        result = _resume(
            output_dir,
            completion_path,
            output_model,
            allowed_profiles,
        )
        if accept_result is not None:
            accept_result(result.output_path)
        return result
    result = execute_stage(
        project_root=project_root,
        config=config,
        stage=stage,
        prompt=prompt,
        output_model=output_model,
        output_dir=output_dir,
        profiles_path=profiles_path,
        allowed_profiles=allowed_profiles,
        defer_invalid_content_to_stage_adapter=defer_invalid_content_to_stage_adapter,
    )
    if accept_result is not None:
        accept_result(result.output_path)
    completion = _completion(output_dir, result)
    store.write_immutable("resume-completion.json", completion)
    return result


def _binding(
    *,
    project_root: Path,
    stage: str,
    prompt: str,
    schema: dict,
    stage_profile,
    profiles_path: Path,
    allowed_profiles: frozenset[str] | None,
) -> ResumeBinding:
    return ResumeBinding(
        stage=stage,
        prompt_sha256=sha256(prompt.encode()).hexdigest(),
        schema_sha256=sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        model_profiles=(stage_profile.model, *stage_profile.fallbacks),
        stage_profile_sha256=sha256(
            stage_profile.model_dump_json().encode()
        ).hexdigest(),
        profiles_file_sha256=sha256_file(profiles_path),
        project_root=str(project_root.resolve()),
        allowed_profiles=tuple(sorted(allowed_profiles or ())),
    )


def _write_or_validate_binding(
    store: ArtifactStore,
    binding_path: Path,
    completion_path: Path,
    binding: ResumeBinding,
) -> None:
    if binding_path.exists():
        stored = ResumeBinding.model_validate_json(
            binding_path.read_text(encoding="utf-8")
        )
        if stored != binding:
            raise ValueError(f"resume binding mismatch: {binding_path.parent}")
        return
    if completion_path.exists():
        raise ValueError(f"unbound completion cannot be resumed: {binding_path.parent}")
    store.write_immutable("resume-binding.json", binding)


def _resume(
    output_dir: Path,
    completion_path: Path,
    output_model: type[BaseModel],
    allowed_profiles: frozenset[str] | None,
) -> StageExecutionResult:
    from .execution import read_stage_usage

    completion = ResumeCompletion.model_validate_json(
        completion_path.read_text(encoding="utf-8")
    )
    _validate_normalization(completion)
    _validate_discarded(output_dir, completion.discarded_attempts)
    if allowed_profiles is not None and completion.model_profile not in allowed_profiles:
        raise ValueError("resumed model profile is no longer allowed")
    output_path = _safe_path(output_dir, completion.output_path)
    attempt_dir = output_path.parent
    events_path = attempt_dir / "events.jsonl"
    stderr_path = attempt_dir / "stderr.txt"
    expected = [
        (output_path, completion.output_sha256),
        (events_path, completion.events_sha256),
        (stderr_path, completion.stderr_sha256),
    ]
    raw_output_path = None
    if completion.raw_output_path is not None:
        raw_output_path = _safe_path(output_dir, completion.raw_output_path)
        expected.append((raw_output_path, completion.raw_output_sha256 or ""))
    _validate_hashes(expected, "resumable stage artifact changed")
    output_model.model_validate_json(output_path.read_text(encoding="utf-8"))
    usage = read_stage_usage(events_path)
    input_tokens, output_tokens, total_tokens = _aggregate_usage(
        usage,
        completion.discarded_attempts,
    )
    return StageExecutionResult(
        output_path=output_path,
        events_path=events_path,
        stderr_path=stderr_path,
        raw_output_path=raw_output_path,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        model_profile=completion.model_profile,
        attempt=completion.attempt,
        prior_failures=completion.prior_failures,
        normalization=completion.normalization,
        discarded_attempts=completion.discarded_attempts,
    )


def _completion(output_dir: Path, result: StageExecutionResult) -> ResumeCompletion:
    return ResumeCompletion(
        output_path=str(result.output_path.relative_to(output_dir)),
        output_sha256=sha256_file(result.output_path),
        events_sha256=sha256_file(result.events_path),
        stderr_sha256=sha256_file(result.stderr_path),
        raw_output_path=(
            str(result.raw_output_path.relative_to(output_dir))
            if result.raw_output_path is not None
            else None
        ),
        raw_output_sha256=(
            sha256_file(result.raw_output_path)
            if result.raw_output_path is not None
            else None
        ),
        model_profile=result.model_profile,
        attempt=result.attempt,
        prior_failures=result.prior_failures,
        normalization=result.normalization,
        discarded_attempts=result.discarded_attempts,
    )


def _validate_normalization(completion: ResumeCompletion) -> None:
    if (completion.normalization is None) != (completion.raw_output_path is None):
        raise ValueError("normalization trace and raw output presence differ")
    if completion.raw_output_path is None and completion.raw_output_sha256 is not None:
        raise ValueError("raw output hash exists without a raw output artifact")
    trace = completion.normalization
    if trace is not None and (
        trace.raw_sha256 != completion.raw_output_sha256
        or trace.normalized_sha256 != completion.output_sha256
    ):
        raise ValueError("normalization trace hashes differ from completion")


def _validate_discarded(
    output_dir: Path,
    attempts: tuple[DiscardedAttemptTrace, ...],
) -> None:
    from .execution import read_stage_usage

    for attempt in attempts:
        expected_name = f"attempt-{attempt.attempt:02d}-{attempt.model_profile}"
        if attempt.attempt_dir != expected_name:
            raise ValueError("discarded attempt identity differs from its directory")
        attempt_dir = _safe_path(output_dir, attempt.attempt_dir)
        expected = [
            (attempt_dir / "events.jsonl", attempt.events_sha256),
            (attempt_dir / "stderr.txt", attempt.stderr_sha256),
        ]
        if attempt.output_sha256 is not None:
            expected.append((attempt_dir / "output.json", attempt.output_sha256))
        _validate_hashes(expected, "discarded attempt artifact changed")
        usage = read_stage_usage(attempt_dir / "events.jsonl")
        if _usage_tuple(usage) != (
            attempt.input_tokens,
            attempt.output_tokens,
            attempt.total_tokens,
        ):
            raise ValueError("discarded attempt usage differs from its event log")


def _aggregate_usage(
    usage: dict[str, int],
    attempts: tuple[DiscardedAttemptTrace, ...],
) -> tuple[int, int, int]:
    current = _usage_tuple(usage)
    return (
        current[0] + sum(item.input_tokens for item in attempts),
        current[1] + sum(item.output_tokens for item in attempts),
        current[2] + sum(item.total_tokens for item in attempts),
    )


def _usage_tuple(usage: dict[str, int]) -> tuple[int, int, int]:
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    return (
        input_tokens,
        output_tokens,
        usage.get("total_tokens", 0) or input_tokens + output_tokens,
    )


def _safe_path(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / relative).resolve()
    if not path.is_relative_to(resolved_root):
        raise ValueError("resumed artifact path escapes its stage directory")
    return path


def _validate_hashes(expected: list[tuple[Path, str]], message: str) -> None:
    if any(not path.exists() or sha256_file(path) != digest for path, digest in expected):
        raise ValueError(message)


__all__ = ["execute_or_resume_bound_stage", "validate_stage_resume_binding"]
