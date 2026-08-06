# Local/Web-Separated 2022 Ten-Case Gate

Date: 2026-07-24  
Run: `separated-gate-2022-v1`

Curated artifacts:
`configs/evaluations/snapshots/local-web-separated-2022-ten-case-gate.tar.gz`  
Archive SHA-256:
`5d7fd4938a2f75d36958d936030a05c9e6254167ffd11b4e6cf0733c12196da6`

## Decision

The separated architecture passed the ten-case integration gate:

`local evidence builder → direct local judge package`

`web researcher → no-search review/continuation → formatter → web dossier`

`local judge package + web dossier → chapter judge`

The web researcher never received the full local package. Each initial or continuation
brief contained ruler/year scope, the selected chapter questions, reviewer-directed
gaps, and a bounded resource index. The formatter received the web notebook and ten
short local-disposition/provenance summaries. The judge received a bounded
chapter-specific selection derived from the complete hash-verified parent artifact,
together with the projected web dossier.

This is evidence that the architecture and handoffs work across all eight chapters. It
is not yet a production-promotion decision: seven chapters were singleton integration
cases, only Chapter 2B was judged as a comparative batch, and the full 20-ruler cohort
has not yet been rerun.

## Test design

The matrix covered every chapter and three contrasting international-peace cases:

| Case | Chapter |
|---|---|
| Xi Jinping | 1B |
| Vladimir Putin | 2B |
| Olaf Scholz | 2B |
| Félix Tshisekedi | 2B |
| Abdel Fattah el-Sisi | 3B |
| Sheikh Hasina | 4B |
| Andrés Manuel López Obrador | 5B |
| Joe Biden | 6B |
| Jair Bolsonaro | 7B |
| Nguyễn Phú Trọng | 8B |

Every case used the preserved prompt-D first pass, up to two compact
reviewer-directed web continuations, three no-search reviews with the last review
terminal, strict dossier formatting, direct local-package projection, and a validated
chapter judgment. The three 2B rulers were judged together on one common meter.
The committed archive preserves the source prompts, terminal reviews, final ledgers,
local judge packages, dossiers, projections, judge prompts/outputs, per-call usage
events, matrix results, and an internal 123-file SHA-256 manifest.

## Results

“Defensible” and “families” are the terminal no-search reviewer's estimates. Residual
themes are preserved uncertainties after the two allowed continuation rounds, not
failed lenses and not adverse ruler evidence.

| Ruler/chapter | Web initial → ledger → accepted | Defensible / families | Residual themes | Mappings | Local facts / signals | Score / confidence |
|---|---:|---:|---:|---:|---:|---:|
| Xi 1B | 14 → 32 → 30 | 27 / 15 | 4 | 92 | 5 / 0 | 4.5 / 72 |
| Putin 2B | 18 → 33 → 30 | 29 / 20 | 4 | 108 | 40 / 8 | 1.0 / 94 |
| Scholz 2B | 20 → 39 → 35 | 37 / 15 | 6 | 110 | 32 / 8 | 7.5 / 84 |
| Tshisekedi 2B | 14 → 30 → 30 | 27 / 12 | 10 | 100 | 40 / 8 | 5.0 / 78 |
| Sisi 3B | 15 → 35 → 32 | 25 / 11 | 6 | 118 | 79 / 16 | 3.0 / 79 |
| Hasina 4B | 18 → 39 → 36 | 36 / 12 | 10 | 136 | 135 / 23 | 3.0 / 86 |
| AMLO 5B | 18 → 35 → 35 | 31 / 13 | 5 | 120 | 98 / 14 | 5.5 / 82 |
| Biden 6B | 18 → 35 → 35 | 32 / 20 | 6 | 189 | 25 / 10 | 6.5 / 78 |
| Bolsonaro 7B | 16 → 33 → 25 | 25 / 11 | 6 | 97 | 35 / 7 | 2.5 / 91 |
| Nguyễn 8B | 12 → 33 → 30 | 29 / 10 | 4 | 97 | 29 / 5 | 6.0 / 79 |
| **Total** | **163 → 344 → 318** | — | — | **1,167** | **518 / 99** | — |

