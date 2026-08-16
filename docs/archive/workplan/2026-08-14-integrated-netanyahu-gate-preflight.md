# Integrated Netanyahu gate preflight

## Outcome

Task 6 was rejected before model execution. The fresh diagnostic release
`netanyahu-2023-integrated-gate-v3` validated the frozen Netanyahu corpus and selected
chapter manifest and deterministically built eight question packages containing all 80
questions. It then stopped because the straight-through call inventory is ineligible for
the plan's cost gate.

## Call inventory

| Action | Model | Surface | Calls |
|---|---|---|---:|
| Question writing | `gpt-5.6-terra` | Codex subscription | 80 |
| Independent question review | `gpt-5.6-sol` | Codex subscription | 80 |
| Chapter judging | `gpt-5.6-terra` | Codex subscription | 8 |
| Independent judgment review | `gpt-5.6-sol` | Codex subscription | 8 |
| Total | | | 176 |

The one-ruler promotion target is below 150 calls, represented as a hard ceiling of 149.
Removing a required independent review merely to reach the target would violate the Task 5
control contract and the quality gate. No call was started, so input, cached-input, output,
and reasoning-output usage are all zero. No API key was used.

## Trusted artifacts

The release config is
`configs/evidence-funnel/netanyahu-2023-integrated-gate-v1.yaml`. The fresh run directory
is `research/runs/netanyahu-2023-integrated-gate-v3/`; its preflight manifest binds the
experimental config, control flow, frozen v4 release, corpus judge package, selection
manifest, stage-budget contract, and all eight derived question packages by SHA-256.

The first independent review found that the initial manifest omitted the stage-budget hash
and trusted configured question/call counts. The corrected preflight validates the exact
four-stage inventory, the expected ten ordered IDs in every package, all required stage
budgets, and the budget hash. It also added the previously missing pre-call budget to the
chapter-judgment reviewer. The second review requested an exact configured question-count
check and executor-level budget tests. Those tests exposed and fixed append-mode corruption
when separate trackers reused a shared ledger. The final manifest also binds the preflight
implementation by hash.

The final concurrency review found that first-time shared-ledger creation still used a
check-then-truncate sequence before locking. Ledger creation now uses atomic, non-truncating
`O_CREAT | O_RDWR`; a sixteen-contender regression test proves exactly eight reservations
succeed and eight stop under the configured ceiling.
Independent re-review found no remaining blocker.

## Decision

Do not run the 176 calls. Task 6 cannot pass until a later design change reduces the
production and independent-quality actions below 150 calls without weakening complete
80-question review. Task 7 remains blocked because no integrated one-ruler result passed.
