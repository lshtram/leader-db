# Leaders Database — Canonical Workplan

## 1. Authority and purpose

This is the only document that selects the next project task or defines execution order.
Point an implementation session to this file; the active task contract below contains the
scope, inputs, constraints, deliverables, verification, completion gate, and archival handoff
needed to do the work without consulting another plan for sequencing.

Other planning documents are design/reference records only. They may explain a subsystem,
but they do not create active work, change status, reorder tasks, or authorize model calls.
Normative product and scientific requirements remain authoritative in their own domains:

- [`requirements/top-level-requirements.md`](requirements/top-level-requirements.md)
- [`requirements/core.md`](requirements/core.md)
- [`architecture/overview.md`](architecture/overview.md)
- [`methodology/ranking-evaluation-criteria.md`](methodology/ranking-evaluation-criteria.md)
- [`methodology/cited-evaluation-calibration.md`](methodology/cited-evaluation-calibration.md)
- [`process/coding-guidelines.md`](process/coding-guidelines.md)
- [`process/operational-hygiene.md`](process/operational-hygiene.md)

If one of those documents appears to imply a different implementation order, record the
conflict here and resolve it before execution. Do not silently create an extra phase.

## 2. Operating rules

### One queue and one active task

- Phases and tasks execute in the order listed in §5.
- At most one task has status `ACTIVE`.
- A task begins only when every dependency is complete and its start gate passes.
- Do not begin the next task in the same session unless the user explicitly requests it.
- No implementation session may end with an unnamed “next step.”

Use only `ACTIVE`, `READY`, `BLOCKED`, `DEFERRED`, `COMPLETE`, and `REJECTED`.

### No-surprise-task rule

Classify newly discovered work before continuing:

1. A general defect inside the active contract is fixed within that task.
2. A material expansion is added, with dependencies and an acceptance gate, to an existing
   phase; obtain user approval if it changes scope.
3. An optional improvement is recorded as non-blocking in the task archive.
4. A historical observation goes to the archive, not the active queue.

### Model-run rule

Every model-bearing task starts with a zero-call preflight that measures complete serialized
requests, validates hashes and artifacts, records exact inventory and hard limits, and proves
the output directory is unused. A user instruction to execute a named pipeline or experiment
end to end authorizes all preflighted Codex/subscription stages in that scope without repeated
phase approvals. The run records provider, model, reasoning, surface, calls, token quotas,
artifacts, and eligibility; executes under a durable owner; profiles every call; and reconciles
the ledger. A directly billed API surface, model substitution, material scope expansion, or
material non-quota failure still requires a stop and fresh authority where applicable. Never
repair or relabel a failed run into a pass.
An aggregate-quota-only stop may resume in place under the end-to-end authorization when the
prospective bounded quota amendment stays within the recorded run envelope; otherwise it
requires explicit approval of the larger ceiling. Every amendment binds the exact settled ledger prefix. The
request inventory and call ceiling remain fixed, settled calls are never rerun, and any
scientific, structural, provenance, identity, transport, or quality failure still requires a
fresh release.

### Task closeout and archive transition

Closing a task is part of the task. In the same reviewed change:

1. Write `docs/archive/workplan/YYYY-MM-DD-<task-id>-<slug>.md` using §7.
2. Add it to [`archive/workplan/README.md`](archive/workplan/README.md).
3. Replace detailed completed-task text here with a one-line result and archive link.
4. Activate the next dependency-complete task, or name its exact blocker.
5. Update `Current checkpoint` and the `Completed ledger`.
6. Synchronize architecture, requirements, registry/attributions, and testing guides affected
   by the task.
7. Run task verification, `git diff --check`, hygiene scans, and `git status`.

### Common implementation contract for every queued task

In addition to task-specific inputs, every task reads `AGENTS.md`, this workplan, the
authoritative requirements, the relevant architecture section, coding guidelines, and
operational hygiene. Source work also reads the registry, attributions, source requirements,
and local-data-store rules. Score-bearing work also reads calibration and every applicable
chapter guide. Public-output work validates exact attribution text.

Every task must produce: a versioned/configuration-driven implementation or documented terminal
decision; focused boundary tests; persisted reproducibility artifacts; a self-review fixed in
place; an independent review when required by risk; synchronized normative documentation; and
the archive/queue transition. Code tasks run focused pytest, Ruff, the applicable integration
or slow smoke, and the full default suite before promotion. Documentation tasks run link,
status/dependency, diff, and hygiene checks. A task is not complete merely because code exists;
its runtime path, CLI/registry boundary when applicable, artifact validation, and failure path
must be proven.

## 3. Current checkpoint

