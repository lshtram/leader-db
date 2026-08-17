# Focused Luna question-verifier diagnostic

## Decision

The focused second Luna pass is materially better than a duplicate broad review, but it is
not ready for an 80-question gate. It caught both known defects, preserved one clean
control, confirmed three repeated failures, and produced no invalid evidence ID. A local
evidence-level inspection also confirmed its two disputed decisions: repaired `3B.2`
still contains a material imbalance and unresolved evidence gap, while `2B.1` correctly
attributes the disputed statement and should pass. Repeatability remains untested.

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
| `2B.1` | pass | Correctly rejected all five first-pass findings. The answer says that the United States representative characterized Israel as committed to another agreement, which is exactly how the UN transcript identifies the speaker. |
| `2B.2` | fail | Found four materially omitted priority records and one reopenable omission. |
| `2B.4` | fail | Confirmed that the answer incorrectly described the State Comptroller investigation as suspended by the High Court. |
| `3B.2` | fail | Correctly found that the answer used a mixed source as favorable evidence while omitting Netanyahu's demand that military and security forces stop refusal to serve, which he called a crime. The answer also explicitly requested reopening the record about intelligence and initial-response failures; this is an unresolved material gap rather than a silently missing record. |
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

## Local adjudication of the disputed cases

### `2B.1`: focused pass confirmed

The answer states: “The United States representative said Israel was committed to another
agreement and that further pauses depended on Hamas.” In the exact UN transcript, the
speaker is United States representative Linda Thomas-Greenfield, and her statement says
that “Israel has made clear that it is committed to reaching another agreement.” The
answer therefore did not reverse the speaker attribution. The first broad review's five
blocking findings all depended on that mistaken premise. The focused verifier correctly
rejected them.

### `3B.2`: focused failure confirmed, with one wording correction

The answer cites `BATCH-0030-R01-E010` as countervailing evidence that Netanyahu delayed
the judicial-overhaul legislation, called for debate, and urged security forces to defend
everyone. The same exact passage also says that refusal to serve was a crime and records
Netanyahu demanding that military and security forces put an end to it. That is not a
minor detail for a question about how a ruler directed coercive institutions. Omitting it
makes the cited record appear more unambiguously favorable than it is and can change the
balance and strength of the judgment. The focused verifier was right to treat this as a
material priority-evidence omission.

The verifier also named `BATCH-0004-E021`, concerning intelligence and initial-response
failures around 7 October. The answer had not ignored this record: it explicitly requested
that it be reopened because a fuller account could change attribution and weight. Under
the current contract, that remains a blocking unresolved material gap—the final answer
does not contain the evidence needed to resolve it—but future reports should describe it
as an unresolved reopen request rather than a silently omitted record.

## Next bounded step

Do not run all 80 questions yet. Make accepted reopen requests deterministic blocking
inputs rather than asking Luna to rediscover them. Keep Luna responsible for chronology,
priority-evidence materiality, first-review findings, and new candidate gaps. Test that
general change independently, then rerun only the affected controls before deciding on a
larger diagnostic.

## Repeatability test

### Test performed

The same ten frozen packets, answers, and first reviews were sent through a second fresh
sequential Luna-high run. No writing, judging, scoring, audit, or publication stage ran.
The fresh run completed ten of ten calls; every strict response validated and every saved
artifact passed trusted reconstruction.

### Results and differences

Nine of ten final gates matched the first focused run. All eight first-run failures failed
again, and `2B.1` passed again after rejecting the earlier broad review's false attribution
finding. `4B.2` changed from pass to fail.

The `4B.2` change is a correction, not a newly invented defect. Its answer explicitly
requested reopening `BATCH-0032-E013`, saying the proposed National Guard could materially
change the security-forces analysis and its attribution to Netanyahu. The second verifier
correctly treated that unresolved material gap as blocking. The first verifier had missed
the answer's explicit reopen signal.

The detailed findings were substantially less stable than the final gates:

- `1B.2` caught the known chronology error in both runs.
- `2B.2` failed in both runs, but the first named four priority omissions and one additional
  gap while the second named three priority omissions and three additional gaps.
- `3B.2` failed in both runs, but the first named one priority omission and one additional
  gap while the second named no priority omission and ten additional gaps. Both included
  the answer's explicit `BATCH-0004-E021` reopen request.
