"""Database readiness checks for CLI commands that read persisted tables."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

EVIDENCE_TABLES: tuple[str, ...] = ("normalized_observations",)
RESEARCH_RESULT_TABLES: tuple[str, ...] = (
    "research_questions",
    "research_question_answers",
    "research_answer_evidence_links",
    "chapter_scores",
)
LOCAL_EVIDENCE_DB_NOT_READY = (
    "The local evidence database is not initialized. Run `leaders-db init-db` "
    "or pass `--db-url`."
)


class DatabaseReadinessError(RuntimeError):
    """Raised when a CLI read command points at an uninitialized database."""


def assert_database_ready(
    engine: Engine,
    *,
    required_tables: Sequence[str] = EVIDENCE_TABLES,
) -> None:
    """Ensure ``engine`` can see the persisted tables required by a read command."""

    try:
        existing_tables = set(inspect(engine).get_table_names())
    except SQLAlchemyError as exc:
        raise DatabaseReadinessError(LOCAL_EVIDENCE_DB_NOT_READY) from exc

    missing = tuple(table for table in required_tables if table not in existing_tables)
    if missing:
        missing_list = ", ".join(missing)
        raise DatabaseReadinessError(
            f"{LOCAL_EVIDENCE_DB_NOT_READY} Missing table(s): {missing_list}."
        )


__all__ = [
    "EVIDENCE_TABLES",
    "LOCAL_EVIDENCE_DB_NOT_READY",
    "RESEARCH_RESULT_TABLES",
    "DatabaseReadinessError",
    "assert_database_ready",
]
