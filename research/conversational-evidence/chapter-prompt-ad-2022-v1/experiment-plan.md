# Deep-Chapter Prompt A/D Gate

## Purpose

Compare the current executable deep-chapter research prompt (A) with a refined,
natural-language prompt (D). The comparison tests research quality, evidence
engineering, and token use before any prompt is promoted.

## Cases

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

The matrix covers every scored chapter. Chapter 2B has three rulers to test whether
the prompt behaves consistently across aggressor-attribution, coalition/shared
authority, and conflict-exposure cases.

## Controlled execution

Each A/D pair must use:

- the same model and model settings;
- fresh, independent sessions;
- the same frozen ruler, chapter, reconnaissance, guide, and prior-resource inputs;
- a working web-browsing tool;
- no repository access or project instructions beyond the supplied prompt; and
- complete event logs and token usage.

Outputs must be evaluated blind in both presentation orders. Evaluation covers all-ten-
lens material coverage, source authority and diversity, stable locators, period fit,
ruler attribution, baseline and shocks, contrary research, dependency and duplicate
handling, honest gaps, reusable atomic records, and efficiency.

## Execution status

All twenty valid cells completed with `gpt-5.6-sol`, live web search, isolated working
directories, and terminal token records. Two no-search blind evaluations completed
with the artifact order reversed. See `comparison.md`, `metrics.csv`, and
`metrics-summary.json`.

The first execution attempt was rejected because sessions inherited repository rules.
A second attempt was rejected because the fallback model had no web tool and generated
records from prior knowledge. Those rejected attempts are not experiment results.
