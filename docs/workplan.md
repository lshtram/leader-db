# Workplan

## Purpose

This document is the operational handoff for the next development session. It records
only the current production baseline, active decision, remaining tasks, and completion
criteria. Detailed history through 2026-08-14 is preserved in
[`archive/workplan/workplan-through-2026-08-14.md`](archive/workplan/workplan-through-2026-08-14.md).

Normative scope and pipeline requirements remain in
[`requirements/top-level-requirements.md`](requirements/top-level-requirements.md).
Architecture belongs in [`architecture/overview.md`](architecture/overview.md), tracked
requirements in [`requirements/core.md`](requirements/core.md), source status in
[`sources/registry.md`](sources/registry.md), and the detailed cost program in
[`process/model-cost-optimization-implementation-plan.md`](process/model-cost-optimization-implementation-plan.md).

## Current objective

Use affordable models for the high-volume question work while preserving materially
accurate factual support, balance, ruler attribution, period handling, and judgeability.
Do not impose transcription-level precision when a numerical approximation cannot affect
the eventual human-style judgment. Keep the production flow
straightforward: one production phase, one dedicated independent quality phase, and no
automatic model repair or re-review loops inside either phase.

The compact table-row representation, lossless writer transport, stage budgets, and
straight-through control contract have passed their bounded gates. The 72 unresolved v10
evidence requests have now been explicitly promoted and the fresh v11 zero-call preflight
has passed. The next bounded phase is Luna-high writing only; review and judging remain
stopped until all 80 new answers pass deterministic validation with no reopen requests.

## Current production baseline

- Production release remains `production-2023-v4`; experiments do not mutate it.
- The approved five-ruler reference is `2023-five-ruler-flow-test-v2`.
- The approved deep Netanyahu reference is the frozen full-catalogue package and its
  approved eight-chapter output.
- The next candidate uses ten ordered Luna-high writes followed by ten Luna-high reviews;
  Sol-high is reserved for chapter judgment and judgment review. There is no internal critique, repair planner,
  correction pass, or automatic retry.
- Each question receives exact selected evidence plus a compact index of other candidates.
  Evidence dispositions are the single authoritative citation ledger.
- Corpus fact discovery uses whole extraction units. Deterministic code binds exact source
  text and hashes; historical evidence records remain valid.
- Model-cost accounting uses trusted event artifacts and reports API cost, Codex-equivalent
  usage, and unknown subscription billing separately.
- Model execution currently uses the Codex subscription. Before any API-key call, obtain
  user approval for the specific model and estimated token or monetary quota.
- The temporary module-size exception is closed. `chapter_judge_worker.py`,
  `corpus_reader_runner.py`, `research_worker_commands.py`, `model_call_budget.py`, and
  `question_packet_chapter.py` are below the 400-line convention, and their two named
  oversized focused test modules have been split by responsibility. The original public
  imports and patchable test seams remain available.

## Decisions already made

| Decision | Outcome |
|---|---|
| Canonical cost profiler | Retained and used as the measurement baseline. |
| Cache-oriented request envelope | Rejected; it increased complexity without reliable quality or cache benefit. |
| One chapter-wide writing call | Replaced by question packets and ten ordered writes because bounded exact evidence is safer and clearer. |
| One chapter-wide review call | Rejected; the exact request exceeds the Codex transport limit even after deduplication. Keep ten independent reviews. |
| Automatic repair and re-review | Rejected from the straight-through path. Fail once and make any later correction an explicit new decision. |
| Shared repeated-passage table | Rejected; 8.6% serialized saving did not justify another storage contract. |
| Paragraph-labeled fact discovery | Rejected; it omitted material facts. Whole-unit discovery remains active. |
| Verifier-selected paragraph citations | Technically sound but not promoted as a saving: the bounded run reduced citation text only 17% and omitted one known comparison during discovery. |

Detailed evidence for these decisions is in the archived workplan and immutable artifacts
under `research/runs/`.

## Current status of the cost-optimization plan

The numbered source plan remains useful as a design record, but rejected experiments mean
its original implementation sequence is no longer literal.