- Active phase: **Phase 3 — promote and harden the ruler-quality pipeline**.
- Active task: **P3-T2 — version and activate**.
- Commit `ac033fdd` records completed v17 final writing.
- Production remains `production-2023-v4`; experiments never mutate it.
- Frozen cohort: `research/runs/2023-five-ruler-flow-test-v2/`.
- Frozen Netanyahu inputs: `research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/`.
- Active run: `research/runs/netanyahu-2023-integrated-luna-sol-v17/`.
- v17 writing: 80/80 Luna-high calls validated; 4,703,846 input, zero cached input,
  320,509 output, and 100,066 reasoning-output tokens. The ledger has 80 completed writer
  reservations and no unresolved work.
- Five-ruler v5 writing is complete and trusted-reloads: 400/400 answers across 40 chapters.
  The quota-only continuation preserved all 306 settled calls, promoted seven already-paid raw
  outputs without replay, and made only the remaining 94 calls. Cumulative usage is 28,203,395
  input, 366,080 cached input, 1,745,582 output, and 687,254 reasoning-output tokens under the
  approved 40,000,000-input / 5,000,000-output / 400-call ceiling.
- Fresh cohort release `five-ruler-2023-luna-sol-v7` binds the reviewed PRK `7B.3`
  supplement through PRK release `five-ruler-2023-prk-v2`. Its zero-call preflight is eligible:
  400/400 complete writer requests measure 21,936,632 input tokens and reserve exactly
  5,000,000 output tokens under the intended 40,000,000-input ceiling; all five integrated
  manifests pass, with zero calls and zero reservations. The earlier v6 diagnostic remains
  preserved with its looser inherited ceiling. This historical checkpoint preceded the user's
  later end-to-end subscription authorization; the completed execution is recorded below.
- V7 trusted-import preflight reconstructs and reuses 39/40 complete writing chapters and all
  16 complete review chapters from v5. The only writing chapter still requiring execution is
  PRK `7B`: its 10 authorization-bound Luna-high calls completed and trusted-reload using
  500,568 input, zero cached input, 29,964 output, and 14,942 reasoning-output tokens. The next
  review preflight imports 160 completed reviews and measures the remaining 240 requests at
  14,517,174 input tokens and 3,000,000 configured output capacity under per-ruler profiles;
  this historical zero-call checkpoint was subsequently executed under the end-to-end
  subscription authorization recorded below.
- Targeted research established that PRK `7B.3` was an evidence-collection defect, not a true
  unavailable lens; four source-claim units are preserved in
  `research/runs/five-ruler-2023-luna-sol-v5-release/research-gaps/PRK-7B.3-targeted-research.md`
  and now produce a fresh trusted-reloadable v2 package in
  `research/runs/five-ruler-2023-prk-evidence-v2/question-packages/7B/package.json`. Three units
  are adverse evidence and the older Treasury record is context-only; raw snapshots, extracted
  passages, excerpts, limitations, the base package, and the independent review are hash-bound.
  Generically, an empty packet now stops unless exact search
  and zero-admissible inventories have an independent, hash-bound saturation pass. A genuine
  unavailable lens skips question writing/review and remains judge-visible as lower confidence.
- P1-T1 rejected v17 review launch without a model call: all 80 requests measured
  4,696,427 input tokens, but chapter 6B requires 1,007,971 tokens against the configured
  1,000,000-token per-chapter review ceiling. The user subsequently set the prospective
  question-review ceiling to 1,200,000 tokens; the rejected preflight remains immutable.
- The fresh v18 review run stopped after five settled calls when `4B.1` failed citation
  entailment. Four reviews passed; no later review, judgment, audit, or publication ran.
- The user authorized replacing per-failure decisions with a finite configuration-driven
  experiment. Its first policy collects one complete review round, performs no rerun or
  evidence return, stops on invalid infrastructure/artifacts, and stops before judging.
- The v19 autonomous run completed 19 calls and produced 18 valid reviews, including two
  scientific failures that did not stop the batch. It then stopped as configured when `2B.3`
  emitted unknown evidence ID `BATCH-0036-E020`; no reservation remains unresolved.
- P1-T2B completed the prospective transport fix without a model call. New blind reviews use
  prompt contract v15 and packet-constrained schema v5; historical v14/v4 artifacts continue
  to trusted-reload, and schema-version downgrade is rejected.
- P1-T2C passed a fresh zero-call v20 preflight: 80 packet-bound requests require 4,787,345
  measured input tokens and 20,370,678 characters; all downstream roots remain unused.
- P1-T2D completed all 80 constrained reviews with no structural failure. Eight experimental
  answers failed across chapters 2B-7B; the zero-return policy stopped before judgment with
  no unresolved reservation.
