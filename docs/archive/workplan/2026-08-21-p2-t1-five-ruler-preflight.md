# P2-T1 — freeze cohort and zero-call preflight

- Date closed: 2026-08-21
- Outcome: REJECTED
- Starting commit and ending commit: `ac033fdd` to uncommitted working tree
- Objective and scope executed: trusted-reload the frozen 2023 five-ruler cohort, create fresh
  model-output identities, build all forty chapter packets, and measure the complete writing
  request inventory without launching a model or downstream stage.
- Decisions and lasting constraints: the frozen cohort and source artifacts remain immutable;
  the rejected diagnostic attempts and terminal v2 release preflight must not be repaired in place.
- Files/configs changed: five-ruler zero-call preflight implementation and test; one cohort config;
  five per-ruler integrated release configs; synchronized workplan, architecture, and requirements.
- Durable artifacts and SHA-256 bindings: `research/runs/five-ruler-2023-luna-sol-v2-release/`
  contains the terminal manifest (`5fe0c91cb1b4b3bf03143a778640553b7f0ae63a45904a83ec58681487591922`),
  bound to fresh release config SHA-256
  `928ad4917df096b872d0c69388487190e5b4cbf346536684f8ad6fee3ff7232a`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: prospective OpenAI
  `gpt-5.6-luna`, high reasoning, Codex subscription; no approval consumed and zero actual calls.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: 399 complete requests
  measured 21,933,327 input tokens; one request was not constructible; zero model usage or billing.
- Focused/full tests, lint, validators, and reviews: focused preflight and related pipeline tests
  passed; Ruff and independent review passed. The default full suite completed with 25 failures
  outside the scoped P2-T1 files, recorded in `.pytest_cache`; this rejected task did not repair or
  conceal that broader dirty-worktree baseline.
- Failures/findings and disposition: frozen `PRK` question `7B.3` has no required evidence ID, so
  the exact Phase 1 writer transport cannot construct its strict response schema. Independently,
  400 calls require 51,200,000 tokens of configured output-reservation capacity against the
  5,000,000-token cohort ceiling. The result is preserved; no evidence, request, or limit was changed.
- Deferred/optional items (non-blocking): none.
- Next task activated or exact blocker: P2-T2 remains blocked until a prospective general contract
  for evidence-empty question packets is implemented and the complete output-reservation inventory
  fits prospective limits; both require a completely fresh release and preflight.
