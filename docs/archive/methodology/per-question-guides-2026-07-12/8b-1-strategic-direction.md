# 8B.1 Strategic Direction

Status: draft; not yet smoke-tested

## Question Identity

- `methodology_id`: `8B.1`
- Category: `ruler_effectiveness_and_competence`
- Evidence strategy: `internet_manual`
- Rubric version: `8b1_strategic_direction_v1`
- Guide owner/status note: initial ideology-neutral draft for guide expansion.

## Question Text

Does the ruler articulate a clear governing ideology, strategic direction, or
program, including explicit or revealed goals for power, policy, or regime
control, that can be evaluated against later action?

## What This Question Asks

Registry context: 8B is ideology-neutral. It evaluates whether the ruler can
define direction and execute their own declared or revealed program. A harmful or
repressive program can score strongly here while scoring poorly elsewhere.

Higher scores mean the ruler communicates a coherent, sufficiently specific and
stable hierarchy of policy, power, regime-control, or international goals that
permits later falsification and evaluation. Revealed goals may be used when
repeated choices establish them, but must be distinguished from speculation.
Lower scores mean no discernible stable direction, mutually incompatible
priorities, constant opportunistic shifts, or slogans too vague to evaluate. A
coherent strategy focused narrowly on immediate survival or regime control is
still a strategy and must be scored for clarity and evaluability without moral
penalty.

## What This Question Does Not Ask

- Do not judge whether the ideology or goal is moral, democratic, peaceful,
  popular, economically wise, or socially beneficial.
- Do not reward later implementation or outcomes; those belong mainly to
  `8B.2`-`8B.10`.
- Do not equate charisma, speech volume, propaganda sophistication, manifesto
  length, or authoritarian control with strategic clarity.
- Do not infer a coherent hidden goal from every action after the fact; revealed
  goals require repeated, discriminating evidence and contrary-action review.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Follow [`../local-first-researcher-guide.md`](../local-first-researcher-guide.md),
query exact-case local evidence, and apply
[`../source-confidence-registry.json`](../source-confidence-registry.json).
Governance indicators are context, not direct proof of strategic articulation.
Use approved Parallel Search for discovery, cite underlying sources, profile every
citation with the four required fields, and include the required `run_profile`.

## Researcher Instructions

Collect dated campaign platforms, manifestos, major speeches, government or party
programs, strategy documents, directives, and repeated private/revealed choices.
Extract the claimed goals, priority ordering, specificity, time horizon, target
institutions/populations, consistency, changes with explanations, and observable
tests. Seek contrary evidence: contradictory commitments, abrupt reversals,
personal improvisation, factional ambiguity, or retrospective rationalization.
Separate ruler-authored direction from inherited plans and subordinate rhetoric.
Do not score morality, execution, outcomes, or final comparative performance.

## Judge Instructions

Apply `8b1_strategic_direction_v1` across one batch. Judge clarity,
specificity, coherence, stability/adaptation, ruler ownership, and evaluability.
Do not downgrade reprehensible goals or upgrade benevolent aspirations. A changed
strategy can remain clear if the ruler explains new priorities after evidence or
shocks; incoherent opportunism cannot. Treat inferred goals cautiously and flag
cases where independent evidence cannot distinguish strategy from propaganda.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | No stable or evaluable governing direction: choices are chaotic, mutually contradictory, or purely reactive, and neither explicit nor rigorously evidenced revealed goals organize them. A coherent immediate-survival or regime-control strategy does not fit this anchor. |
| 2-3 | Mostly slogans, shifting claims, or weakly evidenced hidden aims; priorities are too contradictory or vague for meaningful later evaluation. |
| 4-5 | Some identifiable goals and themes, but hierarchy, specificity, ownership, consistency, or evaluability is materially weak. |
| 6-7 | A generally coherent program with identifiable priorities and tests, though important ambiguity, shifts, omissions, or competing goals remain. |
| 8-9 | Clear, coherent, specific, ruler-owned strategic direction across major domains, with disciplined prioritization and explainable adaptation. |
| 10 | Exceptional strategic clarity: explicit or rigorously evidenced goals, hierarchy, tradeoffs, time horizons, and success tests remain coherent under pressure and permit strong later evaluation. |

## Evidence Requirements

Minimum evidence: one citation, local-prior status, target/ruler-period evidence,
contrary evidence, and source-mix note. At least one primary programmatic source is
preferred; inferred goals require at least two independent evidence types and
must name the inference. Preferred sources: official platforms, manifestos,
speeches, strategy documents, directives, budgets only as corroboration;
party/coalition documents; archives and declassified records; legislative or
cabinet records; scholarly histories; reputable interviews and reporting.
Official texts are strong for what was declared, not for whether it was sincere or
implemented.

## Bias And Comparability Checks

Complete all common checks. Address documentation advantages of wealthy/open
states; propaganda volume in closed systems; oral/customary governing traditions;
translation; short caretaker terms; coalition constraints; crises; hindsight
construction of revealed goals; and whether moral approval or outcome knowledge
contaminated the clarity assessment.

## Required Calibration Values

Use every common calibration field; generic fields remain required even when
their fit is imperfect and should be interpreted explicitly.

- `rubric_version`: `8b1_strategic_direction_v1`
- `severity_band`: common enum, interpreted as extent of strategic incoherence
- `state_responsibility`: common enum, interpreted as ruler ownership/attribution
- `accountability_level`: common enum, interpreted as external testability and correction
- `program_clarity`: `none`, `low`, `partial`, `clear`, `exceptionally_clear`, or `unclear`
- `goal_basis`: `explicit`, `mostly_explicit`, `mixed_explicit_revealed`, `mostly_revealed`, `speculative`, or `unclear`
- `program_coherence`: `contradictory`, `fragmented`, `mixed`, `coherent`, `highly_coherent`, or `unclear`
- `evaluability`: `not_evaluable`, `weak`, `partial`, `strong`, `exceptional`, or `unclear`
- `program_domains`: list from `policy`, `regime_control`, `power_consolidation`, `international_influence`, `state_building`, `other`

## Smoke-Test Ruler Set

Plausible roles only; do not assign final scores in advance.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Lee Kuan Yew | Singapore | 1965-1990 | explicit long-horizon direction candidate; morality separation |
| Deng Xiaoping | China | 1978-1992 | revealed/pragmatic strategy and slogan-specificity edge |
| Margaret Thatcher | United Kingdom | 1979-1990 | ideologically explicit program candidate |
| Adolf Hitler | Germany | 1933-1939 | highly harmful goals; ideology-neutrality stress test |
| Donald Trump | United States | 2017-2020 | manifesto/revealed-goal coherence dispute |
| Boris Yeltsin | Russia | 1991-1999 | shifting priorities and crisis-context middle/low candidate |
| Volodymyr Zelenskyy | Ukraine | 2022 | external-shock and wartime adaptation edge |
| Liz Truss | United Kingdom | 2022 | very short tenure and explicit-program evaluability edge |

## Acceptance Checklist

- Local-first, source profiling, and run profiling are satisfied.
- Explicit and revealed goals are labeled and evidentially separated.
- Clarity is not conflated with morality, implementation, outcomes, charisma, or propaganda.
- Ruler ownership, priority hierarchy, tradeoffs, and time fit are assessed.
- Contrary actions and strategic changes are preserved.
- One batch judge completes all fields and substantive adjacent-anchor rejections.
- Smoke roles are tested, and the guide is revised before activation.
