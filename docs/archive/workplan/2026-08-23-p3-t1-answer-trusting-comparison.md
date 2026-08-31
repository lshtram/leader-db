# P3-T1 — answer-trusting judgment comparison

- Date closed: 2026-08-23
- Outcome: COMPLETE
- Starting commit and ending commit: `ac033fdd`; uncommitted working tree.
- Objective and scope executed: Compared the completed five-ruler evidence-reading judgments with a fresh no-search diagnostic that judged the same five rulers and eight guides from the 400 reviewed answers and limitations without receiving source excerpts or local evidence records.
- Decisions and lasting constraints: The evidence-reading v8 publication remains authoritative. Answer-trusting judging is a lower-cost diagnostic option; it may not publish or replace the cited path without a separate promotion decision.
- Files/configs changed: Added the answer-trusting preflight/executor, explicit Codex web-search disable transport, focused tests, comparison artifacts, and synchronized governance/architecture/workplan documentation.
- Durable artifacts and SHA-256 bindings: accepted v5 preflight `a8683eac50f9ec8f6767dcc4bf9046719460a868a0575272b44d1f0a35deb829`; eight exact judgment and result-binding hashes are embedded in comparison JSON `57d4ff4d33b697acc293609a3f7fb7334645f4ba656ad337883dd66c5a150778`; comparison Markdown `bc7e4bcaae9e461255a22a4d2fa93bdb7379e9fe59d210231c8ee90f150e92e0`; baseline reviewed package `a3d0efc10fa5fa30071db1a075fafb45d0beb6448361485bb3448082b52eda2c`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: OpenAI `gpt-5.6-sol`, high reasoning, Codex subscription; end-to-end envelope 8 calls / 2,500,000 input / 500,000 output; actual accepted v5 calls 8.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: accepted v5 used 854,723 input, 275,712 cached input, 89,287 output, and 16,119 reasoning-output tokens; subscription surface exposes no direct billed cost.
- Focused/full tests, lint, validators, and reviews: Focused answer-trusting and command-boundary tests, Ruff, strict identity/citation/confidence/no-tool validation, exact usage reconciliation, deterministic comparison, and independent review passed.
- Failures/findings and disposition: V2 failed lens-set disjointness, v3 exposed invalid fractional confidence, and v4 exposed an unauthorized 8B web-search action. All remain immutable diagnostics. Prospective v5 fixed the general prompt, confidence, and technical web-disable contracts and completed cleanly.
- Deferred/optional items (non-blocking): Repeatability across other cohorts and a promotion decision for any answer-trusting production variant.
- Next task activated or exact blocker: P3-T2 — version and activate the promoted five-ruler pipeline.
