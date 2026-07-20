You are the final score/order auditor for the Leaders Database 2022 top-20 hybrid run.
Do not browse, search, or modify evidence or scores. Read the local judgment artifacts:

- `research/conversational-evidence/hybrid-experiment/2022-top20-v2/judgments-v1/{1B,2B,3B,4B,5B,6B,7B}/judgment.json`
- `research/conversational-evidence/hybrid-experiment/2022-top20-v2/judgments-8b-v2/8B/judgment.json`
- the eight chapter guides in `docs/methodology/chapter-guides/`
- `docs/methodology/cited-evaluation-calibration.md`
- `src/leaders_db/conversational_evidence/hybrid_experiment/data/2022-judge-instructions.md`

Audit all 160 ruler/chapter evaluations for:

1. comparative ordering and obvious within-chapter inconsistency;
2. rubric drift or chapter contamination;
3. ruler attribution and inherited-baseline handling;
4. nulls, confidence, plausible ranges, and manual-review flags;
5. evidence-reference integrity and source-balance warnings visible in the judgments;
6. the absolute historical score floor, especially Chapter 1B: score 1 is reserved for
   actual nuclear detonation against people or a military target, or an equivalent
   realized nuclear catastrophe. Threats, escalation, aggression, arms buildup, or
   authoritarian repression alone cannot justify 1B=1.

Do not silently rewrite any result. Produce a concise Markdown audit with:

- overall verdict: pass, pass_with_cautions, or block;
- chapter-by-chapter verdicts;
- every blocking issue, if any, naming chapter and ruler;
- every material caution naming chapter and ruler;
- explicit confirmation of the 1B floor check and all score-1 cases across chapters;
- explicit review of every null;
- release recommendation and exact next actions.
