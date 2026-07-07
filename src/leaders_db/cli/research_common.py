"""Shared helpers for research CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer


def load_evaluations(input_path: Path, model: Any) -> tuple[Any, ...]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "evaluations" in raw:
        raw = raw["evaluations"]
    if not isinstance(raw, list):
        raise ValueError("input JSON must be an array or an object with an 'evaluations' array")
    return tuple(model.model_validate(item) for item in raw)


def fail(message: str, *, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps({"error": message}, sort_keys=True))
    else:
        typer.echo(f"error: {message}")
    raise typer.Exit(1)


__all__ = ["fail", "load_evaluations"]