- `7B.6` and `8B.9` failed in both runs, but chronology passed in the first run and failed in
  the second.
- No run emitted an invented or disallowed evidence ID.

This means Luna is repeatable enough to identify these answers as unsafe, but not yet
repeatable enough for its complete list of reasons to be treated as authoritative. The
current design also wastes model judgment on a fact already recorded structurally: a
writer's accepted reopen request states that candidate evidence may materially change the
answer. That condition should block deterministically before interpreting Luna's newly
discovered omissions.

### Repeatability profile

- Calls: 10 Luna-high Codex-subscription calls.
- Input: 768,878 tokens; cached input: 0.
- Output: 79,999 tokens, including 65,738 reasoning-output tokens.
- Total: 848,877 tokens.
- Combined call time: 1,496.318462 seconds.
- Codex-equivalent usage: 6.244360 credits.
- PAYG-equivalent estimate: $0.249773-$0.288220.
- Actual subscription billing: unavailable from the execution surface.
- Reconciliation: exact; all ten reservations completed, with zero unresolved reservations
  and zero token differences.

### Decision

Do not run an 80-question verifier yet. First make explicit accepted reopen requests a
deterministic blocking category with their own clear label. This removes the observed
`4B.2` inconsistency without asking the model to make the same decision twice. Then test
the affected cases and independently review the code. Luna's variable newly discovered
candidate lists still require conservative treatment and evidence-level adjudication; they
should not silently become production truth.

### Deterministic reopen update

Contract v2 now records every accepted writer reopen request separately as an unresolved
reopen ID and makes that field a deterministic blocker. Those IDs are removed from Luna's
compact candidate list and response allowlist, leaving Luna to identify only genuinely new
candidate gaps. The raw v2 response no longer contains `final_gate`; code derives the gate
from chronology, priority checks, first-review finding checks, unresolved reopen requests,
and new omissions.

The original prompt is frozen byte-for-byte as v1. Trusted reload selects the saved
contract version and reconstructs old v1 artifacts without applying v2 semantics. All 20
artifacts from the two completed focused runs trusted-reloaded exactly. Strict version
parsing also rejects boolean and floating-point substitutions for integer manifest
versions.

Verification completed with 33 focused and adjacent tests passing, Ruff passing, and a
clean independent review after one manifest-version tamper issue was found and repaired.
No model call was used for this update.

## Focused v2 control run

The first live v2 check ran only `3B.2` and `4B.2` in a fresh directory. Both calls
completed, passed strict parsing and trusted reconstruction, and failed as expected:

- `3B.2` records `BATCH-0004-E021` as an unresolved accepted reopen request. Luna did not
  repeat that ID as a new omission. It independently found the previously adjudicated
  `BATCH-0030-R01-E010` priority omission and proposed nine other advisory candidate gaps.
- `4B.2` records `BATCH-0032-E013` as an unresolved accepted reopen request. Luna did not
  repeat that ID as a new omission. It proposed two other advisory candidate gaps.

The update therefore fixed the observed category error: accepted reopen requests are
stable deterministic inputs, while Luna's newly proposed gaps remain separate and subject
to evidence-level adjudication.

Profile:

- Calls: 2 Luna-high Codex-subscription calls.
- Input: 129,496 tokens; cached input: 0.
- Output: 18,051 tokens, including 16,360 reasoning-output tokens.
- Total: 147,547 tokens.
- Combined call time: 333.511867 seconds.
- Codex-equivalent usage: 1.189010 credits.
- PAYG-equivalent estimate: $0.047561-$0.054036.
- Actual subscription billing: unavailable from the execution surface.
- Reconciliation: exact; both reservations completed with zero token differences.

A deterministic inventory then found that 56 of the 80 frozen answers already contain
one or more accepted reopen requests: 72 unresolved IDs in total. Those 56 answers are
known v2 failures without a model call. Only 24 answers have no accepted reopen request.
An 80-call verifier run would therefore spend 56 calls rediscovering a gate result that
code already knows.

The next possible diagnostic is limited to the 24 no-reopen answers. It requires a new
bounded subscription-run decision. The 56 deterministic failures instead identify an
upstream evidence-selection and answer-completion problem; they should not be sent through
Luna merely to reproduce the same failure.
