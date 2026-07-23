"""Short reconnaissance prompt for ruler evidence research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_prior_package import build_local_research_briefing
from .research_workflow import ResearchWorkflow


def build_research_notebook_prompt(
    job: dict[str, Any],
    *,
    project_root: Path,
    worker_output_dir: Path,
    local_priors: tuple[dict[str, Any], ...],
    workflow: ResearchWorkflow,
) -> str:
    """Build a small orientation prompt; deep research happens chapter by chapter."""

    del project_root
    question_ids = tuple(job["input"]["question_ids"])
    job_payload = {
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "selected_chapters": sorted(
            {item.split(".", maxsplit=1)[0] for item in question_ids}
        ),
        "research_materials_path": str(worker_output_dir / "research-materials.md"),
        "research_ledger_manifest_path": str(
            worker_output_dir / "research-ledger-manifest.json"
        ),
    }
    briefing = build_local_research_briefing(local_priors)
    return f"""Research the named ruler and period without scoring.

This is a short reconnaissance turn. Later turns will resume this exact session once
per selected chapter with that chapter's ten questions. Do not attempt the complete
dossier now.

Job:
{json.dumps(job_payload, separators=(",", ":"), sort_keys=True)}

What the local pipeline already knows:
{json.dumps(briefing, separators=(",", ":"), sort_keys=True, default=str)}

The local briefing is orientation, not web evidence and not ruler attribution. The
parent retains the complete local package; do not request or reconstruct it. Avoid
re-fetching listed structured datasets unless a specific web source is needed to
interpret a material gap.

Use web search and open promising underlying sources. Search results and snippets are
discovery only. Prefer primary records plus independent high-quality analysis, include
credible contrary material, and use local-language searches where useful. Never use a
recent-news filter for this historical period.

In this turn:
1. verify ruler identity, practical authority, and important constraints;
2. identify major period events and the information environment;
3. find 8-15 reusable cross-chapter source-claim units when genuinely useful;
4. give a brief chapter search plan naming unresolved themes and likely source families.

For every accepted unit, preserve one material claim, canonical URL, publisher/date,
precise locator, period fit, attribution limits, contrary evidence, and applicable
methodology IDs. Keep stable IDs and append to `research-materials.md`. Maintain one
cumulative `research-ledger-manifest.json`; later turns must extend, never replace, it.
If file writing fails, include the complete handoff in the response.

Do not pad counts, infer favorable conduct from missing reporting, confuse complaint
volume with severity, count repeated coverage as independent corroboration, turn
country context into personal conduct, or treat allegations as findings. Chapter 7B
requires a personal integrity nexus. Missing evidence lowers confidence later; it does
not invalidate useful research.

Finish with sources opened and retained, the evidence-environment summary, and the
chapter-by-chapter gaps. This turn is reconnaissance only.
"""


__all__ = ["build_research_notebook_prompt"]
