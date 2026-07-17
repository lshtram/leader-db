"""Explicit, durable locks for confirmed ruler-year identities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.db.models import (
    Country,
    CountryYear,
    CountryYearFact,
    Leader,
    RulerIdentityAdjudication,
    RulerSpell,
    RulerYear,
)
from leaders_db.normalize.leader_names import normalize_leader_name

LOCKED_STATUS = "confirmed_locked"
LOCKED_CLASSIFICATION = "resolved_canonical_formal_office"
LOCKED_RULE = "formal_governing_office_confirmed"
LOCK_SOURCE = "canonical_identity_lock"


class CanonicalIdentityCase(BaseModel):
    """One reviewed formal-governing-office selection."""

    model_config = ConfigDict(extra="forbid")

    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    ruler_name: str = Field(min_length=1)
    office_title: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    rationale: str = Field(min_length=1)
    source_urls: tuple[str, ...] = Field(min_length=1)


class CanonicalIdentityManifest(BaseModel):
    """A reviewed set of ruler-year identities to persist and lock."""

    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=1800, le=2200)
    run_id: str = Field(min_length=1)
    cases: tuple[CanonicalIdentityCase, ...] = Field(min_length=1)


@dataclass(frozen=True)
class CanonicalIdentityLockResult:
    """Result of applying a canonical identity manifest."""

    locked: int
    ruler_years_created: int
    identities: tuple[tuple[str, str, int], ...]


def load_canonical_identity_manifest(path: Path) -> CanonicalIdentityManifest:
    """Load and validate a canonical identity manifest."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CanonicalIdentityManifest.model_validate(payload)


def apply_canonical_identity_locks(
    engine: Engine, manifest: CanonicalIdentityManifest
) -> CanonicalIdentityLockResult:
    """Persist confirmed identities; existing locks require an explicit challenge."""

    created = 0
    identities: list[tuple[str, str, int]] = []
    with Session(engine) as session:
        for case in manifest.cases:
            country = session.scalar(select(Country).where(Country.iso3 == case.iso3))
            if country is None:
                raise ValueError(f"unknown country ISO3: {case.iso3}")
            country_year = session.scalar(
                select(CountryYear).where(
                    CountryYear.country_id == country.id,
                    CountryYear.year == manifest.year,
                )
            )
            if country_year is None:
                raise ValueError(f"missing country-year: {case.iso3}/{manifest.year}")
            existing_lock = session.scalar(
                select(RulerIdentityAdjudication).where(
                    RulerIdentityAdjudication.country_year_id == country_year.id
                )
            )
            if existing_lock is not None and existing_lock.review_status == LOCKED_STATUS:
                if existing_lock.selected_leader_name != case.ruler_name:
                    raise ValueError(
                        f"{case.iso3}/{manifest.year} is locked to "
                        f"{existing_lock.selected_leader_name}; challenge it explicitly first"
                    )
                locked_ruler_year = session.get(
                    RulerYear, existing_lock.selected_ruler_year_id
                )
                if locked_ruler_year is None:
                    raise ValueError(
                        f"locked ruler-year is missing for {case.iso3}/{manifest.year}"
                    )
                _assert_spell_matches(session, locked_ruler_year, case)
                identities.append(
                    (case.iso3, case.ruler_name, existing_lock.selected_ruler_year_id)
                )
                continue

            leader = session.scalar(
                select(Leader).where(
                    Leader.normalized_name == normalize_leader_name(case.ruler_name)
                )
            )
            if leader is None:
                leader = Leader(
                    full_name=case.ruler_name,
                    normalized_name=normalize_leader_name(case.ruler_name),
                    notes="Created by reviewed canonical ruler-year lock.",
                )
                session.add(leader)
                session.flush()
            ruler_year = session.scalar(
                select(RulerYear).where(
                    RulerYear.leader_id == leader.id,
                    RulerYear.country_id == country.id,
                    RulerYear.year == manifest.year,
                )
            )
            if ruler_year is None:
                spell = RulerSpell(
                    leader_id=leader.id,
                    country_id=country.id,
                    office_title=case.office_title,
                    start_date=case.start_date,
                    end_date=case.end_date,
                    source_dataset=LOCK_SOURCE,
                    is_actual_ruler=True,
                    is_formal_leader=True,
                    rule_type="formal governing officeholder",
                    confidence_score=100,
                    notes="Canonical lock sources: " + "; ".join(case.source_urls),
                )
                session.add(spell)
                session.flush()
                ruler_year = RulerYear(
                    leader_id=leader.id,
                    country_id=country.id,
                    year=manifest.year,
                    ruler_spell_id=spell.id,
                    actual_ruler_status="formal_governing_officeholder",
                    system_selected_leader_name=case.ruler_name,
                    match_status=LOCKED_CLASSIFICATION,
                    confidence_score=100,
                    review_status=LOCKED_STATUS,
                    review_note=case.rationale,
                )
                session.add(ruler_year)
                session.flush()
                created += 1
            ruler_year.system_selected_leader_name = case.ruler_name
            ruler_year.actual_ruler_status = "formal_governing_officeholder"
            ruler_year.match_status = LOCKED_CLASSIFICATION
            ruler_year.review_status = LOCKED_STATUS
            ruler_year.review_note = case.rationale
            ruler_year.confidence_score = 100
            _synchronize_spell(session, ruler_year, case)
            _lock_adjudication(
                session, country_year, ruler_year, case, manifest.run_id, existing_lock
            )
            identities.append((case.iso3, case.ruler_name, ruler_year.id))
        session.commit()
    return CanonicalIdentityLockResult(len(identities), created, tuple(identities))