- P1-T2E through P1-T5 completed the one-ruler gate: eight bounded corrections and final
  reviews, eight reviewed judgments, a passing deterministic audit, and a cited experimental
  publication. The continuation used 35 calls, 12,664,316 input, 8,550,656 cached input,
  191,649 output, and 100,219 reasoning-output tokens.
- P2-T2 through P2-T4 completed the five-ruler gate: 400 writings/reviews, 51 bounded
  corrections/final reviews, 40 evidence-reading first passes, eight five-ruler calibrations,
  eight independent reviews, and a passing cited publication. The reviewed ordering is USA,
  ISR, CHN, RUS, PRK by eight-chapter mean. The next active task is production versioning;
  a separate answer-trusting judge comparison is retained as a requested experiment.
- Reader-facing review v4 corrected a publication-language defect without changing scores:
  retained judgments now preserve the calibrated rationale instead of replacing it with terse
  evidence-ID shorthand. Eight fresh bounded reviews completed under the hash-bound policy;
  the reader-v2 public build contains 721 validated files and binds its selected audit by path
  and SHA-256. Historical v3 review and projection artifacts remain reconstructable.
- Reader-facing review v5 adds a distinct short answer and fuller period account for every one
  of the 40 chapter judgments. The account names relevant events and affected populations and
  separates inherited institutions and external constraints from the ruler's own decisions and
  omissions. All scores, confidence values, plausible ranges, and ruler identities remain
  unchanged; the reader-v3 build contains 721 hash-bound files.

### Fixed v17 control flow

```text
80 Luna-high final writes (COMPLETE)
  -> 80 Luna-high blind independent question reviews
  -> for each failed review: exactly one Luna-high correction
     -> exactly one Luna-high final review
     -> carry any residual concern forward at lower confidence
  -> 8 Sol-high chapter judgments
  -> 8 Sol-high independent judgment reviews
  -> deterministic score/order/citation/attribution audit
  -> cited experimental publication
  -> one-ruler promotion decision
```

The focused Luna verifier is an archived diagnostic, not another production stage. The
authoritative initial question-quality action is `run_all_chapter_question_review`. A failed
initial review authorizes one configured correction and one mandatory final review; it never
authorizes a second correction, another final review, or an unbounded repair loop. Residual
concerns after that review remain judge-visible and lower confidence rather than stopping the
pipeline.

Preflight inventories the exact failed-count-derived path: 176 straight-through calls plus
two calls for each failed initial review. The realized one-ruler path required 192 calls; the
prospective maximum is 336 calls if all 80 initial reviews fail. Every run must fit its exact
inventory within the configured run-wide ceilings before execution; the original v17 ceilings
were 250 calls, 40,000,000 input tokens, and 1,000,000 output tokens and therefore are not a
universal ceiling for the expanded worst case. Older goals
of fewer than 150 calls, 500,000 output tokens, and majority cache rates remain historical
comparison measures, not current gates: they conflict with the retained 80-write + 80-review
+ 8-judgment + 8-review architecture. Quality remains controlling.

## 4. Definition of project completion

All required phases in §5 must be complete, with:

- a promoted versioned pipeline and validated full-scope 2023 run;
- resolved ruler identities, with genuine ambiguity quarantined;
- structured and cited/manual evidence with explicit missingness;
- calibrated ruler scores, confidence, client deltas, and review states without using the
  client matrix as evidence;
- complete review-queue and cited publication outputs with exact attribution;
- reproducible manifests, source locators, hashes, model profiles, and budgets;
- passing score/order, citation, attribution, tests, lint, and hygiene gates;
- no required job pending, running, retryable, failed, or undispositioned.

## 5. Canonical phase and task queue

### Phase 0 — planning and governance consolidation

Status: `COMPLETE` when this change is archived.

Outcome: this file becomes the sole executable queue; subsystem plans become reference only;
the archive/closeout protocol, current v17 state, review contract, and current promotion limits
are reconciled.

### Phase 1 — finish the Netanyahu 2023 one-ruler gate

Purpose: prove the simplified lower-cost pipeline preserves scientific quality from frozen
evidence through publication before cohort expansion.

#### P1-T1 — preflight v17 blind independent question review

Status: `REJECTED` — zero-call preflight found the 6B review inventory 7,971 tokens above its
configured chapter ceiling; see
[`archive/workplan/2026-08-20-p1-t1-v17-question-review-preflight.md`](archive/workplan/2026-08-20-p1-t1-v17-question-review-preflight.md).

#### P1-T2 — execute v17 blind independent question review

Status: `REJECTED` — the run stopped after five settled calls when `4B.1` failed citation
entailment; see
[`archive/workplan/2026-08-20-p1-t2-v18-question-review.md`](archive/workplan/2026-08-20-p1-t2-v18-question-review.md).

