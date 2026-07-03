"""Tests for I4 ruler identity infrastructure."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

import leaders_db.identity.coverage as identity_coverage
from leaders_db.cli import app
from leaders_db.db.engine import build_engine, init_database
from leaders_db.db.models import (
    Country,
    CountryYear,
    CountryYearFact,
    Leader,
    LeaderAlias,
    RulerIdentityAdjudication,
    RulerScore,
    RulerSpell,
    RulerYear,
    ScoreCategory,
    Source,
)
from leaders_db.db.readiness import DatabaseReadinessError
from leaders_db.identity.adjudications import build_ruler_identity_adjudications
from leaders_db.identity.coverage import (
    CLASSIFICATION_MEANINGS,
    build_identity_coverage_gap_report,
    identity_gap_report_to_json,
    write_identity_gap_report_artifacts,
)
from leaders_db.identity.ruler_identity import (
    build_ruler_identity,
    build_ruler_identity_coverage_report,
    ruler_identity_coverage_to_json,
)
from leaders_db.research.sql_repository import write_observations
from leaders_db.scope.country_year_grid import CountryDefinition, build_country_year_grid
from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceId,
    TransformLocator,
)

runner = CliRunner()


def _country_universe() -> tuple[CountryDefinition, ...]:
    return (
        CountryDefinition("AAA", "Alpha", "alpha"),
        CountryDefinition("BBB", "Beta", "beta"),
    )


def _three_country_universe() -> tuple[CountryDefinition, ...]:
    return (
        CountryDefinition("AAA", "Alpha", "alpha"),
        CountryDefinition("BBB", "Beta", "beta"),
        CountryDefinition(
            "CCC",
            "Gamma",
            "gamma",
            included_in_project=False,
            scope_exclusion_reason="fixture out of scope",
        ),
    )


def _init_grid(database_url: str, *, start_year: int = 2021, end_year: int = 2023):
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=start_year,
        end_year=end_year,
        countries=_country_universe(),
    )
    return engine


def _identity_observation(
    observation_id: str,
    *,
    source_slug: str = "fixture_identity",
    family: str = "leader_identity_spell",
    indicator_code: str = "fixture_ruler_spell",
    country_code: str | None = "AAA",
    country_name: str | None = None,
    leader_id: str | None = None,
    leader_name: str = "Leader One",
    year: int | None = 2022,
    extension: dict[str, object] | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(source_slug),
        observation_id=observation_id,
        observation_family=family,
        indicator_code=indicator_code,
        value=leader_name,
        value_type="text",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=leader_id,
        leader_name=leader_name,
        unit=None,
        scale=None,
        source_version="test",
        raw_locator=RawLocator(asset_id="fixture"),
        transform_locator=TransformLocator(transform_name="fixture"),
        extension=extension or {},
    )


def test_build_ruler_identity_populates_fixture_backed_rows(database_url: str) -> None:
    engine = _init_grid(database_url)
    write_observations(
        engine,
        [
            _identity_observation(
                "spell-1",
                extension={
                    "start_date": "2022-06-01",
                    "end_date": "2023-03-01",
                    "office_title": "Prime Minister",
                    "is_actual_ruler": True,
                    "is_formal_leader": True,
                    "confidence_score": 92,
                },
            )
        ],
    )

    result = build_ruler_identity(engine)

    assert result.observations_read == 1
    assert result.observations_used == 1
    assert result.leaders_created == 1
    assert result.aliases_created == 1
    assert result.ruler_spells_created == 1
    assert result.ruler_years_created == 2
    with engine.connect() as conn:
        leaders = conn.execute(select(Leader.full_name)).scalars().all()
        aliases = conn.execute(select(LeaderAlias.alias)).scalars().all()
        spells = conn.execute(select(RulerSpell.office_title, RulerSpell.confidence_score)).all()
        years = conn.execute(select(RulerYear.year).order_by(RulerYear.year)).scalars().all()
    assert leaders == ["Leader One"]
    assert aliases == ["Leader One"]
    assert spells == [("Prime Minister", 92)]
    assert years == [2022, 2023]


def test_build_ruler_identity_requires_included_country_year_grid(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    with pytest.raises(DatabaseReadinessError, match="scope build-country-years"):
        build_ruler_identity(engine)

    with pytest.raises(DatabaseReadinessError, match="scope build-country-years"):
        build_ruler_identity_coverage_report(engine)


def test_build_ruler_identity_is_idempotent(database_url: str) -> None:
    engine = _init_grid(database_url)
    write_observations(
        engine,
        [
            _identity_observation(
                "spell-idem",
                extension={"start_date": "2021-01-01", "end_date": "2021-12-31"},
            )
        ],
    )

    first = build_ruler_identity(engine)
    second = build_ruler_identity(engine)

    assert first.ruler_years_created == 1
    assert second.leaders_created == 0
    assert second.aliases_created == 0
    assert second.ruler_spells_created == 0
    assert second.ruler_spells_updated == 0
    assert second.ruler_years_created == 0
    assert second.ruler_years_updated == 0


def test_ruler_coverage_ignores_stale_excluded_country_years(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    included_universe = (
        CountryDefinition("AAA", "Alpha", "alpha"),
        CountryDefinition("BBB", "Beta", "beta"),
    )
    scoped_universe = (
        CountryDefinition("AAA", "Alpha", "alpha"),
        CountryDefinition(
            "BBB",
            "Beta",
            "beta",
            included_in_project=False,
            scope_exclusion_reason="test excluded territory",
        ),
    )
    build_country_year_grid(engine, start_year=2023, end_year=2023, countries=included_universe)
    write_observations(
        engine,
        [
            _identity_observation(
                "aaa-leader",
                country_code="AAA",
                leader_name="Alpha Leader",
                year=2023,
            ),
            _identity_observation(
                "bbb-leader",
                country_code="BBB",
                leader_name="Beta Leader",
                year=2023,
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    build_country_year_grid(engine, start_year=2023, end_year=2023, countries=scoped_universe)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2023)
    )

    assert payload["total_country_years"] == 1
    assert payload["covered_country_years"] == 1
    assert payload["missing_country_years"] == 0


def test_build_ruler_identity_dedupes_same_source_spell_catalog_rows(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2021, end_year=2021)
    write_observations(
        engine,
        [
            _identity_observation(
                "spell-leader",
                indicator_code="reign_leader",
                family="leader_identity_month",
                year=2021,
                extension={"reign_month": 1},
            ),
            _identity_observation(
                "spell-age",
                indicator_code="reign_age",
                family="leader_identity_month",
                year=2021,
                extension={"reign_month": 1},
            ),
        ],
    )

    result = build_ruler_identity(engine)

    assert result.observations_read == 2
    assert result.observations_used == 1
    assert result.ruler_spells_created == 1
    assert result.ruler_years_created == 1


def test_build_ruler_identity_removes_stale_reign_month_fragments_without_bridging_gaps(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2020, end_year=2021)
    write_observations(
        engine,
        [
            _identity_observation(
                "reign-2020-01",
                source_slug="reign",
                indicator_code="reign_leader",
                family="leader_identity_month",
                leader_name="Monthly Leader",
                year=2020,
                extension={"reign_month": 1},
            ),
            _identity_observation(
                "reign-2020-02",
                source_slug="reign",
                indicator_code="reign_leader",
                family="leader_identity_month",
                leader_name="Monthly Leader",
                year=2020,
                extension={"reign_month": 2},
            ),
            _identity_observation(
                "reign-2021-gap-singleton",
                source_slug="reign",
                indicator_code="reign_leader",
                family="leader_identity_month",
                leader_name="Monthly Leader",
                year=2021,
                extension={"reign_month": 1},
            ),
        ],
    )

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        leader = Leader(full_name="Monthly Leader", normalized_name="monthly leader")
        country = session.scalar(select(Country).where(Country.iso3 == "AAA"))
        assert country is not None
        session.add(leader)
        session.flush()
        stale_spells = [
            RulerSpell(
                leader_id=leader.id,
                country_id=country.id,
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1, 31),
                source_dataset="reign",
                is_actual_ruler=True,
                is_formal_leader=False,
                notes="old monthly fragment",
            ),
            RulerSpell(
                leader_id=leader.id,
                country_id=country.id,
                start_date=date(2020, 2, 1),
                end_date=date(2020, 2, 29),
                source_dataset="reign",
                is_actual_ruler=True,
                is_formal_leader=False,
                notes="old monthly fragment",
            ),
            RulerSpell(
                leader_id=leader.id,
                country_id=country.id,
                start_date=date(2021, 1, 1),
                end_date=date(2021, 1, 31),
                source_dataset="reign",
                is_actual_ruler=True,
                is_formal_leader=False,
                notes="old singleton gap fragment",
            ),
        ]
        session.add_all(stale_spells)
        session.flush()
        session.add(
            RulerYear(
                leader_id=leader.id,
                country_id=country.id,
                year=2020,
                ruler_spell_id=stale_spells[0].id,
                system_selected_leader_name="Monthly Leader",
                match_status="matched",
            )
        )
        session.commit()
        stale_2020_ids = {stale_spells[0].id, stale_spells[1].id}

    result = build_ruler_identity(engine, start_year=2020, end_year=2021)
    second = build_ruler_identity(engine, start_year=2020, end_year=2021)

    with engine.connect() as conn:
        spells = conn.execute(
            select(RulerSpell.start_date, RulerSpell.end_date)
            .where(RulerSpell.source_dataset == "reign")
            .order_by(RulerSpell.start_date)
        ).all()
        remaining_stale = conn.execute(
            select(RulerSpell.id).where(RulerSpell.id.in_(stale_2020_ids))
        ).all()
        stale_ruler_year_refs = conn.execute(
            select(RulerYear.id).where(RulerYear.ruler_spell_id.in_(stale_2020_ids))
        ).all()

    assert result.ruler_spells_created == 1
    assert remaining_stale == []
    assert stale_ruler_year_refs == []
    assert spells == [
        (date(2020, 1, 1), date(2020, 2, 29)),
        (date(2021, 1, 1), date(2021, 1, 31)),
    ]
    assert second.ruler_spells_created == 0
    assert second.ruler_spells_updated == 0
    assert second.ruler_years_created == 0
    assert second.ruler_years_updated == 0


def test_stale_reign_cleanup_marks_dependent_principal_ruler_fact_unresolved(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2020, end_year=2020)
    write_observations(
        engine,
        [
            _identity_observation(
                "reign-2020-01",
                source_slug="reign",
                indicator_code="reign_leader",
                family="leader_identity_month",
                leader_name="Monthly Leader",
                year=2020,
                extension={"reign_month": 1},
            ),
            _identity_observation(
                "reign-2020-02",
                source_slug="reign",
                indicator_code="reign_leader",
                family="leader_identity_month",
                leader_name="Monthly Leader",
                year=2020,
                extension={"reign_month": 2},
            ),
        ],
    )

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        country = session.scalar(select(Country).where(Country.iso3 == "AAA"))
        assert country is not None
        country_year = session.scalar(
            select(CountryYear).where(
                CountryYear.country_id == country.id,
                CountryYear.year == 2020,
            )
        )
        assert country_year is not None
        country_id = country.id
        country_year_id = country_year.id
        leader = Leader(full_name="Monthly Leader", normalized_name="monthly leader")
        category = ScoreCategory(category_key="fixture", category_name="Fixture")
        session.add_all([leader, category])
        session.flush()
        stale_spell = RulerSpell(
            leader_id=leader.id,
            country_id=country_id,
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 31),
            source_dataset="reign",
            is_actual_ruler=True,
            is_formal_leader=False,
            notes="old monthly fragment",
        )
        session.add(stale_spell)
        session.flush()
        stale_ruler_year = RulerYear(
            leader_id=leader.id,
            country_id=country_id,
            year=2020,
            ruler_spell_id=stale_spell.id,
            system_selected_leader_name="Monthly Leader",
            match_status="matched",
        )
        session.add(stale_ruler_year)
        session.flush()
        stale_ruler_year_id = stale_ruler_year.id
        session.add_all(
            [
                RulerScore(
                    ruler_year_id=stale_ruler_year_id,
                    category_id=category.id,
                    system_proposed_score=7,
                    final_score=7,
                    confidence_score=90,
                ),
                RulerIdentityAdjudication(
                    country_year_id=country_year_id,
                    country_id=country_id,
                    year=2020,
                    selected_ruler_year_id=stale_ruler_year_id,
                    selected_leader_name="Monthly Leader",
                    candidate_ruler_year_ids_json=json.dumps([stale_ruler_year_id]),
                    candidates_json="[]",
                    classification="resolved_auto_single_candidate",
                    selection_rule="single_candidate",
                    review_status="auto_resolved",
                    confidence_score=95,
                    confidence_penalties_json="[]",
                    warnings_json="[]",
                    rationale="fixture auto selection",
                    recommended_next_action="No action required.",
                    source_slugs_json=json.dumps(["reign"]),
                    source_observation_ids_json=json.dumps(["reign-2020-01"]),
                    method_version="test",
                ),
                CountryYearFact(
                    country_year_id=country_year_id,
                    country_id=country_id,
                    year=2020,
                    field_key="principal_ruler",
                    field_label="Principal ruler",
                    value_type="entity",
                    selected_value_text="Monthly Leader",
                    selected_entity_table="ruler_years",
                    selected_entity_id=stale_ruler_year_id,
                    candidate_values_json="[]",
                    selection_rule="single_candidate",
                    adjudication_status="auto_resolved",
                    confidence_score=95,
                    quality_signals_json="{}",
                    warnings_json="[]",
                    rationale="fixture auto fact",
                    recommended_next_action="No action required.",
                    source_slugs_json=json.dumps(["reign"]),
                    source_observation_ids_json=json.dumps(["reign-2020-01"]),
                    producer="ruler_identity_adjudications",
                    method_version="test",
                ),
            ]
        )
        session.commit()

    result = build_ruler_identity(engine, start_year=2020, end_year=2020)

    with Session(engine) as session:
        stale_ruler_year = session.scalar(
            select(RulerYear)
            .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
            .where(
                RulerSpell.start_date == date(2020, 1, 1),
                RulerSpell.end_date == date(2020, 1, 31),
            )
        )
        stale_score = session.scalar(
            select(RulerScore).where(RulerScore.ruler_year_id == stale_ruler_year_id)
        )
        adjudication = session.scalar(
            select(RulerIdentityAdjudication).where(
                RulerIdentityAdjudication.country_year_id == country_year_id
            )
        )
        fact = session.scalar(
            select(CountryYearFact).where(
                CountryYearFact.country_year_id == country_year_id,
                CountryYearFact.field_key == "principal_ruler",
            )
        )

    assert result.ruler_spells_created == 1
    assert stale_ruler_year is None
    assert stale_score is None
    assert adjudication is not None
    assert adjudication.selected_ruler_year_id is None
    assert fact is not None
    assert fact.selected_entity_table is None
    assert fact.selected_entity_id is None
    assert fact.selected_value_text is None
    assert fact.adjudication_status == "needs_review"
    assert fact.selection_rule == "stale_monthly_spell_cleanup"
    assert "stale_identity_evidence_superseded" in json.loads(fact.warnings_json)


def test_build_ruler_identity_resolves_source_native_country_code(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=2015,
        end_year=2015,
        countries=(CountryDefinition("KOR", "Korea, Republic of", "korea republic of"),),
    )
    write_observations(
        engine,
        [
            _identity_observation(
                "archigos-rok-leader",
                source_slug="archigos",
                indicator_code="archigos_leader_name",
                country_code="ROK",
                leader_name="Test Leader",
                year=2015,
                extension={
                    "archigos_idacr": "ROK",
                    "start_date": "2015-01-01",
                    "end_date": "2015-12-31",
                },
            )
        ],
    )

    result = build_ruler_identity(engine, start_year=2015, end_year=2015)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2015)
    )

    assert result.observations_used == 1
    assert result.ruler_years_created == 1
    assert payload["covered_country_years"] == 1
    assert payload["missing_country_years"] == 0


@pytest.mark.parametrize("source_slug", ["client_existing", "vertical_slice_client_seed"])
def test_build_ruler_identity_excludes_non_evidence_identity_sources(
    database_url: str,
    source_slug: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                f"{source_slug}-leader",
                source_slug=source_slug,
                leader_name="Client Seed Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            )
        ],
    )

    result = build_ruler_identity(engine)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2023)
    )

    assert result.observations_read == 0
    assert result.observations_used == 0
    assert result.leaders_created == 0
    assert result.aliases_created == 0
    assert result.ruler_spells_created == 0
    assert result.ruler_years_created == 0
    assert payload["covered_country_years"] == 0
    assert payload["missing_country_years"] == 2
    with engine.connect() as conn:
        assert conn.execute(select(Leader)).all() == []
        assert conn.execute(select(LeaderAlias)).all() == []
        assert conn.execute(select(RulerSpell)).all() == []
        assert conn.execute(select(RulerYear)).all() == []


def test_build_ruler_identity_removes_existing_non_evidence_identity_outputs(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "client-seed-leader",
                source_slug="vertical_slice_client_seed",
                leader_name="Client Seed Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            )
        ],
    )

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        source = session.scalar(
            select(Source).where(Source.source_name == "vertical_slice_client_seed")
        )
        if source is None:
            source = Source(source_name="vertical_slice_client_seed", source_type="validation_only")
            session.add(source)
            session.flush()
        leader = Leader(full_name="Client Seed Leader", normalized_name="client seed leader")
        session.add(leader)
        session.flush()
        session.add(
            LeaderAlias(leader_id=leader.id, source_id=source.id, alias="Client Seed Leader")
        )
        spell = RulerSpell(
            leader_id=leader.id,
            country_id=1,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            source_dataset="vertical_slice_client_seed",
            is_actual_ruler=True,
            is_formal_leader=True,
        )
        session.add(spell)
        session.flush()
        session.add(
            RulerYear(
                leader_id=leader.id,
                country_id=1,
                year=2023,
                ruler_spell_id=spell.id,
                system_selected_leader_name="Client Seed Leader",
                match_status="matched",
            )
        )
        session.commit()

    build_ruler_identity(engine)

    with engine.connect() as conn:
        assert conn.execute(select(Leader)).all() == []
        assert conn.execute(select(LeaderAlias)).all() == []
        assert conn.execute(select(RulerSpell)).all() == []
        assert conn.execute(select(RulerYear)).all() == []


def test_source_native_person_ids_are_provenance_not_aliases(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2022)
    write_observations(
        engine,
        [
            _identity_observation(
                "source-id-spell",
                leader_id="Q12345",
                leader_name="Readable Leader",
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "person_qid": "Q99999",
                    "archigos_obsid": "ARCH1",
                },
            )
        ],
    )

    build_ruler_identity(engine)

    with engine.connect() as conn:
        aliases = conn.execute(select(LeaderAlias.alias)).scalars().all()
        notes = conn.execute(select(RulerSpell.notes)).scalars().all()
    assert aliases == ["Readable Leader"]
    assert all(alias not in {"Q12345", "Q99999", "ARCH1"} for alias in aliases)
    assert any("row_leader_id=Q12345" in note for note in notes)
    assert any("person_qid=Q99999" in note for note in notes)
    assert any("archigos_obsid=ARCH1" in note for note in notes)


def test_build_ruler_identity_resolves_source_native_cow_code(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=1990,
        end_year=1991,
        countries=(CountryDefinition("YUG", "Yugoslavia", "yugoslavia"),),
    )
    write_observations(
        engine,
        [
            _identity_observation(
                "archigos-yug",
                source_slug="archigos",
                indicator_code="archigos_leader_name",
                country_code=None,
                country_name=None,
                leader_name="Yugoslav Leader",
                year=1990,
                extension={
                    "archigos_ccode": 345,
                    "start_year": 1990,
                    "archigos_end_year": 1991,
                },
            )
        ],
    )

    result = build_ruler_identity(engine)

    assert result.observations_used == 1
    assert result.ruler_years_created == 2
    with engine.connect() as conn:
        years = conn.execute(select(RulerYear.year).order_by(RulerYear.year)).scalars().all()
    assert years == [1990, 1991]


def test_build_ruler_identity_maps_soviet_reign_rows_to_sun_not_rus(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=1991,
        end_year=1991,
        countries=(
            CountryDefinition("SUN", "Soviet Union", "soviet union"),
            CountryDefinition("RUS", "Russia", "russia"),
        ),
    )
    write_observations(
        engine,
        [
            _identity_observation(
                "reign-soviet-1991",
                source_slug="reign",
                family="leader_identity_month",
                indicator_code="reign_leader",
                country_code=None,
                country_name="Soviet Union",
                leader_name="Soviet Leader",
                year=1991,
                extension={
                    "reign_country": "Soviet Union",
                    "reign_ccode": 365,
                    "reign_month": 8,
                },
            )
        ],
    )

    result = build_ruler_identity(engine, start_year=1991, end_year=1991)

    assert result.observations_used == 1
    with engine.connect() as conn:
        country_codes = conn.execute(
            select(RulerYear.year, Country.iso3)
            .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
            .join(Country, RulerYear.country_id == Country.id)
            .order_by(RulerYear.year)
        ).all()
    assert country_codes == [(1991, "SUN")]


def test_reign_months_aggregate_into_contiguous_transition_spells(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=1953, end_year=1953)
    observations = [
        _identity_observation(
            f"reign-alpha-{month}",
            source_slug="reign",
            family="leader_identity_month",
            indicator_code="reign_leader",
            leader_name="Leader Alpha",
            year=1953,
            extension={"reign_month": month, "source_row_reference": f"alpha:{month}"},
        )
        for month in range(1, 9)
    ]
    observations.extend(
        _identity_observation(
            f"reign-beta-{month}",
            source_slug="reign",
            family="leader_identity_month",
            indicator_code="reign_leader",
            leader_name="Leader Beta",
            year=1953,
            extension={"reign_month": month, "source_row_reference": f"beta:{month}"},
        )
        for month in range(9, 13)
    )
    write_observations(engine, observations)

    identity = build_ruler_identity(engine, start_year=1953, end_year=1953)
    adjudication = build_ruler_identity_adjudications(engine, start_year=1953, end_year=1953)

    assert identity.observations_read == 12
    assert identity.observations_used == 2
    assert identity.ruler_spells_created == 2
    assert adjudication.review_status_counts["auto_resolved"] == 1
    assert adjudication.classification_counts["resolved_auto_duration_majority"] == 1
    with engine.connect() as conn:
        spells = conn.execute(
            select(
                RulerSpell.start_date,
                RulerSpell.end_date,
                Leader.full_name,
                RulerSpell.notes,
            )
            .join(Leader, RulerSpell.leader_id == Leader.id)
            .order_by(RulerSpell.start_date)
        ).all()
        fact = conn.execute(
            select(CountryYearFact.selected_value_text, CountryYearFact.adjudication_status)
            .join(Country, CountryYearFact.country_id == Country.id)
            .where(CountryYearFact.field_key == "principal_ruler", Country.iso3 == "AAA")
        ).one()

    assert [(row.start_date, row.end_date, row.full_name) for row in spells] == [
        (date(1953, 1, 1), date(1953, 8, 31), "Leader Alpha"),
        (date(1953, 9, 1), date(1953, 12, 31), "Leader Beta"),
    ]
    assert "normalized_observations:" in spells[0].notes
    assert fact == ("Leader Alpha", "auto_resolved")


def test_reign_month_aggregation_does_not_bridge_missing_month_gap(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=1953, end_year=1953)
    write_observations(
        engine,
        [
            _identity_observation(
                "reign-alpha-jan",
                source_slug="reign",
                family="leader_identity_month",
                indicator_code="reign_leader",
                leader_name="Leader Alpha",
                year=1953,
                extension={"reign_month": 1},
            ),
            _identity_observation(
                "reign-alpha-mar",
                source_slug="reign",
                family="leader_identity_month",
                indicator_code="reign_leader",
                leader_name="Leader Alpha",
                year=1953,
                extension={"reign_month": 3},
            ),
        ],
    )

    result = build_ruler_identity(engine, start_year=1953, end_year=1953)

    assert result.observations_read == 2
    assert result.observations_used == 2
    with engine.connect() as conn:
        spans = conn.execute(
            select(RulerSpell.start_date, RulerSpell.end_date).order_by(RulerSpell.start_date)
        ).all()
    assert spans == [(date(1953, 1, 1), date(1953, 1, 31)), (date(1953, 3, 1), date(1953, 3, 31))]


def test_ruler_years_expand_only_overlapping_country_years(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2020, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "spell-overlap",
                extension={"start_date": "2019-01-01", "end_date": "2021-12-31"},
            )
        ],
    )

    build_ruler_identity(engine)

    with engine.connect() as conn:
        years = conn.execute(select(RulerYear.year).order_by(RulerYear.year)).scalars().all()
    assert years == [2020, 2021]


def test_old_source_does_not_fill_2023_and_coverage_reports_missing(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2021, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "old-source",
                source_slug="reign_fixture",
                family="leader_identity_month",
                year=2021,
                extension={"reign_month": 8, "confidence_score": 85},
            )
        ],
    )

    build_ruler_identity(engine)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2023)
    )

    assert payload["total_country_years"] == 2
    assert payload["covered_country_years"] == 0
    assert payload["missing_country_years"] == 2


def test_wikidata_current_identity_observation_covers_2023(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "wikidata-usa-2023",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                country_code="AAA",
                leader_name="Current Leader",
                year=2023,
                extension={
                    "person_qid": "Q123",
                    "person_label": "Current Leader",
                    "start_date": "2023-01-01T00:00:00Z",
                    "end_date": "2023-12-31T00:00:00Z",
                    "office_label": "head of government",
                },
            )
        ],
    )

    result = build_ruler_identity(engine, start_year=2023, end_year=2023)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2023)
    )

    assert result.observations_used == 1
    assert result.ruler_years_created == 1
    assert payload["covered_country_years"] == 1
    assert payload["missing_country_years"] == 1


def test_wikidata_without_source_iso3_does_not_match_by_country_name(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "wikidata-no-iso3-2023",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                country_code=None,
                country_name="Alpha",
                leader_name="Current Leader",
                year=2023,
                extension={
                    "person_qid": "Q123",
                    "person_label": "Current Leader",
                    "country_label": "Alpha",
                    "start_date": "2023-01-01T00:00:00Z",
                    "end_date": "2023-12-31T00:00:00Z",
                },
            )
        ],
    )

    result = build_ruler_identity(engine, start_year=2023, end_year=2023)
    payload = ruler_identity_coverage_to_json(
        build_ruler_identity_coverage_report(engine, year=2023)
    )

    assert result.observations_read == 1
    assert result.observations_used == 0
    assert result.ruler_years_created == 0
    assert payload["covered_country_years"] == 0
    assert payload["missing_country_years"] == 2


def test_coverage_report_counts_disputed_multiple_low_confidence_and_conflict(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2022)
    write_observations(
        engine,
        [
            _identity_observation(
                "leader-a",
                source_slug="source_a",
                leader_name="Leader A",
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "confidence_score": 65,
                },
            ),
            _identity_observation(
                "leader-b",
                source_slug="source_b",
                leader_name="Leader B",
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "disputed_rule_flag": True,
                    "confidence_score": 90,
                },
            ),
        ],
    )

    build_ruler_identity(engine)
    second = build_ruler_identity(engine)
    payload = ruler_identity_coverage_to_json(build_ruler_identity_coverage_report(engine))

    assert second.ruler_spells_created == 0
    assert second.ruler_spells_updated == 0
    assert second.ruler_years_created == 0
    assert second.ruler_years_updated == 0

    assert payload["total_country_years"] == 2
    assert payload["covered_country_years"] == 1
    assert payload["missing_country_years"] == 1
    assert payload["disputed_country_years"] == 1
    assert payload["multiple_ruler_country_years"] == 1
    assert payload["low_confidence_country_years"] == 1
    assert payload["source_conflict_country_years"] == 1
    assert any("leaderless unresolved" in item for item in payload["limitations"])


def test_detailed_identity_gap_report_classifies_rows_and_sources(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=2023,
        end_year=2023,
        countries=_three_country_universe(),
    )
    write_observations(
        engine,
        [
            _identity_observation(
                "resolved-a",
                country_code="AAA",
                leader_name="Resolved Leader",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "confidence_score": 95,
                },
            ),
            _identity_observation(
                "unmapped",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                country_code=None,
                country_name="Beta",
                leader_name="Unmapped Leader",
                year=2023,
                extension={
                    "country_label": "Beta",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                },
            ),
            _identity_observation(
                "missing-leader",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                country_code="BBB",
                leader_name="",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    report = build_identity_coverage_gap_report(engine, year=2023)
    payload = identity_gap_report_to_json(report, detail=True)
    rows = {row["iso3"]: row for row in payload["rows"]}

    assert rows["AAA"]["classification"] == "resolved_auto_single_candidate"
    assert rows["BBB"]["classification"] == "missing_unresolved_country_mapping"
    assert rows["CCC"]["classification"] == "out_of_scope"
    assert payload["summary"]["classification_counts"] == {
        "missing_unresolved_country_mapping": 1,
        "out_of_scope": 1,
        "resolved_auto_single_candidate": 1,
    }
    diagnostics = {row["source_slug"]: row for row in payload["source_diagnostics"]}
    assert diagnostics["fixture_identity"]["loaded_row_count"] == 1
    assert diagnostics["wikidata_heads_of_state_government"]["unresolved_country_count"] == 1
    assert diagnostics["wikidata_heads_of_state_government"]["missing_leader_count"] == 1
    assert "missing_current_source_cache" in CLASSIFICATION_MEANINGS


def test_detailed_identity_gap_report_flags_review_statuses(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2022)
    write_observations(
        engine,
        [
            _identity_observation(
                "low-confidence",
                country_code="AAA",
                leader_name="Low Confidence Leader",
                year=2022,
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "confidence_score": 40,
                },
            ),
            _identity_observation(
                "conflict-a",
                country_code="BBB",
                source_slug="source_a",
                leader_name="Candidate A",
                year=2022,
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                "conflict-b",
                country_code="BBB",
                source_slug="source_b",
                leader_name="Candidate B",
                year=2022,
                extension={
                    "start_date": "2022-01-01",
                    "end_date": "2022-12-31",
                    "confidence_score": 90,
                },
            ),
        ],
    )
    build_ruler_identity(engine)

    report = build_identity_coverage_gap_report(engine, year=2022)
    rows = {row.iso3: row for row in report.rows}

    assert rows["AAA"].classification == "low_confidence"
    assert rows["BBB"].classification == "source_conflict_manual_review"
    assert rows["BBB"].next_action == "Manual adjudication required."


def test_adjudication_role_priority_preserves_formal_candidate(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "formal-hos",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_state_held",
                leader_name="Formal President",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "President",
                    "is_actual_ruler": False,
                    "is_formal_leader": True,
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                "actual-hog",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                leader_name="Dominant Prime Minister",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "Prime Minister",
                    "is_actual_ruler": True,
                    "is_formal_leader": True,
                    "confidence_score": 92,
                },
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == (
        "resolved_auto_role_priority"
    )
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                RulerYear.system_selected_leader_name,
                RulerYear.match_status,
                RulerYear.review_status,
                RulerYear.confidence_score,
                RulerYear.review_note,
            ).order_by(RulerYear.match_status)
        ).all()
    assert len(rows) == 2
    assert {row.system_selected_leader_name for row in rows} == {"Dominant Prime Minister"}
    assert {row.match_status for row in rows} == {
        "preserved_competing_candidate",
        "resolved_auto_role_priority",
    }
    assert any(row.review_status == "auto_resolved" for row in rows)
    assert any("competing_candidates" in str(row.review_note) for row in rows)
    assert sorted(row.confidence_score for row in rows) == [80, 82]


def test_build_ruler_identity_adjudications_persists_auto_selection_and_is_idempotent(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "formal-adj",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_state_held",
                leader_name="Formal President",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "President",
                    "is_actual_ruler": False,
                    "is_formal_leader": True,
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                "actual-adj",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                leader_name="Dominant Prime Minister",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "Prime Minister",
                    "is_actual_ruler": True,
                    "is_formal_leader": True,
                    "confidence_score": 92,
                },
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    first = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)
    second = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert first.rows_created == 2
    assert second.rows_created == 0
    assert second.rows_updated == 0
    assert second.review_status_counts == {"auto_resolved": 1, "research_required": 1}
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                RulerIdentityAdjudication.classification,
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.selected_leader_name,
                RulerIdentityAdjudication.candidates_json,
                RulerIdentityAdjudication.research_prompt,
            ).order_by(RulerIdentityAdjudication.classification)
        ).all()
        fact_rows = conn.execute(
            select(
                CountryYearFact.field_key,
                CountryYearFact.adjudication_status,
                CountryYearFact.selected_value_text,
                CountryYearFact.selected_entity_table,
                CountryYearFact.selected_entity_id,
                CountryYearFact.candidate_values_json,
                CountryYearFact.quality_signals_json,
                CountryYearFact.producer,
            ).order_by(CountryYearFact.adjudication_status)
        ).all()
    auto = next(row for row in rows if row.review_status == "auto_resolved")
    assert auto.classification == "resolved_auto_role_priority"
    assert auto.selected_ruler_year_id is not None
    assert auto.selected_leader_name == "Dominant Prime Minister"
    assert "Prime Minister" in auto.candidates_json
    assert auto.research_prompt is None
    assert first.fact_rows_created == 2
    assert second.fact_rows_created == 0
    assert second.fact_rows_updated == 0
    auto_fact = next(row for row in fact_rows if row.adjudication_status == "auto_resolved")
    assert auto_fact.field_key == "principal_ruler"
    assert auto_fact.selected_value_text == "Dominant Prime Minister"
    assert auto_fact.selected_entity_table == "ruler_years"
    assert auto_fact.selected_entity_id == auto.selected_ruler_year_id
    assert "Prime Minister" in auto_fact.candidate_values_json
    assert json.loads(auto_fact.quality_signals_json)["classification"] == (
        "resolved_auto_role_priority"
    )
    assert auto_fact.producer == "ruler_identity_adjudications"


def test_build_ruler_identity_adjudications_persists_manual_conflict_prompt(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "manual-a",
                source_slug="source_a",
                leader_name="Candidate A",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "manual-b",
                source_slug="source_b",
                leader_name="Candidate B",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "manual-c",
                source_slug="source_c",
                leader_name="Candidate C",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert result.classification_counts["source_conflict_manual_review"] == 1
    with engine.connect() as conn:
        row = conn.execute(
            select(
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.candidate_ruler_year_ids_json,
                RulerIdentityAdjudication.source_slugs_json,
                RulerIdentityAdjudication.research_prompt,
            ).where(
                RulerIdentityAdjudication.classification == "source_conflict_manual_review"
            )
        ).one()
        fact_row = conn.execute(
            select(
                CountryYearFact.selected_entity_id,
                CountryYearFact.adjudication_status,
                CountryYearFact.source_slugs_json,
                CountryYearFact.research_prompt,
                CountryYearFact.candidate_values_json,
            ).where(
                CountryYearFact.field_key == "principal_ruler",
                CountryYearFact.adjudication_status == "needs_review",
            )
        ).one()
    assert row.selected_ruler_year_id is None
    assert row.review_status == "needs_review"
    assert json.loads(row.candidate_ruler_year_ids_json)
    assert json.loads(row.source_slugs_json) == ["source_a", "source_b", "source_c"]
    assert "Who was the principal/dominant ruler of Alpha (AAA) in 2023?" in row.research_prompt
    assert "Candidate A" in row.research_prompt
    assert "Use non-client evidence only" in row.research_prompt
    assert fact_row.selected_entity_id is None
    assert fact_row.adjudication_status == "needs_review"
    assert json.loads(fact_row.source_slugs_json) == ["source_a", "source_b", "source_c"]
    assert "Who was the principal/dominant ruler of Alpha (AAA) in 2023?" in (
        fact_row.research_prompt
    )
    assert "Candidate A" in fact_row.candidate_values_json


@pytest.mark.parametrize("de_facto_phrase", ["de facto ruler", "de-facto ruler"])
def test_research_adjudication_resolves_single_strong_internet_research_candidate(
    database_url: str,
    de_facto_phrase: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "formal-officeholder",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_state_held",
                leader_name="Formal President",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "President",
                    "is_actual_ruler": False,
                    "is_formal_leader": True,
                    "confidence_score": 91,
                },
            ),
            _identity_observation(
                "structured-actual-conflict",
                source_slug="source_a",
                leader_name="Structured Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "Prime Minister",
                    "is_actual_ruler": True,
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                "research-mbz-like",
                source_slug="internet_research_adjudication",
                indicator_code="internet_research_de_facto_principal_ruler",
                leader_name="Research Principal Ruler",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "Principal ruler",
                    "rule_type": "de_facto_ruler",
                    "is_actual_ruler": True,
                    "confidence_score": 88,
                    "source_urls": ["https://example.test/research"],
                    "source_quotes": [f"Research identifies this leader as the {de_facto_phrase}."],
                },
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert result.classification_counts["resolved_research_adjudicated"] == 1
    with engine.connect() as conn:
        adjudication = conn.execute(
            select(
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_leader_name,
                RulerIdentityAdjudication.selection_rule,
                RulerIdentityAdjudication.candidates_json,
                RulerIdentityAdjudication.research_prompt,
            ).where(RulerIdentityAdjudication.classification == "resolved_research_adjudicated")
        ).one()
        fact = conn.execute(
            select(
                CountryYearFact.selected_value_text,
                CountryYearFact.selection_rule,
                CountryYearFact.adjudication_status,
                CountryYearFact.candidate_values_json,
                CountryYearFact.quality_signals_json,
            )
            .join(Country, CountryYearFact.country_id == Country.id)
            .where(CountryYearFact.field_key == "principal_ruler", Country.iso3 == "AAA")
        ).one()
    candidates = json.loads(adjudication.candidates_json)
    research_candidate = next(
        item for item in candidates if item["source_slug"] == "internet_research_adjudication"
    )
    assert adjudication.review_status == "auto_resolved"
    assert adjudication.selected_leader_name == "Research Principal Ruler"
    assert adjudication.selection_rule == "internet_research_adjudication"
    assert adjudication.research_prompt is None
    assert research_candidate["source_observation_ids"]
    assert "https://example.test/research" in research_candidate["source_notes"]
    assert f"Research identifies this leader as the {de_facto_phrase}." in research_candidate[
        "source_notes"
    ]
    assert fact.selected_value_text == "Research Principal Ruler"
    assert fact.selection_rule == "internet_research_adjudication"
    assert fact.adjudication_status == "auto_resolved"
    assert "Research Principal Ruler" in fact.candidate_values_json
    assert json.loads(fact.quality_signals_json)["classification"] == (
        "resolved_research_adjudicated"
    )


def test_research_adjudication_weak_candidate_remains_needs_review(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "weak-research-a",
                source_slug="internet_research_adjudication",
                indicator_code="internet_research_de_facto_principal_ruler",
                leader_name="Weak Research Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "is_actual_ruler": True,
                    "confidence_score": 79,
                },
            ),
            _identity_observation(
                "conflicting-structured-b",
                source_slug="source_b",
                leader_name="Structured Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "is_actual_ruler": True,
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                "formal-candidate-c",
                source_slug="source_c",
                leader_name="Formal Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "is_actual_ruler": False,
                    "is_formal_leader": True,
                    "confidence_score": 90,
                },
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert "resolved_research_adjudicated" not in result.classification_counts
    assert result.classification_counts["source_conflict_manual_review"] == 1
    with engine.connect() as conn:
        adjudication = conn.execute(
            select(
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.review_status,
            )
            .join(Country, RulerIdentityAdjudication.country_id == Country.id)
            .where(Country.iso3 == "AAA")
        ).one()
        fact = conn.execute(
            select(CountryYearFact.selected_entity_id, CountryYearFact.adjudication_status)
            .join(Country, CountryYearFact.country_id == Country.id)
            .where(CountryYearFact.field_key == "principal_ruler", Country.iso3 == "AAA")
        ).one()
    assert adjudication.selected_ruler_year_id is None
    assert adjudication.review_status == "needs_review"
    assert fact.selected_entity_id is None
    assert fact.adjudication_status == "needs_review"


@pytest.mark.parametrize("hard_marker", ["shared", "disputed"])
def test_research_adjudication_hard_marker_remains_needs_review(
    database_url: str,
    hard_marker: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                f"strong-research-{hard_marker}",
                source_slug="internet_research_adjudication",
                indicator_code="internet_research_principal_ruler",
                leader_name="Strong Research Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": f"{hard_marker.title()} principal ruler",
                    "is_actual_ruler": True,
                    "confidence_score": 91,
                    "source_urls": ["https://example.test/hard-marker"],
                    "source_quotes": [f"Research notes a {hard_marker} rule arrangement."],
                },
            ),
            _identity_observation(
                f"structured-conflict-{hard_marker}",
                source_slug="source_b",
                leader_name="Structured Candidate",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "office_title": "Prime Minister",
                    "is_actual_ruler": True,
                    "confidence_score": 90,
                },
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert "resolved_research_adjudicated" not in result.classification_counts
    assert result.classification_counts["source_conflict_manual_review"] == 1
    with engine.connect() as conn:
        adjudication = conn.execute(
            select(
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.candidates_json,
            )
            .join(Country, RulerIdentityAdjudication.country_id == Country.id)
            .where(Country.iso3 == "AAA")
        ).one()
        fact = conn.execute(
            select(CountryYearFact.selected_entity_id, CountryYearFact.adjudication_status)
            .join(Country, CountryYearFact.country_id == Country.id)
            .where(CountryYearFact.field_key == "principal_ruler", Country.iso3 == "AAA")
        ).one()
    candidates = json.loads(adjudication.candidates_json)
    research_candidate = next(
        item for item in candidates if item["source_slug"] == "internet_research_adjudication"
    )
    assert adjudication.selected_ruler_year_id is None
    assert adjudication.review_status == "needs_review"
    assert hard_marker in research_candidate["source_notes"].casefold()
    assert fact.selected_entity_id is None
    assert fact.adjudication_status == "needs_review"


def test_second_pass_year_coverage_majority_resolves_transition_review_row(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "transition-jan-mar",
                source_slug="source_a",
                leader_name="Quarter Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-03-31"},
            ),
            _identity_observation(
                "transition-apr-dec",
                source_slug="source_a",
                leader_name="Majority Transition Leader",
                year=2023,
                extension={"start_date": "2023-04-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "transition-short-fragment",
                source_slug="source_a",
                leader_name="One Day Acting Leader",
                year=2023,
                extension={"start_date": "2023-12-31", "end_date": "2023-12-31"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert result.classification_counts["resolved_auto_year_coverage_majority"] == 1
    with engine.connect() as conn:
        adjudication = conn.execute(
            select(
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_leader_name,
                RulerIdentityAdjudication.selection_rule,
                RulerIdentityAdjudication.candidates_json,
                RulerIdentityAdjudication.research_prompt,
            ).where(
                RulerIdentityAdjudication.classification
                == "resolved_auto_year_coverage_majority"
            )
        ).one()
        fact = conn.execute(
            select(
                CountryYearFact.selected_value_text,
                CountryYearFact.selected_entity_id,
                CountryYearFact.selection_rule,
                CountryYearFact.adjudication_status,
                CountryYearFact.temporal_fit_score,
                CountryYearFact.candidate_values_json,
                CountryYearFact.quality_signals_json,
            ).where(
                CountryYearFact.field_key == "principal_ruler",
                CountryYearFact.selection_rule == "year_coverage_majority",
            )
        ).one()
    candidates = json.loads(adjudication.candidates_json)
    assert adjudication.review_status == "auto_resolved"
    assert adjudication.selected_leader_name == "Majority Transition Leader"
    assert adjudication.selection_rule == "year_coverage_majority"
    assert adjudication.research_prompt is None
    assert {item["leader_name"]: item["year_coverage_days"] for item in candidates} == {
        "Quarter Leader": 90,
        "Majority Transition Leader": 275,
        "One Day Acting Leader": 1,
    }
    assert fact.selected_value_text == "Majority Transition Leader"
    assert fact.selected_entity_id is not None
    assert fact.selection_rule == "year_coverage_majority"
    assert fact.adjudication_status == "auto_resolved"
    assert fact.temporal_fit_score == pytest.approx(275 / 365)
    assert "year_coverage_ratio" in fact.candidate_values_json
    assert json.loads(fact.quality_signals_json)["temporal_fit_score"] == pytest.approx(275 / 365)


def test_second_pass_clear_margin_below_majority_remains_needs_review(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "submajority-leading",
                source_slug="source_a",
                leader_name="Submajority Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-06-17"},
            ),
            _identity_observation(
                "submajority-runner-up",
                source_slug="source_a",
                leader_name="Runner Up Fragment",
                year=2023,
                extension={"start_date": "2023-07-01", "end_date": "2023-07-31"},
            ),
            _identity_observation(
                "submajority-short-fragment",
                source_slug="source_a",
                leader_name="Short Fragment",
                year=2023,
                extension={"start_date": "2023-08-01", "end_date": "2023-08-01"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert "resolved_auto_year_coverage_majority" not in result.classification_counts
    assert result.classification_counts["multiple_candidates_manual_review"] == 1
    with engine.connect() as conn:
        adjudication = conn.execute(
            select(
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.selected_leader_name,
                RulerIdentityAdjudication.selection_rule,
                RulerIdentityAdjudication.candidates_json,
                RulerIdentityAdjudication.research_prompt,
            ).where(
                RulerIdentityAdjudication.classification == "multiple_candidates_manual_review"
            )
        ).one()
        fact = conn.execute(
            select(
                CountryYearFact.selected_value_text,
                CountryYearFact.selected_entity_id,
                CountryYearFact.selection_rule,
                CountryYearFact.adjudication_status,
                CountryYearFact.temporal_fit_score,
                CountryYearFact.candidate_values_json,
                CountryYearFact.research_prompt,
            )
            .join(Country, CountryYearFact.country_id == Country.id)
            .where(CountryYearFact.field_key == "principal_ruler", Country.iso3 == "AAA")
        ).one()
    candidates = json.loads(adjudication.candidates_json)
    assert adjudication.review_status == "needs_review"
    assert adjudication.selected_ruler_year_id is None
    assert adjudication.selected_leader_name is None
    assert adjudication.selection_rule == "manual_or_research_required"
    assert {item["leader_name"]: item["year_coverage_days"] for item in candidates} == {
        "Submajority Leader": 168,
        "Runner Up Fragment": 31,
        "Short Fragment": 1,
    }
    assert "Submajority Leader" in adjudication.research_prompt
    assert fact.selected_value_text is None
    assert fact.selected_entity_id is None
    assert fact.selection_rule == "manual_or_research_required"
    assert fact.adjudication_status == "needs_review"
    assert fact.temporal_fit_score is None
    assert "Submajority Leader" in fact.candidate_values_json
    assert "Submajority Leader" in fact.research_prompt


def test_second_pass_tiny_fragments_remain_needs_review_with_prompt(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=1953, end_year=1953)
    write_observations(
        engine,
        [
            _identity_observation(
                "tiny-jan",
                source_slug="source_a",
                leader_name="January Fragment",
                year=1953,
                extension={"start_date": "1953-01-01", "end_date": "1953-01-31"},
            ),
            _identity_observation(
                "tiny-sep",
                source_slug="source_a",
                leader_name="September Fragment",
                year=1953,
                extension={"start_date": "1953-09-01", "end_date": "1953-09-30"},
            ),
            _identity_observation(
                "tiny-oct",
                source_slug="source_a",
                leader_name="October Fragment",
                year=1953,
                extension={"start_date": "1953-10-01", "end_date": "1953-10-31"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=1953, end_year=1953)

    result = build_ruler_identity_adjudications(engine, start_year=1953, end_year=1953)

    assert result.classification_counts["multiple_candidates_manual_review"] == 1
    with engine.connect() as conn:
        row = conn.execute(
            select(
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_ruler_year_id,
                RulerIdentityAdjudication.research_prompt,
                RulerIdentityAdjudication.candidates_json,
            ).where(RulerIdentityAdjudication.classification == "multiple_candidates_manual_review")
        ).one()
    assert row.review_status == "needs_review"
    assert row.selected_ruler_year_id is None
    assert "Who was the principal/dominant ruler of Alpha (AAA) in 1953?" in row.research_prompt
    assert {item["year_coverage_days"] for item in json.loads(row.candidates_json)} == {30, 31}


def test_second_pass_hard_conflict_flag_blocks_year_coverage_auto_resolution(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "hard-short",
                source_slug="source_a",
                leader_name="Short Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-01-31"},
            ),
            _identity_observation(
                "hard-majority",
                source_slug="source_a",
                leader_name="Coup Majority Leader",
                year=2023,
                extension={
                    "start_date": "2023-02-01",
                    "end_date": "2023-12-31",
                    "rule_type": "coup",
                },
            ),
            _identity_observation(
                "hard-fragment",
                source_slug="source_a",
                leader_name="Fragment Leader",
                year=2023,
                extension={"start_date": "2023-03-01", "end_date": "2023-03-01"},
            ),
        ],
    )
    build_ruler_identity(engine, start_year=2023, end_year=2023)

    result = build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert "resolved_auto_year_coverage_majority" not in result.classification_counts
    assert result.classification_counts["multiple_candidates_manual_review"] == 1
    with engine.connect() as conn:
        row = conn.execute(
            select(
                RulerIdentityAdjudication.review_status,
                RulerIdentityAdjudication.selected_leader_name,
                RulerIdentityAdjudication.research_prompt,
            ).where(RulerIdentityAdjudication.classification == "multiple_candidates_manual_review")
        ).one()
    assert row.review_status == "needs_review"
    assert row.selected_leader_name is None
    assert "Coup Majority Leader" in row.research_prompt


def test_adjudication_single_disputed_candidate_requires_review(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "single-disputed",
                leader_name="Disputed Leader",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "disputed_rule_flag": True,
                    "confidence_score": 90,
                },
            )
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == "disputed_rule"
    with engine.connect() as conn:
        row = conn.execute(
            select(RulerYear.match_status, RulerYear.review_status, RulerYear.review_note)
        ).one()
    assert row.match_status == "disputed_rule"
    assert row.review_status == "needs_review"
    assert "manual_hard_conflict" in row.review_note


@pytest.mark.parametrize("rule_type", ["disputed", "de-facto", "de facto"])
def test_adjudication_hard_rule_type_blocks_role_priority(
    database_url: str,
    rule_type: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                f"formal-{rule_type}",
                leader_name="Formal Leader",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "is_actual_ruler": False,
                    "is_formal_leader": True,
                    "office_title": "President",
                    "confidence_score": 90,
                },
            ),
            _identity_observation(
                f"actual-{rule_type}",
                leader_name="Actual Leader",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "is_actual_ruler": True,
                    "is_formal_leader": True,
                    "office_title": "Prime Minister",
                    "rule_type": rule_type,
                    "confidence_score": 90,
                },
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == (
        "multiple_candidates_manual_review"
    )
    with engine.connect() as conn:
        statuses = conn.execute(select(RulerYear.match_status)).scalars().all()
    assert statuses == ["multiple_candidates_manual_review", "multiple_candidates_manual_review"]


def test_adjudication_alias_variants_collapse_before_conflict(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "alias-a",
                source_slug="source_a",
                leader_name="President Maria Example (acting)",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "alias-b",
                source_slug="source_b",
                leader_name="Maria Example",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == (
        "resolved_auto_single_candidate"
    )
    with engine.connect() as conn:
        assert len(conn.execute(select(Leader)).all()) == 1
        assert len(conn.execute(select(RulerYear)).all()) == 1


def test_adjudication_duration_majority_selects_transition_year_winner(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "short-acting",
                source_slug="source_a",
                leader_name="Short Acting Leader",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-02-15"},
            ),
            _identity_observation(
                "majority-leader",
                source_slug="source_a",
                leader_name="Majority Leader",
                year=2023,
                extension={"start_date": "2023-02-16", "end_date": "2023-12-31"},
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == (
        "resolved_auto_duration_majority"
    )
    with engine.connect() as conn:
        selected_names = conn.execute(select(RulerYear.system_selected_leader_name)).scalars().all()
    assert set(selected_names) == {"Majority Leader"}


def test_adjudication_unresolved_source_conflict_remains_manual(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "conflict-a-2023",
                source_slug="source_a",
                leader_name="Candidate A",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "conflict-b-2023",
                source_slug="source_b",
                leader_name="Candidate B",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
            _identity_observation(
                "conflict-c-2023",
                source_slug="source_c",
                leader_name="Candidate C",
                year=2023,
                extension={"start_date": "2023-01-01", "end_date": "2023-12-31"},
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    assert {row.iso3: row.classification for row in report.rows}["AAA"] == (
        "source_conflict_manual_review"
    )
    with engine.connect() as conn:
        statuses = conn.execute(select(RulerYear.review_status)).scalars().all()
        notes = conn.execute(select(RulerYear.review_note)).scalars().all()
    assert statuses == ["needs_review", "needs_review", "needs_review"]
    assert all("principal ruler not auto-selected" in str(note) for note in notes)


def test_low_confidence_manual_conflict_keeps_manual_classification(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "low-conflict-a",
                source_slug="source_a",
                leader_name="Candidate A",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "confidence_score": 65,
                },
            ),
            _identity_observation(
                "low-conflict-b",
                source_slug="source_b",
                leader_name="Candidate B",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "confidence_score": 65,
                },
            ),
            _identity_observation(
                "low-conflict-c",
                source_slug="source_c",
                leader_name="Candidate C",
                year=2023,
                extension={
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "confidence_score": 65,
                },
            ),
        ],
    )

    build_ruler_identity(engine, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)
    rows = {row.iso3: row for row in report.rows}

    assert rows["AAA"].classification == "source_conflict_manual_review"
    assert rows["AAA"].confidence_min == 45
    assert rows["AAA"].next_action == "Manual adjudication required."


def test_detailed_identity_gap_report_flags_missing_source_range_and_current_cache(
    database_url: str,
) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2023)
    write_observations(
        engine,
        [
            _identity_observation(
                "historical-2022",
                source_slug="reign_fixture",
                family="leader_identity_month",
                country_code="AAA",
                leader_name="Historical Leader",
                year=2022,
                extension={"reign_month": 1},
            )
        ],
    )
    build_ruler_identity(engine)

    report_2023 = build_identity_coverage_gap_report(engine, year=2023)
    classifications_2023 = {row.iso3: row.classification for row in report_2023.rows}
    assert classifications_2023 == {
        "AAA": "missing_source_out_of_range",
        "BBB": "missing_source_out_of_range",
    }

    write_observations(
        engine,
        [
            _identity_observation(
                "wikidata-2022",
                source_slug="wikidata_heads_of_state_government",
                family="leader_identity_country_year",
                indicator_code="wikidata_head_of_government_held",
                country_code="AAA",
                leader_name="Current Leader",
                year=2022,
                extension={"start_date": "2022-01-01", "end_date": "2022-12-31"},
            )
        ],
    )
    build_ruler_identity(engine, start_year=2022, end_year=2022)

    report_2023_after_wikidata = build_identity_coverage_gap_report(engine, year=2023)
    classifications_after = {
        row.iso3: row.classification for row in report_2023_after_wikidata.rows
    }
    assert classifications_after == {
        "AAA": "missing_current_source_cache",
        "BBB": "missing_current_source_cache",
    }


def test_identity_gap_report_writes_json_csv_and_markdown_artifacts(
    database_url: str,
    tmp_path,
) -> None:
    engine = _init_grid(database_url, start_year=2023, end_year=2023)
    report = build_identity_coverage_gap_report(engine, year=2023)

    paths = write_identity_gap_report_artifacts(report, output_dir=tmp_path)

    assert set(paths) == {"json", "csv", "markdown"}
    assert (
        json.loads(paths["json"].read_text(encoding="utf-8"))["summary"]["total_country_years"] == 2
    )
    assert "classification" in paths["csv"].read_text(encoding="utf-8")
    assert "Ruler identity coverage/gap report" in paths["markdown"].read_text(encoding="utf-8")


@pytest.mark.parametrize("output_format", ["json", "csv", "markdown"])
def test_identity_cli_detail_write_artifact_outputs_files_for_all_formats(
    database_url: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    output_format: str,
) -> None:
    _init_grid(database_url, start_year=2023, end_year=2023)
    monkeypatch.setattr(identity_coverage, "outputs_dir", lambda: tmp_path)

    result = runner.invoke(
        app,
        [
            "identity",
            "ruler-coverage",
            "--year",
            "2023",
            "--detail",
            "--write-artifact",
            "--output",
            output_format,
            "--db-url",
            database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    json_path = tmp_path / "identity_ruler_coverage_2023_gap_report.json"
    csv_path = tmp_path / "identity_ruler_coverage_2023_gap_report.csv"
    markdown_path = tmp_path / "identity_ruler_coverage_2023_gap_report.md"
    assert f"json_artifact: {json_path}" in result.stdout
    assert f"csv_artifact: {csv_path}" in result.stdout
    assert f"markdown_artifact: {markdown_path}" in result.stdout
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["classification_counts"] == {
        "missing_source_out_of_range": 2
    }
    assert payload["rows"][0]["classification"] == "missing_source_out_of_range"
    assert "missing_source_out_of_range" in csv_path.read_text(encoding="utf-8")
    assert "Ruler identity coverage/gap report" in markdown_path.read_text(encoding="utf-8")

    if output_format == "json":
        assert '"classification_counts"' in result.stdout
    elif output_format == "csv":
        assert "classification" in result.stdout
    else:
        assert "# Ruler identity coverage/gap report" in result.stdout


def test_identity_cli_build_and_coverage_json(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2022)
    write_observations(
        engine,
        [
            _identity_observation(
                "cli-spell",
                extension={"start_date": "2022-01-01", "end_date": "2022-12-31"},
            )
        ],
    )

    build_result = runner.invoke(
        app,
        ["identity", "build-ruler-years", "--db-url", database_url],
    )
    assert build_result.exit_code == 0, build_result.stdout
    assert "ruler_years_created: 1" in build_result.stdout

    coverage_result = runner.invoke(
        app,
        ["identity", "ruler-coverage", "--year", "2022", "--json", "--db-url", database_url],
    )
    assert coverage_result.exit_code == 0, coverage_result.stdout
    payload = json.loads(coverage_result.stdout)
    assert payload["covered_country_years"] == 1
    assert payload["missing_country_years"] == 1

    detail_result = runner.invoke(
        app,
        [
            "identity",
            "ruler-coverage",
            "--year",
            "2022",
            "--detail",
            "--output",
            "json",
            "--db-url",
            database_url,
        ],
    )
    assert detail_result.exit_code == 0, detail_result.stdout
    detail_payload = json.loads(detail_result.stdout)
    assert detail_payload["summary"]["classification_counts"] == {
        "missing_no_identity_observation": 1,
        "resolved_auto_single_candidate": 1,
    }
    assert len(detail_payload["rows"]) == 2


def test_identity_cli_build_adjudications_json(database_url: str) -> None:
    engine = _init_grid(database_url, start_year=2022, end_year=2022)
    write_observations(
        engine,
        [
            _identity_observation(
                "cli-adjudication-spell",
                extension={"start_date": "2022-01-01", "end_date": "2022-12-31"},
            )
        ],
    )
    build_ruler_identity(engine)

    result = runner.invoke(
        app,
        [
            "identity",
            "build-adjudications",
            "--start-year",
            "2022",
            "--end-year",
            "2022",
            "--json",
            "--db-url",
            database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["rows_created"] == 2
    assert payload["fact_rows_created"] == 2
    assert payload["review_status_counts"] == {
        "auto_resolved": 1,
        "research_required": 1,
    }

    coverage_result = runner.invoke(
        app,
        [
            "identity",
            "adjudication-coverage",
            "--start-year",
            "2022",
            "--end-year",
            "2022",
            "--json",
            "--db-url",
            database_url,
        ],
    )
    assert coverage_result.exit_code == 0, coverage_result.stdout
    coverage_payload = json.loads(coverage_result.stdout)
    assert coverage_payload["total_rows"] == 2


def test_identity_cli_fails_friendly_when_db_uninitialized(database_url: str) -> None:
    result = runner.invoke(
        app,
        ["identity", "ruler-coverage", "--db-url", database_url, "--json"],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert "local ruler identity database is not initialized" in payload["error"]
    assert "leaders-db init-db" in payload["error"]
    assert "no such table" not in payload["error"].lower()


def test_identity_cli_fails_friendly_before_scope_grid(database_url: str) -> None:
    init_database(database_url)

    coverage_result = runner.invoke(
        app,
        ["identity", "ruler-coverage", "--db-url", database_url, "--json"],
    )
    assert coverage_result.exit_code == 1, coverage_result.stdout
    payload = json.loads(coverage_result.stdout)
    assert "scope build-country-years" in payload["error"]
    assert "No included country_years rows" in payload["error"]

    build_result = runner.invoke(
        app,
        ["identity", "build-ruler-years", "--db-url", database_url],
    )
    assert build_result.exit_code == 1, build_result.stdout
    assert "scope build-country-years" in build_result.stdout
