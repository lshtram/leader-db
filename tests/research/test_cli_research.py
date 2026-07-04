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