#### P1-T2A — autonomous collect-all question-review experiment

Status: `REJECTED` — collect-all scientific failures worked, but `2B.3` produced an invalid
unknown evidence ID after 19 settled calls; see
[`archive/workplan/2026-08-20-p1-t2a-v19-autonomous-review.md`](archive/workplan/2026-08-20-p1-t2a-v19-autonomous-review.md).

#### P1-T2B — constrain blind-review evidence-ID transport

Status: `COMPLETE` — packet-constrained schema v5 is bound to prompt contract v15 with
historical reload and downgrade protection; see
[`archive/workplan/2026-08-20-p1-t2b-constrained-review-transport.md`](archive/workplan/2026-08-20-p1-t2b-constrained-review-transport.md).

#### P1-T2C — fresh constrained autonomous-review preflight

Status: `COMPLETE` — fresh v20 zero-call preflight is eligible for all 80 packet-constrained
reviews; see
[`archive/workplan/2026-08-20-p1-t2c-v20-constrained-preflight.md`](archive/workplan/2026-08-20-p1-t2c-v20-constrained-preflight.md).

#### P1-T2D — execute the v20 constrained autonomous review

Status: `REJECTED` — all 80 reviews validated, but eight experimental answers failed and the
frozen zero-return policy stopped before judging; see
[`archive/workplan/2026-08-21-p1-t2d-v20-constrained-review.md`](archive/workplan/2026-08-21-p1-t2d-v20-constrained-review.md).

#### P1-T2E — one correction and residual-confidence handoff

Status: `COMPLETE` — eight corrections and final reviews produced the trusted 80-answer handoff;
see [`archive/workplan/2026-08-21-p1-t2e-one-correction-handoff.md`](archive/workplan/2026-08-21-p1-t2e-one-correction-handoff.md).

#### P1-T3 — preflight and execute eight chapter judgments

Status: `COMPLETE` — eight reviewed-answer-bound judgments validated; see
[`archive/workplan/2026-08-21-p1-t3-chapter-judgments.md`](archive/workplan/2026-08-21-p1-t3-chapter-judgments.md).

#### P1-T4 — preflight and execute eight independent judgment reviews

Status: `COMPLETE` — all eight judgments received one independent review; see
[`archive/workplan/2026-08-21-p1-t4-judgment-reviews.md`](archive/workplan/2026-08-21-p1-t4-judgment-reviews.md).

#### P1-T5 — final audit, publication, and one-ruler decision

Status: `COMPLETE` — audit and cited experimental publication passed; see
[`archive/workplan/2026-08-21-p1-t5-audit-publication.md`](archive/workplan/2026-08-21-p1-t5-audit-publication.md).

### Phase 2 — five-ruler confirmation and release decision

Status: `COMPLETE`.

1. **P2-T1 — freeze cohort and zero-call preflight.** `REJECTED` — 399/400 writing requests measured;
   frozen `PRK` `7B.3` cannot construct the Phase 1 writer schema, and the 5,000,000-token cohort
   output ceiling cannot cover 51,200,000 tokens of required reservation capacity;
   see [`archive/workplan/2026-08-21-p2-t1-five-ruler-preflight.md`](archive/workplan/2026-08-21-p2-t1-five-ruler-preflight.md).
1A. **P2-T1A — generic sparse-question transport.** `COMPLETE` — evidence-empty packets now use a
   strict evidence-insufficient writer and empty-allowlist review contract; fresh v3 preflight
   constructs all 400 requests and remains rejected only on output capacity; see
   [`archive/workplan/2026-08-21-p2-t1a-sparse-question-transport.md`](archive/workplan/2026-08-21-p2-t1a-sparse-question-transport.md).
1B. **P2-T1B — output-capacity preflight.** `COMPLETE` — the fresh v4 release measures all 400
   requests and is eligible under the approved 52,000,000-token reservation ceiling; see
   [`archive/workplan/2026-08-21-p2-t1b-output-capacity-preflight.md`](archive/workplan/2026-08-21-p2-t1b-output-capacity-preflight.md).
2. **P2-T2 — execute writing and question review.** `COMPLETE` — 400 answers/reviews and 51 bounded
   correction/final-review branches produced five trusted handoffs; see
   [`archive/workplan/2026-08-23-p2-t2-five-ruler-writing-review.md`](archive/workplan/2026-08-23-p2-t2-five-ruler-writing-review.md).
