# Three-ruler saturation-v3 gate audit

This compact audit supersedes the interrupted exploratory auditor in `audit.md`. The
exploratory attempt was stopped after 146,293 tokens because it repeatedly searched
known paths and emitted oversized event-log content. Its failure is itself a bounded-
input lesson for the next gate.

## Evidence results

| Ruler | v2 records / URLs / domains | v3 raw / curated / URLs / domains | v3 evidence cost |
|---|---:|---:|---:|
| Vladimir Putin | 102 / 91 / n/a | 243 / 157 / 133 / 57 | $4.974 |
| Joe Biden | 100 / 82 / 25 | 229 / 162 / 155 / 61 | $4.943 |
| Felix Tshisekedi | 122 / 94 / 38 | 196 / 121 / 93 / 43 | $4.565 |

Biden shows a clear breadth and diversity gain. Tshisekedi shows wider discovery and
slightly better domain diversity, but no gain in final distinct URLs. That is a useful
scarcity result rather than a target failure: the curator removed duplicate, indirect,
weakly attributed, and irrelevant material instead of padding the dossier.

## Judgment interpretation

The controlled rerun replaced only the Biden and Tshisekedi projections (plus the
already accepted Putin pilot) in the same 20-ruler cohort. Among the 17 unchanged
rulers, mean absolute score drift was 0.46, 0.47, 0.21, 0.62, 0.35, 0.32, 0.53, and
0.26 points for Chapters 1B through 8B. Maximum drift reached 1.5 points. Consequently,
most Biden changes of 0.5-1 point cannot be confidently credited to added evidence.
Tshisekedi's recovery from null to 6 in 1B and null to 4 in 5B is a substantive
coverage improvement; its other movements should be interpreted against rerun noise.

No audited ruler received a 1B score of 1. Putin received 2. The chapter-specific
catastrophic-risk floor remained reserved for realized catastrophe rather than used as
a general condemnation score.

## Reliability and gate decision

Evidence research stayed below the $5 target for all three rulers, but runtime was
long and curation/judging needed too many retries. The first controlled judge run
failed 3B through context/output exhaustion and twice failed 4B because one numeric
evaluation omitted decisive evidence. A concise retry succeeded. Curation also spent
avoidable calls repairing exact-ID and composition-contract errors.

Decision: **hold before the five-ruler gate, fix, then test two rulers**. Promotion is
appropriate only if the next two runs retain the evidence-quality gains while showing:

- complete first-pass curation or one targeted correction at most;
- complete judge batches without context exhaustion;
- every numeric score linked to a decisive same-dossier evidence ID;
- mean evidence cost at or below $5 per ruler;
- honest sparse results rather than quota padding.

The implemented correction makes curator inputs mechanically explicit and constrains
judge prose while preserving the full calibration contract. All old v2, failed v3,
retry, and accepted artifacts remain separate for 1:1 comparison.
