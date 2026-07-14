# V3 Judge-Only Acceptance Review

## Run

- Judge run: `2020-diverse-20-luna-judge-v3`
- Frozen dossier source: `2020-diverse-20-luna-v2`
- Cohort: 20 ruler-years, eight chapter judges, 160 judgments
- Judge usage: 1,608,219 tokens
- PAYG-equivalent range: $2.387242-$3.179249
- Actual subscription billing: not exposed

The first execution attempt exposed a zero-token worker defect: planning supported a
separate dossier run key, but dependency loading still searched the judge run. The
worker now resolves and validates artifacts against the explicit dossier run key.

## Contract improvements verified

- Numeric scores use half-point increments.
- Numeric scores cannot use `recoverable_null`.
- Every numeric score cites at least one decisive stable evidence ID.
- Manual-review flags fell from 130/160 in v2 to 11/160 in v3.
- Nulls increased where the dossier did not support a discriminating judgment: 13 in
  1B, 12 in 2B, two in 3B, eight in 5B, seven in 6B, and 15 in 7B.

## Independent verdicts

The 1B-4B auditor accepted 4B, narrowly rejected 3B, and rejected 1B and 2B. The
5B-8B auditor rejected all four chapters for scaling. Overall verdict: **NO-GO**.

- `1B`: several numeric scores still rely on speeches, generic posture, civil nuclear
  policy, or evidence outside 2020 rather than a target-period risk-bearing choice.
- `2B`: Modi, Widodo, Merkel, and Rouhani still rely on domestic, generic, speech, or
  weakly personalized evidence rather than target-period international conduct.
- `3B`: ordering is otherwise credible, but Ardern's 8 lacks the required multiple
  independent target-period source types. `4B` is accepted.
- `5B`: Ardern, Xi, and Buhari do not cleanly meet the economic action plus
  implementation/outcome floor.
- `6B`: Orbán and Erdoğan are scored from country/context evidence without a decisive
  ruler-attributed welfare action; Xi's attribution chain is also weak.
- `7B`: null discipline is much better, but Kim's low score still substitutes regime
  repression/corruption for a personal-integrity nexus; Trump has a misclassified
  positive item.
- `8B`: Xi and Kim remain over-scored from control rather than independently supported
  portfolio outcomes/adaptation; Orbán is penalized for missing implementation evidence.

Cross-cutting defects remain: `calibrated_against` lists only two anchors instead of
the complete comparison set; research-recoverable nulls are often not routed to
manual review or a targeted continuation; false review records retain boilerplate
reason text; and the chapter-specific semantic predicates remain prompt-only.

## Next gate

Before another paid case or larger batch, implement a deterministic semantic
preflight/repair layer that verifies complete calibration membership, cleans review
reason semantics, routes recoverable nulls, and checks machine-inspectable
chapter-specific predicates. Rejudge the named failures first; only a clean targeted
audit should authorize another full batch.