| Original step | Status |
|---|---|
| 1. Canonical profiling | Complete. |
| 2. Cache-oriented envelope | Tested and removed. |
| 3. Chapter synthesis | Goal addressed through deterministic question packets and straight-through per-question writing. |
| 4. Chapter-scoped review | Tested without a model call and removed because the request is too large. |
| 5–6. Delta repair and changed-only review | Not adopted; these would recreate the review loops the current design avoids. |
| 7. Compact research/reading output | Complete for the selected table-row representation; paragraph granularity was rejected. |
| 8. Stage budgets and stop rules | Complete for the straight-through pipeline. |
| 9. Integrated one-ruler gate | Rejected after the fresh Terra/Sol comparison and the Luna `xhigh` material omission. |
| 10. Five-ruler confirmation | Blocked pending an explicit new candidate decision and a passing fresh one-ruler gate. |

## Remaining task sequence

Complete one task per development session. Do not begin the next task until the current
task has a persisted result, passing focused verification, a clean review, and an updated
handoff in this document.

### Task 1 — Determine whether table-row citation granularity is viable

Status: **complete — promising for one bounded comparison**

Objective: determine without a model call whether statistical tables can be divided into
smaller immutable citation units than blank-line paragraphs.

Scope:

- Use frozen extractions, beginning with the Labour Force Survey slice that exposed the
  paragraph limitation.
- Identify table rows using deterministic source-text offsets; do not normalize or rewrite
  the authoritative text.
- Resolve every row back to the exact original substring with source, unit, offsets, and
  SHA-256.
- Measure row coverage, unsplittable content, citation-size distribution, and the potential
  saving for the known facts.
- Keep this isolated from the production reader and evidence schema.

Complete when:

- round-trip and tamper tests pass for ordinary text, Unicode, and table-shaped input;
- every nonblank source character is represented or explicitly classified outside the row
  grammar;
- measurements show whether the representation materially improves on paragraph spans;
- the result is recorded as `promising` or `rejected`, with no ambiguous partial promotion.

Result: exact row addresses covered all 38,936 nonblank characters in the frozen 12-unit
slice. The three known rows plus every context line from their source units required 1,866
characters versus a reproducible 39,620-character like-for-like paragraph baseline, a
95.3% reduction. This is representation evidence only. See
[`archive/workplan/2026-08-14-table-row-feasibility.md`](archive/workplan/2026-08-14-table-row-feasibility.md).

### Task 2 — Run one bounded table-row quality comparison, only if Task 1 passes

Status: **complete — passed**

Objective: test one frozen source slice through the existing discovery and quality
boundaries without adding a pipeline phase.

Scope:

- Keep whole-unit fact discovery.
- Let the existing verifier or a single bounded comparison select/check exact rows.
- Use a fresh output directory and exactly the calls authorized at session start.
- Compare against the corrected frozen baseline, including the 60.1% owner-occupied,
  71.9% rented, and Jewish-Arab employment facts.
- Stop after one failed result; do not automatically repair or review it again.

Complete when factual coverage and citation integrity pass and citation text is reduced
enough to justify integration. Otherwise archive the result and close row granularity as
rejected.

Result: one Codex-subscription `gpt-5.6-sol` call preserved all four corrected employment
facts, table-column and population meanings, limitations, exact source bindings, and the
lack of ruler-specific causal attribution. Exact citation text fell from 39,620 to 2,780
characters, a 93.0% reduction; the complete serialized comparison fell 86.3%. See
[`archive/workplan/2026-08-14-table-row-quality-comparison.md`](archive/workplan/2026-08-14-table-row-quality-comparison.md).

### Task 3 — Integrate compact citations at one downstream boundary, only if Task 2 passes

Status: **complete — passed**

Objective: prove actual transport savings rather than only representation savings.

Scope:

- Select one consumer with substantial exact-text input, preferably question-packet
  construction or verification.
- Preserve the existing whole-unit evidence record during compatibility migration.
- Reconstruct and validate all compact citations from frozen sources before use.
- Measure the complete serialized request before and after the change.
- Do not add a new model phase, review role, or storage abstraction unrelated to the saving.

Complete when the trusted old artifacts still load, the selected consumer uses the compact
representation safely, and measured request savings are material with no evidence loss.

Result: the diagnostic question writer retains the whole-unit evidence record by default
and can explicitly project exact table rows only after reconstructing them from frozen
source units. The corrected like-for-like serialized request fell from 148,462 to 24,983
characters, an 83.2% reduction, with no model call or evidence loss. See
[`archive/workplan/2026-08-14-table-row-writer-transport.md`](archive/workplan/2026-08-14-table-row-writer-transport.md).

### Task 4 — Finish stage budgets and explicit stop rules

Status: **complete — passed**

Objective: make model spending predictable without creating recovery loops.

Scope:

