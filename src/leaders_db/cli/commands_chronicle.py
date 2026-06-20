"""``run-country-year-chronicle`` command.

The Country-Year Chronicle (CYC) is an experimental vertical slice that
emits a CSV of country-year profile rows for a user-specified window of
years and ISO3 codes. The command is read-only — it does not touch the
client matrix, the LLM, or the main prototype database.

Usage:

    leaders-db run-country-year-chronicle \\
        --start-year 1900 --end-year 2026 \\
        --countries USA,GBR,FRA,IND,RUS,SUN,CHN \\
        --output data/outputs/country-year-chronicle/pilot.csv

The default ISO3 scope, year window, and output path match the
Increment 0 plan in
:file:`docs/country-year-chronicle-increment-0.md`. The command always
writes an attribution comment block before the header per
:file:`docs/source-attributions.md` §3.2.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..chronicle import (
    CHRONICLE_OUTPUT_DIR_NAME,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_START_YEAR,
    ChronicleResult,
    run_country_year_chronicle,
)
from ..paths import project_root as _project_root
from ._app import app


def _parse_iso3_scope(value: str) -> tuple[str, ...]:
    """Parse a comma-separated ``--countries`` value into a tuple.

    Strips whitespace, uppercases, drops empties, dedups while
    preserving order. Raises :class:`typer.BadParameter` when the
    value is empty after parsing.
    """
    parts = [chunk.strip().upper() for chunk in value.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise typer.BadParameter(
            "--countries must be a non-empty comma-separated list of ISO3 codes"
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        deduped.append(part)
    return tuple(deduped)


def _default_output_path() -> Path:
    """Resolve the default CSV output path under the project root.

    Uses ``leaders_db.paths.project_root`` so the default lands at
    ``<project_root>/data/outputs/country-year-chronicle/<basename>``
    regardless of the caller's working directory.
    """
    return (
        _project_root()
        / "data"
        / "outputs"
        / CHRONICLE_OUTPUT_DIR_NAME
        / DEFAULT_OUTPUT_BASENAME
    )


@app.command("run-country-year-chronicle")
def run_country_year_chronicle_cmd(
    start_year: int = typer.Option(
        DEFAULT_START_YEAR,
        "--start-year",
        help="First year (inclusive) for the chronicle window.",
    ),
    end_year: int = typer.Option(
        DEFAULT_END_YEAR,
        "--end-year",
        help="Last year (inclusive) for the chronicle window.",
    ),
    countries: str = typer.Option(
        ",".join(DEFAULT_COUNTRIES),
        "--countries",
        help=(
            "Comma-separated ISO3 scope. "
            f"Default: {','.join(DEFAULT_COUNTRIES)}."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Destination CSV path. "
            "The parent directory is created if missing. "
            "Default: <project_root>/data/outputs/country-year-chronicle/"
            f"{DEFAULT_OUTPUT_BASENAME}."
        ),
    ),
    allow_regime_proxy: bool = typer.Option(
        True,
        "--allow-regime-proxy/--no-allow-regime-proxy",
        help=(
            "When set, rows for years beyond V-Dem coverage (2026 today) "
            "use V-Dem 2025 as a one-year proxy and carry the "
            "``proxy_year_used`` flag. When --no-allow-regime-proxy is "
            "passed, those rows emit ``Unknown`` + ``regime_source_gap``."
        ),
    ),
) -> None:
    """Run the Country-Year Chronicle pilot CSV.

    The command emits one CSV row per requested ``(iso3, year)`` pair
    regardless of whether every field could be populated. Missing
    fields are empty and the row carries the appropriate
    ``data_quality_flags``. See
    ``docs/country-year-chronicle-increment-0.md`` for the full
    contract.
    """
    iso3_scope = _parse_iso3_scope(countries)

    if start_year > end_year:
        raise typer.BadParameter(
            f"--start-year ({start_year}) must be <= --end-year ({end_year})"
        )

    # Resolve the default output path lazily so that
    # ``LEADERSDB_PROJECT_ROOT`` overrides (e.g. the test fixture) are
    # honored at invocation time, not at module-import time.
    output_path = output if output is not None else _default_output_path()

    typer.echo(
        f"[country_year_chronicle] year_window={start_year}-{end_year} "
        f"countries={','.join(iso3_scope)} "
        f"allow_regime_proxy={allow_regime_proxy} "
        f"output={output_path}"
    )

    result: ChronicleResult = run_country_year_chronicle(
        output_path=output_path,
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        allow_regime_proxy=allow_regime_proxy,
    )

    typer.echo("Done. Summary:")
    typer.echo(f"  rows_written:        {result.rows_written}")
    typer.echo(f"  iso3_scope:          {', '.join(result.iso3_scope)}")
    typer.echo(f"  start_year:          {result.start_year}")
    typer.echo(f"  end_year:            {result.end_year}")
    typer.echo(f"  sources_used:        {', '.join(result.sources_used) or '(none)'}")
    typer.echo(f"  output_path:         {result.output_path}")
    typer.echo(
        "Caveat: this is an experimental vertical slice — "
        "not the final scoring or the authoritative record."
    )


__all__ = ["run_country_year_chronicle_cmd"]
