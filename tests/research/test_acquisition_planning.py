import csv
import json
from pathlib import Path

from leaders_db.research.models import DimensionFilter, ResearchQuestion, ScopeFilter
from leaders_db.research.runner import run_research_question
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_missing_qualitative_leader_case_plans_task_without_acquired_evidence(
    tmp_path: Path,
) -> None:
    question = ResearchQuestion(
        question_id="leader-legal-cases-selected-2023",
        question_key="leader_legal_cases_qualitative",
        display_text="Identify open criminal or corruption legal cases with cited evidence.",
        concepts=("leader_open_criminal_or_corruption_case",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("ISR",), role="entity"),
                DimensionFilter(key="leader", values=("leader-1",), role="entity"),
                DimensionFilter(key="year", values=(2023,), role="time"),
            )
        ),
        analyses=("coverage", "human_review_queue"),
        preferred_sources=("official_court_records", "prosecutor_records", "reputable_news"),
    )

    result = run_research_question(
        question=question,
        repository=InMemoryEvidenceRepository(),
        output_root=tmp_path,
        run_id="legal-run",
    )

    assert result.status == "partial"
    output_dir = tmp_path / "legal-run"
    gap_report = json.loads((output_dir / "evidence-gap-report.json").read_text(encoding="utf-8"))
    assert gap_report["missing"][0]["reason"] == "qualitative_evidence_needed"
    assert gap_report["recommended_acquisition_tasks"] == [
        gap_report["missing"][0]["gap_id"].replace("gap-", "task-gap-", 1)
    ]

    tasks = json.loads((output_dir / "acquisition-tasks.json").read_text(encoding="utf-8"))
    assert tasks[0]["status"] == "planned"
    assert tasks[0]["required_output_schema"] == "AcquiredEvidenceRecord"

    with (output_dir / "analytical-dataset.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["coverage_status"] == "missing"
    assert rows[0]["value_type"] == "missing"
    assert json.loads(rows[0]["warning_codes"]) == ["missing_evidence"]
    assert not (output_dir / "acquired-evidence.json").exists()
