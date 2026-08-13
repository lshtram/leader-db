# Model cost optimization implementation plan

## Purpose

This plan reduces model input, output, and repeated-call cost in the ruler-quality
pipeline while preserving the current evidence, independent-review, audit, and
publication controls. It addresses the profile of
`2023-five-ruler-flow-test-v2`, where five rulers required 3,778 completed model
calls, 585.33 million input tokens, and 11.70 million output tokens. Chapter
analysis and chapter-quality work accounted for 2,821 calls, 386.39 million input
tokens, and 6.95 million output tokens. Their reported cache rates were only
3.8–4.8 percent.

The work proceeds as a sequence of small platform changes. Every step ends with a
fresh one-ruler test. A step advances only when its functional, evidence-quality,
and cost gates pass. Failed experiments remain immutable diagnostics and do not
change the production release.

Quality is the controlling objective. Cost and cache improvements are evaluated only
after the experimental output passes its quality gate. A cheaper result with weaker
evidence coverage, factual accuracy, balance, attribution, reasoning, confidence
calibration, or judgeability fails the experiment. The current approved output is a
minimum comparison baseline, not a quality ceiling: an experimental result should
preserve it or improve on it when the complete evidence supports an improvement.

## Final targets

The optimized path should meet these targets on a representative ruler before a
larger cohort is attempted:

| Measure | Five-ruler v4 average | Final one-ruler target |
|---|---:|---:|
| Total calls per ruler | 756 | Below 150 |
| Calls per final question | 7.1 | 1–2 |
| Input tokens per ruler | 117.07M | Below 40M |
| Output tokens per ruler | 2.34M | Below 500K |
| Chapter-analysis cache rate | 4.8% | At least 50% |
| Chapter-review cache rate | 3.8% | At least 50% |
| Overall cache rate | 24.3% | Above 60% |
| Final chapter answers | 80 | Exactly 80 |
| Final chapter scores | 8 | Exactly 8 after comparative validation |

Token targets are engineering promotion gates, not reasons to omit relevant
evidence. If an input is genuinely large, deterministic transport splitting and
complete manifests remain mandatory.

## Fixed test case and baselines

Use Benjamin Netanyahu, Israel, 2023 as the recurring gate case.

The primary reference is the completed v4 package in:

```text
research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/
```

The earlier deep-corpus comparison is:

```text
research/runs/netanyahu-2023-pilot-frozen-v1/jobs/565/corpus-continuation/
```

The current v4 selected chapter analyses, independent reviews, review bindings,
corpus judge package, and approved ruler package are immutable test inputs. Each
optimization experiment must write to a new run directory. Suggested IDs are
provided below. Do not edit, relink, or replace either reference run.

Before Step 1, freeze a machine-readable baseline containing:

- every selected chapter answer and cited evidence ID;
- every review finding and quality rating;
- evidence and mapping counts by chapter and question;
- evidence source-domain and publisher diversity;
- answer length by question;
- all completed-call token fields by phase;
- prompt byte count, request estimate, elapsed time, and retry count;
- the eight accepted scores, rationales, ranges, and confidence values;
- all artifact paths and SHA-256 hashes.

## Controls that remain unchanged

Every step must preserve the following controls:

1. The complete acquired corpus and verified evidence ledger remain available.
2. Evidence IDs, source IDs, hashes, unit ranges, locators, and exact passages remain
   stable and auditable.
3. Each final ruler package contains chapters 1B–8B and exactly ten answers per
   chapter.
4. Research, synthesis, independent evidence review, formatting, judging, final
   score review, score/order audit, and publication remain distinct contracts.
5. Independent reviewers receive no discovery authority.
6. A repair may change only the questions and fields named in its defect manifest.
7. Unchanged answers are copied deterministically from their approved predecessor;
   a model does not rewrite them.
8. Every model request is preflighted using the complete serialized request and
   response schema with the configured safety margin.
9. Missing lenses reduce confidence when appropriate; token targets never convert
   missing evidence into favorable evidence.
10. Client scores remain validation references and never enter research or judging
    prompts.

## Common one-ruler test protocol

Run this protocol after every implementation step.

