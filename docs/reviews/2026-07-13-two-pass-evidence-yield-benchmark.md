# Two-pass evidence-yield benchmark — 2026-07-13

## Scope

This smoke benchmark tested the corrected full-ruler workflow on two contrasting
2020 cases:

- Jacinda Ardern, New Zealand (`ruler_year_id=15125`), a high-information case.
- George Weah, Liberia (`ruler_year_id=11650`), a medium-information case.

Each case used eight parent Parallel Search calls, one per chapter. The resulting
hashed discovery packet was shared between the Luna and MiniMax M3 researcher
runs. Every researcher produced a permissive notebook/handoff; a separate Luna
pass produced the strict 80-lens dossier. The target was 5–20 retained,
non-duplicative evidence items per chapter, normally about 10, without making the
count a publication gate.

## Implementation correction and verification

The benchmark ran only after the following behavior was implemented and reviewed:

- schema-light researcher pass and separate persisted formatter profile;
- soft 5–20 evidence-item goal per chapter;
- one independently hashed discovery call per chapter;
- parent-only trusted storage for discovery, schema, local priors, event logs,
  research notebook, and checkpoint hashes;
- formatter-only retry using a verified notebook and discovery packet;
- recovery of individually completed chapter searches after partial discovery
  failure;
- separate researcher/formatter usage and mixed-model cost accounting;
- shared discovery charged only to the job that purchased it;
- `plan-case` defaults to all 80 ruler-quality lenses when `--question-id` is
  omitted.

Independent code review found no remaining blocker, major, or minor issue in the
trust, retry, or partial-search accounting paths. Sixty-nine focused tests pass
across worker contracts, planning, discovery continuation, costing, and
readiness; Ruff is clean on the affected files. The full repository suite was
intentionally not run.

## Discovery yield

| Case | Chapter result counts | Raw results | Unique URLs | Physical search cost |
|---|---:|---:|---:|---:|
| New Zealand 2020 | 10 for every chapter | 80 | 53 | $0.040 |
| Liberia 2020 | 10 except 3B=7 | 77 | 55 | $0.040 |

The search stage therefore supplied enough candidate records to make the target
plausible. Retained evidence, not initial discovery count, remained the limiting
stage.

## Published dossier results

| Case / researcher | Evidence | Mappings | Unique source hosts | Evidence IDs mapped to chapters 1B→8B | Result |
|---|---:|---:|---:|---|---|
| New Zealand / Luna | 15 | 93 | 15 | 2, 0, 6, 6, 5, 7, 2, 7 | Valid; usable after cleanup |
| New Zealand / M3 | 24 | 125 | 16 | 3, 3, 2, 3, 5, 3, 6, 5 | Valid; broader but less reliable |
| Liberia / Luna | 12 | 7 | 11 | 1, 1, 0, 2, 1, 0, 1, 1 | Valid evidence; formatter mapping defect |
| Liberia / M3 | 1 | 3 | 1 local prior | 0, 0, 0, 1, 0, 0, 0, 0 | Infrastructure-invalid researcher run |

No run achieved the 5–20 goal in every chapter. New Zealand/M3 had the highest
raw yield but still fell below five in five chapters. New Zealand/Luna met the
minimum in five chapters. Liberia/Luna's twelve substantive records span more
themes than its seven mappings indicate: the formatter incorrectly marked all 80
coverage rows `no_evidence_found`, even where its own evidence and explanations
show coverage. Those labels remain advisory, but the defect makes automatic
chapter-yield measurement unreliable. Liberia/M3 is not a genuine quality result:
the researcher returned a sandbox refusal and the formatter correctly avoided
inventing evidence.

## Independent evidence-quality review

An independent, no-web review treated mapping/status labels as advisory and rated
the underlying evidence:

1. **New Zealand / Luna — 7.5/10.** Diverse, mostly plausible locators and careful
   period/ruler attribution; good contrary evidence. Minor duplicate, homepage,
   retrospective, and carryover-source cleanup remains.
2. **Liberia / Luna — 7/10.** Best sparse-case result, with Freedom House, State
   Department, CRS, IMF, HRW, IAEA, Transparency International, government, and
   media sources. Some publication dates appear inferred incorrectly, and the
   formatter's coverage/mapping output is defective.
