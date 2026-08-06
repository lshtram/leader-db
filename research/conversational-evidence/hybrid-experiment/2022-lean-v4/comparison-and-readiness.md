# Improved 2022 run: comparison and release readiness

## Outcome

The improved run is complete for all 20 rulers and all eight comparative chapters.
Every evidence dossier passed no-search review, every judgment was made on a common
20-ruler chapter meter, and the final score/order audit found no required score change.

## Evidence and cost versus the prior 2022 release

| Measure | Prior top-20 v2 | Improved accepted cohort | Change |
|---|---:|---:|---:|
| Accepted claims | 2,062 | 2,386 | +324 (+15.7%) |
| Distinct-URL sum by ruler | 1,686 | 1,947 | +261 (+15.5%) |
| Evidence model cost | $41.59 | $48.48 | +$6.89 (+16.6%) |
| Mean evidence cost per ruler | $2.08 | $2.42 | +$0.34 |
| Cumulative evidence model time | 25.7 h | 28.3 h | +2.6 h (+10.1%) |

The mean remains well below the approved $5 ceiling. The cost increase is almost
proportional to the increase in accepted, deduplicated evidence rather than a return to
the expensive saturation workflow. Seventeen rulers used the lean flow; the three
preserved saturation dossiers were Putin, Biden, and Tshisekedi.

The valid eight-judge run cost $1.73. Three initial three-item-per-lens judge attempts
exhausted context and reported no billable usage; those artifacts are preserved. Their
two-item-per-lens retries completed without a scale break, as confirmed by the final
auditor.

## Quality findings

- Evidence review retained credible gaps instead of filling quotas. Personal-integrity
  chapter 7B was the most common limitation, reflecting the difficulty of proving a
  ruler's own honesty from institutional or self-reported material.
- Review now deterministically derives the whole-ruler disposition from chapter
  decisions, resumes terminal review after a saved follow-up, and converts any forbidden
  second follow-up request into a documented credible gap.
- Conversion now merges duplicate canonical source-locator-claim facts before judging,
  preserving the first stable item and remapping its lens coverage.
- The final judgments contain 160 evaluations: 156 numeric scores and four explicit
  nulls. The nulls are Ethiopia, Turkey, and Vietnam in 1B and China in 7B. The auditor
  found each genuinely unscorable from the supplied ruler-attributed record; none was
  converted into a low score.
- Chapter 1B uses no score 1; its minimum numeric score is 2. The only score-1 cases are
  Putin in 2B and China and Putin in 4B, which the auditor found rubric-consistent.
- Five projection-reference warnings were reviewed and cleared without score changes.
  All final `manual_review_required` flags are false.

## Judgment comparison

Compared with the prior release, 103 of 160 cells changed. Across the 152 ruler/chapter
pairs numeric in both versions, mean absolute change was 0.49 points. The null set also
became more evidence-specific: numeric scores were recovered for COD, Egypt, and the
Philippines in 1B and Nigeria in 2B, while Turkey and Vietnam in 1B and China in 7B moved
to null because direct ruler attribution was insufficient. Ethiopia 1B remained null.

This amount of movement is larger than pure rerun noise observed in the earlier
controlled tests, but it should not all be attributed to evidence volume: the common
meter was rerun and the improved workflow applies stricter attribution and sparse-
evidence rules. The release is therefore best understood as a new, audited 2022
judgment version, not a mechanical patch to the old scores.

## Release decision

Ready. The score/order auditor returned `targeted_review`; all nine flagged cases were
resolved through recorded unchanged-score or retained-null clearances. No remaining
issue blocks use of `viewer-judgments.json` as the improved 2022 selection.

Focused conversational-evidence tests, Ruff, and diff checks pass. The repository-wide
test run reached completion but retained eight unrelated failures in the Wikidata heads-
of-state/government offline fixture tests, all returning zero staged observations; no
code changed in that adapter during this run.
