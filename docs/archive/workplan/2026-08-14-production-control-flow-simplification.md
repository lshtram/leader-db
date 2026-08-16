# Production control-flow simplification

## Decision

Task 5 passed without a model call. The candidate control contract retires the historical
three-round targeted repair, requirement-led automatic repair, post-compaction re-review,
and retryable model-job failure paths. `production-2023-v4` remains unchanged as the
frozen comparison release; Task 6 must use a new experimental release and run ID.

## Active call map

The model-bearing path is three straight-through pairs:

```text
corpus reading -> independent corpus verification
question writing -> independent question review
chapter judging -> independent chapter-judgment review
```

Each production action has exactly one named independent quality action. A quality action
cannot invoke another model review. Source identity and hash checks, schema and citation
checks, corpus-completion checks, score/order audit, and publication validation are
deterministic and therefore do not add model calls.

## Failure and return behavior

Model-job failures are recorded as terminal failures rather than being marked retryable.
A later attempt requires an explicit operator action. A recoverable null judgment may
emit one user-visible research-return request; the artifact records that it does not run
automatically and caps the return at one round. Other nulls proceed to substantive review.

## Frozen comparison

The reproducible comparison is
`research/runs/netanyahu-2023-cost-opt-task5-control-flow-v2/control-flow-comparison.json`.
It binds the candidate contract and frozen `production-2023-v4` by SHA-256. The baseline
allows three targeted repair rounds, requirement-led repairs, and review after compaction;
the candidate allows zero automatic retry, repair, re-review, or supervisor-takeover
rounds. This structural comparison uses the same frozen release/case and makes no quality
claim beyond the already accepted straight-through question result. End-to-end quality
remains the Task 6 gate.

## Verification

- 31 focused control-flow and chapter-judge tests passed.
- Scoped Ruff and `git diff --check` passed.
- No model or API-key call was made; token usage is zero.
- The first independent review found that the declarative contract was not enforced and
  did not reject shared or orphan reviewers. Both findings were corrected by enforcing the
  contract at all six model executor boundaries and requiring one-to-one pairs; a clean
  independent re-review found no remaining blocker.
