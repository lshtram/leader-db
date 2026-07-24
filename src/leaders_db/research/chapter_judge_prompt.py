"""Prompt construction for comparative chapter judging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chapter_projection import RulerChapterProjection


def build_chapter_judge_prompt(
    job: dict[str, Any],
    *,
    project_root: Path,
    guide_text: str,
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
    previous_candidate_path: Path | None = None,
    supplemental_instructions: str = "",
) -> str:
    """Build a no-discovery prompt for one chapter-wide comparative judgment."""

    manifest = [
        {
            "dossier_job_key": dossier.job_key,
            "iso3": dossier.iso3,
            "ruler_id": dossier.ruler_id,
            "ruler_year_id": dossier.ruler_year_id,
            "ruler_name": dossier.ruler_name,
            "period_start_year": dossier.period_start_year,
            "period_end_year": dossier.period_end_year,
        }
        for _, dossier in projections
    ]
    embedded_projections = [
        projection.model_dump(mode="json") for _, projection in projections
    ]
    unavailable = job["input"].get("unavailable_dossiers", [])
    repair_note = (
        "A prior candidate was semantically rejected. Produce a fresh complete batch "
        "from the embedded projections and correct the earlier defects; do not read "
        "the prior candidate from the filesystem."
        if previous_candidate_path is not None
        else "There is no prior candidate for this attempt."
    )
    return f"""You are the ruler-chapter-judge for one comparative batch.

Judge every dossier in the manifest using one common meter. The ten questions are
overlapping evidence lenses, not ten scores and not an arithmetic checklist.
Read each compact chapter projection in full and use only its cited web evidence and
its separately embedded `local_evidence` package. The parent has hash-bound each
projection to its complete source dossier and local-evidence artifact. Web evidence
uses E-IDs; structured local facts and signals use LF/LS IDs. Keep those provenance
families separate. Do not browse, search the web, use the client matrix, add facts from
memory, or rewrite a local fact as a web citation. Evidence IDs are local to each
dossier.

All scoring inputs are embedded below. Do not invoke shell commands, filesystem
tools, MCP resources, or local file reads. A local-tool failure is not a reason to
return null scores because the complete chapter projections are present in this prompt.
An `available` local package is authoritative structured context. An `unavailable` or
`invalid` local package lowers confidence when material but does not erase usable web
evidence or automatically force a null.

First inspect the whole batch and establish low, middle, high, and edge anchors.
Then score every available dossier exactly once. Missing lenses reduce confidence
and widen the plausible range; they do not mechanically lower the score. Use a
null score only when the chapter as a whole is genuinely not defensibly judgeable.
Treat projection coverage statuses and evidence-to-lens mappings as advisory
bookkeeping, not binding admissibility decisions. Apply every cited chapter evidence
item to the ten lenses yourself. A projection mapping does not make an item relevant:
the active guide's scope, non-goals, exclusions, and attribution limits are mandatory.
Identify and give zero scoring weight to mapped evidence that fails those gates; do not
use it as a positive, negative, contrary, or anchor reason. In particular,
`research_blocked` means that the
formatter did not record a complete lens disposition; it does not erase relevant
chapter evidence or require a null score.
Use half-point score increments. A numeric score must rest on a concrete record of
relevant governing conduct, not merely country indicators or evidence volume. For
Chapters 1B-6B and 8B, documented formal responsibility for national policy, programs,
appointments, command, implementation, tolerance, or remedy can satisfy attribution
without proof of a personal order. Chapter 7B requires a personal-integrity nexus.
Shared authority affects weight and confidence rather than automatically erasing the
evidence. Inherited conditions, generic country
context, intentions, missing implementation evidence, or missing adverse evidence
cannot determine the score's direction. If the record remains insufficient, return null with
the full 1-10 range. Cite the qualifying ruler-attribution evidence by stable E-ID in
a decisive web-evidence array. Local structured evidence is country-level context and
cannot support a numeric ruler score by itself. Use `decisive_local_evidence` only
alongside a decisive E-ID that establishes the ruler's relevant authority or nexus;
use `contextual_local_evidence` for baselines or signals that frame interpretation
without independently determining direction. Never
attach `recoverable_null` to a numeric score. Reserve
manual review for a concrete issue that could materially change the chapter result;
do not flag ordinary uncertainty already represented by confidence and range.
Before scoring each ruler: (1) establish the information environment and evidence
opportunity; (2) identify the inherited baseline and external shocks; (3) establish
formal and practical ruler authority; (4) collapse repeated coverage into independent
underlying facts; (5) compare absolute conditions with change from baseline; and
(6) compare the ruler with adjacent cases. Then make the holistic judgment. Preserve
inherited conditions, ruler authority, contrary evidence, source bias, and adjacent-case
comparisons. Evidence references must use IDs from that ruler's
own dossier and must not cite `discovery_only` items as decisive evidence. For a
batch with multiple rulers, `calibrated_against` must name at least one other
available dossier job key. Put guide-specific additions such as `trajectory` in
the `chapter_specific` field/value list. Natural language inside semantic fields
is welcome.

