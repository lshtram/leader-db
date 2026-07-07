from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from leaders_db.cli import app

runner = CliRunner()


def test_research_build_local_prior_cli_returns_artifact_shaped_json_error(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "error-prior.json"

    result = runner.invoke(
        app,
        [
            "research", "build-local-prior", "--methodology-id", "4B.1",
            "--year", "2020", "--start-year", "2019", "--end-year", "2020",
            "--iso3", "usa", "--output", str(output_path), "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload == json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["country"] == {"iso3": "USA", "name": None}
    assert "provide either year or start_year/end_year" in payload["missing_or_empty_reason"]
    assert payload["client_matrix_policy"] == "excluded_as_evidence"


def test_research_cited_evaluation_schema_cli_outputs_contract() -> None:
    result = runner.invoke(app, ["research", "cited-evaluation-schema"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "methodology_id" in payload["required"]
    assert payload["properties"]["citations"]["minItems"] == 1


def test_research_cited_evaluation_template_cli_outputs_valid_record() -> None:
    result = runner.invoke(
        app,
        [
            "research", "cited-evaluation-template", "--methodology-id", "1B.1",
            "--year", "1967", "--iso3", "tza", "--country-name", "Tanzania",
            "--leader-name", "Julius Nyerere", "--period-label", "1967-1985",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["methodology_id"] == "1B.1"
    assert payload["iso3"] == "TZA"
    assert payload["leader_name"] == "Julius Nyerere"
    assert payload["citations"][0]["url"] == "https://example.test/source"


def test_research_cited_evaluation_template_cli_uses_4b1_guide_rubric() -> None:
    result = runner.invoke(
        app,
        [
            "research", "cited-evaluation-template", "--methodology-id", "4B.1",
            "--year", "2020", "--iso3", "nzl", "--country-name", "New Zealand",
            "--leader-name", "Jacinda Ardern",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    calibration = payload["answer_payload"]["calibration"]
    assert payload["methodology_id"] == "4B.1"
    assert payload["iso3"] == "NZL"
    assert calibration["rubric_version"] == "4b1_electoral_contestability_v1"
    assert calibration["electoral_system_status"] == "unclear"
    assert calibration["incumbent_acceptance_of_loss"] == "unclear"
    assert calibration["contestability_constraints"] == ["none_found"]


def test_research_validate_shard_output_cli_records_progress(tmp_path: Path) -> None:
    status_path = tmp_path / "shard-status.json"
    input_path = tmp_path / "shard-input.json"
    output_path = tmp_path / "shard-output.json"
    input_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "research", "validate-shard-output", "--status", str(status_path),
            "--input", str(input_path), "--output", str(output_path),
            "--expected-record-count", "1", "--max-expected-minutes", "30",
            "--max-progress-stale-minutes", "10", "--progress-message",
            "started source search", "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "missing_output"
    assert payload["max_progress_stale_minutes"] == 10
    assert payload["progress_events"][0]["message"] == "started source search"


def test_research_cited_evaluation_template_cli_rejects_structured_question() -> None:
    result = runner.invoke(
        app,
        [
            "research", "cited-evaluation-template", "--methodology-id", "5.1",
            "--year", "2023", "--iso3", "USA", "--country-name", "United States",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert "unsupported cited methodology_id" in json.loads(result.stdout)["error"]