- Inventory every production model-bearing stage and its current character/token preflight.
- Add missing configured budgets and complete-request measurement.
- Stop before a call when a request is unsafe or a stage budget is exhausted.
- Resume only from trusted completed artifacts; never retry an unchanged failed request.
- Report the stage and request component responsible for a stop.

Complete when normal execution, deliberately low budgets, oversized input, and trusted
resume are covered by focused tests and no automatic repeat call is possible.

Result: the active reader, verifier, question-writer, independent-review, and chapter-judge
stages now reserve configured complete-request and cumulative stage capacity before
execution. Stops name the stage, component, and exhausted dimension; trusted completed
artifacts resume without calls, and invalid saved output cannot trigger an unchanged
automatic repeat. See
[`archive/workplan/2026-08-14-stage-budgets-and-stop-rules.md`](archive/workplan/2026-08-14-stage-budgets-and-stop-rules.md).

### Task 5 — Simplify the production control flow

Status: **complete; passed**

Objective: decide which historical review/correction mechanisms can be retired while
preserving quality.

Scope:

- Map model calls in the active production release from research through publication.
- Separate deterministic validation from model review.
- Target one production action followed by one dedicated independent quality action.
- Permit at most one explicit return for a material defect; it must be user-visible and
  must not run automatically.
- Compare any proposed removal on the same frozen case before changing production.

Complete when the active pipeline diagram and call inventory contain no hidden review,
repair, retry, or supervisor loops, or when each retained loop has a concise evidence-based
justification.

Result: the candidate contract maps three production/independent-quality pairs, separates
deterministic validation, disables automatic retry/repair/re-review/supervisor takeover,
and permits only one user-authorized, non-automatic material-defect return. Frozen
`production-2023-v4` was hashed and compared without mutation. See
[`archive/workplan/2026-08-14-production-control-flow-simplification.md`](archive/workplan/2026-08-14-production-control-flow-simplification.md).

### Task 6 — Run the integrated Netanyahu gate

Status: **rejected after fresh Terra/Sol comparison**

Objective: validate the chosen compact and simplified design from frozen acquisition
through approved answers, judging, audit, and publication.

Use a new experimental release and run ID. Promotion requires complete artifacts, passing
quality and score/order audits, a validated cited publication, no unresolved jobs, and the
cost targets in the detailed optimization plan. A cheaper result with a material quality
regression fails.

Result: the fresh release validated the frozen corpus/selection inputs and built all eight
question packages (80 questions), then stopped before model execution. The required
straight-through inventory totals 176 calls, above the below-150 promotion target. Dropping
an independent quality action would violate Task 5, so no ineligible subscription work was
started. See
[`archive/workplan/2026-08-14-integrated-netanyahu-gate-preflight.md`](archive/workplan/2026-08-14-integrated-netanyahu-gate-preflight.md).

Follow-up result: with user approval, the call ceiling was relaxed to 176 and production
actions were switched to Luna `xhigh`, retaining Sol `high` for independent quality. The
run stopped at 2B.3 because Luna omitted one of 28 mandatory evidence records. No retry,
repair, Sol review, judging, or publication followed. See
[`archive/workplan/2026-08-14-integrated-luna-xhigh-comparison.md`](archive/workplan/2026-08-14-integrated-luna-xhigh-comparison.md).

Terra continuation: the user accepted 176 calls and selected Sol for both judging stages.
Seventy-seven of 78 completed Terra writes passed. Question 1B.10 covered all 25 mandatory
records but requested one optional evidence ID outside its packet; two concurrent final
writes were interrupted when the strict gate stopped. Completion now requires explicit
authorization for deterministic removal of that optional request and a realized ceiling of
178 calls. No review or judging call has started.

Fresh general-pipeline result: optional reopen normalization was implemented prospectively,
with immutable raw output, a reconstructed accepted artifact, and a hash-bound ledger. A
shared executor-boundary coordinator now prevents post-failure reservations and launches in
both concurrent writing and review. After focused tests and clean independent review, the
completely fresh `netanyahu-2023-integrated-terra-sol-v2` run completed 80/80 Terra writes.
The separate Sol review rejected question 6B.1 after 14 authorized reviews: it preferred the
frozen approved answer because its claim-level citations and allocation-versus-execution
distinctions were easier to audit. The reviewer also identified three material evidence
records omitted by both answers. No repair, retry, judging, or judgment-review call followed.
The immutable result is
`research/runs/netanyahu-2023-integrated-terra-sol-v2/run-result.json`. Actual usage was
6,475,855 input tokens (843,264 cached), 216,148 output tokens, and 94 calls. Task 6 remains
rejected; Task 7 remains blocked.

