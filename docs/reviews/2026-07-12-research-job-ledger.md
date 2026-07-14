# Research Job Ledger Review — 2026-07-12

## Scope

Reviewed migrations `0006_research_job_ledger.sql` and
`0007_research_job_lease_fencing.sql`, matching ORM models, ledger
repository, planner, CLI commands, readiness integration, and focused tests.

## Invariants checked

- Stable `(run_key, job_key)` planning does not duplicate jobs.
- Existing job inputs, checkpoints, attempts, and results are not overwritten by
  replanning.
- Concurrent compare-and-set claims produce at most one owner.
- Only the current unexpired lease owner with its fencing token can heartbeat,
  checkpoint, complete, or fail active work.
- Expired leases are reclaimable with the last checkpoint preserved.
- Attempts are bounded; repeated retryable failure becomes terminal failure.
- Quarantined jobs never enter the queue.
- Judge dependencies block claims until dossiers complete or are explicitly
  removed through quarantine/cancellation.
- Judge creation and dependency insertion share one transaction.
- Every job records the exact provider profile, provider, and model.
- Credential contents are not stored in the ledger.

## Verification

The first review found a PostgreSQL claim race, non-atomic judge planning, absent
lease fencing, and missing ORM constraint mirrors. The implementation now uses
an outer compare-and-set predicate, atomic judge/dependency planning, rotating
lease tokens with expiry checks, and matching ORM `CheckConstraint` declarations.
The second review found that a PostgreSQL worker losing a safe claim race could
still return a false-empty result; PostgreSQL claims now use `FOR UPDATE SKIP
LOCKED` so concurrent workers move to different eligible rows.

Focused migration, ledger, concurrency, planner, CLI, and readiness tests pass.
Repository-wide `ruff check .` and the full default `pytest -q` suite pass; 29
pre-existing tests remain skipped unless `--runslow` is requested. The final
bounded reviewer pass reported no findings.
