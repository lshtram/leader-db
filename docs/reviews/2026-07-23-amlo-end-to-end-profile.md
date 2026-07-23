# AMLO 2022 End-to-End Evidence and Token Profile

## Outcome

One AMLO 2022 case has now crossed every substantive boundary once: local structured
evidence, segmented web research, no-search bias review, no-search formatting, and all
eight chapter judges. The accepted dossier contains 105 evidence records, 405 mappings,
all 80 coverage rows, all 80 local-prior provenance rows, and a cited
evidence-environment assessment. Every chapter remained judgeable.

This is an experimental AMLO replacement, not a promoted 2022 release. The 19 unchanged
rulers were not re-researched or re-judged. Each new AMLO judge received the complete
new AMLO chapter projection plus the preserved scores and rationales of the other 19
rulers as calibration anchors.

## Stage profile

| Stage | Producer input | Output / quality | Actual model usage | Main finding |
|---|---|---|---:|---|
| Local evidence | Local v3 package, 2,691,856 bytes | 80 lens packages; 56 with evidence; 5,132 routed fact instances; 24 explicit empty states | 0 LLM tokens | Rich but extremely repetitive across lenses; 1B has no local facts |
| Web research | 6.8 KB reconnaissance prompt plus eight 10.4–14.7 KB fresh chapter prompts | 102 ledger units; 97 final, five context; 83 URLs, 51 domains, 371 ledger mappings; all locators present | 5,061,732 input, 4,386,816 cached, 72,328 output | Research quality returned to approximately lean-v4 breadth, but provider/session context dominates explicit prompt size |
| Bias review | 181,201-character compact ledger handoff; raw notebook was 357,197 characters | Eight chapter reviews; 9–12 defensible units and 7–10 source families per chapter; 128 cited bias-support references; terminal residual-risk record | 135,962 input, 63,232 cached, 6,583 output | Compact review works, but the handoff omitted an explicit compact local-data disposition audit |
| Formatter | 214,433-character prompt: 181,254 compact research, 23,214 summarized local evidence, 8,071 requirements | 105 evidence, 405 mappings, 80 coverage rows, cited evidence environment | 71,313 input, 0 cached, 28,879 output | Raw-notebook removal cut the planned prompt from 390,429 characters by 45%; tolerant recovery had to select the richer earlier agent message |
| Eight judges | 70,523–101,891 characters each; one full AMLO projection plus 19 compact preserved anchors | Eight numeric judgments; four targeted manual-review flags; all decisive and bias E-IDs resolve | 319,843 input, 24,064 cached, 21,410 output | Anchor reuse cut judge prompt material by roughly 85–94% versus replaying all 20 projections |

Cached input is a subset of input. For the accepted path, the five stages used
5,588,850 input tokens, including 4,474,112 cached tokens, and 129,200 output tokens.
Actual subscription billing and hidden cache-write costs were not exposed.

The development/recovery audit also preserves an additional completed formatter call
of 134,221 input and 3,492 output tokens. It is excluded from the accepted-path table
but remains part of cumulative development cost, as required by REQ-LLM-019.
The subsequent 2B preflight correction used 78,488 input tokens (38,656 cached) and
3,012 output tokens. It replaces the original 2B judgment for the controlled run but
is likewise reported separately from the original end-to-end benchmark.

## Local evidence detail

The raw local package contains 5,132 fact instances because the same underlying facts
are routed to multiple lenses. Chapter totals are:

| Chapter | Routed fact instances |
|---|---:|
| 1B | 0 |
| 2B | 660 |
| 3B | 1,044 |
| 4B | 1,333 |
| 5B | 695 |
| 6B | 429 |
| 7B | 315 |
| 8B | 656 |

The producer is usefully explicit: 56 lenses report `evidence_found` and 24 report
`no_evidence_found`. The main optimization is not to remove facts from the authoritative
package, but to create a fact-key-deduplicated consumer summary containing statuses,
unique observations, longitudinal highlights, warnings, and lens routing. The researcher
correctly received none of the 2.69 MB package. The formatter received only a 23 KB
summary, and judges received chapter-specific summaries inside projections.

## Research quality

| Measure | Lean-v4 | New segmented AMLO | Assessment |
|---|---:|---:|---|
| Evidence / recoverable units | 111 | 102-ledger / 105-dossier | Comparable, slightly lower raw breadth |
| Distinct URLs | 97–98 | 83-ledger / 81-dossier | Lower URL breadth |
| Distinct domains | 39 | 51-ledger / 50-dossier | Better source-family diversity |
| Exact-lens mappings | 377 | 371-ledger / 405-dossier | Comparable ledger depth; formatter increased valid many-to-many routing |
| Located records | Required | 100% | Pass |
| Dossier coverage | Not the comparison gate | 61 covered, 19 partially covered | Complete dispositions |

The new research fixes the prior bias-aware AMLO regression from 13 dossier records and
11 URLs. It is not unambiguously better than lean-v4: it trades some URL breadth for more
domain diversity, better bias structure, and complete evidence-environment reasoning.

Explicit prompts are no longer the research token hog. The reconnaissance and eight
chapter prompts together contain only about 108 thousand characters, yet provider input
was 5.06 million tokens. Of that, 4.39 million was cached. The next research optimization
must target model/tool/session context and invocation topology, not further deletion of
the short task instructions.

## Bias review quality

The one fresh no-search audit found every chapter reviewable and did not request another
research round because it was explicitly the terminal pass. Estimated defensible
evidence ranged from nine to twelve units per chapter; independent source-family estimates
ranged from seven to ten. Attribution risk was high for 1B and 7B and medium elsewhere.

