"""Durable ruler identity adjudication records.

This layer persists the v1 in-memory/``ruler_years`` adjudication outcome into a
queryable country-year table. It records both the selected principal ruler when
deterministic rules resolve the case and a future research/manual prompt when no
safe automated selection exists.
"""

from __future__ import annotations

import calendar
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from leaders_db.db.models import (
    Country,
    CountryYear,
    RulerIdentityAdjudication,
    RulerSpell,
    RulerYear,
)
from leaders_db.db.readiness import DatabaseReadinessError, assert_database_ready
from leaders_db.facts.country_year_facts import COUNTRY_YEAR_FACTS_TABLE, upsert_country_year_fact
from leaders_db.identity.coverage import build_identity_coverage_gap_report
from leaders_db.identity.ruler_identity import IDENTITY_TABLES, NON_EVIDENCE_SOURCE_DATASETS

ADJUDICATION_TABLE = "ruler_identity_adjudications"
ADJUDICATION_METHOD_VERSION = "ruler_identity_adjudication_v1"
PRINCIPAL_RULER_FIELD_KEY = "principal_ruler"
YEAR_COVERAGE_MAJORITY_CLASSIFICATION = "resolved_auto_year_coverage_majority"
YEAR_COVERAGE_MAJORITY_RULE = "year_coverage_majority"
RESEARCH_ADJUDICATED_CLASSIFICATION = "resolved_research_adjudicated"
RESEARCH_ADJUDICATION_RULE = "internet_research_adjudication"
RESEARCH_ADJUDICATION_SOURCE = "internet_research_adjudication"
AUTO_RESOLVED_CLASSIFICATIONS = {
    "resolved_auto_single_candidate",
    "resolved_auto_role_priority",
    "resolved_auto_duration_majority",
    YEAR_COVERAGE_MAJORITY_CLASSIFICATION,
    RESEARCH_ADJUDICATED_CLASSIFICATION,
}
NEEDS_REVIEW_CLASSIFICATIONS = {
    "multiple_candidates_manual_review",
    "source_conflict_manual_review",
    "disputed_rule",
    "low_confidence",
}
SOURCE_OBSERVATION_RE = re.compile(r"normalized_observations:(\d+)")
MIN_RELIABLE_YEAR_COVERAGE_RATIO = 0.50
MIN_CLEAR_COVERAGE_MARGIN_DAYS = 90
HARD_REVIEW_TOKENS = ("coup", "contested", "de facto", "disputed", "junta", "shared")
RESEARCH_DE_FACTO_RULE_TYPES = {
    "de facto ruler",
    "de facto principal ruler",
    "de facto ruler adjudication",
    "de facto principal ruler adjudication",
}


@dataclass(frozen=True)
class RulerIdentityAdjudicationBuildResult:
    """Summary from an idempotent adjudication-table build."""

    rows_created: int
    rows_updated: int
    total_rows: int
    review_status_counts: dict[str, int]
    classification_counts: dict[str, int]
    fact_rows_created: int
    fact_rows_updated: int


@dataclass(frozen=True)
class YearCoverageDecision:
    """Second-pass deterministic year-coverage adjudication decision."""

    selected: RulerYear
    classification: str
    selection_rule: str
    rationale: str
    next_action: str
    temporal_fit_score: float


@dataclass(frozen=True)
class ResearchAdjudicationDecision:
    """Conservative decision from cited internet-research adjudication evidence."""

    selected: RulerYear
    classification: str
    selection_rule: str
    rationale: str
    next_action: str
    temporal_fit_score: float


