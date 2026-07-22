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


class EvidenceBiasReview(BaseModel):
    """No-search review of visibility, independence, and interpretation risks."""

    model_config = ConfigDict(extra="forbid")

    favorable_and_adverse_search: str = Field(min_length=1)
    closed_system_silence: str = Field(min_length=1)
    open_system_complaint_volume: str = Field(min_length=1)
    duplicate_reporting: str = Field(min_length=1)
    allegations_vs_findings: str = Field(min_length=1)
    official_claim_independence: str = Field(min_length=1)
    population_exposure_authority_baseline_shocks: str = Field(min_length=1)
    missing_source_type: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...]
    unresolved_risks: tuple[str, ...]


def _legacy_unassessed_bias_review() -> EvidenceBiasReview:
    """Preserve old review artifacts while making their unassessed state explicit."""

    unknown = "Not assessed by the legacy reviewer contract."
    return EvidenceBiasReview(
        favorable_and_adverse_search=unknown,
        closed_system_silence=unknown,
        open_system_complaint_volume=unknown,
        duplicate_reporting=unknown,
        allegations_vs_findings=unknown,
        official_claim_independence=unknown,
        population_exposure_authority_baseline_shocks=unknown,
        missing_source_type=unknown,
        supporting_evidence_ids=(),
        unresolved_risks=("Bias review was not collected under the legacy contract.",),
    )


class ChapterEvidenceReview(BaseModel):
    """Reviewer assessment of one selected chapter's evidence handoff."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    defensible_evidence_estimate: int = Field(ge=0)
    independent_source_family_estimate: int = Field(ge=0)
    attribution_risk: Literal["low", "medium", "high"]
    substantive_issues: tuple[str, ...]
    missing_themes: tuple[str, ...]
    bias_review: EvidenceBiasReview = Field(default_factory=_legacy_unassessed_bias_review)


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
    notebook: str | None = None,
) -> None:
    """Reject scope changes and, when supplied, invented notebook evidence IDs."""

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
    if notebook is None:
        return
    referenced_ids = {
        evidence_id
        for review in report.chapter_reviews
        for evidence_id in review.bias_review.supporting_evidence_ids
    }
    unknown_ids = sorted(
        evidence_id
        for evidence_id in referenced_ids
        if re.search(
            rf"(?<![A-Z0-9-]){re.escape(evidence_id)}(?![A-Z0-9-])", notebook
        )
        is None
    )
    if unknown_ids:
        raise ValueError(
            "evidence review cites unknown notebook evidence IDs: "
            + ", ".join(unknown_ids)
        )


def normalize_review_evidence_references(
    report: EvidenceReviewReport, *, notebook: str
) -> EvidenceReviewReport:
    """Drop invented reviewer citations while retaining their uncertainty as text."""

    payload = report.model_dump(mode="json")
    changed = False
    for review in payload["chapter_reviews"]:
        bias = review["bias_review"]
        retained: list[str] = []
        dropped: list[str] = []
        for evidence_id in bias["supporting_evidence_ids"]:
            if re.search(
                rf"(?<![A-Z0-9-]){re.escape(evidence_id)}(?![A-Z0-9-])", notebook
            ):
                retained.append(evidence_id)
            else:
                dropped.append(evidence_id)
        if not dropped:
            continue
        changed = True
        bias["supporting_evidence_ids"] = retained
        bias["unresolved_risks"].append(
            "Reviewer references absent from the notebook were removed: "
            + ", ".join(dropped)
        )
    return EvidenceReviewReport.model_validate(payload) if changed else report


def build_evidence_review_prompt(
    *,
    job: dict[str, Any],
    notebook: str,
    qa: NotebookQAReport,
    terminal: bool = False,
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
    selected_methodology_ids = tuple(job.get("input", {}).get("question_ids", ()))
    terminal_instruction = (
        """
