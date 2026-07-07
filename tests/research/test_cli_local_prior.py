from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database

runner = CliRunner()


def test_build_local_prior_cli_outputs_json_and_writes_artifact(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_fact(engine, country_id=1, country_year_id=1, year=2020)
    output_path = tmp_path / "prior.json"

    result = runner.invoke(
        app,
        [
            "research", "build-local-prior", "--methodology-id", "4B.2",
            "--year", "2020", "--iso3", "USA", "--leader", "Donald Trump",
            "--output", str(output_path), "--json", "--db-url", database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    stdout_payload = json.loads(result.stdout)
    assert stdout_payload == json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "evidence_found"
    assert stdout_payload["leader"]["name"] == "Donald Trump"
    assert stdout_payload["local_facts"][0]["source_slugs"] == ["freedom_house"]


def test_build_local_prior_cli_exits_one_for_builder_error_artifact(
    database_url: str,
) -> None:
    init_database(database_url)

    result = runner.invoke(
        app,
        [
            "research", "build-local-prior", "--methodology-id", "UNKNOWN",
            "--year", "2020", "--iso3", "USA", "--db-url", database_url, "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "Unknown methodology question id" in payload["missing_or_empty_reason"]


def test_build_local_prior_slice_cli_writes_manifest_artifacts_and_shard_plan(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_country_year(engine, country_id=2, iso3="CAN", name="Canada", year=2020)
    _insert_fact(engine, country_id=1, country_year_id=1, year=2020)
    _insert_ruler_metadata(engine)
    output_dir = tmp_path / "slice"

    result = runner.invoke(
        app,
        [
            "research", "build-local-prior-slice", "--methodology-id", "4B.2",
            "--year", "2020", "--output-dir", str(output_dir), "--shard-size",
            "1", "--db-url", database_url, "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["total_cases"] == 2
    assert payload["artifact_count"] == 2
    assert payload["status_counts"] == {"evidence_found": 1, "no_evidence_found": 1}
    assert payload["cases_with_ruler_metadata"] == 1
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "shard_plan.json").exists()
    assert len(list((output_dir / "artifacts").glob("*.json"))) == 2


def _insert_country_year(
    engine: object,
    *,
    country_id: int,
    iso3: str,
    name: str,
    year: int,
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO countries (
                    id, iso3, country_name, country_name_normalized
                ) VALUES (:country_id, :iso3, :name, :normalized_name)
                """
            ),
            {"country_id": country_id, "iso3": iso3, "name": name, "normalized_name": name.lower()},
        )
        conn.execute(
            text(
                """
                INSERT INTO country_years (id, country_id, year, included_in_project)
                VALUES (:country_id, :country_id, :year, 1)
                """
            ),
            {"country_id": country_id, "year": year},
        )


def _insert_fact(engine: object, *, country_id: int, country_year_id: int, year: int) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_year_id, country_id, year, field_key, field_label, value_type,
                    selected_value_number, selected_value_text, selected_value_json,
                    candidate_values_json, selection_rule, adjudication_status,
                    confidence_score, quality_signals_json, warnings_json, rationale,
                    recommended_next_action, source_slugs_json, source_observation_ids_json,
                    producer, method_version
                ) VALUES (
                    :country_year_id, :country_id, :year, 'political_liberties',
                    'Political Liberties', 'number', 1.0, NULL, NULL, '[]', 'test_rule',
                    'selected', 88, '{}', '[]', 'Selected fixture fact.', 'none',
                    :source_slugs_json, :source_observation_ids_json, 'test', 'test_v1'
                )
                """
            ),
            {
                "country_year_id": country_year_id,
                "country_id": country_id,
                "year": year,
                "source_slugs_json": json.dumps(("freedom_house",)),
                "source_observation_ids_json": json.dumps(("freedom_house:USA:2020",)),
            },
        )


def _insert_ruler_metadata(engine: object) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO leaders (id, full_name, normalized_name)
                VALUES (1, 'Donald Trump', 'donald trump')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO ruler_years (
                    id, leader_id, country_id, year, system_selected_leader_name, review_status
                ) VALUES (1, 1, 1, 2020, 'Donald Trump', 'resolved')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO ruler_identity_adjudications (
                    country_year_id, country_id, year, selected_ruler_year_id,
                    selected_leader_name, classification, selection_rule, review_status,
                    rationale, recommended_next_action, method_version
                ) VALUES (
                    1, 1, 2020, 1, 'Donald Trump', 'resolved_auto_single_candidate',
                    'single_candidate', 'resolved', 'fixture', 'none', 'test_v1'
                )
                """
            )
        )
