from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country, CountryYear, CountryYearFact
from leaders_db.facts import publish_concept_country_year_facts
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import (
    BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
    CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,
    CONCEPT_BTI_GOVERNANCE_INDEX,
    CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
    CONCEPT_CPI_SCORE,
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_GOVERNMENT_EFFECTIVENESS,
    CONCEPT_MILITARY_SPEND_CONSTANT_USD,
    CONCEPT_MILITARY_SPEND_SHARE_GDP,
    CONCEPT_NUCLEAR_TOTAL_INVENTORY,
    CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
    CONCEPT_POLITICAL_LIBERTIES,
    CONCEPT_POPULATION,
    CONCEPT_PTS_AMNESTY_SCORE,
    CONCEPT_STATE_BASED_CONFLICT_EVENTS,
    FAS_TOTAL_INVENTORY_INDICATOR_CODE,
    FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
    PTS_AMNESTY_SCORE_INDICATOR_CODE,
    PWT_POPULATION_INDICATOR_CODE,
    SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE,
    SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
    TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,
    UCDP_ONE_SIDED_EVENTS_INDICATOR_CODE,
    UCDP_STATE_BASED_EVENTS_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
    WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
)


def test_publish_concept_country_year_facts_selects_preferred_numeric_source(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="pwt",
                indicator_code=PWT_POPULATION_INDICATOR_CODE,
                observation_id="pwt-usa-2020-pop",
                value=330_000,
                unit="thousands_of_persons",
            ),
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
        run_id="test-run",
    )

    assert result.rows_created == 1
    assert result.rows_updated == 0
    assert result.total_rows == 1
    assert result.field_counts == {CONCEPT_POPULATION: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_POPULATION
        assert fact.field_label == "Country population"
        assert fact.selected_value_number == 331_000_000
        assert fact.selected_value_text == "331000000"
        assert fact.adjudication_status == "auto_resolved"
        assert fact.confidence_score == 60
        assert fact.agreement_score == 0
        assert fact.authority_score == 100
        assert fact.specificity_score == 80
        assert fact.temporal_fit_score == 100
        assert fact.source_slugs_json == '["world_bank_wdi","pwt"]'
        assert fact.source_observation_ids_json == ('["wdi-usa-2020-pop","pwt-usa-2020-pop"]')
        selected = json.loads(fact.selected_value_json or "{}")
        assert selected["source_slug"] == "world_bank_wdi"
        candidates = json.loads(fact.candidate_values_json)
        assert [candidate["source_slug"] for candidate in candidates] == [
            "world_bank_wdi",
            "pwt",
        ]
        assert [candidate["selection_role"] for candidate in candidates] == [
            "selected",
            "alternative",
        ]
        quality = json.loads(fact.quality_signals_json)
        assert quality["confidence_components"] == {
            "agreement": 0,
            "authority": 100,
            "specificity": 80,
            "temporal_fit": 100,
        }


def test_publish_concept_country_year_facts_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                observation_id="wdi-usa-2020-gdppc",
                value=65000.0,
                unit="current_usd_per_person",
            ),
        ),
    )

    first = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )
    second = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )

    assert first.rows_created == 1
    assert second.rows_created == 0
    assert second.rows_updated == 0
    with Session(engine) as session:
        facts = session.scalars(select(CountryYearFact)).all()
    assert len(facts) == 1


def test_gdp_nominal_and_ppp_observations_publish_as_distinct_facts(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                observation_id="wdi-usa-2020-gdppc-nominal",
                value=65_000.0,
                unit="current_usd_per_person",
            ),
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
                observation_id="wdi-usa-2020-gdppc-ppp",
                value=60_000.0,
                unit="constant_2017_international_dollars_per_person",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )

    assert result.rows_created == 2
    assert result.field_counts == {
        "gdp_per_capita_nominal_current_usd": 1,
        "gdp_per_capita_ppp_constant_2017_intl": 1,
    }
    with Session(engine) as session:
        facts = session.scalars(select(CountryYearFact)).all()
    by_key = {fact.field_key: fact for fact in facts}
    assert set(by_key) == {
        "gdp_per_capita_nominal_current_usd",
        "gdp_per_capita_ppp_constant_2017_intl",
    }
    assert json.loads(
        by_key["gdp_per_capita_nominal_current_usd"].candidate_values_json
    )[0]["input_observation_ids"] == ["wdi-usa-2020-gdppc-nominal"]
    assert json.loads(
        by_key["gdp_per_capita_ppp_constant_2017_intl"].candidate_values_json
    )[0]["input_observation_ids"] == ["wdi-usa-2020-gdppc-ppp"]