Every step, including infrastructure and transport steps that do not intend to change
research content, must produce a quality result. For a no-model infrastructure step,
that result proves that the same inputs, outputs, counts, hashes, and selected artifacts
are measured or transported unchanged. For a model-bearing step, it requires the full
blind substantive evaluation below.

### Test inputs

- Ruler: Benjamin Netanyahu
- ISO3: `ISR`
- Year: `2023`
- Evidence input: hash-bound copy/reference of the approved v4 ISR corpus package
- Selected chapters: all eight unless a step explicitly begins with a two-chapter
  smoke test
- Required first smoke chapters: `4B` and `8B`, followed by all eight chapters in
  the same step
- Production status: diagnostic only

### Test output

Each run must emit a profile manifest with:

```text
schema and implementation version
source artifact hashes
resolved prompt-template hash
request-envelope hash
call count by stage and chapter
input, cached-input, uncached-input, output, and reasoning-output tokens
cache rate by stage and chapter
elapsed time and attempt count
preflight characters and estimated tokens
answer and citation counts
changed and unchanged question IDs
review defects and repair dispositions
quality comparison with the frozen baseline
```

### Functional gate

- Every expected artifact validates against its current schema.
- Exactly 80 question answers are present after the all-chapter test.
- Every cited evidence ID resolves within the bound corpus.
- Every unchanged answer is byte-identical to its selected predecessor unless a
  versioned deterministic normalizer records the exact change.
- No source, evidence unit, reviewer requirement, or correction disposition is lost.
- The request preflight passes before every model invocation.

### Quality gate

Compare the experimental answers blindly against the selected v4 answers. The
reviewer receives answer A/B in randomized order and the same hash-bound evidence.
Use a separate high-reasoning reviewer that did not produce either answer. The reviewer
must inspect the complete approved evidence relevant to the chapter, including material
evidence omitted by both answers, rather than treating the existing answer as ground
truth. Persist the randomization key, review prompt, model/profile, response, usage,
evidence hashes, and deterministic deblinding record.

The reviewer evaluates every question on:

- factual support and citation entailment;
- coverage of materially distinct favorable, adverse, and qualifying evidence;
- treatment of contrary evidence and source disagreement;
- ruler attribution, authority, inherited baseline, external constraints, and shocks;
- period fit and source limitations;
- allegations versus findings and official claims versus independent checks;
- clarity, internal consistency, and usefulness to the chapter judge;
- unsupported claims, overstatement, repetition, and irrelevant detail.

Promotion requires all of the following:

- no material factual regression;
- no material loss of contrary evidence, attribution, inherited baseline, external
  constraints, or source limitations;
- all original decisive citations retained or replaced by an explicitly reviewed,
  equally supportive citation;
- no reduction in judgeability for any chapter;
- no new unsupported claims;
- no score movement greater than 0.5 in the later frozen-cohort judge test unless an
  independent reviewer finds the new result more faithful to the rubric;
- the experimental output is rated at least equal overall to the baseline for every
  chapter; a material loss in one chapter cannot be offset by gains in another;
- any reviewer preference for the experimental output cites concrete evidence or a
  specific reasoning improvement rather than brevity or lower cost;
- any inconclusive or split quality result is treated as a failed gate until a fresh
  independent adjudication resolves it.

For every model-bearing step, also run deterministic checks for citation validity,
evidence-ID coverage, answer completeness, unsupported-ID introduction, and unchanged
field preservation. Then run an adversarial evidence audit on at least the two smoke
chapters, asking the reviewer to identify the strongest material evidence or limitation
missed by the experimental output. The all-eight-chapter test receives the same audit
before the step passes.

Record the quality decision separately from the cost decision:

```text
quality_gate: pass | fail | inconclusive
baseline_wins: <count by question and chapter>
experimental_wins: <count by question and chapter>
ties: <count by question and chapter>
material_regressions: <typed list>
material_improvements: <typed list>
missed_material_evidence: <typed list>
unsupported_claims: <typed list>
judgeability_regressions: <typed list>
```

Only `quality_gate: pass` permits cost evaluation and progression to the next step.

### Required quality proof by step

The common quality gate applies in full. The following table names the additional
step-specific proof so an implementation session cannot treat a successful execution or
lower token count as sufficient.

