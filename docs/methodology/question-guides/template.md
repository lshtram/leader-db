# <Question ID> <Short Question Name>

Status: draft / smoke-tested / reviewed / active

## Question Identity

- `methodology_id`: `<for example 3B.1>`
- Category: `<category name>`
- Evidence strategy: `internet_manual`
- Rubric version: `<question_specific_v1>`
- Guide owner/status note: `<who last updated this and why>`

## Question Text

Copy the registry question text here.

## What This Question Asks

State the positive scoring direction in plain English. Explain what a high score
means and what a low score means.

## What This Question Does Not Ask

List common traps and nearby topics that should not drive this score.

Examples:

- Do not score by search-result volume.
- Do not score ordinary crime unless the question explicitly includes public
  safety beyond state/political violence.
- Do not use the client matrix as evidence.

## Researcher Instructions

The `internet-research` worker should collect cited evidence only. It should not
finalize comparative scores unless this guide explicitly allows it.

Research output should include:

- concise claims;
- source URLs, titles, and quotes;
- source roles, such as structured dataset, NGO, court/legal, media,
  intergovernmental, official, or academic;
- contrary evidence;
- target-year evidence separated from ruler-period evidence;
- caveats about missing, weak, stale, or regime-constrained evidence.

## Judge Instructions

The `ruler-quality-judge` receives all evidence records for the batch and applies
this guide to every ruler before finalizing scores.

The judge must:

- compare all supplied rulers before assigning final scores;
- use the same `rubric_version` and `calibration_batch_id` for the batch;
- fill every required `answer_payload.calibration` field;
- explain why each score is not one point lower or higher;
- preserve citations and contrary evidence;
- flag records for more research when evidence is insufficient.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | `<worst-case anchor>` |
| 2-3 | `<severe low-score anchor>` |
| 4-5 | `<mixed/weak middle anchor>` |
| 6-7 | `<moderately positive anchor>` |
| 8-9 | `<strong positive anchor>` |
| 10 | `<best-case anchor>` |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- A structured-source prior where available, or `not_available` with explanation.
- Narrative evidence that fits the target year or ruler period.
- Source-mix note explaining whether the record relies too heavily on one source
  type.

Preferred source types:

- `<source type 1>`
- `<source type 2>`
- `<source type 3>`

## Bias And Comparability Checks

The judge must complete these checks in `answer_payload.calibration`:

- `visibility_bias_check`
- `repression_silence_check`
- `population_scale_check`
- `source_type_check`
- `recency_check`
- `subagent_calibration_check`

Add question-specific bias checks here if needed.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `<question_specific_v1>`
- `severity_band`: `<allowed interpretation for this question>`
- `state_responsibility`: `<allowed interpretation for this question>`
- `accountability_level`: `<allowed interpretation for this question>`

Question-specific additional fields, if any:

- `<field>`: `<purpose>`

## Smoke-Test Ruler Set

Use 5-10 cases spanning the scale:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| `<ruler>` | `<country>` | `<year>` | `<high/mid/low/edge>` |

## Acceptance Checklist

- Research records include citations and source roles.
- The judge scored all smoke-test rulers in one batch or with overlapping anchor
  cases.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores are coherent relative to adjacent cases.
- `lower_anchor_rejected` and `higher_anchor_rejected` are substantive.
- Bias checks are specific, not boilerplate.
- Contradictory evidence and caveats are preserved.
- The guide was updated after the smoke test.