def test_duplicate_observations_from_one_source_do_not_increase_agreement(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop-a",
                value=331_000_000,
                unit="persons",
            ),
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop-b",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
    )

    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
    assert fact is not None
    assert fact.agreement_score == 0
    assert fact.confidence_score == 60


def test_publish_concept_country_year_facts_skips_rows_outside_scope(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
    )

    assert result.rows_created == 0
    assert result.skipped_without_country_year == 1
    with Session(engine) as session:
        assert session.scalars(select(CountryYearFact)).all() == []


def test_publish_concept_country_year_facts_respects_year_window(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2020)
    _seed_country_year(engine, year=2021, iso3="CAN", country_name="Canada")
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
                year=2020,
                country_code="USA",
                country_name="United States",
            ),
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-can-2021-pop",
                value=38_000_000,
                unit="persons",
                year=2021,
                country_code="CAN",
                country_name="Canada",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
        start_year=2021,
        end_year=2021,
    )

    assert result.rows_created == 1
    assert result.total_rows == 1
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.year == 2021
        assert fact.selected_value_number == 38_000_000


def test_publish_concept_country_year_facts_persists_missing_values_for_review(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop-missing",
                value=None,
                value_type="missing",
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
    )

    assert result.rows_created == 1
    assert result.adjudication_status_counts == {"needs_review": 1}
    assert [warning.code for warning in result.warnings] == ["missing_value"]
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.value_type == "missing"
        assert fact.selected_value_number is None
        assert fact.adjudication_status == "needs_review"
        assert fact.review_reason == "selected concept value is missing"
        assert fact.recommended_next_action == "review missing concept value"
        warnings = json.loads(fact.warnings_json)
        assert warnings[0]["code"] == "missing_value"


