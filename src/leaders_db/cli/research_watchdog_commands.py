"""Research shard watchdog CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .research_common import fail


def register_watchdog_commands(research_app: typer.Typer) -> None:
    research_app.command("validate-shard-output")(research_validate_shard_output_cmd)


def research_validate_shard_output_cmd(
    status_path: Path = typer.Option(..., "--status", exists=False, dir_okay=False),
    input_path: Path | None = typer.Option(None, "--input", dir_okay=False),
    output_path: Path | None = typer.Option(None, "--output", dir_okay=False),
    expected_record_count: int | None = typer.Option(None, "--expected-record-count", min=1),
    max_expected_minutes: int = typer.Option(30, "--max-expected-minutes", min=1),
    max_progress_stale_minutes: int | None = typer.Option(
        None, "--max-progress-stale-minutes", min=1
    ),
    progress_message: str | None = typer.Option(None, "--progress-message"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Validate an externally-produced research shard artifact."""

    from ..research.watchdog import (
        build_shard_status,
        load_shard_status,
        record_shard_progress,
        validate_shard_output,
        write_shard_status,
    )

    try:
        if status_path.exists():
            status = load_shard_status(status_path)
        else:
            if input_path is None or output_path is None or expected_record_count is None:
                raise ValueError(
                    "--input, --output, and --expected-record-count are required "
                    "when creating a status file"
                )
            status = build_shard_status(
                input_path=input_path,
                output_path=output_path,
                expected_record_count=expected_record_count,
                max_expected_minutes=max_expected_minutes,
                max_progress_stale_minutes=max_progress_stale_minutes,
            )
        if progress_message is not None:
            status = record_shard_progress(status, message=progress_message)
        status = validate_shard_output(status)
        write_shard_status(status_path, status)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc), output_json=output_json)

    if output_json:
        typer.echo(json.dumps(status, indent=2, sort_keys=True))
        return
    typer.echo(f"status: {status['status']}")


__all__ = ["register_watchdog_commands", "research_validate_shard_output_cmd"]
