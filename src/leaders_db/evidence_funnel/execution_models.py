"""Typed execution and resume artifacts for model-assisted stages."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class OutputNormalizationTrace(BaseModel):
    kind: str
    library_version: str | None = None
    raw_sha256: str
    normalized_sha256: str


class DiscardedAttemptTrace(BaseModel):
    attempt_dir: str
    model_profile: str
    attempt: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reason: str
    output_sha256: str | None = None
    events_sha256: str
    stderr_sha256: str


class ValidationRetryTrace(BaseModel):
    output_path: Path
    events_path: Path
    model_profile: str
    attempt: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reason: str
    discarded_attempts: tuple[DiscardedAttemptTrace, ...] = ()


class StageExecutionResult(BaseModel):
    output_path: Path
    events_path: Path
    stderr_path: Path
    raw_output_path: Path | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model_profile: str
    attempt: int
    prior_failures: tuple[str, ...] = ()
    validation_retries: tuple[ValidationRetryTrace, ...] = ()
    normalization: OutputNormalizationTrace | None = None
    discarded_attempts: tuple[DiscardedAttemptTrace, ...] = ()


class ResumeBinding(BaseModel):
    stage: str
    prompt_sha256: str
    schema_sha256: str
    model_profiles: tuple[str, ...]
    stage_profile_sha256: str
    profiles_file_sha256: str
    project_root: str
    allowed_profiles: tuple[str, ...]


class ResumeCompletion(BaseModel):
    output_path: str
    output_sha256: str
    events_sha256: str
    stderr_sha256: str
    raw_output_path: str | None = None
    raw_output_sha256: str | None = None
    model_profile: str
    attempt: int
    prior_failures: tuple[str, ...] = ()
    normalization: OutputNormalizationTrace | None = None
    discarded_attempts: tuple[DiscardedAttemptTrace, ...] = ()


__all__ = [
    "DiscardedAttemptTrace",
    "OutputNormalizationTrace",
    "ResumeBinding",
    "ResumeCompletion",
    "StageExecutionResult",
    "ValidationRetryTrace",
]
