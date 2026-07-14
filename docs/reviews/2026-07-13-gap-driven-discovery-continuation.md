# Gap-Driven Discovery Continuation Review

Date: 2026-07-13
Scope: bounded parent discovery continuation for ruler-level dossiers
Reviewer: independent Codex reviewer (`discovery_continuation_review`)

## Gate history

The first review found no blocker and five majors: rejected discovery results
could satisfy source breadth; child URL opens were not allowlisted; the schema
advertised more rounds than execution supported; retry token use was incomplete;
and search-changing recipe text was still hard-coded. Four minors covered plan
coverage, raw-round provenance, hostname breadth, and a crash window before model
handoff.

All findings were addressed in place:

- sufficiency uses only evidence retained by the validated dossier;
- the implemented contract permits zero or one follow-up round;
- every job persists the full versioned search recipe;
- child URL opens and dossier evidence locators are provenance checked;
- approved HTTP(S) and hash-verified `local-prior:<methodology-id>` are the only
  accepted evidence locator forms;
- exposed usage includes policy-approved failed initial and continuation calls;
- every raw discovery round is path/hash recorded;
- an atomic parent-continuation marker enables crash recovery before child handoff;
- readiness rejects a plan that omits a selected chapter; and
- hostname-family breadth is explicitly conservative and is not treated as a
  source-authority or quality score.

## Verification

- Focused continuation, worker-contract, planner, and readiness tests: passing.
- All research tests: passing.
- Ruff over `src` and `tests`: passing.
- Full repository suite: passing (29 slow tests skipped by the default command).

## Final disposition

Approved after three correction passes. The independent reviewer reported no
blocker, major, or actionable minor. The final focused scope contains 50 passing
tests and passes Ruff. The final full-suite result is recorded in the workplan
and completion report.
