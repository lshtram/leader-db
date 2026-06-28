"""First-slice research runner orchestration."""

from __future__ import annotations

from pathlib import Path

from leaders_db.sources.contracts import SourceId
from leaders_db.sources.query import EvidenceRepository

from .artifacts import write_research_artifacts
from .dataset_builder import build_analytical_dataset
from .models import AnalyticalDatasetRow, Finding, ResearchQuestion, ResearchRunResult
from .planner import plan_question


def run_research_question(
    *,
    question: ResearchQuestion,
    repository: EvidenceRepository,
    output_root: Path,
    run_id: str,
) -> ResearchRunResult:
    """Run plan -> dataset/gaps/tasks -> simple findings -> artifacts."""

    plan = plan_question(question)
    dataset_rows, gap_report, tasks = build_analytical_dataset(plan, repository)
    findings = _simple_findings(question.question_id, dataset_rows, bool(gap_report.missing))
    direct_source_ids = _direct_source_ids(dataset_rows)
    attributions = tuple(repository.get_attributions(direct_source_ids))
    artifact_paths = write_research_artifacts(
        output_root=output_root,
        run_id=run_id,
        question=question,
        plan=plan,
        gap_report=gap_report,
        acquisition_tasks=tasks,
        dataset_rows=dataset_rows,
        findings=findings,
        attributions=attributions,
        direct_source_ids=direct_source_ids,
    )
    status = "partial" if gap_report.missing or tasks else "success"
    warning_codes = ("evidence_gaps",) if gap_report.missing else ()
    return ResearchRunResult(
        run_id=run_id,
        question_id=question.question_id,
        status=status,
        output_dir=output_root / run_id,
        dataset_path=artifact_paths["dataset"],
        findings_path=artifact_paths["findings"],
        report_path=artifact_paths["report"],
        manifest_path=artifact_paths["manifest"],
        warning_codes=warning_codes,
    )


def _direct_source_ids(rows: tuple[AnalyticalDatasetRow, ...]) -> tuple[SourceId, ...]:
    seen: set[str] = set()
    source_ids: list[SourceId] = []
    for row in rows:
        if row.coverage_status != "direct":
            continue
        row_source_ids = row.provenance_json.get("source_ids", ())
        if not isinstance(row_source_ids, tuple | list):
            row_source_ids = ()
        slugs = tuple(str(source_id) for source_id in row_source_ids)
        if row.source_id is not None:
            slugs = (row.source_id, *slugs)
        for slug in slugs:
            if slug in seen:
                continue
            seen.add(slug)
            source_ids.append(SourceId(slug=slug))
    return tuple(source_ids)


def _simple_findings(
    question_id: str,
    rows: tuple[AnalyticalDatasetRow, ...],
    has_gaps: bool,
) -> tuple[Finding, ...]:
    direct_ids = tuple(
        observation_id
        for row in rows
        if row.coverage_status == "direct"
        for observation_id in row.source_observation_ids
    )
    if direct_ids:
        return (
            Finding(
                finding_id=f"finding-{question_id}-direct-evidence",
                question_id=question_id,
                claim=f"Stored evidence supports {len(direct_ids)} direct observation link(s).",
                support=direct_ids,
                source_observation_ids=direct_ids,
                analysis_result_ids=(),
                confidence_score=None,
                caveats=(),
                warning_codes=("evidence_gaps",) if has_gaps else (),
            ),
        )
    return (
        Finding(
            finding_id=f"finding-{question_id}-insufficient-evidence",
            question_id=question_id,
            claim="Stored evidence is insufficient for this question; missing rows were recorded.",
            support=(),
            source_observation_ids=(),
            analysis_result_ids=(),
            confidence_score=None,
            caveats=("No evidence was acquired or invented in Increment 1.",),
            warning_codes=("missing_evidence",),
        ),
    )