No-model follow-up: an all-80-answer audit found that the version 6 prompt produced zero
inline evidence IDs in Terra prose, while 40 of 80 frozen predecessor answers contained
773 per-answer inline-ID occurrences. Terra still returned 1,241 complete structured
dispositions. This supports a general auditability change rather than a 6B.1 repair:
version 7 requires every exact priority ID inline beside its claim while retaining the
disposition ledger, and deterministic validation rejects missing or unknown inline IDs.
The blind gate is unchanged. See
[`archive/workplan/2026-08-14-terra-citation-audit.md`](archive/workplan/2026-08-14-terra-citation-audit.md).

Fresh version 7 test: `netanyahu-2023-integrated-terra-sol-v3` stopped after 22 Terra
calls when question 7B.2 used ordinary semicolon-delimited grouped citations. Twenty-one
answers passed. The validator interpreted each complete bracket group as one ID, reporting
valid group members as missing and the group string as unknown. No review or downstream
call started, and the run remains immutable. Version 8 prospectively defines both `[ID]`
and `[ID-1; ID-2]` and validates every group member independently. This is a general
citation grammar, not a 7B.2 artifact repair.

Fresh version 8 test: `netanyahu-2023-integrated-terra-sol-v4` stopped after 50 Terra
calls. Forty-nine answers passed; question 5B.8 returned a complete disposition for
`BATCH-0028-E005` but did not cite that required ID anywhere in its prose. The validator
correctly rejected it. No review or downstream call started. This is a genuine writer
contract miss, so no further parser change, retry, or automatic fresh attempt follows.
The next decision is whether inline claim-level citation completeness is the intended
product contract; if it is, Terra medium has not demonstrated sufficient reliability.

Fresh all-Sol test: `netanyahu-2023-integrated-sol-v5` completed 80/80 high-reasoning Sol
writes, then stopped after 22 independent Sol reviews. Reviews 1B.2 and 8B.2 preferred the
fresh answers overall but failed mandatory factual-support and citation-entailment gates.
The first contradicted its cited Lebanon source about avoidance of large-scale escalation;
the second misattributed Hanegbi's “central mission” characterization to Netanyahu and
omitted a material inherited home-front baseline. No judging or repair followed. Actual
usage was 7,135,489 input tokens (598,016 cached) and 554,813 output tokens over 102 calls.
This exceeded the stated 500,000-output-token run quota, revealing that current controls
preflight output allowance but do not enforce cumulative observed output across stages.
Task 6 remains rejected, and another model run requires a general cumulative-usage control
rather than a case-specific content fix.

General quota-control follow-up: a file-locked run-wide ledger now reserves calls, exact
serialized input estimates, and the selected model's full provider output maximum before
stage reservation or subprocess launch. Every model execution beneath an eligible integrated
preflight automatically derives the same config-hash-bound tracker from that manifest; a
mismatched explicit tracker is refused. The ledger spans question writing/review and both
judging paths, counts concurrent outstanding reservations, reconciles trusted completed
events, retains allowance when usage is unavailable, and releases capacity only for work
that never launched. Ledger identity and limits cannot change between processes, and a
single-call observed overage is persisted as a terminal failure. Focused concurrency,
identity, reconciliation, and launch-boundary tests pass; no model call was used for this
implementation. Because Sol can emit up to 128,000 tokens per call, the 500,000-token limit
admits at most three simultaneous Sol calls. The rejected v5 writer stage alone observed
496,838 output tokens, so a complete all-Sol run cannot reasonably fit that ceiling. A fresh
run remains blocked until a prospective release chooses a larger honest output limit or a
different approved production architecture.

Profiling and fresh-run follow-up: the partial `netanyahu-2023-integrated-luna-sol-v6`
attempt is immutable diagnostic evidence rather than a resumable run. Its seven completed
Luna-high writing calls reconcile exactly to the run ledger: 346,307 input tokens, 7,936
cached input tokens, 33,617 output tokens, and 18,736 reasoning-output tokens. The canonical
profiler now covers all four integrated stages, run reservations and budget breaches,
preflight limits, per-call timing and transport metadata, validation outcomes, PAYG and
Codex-credit equivalents, and explicit unknown subscription billing. Independent review
of the profiler and execution instrumentation is clean, the full suite passes, and fresh
release `netanyahu-2023-integrated-luna-sol-v7` has an eligible 176-call preflight with
40,000,000 input-token and 1,000,000 output-token hard ceilings. No v7 model call had been
made at this checkpoint.

