from __future__ import annotations

from typing import Any

from leaders_db.chronicle.country_scope import CountryScopeEntry
from leaders_db.chronicle.ruler_resolver import RulerResult
from leaders_db.research.question_2_1 import (
    INCOMPLETE_UCDP_WARNING,
    MISSING_RULER_WARNING,
    MISSING_UCDP_WARNING,
    PROXY_YEAR_WARNING,
    Question21AnswerRow,
    build_q2_1_state_based_conflict_answers,
)
from leaders_db.sources.contracts import (
    EvidenceQuery,
    NormalizedObservation,
    RawLocator,
    SourceId,
    TransformLocator,
)
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_q2_1_direct_true_when_events_or_fatalities_positive() -> None:
    rows = _build_rows(
        observations=(
            _ucdp_observation("USA", 2022, "ucdp_state_based_events", 2),
            _ucdp_observation("USA", 2022, "ucdp_state_based_fatalities", 0),
        ),
        country_scope={"USA": _scope("USA", "United States")},
    )

    assert rows == (
        Question21AnswerRow(
            question_id="2.1",
            year=2022,
            iso3="USA",
            country_name="United States",
            ruler_name=None,
            ruler_source=None,
            answer=True,
            state_based_events=2.0,
            state_based_fatalities=0.0,
            evidence_year=2022,
            coverage_status="direct",
            source_observation_ids=(
                "ucdp:USA:2022:ucdp_state_based_events",
                "ucdp:USA:2022:ucdp_state_based_fatalities",
            ),
            warning_codes=(MISSING_RULER_WARNING,),
            caveats=("No ruler name was resolved by the injected resolver.",),
        ),
    )


def test_q2_1_direct_false_when_both_counts_are_zero() -> None:
    rows = _build_rows(
        observations=(
            _ucdp_observation("CAN", 2022, "ucdp_state_based_events", 0),
            _ucdp_observation("CAN", 2022, "ucdp_state_based_fatalities", 0),
        ),
        country_scope={"CAN": _scope("CAN", "Canada")},
    )

    assert rows[0].answer is False
    assert rows[0].coverage_status == "direct"
    assert rows[0].evidence_year == 2022
    assert rows[0].state_based_events == 0.0
    assert rows[0].state_based_fatalities == 0.0
    assert MISSING_UCDP_WARNING not in rows[0].warning_codes


def test_q2_1_missing_row_still_emitted_for_country_without_evidence() -> None:
    rows = _build_rows(
        observations=(),
        country_scope={"FRA": _scope("FRA", "France")},
    )

    assert len(rows) == 1
    assert rows[0].iso3 == "FRA"
    assert rows[0].answer is None
    assert rows[0].coverage_status == "missing"
    assert rows[0].evidence_year is None
    assert rows[0].source_observation_ids == ()
    assert MISSING_UCDP_WARNING in rows[0].warning_codes


def test_q2_1_query_uses_ucdp_source_family_and_state_based_indicators() -> None:
    repository = _SpyEvidenceRepository(
        observations=(
            _ucdp_observation("USA", 2022, "ucdp_state_based_events", 1),
            _ucdp_observation("USA", 2022, "ucdp_state_based_fatalities", 2),
            _ucdp_observation("USA", 2022, "ucdp_intl_events", 999),
            _ucdp_observation(
                "USA",
                2022,
                "ucdp_state_based_events",
                999,
                source_slug="other_source",
            ),
        )
    )

    rows = build_q2_1_state_based_conflict_answers(
        year=2022,
        country_scope={"USA": _scope("USA", "United States")},
        evidence_repository=repository,
    )

    assert rows[0].state_based_events == 1.0
    assert rows[0].state_based_fatalities == 2.0
    assert repository.queries == [
        EvidenceQuery(
            source_ids=(SourceId(slug="ucdp"),),
            observation_families=("international_peace_country_year",),
            indicator_codes=("ucdp_state_based_events", "ucdp_state_based_fatalities"),
            years=(2022,),
            countries=("USA",),
        )
    ]


def test_q2_1_explicit_proxy_year_is_marked_and_not_silent_2023_evidence() -> None:
    rows = _build_rows(
        year=2023,
        proxy_year=2022,
        observations=(
            _ucdp_observation("UKR", 2022, "ucdp_state_based_events", 1),
            _ucdp_observation("UKR", 2022, "ucdp_state_based_fatalities", 100),
        ),
        country_scope={"UKR": _scope("UKR", "Ukraine")},
    )

    assert rows[0].answer is True
    assert rows[0].coverage_status == "proxy"
    assert rows[0].evidence_year == 2022
    assert rows[0].year == 2023
    assert PROXY_YEAR_WARNING in rows[0].warning_codes
    assert any("proxy year 2022" in caveat for caveat in rows[0].caveats)


