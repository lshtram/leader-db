# Question Guide Coverage Audit — 2026-07-12

> Superseded later on 2026-07-12. The active design uses eight chapter guides;
> the 17 per-question drafts counted below are archived design history.

## Result

The authoritative 1B–8B bank currently contains **80 questions**, not 81: ten
questions in each of eight chapters.

| State | Count |
|---|---:|
| Expected question guides | 80 |
| Structurally substantive draft guides | 17 |
| Missing guides | 63 |
| Production-ready guides | 0 |

Existing drafts cover `1B.1`–`1B.2`, `2B.1`–`2B.2`, `3B.1`–`3B.2`,
`4B.1`–`4B.3`, `5B.1`–`5B.2`, `6B.1`–`6B.2`, `7B.1`–`7B.2`, and
`8B.1`–`8B.2`. Each contains the main template sections, but each is explicitly
marked draft. Under
`docs/methodology/question-guides/readme.md`, a guide becomes production-ready
only after its smoke cases, coherent judge batch, review, and post-test update
are complete.

## Operational consequence

- Full 80-question ruler research and production judging are blocked.
- A bounded evidence-only pilot may use a named draft guide when the run is
  explicitly identified as a guide-validation pilot.
- No score-bearing judge run may treat a draft guide as production-ready.
- Guide completion must be tracked per methodology ID, with smoke and judge-batch
  evidence rather than file existence alone.

## Cross-guide calibration finding

The expansion exposed a schema-level issue that should be resolved before judge
activation outside the current political-freedom slice. The common required
fields `severity_band`, `state_responsibility`, and `accountability_level` were
designed around abuse and culpability. Values such as `mass`,
`perpetrator_impunity`, and `state_policy` are semantically awkward for strategic
clarity, professional appointments, welfare purpose, and operational competence.
Draft guides currently explain a question-specific interpretation, but that does
not make the persisted enum values unambiguous. The judge schema needs either a
category-neutral common core plus question-specific dimensions, or explicit
applicability semantics, before these new guides can become active.

The first adversarial review also required explicit rules for no-exposure cases:
no nuclear rhetoric, no international crisis choice point, or no material
conflict must not automatically produce either a high or low score. Similarly,
an `8B.2` operationalization score requires an identifiable explicit or revealed
program; an unclear program is an evidence gap rather than proof of weak
execution.

The missing set is every 1B–8B ID except the 17 IDs listed above. The 12-guide
expansion deliberately spans six previously uncovered chapters so the next
end-to-end dossier and judge pilots can test nuclear-risk, international-peace,
economic, social, integrity, and ideology-neutral effectiveness reasoning rather
than only domestic-safety and political-freedom questions.