3. **P2-T3 — execute comparative judging and judgment review.** `COMPLETE` — 40 lossless first
   passes, eight five-ruler calibrations, and eight independent reviews passed; see
   [`archive/workplan/2026-08-23-p2-t3-comparative-judging.md`](archive/workplan/2026-08-23-p2-t3-comparative-judging.md).
4. **P2-T4 — aggregate audit, publication, and recommendation.** `COMPLETE` — deterministic audit
   and corrected-answer-bound cited publication passed; see
   [`archive/workplan/2026-08-23-p2-t4-audit-publication.md`](archive/workplan/2026-08-23-p2-t4-audit-publication.md).

Exit: a fresh five-ruler release passes every gate or the candidate architecture is rejected
with a terminal reason.

### Phase 3 — promote and harden the ruler-quality pipeline

Status: `ACTIVE`.

1. **P3-T1 — answer-trusting judgment comparison.** `COMPLETE` — eight answer-only chapter
   calls preserved the exact five-ruler rank order with 27/40 unchanged scores; see
   [`archive/workplan/2026-08-23-p3-t1-answer-trusting-comparison.md`](archive/workplan/2026-08-23-p3-t1-answer-trusting-comparison.md).
2. **P3-T2 — version and activate (`ACTIVE`).** Create a new production config/release with bound prompt,
   schema, control, and source hashes; retain v4 unchanged; synchronize architecture/requirements.
3. **P3-T3 — smoke and rollback proof.** Prove release selection, budgets, attribution, and
   rollback through no-model tests plus the smallest separately authorized model smoke.
4. **P3-T4 — low-cost search-retrieval waterfall (`DEFERRED`).** Improve
   evidence discovery without replacing evidence validation or allowing vendor-generated answers
   to become evidence. Implement and evaluate the following complete prospective contract:

   - Search once per ruler/chapter and reuse deduplicated findings across its ten lenses; do not
     run eighty isolated research jobs. Begin with local packages, known URLs, and a reusable
     authority baseline, then issue distinct ruler-conduct, institution/program, audit/judgment,
     local-language, favorable/remedial, contrary, target-year, and ruler-period query families.
   - Use free specialist discovery before paid escalation: OpenAlex for scholarship/open PDFs;
     GDELT or an equivalent validated historical-news route for multilingual leads; direct UN,
     World Bank, government, court, parliamentary, sanctions, NGO, and archive endpoints; and
     Common Crawl/Wayback only for known changed or missing URLs. Registry, licensing, temporal
     coverage, and attribution rules still apply.
   - Trial Parallel `fast` as the inexpensive general discovery layer (planning price observed
     2026-08-21: approximately $1/1,000 ten-result searches) and Brave as an independent broad-
     index fallback (approximately $5/1,000). Use Exa semantic search only for residual conceptual
     gaps (approximately $7/1,000). Tavily's free allowance may participate in evaluation, but
     no provider is selected from vendor benchmarks or marketing claims alone. Recheck current
     prices, terms, index coverage, and retention policy at implementation time.
   - Integrate through direct, quota-bound APIs for production reproducibility; MCP remains an
     optional interactive surface. Persist exact query/provider/mode/time, returned URL and
     snippet hashes, rank, language, cache status, usage, and cost. Deduplicate before retrieval;
     fetch only promising documents; extract and hash exact passages locally; and keep search
     snippets and synthesized vendor reports as leads rather than evidence.
   - Apply a cost-controlled waterfall: primary discovery for every selected chapter, a second
     independent index only for unresolved or source-concentrated themes, semantic escalation
     only for the hardest residual gaps, and bounded deep-research tasks only as lead generators.
     The planning envelope for five rulers is 1,000 primary searches, 300 fallback searches, 100
     semantic searches, and 1,000 managed page extractions—roughly $4-$5 at the observed prices
     and below $20 with contingency. Returned-context/model tokens are budgeted separately and
     controlled by local URL deduplication and bounded passage extraction.
   - Before adoption, freeze a 40-50-lens repository benchmark containing known collection misses
     (including PRK `7B.3`), genuinely sparse lenses, multilingual/local-language cases, obscure
     PDFs, and ordinary well-covered questions. Run identical query families blind across the
     current search and candidates. Measure admissible source-claim recall, unique primary-source
     recall, historical/target-year and multilingual fit, PDF retrieval success, source-family
     diversity, duplicates, misleading snippets, cost per accepted evidence unit, downstream
     input tokens, latency, and reproducibility. Promote only a waterfall that materially improves
     repository-specific recall at bounded cost; preserve the benchmark, raw responses, hashes,
     and decision manifest.

   Exit: the selected search waterfall passes the frozen benchmark and plugs into the existing
   cited-research notebook and saturation/adjudication contracts without weakening independent
   evidence review, exact citation verification, local-first reuse, or explicit API-run approval.

