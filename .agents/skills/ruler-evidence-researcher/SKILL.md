---
name: ruler-evidence-researcher
description: Build or resume one reusable, local-first cited evidence dossier for a resolved political ruler and defined year or ruler-period, mapping stable evidence IDs to every applicable Leaders Database 1B-8B question without scoring. Use for ruler-level evidence collection, dossier continuation, evidence deduplication, question coverage mapping, and gap reporting before chapter-specific judging.
---

# Ruler Evidence Researcher

Build one durable evidence dossier per ruler-period. Do not run one research pass
per question and do not assign final comparative scores.

## Required inputs

Require a resolved ruler identity, ISO3 country, target year or bounded period,
output/checkpoint directory, question catalog, and local-prior package. Stop if
the case is identity-quarantined or the readiness report is not ready.

Read `AGENTS.md`, `docs/methodology/local-first-researcher-guide.md`,
`docs/methodology/ranking-evaluation-criteria.md`, the applicable chapter
guides, and `docs/methodology/source-confidence-registry.json` before external
research.

## Workflow

1. Load the ruler identity, period boundaries, local facts, existing dossier,
   completed queries, and question coverage matrix.
2. Audit the supplied deduplicated local package before internet material.
   Record which stable local fact IDs are usable, contextual, or unused; preserve
   source observation IDs, years, warnings, and valid local-prior locators; and
   distinguish country/inherited baselines from ruler conduct. Candidate lens links
   are routing hints, not proof of direct support. Never refetch a dataset already
   represented locally merely to restate its numeric values, and never interpret a
   missing local row as a zero or favorable condition.
   Resolve compact disposition references when explaining missingness. Treat an
   `error` status as a blocking local-input failure and keep it visible separately.
   Web research may continue, but it does not repair or conceal the local error.
   Establish one reusable authority baseline for the ruler: formal office, national
   policy and appointment responsibility, command or party authority where relevant,
   and material legal or coalition constraints. Cite it once and reuse it across
   chapters; do not demand proof of a personal order for ordinary authority-based
   responsibility. Personal-integrity claims still require a personal nexus.
3. Work through chapters `1B` to `8B`, and their lenses, in order in the same
   researcher session. Begin each chapter with broad discovery before judging source
   admissibility: use varied event, institution, archive, source-family, and local-
   language queries to build a candidate URL pool. Search results are candidates, not
   evidence. Never use a recent-news filter for a historical period. Then open the
   promising pages, reports, and PDFs; extract claims and locators; and only then decide
   what belongs in the evidence ledger. Before each lens, reuse and map the accumulated
   ledger, then search for remaining events, contrary interpretations, or attribution
   gaps. Continue until the chapter is reasonably saturated or a specific access
   blocker is documented.
4. Persist every accepted evidence item immediately under a stable evidence ID in the
   permissive notebook. A separate machine-readable ledger manifest is optional and must
   never block a substantive handoff when the execution profile cannot write files.
   Record the claim, source, URL, publisher, date, short excerpt, source type,
   source confidence, period fit, ruler attribution, and contrary evidence.
   Aim for 5–20 defensible source-claim units per selected chapter, with 10 as the
   normal target. One unit is one traceable source supporting one materially
   distinct claim; headings, excerpt fragments, empty priors, equivalent URLs, and
   repeated statements do not create new units. A substantial report may support more
   than two distinct claims when each has its own locator and material meaning; report
   source concentration rather than discarding them. Report chapter mappings separately
   from independent locator/source families. This is a research-depth goal, not a
   publication gate: sparse or closed-information cases remain valid when the
   notebook records inspected candidates, rejection reasons, usable evidence, and
   the exact themes/source types still missing.
5. Indicate which chapter lenses each evidence item may inform. Natural mapping
   and coverage language is acceptable; the parent may normalize it later.
6. Checkpoint search queries, sources visited, evidence records, mappings,
   unresolved gaps, and run profile throughout the session. Resume from those
   checkpoints instead of repeating discovery.
7. After the initial notebook, respond to the evidence review in the same session.
   Search directly for every material gap selected by the reviewer, merge useful
   evidence into the register, and document gaps that cannot be improved. Repeat for
   at most three review rounds, stopping earlier when the reviewer passes the dossier
   or the researcher reports a reasoned saturation/blocker conclusion.
8. Produce a permissive research notebook/handoff before formatting. Record each
   source as it is accepted, including its reference, main-points summary, useful
   excerpts or locators, temporal fit, attribution, contrary points, and candidate
   chapter/lens links. Do not spend the research pass satisfying a strict final schema.
9. Finish with chapter-level candidate, accepted-evidence, and gap notes plus suggested
   lens links. The formatter derives exact per-lens coverage from explicit mappings;
   the researcher need not manufacture 80 terminal status rows. An empty theme still
   requires recorded targeted searches and a specific explanation.
10. Self-audit the register before handoff: empty priors never count; post-period
    material is context unless it establishes a target-period fact; same-source
    splits are non-independent; country/institutional evidence is not automatically
    ruler-attributable; and global IDs, chapter mappings, and reported counts must
    reconcile.
11. Do not declare a chapter ready merely because it has several sources or local
    indicators. Confirm that its concrete evidence is sufficient to present the
    relevant governing conduct, important contrary material, and attribution fairly.
    Otherwise continue the exact missing themes or document a credible blocker.

## Boundaries

- Treat the client matrix as validation-only, never evidence.
- Do not silently resolve ruler identity or expand the requested period.
- Do not invent citations, quotations, facts, usage, or token counts.
- Preserve one evidence record even when it maps to many questions.
- Record meaningful contrary evidence and closed-information-environment gaps.
- Use the provider/model selected by the parent run profile. Do not change model
  or provider inside the dossier.
- Internet search is an essential researcher capability. Do not accept a preselected
  link packet as a substitute for direct iterative research.
- Return a blocker rather than bypassing tool, credential, budget, or output
  restrictions.

## Handoff

Return a durable permissive research notebook and handoff. A separate formatter
may interpret natural-language headings, tables, JSON fragments, or prose and turn
them into the validated cited dossier. The downstream scientific unit remains one
chapter-year judge batch across all eligible ruler dossiers.
