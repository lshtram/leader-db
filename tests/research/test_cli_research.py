from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
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
        "candidate_structured_observation": {"support_status": "partially_supported"},
        "citations": [
            {
                "url": "https://example.test/program",
                "title": "Program source",
            }
        ],
        "caveats": ["Broad mobilization question."],
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
