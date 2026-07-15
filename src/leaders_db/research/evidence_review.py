"""Deterministic and model-assisted review of a schema-light research notebook."""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .research_workflow import ResearchWorkflow


class NotebookQAFinding(BaseModel):
    """One deterministic reason to inspect or continue a notebook."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    message: str


class NotebookQAReport(BaseModel):
    """Pure, cheap QA used to decide whether model review is warranted."""

    model_config = ConfigDict(extra="forbid")

    selected_chapter_ids: tuple[str, ...]
    observed_chapter_ids: tuple[str, ...]
    approximate_locator_count: int
    approximate_source_family_count: int
    minimum_source_claim_units_per_chapter: int
    minimum_independent_source_families_per_chapter: int
    needs_reviewer: bool
    findings: tuple[NotebookQAFinding, ...]


class ChapterEvidenceReview(BaseModel):
    """Reviewer assessment of one selected chapter's evidence handoff."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    defensible_evidence_estimate: int = Field(ge=0)
    independent_source_family_estimate: int = Field(ge=0)
    attribution_risk: Literal["low", "medium", "high"]
    substantive_issues: tuple[str, ...]
    missing_themes: tuple[str, ...]


class EvidenceReviewReport(BaseModel):
    """No-search, no-score reviewer brief for one possible researcher resume."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ruler_evidence_review_v1"]
    needs_continuation: bool
    selected_theme_ids: tuple[str, ...] = Field(max_length=8)
    chapter_reviews: tuple[ChapterEvidenceReview, ...]
    global_findings: tuple[str, ...]
    reviewer_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _continuation_has_themes(self) -> EvidenceReviewReport:
        if self.needs_continuation != bool(self.selected_theme_ids):
            raise ValueError(
                "needs_continuation must match whether selected_theme_ids is non-empty"
            )
        if len(self.selected_theme_ids) != len(set(self.selected_theme_ids)):
            raise ValueError("selected_theme_ids must be unique")
        reviewed = {item.chapter_id for item in self.chapter_reviews}
        if not set(self.selected_theme_ids).issubset(reviewed):
            raise ValueError("selected continuation themes must have chapter reviews")
        return self


def assess_research_notebook(
    notebook: str,
    *,
    methodology_ids: tuple[str, ...],
    workflow: ResearchWorkflow | None = None,
) -> NotebookQAReport:
    """Flag structural evidence-quality risks without interpreting ruler quality."""

    minimum_units = workflow.minimum_source_claim_units_per_chapter if workflow is not None else 5
    minimum_families = (
        workflow.minimum_independent_source_families_per_chapter if workflow is not None else 3
    )
    selected = tuple(sorted({item.split(".", maxsplit=1)[0] for item in methodology_ids}))
    observed = tuple(
        chapter
        for chapter in selected
        if re.search(rf"(?<![A-Z0-9]){re.escape(chapter)}(?![A-Z0-9])", notebook)
    )
    locators = set(re.findall(r"https?://[^\s>)\]}]+|local-prior:[1-8]B\.\d+", notebook))
    source_families = {_source_family(locator) for locator in locators if _source_family(locator)}
    findings: list[NotebookQAFinding] = []
    if len(notebook.strip()) < 2_000:
        findings.append(
            NotebookQAFinding(
                check_id="notebook_too_short",
                message="Notebook is too short for a full evidence audit.",
            )
        )
    missing = tuple(chapter for chapter in selected if chapter not in observed)
    if missing:
        findings.append(
            NotebookQAFinding(
                check_id="missing_chapter_sections",
                message=f"No explicit notebook section found for: {', '.join(missing)}.",
            )
        )
    minimum_locators = max(minimum_units, len(selected) * minimum_units)
    if len(locators) < minimum_locators:
        findings.append(
            NotebookQAFinding(
                check_id="low_locator_yield",
                message=(
                    f"Only {len(locators)} unique locators were observed; "
                    f"the soft review threshold is {minimum_locators}."
                ),
            )
        )
    minimum_family_total = max(minimum_families, len(selected) * minimum_families)
    if len(source_families) < minimum_family_total:
        findings.append(
            NotebookQAFinding(
                check_id="low_source_family_yield",
                message=(
                    f"Only {len(source_families)} approximate source families were "
                    f"observed; the soft review threshold is {minimum_family_total}."
                ),
            )
        )
    lowered = notebook.lower()
    for check_id, phrase, message in (
        ("missing_contrary_audit", "contrary", "Contrary evidence is not explicit."),
        ("missing_gap_audit", "gap", "Unresolved evidence gaps are not explicit."),
        (
            "missing_local_audit",
            "local-data audit",
            "The required local-data disposition audit is not explicit.",
        ),
    ):
        if phrase not in lowered:
            findings.append(NotebookQAFinding(check_id=check_id, message=message))
    return NotebookQAReport(
        selected_chapter_ids=selected,
        observed_chapter_ids=observed,
        approximate_locator_count=len(locators),
        approximate_source_family_count=len(source_families),
        minimum_source_claim_units_per_chapter=minimum_units,
        minimum_independent_source_families_per_chapter=minimum_families,
        needs_reviewer=bool(findings),
        findings=tuple(findings),
    )


def validate_review_scope(
    report: EvidenceReviewReport,
    *,
    selected_chapter_ids: tuple[str, ...],
    expected_chapter_ids: tuple[str, ...] | None = None,
) -> None:
    """Reject a reviewer that omits expected chapters or expands immutable scope."""

    selected = set(selected_chapter_ids)
    expected = (
        selected if expected_chapter_ids is None else set(expected_chapter_ids)
    )
    reviewed = {item.chapter_id for item in report.chapter_reviews}
    continuation = set(report.selected_theme_ids)
    if (
        not expected.issubset(reviewed)
        or not reviewed.issubset(selected)
        or not continuation.issubset(reviewed)
    ):
        raise ValueError("evidence review differs from the selected chapter scope")


def build_evidence_review_prompt(
    *, job: dict[str, Any], notebook: str, qa: NotebookQAReport
) -> str:
    """Build a strict, no-search reviewer prompt without ruler scoring."""

    workflow_payload = job.get("input", {}).get("research_workflow")
    workflow = (
        ResearchWorkflow.model_validate(workflow_payload) if workflow_payload is not None else None
    )
    configured_qa = assess_research_notebook(
        notebook,
        methodology_ids=tuple(job.get("input", {}).get("question_ids", ()))
        or qa.selected_chapter_ids,
        workflow=workflow,
    )
    identity = {
        key: job.get(key)
        for key in (
            "job_key",
            "iso3",
            "country_name",
            "ruler_name",
            "period_start_year",
            "period_end_year",
        )
    }
    return f"""You are an evidence-quality reviewer, not a ruler judge.

