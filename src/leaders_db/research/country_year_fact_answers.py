"""Generic D24 answer builder backed by ``country_year_facts``."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.chronicle.country_scope import CountryScopeEntry
from leaders_db.research.registry import get_question_spec_by_methodology_id
from leaders_db.research.results_store import (
    ResearchAnswerEvidence,
    ResearchAnswerRow,
    ResearchQuestionMetadata,
    persist_research_answers,
)

COUNTRY_YEAR_FACTS_METHOD_VERSION = "country_year_facts_structured_v1"
MISSING_FACT_WARNING = "missing_country_year_fact"
PARTIAL_FACT_WARNING = "partial_country_year_fact"


@dataclass(frozen=True)
class _ScopeEntry:
    iso3: str
    country_name: str


@dataclass(frozen=True)
class _FactRow:
    field_key: str
    field_label: str
    value_type: str
    selected_value_text: str | None
    selected_value_number: float | None
    selected_value_json: Any
    candidate_values: Any
    adjudication_status: str
    confidence_score: int | None
    source_slugs: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    warnings: tuple[str, ...]


def build_country_year_fact_answers(
    *,
    bind: Engine | Session,
    question_id: str,
    year: int,
    country_scope: Mapping[str, CountryScopeEntry | Mapping[str, Any]],
    method_version: str = COUNTRY_YEAR_FACTS_METHOD_VERSION,
) -> tuple[ResearchAnswerRow, ...]:
    """Build structured country-year answer rows from selected facts.

    This is the generic D24 path for registry questions whose answer can be
    represented by one or more concept keys already published to
    ``country_year_facts``. It does not infer missing facts; it emits an explicit
    ``missing`` row per in-scope country instead.
    """

    spec = get_question_spec_by_methodology_id(question_id)
    if spec is None:
        raise ValueError(f"Unknown methodology question id: {question_id!r}")
    if spec.answer_level != "country_year":
        raise ValueError("country-year fact answers require a country_year question")
    if spec.evidence_strategy not in {"structured", "structured_plus_context"}:
        raise ValueError("country-year fact answers require structured evidence")

    entries = tuple(
        _ScopeEntry(iso3=iso3, country_name=_country_name(entry))
        for iso3, entry in sorted(country_scope.items())
        if _is_in_scope(entry, year)
    )
    facts_by_country = _load_facts_by_country(
        bind=bind,
        year=year,
        countries=tuple(entry.iso3 for entry in entries),
        field_keys=spec.concept_keys,
    )

    return tuple(
        _answer_from_facts(
            question_id=question_id,
            answer_type=spec.answer_type,
            year=year,
            entry=entry,
            facts=facts_by_country.get(entry.iso3, ()),
            required_field_keys=spec.concept_keys,
            method_version=method_version,
        )
        for entry in entries
    )


def persist_country_year_fact_answers(
    bind: Engine | Session,
    rows: Sequence[ResearchAnswerRow],
    method_version: str = COUNTRY_YEAR_FACTS_METHOD_VERSION,
) -> None:
    """Persist rows built by :func:`build_country_year_fact_answers`."""

    if not rows:
        return
    question_id = rows[0].question_id
    spec = get_question_spec_by_methodology_id(question_id)
    if spec is None:
        raise ValueError(f"Unknown methodology question id: {question_id!r}")
    persist_research_answers(
        bind,
        ResearchQuestionMetadata(
            question_id=spec.methodology_id,
            chapter_id=spec.methodology_id.split(".", maxsplit=1)[0],
            question_text=spec.text,
            answer_type=spec.answer_type,
            category_key=spec.category,
            method_version=method_version,
        ),
        rows,
    )


def _load_facts_by_country(
    *,
    bind: Engine | Session,
    year: int,
    countries: tuple[str, ...],
    field_keys: tuple[str, ...],
) -> dict[str, tuple[_FactRow, ...]]:
    if not countries or not field_keys:
        return {}

    statement = text(
        """
        SELECT
            c.iso3,
            f.field_key,
            f.field_label,
            f.value_type,
            f.selected_value_text,
            f.selected_value_number,
            f.selected_value_json,
            f.candidate_values_json,
            f.adjudication_status,
            f.confidence_score,
            f.source_slugs_json,
            f.source_observation_ids_json,
            f.warnings_json
        FROM country_year_facts f
        JOIN countries c ON c.id = f.country_id
        WHERE f.year = :year
          AND c.iso3 IN :countries
          AND f.field_key IN :field_keys
        ORDER BY c.iso3, f.field_key
        """
    ).bindparams(
        bindparam("countries", expanding=True),
        bindparam("field_keys", expanding=True),
    )
    params = {"year": year, "countries": countries, "field_keys": field_keys}
    context = bind.connect() if isinstance(bind, Engine) else bind.connection()
    close_context = isinstance(bind, Engine)
    try:
        rows = context.execute(statement, params).mappings().all()
    finally:
        if close_context:
            context.close()

    by_country: dict[str, tuple[_FactRow, ...]] = {}
    for row in rows:
        iso3 = str(row["iso3"])
        fact = _fact_from_row(row)
        by_country[iso3] = (*by_country.get(iso3, ()), fact)
    return by_country


def _fact_from_row(row: Mapping[str, Any]) -> _FactRow:
    return _FactRow(
        field_key=str(row["field_key"]),
        field_label=str(row["field_label"]),
        value_type=str(row["value_type"]),
        selected_value_text=row["selected_value_text"],
        selected_value_number=row["selected_value_number"],
        selected_value_json=_loads(row["selected_value_json"]),
        candidate_values=_loads(row["candidate_values_json"]),
        adjudication_status=str(row["adjudication_status"]),
        confidence_score=row["confidence_score"],
        source_slugs=tuple(str(item) for item in _loads(row["source_slugs_json"])),
        source_observation_ids=tuple(
            str(item) for item in _loads(row["source_observation_ids_json"])
        ),
        warnings=tuple(str(item) for item in _loads(row["warnings_json"])),
    )


def _answer_from_facts(
    *,
    question_id: str,
    answer_type: str,
    year: int,
    entry: _ScopeEntry,
    facts: tuple[_FactRow, ...],
    required_field_keys: tuple[str, ...],
    method_version: str,
) -> ResearchAnswerRow:
    if not facts:
        return ResearchAnswerRow(
            question_id=question_id,
            year=year,
            iso3=entry.iso3,
            country_name=entry.country_name,
            method_version=method_version,
            coverage_status="missing",
            warning_codes=(MISSING_FACT_WARNING,),
            caveats=("No selected country-year facts were available for this question.",),
        )

    primary = facts[0]
    missing_field_keys = tuple(key for key in required_field_keys if key not in _fact_keys(facts))
    coverage_status = "partial" if missing_field_keys else "direct"
    warning_codes = _unique(item for fact in facts for item in fact.warnings)
    caveats: tuple[str, ...] = ()
    if missing_field_keys:
        warning_codes = (*warning_codes, PARTIAL_FACT_WARNING)
        caveats = (
            "Some selected country-year facts required by this question were missing.",
        )
    answer_json: dict[str, Any] = {
        "facts": tuple(_fact_payload(fact) for fact in facts),
        "missing_field_keys": missing_field_keys,
    }
    answer_text = _text_answer(primary, facts)
    _apply_question_shape(
        question_id=question_id,
        answer_type=answer_type,
        facts=facts,
        answer_json=answer_json,
    )
    answer_text = (
        _shaped_text(
            question_id=question_id,
            answer_type=answer_type,
            facts=facts,
            answer_json=answer_json,
        )
        or answer_text
    )
    return ResearchAnswerRow(
        question_id=question_id,
        year=year,
        iso3=entry.iso3,
        country_name=entry.country_name,
        answer_boolean=_boolean_answer(question_id, facts),
        answer_numeric=_numeric_answer(
            primary,
            facts,
            answer_type=answer_type,
            required_field_keys=required_field_keys,
        ),
        answer_text=answer_text,
        answer_json=answer_json,
        confidence_score=_confidence(facts),
        coverage_status=coverage_status,
        evidence_year=year,
        method_version=method_version,
        warning_codes=warning_codes,
        caveats=caveats,
        evidence_links=_evidence_links(facts),
    )


def _numeric_answer(
    primary: _FactRow,
    facts: tuple[_FactRow, ...],
    *,
    answer_type: str,
    required_field_keys: tuple[str, ...],
) -> float | None:
    if (
        answer_type == "numeric"
        and len(required_field_keys) == 1
        and len(facts) == 1
        and primary.value_type in {"number", "numeric"}
    ):
        return primary.selected_value_number
    return None


def _text_answer(primary: _FactRow, facts: tuple[_FactRow, ...]) -> str | None:
    if len(facts) == 1 and primary.value_type in {"categorical", "text", "boolean"}:
        return primary.selected_value_text
    return None


def _apply_question_shape(
    *,
    question_id: str,
    answer_type: str,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    if answer_type in {"evidence_bundle", "categorical"}:
        _apply_named_fact_fields(facts=facts, answer_json=answer_json)
    if question_id == "1.7":
        _apply_nuclear_stockpile_reserve_shape(facts=facts, answer_json=answer_json)
    elif question_id == "1.1":
        _apply_nuclear_possession_shape(facts=facts, answer_json=answer_json)
    elif question_id == "2.2":
        _apply_internationalized_conflict_shape(facts=facts, answer_json=answer_json)
    elif question_id == "2.6":
        _apply_military_spending_scale_shape(facts=facts, answer_json=answer_json)


def _apply_named_fact_fields(
    *,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    for fact in facts:
        answer_json[fact.field_key] = _selected_fact_value(fact)


def _apply_nuclear_stockpile_reserve_shape(
    *,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    values = {
        fact.field_key: fact.selected_value_number
        for fact in facts
        if fact.value_type in {"number", "numeric"} and fact.selected_value_number is not None
    }
    stockpile = values.get("nuclear_military_stockpile")
    reserve = values.get("nuclear_reserve_nondeployed")
    shaped: dict[str, float | None] = {
        "stockpile_warheads": stockpile,
        "reserve_nondeployed_warheads": reserve,
        "stockpile_plus_reserve_warheads": None,
        "stockpile_share_of_stockpile_plus_reserve": None,
    }
    if stockpile is not None and reserve is not None:
        total = stockpile + reserve
        shaped["stockpile_plus_reserve_warheads"] = total
        shaped["stockpile_share_of_stockpile_plus_reserve"] = stockpile / total if total else None
    answer_json.update(shaped)


def _apply_nuclear_possession_shape(
    *,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    answer_json["nuclear_total_inventory"] = _numeric_value_for_key(
        facts,
        "nuclear_total_inventory",
    )


def _apply_internationalized_conflict_shape(
    *,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    event_count = _numeric_value_for_key(facts, "internationalized_conflict_events")
    answer_json["internationalized_conflict_events"] = event_count


def _apply_military_spending_scale_shape(
    *,
    facts: tuple[_FactRow, ...],
    answer_json: dict[str, Any],
) -> None:
    answer_json["military_spend_constant_usd"] = _numeric_value_for_key(
        facts,
        "military_spend_constant_usd",
    )
    answer_json["military_spend_per_capita"] = _numeric_value_for_key(
        facts,
        "military_spend_per_capita",
    )


def _shaped_text(
    *,
    question_id: str,
    answer_type: str,
    facts: tuple[_FactRow, ...],
    answer_json: Mapping[str, Any],
) -> str | None:
    if question_id == "1.1":
        return _nuclear_possession_text(answer_json)
    if question_id == "2.2":
        return _internationalized_conflict_text(answer_json)
    if question_id == "2.6":
        return _military_spending_scale_text(answer_json)
    if question_id == "1.7":
        return _nuclear_stockpile_reserve_text(answer_json)
    if answer_type in {"evidence_bundle", "categorical"}:
        return _fact_summary_text(facts)
    return None


def _nuclear_possession_text(answer_json: Mapping[str, Any]) -> str | None:
    total_inventory = answer_json.get("nuclear_total_inventory")
    if total_inventory is None:
        return None
    return f"nuclear total inventory: {_format_count(total_inventory)}"


def _internationalized_conflict_text(answer_json: Mapping[str, Any]) -> str | None:
    event_count = answer_json.get("internationalized_conflict_events")
    if event_count is None:
        return None
    return f"internationalized conflict events: {_format_count(event_count)}"


def _military_spending_scale_text(answer_json: Mapping[str, Any]) -> str | None:
    constant_usd = answer_json.get("military_spend_constant_usd")
    per_capita = answer_json.get("military_spend_per_capita")
    if constant_usd is None and per_capita is None:
        return None
    parts = []
    if constant_usd is not None:
        parts.append(f"constant USD: {_format_count(constant_usd)}")
    if per_capita is not None:
        parts.append(f"per capita: {_format_count(per_capita)}")
    return "; ".join(parts)


def _nuclear_stockpile_reserve_text(answer_json: Mapping[str, Any]) -> str | None:
    stockpile = answer_json.get("stockpile_warheads")
    reserve = answer_json.get("reserve_nondeployed_warheads")
    if stockpile is None and reserve is None:
        return None
    parts = []
    if stockpile is not None:
        parts.append(f"military stockpile: {_format_count(stockpile)}")
    if reserve is not None:
        parts.append(f"reserve/nondeployed: {_format_count(reserve)}")
    return "; ".join(parts)


def _format_count(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _fact_summary_text(facts: tuple[_FactRow, ...]) -> str | None:
    parts = []
    for fact in facts:
        value = _selected_fact_value(fact)
        if value is not None:
            parts.append(f"{fact.field_label or fact.field_key}: {_format_value(value)}")
    return "; ".join(parts) if parts else None


def _selected_fact_value(fact: _FactRow) -> Any:
    if fact.value_type in {"number", "numeric"}:
        return fact.selected_value_number
    if fact.value_type in {"categorical", "text", "boolean"}:
        return fact.selected_value_text
    return fact.selected_value_json


def _format_value(value: Any) -> str:
    if isinstance(value, int | float):
        return _format_count(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _boolean_answer(question_id: str, facts: tuple[_FactRow, ...]) -> bool | None:
    if question_id == "1.1":
        total_inventory = _numeric_value_for_key(facts, "nuclear_total_inventory")
        return None if total_inventory is None else total_inventory > 0
    if question_id == "2.2":
        event_count = _numeric_value_for_key(facts, "internationalized_conflict_events")
        return None if event_count is None else event_count > 0
    return None


def _numeric_value_for_key(facts: tuple[_FactRow, ...], field_key: str) -> float | None:
    for fact in facts:
        if (
            fact.field_key == field_key
            and fact.value_type in {"number", "numeric"}
            and fact.selected_value_number is not None
        ):
            return fact.selected_value_number
    return None


def _fact_payload(fact: _FactRow) -> dict[str, Any]:
    return {
        "field_key": fact.field_key,
        "field_label": fact.field_label,
        "value_type": fact.value_type,
        "selected_value_number": fact.selected_value_number,
        "selected_value_text": fact.selected_value_text,
        "selected_value_json": fact.selected_value_json,
        "candidate_values": fact.candidate_values,
        "adjudication_status": fact.adjudication_status,
        "confidence_score": fact.confidence_score,
        "source_slugs": fact.source_slugs,
        "source_observation_ids": fact.source_observation_ids,
    }


def _confidence(facts: tuple[_FactRow, ...]) -> float | None:
    scores = tuple(fact.confidence_score for fact in facts if fact.confidence_score is not None)
    if not scores:
        return None
    return sum(scores) / len(scores) / 100.0


def _evidence_links(facts: tuple[_FactRow, ...]) -> tuple[ResearchAnswerEvidence, ...]:
    links: list[ResearchAnswerEvidence] = []
    for fact in facts:
        source_by_observation = _source_by_observation_id(fact)
        for observation_id in fact.source_observation_ids:
            links.append(
                ResearchAnswerEvidence(
                    source_slug=source_by_observation.get(
                        observation_id, "country_year_facts"
                    ),
                    source_observation_id=observation_id,
                    evidence_role="primary",
                )
            )
    return tuple(dict.fromkeys(links))


def _fact_keys(facts: tuple[_FactRow, ...]) -> set[str]:
    return {fact.field_key for fact in facts}


def _source_by_observation_id(fact: _FactRow) -> dict[str, str]:
    source_by_observation: dict[str, str] = {}
    for payload in _candidate_payloads(fact):
        source_slug = payload.get("source_slug")
        if not isinstance(source_slug, str):
            continue
        input_ids = payload.get("input_observation_ids", ())
        if not isinstance(input_ids, Sequence) or isinstance(input_ids, str):
            continue
        for observation_id in input_ids:
            if isinstance(observation_id, str):
                source_by_observation[observation_id] = source_slug
    return source_by_observation


def _candidate_payloads(fact: _FactRow) -> tuple[Mapping[str, Any], ...]:
    payloads: list[Mapping[str, Any]] = []
    if isinstance(fact.selected_value_json, Mapping):
        payloads.append(fact.selected_value_json)
    if isinstance(fact.candidate_values, Sequence) and not isinstance(fact.candidate_values, str):
        payloads.extend(item for item in fact.candidate_values if isinstance(item, Mapping))
    return tuple(payloads)


def _is_in_scope(entry: CountryScopeEntry | Mapping[str, Any], year: int) -> bool:
    start_year = _scope_year(entry, "start_year")
    end_year = _scope_year(entry, "end_year")
    return (start_year is None or start_year <= year) and (end_year is None or year <= end_year)


def _scope_year(entry: CountryScopeEntry | Mapping[str, Any], key: str) -> int | None:
    value = entry.get(key) if isinstance(entry, Mapping) else getattr(entry, key)
    return value if isinstance(value, int) else None


def _country_name(entry: CountryScopeEntry | Mapping[str, Any]) -> str:
    value = entry.get("country_name") if isinstance(entry, Mapping) else entry.country_name
    return str(value)


def _loads(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _unique(values: Sequence[str] | Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__ = [
    "COUNTRY_YEAR_FACTS_METHOD_VERSION",
    "MISSING_FACT_WARNING",
    "PARTIAL_FACT_WARNING",
    "build_country_year_fact_answers",
    "persist_country_year_fact_answers",
]
