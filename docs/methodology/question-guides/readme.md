# Question Guides

Each score-bearing manual/internet methodology question gets one guide file in
this directory. The guide is the shared contract for humans, `internet-research`
workers, and the `ruler-quality-judge` calibration worker.

Do not rely on ad hoc chat instructions once a question enters a vertical slice.
Create or update the question guide first, then run the smoke test, then refine
the guide from observed failures.

## File naming

Use lowercase question IDs with dots removed or replaced by hyphens:

- `3b-1-domestic-safety.md`
- `8b-3-effectiveness.md`

## Vertical-slice workflow

For each question:

1. Draft the question guide from `template.md`.
2. Select 5-10 rulers/country-years that cover clear high, middle, low, and edge
   cases.
3. Run `internet-research` evidence passes for each case. Researchers collect
   evidence only; they should not finalize comparative scores unless explicitly
   asked by the guide.
4. Run one `ruler-quality-judge` batch over all evidence records for that
   question/year or ruler-period set.
5. Persist only records that satisfy the cited-evaluation schema and required
   `answer_payload.calibration` fields.
6. Review the batch for score order, missing evidence, source balance, bias
   checks, and whether each score is justified against neighboring anchors.
7. Update the guide with lessons learned before using the question at larger
   scale.

## Required guide sections

Each guide must include:

- Question identity and registry context.
- What the question is and is not asking.
- Researcher instructions.
- Judge instructions.
- 1-10 scoring anchors.
- Required evidence and preferred source types.
- Bias and comparability checks.
- Required `answer_payload.calibration` values and any question-specific fields.
- Smoke-test ruler set.
- Acceptance checklist.

## Completion standard

A question guide is production-ready for small-batch use only after:

- The 5-10 case smoke test has been run.
- The judge batch output is internally coherent.
- At least one review pass has checked source quality and relative ordering.
- The guide has been updated to reflect observed failure modes.
