"""Generic adjudicated country-year facts.

This module is the reusable persistence contract for values that populate the
country-year data tables. Domain-specific builders, such as ruler identity,
produce one fact per ``country_year_id`` and ``field_key`` with the same audit
envelope: candidate values, selected value, source links, quality signals,
confidence, review state, and a research prompt when automation cannot safely
resolve the value.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.db.models import CountryYearFact

COUNTRY_YEAR_FACTS_TABLE = "country_year_facts"


@dataclass(frozen=True)
class CountryYearFactBuildResult:
    """Summary from a generic country-year fact upsert batch."""

    rows_created: int
    rows_updated: int
    total_rows: int
    adjudication_status_counts: dict[str, int]
    field_counts: dict[str, int]


def upsert_country_year_fact(
    session: Session,
    payload: dict[str, Any],
    *,
    updated_at: datetime | None = None,
) -> str:
    """Create or update one generic fact.

    Returns ``"created"``, ``"updated"``, or ``"unchanged"``. The caller owns the
    transaction so a domain builder can keep its specific and generic tables in
    sync in one commit.
    """

    timestamp = updated_at or datetime.now(UTC)
    existing = session.scalar(
        select(CountryYearFact).where(
            CountryYearFact.country_year_id == payload["country_year_id"],
            CountryYearFact.field_key == payload["field_key"],
        )
    )
    if existing is None:
        session.add(CountryYearFact(**payload, created_at=timestamp, updated_at=timestamp))
        return "created"
    changed = False
    for key, value in payload.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    if not changed:
        return "unchanged"
    existing.updated_at = timestamp
    return "updated"


def country_year_fact_counts(
    engine: Engine,
    *,
    field_key: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict[str, Any]:
    """Return generic fact counts for one field or all fields."""

    with Session(engine) as session:
        statement = select(CountryYearFact)
        if field_key is not None:
            statement = statement.where(CountryYearFact.field_key == field_key)
        if start_year is not None:
            statement = statement.where(CountryYearFact.year >= start_year)
        if end_year is not None:
            statement = statement.where(CountryYearFact.year <= end_year)
        rows = session.scalars(statement).all()
    return {
        "total_rows": len(rows),
        "adjudication_status_counts": dict(
            sorted(Counter(row.adjudication_status for row in rows).items())
        ),
        "field_counts": dict(sorted(Counter(row.field_key for row in rows).items())),
    }


__all__ = [
    "COUNTRY_YEAR_FACTS_TABLE",
    "CountryYearFactBuildResult",
    "country_year_fact_counts",
    "upsert_country_year_fact",
]
