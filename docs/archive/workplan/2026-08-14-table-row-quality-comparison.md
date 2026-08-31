# Table-row quality comparison — 2026-08-14

## Decision

The bounded comparison **passed**. Exact table rows may proceed to one downstream-boundary
integration experiment. This result does not integrate the representation with production
and does not change whole-unit fact discovery.

## Frozen inputs and method

The comparison reused the Task 1 Labour Force Survey slice and verified both the extraction
SHA-256 and predecessor verified-evidence SHA-256 before constructing the request. The
request contained 38 exact physical lines from units 236, 238, and 240: source and year,
the necessary table and English column headers, population labels, the percentage label,
and the three employment-rate rows. Each line retained its source ID, unit, Unicode
code-point offsets, UTF-8 SHA-256, and exact source substring.

Whole-unit fact discovery was not changed. One `gpt-5.6-sol` call used the Codex subscription
surface. There was no API-key use, retry, correction call, repair, or re-review. The saved
event log contains exactly one completed turn.

## Result

The model result correctly reported:

- 60.1% employment for the total population aged 15 and over in owner-occupied dwellings;
- 71.9% for the same age population in the rented-dwelling `Total(2)` column;
- 65.7% for the Jewish population aged 15 and over in the overall `Total(1)` column; and
- 49.2% for the Arab population aged 15 and over in the overall `Total(1)` column.

It identified the statistic as the employment rate and the unit as percent, distinguished
the population-total and dwelling-tenure columns, and stated that the table is descriptive
and provides no ruler-specific causal attribution. Every cited line ID resolves to the
frozen source and the value fields cite their exact data rows.

The first deterministic evaluation displayed a rejection because its validator searched
for `Jewish` and `Arab` in the column-name field. Those are population labels, while the
correct column label is `Total(1)`. The validator was corrected to evaluate population and
column fields separately and the unchanged model output was re-evaluated. This was a code
validation correction, not another model pass or a change to the result.

## Size and usage

- Exact citation characters: 2,780.
- Like-for-like paragraph baseline: 39,620 characters.
- Citation-text reduction: 93.0%.
- Complete serialized request comparison, including fixed instructions, line labels, and
  response schema: 5,865 versus 42,705 characters, an 86.3% reduction.
- Preflight estimate: 1,324 input tokens and a 4,000-token maximum planned output quota.
- Reported Codex usage: 18,774 input, 0 cached input, 572 output, including 86 reasoning
  output tokens. The difference from the prompt-only estimate reflects execution-envelope
  overhead exposed by the Codex event record.

## Artifacts and verification

The immutable diagnostic directory is
`research/runs/netanyahu-2023-cost-opt-step11-table-row-quality-v1/`. It contains the exact
prompt, strict response schema, output, event log, stderr, and a manifest binding the Task 1
measurement, extraction, predecessor, configuration, prompt, output, line spans, usage, and
gate decision.

Focused Task 1 and Task 2 tests pass, scoped Ruff passes, and the change received an
independent read-only review. Task 3 is now the next permitted task, but was not begun in
this session.
