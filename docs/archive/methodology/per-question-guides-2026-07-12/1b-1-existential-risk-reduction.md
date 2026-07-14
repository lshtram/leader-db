# 1B.1 Existential-Risk Reduction

Status: draft

## Question Identity

- `methodology_id`: `1B.1`
- Category: `nuclear_global_existential_responsibility`
- Evidence strategy: `internet_manual`
- Rubric version: `1b1_existential_risk_reduction_v1`
- Guide owner/status note: initial draft for multi-ruler smoke testing.

## Question Text

Did the ruler seek to reduce nuclear or other existential risk, rather than
increase prestige, leverage, or personal power through escalation?

## What This Question Asks

This question scores the ruler's demonstrated direction of policy and conduct:
whether they reduced catastrophic nuclear or comparable existential risk, or
deliberately increased it for political advantage. Higher scores require
credible restraint, de-escalation, risk-reduction measures, or strengthening of
protective institutions. Lower scores reflect deliberate escalation, dangerous
capability expansion, erosion of safeguards, or exploitation of catastrophic
risk for prestige, leverage, regime survival, or personal power.

Assess choices relative to inherited capability, authority, threat environment,
and realistic alternatives. A non-nuclear ruler may still act responsibly or
irresponsibly through proliferation policy, alliance decisions, diplomacy, and
other catastrophic-risk domains.

For this guide, a non-nuclear domain qualifies only when the evidence identifies
a plausible pathway to civilization-scale disruption or mass-catastrophic harm
across borders or generations, not merely serious national security, economic,
privacy, public-health, or human-rights harm. Ordinary cyber incidents,
biotechnology policy, AI regulation, industrial accidents, epidemics, and
conventional environmental policy are out of scope unless a credible technical
or intergovernmental source connects the ruler's decision to that threshold.

## What This Question Does Not Ask

- Do not infer ruler quality directly from arsenal size or nuclear-state status.
- Do not reward low risk that results only from lack of capability or authority.
- Do not penalize defensive preparedness without evidence that the ruler
  needlessly increased catastrophic risk.
- Do not equate every military dispute with existential escalation.
- Do not broaden the category to ordinary cyber, biological, AI, climate, or
  technology governance absent a documented civilization-scale or
  mass-catastrophic pathway.
- Do not substitute rhetoric alone for policy unless the rhetoric materially
  changes risk; `1B.2` evaluates rhetoric in its own right.
- Do not judge all treaty or command-and-control conduct here when it is better
  addressed by `1B.3` or `1B.4`; use it here only as evidence of overall
  risk-reducing or risk-increasing direction.
- Do not use the client matrix as evidence.

## Researcher Instructions

The `internet-research` worker collects cited evidence only and must not assign
the final comparative score. Follow the local-first workflow: read this guide,
reuse local FAS/SIPRI and other structured priors, inspect existing ruler-period
artifacts, then seek external evidence only for unresolved behavioral questions.

Collect evidence on:

- inherited nuclear or catastrophic-risk posture and the ruler's actual
  decision authority;
- arsenal, readiness, delivery-system, fissile-material, weapons-development,
  cyber, biological, AI, or other relevant risk changes attributable to the
  ruler;
- restraint, de-alerting, hotlines, transparency, safeguards, crisis
  communication, inspections, arms control, nonproliferation, or de-escalation;
- withdrawals, inspection limits, destabilizing deployments, riskier doctrine,
  testing, proliferation, or dismantling of protective institutions;
- evidence of prestige, leverage, diversionary, regime-survival, or personal
  power motives, separated from analyst inference;
- credible peaceful or safer alternatives available at the time;
- contrary evidence and target-year evidence separated from ruler-period trends.

Profile every citation using the source-confidence registry's exact fields:
`source_confidence`, `source_confidence_reason`, `source_type`, and
`final_evidence_use`. Low or `very_low` confidence sources may not solely support
a score-bearing claim. Prefer at least two independent source types for material
claims where available.

## Judge Instructions

The `ruler-quality-judge` scores the full question-year batch together and must:

- use `rubric_version = "1b1_existential_risk_reduction_v1"` and one
  `calibration_batch_id`;
- establish the inherited baseline, ruler authority, available alternatives, and
  net direction before comparing cases;
- distinguish deliberate escalation from unavoidable exposure, defensive
  maintenance, bureaucratic inertia, and actions imposed by predecessors;
- weigh both capability and probability/consequence pathways without treating
  raw arsenal counts as ruler behavior;
- preserve contrary evidence and uncertainty around secret programs;
- explain why each score is not one point lower or higher;
- require manual review when attribution, intent, counterfactual alternatives,
  or classified evidence is materially uncertain.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | The ruler deliberately and substantially increased catastrophic risk as a central instrument of power, dismantled major safeguards, or pursued extreme escalation despite credible safer alternatives. |
