"""Generic country-year fact publishing commands."""

from __future__ import annotations

import json

import typer
from sqlalchemy.exc import SQLAlchemyError

from leaders_db.sources.concepts import KNOWN_CONCEPT_KEYS

from ._app import app

facts_app = typer.Typer(
    help="Publish harmonized source concepts into country-year facts.",
    no_args_is_help=True,
)
app.add_typer(facts_app, name="facts")


@facts_app.command("publish-concepts")
def facts_publish_concepts_cmd(
    concepts: list[str] | None = typer.Option(
        None,
        "--concept",
        help="Concept key to publish. Repeat or pass comma-separated values.",
    ),
    sources: list[str] | None = typer.Option(
        None,
        "--source",
        help="Optional source slug filter. Repeat or pass comma-separated values.",
    ),
    source_precedence: list[str] | None = typer.Option(
        None,
        "--source-precedence",
        help="Preferred source order. Repeat or pass comma-separated values.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Optional run identifier stored on generated fact rows.",
    ),
    start_year: int | None = typer.Option(
        None,
        "--start-year",
        help="First observation/country-year to publish. Requires --end-year.",
    ),
    end_year: int | None = typer.Option(
        None,
        "--end-year",
        help="Last observation/country-year to publish. Requires --start-year.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """Publish supported concept observations into ``country_year_facts``."""

    from ..db.engine import build_engine
    from ..db.readiness import (
        EVIDENCE_TABLES,
        DatabaseReadinessError,
        assert_database_ready,
    )
    from ..db.session import default_sqlite_url
    from ..facts import publish_concept_country_year_facts
    from ..research.sql_repository import SqlEvidenceRepository
    from ..sources.contracts import SourceId

    concept_keys = _parse_csv_options(concepts) or list(KNOWN_CONCEPT_KEYS)
    source_slugs = _parse_csv_options(sources)
    precedence = _parse_csv_options(source_precedence)
    if (start_year is None) != (end_year is None):
        raise typer.BadParameter("--start-year and --end-year must be provided together")
    if start_year is not None and end_year is not None and start_year > end_year:
        raise typer.BadParameter("start_year must be less than or equal to end_year")
    try:
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(
            engine,
            required_tables=(
                *EVIDENCE_TABLES,
                "countries",
                "country_years",
                "country_year_facts",
            ),
        )
        kwargs = {"source_precedence": tuple(precedence)} if precedence else {}
        result = publish_concept_country_year_facts(
            engine,
            SqlEvidenceRepository(engine),
            concept_keys=tuple(concept_keys),
            source_ids=tuple(SourceId(slug=slug) for slug in source_slugs) or None,
            start_year=start_year,
            end_year=end_year,
            run_id=run_id,
            **kwargs,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except (DatabaseReadinessError, SQLAlchemyError) as exc:
        if output_json:
            typer.echo(json.dumps({"error": str(exc)}, sort_keys=True))
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc

    payload = {
        "rows_created": result.rows_created,
        "rows_updated": result.rows_updated,
        "total_rows": result.total_rows,
        "skipped_without_country_year": result.skipped_without_country_year,
        "adjudication_status_counts": result.adjudication_status_counts,
        "field_counts": result.field_counts,
        "warning_codes": [warning.code for warning in result.warnings],
    }
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def _parse_csv_options(values: list[str] | None) -> list[str]:
    parsed: list[str] = []
    for value in values or []:
        parsed.extend(item.strip() for item in value.split(",") if item.strip())
    return parsed


__all__ = ["facts_app", "facts_publish_concepts_cmd"]