Review the schema-light notebook for the immutable ruler-period below. Do not browse,
open URLs, add facts from memory, rewrite the notebook, or assign scores. Formatting
imperfections are not evidence defects. Assess defensible source-claim units, source
independence, target-period fit, ruler attribution, contrary evidence, local-fact use,
and exact missing themes. Missing evidence is not negative ruler evidence.

Treat these as substantive evidence defects rather than formatting preferences:
- an HTTP source without a precise page/section/paragraph/table/timestamp locator;
- a homepage, search result, document index, or labels such as `release page` or
  `article` used as though they were precise locators;
- a gateway source used without its underlying source URL;
- multiple sources or materially distinct claims bundled into one evidence item;
- the same source-locator-claim fact recreated under chapter-specific IDs instead of
  one stable global ID with many-to-many lens mappings;
- country, institutional, election-result, or subordinate conduct attributed directly
  to the ruler without evidence of direction, ownership, knowledge, benefit, tolerance,
  obstruction, correction, or authority-based responsibility;
- post-period outcomes presented as target-period events; or
- any researcher-written score, score range, anchor, ranking recommendation, or advice
  that a judge should score or return null.

Exclude gateway-only, locator-missing, bundled, and duplicated copies from the
`defensible_evidence_estimate`. Put deterministic cleanup defects in
`substantive_issues`; select a chapter for continuation only when web research can
materially recover an underlying source, locator, attribution fact, contrary source,
or missing event theme.

Apply the configured marginal-value gate before selecting any continuation chapter.
A further broad round is justified only when it is reasonably likely to add at least
`continuation_minimum_expected_new_units_per_selected_chapter` new defensible,
precisely located source-claim units in that selected chapter, or to close a material
ruler-attribution blocker. Deduplication, splitting bundled claims, neutral wording,
lens dispositions, count reconciliation, and formatter work are deterministic cleanup
and never justify another web-research round. After one continuation, prefer stopping
broad research and naming at most three optional targeted themes when the remaining
gaps are mainly attribution-limited or show diminishing returns.

Return all selected chapters exactly once. Select every chapter with a material,
research-recoverable attribution, temporal, source-quality, event-coverage, contrary-
evidence, or evidence-yield gap. Do not limit the review to the three weakest chapters.
If the notebook gives a credible saturation or access-blocker explanation and another
search round is unlikely to improve it, do not select that chapter. If no continuation
would materially improve the dossier, return needs_continuation=false and an empty
selected_theme_ids list.

Immutable job:
{json.dumps(identity, indent=2)}

Deterministic QA:
{configured_qa.model_dump_json(indent=2)}

Configured research workflow:
{workflow.model_dump_json(indent=2) if workflow is not None else "not supplied"}

Research notebook:
---
{notebook}
---
"""


def _source_family(locator: str) -> str:
    if locator.startswith("local-prior:"):
        return "local-prior"
    return urlsplit(locator).netloc.lower().removeprefix("www.")


def evidence_review_json_schema() -> dict[str, Any]:
    """Return the strict-output schema accepted by Codex exec."""

    schema = EvidenceReviewReport.model_json_schema()
    _require_every_property(schema)
    return schema


def _require_every_property(node: object) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
        for value in node.values():
            _require_every_property(value)
    elif isinstance(node, list):
        for value in node:
            _require_every_property(value)


__all__ = [
    "EvidenceReviewReport",
    "NotebookQAReport",
    "assess_research_notebook",
    "build_evidence_review_prompt",
    "evidence_review_json_schema",
    "validate_review_scope",
]
