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
:file:`docs/sources/attributions.md` §3.2.

SQLite artifact. Pass ``--sqlite-output <PATH>`` to write a SQLite
database to a custom path. When the flag is omitted, the command writes
the SQLite artifact to the default path
``<project_root>/data/outputs/country-year-chronicle/pilot.sqlite``.
The CSV behavior is unchanged when ``--sqlite-output`` is not passed.

All-country scope (Increment 5). Pass ``--countries all`` to derive the
country list from V-Dem coverage (~200 ISO3 codes) instead of the
seven-country pilot list. The runner derives the all-country scope
from the local V-Dem raw CSV, filters to valid 3-letter uppercase ISO3
codes, overlays the pilot historical identities (SUN, etc.), and
emits one row per ``(iso3, year)`` pair across the requested window.

Condensed CSV (Increment 5). The command writes a companion
``condensed.csv`` artifact by default
(``<project_root>/data/outputs/country-year-chronicle/condensed.csv``).
The condensed export drops every source / provenance / confidence /
text column so a reader can scan the file by eye. Use
``--condensed-output <PATH>`` to write the condensed CSV to a custom
path, or ``--no-condensed-output`` to disable it.
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

#: Default basename for the Increment 5 condensed CSV. Resolved
#: under ``<project_root>/data/outputs/country-year-chronicle/``.
CONDENSED_DEFAULT_BASENAME: str = "condensed.csv"

#: Sentinel used to detect ``--no-condensed-output`` via Typer's
#: boolean-optional flag pair. We do not expose a sentinel string;
#: the runner treats ``None`` as "use the default" and a non-``None``
#: ``Path`` as "write to this path".
_NO_CONDENSED_OUTPUT_FLAG: str = "--no-condensed-output"


