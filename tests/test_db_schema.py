"""Database schema migration tests.

The ordered SQL files under ``src/leaders_db/db/migrations/`` are the source of
truth for the prototype schema and research evidence store. These tests apply
the migrations to a fresh SQLite file and verify that core tables are created,
expected columns exist, and the runner is idempotent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

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
        "normalized_observations",
        "research_questions",
        "research_question_answers",
        "research_answer_evidence_links",
        "chapter_scores",
        "ruler_identity_adjudications",
        "country_year_facts",
        "research_jobs",
        "research_job_events",
        "research_job_dependencies",
        # Internal to the migration runner.
        "schema_migrations",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_init_database_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    init_database(database_url)  # second call must not raise

    engine = create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
    expected_migrations = {
        path.name
        for path in (Path(__file__).parents[1] / "src/leaders_db/db/migrations").glob(
            "[0-9][0-9][0-9][0-9]_*.sql"
        )
    }
    assert set(rows) == expected_migrations


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

    adjudication_cols = {c["name"] for c in inspector.get_columns("ruler_identity_adjudications")}
    assert {
        "country_year_id",
        "selected_ruler_year_id",
        "candidate_ruler_year_ids_json",
        "candidates_json",
        "classification",
        "selection_rule",
        "review_status",
        "research_prompt",
        "source_slugs_json",
        "source_observation_ids_json",
    }.issubset(adjudication_cols)

    fact_cols = {c["name"] for c in inspector.get_columns("country_year_facts")}
    assert {
        "country_year_id",
        "field_key",
        "value_type",
        "selected_value_text",
        "selected_entity_table",
        "selected_entity_id",
        "candidate_values_json",
        "selection_rule",
        "adjudication_status",
        "confidence_score",
        "agreement_score",
        "authority_score",
        "specificity_score",
        "temporal_fit_score",
        "quality_signals_json",
        "research_prompt",
        "producer",
    }.issubset(fact_cols)

    job_cols = {c["name"] for c in inspector.get_columns("research_jobs")}
    assert {
        "job_key",
        "run_key",
        "job_type",
        "target_year",
        "provider_profile",
        "provider",
        "model",
        "status",
        "attempt_count",
        "max_attempts",
        "claimed_by",
        "lease_expires_at",
        "lease_token",
        "heartbeat_at",
        "checkpoint_json",
        "input_json",
        "result_path",
        "error_json",
        "quarantine_reason",
    }.issubset(job_cols)

    chapter_score_cols = {
        c["name"] for c in inspector.get_columns("chapter_scores")
    }
    assert {
        "ruler_year_id",
        "run_key",
        "job_key",
        "calibration_batch_id",
        "plausible_score_lower",
        "plausible_score_upper",
        "manual_review_required",
        "judgment_json",
    }.issubset(chapter_score_cols)


def test_research_job_check_constraints_are_enforced(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)

    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                """
                INSERT INTO research_jobs (
                    job_key, run_key, job_type, target_year, provider_profile,
                    provider, model, status, max_attempts
                ) VALUES (
                    'invalid', 'test', 'unknown', 2020, 'test',
                    'test', 'test', 'pending', 0
                )
                """
            )
        )


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
