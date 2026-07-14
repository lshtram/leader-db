# 2B.2 Wars Of Choice And Cross-Border Coercion

Status: draft

## Question Identity

- `methodology_id`: `2B.2`
- Category: `international_peace`
- Evidence strategy: `internet_manual`
- Rubric version: `2b2_wars_of_choice_coercion_v1`
- Guide owner/status note: initial draft for multi-ruler smoke testing.

## Question Text

Did the ruler initiate, expand, prolong, or justify wars of choice, cross-border
coercion, annexation, covert destabilization, or proxy conflict beyond defensive
necessity?

## What This Question Asks

This question scores the ruler's responsibility for optional or excessive
external conflict. Higher scores mean restraint from wars of choice, annexation,
covert destabilization, proxy war, and coercion beyond genuine defense, plus
credible efforts to limit or end inherited conflict. Lower scores mean the ruler
initiated, expanded, prolonged, or falsely justified such conduct when defensive
necessity did not require it.

Scoring also requires meaningful opportunity/exposure: an external armed
conflict, coercive confrontation, proxy relationship, inherited war, or credible
occasion where the ruler could choose expansion, restraint, withdrawal, or
destabilization. `no_material_conflict` does not demonstrate restraint. If the
ruler had no material exposure, mark `not_applicable`; if exposure or covert
conduct cannot be determined, use `insufficient_evidence` or
`manual_review_required`. High scores require demonstrated restraint under a
real opportunity to use or expand force, not merely an uneventful period.

## What This Question Does Not Ask

- Do not assign guilt from conflict involvement or fatalities alone.
- Do not treat every first battlefield action as aggression; assess prior attack,
  imminent threat, invitation, occupation, treaty duties, and international law.
- Do not excuse disproportionate expansion merely because a conflict began
  defensively.
- Do not ignore covert action, proxies, blockades, territorial faits accomplis,
  or armed coercion below formal-war thresholds.
- Do not score operational civilian protection here except where it establishes
  expansion or defensive necessity; `2B.4` owns conduct of hostilities.
- Do not equate military spending with aggression.
- Do not use the client matrix as evidence.

## Researcher Instructions

Collect cited evidence only. Begin with local UCDP event/fatality and
internationalization priors plus SIPRI context. For every material conflict,
produce a dated responsibility record covering:

- conflict inheritance, triggering events, territorial/legal status, and ruler
  authority;
- initiation, escalation, geographic expansion, annexation, occupation,
  destabilization, proxy support, arms/training, blockade, or prolongation;
- asserted justification and independent evidence for actual threat, imminence,
  necessity, invitation, consent, and proportionality of strategic aims;
- available exit ramps, ceasefires, withdrawals, settlements, and decisions that
  prolonged or ended fighting;
- command/support relationship to proxies and foreseeability of their conduct;
- UN, court, commission, or credible expert findings, including disagreement;
- target-year responsibility separate from inherited and later conduct.

Profile all citations using `source_confidence`, `source_confidence_reason`,
`source_type`, and `final_evidence_use`. Low/`very_low` sources cannot solely
support material responsibility findings. State propaganda and belligerent
self-justification are context unless independently corroborated.

## Judge Instructions

Use one `2b2_wars_of_choice_coercion_v1` batch. Determine separately whether the
ruler initiated, expanded, prolonged, justified, or ended each conflict and
whether the relevant conduct exceeded defensive necessity. Do not convert UCDP
fatalities into culpability without actor-role evidence. Attribute covert and
proxy conduct by control, material support, knowledge, and foreseeability, with
uncertainty preserved. Evaluate inherited wars by the ruler's feasible choices
after taking office. Require manual review for disputed identity, invitation,
imminence, territorial status, or classified proxy evidence.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | The ruler deliberately launches or radically expands a major war of choice, annexation, or sustained destabilization with grave consequences and no credible defensive necessity. |
| 2-3 | Severe recurring or prolonged aggression, coercion, occupation, or proxy war beyond necessity, with false justification, rejected exit ramps, or major territorial aims. |
| 4-5 | Significant but bounded optional coercion or conflict expansion, or a mixed record combining legitimate defense with avoidable escalation/prolongation. |
| 6-7 | Broad restraint and substantially defensive conduct, but with notable excessive aims, coercive episodes, proxy ambiguity, delayed exit, or inherited-war prolongation. |
| 8-9 | Strong restraint from optional force, narrowly defensive action where necessary, and credible efforts to prevent expansion or end inherited conflict. |
| 10 | Exemplary restraint under serious threat: rigorously limited defense, rejection of advantageous aggression, transparent lawful justification, and durable reduction of inherited external conflict. |

## Evidence Requirements

- At least one citation and local UCDP/SIPRI prior, or `not_available`.
- Actor-role evidence beyond event/fatality totals.
- A conflict timeline separating inherited, initiated, expanded, prolonged, and
  terminated phases under the ruler.
