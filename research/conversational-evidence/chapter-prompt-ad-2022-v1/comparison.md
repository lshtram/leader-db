# Deep-Chapter Prompt A/D Comparison

## Decision

Prompt D is the stronger researcher, but it should not replace A unchanged.

Across ten matched cases and two blinded presentation orders, D scored 8.71 versus
8.59 for A. D scored higher in eight cases and lower in two. Its advantage appeared
in both evaluator orders, so it is not explained by whether D was labeled X or Y.

D's gain is real but expensive: it used 46.5% more total input tokens, 23.4% more
non-cached input tokens, 52.8% more output tokens, and produced 52.3% more evidence
records. The evaluators repeatedly found that D improved chapter coverage, authority
and baseline framing, contrary evidence, and source-state reporting, but also split
single reports into too many records and sometimes gave weakly inspected or later
sources too much weight.

The next version should therefore be a hybrid: retain D's natural assignment and
research breadth while restoring A's atomicity, locator discipline, contemporaneous-
source preference, and evidence-to-volume efficiency.

## Experimental controls

- Ten cases covered all eight scored chapters.
- Chapter 2B used three rulers with different attribution problems.
- Every A/D pair received identical frozen inputs and used fresh sessions.
- All twenty cells used `gpt-5.6-sol` with live web search and no repository access.
- Each artifact contains all ten question IDs and at least one live search.
- Every cell has a terminal usage record and a nonempty output.
- Two no-search evaluators saw the same ten pairs with X/Y order reversed.
- The evaluator assessed evidence quality, not ruler scores.

The initially rejected repository-leaking and non-browsing attempts are not included.

## Case results

Scores are the mean of the forward and reverse blinded evaluations.

| Case | Chapter | A score | D score | D−A | A input | D input | A output | D output | A records | D records |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMLO | 5B | 8.70 | 8.45 | −0.25 | 575K | 540K | 7.4K | 11.2K | 12 | 18 |
| Biden | 6B | 8.55 | 8.80 | +0.25 | 437K | 371K | 6.4K | 11.1K | 8 | 18 |
| Bolsonaro | 7B | 8.30 | 8.60 | +0.30 | 302K | 1,117K | 6.6K | 12.4K | 10 | 16 |
| Hasina | 4B | 8.55 | 8.75 | +0.20 | 414K | 478K | 7.5K | 11.9K | 10 | 18 |
| Nguyễn | 8B | 8.40 | 8.25 | −0.15 | 228K | 234K | 6.7K | 8.9K | 11 | 12 |
| Putin | 2B | 8.90 | 9.05 | +0.15 | 508K | 1,102K | 7.8K | 11.9K | 13 | 18 |
| Scholz | 2B | 8.65 | 8.90 | +0.25 | 403K | 770K | 6.9K | 12.7K | 10 | 20 |
| Sisi | 3B | 8.55 | 8.80 | +0.25 | 707K | 473K | 8.1K | 10.0K | 11 | 15 |
| Tshisekedi | 2B | 8.60 | 8.75 | +0.15 | 299K | 630K | 6.1K | 9.8K | 8 | 14 |
| Xi | 1B | 8.70 | 8.75 | +0.05 | 301K | 400K | 7.7K | 8.6K | 14 | 14 |
| **Mean / total** | — | **8.59** | **8.71** | **+0.12** | **4.175M** | **6.117M** | **71.1K** | **108.6K** | **107** | **163** |

One A record in the Tshisekedi artifact has malformed JSON; all 163 D records and the
other 106 A records parse successfully.

## Order-reversal result

| Evaluator order | A mean | D mean | D−A |
|---|---:|---:|---:|
| Forward: A shown as X | 8.50 | 8.56 | +0.06 |
| Reverse: D shown as X | 8.68 | 8.86 | +0.18 |
| Combined | 8.59 | 8.71 | +0.12 |

The different absolute levels show a modest first-position effect, but D remains ahead
under both label assignments.

## What D improved

- More complete treatment of all ten questions, especially secondary domains that A
  sometimes left thin.
- A clearer formal/practical authority baseline, inherited conditions, and external
  shocks.
- More favorable, adverse, exculpatory, and contrary evidence.
- Better searches for direct ruler acts and final adjudication.
- Better source-state and residual-gap reporting.
- Better structured end-state evidence for conflict, spending, implementation, and
  vulnerable groups.
- Perfect machine-line validity across 163 records.

The strongest D gains appeared for Biden, Bolsonaro, Hasina, Scholz, Sisi, and
Tshisekedi. D was only narrowly better for Putin and Xi.

## Where D regressed

- It often created several records from one annual report or underlying source.
- Some `fully_extracted` dispositions overstated what was opened when the researcher
  had only an indexed extract, landing page, or blocked PDF.
- Later retrospective evidence sometimes became too prominent.
- Some purportedly atomic records synthesized several sources or underlying facts.
- Additional context did not always materially discriminate ruler conduct.
- Output structure repeated detail already present in the machine records.
- Token cost was volatile: Bolsonaro and Putin D each exceeded 1.1 million input
  tokens.

AMLO and Nguyễn are the clearest cases where A's selectivity and locator discipline
outweighed D's additional breadth.

## Required hybrid changes

The next prompt should preserve D's natural-language framing and require:

1. the authority, inherited-baseline, shock, and information-environment orientation;
2. a scan of all ten questions and meaningful favorable, adverse, and contrary search;
3. direct ruler acts, material outcomes, and final findings where available;
4. explicit contemporaneous, immediate-retrospective, and later-adjudicative labels;
5. distinct opened-source, partial-page, indexed-text, blocked, and uninspected states;
6. one record per materially distinct underlying fact;
7. multiple records from one source only when each states the new fact it contributes;
8. synthesis in prose rather than multi-source “atomic” records;
9. page, paragraph, table, or section locators for accepted evidence; and
10. a compact human index with full detail only in valid machine records.

No fixed source or record quota should be introduced. The stopping rule remains
material saturation.

## Next gate

Create prompt E with those hybrid controls and compare it against D on the same frozen
ten-case matrix. Promotion into the score-bearing workflow should wait for that gate,
followed by compact reviewer-continuation and formatter handoff testing.
