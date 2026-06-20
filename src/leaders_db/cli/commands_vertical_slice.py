"""``run-vertical-slice-2023`` command.

The vertical slice 2023 is a named experimental Stage 3–15 mini-
orchestrator that proves the Stage 2-to-validation flow on a
deliberately narrow scope (``MEX`` / ``NGA`` / ``USA`,
``social_wellbeing`` + ``integrity``) before the real pipeline
lands. It is NOT the production Stage 3-15 pipeline; it scores with
provisional formulas and writes the three output files under
``data/outputs/vertical_slice_2023/``.

When ``--years`` is provided, an additional source-only multi-year
time-series CSV is written. The DB (ruler_years / ruler_scores /
validation_results) stays 2023-only.

See ``docs/architecture/vertical-slice-2023.md`` for the canonical
scope statement.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _parse_years_flag, _safe_load_config


@app.command("run-vertical-slice-2023")
def run_vertical_slice_2023(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
    countries: str = typer.Option(
        "MEX,NGA,USA",
        "--countries",
        help="Comma-separated ISO3 scope, e.g. MEX,NGA,USA.",
    ),
    categories: str = typer.Option(
        "social_wellbeing,integrity",
        "--categories",
        help="Comma-separated category keys to score.",
    ),
    years: str | None = typer.Option(
        None,
        "--years",
        help=(
            "Optional comma-separated year list for a multi-year "
            "source-only time-series CSV (e.g. 2020,2021,2022,2023). "
            "When set, the orchestrator additionally writes "
            "data/outputs/vertical_slice_2023/vertical_slice_timeseries.csv. "
            "DB writes remain 2023-only regardless."
        ),
    ),
    run_adapters: bool = typer.Option(
        True,
        "--run-adapters/--no-run-adapters",
        help=(
            "When set, the slice runs the UNDP HDI Stage 2 adapter "
            "(and WGI if its xlsx is locally available) before scoring. "
            "When --no-run-adapters is passed, the slice reads "
            "already-staged source_observations rows only."
        ),
    ),
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Override the SQLite URL (otherwise uses RunConfig.database.url).",
    ),
    client_xlsx: Path | None = typer.Option(
        None,
        "--client-xlsx",
        help=(
            "Override the client xlsx path "
            "(otherwise picks the first xlsx under data/raw/client_existing/)."
        ),
    ),
) -> None:
    """Run the 2023 vertical slice end-to-end.

    This is a named experimental slice per
    ``docs/architecture/vertical-slice-2023.md``. It is NOT the real
    Stage 3-15 pipeline — it scores MEX/NGA/USA on
    ``social_wellbeing`` and ``integrity`` with provisional formulas and
    writes the three output files under
    ``data/outputs/vertical_slice_2023/``.

    When ``--years`` is provided, an additional source-only multi-year
    time-series CSV is written. The DB (ruler_years / ruler_scores /
    validation_results) stays 2023-only.
    """
    cfg = _safe_load_config(config)
    iso3_scope = tuple(c.strip().upper() for c in countries.split(",") if c.strip())
    category_scope = tuple(c.strip() for c in categories.split(",") if c.strip())
    years_tuple: tuple[int, ...] = (
        _parse_years_flag(years) if years else ()
    )

    typer.echo(
        f"[vertical_slice_2023] target_year={cfg.project.target_year} "
        f"countries={iso3_scope} categories={category_scope} "
        f"run_adapters={run_adapters} "
        f"years={years_tuple or '(2023-only)'}"
    )

    # Local import keeps the CLI lean — only the slice command pays the
    # parser/import cost.
    from ..vertical_slice.slice_2023 import run_vertical_slice_2023 as _run

    result = _run(
        cfg,
        countries=iso3_scope,
        categories=category_scope,
        run_adapters=run_adapters,
        database_url=database_url,
        client_xlsx=client_xlsx,
        years=years_tuple or None,
    )

    typer.echo("Done. Summary:")
    typer.echo(f"  client_rows_parsed:    {result.client_rows_parsed}")
    typer.echo(f"  countries_seeded:      {result.countries_seeded}")
    typer.echo(f"  observations_linked:   {result.observations_linked}")
    typer.echo(f"  ruler_years_written:   {result.ruler_years_written}")
    typer.echo(f"  score_rows_written:    {result.score_rows_written}")
    typer.echo(f"  validation_rows_written: {result.validation_rows_written}")
    typer.echo(f"  sources_used:          {', '.join(result.sources_used) or '(none)'}")
    if result.timeseries_years:
        typer.echo(
            f"  timeseries_years:      {result.timeseries_years} "
            f"(rows={result.timeseries_rows_written})"
        )
        typer.echo(f"  timeseries_csv_path:   {result.timeseries_csv_path}")
    if result.skipped:
        typer.echo("  skipped:")
        for iso3, cat, reason in result.skipped:
            typer.echo(f"    - {iso3} / {cat}: {reason}")
    typer.echo(f"  score_csv_path:    {result.score_csv_path}")
    typer.echo(f"  comparison_csv:    {result.comparison_csv_path}")
    typer.echo(f"  summary_md_path:   {result.summary_md_path}")
    typer.echo(
        "Caveat: this is a provisional, experimental vertical slice — "
        "not the final scoring."
    )


__all__ = ["run_vertical_slice_2023"]