The fresh v7 execution is also now frozen as a failed diagnostic. It launched 28 Luna-high
question-writing calls before stopping the stage: 28 calls completed and reconciled exactly
to 1,605,550 input tokens, 7,936 cached input tokens, 142,086 output tokens, and 68,407
reasoning-output tokens. All 28 calls have measured execution profiles totaling 2,721.462288
call-seconds; the PAYG equivalent is $0.490183-$0.570066 and the Codex-credit equivalent is
12.254618, while actual subscription billing remains unavailable. One completed answer
(`2B.3`) failed deterministic evidence coverage, and the prospective run-wide budget then
refused `3B.5` because outstanding 128,000-token provider-maximum reservations would exceed
the one-million-token output ceiling. Review and judging did not run. The ledger itself is
complete and token reconciliation passes; the integrated scientific gate is inconclusive.
The general scheduler correction is complete without weakening the ceiling or inventing a
smaller per-call allowance. When active provider-maximum reservations are the only obstacle,
new work now waits for reconciliation; permanently exhausted capacity still stops at once.
The shared failure coordinator is checked before and throughout the wait, a 30-minute bound
stops a genuinely stuck reservation, and reservation-file failures cancel their unlaunched
ledger capacity. Focused scheduler, coordinator, question-concurrency, profiling, preflight,
judge, and judgment-review tests pass, and independent re-review is clean. A fresh v8 may be
preflighted, but it must use new model outputs and must not resume or alter v7 or repair its
failed answer.

Fresh v8 is now frozen as a failed diagnostic after its question-writing phase. Its
zero-call preflight passed with all eight packages and eighty questions, and the repaired
scheduler behaved correctly: one call waited 22.026149 seconds for temporary capacity, then
continued; after the scientific failure, one reserved but unlaunched call was cancelled.
Thirty-one Luna-high calls completed and reconcile exactly to 1,759,628 input tokens, 15,872
cached input tokens, 152,135 output tokens, and 77,346 reasoning-output tokens. Measured
call time totals 2,927.983972 seconds; the PAYG equivalent is $0.531631-$0.618820 and the
Codex-credit equivalent is 13.290766, while actual subscription billing remains unavailable.
Thirty answers passed and `2B.3` failed. It cited `BATCH-0030-R02-E002` in prose but omitted
the required machine-readable evidence-disposition entry. v7 had failed on the same record,
although it had omitted both the prose citation and disposition. The approved predecessor's
metadata classifies this record as contrary/qualifying for `2B.3`, even though the evidence
record's own methodology mappings are `2B.5`, `6B.6`, and `8B.9`; its predecessor prose also
does not cite the record. Review and judging did not run. Before another model call, resolve
this general producer-contract inconsistency and make the strict response contract enforce
complete dispositions structurally rather than relying on an unbounded array instruction.
Do not resume or alter v8 and do not repair either failed output.

The general v8 contract repair is complete in two independently revertible versions. The
routing audit found 622 selection-added assignments across 76 of 80 questions, so deleting
cross-mapped records would discard reviewed evidence. Question packets now preserve ordered
source-routed and selection-added provenance separately; frozen historical base and expanded
packets upgrade only omitted fields after trusted reconstruction, while explicit clearing or
tampering fails. Separately, writer prompt version 10 and its dynamic strict JSON schema make
every required evidence ID a mandatory object key and reject extra or generated internal
keys. The transport response is deterministically converted to the existing ordered-list
accepted artifact, and trusted reload supports both the new keyed raw shape and historical
canonical raw files. Independent review is clean for both versions. No model calls were used
for these repairs; a completely fresh release is required to test whether the repeated
`2B.3` omission is eliminated in practice.

