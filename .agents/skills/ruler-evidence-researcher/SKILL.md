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
   `error` status as a blocking local-input failure and keep it visible in the
   handoff; internet evidence must not silently replace a broken extraction.
3. Work through chapters `1B` to `8B` in order. For each chapter, plan and perform
   as many internet searches as needed to understand the material events, decisions,
   outcomes, contrary interpretations, and attribution questions for the ruler-period.
   Search by event and evidence theme, not by issuing one omnibus query or one query
   per lens. Continue until the chapter is reasonably saturated or further searching
   is unlikely to improve it; explain the stopping judgment.
4. Persist every accepted evidence item immediately under a stable evidence ID.
   Record the claim, source, URL, publisher, date, short excerpt, source type,
   source confidence, period fit, ruler attribution, and contrary evidence.
   Aim for 5–20 defensible source-claim units per selected chapter, with 10 as the
   normal target. One unit is one traceable source supporting one materially
   distinct claim; headings, excerpt fragments, empty priors, equivalent URLs, and
   repeated statements do not create new units. Normally retain no more than two
   units from one URL and justify exceptions. Report chapter mappings separately
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
9. Finish only when each applicable question is marked `covered`,
   `partially_covered`, `no_evidence_found`, `not_applicable`, or
   `research_blocked` with a reason.
10. Self-audit the register before handoff: empty priors never count; post-period
    material is context unless it establishes a target-period fact; same-source
    splits are non-independent; country/institutional evidence is not automatically
    ruler-attributable; and global IDs, chapter mappings, and reported counts must
    reconcile.

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
