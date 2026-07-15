"""Prompt construction for one ruler-period evidence worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_prior_package import compact_local_priors


def build_dossier_prompt(
    job: dict[str, Any],
    *,
    project_root: Path,
    worker_output_dir: Path,
    local_priors: tuple[dict[str, Any], ...] = (),
    existing_candidate: dict[str, Any] | None = None,
    research_notebook: str | None = None,
    evidence_preservation_floors: dict[str, int] | None = None,
) -> str:
    """Build a bounded prompt whose final response must be the dossier JSON."""

    question_ids = tuple(job["input"].get("question_ids", ()))
    if not question_ids:
        raise ValueError("dossier job has no selected question IDs")
    guides = list(
        dict.fromkeys(_guide_path(project_root, methodology_id) for methodology_id in question_ids)
    )
    payload = {
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"].get("ruler_year_id"),
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "methodology_ids": question_ids,
        "provider_profile": job["provider_profile"],
        "provider": job["provider"],
        "model": job["model"],
        "worker_output_dir": str(worker_output_dir),
    }
    local_prior_package = compact_local_priors(local_priors)
    return f"""Use the ruler-evidence-researcher skill for this job.

Read these required files before research:
- .agents/skills/ruler-evidence-researcher/SKILL.md
- docs/methodology/local-first-researcher-guide.md
- docs/methodology/ranking-evaluation-criteria.md
- docs/methodology/source-confidence-registry.json
{chr(10).join(f'- {path.relative_to(project_root)}' for path in guides)}

Job input:
{json.dumps(payload, indent=2, sort_keys=True)}

Deduplicated local structured evidence (client matrix excluded):
{json.dumps(local_prior_package.model_dump(mode="json"), indent=2, sort_keys=True)}

Permissive evidence-research notebook and handoff:
{research_notebook}

Existing candidate from a prior failed validation:
{json.dumps(existing_candidate, indent=2, sort_keys=True)}

Reviewed minimum distinct source-claim units to preserve by chapter:
{json.dumps(evidence_preservation_floors or {}, indent=2, sort_keys=True)}

Requirements:
- This is only a formatting and normalization pass.
  Interpret its prose, headings, tables, and JSON fragments flexibly. Preserve the
  researcher's claims, citations, caveats, main points, contrary evidence, and gaps;
  do not perform new research or discard material merely because its format varies.
- Treat the local structured priors above as the required local-first
  step. Do not rerun the local-evidence CLI when those payloads are present.
- Never use the client matrix as evidence.
- Do not search or add facts. The researcher has already completed direct internet
  research and reviewer-directed continuations in the notebook.
- Treat every `error_methodology_ids` entry as a blocking local-input failure, not
  missing evidence that internet material can silently replace. Preserve its compact
  disposition reason and instructions in the resulting gap or warning.
- Set each evidence `url` to either the exact HTTP(S) URL recorded by the researcher or
  `local-prior:<methodology-id>` for a claim taken directly from that question's
  hashed local-prior artifact. No other locator form is valid.
- Preserve one evidence object per defensible source-claim unit identified in the
  notebook. A source-claim unit is one traceable source supporting one materially
  distinct claim. The same URL may therefore appear in multiple evidence objects;
  do not collapse a report's distinct events, findings, decisions, or outcomes into
  one omnibus record merely because they share a source. Deduplicate only genuinely
  duplicate claims, then indicate every chapter lens each retained unit informs.
  Mapping and coverage wording are advisory handoff aids, not score-bearing decisions.
- Treat the evidence review's `defensible_evidence_estimate` for each chapter as a
  preservation floor for formatting, not a new research target. Retain at least that
  many distinct mapped source-claim units from the notebook unless the notebook itself
  explicitly retracts them; never manufacture or split claims mechanically to reach it.
- Before responding, count unique mapped evidence IDs separately for every chapter and
  verify each count meets the explicit reviewed minimum above. A mapping to one lens in
  a chapter is sufficient to count the retained source-claim unit for that chapter.
  Count only IDs that have both a complete declaration in `evidence` and at least one
  row in `mappings`; IDs mentioned only in `coverage` do not count. Ensure every ID in
  `coverage` is declared in `evidence` and joined through `mappings` before responding.
- Use simple stable evidence IDs when practical. The parent normalizes harmless ID,
  mapping, and coverage inconsistencies and records warnings rather than rejecting
  otherwise useful research.
- Every retained evidence item must appear in at least one `mappings` row so chapter
  judges can see it. Every mapping and coverage `evidence_id` must exactly equal one
  declared evidence ID; never concatenate, abbreviate, or combine evidence IDs.
  Reuse evidence across every genuinely relevant lens rather than leaving it invisible.
- Collect meaningful contrary evidence and explicit gaps. Do not assign scores.
- Use publication_date=unknown_not_exposed_by_source only when a reliable date
  cannot be established; never use null.
- Map general repression or protest-policing evidence as context unless the claim
  explains its specific incumbent-entrenchment mechanism.
- State source-type limitations and diversity in run_profile.source_mix_note.
- Populate local_priors with one schema-valid placeholder for every selected
  methodology ID using `methodology_statuses`; the parent replaces them with its
  complete hashed provenance before validation.
- The final response must be only one JSON object matching the supplied output schema.
- Echo the exact job/run/identity/period/model fields from Job input.
- Record unknown usage fields as unknown_not_exposed_by_tool; never invent usage.
- If Existing candidate is not null, this is a repair-only retry: preserve its valid
  claims and citations, but compare it against the complete inlined notebook and
  restore any defensible source-claim units it collapsed or omitted. Correct
  schema/reference defects, perform the final consistency check, and do not repeat
  research or broad file reading outside the supplied materials.
"""


def _guide_path(project_root: Path, methodology_id: str) -> Path:
    chapter = methodology_id.split(".", maxsplit=1)[0].lower()
    matches = tuple((project_root / "docs/methodology/chapter-guides").glob(f"{chapter}-*.md"))
    if len(matches) != 1:
        raise ValueError(f"chapter guide unavailable or ambiguous for {methodology_id}")
    return matches[0]


__all__ = ["build_dossier_prompt"]
