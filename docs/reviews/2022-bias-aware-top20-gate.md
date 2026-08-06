# 2022 Bias-Aware Top-20 Gate

Date: 2026-07-23

Status: full cohort completed; targeted remediation required before release promotion.

## Scope

The controlled runs `2022-bias-aware-top20-v1` and
`2022-bias-aware-top20-judges-v1` produced one reusable dossier for each of the
preserved 20-ruler 2022 cases and one common-meter judgment batch for each chapter
from 1B through 8B. The run exercised the new evidence-environment assessment,
bias-aware review, receiver-side recovery, local-prior transmission, and required
chapter bias assessment.

The artifacts remain beside the lean-v4 release under
`research/conversational-evidence/bias-smoke/2022-top20-v1/`. They are a controlled
release candidate, not a replacement for the preserved release.

## Deterministic results

| Measure | Result |
|---|---:|
| Completed dossiers | 20 / 20 |
| Evidence records | 1,092 |
| Evidence mappings | 5,377 |
| Lens coverage rows | 1,600 / 1,600 |
| Local-prior provenance rows | 1,600 / 1,600 |
| Completed judgments | 160 / 160 |
| Dangling dossier references | 0 |
| Dangling judgment references | 0 |
| Missing report-volume safeguards | 0 |
| Missing no-blanket-correction safeguards | 0 |
| Numeric judgments | 138 |
| Reasoned null judgments | 22 |
| Manual-review flags | 13 |

Evidence per dossier ranges from 13 to 82, with a median of 56.5. Mappings range
from 44 to 527, with a median of 249.5. All evidence-environment support IDs,
question mappings, decisive evidence, contrary evidence, and bias-assessment support
IDs resolve to evidence in the applicable dossier.

The two empty `material_biases` arrays are the receiver's explicit zero-evidence
fallbacks for Biden 1B and 2B. They retain full uncertainty, affirm both bias
safeguards, and do not fabricate a cited bias finding.

## Chapter results

| Chapter | Numeric | Null | Numeric mean | Numeric range |
|---|---:|---:|---:|---:|
| 1B | 18 | 2 | 5.58 | 2.5–7.0 |
| 2B | 18 | 2 | 4.92 | 1.0–6.5 |
| 3B | 18 | 2 | 4.47 | 2.0–7.0 |
| 4B | 19 | 1 | 4.00 | 1.5–7.0 |
| 5B | 18 | 2 | 4.56 | 3.5–5.5 |
| 6B | 19 | 1 | 4.71 | 3.5–6.5 |
| 7B | 10 | 10 | 4.65 | 2.5–6.5 |
| 8B | 18 | 2 | 4.56 | 3.5–6.0 |

The concentration of 7B nulls is methodologically coherent: the receiver and judge
do not convert country-level corruption, repression, or institutional weakness into
a ruler's personal-integrity score without a personal knowledge, benefit, direction,
protection, deception, or obstruction nexus. This is safer than the prior release,
but the size of the change requires targeted review before promotion.

## Lean-v4 comparison

All 160 ruler-chapter cells match the preserved lean-v4 cohort by chapter and ISO3.
The old run contained four nulls; this run contains 22. Among the 134 cells numeric
in both versions:

- median absolute movement is 0.5;
- mean absolute movement is 0.80;
- 33 cells move by more than one point;
- maximum movement is 3.0 points.

Mean confidence falls from 79.9 to 61.0. Much of that reduction is desirable:
missing personal attribution, sparse evidence, shared authority, inherited
conditions, information restrictions, and duplicated source families now widen
ranges or produce nulls instead of false precision. The greater-than-one-point
movements nevertheless exceed the controlled promotion rule and require an explicit
score/order audit rather than automatic acceptance.

No client score fields enter the judge prompts. The only `client matrix` text is a
prohibition against using it as evidence.

## Contrasting-case manual read

- **Putin:** all eight chapters are scoreable. The record preserves actor attribution
  for the Ukraine invasion, nuclear alert and signaling, repression, election
  conditions, personal-network integrity evidence, economic shocks, social-policy
  actions, and implementation. Confidence and ranges reflect censorship and shock
  attribution rather than applying a blanket closed-regime penalty.
- **Tshisekedi:** all eight chapters are scoreable despite weaker state capacity and
  conflict exposure. The judgments distinguish state-of-siege authority, armed-group
  violence, peace efforts, shared humanitarian delivery, procurement reform, and
  ruler-specific attribution.
- **Scholz:** all eight chapters are scoreable. Coalition, federal, parliamentary,
  municipal, EU, NATO, war, energy, and refugee constraints remain explicit, and
  Germany's high inherited baseline is not credited to Scholz automatically.
- **Biden:** the run exposes a real producer/receiver regression. The producer omitted
  its required manifest and repeated formatters returned empty shells. The receiver
  safely recovered 25 individually cited bullets as context, but promoted none to
  final evidence. Five chapters are consequently null and the three numeric social,
  economic, and political-freedom judgments have low confidence. This is conservative
  and auditable, but it is not an improvement over the preserved saturated Biden
  dossier.

AMLO is the other material sparse-evidence case: 13 evidence records and 44 mappings
produce six null chapters. Those nulls avoid invention, but the dossier should be
recollected or supplemented before release promotion.

## Runtime and usage

The cohort dossier jobs ran for roughly seven wall-clock hours, followed by roughly
37 minutes for the chapter queue after receiver fixes and retries. Unique recorded
model turns account for approximately 3.50 million dossier input tokens, 1.13 million
dossier output tokens, 1.90 million judge input tokens, and 0.21 million judge output
tokens. Dollar cost is unavailable because the tool did not expose pricing.

## Verification

- `pytest -q tests/research` passed.
- `ruff check src/leaders_db/research tests/research` passed.
- The known repository-wide Wikidata fixture failures remain unrelated to this work.

## Gate decision

The engineering and methodology gate passes: the pipeline completed at cohort scale,
preserved local evidence end to end, recovered imperfect producer output without
crashing, required auditable bias reasoning, and produced 160 structurally valid
judgments.

Release promotion does not pass yet. Before calling this the improved 2022 release:

1. rebuild or safely migrate the preserved Biden dossier so all admissible cited
   evidence is available to the new bias-aware judge;
2. recollect or supplement AMLO's sparse dossier;
3. rerun all eight common-meter chapters after those dossier changes;
4. perform and record the explicit audit of all 33 movements greater than one point;
5. rebuild the viewer only after that targeted audit clears the score/order gate.

Normative source wording and licenses remain in
[`docs/sources/attributions.md`](../sources/attributions.md).