The reviewer explicitly covered favorable/adverse search balance, closed-system silence,
open-system complaint volume, duplication, allegations versus findings, official-claim
independence, denominators/authority/baseline/shocks, and missing source types. All 128
bias-support references resolve to the compact ledger.

The deterministic precheck found one material handoff omission:
`missing_local_audit`. The fix should add a bounded local-disposition section to the
compact handoff. It should not replay 5,132 routed fact instances.

## Formatter quality and receiver behavior

The accepted formatter call produced a substantive structured message followed by an
empty final message. A last-message-only receiver would have lost the dossier. Recovery
now scans all completed structured agent messages, ranks validated linked content before
bias-support tie-breakers, restores exact evidence rows from the hashed ledger manifest,
and rejects fake support IDs. The final dossier has:

- 105 evidence records: 97 final and eight context;
- 81 distinct URLs and 50 domains;
- 405 valid evidence-to-lens mappings;
- 61 covered and 19 partially covered lenses;
- zero missing source locators;
- a full evidence environment with 19 valid supporting E-IDs.

This is the intended strict-producer/tolerant-consumer result: the producer attempted a
complete dossier; the receiver retained all usable material and repaired deterministic
serialization defects without inventing facts, mappings, or bias support.

## Judge results

| Chapter | New score | Confidence | Plausible range | Previous stage-3 score | Lean-v4 score | Manual review |
|---|---:|---:|---:|---:|---:|---|
| 1B | 5.0 | 55 | 4.5–6.0 | 5.0 | 6.5 | No |
| 2B | 6.0 | 78 | 5.5–6.5 | 7.5 | 7.0 | No |
| 3B | 4.5 | 82 | 3.5–5.5 | 4.0 | 4.0 | No |
| 4B | 5.0 | 82 | 4.5–6.0 | 5.0 | 5.0 | Attribution review |
| 5B | 5.5 | 68 | 5.0–6.0 | 5.5 | 5.5 | Attribution review |
| 6B | 5.5 | 78 | 4.5–6.5 | 6.0 | 5.5 | No |
| 7B | 4.5 | 65 | 3.5–5.5 | 3.5 | 3.5 | Attribution review |
| 8B | 6.0 | 81 | 5.5–7.0 | 6.0 | 5.5 | Attribution review |

The original two-point 2B reduction failed preflight audit because it gave directional
international-peace weight to domestic National Guard policing. The corrected judge
excluded those records under the chapter's international-conduct gate, credited AMLO's
truce proposal, Mexico's mediation posture and UN conduct, and declined to treat absence
of aggression as exemplary. The corrected 6.0 remains 1.5 points below the previous
stage-3 result and therefore still receives full-cohort score/order audit.

The one-point 7B increase rests on direct personal-nexus evidence: sampled false or
misleading presidential claims and personal pressure on a critical journalist, balanced
against lack of proof of personal enrichment or direction of family conflicts. This
respects the 7B personal-integrity boundary, but still merits the emitted attribution
review.

Direct strict schema validation initially rejected six otherwise substantive judge
outputs because supported and weak lens lists overlapped or contained descriptive text.
The production tolerant receiver normalized those lists without changing scores,
evidence, rationales, confidence, or bias assessments. All eight resulting judgments
validate and every cited decisive, contrary, and bias E-ID belongs to AMLO's projection.

## Judge token detail

| Chapter | Prompt chars | Input | Cached input | Output | Reasoning output |
|---|---:|---:|---:|---:|---:|
| 1B | 84,403 | 40,775 | 0 | 2,704 | 766 |
| 2B | 74,552 | 38,627 | 0 | 2,431 | 261 |
| 3B | 88,389 | 41,857 | 0 | 3,379 | 400 |
| 4B | 81,969 | 40,408 | 0 | 2,427 | 330 |
| 5B | 74,114 | 37,321 | 12,032 | 2,367 | 404 |
| 6B | 70,523 | 36,337 | 12,032 | 2,873 | 826 |
| 7B | 89,915 | 40,945 | 0 | 2,607 | 495 |
| 8B | 101,891 | 43,573 | 0 | 2,622 | 435 |

The full unchanged-cohort projection directories occupy 589 KB–1.249 MB per chapter.
The new anchor-reuse prompts occupy only 71–102 KB and completed all eight chapters in
one four-way parallel wave. This is the correct topology for a one-ruler rejudgment:
full evidence for the changed ruler, compact immutable outcomes for unchanged anchors.

## Optimization order

1. Add a compact local-disposition audit to reviewer handoffs.
2. Make all-action candidate recovery and tolerant lens normalization part of every
   accepted worker path, with no extra LLM repair call for deterministic defects.
3. Persist anchor-reuse rejudgment as a supported workflow rather than an experiment
   script, including strict identity and evidence validation.
4. Profile research invocation context beyond prompt text; 4.39M cached tokens are the
   dominant cost.
5. Carry the completed AMLO preflight audit into the full-cohort score/order audit.
6. After that audit, replace only AMLO in the preserved 2022 cohort and rerun/order-audit
   affected common-meter outputs before considering wider promotion.

## Verification

- `pytest -q tests/research`: passed.
- Ruff on all changed research modules and tests: passed.
- `git diff --check`: passed.
- Full `pytest -q`: completed with eight failures confined to
  `tests/sources/test_wikidata_heads_of_state_government_adapter.py`; each expected
  three staged cache observations and received zero. No failing test exercises the
  AMLO research, bias, formatter, judge, recovery, or profiling paths.
