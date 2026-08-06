"""Bounded, audit-preserving selection of CLI extraction attempt directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import EvidenceFunnelConfig
from .low_cost import assert_low_cost_stage_profiles


@dataclass(frozen=True)
class CliAttemptSelection:
    """Selected attempt directory and all prior directories for token accounting."""

    root: Path
    prior_roots: tuple[Path, ...]
    exhausted: bool


@dataclass(frozen=True)
class CliAttemptPlan:
    """Ladder-wide attempt plan with complete prior-root accounting."""

    attempts: tuple[tuple[int, str, CliAttemptSelection], ...]
    prior_roots: tuple[Path, ...]


def select_cli_attempt(
    *,
    stage_root: Path,
    attempt: int,
    profile_name: str,
    interruption_retries: int,
) -> CliAttemptSelection:
    """Resume a completed attempt or allocate one bounded interruption retry."""

    base = stage_root / f"cli-attempt-{attempt:02d}-{profile_name}"
    candidates = (
        base,
        *(
            stage_root / f"{base.name}-retry-{retry:02d}"
            for retry in range(1, interruption_retries + 1)
        ),
    )
    existing = tuple(path for path in candidates if path.exists())
    completed = next(
        (path for path in existing if (path / "completion.json").exists()),
        None,
    )
    if completed is not None:
        return CliAttemptSelection(completed, existing, exhausted=False)
    available = next((path for path in candidates if not path.exists()), None)
    if available is not None:
        return CliAttemptSelection(available, existing, exhausted=False)
    return CliAttemptSelection(candidates[-1], existing, exhausted=True)


def extraction_profiles(config: EvidenceFunnelConfig) -> tuple[str, ...]:
    """Return the configured, validated low-cost extraction ladder."""

    assert_low_cost_stage_profiles(config)
    stage = config.stages["extraction"]
    return (stage.model, *stage.fallbacks)[: stage.max_attempts]


def plan_cli_attempts(
    *,
    stage_root: Path,
    profile_names: tuple[str, ...],
    interruption_retries: int,
) -> CliAttemptPlan:
    """Prefer any completed ladder attempt before allocating additional work."""

    selections = tuple(
        (
            attempt,
            profile_name,
            select_cli_attempt(
                stage_root=stage_root,
                attempt=attempt,
                profile_name=profile_name,
                interruption_retries=interruption_retries,
            ),
        )
        for attempt, profile_name in enumerate(profile_names, start=1)
    )
    prior_roots = tuple(
        root
        for _, _, selection in selections
        for root in selection.prior_roots
    )
    completed = next(
        (
            item
            for item in selections
            if (item[2].root / "completion.json").exists()
        ),
        None,
    )
    return CliAttemptPlan(
        attempts=(completed,) if completed is not None else selections,
        prior_roots=prior_roots,
    )
