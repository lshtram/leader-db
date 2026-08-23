# P1-T3 — eight chapter judgments

- Date closed: 2026-08-21
- Outcome: COMPLETE
- Starting commit and ending commit: `ac033fdd`; uncommitted working tree.
- Objective and scope executed: Produced one reviewed-answer-bound Sol-high judgment for each chapter 1B-8B.
- Decisions and lasting constraints: Judge schemas bind chapter lens IDs, eligible calibration dossiers, reviewed answer selection, and projected citation IDs.
- Files/configs changed: Approved projection transport, chapter schema/prompt/worker wiring, tests, and normative docs.
- Durable artifacts and SHA-256 bindings: Valid judgments are retained across immutable v24-v26 run identities and assembled into the v27/v28 review sources.
- Model provider/model/reasoning/surface; approved maximum and actual calls: OpenAI `gpt-5.6-sol`, high, Codex subscription; calls are included in the 35-call continuation total.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: Included in consolidated Phase 1 usage; direct billed cost zero, subscription billing unavailable.
- Focused/full tests, lint, validators, and reviews: Projection/judge suites and Ruff passed; each prospective transport fix received clean independent review.
- Failures/findings and disposition: v22 pre-inference schema rejection, v23 semantic lens failure, v24 calibration failure, and v25 8B overlap failure remain immutable diagnostics; general contracts were fixed before fresh runs.
- Deferred/optional items (non-blocking): None.
- Next task activated or exact blocker: P1-T4 executed with eight valid judgments.
