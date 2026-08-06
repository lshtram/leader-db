## Overall decision: blocker — do not promote this release

No search was performed. This audit used only the named local dossier, projections, new judgments, preserved judgments, and run records.

All cited IDs in the eight new Putin judgments resolve in their corresponding new RUS projection. That does not make the projections sufficient: the compaction ledger shows decisive dossier evidence was omitted, and the run record marks 5B and 8B as failed.

| Chapter | Old → new score; confidence; range | Audit result |
|---|---|---|
| 1B | 2.0 → 4.5; 94 → 37; 1.5–2.5 → 3–6 | retain_old_pending_research |
| 2B | 1.0 → 1.0; 98 → 86; 1–1.5 → 1–1.5 | targeted_rejudge |
| 3B | 2.0 → 4.0; 97 → 42; 1.5–2.5 → 2.5–6 | retain_old_pending_research |
| 4B | 1.0 → 1.5; 95 → 92; 1–1.5 → 1–2 | accept |
| 5B | 2.0 → 4.0; 91 → 58; 1.5–2.5 → 3.5–5 | blocker |
| 6B | 3.5 → 2.5; 66 → 34; 2.5–4.5 → 1.5–4 | retain_old_pending_research |
| 7B | 1.5 → 2.0; 95 → 86; 1–2.5 → 1.5–3 | accept |
| 8B | 6.0 → 4.5; 80 → 31; 5.5–6.5 → 2.5–6 | blocker |

The new bias assessments are generally specific, cited, and explicitly state that report volume was not used as severity and no blanket regime correction was applied. Local priors are also described as context rather than personal conduct evidence. These controls are sound in form.

### Non-accept findings

- **1B — retain old pending research.** The +2.5 change has an explicit projection explanation, not a substantive replacement basis: only 4 of 26 source items were retained, omitting the direct nuclear-threat and command material. The judgment itself acknowledges this and raises a `decisive_source` manual flag. The cited E051/E052 resolve, but they cannot replace the preserved low-anchor record. No promotion.

- **2B — targeted rejudge.** The score is unchanged and the evidence supports the common-meter placement. However, the `material_attribution` flag is inconsistent with the calibration contract: for 1B–6B, documented formal authority can establish chapter-level responsibility without a personal order. Rejudge the attribution/manual-review decision only; no replacement score is indicated.

- **3B — retain old pending research.** The +2 change is explicitly explained by projection loss: 4 of 20 items retained, with most lenses absent and a `projection_integrity` flag. The cited E054/E055 resolve, but the score is not comparable with the preserved, broad repression/safety record. Keep the old result pending a restored projection.

- **5B — blocker.** The +2 change is not promotable because the run summary records the 5B batch as failed for a cohort identity mismatch. This is a provenance/calibration defect, irrespective of the Putin citations resolving. Do not use the existing `judgment.json`.

- **6B — retain old pending research.** The −1 change has an explicit thin-projection explanation: only two supported lenses, low confidence, wide range, and a `projection_integrity` flag. Differences in welfare evidence should affect confidence/range first; this record cannot displace the preserved score.

- **8B — blocker.** The −1.5 change is explicitly projection-limited, but more importantly the 8B batch failed validation because a scored cohort record used `recoverable_null`. The comparative batch is invalid, so the Putin judgment is unsafe for release. The retained projection also has only two supported lenses and flags projection integrity.

### Cross-chapter findings

The observed changes greater than one point—**1B, 3B, 5B, and 8B**—all have explicit projection/baseline explanations. None provides a defensible new common-meter result:

- 1B and 3B become less severe after decisive evidence loss.
- 5B comes from a batch with an identity failure.
- 8B comes from a validation-failed batch and a severely incomplete implementation record.

There is no indication that greater report volume mechanically worsened scores, nor that regime type was mechanically applied as a penalty. The more material risk is the converse: selective compaction changes the available evidence and thereby changes severity despite the required confidence/range safeguards.

### Exact next action

Stop promotion; repair the projection and batch-validation pipeline, then rerun 1B, 3B, 5B, 6B, and 8B against the complete unchanged 20-ruler cohort. Restore the omitted decisive 1B and 3B material; preserve a complete welfare record for 6B and governing-portfolio record for 8B; resolve the 5B identity mismatch and the 8B `recoverable_null` validation error. Separately rejudge 2B’s attribution/manual-review flag under the formal-authority rule. Re-audit only after all eight batches complete validly.