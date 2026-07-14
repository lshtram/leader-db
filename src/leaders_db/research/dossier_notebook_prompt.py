"""Prompt for the evidence-focused, schema-light ruler research pass."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_prior_package import compact_local_priors
from .research_workflow import ResearchWorkflow


def build_research_notebook_prompt(
    job: dict[str, Any],
    *,
    project_root: Path,
    worker_output_dir: Path,
    local_priors: tuple[dict[str, Any], ...],
    workflow: ResearchWorkflow,
) -> str:
    """Ask the researcher to maximize cited material rather than serialize a dossier."""

    question_ids = tuple(job["input"]["question_ids"])
    guides = tuple(
        sorted(
            {
                next(
                    (project_root / "docs/methodology/chapter-guides").glob(
                        f"{item.split('.', maxsplit=1)[0].lower()}-*.md"
                    )
                )
                for item in question_ids
            }
        )
    )
    job_payload = {
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"]["ruler_year_id"],
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "methodology_ids": question_ids,
        "research_materials_path": str(worker_output_dir / "research-materials.md"),
    }
    guide_material = "\n\n".join(
        f"## {path.relative_to(project_root)}\n\n{path.read_text(encoding='utf-8')}"
        for path in guides
    )
    local_prior_package = compact_local_priors(local_priors)
    return f"""Use the ruler-evidence-researcher skill for an evidence-collection pass.

Read:
- .agents/skills/ruler-evidence-researcher/SKILL.md
- docs/methodology/local-first-researcher-guide.md
- docs/methodology/ranking-evaluation-criteria.md
- docs/methodology/source-confidence-registry.json
{chr(10).join(f'- {path.relative_to(project_root)}' for path in guides)}

Job:
{json.dumps(job_payload, indent=2, sort_keys=True)}

Deduplicated local structured evidence package:
{json.dumps(local_prior_package.model_dump(mode="json"), indent=2, sort_keys=True)}

Research workflow:
    {json.dumps(workflow.model_dump(mode="json"), indent=2, sort_keys=True)}

Chapter guides (inlined because some low-cost execution profiles cannot read files):
{guide_material}

Your task is research, not final formatting. Start with the deduplicated local
package before inspecting internet discovery. Establish a chapter-by-chapter local
baseline: which facts exist, their exact years/sources/warnings, what they measure,
what is only country or inherited-capacity context, and which attribution or narrative
gaps require internet evidence. Do not re-fetch a structured dataset already supplied
locally. Absence of a local row is a gap, not proof that the real-world condition was
zero, peaceful, safe, responsible, or inapplicable. The package's
`candidate_methodology_ids` are routing hints, not proof that a fact directly answers
every listed lens; decide and explain actual reuse yourself.
Any `error_methodology_ids` entry is a local-input failure, not ordinary missing
evidence: flag it as a blocking data-quality issue in the handoff and never conceal
it by substituting web evidence. Use the referenced disposition reason and guidance
to distinguish an extraction error, absent country-year, empty mapped fields, and a
genuinely inapplicable lens.

Then work through chapters 1B to 8B in order. For each selected chapter, build a
short event/topic inventory, search the internet directly, inspect promising sources,
and follow new leads until you are reasonably satisfied that the material positive,
negative, mixed, and contrary evidence has been found. Do not stop after one broad
query. Use multiple focused searches for distinct events, decisions, outcomes,
institutions, and competing interpretations. Adjust depth to evidence abundance: a
globally prominent contemporary ruler normally requires substantially more searching
than an obscure or closed historical case. Record why you believe each chapter is
saturated or why further improvement is blocked.

Record
accepted material as you go in `research-materials.md` inside the supplied output
directory. Markdown, tables, JSON fragments, and prose are all acceptable.

For every retained evidence item record:
- a stable provisional ID;
- exact approved URL or canonical `local-prior:<methodology_id>` locator from the
  supplied fact record;
- title, publisher, and date when known;
- factual claim and a concise main-points summary;
- useful excerpt or precise locator;
- source type/confidence and limitations;
- target-period fit and ruler attribution;
- contrary or mitigating points;
- candidate chapters and lenses it can inform.

Aim for 5–20 defensible source-claim units per selected chapter, normally about 10.
A source-claim unit is one traceable source supporting one materially distinct claim;
a heading, excerpt, paragraph, empty prior, alternate/AMP URL, or repeated statement
is not another item. Normally retain at most two units from one URL and justify any
exception. Reuse one stable item across chapters instead of duplicating it globally.
This is a goal, not a hard gate: never pad, invent, or lower source standards to meet
a count. If a chapter remains below five, inspect every supplied candidate, record
candidate-level rejection reasons, and name the exact missing themes and source types.

For each chapter, report both mapped source-claim units and independent locator/source
families. Seek at least three source organizations and two source types when the
available evidence permits, but do not manufacture diversity. Treat post-period material
as context unless it directly establishes a target-period fact. Empty or
`no_evidence_found` priors are gap signals and never retained evidence.

Do not assign scores. Do not use the client matrix. Your final response is a flexible research
handoff summarizing the global evidence register, chapter yield and source diversity,
same-URL splits, cross-chapter reuse, rejected candidates, strongest contrary
evidence, and unresolved gaps. Self-audit temporal fit, ruler attribution, weak or
context-only items, and claims lacking independent corroboration. Include a local-data
audit stating which supplied fact IDs were retained, used as context, or left unused
and why. It does not need to match a JSON schema.
"""


__all__ = ["build_research_notebook_prompt"]