| Step | Required quality proof |
|---|---|
| 1. Profiling | Counts, hashes, selected/superseded classification, and token totals reconcile exactly; the profiler changes no scientific artifact. |
| 2. Request envelope | Old and new envelopes contain semantically identical instructions, evidence, metadata, and schemas; repeated diagnostic outputs pass blind equivalence review. |
| 3. Chapter synthesis | All 80 answers pass blind A/B review and adversarial omitted-evidence audit against the approved baseline. |
| 4. Structured review | The new reviewer finds every material baseline defect plus any newly supported defect; precision is checked so harmless editorial preferences do not trigger repairs. |
| 5. Delta repair | Repairs resolve the named defects, preserve unaffected answers exactly, and introduce no unsupported claim or citation. |
| 6. Scoped verification | A full independent review of the same package finds no material issue missed by scoped verification. |
| 7. Compact ledgers | Raw-document audit shows equal or better factual support, locator fidelity, evidence yield, contrary-evidence yield, and source diversity. |
| 8. Budgets | Normal and constrained executions produce identical accepted scientific outputs; a budget stop leaves no partial result eligible for approval. |
| 9. One-ruler integration | Full 80-lens blind review, adversarial evidence audit, frozen-cohort judgment comparison, score review, and publication audit all pass. |
| 10. Five-ruler confirmation | Every ruler and chapter passes separately; cohort ordering, confidence calibration, and information-environment bias are independently audited. |

### Cost gate

Each step has its own threshold. Report both total tokens and uncached tokens. A step
does not pass merely because its total input is lower if its uncached input or output
increases materially. Meeting the cost target cannot compensate for a failed or
inconclusive quality gate. If the quality-preserving implementation costs more than the
target, retain the quality-preserving result as the candidate and continue optimizing
in a later step rather than weakening it.

## Step 1 — Add a canonical profiling and comparison harness

### Platform change

Create a reusable profiler that reads trusted event logs and manifests instead of
using one-off scripts. It should classify calls by production stage, distinguish
selected work from superseded and failed work, and compare two runs using identical
definitions.

Required outputs:

- JSON profile manifest;
- CSV call ledger;
- Markdown comparison report;
- per-stage and per-chapter totals;
- cache-rate distribution, including calls with at least 10%, 50%, and 90% cached
  input;
- output-size distribution and largest-call list;
- selected versus superseded token totals;
- corpus words, extracted characters, estimated source tokens, source counts,
  evidence counts, mappings, and evidence-question links.

Add CLI commands for profiling one run and comparing two profiles. Derive stage
classification from versioned workflow metadata or explicit artifact types. Do not
infer scientific stages solely from directory-name substrings in production code.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step01-profile-v1
```

Profile both Netanyahu reference packages and reconcile totals against their existing
usage reports. No model call is required.

### Acceptance gate

- Token totals reconcile exactly with completed event records.
- Corpus/evidence counts reconcile exactly with manifests.
- Re-running the profiler produces byte-identical normalized outputs apart from an
  explicitly excluded generation timestamp.
- Tests cover duplicate event discovery, malformed lines, missing usage, superseded
  attempts, and shared-stage allocation.

## Step 2 — Version a cache-oriented request envelope

### Platform change

Introduce one request builder used by chapter synthesis, chapter review, and repair.
Serialize request components in this order:

1. stable system and role instructions;
2. stable methodology version and response contract;
3. stable hash-bound chapter evidence package;
4. variable task identity and selected question IDs;
5. variable predecessor answer or defect manifest;
6. response schema reference.

Persist the byte length and SHA-256 of each component. The manifest must expose the
longest identical prefix between consecutive calls. Keep model-facing instructions in
one versioned configuration source rather than Python strings or test copies.

The evidence package must use canonical ordering for evidence, mappings, questions,
and object keys. Volatile values such as timestamps, attempt UUIDs, absolute paths,
and output directories belong after the stable prefix or outside the model request.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step02-envelope-v1
```

Run two no-write diagnostic calls for chapters 4B and 8B, then repeat them with only
the task suffix changed. Compare reported caching and verify all protected source
hashes remain unchanged.

### Acceptance gate

- At least 90% of immutable request bytes occur in the identical prefix for repeated
  calls over the same chapter package.