Exit: a reviewed, reproducible, tested production candidate is active.

### Phase 4 — structured source and country-year coverage completion

Status: `DEFERRED` until Phase 3. Status evidence comes from `architecture/sources.md` and
`sources/registry.md`; old ingestion/vetting plans do not override them.

1. **P4-T1 — mapping/lifecycle/precedence hardening.** Close remaining PTS, CIRIGHTS, Freedom
   House, WGI, CPI, BTI, EIU, territory, aggregate, and historical-state publication gaps with
   explicit policies and coverage reports. Re-probe or terminally disposition the still-blocked
   Leader Survival, IMF WEO, COW MID, NTI, and ICOW/dependency sources; user-managed acquisition
   remains a named blocker, never an inferred download task.
2. **P4-T2 — economic/social tranche.** Vet and disposition ILO labor, Global Findex, World
   Inequality Database, and remaining poverty/service concepts, reusing PIP/WDI/Maddison/PWT/
   UNDP/WHO first.
3. **P4-T3 — conflict/proxy/arms tranche.** Vet and disposition UCDP external support,
   Non-State Actor Dataset, Dangerous Companions/NAGs, ATT Monitor, and ACLED for named 2B/3B
   gaps.
4. **P4-T4 — nuclear tranche.** Reuse FAS/SIPRI/IAEA/CTBTO first; vet and disposition UNODA,
   nuclear-test, Ban Monitor, CSIS, CNS/NTI, WNA, and user-managed NTI candidates.
5. **P4-T5 — effectiveness tranche.** Define cited acquisition for manifestos, budget execution,
   goal indicators, and audit/oversight reports; keep heterogeneous documents out of bulk Stage 2
   absent a stable structured contract.

Every candidate ends as implemented, rejected, blocked-user-managed, or unnecessary. Exit when
required concepts have an implemented or explicit missing/manual route and all registries,
attributions, manifests, tests, and reviews agree.

### Phase 5 — research engine, answer tables, scoring, and review queue

Status: `DEFERRED` until Phase 4. This consolidates incomplete I5-I11 and D8-D30 work.

1. **P5-T1 — concepts/facts (I5/I6; D8-D17).** Finish units, direction, time/proxy rules,
   precedence, and harmonized facts while retaining observations/provenance.
2. **P5-T2 — executable registry (I7; D23).** Register chapter 1-8 and confirm 1B-8B with scope,
   answer type, strategy, concepts, sources, proxy, handler, review, and internet metadata.
3. **P5-T3 — generic dispatch/runner (I7.5).** Make question + years + countries/rulers a
   parameterized, idempotent run over reusable structured/context/manual/hybrid strategies.
4. **P5-T4 — structured answers (I8; D24).** Build reusable fact-backed answers, explicit gaps,
   and exact evidence links.
5. **P5-T5 — ruler-period/cited persistence (I9/I10; D18-D26).** Persist typed goals,
   implementation, crises, appointments, integrity cases, dossiers, mappings, answers, and
   calibrated chapter scores through generic tables.
6. **P5-T6 — audit-complete links (D27).** Require exact observation IDs or cited locators and
   queryable QA for orphan/bad-period/attribution gaps.
7. **P5-T7 — aggregation/confidence (I11; D28).** Aggregate only after a sufficient pilot; keep
   fixed confidence and separate client/proposed/final/delta fields.
8. **P5-T8 — D29 decision.** Implement country-category scores only if the product needs a layer
   separate from ruler responsibility; rejection is a valid archived result.
9. **P5-T9 — review queue (D30).** Build attributed review items from missingness, confidence,
   conflicts, impact, explicit flags, and thresholds.

Exit: registered questions flow through generic strategies into audit-complete answers, scores,
confidence, and review items without question-specific orchestration changes.

### Phase 6 — Country-Year Chronicle completion

Status: `DEFERRED` until Phase 5.

1. **P6-T1 — recent-window summary/review artifacts.** Finish all-country 1960-2026 summary,
   missingness, quality flags, and manual review; validate detailed/condensed CSV, SQLite,
   attribution, and deterministic reruns.
2. **P6-T2 — controlled/imperial-area decision.** Recheck ICOW/COW/alternatives; define control
   semantics and dependency rows; accept a vetted source or retain country-only fallback. Never
   invent colonial mappings.
3. **P6-T3 — stabilization/schema decision.** Resolve system-type taxonomy, validate 1900-2026,
   and decide whether to migrate the stable Chronicle contract into the canonical database.

### Phase 7 — visualization, publication surfaces, and controlled client access

Status: `DEFERRED` until Phase 6; live access also needs user credentials. P7-T4 is an optional
deployment activation and does not block Phase 8 scientific/product acceptance when the local
publication surface has passed.

