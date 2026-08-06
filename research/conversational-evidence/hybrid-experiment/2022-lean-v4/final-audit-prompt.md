Perform a no-search release audit of the improved 2022 20-ruler judgments.

Read:

- `judge-instructions.md`;
- `judge-inputs-v1/conversion-report.json`;
- `judge-compact-v1/compaction-report.json` and `judge-compact-v2/compaction-report.json`;
- all eight `judgments-v1/{1B,...,8B}/judgment.json` files;
- the relevant compact projection whenever an evaluation is null or has
  `manual_review_required=true`.

Check:

1. exactly 20 evaluations per chapter and one common comparative meter;
2. score ordering and anchor consistency within each chapter;
3. ruler attribution, contrary evidence, temporal fit, and sparse-evidence handling;
4. every null and every manual-review flag, distinguishing a genuinely unscorable case
   from missing evidence that should only reduce confidence;
5. Chapter 1B's exceptional floor: score 1 only for realized catastrophic conduct
   comparable to the absolute historical worst cases, never merely possession, threats,
   opacity, proliferation risk, or weak disarmament;
6. any score-1 assignment in other chapters against its rubric;
7. whether the two-item retries for 3B, 6B, and 8B remain comparable to the three-item
   judgments for the other chapters.

Do not browse or alter files. Return concise Markdown with verdict (`pass`,
`targeted_review`, or `block`), exact flagged chapter/ISO3 cases, whether each existing
score can be cleared unchanged, and specific bounded corrections if required. Do not
invent replacement scores without support in the supplied projections.