def _parse_iso3_scope(value: str) -> tuple[str, ...]:
    """Parse a comma-separated ``--countries`` value into a tuple.

    Strips whitespace, uppercases, drops empties, dedups while
    preserving order. Raises :class:`typer.BadParameter` when the
    value is empty after parsing. The sentinel ``all`` is
    forwarded verbatim; the caller (the CLI command body) decides
    how to expand it.
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


def _default_condensed_output_path() -> Path:
    """Return the canonical condensed CSV artifact default path.

    Resolves to
    ``<project_root>/data/outputs/country-year-chronicle/condensed.csv``
    regardless of the caller's working directory.
    """
    return (
        _project_root()
        / "data"
        / "outputs"
        / CHRONICLE_OUTPUT_DIR_NAME
        / CONDENSED_DEFAULT_BASENAME
    )


def _default_sqlite_output_path() -> Path:
    """Return the canonical SQLite artifact default path.

    Resolves to
    ``<project_root>/data/outputs/country-year-chronicle/pilot.sqlite``
    regardless of the caller's working directory.
    """
    from ..chronicle.sqlite_writer import default_sqlite_path
    return default_sqlite_path()


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
            "Use 'all' (or a comma list including 'all') to derive the "
            f"scope from V-Dem coverage (~200 ISO3 codes) instead of the "
            f"seven-country pilot list (default: {','.join(DEFAULT_COUNTRIES)})."
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
    sqlite_output: Path | None = typer.Option(
        None,
        "--sqlite-output",
        help=(
            "Optional SQLite artifact path. When set, the runner writes "
            "a SQLite database to the given path with the same row "
            "contents (plus a ``source_attributions`` sidecar table). "
            "If omitted, the default path "
            "``<project_root>/data/outputs/country-year-chronicle/pilot.sqlite``"
            " is used."
        ),
    ),
    condensed_output: Path | None = typer.Option(
        None,
        "--condensed-output",
        help=(
            "Optional condensed CSV artifact path (Increment 5). "
            "When set, the runner writes a condensed CSV with the "
            "Increment 5 column set (year, iso3, country, existence_status, "
            "ruler, political_regime, system_type, population, gdp, "
            "gdp_per_capita, military_spend, country_area_km2). "
            "If omitted, the default path "
            "``<project_root>/data/outputs/country-year-chronicle/condensed.csv``"
            " is used. Pass --no-condensed-output to disable the condensed "
            "write entirely."
        ),
    ),
    no_condensed_output: bool = typer.Option(
        False,
        "--no-condensed-output",
        help=(
            "Disable the condensed CSV artifact (Increment 5). "
            "When set, the runner skips the condensed write even when "
            "--condensed-output is omitted. The detailed CSV / SQLite "
            "behavior is unchanged."
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

    Omit ``--sqlite-output`` for the default SQLite path,
    ``<project_root>/data/outputs/country-year-chronicle/pilot.sqlite``.
    Passing ``--sqlite-output <PATH>`` writes SQLite to that path.
    The SQLite schema is a single ``country_year_chronicle``
    table with TEXT / INTEGER / REAL columns matching the CSV field
    names, plus a ``source_attributions`` sidecar table that mirrors
    the attribution block from the CSV comment lines.

    Pass ``--countries all`` to derive the scope from V-Dem
    coverage (~200 ISO3 codes). The runner merges the V-Dem
    country_text_id list with the pilot historical identities
    (SUN, etc.) and emits the full all-country condensed export
    alongside the detailed CSV.
    """
    iso3_scope_or_all = _parse_iso3_scope(countries)
    use_all_countries = "ALL" in iso3_scope_or_all

    if start_year > end_year:
        raise typer.BadParameter(
            f"--start-year ({start_year}) must be <= --end-year ({end_year})"
        )

    # Resolve the default output paths lazily so that
    # ``LEADERSDB_PROJECT_ROOT`` overrides (e.g. the test fixture) are
    # honored at invocation time, not at module-import time.
    output_path = output if output is not None else _default_output_path()
    sqlite_path = (
        sqlite_output
        if sqlite_output is not None
        else _default_sqlite_output_path()
    )
    if no_condensed_output:
        condensed_path: Path | None = None
    elif condensed_output is not None:
        condensed_path = condensed_output
    else:
        condensed_path = _default_condensed_output_path()

    country_scope = None
    iso3_scope = iso3_scope_or_all
    if use_all_countries:
        from ..chronicle.country_scope import (
            default_vdem_csv_path,
            derive_all_country_scope,
        )

        country_scope = derive_all_country_scope(
            vdem_csv_path=default_vdem_csv_path(),
        )
        iso3_scope = tuple(country_scope.keys())
    elif condensed_path is not None:
        # Even for the pilot scope we derive a country_scope so the
        # condensed writer can compute ``existence_status`` for each
        # row. We use ``derive_country_scope`` with the canonical
        # V-Dem CSV as the seed; the pilot countries always have a
        # V-Dem row, so the pilot scope is a subset of the all-country
        # scope and the per-row existence_status values match.
        from ..chronicle.country_scope import (
            default_vdem_csv_path,
            derive_country_scope,
        )

        country_scope = derive_country_scope(
            vdem_csv_path=default_vdem_csv_path(),
        )

    typer.echo(
        f"[country_year_chronicle] year_window={start_year}-{end_year} "
        f"countries={'all' if use_all_countries else ','.join(iso3_scope)} "
        f"scope_size={len(iso3_scope)} "
        f"allow_regime_proxy={allow_regime_proxy} "
        f"output={output_path} "
        f"sqlite_output={sqlite_path} "
        f"condensed_output={condensed_path}"
    )

    result: ChronicleResult = run_country_year_chronicle(
        output_path=output_path,
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        sqlite_output_path=sqlite_path,
        allow_regime_proxy=allow_regime_proxy,
        country_scope=country_scope,
        condensed_output_path=condensed_path,
    )

    typer.echo("Done. Summary:")
    typer.echo(f"  rows_written:        {result.rows_written}")
    typer.echo(f"  iso3_scope:          {', '.join(result.iso3_scope)}")
    typer.echo(f"  start_year:          {result.start_year}")
    typer.echo(f"  end_year:            {result.end_year}")
    typer.echo(f"  sources_used:        {', '.join(result.sources_used) or '(none)'}")
    typer.echo(f"  output_path:         {result.output_path}")
    typer.echo(f"  sqlite_output_path:  {result.sqlite_output_path}")
    if result.condensed_output_path is not None:
        typer.echo(
            f"  condensed_output_path:  {result.condensed_output_path} "
            f"({result.condensed_rows_written} rows)"
        )
    else:
        typer.echo(
            "  condensed_output_path:  (skipped)"
        )
    typer.echo(
        "Caveat: this is an experimental vertical slice — "
        "not the final scoring or the authoritative record."
    )


__all__ = ["run_country_year_chronicle_cmd"]
