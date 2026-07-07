"""Country-year fact answer and answer-list research CLI commands."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

import typer
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from .research_common import fail


def register_answer_commands(research_app: typer.Typer) -> None:
    research_app.command("build-country-year-fact-answers")(
        research_build_country_year_fact_answers_cmd
    )
    research_app.command("list-answers")(research_list_answers_cmd)


def research_build_country_year_fact_answers_cmd(
    question_id: str = typer.Option(..., "--question-id"),
    year: int = typer.Option(..., "--year", help="Answer year."),
    iso3: list[str] | None = typer.Option(None, "--iso3"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build and persist fact-backed country-year answers for one question/year."""

    from ..db.engine import build_engine
    from ..db.readiness import DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.country_year_fact_answers import (
        COUNTRY_YEAR_FACTS_METHOD_VERSION,
        build_country_year_fact_answers,
        persist_country_year_fact_answers,
    )

    try:
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(
            engine,
            required_tables=(
                "countries",
                "country_years",
                "country_year_facts",
                "research_questions",
                "research_question_answers",
                "research_answer_evidence_links",
            ),
        )
        country_scope = _country_scope_from_db(engine, year=year, iso3_filter=iso3)
        rows = build_country_year_fact_answers(
            bind=engine,
            question_id=question_id,
            year=year,
            country_scope=country_scope,
            method_version=COUNTRY_YEAR_FACTS_METHOD_VERSION,
        )
        persist_country_year_fact_answers(
            engine,
            rows,
            method_version=COUNTRY_YEAR_FACTS_METHOD_VERSION,
        )
    except (DatabaseReadinessError, SQLAlchemyError, ValueError) as exc:
        fail(str(exc), output_json=output_json)

    payload = {
        "question_id": question_id,
        "year": year,
        "answers_built": len(rows),
        "answers_persisted": len(rows),
        "coverage_counts": _coverage_counts(rows),
        "method_version": COUNTRY_YEAR_FACTS_METHOD_VERSION,
    }
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"answers_persisted: {len(rows)}")


def research_list_answers_cmd(
    question_id: str | None = typer.Option(None, "--question-id"),
    year: int | None = typer.Option(None, "--year"),
    iso3: str | None = typer.Option(None, "--iso3"),
    method_version: str | None = typer.Option(None, "--method-version"),
    output: str = typer.Option("json", "--output", "-o"),
    db_url: str | None = typer.Option(None, "--db-url"),
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
        fail(str(exc), output_json=output == "json")

    if output == "json":
        typer.echo(json.dumps(rows, indent=2, sort_keys=True))
        return
    typer.echo(_answers_to_csv(rows), nl=False)


def _country_scope_from_db(
    engine: Any,
    *,
    year: int,
    iso3_filter: list[str] | None,
) -> dict[str, dict[str, Any]]:
    countries = tuple(country.upper() for country in iso3_filter or ())
    statement = text(
        """
        SELECT c.iso3, c.country_name, cy.year
        FROM country_years cy
        JOIN countries c ON c.id = cy.country_id
        WHERE cy.year = :year
          AND cy.included_in_project = :included_in_project
          AND (:country_all = 1 OR c.iso3 IN :countries)
        ORDER BY c.iso3
        """
    ).bindparams(bindparam("countries", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(
            statement,
            {
                "year": year,
                "included_in_project": True,
                "country_all": int(not countries),
                "countries": countries,
            },
        ).mappings().all()
    return {
        str(row["iso3"]): {
            "country_name": row["country_name"],
            "start_year": year,
            "end_year": year,
        }
        for row in rows
    }


def _coverage_counts(rows: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.coverage_status] = counts.get(row.coverage_status, 0) + 1
    return counts


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
    with engine.connect() as conn:
        answer_rows = conn.execute(_answers_statement(where), params).mappings().all()
        link_rows = conn.execute(_links_statement()).mappings().all()
    links_by_answer_id: dict[int, list[dict[str, str]]] = {}
    for row in link_rows:
        links_by_answer_id.setdefault(int(row["answer_id"]), []).append(
            {
                "source_slug": row["source_slug"],
                "source_observation_id": row["source_observation_id"],
                "evidence_role": row["evidence_role"],
            }
        )
    return [
        _answer_payload(row, links_by_answer_id.get(int(row["id"]), []))
        for row in answer_rows
    ]


def _answers_statement(where: str) -> Any:
    return text(
        f"""
        SELECT a.id, a.question_id, q.question_text, q.category_key, a.year, a.iso3,
            a.country_name, a.ruler_id, a.ruler_name, a.answer_boolean,
            a.answer_numeric, a.answer_text, a.answer_json, a.score_1_to_10,
            a.confidence_score, a.coverage_status, a.evidence_year, a.method_version,
            a.warning_codes_json, a.caveats_json, COUNT(l.id) AS evidence_link_count
        FROM research_question_answers a
        JOIN research_questions q ON q.question_id = a.question_id
        LEFT JOIN research_answer_evidence_links l ON l.answer_id = a.id
        {where}
        GROUP BY a.id
        ORDER BY a.question_id, a.year, a.iso3, a.ruler_name
        """
    )


def _links_statement() -> Any:
    return text(
        """
        SELECT answer_id, source_slug, source_observation_id, evidence_role
        FROM research_answer_evidence_links
        ORDER BY answer_id, source_slug, source_observation_id, evidence_role
        """
    )


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


__all__ = [
    "register_answer_commands",
    "research_build_country_year_fact_answers_cmd",
    "research_list_answers_cmd",
]
