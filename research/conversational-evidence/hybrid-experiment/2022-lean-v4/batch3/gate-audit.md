# Lean-v4 batch-three evidence gate

All five rulers completed with preserved research, review, follow-up, final-review,
ledger, dossier, and execution profiles. Two terminal-review recovery defects were
found and fixed before accepting the batch.

## Results

| Ruler | Accepted claims | Distinct URLs | Domains | Web calls | Cost | Model time |
|---|---:|---:|---:|---:|---:|---:|
| Abdel Fattah el-Sisi | 104 | 77 | 37 | 177 | $2.312 | 79.7 min |
| Abiy Ahmed | 104 | 75 | 40 | 178 | $2.061 | 74.0 min |
| Fumio Kishida | 102 | 76 | 27 | 203 | $2.311 | 84.0 min |
| Bongbong Marcos | 116 | 101 | 45 | 255 | $2.368 | 102.1 min |
| Nguyen Phu Trong | 109 | 84 | 42 | 212 | $2.170 | 85.0 min |

The batch produced 535 accepted claims from 413 distinct URLs. Mean cost was $2.24
per ruler and final total cost was $11.22, below both configured ceilings.

## Quality decision

- El-Sisi passed six chapters; 1B and 7B remain manual review. Final review keeps
  state posture and institutional context separate from direct ruler conduct.
- Abiy passed six chapters; 1B retains a credible gap and 7B remains manual review.
- Kishida passed six chapters; 3B and 7B remain manual review where direct personal
  attribution is weaker than state or institutional evidence.
- Marcos passed all eight chapters after one bounded follow-up. The final reviewer
  accepted the adverse, mitigating, and attribution evidence without a remaining gap.
- Nguyen Phu Trong passed seven chapters; 7B remains manual review because the
  integrity evidence requires careful separation of anti-corruption enforcement from
  proof about the ruler's own conduct.

## Process findings

Egypt and the Philippines both completed valid follow-up research, but their first
terminal reviews improperly requested another research round. The rejection exposed a
resume branch that skipped final review when `follow-up.md` already existed and could
prematurely reuse a dossier. Commit `cf75ab0` makes final review independently resumable;
the premature dossier and profile files are retained under each affected ruler's
`recovery-before-final-review/` directory.

Egypt's terminal reviewer repeated the forbidden request. Commit `01f9d1e` now applies
the methodology deterministically: after the single allowed follow-up, any unresolved
request becomes a credible gap rather than causing repeated model calls. Focused tests,
Ruff, and diff checks passed for both fixes.

Decision: pass the evidence flow to batch four. Comparative judgment remains deferred
until the complete 20-ruler cohort is assembled.
