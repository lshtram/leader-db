"""Direct Parallel API research CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .research_common import fail


def register_parallel_commands(research_app: typer.Typer) -> None:
    research_app.command("parallel-search")(research_parallel_search_cmd)


def research_parallel_search_cmd(
    objective: str | None = typer.Option(None, "--objective"),
    queries: list[str] | None = typer.Option(None, "--query"),
    output_path: Path = typer.Option(..., "--output", "-o", dir_okay=False, writable=True),
    timeout_seconds: float = typer.Option(30.0, "--timeout", min=1.0),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Call Parallel Search directly and persist the full JSON response."""

    from ..env import env_value
    from ..research.parallel_api import (
        ParallelApiError,
        ParallelSearchRequest,
        call_parallel_search,
        write_parallel_search_response,
    )

    api_key = env_value("PARALLEL_API_KEY")
    if not api_key:
        fail("PARALLEL_API_KEY is required in the environment or .env", output_json=output_json)

    search_queries = [query.strip() for query in (queries or ()) if query.strip()]
    if not search_queries:
        fail("At least one --query value is required", output_json=output_json)

    try:
        request = ParallelSearchRequest(objective=objective, search_queries=search_queries)
        payload, elapsed_seconds = call_parallel_search(
            request,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        summary = write_parallel_search_response(
            payload,
            output_path=output_path,
            elapsed_seconds=elapsed_seconds,
        )
    except (ParallelApiError, ValueError) as exc:
        fail(str(exc), output_json=output_json)

    summary_payload = summary.model_dump(mode="json")
    if output_json:
        typer.echo(json.dumps(summary_payload, indent=2, sort_keys=True))
        return
    typer.echo(
        f"parallel_search_written: {summary.output_path}; "
        f"results: {summary.result_count}; elapsed_seconds: {summary.elapsed_seconds}"
    )


__all__ = ["register_parallel_commands", "research_parallel_search_cmd"]
