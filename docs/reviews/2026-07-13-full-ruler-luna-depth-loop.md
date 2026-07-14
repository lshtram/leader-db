# Full-ruler Luna depth and review loop — 2026-07-13

## Scope

This controlled experiment returned to the normative unit: one persistent
researcher for one resolved ruler-period across all eight chapters. The case was
Jacinda Ardern, New Zealand, 2020, using the same original eight chapter discovery
packets and local priors as the earlier Luna benchmark. This controls for the
candidate pool while testing a deeper research contract.

Only Luna was used for model work. One fresh Luna session owned the ruler research
through every continuation. A second fresh Luna session acted as an independent
evidence reviewer. Neither session formatted JSON or assigned ruler scores.

The tested sequence was:

1. one full-ruler researcher inventories all supplied candidates, builds a global
   evidence register, and audits every chapter;
2. an independent reviewer assigns item-level `accept`, `revise`, `merge`,
   `context-only`, or `reject` dispositions and produces chapter gap requests;
3. the same researcher session revises the complete notebook;
4. the reviewer re-audits it;
5. a bounded cleanup/confirmation pair tests whether more rewriting adds value;
6. the parent runs three reviewer-guided searches for the weakest themes (`1B`,
   `2B`, and `5B`), and the same researcher inspects all 30 new candidates;
7. the same reviewer audits the final continuation.

The depth contract counted distinct source-claim units rather than headings or
records. Empty priors could not count, same-URL splits were normally limited to
one or two, post-period material was context unless it established a 2020 fact,
and each chapter had to report source/locator diversity plus candidate rejections.

## Evidence result

The initial researcher produced 30 raw global records. Review and revision reduced
the coherent dossier to 26 retained units, of which 22 were defensible/usable and
four were explicitly context-only. The targeted discovery round inspected 30 new
candidates and accepted only three:

- `E-31`: a qualified, partisan 2019 military-deployment precedent for `2B`;
- `E-32`: strong official New Zealand Treasury evidence on 2020 fiscal allocations,
  wage subsidies, income support, forecasts, and stabilization mechanisms;
- `E-33`: contemporary contrary evidence on poverty/material hardship, retained
  with partisan-source and attribution limitations.

The final independently audited global result is **29 retained units, 25
defensible/usable units, four context-only units, and 25 unique locator families**.
The reviewer found no unapproved locator and no scoring. Country-level evidence
was generally separated from personal Ardern conduct.

| Chapter | Defensible mappings | Unique locator families | Evidence quality |
|---|---:|---:|---:|
| 1B | 0 direct | 1 contextual | 1/10 |
| 2B | 2 | 2 | 3/10 |
| 3B | 8 | 7 | 7/10 |
| 4B | 8 | 8 | 7/10 |
| 5B | 8 | 7 | 6/10 |
| 6B | 11 | 10 | 7/10 |
| 7B | 5 | 4 | 5/10 |
| 8B | 12 | 11 | 7/10 |

The targeted round materially improved `5B`, `6B`, and `8B`, through the Treasury
record and contrary poverty evidence. It only marginally improved `2B` and did not
improve `1B`: the new nuclear material was from 2022 and was correctly rejected for
the 2020 target. This is the desired behavior. A sparse chapter is better than a
padded one.

The chapter mapping total is 54 because one stable evidence unit may properly
inform several chapters. It is not 54 independent sources.

## What the reviewer changed

The reviewer was useful for substantive discipline:

- it separated national/institutional context from ruler-attributable action;
- demoted post-period, reputational, tertiary, and headline-only material;
- preserved intelligence, rights, poverty, housing, and implementation contrary
  evidence;
- identified artificial same-source independence and bundled claims;
- converted thin chapters into explicit gap reports rather than count-compliant
  evidence.

Repeated rewriting was not useful. The bounded cleanup and confirmation pair added
no evidence, cost 485,079 tokens, and still left mechanical chapter-count errors.
The final targeted handoff also overstated three chapter counts; the reviewer
corrected them immediately. Counts and ID reconciliation should therefore be done
by deterministic parent code or a very small formatter, not by the researcher.

## Usage and estimated cost

All eight Luna turns in the exploratory sequence, including deliberately redundant
cleanup/confirmation and final audit, consumed:

| Metric | Total |
|---|---:|
| Input tokens | 1,506,236 |
| Cached input tokens | 862,208 |
| Uncached input tokens | 644,028 |
| Output tokens | 141,796 |
| Reasoning output tokens | 23,535 |
| Total tokens | 1,648,032 |
| Parallel Search calls | 3 |
| API-equivalent cost range including search | $1.596–$2.235 |
| Codex-credit equivalent | 39.526 |

The total is reproducible from the trusted per-turn event logs as follows. Costs
exclude search in each row; the final total adds three searches × $0.005 = $0.015.
`Long range` means the turn's aggregate input exceeded Luna's 272,000-token
threshold, so the upper estimate applies the long-context/cache-write rates.

