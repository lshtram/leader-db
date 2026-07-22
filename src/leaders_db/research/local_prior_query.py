"""Database query helpers for local structured-prior artifacts."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .local_prior_schema import (
    CLIENT_MATRIX_SOURCE_SLUGS,
    LocalPriorFact,
    LocalStructuredPriorRequest,
)


def load_country_name(bind: Engine | Session, iso3: str) -> str | None:
    statement = text("SELECT country_name FROM countries WHERE iso3 = :iso3")
    rows = execute_mappings(bind, statement, {"iso3": iso3})
    if not rows:
        return None
    return str(rows[0]["country_name"])


def load_leader_accession_year(
    bind: Engine | Session,
    *,
    leader_id: int,
    iso3: str,
    target_year: int,
    leader_name: str | None = None,
) -> int | None:
    statement = text(
        """
        SELECT rs.leader_id, rs.start_date, l.normalized_name
        FROM ruler_spells rs
        JOIN leaders l ON l.id = rs.leader_id
        JOIN countries c ON c.id = rs.country_id
        WHERE c.iso3 = :iso3
        ORDER BY rs.start_date
        """
    )
    rows = execute_mappings(
        bind,
        statement,
        {"iso3": iso3},
    )
    eligible_leader_ids = {leader_id}
    normalized_name = " ".join((leader_name or "").casefold().split())
    name_tokens = normalized_name.split()
    if len(name_tokens) >= 2:
        surname_only_ids = {
            int(row["leader_id"])
            for row in rows
            if str(row["normalized_name"]).casefold() == name_tokens[-1]
        }
        if len(surname_only_ids) == 1:
            eligible_leader_ids.update(surname_only_ids)
    for row in rows:
        if int(row["leader_id"]) not in eligible_leader_ids:
            continue
        value = row["start_date"]
        year = int(str(value)[:4])
        if year <= target_year:
            return year
    return None


def load_included_scope_years(
    bind: Engine | Session,
    *,
    iso3: str,
    years: tuple[int, ...],
) -> tuple[int, ...]:
    statement = text(
        """
        SELECT cy.year
        FROM country_years cy
        JOIN countries c ON c.id = cy.country_id
        WHERE c.iso3 = :iso3
          AND cy.year IN :years
          AND cy.included_in_project = :included_in_project
        ORDER BY cy.year
        """
    ).bindparams(bindparam("years", expanding=True))
    rows = execute_mappings(
        bind,
        statement,
        {"iso3": iso3, "years": years, "included_in_project": True},
    )
    return tuple(int(row["year"]) for row in rows)


def load_local_prior_facts(
    bind: Engine | Session,
    *,
    request: LocalStructuredPriorRequest,
    field_keys: tuple[str, ...],
    included_years: tuple[int, ...],
) -> list[LocalPriorFact]:
    statement = text(
        """
        SELECT
            f.year,
            f.field_key,
            f.field_label,
            f.value_type,
            f.selected_value_text,
            f.selected_value_number,
            f.selected_value_json,
            f.source_slugs_json,
            f.source_observation_ids_json,
            f.confidence_score,
            f.warnings_json
        FROM country_year_facts f
        JOIN country_years cy ON cy.id = f.country_year_id
        JOIN countries c ON c.id = cy.country_id
        WHERE c.iso3 = :iso3
          AND cy.included_in_project = :included_in_project
          AND f.country_id = cy.country_id
          AND f.year = cy.year
          AND f.year IN :years
          AND f.field_key IN :field_keys
        ORDER BY f.year, f.field_key
        """
    ).bindparams(bindparam("years", expanding=True), bindparam("field_keys", expanding=True))
    rows = execute_mappings(
        bind,
        statement,
        {
            "iso3": request.iso3,
            "years": included_years,
            "field_keys": field_keys,
            "included_in_project": True,
        },
    )
    facts: list[LocalPriorFact] = []
    for row in rows:
        source_slugs = _loads_list(row["source_slugs_json"])
        if any(slug in CLIENT_MATRIX_SOURCE_SLUGS for slug in source_slugs):
            continue
        selected_metadata = _selected_metadata(row["selected_value_json"])
        facts.append(
            LocalPriorFact(
                year=int(row["year"]),
                field_key=str(row["field_key"]),
                label=str(row["field_label"]),
                value=_selected_value(row),
                value_type=str(row["value_type"]),
                source_slugs=source_slugs,
                source_observation_ids=_loads_list(row["source_observation_ids_json"]),
                confidence=row["confidence_score"],
                warnings=_loads_list(row["warnings_json"]),
                period_role=_period_role(
                    year=int(row["year"]),
                    target_year=max(request.period.years()),
                    accession_year=request.leader.accession_year,
                ),
                unit=_optional_text(selected_metadata.get("unit")),
                scale=_optional_text(selected_metadata.get("scale")),
                uncertainty=_uncertainty(selected_metadata),
            )
        )
    return facts


def _period_role(*, year: int, target_year: int, accession_year: int | None) -> str:
    if year == target_year:
        return "target"
    if accession_year is not None and year < accession_year:
        return "pre_accession"
    return "tenure"


def execute_mappings(
    bind: Engine | Session,
    statement: Any,
    params: dict[str, Any],
) -> list[Any]:
    context = bind.connect() if isinstance(bind, Engine) else bind.connection()
    close_context = isinstance(bind, Engine)
    try:
        return list(context.execute(statement, params).mappings().all())
    finally:
        if close_context:
            context.close()


def _loads_list(value: Any) -> list[str]:
    if value is None:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _selected_value(row: Any) -> Any:
    if row["selected_value_number"] is not None:
        return row["selected_value_number"]
    if row["selected_value_text"] is not None:
        return row["selected_value_text"]
    if row["selected_value_json"] is not None:
        return json.loads(row["selected_value_json"])
    return None


def _selected_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _uncertainty(selected_metadata: dict[str, Any]) -> dict[str, Any] | None:
    extension = selected_metadata.get("extension")
    if not isinstance(extension, dict):
        return None
    uncertainty = extension.get("uncertainty")
    return uncertainty if isinstance(uncertainty, dict) else None


__all__ = [
    "execute_mappings",
    "load_country_name",
    "load_included_scope_years",
    "load_leader_accession_year",
    "load_local_prior_facts",
]