- The provider reports at least 50% cached input on the repeated diagnostic call, or
  the report documents that the provider surface does not expose/retain prefix cache.
- Request content is semantically equivalent to the current contract.
- No model output enters a production artifact.

## Step 3 — Replace ten question calls with one chapter synthesis call

### Platform change

Implement one strict-JSON synthesis call per ruler/chapter. It returns exactly ten
question answers, citation lists, limitations, and reopening requests. The model sees
the full approved compact ledger for the ruler but the request builder presents a
chapter-indexed evidence view and retains access to challenged cross-chapter routes.

If the complete chapter request exceeds transport limits, split by deterministic,
non-overlapping evidence shards. Shard outputs may identify evidence and candidate
findings; one bounded synthesis call must assemble the ten answers. Persist a coverage
manifest proving every evidence unit was represented or explicitly dispositioned.

Retain the old per-question path behind a diagnostic rollback flag during this step.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step03-chapter-synthesis-v1
```

Run 4B and 8B first. If both pass, run all eight chapters from the same frozen corpus.

### Acceptance gate

- Eight synthesis calls in the normal all-chapter case, plus only transport shards
  proved necessary by preflight.
- Exactly 80 answers and valid evidence references.
- Blind quality comparison passes.
- Chapter synthesis uses no more than 20 calls and 250K output tokens for the ruler.
- Input is at least 50% lower than the current selected-plus-superseded chapter-answer
  work for the same ruler.

## Step 4 — Make independent review chapter-scoped and defect-structured

### Platform change

Use one independent review call per chapter. The response contains:

- a pass/fail decision for each of ten questions;
- material defect IDs;
- affected question IDs and evidence IDs;
- defect type and severity;
- exact fields requiring change;
- whether discovery is required or existing evidence is sufficient;
- chapter-wide requirements, each routed to affected questions;
- a final safe-for-judge decision.

The reviewer does not rewrite answers. It diagnoses them. Deterministic code converts
the review to an immutable repair manifest.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step04-structured-review-v1
```

Review the Step 3 outputs, beginning with 4B and 8B and then all chapters.

### Acceptance gate

- Eight normal review calls.
- Every material issue found by the existing selected reviews is retained or
  explicitly dispositioned as no longer applicable.
- No answer prose is generated by the reviewer.
- Review output stays below 80K tokens for all eight chapters.
- Review cache rate is at least 50% after the first chapter when the provider supports
  the stable-prefix cache.

## Step 5 — Add deterministic delta repair and merge

### Platform change

Repair only failed questions. A repair request contains:

- the stable evidence package;
- the immutable defect manifest;
- only the affected predecessor answers;
- exact permitted fields;
- all reviewer-bound evidence routes.

The response returns patches keyed by question ID. Deterministic code verifies allowed
fields, resolves evidence IDs, and merges patches into the predecessor chapter. It
copies every unaffected answer byte-for-byte. A repair cannot delete a reviewer-bound
route or silently change a sibling answer.

Allow one normal repair round. A second round requires a remaining material defect and
an explicit persisted reason. A third round is a terminal manual-review state for this
experiment rather than another automatic rewrite.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step05-delta-repair-v1
```

Inject controlled synthetic defects into copies of one 4B answer and one 8B answer,
then run the real reviewer and repair flow. Follow with an all-chapter test using only
naturally identified defects.

### Acceptance gate

- Synthetic defects are detected and repaired.
- Unaffected answers remain byte-identical.
- Every patch has a complete before/after ledger and source hashes.
- No more than two repair calls per affected chapter.
- Repair output is below 100K tokens for the full ruler.
- Blind quality comparison passes after deterministic merge.

## Step 6 — Review only changed questions after repair

### Platform change

Replace full-chapter re-review after a patch with a scoped verification call. The
verifier receives the original chapter review, patch ledger, changed answers, directly
relevant evidence, and chapter-wide requirements. Deterministic code carries forward
the earlier pass decisions for unchanged questions.

A full-chapter re-review occurs only when the patch changes chapter-wide framing,
contrary-evidence interpretation, ruler attribution, or the evidence environment. The
reason must be recorded as a typed escalation.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step06-scoped-verification-v1
```

Run the Step 5 repaired package through scoped verification and compare it with a full
review of the same result.

