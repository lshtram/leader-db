"""Build all-scope local structured-prior artifact packages."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .local_structured_prior import (
    LeaderPriorMetadata,
    LocalPriorPeriod,
    LocalStructuredPriorArtifact,
    LocalStructuredPriorRequest,
    build_local_structured_prior,
)

LOCAL_PRIOR_SLICE_METHOD_VERSION = "local_structured_prior_slice_v1"


class LocalPriorSliceCase(BaseModel):
    """One country-year/ruler case included in an all-scope prior package."""

    model_config = ConfigDict(extra="forbid")

    iso3: str
    country_name: str
    year: int
    leader_name: str | None = None
    leader_id: int | None = None
    ruler_year_id: int | None = None
    identity_classification: str | None = None
    identity_review_status: str | None = None


class LocalPriorSliceManifest(BaseModel):
    """Manifest for a generated local-prior slice package."""

    model_config = ConfigDict(extra="forbid")

    methodology_id: str
    year: int
    output_dir: str
    method_version: str = LOCAL_PRIOR_SLICE_METHOD_VERSION
    total_cases: int
    artifact_count: int
    status_counts: dict[str, int]
    local_fact_coverage_counts: dict[str, int]
    total_local_facts: int
    cases_with_ruler_metadata: int
    cases_needing_identity_review: int
    shard_plan_path: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


def build_local_prior_slice_package(
    bind: Engine | Session,
    *,
    methodology_id: str,
    year: int,
    output_dir: Path,
    shard_size: int = 10,
) -> LocalPriorSliceManifest:
    """Write one local-prior artifact per included country-year and a manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    cases = list_local_prior_slice_cases(bind, year=year)
    artifacts: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    local_fact_coverage_counts: Counter[str] = Counter()
    total_local_facts = 0
    cases_with_ruler_metadata = 0
    cases_needing_identity_review = 0

    for case in cases:
        if case.leader_name or case.leader_id is not None:
            cases_with_ruler_metadata += 1
        if case.identity_review_status and case.identity_review_status not in {
            "resolved",
            "auto_resolved",
            "not_needed",
        }:
            cases_needing_identity_review += 1
        artifact = build_local_structured_prior(
            bind,
            LocalStructuredPriorRequest(
                methodology_id=methodology_id,
                iso3=case.iso3,
                period=LocalPriorPeriod(year=year),
                leader=LeaderPriorMetadata(
                    name=case.leader_name,
                    leader_id=case.leader_id,
                    period_label=str(year),
                ),
            ),
        )
        payload = artifact.model_dump(mode="json")
        payload["slice_case"] = case.model_dump(mode="json")
        methodology_slug = methodology_id.lower().replace(".", "")
        artifact_name = f"{methodology_slug}_{year}_{case.iso3.lower()}_local_prior.json"
        artifact_path = artifacts_dir / artifact_name
        artifact_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        fact_count = len(artifact.local_facts)
        total_local_facts += fact_count
        status_counts[artifact.status] += 1
        local_fact_coverage_counts[_fact_coverage_bucket(artifact)] += 1
        artifacts.append(
            {
                "iso3": case.iso3,
                "country_name": case.country_name,
                "year": year,
                "leader_name": case.leader_name,
                "status": artifact.status,
                "local_fact_count": fact_count,
                "path": str(artifact_path),
            }
        )

    shard_plan_path = output_dir / "shard_plan.json"
    shard_plan = _build_shard_plan(artifacts, shard_size=shard_size)
    shard_plan_path.write_text(
        json.dumps(shard_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = LocalPriorSliceManifest(
        methodology_id=methodology_id,
        year=year,
        output_dir=str(output_dir),
        total_cases=len(cases),
        artifact_count=len(artifacts),
        status_counts=dict(sorted(status_counts.items())),
        local_fact_coverage_counts=dict(sorted(local_fact_coverage_counts.items())),
        total_local_facts=total_local_facts,
        cases_with_ruler_metadata=cases_with_ruler_metadata,
        cases_needing_identity_review=cases_needing_identity_review,
        shard_plan_path=str(shard_plan_path),
        artifacts=artifacts,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def list_local_prior_slice_cases(
    bind: Engine | Session,
    *,
    year: int,
) -> tuple[LocalPriorSliceCase, ...]:
    """Return included country-years with selected ruler metadata when available."""

    statement = text(
        """
        SELECT
            c.iso3,
            c.country_name,
            cy.year,
            rya.selected_ruler_year_id AS ruler_year_id,
            COALESCE(
                rya.selected_leader_name,
                l.full_name,
                ry.system_selected_leader_name
            ) AS leader_name,
            l.id AS leader_id,
            rya.classification AS identity_classification,
            rya.review_status AS identity_review_status
        FROM country_years cy
        JOIN countries c ON c.id = cy.country_id
        LEFT JOIN ruler_identity_adjudications rya ON rya.country_year_id = cy.id
        LEFT JOIN ruler_years ry ON ry.id = rya.selected_ruler_year_id
        LEFT JOIN leaders l ON l.id = ry.leader_id
        WHERE cy.year = :year
          AND cy.included_in_project = :included_in_project
        ORDER BY c.iso3
        """
    )
    rows = _execute_mappings(bind, statement, {"year": year, "included_in_project": True})
    return tuple(
        LocalPriorSliceCase(
            iso3=str(row["iso3"]),
            country_name=str(row["country_name"]),
            year=int(row["year"]),
            leader_name=row["leader_name"],
            leader_id=row["leader_id"],
            ruler_year_id=row["ruler_year_id"],
            identity_classification=row["identity_classification"],
            identity_review_status=row["identity_review_status"],
        )
        for row in rows
    )


def _fact_coverage_bucket(artifact: LocalStructuredPriorArtifact) -> str:
    count = len(artifact.local_facts)
    if count == 0:
        return "zero_facts"
    if count < 3:
        return "one_to_two_facts"
    return "three_or_more_facts"


def _build_shard_plan(artifacts: list[dict[str, Any]], *, shard_size: int) -> dict[str, Any]:
    shards = []
    for index in range(0, len(artifacts), shard_size):
        shard_artifacts = artifacts[index : index + shard_size]
        shard_number = len(shards) + 1
        shards.append(
            {
                "shard_id": f"shard-{shard_number:03d}",
                "expected_record_count": len(shard_artifacts),
                "local_prior_paths": [item["path"] for item in shard_artifacts],
                "watchdog_command_template": (
                    "leaders-db research validate-shard-output --status <status.json> "
                    "--input <shard-input.json> --output <shard-output.json> "
                    f"--expected-record-count {len(shard_artifacts)} "
                    "--max-expected-minutes 30 --max-progress-stale-minutes 10 --json"
                ),
            }
        )
    return {
        "execution_policy": (
            "Do not launch full internet-research automatically from this manifest; use "
            "human-approved bounded shards with local prior artifacts and watchdog validation."
        ),
        "recommended_shard_size": shard_size,
        "shard_count": len(shards),
        "shards": shards,
    }


def _execute_mappings(bind: Engine | Session, statement: Any, params: dict[str, Any]) -> list[Any]:
    context = bind.connect() if isinstance(bind, Engine) else bind.connection()
    close_context = isinstance(bind, Engine)
    try:
        return list(context.execute(statement, params).mappings().all())
    finally:
        if close_context:
            context.close()


__all__ = [
    "LOCAL_PRIOR_SLICE_METHOD_VERSION",
    "LocalPriorSliceCase",
    "LocalPriorSliceManifest",
    "build_local_prior_slice_package",
    "list_local_prior_slice_cases",
]
