"""Local structured evidence helper CLI commands."""

from __future__ import annotations

import json

import typer
from sqlalchemy.exc import SQLAlchemyError

from leaders_db.db.readiness import DatabaseReadinessError
from leaders_db.research.local_evidence_summary import (
    RulerPeriodEvidenceRequest,
    parse_concept_options,
    summarize_ruler_period_evidence,
)
from leaders_db.sources.query import EvidenceRepository

from ._app import app

evidence_app = typer.Typer(help="Summarize local structured evidence.", no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")


@evidence_app.command("summarize-ruler-period")
def evidence_summarize_ruler_period_cmd(
    country: str = typer.Option(..., "--country", help="Country code or name to query."),
    leader: str | None = typer.Option(
        None,
        "--leader",
        help="Leader text to carry in request metadata; no leader matching is attempted.",
    ),
    start_year: int = typer.Option(..., "--start-year", help="First year in window."),
    end_year: int = typer.Option(..., "--end-year", help="Last year in window."),
    concepts: list[str] | None = typer.Option(
        None,
        "--concept",
        help="Concept key to include. Repeat or pass comma-separated values.",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL for persisted normalized observations.",
    ),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json."),
) -> None:
    """Summarize local concept evidence for a ruler-period window."""

    if output != "json":
        raise typer.BadParameter("--output must be 'json'")
    try:
        request = RulerPeriodEvidenceRequest(
            country=country.strip(),
            leader=leader,
            start_year=start_year,
            end_year=end_year,
            concepts=parse_concept_options(concepts),
        )
        repository = _build_evidence_repository(db_url)
        payload = summarize_ruler_period_evidence(repository, request)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except DatabaseReadinessError as exc:
        typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from exc
    except SQLAlchemyError as exc:
        typer.echo(
            json.dumps(
                {
                    "error": "could not query normalized observations",
                    "detail": str(exc),
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc

    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _build_evidence_repository(db_url: str | None) -> EvidenceRepository:
    """Build the persisted clean-source query repository for CLI use."""

    from ..db.engine import build_engine
    from ..db.readiness import EVIDENCE_TABLES, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.sql_repository import SqlEvidenceRepository

    engine = build_engine(db_url or default_sqlite_url())
    assert_database_ready(engine, required_tables=EVIDENCE_TABLES)
    return SqlEvidenceRepository(engine)


__all__ = ["evidence_app", "evidence_summarize_ruler_period_cmd"]