| 2-3 | Repeated, consequential risk-increasing choices—such as destabilizing expansion, proliferation, inspection obstruction, or crisis escalation—outweigh limited restraint. |
| 4-5 | Mixed or weak performance: meaningful risk-increasing choices coexist with restraint, inherited constraints, or partial mitigation; net direction is adverse or unclear. |
| 6-7 | Net risk reduction or prudent maintenance under real constraints, with some notable escalation, omissions, implementation gaps, or limited ambition. |
| 8-9 | Strong, sustained, attributable risk reduction through restraint, safeguards, de-escalation, agreements, institutional strengthening, or reversal of dangerous policies. |
| 10 | Exceptional and durable reduction of grave risk despite meaningful authority and exposure, with robust safeguards, credible verification, and no material opportunistic escalation. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- at least one citation and a structured-source prior where available, or
  `not_available` with explanation;
- evidence establishing inherited posture and ruler decision authority;
- at least one target-year or near-period behavioral source;
- evidence about both risk-increasing and risk-reducing conduct, or an explicit
  no-finding statement for one side;
- a source-mix note and caveats for secrecy, deterrence claims, and attribution.

Preferred source types:

- local structured priors, FAS Nuclear Notebook, and SIPRI Yearbook;
- IAEA safeguards and Board of Governors reports, CTBTO, UNODA, UN treaty and
  Security Council records;
- official treaty texts, doctrine, budgets, and primary statements, corroborated
  for self-serving claims;
- credible legislative or oversight reports and established technical experts;
- Reuters, Associated Press, BBC, and comparable reporting for chronology;
- peer-reviewed or established academic security research.

## Bias And Comparability Checks

Complete all common calibration checks. In particular:

- `visibility_bias_check`: do not reward opaque programs or punish transparent
  states merely because more detail is public.
- `repression_silence_check`: treat secrecy, censorship, and restricted expert
  access as uncertainty, not proof of restraint.
- `population_scale_check`: replace population mechanically with capability,
  exposure, and consequence scale; do not let state size decide the score.
- `source_type_check`: identify dependence on official claims, intelligence
  allegations, advocacy, or a single technical estimate.
- `recency_check`: separate target-year decisions from inherited and later
  posture.
- `subagent_calibration_check`: compare cases with similar authority and risk
  exposure, including one neighboring score above and below.

Also check deterrence/defense confounding, survivorship bias from crises that did
not become disasters, and outcome bias where prudent action nevertheless had a
bad result or reckless action happened not to fail.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `1b1_existential_risk_reduction_v1`
- `severity_band`: apply to attributable risk-increasing conduct: `none`,
  `isolated`, `recurring`, `widespread`, `systematic`, or `mass`
- `state_responsibility`: use the common enum for attribution; `direct` means a
  ruler-directed choice and `unclear` is required when authority is unresolved
- `accountability_level`: apply to oversight and correction of risky choices:
  `strong`, `partial`, `weak`, `none`, `perpetrator_impunity`, or `state_policy`

Question-specific additional calibration fields:

- `inherited_risk_posture`: `minimal`, `latent`, `material`, `severe`,
  `extreme`, or `unclear`.
- `ruler_decision_authority`: `decisive`, `shared`, `limited`, `ceremonial`, or
  `unclear`.
- `net_risk_direction`: `strongly_reduced`, `reduced`, `mixed`, `increased`,
  `strongly_increased`, or `unclear`.
- `risk_domains`: list drawn from `nuclear_arsenal`, `proliferation`,
  `crisis_escalation`, `command_and_control`, `biological`, `cyber`, `ai`,
  `other`, or `none_material`.
- `existential_inclusion_basis`: for every non-nuclear domain, identify the
  credible civilization-scale or mass-catastrophic pathway and supporting
  source; use `not_established` when the threshold is not met and exclude that
  conduct from scoring.
- `credible_alternatives`: concise account of safer options and constraints.

## Smoke-Test Ruler Set

These are research hypotheses for calibration roles, not asserted final scores:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Mikhail Gorbachev | Soviet Union | 1985-1991 | historically plausible strong risk-reduction case |
| Ronald Reagan | United States | 1981-1989 | edge case combining early escalation with later arms reduction |
| John F. Kennedy | United States | 1962 | crisis de-escalation and prior escalation edge case |
| Nikita Khrushchev | Soviet Union | 1962 | crisis brinkmanship/de-escalation mixed case |
| George W. Bush | United States | 2001-2008 | arms-control withdrawal and nonproliferation mixed case |
| Barack Obama | United States | 2009-2016 | risk-reduction ambition versus modernization/implementation edge |
| Vladimir Putin | Russia | 2022 | severe escalation hypothesis requiring careful period evidence |
| Kim Jong Un | North Korea | 2017 | capability expansion and crisis-escalation low-anchor hypothesis |
| Jacinda Ardern | New Zealand | 2020 | low-exposure/non-nuclear authority-limit edge case |

## Acceptance Checklist

- Research records contain citations, registry profiles, and period caveats.
- Inherited posture and ruler authority are explicit.
- Raw arsenal size is not treated as ruler conduct.
- Risk-increasing and risk-reducing evidence are both addressed.
- The judge handles all smoke cases together or uses overlapping anchors.
- Every score-bearing record contains complete calibration fields.
- Adjacent-anchor rejections and bias checks are substantive.
- Contrary evidence and secrecy/attribution caveats are preserved.
- The guide is updated after smoke testing.
