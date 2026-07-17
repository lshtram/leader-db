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

from leaders_db.identity.coverage import (
    IdentityCoverageDetailRow,
    build_identity_coverage_gap_report,
)

from .local_structured_prior import (
    LeaderPriorMetadata,
    LocalPriorPeriod,
    LocalStructuredPriorArtifact,
    LocalStructuredPriorRequest,
    build_local_structured_prior,
)

LOCAL_PRIOR_SLICE_METHOD_VERSION = "local_structured_prior_slice_v2"

RESEARCH_ELIGIBLE_IDENTITY_CLASSIFICATIONS = {
    "resolved",
    "resolved_auto_single_candidate",
    "resolved_auto_role_priority",
    "resolved_auto_duration_majority",
    "resolved_auto_year_coverage_majority",
}

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
    persisted_identity_classification: str | None = None
    persisted_identity_review_status: str | None = None
    identity_research_eligible: bool
    identity_block_reason: str | None = None


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
    research_eligible_cases: int
    quarantined_cases: int
    shard_plan_path: str
    quarantine_path: str
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
        if not case.identity_research_eligible:
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
                "identity_research_eligible": case.identity_research_eligible,
                "identity_block_reason": case.identity_block_reason,
                "local_fact_count": fact_count,
                "path": str(artifact_path),
            }
        )

    eligible_artifacts = [
        artifact for artifact in artifacts if artifact["identity_research_eligible"]
    ]
    quarantined_artifacts = [
        artifact for artifact in artifacts if not artifact["identity_research_eligible"]
    ]
    shard_plan_path = output_dir / "shard_plan.json"
    shard_plan = _build_shard_plan(eligible_artifacts, shard_size=shard_size)
    shard_plan_path.write_text(
        json.dumps(shard_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quarantine_path = output_dir / "identity_quarantine.json"
    quarantine_path.write_text(
        json.dumps({"cases": quarantined_artifacts}, indent=2, sort_keys=True) + "\n",
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
        research_eligible_cases=len(eligible_artifacts),
        quarantined_cases=len(quarantined_artifacts),
        shard_plan_path=str(shard_plan_path),
        quarantine_path=str(quarantine_path),
        artifacts=artifacts,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_launch_plan(output_dir, manifest=manifest, shard_plan=shard_plan)
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
    coverage_rows = _identity_coverage_rows(bind, year=year)
    return tuple(
        _local_prior_slice_case(row, coverage_rows.get(str(row["iso3"])))
        for row in rows
    )


def _identity_coverage_rows(
    bind: Engine | Session,
    *,
    year: int,
) -> dict[str, IdentityCoverageDetailRow]:
    engine = bind if isinstance(bind, Engine) else bind.get_bind()
    if not isinstance(engine, Engine):
        raise TypeError("local-prior identity coverage requires an Engine-backed session")
    report = build_identity_coverage_gap_report(
        engine,
        year=year,
        include_out_of_scope=False,
    )
    return {row.iso3: row for row in report.rows}


def _local_prior_slice_case(
    row: Any,
    coverage: IdentityCoverageDetailRow | None,
) -> LocalPriorSliceCase:
    leader_name = row["leader_name"]
    eligibility, block_reason = _identity_research_eligibility(
        coverage,
        leader_name=leader_name,
        persisted_classification=row["identity_classification"],
        persisted_review_status=row["identity_review_status"],
    )
    is_canonical_lock = row["identity_review_status"] == "confirmed_locked"
    return LocalPriorSliceCase(
        iso3=str(row["iso3"]),
        country_name=str(row["country_name"]),
        year=int(row["year"]),
        leader_name=leader_name,
        leader_id=row["leader_id"],
        ruler_year_id=row["ruler_year_id"],
        identity_classification=(
            row["identity_classification"]
            if is_canonical_lock
            else coverage.classification if coverage else None
        ),
        identity_review_status="resolved" if eligibility else "needs_review",
        persisted_identity_classification=row["identity_classification"],
        persisted_identity_review_status=row["identity_review_status"],
        identity_research_eligible=eligibility,
        identity_block_reason=block_reason,
    )


def _identity_research_eligibility(
    coverage: IdentityCoverageDetailRow | None,
    *,
    leader_name: str | None,
    persisted_classification: str | None = None,
    persisted_review_status: str | None = None,
) -> tuple[bool, str | None]:
    if persisted_review_status == "confirmed_locked":
        return _canonical_lock_eligibility(persisted_classification, leader_name)
    if coverage is None:
        return False, "missing_current_identity_diagnostic"
    if coverage.classification not in RESEARCH_ELIGIBLE_IDENTITY_CLASSIFICATIONS:
        return False, f"identity_classification:{coverage.classification}"
    if not leader_name:
        return False, "missing_selected_leader"
    if leader_name not in coverage.leader_names:
        return False, "selected_leader_not_in_current_identity_candidates"
    return True, None


def _canonical_lock_eligibility(
    classification: str | None, leader_name: str | None
) -> tuple[bool, str | None]:
    if classification != "resolved_canonical_formal_office":
        return False, "invalid_canonical_lock_classification"
    if not leader_name:
        return False, "missing_selected_leader"
    return True, None


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


def _write_launch_plan(
    output_dir: Path,
    *,
    manifest: LocalPriorSliceManifest,
    shard_plan: dict[str, Any],
) -> None:
    """Write durable human launch instructions next to a local-prior package."""

    output_dir_text = manifest.output_dir
    chapter_id = manifest.methodology_id.split(".", maxsplit=1)[0].lower()
    question_guide = f"the {chapter_id} guide under docs/methodology/chapter-guides/"
    first_shard_size = 0
    shards = shard_plan.get("shards")
    if isinstance(shards, list) and shards:
        first = shards[0]
        if isinstance(first, dict):
            first_shard_size = int(first.get("expected_record_count") or 0)
    reset_note = _launch_plan_reset_note(manifest)
    objective_text = (
        f"Find cited evidence for {manifest.methodology_id} {manifest.year}; prioritize "
        "primary, observer, legal, NGO, intergovernmental, and reputable media sources."
    )

    plan = f"""# {manifest.methodology_id} {manifest.year} Internet Research Launch Plan

This package is a clean local-first start package for chapter lens
`{manifest.methodology_id}`. It intentionally does **not** launch
`internet-research` workers automatically.

## Mandatory local-first process

Every worker and parent dispatcher must read:

1. `docs/methodology/local-first-researcher-guide.md`
2. `{question_guide}` for `{manifest.methodology_id}`
3. `docs/methodology/source-confidence-registry.json`
4. The relevant local-prior artifact from this package
5. The cited-evaluation schema from `leaders-db research cited-evaluation-schema`

Research order is mandatory: inspect the local chapter guide, query local
DB/artifacts, apply the source-confidence registry, use preferred external
sources, and use general web search only last. Local structured datasets already
loaded into the DB must not be re-fetched from the web for numeric/structured
priors.

## Search-tool policy

Use one discovery path only: the direct Parallel Search CLI wrapper
(`leaders-db research parallel-search`) for discovery, and `webfetch` for exact
known URLs when snippets are insufficient. Do **not** run Parallel MCP discovery,
Minimax web search, Brave generic searches, Playwright/browser searches,
duplicate searches, or unsafe browser code for this research run.

Approved discovery command shape:

```bash
leaders-db research parallel-search \
  --objective "{objective_text}" \
  --query "<country> <ruler> <topic> {manifest.year}" \
  --query "<country> <topic> report {manifest.year}" \
  --output {output_dir_text}/<case-id>-parallel-search-01.json \
  --json
```

Treat wrapper JSON as discovery/profile evidence only. Final citations must cite
underlying source URLs, not the wrapper result file.

## Source-confidence and profiling policy

{reset_note}Every citation must include `source_confidence`, `source_confidence_reason`,
`source_type`, and `final_evidence_use` using
`docs/methodology/source-confidence-registry.json`. Low and very-low confidence
sources may not be sole support for score-bearing claims. Grokipedia is
very-low/discovery-only; Wikipedia is medium-high orientation/basic facts;
official government sites are medium-low for self-serving fairness/restraint
claims but can be higher for formal facts.

Every shard must emit a `run_profile` object or sibling profile JSON with timing,
local evidence reads, Parallel call counts, fetch counts, usage/token fields when
exposed, and explicit unknowns when the tool hides usage.

## Local-prior package

- Manifest: `{output_dir_text}/manifest.json`
- Artifacts: `{output_dir_text}/artifacts/`
- Shard plan: `{output_dir_text}/shard_plan.json`
- Identity quarantine: `{manifest.quarantine_path}`
- Total cases: {manifest.total_cases}
- Artifact count: {manifest.artifact_count}
- Research-eligible cases: {manifest.research_eligible_cases}
- Identity-quarantined cases: {manifest.quarantined_cases}
- Shard size: {shard_plan.get("recommended_shard_size", first_shard_size)}
- Shard count: {shard_plan.get("shard_count", 0)}

Every `internet-research` worker must receive the corresponding local-prior JSON
artifact before external search. Only artifacts present in `shard_plan.json` are
eligible for research. Never launch cases listed in `identity_quarantine.json`;
resolve and rebuild their ruler identity first. If local evidence is absent,
record `no local evidence found` in the output rather than inventing a structured
prior.

## Bounded smoke cases

Suggested first smoke set, chosen to cover high/low/edge cases without launching
hundreds of workers:

1. `USA` / United States / Trump / {manifest.year}
2. `CHN` / China / Xi Jinping / {manifest.year}
3. `BLR` / Belarus / Lukashenka / {manifest.year}
4. `NZL` / New Zealand / Jacinda Ardern / {manifest.year}

For each approved case or shard, give the worker:

- `docs/methodology/local-first-researcher-guide.md`
- `{question_guide}`
- `docs/methodology/source-confidence-registry.json`
- the relevant local-prior artifact from `{output_dir_text}/artifacts/`
- the cited-evaluation schema from `leaders-db research cited-evaluation-schema`
- the instruction to collect citations/evidence only, not final comparative scores

## Watchdog template

For each approved shard, create a shard input file listing local-prior artifact
paths, then validate status/output with:

```bash
leaders-db research validate-shard-output \\
  --status {output_dir_text}/<shard-id>-status.json \\
  --input {output_dir_text}/<shard-id>-input.json \\
  --output {output_dir_text}/<shard-id>-output.json \\
  --expected-record-count <N> \\
  --max-expected-minutes 30 \\
  --max-progress-stale-minutes 10 \\
  --json
```

Record heartbeat/progress updates while work is active:

```bash
leaders-db research validate-shard-output \\
  --status {output_dir_text}/<shard-id>-status.json \\
  --progress-message "queried local DB/artifact and searched election-observer/legal sources" \\
  --json
```

## Full-run policy

Full all-ruler internet research remains pending human approval or a parent-owned
dispatcher that launches bounded shards, requires local-first artifacts, writes
one status JSON per shard, emits heartbeats, and validates each output before any
judge/calibration pass. Keep the current 10-case shard size unless the parent
explicitly changes it.
"""
    (output_dir / "internet_research_launch_plan.md").write_text(plan, encoding="utf-8")


def _launch_plan_reset_note(manifest: LocalPriorSliceManifest) -> str:
    """Return methodology-specific stale-output warning text for launch plans."""

    if manifest.methodology_id == "4B.2" and manifest.year == 2020:
        return (
            "The next full run starts from a clean 4B.2 2020 state: prior shard\n"
            "input/status/output files and persisted `4B.2` / 2020 /\n"
            "`cited_manual_evaluation_v1` answers were removed during preparation. Do not\n"
            "reuse old shard outputs.\n\n"
        )
    return ""


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
