# Reconnaissance Prompt A/C Experiment

Date: 2026-07-24  
Cases: Vladimir Putin (Russia, 2022) and Félix Tshisekedi (DRC, 2022)  
Model: `gpt-5.6-sol`

## Question

Can a hybrid prompt retain the natural-language prompt's research breadth while
restoring atomic evidence packaging, deduplication, and reasonable token use?

Variant A was the current executable prompt. Variant C was self-contained and written
in ordinary language. It used saturation instead of a numerical evidence ceiling,
required one underlying fact per evidence record, and separated fully extracted
evidence, opened corroboration, and uninspected leads.

## Controls

Both variants received the same ruler identity, target year, compact local briefing,
model, web access, and execution settings. Researchers ran from an empty working
directory with shell and file tools disabled and no project instructions available.
All four runs were fresh.

Two no-search assessments compared the outputs. The second reversed the anonymous X/Y
order to expose position effects.

## Results

| Ruler | Variant | Prompt characters | Output words | URLs preserved | Input tokens | Output tokens | Mean blinded quality |
|---|---|---:|---:|---:|---:|---:|---:|
| Putin | A, current | 6,916 | 1,303 | 12 | 259,045 | 4,934 | 8.15 |
| Putin | C, hybrid | 7,583 | 4,389 | 23 | 329,732 | 8,515 | 8.50 |
| Tshisekedi | A, current | 6,289 | 1,557 | 12 | 260,104 | 5,546 | 8.10 |
| Tshisekedi | C, hybrid | 6,942 | 4,663 | 24 | 327,238 | 9,005 | 8.65 |

`Input tokens` are cumulative model input during web research, including retrieved and
replayed context. They are not the initial prompt length.

## Quality Findings

Both blinded evaluations preferred C for both rulers.

C produced:

- 15 atomic Putin evidence records and 16 atomic Tshisekedi records;
- broader favorable, adverse, and contrary coverage;
- stronger information-environment analysis;
- explicit distinction between direct presidential decisions, shared implementation,
  state conduct, and external constraints;
- separate later-retrospective sections;
- separate corroboration and uninspected-lead lists;
- more actionable deeper-research questions.

Material additions included:

- for Putin: strategic reversals, mobilization, energy-system attacks, casualty
  underreporting, final economic performance, media exile, and the limits of available
  social-service evidence;
- for Tshisekedi: regional security diplomacy, displacement and service disruption,
  election preparation, free primary education, health capacity, anti-corruption
  auditing, and Indigenous-rights reform.

## Remaining Defects

C still needs downstream curation:

- several locators were broader than ideal;
- a minority of records relied too heavily on one source family;
- some corroborating entries were only prospective leads;
- a few causal or personal-attribution formulations were stronger than the cited
  source;
- one weakly evidenced topic was represented mainly to record a gap;
- output volume remained approximately 1.6-1.7 times A's output tokens.

These defects are materially smaller than B's repetition and resource-list inflation.

## Efficiency Against Variant B

| Ruler | B input tokens | C input tokens | Reduction |
|---|---:|---:|---:|
| Putin | 1,122,045 | 329,732 | 70.6% |
| Tshisekedi | 699,055 | 327,238 | 53.2% |

C retained the breadth advantage without reproducing B's runaway cumulative context.

## Decision

Variant C passes this prompt-level experiment and should replace the current
reconnaissance wording.

Promotion should preserve the exact tested principles:

1. explain the task without internal pipeline vocabulary;
2. embed all factual background the researcher needs;
3. use informational saturation, not a maximum evidence count;
4. preserve every credible source with an honest source state;
5. emit one atomic record per underlying fact;
6. require stable source details, period fit, attribution limits, contrary evidence,
   and source cautions;
7. separate extracted evidence, corroboration, and uninspected leads;
8. segregate retrospective evidence;
9. consolidate repeated facts;
10. finish with a concise deeper-research plan.

## Artifacts

- [`manifest.json`](manifest.json)
- [`Putin A`](putin/a/output.md) and [`Putin C`](putin/c/output.md)
- [`Tshisekedi A`](tshisekedi/a/output.md) and
  [`Tshisekedi C`](tshisekedi/c/output.md)
- [`Forward assessment`](evaluation/forward.md)
- [`Reverse-order assessment`](evaluation/reverse.md)

