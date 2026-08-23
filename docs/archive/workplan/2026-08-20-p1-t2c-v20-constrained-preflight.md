# P1-T2C — fresh constrained autonomous-review preflight

- Date closed: 2026-08-20
- Outcome: COMPLETE
- Starting commit and ending commit: uncommitted working tree based on `ac033fdd53e192bc1e9a9df1af4f17af4c3760f1`; no commit created.
- Objective and scope executed: built a fresh zero-call preflight under release identity `netanyahu-2023-integrated-luna-sol-v20-constrained-review` for all 80 v17 blind-review requests using prompt contract v15 and packet-specific review schema v5.
- Decisions and lasting constraints: v17 promoted packages are trusted against their exact integrated-preflight hashes rather than reconstructed from the pre-promotion base package. Every writing artifact trusted-reloaded; raw outputs contain no reopen field and normalized reopen lists are empty. All review and judgment roots were unused before the manifest was created.
- Files/configs changed: persisted `research/runs/netanyahu-2023-integrated-luna-sol-v20-constrained-review/question-review-preflight.json`; workplan and archive documentation only. The temporary preflight runner was removed after use.
- Durable artifacts and SHA-256 bindings: v20 preflight SHA-256 `809840ed5fe658794ad6892bf16b29d7d702617a015393319480152de23d04d7`; prompt contract SHA-256 `5245e1fee74afb14f8d9545e69b8267f4124ee8e24c762b45ebb52bc3953ad9e`; experiment policy SHA-256 `b70b3c299d41ee293af7d05de09205d3159b3e031b9f075aeed142f357ad3c97`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: planned OpenAI `gpt-5.6-luna`, high reasoning, Codex subscription; no execution approval consumed and actual calls 0.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: measured planned input 4,787,345 tokens across 20,370,678 request characters; maximum per-call output allowance 128,000 and available aggregate output quota 679,491; actual usage was zero. Subscription billing is not exposed; directly billed cost was $0.
- Focused/full tests, lint, validators, and reviews: the constrained transport's 51 focused tests, Ruff, full default suite, and independent review were already clean; the persisted preflight validated 80 requests, eight chapters of ten, 80 distinct schema hashes, all configured budgets, and all input bindings.
- Failures/findings and disposition: the first local zero-call construction attempted the generic base-package rebuilder, which correctly rejected v17's promoted packages. No artifact was written. The preflight then used the authoritative v17 integrated-manifest package hashes, without changing inputs or making a model call.
- Deferred/optional items (non-blocking): none.
- Next task activated or exact blocker: P1-T2D is active but blocked on quota-bound approval. No review, judgment, audit, or publication call has started.
