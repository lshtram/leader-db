from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from leaders_db.db.engine import init_database
from leaders_db.research.sql_repository import (
    SqlEvidenceRepository,
    observation_to_row,
    row_to_observation,
    write_observations,
)
from leaders_db.sources.contracts import (
    EvidenceQuery,
    NormalizedObservation,
    RawLocator,
    SourceId,
    SourceWarning,
    TransformLocator,
)


def test_normalized_observations_migration_exists(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)

    columns = {c["name"] for c in inspect(engine).get_columns("normalized_observations")}

    assert {
        "source_slug",
        "observation_id",
        "observation_family",
        "indicator_code",
        "value_json",
        "raw_locator_json",
        "transform_locator_json",
        "scope_json",
    }.issubset(columns)


def test_observation_serialization_round_trips() -> None:
    observation = _observation()

    row = observation_to_row(observation)
    restored = row_to_observation(row)

    assert restored == observation
    assert row["scope_json"] == '{"country":"USA","country_name":"United States","year":2020}'


def test_sql_repository_filters_and_preserves_traceability(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(),
            _observation(
                source_slug="other_source",
                observation_id="other-usa-2020",
                indicator_code="other_indicator",
            ),
        ),
    )
    repository = SqlEvidenceRepository(engine)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug="ucdp"),),
            observation_families=("conflict",),
            indicator_codes=("conflict_fatalities",),
            years=(2020,),
            countries=("USA",),
        )
    )

    assert len(rows) == 1
    assert rows[0].observation_id == "ucdp-usa-2020"
    assert rows[0].raw_locator.url == "https://example.test/ucdp.csv"
    assert rows[0].raw_locator.row_number == 7
    assert rows[0].transform_locator.rule_id == "fixture-rule"
    assert rows[0].extension["retrieved_at"] == "2026-06-28"


@pytest.mark.parametrize(
    ("query", "nonmatching_kwargs"),
    [
        (
            EvidenceQuery(source_ids=(SourceId(slug="ucdp"),)),
            {"source_slug": "other_source", "observation_id": "other-source"},
        ),
        (
            EvidenceQuery(observation_families=("conflict",)),
            {"observation_family": "economy", "observation_id": "other-family"},
        ),
        (
            EvidenceQuery(indicator_codes=("conflict_fatalities",)),
            {"indicator_code": "other_indicator", "observation_id": "other-indicator"},
        ),
        (
            EvidenceQuery(years=(2020,)),
            {"year": 2021, "observation_id": "other-year"},
        ),
        (
            EvidenceQuery(countries=("USA",)),
            {
                "country_code": "CAN",
                "country_name": "Canada",
                "observation_id": "other-country",
            },
        ),
    ],
)
def test_sql_repository_filters_each_dimension_independently(
    database_url: str,
    query: EvidenceQuery,
    nonmatching_kwargs: dict[str, object],
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(engine, (_observation(), _observation(**nonmatching_kwargs)))

    rows = SqlEvidenceRepository(engine).query_observations(query)

    assert tuple(row.observation_id for row in rows) == ("ucdp-usa-2020",)


@pytest.mark.parametrize("leader", ["leader-1", "Leader One"])
def test_sql_repository_filters_by_leader_id_or_name(
    database_url: str,
    leader: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(leader_id="leader-1", leader_name="Leader One"),
            _observation(
                observation_id="other-leader",
                leader_id="leader-2",
                leader_name="Leader Two",
            ),
        ),
    )

    rows = SqlEvidenceRepository(engine).query_observations(EvidenceQuery(leaders=(leader,)))

    assert tuple(row.observation_id for row in rows) == ("ucdp-usa-2020",)


def test_sql_repository_upsert_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    observation = _observation()

    write_observations(engine, (observation,))
    write_observations(engine, (observation,))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM normalized_observations")).scalar_one()
    assert count == 1


def test_sql_repository_does_not_read_raw_files(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(engine, (_observation(),))
    repository = SqlEvidenceRepository(engine)

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("raw files must not be opened during evidence queries")

    monkeypatch.setattr(Path, "open", fail_open)

    rows = repository.query_observations(EvidenceQuery(countries=("USA",)))

    assert len(rows) == 1


def _observation(
    *,
    source_slug: str = "ucdp",
    observation_id: str = "ucdp-usa-2020",
    observation_family: str = "conflict",
    indicator_code: str = "conflict_fatalities",
    year: int | None = 2020,
    country_code: str | None = "USA",
    country_name: str | None = "United States",
    leader_id: str | None = None,
    leader_name: str | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=observation_id,
        observation_family=observation_family,
        indicator_code=indicator_code,
        value=12,
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=leader_id,
        leader_name=leader_name,
        unit="deaths",
        scale=None,
        source_version="fixture-v1",
        raw_locator=RawLocator(
            asset_id="ucdp-fixture",
            url="https://example.test/ucdp.csv",
            row_number=7,
            column_name="best",
        ),
        transform_locator=TransformLocator(
            transform_name="fixture-transform",
            rule_id="fixture-rule",
        ),
        quality_flags=("fixture_quality",),
        warnings=(
            SourceWarning(
                code="fixture_warning",
                message="fixture warning",
                source_id=SourceId(slug=source_slug),
            ),
        ),
        extension={"retrieved_at": "2026-06-28"},
    )