This is the terminal review after all permitted research rounds. Do not request
another continuation. Set `needs_continuation=false` and `selected_theme_ids=[]`.
Preserve every residual issue and missing theme, and state explicitly in
`global_findings` that research rounds were exhausted without full saturation. This
is a terminal research conclusion, not a claim that the dossier is complete.
"""
        if terminal
        else ""
    )
    return f"""You are an evidence-quality reviewer, not a ruler judge.
{terminal_instruction}

Review the schema-light notebook for the immutable ruler-period below. Do not browse,
open URLs, add facts from memory, rewrite the notebook, or assign scores. Formatting
imperfections are not evidence defects. Assess defensible source-claim units, source
independence, target-period fit, ruler attribution, contrary evidence, local-fact use,
and exact missing themes. Missing evidence is not negative ruler evidence.

For every chapter, complete `bias_review` from the notebook and cite its stable evidence
IDs where available. Explicitly assess whether favorable and adverse searches were both
performed; whether closed-system silence could hide misconduct; whether open-system
complaint volume could exaggerate apparent severity; whether repeated coverage describes
one underlying fact; whether allegations are separated from findings; whether official
claims have independent checks; whether population, exposure, authority, inherited
baseline, and external shocks are addressed; and whether the source type needed to
resolve the chapter's principal bias risk is missing. `supporting_evidence_ids` must
contain only IDs actually present in the notebook. Record credible blockers and residual
risks rather than inventing completeness. A bias gap requires continuation only when
another bounded search can materially improve it; otherwise preserve it as unresolved
for confidence and interpretation downstream.

The immutable selected lens scope is:
{json.dumps(selected_methodology_ids, indent=2)}

Review only those exact lenses. A full chapter job selects all ten chapter lenses; a
bounded one-lens pilot does not. Do not require, research, or list unselected sibling
lenses as missing themes, and do not expand continuation beyond the selected lens
scope. Return the containing selected chapter exactly once, but judge its evidence
adequacy only for the selected methodology IDs above.

Use proportional attribution. For Chapters 1B-6B and 8B, cited formal responsibility
for national policy, appointments, command, implementation, tolerance, or remedy can be
sufficient without proof of a personal order. Chapter 7B requires a personal-integrity
nexus. Shared authority or constraints reduce attribution strength rather than erasing
otherwise relevant evidence.

Treat these as substantive evidence defects rather than formatting preferences:
- a claim whose underlying source cannot be identified or does not support it;
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

Exclude gateway-only and duplicated copies from the `defensible_evidence_estimate`.
Treat an identified credible source with a missing precise locator as a recoverable
extraction task, not proof that evidence is absent. Select a chapter for continuation
when opening/fetching can recover the locator or research can recover an attribution
fact, contrary source, or missing event theme.

Do not use workflow exhaustion, low current evidence count, or a guessed marginal-
value threshold as a saturation finding. If the notebook names promising unfetched
sources, contains snippet-only candidates, lacks candidate breadth, or omitted local-
language/source-specific searches for a well-covered case, require continuation.
Deduplication, splitting bundled claims, neutral wording, lens dispositions, and count
reconciliation remain deterministic cleanup rather than web-research tasks.

Return all selected chapters exactly once. Select every chapter with a material,
research-recoverable attribution, temporal, source-quality, event-coverage, contrary-
evidence, or evidence-yield gap. Do not limit the review to the three weakest chapters.
Do not pass a chapter merely because it has several sources or indicators. Pass it only
when the concrete evidence is sufficient to present the relevant governing conduct,
important contrary material, and attribution fairly, or when a credible blocker shows
that another search round is unlikely to improve it.
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
    "EvidenceBiasReview",
    "EvidenceReviewReport",
    "NotebookQAReport",
    "assess_research_notebook",
    "build_evidence_review_prompt",
    "evidence_review_json_schema",
    "normalize_review_evidence_references",
    "validate_review_scope",
]
