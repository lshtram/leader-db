# Luna-high independent question-review experiment

## Decision

Two identical Luna-high reviews are not reliable enough to act as the independent quality
gate. They agreed on 67 of 80 questions, missed a known chronology defect in both passes,
and produced three invalid evidence references in each pass. A second Luna call remains
worth testing, but it should perform a narrower verification task rather than repeat the
first review.

No writing, chapter judging, judgment review, scoring, audit, or publication stage ran in
this experiment.

## Test design

Both passes reviewed the same immutable set of 80 accepted question answers from
`netanyahu-2023-integrated-luna-sol-v10`. Each question received a fresh Luna call with high
reasoning and prompt configuration version 11. The response validator rejected evidence
IDs that were not present in the question's supplied packet. Both passes used separate run
directories and identical call, input-token, and output-token ceilings.

The known checks were:

- `1B.2` should fail because it places a 3 November statement before a 28 October event.
- `2B.2` should fail because it omits material evidence.
- repaired `3B.2` should pass.
- `4B.2` should produce a logically consistent result under the version-11 contract.

## Pass 1 result

All 80 model calls completed and reconciled. Seventy-seven responses validated: 67 passed
their answer and 10 failed it. Three responses were invalid because Luna named unavailable
evidence: `2B.3` named `BATCH-0036-E020`, `3B.10` named `BATCH-0018-E006`, and `8B.9`
named `BATCH-0036-E019` and `BATCH-0036-E020`.

Luna passed `1B.2` and `2B.2`, missing both known defects. It passed repaired `3B.2` and
returned a coherent pass for `4B.2`.

Measured use was 5,777,731 input tokens, including 55,552 cached tokens, and 377,289 output
tokens, including 329,419 reasoning tokens. Total use was 6,155,020 tokens. The profile
estimates 39.957341 Codex-equivalent credits and a $1.598292-$1.884404 PAYG equivalent;
actual subscription billing is not exposed. Summed model-call time was 7,187.419980 seconds.

## Pass 2 result

All 80 model calls completed and reconciled. Seventy-seven responses validated: 70 passed
their answer and 7 failed it. Three responses were invalid because Luna named unavailable
evidence: `1B.3` named `BATCH-0017-E014`, `5B.7` named `BATCH-0016-R01-E020`, and `8B.9`
named `BATCH-0036-E019`.

Luna again passed `1B.2`, missing the known chronology defect twice. It failed `2B.2` in
this pass, so the known omission was detected once in two attempts. It again passed
repaired `3B.2` and returned a coherent pass for `4B.2`.

Measured use was 5,777,731 input tokens, including 47,616 cached tokens, and 360,026 output
tokens, including 313,195 reasoning tokens. Total use was 6,137,757 tokens. The profile
estimates 39.475163 Codex-equivalent credits and a $1.579008-$1.865513 PAYG equivalent;
actual subscription billing is not exposed. Summed model-call time was 6,884.697161 seconds.

## Repeatability

The passes agreed on 67 of 80 final states (pass, fail, or invalid), an agreement rate of
83.75%. They disagreed on 13 questions:

| Question | Pass 1 | Pass 2 |
|---|---:|---:|
| `1B.3` | pass | invalid |
| `2B.1` | fail | pass |
| `2B.2` | pass | fail |
| `2B.3` | invalid | pass |
| `2B.7` | pass | fail |
| `3B.10` | invalid | pass |
| `4B.10` | fail | pass |
| `4B.5` | fail | pass |
| `5B.4` | pass | fail |
| `5B.6` | fail | pass |
| `5B.7` | pass | invalid |
| `5B.9` | fail | pass |
| `7B.4` | fail | pass |

Only `1B.1`, `2B.4`, `6B.9`, and `7B.6` failed substantively in both passes. `8B.9` was
invalid in both passes. The strict evidence-ID validator prevented every invalid response
from becoming an accepted review artifact.

## Suggested next Luna experiment

Do not decide by majority vote between two duplicate reviews. Keep the first Luna review
as the broad assessment, then give the second Luna call a narrower verification contract:

1. provide the first review's proposed defects;
2. require an explicit chronology check;
3. require a disposition for every priority evidence item;
4. constrain all evidence selections to an exact keyed allowlist; and
5. ask the verifier to confirm or reject each proposed blocking defect separately.

Evaluate that design first on a bounded diagnostic set containing known defects, repeated
findings, disagreements, and invalid-ID cases. Do not run the remaining pipeline until the
review gate is repeatable and catches the known defects.