Every evaluation must include a substantive `bias_assessment`. Cite the dossier E-IDs
that support each material bias finding, state its likely direction and how it changed
interpretation, and explain the effect on confidence and plausible range. Confirm that
complaint/report volume was not treated as severity and that no blanket democracy or
autocracy score correction was applied. Closed-system silence is not favorable evidence;
open-system disclosure and remedy are not additional misconduct.

Write `chapter_rationale` as a self-contained reader-facing abstract, not as terse
notes between specialists. Assume the reader knows the ruler's name but does not
know the events, institutions, controversies, programs, or acronyms in the dossier.
Keep it concise: normally 120-220 words and never more than 300 words. Keep every
other prose field to one or two sentences. Spend output tokens on completing and
validating all evaluations, not on repeating dossier evidence.
Use this order: (1) state the overall chapter appraisal and score in plain language;
(2) explain the main favorable and unfavorable findings, identifying what each
specific case was and why it matters; (3) distinguish proven facts from allegations,
institutional context, and uncertain ruler attribution; and (4) conclude why the
evidence supports this score rather than a materially higher or lower one. Define
unfamiliar cases on first mention. Do not open with an unexplained case name, event,
acronym, or compressed phrase such as "the X scrutiny." The abstract must answer the
chapter question for a reader who has not read the dossier.

Retry context: {repair_note}

Run-scoped audit corrections (mandatory; they may exclude evidence but may not
prescribe a score):
{supplemental_instructions or "None."}

Immutable batch identity:
{json.dumps({
    "schema_version": "ruler_chapter_judgment_v1",
    "job_key": job["job_key"],
    "run_key": job["run_key"],
    "chapter_id": job["input"]["chapter_id"],
    "target_year": job["target_year"],
    "calibration_batch_id": job["job_key"],
}, indent=2)}

Unavailable dossiers (report them, do not invent evaluations):
{json.dumps(unavailable, indent=2)}

Available dossier manifest:
{json.dumps(manifest, indent=2)}

Embedded chapter projections (authoritative judge inputs):
{json.dumps(embedded_projections, indent=2, sort_keys=True)}

Active chapter guide:
---
{guide_text}
---

Return only the requested JSON batch. Include one evaluation per available
dossier, the unavailable manifest unchanged, substantive calibration notes, and
the run profile. If token usage is unavailable, use
`unknown_not_exposed_by_tool`; the parent will stamp observed usage when exposed.
Before returning, verify that every numeric evaluation cites at least one valid
same-dossier E-ID in its decisive positive or negative evidence arrays; that every
LF/LS ID in `decisive_local_evidence` accompanies such a decisive E-ID; that
`structured_prior_summary` accurately describes the embedded local package; and that
every confidence score is on the required 0-100 scale.
"""


__all__ = ["build_chapter_judge_prompt"]
