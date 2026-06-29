"""Persistence helpers for dashboard-ready research question answers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import nullcontext
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.research.question_2_1 import QUESTION_ID, Question21AnswerRow

Q2_1_METHOD_VERSION = "q2_1_state_based_conflict_v1"
Q2_1_QUESTION_TEXT = "Was the country involved in state-based armed conflict?"


def persist_q2_1_answers(
    bind: Engine | Session,
    rows: Sequence[Question21AnswerRow],
    *,
    method_version: str = Q2_1_METHOD_VERSION,
) -> None:
    """Upsert Q2.1 answer rows and refresh their evidence links.

    This function persists already-built Q2.1 rows only. It does not read raw
    source files, call adapters, or execute network lookups.
    """

    if isinstance(bind, Session):
        context = nullcontext(bind)
    else:
        context = bind.begin()

    with context as conn:
        conn.execute(
            text(
                """
                INSERT INTO research_questions (
                    question_id, chapter_id, question_text, answer_type,
                    category_key, method_version, is_active, updated_at
                ) VALUES (
                    :question_id, :chapter_id, :question_text, :answer_type,
                    :category_key, :method_version, 1, CURRENT_TIMESTAMP
                )
                ON CONFLICT(question_id) DO UPDATE SET
                    chapter_id = excluded.chapter_id,
                    question_text = excluded.question_text,
                    answer_type = excluded.answer_type,
                    category_key = excluded.category_key,
                    method_version = excluded.method_version,
                    is_active = excluded.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "question_id": QUESTION_ID,
                "chapter_id": "2",
                "question_text": Q2_1_QUESTION_TEXT,
                "answer_type": "boolean",
                "category_key": "peace",
                "method_version": method_version,
            },
        )
        for row in rows:
            _upsert_answer(conn, row, method_version=method_version)


def _upsert_answer(conn: Any, row: Question21AnswerRow, *, method_version: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO research_question_answers (
                question_id, year, iso3, country_name, ruler_id, ruler_name,
                answer_boolean, answer_numeric, answer_text, answer_json,
                score_1_to_10, confidence_score, coverage_status, evidence_year,
                method_version, warning_codes_json, caveats_json, updated_at
            ) VALUES (
                :question_id, :year, :iso3, :country_name, :ruler_id, :ruler_name,
                :answer_boolean, :answer_numeric, :answer_text, :answer_json,
                :score_1_to_10, :confidence_score, :coverage_status, :evidence_year,
                :method_version, :warning_codes_json, :caveats_json, CURRENT_TIMESTAMP
            )
            ON CONFLICT(question_id, year, iso3, method_version) DO UPDATE SET
                country_name = excluded.country_name,
                ruler_id = excluded.ruler_id,
                ruler_name = excluded.ruler_name,
                answer_boolean = excluded.answer_boolean,
                answer_numeric = excluded.answer_numeric,
                answer_text = excluded.answer_text,
                answer_json = excluded.answer_json,
                score_1_to_10 = excluded.score_1_to_10,
                confidence_score = excluded.confidence_score,
                coverage_status = excluded.coverage_status,
                evidence_year = excluded.evidence_year,
                warning_codes_json = excluded.warning_codes_json,
                caveats_json = excluded.caveats_json,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        _answer_params(row, method_version=method_version),
    )
    answer_id = conn.execute(
        text(
            """
            SELECT id
            FROM research_question_answers
            WHERE question_id = :question_id
              AND year = :year
              AND iso3 = :iso3
              AND method_version = :method_version
            """
        ),
        {
            "question_id": row.question_id,
            "year": row.year,
            "iso3": row.iso3,
            "method_version": method_version,
        },
    ).scalar_one()
    conn.execute(
        text("DELETE FROM research_answer_evidence_links WHERE answer_id = :answer_id"),
        {"answer_id": answer_id},
    )
    links = _evidence_link_params(answer_id, row)
    if links:
        conn.execute(
            text(
                """
                INSERT INTO research_answer_evidence_links (
                    answer_id, source_slug, source_observation_id, evidence_role
                ) VALUES (
                    :answer_id, :source_slug, :source_observation_id, :evidence_role
                )
                ON CONFLICT(
                    answer_id, source_slug, source_observation_id, evidence_role
                ) DO NOTHING
                """
            ),
            links,
        )


def _answer_params(row: Question21AnswerRow, *, method_version: str) -> dict[str, Any]:
    return {
        "question_id": row.question_id,
        "year": row.year,
        "iso3": row.iso3,
        "country_name": row.country_name,
        "ruler_id": None,
        "ruler_name": row.ruler_name,
        "answer_boolean": _bool_to_db(row.answer),
        "answer_numeric": None,
        "answer_text": None,
        "answer_json": _dumps(
            {
                "state_based_events": row.state_based_events,
                "state_based_fatalities": row.state_based_fatalities,
                "ruler_source": row.ruler_source,
            }
        ),
        "score_1_to_10": None,
        "confidence_score": None,
        "coverage_status": row.coverage_status,
        "evidence_year": row.evidence_year,
        "method_version": method_version,
        "warning_codes_json": _dumps(row.warning_codes),
        "caveats_json": _dumps(row.caveats),
    }


def _evidence_link_params(answer_id: int, row: Question21AnswerRow) -> list[dict[str, Any]]:
    evidence_role = "proxy" if row.coverage_status == "proxy" else "primary"
    return [
        {
            "answer_id": answer_id,
            "source_slug": "ucdp",
            "source_observation_id": observation_id,
            "evidence_role": evidence_role,
        }
        for observation_id in dict.fromkeys(row.source_observation_ids)
    ]


def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = ["Q2_1_METHOD_VERSION", "persist_q2_1_answers"]