1. **P7-T1 — close reviews.** Independently review generic CLI and investigation slice; verify
   semantic queries, provenance, attribution, source-series separation, and read-only Superset.
2. **P7-T2 — expand generic question families.** Publish selected economic, regime/population,
   tenure, governance, freedom, and coverage outputs through the generic metric layer.
3. **P7-T3 — validate the static ruler-study projection.** Exercise the production-gated static
   study builder, year/release registry, client-score exclusion, citation/source excerpt binding,
   attribution, route/file manifest, and read-only portal integration. Keep public study output
   separate from operational prompts, logs, raw documents, secrets, and local paths.
4. **P7-T4 — secure activation.** Blocked on Cloudflare token and email allowlist. Create Access
   before hostname; verify denial, least privilege, read-only data, HTTPS/session hardening, and
   recovery.

### Phase 8 — full 2023 production acceptance

Status: `DEFERRED` until required components of Phases 3-7 are complete.

1. **P8-T1 — readiness/transport preflight.** Resolve full cohort; validate sources, identity
   locks, coverage, request splitting/manifests, budgets, attribution, roots, and durable jobs.
2. **P8-T2 — execute Stages 0-15.** Run ingestion through publication under one named end-to-end
   Codex/subscription authorization, with a zero-call bounded preflight at every model-bearing
   stage and persistence through recoverable work. Obtain new authority only for direct billing,
   model substitution, material expansion or failure, or a run-envelope increase.
3. **P8-T3 — acceptance/release.** Require top-level criteria, relevant full/slow tests, lint,
   independent code/scientific review, citations, attribution, manifests, and no unresolved jobs.

### Phase 9 — historical expansion and maintenance

Status: `DEFERRED` until Phase 8.

1. **P9-T1 — historical pilot.** Run a bounded older-year cohort with explicit missingness,
   uncertainty, and no silent modern backfill.
2. **P9-T2 — maintenance.** Define source-version checks, blocked-source re-probes, schema/prompt
   migration tests, cost drift, backup/restore, and release deprecation with versioned manifests.

## 6. Completed ledger

