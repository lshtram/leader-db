"""Deterministic country/year grid builder for research scope.

The base universe preserves the current ISO 3166-1 alpha-3 seed where valid and
layers a packaged year-level lifecycle seed over it. Rows outside a code's known
lifecycle are retained as audit-only rows so coverage denominators count only
country-years where the state exists while still exposing exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from sqlalchemy import Select, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..db.models import Country, CountryYear
from ..db.readiness import DatabaseReadinessError, assert_database_ready
from ..normalize.countries import normalize_country_name, normalize_iso3
from ._country_lifecycle_seed import COUNTRY_LIFECYCLE_SEED, CountryLifecycleRecord
from ._country_scope_seed import COUNTRY_SCOPE_SEED, CountryScopeRecord
from ._country_seed import ISO3_COUNTRY_SEED

SCOPE_TABLES: tuple[str, ...] = ("countries", "country_years")
DEFAULT_INCLUSION_REASON = (
    "included by D1/D2 lifecycle-aware country-year scope; packaged lifecycle seed "
    "and conservative non-sovereign/special-entry exclusions applied where known; "
    "population and disputed-country rules are not yet modeled"
)
LIFECYCLE_EXCLUSION_REASON = (
    "excluded by D1/D2 lifecycle-aware country-year scope because year is outside "
    "the packaged lifecycle interval for this country code"
)
LIMITATIONS: tuple[str, ...] = (
    "Country universe starts from current ISO 3166-1 alpha-3 entries and a packaged seed; "
    "pycountry is used when installed, otherwise the packaged I3 seed is used.",
    "A packaged year-level lifecycle seed is applied for post-1950 independence, "
    "state-successor, and selected ceased-state cases; it is not a complete global "
    "historical-state ontology and does not model month/day recognition changes.",
    "Population-threshold, sovereignty, recognition, successor-subperiod, and disputed-territory "
    "rules are not globally complete yet; only clear non-sovereign/special ISO entries "
    "in the packaged scope seed are excluded from the ruler-scoring denominator.",
)


@dataclass(frozen=True)
class CountryDefinition:
    """Canonical country row candidate for the I3 grid builder."""

    iso3: str
    country_name: str
    country_name_normalized: str
    valid_from_year: int = 1900
    valid_to_year: int | None = None
    entity_type: str = "current_iso3"
    predecessor_codes: tuple[str, ...] = ()
    successor_codes: tuple[str, ...] = ()
    notes: str | None = None
    included_in_project: bool = True
    scope_exclusion_reason: str | None = None

    def is_valid_in_year(self, year: int) -> bool:
        """Return whether this country definition should be in scope for ``year``."""

        if year < self.valid_from_year:
            return False
        return self.valid_to_year is None or year <= self.valid_to_year


@dataclass(frozen=True)
class CountryYearGridBuildResult:
    """Summary of an idempotent country/year grid build."""

    start_year: int
    end_year: int
    countries_total: int
    countries_created: int
    countries_updated: int
    country_years_total: int
    country_years_created: int
    country_years_updated: int


@dataclass(frozen=True)
class CountryYearCoverageReport:
    """Coverage summary for populated country/year scope rows."""

    total_countries: int
    total_country_years: int
    min_year: int | None
    max_year: int | None
    included_country_years: int
    excluded_country_years: int
    country_years_without_inclusion_reason: int
    limitations: tuple[str, ...]


def load_country_universe() -> tuple[CountryDefinition, ...]:
    """Load the deterministic current ISO3 country universe for I3.

    ``pycountry`` is optional. The bundled seed keeps tests and CLI builds
    functional in environments where dependencies have not been reinstalled.
    """

    try:
        pycountry = import_module("pycountry")
    except ModuleNotFoundError:
        return _seed_country_universe()

    countries: list[CountryDefinition] = []
    for raw_country in pycountry.countries:
        record: Any = raw_country
        iso3 = normalize_iso3(record.alpha_3)
        country_name = str(getattr(record, "common_name", record.name)).strip()
        countries.append(
            CountryDefinition(
                iso3=iso3,
                country_name=country_name,
                country_name_normalized=normalize_country_name(country_name),
            )
        )
    return _apply_lifecycle_seed(tuple(countries))


def load_pycountry_universe() -> tuple[CountryDefinition, ...]:
    """Backward-compatible alias for the I3 current ISO3 universe loader."""

    return load_country_universe()


def build_country_year_grid(
    engine: Engine,
    *,
    start_year: int,
    end_year: int,
    countries: tuple[CountryDefinition, ...] | None = None,
) -> CountryYearGridBuildResult:
    """Populate ``countries`` and ``country_years`` for the requested range."""

    _validate_year_range(start_year, end_year)
    assert_scope_database_ready(engine)
    country_universe = countries or load_country_universe()
    years = tuple(range(start_year, end_year + 1))

    with Session(engine, expire_on_commit=False) as session:
        existing_by_iso3 = {
            country.iso3: country
            for country in session.scalars(select(Country).order_by(Country.iso3)).all()
        }
        countries_created = 0
        countries_updated = 0
        for definition in country_universe:
            existing = existing_by_iso3.get(definition.iso3)
            if existing is None:
                existing = Country(
                    iso3=definition.iso3,
                    country_name=definition.country_name,
                    country_name_normalized=definition.country_name_normalized,
                    notes=definition.notes,
                )
                session.add(existing)
                existing_by_iso3[definition.iso3] = existing
                countries_created += 1
                continue
            if _country_needs_update(existing, definition):
                existing.country_name = definition.country_name
                existing.country_name_normalized = definition.country_name_normalized
                if definition.notes is not None:
                    existing.notes = definition.notes
                countries_updated += 1

        session.flush()
        country_years_created = 0
        country_years_updated = 0
        country_ids = [existing_by_iso3[definition.iso3].id for definition in country_universe]
        existing_pairs = _existing_country_year_pairs(session, country_ids, years)

        for definition in country_universe:
            country = existing_by_iso3[definition.iso3]
            for year in years:
                key = (country.id, year)
                existing_country_year = existing_pairs.get(key)
                created, updated = _upsert_country_year(
                    session,
                    country_id=country.id,
                    year=year,
                    definition=definition,
                    existing_country_year=existing_country_year,
                )
                country_years_created += created
                country_years_updated += updated

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise

    return CountryYearGridBuildResult(
        start_year=start_year,
        end_year=end_year,
        countries_total=len(country_universe),
        countries_created=countries_created,
        countries_updated=countries_updated,
        country_years_total=len(country_universe) * len(years),
        country_years_created=country_years_created,
        country_years_updated=country_years_updated,
    )


def build_country_year_coverage_report(engine: Engine) -> CountryYearCoverageReport:
    """Return aggregate coverage for ``countries`` and ``country_years``."""

    assert_scope_database_ready(engine)
    with Session(engine) as session:
        total_countries = session.scalar(select(func.count(Country.id))) or 0
        total_country_years = session.scalar(select(func.count(CountryYear.id))) or 0
        min_year = session.scalar(select(func.min(CountryYear.year)))
        max_year = session.scalar(select(func.max(CountryYear.year)))
        included = _count_country_years(session, CountryYear.included_in_project.is_(True))
        excluded = _count_country_years(session, CountryYear.included_in_project.is_(False))
        missing_reason = _count_country_years(session, CountryYear.inclusion_reason.is_(None))

    return CountryYearCoverageReport(
        total_countries=total_countries,
        total_country_years=total_country_years,
        min_year=min_year,
        max_year=max_year,
        included_country_years=included,
        excluded_country_years=excluded,
        country_years_without_inclusion_reason=missing_reason,
        limitations=LIMITATIONS,
    )


def coverage_report_to_json(report: CountryYearCoverageReport) -> dict[str, object]:
    """Return a JSON-serializable country/year coverage payload."""

    return {
        "total_countries": report.total_countries,
        "total_country_years": report.total_country_years,
        "min_year": report.min_year,
        "max_year": report.max_year,
        "included_country_years": report.included_country_years,
        "excluded_country_years": report.excluded_country_years,
        "country_years_without_inclusion_reason": report.country_years_without_inclusion_reason,
        "limitations": list(report.limitations),
    }


def _validate_year_range(start_year: int, end_year: int) -> None:
    if start_year < 1900 or end_year > 2100:
        raise ValueError("country-year grid range must be within 1900-2100")
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")


def _seed_country_universe() -> tuple[CountryDefinition, ...]:
    countries = tuple(
        CountryDefinition(
            iso3=normalize_iso3(iso3),
            country_name=country_name,
            country_name_normalized=normalize_country_name(country_name),
        )
        for iso3, country_name in ISO3_COUNTRY_SEED
    )
    return _apply_lifecycle_seed(countries)


def _apply_lifecycle_seed(
    countries: tuple[CountryDefinition, ...],
) -> tuple[CountryDefinition, ...]:
    by_iso3 = {country.iso3: country for country in countries}
    for record in COUNTRY_LIFECYCLE_SEED:
        definition = _definition_from_lifecycle_record(record)
        existing = by_iso3.get(definition.iso3)
        if existing is not None:
            definition = CountryDefinition(
                iso3=definition.iso3,
                country_name=existing.country_name,
                country_name_normalized=existing.country_name_normalized,
                valid_from_year=definition.valid_from_year,
                valid_to_year=definition.valid_to_year,
                entity_type=definition.entity_type,
                predecessor_codes=definition.predecessor_codes,
                successor_codes=definition.successor_codes,
                notes=definition.notes,
            )
        by_iso3[definition.iso3] = definition
    return _apply_scope_seed(tuple(sorted(by_iso3.values(), key=lambda country: country.iso3)))


def _apply_scope_seed(
    countries: tuple[CountryDefinition, ...],
) -> tuple[CountryDefinition, ...]:
    scope_by_iso3 = {record.code: record for record in COUNTRY_SCOPE_SEED}
    scoped: list[CountryDefinition] = []
    for country in countries:
        scope = scope_by_iso3.get(country.iso3)
        if scope is None:
            scoped.append(country)
            continue
        scoped.append(_merge_scope_record(country, scope))
    return tuple(scoped)


def _definition_from_lifecycle_record(record: CountryLifecycleRecord) -> CountryDefinition:
    return CountryDefinition(
        iso3=normalize_iso3(record.code),
        country_name=record.name,
        country_name_normalized=normalize_country_name(record.name),
        valid_from_year=record.valid_from_year,
        valid_to_year=record.valid_to_year,
        entity_type=record.entity_type,
        predecessor_codes=record.predecessor_codes,
        successor_codes=record.successor_codes,
        notes=record.notes,
    )


def _merge_scope_record(
    current: CountryDefinition,
    record: CountryScopeRecord,
) -> CountryDefinition:
    notes = (
        f"{current.notes} Scope policy: {record.reason}"
        if current.notes
        else f"Scope policy: {record.reason}"
    )
    return CountryDefinition(
        iso3=current.iso3,
        country_name=current.country_name,
        country_name_normalized=current.country_name_normalized,
        valid_from_year=current.valid_from_year,
        valid_to_year=current.valid_to_year,
        entity_type=current.entity_type,
        predecessor_codes=current.predecessor_codes,
        successor_codes=current.successor_codes,
        notes=notes,
        included_in_project=record.included_in_project,
        scope_exclusion_reason=record.reason,
    )


def _country_needs_update(country: Country, definition: CountryDefinition) -> bool:
    return (
        country.country_name != definition.country_name
        or country.country_name_normalized != definition.country_name_normalized
        or (definition.notes is not None and country.notes != definition.notes)
    )


def _country_year_needs_update(country_year: CountryYear, definition: CountryDefinition) -> bool:
    return (
        country_year.included_in_project != definition.included_in_project
        or country_year.inclusion_reason != _lifecycle_inclusion_reason(definition)
    )


def _country_year_needs_exclusion(country_year: CountryYear) -> bool:
    return (
        country_year.included_in_project is not False
        or country_year.inclusion_reason is None
        or not country_year.inclusion_reason.startswith(LIFECYCLE_EXCLUSION_REASON)
    )


def _upsert_country_year(
    session: Session,
    *,
    country_id: int,
    year: int,
    definition: CountryDefinition,
    existing_country_year: CountryYear | None,
) -> tuple[int, int]:
    if not definition.is_valid_in_year(year):
        return _upsert_out_of_lifecycle_country_year(
            session,
            country_id=country_id,
            year=year,
            definition=definition,
            existing_country_year=existing_country_year,
        )
    if existing_country_year is None:
        session.add(
            CountryYear(
                country_id=country_id,
                year=year,
                included_in_project=definition.included_in_project,
                inclusion_reason=_lifecycle_inclusion_reason(definition),
            )
        )
        return (1, 0)
    if _country_year_needs_update(existing_country_year, definition):
        existing_country_year.included_in_project = definition.included_in_project
        existing_country_year.inclusion_reason = _lifecycle_inclusion_reason(definition)
        return (0, 1)
    return (0, 0)


def _upsert_out_of_lifecycle_country_year(
    session: Session,
    *,
    country_id: int,
    year: int,
    definition: CountryDefinition,
    existing_country_year: CountryYear | None,
) -> tuple[int, int]:
    reason = _lifecycle_exclusion_reason(definition)
    if existing_country_year is None:
        session.add(
            CountryYear(
                country_id=country_id,
                year=year,
                included_in_project=False,
                inclusion_reason=reason,
            )
        )
        return (1, 0)
    if _country_year_needs_exclusion(existing_country_year):
        existing_country_year.included_in_project = False
        existing_country_year.inclusion_reason = reason
        return (0, 1)
    return (0, 0)


def _lifecycle_inclusion_reason(definition: CountryDefinition) -> str:
    if not definition.included_in_project and definition.scope_exclusion_reason:
        return definition.scope_exclusion_reason
    if _has_explicit_lifecycle(definition):
        end_year = definition.valid_to_year if definition.valid_to_year is not None else "present"
        return (
            f"{DEFAULT_INCLUSION_REASON}; lifecycle={definition.valid_from_year}-{end_year}; "
            f"entity_type={definition.entity_type}"
        )
    return DEFAULT_INCLUSION_REASON


def _lifecycle_exclusion_reason(definition: CountryDefinition) -> str:
    end_year = definition.valid_to_year if definition.valid_to_year is not None else "present"
    return (
        f"{LIFECYCLE_EXCLUSION_REASON}; lifecycle={definition.valid_from_year}-{end_year}; "
        f"entity_type={definition.entity_type}"
    )


def _has_explicit_lifecycle(definition: CountryDefinition) -> bool:
    return definition.entity_type != "current_iso3" or definition.valid_from_year != 1900


def _existing_country_year_pairs(
    session: Session,
    country_ids: list[int],
    years: tuple[int, ...],
) -> dict[tuple[int, int], CountryYear]:
    if not country_ids or not years:
        return {}
    rows = session.scalars(
        select(CountryYear).where(
            CountryYear.country_id.in_(country_ids),
            CountryYear.year.in_(years),
        )
    ).all()
    return {(row.country_id, row.year): row for row in rows}


def _count_country_years(session: Session, where_clause: Any) -> int:
    statement: Select[tuple[int]] = select(func.count(CountryYear.id)).where(where_clause)
    return session.scalar(statement) or 0


def assert_scope_database_ready(engine: Engine) -> None:
    """Ensure country scope tables are present, including friendly empty DB failures."""

    message = (
        "The local scope database is not initialized. Run `leaders-db init-db` "
        "or pass `--db-url`."
    )
    try:
        inspect(engine).get_table_names()
    except SQLAlchemyError as exc:
        raise DatabaseReadinessError(message) from exc
    try:
        assert_database_ready(engine, required_tables=SCOPE_TABLES)
    except DatabaseReadinessError as exc:
        missing = ", ".join(SCOPE_TABLES)
        raise DatabaseReadinessError(f"{message} Missing table(s): {missing}.") from exc


__all__ = [
    "CountryDefinition",
    "CountryYearCoverageReport",
    "CountryYearGridBuildResult",
    "build_country_year_coverage_report",
    "build_country_year_grid",
    "coverage_report_to_json",
    "load_country_universe",
    "load_pycountry_universe",
]
