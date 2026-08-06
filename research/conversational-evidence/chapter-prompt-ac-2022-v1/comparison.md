# Deep Chapter Research Prompt A/C Experiment

Date: 2026-07-24  
Model: `gpt-5.6-sol`

## Question

Does a self-contained, natural-language, saturation-based chapter prompt produce better
deep research than the current count-oriented and pipeline-oriented prompt?

## Cases

| Case | Purpose |
|---|---|
| Vladimir Putin, 2B international peace | Abundant, adversarial, duplicated war evidence and concentrated authority |
| Félix Tshisekedi, 3B domestic safety | Conflict exposure, divided responsibility, weak access, and sparse institutional evidence |
| Joe Biden, 6B social wellbeing | Open information environment, high reporting volume, shared authority, and administrative outcomes |

Three cases are an initial diagnostic gate, not a promotion sample.

## Treatments and Controls

Variant A was the current executable chapter prompt. Variant C:

- described the substantive assignment in ordinary language;
- explained that the ten questions are complementary angles, not quotas or ratings;
- included all researcher-facing guide sections before the scoring rubric;
- used informational saturation instead of document and evidence-count targets;
- separated extracted evidence, corroboration, unopened leads, rejections, blockers, and
  retrospective evidence;
- retained the existing machine-recovery fields in a technical appendix.

Within each pair, both agents received the same ruler-period, chapter questions,
evidence-environment summary, known-resource list, model, web access, and execution
controls. All ran as fresh sessions without project rules or filesystem tools.

Two no-search evaluators assessed all three pairs together. The second reversed
anonymous X/Y order.

## Quantitative Results

| Case | Variant | Output words | URLs | Developed records | Input tokens | Output tokens | Mean blinded quality |
|---|---|---:|---:|---:|---:|---:|---:|
| Putin 2B | A | 2,086 | 20 | 10 | 416,951 | 7,249 | 8.35 |
| Putin 2B | C | 5,030 | 42 | 14 | 414,885 | 11,937 | 9.15 |
| Tshisekedi 3B | A | 1,797 | 20 | 10 | 388,201 | 6,779 | 8.75 |
| Tshisekedi 3B | C | 4,465 | 29 | 10 | 367,338 | 10,577 | 8.90 |
| Biden 6B | A | 2,488 | 32 | 16 | 333,506 | 8,545 | 8.90 |
| Biden 6B | C | 4,642 | 29 | 14 | 423,796 | 12,312 | 8.95 |

Input tokens are cumulative across web research, including retrieved and replayed
context. Counts are measurements, not quality targets.

## Findings

### C improved substantive research architecture

The strongest result was Putin 2B. C reconstructed:

- inherited security and conflict conditions;
- the direct ruler decision;
- stated and alternative justifications;
- available diplomatic alternatives;
- legality and international restraint;
- escalation and annexation;
- civilian consequences;
- ruler, state, command, and incident-level attribution;
- end-of-period outcomes.

A was more compact but omitted several of these necessary links.

For Tshisekedi 3B, C modestly improved institutional evidence, ruler attribution,
conflict-actor separation, inherited conditions, and source-access analysis.

For Biden 6B, C broadened substantive coverage, but A remained competitive because its
records were more compact and consistently atomic.

### Current A features remain valuable

A more consistently provided:

- smaller atomic records;
- clearer disposition accounting;
- discovered/opened/accepted/rejected counts;
- deterministic ledger identifiers;
- less repetition between prose and machine appendices;
- higher output efficiency.

These should be incorporated into the next C revision.

### C defects

C sometimes:

- combined facts with different sources, dates, or attribution levels;
- repeated prose evidence in the machine appendix;
- listed prospective corroboration without fully extracting it;
- used broad rather than stable locators;
- produced substantially longer outputs;
- did not always expose the exact discovered/opened/rejected accounting available in A.

## Guide-Delivery Defect Confirmed

The current guide compactor searches only for `## Researcher Evidence Plan`. That
heading exists for Chapters 4B-6B but not consistently for 1B-3B, 7B, and 8B. The
Putin and Tshisekedi results support the concern that current agents can miss important
researcher guidance. C included all researcher-facing sections before the scoring
rubric and showed its largest advantage in the affected Putin 2B case.

## Decision

The results favor C's research architecture but do not justify production promotion
after three cases.

The next candidate should preserve C while adding:

1. one fact per machine record;
2. one stable URL and locator for every source contributing to a record;
3. source-dependence disclosure, not merely publisher counts;
4. explicit discovered, opened, blocked, accepted, reused, and rejected accounting;
5. deterministic append-only ledger fields;
6. a compact appendix that does not duplicate the readable account;
7. direct ruler statements and concrete corrective cases where available.

## Expanded Gate

Run at least six additional paired cases covering:

- a low-information or highly access-blocked ruler;
- a peaceful case where absence evidence and non-exposure are central;
- an earlier historical period;
- an economic chapter dominated by administrative outcomes;
- a personal-integrity chapter requiring a direct ruler nexus;
- an effectiveness chapter requiring program-to-implementation attribution;
- fragmented local-language evidence;
- weak practical ruler authority.

Promotion requires the C-style coverage and attribution advantage to persist without a
systematic increase in duplication, unstable records, or unnecessary volume.

## Artifacts

- [`manifest.json`](manifest.json)
- [`Putin A`](putin-2b/a/output.md) and [`Putin C`](putin-2b/c/output.md)
- [`Tshisekedi A`](tshisekedi-3b/a/output.md) and
  [`Tshisekedi C`](tshisekedi-3b/c/output.md)
- [`Biden A`](biden-6b/a/output.md) and [`Biden C`](biden-6b/c/output.md)
- [`Forward assessment`](evaluation/forward.md)
- [`Reverse-order assessment`](evaluation/reverse.md)

