# Putin 2022 bias-aware pilot — compaction v2 gate

## Outcome

The repaired eight-chapter pilot passes the one-ruler promotion gate. It does not
authorize cohort scaling by itself. Relation-aware compaction retained ten final
evidence records per Putin chapter while every 20-ruler prompt stayed below the Codex
character ceiling. All eight chapter judgments validate, all cited evidence and bias
support IDs resolve within the corresponding projection, and both mandatory bias
safeguards are true.

The first no-search audit returned `PROMOTE_WITH_REVIEW`. A separate focused 8B
score/order review then explicitly returned `APPROVE_4_5`, clearing the only score change
larger than one point.

## Old release versus v2

| Chapter | Old score | v2 score | Delta | v2 confidence | v2 range | Gate |
|---|---:|---:|---:|---:|---|---|
| 1B | 2.0 | 2.0 | 0.0 | 92 | 1.5–2.5 | accepted |
| 2B | 1.0 | 1.0 | 0.0 | 97 | 1.0–1.5 | accepted |
| 3B | 2.0 | 1.5 | -0.5 | 90 | 1.0–2.5 | accepted |
| 4B | 1.0 | 1.0 | 0.0 | 97 | 1.0–1.5 | accepted |
| 5B | 2.0 | 2.0 | 0.0 | 90 | 1.5–2.5 | accepted |
| 6B | 3.5 | 3.0 | -0.5 | 70 | 2.0–4.0 | accepted |
| 7B | 1.5 | 1.5 | 0.0 | 74 | 1.0–2.5 | accepted |
| 8B | 6.0 | 4.5 | -1.5 | 58 | 3.5–5.5 | explicitly approved |

The 8B reviewer found that omitted E048, E049, E057, and E058 add favorable official
delivery context but do not establish enough Putin-specific program ownership or durable
progress to restore 6.0. The 4.5 judgment better follows the guide's separation of
agenda-setting, implementation, outcomes, and coercive state functioning.

## Recovery and validation

Three otherwise substantive candidates copied Putin's old dossier job key. They were
recovered without an LLM rerun only after exact matching of ISO3, ruler ID, ruler-year
ID, ruler name, period, and chapter to one unique trusted projection. Their evidence IDs
then validated against that projection. Ambiguous or conflicting identities remain
blocking.

Focused tests: 18 passed; Ruff passed. The full repository suite reached completion with
the same eight pre-existing Wikidata heads-of-state adapter failures (zero fixture
observations) and no compaction-related failures.

## Runtime and cost

The eight comparative judges used 1,529,479 input tokens (365,568 cached), 355,180 output
tokens, and 128,526 reasoning-output tokens. Estimated judge cost was $2.498662. Chapter
wall times ranged from about 9.9 to 16.6 minutes, so the next contrast pilot must retain
an explicit runtime/cost gate before broader scaling.

## Preserved evidence

- `comparative-inputs-v2/`: exact compact cohort inputs and omission ledgers.
- `comparative-judgments-v2/`: prompts, schemas, event logs, profiles, raw candidates,
  repaired canonical judgments, and run summary.
- `score-order-audit-v2.md`: valid eight-chapter no-search audit.
- `8b-order-review-v2.md`: explicit approval of the 8B score change.

The old lean-v4 release remains preserved and inspectable. The next controlled stage is
the three-ruler contrast pilot, not production promotion.