- Evidence assessing defensive necessity and independent legal/factual findings.
- Evidence establishing the ruler's opportunity/exposure to a material conflict
  choice; no-event cases must use the non-score rule above.
- Proxy/covert attribution evidence where relevant, contrary evidence, and a
  source-mix/uncertainty note.

Preferred source types:

- UCDP datasets and narratives, UN Security Council/General Assembly and panels
  of experts, UN commissions, and peace-agreement records;
- ICJ, ICC, arbitral, and other primary legal records, with mandate/status noted;
- SIPRI arms transfers and established conflict datasets for context;
- official documents for orders, doctrine, invitations, and stated reasons,
  corroborated for disputed claims;
- Reuters, Associated Press, BBC, and comparable contemporaneous reporting;
- peer-reviewed histories and conflict/security scholarship.

## Bias And Comparability Checks

- `visibility_bias_check`: overt interventions are easier to document than
  covert destabilization and proxy support.
- `repression_silence_check`: sealed archives, propaganda, and witness risk make
  absence of evidence weak in closed belligerents.
- `population_scale_check`: fatalities and force size indicate consequence, not
  by themselves initiation or necessity.
- `source_type_check`: expose dependence on one belligerent's narrative,
  intelligence allegation, legal filing, or advocacy source.
- `recency_check`: allocate responsibility to the ruler's actual period and
  distinguish later evidence about earlier conduct.
- `subagent_calibration_check`: compare actor role, necessity, territorial aim,
  duration, and available exits across adjacent cases.

Also check false equivalence, winner/loser and Western-media bias, formal-war
bias, hindsight bias, inherited-conflict confounding, alliance/invitation claims,
and contested borders or statehood.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `2b2_wars_of_choice_coercion_v1`
- `severity_band`: apply to optional/excessive external conduct using the common
  enum
- `state_responsibility`: use the common enum for direct, aligned, tolerated,
  failure-to-prevent, non-state-only, or uncertain attribution
- `accountability_level`: apply to acknowledgment, investigation, correction,
  withdrawal, or impunity using the common enum

Question-specific additional calibration fields:

- `conflict_opportunity_exposure`: `material_decisive`, `material_shared`,
  `material_limited`, `credible_restraint_opportunity`, `no_material_exposure`,
  or `unclear`. `no_material_exposure` is not applicable and `unclear` is
  insufficient/manual review; neither earns a high score.
- `conflict_role`: list drawn from `initiated`, `expanded`, `prolonged`,
  `justified`, `inherited_and_restrained`, `inherited_and_ended`,
  `defended_without_material_excess`, `no_material_conflict`, or `unclear`.
- `conduct_channels`: list drawn from `direct_war`, `annexation`, `occupation`,
  `cross_border_coercion`, `covert_destabilization`, `proxy_support`,
  `blockade`, `arms_or_training`, or `none_found`.
- `defensive_necessity`: `credible_and_proportionate`, `credible_but_exceeded`,
  `weak_or_pretextual`, `absent`, `not_applicable`, or `unclear`.
- `ruler_attribution`: `decisive`, `shared`, `inherited_with_choice`, `limited`,
  or `unclear`.
- `exit_ramp_response`: `pursued`, `partly_pursued`, `rejected`, `sabotaged`,
  `none_credible`, or `unclear`.

## Smoke-Test Ruler Set

These are plausible calibration hypotheses, not final scores:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Adolf Hitler | Germany | 1939 | extreme war-of-choice anchor |
| Saddam Hussein | Iraq | 1990 | invasion/annexation low-anchor hypothesis |
| Vladimir Putin | Russia | 2022 | invasion and annexation low-anchor hypothesis |
| George W. Bush | United States | 2003 | disputed/pretextual necessity low-edge case |
| Lyndon B. Johnson | United States | 1964-1968 | inherited involvement and major expansion case |
| Tony Blair | United Kingdom | 2003 | coalition/shared-attribution and justification edge |
| Margaret Thatcher | United Kingdom | 1982 | response to invasion/limited-war defensive edge |
| George H. W. Bush | United States | 1990-1991 | collective defense and war-aim restraint case |
| Volodymyr Zelenskyy | Ukraine | 2022 | invaded defender and necessity edge case |
| José Ramos-Horta | Timor-Leste | 2007-2012 | low-exposure/no-material-conflict comparability case |

## Acceptance Checklist

- UCDP conflict volume is not treated as culpability without role evidence.
- Inherited, initiated, expanded, prolonged, and ended phases are separated.
- Defensive necessity and ruler attribution are explicit.
- Covert/proxy channels and formal armed force use the same responsibility test.
- Registry profiles, contrary evidence, and source gaps are preserved.
- The judge scores all smoke cases together or with overlapping anchors.
- Every score-bearing record has complete calibration fields.
- Adjacent-anchor rejections and bias checks are substantive.
- The guide is updated after smoke testing.
