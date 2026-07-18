---
name: ruler-chapter-judge
description: Judge one Leaders Database chapter for one target year or period across all eligible ruler dossiers, synthesizing ten evidence lenses into one calibrated chapter score and confidence assessment.
---

# Ruler Chapter Judge

Own exactly one chapter (`1B` through `8B`) and judge every eligible ruler in the
batch with one common meter. The ten questions are complementary evidence lenses,
not ten independent final scores.

## Required inputs

Require the chapter ID, target year or period, draft-or-active chapter guide,
complete eligible-ruler manifest, ruler dossiers, explicit missing/quarantined
cases, and the selected provider/model profile. Stop on unresolved identity, but
do not stop merely because some lenses lack evidence.

Read `AGENTS.md`, the exact guide under `docs/methodology/chapter-guides/`, and
the cited evidence for the chapter before judging.

## Workflow

1. Validate ruler identities, period bounds, citations, and source provenance.
2. Review all ten lenses for each ruler. Treat lens labels and coverage wording as
   advisory; reason from the cited evidence itself.
3. Establish chapter-level high, middle, low, and edge anchors across the supplied
   ruler batch.
4. Assign one tentative chapter score per ruler, then compare neighboring cases
   before finalizing.
5. Weight lenses by relevance, evidence strength, ruler authority, and the chapter
   guide. Do not mechanically average ten lens scores.
   Apply attribution proportionally: formal responsibility can support Chapters
   1B–6B and 8B without a personal order; Chapter 7B requires a personal-integrity
   nexus. Shared authority affects weight and confidence rather than automatically
   erasing the evidence.
6. Lower confidence for missing lenses, sparse historical records, weak source
   diversity, closed information environments, or uncertain attribution. Do not
   convert missing evidence into an automatic low score.
7. Preserve major positive, negative, contrary, and contextual evidence and emit
   targeted follow-up requests for material gaps.
8. Write the chapter rationale as a self-contained abstract for a new reader:
   begin with the overall appraisal, explain the decisive cases and why they matter,
   distinguish findings from allegations and inherited context, and close by tying
   the balance of evidence to the score. Define unfamiliar events and acronyms on
   first mention; never begin with unexplained dossier shorthand.

## Boundaries

- Emit one score for the chapter, not one score per lens.
- Treat client scores as validation-only and keep them out of initial judgment.
- Do not reward evidence volume or punish obscure/historical rulers merely for
  having thinner records.
- Use insufficient evidence only when the chapter as a whole cannot be judged,
  not because one or several lenses are missing.
- If one context cannot contain the batch, split with overlapping anchor rulers
  and perform a final cross-shard calibration.

## Handoff

Return one chapter evaluation per eligible ruler with score, confidence, evidence
strength, supported and missing lenses, attribution/baseline caveats, adjacent-
anchor rationale, review flags, and a batch run profile.
