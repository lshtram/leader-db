# P2-T1A — generic sparse-question transport

- Date closed: 2026-08-21
- Outcome: COMPLETE
- Starting commit and ending commit: `ac033fdd` to uncommitted working tree
- Objective and scope executed: make genuinely evidence-empty question packets writable and
  independently reviewable without inventing evidence, special-casing a ruler, or changing frozen
  source artifacts.
- Decisions and lasting constraints: prompt contract v16 instructs an evidence-insufficient answer;
  its strict transport permits no citations, requires at least one stated limitation, and fixes the
  evidence-disposition ledger as empty. Blind review permits only empty evidence-selection arrays.
- Files/configs changed: question prompt/schema/validation code and tests; archived prompt v15;
  fresh five-ruler v3 preflight config; synchronized normative documentation.
- Durable artifacts and SHA-256 bindings: `research/runs/five-ruler-2023-luna-sol-v3-release/`
  manifest SHA-256 `1756b2cf73be57cb6a0af07fa762656afebe775ea513f1072dab7099651fe999`,
  config SHA-256 `c8690cb93041f60ed2afe345daef459b6265a42eb25a395bdcff93e353779525`,
  and prompt SHA-256 `e90d1b969b4409c497e0679e280f88677a4694361a442a860fdc50249c774401`.
- Model provider/model/reasoning/surface; approved maximum and actual calls: prospective OpenAI
  `gpt-5.6-luna`, high reasoning, Codex subscription; zero calls and no approval consumed.
- Input/cached/output/reasoning tokens, elapsed time, billing limitation: all 400 complete writer
  requests measure 21,934,404 input tokens; zero model usage or billing.
- Focused/full tests, lint, validators, and reviews: focused writer, review, and cohort-preflight
  tests; Ruff; independent review; final verification recorded at closeout.
- Failures/findings and disposition: the sparse-packet blocker is resolved. The immutable v3
  preflight remains rejected solely because 51,200,000 tokens of output-reservation capacity exceed
  its prospective 5,000,000-token cohort ceiling.
- Deferred/optional items (non-blocking): none.
- Next task activated or exact blocker: P2-T2 remains blocked only on a prospective output-capacity
  decision and a fresh preflight; model execution has not begun.
