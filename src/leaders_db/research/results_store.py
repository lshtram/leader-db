"""Persistence helpers for dashboard-ready research question answers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.research.question_2_1 import QUESTION_ID, Question21AnswerRow

Q2_1_METHOD_VERSION = "q2_1_state_based_conflict_v1"
Q2_1_QUESTION_TEXT = "Was the country involved in state-based armed conflict?"


@dataclass(frozen=True)
class ResearchQuestionMetadata:
    """Question metadata persisted into ``research_questions``."""

    question_id: str
    chapter_id: str
    question_text: str
    answer_type: str
    category_key: str
    method_version: str


@dataclass(frozen=True)
class ResearchAnswerEvidence:
    """One provenance link for a persisted research answer."""

    source_slug: str
    source_observation_id: str
    evidence_role: str = "primary"


@dataclass(frozen=True)
class ResearchAnswerRow:
    """Generic D24-D27 row for existing research answer tables."""

    question_id: str
    year: int
    iso3: str
    country_name: str
    method_version: str
    coverage_status: str
    ruler_id: str | None = None
    ruler_name: str | None = None
    answer_boolean: bool | None = None
    answer_numeric: float | None = None
    answer_text: str | None = None
    answer_json: dict[str, Any] = field(default_factory=dict)
    score_1_to_10: float | None = None
    confidence_score: float | None = None
    evidence_year: int | None = None
    warning_codes: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    evidence_links: tuple[ResearchAnswerEvidence, ...] = ()


def persist_research_answers(
    bind: Engine | Session,
    question: ResearchQuestionMetadata,
    rows: Sequence[ResearchAnswerRow],
) -> None:
    """Upsert generic research answers and refresh evidence links.

    This is the D24-D27 persistence contract for now. It deliberately reuses the
    existing generic research tables instead of introducing grain-specific answer
    tables before answer shapes stabilize.
    """

    if isinstance(bind, Session):
        context = nullcontext(bind)
    else:
        context = bind.begin()

    with context as conn:
        _upsert_question(conn, question)
        for row in rows:
            if row.question_id != question.question_id:
                raise ValueError("answer row question_id must match question metadata")
            if row.method_version != question.method_version:
                raise ValueError("answer row method_version must match question metadata")
            _upsert_generic_answer(conn, row)


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

    question = ResearchQuestionMetadata(
        question_id=QUESTION_ID,
        chapter_id="2",
        question_text=Q2_1_QUESTION_TEXT,
        answer_type="boolean",
        category_key="peace",
        method_version=method_version,
    )
    persist_research_answers(
        bind,
        question,
        tuple(_q2_1_to_generic_answer(row, method_version=method_version) for row in rows),
    )


def _upsert_question(conn: Any, question: ResearchQuestionMetadata) -> None:
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
            "question_id": question.question_id,
            "chapter_id": question.chapter_id,
            "question_text": question.question_text,
            "answer_type": question.answer_type,
            "category_key": question.category_key,
            "method_version": question.method_version,
        },
    )


def _upsert_generic_answer(conn: Any, row: ResearchAnswerRow) -> None:
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
        _generic_answer_params(row),
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
            "method_version": row.method_version,
        },
    ).scalar_one()
    conn.execute(
        text("DELETE FROM research_answer_evidence_links WHERE answer_id = :answer_id"),
        {"answer_id": answer_id},
    )
    links = _generic_evidence_link_params(answer_id, row)
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


def _generic_answer_params(row: ResearchAnswerRow) -> dict[str, Any]:
    return {
        "question_id": row.question_id,
        "year": row.year,
        "iso3": row.iso3,
        "country_name": row.country_name,
        "ruler_id": row.ruler_id,
        "ruler_name": row.ruler_name,
        "answer_boolean": _bool_to_db(row.answer_boolean),
        "answer_numeric": row.answer_numeric,
        "answer_text": row.answer_text,
        "answer_json": _dumps(row.answer_json),
        "score_1_to_10": row.score_1_to_10,
        "confidence_score": row.confidence_score,
        "coverage_status": row.coverage_status,
        "evidence_year": row.evidence_year,
        "method_version": row.method_version,
        "warning_codes_json": _dumps(row.warning_codes),
        "caveats_json": _dumps(row.caveats),
    }


def _generic_evidence_link_params(
    answer_id: int,
    row: ResearchAnswerRow,
) -> list[dict[str, Any]]:
    return [
        {
            "answer_id": answer_id,
            "source_slug": link.source_slug,
            "source_observation_id": link.source_observation_id,
            "evidence_role": link.evidence_role,
        }
        for link in _unique_evidence_links(row.evidence_links)
    ]


def _q2_1_to_generic_answer(
    row: Question21AnswerRow,
    *,
    method_version: str,
) -> ResearchAnswerRow:
    evidence_role = "proxy" if row.coverage_status == "proxy" else "primary"
    return ResearchAnswerRow(
        question_id=row.question_id,
        year=row.year,
        iso3=row.iso3,
        country_name=row.country_name,
        ruler_name=row.ruler_name,
        answer_boolean=row.answer,
        answer_json={
            "state_based_events": row.state_based_events,
            "state_based_fatalities": row.state_based_fatalities,
            "ruler_source": row.ruler_source,
        },
        coverage_status=row.coverage_status,
        evidence_year=row.evidence_year,
        method_version=method_version,
        warning_codes=row.warning_codes,
        caveats=row.caveats,
        evidence_links=tuple(
            ResearchAnswerEvidence(
                source_slug="ucdp",
                source_observation_id=observation_id,
                evidence_role=evidence_role,
            )
            for observation_id in dict.fromkeys(row.source_observation_ids)
        ),
    )


def _unique_evidence_links(
    links: Sequence[ResearchAnswerEvidence],
) -> tuple[ResearchAnswerEvidence, ...]:
    return tuple(dict.fromkeys(links))


def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "Q2_1_METHOD_VERSION",
    "ResearchAnswerEvidence",
    "ResearchAnswerRow",
    "ResearchQuestionMetadata",
    "persist_q2_1_answers",
    "persist_research_answers",
]
