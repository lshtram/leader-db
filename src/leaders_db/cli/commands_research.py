"""Research answer persistence CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ._app import app

research_app = typer.Typer(
    help="Persist and inspect research-question answers.",
    no_args_is_help=True,
)
app.add_typer(research_app, name="research")


@research_app.command("persist-8b-evaluations")
def research_persist_8b_evaluations_cmd(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="JSON file containing an array of 8B evaluations or {'evaluations': [...]}",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Persist already-cited 8B effectiveness evaluations from JSON."""

    from ..db.engine import build_engine
    from ..db.readiness import (
        RESEARCH_RESULT_TABLES,
        DatabaseReadinessError,
        assert_database_ready,
    )
    from ..db.session import default_sqlite_url
    from ..research.effectiveness_8b import (
        Effectiveness8BEvaluation,
        persist_effectiveness_8b_evaluations,
    )

    try:
        evaluations = _load_8b_evaluations(input_path, Effectiveness8BEvaluation)
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(engine, required_tables=RESEARCH_RESULT_TABLES)
        persist_effectiveness_8b_evaluations(engine, evaluations)
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON in {input_path}: {exc}", output_json=output_json)
    except (OSError, ValidationError, ValueError) as exc:
        _fail(str(exc), output_json=output_json)
    except (DatabaseReadinessError, SQLAlchemyError) as exc:
        _fail(str(exc), output_json=output_json)

    payload = {"evaluations_persisted": len(evaluations)}
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"evaluations_persisted: {len(evaluations)}")


def _load_8b_evaluations(input_path: Path, model: Any) -> tuple[Any, ...]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "evaluations" in raw:
        raw = raw["evaluations"]
    if not isinstance(raw, list):
        raise ValueError("input JSON must be an array or an object with an 'evaluations' array")
    return tuple(model.model_validate(item) for item in raw)


def _fail(message: str, *, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps({"error": message}, sort_keys=True))
    else:
        typer.echo(f"error: {message}")
    raise typer.Exit(1)


__all__ = ["research_app", "research_persist_8b_evaluations_cmd"]
