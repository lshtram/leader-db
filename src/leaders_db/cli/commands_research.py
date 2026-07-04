"""Research answer persistence CLI commands."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from sqlalchemy import text
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


@research_app.command("list-answers")
def research_list_answers_cmd(
    question_id: str | None = typer.Option(None, "--question-id", help="Filter by question ID."),
    year: int | None = typer.Option(None, "--year", help="Filter by answer year."),
    iso3: str | None = typer.Option(None, "--iso3", help="Filter by ISO3 country code."),
    method_version: str | None = typer.Option(
        None,
        "--method-version",
        help="Filter by method version.",
    ),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or csv."),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy database URL. Defaults to the initialized local SQLite DB.",
    ),
) -> None:
    """List persisted research answers with optional filters."""

    from ..db.engine import build_engine
    from ..db.readiness import (
        RESEARCH_RESULT_TABLES,
        DatabaseReadinessError,
        assert_database_ready,
    )
    from ..db.session import default_sqlite_url

    if output not in {"json", "csv"}:
        raise typer.BadParameter("--output must be 'json' or 'csv'")
    try:
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(engine, required_tables=RESEARCH_RESULT_TABLES)
        rows = _query_research_answers(
            engine,
            question_id=question_id,
            year=year,
            iso3=iso3,
            method_version=method_version,
        )
    except (DatabaseReadinessError, SQLAlchemyError) as exc:
        _fail(str(exc), output_json=output == "json")

    if output == "json":
        typer.echo(json.dumps(rows, indent=2, sort_keys=True))
        return
    typer.echo(_answers_to_csv(rows), nl=False)


def _load_8b_evaluations(input_path: Path, model: Any) -> tuple[Any, ...]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "evaluations" in raw:
        raw = raw["evaluations"]
    if not isinstance(raw, list):
        raise ValueError("input JSON must be an array or an object with an 'evaluations' array")
    return tuple(model.model_validate(item) for item in raw)


def _query_research_answers(
    engine: Any,
    *,
    question_id: str | None,
    year: int | None,
    iso3: str | None,
    method_version: str | None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if question_id is not None:
        clauses.append("a.question_id = :question_id")
        params["question_id"] = question_id
    if year is not None:
        clauses.append("a.year = :year")
        params["year"] = year
    if iso3 is not None:
        clauses.append("a.iso3 = :iso3")
        params["iso3"] = iso3.upper()
    if method_version is not None:
        clauses.append("a.method_version = :method_version")
        params["method_version"] = method_version
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    statement = text(
        f"""
        SELECT
            a.id,
            a.question_id,
            q.question_text,
            q.category_key,
            a.year,
            a.iso3,
            a.country_name,
            a.ruler_id,
            a.ruler_name,
            a.answer_boolean,
            a.answer_numeric,
            a.answer_text,
            a.answer_json,
            a.score_1_to_10,
            a.confidence_score,
            a.coverage_status,
            a.evidence_year,
            a.method_version,
            a.warning_codes_json,
            a.caveats_json,
            COUNT(l.id) AS evidence_link_count
        FROM research_question_answers a
        JOIN research_questions q ON q.question_id = a.question_id
        LEFT JOIN research_answer_evidence_links l ON l.answer_id = a.id
        {where}
        GROUP BY a.id
        ORDER BY a.question_id, a.year, a.iso3, a.ruler_name
        """
    )
    with engine.connect() as conn:
        answer_rows = conn.execute(statement, params).mappings().all()
        link_rows = (
            conn.execute(
                text(
                    """
                SELECT answer_id, source_slug, source_observation_id, evidence_role
                FROM research_answer_evidence_links
                ORDER BY answer_id, source_slug, source_observation_id, evidence_role
                """
                )
            )
            .mappings()
            .all()
        )
    links_by_answer_id: dict[int, list[dict[str, str]]] = {}
    for row in link_rows:
        links_by_answer_id.setdefault(int(row["answer_id"]), []).append(
            {
                "source_slug": row["source_slug"],
                "source_observation_id": row["source_observation_id"],
                "evidence_role": row["evidence_role"],
            }
        )
    return [_answer_payload(row, links_by_answer_id.get(int(row["id"]), [])) for row in answer_rows]


def _answer_payload(row: Any, evidence_links: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "question_id": row["question_id"],
        "question_text": row["question_text"],
        "category_key": row["category_key"],
        "year": row["year"],
        "iso3": row["iso3"],
        "country_name": row["country_name"],
        "ruler_id": row["ruler_id"],
        "ruler_name": row["ruler_name"],
        "answer_boolean": row["answer_boolean"],
        "answer_numeric": row["answer_numeric"],
        "answer_text": row["answer_text"],
        "answer_json": json.loads(row["answer_json"] or "{}"),
        "score_1_to_10": row["score_1_to_10"],
        "confidence_score": row["confidence_score"],
        "coverage_status": row["coverage_status"],
        "evidence_year": row["evidence_year"],
        "method_version": row["method_version"],
        "warning_codes": json.loads(row["warning_codes_json"] or "[]"),
        "caveats": json.loads(row["caveats_json"] or "[]"),
        "evidence_link_count": row["evidence_link_count"],
        "evidence_links": evidence_links,
    }


def _answers_to_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "question_id",
        "year",
        "iso3",
        "country_name",
        "ruler_name",
        "answer_boolean",
        "answer_numeric",
        "answer_text",
        "score_1_to_10",
        "confidence_score",
        "coverage_status",
        "evidence_year",
        "method_version",
        "evidence_link_count",
    ]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _fail(message: str, *, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps({"error": message}, sort_keys=True))
    else:
        typer.echo(f"error: {message}")
    raise typer.Exit(1)


__all__ = [
    "research_app",
    "research_list_answers_cmd",
    "research_persist_8b_evaluations_cmd",
]
