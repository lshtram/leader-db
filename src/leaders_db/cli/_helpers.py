"""Shared helpers used by every per-stage command submodule.

The three helpers cover the cross-stage concerns:

- :func:`_safe_load_config` — load a :class:`RunConfig` from YAML,
  falling back to defaults if the file is missing. Used by every
  Stage 0–15 command that needs the run config (database URL,
  target year, source selection).
- :func:`_not_implemented_yet` — the consistent "stub" message
  every unimplemented stage command prints. Keeps the surface
  enumerable in ``leaders-db --help`` while signalling which
  module the next implementer should edit.
- :func:`_parse_years_flag` — parse a comma-separated
  ``--years`` value (used by the vertical slice command) into a
  deduplicated tuple of integers, raising :class:`typer.BadParameter`
  on a non-integer component.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import RunConfig, load_config


def _safe_load_config(path: Path) -> RunConfig:
    """Load a config, falling back to defaults if the file is missing."""
    if not path.exists():
        typer.echo(
            f"[info] config {path} not found; using RunConfig() defaults. "
            f"Run `cp .env.example .env` and create configs/prototype-2023.yaml "
            f"to override.",
            err=True,
        )
        return RunConfig()
    return load_config(path)


def _parse_years_flag(value: str) -> tuple[int, ...]:
    """Parse a ``--years`` value like ``"2020,2021,2022,2023"``.

    Duplicates are dropped, the order is preserved (the orchestrator
    sorts the tuple for stability), and an empty string after parsing
    is treated as "no years requested" (returns an empty tuple). A
    non-integer component raises :class:`typer.BadParameter` so the
    caller sees a clear, actionable error.
    """
    parts = [chunk.strip() for chunk in value.split(",")]
    parts = [chunk for chunk in parts if chunk]
    parsed: list[int] = []
    seen: set[int] = set()
    for chunk in parts:
        try:
            year = int(chunk)
        except ValueError as exc:
            raise typer.BadParameter(
                f"--years must be a comma-separated list of integers "
                f"(e.g. 2020,2021,2022,2023); got {chunk!r}"
            ) from exc
        if year in seen:
            continue
        seen.add(year)
        parsed.append(year)
    return tuple(parsed)


def _not_implemented_yet(module: str, note: str = "") -> None:
    """Consistent 'stub' message for unimplemented stages."""
    msg = f"[stub] {module}: not implemented yet."
    if note:
        msg += f" {note}"
    typer.echo(msg)


__all__ = [
    "_not_implemented_yet",
    "_parse_years_flag",
    "_safe_load_config",
]
