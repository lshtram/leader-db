# Reconnaissance Prompt A/B Experiment

Date: 2026-07-24  
Cases: Vladimir Putin (Russia, 2022) and Félix Tshisekedi (DRC, 2022)  
Model: `gpt-5.6-sol`

## Question

Does a self-contained, natural-language prompt produce better reconnaissance research
than the current project-oriented prompt?

Variant A was the current executable prompt. Variant B explained the task in ordinary
language, removed unexplained pipeline vocabulary, removed the 8-15 evidence ceiling,
and used saturation as the stopping condition.

## Controls

For each ruler, both variants received the same identity, period, compact local
briefing, model, web access, and execution settings. Prompt sizes differed by about one
percent. Researchers ran from an empty working directory with shell and file tools
disabled, project rules unavailable, and no ability to inspect the repository.

The outputs were assessed twice without web research. The second assessment reversed
the anonymous X/Y order to test position bias.

## Quantitative Results

| Ruler | Variant | Prompt characters | Output words | URLs preserved | Input tokens | Output tokens | Mean blinded quality |
|---|---|---:|---:|---:|---:|---:|---:|
| Putin | A, current | 6,916 | 1,402 | 11 | 387,092 | 5,122 | 8.40 |
| Putin | B, natural | 7,000 | 4,162 | 40 | 1,122,045 | 9,579 | 8.75 |
| Tshisekedi | A, current | 6,289 | 1,656 | 21 | 256,117 | 5,583 | 8.20 |
| Tshisekedi | B, natural | 6,359 | 5,495 | 73 | 699,055 | 12,143 | 8.85 |

`Input tokens` are cumulative model input during the web-research turn, including
replayed context and retrieved material; they are not merely initial prompt tokens.

## Findings

### Variant B improved discovery and breadth

For Putin, B added material coverage of military-plan failure, the ICC warrant,
mobilization implementation, public-opinion limitations, NATO applications, diplomacy,
military expenditure, independent macroeconomic assessment, and contrary poverty data.

For Tshisekedi, B added substantial work on free primary education, the 145 Territories
program, EITI and extractive governance, electoral preparation, regional diplomacy,
Indigenous rights, and the conflict between conservation claims and hydrocarbon
auctions. It also inspected more underlying UN, IMF, EITI, UNDP, and World Bank
documents.

Both order-reversed evaluators preferred B. The advantage was narrow for Putin and
clear for Tshisekedi.

### Variant A remained better at packaging and efficiency

A produced compact atomic records with:

- canonical fact keys;
- explicit period fit;
- ruler-attribution limits;
- contrary evidence;
- clear accepted disposition;
- strong duplicate control;
- a concise gap list.

It also used much less cumulative research context. Relative to A, B used:

- 2.90 times the input tokens and 1.87 times the output tokens for Putin;
- 2.73 times the input tokens and 2.18 times the output tokens for Tshisekedi.

### Variant B introduced manageable defects

B sometimes:

- repeated facts across the overview, main findings, resource list, limitations, and
  source inventory;
- mixed fully extracted evidence with sources that were only discovered;
- used later retrospective evidence too prominently;
- grouped several underlying facts into one long finding;
- used broad locators for a minority of sources;
- made attribution or causation wording slightly stronger than the supporting source;
- preserved more material than a later researcher should have to read in full.

These are curation and output-contract problems, not evidence-discovery failures.

## Decision

The experiment supports replacing the current reconnaissance language with a hybrid
prompt based on Variant B's natural explanation and saturation behavior while retaining
Variant A's evidence packaging.

The production candidate should:

1. explain the research objective without internal pipeline terminology;
2. include the full set of relevant subject areas in ordinary language;
3. preserve every credible, potentially useful source;
4. stop on diminishing informational returns rather than an evidence-count ceiling;
5. distinguish:
   - opened and fully extracted evidence;
   - opened corroborating material;
   - discovered leads still needing inspection;
6. require one atomic underlying fact per developed evidence record;
7. require a stable locator, period fit, attribution limits, contrary evidence, and
   source caution for every developed record;
8. consolidate repeated facts before returning;
9. segregate later retrospective evidence;
10. finish with a compact, actionable deeper-research plan.

## Promotion Recommendation

The result is strong enough to draft and test the hybrid prompt. It is not yet enough
to promote B unchanged because its token cost and repetition are material. The next
experiment should compare the current prompt with the hybrid prompt on the same two
rulers and determine whether the hybrid retains B's breadth while reducing cumulative
input use and output volume.

## Artifacts

- [`manifest.json`](manifest.json)
- [`Putin A prompt`](putin/prompt-a.txt) and
  [`output`](putin/a/output.md)
- [`Putin B prompt`](putin/prompt-b.txt) and
  [`output`](putin/b/output.md)
- [`Tshisekedi A prompt`](tshisekedi/prompt-a.txt) and
  [`output`](tshisekedi/a/output.md)
- [`Tshisekedi B prompt`](tshisekedi/prompt-b.txt) and
  [`output`](tshisekedi/b/output.md)
- [`Forward blinded assessment`](evaluation/forward.md)
- [`Reverse-order blinded assessment`](evaluation/reverse.md)