def build_ruler_identity_adjudications(
    engine: Engine,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    run_id: str | None = None,
) -> RulerIdentityAdjudicationBuildResult:
    """Build or update durable adjudication rows for a year/range."""

    if start_year is not None and end_year is not None and start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    assert_adjudication_database_ready(engine)
    report = build_identity_coverage_gap_report(
        engine,
        start_year=start_year,
        end_year=end_year,
        include_out_of_scope=False,
    )
    with Session(engine, expire_on_commit=False) as session:
        rows_by_pair = _ruler_rows_by_pair(session, start_year=start_year, end_year=end_year)
        created = 0
        updated = 0
        fact_created = 0
        fact_updated = 0
        now = datetime.now(UTC)
        for detail in report.rows:
            country_year = _country_year(session, detail.iso3, detail.year)
            if country_year is None:
                continue
            ruler_rows = rows_by_pair.get((country_year.country_id, country_year.year), [])
            payload = _adjudication_payload(country_year, detail, ruler_rows, run_id=run_id)
            existing = session.scalar(
                select(RulerIdentityAdjudication).where(
                    RulerIdentityAdjudication.country_year_id == country_year.id
                )
            )
            if existing is None:
                session.add(
                    RulerIdentityAdjudication(
                        **_adjudication_model_payload(payload),
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
            elif _apply_payload(existing, _adjudication_model_payload(payload), now):
                updated += 1
            fact_result = upsert_country_year_fact(
                session,
                _principal_ruler_fact_payload(payload),
                updated_at=now,
            )
            if fact_result == "created":
                fact_created += 1
            elif fact_result == "updated":
                fact_updated += 1
        session.commit()
        status_counts, classification_counts, total = _counts(
            session, start_year=start_year, end_year=end_year
        )
    return RulerIdentityAdjudicationBuildResult(
        rows_created=created,
        rows_updated=updated,
        total_rows=total,
        review_status_counts=status_counts,
        classification_counts=classification_counts,
        fact_rows_created=fact_created,
        fact_rows_updated=fact_updated,
    )


def adjudication_counts(
    engine: Engine,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict[str, Any]:
    """Return persisted adjudication counts for a year/range."""

    assert_adjudication_database_ready(engine)
    with Session(engine) as session:
        status_counts, classification_counts, total = _counts(
            session, start_year=start_year, end_year=end_year
        )
    return {
        "total_rows": total,
        "review_status_counts": status_counts,
        "classification_counts": classification_counts,
    }


def assert_adjudication_database_ready(engine: Engine) -> None:
    """Ensure identity and adjudication tables are present."""

    message = (
        "The local ruler identity adjudication database is not initialized. Run "
        "`leaders-db init-db`, `leaders-db scope build-country-years`, and "
        "`leaders-db identity build-ruler-years`, or pass `--db-url`."
    )
    try:
        inspect(engine).get_table_names()
    except SQLAlchemyError as exc:
        raise DatabaseReadinessError(message) from exc
    try:
        assert_database_ready(
            engine,
            required_tables=(*IDENTITY_TABLES, ADJUDICATION_TABLE, COUNTRY_YEAR_FACTS_TABLE),
        )
    except DatabaseReadinessError as exc:
        raise DatabaseReadinessError(message) from exc


def _adjudication_payload(
    country_year: CountryYear,
    detail: Any,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    *,
    run_id: str | None,
) -> dict[str, Any]:
    selected = _selected_ruler_year(ruler_rows)
    sorted_rows = _sorted_ruler_rows(ruler_rows)
    candidates = [_candidate_payload(row, spell) for row, spell in sorted_rows]
    research_decision = _research_adjudication_decision(
        detail.classification,
        sorted_rows,
        country_year.year,
    )
    year_coverage_decision = (
        None
        if research_decision is not None
        else _second_pass_year_coverage_decision(
            detail.classification,
            sorted_rows,
            country_year.year,
        )
    )
    decision = research_decision or year_coverage_decision
    if selected is None and decision is not None:
        selected = decision.selected
    selected_leader_name = selected.system_selected_leader_name if selected is not None else None
    candidate_ids = [row.id for row, _ in sorted_rows]
    source_slugs = sorted({item[1].source_dataset for item in ruler_rows})
    source_observation_ids = sorted(
        {
            value
            for _, spell in ruler_rows
            for value in SOURCE_OBSERVATION_RE.findall(spell.notes or "")
        }
    )
    confidence_penalties = _confidence_penalties(ruler_rows)
    classification = (
        decision.classification
        if decision is not None
        else detail.classification
    )
    rationale = (
        decision.rationale
        if decision is not None
        else detail.reason
    )
    next_action = (
        decision.next_action
        if decision is not None
        else detail.next_action
    )
    warnings = _warnings(classification, ruler_rows)
    review_status = _review_status(classification)
    review_reason = None if review_status == "auto_resolved" else rationale
    return {
        "country_year_id": country_year.id,
        "country_id": country_year.country_id,
        "year": country_year.year,
        "selected_ruler_year_id": selected.id if selected is not None else None,
        "selected_leader_name": selected_leader_name,
        "candidate_ruler_year_ids_json": _dumps(candidate_ids),
        "candidates_json": _dumps(candidates),
        "classification": classification,
        "selection_rule": _selection_rule(classification, selected),
        "review_status": review_status,
        "confidence_score": _confidence_score(selected, detail, ruler_rows),
        "confidence_penalties_json": _dumps(confidence_penalties),
        "warnings_json": _dumps(warnings),
        "rationale": rationale,
        "review_reason": review_reason,
        "research_prompt": _research_prompt(country_year, detail, candidates, review_status),
        "recommended_next_action": next_action,
        "source_slugs_json": _dumps(source_slugs),
        "source_observation_ids_json": _dumps(source_observation_ids),
        "run_id": run_id,
        "method_version": ADJUDICATION_METHOD_VERSION,
        "temporal_fit_score": (
            decision.temporal_fit_score
            if decision is not None
            else _selected_temporal_fit_score(selected, candidates)
        ),
    }


def _principal_ruler_fact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map ruler-specific adjudication into the generic country-year fact contract."""

    quality_signals = {
        "classification": payload["classification"],
        "confidence_penalties": json.loads(payload["confidence_penalties_json"]),
        "candidate_ruler_year_ids": json.loads(payload["candidate_ruler_year_ids_json"]),
        "temporal_fit_score": payload["temporal_fit_score"],
    }
    return {
        "country_year_id": payload["country_year_id"],
        "country_id": payload["country_id"],
        "year": payload["year"],
        "field_key": PRINCIPAL_RULER_FIELD_KEY,
        "field_label": "Principal/dominant ruler",
        "value_type": "entity_reference",
        "selected_value_text": payload["selected_leader_name"],
        "selected_value_number": None,
        "selected_value_json": None,
        "selected_entity_table": "ruler_years" if payload["selected_ruler_year_id"] else None,
        "selected_entity_id": payload["selected_ruler_year_id"],
        "candidate_values_json": payload["candidates_json"],
        "selection_rule": payload["selection_rule"],
        "adjudication_status": payload["review_status"],
        "confidence_score": payload["confidence_score"],
        "agreement_score": None,
        "authority_score": None,
        "specificity_score": None,
        "temporal_fit_score": payload["temporal_fit_score"],
        "quality_signals_json": _dumps(quality_signals),
        "warnings_json": payload["warnings_json"],
        "rationale": payload["rationale"],
        "review_reason": payload["review_reason"],
        "research_prompt": payload["research_prompt"],
        "recommended_next_action": payload["recommended_next_action"],
        "source_slugs_json": payload["source_slugs_json"],
        "source_observation_ids_json": payload["source_observation_ids_json"],
        "producer": "ruler_identity_adjudications",
        "method_version": payload["method_version"],
        "run_id": payload["run_id"],
    }


def _adjudication_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop generic-fact-only fields before writing the ruler-specific table."""

    return {key: value for key, value in payload.items() if key != "temporal_fit_score"}


def _selected_ruler_year(ruler_rows: list[tuple[RulerYear, RulerSpell]]) -> RulerYear | None:
    auto_rows = [row for row, _ in ruler_rows if row.review_status == "auto_resolved"]
    if len(auto_rows) == 1:
        return auto_rows[0]
    if len(ruler_rows) == 1 and ruler_rows[0][0].match_status in AUTO_RESOLVED_CLASSIFICATIONS:
        return ruler_rows[0][0]
    return None


def _candidate_payload(row: RulerYear, spell: RulerSpell) -> dict[str, Any]:
    coverage_days = _days_in_year(spell, row.year)
    days_in_year = _year_day_count(row.year)
    return {
        "ruler_year_id": row.id,
        "leader_id": row.leader_id,
        "leader_name": row.system_selected_leader_name,
        "match_status": row.match_status,
        "review_status": row.review_status,
        "confidence_score": row.confidence_score,
        "source_slug": spell.source_dataset,
        "source_observation_ids": SOURCE_OBSERVATION_RE.findall(spell.notes or ""),
        "source_notes": spell.notes,
        "office_title": spell.office_title,
        "start_date": spell.start_date.isoformat(),
        "end_date": spell.end_date.isoformat() if spell.end_date else None,
        "year_coverage_days": coverage_days,
        "year_coverage_ratio": round(coverage_days / days_in_year, 6),
        "is_actual_ruler": spell.is_actual_ruler,
        "is_formal_leader": spell.is_formal_leader,
        "rule_type": spell.rule_type,
        "shared_rule_flag": spell.shared_rule_flag,
        "disputed_rule_flag": spell.disputed_rule_flag,
    }


def _second_pass_year_coverage_decision(  # noqa: PLR0911
    classification: str,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    year: int,
) -> YearCoverageDecision | None:
    """Auto-resolve unresolved transition rows when year coverage is decisive."""

    if classification not in {"multiple_candidates_manual_review", "source_conflict_manual_review"}:
        return None
    if _has_hard_review_flag(ruler_rows):
        return None
    by_leader: dict[int, tuple[RulerYear, int]] = {}
    for row, spell in ruler_rows:
        days = _days_in_year(spell, year)
        existing = by_leader.get(row.leader_id)
        if existing is None or days > existing[1]:
            by_leader[row.leader_id] = (row, days)
    if len(by_leader) < 2:
        return None

    ordered = sorted(by_leader.values(), key=lambda item: item[1], reverse=True)
    selected, selected_days = ordered[0]
    runner_up_days = ordered[1][1]
    days_in_year = _year_day_count(year)
    selected_ratio = selected_days / days_in_year
    total_distinct_days = _distinct_covered_days(ruler_rows, year)
    if total_distinct_days / days_in_year <= MIN_RELIABLE_YEAR_COVERAGE_RATIO:
        return None
    if selected_days == runner_up_days:
        return None
    if not _has_decisive_coverage(selected_days, runner_up_days, days_in_year):
        return None
    if _equivalent_cross_source_coverage(ruler_rows, selected.leader_id, selected_days):
        return None

    leader_name = selected.system_selected_leader_name or f"leader_id={selected.leader_id}"
    rationale = (
        f"Second-pass year coverage selected {leader_name}: candidate covered "
        f"{selected_days}/{days_in_year} days ({selected_ratio:.1%}) in {year}, "
        f"ahead of the next candidate by {selected_days - runner_up_days} days."
    )
    return YearCoverageDecision(
        selected=selected,
        classification=YEAR_COVERAGE_MAJORITY_CLASSIFICATION,
        selection_rule=YEAR_COVERAGE_MAJORITY_RULE,
        rationale=rationale,
        next_action=(
            "No identity action required; second-pass year-coverage rule resolved transition."
        ),
        temporal_fit_score=round(selected_ratio, 6),
    )


def _research_adjudication_decision(
    classification: str,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    year: int,
) -> ResearchAdjudicationDecision | None:
    """Resolve conflicts only when exactly one strong cited research candidate exists."""

    if classification not in {"multiple_candidates_manual_review", "source_conflict_manual_review"}:
        return None
    strong_rows: list[tuple[RulerYear, RulerSpell, float]] = []
    for row, spell in ruler_rows:
        if spell.source_dataset != RESEARCH_ADJUDICATION_SOURCE:
            continue
        coverage_ratio = _days_in_year(spell, year) / _year_day_count(year)
        confidence = (
            spell.confidence_score if spell.confidence_score is not None else row.confidence_score
        )
        if (
            spell.is_actual_ruler
            and confidence is not None
            and confidence >= 80
            and coverage_ratio > MIN_RELIABLE_YEAR_COVERAGE_RATIO
            and not _candidate_has_hard_conflict(row, spell)
        ):
            strong_rows.append((row, spell, coverage_ratio))
    if len(strong_rows) != 1:
        return None

    selected, _spell, coverage_ratio = strong_rows[0]
    leader_name = selected.system_selected_leader_name or f"leader_id={selected.leader_id}"
    rationale = (
        f"Cited internet-research adjudication selected {leader_name}: exactly one "
        f"strong {RESEARCH_ADJUDICATION_SOURCE} candidate is marked actual ruler, has "
        f"confidence >=80, and covers {coverage_ratio:.1%} of {year}."
    )
    return ResearchAdjudicationDecision(
        selected=selected,
        classification=RESEARCH_ADJUDICATED_CLASSIFICATION,
        selection_rule=RESEARCH_ADJUDICATION_RULE,
        rationale=rationale,
        next_action=(
            "No identity action required; cited internet-research adjudication resolved the "
            "conflict."
        ),
        temporal_fit_score=round(coverage_ratio, 6),
    )


def _candidate_has_hard_conflict(row: RulerYear, spell: RulerSpell) -> bool:
    text = " ".join(
        str(value or "")
        for value in (spell.rule_type, spell.office_title, spell.notes, row.review_note)
    ).casefold()
    text = text.replace("-", " ").replace("_", " ")
    hard_tokens = HARD_REVIEW_TOKENS
    if _is_research_adjudicated_de_facto_candidate(spell, text):
        hard_tokens = tuple(token for token in hard_tokens if token != "de facto")
    return spell.disputed_rule_flag or spell.shared_rule_flag or any(
        token in text for token in hard_tokens
    )


def _is_research_adjudicated_de_facto_candidate(spell: RulerSpell, text: str) -> bool:
    if spell.source_dataset != RESEARCH_ADJUDICATION_SOURCE:
        return False
    rule_type = (spell.rule_type or "").casefold().replace("-", " ").replace("_", " ")
    if rule_type in RESEARCH_DE_FACTO_RULE_TYPES:
        return True
    return "de facto" in text and (
        "principal ruler" in text or "de facto ruler" in text or "de facto president" in text
    )


def _has_decisive_coverage(
    selected_days: int,
    runner_up_days: int,
    days_in_year: int,
) -> bool:
    return (
        selected_days / days_in_year > MIN_RELIABLE_YEAR_COVERAGE_RATIO
        and selected_days - runner_up_days >= 1
    )


def _has_hard_review_flag(ruler_rows: list[tuple[RulerYear, RulerSpell]]) -> bool:
    for row, spell in ruler_rows:
        text = " ".join(
            str(value or "")
            for value in (spell.rule_type, spell.office_title, spell.notes, row.review_note)
        ).casefold()
        text = text.replace("-", " ").replace("_", " ")
        if spell.disputed_rule_flag or spell.shared_rule_flag:
            return True
        if any(token in text for token in HARD_REVIEW_TOKENS):
            return True
    return False


def _equivalent_cross_source_coverage(
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    selected_leader_id: int,
    selected_days: int,
) -> bool:
    source_slugs = {spell.source_dataset for _, spell in ruler_rows}
    if len(source_slugs) <= 1:
        return False
    return any(
        row.leader_id != selected_leader_id
        and _days_in_year(spell, row.year) >= selected_days - MIN_CLEAR_COVERAGE_MARGIN_DAYS
        for row, spell in ruler_rows
    )


def _selected_temporal_fit_score(
    selected: RulerYear | None,
    candidates: list[dict[str, Any]],
) -> float | None:
    if selected is None:
        return None
    for candidate in candidates:
        if candidate["ruler_year_id"] == selected.id:
            return candidate["year_coverage_ratio"]
    return None


def _days_in_year(spell: RulerSpell, year: int) -> int:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    start = max(spell.start_date, year_start)
    end = min(spell.end_date or year_end, year_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _distinct_covered_days(ruler_rows: list[tuple[RulerYear, RulerSpell]], year: int) -> int:
    covered: set[date] = set()
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    for _, spell in ruler_rows:
        start = max(spell.start_date, year_start)
        end = min(spell.end_date or year_end, year_end)
        if end < start:
            continue
        for ordinal in range(start.toordinal(), end.toordinal() + 1):
            covered.add(date.fromordinal(ordinal))
    return len(covered)


def _year_day_count(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def _research_prompt(
    country_year: CountryYear,
    detail: Any,
    candidates: list[dict[str, Any]],
    review_status: str,
) -> str | None:
    if review_status == "auto_resolved":
        return None
    candidate_lines = [
        "- "
        f"ruler_year_id={item['ruler_year_id']}; leader={item['leader_name']}; "
        f"source={item['source_slug']}; office={item['office_title']}; "
        f"interval={item['start_date']} to {item['end_date'] or 'open'}; "
        f"actual={item['is_actual_ruler']}; formal={item['is_formal_leader']}"
        for item in candidates
    ] or ["- No ruler_year candidates are persisted for this country-year."]
    return "\n".join(
        [
            f"Question: Who was the principal/dominant ruler of "
            f"{country_year.country.country_name} ({country_year.country.iso3}) "
            f"in {country_year.year}?",
            f"Current classification: {detail.classification}.",
            f"Reason: {detail.reason}",
            "Candidate context:",
            *candidate_lines,
            f"Recommended next action: {detail.next_action}",
            "Use non-client evidence only; do not invent rulers. Record citations and rationale.",
        ]
    )


def _selection_rule(classification: str, selected: RulerYear | None) -> str:
    if selected is not None and classification == RESEARCH_ADJUDICATED_CLASSIFICATION:
        return RESEARCH_ADJUDICATION_RULE
    if selected is not None and classification == YEAR_COVERAGE_MAJORITY_CLASSIFICATION:
        return YEAR_COVERAGE_MAJORITY_RULE
    if selected is not None and classification in AUTO_RESOLVED_CLASSIFICATIONS:
        return classification.removeprefix("resolved_auto_")
    if classification in NEEDS_REVIEW_CLASSIFICATIONS:
        return "manual_or_research_required"
    return "unresolved_missing_evidence"


def _review_status(classification: str) -> str:
    if classification in AUTO_RESOLVED_CLASSIFICATIONS:
        return "auto_resolved"
    if classification in {"missing_no_identity_observation", "missing_current_source_cache"}:
        return "research_required"
    return "needs_review"


def _confidence_score(
    selected: RulerYear | None,
    detail: Any,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
) -> int | None:
    if selected is not None:
        return selected.confidence_score
    confidences = [
        row.confidence_score for row, _ in ruler_rows if row.confidence_score is not None
    ]
    if confidences:
        return min(confidences)
    return detail.confidence_min


def _confidence_penalties(ruler_rows: list[tuple[RulerYear, RulerSpell]]) -> list[str]:
    penalties: list[str] = []
    for row, _ in ruler_rows:
        if row.review_note and "confidence_penalty_applied" in row.review_note:
            penalties.append(f"ruler_year_id={row.id}:confidence_penalty_applied")
    return sorted(set(penalties))


def _warnings(classification: str, ruler_rows: list[tuple[RulerYear, RulerSpell]]) -> list[str]:
    warnings = []
    if classification not in AUTO_RESOLVED_CLASSIFICATIONS:
        warnings.append(classification)
    if any(spell.disputed_rule_flag for _, spell in ruler_rows):
        warnings.append("disputed_rule_flag")
    if any(spell.shared_rule_flag for _, spell in ruler_rows):
        warnings.append("shared_rule_flag")
    return sorted(set(warnings))


def _ruler_rows_by_pair(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
) -> dict[tuple[int, int], list[tuple[RulerYear, RulerSpell]]]:
    statement = _ruler_rows_statement()
    if start_year is not None:
        statement = statement.where(RulerYear.year >= start_year)
    if end_year is not None:
        statement = statement.where(RulerYear.year <= end_year)
    rows_by_pair: dict[tuple[int, int], list[tuple[RulerYear, RulerSpell]]] = {}
    for ruler_year, spell in session.execute(statement).all():
        rows_by_pair.setdefault((ruler_year.country_id, ruler_year.year), []).append(
            (ruler_year, spell)
        )
    return rows_by_pair


def _ruler_rows_statement() -> Select[tuple[RulerYear, RulerSpell]]:
    return (
        select(RulerYear, RulerSpell)
        .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
        .join(
            CountryYear,
            (CountryYear.country_id == RulerYear.country_id) & (CountryYear.year == RulerYear.year),
        )
        .where(
            CountryYear.included_in_project.is_(True),
            RulerSpell.source_dataset.not_in(NON_EVIDENCE_SOURCE_DATASETS),
        )
    )


def _country_year(session: Session, iso3: str, year: int) -> CountryYear | None:
    return session.scalar(
        select(CountryYear)
        .join(Country)
        .where(Country.iso3 == iso3, CountryYear.year == year)
        .limit(1)
    )


def _apply_payload(
    existing: RulerIdentityAdjudication,
    payload: dict[str, Any],
    updated_at: datetime,
) -> bool:
    changed = False
    for key, value in payload.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    if changed:
        existing.updated_at = updated_at
    return changed


def _counts(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
) -> tuple[dict[str, int], dict[str, int], int]:
    statement = select(RulerIdentityAdjudication)
    if start_year is not None:
        statement = statement.where(RulerIdentityAdjudication.year >= start_year)
    if end_year is not None:
        statement = statement.where(RulerIdentityAdjudication.year <= end_year)
    rows = session.scalars(statement).all()
    return (
        dict(sorted(Counter(row.review_status for row in rows).items())),
        dict(sorted(Counter(row.classification for row in rows).items())),
        len(rows),
    )


def _sorted_ruler_rows(
    rows: list[tuple[RulerYear, RulerSpell]],
) -> list[tuple[RulerYear, RulerSpell]]:
    return sorted(rows, key=lambda item: (item[0].leader_id, item[0].id))


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ADJUDICATION_METHOD_VERSION",
    "RulerIdentityAdjudicationBuildResult",
    "adjudication_counts",
    "assert_adjudication_database_ready",
    "build_ruler_identity_adjudications",
]