def test_publish_concept_country_year_facts_resolves_country_name_fallback(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2014)
    write_observations(
        engine,
        (
            _observation(
                source_slug="fas",
                indicator_code=FAS_TOTAL_INVENTORY_INDICATOR_CODE,
                observation_id="fas:United States:2014:fas_total_inventory",
                value=5244,
                unit="warheads",
                year=2014,
                country_code=None,
                country_name="United States",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_NUCLEAR_TOTAL_INVENTORY,),
        start_year=2014,
        end_year=2014,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_NUCLEAR_TOTAL_INVENTORY: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_NUCLEAR_TOTAL_INVENTORY
        assert fact.selected_value_number == 5244
        assert fact.source_slugs_json == '["fas"]'


def test_publish_concept_country_year_facts_publishes_sipri_milex_by_country_name(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(
        engine,
        year=2023,
        iso3="USA",
        country_name="United States of America",
    )
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
                observation_id="sipri_milex:United States of America:2023:sipri_milex_share_of_gdp",
                value=0.033,
                unit="percent",
                year=2023,
                country_code=None,
                country_name="United States of America",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_SHARE_GDP,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_MILITARY_SPEND_SHARE_GDP: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_MILITARY_SPEND_SHARE_GDP
        assert fact.field_label == "Military expenditure share of GDP"
        assert fact.selected_value_number == 0.033
        assert fact.source_slugs_json == '["sipri_milex"]'


def test_publish_concept_country_year_facts_publishes_sipri_milex_alias_name(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(
        engine,
        year=2023,
        iso3="COD",
        country_name="Congo, The Democratic Republic of the",
    )
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
                observation_id="sipri_milex:Congo, DR:2023:sipri_milex_share_of_gdp",
                value=0.011,
                unit="percent",
                year=2023,
                country_code=None,
                country_name="Congo, DR",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_SHARE_GDP,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_MILITARY_SPEND_SHARE_GDP
        assert fact.selected_value_number == 0.011
        assert fact.source_slugs_json == '["sipri_milex"]'


def test_publish_concept_country_year_facts_skips_sipri_milex_european_union_aggregate(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="DEU", country_name="Germany")
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
                observation_id="sipri_milex:European Union:2023:sipri_milex_share_of_gdp",
                value=1.6,
                unit="percent",
                year=2023,
                country_code=None,
                country_name="European Union",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_SHARE_GDP,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 0
    assert result.field_counts == {}
    with Session(engine) as session:
        assert session.scalar(select(CountryYearFact)) is None


def test_publish_concept_country_year_facts_resolves_lifecycle_source_name(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=1990, iso3="SUN", country_name="Soviet Union")
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE,
                observation_id="sipri_milex:USSR:1990:sipri_milex_constant_usd",
                value=250_000.0,
                unit="usd_millions_2024",
                year=1990,
                country_code=None,
                country_name="USSR",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_CONSTANT_USD,),
        start_year=1990,
        end_year=1990,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_MILITARY_SPEND_CONSTANT_USD
        assert fact.selected_value_number == 250_000.0
        assert fact.source_slugs_json == '["sipri_milex"]'
        assert json.loads(fact.selected_value_json or "{}")["unit"] == (
            "usd_millions_2024"
        )
        warning_codes = {item["code"] for item in json.loads(fact.warnings_json)}
        assert warning_codes == {
            "military_spending_not_aggression",
            "sipri_exact_unit",
        }


def test_publish_concept_country_year_facts_resolves_sipri_east_germany(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(
        engine,
        year=1989,
        iso3="DDR",
        country_name="German Democratic Republic",
    )
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE,
                observation_id=(
                    "sipri_milex:German Democratic Republic:1989:"
                    "sipri_milex_constant_usd"
                ),
                value=12_345.0,
                unit="usd_millions",
                year=1989,
                country_code=None,
                country_name="German Democratic Republic",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_CONSTANT_USD,),
        start_year=1989,
        end_year=1989,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_MILITARY_SPEND_CONSTANT_USD
        assert fact.selected_value_number == 12_345.0
        assert fact.source_slugs_json == '["sipri_milex"]'


def test_publish_concept_country_year_facts_resolves_sipri_kosovo(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="XKX", country_name="Kosovo")
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
                observation_id="sipri_milex:Kosovo:2023:sipri_milex_share_of_gdp",
                value=0.014,
                unit="percent",
                year=2023,
                country_code=None,
                country_name="Kosovo",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_SHARE_GDP,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_MILITARY_SPEND_SHARE_GDP
        assert fact.selected_value_number == 0.014
        assert fact.source_slugs_json == '["sipri_milex"]'


def test_publish_concept_country_year_facts_publishes_freedom_house(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="USA", country_name="United States")
    write_observations(
        engine,
        (
            _observation(
                source_slug="freedom_house",
                indicator_code=FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
                observation_id=(
                    "freedom_house:country:United States:2023:"
                    "freedom_house_political_rights"
                ),
                value=1,
                unit="rating",
                year=2023,
                country_code=None,
                country_name="United States",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POLITICAL_LIBERTIES,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_POLITICAL_LIBERTIES: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_POLITICAL_LIBERTIES
        assert fact.field_label == "Political civil liberties"
        assert fact.selected_value_number == 1
        assert fact.source_slugs_json == '["freedom_house"]'


def test_publish_concept_country_year_facts_skips_sipri_european_union(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                source_slug="sipri_milex",
                indicator_code=SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,
                observation_id="sipri_milex:European Union:2023:sipri_milex_share_of_gdp",
                value=0.013,
                unit="percent",
                year=2023,
                country_code=None,
                country_name="European Union",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_MILITARY_SPEND_SHARE_GDP,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 0
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {}
    with Session(engine) as session:
        assert session.scalar(select(CountryYearFact)) is None


def test_publish_concept_country_year_facts_resolves_ucdp_country_id(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2022, iso3="RUS", country_name="Russia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="ucdp",
                indicator_code=UCDP_STATE_BASED_EVENTS_INDICATOR_CODE,
                observation_id="ucdp:365:2022:ucdp_state_based_events",
                value=3,
                unit="count",
                year=2022,
                country_code="365",
                country_name=None,
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_STATE_BASED_CONFLICT_EVENTS,),
        start_year=2022,
        end_year=2022,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_STATE_BASED_CONFLICT_EVENTS: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_STATE_BASED_CONFLICT_EVENTS
        assert fact.field_label == "State-based conflict events"
        assert fact.selected_value_number == 3
        assert fact.source_slugs_json == '["ucdp"]'
        assert {item["code"] for item in json.loads(fact.warnings_json)} == {
            "ucdp_location_not_responsibility"
        }


def test_publish_concept_country_year_facts_resolves_ucdp_country_id_by_year(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=1999, iso3="YUG", country_name="Yugoslavia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="ucdp",
                indicator_code=UCDP_STATE_BASED_EVENTS_INDICATOR_CODE,
                observation_id="ucdp:345:1999:ucdp_state_based_events",
                value=341,
                unit="count",
                year=1999,
                country_code="345",
                country_name=None,
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_STATE_BASED_CONFLICT_EVENTS,),
        start_year=1999,
        end_year=1999,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_STATE_BASED_CONFLICT_EVENTS
        assert fact.selected_value_number == 341
        assert fact.source_slugs_json == '["ucdp"]'


def test_publish_concept_country_year_facts_skips_post_lifecycle_ucdp_dense_zero(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="SRB", country_name="Serbia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="ucdp",
                indicator_code=UCDP_STATE_BASED_EVENTS_INDICATOR_CODE,
                observation_id="ucdp:345:2023:ucdp_state_based_events",
                value=0,
                unit="count",
                year=2023,
                country_code="345",
                country_name=None,
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_STATE_BASED_CONFLICT_EVENTS,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 0
    assert result.field_counts == {}
    with Session(engine) as session:
        assert session.scalar(select(CountryYearFact)) is None


def test_publish_concept_country_year_facts_publishes_ucdp_one_sided_violence(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2022, iso3="RUS", country_name="Russia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="ucdp",
                indicator_code=UCDP_ONE_SIDED_EVENTS_INDICATOR_CODE,
                observation_id="ucdp:365:2022:ucdp_onesided_events",
                value=2,
                unit="count",
                year=2022,
                country_code="365",
                country_name=None,
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,),
        start_year=2022,
        end_year=2022,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_ONE_SIDED_VIOLENCE_EVENTS: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_ONE_SIDED_VIOLENCE_EVENTS
        assert fact.field_label == "One-sided violence events"
        assert fact.selected_value_number == 2
        assert fact.source_slugs_json == '["ucdp"]'


def test_publish_concept_country_year_facts_publishes_transparency_cpi(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="USA", country_name="United States")
    write_observations(
        engine,
        (
            _observation(
                source_slug="transparency_cpi",
                indicator_code=TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,
                observation_id="transparency_cpi:USA:2023:cpi_score",
                value=69.0,
                unit="score_0_100",
                year=2023,
                country_code="USA",
                country_name="United States",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_CPI_SCORE,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_CPI_SCORE: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_CPI_SCORE
        assert fact.selected_value_number == 69.0
        assert fact.source_slugs_json == '["transparency_cpi"]'


def test_publish_concept_country_year_facts_publishes_wgi_government_effectiveness(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2022, iso3="USA", country_name="United States")
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wgi",
                indicator_code=WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
                observation_id="world_bank_wgi:USA:2022:wgi_government_effectiveness",
                value=1.31,
                unit="estimate",
                year=2022,
                country_code="USA",
                country_name=None,
                extension={
                    "uncertainty": {
                        "standard_error": 0.12,
                        "percentile_rank_lower_bound": 70.0,
                        "percentile_rank_upper_bound": 82.0,
                    }
                },
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GOVERNMENT_EFFECTIVENESS,),
        start_year=2022,
        end_year=2022,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_GOVERNMENT_EFFECTIVENESS: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_GOVERNMENT_EFFECTIVENESS
        assert fact.field_label == "Government effectiveness"
        assert fact.selected_value_number == 1.31
        assert fact.source_slugs_json == '["world_bank_wgi"]'
        selected = json.loads(fact.selected_value_json or "{}")
        assert selected["extension"]["uncertainty"]["standard_error"] == 0.12


def test_publish_concept_country_year_facts_resolves_wgi_source_code(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2022, iso3="AND", country_name="Andorra")
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wgi",
                indicator_code=WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
                observation_id="world_bank_wgi:ADO:2022:wgi_government_effectiveness",
                value=1.1,
                unit="estimate",
                year=2022,
                country_code="ADO",
                country_name=None,
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GOVERNMENT_EFFECTIVENESS,),
        start_year=2022,
        end_year=2022,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_GOVERNMENT_EFFECTIVENESS: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_GOVERNMENT_EFFECTIVENESS
        assert fact.selected_value_number == 1.1
        assert fact.source_slugs_json == '["world_bank_wgi"]'


def test_publish_concept_country_year_facts_resolves_cpi_source_code(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="XKX", country_name="Kosovo")
    write_observations(
        engine,
        (
            _observation(
                source_slug="transparency_cpi",
                indicator_code=TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,
                observation_id="transparency_cpi:KSV:2023:cpi_score",
                value=41,
                unit="score_0_100",
                year=2023,
                country_code="KSV",
                country_name="Kosovo",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_CPI_SCORE,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_CPI_SCORE: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_CPI_SCORE
        assert fact.selected_value_number == 41
        assert fact.source_slugs_json == '["transparency_cpi"]'


def test_publish_concept_country_year_facts_publishes_bti_name_only_country(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="COG", country_name="Republic of Congo")
    write_observations(
        engine,
        (
            _observation(
                source_slug="bti",
                indicator_code=BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
                observation_id="bti:Congo, Rep.:2023:bti_governance_index",
                value=4.9,
                unit="index",
                year=2023,
                country_code=None,
                country_name="Congo, Rep.",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_BTI_GOVERNANCE_INDEX,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_BTI_GOVERNANCE_INDEX: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_BTI_GOVERNANCE_INDEX
        assert fact.field_label == "BTI governance index"
        assert fact.selected_value_number == 4.9
        assert fact.source_slugs_json == '["bti"]'


def test_publish_concept_country_year_facts_publishes_bti_kosovo(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="XKX", country_name="Kosovo")
    write_observations(
        engine,
        (
            _observation(
                source_slug="bti",
                indicator_code=BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
                observation_id="bti:Kosovo:2023:bti_governance_index",
                value=5.1,
                unit="index",
                year=2023,
                country_code=None,
                country_name="Kosovo",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_BTI_GOVERNANCE_INDEX,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_BTI_GOVERNANCE_INDEX: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_BTI_GOVERNANCE_INDEX
        assert fact.selected_value_number == 5.1
        assert fact.source_slugs_json == '["bti"]'


def test_publish_concept_country_year_facts_resolves_bti_turkiye_decomposed_name(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023, iso3="TUR", country_name="Türkiye")
    write_observations(
        engine,
        (
            _observation(
                source_slug="bti",
                indicator_code=BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
                observation_id="bti:Türkiye:2023:bti_governance_index",
                value=4.2,
                unit="index",
                year=2023,
                country_code=None,
                country_name="Türkiye",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_BTI_GOVERNANCE_INDEX,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_BTI_GOVERNANCE_INDEX: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_BTI_GOVERNANCE_INDEX
        assert fact.selected_value_number == 4.2
        assert fact.source_slugs_json == '["bti"]'


def test_publish_concept_country_year_facts_publishes_cirights_name_only_country(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2022, iso3="CIV", country_name="Cote d'Ivoire")
    write_observations(
        engine,
        (
            _observation(
                source_slug="cirights",
                indicator_code=CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,
                observation_id="cirights:Côte d’Ivoire:2022:cirights_physint",
                value=5,
                unit="score",
                year=2022,
                country_code=None,
                country_name="Côte d’Ivoire",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,),
        start_year=2022,
        end_year=2022,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY
        assert fact.field_label == "CIRIGHTS physical integrity"
        assert fact.selected_value_number == 5
        assert fact.source_slugs_json == '["cirights"]'
        assert {item["code"] for item in json.loads(fact.warnings_json)} == {
            "cirights_favorable_code_ambiguity"
        }


def test_publish_concept_country_year_facts_publishes_cirights_yugoslavia(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=1990, iso3="YUG", country_name="Yugoslavia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="cirights",
                indicator_code=CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,
                observation_id="cirights:Yugoslavia:1990:cirights_physint",
                value=4,
                unit="ordinal_score",
                year=1990,
                country_code=None,
                country_name="Yugoslavia",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,),
        start_year=1990,
        end_year=1990,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY
        assert fact.selected_value_number == 4
        assert fact.source_slugs_json == '["cirights"]'


def test_publish_concept_country_year_facts_publishes_pts(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=2023)
    write_observations(
        engine,
        (
            _observation(
                source_slug="pts",
                indicator_code=PTS_AMNESTY_SCORE_INDICATOR_CODE,
                observation_id="pts:USA:2023:pts_amnesty_score",
                value=2,
                unit="ordinal_score",
                year=2023,
                country_code="USA",
                country_name="United States",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_PTS_AMNESTY_SCORE,),
        start_year=2023,
        end_year=2023,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_PTS_AMNESTY_SCORE: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_PTS_AMNESTY_SCORE
        assert fact.field_label == "PTS Amnesty score"
        assert fact.selected_value_number == 2
        assert fact.source_slugs_json == '["pts"]'


def test_publish_concept_country_year_facts_resolves_pts_czechoslovakia(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine, year=1989, iso3="CSK", country_name="Czechoslovakia")
    write_observations(
        engine,
        (
            _observation(
                source_slug="pts",
                indicator_code=PTS_AMNESTY_SCORE_INDICATOR_CODE,
                observation_id="pts:CZE:Czechoslovakia:1989:pts_amnesty_score",
                value=2,
                unit="ordinal_score",
                year=1989,
                country_code="CZE",
                country_name="Czechoslovakia",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_PTS_AMNESTY_SCORE,),
        start_year=1989,
        end_year=1989,
    )

    assert result.rows_created == 1
    assert result.skipped_without_country_year == 0
    assert result.field_counts == {CONCEPT_PTS_AMNESTY_SCORE: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_PTS_AMNESTY_SCORE
        assert fact.selected_value_number == 2
        assert fact.source_slugs_json == '["pts"]'


def _seed_country_year(
    engine: Any,
    *,
    year: int = 2020,
    iso3: str = "USA",
    country_name: str = "United States",
) -> None:
    with Session(engine) as session:
        country = Country(
            iso3=iso3,
            country_name=country_name,
            country_name_normalized=country_name.lower(),
            notes=None,
        )
        session.add(country)
        session.flush()
        session.add(
            CountryYear(
                country_id=country.id,
                year=year,
                included_in_project=True,
                inclusion_reason="test fixture",
            )
        )
        session.commit()


def _observation(
    *,
    source_slug: str,
    indicator_code: str,
    observation_id: str,
    value: Any,
    unit: str,
    value_type: str = "numeric",
    year: int = 2020,
    country_code: str | None = "USA",
    country_name: str = "United States",
    extension: dict[str, Any] | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=observation_id,
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type=value_type,
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=None,
        source_version="fixture",
        raw_locator=RawLocator(asset_id=f"{source_slug}-fixture", json_pointer="/0"),
        transform_locator=TransformLocator(transform_name="fixture_transform"),
        extension=extension or {},
    )
