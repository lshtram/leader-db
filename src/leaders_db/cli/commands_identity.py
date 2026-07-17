"""Ruler identity infrastructure commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.engine import Engine

from ..db.readiness import DatabaseReadinessError
from ..identity import coverage as identity_coverage
from ._app import app

identity_app = typer.Typer(
    help="Build and inspect ruler identity tables.",
    no_args_is_help=True,
)
app.add_typer(identity_app, name="identity")


@identity_app.command("lock-canonical")
def identity_lock_canonical_cmd(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    db_url: str | None = typer.Option(None, "--db-url"),
) -> None:
    """Persist reviewed formal ruler-year identities as immutable canonical choices."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.canonical_locks import (
        apply_canonical_identity_locks,
        load_canonical_identity_manifest,
    )

    result = apply_canonical_identity_locks(
        build_engine(db_url or default_sqlite_url()),
        load_canonical_identity_manifest(manifest),
    )
    typer.echo(f"locked: {result.locked}")
    typer.echo(f"ruler_years_created: {result.ruler_years_created}")
    for iso3, ruler_name, ruler_year_id in result.identities:
        typer.echo(f"{iso3}\t{ruler_year_id}\t{ruler_name}")


@identity_app.command("challenge-canonical")
def identity_challenge_canonical_cmd(
    iso3: str = typer.Option(..., "--iso3"),
    year: int = typer.Option(..., "--year"),
    reason: str = typer.Option(..., "--reason"),
    db_url: str | None = typer.Option(None, "--db-url"),
) -> None:
    """Explicitly reopen one canonical lock for exceptional correction."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.canonical_locks import challenge_canonical_identity_lock

    challenge_canonical_identity_lock(
        build_engine(db_url or default_sqlite_url()), iso3=iso3, year=year, reason=reason
    )
    typer.echo(f"challenged: {iso3}/{year}")


@identity_app.command("build-ruler-years")
def identity_build_ruler_years_cmd(
    start_year: int | None = typer.Option(
        None,
        "--start-year",
        help="First observation year to consume. Defaults to all persisted identity observations.",
    ),
    end_year: int | None = typer.Option(
        None,
        "--end-year",
        help="Last observation year to consume. Defaults to all persisted identity observations.",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Populate leaders, ruler_spells, and ruler_years from persisted observations."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.ruler_identity import build_ruler_identity

    if start_year is not None and end_year is not None and start_year > end_year:
        raise typer.BadParameter("start_year must be less than or equal to end_year")

    try:
        result = build_ruler_identity(
            build_engine(db_url or default_sqlite_url()),
            start_year=start_year,
            end_year=end_year,
        )
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(f"observations_read: {result.observations_read}")
    typer.echo(f"observations_used: {result.observations_used}")
    typer.echo(f"observations_skipped: {result.observations_skipped}")
    typer.echo(f"leaders_created: {result.leaders_created}")
    typer.echo(f"aliases_created: {result.aliases_created}")
    typer.echo(f"ruler_spells_created: {result.ruler_spells_created}")
    typer.echo(f"ruler_spells_updated: {result.ruler_spells_updated}")
    typer.echo(f"ruler_years_created: {result.ruler_years_created}")
    typer.echo(f"ruler_years_updated: {result.ruler_years_updated}")


@identity_app.command("ruler-coverage")
def identity_ruler_coverage_cmd(
    year: int | None = typer.Option(
        None,
        "--year",
        help="Limit coverage to one year. Defaults to all populated country-years.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    detail: bool = typer.Option(
        False,
        "--detail",
        help="Include per-country-year classifications in JSON output.",
    ),
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output format: text, json, csv, or markdown.",
        ),
    ] = "text",
    start_year: int | None = typer.Option(
        None,
        "--start-year",
        help="First country-year to report. Ignored when --year is set.",
    ),
    end_year: int | None = typer.Option(
        None,
        "--end-year",
        help="Last country-year to report. Ignored when --year is set.",
    ),
    write_artifact: bool = typer.Option(
        False,
        "--write-artifact",
        help="Write JSON, CSV, and Markdown gap-report artifacts under data/outputs/.",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Report ruler identity coverage for the country/year grid."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.ruler_identity import (
        build_ruler_identity_coverage_report,
        ruler_identity_coverage_to_json,
    )

    if output_json:
        output = "json"
    if output not in {"text", "json", "csv", "markdown"}:
        raise typer.BadParameter("output must be one of: text, json, csv, markdown")
    if year is None and start_year is not None and end_year is not None and start_year > end_year:
        raise typer.BadParameter("start_year must be less than or equal to end_year")

    try:
        engine = build_engine(db_url or default_sqlite_url())
        if _uses_gap_report(output, detail, write_artifact, start_year, end_year):
            _run_gap_report_output(
                engine,
                year=year,
                start_year=start_year,
                end_year=end_year,
                output=output,
                detail=detail,
                write_artifact=write_artifact,
            )
            return

        report = build_ruler_identity_coverage_report(engine, year=year)
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        if output == "json":
            typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc

    payload = ruler_identity_coverage_to_json(report)
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    for key, value in payload.items():
        if key == "limitations":
            typer.echo("limitations:")
            for limitation in value:
                typer.echo(f"  - {limitation}")
            continue
        typer.echo(f"{key}: {value}")


@identity_app.command("build-adjudications")
def identity_build_adjudications_cmd(
    start_year: int | None = typer.Option(
        None,
        "--start-year",
        help="First country-year to persist. Defaults to all included country-years.",
    ),
    end_year: int | None = typer.Option(
        None,
        "--end-year",
        help="Last country-year to persist. Defaults to all included country-years.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Optional run identifier stored on adjudication rows.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Persist principal-ruler adjudications and unresolved review prompts."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.adjudications import build_ruler_identity_adjudications

    if start_year is not None and end_year is not None and start_year > end_year:
        raise typer.BadParameter("start_year must be less than or equal to end_year")
    try:
        result = build_ruler_identity_adjudications(
            build_engine(db_url or default_sqlite_url()),
            start_year=start_year,
            end_year=end_year,
            run_id=run_id,
        )
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        if output_json:
            typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc
    payload = {
        "rows_created": result.rows_created,
        "rows_updated": result.rows_updated,
        "total_rows": result.total_rows,
        "review_status_counts": result.review_status_counts,
        "classification_counts": result.classification_counts,
        "fact_rows_created": result.fact_rows_created,
        "fact_rows_updated": result.fact_rows_updated,
    }
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        if isinstance(value, dict):
            typer.echo(f"{key}:")
            for item_key, item_value in value.items():
                typer.echo(f"  {item_key}: {item_value}")
            continue
        typer.echo(f"{key}: {value}")


@identity_app.command("adjudication-coverage")
def identity_adjudication_coverage_cmd(
    start_year: int | None = typer.Option(None, "--start-year", help="First persisted year."),
    end_year: int | None = typer.Option(None, "--end-year", help="Last persisted year."),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Report counts from persisted ruler identity adjudications."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..identity.adjudications import adjudication_counts

    if start_year is not None and end_year is not None and start_year > end_year:
        raise typer.BadParameter("start_year must be less than or equal to end_year")
    try:
        payload = adjudication_counts(
            build_engine(db_url or default_sqlite_url()),
            start_year=start_year,
            end_year=end_year,
        )
    except Exception as exc:
        if not _is_database_readiness_error(exc):
            raise
        if output_json:
            typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"total_rows: {payload['total_rows']}")
    typer.echo("review_status_counts:")
    for key, value in payload["review_status_counts"].items():
        typer.echo(f"  {key}: {value}")
    typer.echo("classification_counts:")
    for key, value in payload["classification_counts"].items():
        typer.echo(f"  {key}: {value}")


def _uses_gap_report(
    output: str,
    detail: bool,
    write_artifact: bool,
    start_year: int | None,
    end_year: int | None,
) -> bool:
    return (
        detail
        or output in {"csv", "markdown"}
        or write_artifact
        or start_year is not None
        or end_year is not None
    )


def _run_gap_report_output(
    engine: Engine,
    *,
    year: int | None,
    start_year: int | None,
    end_year: int | None,
    output: str,
    detail: bool,
    write_artifact: bool,
) -> None:
    detailed_report = identity_coverage.build_identity_coverage_gap_report(
        engine,
        year=year,
        start_year=start_year,
        end_year=end_year,
    )
    if write_artifact:
        paths = identity_coverage.write_identity_gap_report_artifacts(detailed_report)
        for format_name, path in paths.items():
            typer.echo(f"{format_name}_artifact: {path}")
    if output == "json":
        typer.echo(
            json.dumps(
                identity_coverage.identity_gap_report_to_json(detailed_report, detail=detail),
                indent=2,
                sort_keys=True,
            )
        )
    elif output == "markdown":
        typer.echo(identity_coverage.identity_gap_report_to_markdown(detailed_report).rstrip())
    elif output == "csv":
        _echo_gap_report_csv(detailed_report)
    else:
        _echo_gap_report_text(detailed_report)


__all__ = [
    "identity_adjudication_coverage_cmd",
    "identity_app",
    "identity_build_adjudications_cmd",
    "identity_build_ruler_years_cmd",
    "identity_ruler_coverage_cmd",
]


def _is_database_readiness_error(exc: Exception) -> bool:
    """Return true for readiness errors across import/reload boundaries."""

    return (
        isinstance(exc, DatabaseReadinessError)
        or exc.__class__.__name__ == "DatabaseReadinessError"
    )


def _echo_gap_report_text(report: object) -> None:
    payload = report.summary  # type: ignore[attr-defined]
    typer.echo(f"total_country_years: {payload.total_country_years}")
    typer.echo(f"included_country_years: {payload.included_country_years}")
    typer.echo(f"excluded_country_years: {payload.excluded_country_years}")
    typer.echo("classification_counts:")
    for key, value in payload.classification_counts.items():
        typer.echo(f"  {key}: {value}")
    typer.echo("source_diagnostics:")
    for diagnostic in report.source_diagnostics:  # type: ignore[attr-defined]
        typer.echo(
            f"  {diagnostic.source_slug}: rows={diagnostic.loaded_row_count}, "
            f"years={diagnostic.min_year}-{diagnostic.max_year}, "
            f"countries={diagnostic.country_count}, skipped={diagnostic.skipped_observation_count}"
        )


def _echo_gap_report_csv(report: object) -> None:
    import csv
    import sys

    from ..identity.coverage import identity_gap_report_to_json

    rows = identity_gap_report_to_json(report, detail=True).get("rows", [])
    if not rows:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