Fresh v9 is frozen as a failed diagnostic after independent question review. All eighty
Luna-high question-writing calls passed, including `2B.3` with all 28 required evidence
dispositions. This confirms that the dynamic exact-key response contract fixed the repeated
structural omission. Review then completed twelve calls before `3B.2` failed material
coverage: the preferred new answer was factual, cited, balanced, period-aware, and usable,
but did not adequately incorporate `BATCH-0031-E004`, `BATCH-0036-E023`, or
`BATCH-0009-E005`, which bear materially on personal superior responsibility and detention
oversight. The fail-stop prevented the other 68 reviews and all judging calls. All 92 calls
reconcile exactly to the run ledger: 6,193,807 input tokens, 90,624 cached input tokens,
478,369 output tokens, and 237,131 reasoning-output tokens. Summed call time is
9,069.232289 seconds; the PAYG equivalent is $1.796495-$2.101654 and the Codex-credit
equivalent is 44.912297, while actual subscription billing remains unavailable. Diagnose
the general evidence-selection or answer-coverage contract before a completely fresh v10;
do not resume, alter, or selectively repair v9.

The general v9 material-coverage return repair is complete without changing the reviewer or
the failed run. Diagnosis showed that the three omitted `3B.2` records were available only
in the compact omission index, which the writer is correctly forbidden to cite as exact
evidence. Integrated preflight can now consume the single explicit user-authorized return
defined by the control contract and promote only the failed review's named, currently
reopenable IDs into a completely fresh release. The authorization binds the predecessor
release and zero-return lineage, predecessor preflight, failed review manifest and output,
question packet, promoted IDs, and configuration by hash. All return inputs are read into
one stable snapshot, fresh output may not overlap the failed run, the applied IDs and hashes
are recorded, and a second descendant return is rejected. Forty-five broader boundary tests
pass, focused Ruff passes, and independent review is clean. No model call was used for the
repair. The next step is to create and zero-call preflight a fresh v10 configuration using
the authorized v9 `3B.2` recommendation; v9 remains immutable.

Fresh v10 now has an eligible zero-call preflight. It binds the single authorized return to
v9 and constructs all eight packages and eighty questions. `3B.2` contains eleven exact
required records rather than eight: `BATCH-0031-E004`, `BATCH-0036-E023`, and
`BATCH-0009-E005` are now full required evidence and are no longer compact-only candidates.
The preflight records return count one, the predecessor release and preflight hash, the
failed child-review and output hashes, and the three applied IDs. It inventories 176 planned
calls under the existing 250-call, 40,000,000-input-token, and 1,000,000-output-token hard
ceilings. No model call has been made in v10 at this checkpoint.

Fresh v10 is now frozen as a failed diagnostic after independent question review. All
eighty Luna-high writing calls passed, and the repaired `3B.2` answer substantively used all
three promoted records and passed independent review. Nine review calls completed before
the fail-stop settled: six passed and three failed. `2B.2` omitted four compact-only records
about administrative detention, settlement policy, and the 7 October response. `1B.2`
compressed the chronology by treating a 3 November statement as preceding the 28 October
ground-operation announcement. `4B.2` exposed a reviewer-contract inconsistency: every
quality dimension and the overall rationale said the answer passed, but the reviewer also
populated `material_regressions`, which deterministic code correctly treats as a failure.
The lineage permits no second material-defect return, and no judging call ran. All 89 calls
reconcile exactly to 6,075,388 input tokens, 320,000 cached input tokens, 442,823 output
tokens, and 201,024 reasoning-output tokens. Summed call time is 8,564.770910 seconds; the
PAYG equivalent is $1.688864-$1.976636 and the Codex-credit equivalent is 42.221630, while
actual subscription billing remains unavailable. Do not resume or alter v10. Diagnose the
reviewer output-contract inconsistency separately, but reject this returned Luna lineage
rather than attempting another evidence return.

The general reviewer-output inconsistency exposed by v10 `4B.2` is fixed independently of
the failed run. Prompt version 11 now tells the reviewer that `material_regressions` and
`unsupported_claims` are blocking fields and requires corresponding failed dimensions;
non-blocking corrections belong in `material_improvements`. Local cross-field validation
rejects contradictory fresh JSON. Immutable version-10 reviews remain trusted-loadable via
a byte-identical frozen v10 prompt configuration and legacy parsing limited to that saved
version; raw output, prompt, configuration, schema, and full-manifest hashes are still
reconstructed without rewriting. Thirty focused and adjacent tests pass, Ruff passes, and
independent review is clean. No model call was used. This repair improves future review
integrity but cannot reopen the spent v10 lineage or cure its separate `1B.2` and `2B.2`
content failures.

