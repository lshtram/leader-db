---
name: ruler-question-judge
description: Judge one Leaders Database methodology question for one target year or period across all eligible ruler evidence dossiers using a single versioned guide and calibrated comparison meter. Use after ruler-level evidence collection to produce consistent score-bearing answers, evidence links, confidence, and review flags for the full ruler batch.
---

# Ruler Question Judge

Own exactly one methodology question and judge every eligible ruler in the batch
with one common meter. Do not perform broad discovery or judge several questions
in the same run.

## Required inputs

Require the methodology ID and text, target year/period, production-ready
question guide, rubric version, calibration schema, complete eligible-ruler
manifest, mapped dossier evidence for the question, and explicit missing or
quarantined cases. Stop if the readiness report is not ready.

Read `AGENTS.md`, `docs/methodology/cited-evaluation-calibration.md`, the exact
question guide, and the cited-evaluation schema before judging.

## Workflow

1. Validate that every input record belongs to the same question and target
   year/period and that evidence IDs resolve to cited dossier evidence.
2. Separate eligible, identity-quarantined, missing-evidence, and not-applicable
   cases. Never score an identity-quarantined ruler.
3. Establish high, middle, low, and edge anchors from the supplied batch and the
   guide's smoke cases.
4. Assign tentative answers across the whole ruler set before finalizing close
   cases. Compare neighboring scores and apply one rubric version consistently.
5. Preserve mapped citations and contrary evidence. Do not invent or broaden
   evidence; request a targeted dossier follow-up when a material gap remains.
6. Emit calibration fields, lower/higher-anchor rejections, bias checks,
   confidence, caveats, and manual-review reasons required by the schema.
7. Validate the complete output batch before persistence and write a batch
   profile containing model/provider, rubric version, counts, splits, and gaps.

## Boundaries

- Judge one question across rulers, never one ruler across questions.
- Treat evidence volume as confidence, not automatic severity or merit.
- Use `insufficient_evidence` or `manual_review_required` instead of guessing.
- Keep client scores out of evidence and initial judgment.
- Use the provider/model chosen by the parent run profile. A low-cost model may
  judge only after passing question-specific calibration tests.
- If a single context cannot contain the batch, split with shared anchor cases
  and record the overlap; never create uncalibrated independent partitions.

## Handoff

Return validated cited evaluations for all eligible rulers, a missing/research
request list, calibration metadata, evidence links, and a batch run profile ready
for durable persistence.
