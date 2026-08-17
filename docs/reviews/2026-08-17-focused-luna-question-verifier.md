# Focused Luna question-verifier diagnostic

## Decision

The focused second Luna pass is materially better than a duplicate broad review, but it is
not ready for an 80-question gate. It caught both known defects, preserved one clean
control, confirmed three repeated failures, and produced no invalid evidence ID. It also
failed repaired `3B.2` on newly identified omissions and passed disputed `2B.1` after
rejecting the first review's attribution finding. Those two cases require bounded
evidence-level adjudication before another model experiment.

No writing, chapter judging, judgment review, scoring, audit, or publication stage ran.

## Test

Ten immutable v10 answers were selected before execution:

- known defects: `1B.2`, `2B.2`;
- repaired or contract controls: `3B.2`, `4B.2`;
- failures repeated in both broad passes: `1B.1`, `2B.4`, `6B.9`, `7B.6`;
- repeated invalid-ID case: `8B.9`;
- broad-pass disagreement: `2B.1`.

Each answer received one sequential Luna-high call through the Codex subscription. The
verifier checked chronology separately, dispositioned every priority record, could name
new omissions only from the packet's reopenable-ID allowlist, and checked each first-pass
blocking finding. Deterministic code derived the final gate. Trusted reload reconstructed
the prompt, raw response, strict schema, canonical output, inputs, hashes, and manifest.

The estimated combined input was 615,102 tokens. The run ledger capped calls at 10, input
at 1.2 million tokens, and formal worst-case output reservations at 1.28 million tokens.
Expected actual output was below 120,000 tokens.

## Results

| Question | Result | Plain-language finding |
|---|---|---|
| `1B.1` | fail | Confirmed all three first-pass blocking findings. |
| `1B.2` | fail | Correctly found that the 3 November Amalek letter followed the 28 October ground-operation announcement. It also identified priority and reopenable omissions. |
| `2B.1` | pass | Rejected all five first-pass findings and found no omission. The earlier speaker-attribution concern remains disputed and needs evidence-level adjudication. |
| `2B.2` | fail | Found four materially omitted priority records and one reopenable omission. |
| `2B.4` | fail | Confirmed that the answer incorrectly described the State Comptroller investigation as suspended by the High Court. |
| `3B.2` | fail | Found that one priority record omitted Netanyahu's demand to stop refusal to serve and named one reopenable record about intelligence and initial-response failures. This is a plausible new finding against a previously repaired control and requires adjudication. |
| `4B.2` | pass | Found chronology, priority coverage, and reopen handling adequate. |
| `6B.9` | fail | Confirmed omission of the record about the civilian-home-front authority gap and Netanyahu's responsibility. |
| `7B.6` | fail | Confirmed all three first-pass findings and four reopenable omissions. |
| `8B.9` | fail | Named only allowed IDs and found one priority and one reopenable omission. The prior invalid-ID failure did not recur. |

All ten calls produced valid strict responses and passed trusted reload. Eight answers
failed and two passed. No unknown evidence ID was accepted or attempted in output because
the schema exposed only the allowed reopenable IDs.

## Profile

- Calls: 10 Luna-high Codex-subscription calls.
- Input: 768,878 tokens; cached input: 0.
- Output: 76,785 tokens, including 64,168 reasoning-output tokens.
- Total: 845,663 tokens.
- Combined call time: 1,437.740752 seconds.
- Codex-equivalent usage: 6.147940 credits.
- PAYG-equivalent estimate: $0.245919-$0.284361.
- Actual subscription billing: unavailable from the execution surface.
- Reconciliation: exact; zero unresolved reservations and zero token differences.

The first generated profile counted usage correctly but classified scientific gates as
unavailable because the generic profiler did not recognize the new focused manifest. A
reviewed general fix added that manifest to metadata discovery. Fresh profile v2 reports
eight failures and two passes with no unavailable gate.

## Next bounded step

Do not run all 80 questions yet. Inspect the exact evidence, answer text, and verifier
rationale for `3B.2` and `2B.1` without a model call. Decide whether each focused result is
correct under the materiality standard. If both are correct, define the focused verifier
as deliberately stricter and test repeatability on the same ten cases. If either is an
over-sensitive or mistaken result, change the general verifier instruction or gate rule,
unit-test it, independently review it, and rerun only the affected diagnostic cases in a
fresh directory.
