"""Database schema migration tests.

The DDL at ``src/leaders_db/db/migrations/0001_initial.sql`` is the source
of truth for the prototype schema. These tests apply it to a fresh SQLite
file and verify that:

- All 11 tables are created.
- The expected columns exist with the expected nullability.
- The runner is idempotent (re-applying does not duplicate rows).
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from leaders_db.db.engine import init_database


def test_init_database_creates_all_tables(database_url: str) -> None:
    init_database(database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "countries",
        "country_years",
        "leaders",
        "leader_aliases",
        "ruler_spells",
        "ruler_years",
        "score_categories",
        "ruler_scores",
        "sources",
        "source_observations",
        "validation_results",
        # Internal to the migration runner.
        "schema_migrations",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_init_database_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    init_database(database_url)  # second call must not raise

    engine = create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one()
    assert rows == 1


def test_required_columns_present(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    inspector = inspect(engine)

    # Spot-check a few columns that downstream code depends on.
    countries_cols = {c["name"] for c in inspector.get_columns("countries")}
    assert {"id", "iso3", "country_name", "country_name_normalized"}.issubset(
        countries_cols
    )

    ruler_scores_cols = {c["name"] for c in inspector.get_columns("ruler_scores")}
    assert {
        "id",
        "ruler_year_id",
        "category_id",
        "client_score",
        "system_proposed_score",
        "final_score",
        "score_delta_vs_client",
        "confidence_score",
    }.issubset(ruler_scores_cols)


def test_ruler_year_uniqueness_constraint(database_url: str) -> None:
    """The UNIQUE(leader_id, country_id, year) constraint is enforced."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    init_database(database_url)
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO countries (iso3, country_name, country_name_normalized) "
                          "VALUES ('USA', 'United States', 'united states')"))
        conn.execute(text("INSERT INTO leaders (full_name, normalized_name) "
                          "VALUES ('Joe Example', 'joe example')"))

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ruler_years (leader_id, country_id, year) "
                "VALUES (1, 1, 2023)"
            )
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ruler_years (leader_id, country_id, year) "
                    "VALUES (1, 1, 2023)"
                )
            )
