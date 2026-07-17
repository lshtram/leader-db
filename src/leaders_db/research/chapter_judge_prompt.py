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
Read each compact chapter projection in full and use only its cited evidence and
local-prior summaries. The parent has hash-bound each projection to its complete
source dossier. Do not browse, search the web, use the client matrix, or add facts from
memory. Evidence IDs are local to each dossier.

All scoring inputs are embedded below. Do not invoke shell commands, filesystem
tools, MCP resources, or local file reads. A local-tool failure is not a reason to
return null scores because the complete chapter projections are present in this prompt.

First inspect the whole batch and establish low, middle, high, and edge anchors.
Then score every available dossier exactly once. Missing lenses reduce confidence
and widen the plausible range; they do not mechanically lower the score. Use a
null score only when the chapter as a whole is genuinely not defensibly judgeable.
Treat projection coverage statuses and evidence-to-lens mappings as advisory
bookkeeping, not binding admissibility decisions. Apply every cited chapter evidence
item to the ten lenses yourself. In particular, `research_blocked` means that the
formatter did not record a complete lens disposition; it does not erase relevant
chapter evidence or require a null score.
Use half-point score increments. A numeric score must rest on at least one direct,
ruler-attributed, chapter-discriminating fact. Documented formal authority for a
national policy, program, appointment, or state action can satisfy ruler attribution
when the evidence and guide support authority-based responsibility; a personal order
is not required in every case. Inherited conditions, generic country
context, intentions, missing implementation evidence, or missing adverse evidence
cannot determine the score's direction. If that floor is not met, return null with
the full 1-10 range. Cite the qualifying fact by stable E-ID in at least one of the
decisive evidence arrays. Never attach `recoverable_null` to a numeric score. Reserve
manual review for a concrete issue that could materially change the chapter result;
do not flag ordinary uncertainty already represented by confidence and range.
Preserve inherited conditions, ruler authority, contrary evidence, source bias,
and adjacent-case comparisons. Evidence references must use IDs from that ruler's
own dossier and must not cite `discovery_only` items as decisive evidence. For a
batch with multiple rulers, `calibrated_against` must name at least one other
available dossier job key. Put guide-specific additions such as `trajectory` in
the `chapter_specific` field/value list. Natural language inside semantic fields
is welcome.

Retry context: {repair_note}

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
"""


__all__ = ["build_chapter_judge_prompt"]
