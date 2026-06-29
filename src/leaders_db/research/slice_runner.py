"""Generic runners for first-slice research requests."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.chronicle.country_scope import CountryScopeEntry
from leaders_db.research.question_2_1 import (
    Question21AnswerRow,
    RulerLookup,
    build_q2_1_state_based_conflict_answers,
)
from leaders_db.research.results_store import Q2_1_METHOD_VERSION, persist_q2_1_answers
from leaders_db.sources.query import EvidenceRepository

Slice1Status = Literal["completed", "blocked"]
CountrySelection = Literal["all"] | tuple[str, ...]


class _RulerResolverLike(Protocol):
    def resolve(self, iso3: str, year: int) -> Any: ...


@dataclass(frozen=True)
class Slice1Request:
    """One question, one year, and all or selected in-scope countries."""

    question_id: str
    year: int
    countries: CountrySelection = "all"
    proxy_year: int | None = None
    method_version: str | None = None

    def __post_init__(self) -> None:
        if self.countries != "all":
            object.__setattr__(
                self,
                "countries",
                tuple(str(country).upper() for country in self.countries),
            )


@dataclass(frozen=True)
class Slice1RunResult:
    """Execution summary for a Slice 1 request."""

    status: Slice1Status
    question_id: str
    year: int
    answer_count: int
    persisted_count: int
    infrastructure_gaps: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Slice1QuestionHandler:
    """Question-specific callable pair used by the generic Slice 1 runner."""

    build: Callable[..., Sequence[Any]]
    persist: Callable[[Engine | Session, Sequence[Any], str], None]
    default_method_version: str


def run_slice_1_question_year(
    *,
    request: Slice1Request,
    country_scope: Mapping[str, CountryScopeEntry | Mapping[str, Any]],
    evidence_repository: EvidenceRepository,
    results_bind: Engine | Session | None,
    ruler_resolver: _RulerResolverLike | RulerLookup | None = None,
    handlers: Mapping[str, Slice1QuestionHandler] | None = None,
) -> Slice1RunResult:
    """Run one Slice 1 question/year through the registered handler.

    The runner owns generic scope selection and persistence orchestration.
    Question-specific modules remain responsible for answer construction.
    """

    registry = handlers or default_slice_1_handlers()
    handler = registry.get(request.question_id)
    if handler is None:
        return Slice1RunResult(
            status="blocked",
            question_id=request.question_id,
            year=request.year,
            answer_count=0,
            persisted_count=0,
            infrastructure_gaps=(
                "missing_question_registry_entry",
                "unsupported_question_handler",
            ),
        )

    selected_scope = _select_country_scope(
        country_scope=country_scope,
        year=request.year,
        countries=request.countries,
    )
    rows = tuple(
        handler.build(
            year=request.year,
            country_scope=selected_scope,
            evidence_repository=evidence_repository,
            ruler_resolver=ruler_resolver,
            proxy_year=request.proxy_year,
        )
    )
    method_version = request.method_version or handler.default_method_version
    persisted_count = 0
    if results_bind is not None:
        handler.persist(results_bind, rows, method_version)
        persisted_count = len(rows)

    return Slice1RunResult(
        status="completed",
        question_id=request.question_id,
        year=request.year,
        answer_count=len(rows),
        persisted_count=persisted_count,
        warning_codes=_warning_codes(rows),
    )


def default_slice_1_handlers() -> Mapping[str, Slice1QuestionHandler]:
    """Return the currently supported Slice 1 question handlers."""

    return {
        "2.1": Slice1QuestionHandler(
            build=build_q2_1_state_based_conflict_answers,
            persist=_persist_q2_1,
            default_method_version=Q2_1_METHOD_VERSION,
        )
    }


def _persist_q2_1(
    bind: Engine | Session,
    rows: Sequence[Any],
    method_version: str,
) -> None:
    typed_rows = tuple(cast(Question21AnswerRow, row) for row in rows)
    persist_q2_1_answers(bind, typed_rows, method_version=method_version)


def _select_country_scope(
    *,
    country_scope: Mapping[str, CountryScopeEntry | Mapping[str, Any]],
    year: int,
    countries: CountrySelection,
) -> dict[str, CountryScopeEntry | Mapping[str, Any]]:
    requested = None if countries == "all" else set(countries)
    return {
        iso3: entry
        for iso3, entry in sorted(country_scope.items())
        if (requested is None or iso3.upper() in requested) and _is_in_scope(entry, year)
    }


def _is_in_scope(entry: CountryScopeEntry | Mapping[str, Any], year: int) -> bool:
    start_year = _scope_year(entry, "start_year")
    end_year = _scope_year(entry, "end_year")
    return (start_year is None or start_year <= year) and (end_year is None or year <= end_year)


def _scope_year(entry: CountryScopeEntry | Mapping[str, Any], key: str) -> int | None:
    value = entry.get(key) if isinstance(entry, Mapping) else getattr(entry, key)
    return value if isinstance(value, int) else None


def _warning_codes(rows: Sequence[Any]) -> tuple[str, ...]:
    codes: list[str] = []
    for row in rows:
        for code in getattr(row, "warning_codes", ()):
            if code not in codes:
                codes.append(code)
    return tuple(codes)


__all__ = [
    "Slice1QuestionHandler",
    "Slice1Request",
    "Slice1RunResult",
    "default_slice_1_handlers",
    "run_slice_1_question_year",
]
