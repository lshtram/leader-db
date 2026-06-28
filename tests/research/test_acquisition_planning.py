import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.research.acquisition import acquired_evidence_to_observation
from leaders_db.research.dataset_builder import build_analytical_dataset
from leaders_db.research.models import (
    AcquiredEvidenceRecord,
    DimensionBinding,
    DimensionFilter,
    ResearchQuestion,
    RowScope,
    ScopeFilter,
)
from leaders_db.research.planner import plan_question
from leaders_db.research.runner import run_research_question
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_missing_qualitative_leader_case_plans_task_without_acquired_evidence(
    tmp_path: Path,
) -> None:
    question = _legal_case_question(preferred_sources=("official_court_records",))

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
    assert tasks[0]["allowed_source_types"] == ["official_record", "reputable_news"]

    with (output_dir / "analytical-dataset.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["coverage_status"] == "missing"
    assert rows[0]["value_type"] == "missing"
    assert json.loads(rows[0]["warning_codes"]) == ["missing_evidence"]
    assert not (output_dir / "acquired-evidence.json").exists()


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        (True, "boolean"),
        (12, "numeric"),
        (12.5, "numeric"),
        ("high", "categorical"),
        ("reported in docket", "text"),
        (None, "missing"),
    ],
)
def test_acquired_evidence_record_accepts_value_matching_value_type(
    value: bool | int | float | str | None,
    value_type: str,
) -> None:
    _acquired_record(value=value, value_type=value_type)


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        ("true", "boolean"),
        (True, "numeric"),
        (12, "categorical"),
        (12.5, "text"),
        ("unknown", "missing"),
    ],
)
def test_acquired_evidence_record_rejects_value_type_mismatch(
    value: bool | int | float | str | None,
    value_type: str,
) -> None:
    with pytest.raises(ValidationError, match="value must match value_type"):
        _acquired_record(value=value, value_type=value_type)


def test_missing_structured_evidence_with_acquisition_none_has_no_task(
    tmp_path: Path,
) -> None:
    question = ResearchQuestion(
        question_id="conflict-missing-2020",
        question_key="conflict_fatalities_structured",
        display_text="Get conflict fatalities for USA in 2020.",
        concepts=("conflict_fatalities",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("USA",), role="entity"),
                DimensionFilter(key="year", values=(2020,), role="time"),
            )
        ),
        analyses=("coverage",),
    )

    result = run_research_question(
        question=question,
        repository=InMemoryEvidenceRepository(),
        output_root=tmp_path,
        run_id="structured-missing",
    )

    assert result.status == "partial"
    output_dir = tmp_path / "structured-missing"
    tasks = json.loads((output_dir / "acquisition-tasks.json").read_text(encoding="utf-8"))
    assert tasks == []
    gap_report = json.loads((output_dir / "evidence-gap-report.json").read_text(encoding="utf-8"))
    assert gap_report["missing"][0]["reason"] == "indicator_missing"


def test_run_approved_tasks_does_not_execute_live_acquisition() -> None:
    question = _legal_case_question()
    plan = plan_question(question).model_copy(update={"acquisition_policy": "run_approved_tasks"})

    rows, _gap_report, tasks = build_analytical_dataset(plan, InMemoryEvidenceRepository())

    assert tasks[0].status == "planned"
    assert rows[0].coverage_status == "missing"
    assert "live_acquisition_not_executed" in rows[0].warning_codes


def test_acquired_evidence_fixture_becomes_direct_stored_evidence(
    tmp_path: Path,
) -> None:
    observation = acquired_evidence_to_observation(
        _acquired_record(value=True, value_type="boolean")
    )

    result = run_research_question(
        question=_legal_case_question(question_id="leader-legal-cases-fixture-2023"),
        repository=InMemoryEvidenceRepository(observations=(observation,)),
        output_root=tmp_path,
        run_id="stored-generated-evidence",
    )

    assert result.status == "success"
    with (tmp_path / "stored-generated-evidence" / "analytical-dataset.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["coverage_status"] == "direct"
    assert json.loads(rows[0]["source_observation_ids"]) == [
        "task-gap-legal-case:leader_open_criminal_or_corruption_case"
    ]
    provenance = json.loads(rows[0]["provenance_json"])
    assert provenance["raw_locator"]["url"] == "https://example.test/court-docket"
    assert provenance["extension"]["quote"] == "The case remains open."
    assert provenance["extension"]["retrieved_at"] == "2026-06-28"
    assert provenance["extension"]["caveats"] == ["fixture only"]


def _legal_case_question(
    *,
    question_id: str = "leader-legal-cases-selected-2023",
    preferred_sources: tuple[str, ...] = (),
) -> ResearchQuestion:
    return ResearchQuestion(
        question_id=question_id,
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
        preferred_sources=preferred_sources,
    )


def _acquired_record(
    *,
    value: bool | int | float | str | None,
    value_type: str,
) -> AcquiredEvidenceRecord:
    return AcquiredEvidenceRecord(
        task_id="task-gap-legal-case",
        subject_scope=_leader_scope(),
        claim_key="leader_open_criminal_or_corruption_case",
        value=value,
        value_type=value_type,
        source_url="https://example.test/court-docket",
        source_title="Court docket fixture",
        source_type="official_record",
        quote="The case remains open.",
        retrieved_at="2026-06-28",
        confidence_score=82,
        human_review_required=True,
        caveats=("fixture only",),
    )


def _leader_scope() -> RowScope:
    return RowScope(
        dimensions=(
            DimensionBinding(key="country", value="ISR", value_type="string", role="entity"),
            DimensionBinding(key="leader", value="leader-1", value_type="string", role="entity"),
            DimensionBinding(key="year", value=2023, value_type="integer", role="time"),
        )
    )
