# P1 v17 final writing

- Date closed: 2026-08-20
- Outcome: COMPLETE
- Starting commit and ending commit: `d88e9cd4` to `ac033fdd`
- Objective and scope executed: run the fresh Netanyahu 2023 v17 final-writing stage only under
  the closed evidence-discovery contract.
- Decisions and lasting constraints: the 80 accepted answers are immutable inputs to blind
  independent review; the focused verifier is not an extra production stage; no review or
  judging authorization was consumed.
- Files/configs changed: `docs/workplan.md` checkpoint only; run artifacts are in the local
  research run store.
- Durable artifacts: `research/runs/netanyahu-2023-integrated-luna-sol-v17/` and
  `research/runs/netanyahu-2023-integrated-luna-sol-v17-profile-writing-v1/`.
- Model execution: 80 OpenAI `gpt-5.6-luna` high-reasoning calls through Codex subscription;
  no API key.
- Usage: 4,703,846 input, zero cached input, 320,509 output, 100,066 reasoning-output tokens,
  and 6,126.346563 summed call seconds. Subscription billing is not exposed; PAYG equivalent
  was $1.325380-$1.560572 and Codex-credit equivalent 33.1345.
- Verification: all 80 raw responses use the closed schema; 80 trusted reconstructions and
  deterministic gates pass; eight writing manifests pass; the ledger reconciles with zero
  difference and no unresolved reservation; focused tests and the full default suite pass.
- Findings: scientific quality remains inconclusive until blind independent question review.
- Deferred/optional items: none inside writing.
- Next task: P1-T1, zero-call blind-review preflight.
