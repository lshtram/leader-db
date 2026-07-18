# Chapter Evaluation Calibration

This is the common calibration contract for cited ruler-quality judgment. The
active unit is one chapter (`1B`–`8B`), not one question. Each chapter guide uses
its ten questions as overlapping evidence lenses and produces one final score for
the ruler-period.

## Roles

1. A persistent ruler evidence researcher reads the complete selected guides and
   local facts, then collects one reusable cited dossier across all applicable
   chapters. The researcher may use natural coverage language and does not score.
2. A no-search evidence reviewer inspects every selected chapter and returns all
   recoverable gaps to the same researcher thread for up to three rounds, stopping
   earlier on a pass or credible saturation/access blocker.
3. A separate no-search formatter converts the final permissive notebook into the
   validated dossier without adding evidence or scores.
4. One chapter judge reviews the same chapter across every eligible ruler in the
   target batch and applies one common meter without new discovery.
5. A score/order auditor reviews relative ordering, attribution, missingness, source
   balance, and rubric drift after the comparative judgments exist.

The normal annual topology is approximately one persistent researcher thread per
ruler, its bounded evidence-review/formatting phases, plus eight chapter-judge runs
and a score/order audit. If a ruler batch does not fit one context, split it with
overlapping anchor rulers and perform a final cross-shard calibration.

## Ten lenses, one score

The ten questions in a chapter are prompts for finding and organizing evidence.
They are deliberately redundant. A judge must not assign ten independent scores
and average them mechanically. Instead, the judge weighs the evidence by:

- relevance to the chapter's purpose;
- source authority and independence;
- ruler attribution and decision authority;
- target-period fit;
- severity, scale, duration, or importance where relevant;
- inherited baseline, available alternatives, and external constraints;
- corroboration, contradiction, and information-environment limitations.

Missing lenses reduce confidence and may widen the plausible score range. They do
not automatically lower the score or make a dossier invalid. A chapter is
`insufficient_evidence` only when the available record cannot support a defensible
holistic comparison.

This distinction does not authorize a fabricated midpoint. Evidence review asks a
plain question: does the chapter contain enough concrete, relevant material about
governing choices, actions, implementation, restraint, remedies, or outcomes to
support a balanced judgment? Source counts and country indicators cannot answer that
question by themselves. When the answer is no, research continues with the exact
missing themes; when the record remains genuinely insufficient, the judge returns a
null rather than inventing a midpoint.

Attribution is proportional to the chapter. For Chapters 1B–6B and 8B, documented
formal authority and responsibility for national policy, appointments, command,
implementation, tolerance, or remedy can establish ruler responsibility without a
personal order. Shared authority and real constraints lower attribution strength; they
do not erase it. Chapter 7B evaluates personal integrity and therefore requires a
personal nexus such as the ruler's own statement, interest, benefit, appointment,
response to scrutiny, concealment, correction, or knowingly protected network. Country
baselines, official plans, silence, and absence of reported misconduct remain context.

## Common chapter-judgment envelope

Every chapter judge returns these semantic fields. Exact JSON spelling can be
normalized by the parent or a low-cost formatter; evidence quality must not be
discarded over harmless formatting differences.

| Field | Meaning |
|---|---|
| `chapter_id` | One of `1B` through `8B`. |
| `rubric_version` | Exact version from the active chapter guide. |
| `calibration_batch_id` | Stable identifier for the chapter/year comparison batch. |
| `calibrated_against` | Complete comparison set available to the judge. |
| `score_1_to_10` | One holistic chapter score, or null when genuinely insufficient. |
| `insufficient_evidence_reason` | Required when no score is assigned. |
| `confidence_score` | 0–100 confidence in the chapter judgment. |
| `plausible_score_range` | Lower and upper plausible score given evidence gaps. |
| `decisive_positive_evidence` | Most important evidence raising the chapter score. |
| `decisive_negative_evidence` | Most important evidence lowering the chapter score. |
| `inherited_baseline_and_constraints` | What the ruler inherited and could plausibly control. |
| `ruler_attribution` | Why the evidence is attributable to this ruler or shared authority. |
| `supported_lenses` | Lenses materially informed by evidence. |
| `missing_or_weak_lenses` | Lenses with sparse, indirect, or unavailable evidence. |
| `contrary_evidence` | Material evidence against the selected interpretation. |
| `source_mix` | Source types and material concentration limitations. |
| `structured_prior_summary` | Relevant local structured context or `not_available`. |
| `chapter_rationale` | Why the evidence fits the chosen chapter anchor. |
| `lower_anchor_rejected` | Why the next lower anchor is too harsh. |
| `higher_anchor_rejected` | Why the next higher anchor is too generous. |
| `manual_review_required` | Whether identity, attribution, evidence, or calibration needs review. |
| `manual_review_reason_type` | Stable release-blocking reason category when review is required. |
| `manual_review_reason` | Specific reason when review is required. |

## Publication review versus ordinary uncertainty

`manual_review_required` is a release-blocking queue, not a general uncertainty
label. Set it only for one or more of these material conditions:

- unresolved identity or projection integrity;
- an unverified or contradictory decisive source;
- ruler attribution disputed enough to plausibly move the score by at least one
  point;
- a null result for which targeted research could reasonably recover a score;
- an internal or adjacent-ruler calibration inconsistency that could materially
  change the ordering.

Use a stable `manual_review_reason_type` of `identity`, `projection_integrity`,
`decisive_source`, `material_attribution`, `recoverable_null`, or
`calibration_inconsistency`, followed by a case-specific explanation. Ordinary
missing lenses, thin source diversity, visibility bias, official-source reliance,
post-period caveats, or moderate attribution uncertainty belong in confidence,
the plausible range, and targeted research gaps. They do not independently place
every result in manual review.

Judges use half-point increments. The evidence and batch sizes in this prototype do
not identify finer distinctions reliably. A numeric judgment may never use
`recoverable_null`; that reason type is reserved for a null whose targeted research
could plausibly recover a score.

Chapter guides may add domain-specific fields but may not remove this common
semantic envelope.

## Sparse and historical evidence

Evidence availability is not ruler quality. An obscure ruler from fifty years ago
will often have fewer sources than a recent US president. Judges must:

- judge choices within documented opportunities and authority;
- avoid rewarding silence in closed or poorly documented environments;
- avoid punishing a ruler merely for low media visibility;
- use reputable historical scholarship, archives, diplomatic records, legal
  materials, and structured historical sources when contemporary web evidence is
  unavailable;
- lower confidence and widen the range when source diversity or lens coverage is
  weak;
- preserve a score when the chapter-level record is still discriminating.

Low exposure is not automatically excellent or poor performance. When a ruler had
meaningful opportunities, documented responsible restraint can support a high
score. When no discriminating opportunity exists, the judge returns null and explains
the limited exposure rather than fabricating a midpoint or narrow plausible range. The
schema still carries the mandatory broad `1`–`10` uncertainty interval for a null; this
records non-identification and is not a substantive score estimate.

## Bias checks

Every judgment addresses, in prose or normalized fields:

- visibility and English-language search bias;
- silence under repression or secrecy;
- population, state-capacity, and exposure differences;
- source-type concentration and official-source incentives;
- recency and target-period fit;
- inherited conditions and external shocks;
- ruler authority, coalition, ceremonial office, and shared decision-making;
- comparison with adjacent rulers in the same chapter batch.

## Integrity boundary

The parent may normalize IDs, coverage labels, mappings, optional fields, and
extra explanatory content. It must not normalize away invented citations,
incorrect identity, false period attribution, fabricated quotations, or material
changes to claims. Those remain blockers or manual-review cases.
