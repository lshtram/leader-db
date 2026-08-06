Verdict: `targeted_review`

- Pass on count and meter: every chapter has exactly 20 evaluations, and each chapter uses one calibration set (`calibrated_against`) for the whole batch.
- Pass on ordering/anchors: I did not find a cross-chapter meter split or an anchor inconsistency that would force score renormalization.
- Pass on score-1 rules: `1B` uses no score `1`, and the score-1 cases in other chapters are rubric-consistent (`2B/RUS`, `4B/CHN`, `4B/RUS`).

| Chapter | ISO3 | Case | Clear unchanged? | Bounded correction |
|---|---|---|---|---|
| 1B | ETH | `null` + `manual_review_required=true` (`recoverable_null`) | n/a | Keep `null`; this is a genuine unscorable gap, not a score reduction. |
| 1B | TUR | `null` + `manual_review_required=true` (`recoverable_null`) | n/a | Keep `null`. |
| 1B | VNM | `null` + `manual_review_required=true` (`recoverable_null`) | n/a | Keep `null`. |
| 2B | COD | numeric score with `projection_integrity` flag | yes | Keep `5.5`; clean the out-of-projection citation set noted in the review reason. |
| 5B | THA | numeric score with `projection_integrity` flag | yes | Keep `4.5`; drop the out-of-projection citation noted in the review reason. |
| 6B | TUR | numeric score with `projection_integrity` flag | yes | Keep `4.5`; remove the out-of-projection citations noted in the review reason. |
| 7B | CHN | `null` + `manual_review_required=true` (`recoverable_null`) | n/a | Keep `null`; the dossier is still not scoreable from the supplied record. |
| 7B | IND | numeric score with `projection_integrity` flag | yes | Keep `5.5`; clean the out-of-projection citations noted in the review reason. |
| 8B | IND | numeric score with `projection_integrity` flag | yes | Keep `7.0`; clean the out-of-projection citation noted in the review reason. |

- No chapter needs a replacement score.
- No 1B floor violation found.
- The 3B, 6B, and 8B retry chapters remain comparable to the others; I do not see a scale break that requires re-anchoring.

Sources:
- [judge-instructions.md](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judge-instructions.md)
- [conversion-report.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judge-inputs-v1/conversion-report.json)
- [compaction-report.json (v1)](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judge-compact-v1/compaction-report.json)
- [compaction-report.json (v2)](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judge-compact-v2/compaction-report.json)
- [1B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/1B/judgment.json)
- [2B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/2B/judgment.json)
- [4B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/4B/judgment.json)
- [5B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/5B/judgment.json)
- [6B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/6B/judgment.json)
- [7B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/7B/judgment.json)
- [8B/judgment.json](/home/liorshtram/projects/leaders-db/research/conversational-evidence/hybrid-experiment/2022-lean-v4/judgments-v1/8B/judgment.json)