| Trusted event log | Role | Input / cached | Output | Total tokens | Pricing treatment | USD lower–upper |
|---|---|---:|---:|---:|---|---:|
| `research-initial-events.jsonl` | researcher | 55,752 / 0 | 13,906 | 69,658 | standard/cache-write range | $0.139188–$0.153126 |
| `review-initial-events.jsonl` | reviewer | 65,939 / 7,936 | 3,748 | 69,687 | standard/cache-write range | $0.081285–$0.095785 |
| `research-revision-events.jsonl` | researcher | 128,078 / 55,040 | 22,694 | 150,772 | standard/cache-write range | $0.214706–$0.232965 |
| `review-final-events.jsonl` | reviewer | 143,718 / 73,216 | 8,092 | 151,810 | standard/cache-write range | $0.126376–$0.144001 |
| `research-cleanup-events.jsonl` | researcher | 211,342 / 126,464 | 30,983 | 242,325 | standard/cache-write range | $0.283422–$0.304642 |
| `review-confirmation-events.jsonl` | reviewer | 233,341 / 150,784 | 9,413 | 242,754 | standard/cache-write range | $0.154113–$0.174753 |
| `research-targeted-continuation-events.jsonl` | researcher | 322,849 / 209,152 | 41,544 | 364,393 | Long range | $0.383876–$0.699969 |
| `review-targeted-events.jsonl` | reviewer | 345,217 / 239,616 | 11,416 | 356,633 | Long range | $0.198059–$0.414670 |
| **Model subtotal** | — | **1,506,236 / 862,208** | **141,796** | **1,648,032** | — | **$1.581025–$2.219911** |
| **Plus three searches** | — | — | — | — | $0.015 | **$1.596025–$2.234911** |

Actual subscription billing is not exposed. The range uses the checked-in pricing
snapshot. The two targeted continuation turns crossed the aggregate long-context
threshold; because one Codex turn may contain hidden provider requests, standard
and long-context/cache-write interpretations form the lower and upper bounds.

The primary researcher consumed 827,148 tokens and the reviewer consumed 820,884.
An unconditional reviewer loop therefore nearly doubles model usage.

The useful production-shaped subset is much smaller: exactly
`research-initial-events.jsonl`, `review-initial-events.jsonl`,
`research-targeted-continuation-events.jsonl`, and three targeted searches. Using
those observed calls as an upper-bound proxy, that sequence consumed 503,738 model
tokens and costs **$0.619349–$0.963880**, including $0.015 of search, before
deterministic formatting. The final benchmark reviewer is valuable for evaluating
the method but should not run for every production ruler.

## Comparison

| Design | Primary researchers | Total model tokens | Defensible evidence result | Main limitation |
|---|---:|---:|---:|---|
| Earlier all-chapter Luna research pass | 1 | 915,368 research tokens | 15 published items | shallow promotion and weak chapter accounting |
| Eight chapter-only Luna researchers | 8 | 257,849 | about 29 defensible units | count inflation and repeated corpus use |
| Full exploratory Luna depth/review loop | 1 + reviewer | 1,648,032 | 25 defensible units | too many review/rewrite turns |
| Recommended conditional loop | 1 + one conditional reviewer | about 503,738 observed-proxy tokens | expected near final 25-unit result | requires persistent-session production support |

The full-ruler design can produce a substantially better dossier than the earlier
single pass while preserving ruler familiarity. It does not need eight primary
researchers. The cost-effective mechanism is one adversarial review followed by
new targeted evidence and one revision—not repeated prose cleanup.

## Recommended production sequence

1. **Initial persistent researcher:** inventory the chapter packets and local priors,
   produce one global source-claim register, and report chapter diversity/gaps.
2. **Deterministic parent QA:** reconcile IDs and mappings; flag empty priors,
   same-URL splits, equivalent URLs, post-period items, below-floor chapters, and
   weak locator/source diversity.
3. **Conditional Luna evidence reviewer:** run only for substantive QA flags or a
   sampled audit. It cannot search, score, or format; it returns item dispositions
   and prioritized missing themes.
4. **Bounded parent discovery:** search only the weakest high-value themes. Preserve
   every exact packet and search cost.
5. **Same researcher continuation:** resume the original session once with the
   reviewer brief and new exact candidates; return a complete replacement notebook.
6. **Deterministic reconciliation and cheap formatting:** compute counts from links,
   normalize serialization, and never ask the researcher to fix mechanical syntax.

The current production worker does not yet implement this exact sequence. It runs
the schema-light notebook and formatter, while its legacy targeted continuation
starts a new strict-schema Codex invocation rather than resuming the original
research thread. Persistent researcher-thread capture/resume, conditional reviewer
execution, and pre-format targeted continuation are the next implementation gap.

## Artifacts

All prompts, trusted Codex event logs, initial/revised/final notebooks, reviewer
audits, targeted discovery packets, and the usage manifest are under
`data/outputs/research/full-ruler-nzl-2020-luna-depth-loop-v1/`.