A review-only Luna-high experiment then ran two independent version-11 passes over the
same frozen 80 v10 answers. No other pipeline stage ran. The passes agreed on 67 of 80
outcomes, but both missed the known `1B.2` chronology error; `2B.2` failed only in the
second pass. Each pass also produced three unavailable evidence IDs, all rejected by the
validator. Combined use was 160 Luna-high calls, 11,555,462 input tokens, 103,168 cached
input tokens, 737,315 output tokens, and 642,614 reasoning-output tokens. The duplicate
two-pass design is rejected as a production gate. The next bounded experiment should make
pass two a focused Luna verifier of chronology, priority-evidence disposition, allowed IDs,
and pass-one defect claims. Full results are in
[`reviews/2026-08-17-luna-high-question-review-two-pass.md`](reviews/2026-08-17-luna-high-question-review-two-pass.md).

A subsequent ten-case diagnostic replaced the duplicate second review with a focused
Luna-high verifier. It caught both known defects (`1B.2`, `2B.2`), confirmed the repeated
`1B.1`, `2B.4`, `6B.9`, and `7B.6` failures, preserved the `4B.2` pass, and prevented the
`8B.9` invalid-ID behavior through a schema allowlist. It passed disputed `2B.1` and failed
previously repaired `3B.2` on newly identified omissions, so it is not yet approved for an
80-question gate. All ten calls reconciled exactly to 768,878 input and 76,785 output
tokens, including 64,168 reasoning tokens. Full results are in
[`reviews/2026-08-17-focused-luna-question-verifier.md`](reviews/2026-08-17-focused-luna-question-verifier.md).

### Task 7 — Run five-ruler confirmation and decide production promotion

Status: **blocked by a passing Task 6**

Run the same five-ruler cohort as the approved reference with fresh model outputs and
verified immutable source reuse. Require complete per-ruler and aggregate quality, cost,
audit, attribution, and publication gates. Promote through a new release; never mutate
`production-2023-v4`.

## Parallel and deferred work

- Static study-site development is a separate parallel track. Cost-optimization sessions
  must not edit `research_study_site_commands.py`, `study_site_*`, or
  `tests/research/test_study_site.py` unless that scope is explicitly transferred.
- Broader source acquisition, score recalibration, and unrelated visualization work remain
  outside the current optimization sequence. Their status belongs in their dedicated
  plans and registries rather than here.

## Session start checklist

1. Read `AGENTS.md`, this file, and the named task's referenced design documents.
2. Run `git status` and preserve unrelated or parallel changes.
3. Validate the predecessor task's persisted artifact and completion gate.
4. Work on only one numbered task.
5. Before a model call, state the model, execution surface, number of calls, and estimated
   quota. API-key calls require explicit user approval.
6. A failed run is immutable diagnostic evidence. Fix only the general pipeline contract,
   verify it independently, and evaluate the fix in a completely fresh release/run; never
   patch or resume the failed test into a passing result.

## Session completion handoff

Before ending a task session, update this document with:

```text
Task:
Outcome: complete / rejected / blocked
Decision and plain-language reason:
Artifacts:
Model calls and execution surface:
Input / cached / output tokens:
Tests and review:
Known limits:
Next task:
```

Move the completed task's detailed narrative to a dated file under
`docs/archive/workplan/` or an appropriate `docs/reviews/` report. Keep only its one-line
decision, lasting constraints, and next dependency here.

## Current handoff

Task: focused Luna-high question-verifier diagnostic

Outcome: promising but not yet approved for an 80-question gate

Decision and plain-language reason: the focused verifier caught both known defects,
confirmed repeated failures, and eliminated invalid evidence IDs. It also failed repaired
`3B.2` and passed disputed `2B.1`; those findings must be checked against the exact evidence
before deciding whether the verifier is accurately stricter or over-sensitive.

Artifacts: `research/runs/netanyahu-2023-luna-focused-verifier-v1/`,
`research/runs/netanyahu-2023-luna-focused-verifier-v1-profile-v2/`, and
`docs/reviews/2026-08-17-focused-luna-question-verifier.md`.

Model calls and execution surface: 10 Luna-high Codex-subscription verifier calls completed.
No writing, judging, scoring, audit, or publication call ran. No API key was used.

Input / cached / output tokens: 768,878 / 0 / 76,785; 64,168 reasoning-output tokens and
845,663 total tokens. Event and ledger accounting agree exactly.

Tests and review: all 10 calls completed, strictified, and trusted-reloaded; 8 failed and 2
passed. The verifier code's 26-test gate and independent review are clean. The profiler
integration's 11-test gate and independent review are also clean.

