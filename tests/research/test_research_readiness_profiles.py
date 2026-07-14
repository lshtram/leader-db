from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from leaders_db.cli.research_worker_commands import plan_case_cmd
from leaders_db.research import readiness
from leaders_db.research.readiness import ReadinessCheck, build_research_readiness_report


def test_dossier_readiness_validates_reviewer_and_formatter_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles = _profiles(tmp_path)
    workflow = tmp_path / "research-workflow.yaml"
    workflow.write_text(
        """version: 1
chapter_order: [1B, 2B, 3B, 4B, 5B, 6B, 7B, 8B]
max_review_rounds: 3
minimum_source_claim_units_per_chapter: 5
normal_source_claim_units_per_chapter: 10
maximum_source_claim_units_per_chapter: 20
minimum_independent_source_families_per_chapter: 3
""",
        encoding="utf-8",
    )
    passed = ReadinessCheck(check_id="fixture", status="pass", message="fixture")
    monkeypatch.setattr(readiness, "_database_check", lambda *args, **kwargs: passed)
    monkeypatch.setattr(readiness, "_question_checks", lambda *args, **kwargs: (passed,))
    monkeypatch.setattr(readiness, "_role_skill_check", lambda *args, **kwargs: passed)
    monkeypatch.setattr(readiness, "_output_path_check", lambda *args, **kwargs: passed)
    monkeypatch.setattr(
        readiness,
        "_identity_check",
        lambda *args, **kwargs: (passed, 1, 0),
    )

    report = build_research_readiness_report(
        create_engine("sqlite+pysqlite:///:memory:"),
        project_root=tmp_path,
        mode="dossier_researcher",
        year=2020,
        methodology_ids=("1B.1",),
        provider_profile="researcher",
        reviewer_profile="reviewer",
        formatter_profile="reviewer",
        output_dir=tmp_path / "output",
        model_profiles_path=profiles,
        research_workflow_path=workflow,
    )

    checks = {check.check_id: check for check in report.checks}
    assert checks["model_profile"].status == "pass"
    assert checks["reviewer_model_profile"].status == "pass"
    assert checks["formatter_model_profile"].status == "fail"
    assert report.ready is False


def test_plan_case_runs_readiness_before_planning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def stop_at_readiness(*args: object, **kwargs: object) -> None:
        calls.append("readiness")
        raise RuntimeError("stop after readiness")

    monkeypatch.setattr("leaders_db.cli.research_job_commands._require_ready", stop_at_readiness)

    with pytest.raises(RuntimeError, match="stop after readiness"):
        plan_case_cmd(
            year=2020,
            ruler_year_id=1,
            run_key="test",
            question_ids=["1B.1"],
            provider_profile="researcher",
            reviewer_profile="reviewer",
            formatter_profile="formatter",
            output_root=tmp_path / "output",
            max_attempts=1,
            db_url="sqlite+pysqlite:///:memory:",
            model_profiles_path=tmp_path / "profiles.yaml",
            research_workflow_path=None,
            output_json=False,
        )

    assert calls == ["readiness"]


def _profiles(tmp_path: Path) -> Path:
    config = tmp_path / "codex.toml"
    credentials = tmp_path / "auth.json"
    config.write_text('model = "fixture"\n', encoding="utf-8")
    credentials.write_text("{}", encoding="utf-8")
    profiles = tmp_path / "profiles.yaml"
    profiles.write_text(
        f"""version: 1
profiles:
  researcher:
    provider: openai
    model: researcher
    execution_surface: codex
    roles: [dossier_researcher]
    cost_class: test
    context_window: 100000
    codex_config_path: {config}
    credential_path: {credentials}
    notes: fixture
  reviewer:
    provider: openai
    model: reviewer
    execution_surface: codex
    roles: [dossier_evidence_reviewer]
    cost_class: test
    context_window: 100000
    codex_config_path: {config}
    credential_path: {credentials}
    notes: fixture
""",
        encoding="utf-8",
    )
    return profiles