3. **New Zealand / M3 — 5/10.** Broader but temporally looser and more willing to
   promote implicit, synthesized, post-period, polemical, or weak-profile evidence.
   It also proposed score bands despite the non-scoring research role.
4. **Liberia / M3 — 1/10 as an output, not an intrinsic-model judgment.** The
   trusted notebook is a sandbox-failure refusal; the one-item dossier is an
   appropriately conservative local-prior fallback.

The current quality recommendation is Luna for evidence research. M3 remains
comparison-only until its Codex execution path is reliable and its evidence
promotion/temporal discipline improve.

## Usage and cost equivalents

Actual billed cash is not exposed. Values below are checked-in PAYG/API-equivalent
ranges; Codex subscription and MiniMax Coding Plan billing may differ.

| Case / researcher | Research tokens | Formatter tokens | Total tokens | Artifact cost range | True marginal range |
|---|---:|---:|---:|---:|---:|
| New Zealand / Luna | 915,368 | 170,317 | 1,085,685 | $0.411–$0.674 | same |
| New Zealand / M3 | 700,731 | 288,245 | 988,976 | $0.331–$0.443 | $0.291–$0.403 |
| Liberia / Luna | 633,036 | 452,284 | 1,085,320 | $0.469–$0.946 | same |
| Liberia / M3 | 1,682,800 | 83,367 | 1,766,167 | $0.279–$0.437 | $0.239–$0.397 |

The already-published M3 artifacts allocate the shared $0.040 discovery packet to
their research usage even though no second search was physically run. The true
marginal column removes that duplicated allocation. The worker was corrected
after observing this, so future shared-discovery comparison jobs record zero new
search cost.

The very large aggregate token counts are not evidence volume. They include
repeated cached context and internal formatter correction attempts. Luna formatting
alone consumed 170k–452k tokens. The Liberia/M3 refusal consumed 1.68M tokens,
mostly cached input, before producing no usable internet evidence. Low nominal
per-token price therefore did not make that run economical.

## Operational observations

- Every child model encountered `bwrap: loopback: Failed RTM_NEWADDR`. Luna still
  returned usable final handoffs; M3 succeeded for New Zealand but refused for
  Liberia. Neither model could reliably append `research-materials.md` or open
  approved URLs.
- Parent capture preserved each final handoff and bound it to the dossier, so the
  file-write failure did not lose completed research.
- Liberia/M3's first Luna formatter call emitted no completion event for about
  fourteen minutes. It was terminated and marked retryable. The second attempt
  reused the exact M3 notebook and discovery packet, ran no second research pass,
  and completed in about two minutes. The stalled attempt exposed no completed
  usage counters, so no token estimate could be added for it.
- Strict 80-row formatting remains expensive even after separating it from
  research. The two-pass boundary protects research quality and retry cost, but
  does not by itself make the formatter cheap.

## Required corrections before a larger batch

1. Make low-cost research explicitly tool-free in this execution environment:
   inline all required instructions/material, forbid shell/file/web tool attempts,
   and ask for chapter-by-chapter progress messages that the parent event log can
   checkpoint.
2. Make the researcher close with an explicit chapter yield audit. It should
   extract distinct claims from a source when warranted, not equate one URL with
   one evidence item, and document every below-five chapter without padding.
3. Reduce formatter scope. It should normalize only the explicit evidence
   register and mappings; deterministic parent code can generate default coverage
   rows and inject immutable identity/provenance fields. This should remove much
   of the 80-row schema-correction cost.
4. Add parent QA flags for suspect publication dates, equivalent/AMP URL
   duplicates, homepage-only locators, discovery synthesis promoted without a
   direct source, post-period evidence, and prohibited score suggestions.
5. Require a substantive trusted research handoff before formatting. A refusal
   may publish an explicit `research_blocked` artifact directly, without paying a
   full formatter to rediscover that it contains no evidence.

The two-pass architecture is an improvement in separation of concerns,
durability, and retry behavior. It has not yet achieved the requested per-chapter
evidence yield or batch-ready token efficiency.
