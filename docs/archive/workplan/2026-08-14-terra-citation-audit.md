# Terra question-answer citation audit

## Decision

The fresh Terra/Sol run remains rejected and immutable. The writer contract will change
prospectively for every future question-packet run: answer prose must place every required
exact evidence ID beside the claim it supports or qualifies, while the structured evidence
dispositions remain the authoritative machine-readable ledger.

The blind quality gate is unchanged. It remains deliberately conservative and continues to
require every question to pass independently.

## Frozen inputs

- Run: `research/runs/netanyahu-2023-integrated-terra-sol-v2`
- Frozen predecessor selection:
  `research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/selected-chapter-manifest.json`
- Population: all 80 accepted Terra question answers and all 80 selected predecessor
  answers, across chapters 1B–8B.
- Model calls for this audit: zero.

## Method and result

The audit searched each answer's prose for its evidence IDs and separately counted the
structured dispositions. It did not treat a disposition as an inline citation.

| Measure | Terra | Frozen predecessor |
|---|---:|---:|
| Questions audited | 80 | 80 |
| Questions with at least one inline evidence ID | 0 | 40 |
| Distinct per-answer inline-ID occurrences | 0 | 773 |
| Structured dispositions | 1,241 | not applicable to the predecessor schema |
| Minimum / maximum Terra dispositions per question | 5 / 47 | not applicable |

The zero-of-eighty result follows the version 6 writer instruction that the disposition
entry was the citation and that no separate citation list should be created. The 6B.1 Sol
review therefore exposed a general transport and presentation rule rather than an isolated
formatting choice. It narrowly preferred the predecessor for claim-level auditability and
allocation-versus-execution distinctions; both answers omitted the same three candidate
records.

## Prospective control

Version 7 of `configs/question-packet-prompts.yaml` requires inline square-bracketed IDs
beside claims and retains one disposition per required record. Deterministic validation now
requires every exact priority ID inline and rejects unknown inline IDs, including compact
candidates that have not been reopened. Historical run artifacts are not rewritten,
revalidated as version 7, or promoted.
