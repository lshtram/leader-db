# Random 2025 twelve-guide dossier smoke — 2026-07-12

> Historical failure analysis. This run motivated the later eight-chapter-guide
> design and permissive normalization of harmless LLM handoff formatting.

## Scope and selection

A deterministic random draw (`guide-smoke-2026-07-12`) selected 2025 from the
eligible 2018–2025 years and three of 96 eligible resolved ruler-year rows:

- Abdulla Aripov / Uzbekistan (`ruler_year_id=19243`);
- Roosevelt Skerrit / Dominica (`ruler_year_id=19285`);
- Philip "Brave" Davis / Bahamas (`ruler_year_id=19072`).

Each Luna dossier job covered the 12 new draft guides: `1B.1`, `1B.2`, `2B.1`,
`2B.2`, `5B.1`, `5B.2`, `6B.1`, `6B.2`, `7B.1`, `7B.2`, `8B.1`, and `8B.2`.
Each case received a parent-supplied, period-bounded discovery artifact and was
allowed one repair attempt. This was an evidence-only guide-validation run; no
scores were assigned.

## Execution result

| Case | Outcome | Evidence | Mappings | Input tokens | Cached input | Output tokens | Active wall time |
|---|---|---:|---:|---:|---:|---:|---:|
| Skerrit / DMA | failed semantic validation | 6 | 23 | 800,889 | 651,008 | 23,070 | 452 s |
| Aripov / UZB | failed semantic validation | 3 | 14 | 632,061 | 519,168 | 26,631 | 509 s |
| Davis / BHS | failed semantic validation | 4 | 18 | 909,378 | 760,832 | 27,773 | 530 s |

Usage is cumulative across both attempts. All six attempts produced parseable
JSON, but none published a valid v2 dossier. The repair prompt receives the
prior candidate but not the exact validation error, so each repair preserved the
same class of defect:

- Skerrit: coverage IDs lacked mappings to the same methodology for `5B.2`,
  `6B.1`, and `8B.1`;
- Aripov: `7B.2` was `no_evidence_found` while citing `E003`;
- Davis: coverage IDs lacked same-question mappings for `5B.1` and `5B.2`.

This is a harness defect, not a reason for unbounded retries. Exact validator
diagnostics must be supplied to repair, and deterministic reference
normalization should be considered before another multi-question run.

## Independent quality review

The candidates contain useful research but are not acceptable judge handoffs.

Exposure rules were applied inconsistently. All three cases lacked meaningful
nuclear authority/rhetoric and material conflict exposure, yet outputs used
`no_evidence_found` instead of the guides' `not_applicable` disposition. Routine
international cooperation was treated as partial `2B.1` diplomacy despite no
material crisis choice point. `1B.1` itself still needs an explicit no-exposure
disposition.

Ruler attribution is the largest case-level problem. The Uzbekistan program
evidence largely describes President Mirziyoyev's priorities; Aripov presented
the Cabinet program but should not automatically be treated as the independently
decisive ruler. This case needs identity/authority quarantine or a shared-
attribution cap before research proceeds.

Mapping relevance was too permissive:

- none of the three `5B.2` partial-coverage findings directly established the
  selection, competence, autonomy, or empowerment of economic professionals;
- Davis's organ-transplant allocation evidence was incorrectly reused as
  truthfulness/error-correction evidence;
- proposed oversight and whistleblower bills do not alone establish treatment
  of truth-tellers or a sustained truthfulness pattern;
- a journalism-training event with no Aripov attribution should not be ruler
  evidence;
- a 2006 Skerrit speech is context, not supporting evidence for 2025;
- IMF conclusions concern the government collectively and require careful
  personal attribution.

All mappings were `supports` or `context`; no candidate used `contradicts` or
`mitigates` despite contrary material inside evidence records. This makes the
judge handoff directionally biased.

## Discovery assessment

The random low-visibility cases exposed the search bottleneck. Dominica had the
best packet through its 2025 IMF report and budget material, but contained
duplicate and lower-quality sources. Bahamas had only two useful sources, both
from the prime minister's office. Uzbekistan had one useful program source,
plus a roster and weakly relevant material. A ten-result discovery packet is not
enough merely because it has ten URLs; source-role and theme coverage need a
parent-side sufficiency gate before launching an expensive worker.

## Decision

The 12 guides remain drafts. This smoke test is valuable but unsuccessful:
zero of three dossiers published, total input exceeded 2.34 million tokens, and
substantive exposure, attribution, and relevance rules drifted. Before rerunning:

1. pass exact semantic-validation diagnostics into repair prompts;
2. add deterministic coverage/mapping reference checks or normalization;
3. add an explicit `1B.1` no-exposure disposition;
4. enforce question-specific exposure and evidence-eligibility rules in the
   dossier prompt/schema, not only in long guide prose;
5. quarantine or cap shared/incorrect ruler authority before research;
6. require parent discovery sufficiency by evidence theme and source type;
7. reject `5B.2`, `7B.1`, and `7B.2` mappings without their guide-specific
   minimum evidence dimensions.
