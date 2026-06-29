"""Question 2.1 state-based armed-conflict helper.

This module is intentionally pure: callers provide country scope, persisted
evidence access, and optional ruler resolution. It does not read raw UCDP files,
perform network access, or write artifacts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from leaders_db.chronicle.country_scope import CountryScopeEntry
from leaders_db.chronicle.ruler_resolver import RulerResolver, RulerResult
from leaders_db.sources.contracts import EvidenceQuery, NormalizedObservation, SourceId
from leaders_db.sources.query import EvidenceRepository

QUESTION_ID = "2.1"
UCDP_SOURCE_ID = SourceId(slug="ucdp")
OBSERVATION_FAMILY = "international_peace_country_year"
STATE_BASED_EVENTS = "ucdp_state_based_events"
STATE_BASED_FATALITIES = "ucdp_state_based_fatalities"
MISSING_UCDP_WARNING = "missing_ucdp_state_based_evidence"
INCOMPLETE_UCDP_WARNING = "incomplete_ucdp_state_based_evidence"
MISSING_RULER_WARNING = "missing_ruler"
PROXY_YEAR_WARNING = "proxy_ucdp_state_based_evidence_year"

CoverageStatus = Literal["direct", "proxy", "missing"]
RulerLookup = Callable[[str, int], RulerResult | Mapping[str, Any] | None]


class _RulerResolverLike(Protocol):
    def resolve(self, iso3: str, year: int) -> RulerResult: ...


@dataclass(frozen=True)
class Question21AnswerRow:
    """One country-year answer row for methodology Question 2.1."""

    question_id: str
    year: int
    iso3: str
    country_name: str
    ruler_name: str | None
    ruler_source: str | None
    answer: bool | None
    state_based_events: float | None
    state_based_fatalities: float | None
    evidence_year: int | None
    coverage_status: CoverageStatus
    source_observation_ids: tuple[str, ...]
    warning_codes: tuple[str, ...]
    caveats: tuple[str, ...]


def build_q2_1_state_based_conflict_answers(
    *,
    year: int,
    country_scope: Mapping[str, CountryScopeEntry | Mapping[str, Any]],
    evidence_repository: EvidenceRepository,
    ruler_resolver: RulerResolver | _RulerResolverLike | RulerLookup | None = None,
    proxy_year: int | None = None,
) -> tuple[Question21AnswerRow, ...]:
    """Build all-country Q2.1 state-based conflict rows for ``year``.

    Direct observations for ``year`` are always queried and preferred. Proxy
    evidence is only queried/used when ``proxy_year`` is explicit and a country
    has no direct-year UCDP state-based observations.
    """

    entries = tuple(
        _ScopeEntry(iso3=iso3, country_name=_country_name(entry))
        for iso3, entry in sorted(country_scope.items())
        if _is_in_scope(entry, year)
    )
    countries = tuple(entry.iso3 for entry in entries)

    direct_by_country = _query_ucdp_by_country(
        evidence_repository=evidence_repository,
        year=year,
        countries=countries,
    )
    proxy_by_country: Mapping[str, tuple[NormalizedObservation, ...]] = {}
    if proxy_year is not None:
        proxy_by_country = _query_ucdp_by_country(
            evidence_repository=evidence_repository,
            year=proxy_year,
            countries=countries,
        )

    return tuple(
        _build_row(
            requested_year=year,
            entry=entry,
            direct_observations=direct_by_country.get(entry.iso3, ()),
            proxy_observations=proxy_by_country.get(entry.iso3, ()),
            proxy_year=proxy_year,
            ruler_resolver=ruler_resolver,
        )
        for entry in entries
    )


@dataclass(frozen=True)
class _ScopeEntry:
    iso3: str
    country_name: str


@dataclass(frozen=True)
class _EvidenceDecision:
    answer: bool | None
    events: float | None
    fatalities: float | None
    evidence_year: int | None
    coverage_status: CoverageStatus
    source_observation_ids: tuple[str, ...]
    warning_codes: tuple[str, ...]
    caveats: tuple[str, ...]


def _query_ucdp_by_country(
    *,
    evidence_repository: EvidenceRepository,
    year: int,
    countries: tuple[str, ...],
) -> dict[str, tuple[NormalizedObservation, ...]]:
    observations = evidence_repository.query_observations(
        EvidenceQuery(
            source_ids=(UCDP_SOURCE_ID,),
            observation_families=(OBSERVATION_FAMILY,),
            indicator_codes=(STATE_BASED_EVENTS, STATE_BASED_FATALITIES),
            years=(year,),
            countries=countries,
        )
    )
    by_country: dict[str, tuple[NormalizedObservation, ...]] = {}
    for observation in observations:
        if observation.country_code is None:
            continue
        by_country[observation.country_code] = (
            *by_country.get(observation.country_code, ()),
            observation,
        )
    return by_country


def _build_row(
    *,
    requested_year: int,
    entry: _ScopeEntry,
    direct_observations: Sequence[NormalizedObservation],
    proxy_observations: Sequence[NormalizedObservation],
    proxy_year: int | None,
    ruler_resolver: RulerResolver | _RulerResolverLike | RulerLookup | None,
) -> Question21AnswerRow:
    decision = _decide_evidence(
        requested_year=requested_year,
        direct_observations=tuple(direct_observations),
        proxy_observations=tuple(proxy_observations),
        proxy_year=proxy_year,
    )
    ruler_name, ruler_source, ruler_warning = _resolve_ruler(
        ruler_resolver=ruler_resolver,
        iso3=entry.iso3,
        year=requested_year,
    )
    warnings = decision.warning_codes
    caveats = decision.caveats
    if ruler_warning is not None:
        warnings = (*warnings, ruler_warning)
        caveats = (*caveats, "No ruler name was resolved by the injected resolver.")

    return Question21AnswerRow(
        question_id=QUESTION_ID,
        year=requested_year,
        iso3=entry.iso3,
        country_name=entry.country_name,
        ruler_name=ruler_name,
        ruler_source=ruler_source,
        answer=decision.answer,
        state_based_events=decision.events,
        state_based_fatalities=decision.fatalities,
        evidence_year=decision.evidence_year,
        coverage_status=decision.coverage_status,
        source_observation_ids=decision.source_observation_ids,
        warning_codes=warnings,
        caveats=caveats,
    )


def _decide_evidence(
    *,
    requested_year: int,
    direct_observations: tuple[NormalizedObservation, ...],
    proxy_observations: tuple[NormalizedObservation, ...],
    proxy_year: int | None,
) -> _EvidenceDecision:
    if direct_observations:
        return _decision_from_observations(
            observations=direct_observations,
            evidence_year=requested_year,
            coverage_status="direct",
            extra_warning_codes=(),
            extra_caveats=(),
        )
    if proxy_year is not None and proxy_observations:
        return _decision_from_observations(
            observations=proxy_observations,
            evidence_year=proxy_year,
            coverage_status="proxy",
            extra_warning_codes=(PROXY_YEAR_WARNING,),
            extra_caveats=(
                f"UCDP state-based conflict evidence is from proxy year {proxy_year}, "
                f"not requested year {requested_year}.",
            ),
        )
    return _missing_decision(
        evidence_year=None,
        source_observation_ids=(),
        extra_caveats=(
            f"No UCDP state-based event/fatality observations were available for {requested_year}.",
        ),
    )


def _decision_from_observations(
    *,
    observations: tuple[NormalizedObservation, ...],
    evidence_year: int,
    coverage_status: CoverageStatus,
    extra_warning_codes: tuple[str, ...],
    extra_caveats: tuple[str, ...],
) -> _EvidenceDecision:
    events = _indicator_value(observations, STATE_BASED_EVENTS)
    fatalities = _indicator_value(observations, STATE_BASED_FATALITIES)
    ids = tuple(observation.observation_id for observation in observations)
    if (events is not None and events > 0) or (fatalities is not None and fatalities > 0):
        return _EvidenceDecision(
            answer=True,
            events=events,
            fatalities=fatalities,
            evidence_year=evidence_year,
            coverage_status=coverage_status,
            source_observation_ids=ids,
            warning_codes=extra_warning_codes,
            caveats=extra_caveats,
        )
    if events is not None and fatalities is not None and events <= 0 and fatalities <= 0:
        return _EvidenceDecision(
            answer=False,
            events=events,
            fatalities=fatalities,
            evidence_year=evidence_year,
            coverage_status=coverage_status,
            source_observation_ids=ids,
            warning_codes=extra_warning_codes,
            caveats=extra_caveats,
        )
    return _missing_decision(
        evidence_year=evidence_year,
        events=events,
        fatalities=fatalities,
        source_observation_ids=ids,
        extra_warning_codes=(INCOMPLETE_UCDP_WARNING, *extra_warning_codes),
        extra_caveats=(
            "UCDP state-based conflict evidence is incomplete: both event and "
            "fatality counts are required to answer false.",
            *extra_caveats,
        ),
    )


def _missing_decision(
    *,
    evidence_year: int | None,
    events: float | None = None,
    fatalities: float | None = None,
    source_observation_ids: tuple[str, ...],
    extra_warning_codes: tuple[str, ...] = (),
    extra_caveats: tuple[str, ...] = (),
) -> _EvidenceDecision:
    return _EvidenceDecision(
        answer=None,
        events=events,
        fatalities=fatalities,
        evidence_year=evidence_year,
        coverage_status="missing",
        source_observation_ids=source_observation_ids,
        warning_codes=(MISSING_UCDP_WARNING, *extra_warning_codes),
        caveats=extra_caveats,
    )


def _indicator_value(
    observations: tuple[NormalizedObservation, ...],
    indicator_code: str,
) -> float | None:
    for observation in observations:
        if observation.indicator_code == indicator_code:
            value = observation.value
            if isinstance(value, bool) or value is None:
                return None
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return None
    return None


def _resolve_ruler(
    *,
    ruler_resolver: RulerResolver | _RulerResolverLike | RulerLookup | None,
    iso3: str,
    year: int,
) -> tuple[str | None, str | None, str | None]:
    if ruler_resolver is None:
        return None, None, MISSING_RULER_WARNING

    if callable(ruler_resolver) and not hasattr(ruler_resolver, "resolve"):
        result = ruler_resolver(iso3, year)
    else:
        result = ruler_resolver.resolve(iso3, year)  # type: ignore[union-attr]
    name, source, has_ruler = _ruler_fields(result)
    if not has_ruler or not name:
        return None, source, MISSING_RULER_WARNING
    return name, source, None


def _ruler_fields(
    result: RulerResult | Mapping[str, Any] | None,
) -> tuple[str | None, str | None, bool]:
    if result is None:
        return None, None, False
    if isinstance(result, Mapping):
        name = _optional_string(result.get("ruler_name"))
        source = _optional_string(result.get("ruler_source"))
        has_ruler = bool(result.get("has_ruler", bool(name)))
        return name, source, has_ruler
    return result.ruler_name or None, result.ruler_source or None, result.has_ruler


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _country_name(entry: CountryScopeEntry | Mapping[str, Any]) -> str:
    if isinstance(entry, Mapping):
        value = entry.get("country_name") or entry.get("name")
        return str(value) if value is not None else ""
    return entry.country_name


def _is_in_scope(entry: CountryScopeEntry | Mapping[str, Any], year: int) -> bool:
    start_year = _scope_year(entry, "start_year")
    end_year = _scope_year(entry, "end_year")
    return (start_year is None or start_year <= year) and (end_year is None or year <= end_year)


def _scope_year(entry: CountryScopeEntry | Mapping[str, Any], key: str) -> int | None:
    value = entry.get(key) if isinstance(entry, Mapping) else getattr(entry, key)
    return value if isinstance(value, int) else None


__all__ = [
    "Question21AnswerRow",
    "build_q2_1_state_based_conflict_answers",
]
