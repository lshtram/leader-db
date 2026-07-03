"""DB-backed ruler identity builder for the country/year grid.

I4 intentionally consumes already-persisted normalized observations rather than
reading raw source files. It accepts the source-layer leader identity families
and expands resolved spell candidates only across existing ``country_years``.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from leaders_db.db.models import (
    Country,
    CountryYear,
    CountryYearFact,
    Leader,
    LeaderAlias,
    NormalizedObservationRow,
    RulerIdentityAdjudication,
    RulerScore,
    RulerSpell,
    RulerYear,
    Source,
)
from leaders_db.db.readiness import DatabaseReadinessError, assert_database_ready
from leaders_db.normalize.countries import normalize_country_name, normalize_iso3
from leaders_db.normalize.leader_names import normalize_leader_name
from leaders_db.sources.country_codes import (
    iso3_from_cow_code,
    iso3_from_source_country,
    normalize_source_country_code,
)

IDENTITY_TABLES: tuple[str, ...] = (
    "countries",
    "country_years",
    "leaders",
    "leader_aliases",
    "ruler_spells",
    "ruler_years",
    "sources",
    "normalized_observations",
)
IDENTITY_FAMILIES: tuple[str, ...] = (
    "leader_identity_spell",
    "leader_identity_month",
    "leader_identity_country_year",
)
SOURCE_IDENTITY_INDICATORS: dict[str, tuple[str, ...]] = {
    "archigos": ("archigos_leader_name",),
    "reign": ("reign_leader",),
}
NON_EVIDENCE_SOURCE_DATASETS: tuple[str, ...] = (
    "client_existing",
    "vertical_slice_client_seed",
)
LIMITATIONS: tuple[str, ...] = (
    "I4 consumes persisted normalized observations only; it does not read raw source files.",
    "Unresolved country-years are reported as missing because ruler_years has no "
    "leaderless unresolved row shape.",
    "Leader matching is deterministic by normalized name plus aliases; same-name "
    "people are not yet disambiguated by birth/death metadata.",
    "Sources without ISO3, a supported source-native country code/COW code, or an "
    "exact country-name match in countries are skipped and counted as unresolvable observations.",
)
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 70
AUTO_ADJUDICATION_PENALTY = 10
MANUAL_CONFLICT_PENALTY = 20
YEAR_MAJORITY_DAYS = 183


@dataclass(frozen=True)
class IdentitySpellInput:
    """Normalized spell candidate crossing the source/identity boundary."""

    source_slug: str
    observation_id: str
    observation_family: str
    country_iso3: str
    leader_name: str
    leader_source_id: str | None
    alias: str | None
    office_title: str | None
    start_date: date
    end_date: date | None
    is_actual_ruler: bool
    is_formal_leader: bool
    rule_type: str | None
    shared_rule_flag: bool
    disputed_rule_flag: bool
    confidence_score: int | None
    notes: str | None


@dataclass(frozen=True)
class RulerIdentityBuildResult:
    """Summary of an idempotent ruler identity build."""

    observations_read: int
    observations_used: int
    observations_skipped: int
    leaders_created: int
    aliases_created: int
    ruler_spells_created: int
    ruler_spells_updated: int
    ruler_years_created: int
    ruler_years_updated: int


@dataclass(frozen=True)
class RulerIdentityCoverageReport:
    """Aggregate identity coverage for country-years."""

    total_country_years: int
    covered_country_years: int
    missing_country_years: int
    disputed_country_years: int
    multiple_ruler_country_years: int
    low_confidence_country_years: int
    source_conflict_country_years: int
    skipped_identity_observations: int
    limitations: tuple[str, ...]


def build_ruler_identity(
    engine: Engine,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
) -> RulerIdentityBuildResult:
    """Populate leaders, aliases, ruler spells, and ruler years from observations."""

    assert_identity_database_ready(engine)
    with Session(engine, expire_on_commit=False) as session:
        _remove_non_evidence_identity_outputs(session)
        country_by_iso3 = _country_by_iso3(session)
        country_by_name = _country_by_normalized_name(session)
        rows = _identity_observation_rows(session, start_year=start_year, end_year=end_year)
        candidates = _dedupe_spell_inputs(
            candidate
            for row in rows
            if (candidate := _row_to_spell_input(row, country_by_iso3, country_by_name))
            is not None
        )

        leaders_created = 0
        aliases_created = 0
        spells_created = 0
        spells_updated = 0
        years_created = 0
        years_updated = 0
        leader_by_name = _leader_by_normalized_name(session)
        sources_by_slug: dict[str, Source] = {}

        for candidate in candidates:
            source = _get_or_create_source(session, candidate.source_slug, sources_by_slug)
            normalized_name = normalize_leader_name(candidate.leader_name)
            leader = leader_by_name.get(normalized_name)
            if leader is None:
                leader = Leader(full_name=candidate.leader_name, normalized_name=normalized_name)
                session.add(leader)
                session.flush()
                leader_by_name[normalized_name] = leader
                leaders_created += 1

            if _ensure_alias(session, leader, source, candidate.alias or candidate.leader_name):
                aliases_created += 1
            country = country_by_iso3[candidate.country_iso3]
            _remove_superseded_monthly_spell_fragments(session, leader, country, candidate)
            spell, created, changed = _upsert_spell(session, leader, country, candidate)
            if created:
                spells_created += 1
            elif changed:
                spells_updated += 1
            created_years, updated_years = _expand_spell_to_ruler_years(session, spell, candidate)
            years_created += created_years
            years_updated += updated_years

        _refresh_ruler_year_statuses(session)
        session.commit()

    return RulerIdentityBuildResult(
        observations_read=len(rows),
        observations_used=len(candidates),
        observations_skipped=len(rows) - len(candidates),
        leaders_created=leaders_created,
        aliases_created=aliases_created,
        ruler_spells_created=spells_created,
        ruler_spells_updated=spells_updated,
        ruler_years_created=years_created,
        ruler_years_updated=years_updated,
    )


def build_ruler_identity_coverage_report(
    engine: Engine,
    *,
    year: int | None = None,
    low_confidence_threshold: int = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> RulerIdentityCoverageReport:
    """Return identity coverage for all or one populated country-year."""

    assert_identity_database_ready(engine)
    with Session(engine) as session:
        country_year_filter = _country_year_filter(year)
        total = session.scalar(select(func.count(CountryYear.id)).where(*country_year_filter)) or 0
        covered_pairs = _covered_country_year_pairs(session, year=year)
        covered = len(covered_pairs)
        disputed = _count_distinct_ruler_year_pairs(
            session,
            or_(RulerYear.match_status == "disputed", RulerSpell.disputed_rule_flag.is_(True)),
            year=year,
        )
        multiple = _count_multiple_ruler_pairs(session, year=year)
        low_confidence = _count_distinct_ruler_year_pairs(
            session,
            RulerYear.confidence_score.is_not(None),
            RulerYear.confidence_score < low_confidence_threshold,
            year=year,
        )
        source_conflicts = _count_source_conflict_pairs(session, year=year)
        rows = _identity_observation_rows(session, start_year=year, end_year=year)
        country_by_iso3 = _country_by_iso3(session)
        country_by_name = _country_by_normalized_name(session)
        skipped = sum(
            1
            for row in rows
            if _row_to_spell_input(row, country_by_iso3, country_by_name) is None
        )

    return RulerIdentityCoverageReport(
        total_country_years=total,
        covered_country_years=covered,
        missing_country_years=max(total - covered, 0),
        disputed_country_years=disputed,
        multiple_ruler_country_years=multiple,
        low_confidence_country_years=low_confidence,
        source_conflict_country_years=source_conflicts,
        skipped_identity_observations=skipped,
        limitations=LIMITATIONS,
    )


def ruler_identity_coverage_to_json(report: RulerIdentityCoverageReport) -> dict[str, object]:
    """Return a JSON-serializable coverage payload."""

    return {
        "total_country_years": report.total_country_years,
        "covered_country_years": report.covered_country_years,
        "missing_country_years": report.missing_country_years,
        "disputed_country_years": report.disputed_country_years,
        "multiple_ruler_country_years": report.multiple_ruler_country_years,
        "low_confidence_country_years": report.low_confidence_country_years,
        "source_conflict_country_years": report.source_conflict_country_years,
        "skipped_identity_observations": report.skipped_identity_observations,
        "limitations": list(report.limitations),
    }


def assert_identity_database_ready(engine: Engine) -> None:
    """Ensure identity tables are present, with a friendly CLI-safe message."""

    message = (
        "The local ruler identity database is not initialized. Run `leaders-db init-db` "
        "and `leaders-db scope build-country-years`, or pass `--db-url`."
    )
    try:
        inspect(engine).get_table_names()
    except SQLAlchemyError as exc:
        raise DatabaseReadinessError(message) from exc
    try:
        assert_database_ready(engine, required_tables=IDENTITY_TABLES)
    except DatabaseReadinessError as exc:
        missing = ", ".join(IDENTITY_TABLES)
        raise DatabaseReadinessError(f"{message} Missing table(s): {missing}.") from exc
    try:
        with engine.connect() as conn:
            included_country_years = conn.execute(
                select(func.count(CountryYear.id)).where(
                    CountryYear.included_in_project.is_(True)
                )
            ).scalar_one()
    except SQLAlchemyError as exc:
        raise DatabaseReadinessError(message) from exc
    if included_country_years == 0:
        raise DatabaseReadinessError(
            f"{message} No included country_years rows found. Run "
            "`leaders-db scope build-country-years` before building ruler identity."
        )


def _identity_observation_rows(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
) -> list[NormalizedObservationRow]:
    statement: Select[tuple[NormalizedObservationRow]] = select(NormalizedObservationRow).where(
        NormalizedObservationRow.observation_family.in_(IDENTITY_FAMILIES)
    )
    statement = statement.where(
        NormalizedObservationRow.source_slug.not_in(NON_EVIDENCE_SOURCE_DATASETS)
    )
    source_indicator_clauses = [
        NormalizedObservationRow.source_slug.not_in(tuple(SOURCE_IDENTITY_INDICATORS))
    ]
    for source_slug, indicator_codes in SOURCE_IDENTITY_INDICATORS.items():
        source_indicator_clauses.append(
            (NormalizedObservationRow.source_slug == source_slug)
            & (NormalizedObservationRow.indicator_code.in_(indicator_codes))
        )
    statement = statement.where(or_(*source_indicator_clauses))
    if start_year is not None:
        statement = statement.where(
            (NormalizedObservationRow.year.is_(None))
            | (NormalizedObservationRow.year >= start_year)
        )
    if end_year is not None:
        statement = statement.where(
            (NormalizedObservationRow.year.is_(None))
            | (NormalizedObservationRow.year <= end_year)
        )
    return list(session.scalars(statement.order_by(NormalizedObservationRow.id)).all())


def _remove_non_evidence_identity_outputs(session: Session) -> None:
    """Remove production identity rows previously created from non-evidence seeds."""

    non_evidence_spells = session.scalars(
        select(RulerSpell).where(RulerSpell.source_dataset.in_(NON_EVIDENCE_SOURCE_DATASETS))
    ).all()
    non_evidence_spell_ids = [spell.id for spell in non_evidence_spells]
    if non_evidence_spell_ids:
        non_evidence_ruler_years = session.scalars(
            select(RulerYear).where(RulerYear.ruler_spell_id.in_(non_evidence_spell_ids))
        ).all()
        non_evidence_ruler_year_ids = [ruler_year.id for ruler_year in non_evidence_ruler_years]
        if non_evidence_ruler_year_ids:
            for ruler_score in session.scalars(
                select(RulerScore).where(
                    RulerScore.ruler_year_id.in_(non_evidence_ruler_year_ids)
                )
            ).all():
                session.delete(ruler_score)
        for ruler_year in session.scalars(
            select(RulerYear).where(RulerYear.ruler_spell_id.in_(non_evidence_spell_ids))
        ).all():
            session.delete(ruler_year)
        for spell in non_evidence_spells:
            session.delete(spell)

    non_evidence_source_ids = [
        source.id
        for source in session.scalars(
            select(Source).where(Source.source_name.in_(NON_EVIDENCE_SOURCE_DATASETS))
        ).all()
    ]
    if non_evidence_source_ids:
        for alias in session.scalars(
            select(LeaderAlias).where(LeaderAlias.source_id.in_(non_evidence_source_ids))
        ).all():
            session.delete(alias)

    session.flush()
    _remove_orphan_leaders(session)


def _remove_orphan_leaders(session: Session) -> None:
    for leader in session.scalars(select(Leader)).all():
        has_spell = session.scalar(
            select(func.count(RulerSpell.id)).where(RulerSpell.leader_id == leader.id)
        )
        has_alias = session.scalar(
            select(func.count(LeaderAlias.id)).where(LeaderAlias.leader_id == leader.id)
        )
        if not has_spell and not has_alias:
            session.delete(leader)
    session.flush()


def _row_to_spell_input(
    row: NormalizedObservationRow,
    country_by_iso3: dict[str, Country],
    country_by_name: dict[str, Country],
) -> IdentitySpellInput | None:
    extension = _loads_json(row.extension_json)
    country = _resolve_country(row, extension, country_by_iso3, country_by_name)
    leader_name = _first_text(
        row.leader_name,
        extension.get("leader_name"),
        extension.get("person_label"),
        extension.get("reign_leader"),
        extension.get("archigos_leader_name"),
    )
    if country is None or not leader_name:
        return None
    start = _extract_start_date(row, extension)
    if start is None:
        return None
    end = _extract_end_date(row, extension, start)
    if end is not None and end < start:
        return None
    office_title = _first_text(extension.get("office_title"), extension.get("office_label"))
    source_slug = row.source_slug
    return IdentitySpellInput(
        source_slug=source_slug,
        observation_id=row.observation_id,
        observation_family=row.observation_family,
        country_iso3=country.iso3,
        leader_name=leader_name,
        leader_source_id=_first_text(
            row.leader_id,
            extension.get("person_qid"),
            extension.get("archigos_obsid"),
        ),
        alias=leader_name,
        office_title=office_title,
        start_date=start,
        end_date=end,
        is_actual_ruler=_bool_value(
            extension.get("is_actual_ruler"),
            default=_default_actual_status(row.indicator_code),
        ),
        is_formal_leader=_bool_value(
            extension.get("is_formal_leader"),
            default=_default_formal_status(row.indicator_code),
        ),
        rule_type=_first_text(extension.get("rule_type"), extension.get("actual_ruler_status")),
        shared_rule_flag=_bool_value(extension.get("shared_rule_flag"), default=False),
        disputed_rule_flag=_bool_value(extension.get("disputed_rule_flag"), default=False),
        confidence_score=_confidence(row, extension),
        notes=_notes(row, extension),
    )


def _dedupe_spell_inputs(candidates: Iterable[IdentitySpellInput]) -> list[IdentitySpellInput]:
    """Collapse repeated rows and aggregate consecutive monthly observations."""

    unique: list[IdentitySpellInput] = []
    seen: set[tuple[object, ...]] = set()
    for candidate in candidates:
        key = (
            candidate.source_slug,
            candidate.country_iso3,
            normalize_leader_name(candidate.leader_name),
            candidate.start_date,
            candidate.end_date,
            candidate.office_title,
            candidate.is_actual_ruler,
            candidate.is_formal_leader,
            candidate.rule_type,
            candidate.shared_rule_flag,
            candidate.disputed_rule_flag,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return _aggregate_monthly_spell_inputs(unique)


def _aggregate_monthly_spell_inputs(
    candidates: Iterable[IdentitySpellInput],
) -> list[IdentitySpellInput]:
    """Merge conservative same-leader month runs into continuous spans."""

    passthrough: list[IdentitySpellInput] = []
    monthly_by_key: dict[tuple[object, ...], list[IdentitySpellInput]] = {}
    for candidate in candidates:
        if not _is_monthly_spell(candidate):
            passthrough.append(candidate)
            continue
        monthly_by_key.setdefault(_monthly_aggregation_key(candidate), []).append(candidate)

    aggregated: list[IdentitySpellInput] = []
    for group in monthly_by_key.values():
        aggregated.extend(_continuous_monthly_runs(group))
    return sorted(
        [*passthrough, *aggregated],
        key=lambda item: (item.source_slug, item.country_iso3, item.start_date, item.leader_name),
    )


def _is_monthly_spell(candidate: IdentitySpellInput) -> bool:
    return (
        candidate.observation_family == "leader_identity_month"
        and candidate.end_date is not None
        and candidate.start_date.day == 1
        and candidate.end_date
        == date(
            candidate.start_date.year,
            candidate.start_date.month,
            calendar.monthrange(candidate.start_date.year, candidate.start_date.month)[1],
        )
    )


def _monthly_aggregation_key(candidate: IdentitySpellInput) -> tuple[object, ...]:
    return (
        candidate.source_slug,
        candidate.country_iso3,
        normalize_leader_name(candidate.leader_name),
        candidate.office_title,
        candidate.is_actual_ruler,
        candidate.is_formal_leader,
        candidate.rule_type,
        candidate.shared_rule_flag,
        candidate.disputed_rule_flag,
    )


def _continuous_monthly_runs(group: list[IdentitySpellInput]) -> list[IdentitySpellInput]:
    ordered = sorted(group, key=lambda item: (item.start_date, item.end_date or item.start_date))
    if not ordered:
        return []
    runs: list[list[IdentitySpellInput]] = [[ordered[0]]]
    for candidate in ordered[1:]:
        previous = runs[-1][-1]
        if (
            previous.end_date is not None
            and candidate.start_date == previous.end_date + timedelta(days=1)
        ):
            runs[-1].append(candidate)
        else:
            runs.append([candidate])
    return [_merge_monthly_run(run) for run in runs]


def _merge_monthly_run(run: list[IdentitySpellInput]) -> IdentitySpellInput:
    first = run[0]
    last = run[-1]
    confidence_values = [item.confidence_score for item in run if item.confidence_score is not None]
    return IdentitySpellInput(
        source_slug=first.source_slug,
        observation_id="|".join(item.observation_id for item in run),
        observation_family=first.observation_family,
        country_iso3=first.country_iso3,
        leader_name=first.leader_name,
        leader_source_id=first.leader_source_id,
        alias=first.alias,
        office_title=first.office_title,
        start_date=first.start_date,
        end_date=last.end_date,
        is_actual_ruler=first.is_actual_ruler,
        is_formal_leader=first.is_formal_leader,
        rule_type=first.rule_type,
        shared_rule_flag=first.shared_rule_flag,
        disputed_rule_flag=first.disputed_rule_flag,
        confidence_score=min(confidence_values) if confidence_values else None,
        notes=_aggregated_monthly_notes(run),
    )


def _aggregated_monthly_notes(run: list[IdentitySpellInput]) -> str:
    observation_notes = "; ".join(item.notes or "" for item in run if item.notes)
    end_text = run[-1].end_date.isoformat() if run[-1].end_date else "open"
    return (
        f"I4 aggregated {len(run)} consecutive monthly identity observations "
        f"from {run[0].start_date.isoformat()} to {end_text}; "
        f"{observation_notes}"
    ).strip()


def _resolve_country(  # noqa: PLR0911, PLR0912
    row: NormalizedObservationRow,
    extension: dict[str, Any],
    country_by_iso3: dict[str, Country],
    country_by_name: dict[str, Country],
) -> Country | None:
    if row.source_slug == "wikidata_heads_of_state_government":
        return _resolve_wikidata_country(row, extension, country_by_iso3)
    for value in (
        row.country_code,
        extension.get("country_code"),
        extension.get("country_iso3"),
        extension.get("iso3"),
        extension.get("archigos_idacr"),
        extension.get("reign_country"),
    ):
        if not value:
            continue
        try:
            country = country_by_iso3.get(normalize_iso3(str(value)))
        except ValueError:
            country = None
        if country is not None:
            return country
    for value, ccode in (
        (extension.get("reign_country"), extension.get("reign_ccode")),
        (extension.get("country_name"), extension.get("ccode")),
        (extension.get("country_label"), extension.get("ccode")),
    ):
        iso3 = iso3_from_source_country(value, ccode=ccode, year=row.year)
        if iso3 is None:
            continue
        country = country_by_iso3.get(iso3)
        if country is not None:
            return country
    for value in (
        extension.get("ccode"),
        extension.get("cowcode"),
        extension.get("archigos_ccode"),
        extension.get("reign_ccode"),
    ):
        iso3 = iso3_from_cow_code(value)
        if iso3 is None:
            continue
        if (
            row.source_slug == "reign"
            and iso3 == "RUS"
            and row.year is not None
            and row.year <= 1991
        ):
            continue
        country = country_by_iso3.get(iso3)
        if country is not None:
            return country
    for value in (extension.get("archigos_idacr"), extension.get("reign_country")):
        iso3 = normalize_source_country_code(value)
        if iso3 is not None and (country := country_by_iso3.get(iso3)) is not None:
            return country
    for value in (row.country_name, extension.get("country_name"), extension.get("country_label")):
        if not value:
            continue
        country = country_by_name.get(normalize_country_name(str(value)))
        if country is not None:
            return country
    return None


def _resolve_wikidata_country(
    row: NormalizedObservationRow,
    extension: dict[str, Any],
    country_by_iso3: dict[str, Country],
) -> Country | None:
    """Resolve Wikidata identity rows only by source-provided ISO3."""

    for value in (row.country_code, extension.get("country_iso3"), extension.get("iso3")):
        if not value:
            continue
        try:
            country = country_by_iso3.get(normalize_iso3(str(value)))
        except ValueError:
            country = None
        if country is not None:
            return country
    return None


def _extract_start_date(row: NormalizedObservationRow, extension: dict[str, Any]) -> date | None:
    explicit = _parse_date(_first_text(extension.get("start_date"), extension.get("start")))
    if explicit is not None:
        return explicit
    year = _int_value(extension.get("start_year")) or row.year
    month = _int_value(extension.get("month"), extension.get("reign_month"))
    if year is None:
        return None
    return date(int(year), int(month or 1), 1)


def _extract_end_date(
    row: NormalizedObservationRow,
    extension: dict[str, Any],
    start: date,
) -> date | None:
    explicit = _parse_date(_first_text(extension.get("end_date"), extension.get("end")))
    if explicit is not None:
        return explicit
    end_year = _int_value(extension.get("end_year"), extension.get("archigos_end_year"))
    end_month = _int_value(extension.get("end_month"))
    if end_year is not None:
        month = int(end_month or 12)
        return date(int(end_year), month, calendar.monthrange(int(end_year), month)[1])
    if row.observation_family == "leader_identity_month":
        month = _int_value(extension.get("month"), extension.get("reign_month")) or start.month
        return date(start.year, int(month), calendar.monthrange(start.year, int(month))[1])
    if row.year is not None and row.observation_family == "leader_identity_country_year":
        return date(int(row.year), 12, 31)
    return None


def _get_or_create_source(
    session: Session,
    source_slug: str,
    cache: dict[str, Source],
) -> Source:
    if source_slug in cache:
        return cache[source_slug]
    source = session.scalar(select(Source).where(Source.source_name == source_slug).limit(1))
    if source is None:
        source = Source(source_name=source_slug, source_type="dataset")
        session.add(source)
        session.flush()
    cache[source_slug] = source
    return source


def _ensure_alias(session: Session, leader: Leader, source: Source, alias: str) -> bool:
    clean_alias = alias.strip()
    if not clean_alias:
        return False
    existing = session.scalar(
        select(LeaderAlias).where(
            LeaderAlias.leader_id == leader.id,
            LeaderAlias.source_id == source.id,
            LeaderAlias.alias == clean_alias,
        )
    )
    if existing is not None:
        return False
    session.add(LeaderAlias(leader_id=leader.id, source_id=source.id, alias=clean_alias))
    session.flush()
    return True


def _upsert_spell(
    session: Session,
    leader: Leader,
    country: Country,
    candidate: IdentitySpellInput,
) -> tuple[RulerSpell, bool, bool]:
    existing = session.scalar(
        select(RulerSpell).where(
            RulerSpell.leader_id == leader.id,
            RulerSpell.country_id == country.id,
            RulerSpell.source_dataset == candidate.source_slug,
            RulerSpell.start_date == candidate.start_date,
            RulerSpell.end_date.is_(candidate.end_date)
            if candidate.end_date is None
            else RulerSpell.end_date == candidate.end_date,
            RulerSpell.office_title.is_(candidate.office_title)
            if candidate.office_title is None
            else RulerSpell.office_title == candidate.office_title,
        )
    )
    if existing is None:
        spell = RulerSpell(
            leader_id=leader.id,
            country_id=country.id,
            office_title=candidate.office_title,
            start_date=candidate.start_date,
            end_date=candidate.end_date,
            source_dataset=candidate.source_slug,
            is_actual_ruler=candidate.is_actual_ruler,
            is_formal_leader=candidate.is_formal_leader,
            rule_type=candidate.rule_type,
            shared_rule_flag=candidate.shared_rule_flag,
            disputed_rule_flag=candidate.disputed_rule_flag,
            confidence_score=candidate.confidence_score,
            notes=candidate.notes,
        )
        session.add(spell)
        session.flush()
        return spell, True, True
    changed = _spell_needs_update(existing, candidate)
    if not changed:
        return existing, False, False
    existing.is_actual_ruler = candidate.is_actual_ruler
    existing.is_formal_leader = candidate.is_formal_leader
    existing.rule_type = candidate.rule_type
    existing.shared_rule_flag = candidate.shared_rule_flag
    existing.disputed_rule_flag = candidate.disputed_rule_flag
    existing.confidence_score = candidate.confidence_score
    existing.notes = candidate.notes
    return existing, False, True


def _remove_superseded_monthly_spell_fragments(
    session: Session,
    leader: Leader,
    country: Country,
    candidate: IdentitySpellInput,
) -> None:
    """Delete stale one-month spell rows covered by a new monthly aggregate.

    The pre-aggregation builder wrote one ``ruler_spells`` row per REIGN month.
    Because spell upsert keys include exact dates, those rows survive forever
    unless the aggregate run explicitly supersedes them.  Only multi-month
    aggregate candidates can supersede fragments; singleton monthly runs are
    left intact so non-consecutive gap spells remain conservative.
    """

    if not _is_multi_month_monthly_aggregate(candidate):
        return

    stale_spells = session.scalars(
        select(RulerSpell).where(
            RulerSpell.leader_id == leader.id,
            RulerSpell.country_id == country.id,
            RulerSpell.source_dataset == candidate.source_slug,
            RulerSpell.start_date >= candidate.start_date,
            RulerSpell.end_date.is_not(None),
            RulerSpell.end_date <= candidate.end_date,
            RulerSpell.office_title.is_(candidate.office_title)
            if candidate.office_title is None
            else RulerSpell.office_title == candidate.office_title,
            RulerSpell.is_actual_ruler == candidate.is_actual_ruler,
            RulerSpell.is_formal_leader == candidate.is_formal_leader,
            RulerSpell.rule_type.is_(candidate.rule_type)
            if candidate.rule_type is None
            else RulerSpell.rule_type == candidate.rule_type,
            RulerSpell.shared_rule_flag == candidate.shared_rule_flag,
            RulerSpell.disputed_rule_flag == candidate.disputed_rule_flag,
        )
    ).all()
    stale_spells = [spell for spell in stale_spells if _is_one_month_spell(spell)]
    if not stale_spells:
        return

    stale_spell_ids = [spell.id for spell in stale_spells]
    stale_ruler_years = session.scalars(
        select(RulerYear).where(RulerYear.ruler_spell_id.in_(stale_spell_ids))
    ).all()
    stale_ruler_year_ids = [ruler_year.id for ruler_year in stale_ruler_years]
    affected_country_years = {
        (ruler_year.country_id, ruler_year.year) for ruler_year in stale_ruler_years
    }
    if stale_ruler_year_ids:
        for ruler_score in session.scalars(
            select(RulerScore).where(RulerScore.ruler_year_id.in_(stale_ruler_year_ids))
        ).all():
            session.delete(ruler_score)
        for adjudication in session.scalars(
            select(RulerIdentityAdjudication).where(
                RulerIdentityAdjudication.selected_ruler_year_id.in_(stale_ruler_year_ids)
            )
        ).all():
            adjudication.selected_ruler_year_id = None
            adjudication.selected_leader_name = None
            adjudication.classification = "needs_rebuild_stale_monthly_spell_cleanup"
            adjudication.review_status = "needs_review"
            adjudication.selection_rule = "stale_monthly_spell_cleanup"
        _mark_stale_principal_ruler_facts_unresolved(session, stale_ruler_year_ids)
        for country_id, year in affected_country_years:
            for adjudication in session.scalars(
                select(RulerIdentityAdjudication).where(
                    RulerIdentityAdjudication.country_id == country_id,
                    RulerIdentityAdjudication.year == year,
                )
            ).all():
                adjudication.candidate_ruler_year_ids_json = "[]"
        for ruler_year in stale_ruler_years:
            session.delete(ruler_year)
    for spell in stale_spells:
        session.delete(spell)
    session.flush()


def _mark_stale_principal_ruler_facts_unresolved(
    session: Session,
    stale_ruler_year_ids: list[int],
) -> None:
    bind = session.get_bind()
    if not inspect(bind).has_table("country_year_facts"):
        return
    stale_message = (
        "Selected ruler-year identity evidence was superseded by REIGN monthly "
        "spell cleanup; rebuild ruler identity adjudications before using this fact."
    )
    timestamp = datetime.now(UTC)
    facts = session.scalars(
        select(CountryYearFact).where(
            CountryYearFact.field_key == "principal_ruler",
            CountryYearFact.selected_entity_table == "ruler_years",
            CountryYearFact.selected_entity_id.in_(stale_ruler_year_ids),
        )
    ).all()
    for fact in facts:
        fact.selected_value_text = None
        fact.selected_value_number = None
        fact.selected_value_json = None
        fact.selected_entity_table = None
        fact.selected_entity_id = None
        fact.selection_rule = "stale_monthly_spell_cleanup"
        fact.adjudication_status = "needs_review"
        fact.confidence_score = None
        fact.warnings_json = _append_json_string(
            fact.warnings_json,
            "stale_identity_evidence_superseded",
        )
        fact.rationale = stale_message
        fact.review_reason = stale_message
        fact.research_prompt = stale_message
        fact.recommended_next_action = "Rebuild ruler identity adjudications."
        fact.updated_at = timestamp


def _append_json_string(raw_json: str, value: str) -> str:
    try:
        values = json.loads(raw_json)
    except json.JSONDecodeError:
        values = []
    if not isinstance(values, list):
        values = []
    if value not in values:
        values.append(value)
    return json.dumps(values, sort_keys=True)


def _is_multi_month_monthly_aggregate(candidate: IdentitySpellInput) -> bool:
    return (
        candidate.observation_family == "leader_identity_month"
        and candidate.end_date is not None
        and candidate.end_date > _month_end(candidate.start_date)
    )


def _is_one_month_spell(spell: RulerSpell) -> bool:
    return (
        spell.end_date is not None
        and spell.start_date.day == 1
        and spell.end_date == _month_end(spell.start_date)
    )


def _month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def _spell_needs_update(existing: RulerSpell, candidate: IdentitySpellInput) -> bool:
    return (
        existing.is_actual_ruler != candidate.is_actual_ruler
        or existing.is_formal_leader != candidate.is_formal_leader
        or existing.rule_type != candidate.rule_type
        or existing.shared_rule_flag != candidate.shared_rule_flag
        or existing.disputed_rule_flag != candidate.disputed_rule_flag
        or existing.confidence_score != candidate.confidence_score
        or existing.notes != candidate.notes
    )


def _expand_spell_to_ruler_years(
    session: Session,
    spell: RulerSpell,
    candidate: IdentitySpellInput,
) -> tuple[int, int]:
    country_years = session.scalars(
        select(CountryYear).where(
            CountryYear.country_id == spell.country_id,
            CountryYear.included_in_project.is_(True),
            CountryYear.year >= spell.start_date.year,
            CountryYear.year <= (spell.end_date.year if spell.end_date else 2100),
        )
    ).all()
    created = 0
    updated = 0
    for country_year in country_years:
        if not _year_overlaps_spell(country_year.year, spell.start_date, spell.end_date):
            continue
        existing = session.scalar(
            select(RulerYear).where(
                RulerYear.leader_id == spell.leader_id,
                RulerYear.country_id == spell.country_id,
                RulerYear.year == country_year.year,
            )
        )
        status = _actual_ruler_status(candidate)
        if existing is None:
            session.add(
                RulerYear(
                    leader_id=spell.leader_id,
                    country_id=spell.country_id,
                    year=country_year.year,
                    ruler_spell_id=spell.id,
                    actual_ruler_status=status,
                    system_selected_leader_name=candidate.leader_name,
                    match_status="matched",
                    confidence_score=candidate.confidence_score,
                    review_status=_review_status(candidate),
                    review_note=_review_note(candidate),
                )
            )
            created += 1
            continue
        if _ruler_year_needs_update(session, existing, spell, candidate, status):
            existing.ruler_spell_id = spell.id
            existing.actual_ruler_status = status
            existing.system_selected_leader_name = candidate.leader_name
            existing.confidence_score = candidate.confidence_score
            updated += 1
    session.flush()
    return created, updated


def _refresh_ruler_year_statuses(session: Session) -> None:
    ruler_years = session.scalars(
        select(RulerYear).order_by(RulerYear.country_id, RulerYear.year)
    ).all()
    by_pair: dict[tuple[int, int], list[RulerYear]] = {}
    for ruler_year in ruler_years:
        by_pair.setdefault((ruler_year.country_id, ruler_year.year), []).append(ruler_year)
    spell_ids = {row.ruler_spell_id for row in ruler_years if row.ruler_spell_id is not None}
    spells = {
        spell.id: spell
        for spell in session.scalars(select(RulerSpell).where(RulerSpell.id.in_(spell_ids))).all()
    } if spell_ids else {}
    for rows in by_pair.values():
        _adjudicate_ruler_year_rows(rows, spells)


def _adjudicate_ruler_year_rows(
    rows: list[RulerYear],
    spells: dict[int, RulerSpell],
) -> None:
    leader_ids = {row.leader_id for row in rows}
    if len(leader_ids) == 1:
        for row in rows:
            spell = spells.get(row.ruler_spell_id) if row.ruler_spell_id else None
            row.match_status = (
                "disputed_rule" if _has_hard_manual_flag(rows, spells)
                else "resolved_auto_single_candidate"
            )
            row.confidence_score = (
                spell.confidence_score if spell is not None else row.confidence_score
            )
            row.review_status = (
                "needs_review"
                if row.match_status == "disputed_rule"
                else _review_status_from_spell(spell) if spell is not None else None
            )
            row.review_note = _join_notes(
                _review_note_from_spell(spell) if spell is not None else None,
                "selection_rule=manual_hard_conflict"
                if row.match_status == "disputed_rule"
                else "selection_rule=single_candidate",
            )
        return

    selected, rule = _select_principal_candidate(rows, spells)
    if selected is None:
        manual_status = _manual_conflict_status(rows, spells)
        for row in rows:
            spell = spells.get(row.ruler_spell_id) if row.ruler_spell_id else None
            row.match_status = manual_status
            row.review_status = "needs_review"
            row.review_note = _join_notes(
                _review_note_from_spell(spell) if spell is not None else None,
                _adjudication_note(
                    rows,
                    spells,
                    selection_rule=manual_status,
                    warning="principal ruler not auto-selected",
                ),
            )
            row.confidence_score = _penalized_confidence(
                spell.confidence_score if spell is not None else row.confidence_score,
                MANUAL_CONFLICT_PENALTY,
            )
        return

    selected_name = selected.system_selected_leader_name
    for row in rows:
        spell = spells.get(row.ruler_spell_id) if row.ruler_spell_id else None
        is_selected = row.id == selected.id
        row.match_status = rule if is_selected else "preserved_competing_candidate"
        row.review_status = "auto_resolved" if is_selected else "needs_review"
        row.system_selected_leader_name = selected_name
        row.review_note = _join_notes(
            _review_note_from_spell(spell) if spell is not None else None,
            _adjudication_note(
                rows,
                spells,
                selection_rule=rule,
                warning="competing candidates preserved; confidence penalized",
                selected_leader_id=selected.leader_id,
            ),
        )
        row.confidence_score = _penalized_confidence(
            spell.confidence_score if spell is not None else row.confidence_score,
            AUTO_ADJUDICATION_PENALTY,
        )


def _select_principal_candidate(
    rows: list[RulerYear],
    spells: dict[int, RulerSpell],
) -> tuple[RulerYear | None, str]:
    if _has_hard_manual_flag(rows, spells):
        return None, ""
    actual_rows = [row for row in rows if _spell_for_row(row, spells).is_actual_ruler]
    formal_only_rows = [
        row
        for row in rows
        if _spell_for_row(row, spells).is_formal_leader
        and not _spell_for_row(row, spells).is_actual_ruler
    ]
    actual_leaders = {row.leader_id for row in actual_rows}
    if len(actual_leaders) == 1 and formal_only_rows:
        return _best_row_for_leader(actual_rows, spells), "resolved_auto_role_priority"

    duration_winner = _duration_majority_winner(rows, spells)
    if duration_winner is not None:
        return duration_winner, "resolved_auto_duration_majority"
    return None, ""


def _has_hard_manual_flag(rows: list[RulerYear], spells: dict[int, RulerSpell]) -> bool:
    if len({row.leader_id for row in rows}) >= 3:
        return True
    for row in rows:
        spell = _spell_for_row(row, spells)
        text = " ".join(
            str(value or "")
            for value in (spell.rule_type, spell.office_title, spell.notes, row.review_note)
        ).casefold()
        text = text.replace("-", " ").replace("_", " ")
        if spell.disputed_rule_flag or any(
            token in text
            for token in ("coup", "contested", "de facto", "disputed", "junta", "shared")
        ):
            return True
    return False


def _manual_conflict_status(rows: list[RulerYear], spells: dict[int, RulerSpell]) -> str:
    source_slugs = {_spell_for_row(row, spells).source_dataset for row in rows}
    leader_ids = {row.leader_id for row in rows}
    if len(source_slugs) > 1 and len(leader_ids) > 1:
        return "source_conflict_manual_review"
    return "multiple_candidates_manual_review"


def _duration_majority_winner(
    rows: list[RulerYear],
    spells: dict[int, RulerSpell],
) -> RulerYear | None:
    if len({row.leader_id for row in rows}) != 2:
        return None
    by_leader: dict[int, int] = {}
    representative: dict[int, RulerYear] = {}
    year = rows[0].year
    for row in rows:
        days = _days_in_year(_spell_for_row(row, spells), year)
        by_leader[row.leader_id] = max(by_leader.get(row.leader_id, 0), days)
        representative.setdefault(row.leader_id, row)
    ordered = sorted(by_leader.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) != 2 or ordered[0][1] <= YEAR_MAJORITY_DAYS or ordered[0][1] == ordered[1][1]:
        return None
    return representative[ordered[0][0]]


def _best_row_for_leader(rows: list[RulerYear], spells: dict[int, RulerSpell]) -> RulerYear:
    return max(
        rows,
        key=lambda row: (
            row.confidence_score or 0,
            _days_in_year(_spell_for_row(row, spells), row.year),
            -row.id,
        ),
    )


def _spell_for_row(row: RulerYear, spells: dict[int, RulerSpell]) -> RulerSpell:
    if row.ruler_spell_id is None or row.ruler_spell_id not in spells:
        raise ValueError("ruler_year is missing its ruler_spell evidence")
    return spells[row.ruler_spell_id]


def _days_in_year(spell: RulerSpell, year: int) -> int:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    start = max(spell.start_date, year_start)
    end = min(spell.end_date or year_end, year_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _adjudication_note(
    rows: list[RulerYear],
    spells: dict[int, RulerSpell],
    *,
    selection_rule: str,
    warning: str,
    selected_leader_id: int | None = None,
) -> str:
    parts = [
        f"selection_rule={selection_rule}",
        f"warning={warning}",
        "confidence_penalty_applied",
    ]
    if selected_leader_id is not None:
        parts.append(f"selected_leader_id={selected_leader_id}")
    observations = []
    for row in sorted(rows, key=lambda item: (item.leader_id, item.id)):
        spell = _spell_for_row(row, spells)
        observations.append(
            f"leader_id={row.leader_id},name={row.system_selected_leader_name},"
            f"source={spell.source_dataset},office={spell.office_title or 'n/a'},"
            f"actual={spell.is_actual_ruler},formal={spell.is_formal_leader},"
            f"days={_days_in_year(spell, row.year)}"
        )
    parts.append("competing_candidates=[" + " | ".join(observations) + "]")
    return "; ".join(parts)


def _penalized_confidence(value: int | None, penalty: int) -> int | None:
    if value is None:
        return None
    return max(0, value - penalty)


def _covered_country_year_pairs(session: Session, *, year: int | None) -> set[tuple[int, int]]:
    statement = _evidence_ruler_year_statement().with_only_columns(
        RulerYear.country_id,
        RulerYear.year,
    )
    if year is not None:
        statement = statement.where(RulerYear.year == year)
    return set(session.execute(statement.distinct()).all())


def _count_distinct_ruler_year_pairs(session: Session, *clauses: Any, year: int | None) -> int:
    statement = select(func.count()).select_from(
        _evidence_ruler_year_statement()
        .with_only_columns(RulerYear.country_id, RulerYear.year)
        .where(*clauses, *(_ruler_year_filter(year)))
        .distinct()
        .subquery()
    )
    return session.scalar(statement) or 0


def _count_multiple_ruler_pairs(session: Session, *, year: int | None) -> int:
    statement = (
        _evidence_ruler_year_statement()
        .with_only_columns(RulerYear.country_id, RulerYear.year)
        .where(*_ruler_year_filter(year))
        .group_by(RulerYear.country_id, RulerYear.year)
        .having(func.count(func.distinct(RulerYear.leader_id)) > 1)
    )
    return len(session.execute(statement).all())


def _count_source_conflict_pairs(session: Session, *, year: int | None) -> int:
    statement = (
        select(RulerYear.country_id, RulerYear.year)
        .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
        .where(RulerSpell.source_dataset.not_in(NON_EVIDENCE_SOURCE_DATASETS))
        .where(*_ruler_year_filter(year))
        .group_by(RulerYear.country_id, RulerYear.year)
        .having(func.count(func.distinct(RulerSpell.source_dataset)) > 1)
        .having(func.count(func.distinct(RulerYear.leader_id)) > 1)
    )
    return len(session.execute(statement).all())


def _evidence_ruler_year_statement() -> Select[tuple[RulerYear]]:
    return (
        select(RulerYear)
        .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
        .join(
            CountryYear,
            (CountryYear.country_id == RulerYear.country_id)
            & (CountryYear.year == RulerYear.year),
        )
        .where(
            RulerSpell.source_dataset.not_in(NON_EVIDENCE_SOURCE_DATASETS),
            CountryYear.included_in_project.is_(True),
        )
    )


def _country_year_filter(year: int | None) -> tuple[Any, ...]:
    clauses: list[Any] = [CountryYear.included_in_project.is_(True)]
    if year is not None:
        clauses.append(CountryYear.year == year)
    return tuple(clauses)


def _ruler_year_filter(year: int | None) -> tuple[Any, ...]:
    return (RulerYear.year == year,) if year is not None else ()


def _country_by_iso3(session: Session) -> dict[str, Country]:
    return {country.iso3: country for country in session.scalars(select(Country)).all()}


def _country_by_normalized_name(session: Session) -> dict[str, Country]:
    return {
        country.country_name_normalized: country
        for country in session.scalars(select(Country)).all()
    }


def _leader_by_normalized_name(session: Session) -> dict[str, Leader]:
    return {leader.normalized_name: leader for leader in session.scalars(select(Leader)).all()}


def _loads_json(value: str) -> dict[str, Any]:
    payload = json.loads(value or "{}")
    return payload if isinstance(payload, dict) else {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 4 and text.isdigit():
        return date(int(text), 1, 1)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _int_value(*values: Any) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(float(str(value)))
        except ValueError:
            continue
    return None


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _confidence(row: NormalizedObservationRow, extension: dict[str, Any]) -> int | None:
    value = _int_value(extension.get("confidence_score"), extension.get("confidence"))
    if value is None:
        return None
    return max(0, min(100, value))


def _default_actual_status(indicator_code: str) -> bool:
    return indicator_code != "wikidata_head_of_state_held"


def _default_formal_status(indicator_code: str) -> bool:
    return indicator_code in {
        "wikidata_head_of_state_held",
        "wikidata_head_of_government_held",
    }


def _notes(row: NormalizedObservationRow, extension: dict[str, Any]) -> str:
    row_reference = _first_text(extension.get("source_row_reference"), row.observation_id)
    source_id_note = _leader_source_id_note(row, extension)
    citation_note = _citation_note(extension)
    return (
        f"I4 imported from normalized_observations:{row.id}; "
        f"source_row_reference={row_reference}{source_id_note}{citation_note}"
    )


def _citation_note(extension: dict[str, Any]) -> str:
    citation_fields = {
        "source_url": extension.get("source_url"),
        "source_urls": extension.get("source_urls"),
        "url": extension.get("url"),
        "quote": extension.get("quote"),
        "source_quote": extension.get("source_quote"),
        "source_quotes": extension.get("source_quotes"),
        "citations": extension.get("citations"),
    }
    payload = {key: value for key, value in citation_fields.items() if value}
    if not payload:
        return ""
    return f"; citations={json.dumps(payload, sort_keys=True, separators=(',', ':'))}"


def _leader_source_id_note(
    row: NormalizedObservationRow,
    extension: dict[str, Any],
) -> str:
    values = {
        "row_leader_id": row.leader_id,
        "person_qid": extension.get("person_qid"),
        "archigos_obsid": extension.get("archigos_obsid"),
    }
    parts = [f"{key}={value}" for key, value in values.items() if _first_text(value)]
    return f"; leader_source_ids={'|'.join(parts)}" if parts else ""


def _year_overlaps_spell(year: int, start: date, end: date | None) -> bool:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    return start <= year_end and (end is None or end >= year_start)


def _actual_ruler_status(candidate: IdentitySpellInput) -> str:
    if candidate.is_actual_ruler and candidate.is_formal_leader:
        return "actual_and_formal"
    if candidate.is_actual_ruler:
        return "actual"
    if candidate.is_formal_leader:
        return "formal_only"
    return "unknown"


def _review_status(candidate: IdentitySpellInput) -> str | None:
    if candidate.disputed_rule_flag or candidate.shared_rule_flag:
        return "needs_review"
    if (
        candidate.confidence_score is not None
        and candidate.confidence_score < DEFAULT_LOW_CONFIDENCE_THRESHOLD
    ):
        return "needs_review"
    return None


def _review_status_from_spell(spell: RulerSpell) -> str | None:
    if spell.disputed_rule_flag or spell.shared_rule_flag:
        return "needs_review"
    if (
        spell.confidence_score is not None
        and spell.confidence_score < DEFAULT_LOW_CONFIDENCE_THRESHOLD
    ):
        return "needs_review"
    return None


def _review_note(candidate: IdentitySpellInput) -> str | None:
    notes: list[str] = []
    if candidate.disputed_rule_flag:
        notes.append("disputed rule flag from identity source")
    if candidate.shared_rule_flag:
        notes.append("shared rule flag from identity source")
    if (
        candidate.confidence_score is not None
        and candidate.confidence_score < DEFAULT_LOW_CONFIDENCE_THRESHOLD
    ):
        notes.append("low confidence identity match")
    return "; ".join(notes) or None


def _review_note_from_spell(spell: RulerSpell) -> str | None:
    notes: list[str] = []
    if spell.disputed_rule_flag:
        notes.append("disputed rule flag from identity source")
    if spell.shared_rule_flag:
        notes.append("shared rule flag from identity source")
    if (
        spell.confidence_score is not None
        and spell.confidence_score < DEFAULT_LOW_CONFIDENCE_THRESHOLD
    ):
        notes.append("low confidence identity match")
    return "; ".join(notes) or None


def _ruler_year_needs_update(
    session: Session,
    existing: RulerYear,
    spell: RulerSpell,
    candidate: IdentitySpellInput,
    status: str,
) -> bool:
    spell_pointer_needs_update = _ruler_year_spell_pointer_needs_update(session, existing, spell)
    if existing.ruler_spell_id != spell.id and not spell_pointer_needs_update:
        return False
    expected_confidence = _expected_existing_confidence(existing, candidate)
    return (
        spell_pointer_needs_update
        or existing.actual_ruler_status != status
        or _ruler_year_name_needs_update(existing, candidate)
        or existing.confidence_score != expected_confidence
    )


def _ruler_year_name_needs_update(existing: RulerYear, candidate: IdentitySpellInput) -> bool:
    if existing.review_note and "selection_rule=" in existing.review_note:
        return False
    return existing.system_selected_leader_name != candidate.leader_name


def _ruler_year_spell_pointer_needs_update(
    session: Session,
    existing: RulerYear,
    spell: RulerSpell,
) -> bool:
    if existing.ruler_spell_id == spell.id:
        return False
    if existing.ruler_spell_id is None:
        return True
    current_spell = session.get(RulerSpell, existing.ruler_spell_id)
    if current_spell is None:
        return True
    return not (
        current_spell.leader_id == spell.leader_id
        and current_spell.country_id == spell.country_id
        and _year_overlaps_spell(existing.year, current_spell.start_date, current_spell.end_date)
    )


def _expected_existing_confidence(
    existing: RulerYear,
    candidate: IdentitySpellInput,
) -> int | None:
    if not existing.review_note or "confidence_penalty_applied" not in existing.review_note:
        return candidate.confidence_score
    if existing.match_status in {
        "source_conflict_manual_review",
        "multiple_candidates_manual_review",
    }:
        return _penalized_confidence(candidate.confidence_score, MANUAL_CONFLICT_PENALTY)
    return _penalized_confidence(candidate.confidence_score, AUTO_ADJUDICATION_PENALTY)


def _join_notes(existing: str | None, new_note: str) -> str:
    if not existing:
        return new_note
    if new_note in existing:
        return existing
    return f"{existing}; {new_note}"


__all__ = [
    "IDENTITY_FAMILIES",
    "IDENTITY_TABLES",
    "RulerIdentityBuildResult",
    "RulerIdentityCoverageReport",
    "assert_identity_database_ready",
    "build_ruler_identity",
    "build_ruler_identity_coverage_report",
    "ruler_identity_coverage_to_json",
]
