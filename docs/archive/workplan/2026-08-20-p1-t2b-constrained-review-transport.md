# P1-T2B — constrain blind-review evidence-ID transport

- Date closed: 2026-08-20
- Outcome: COMPLETE
- Starting commit and ending commit: uncommitted working tree based on `ac033fdd53e192bc1e9a9df1af4f17af4c3760f1`; no commit created.
- Objective and scope executed: implemented a prospective packet-specific strict response schema for blind question review without launching a model call or modifying immutable v19. The schema fixes `question_id` and limits both candidate-level missed IDs and review-level omitted IDs to the exact packet candidate allowlist.
- Decisions and lasting constraints: execution, budget reservation, zero-call preflight measurement, saved schema hashing, and trusted reload use the same dynamic schema builder. Deterministic post-response identity and allowlist validation remains. New prompt contract v15 requires review manifest/schema v5; archived prompt contracts through v14 require generic schema v4, and a manifest cannot select or downgrade its own validation regime.
- Files/configs changed: `configs/question-packet-prompts.yaml`, archived `configs/question-packet-prompts-v14.yaml`, JSON execution and corpus-runner transport, blind-review producer/validator, review preflight, focused tests, architecture, requirements, and workplan/archive documentation.
- Durable artifacts and SHA-256 bindings: current prompt contract v15 SHA-256 `5245e1fee74afb14f8d9545e69b8267f4124ee8e24c762b45ebb52bc3953ad9e`; archived prompt contract v14 SHA-256 `840dc6c0454889f904e66e1144c1d8cf5c465540edbfa113c441a86bb76a160f`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: no model run; actual calls 0.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: all token usage 0; directly billed cost $0; no model billing surface used.
- Focused/full tests, lint, validators, and reviews: 51 focused tests passed; full default suite passed with its expected slow-test skips; Ruff passed. Independent review found and prompted fixes for historical-schema compatibility and schema-version downgrade, then returned clean with no material findings.
- Failures/findings and disposition: initial unconditional v5 reload would have rejected historical generic schemas; versioned v4 reload fixed it. A subsequent manifest-controlled downgrade path was fixed by deriving schema v4/v5 from the independently loaded prompt contract version and covered by a downgrade regression.
- Deferred/optional items (non-blocking): policy tuning remains empirical and belongs to a fresh immutable run after preflight and approval.
- Next task activated or exact blocker: P1-T2C is active for a fresh zero-call constrained-review preflight. Any model execution remains blocked on that preflight and renewed bounded approval.
