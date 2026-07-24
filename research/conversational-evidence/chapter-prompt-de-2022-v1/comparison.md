# Deep-Chapter Prompt D/E Comparison

## Decision

Prompt E fails the promotion gate. Keep prompt D as the research-quality baseline and
move its useful inspection-state ideas into deterministic formatter/reviewer controls
rather than replacing D's substantive research instructions.

Across ten cases and two blinded presentation orders, D scored 8.675 versus 8.510 for
E. D remained ahead in both orders. E reduced output tokens by only 5.9% and evidence
records by 14.1%, while increasing total input tokens by 16.8%, non-cached input by
4.4%, and web-search events by 10.3%. Its median input was 4.9% lower, but its maximum
input rose from 1.117M to 2.671M, demonstrating worse runtime instability.

The main failure was substantive: E sometimes achieved compactness by omitting material
evidence rather than by removing duplication. This was most damaging for Bolsonaro,
Hasina, and Tshisekedi.

## Controls

- The same ten frozen cases cover every scored chapter.
- D reuses the already validated `gpt-5.6-sol` output from the A/D gate.
- E used fresh isolated `gpt-5.6-sol` sessions with live web search.
- D and E received the same ruler, period, guide, evidence-environment summary, and
  prior-web-resource index.
- Every E cell completed with live-search events, all ten question IDs, a terminal
  usage record, valid machine lines, and a nonempty output.
- Two no-search evaluators reversed D/E presentation order.

## Case results

Scores are the mean of the forward and reverse blinded evaluations.

| Case | Chapter | D score | E score | E−D | D input | E input | D output | E output | D records | E records |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMLO | 5B | 8.60 | 8.35 | −0.25 | 540K | 270K | 11.2K | 8.2K | 18 | 12 |
| Biden | 6B | 8.75 | 8.80 | +0.05 | 371K | 995K | 11.1K | 13.3K | 18 | 19 |
| Bolsonaro | 7B | 8.80 | 8.05 | −0.75 | 1,117K | 575K | 12.4K | 9.7K | 16 | 11 |
| Hasina | 4B | 8.75 | 8.35 | −0.40 | 478K | 483K | 11.9K | 10.2K | 18 | 13 |
| Nguyễn | 8B | 8.25 | 8.65 | +0.40 | 234K | 237K | 8.9K | 9.0K | 12 | 12 |
| Putin | 2B | 9.00 | 9.00 | 0.00 | 1,102K | 585K | 11.9K | 11.3K | 18 | 19 |
| Scholz | 2B | 8.75 | 8.55 | −0.20 | 770K | 2,671K | 12.7K | 14.0K | 20 | 18 |
| Sisi | 3B | 8.75 | 8.70 | −0.05 | 473K | 463K | 10.0K | 9.9K | 15 | 14 |
| Tshisekedi | 2B | 8.65 | 8.10 | −0.55 | 630K | 377K | 9.8K | 7.9K | 14 | 10 |
| Xi | 1B | 8.45 | 8.55 | +0.10 | 400K | 485K | 8.6K | 8.6K | 14 | 12 |
| **Mean / total** | — | **8.675** | **8.510** | **−0.165** | **6.117M** | **7.142M** | **108.6K** | **102.2K** | **163** | **140** |

## Order reversal

| Evaluator order | D mean | E mean | E−D |
|---|---:|---:|---:|
| Forward: D shown as X | 8.60 | 8.48 | −0.12 |
| Reverse: E shown as X | 8.75 | 8.54 | −0.21 |
| Combined | 8.675 | 8.510 | −0.165 |

The result is not explained by label position.

## Useful E features

E did improve several aspects of evidence engineering:

- explicit opened, partial, indexed-only, blocked, and uninspected states;
- `new_fact_contribution`, `source_dependencies`, and `evidence_status` fields;
- valid JSON for all 140 machine records;
- better discipline in the Nguyễn and Xi cases;
- less record proliferation in several cases; and
- a modest reduction in median input, output tokens, and record count.

These are useful controls, but they do not require replacing the research strategy.
They can be enforced when the formatter interprets a permissive notebook and when the
reviewer checks extraction status and duplication.

## Why E failed

- It omitted decisive later adjudication and direct ruler acts in the Bolsonaro case.
- It lost target-year political-freedom coverage for Hasina.
- It removed conflict scale, implementation, and end-state evidence for Tshisekedi.
- It lost important welfare trajectory and fiscal-buffer evidence for AMLO.
- It sometimes converted “be more atomic” into “collect fewer material facts.”
- It did not consistently improve inspection accuracy: some indexed or failed-fetch
  sources were still promoted too strongly.
- Strict source verification could trigger expensive additional browsing, most visibly
  in the 2.671M-token Scholz run.
- Its overall efficiency improvement was illusory: output became slightly shorter while
  total input and search activity increased.

## Next gate

Use D for the next research-only end-to-end test. Keep the researcher notebook
permissive and complete. Add E's safe inspection-state and dependency fields to the
compact no-search reviewer/formatter handoff, where they can be validated
deterministically without discouraging collection.

The next experiment should pass a D-produced chapter notebook through:

1. compact no-search evidence review;
2. a targeted continuation request when a material gap exists;
3. compact formatting combined with the parent-held local-evidence package; and
4. validation that structured local evidence remains separate from web research.
