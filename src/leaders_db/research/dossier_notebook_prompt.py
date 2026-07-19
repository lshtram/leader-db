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
        "research_ledger_manifest_path": str(
            worker_output_dir / "research-ledger-manifest.json"
        ),
    }
    guide_material = "\n\n".join(
        f"## {path.relative_to(project_root)}\n\n{path.read_text(encoding='utf-8')}"
        for path in guides
    )
    # Chapter guides already contain the research lenses. Avoid reinjecting the full
    # product, judge, and process manuals into a low-cost researcher's context.
    required_methodology_paths = (
        project_root / "docs/methodology/source-confidence-registry.json",
    )
    required_methodology = "\n\n".join(
        f"## Required methodology: {path.relative_to(project_root)}\n\n"
        f"{path.read_text(encoding='utf-8')}"
        for path in required_methodology_paths
    )
    local_prior_package = compact_local_priors(local_priors)
    return f"""Perform an evidence-collection pass using the compact execution contract,
local facts, source registry, and chapter research lenses inlined below. Do not read
additional local files during this worker run.

Tool discipline:
- Use the configured reliable search and source-retrieval tools. On MiniMax profiles,
  prefer the provider-native MiniMax Search or Brave search for discovery and use the
  credential-free Fetch MCP for known source URLs. Use Parallel only after a call has
  succeeded in the active execution profile; a rejected or malformed Parallel call is
  a tool failure, not a completed search. Do not use Playwright for ordinary text
  research. Independent discovery calls may run concurrently within provider limits;
  preserve tool and query provenance.
- Do not call image or image-inspection tools for text files, test tool access with
  unrelated paths, inspect system files, or request elevated permissions.
- The desired local writes are the supplied `research_materials_path` and
  `research_ledger_manifest_path`. If writing either is unavailable, continue the
  research and put the complete handoff in the final response for parent persistence.
- A rejected tool call is not a reason to experiment with other unrelated tools or
  paths. Continue with available web research and the inlined material.
- Never request a recency or recent-news filter for a historical ruler-period. Search
  results are discovery candidates; open or fetch promising underlying sources before
  deciding whether they are evidence.

Job:
{json.dumps(job_payload, indent=2, sort_keys=True)}

Deduplicated local structured evidence package:
{json.dumps(local_prior_package.model_dump(mode="json"), indent=2, sort_keys=True)}

Research workflow:
    {json.dumps(workflow.model_dump(mode="json"), indent=2, sort_keys=True)}

Required methodology (fully inlined for self-contained execution):
{required_methodology}

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
evidence: keep it visible as a separate data-quality issue. Continue collecting useful
web evidence for the lens, but do not claim that web material repaired the local
extraction failure. Use the referenced disposition reason and guidance
to distinguish an extraction error, absent country-year, empty mapped fields, and a
genuinely inapplicable lens.

Before lens work, perform one broad ruler-period reconnaissance to understand the
ruler, period, major events, and likely source families across all eight chapters.
During reconnaissance, establish one cited authority baseline covering the ruler's
formal office, responsibility for national policy and appointments, command or party
authority where relevant, and material legal or coalition constraints. Reuse this
baseline across chapters. For Chapters 1B-6B and 8B, formal responsibility can support
attribution without proof of a personal order; Chapter 7B still requires a personal
integrity nexus.
Then work through only the selected chapters and methodology IDs in the job, in guide
order. A full-ruler job selects chapters 1B to 8B and all ten lenses inside each; a
bounded pilot selecting one lens must not silently expand to its other nine chapter
lenses.
This is one continuing ruler research session and one growing evidence library, not
80 independent research tasks. Before every lens,
inspect the accumulated ledger and map any already relevant evidence. Search again
only for the material themes, contrary interpretations, or attribution links that the
current lens still lacks. Append genuinely new evidence and continue; never restart
the ruler research or reproduce an existing fact merely because a new lens can use it.
Do not stop after one broad query. At the start of each chapter, build a lightweight
candidate pool with several differently framed searches: broad topic, event-specific,
named source/archive, adverse or contrary, and local-language searches where useful.
Record query, title, URL, and candidate status without satisfying the evidence schema.
Search tools expose a ranked sample rather than the whole web, so paginate when
supported and vary queries. Then open promising pages and documents, extract exact
claims and locators, and filter them into the evidence ledger. Adjust depth to evidence
abundance: a globally
prominent contemporary ruler normally requires substantially more searching than an
obscure or closed historical case. Record why each lens is covered, partly covered,
explicitly searched without usable evidence, or blocked, and why each chapter is
saturated before moving on.

Record accepted material immediately in `research-materials.md` inside the supplied
output directory before starting another search. Keep one append-only global evidence
ledger for the ruler-period. The ledger may use a Markdown table or one JSON object per
item, but every accepted item must use the same fields and one stable provisional ID.
When file writing is available, also maintain `research-ledger-manifest.json` at the
supplied path as a small accounting index with this shape:
`{{"schema_version":"ruler_research_ledger_manifest_v1","entries":[...]}}`.
Each entry must contain `provisional_id`, `canonical_fact_key`, `chapter_ids`,
`methodology_ids`, and `disposition`, where `chapter_ids` lists every relevant chapter,
`methodology_ids` lists every exact lens explicitly mapped by the researcher, and
disposition is `final_evidence`, `context`, `discovery_only`, or `rejected`. A rejected
entry must also contain a specific `reason`. Update the manifest whenever the ledger
changes. This is not a second evidence format: it is only the complete key/disposition
index used to prove that formatting did not silently lose notebook material.
Chapter notes and prose may remain flexible. The manifest is an optional accounting aid:
never shorten, distort, or abandon substantive research merely to satisfy it. A complete
permissive notebook remains the authoritative handoff when the model cannot write the file.

For every retained evidence item record:
- a stable provisional ID;
- a canonical fact key formed from the canonical source URL, exact locator, and one
  materially distinct claim, so the same fact is not recreated under another chapter;
- exact approved URL or canonical `local-prior:<methodology_id>` locator from the
  supplied fact record;
- title, publisher, and date when known;
- factual claim and a concise main-points summary;
- a precise source locator: PDF page/table/figure, HTML section plus paragraph, legal
  section, transcript timestamp, dataset row/field, or the supplied exact local-prior
  locator; also retain a short supporting excerpt when available;
- source type/confidence and limitations;
- target-period fit and ruler attribution;
- contrary or mitigating points;
- candidate chapters and lenses it can inform.

If the exact underlying URL or locator is unavailable, label the item
`gateway_only`, `locator_missing`, or `underlying_source_missing` and keep it out of
the defensible evidence count. A homepage, search-result page, document index,
`release page`, `article`, or organization name is not a precise locator. Never guess
a locator. Never bundle multiple URLs or materially distinct claims into one ledger
item merely to save space; create separate items when their provenance differs.

Before adding a new item, check the entire ruler ledger for the same canonical fact
key. Reuse its stable ID and add every genuinely relevant chapter/lens mapping instead
of creating chapter-prefixed copies. Mapping is deliberately many-to-many: do not pick
one "best" lens and hide the evidence from other lenses it directly informs.
Local priors are context unless the fact itself directly measures the ruler's conduct;
they use their supplied stable locator and must not be counted as internet sources.

Aim for 5–20 defensible source-claim units per selected chapter, normally about 10.
This is the filtered ledger size, not a search-results ceiling.
A source-claim unit is one traceable source supporting one materially distinct claim;
a heading, excerpt, paragraph, empty prior, alternate/AMP URL, or repeated statement
is not another item. A long report may support several materially distinct claims when
each has a precise locator; retain them and report source concentration instead of
using a per-URL cap. Reuse one stable item across chapters instead of duplicating it globally.
This is a goal, not a hard gate: never pad, invent, or lower source standards to meet
a count. If a chapter remains below five, inspect every supplied candidate, record
candidate-level rejection reasons, and name the exact missing themes and source types.
Do not declare a chapter ready merely because it reached a count. It is ready when the
concrete record is sufficient to present relevant governing conduct, contrary material,
and attribution fairly; otherwise continue the exact missing themes or document a
credible blocker.

For each chapter, record discovery queries, candidate outcomes, and suggested lens
links for accepted evidence. Do not spend research time producing 80 final coverage
rows; the formatter derives exact coverage from explicit mappings. If a theme remains
empty, first run a lens-specific source-landscape pass phrased in the plain language of
the lens. Search the ruler, period, conduct, and institutions named by the lens; include
primary/legal records, independent monitors or scholarship, reputable reporting, and
adverse or contrary interpretations. For a compound lens, vary searches across its
named mechanisms instead of treating one mechanism as the whole question. Record the
queries, promising candidates, opened sources, and rejection reasons. A lens may be
reported empty only after this pass finds no usable source-claim unit or a specific
access blocker is documented. Chapter-level source abundance and structured country
baselines do not substitute for this lens-level discovery check. Report both mapped
source-claim units and independent locator/source families. Seek at least three source
organizations and
two source types when the
available evidence permits, but do not manufacture diversity. Treat post-period material
as context unless it directly establishes a target-period fact. Empty or
`no_evidence_found` priors are gap signals and never retained evidence.

Do not assign scores, score ranges, anchors, ranking recommendations, or advice about
whether a judge should return a score or null. Do not use the client matrix. Your final
response is a flexible research handoff summarizing the global evidence register,
chapter yield and source diversity,
same-URL splits, cross-chapter reuse, rejected candidates, strongest contrary
evidence, and unresolved gaps. Self-audit temporal fit, ruler attribution, weak or
context-only items, and claims lacking independent corroboration. Include a local-data
audit stating which supplied fact IDs were retained, used as context, or left unused
and why. It does not need to match a JSON schema.

Execution requirement for tool-using models: do not finish on a planning statement,
an internal-thinking marker, or immediately after a search/page-inspection call. Begin
the research calls promptly; after every tool result either continue the chapter work
or synthesize the retained evidence. The final response must contain the substantive
selected-scope handoff itself, even when the notebook file was written successfully.
"""


__all__ = ["build_research_notebook_prompt"]
