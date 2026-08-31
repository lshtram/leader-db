# P1-T5 — final audit, publication, and one-ruler decision

- Date closed: 2026-08-21
- Outcome: COMPLETE
- Starting commit and ending commit: `ac033fdd`; uncommitted working tree.
- Objective and scope executed: Audited score/order, citations, hashes, attribution, quotas, and unresolved jobs; published experimental Markdown, HTML, and CSV outputs.
- Decisions and lasting constraints: The Netanyahu 2023 one-ruler gate passes and is production-eligible; five-ruler confirmation remains required before promotion.
- Files/configs changed: Publication/audit artifacts and synchronized workplan documentation.
- Durable artifacts and SHA-256 bindings: publication manifest `87854cf23a94139eaf777be339c823c884f8a44ebecec2472fe72bf9230fe73e`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: OpenAI Luna/Sol high on Codex subscription; maximum 50, actual 35 continuation calls.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: 12,664,316 input, 8,550,656 cached input, 191,649 output, 100,219 reasoning-output tokens; direct billed cost zero, subscription billing unavailable.
- Focused/full tests, lint, validators, and reviews: Deterministic publication audit passed every recorded check; final repository verification recorded at closeout.
- Failures/findings and disposition: Partial v29 renderer used a wrong confidence field and remains diagnostic; fresh v30 publication passed.
- Deferred/optional items (non-blocking): Five-ruler confirmation and release promotion.
- Next task activated or exact blocker: P2-T1 — freeze cohort and zero-call preflight.
