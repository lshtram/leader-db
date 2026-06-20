"""Stage 2 — ``ingest-source`` command.

The Stage 2 dispatcher looks up ``--source`` in the
:data:`leaders_db.ingest.STAGE2_ADAPTERS` table and delegates to
the matching adapter. Sources without an entry fall through to the
standard "not implemented yet" message so the CLI surface stays
enumerable in ``leaders-db --help``.

Most adapters accept ``year=`` and ignore it if the source is a
single-snapshot (FAS) or all-years (WDI). The Wikipedia Action API
adapter is the exception: its input contract is a list of
``queries=`` (the orchestrator never browses). Pass one or more
``--query`` values when ``--source wikipedia_search_extract``; if
none are given, the CLI fails fast with a clear Typer error rather
than surfacing the opaque ``TypeError`` from passing ``year=`` to a
queries-only adapter.

The CLI surfaces the adapter's ``IngestResult.attribution`` so the
AGENTS.md rule #15 attribution text is printed end-of-run (mirroring
the source-attribution block on the Stage 9 CSV).
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _not_implemented_yet, _safe_load_config


@app.command("ingest-source")
def ingest_source(
    source: str = typer.Option(..., "--source", "-s", help="Source key, e.g. vdem"),
    year: int = typer.Option(
        None, "--year", "-y", help="Filter to a single year (default: all years in the source)"
    ),
    query: list[str] | None = typer.Option(
        None,
        "--query",
        "-q",
        help=(
            "Wikipedia Action API query / topic. Repeat the flag for "
            "multiple queries (e.g. --query 'Joe Biden' --query 'AMLO'). "
            "Required when --source is 'wikipedia_search_extract' "
            "(the adapter does not browse; queries are the deterministic "
            "input contract per AGENTS.md). Ignored for every other source."
        ),
    ),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 2: ingest one external source into ``data/processed/<source>/``.

    The dispatch lives in :data:`leaders_db.ingest.STAGE2_ADAPTERS`. Adding
    a new source is a two-line change: implement the adapter module, then
    add an entry to the table.

    Sources without an entry fall through to the standard "not implemented
    yet" message so the CLI surface stays enumerable in ``--help``.

    Most adapters accept ``year=`` and ignore it if the source is a
    single-snapshot (FAS) or all-years (WDI). The Wikipedia Action API
    adapter is the exception: its input contract is a list of
    ``queries=`` (the orchestrator never browses). Pass one or more
    ``--query`` values when ``--source wikipedia_search_extract``; if
    none are given, the CLI fails fast with a clear Typer error rather
    than surfacing the opaque ``TypeError`` from passing ``year=`` to a
    queries-only adapter.
    """
    from ..ingest import STAGE2_ADAPTERS

    # Validate against the dispatch table's keys, not PRIORITY_SOURCES.
    # PRIORITY_SOURCES is the data-lake folder list (used by
    # ``init-data-lake`` to create ``data/raw/<source>/``); the CLI
    # accepts the *source key* (which may differ from the folder name
    # -- e.g. ``pts`` vs ``political_terror_scale`` for PTS).
    if source not in STAGE2_ADAPTERS:
        raise typer.BadParameter(
            f"unknown source '{source}'. Known: "
            f"{', '.join(sorted(STAGE2_ADAPTERS.keys()))}"
        )
    cfg = _safe_load_config(config)

    adapter = STAGE2_ADAPTERS.get(source)
    if adapter is None:
        typer.echo(f"[Stage 2] ingest source: {source}")
        _not_implemented_yet(
            f"ingest/{source}.py",
            "Phase C. Source must have a vetted_ok / vetted_with_caveats verdict "
            "from Phase B before this is implemented, AND the adapter must be "
            "added to STAGE2_ADAPTERS in leaders_db.ingest.",
        )
        return

    # Wikipedia Action API is the only adapter whose CLI input contract
    # is "explicit queries" (the helper does NOT browse). Fail with a
    # clear, actionable Typer error rather than letting the
    # ``adapter(year=...)`` call surface a TypeError. Other adapters
    # take ``year=`` and ignore unknown kwargs (or accept them silently
    # via **kwargs); this branch keeps them on the unchanged path.
    if source == "wikipedia_search_extract":
        if not query:
            raise typer.BadParameter(
                "--source wikipedia_search_extract requires one or more "
                "--query values (e.g. --query 'Joe Biden'). "
                "The adapter does not browse; queries are the "
                "deterministic input contract."
            )
        typer.echo(
            f"[Stage 2] ingest source: {source} "
            f"(queries={list(query)})"
        )
        result = adapter(queries=list(query))
    else:
        # Use the config's target year if the user did not pass --year.
        effective_year = (
            year if year is not None else cfg.project.target_year
        )
        typer.echo(
            f"[Stage 2] ingest source: {source} (year={effective_year})"
        )
        # Adapters accept ``year`` as a kwarg when they support
        # filtering; they all do. Pass it through unconditionally.
        result = adapter(year=effective_year)

    # Print the adapter's result summary. Adapters return a Pydantic
    # ``IngestResult`` (or equivalent) that carries the attribution
    # (Rule #15) so the CLI surfaces it to the user.
    typer.echo("Done. Summary:")
    for field in (
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "years",
        "indicators",
    ):
        if hasattr(result, field):
            typer.echo(f"  {field}: {getattr(result, field)}")

    # Rule #15: every public output that touches a source must include
    # the source's attribution. The ``IngestResult`` carries it as a
    # ``.attribution`` property; the CLI surfaces it to the user.
    attribution_text = getattr(result, "attribution", None)
    if attribution_text:
        typer.echo("Attribution:")
        for line in attribution_text.splitlines():
            typer.echo(f"  {line}")


__all__ = ["ingest_source"]
