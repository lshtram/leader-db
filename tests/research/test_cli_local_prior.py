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
    launch_plan = output_dir / "internet_research_launch_plan.md"
    assert launch_plan.exists()
    launch_plan_text = launch_plan.read_text(encoding="utf-8")
    assert "docs/methodology/local-first-researcher-guide.md" in launch_plan_text
    assert "leaders-db research parallel-search" in launch_plan_text
    assert "webfetch" in launch_plan_text
    assert "source_confidence" in launch_plan_text
    assert "run_profile" in launch_plan_text
    assert "Minimax web search" in launch_plan_text
    assert "Parallel MCP discovery" in launch_plan_text
    assert "Brave generic" in launch_plan_text
    assert len(list((output_dir / "artifacts").glob("*.json"))) == 2


def test_local_evidence_cli_single_iso_outputs_evidence_found(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_fact(engine, country_id=1, country_year_id=1, year=2020)

    result = runner.invoke(
        app,
        [
            "research", "local-evidence", "--methodology-id", "4B.2", "--year",
            "2020", "--iso3", "USA", "--json", "--db-url", database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["method_version"] == "local_evidence_v1"
    assert payload["record_count"] == 1
    assert payload["status_counts"] == {"evidence_found": 1}
    assert payload["records"][0]["status"] == "evidence_found"
    assert payload["records"][0]["local_facts"][0]["source_slugs"] == ["freedom_house"]


def test_local_evidence_cli_multiple_iso_counts_and_excludes_client_source(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_country_year(engine, country_id=2, iso3="CAN", name="Canada", year=2020)
    _insert_fact(engine, country_id=1, country_year_id=1, year=2020)
    _insert_fact(
        engine,
        country_id=2,
        country_year_id=2,
        year=2020,
        source_slugs=("client_existing",),
        source_observation_ids=("client:CAN:2020",),
    )

    result = runner.invoke(
        app,
        [
            "research", "local-evidence", "--methodology-id", "4B.2", "--year",
            "2020", "--iso3", "USA", "--iso3", "CAN", "--json", "--db-url",
            database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["record_count"] == 2
    assert payload["status_counts"] == {"evidence_found": 1, "no_evidence_found": 1}
    records_by_iso = {record["country"]["iso3"]: record for record in payload["records"]}
    assert records_by_iso["USA"]["local_facts"][0]["source_slugs"] == ["freedom_house"]
    assert records_by_iso["CAN"]["status"] == "no_evidence_found"
    assert records_by_iso["CAN"]["local_facts"] == []
    assert payload["client_matrix_policy"] == "excluded_as_evidence"


def test_local_evidence_cli_missing_iso_returns_stable_error(database_url: str) -> None:
    init_database(database_url)

    result = runner.invoke(
        app,
        [
            "research", "local-evidence", "--methodology-id", "4B.2", "--year",
            "2020", "--json", "--db-url", database_url,
        ],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["records"] == []
    assert payload["record_count"] == 0
    assert payload["status_counts"] == {"error": 1}
    assert "will not dump all local DB rows" in payload["missing_or_empty_reason"]


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


def _insert_fact(
    engine: object,
    *,
    country_id: int,
    country_year_id: int,
    year: int,
    source_slugs: tuple[str, ...] = ("freedom_house",),
    source_observation_ids: tuple[str, ...] = ("freedom_house:USA:2020",),
) -> None:
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
                "source_slugs_json": json.dumps(source_slugs),
                "source_observation_ids_json": json.dumps(source_observation_ids),
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
