"""Preflight checks for ruler-dossier research and chapter-year judging."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from leaders_db.identity.coverage import build_identity_coverage_gap_report
from leaders_db.research.model_profiles import (
    ResearchModelProfile,
    ResearchRole,
    load_research_model_profiles,
)
from leaders_db.research.registry import get_question_spec_by_methodology_id, list_question_specs
from leaders_db.research.research_workflow import load_research_workflow

ReadinessMode = Literal["dossier_researcher", "chapter_judge"]
CheckStatus = Literal["pass", "warning", "fail"]

DOSSIER_REQUIRED_TABLES = (
    "countries",
    "country_years",
    "leaders",
    "ruler_spells",
    "ruler_years",
    "ruler_identity_adjudications",
    "normalized_observations",
    "country_year_facts",
    "research_jobs",
    "research_job_events",
    "research_job_dependencies",
)
JUDGE_REQUIRED_TABLES = (
    *DOSSIER_REQUIRED_TABLES,
    "research_questions",
    "research_question_answers",
    "research_answer_evidence_links",
    "chapter_scores",
)
JUDGE_REQUIRED_CHAPTER_SCORE_COLUMNS = {
    "ruler_year_id",
    "job_key",
    "calibration_batch_id",
    "plausible_score_lower",
    "plausible_score_upper",
    "manual_review_required",
    "judgment_json",
}

ROLE_SKILL_PATHS = {
    "dossier_researcher": Path(".agents/skills/ruler-evidence-researcher/SKILL.md"),
    "chapter_judge": Path(".agents/skills/ruler-chapter-judge/SKILL.md"),
}


class ReadinessCheck(BaseModel):
    """One machine-readable readiness finding."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    status: CheckStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ResearchReadinessReport(BaseModel):
    """Complete preflight report for one research execution role."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    mode: ReadinessMode
    year: int
    methodology_ids: tuple[str, ...]
    provider_profile: str
    provider: str | None = None
    model: str | None = None
    eligible_ruler_count: int | None = None
    quarantined_ruler_count: int | None = None
    checks: tuple[ReadinessCheck, ...]


def build_research_readiness_report(
    engine: Engine,
    *,
    project_root: Path,
    mode: ReadinessMode,
    year: int,
    methodology_ids: tuple[str, ...],
    provider_profile: str,
    reviewer_profile: str | None = None,
    formatter_profile: str | None = None,
    output_dir: Path,
    model_profiles_path: Path | None = None,
    research_workflow_path: Path | None = None,
) -> ResearchReadinessReport:
    """Return a non-mutating readiness report for a researcher or chapter judge."""

    selected_ids = methodology_ids or all_ruler_quality_question_ids()
    checks: list[ReadinessCheck] = []
    checks.append(_database_check(engine, mode=mode))
    checks.extend(_question_checks(project_root, mode=mode, methodology_ids=selected_ids))
    checks.append(_role_skill_check(project_root, mode=mode))
    profile, profile_checks = _model_profile_checks(
        project_root,
        role=mode,
        provider_profile=provider_profile,
        model_profiles_path=model_profiles_path,
    )
    checks.extend(profile_checks)
    if mode == "dossier_researcher":
        for role, profile_name, prefix in (
            (
                "dossier_evidence_reviewer",
                reviewer_profile or provider_profile,
                "reviewer_",
            ),
            (
                "dossier_formatter",
                formatter_profile or provider_profile,
                "formatter_",
            ),
        ):
            _, execution_checks = _model_profile_checks(
                project_root,
                role=role,
                provider_profile=profile_name,
                model_profiles_path=model_profiles_path,
                check_id_prefix=prefix,
            )
            checks.extend(execution_checks)
        checks.append(
            _research_workflow_check(
                research_workflow_path or project_root / "configs/research-workflow.yaml"
            )
        )
    checks.append(_output_path_check(output_dir, allow_existing=mode == "chapter_judge"))

    eligible_count: int | None = None
    quarantined_count: int | None = None
    if not any(check.check_id == "database" and check.status == "fail" for check in checks):
        identity_check, eligible_count, quarantined_count = _identity_check(engine, year=year)
        checks.append(identity_check)

    return ResearchReadinessReport(
        ready=not any(check.status == "fail" for check in checks),
        mode=mode,
        year=year,
        methodology_ids=selected_ids,
        provider_profile=provider_profile,
        provider=profile.provider if profile else None,
        model=profile.model if profile else None,
        eligible_ruler_count=eligible_count,
        quarantined_ruler_count=quarantined_count,
        checks=tuple(checks),
    )


def _research_workflow_check(path: Path) -> ReadinessCheck:
    try:
        workflow = load_research_workflow(path)
    except (OSError, ValueError) as exc:
        return ReadinessCheck(
            check_id="research_workflow",
            status="fail",
            message="Direct-search research workflow is invalid or unreadable.",
            details={"path": str(path), "error_type": type(exc).__name__},
        )
    return ReadinessCheck(
        check_id="research_workflow",
        status="pass",
        message="Direct chapter-sequential research and review iteration are configured.",
        details={
            "path": str(path),
            "version": workflow.version,
            "chapter_order": list(workflow.chapter_order),
            "max_review_rounds": workflow.max_review_rounds,
        },
    )


def _database_check(engine: Engine, *, mode: ReadinessMode) -> ReadinessCheck:
    required = JUDGE_REQUIRED_TABLES if mode == "chapter_judge" else DOSSIER_REQUIRED_TABLES
    try:
        inspector = inspect(engine)
        existing = set(inspector.get_table_names())
    except Exception as exc:  # isolation boundary converted into a readiness finding
        return ReadinessCheck(
            check_id="database",
            status="fail",
            message="Database inspection failed.",
            details={"error_type": type(exc).__name__},
        )
    missing = tuple(table for table in required if table not in existing)
    if missing:
        return ReadinessCheck(
            check_id="database",
            status="fail",
            message="Required research database tables are missing.",
            details={"missing_tables": list(missing)},
        )
    missing_columns = (
        sorted(
            JUDGE_REQUIRED_CHAPTER_SCORE_COLUMNS
            - {column["name"] for column in inspector.get_columns("chapter_scores")}
        )
        if mode == "chapter_judge"
        else []
    )
    if missing_columns:
        return ReadinessCheck(
            check_id="database",
            status="fail",
            message="The chapter-score schema is missing required judge columns.",
            details={"missing_chapter_score_columns": missing_columns},
        )
    return ReadinessCheck(
        check_id="database",
        status="pass",
        message="Required research database tables are available.",
        details={"required_table_count": len(required)},
    )


def _question_checks(
    project_root: Path,
    *,
    mode: ReadinessMode,
    methodology_ids: tuple[str, ...],
) -> tuple[ReadinessCheck, ...]:
    invalid: list[str] = []
    missing_guides: list[str] = []
    guide_paths: dict[str, str] = {}
    draft_guides: set[str] = set()
    for methodology_id in methodology_ids:
        spec = get_question_spec_by_methodology_id(methodology_id)
        if spec is None or spec.evidence_strategy != "internet_manual":
            invalid.append(methodology_id)
            continue
        guide = _chapter_guide_path(project_root, methodology_id)
        if guide is None:
            missing_guides.append(methodology_id)
        else:
            guide_paths[methodology_id] = str(guide)
            if _guide_is_draft(guide):
                draft_guides.add(str(guide))

    checks = [
        ReadinessCheck(
            check_id="question_registry",
            status="fail" if invalid else "pass",
            message=(
                "Every selected methodology ID is a registered internet/manual question."
                if not invalid
                else "Some selected methodology IDs are not registered internet/manual questions."
            ),
            details={"selected_count": len(methodology_ids), "invalid_ids": invalid},
        ),
        ReadinessCheck(
            check_id="chapter_guides",
            status="fail" if missing_guides else "pass",
            message=(
                "Every selected question belongs to an active chapter guide."
                if not missing_guides
                else "Some selected questions do not have active chapter guides."
            ),
            details={"missing_ids": missing_guides, "guide_paths": guide_paths},
        ),
    ]
    if draft_guides:
        checks.append(
            ReadinessCheck(
                check_id="chapter_guide_lifecycle",
                status="warning",
                message="Selected chapter guides are drafts suitable only for smoke testing.",
                details={"draft_paths": sorted(draft_guides)},
            )
        )
    if mode == "chapter_judge":
        chapters = {methodology_id.split(".", maxsplit=1)[0] for methodology_id in methodology_ids}
        expected = {f"{chapter}.{index}" for chapter in chapters for index in range(1, 11)}
        valid_chapter_set = len(chapters) == 1 or chapters == {f"{index}B" for index in range(1, 9)}
        complete_chapter = (
            valid_chapter_set
            and set(methodology_ids) == expected
            and len(methodology_ids) == len(chapters) * 10
        )
        checks.append(
            ReadinessCheck(
                check_id="chapter_scope",
                status="pass" if complete_chapter else "fail",
                message=(
                    "The judge scope contains complete ten-lens chapter sets."
                    if complete_chapter
                    else "Judge planning requires one complete chapter or all eight."
                ),
                details={"chapter_ids": sorted(chapters), "lens_count": len(methodology_ids)},
            )
        )
    return tuple(checks)


def _role_skill_check(project_root: Path, *, mode: ReadinessMode) -> ReadinessCheck:
    path = project_root / ROLE_SKILL_PATHS[mode]
    exists = path.is_file()
    return ReadinessCheck(
        check_id="codex_role_skill",
        status="pass" if exists else "fail",
        message=(
            "The Codex-compatible role skill is available."
            if exists
            else "The Codex-compatible role skill is missing."
        ),
        details={"path": str(path)},
    )


def _model_profile_checks(
    project_root: Path,
    *,
    role: ResearchRole,
    provider_profile: str,
    model_profiles_path: Path | None,
    check_id_prefix: str = "",
) -> tuple[ResearchModelProfile | None, tuple[ReadinessCheck, ...]]:
    path = model_profiles_path or project_root / "configs/research-models.yaml"
    try:
        registry = load_research_model_profiles(path)
    except (OSError, ValueError) as exc:
        return None, (
            ReadinessCheck(
                check_id=f"{check_id_prefix}model_profiles",
                status="fail",
                message="Research model profile registry is invalid or unreadable.",
                details={"path": str(path), "error_type": type(exc).__name__},
            ),
        )
    profile = registry.profiles.get(provider_profile)
    if profile is None:
        return None, (
            ReadinessCheck(
                check_id=f"{check_id_prefix}model_profile",
                status="fail",
                message="Requested research model profile is not configured.",
                details={"profile": provider_profile},
            ),
        )
    checks: list[ReadinessCheck] = []
    role_supported = role in profile.roles
    checks.append(
        ReadinessCheck(
            check_id=f"{check_id_prefix}model_profile",
            status="pass" if role_supported else "fail",
            message=(
                "Requested model profile supports this role."
                if role_supported
                else "Requested model profile does not support this role."
            ),
            details={
                "profile": provider_profile,
                "provider": profile.provider,
                "model": profile.model,
                "cost_class": profile.cost_class,
                "context_window": profile.context_window,
            },
        )
    )
    config_path = Path(profile.codex_config_path).expanduser()
    checks.append(
        ReadinessCheck(
            check_id=f"{check_id_prefix}provider_configuration",
            status="pass" if config_path.is_file() else "fail",
            message=(
                "Provider configuration file is available; credentials were not read."
                if config_path.is_file()
                else "Provider configuration file is missing."
            ),
            details={"path": str(config_path)},
        )
    )
    credential_path = Path(profile.credential_path).expanduser()
    credential_available = credential_path.is_file() and credential_path.stat().st_size > 0
    checks.append(
        ReadinessCheck(
            check_id=f"{check_id_prefix}provider_credentials",
            status="pass" if credential_available else "fail",
            message=(
                "Provider credential material is present; its contents were not read."
                if credential_available
                else "Provider credential material is missing or empty."
            ),
            details={"path": str(credential_path)},
        )
    )
    return profile, tuple(checks)


def _output_path_check(output_dir: Path, *, allow_existing: bool = False) -> ReadinessCheck:
    candidate = output_dir.expanduser().resolve()
    ancestor = candidate
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    writable = ancestor.is_dir() and os.access(ancestor, os.W_OK)
    unsafe_existing = not allow_existing and candidate.exists() and any(candidate.iterdir())
    status: CheckStatus = "fail" if not writable or unsafe_existing else "pass"
    if not writable:
        message = "No writable existing ancestor is available for the output directory."
    elif unsafe_existing:
        message = "Output directory already exists and is not empty."
    else:
        message = (
            "Existing run directory is writable for isolated judge job artifacts."
            if allow_existing and candidate.exists()
            else "Output directory can be created without overwriting an existing run."
        )
    return ReadinessCheck(
        check_id="output_path",
        status=status,
        message=message,
        details={"path": str(candidate), "existing_ancestor": str(ancestor)},
    )


def _identity_check(
    engine: Engine,
    *,
    year: int,
) -> tuple[ReadinessCheck, int, int]:
    report = build_identity_coverage_gap_report(
        engine,
        year=year,
        include_out_of_scope=False,
    )
    eligible_classifications = {
        "resolved",
        "resolved_auto_single_candidate",
        "resolved_auto_role_priority",
        "resolved_auto_duration_majority",
        "resolved_auto_year_coverage_majority",
    }
    eligible = sum(row.classification in eligible_classifications for row in report.rows)
    quarantined = len(report.rows) - eligible
    status: CheckStatus = "pass" if eligible else "fail"
    message = (
        "Identity coverage has eligible ruler cases; unresolved cases will be quarantined."
        if eligible
        else "Identity coverage has no eligible ruler cases for the requested year."
    )
    return (
        ReadinessCheck(
            check_id="identity_coverage",
            status=status,
            message=message,
            details={
                "eligible_count": eligible,
                "quarantined_count": quarantined,
                "classification_counts": report.summary.classification_counts,
            },
        ),
        eligible,
        quarantined,
    )


def _chapter_guide_path(project_root: Path, methodology_id: str) -> Path | None:
    prefix = methodology_id.split(".", maxsplit=1)[0].lower() + "-"
    guide_dir = project_root / "docs/methodology/chapter-guides"
    matches = sorted(guide_dir.glob(f"{prefix}*.md"))
    return matches[0] if len(matches) == 1 else None


def _guide_is_draft(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", maxsplit=1)[1].replace("*", "").strip().lower()
            return status.startswith("draft")
    return False


def all_ruler_quality_question_ids() -> tuple[str, ...]:
    return tuple(
        spec.methodology_id
        for spec in list_question_specs()
        if "B." in spec.methodology_id
        and spec.methodology_id.rsplit(".", maxsplit=1)[-1].isdigit()
        and 1 <= int(spec.methodology_id.rsplit(".", maxsplit=1)[-1]) <= 10
        and spec.evidence_strategy == "internet_manual"
    )


__all__ = [
    "DOSSIER_REQUIRED_TABLES",
    "JUDGE_REQUIRED_TABLES",
    "ReadinessCheck",
    "ResearchModelProfile",
    "ResearchReadinessReport",
    "all_ruler_quality_question_ids",
    "build_research_readiness_report",
]