| Work | Outcome | Archive/reference |
|---|---|---|
| Project history through 2026-08-14 | Complete | [`archive/workplan/workplan-through-2026-08-14.md`](archive/workplan/workplan-through-2026-08-14.md) |
| P0 planning consolidation | Complete; one executable queue established | [`archive/workplan/2026-08-20-p0-plan-consolidation.md`](archive/workplan/2026-08-20-p0-plan-consolidation.md) |
| Cost optimization Tasks 1-5 | Complete | [`archive/workplan/README.md`](archive/workplan/README.md) |
| Netanyahu diagnostics through v16 | Rejected/immutable | [`archive/workplan/2026-08-20-netanyahu-integrated-diagnostic-lineage.md`](archive/workplan/2026-08-20-netanyahu-integrated-diagnostic-lineage.md) |
| Netanyahu v17 final writing | Complete; 80/80 validated | [`archive/workplan/2026-08-20-p1-v17-final-writing.md`](archive/workplan/2026-08-20-p1-v17-final-writing.md) |
| P1-T1 v17 question-review preflight | Rejected; 6B exceeded its configured stage-input ceiling without a model call | [`archive/workplan/2026-08-20-p1-t1-v17-question-review-preflight.md`](archive/workplan/2026-08-20-p1-t1-v17-question-review-preflight.md) |
| P1-T2 v18 question review | Rejected; `4B.1` failed citation entailment after five settled calls | [`archive/workplan/2026-08-20-p1-t2-v18-question-review.md`](archive/workplan/2026-08-20-p1-t2-v18-question-review.md) |
| P1-T2A v19 autonomous review | Rejected; collected valid failures but stopped on an unknown evidence ID after 19 calls | [`archive/workplan/2026-08-20-p1-t2a-v19-autonomous-review.md`](archive/workplan/2026-08-20-p1-t2a-v19-autonomous-review.md) |
| P1-T2B constrained review transport | Complete; packet-local schema v5, historical reload, and downgrade protection | [`archive/workplan/2026-08-20-p1-t2b-constrained-review-transport.md`](archive/workplan/2026-08-20-p1-t2b-constrained-review-transport.md) |
| P1-T2C v20 constrained preflight | Complete; 80/80 packet-bound requests eligible with zero calls or reservations | [`archive/workplan/2026-08-20-p1-t2c-v20-constrained-preflight.md`](archive/workplan/2026-08-20-p1-t2c-v20-constrained-preflight.md) |
| P1-T2D v20 constrained review | Rejected; 80/80 valid reviews found eight material experimental-answer failures | [`archive/workplan/2026-08-21-p1-t2d-v20-constrained-review.md`](archive/workplan/2026-08-21-p1-t2d-v20-constrained-review.md) |
| P1-T2E bounded correction handoff | Complete; eight corrections/final reviews and trusted 80-answer handoff | [`archive/workplan/2026-08-21-p1-t2e-one-correction-handoff.md`](archive/workplan/2026-08-21-p1-t2e-one-correction-handoff.md) |
| P1-T3 chapter judgments | Complete; eight validated reviewed-answer-bound judgments | [`archive/workplan/2026-08-21-p1-t3-chapter-judgments.md`](archive/workplan/2026-08-21-p1-t3-chapter-judgments.md) |
| P1-T4 judgment reviews | Complete; eight independent reviews, one bounded score correction | [`archive/workplan/2026-08-21-p1-t4-judgment-reviews.md`](archive/workplan/2026-08-21-p1-t4-judgment-reviews.md) |
| P1-T5 audit/publication | Complete; passing audit and production-eligible experimental publication | [`archive/workplan/2026-08-21-p1-t5-audit-publication.md`](archive/workplan/2026-08-21-p1-t5-audit-publication.md) |
| P2-T1 five-ruler preflight | Rejected; PRK 7B.3 is unwritable and configured output capacity is insufficient | [`archive/workplan/2026-08-21-p2-t1-five-ruler-preflight.md`](archive/workplan/2026-08-21-p2-t1-five-ruler-preflight.md) |
| P2-T1A sparse-question transport | Complete; all 400 writer requests construct without invented evidence | [`archive/workplan/2026-08-21-p2-t1a-sparse-question-transport.md`](archive/workplan/2026-08-21-p2-t1a-sparse-question-transport.md) |
| P2-T1B output-capacity preflight | Complete; fresh 400-request writing inventory eligible under 52M reservation capacity | [`archive/workplan/2026-08-21-p2-t1b-output-capacity-preflight.md`](archive/workplan/2026-08-21-p2-t1b-output-capacity-preflight.md) |
| P2-T2 five-ruler writing/review | Complete; 400 answers/reviews, 51 corrections/final reviews, five handoffs | [`archive/workplan/2026-08-23-p2-t2-five-ruler-writing-review.md`](archive/workplan/2026-08-23-p2-t2-five-ruler-writing-review.md) |
| P2-T3 comparative judging | Complete; 40 first passes, eight calibrations, eight reviews | [`archive/workplan/2026-08-23-p2-t3-comparative-judging.md`](archive/workplan/2026-08-23-p2-t3-comparative-judging.md) |
| P2-T4 audit/publication | Complete; passing audit and cited five-ruler publication | [`archive/workplan/2026-08-23-p2-t4-audit-publication.md`](archive/workplan/2026-08-23-p2-t4-audit-publication.md) |
| P3-T1 answer-trusting comparison | Complete; 8 calls, exact rank order retained, 27/40 scores unchanged | [`archive/workplan/2026-08-23-p3-t1-answer-trusting-comparison.md`](archive/workplan/2026-08-23-p3-t1-answer-trusting-comparison.md) |

## 7. Required task-archive template

```markdown
# <Task ID> — <title>

- Date closed:
- Outcome: COMPLETE / REJECTED
- Starting commit and ending commit:
- Objective and scope executed:
- Decisions and lasting constraints:
- Files/configs changed:
- Durable artifacts and SHA-256 bindings:
- Model provider/model/reasoning/surface; approved maximum and actual calls:
- Input/cached/output/reasoning tokens, elapsed time, billing limitation:
- Focused/full tests, lint, validators, and reviews:
- Failures/findings and disposition:
- Deferred/optional items (non-blocking):
- Next task activated or exact blocker:
```

## 8. Start prompt for the active task

```text
Work in /home/liorshtram/projects/leaders-db.

Read AGENTS.md and docs/workplan.md completely. Execute only the task marked ACTIVE.
Read its named inputs and validate predecessor artifacts before editing. Follow its boundary,
deliverables, verification, and completion gate. Do not begin the next task.

For model work, a named end-to-end Codex/subscription instruction authorizes every later stage
whose zero-call preflight stays within that scope and its recorded run envelope; do not stop for
another phase approval merely because its exact quota became known during preflight. Request new
authority only for direct billing, model substitution, material scope expansion or failure, or
an envelope increase. Use a durable owner, profile every call, and persist until complete or
genuinely new authority is required.

At completion, archive the task using §7, update the archive index, reduce it to one ledger line,
activate the next eligible task, synchronize affected normative docs, run required checks, and
commit only if explicitly requested.
```