def test_q2_1_direct_evidence_wins_when_proxy_year_is_also_available() -> None:
    rows = _build_rows(
        year=2023,
        proxy_year=2022,
        observations=(
            _ucdp_observation("UKR", 2023, "ucdp_state_based_events", 0),
            _ucdp_observation("UKR", 2023, "ucdp_state_based_fatalities", 0),
            _ucdp_observation("UKR", 2022, "ucdp_state_based_events", 1),
            _ucdp_observation("UKR", 2022, "ucdp_state_based_fatalities", 100),
        ),
        country_scope={"UKR": _scope("UKR", "Ukraine")},
    )

    assert rows[0].answer is False
    assert rows[0].coverage_status == "direct"
    assert rows[0].evidence_year == 2023
    assert PROXY_YEAR_WARNING not in rows[0].warning_codes
    assert not any("proxy year" in caveat for caveat in rows[0].caveats)


def test_q2_1_incomplete_evidence_is_missing_with_traceability() -> None:
    rows = _build_rows(
        observations=(
            _ucdp_observation("ESP", 2022, "ucdp_state_based_events", 0),
        ),
        country_scope={"ESP": _scope("ESP", "Spain")},
    )

    assert rows[0].answer is None
    assert rows[0].coverage_status == "missing"
    assert rows[0].state_based_events == 0.0
    assert rows[0].state_based_fatalities is None
    assert rows[0].source_observation_ids == ("ucdp:ESP:2022:ucdp_state_based_events",)
    assert MISSING_UCDP_WARNING in rows[0].warning_codes
    assert INCOMPLETE_UCDP_WARNING in rows[0].warning_codes


def test_q2_1_ruler_callback_populates_ruler_fields() -> None:
    def ruler_lookup(iso3: str, year: int) -> RulerResult:
        assert (iso3, year) == ("JPN", 2022)
        return RulerResult(
            ruler_name="Fumio Kishida",
            ruler_title="Prime Minister",
            ruler_type="head_of_government",
            ruler_source="fixture",
            ruler_source_year_used=2022,
            ruler_confidence=100,
            has_ruler=True,
            multiple_rulers=False,
        )

    rows = _build_rows(
        observations=(
            _ucdp_observation("JPN", 2022, "ucdp_state_based_events", 0),
            _ucdp_observation("JPN", 2022, "ucdp_state_based_fatalities", 0),
        ),
        country_scope={"JPN": _scope("JPN", "Japan")},
        ruler_resolver=ruler_lookup,
    )

    assert rows[0].ruler_name == "Fumio Kishida"
    assert rows[0].ruler_source == "fixture"
    assert MISSING_RULER_WARNING not in rows[0].warning_codes


def test_q2_1_missing_ruler_warning_for_callback_without_ruler() -> None:
    rows = _build_rows(
        observations=(
            _ucdp_observation("DEU", 2022, "ucdp_state_based_events", 0),
            _ucdp_observation("DEU", 2022, "ucdp_state_based_fatalities", 0),
        ),
        country_scope={"DEU": _scope("DEU", "Germany")},
        ruler_resolver=lambda _iso3, _year: None,
    )

    assert rows[0].ruler_name is None
    assert MISSING_RULER_WARNING in rows[0].warning_codes


def _build_rows(
    *,
    observations: tuple[NormalizedObservation, ...],
    country_scope: dict[str, CountryScopeEntry | dict[str, Any]],
    year: int = 2022,
    proxy_year: int | None = None,
    ruler_resolver: Any | None = None,
) -> tuple[Question21AnswerRow, ...]:
    return build_q2_1_state_based_conflict_answers(
        year=year,
        country_scope=country_scope,
        evidence_repository=InMemoryEvidenceRepository(observations=observations),
        ruler_resolver=ruler_resolver,
        proxy_year=proxy_year,
    )


def _scope(iso3: str, country_name: str) -> CountryScopeEntry:
    return CountryScopeEntry(
        iso3=iso3,
        country_name=country_name,
        start_year=1900,
        end_year=None,
        source="fixture",
    )


def _ucdp_observation(
    iso3: str,
    year: int,
    indicator_code: str,
    value: int,
    *,
    source_slug: str = "ucdp",
    family: str = "international_peace_country_year",
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=f"ucdp:{iso3}:{year}:{indicator_code}",
        observation_family=family,
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
        year=year,
        country_code=iso3,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit="count",
        scale=None,
        source_version="GED 23.1",
        raw_locator=RawLocator(asset_id="ucdp:fixture"),
        transform_locator=TransformLocator(transform_name="fixture"),
    )


class _SpyEvidenceRepository(InMemoryEvidenceRepository):
    def __init__(self, *, observations: tuple[NormalizedObservation, ...]) -> None:
        super().__init__(observations=observations)
        self.queries: list[EvidenceQuery] = []

    def query_observations(self, query: EvidenceQuery) -> tuple[NormalizedObservation, ...]:
        self.queries.append(query)
        return super().query_observations(query)
