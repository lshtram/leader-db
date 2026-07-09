from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database

runner = CliRunner()


def test_research_persist_cited_evaluations_cli_writes_non_8b_answer(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    input_path = tmp_path / "cited.json"
    input_path.write_text(json.dumps({"evaluations": [_cited_payload()]}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "research", "persist-cited-evaluations", "--input", str(input_path),
            "--db-url", database_url, "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"evaluations_persisted": 1}
    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()
    assert answer["question_id"] == "1B.1"
    assert answer["answer_text"] == "supported"
    assert link["source_observation_id"] == "https://example.test/source"


def test_research_persist_cited_evaluations_cli_rejects_empty_citations(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    input_path = tmp_path / "cited-empty-citations.json"
    input_path.write_text(
        json.dumps({"evaluations": [_cited_payload() | {"citations": []}]}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "research", "persist-cited-evaluations", "--input", str(input_path),
            "--db-url", database_url, "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert "citations" in json.loads(result.stdout)["error"]


def _cited_payload() -> dict[str, object]:
    return {
        "methodology_id": "1B.1",
        "year": 1967,
        "iso3": "TZA",
        "country_name": "Tanzania",
        "leader_name": "Julius Nyerere",
        "leader_resolution": "Julius Nyerere / TANU government",
        "period_start_year": 1967,
        "period_end_year": 1985,
        "period_label": "1967-1985",
        "prompt_context": "Nuclear-risk ruler-quality question.",
        "verdict": "supported",
        "evidence_quality": "medium",
        "confidence": "medium",
        "manual_review_reason": "Needs cross-check.",
        "score_1_to_10": 7,
        "confidence_score": 72,
        "claims": [{"claim": "limited nuclear risk exposure"}],
        "answer_payload": {"calibration": _calibration()},
        "citations": [
            {
                "url": "https://example.test/source",
                "source_confidence": "medium_high",
                "source_confidence_reason": "Fixture reputable source.",
                "source_type": "media",
                "final_evidence_use": "final_evidence",
            }
        ],
        "caveats": ["Fixture caveat."],
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
