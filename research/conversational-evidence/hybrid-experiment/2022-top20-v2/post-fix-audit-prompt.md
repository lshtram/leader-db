Perform a short no-search post-fix release audit of the 2022 top-20 hybrid judgments.
Read `audit-v2.md`, `targeted-review.json`, the final judgment files under
`judgments-v1/{1B,2B,3B,4B,5B,6B,7B}/judgment.json`, and
`judgments-8b-v2/8B/judgment.json`.

Verify only:

1. all previously listed projection-integrity and recoverable-null flags were cleared
   through the recorded targeted review without score changes;
2. all eight batches now have zero `manual_review_required` cases;
3. there are still exactly 160 evaluations, 155 numeric scores, and five defensible
   nulls;
4. Chapter 1B has no score 1, Putin is 2.0, and the absolute realized-catastrophe floor
   remains respected;
5. the only score-1 cases are Putin in 2B and 4B, consistent with those rubrics;
6. no remaining issue blocks release.

Do not browse, alter artifacts, or reconsider scores unless the recorded correction is
internally inconsistent. Return concise Markdown with overall verdict, checks, any
remaining cautions, and release recommendation.