### Acceptance gate

- Scoped and full review agree on material pass/fail findings.
- At least 80% of unchanged questions avoid another model review call.
- Verification plus repair uses fewer than 25 calls for the ruler.
- No material defect found by the full comparison review is absent from the scoped
  result.

## Step 7 — Compact research and reading outputs at their source

### Platform change

Reduce output volume before chapter synthesis:

- readers emit compact atomic findings, locators, dispositions, and reopen requests;
- code copies exact source passages after the model selects unit ranges;
- research continuation requests list only unresolved gaps and a bounded relevant
  source index;
- unchanged evidence is referenced by stable ID rather than reproduced in narrative;
- models do not reproduce source catalogues, full prior notebooks, or exact excerpts
  already persisted by code;
- narrative handoffs become generated views of structured ledgers, not primary model
  outputs.

Keep complete corpus coverage. This step changes representation, not acquisition or
reading breadth.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step07-compact-ledger-v1
```

Run the reader and research continuation against a deterministic representative slice
containing short HTML, a long report, a PDF-derived extract, an official source, an
independent source, favorable evidence, adverse evidence, and a no-material-fact
document. Then run the complete frozen Netanyahu reading plan if the slice passes.

### Acceptance gate

- Every planned document receives exactly one terminal disposition.
- Evidence yield, locator fidelity, contrary-evidence yield, and source diversity are
  no worse than the baseline under blind audit.
- Reader/research output falls by at least 50%.
- No exact excerpt is model-authored when code can copy it from the frozen source.
- Complete-plan reconciliation passes.

## Step 8 — Add stage budgets and stop rules

### Platform change

Add versioned engineering budgets for calls, input, uncached input, output, and repair
rounds by stage. A budget is an alert and promotion gate, not permission to truncate
evidence. When a stage approaches its budget, the supervisor must:

1. report the dominant request components;
2. reuse a trusted checkpoint when hashes match;
3. switch to deterministic splitting or delta repair when applicable;
4. stop with an explicit budget-exceeded diagnostic if safe completion cannot fit.

Do not retry an unchanged request after an over-limit or deterministic validation
failure. Record cache-prefix length and cache rate as first-class run metrics.

### One-ruler test

Suggested run ID:

```text
netanyahu-2023-cost-opt-step08-budgets-v1
```

Exercise normal completion, a deliberately low diagnostic budget, a safe checkpoint
resume, and an oversized transport split.

### Acceptance gate

- Normal execution completes under the configured target budget.
- Low-budget execution stops before an unnecessary model call and preserves a resumable
  checkpoint.
- Resume neither duplicates completed calls nor republishes stale work.
- Budget reporting identifies the exact stage and request component responsible.

## Step 9 — Run the integrated one-ruler gate

### Platform change

Create a new experimental pipeline release that selects the optimized implementations
and contracts. Do not modify `leaders-db-production-pipeline-2023-v4`. Suggested
identity:

```text
leaders-db-cost-optimized-pipeline-2023-v1
```

Suggested test run ID:

```text
netanyahu-2023-cost-optimized-e2e-v1
```

Run the complete flow from the frozen candidate catalogue and acquired corpus through
reading, evidence packaging, chapter synthesis, review, delta repair, approval,
comparative-compatible projection, judging, score review, score/order audit, and HTML
publication. For the one-ruler judge test, use immutable score/rationale anchors for
the unchanged four-ruler cohort exactly as allowed by REQ-LLM-029, then run the complete
five-ruler score/order audit before any production promotion.

### Acceptance gate

- Fewer than 150 completed model calls for the Netanyahu work.
- Fewer than 40M total input tokens and 500K output tokens.
- At least 60% overall cached input and at least 50% for analysis and review.
- Exactly 80 valid answers, eight judgments, one reviewed judgment package, a passing
  score/order audit, and a validated cited HTML publication.
- The blind quality gate passes for all eight chapters.
- No score changes by more than 0.5 without an independent finding that the optimized
  result is more rubric-faithful.
- No required job remains pending, running, retryable, failed, or quarantined.

## Step 10 — Five-ruler confirmation and production decision

After the one-ruler gate passes, run a fresh five-ruler confirmation using the same
five rulers as `2023-five-ruler-flow-test-v2`. Use a new run ID and do not reuse model
outputs from the prior run. Immutable source downloads may be reused only through
verified content hashes and explicit acquisition-cache provenance.

Suggested run ID:

```text
2023-five-ruler-cost-optimized-confirmation-v1
```

Promotion requires:

- all per-ruler and aggregate cost targets;
- consistent evidence quality across open and closed information environments;
- no material chapter-order instability unexplained by corrected evidence handling;
- complete attribution and publication;
- full default tests, relevant slow tests, lint, self-review, and independent code
  review;
- a new production release rather than mutation of v4;
- updates to `docs/workplan.md`, `docs/architecture/overview.md`, and
  `docs/requirements/core.md` in the same reviewed change.

## Suggested implementation sequence and commits

Use one conventional commit per accepted step. Do not stack an unreviewed step on top
of the next one.

| Step | Suggested commit |
|---|---|
| 1 | `feat: add canonical research cost profiler` |
| 2 | `feat: add cache-oriented model request envelope` |
| 3 | `feat: synthesize ruler answers by chapter` |
| 4 | `feat: add structured chapter review defects` |
| 5 | `feat: add deterministic question delta repair` |
| 6 | `feat: verify only repaired chapter questions` |
| 7 | `refactor: emit compact structured research ledgers` |
| 8 | `feat: enforce model stage budgets and stop rules` |
| 9 | `test: validate optimized one-ruler production flow` |
| 10 | `feat: promote cost-optimized production pipeline` |

Commits are made only when explicitly requested by the user. The table defines logical
change boundaries.

## Prompt for the implementation session

Start the separate implementation session with this prompt:

```text
Work in /home/liorshtram/projects/leaders-db.

