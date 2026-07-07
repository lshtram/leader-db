"""Cited evaluation research CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .research_common import fail, load_evaluations


def register_cited_commands(research_app: typer.Typer) -> None:
    research_app.command("persist-8b-evaluations")(research_persist_8b_evaluations_cmd)
    research_app.command("persist-cited-evaluations")(research_persist_cited_evaluations_cmd)
    research_app.command("cited-evaluation-schema")(research_cited_evaluation_schema_cmd)
    research_app.command("cited-evaluation-template")(research_cited_evaluation_template_cmd)


def research_persist_8b_evaluations_cmd(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Persist already-cited 8B effectiveness evaluations from JSON."""

    from ..db.engine import build_engine
    from ..db.readiness import RESEARCH_RESULT_TABLES, DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.effectiveness_8b import (
        Effectiveness8BEvaluation,
        persist_effectiveness_8b_evaluations,
    )

    try:
        evaluations = load_evaluations(input_path, Effectiveness8BEvaluation)
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(engine, required_tables=RESEARCH_RESULT_TABLES)
        persist_effectiveness_8b_evaluations(engine, evaluations)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {input_path}: {exc}", output_json=output_json)
    except (OSError, ValidationError, ValueError) as exc:
        fail(str(exc), output_json=output_json)
    except (DatabaseReadinessError, SQLAlchemyError) as exc:
        fail(str(exc), output_json=output_json)

    _echo_persisted(len(evaluations), output_json=output_json)


def research_persist_cited_evaluations_cmd(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Persist already-cited manual/internet evaluations from JSON."""

    from ..db.engine import build_engine
    from ..db.readiness import RESEARCH_RESULT_TABLES, DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.cited_evaluations import CitedEvaluation, persist_cited_evaluations

    try:
        evaluations = load_evaluations(input_path, CitedEvaluation)
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(engine, required_tables=RESEARCH_RESULT_TABLES)
        persist_cited_evaluations(engine, evaluations)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {input_path}: {exc}", output_json=output_json)
    except (OSError, ValidationError, ValueError) as exc:
        fail(str(exc), output_json=output_json)
    except (DatabaseReadinessError, SQLAlchemyError) as exc:
        fail(str(exc), output_json=output_json)

    _echo_persisted(len(evaluations), output_json=output_json)


def research_cited_evaluation_schema_cmd() -> None:
    """Print the JSON Schema for cited/manual research outputs."""

    from ..research.cited_evaluations import cited_evaluation_json_schema

    typer.echo(json.dumps(cited_evaluation_json_schema(), indent=2, sort_keys=True))


def research_cited_evaluation_template_cmd(
    methodology_id: str = typer.Option(..., "--methodology-id"),
    year: int = typer.Option(..., "--year"),
    iso3: str = typer.Option(..., "--iso3"),
    country_name: str = typer.Option(..., "--country-name"),
    leader_name: str | None = typer.Option(None, "--leader-name"),
    period_label: str | None = typer.Option(None, "--period-label"),
) -> None:
    """Print a starter JSON record for cited/manual research outputs."""

    from ..research.cited_evaluations import build_cited_evaluation_template

    try:
        template = build_cited_evaluation_template(
            methodology_id=methodology_id,
            year=year,
            iso3=iso3,
            country_name=country_name,
            leader_name=leader_name,
            period_label=period_label,
        )
    except ValueError as exc:
        fail(str(exc), output_json=True)
    typer.echo(json.dumps(template, indent=2, sort_keys=True))


def _echo_persisted(count: int, *, output_json: bool) -> None:
    payload = {"evaluations_persisted": count}
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"evaluations_persisted: {count}")


__all__ = [
    "register_cited_commands",
    "research_cited_evaluation_schema_cmd",
    "research_cited_evaluation_template_cmd",
    "research_persist_8b_evaluations_cmd",
    "research_persist_cited_evaluations_cmd",
]