All ten dossiers passed substantive-yield, ledger-accounting, recovered-reference, and
strict schema validation after tolerant receiver normalization. Eight of ten formatter
outputs omitted one or more explicit lens mappings: the receiver inferred 45
lens-level mappings from explicit coverage references. The Scholz dossier also needed
one manifest-required fact restored from the accumulated notebook. These recoveries
preserved judgeable inputs, but they are producer defects that must be reduced and
retested before the full-cohort run. All judgments passed web-reference, local-reference,
calibration, lens, confidence-scale, evidence-envelope, and required bias-assessment
validation. No judgment required manual review merely because a lens remained sparse.

The judge used local evidence contextually and did not rewrite it as web evidence. The
local packages included exact observation identifiers, provenance, units, warnings,
and reconstructable longitudinal signals where available. Xi 1B correctly retained
only five older FAS facts and zero longitudinal signals rather than fabricating current
nuclear coverage.

## Token profile

These are provider-reported tokens. Research input includes the preserved prompt-D
first pass and both browser-enabled continuations. Browser/tool context and cached
material dominate researcher input; explicit continuation prompts were only about
10–23 KB.

| LLM phase | Input tokens | Output tokens |
|---|---:|---:|
| Web research, 30 calls | 19,154,134 | 223,947 |
| No-search evidence review, 30 calls | 1,658,809 | 70,320 |
| Strict dossier formatter, 10 calls | 633,861 | 160,416 |
| Chapter judge, 8 calls | 614,914 | 29,824 |
| **Total** | **22,061,718** | **484,507** |

The web researcher is now producing substantially broader and more defensible ledgers,
but it remains the dominant cost. Short prompts solved repository/local-package bloat;
they did not eliminate the large provider-side browsing context. The next optimization
should reduce redundant browser searching and repeated source opening while preserving
the terminal reviewer's measured source-family and defensible-evidence yield.

## Quality assessment

The web process is materially stronger than the preserved first pass:

- ledger records increased from 163 to 344;
- 318 records survived strict formatting;
- terminal reviewers estimated 25–37 defensible records per case;
- source-family breadth reached 10–20 families per case;
- every case retained favorable, adverse, attribution, period-fit, duplication, and
  information-environment analysis;
- residual gaps remained visible instead of forcing false completeness.

The local process is solid for the data actually available:

- local evidence is independently built and chapter-routed;
- 518 facts and 99 longitudinal signals reached judges directly;
- web researchers were not asked to recreate local time-series work;
- missing or historically thin local coverage reduced confidence or remained context,
  rather than becoming favorable evidence;
- incompatible concepts, units, and attribution roles remain separate.

Important limitations remain:

- the test reused the preserved prompt-D first pass rather than rerunning all ten first
  passes with the promoted prompt;
- the ten cases do not establish full-cohort calibration or score-order stability;
- several terminal reviews still list 4–10 unresolved themes;
- researcher cost is too high for an uncontrolled 20-ruler × 8-chapter production run;
- the formatter receiver recovered incomplete producer outputs in eight cases,
  including 45 inferred lens mappings and one restored Scholz fact; producer
  completeness requires a focused repair and rerun before the full cohort;
- source URLs and locators need a sampled human audit before production promotion.

## Promotion boundary

The local evidence builder and compact web-research architecture are ready for a
controlled full-cohort evaluation behind the existing feature flags. Production
promotion still requires:

1. sampled manual source/locator audits across all eight chapters;
2. formatter-producer repair and a repeated ten-case handoff gate showing materially
   fewer inferred mappings and no dropped manifest-required facts;
3. a complete 20-ruler 2022 comparative run with every chapter judged as a cohort;
4. old/new score, order, evidence-family, bias, local-use, drift, cost, and runtime
   audits;
5. explicit review of every score movement greater than one point;
6. unchanged-evidence rerun drift at or below the documented threshold;
7. confirmation that 7B preserves the personal-nexus boundary and 8B preserves the
   program/implementation/outcome distinction;
8. cost controls or an approved budget for browser-heavy research;
9. rebuilding and reviewing the 2022 viewer and attribution-bearing release artifacts.