Read AGENTS.md first, then read:
- docs/process/model-cost-optimization-implementation-plan.md
- docs/workplan.md
- docs/requirements/top-level-requirements.md
- docs/methodology/ranking-evaluation-criteria.md
- docs/methodology/cited-evaluation-calibration.md
- docs/architecture/overview.md
- docs/requirements/core.md
- docs/process/coding-guidelines.md
- docs/process/operational-hygiene.md

Implement only Step 1 of the optimization plan. Do not begin Step 2 in the same
change. Preserve all existing user changes and immutable research artifacts.

Follow pragmatic implementation mode. Inspect the relevant code before editing,
make minimal configuration-driven changes, add focused tests, run the affected tests
and Ruff, self-review against the D2 checklist, and fix every finding before reporting.

Run the specified fresh Netanyahu one-ruler gate for Step 1 and produce its required
profile artifacts. Treat the existing v4 and frozen Netanyahu runs as read-only
references. Quality is the controlling objective: perform the common quality gate and
the step-specific quality proof before evaluating cost. A cheaper result with any
material quality regression fails. Report the functional, quality, and cost gates
separately. If a gate fails or is inconclusive, diagnose it and stop before Step 2. Do
not commit unless I explicitly ask.
```

For later sessions, replace `Step 1` with the next accepted step and add:

```text
Read the prior step's profile manifest and acceptance report. Confirm every prior gate
still passes before editing. Implement only Step N, run its named fresh one-ruler test,
and compare it with both the frozen baseline and the immediately preceding accepted
step. Run the complete common quality gate and Step N's specific quality proof before
assessing savings. Treat an inconclusive quality result as failure. Do not begin Step
N+1.
```

## Per-step handoff template

Every implementation session should finish with this compact handoff:

```text
Step implemented:
Files changed:
Contracts/config versions added:
Test run ID:
Functional gate: PASS/FAIL
Quality gate: PASS/FAIL/INCONCLUSIVE
Blind comparison: baseline wins / experimental wins / ties
Material regressions and improvements:
Adversarial missed-evidence audit:
Unsupported claims or citations:
Judgeability and score-stability result:
Cost gate: PASS/FAIL
Calls:
Input / cached / uncached / output / reasoning tokens:
Cache rate by affected stage:
Answer/evidence/mapping changes:
Superseded or failed work retained:
Tests and lint:
Known limits:
Recommended next action: advance / repair this step / rollback
```

The next step begins only after this handoff and its persisted artifacts have been
reviewed.