def _synchronize_spell(
    session: Session, ruler_year: RulerYear, case: CanonicalIdentityCase
) -> None:
    """Make the selected derived tenure row match the reviewed canonical record."""

    spell = session.get(RulerSpell, ruler_year.ruler_spell_id)
    if spell is None:
        raise ValueError(f"ruler_year_id={ruler_year.id} has no tenure spell")
    spell.office_title = case.office_title
    spell.start_date = case.start_date
    spell.end_date = case.end_date
    spell.is_actual_ruler = True
    spell.is_formal_leader = True
    source_note = "Canonical lock sources: " + "; ".join(case.source_urls)
    if source_note not in (spell.notes or ""):
        spell.notes = f"{spell.notes or ''}; {source_note}".strip("; ")


def _assert_spell_matches(
    session: Session, ruler_year: RulerYear, case: CanonicalIdentityCase
) -> None:
    """Reject attempts to mutate any identity-bearing field of an existing lock."""

    spell = session.get(RulerSpell, ruler_year.ruler_spell_id)
    if spell is None:
        raise ValueError(f"ruler_year_id={ruler_year.id} has no tenure spell")
    actual = (spell.office_title, spell.start_date, spell.end_date)
    expected = (case.office_title, case.start_date, case.end_date)
    if actual != expected:
        raise ValueError(
            f"ruler_year_id={ruler_year.id} tenure metadata is locked; "
            "challenge it explicitly first"
        )


def challenge_canonical_identity_lock(engine: Engine, *, iso3: str, year: int, reason: str) -> None:
    """Reopen one lock through an explicit, auditable operator action."""

    with Session(engine) as session:
        row = session.scalar(
            select(RulerIdentityAdjudication)
            .join(Country, Country.id == RulerIdentityAdjudication.country_id)
            .where(Country.iso3 == iso3, RulerIdentityAdjudication.year == year)
        )
        if row is None or row.review_status != LOCKED_STATUS:
            raise ValueError(f"no canonical lock exists for {iso3}/{year}")
        row.review_status = "challenged"
        row.review_reason = reason
        row.recommended_next_action = "review challenge and apply a new canonical lock"
        row.updated_at = datetime.now(UTC)
        session.commit()


def _lock_adjudication(session, country_year, ruler_year, case, run_id, row) -> None:
    now = datetime.now(UTC)
    values = {
        "country_year_id": country_year.id,
        "country_id": country_year.country_id,
        "year": country_year.year,
        "selected_ruler_year_id": ruler_year.id,
        "selected_leader_name": case.ruler_name,
        "candidate_ruler_year_ids_json": json.dumps([ruler_year.id]),
        "candidates_json": json.dumps(
            [{"ruler_year_id": ruler_year.id, "leader_name": case.ruler_name}]
        ),
        "classification": LOCKED_CLASSIFICATION,
        "selection_rule": LOCKED_RULE,
        "review_status": LOCKED_STATUS,
        "confidence_score": 100,
        "confidence_penalties_json": "[]",
        "warnings_json": "[]",
        "rationale": case.rationale,
        "review_reason": None,
        "research_prompt": None,
        "recommended_next_action": "reuse this canonical identity",
        "source_slugs_json": json.dumps([LOCK_SOURCE]),
        "source_observation_ids_json": "[]",
        "run_id": run_id,
        "method_version": "canonical_identity_lock_v1",
    }
    if row is None:
        row = RulerIdentityAdjudication(**values, created_at=now, updated_at=now)
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = now
    fact = session.scalar(
        select(CountryYearFact).where(
            CountryYearFact.country_year_id == country_year.id,
            CountryYearFact.field_key == "principal_ruler",
        )
    )
    if fact is not None:
        fact.selected_value_text = case.ruler_name
        fact.selected_entity_id = ruler_year.id
        fact.selected_entity_table = "ruler_years"
        fact.selection_rule = LOCKED_RULE
        fact.adjudication_status = LOCKED_STATUS
        fact.confidence_score = 100
        fact.rationale = case.rationale
        fact.review_reason = None
        fact.research_prompt = None
        fact.recommended_next_action = "reuse this canonical identity"
        fact.run_id = run_id
        fact.method_version = "canonical_identity_lock_v1"
        fact.updated_at = now
    else:
        session.add(
            CountryYearFact(
                country_year_id=country_year.id,
                country_id=country_year.country_id,
                year=country_year.year,
                field_key="principal_ruler",
                field_label="Canonical formal ruler",
                value_type="entity_reference",
                selected_value_text=case.ruler_name,
                selected_entity_table="ruler_years",
                selected_entity_id=ruler_year.id,
                candidate_values_json=values["candidates_json"],
                selection_rule=LOCKED_RULE,
                adjudication_status=LOCKED_STATUS,
                confidence_score=100,
                temporal_fit_score=1.0,
                quality_signals_json=json.dumps({"canonical_lock": True}),
                warnings_json="[]",
                rationale=case.rationale,
                recommended_next_action="reuse this canonical identity",
                source_slugs_json=json.dumps([LOCK_SOURCE]),
                source_observation_ids_json="[]",
                producer="canonical_identity_locks",
                method_version="canonical_identity_lock_v1",
                run_id=run_id,
                created_at=now,
                updated_at=now,
            )
        )


__all__ = [
    "LOCKED_STATUS",
    "CanonicalIdentityLockResult",
    "apply_canonical_identity_locks",
    "challenge_canonical_identity_lock",
    "load_canonical_identity_manifest",
]
