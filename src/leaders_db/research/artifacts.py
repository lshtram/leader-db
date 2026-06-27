"""Artifact writers for first-slice research runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import (
    AnalyticalDatasetRow,
    EvidenceAcquisitionTask,
    EvidenceGapReport,
    Finding,
    InvestigationPlan,
    ResearchQuestion,
    evidence_query_to_dict,
)

CSV_COLUMNS = (
    "question_id",
    "row_scope_json",
    "concept_key",
    "value",
    "value_type",
    "unit",
    "source_id",
    "source_observation_ids",
    "coverage_status",
    "confidence_score",
    "warning_codes",
    "caveats",
    "provenance_json",
)


def write_research_artifacts(
    *,
    output_root: Path,
    run_id: str,
    question: ResearchQuestion,
    plan: InvestigationPlan,
    gap_report: EvidenceGapReport,
    acquisition_tasks: tuple[EvidenceAcquisitionTask, ...],
    dataset_rows: tuple[AnalyticalDatasetRow, ...],
    findings: tuple[Finding, ...],
) -> dict[str, Path]:
    """Write the Increment 1 artifact set under ``output_root / run_id``."""

    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "question": output_dir / "question.json",
        "plan": output_dir / "plan.json",
        "gap_report": output_dir / "evidence-gap-report.json",
        "acquisition_tasks": output_dir / "acquisition-tasks.json",
        "dataset": output_dir / "analytical-dataset.csv",
        "findings": output_dir / "findings.json",
        "manifest": output_dir / "manifest.json",
    }
    _write_model_json(paths["question"], question)
    _write_model_json(paths["plan"], plan)
    _write_model_json(paths["gap_report"], gap_report)
    _write_json(paths["acquisition_tasks"], [_dump_model(task) for task in acquisition_tasks])
    _write_dataset_csv(paths["dataset"], dataset_rows)
    _write_json(paths["findings"], [_dump_model(finding) for finding in findings])
    _write_json(paths["manifest"], _manifest(run_id, question, plan, paths, dataset_rows, findings))
    return paths


def _write_model_json(path: Path, model: BaseModel) -> None:
    _write_json(path, _dump_model(model))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_dataset_csv(path: Path, rows: tuple[AnalyticalDatasetRow, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))


def _csv_row(row: AnalyticalDatasetRow) -> dict[str, Any]:
    return {
        "question_id": row.question_id,
        "row_scope_json": _stable_json(_dump_model(row.row_scope)),
        "concept_key": row.concept_key,
        "value": row.value,
        "value_type": row.value_type,
        "unit": row.unit,
        "source_id": row.source_id,
        "source_observation_ids": _stable_json(row.source_observation_ids),
        "coverage_status": row.coverage_status,
        "confidence_score": row.confidence_score,
        "warning_codes": _stable_json(row.warning_codes),
        "caveats": _stable_json(row.caveats),
        "provenance_json": _stable_json(row.provenance_json),
    }


def _manifest(
    run_id: str,
    question: ResearchQuestion,
    plan: InvestigationPlan,
    paths: dict[str, Path],
    dataset_rows: tuple[AnalyticalDatasetRow, ...],
    findings: tuple[Finding, ...],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "question_id": question.question_id,
        "question_key": question.question_key,
        "evidence_query": evidence_query_to_dict(plan.evidence_query),
        "artifact_files": {key: path.name for key, path in sorted(paths.items())},
        "dataset_row_count": len(dataset_rows),
        "finding_count": len(findings),
    }


def _dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