Known limits: local evidence-level adjudication confirmed the focused verifier's `3B.2`
fail and `2B.1` pass. A fresh repeatability run matched nine of ten final gates: all eight
first-run failures failed again, `2B.1` passed again, and `4B.2` changed from pass to fail.
The `4B.2` failure is correct because its answer explicitly records a material National
Guard reopen request; the first focused run failed to rediscover that structured signal.
Detailed omission lists varied substantially, including one versus ten additional gaps for
`3B.2`, and chronology changed for `7B.6` and `8B.9`. The ten cases were selected
diagnostically and do not estimate the pass rate of all 80 questions. Later stages remain
unrun.

The focused verifier v2 update now makes accepted writer reopen requests a separate
deterministic blocking category, removes them from Luna's candidate scan, and derives the
final gate in code rather than accepting a model gate. Frozen v1 prompt and schema
semantics trusted-reloaded all 20 earlier focused artifacts exactly. The 33-test focused
and adjacent gate, Ruff, strict manifest-version tamper regressions, and independent review
are clean.

The fresh v2 control run completed `3B.2` and `4B.2` successfully at the transport and
trusted-reload levels. Both failed deterministically on their accepted reopen requests;
neither reopen ID reappeared in Luna's new-omission field. The two calls used 129,496 input
and 18,051 output tokens (147,547 total), 1.189010 Codex-equivalent credits, and 333.511867
combined seconds, with exact ledger reconciliation.

A zero-call inventory found accepted reopen requests in 56 of 80 frozen answers, covering
72 unresolved IDs. Those 56 are guaranteed v2 failures, so an 80-call run is not justified.
The next optional model diagnostic is bounded to the 24 answers without reopen requests;
the 56 deterministic failures require an upstream selection/completion decision instead.
Do not treat Luna's variable newly discovered candidate-omission list as authoritative
without evidence-level adjudication. Task 7 remains blocked.

The general writing-to-review repair is now implemented: a trusted full-scope preflight
collects accepted writer reopen requests before any independent review worker starts. A
nonempty set writes a hash-bound `reopen-stop.json` containing every affected question,
answer hash, and evidence ID, records zero launched review calls, and stops the phase. The
single-chapter entry point applies the same barrier, and trusted review reload rejects a
review built over unresolved writer requests. No model call was used for this repair.

The follow-on zero-call classification is complete. All 72 accepted requests in 56 frozen
v10 answers name existing dossier records routed to the exact requesting question but left
out of required exact evidence; 37 are among the first 15 routed candidates and 47 among
the first 20. No request requires new research. The artifacts establish a general
selection/completion defect, but do not independently prove that all 72 requests are
material. The next task is a prospective, hash-bound evidence-completion decision that
dispositions each request before constructing a completely fresh release. See
[`reviews/2026-08-17-v10-reopen-request-classification.md`](reviews/2026-08-17-v10-reopen-request-classification.md).

The general evidence-completion contract is implemented and locally verified. The user
explicitly authorized all 72 accepted v10 requests for promotion. The hash-bound decision
ledger covers 56 questions in all eight chapters, preserves accepted-output order, and
promotes every item to required exact evidence; none is retained as compact-only evidence.

The completely fresh `netanyahu-2023-integrated-luna-sol-v11` zero-call preflight is
eligible. It verified the frozen source release and all authorized hashes, built eight
packages containing 80 questions, applied 72 completion items across 56 questions, and
executed zero model calls. The prospective full pipeline contains 176 calls within its
250-call ceiling and has no material-defect return. The next phase is limited to the 80
Luna-high writing calls. Their complete prompts are estimated at 4,160,207 input tokens in
total (mean 52,003; maximum 156,985 for `6B.10`), with no request above the configured
300,000-token ceiling. Review, judging, audit, and publication must not start during that
bounded writing phase.

The approved v11 writing launch is frozen as an incomplete diagnostic after its interactive
execution owner disappeared at a session boundary. Sixty-two answers completed and passed
deterministic validation; five launched calls were interrupted with unresolved reservations
(`2B.7`, `5B.10`, `6B.9`, `7B.10`, and `8B.1`), and thirteen calls never launched. No model
or validation failure caused the stop, but only three complete chapter manifests exist, so
v11 cannot pass and must not be resumed or repaired. The completed calls recorded 4,261,555
input tokens, 285,440 cached input tokens, 321,726 output tokens, and 134,088 reasoning-output
tokens. A fresh v12 release must use a detached durable execution owner and a new bounded
approval before repeating question writing; later stages remain stopped.
