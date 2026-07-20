**Verdict:** `block`

**Chapter Verdicts**
| Chapter | Verdict | Notes |
|---|---|---|
| `1B` | `pass_with_cautions` | No `score_1_to_10 = 1` cases, and the floor rule is respected. Four explicit nulls remain, but they are defensible no-opportunity / no-attribution nulls. |
| `2B` | `block` | One `projection_integrity` flag and one `recoverable_null` flag. |
| `3B` | `block` | One `projection_integrity` flag. |
| `4B` | `block` | Four `projection_integrity` flags. |
| `5B` | `block` | One `projection_integrity` flag. |
| `6B` | `block` | Two `projection_integrity` flags. |
| `7B` | `block` | Two `projection_integrity` flags. |
| `8B` | `block` | Two `projection_integrity` flags. |

**Blocking Issues**
- `2B / Félix Tshisekedi`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped references `E0012`, `E0020`.
- `2B / Muhammadu Buhari`: `manual_review_required = true`, `manual_review_reason_type = recoverable_null`, the chapter is null but explicitly recoverable.
- `3B / Olaf Scholz`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0040`.
- `4B / Joko Widodo`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0038`.
- `4B / Narendra Modi`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped references `E0038`, `E0024`.
- `4B / Muhammadu Buhari`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped references `E0047`, `E0048`, `E0049`.
- `4B / Shehbaz Sharif`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0031`.
- `5B / Bongbong Marcos`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0068`.
- `6B / Prayut Chan-o-cha`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0060`.
- `6B / Recep Tayyip Erdoğan`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0073`.
- `7B / Joko Widodo`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0096`.
- `7B / Narendra Modi`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped references `E0092`, `E0088`.
- `8B / Fumio Kishida`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped reference `E0087`.
- `8B / Recep Tayyip Erdoğan`: `manual_review_required = true`, `manual_review_reason_type = projection_integrity`, dropped references `E0100`, `E0105`.

**Material Cautions**
- `1B / Félix Tshisekedi`, `Abdel Fattah el-Sisi`, `Abiy Ahmed`, `Bongbong Marcos`: all are explicit nulls with broad plausible ranges, and the reasons correctly say the record is too indirect, absent, or inauguration-only for a scored 2022 existential-risk judgment.
- `2B`, `4B`, `5B`, `6B`: the artifact leaves `supported_lenses` and `missing_or_weak_lenses` empty for every ruler in those chapters, which weakens lens-level traceability even though the narratives are readable.
- Batch-wide: many `source_mix` notes say local priors were unavailable and several chapters lean heavily on official/IGO/Reuters material. That is acceptable, but it is a source-balance caution, not a clean release state.

**Null Review**
- `1B / Félix Tshisekedi`: null is defensible, because the material is treaty status, cyber strategy, and peace-process context, not a ruler-attributed catastrophic-risk choice.
- `1B / Abdel Fattah el-Sisi`: null is defensible, because no admissible 2022 ruler-attributed nuclear or equivalent catastrophic-risk decision is recovered.
- `1B / Abiy Ahmed`: null is defensible, because the file gives office/treaty baseline only, not a judgeable 2022 risk-bearing act.
- `1B / Bongbong Marcos`: null is defensible, because the only recovered 2022 fact is inauguration, which is not a score-bearing existential-risk choice.
- `2B / Muhammadu Buhari`: null is defensible on the present record, but it is still a `recoverable_null`, so it blocks release until that status is either resolved or explicitly accepted in a rerun.

**1B Floor Check**
- Checked all `1B` evaluations. None are `1`.
- Lowest `1B` score is `2.0` for `Vladimir Putin`.
- The chapter-specific floor is respected: no `1B` score is based on threats, escalation, repression, or arms buildup alone.
- All score-`1` cases in the full batch are `Vladimir Putin` in `2B` and `4B` only, which is consistent with those chapter rubrics and does not violate the `1B` floor.

**Ordering / Consistency Check**
- No obvious within-chapter rank inversion jumped out beyond the explicit projection-integrity flags.
- No score is outside its stated plausible range.
- All numeric scores are on half-point increments.
- The low anchors are coherent, especially `Putin` at `1.0` in `2B` and `4B`.

**Release Recommendation**
- Do not release this batch yet.

**Exact Next Actions**
1. Revalidate every `projection_integrity` case and either restore the dropped references into the judged projection or regenerate the affected chapter outputs without the out-of-projection material.
2. Decide the status of `2B / Muhammadu Buhari`: either recover a real 2022 target-period conduct item or keep the null, but in either case rerun the audit after the chapter is finalized.
3. Refill the missing lens arrays in `2B`, `4B`, `5B`, and `6B` if those artifacts are meant to be release-grade, because the current JSON loses traceability there.
4. Rerun the score/order audit on the corrected artifacts before any release recommendation changes from `block` to `pass_with_cautions` or `pass`.