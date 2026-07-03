"""Scope infrastructure commands for country/year grid building."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..config import RunConfig, default_config_path
from ..db.readiness import DatabaseReadinessError
from ._app import app
from ._helpers import _safe_load_config

scope_app = typer.Typer(help="Build and inspect country/year scope tables.", no_args_is_help=True)
app.add_typer(scope_app, name="scope")


@scope_app.command("build-country-years")
def scope_build_country_years_cmd(
    start_year: int | None = typer.Option(
        None,
        "--start-year",
        help="First year in the country-year grid. Defaults to config scope.start_year.",
    ),
    end_year: int | None = typer.Option(
        None,
        "--end-year",
        help="Last year in the country-year grid. Defaults to config scope.end_year.",
    ),
    config: Path = typer.Option(
        default_config_path(),
        "--config",
        "-c",
        help="Run config YAML for default scope years and database URL.",
        exists=False,
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Populate ``countries`` and ``country_years`` deterministically."""

    from ..db.engine import build_engine
    from ..scope.country_year_grid import build_country_year_grid

    cfg = _safe_load_config(config)
    resolved_start_year = start_year if start_year is not None else cfg.scope.start_year
    resolved_end_year = end_year if end_year is not None else cfg.scope.end_year
    resolved_db_url = db_url or _config_or_default_db_url(cfg)

    try:
        result = build_country_year_grid(
            build_engine(resolved_db_url),
            start_year=resolved_start_year,
            end_year=resolved_end_year,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(f"range: {result.start_year}-{result.end_year}")
    typer.echo(f"countries_total: {result.countries_total}")
    typer.echo(f"countries_created: {result.countries_created}")
    typer.echo(f"countries_updated: {result.countries_updated}")
    typer.echo(f"country_years_total: {result.country_years_total}")
    typer.echo(f"country_years_created: {result.country_years_created}")
    typer.echo(f"country_years_updated: {result.country_years_updated}")


@scope_app.command("country-year-coverage")
def scope_country_year_coverage_cmd(
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Report aggregate coverage for country/year scope rows."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..scope.country_year_grid import (
        build_country_year_coverage_report,
        coverage_report_to_json,
    )

    try:
        report = build_country_year_coverage_report(
            build_engine(db_url or default_sqlite_url())
        )
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        if output_json:
            typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc

    payload = coverage_report_to_json(report)
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"total_countries: {payload['total_countries']}")
    typer.echo(f"total_country_years: {payload['total_country_years']}")
    typer.echo(f"min_year: {payload['min_year'] or '-'}")
    typer.echo(f"max_year: {payload['max_year'] or '-'}")
    typer.echo(f"included_country_years: {payload['included_country_years']}")
    typer.echo(f"excluded_country_years: {payload['excluded_country_years']}")
    typer.echo(
        "country_years_without_inclusion_reason: "
        f"{payload['country_years_without_inclusion_reason']}"
    )
    typer.echo("limitations:")
    for limitation in payload["limitations"]:
        typer.echo(f"  - {limitation}")


__all__ = ["scope_app", "scope_build_country_years_cmd", "scope_country_year_coverage_cmd"]


def _config_or_default_db_url(cfg: RunConfig) -> str:
    from ..db.session import default_sqlite_url

    if cfg.database.url == RunConfig().database.url:
        return default_sqlite_url()
    return cfg.database.url


def _is_database_readiness_error(exc: Exception) -> bool:
    """Return true for readiness errors across import/reload boundaries."""

    return (
        isinstance(exc, DatabaseReadinessError)
        or exc.__class__.__name__ == "DatabaseReadinessError"
    )
