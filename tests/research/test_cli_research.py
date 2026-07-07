from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database

runner = CliRunner()


def test_research_persist_8b_evaluations_cli_writes_answers(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    input_path = tmp_path / "8b.json"
    input_path.write_text(json.dumps({"evaluations": [_evaluation_payload()]}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "research",
            "persist-8b-evaluations",
            "--input",
            str(input_path),
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"evaluations_persisted": 1}
    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        links = (
            conn.execute(text("SELECT source_observation_id FROM research_answer_evidence_links"))
            .scalars()
            .all()
        )
    assert answer["question_id"] == "8B.3"
    assert answer["answer_text"] == "partially_supported"
    assert links == ["https://example.test/program"]


def test_research_persist_8b_evaluations_cli_rejects_unregistered_question(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    payload = _evaluation_payload() | {"methodology_id": "7B.1"}
    input_path = tmp_path / "8b-invalid.json"
    input_path.write_text(json.dumps([payload]), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "research",
            "persist-8b-evaluations",
            "--input",
            str(input_path),
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert "unsupported 8B methodology_id" in json.loads(result.stdout)["error"]


def test_research_persist_8b_evaluations_cli_fails_when_db_uninitialized(
    isolated_data_lake: object,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "8b.json"
    input_path.write_text(json.dumps([_evaluation_payload()]), encoding="utf-8")

    result = runner.invoke(
        app,
        ["research", "persist-8b-evaluations", "--input", str(input_path)],
    )

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout


def test_research_list_answers_cli_outputs_json_with_evidence_links(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    _persist_fixture_evaluation(database_url, tmp_path)

    result = runner.invoke(
        app,
        [
            "research",
            "list-answers",
            "--question-id",
            "8B.3",
            "--iso3",
            "tza",
            "--db-url",
            database_url,
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["question_id"] == "8B.3"
    assert payload[0]["iso3"] == "TZA"
    assert payload[0]["answer_text"] == "partially_supported"
    assert payload[0]["answer_json"]["leader_resolution"] == ("Julius Nyerere / TANU government")
    assert payload[0]["evidence_link_count"] == 1
    assert payload[0]["evidence_links"] == [
        {
            "evidence_role": "citation",
            "source_observation_id": "https://example.test/program",
            "source_slug": "manual_web",
        }
    ]


def test_research_list_answers_cli_outputs_csv(database_url: str, tmp_path: Path) -> None:
    init_database(database_url)
    _persist_fixture_evaluation(database_url, tmp_path)

    result = runner.invoke(
        app,
        [
            "research",
            "list-answers",
            "--year",
            "1967",
            "--db-url",
            database_url,
            "--output",
            "csv",
        ],
    )

    assert result.exit_code == 0, result.stdout
    lines = result.stdout.splitlines()
    assert lines[0].startswith("question_id,year,iso3,country_name")
    assert "8B.3,1967,TZA,Tanzania,Julius Nyerere" in lines[1]
    assert lines[1].endswith(",8b_cited_evaluation_v1,1")


def test_research_list_answers_cli_fails_when_db_uninitialized(
    isolated_data_lake: object,
) -> None:
    result = runner.invoke(app, ["research", "list-answers"])

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout


def test_research_build_country_year_fact_answers_cli_writes_answers(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_country_year_fact(engine)

    result = runner.invoke(
        app,
        [
            "research",
            "build-country-year-fact-answers",
            "--question-id",
            "5.1",
            "--year",
            "2023",
            "--iso3",
            "usa",
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["answers_persisted"] == 1
    assert payload["coverage_counts"] == {"direct": 1}
    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()
    assert answer["question_id"] == "5.1"
    assert answer["answer_numeric"] == 76399.0
    assert link["source_slug"] == "world_bank_wdi"


def test_research_build_country_year_fact_answers_cli_fails_when_db_uninitialized(
    isolated_data_lake: object,
) -> None:
    result = runner.invoke(
        app,
        [
            "research",
            "build-country-year-fact-answers",
            "--question-id",
            "5.1",
            "--year",
            "2023",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout


def _evaluation_payload() -> dict[str, object]:
    return {
        "methodology_id": "8B.3",
        "year": 1967,
        "iso3": "TZA",
        "country_name": "Tanzania",
        "leader_name": "Julius Nyerere",
        "leader_resolution": "Julius Nyerere / TANU government",
        "program_source": "Arusha Declaration",
        "implementation_or_outcome_window": "1967-1975",
        "verdict": "partially_supported",
        "evidence_quality": "medium",
        "confidence": "medium",
        "manual_review_reason": "Outcome side effects require review.",
        "score_1_to_10": 6,
        "confidence_score": 70,
        "goal_coverage": [{"goal": "ujamaa villages", "score_1_10": 5}],
        "calibration": _calibration(),
        "candidate_structured_observation": {"support_status": "partially_supported"},
        "citations": [
            {
                "url": "https://example.test/program",
                "title": "Program source",
            }
        ],
        "caveats": ["Broad mobilization question."],
    }


def _calibration() -> dict[str, object]:
    return {
        "rubric_version": "fixture_v1",
        "calibration_batch_id": "fixture_1967_batch",
        "calibrated_against": ["Tanzania / Julius Nyerere / 1967"],
        "severity_band": "recurring",
        "state_responsibility": "direct",
        "accountability_level": "partial",
        "information_environment": "partly_restricted",
        "period_fit": "ruler_period",
        "source_mix": ["media"],
        "structured_prior_summary": "not_available",
        "contrary_evidence": [],
        "score_rationale": "Fixture score rationale.",
        "lower_anchor_rejected": "Fixture lower anchor rejection.",
        "higher_anchor_rejected": "Fixture higher anchor rejection.",
        "visibility_bias_check": "Fixture visibility check.",
        "repression_silence_check": "Fixture repression silence check.",
        "population_scale_check": "Fixture population scale check.",
        "source_type_check": "Fixture source type check.",
        "recency_check": "Fixture recency check.",
        "subagent_calibration_check": "Fixture calibration check.",
    }


def _persist_fixture_evaluation(database_url: str, tmp_path: Path) -> None:
    input_path = tmp_path / "8b.json"
    input_path.write_text(json.dumps([_evaluation_payload()]), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "research",
            "persist-8b-evaluations",
            "--input",
            str(input_path),
            "--db-url",
            database_url,
        ],
    )
    assert result.exit_code == 0, result.stdout


def _insert_country_year(
    engine: Engine,
    *,
    country_id: int,
    iso3: str,
    name: str,
    year: int,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO countries (id, iso3, country_name, country_name_normalized)
                VALUES (:country_id, :iso3, :name, :normalized_name)
                """
            ),
            {
                "country_id": country_id,
                "iso3": iso3,
                "name": name,
                "normalized_name": name.lower(),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO country_years (id, country_id, year, included_in_project)
                VALUES (:country_year_id, :country_id, :year, 1)
                """
            ),
            {"country_year_id": country_id, "country_id": country_id, "year": year},
        )


def _insert_country_year_fact(engine: Engine) -> None:
    candidate = {
        "concept_key": "gdp_per_capita",
        "source_slug": "world_bank_wdi",
        "value": 76399.0,
        "value_type": "numeric",
        "unit": "current_usd",
        "scale": None,
        "source_version": "fixture",
        "source_indicator_codes": ["wdi_gdp_per_capita"],
        "input_observation_ids": ["wdi:USA:2023:gdp_per_capita"],
        "mapping_type": "direct",
        "quality_flags": [],
        "warnings": [],
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_year_id, country_id, year, field_key, field_label, value_type,
                    selected_value_number, selected_value_json, candidate_values_json,
                    selection_rule, adjudication_status, confidence_score,
                    quality_signals_json, warnings_json, rationale,
                    recommended_next_action, source_slugs_json,
                    source_observation_ids_json, producer, method_version
                ) VALUES (
                    1, 1, 2023, 'gdp_per_capita', 'GDP per capita', 'number',
                    76399.0, :selected_value_json, :candidate_values_json,
                    'test_rule', 'selected', 92, '{}', '[]', 'Selected fixture fact.',
                    'none', :source_slugs_json, :source_observation_ids_json,
                    'test', 'test_v1'
                )
                """
            ),
            {
                "selected_value_json": json.dumps(candidate),
                "candidate_values_json": json.dumps((candidate,)),
                "source_slugs_json": json.dumps(("world_bank_wdi",)),
                "source_observation_ids_json": json.dumps(("wdi:USA:2023:gdp_per_capita",)),
            },
        )
