# Stage budgets and explicit stop rules — 2026-08-14

## Decision

Task 4 **passed** for the active frozen-corpus production path. Model spending is bounded
before execution for corpus reading, passage verification, straight-through question
writing, independent question review, and comparative chapter judging. The change adds no
retry, repair, or model-review phase.

## Active model-stage inventory

| Stage | Existing safety control | Added configured control | Resume behavior |
|---|---|---|---|
| Corpus reader | character/context checks and source partitions | request characters/tokens and stage calls/tokens | trusted output is reused |
| Passage verifier | deterministic partitions and request binding | request characters/tokens and stage calls/tokens | complete bound verdict is reused |
| Question writer | context check and one ordered call per question | ten-call chapter and request/stage size limits | trusted chapter artifacts load without a call |
| Independent question review | context check and one call per question | ten-call chapter and request/stage size limits | trusted review artifacts load without a call |
| Comparative chapter judge | projection/context estimate and output reserve | eight-call year/chapter stage plus request/stage size limits | trusted batch publishes without another call |

The versioned limits are in `configs/research-stage-budgets.yaml`. Provider context checks
prevent transport overflow; stage budgets separately constrain safe calls and cumulative
estimated input.

## Complete request accounting

The shared reservation measures the exact prompt plus strict response schema with the
`o200k_base` tokenizer before starting the subprocess. File-backed chapter-judge
projections are decoded and measured from the exact serialized files exposed to the model.

Every successful reservation writes `budget-reservation.json`. A refusal writes
`budget-stop.json` with the stage, component, configuration hash, measured size, prior
stage usage, and stable reasons: `request_characters`, `request_input_tokens`,
`stage_call_count`, or `stage_input_tokens`.

Reservations are thread-safe for parallel reader batches. Chapter-judge jobs share an
`fcntl`-locked persistent ledger under the run output root, so separate workers cannot
reset or race the eight-chapter stage allowance.

## Stop and resume rules

A refused reservation occurs before model-process execution and does not consume the
rejected allowance. A continuation may reuse a completed artifact only when it validates
against its contract. The shared loader no longer renames an invalid saved output and
executes the unchanged request again; it stops for explicit reconciliation. The existing
reader-only deterministic normalizer remains a no-model compatibility path.

## Verification

Focused tests cover normal execution planning, deliberately low request/token/stage/call
budgets, persisted stop reasons, process non-execution, exact file-backed inputs,
cross-worker persistent enforcement, invalid saved output, and trusted resume. The focused
suite, scoped Ruff, diff checks, and independent review pass. No model or API call was
made. Task 5 is next and was not begun.
