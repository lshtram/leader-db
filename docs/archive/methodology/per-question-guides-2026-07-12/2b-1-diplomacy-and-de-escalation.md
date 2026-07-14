# 2B.1 Diplomacy And De-escalation

Status: draft

## Question Identity

- `methodology_id`: `2B.1`
- Category: `international_peace`
- Evidence strategy: `internet_manual`
- Rubric version: `2b1_diplomacy_deescalation_v1`
- Guide owner/status note: initial draft for multi-ruler smoke testing.

## Question Text

Did the ruler choose diplomacy, compromise, and de-escalation when credible
peaceful alternatives existed, rather than treating force as the preferred first
option?

## What This Question Asks

This question scores choices among realistic options during international
disputes and crises. Higher scores mean the ruler seriously pursued workable
diplomacy, accepted proportionate compromise, maintained communication, and
de-escalated where peaceful alternatives could protect legitimate security
interests. Lower scores mean the ruler defaulted to force, coercive escalation,
or performative negotiation despite credible peaceful routes.

A score requires at least one material international choice point: a dispute,
crisis, threatened or ongoing interstate/proxy conflict, coercive confrontation,
or inherited external conflict in which the ruler had meaningful authority and
credible options to escalate, sustain, compromise, or de-escalate. Routine
diplomatic activity or general support for peace is not sufficient exposure.
When no such choice point exists, mark `not_applicable`; when one may exist but
the decision record or alternatives cannot be established, use
`insufficient_evidence` or `manual_review_required` rather than a neutral or high
score.

## What This Question Does Not Ask

- Do not equate absence of war with active diplomatic responsibility.
- Do not reward talks, summits, or agreements that were merely performative,
  coercive, or unsupported by implementation.
- Do not assume compromise was credible when the counterpart rejected good-faith
  engagement or posed an immediate threat.
- Do not penalize lawful, necessary defense merely because force was used.
- Do not score initiation and conduct of war wholesale; `2B.2` and `2B.4`
  address nearby but distinct conduct.
- Do not judge success alone: serious good-faith diplomacy can fail, while
  reckless coercion can obtain concessions.
- Do not use the client matrix as evidence.

## Researcher Instructions

Collect cited evidence only. Start with local UCDP/SIPRI priors and existing
ruler-period evidence, then research the decision sequence for material crises:

- threat and inherited dispute context, ruler authority, timing, and urgency;
- available mediation, negotiation, arbitration, inspections, hotlines,
  confidence-building, sanctions relief, ceasefires, or phased settlements;
- offers and counteroffers, including conditions and independent assessment of
  feasibility;
- whether diplomacy was early and serious or delayed until after coercion;
- military threats, ultimatums, mobilization, covert action, or force used before
  alternatives were exhausted;
- concessions, reciprocity, verification, follow-through, and implementation;
- obstruction or bad faith by counterparts and constraints on the ruler;
- contrary episodes and target-year evidence separate from ruler-period context.

Use registry fields `source_confidence`, `source_confidence_reason`,
`source_type`, and `final_evidence_use`. Prefer two independent source types for
material claims; low/`very_low` sources cannot stand alone.

## Judge Instructions

Score the full batch using `2b1_diplomacy_deescalation_v1` and one calibration
batch. Reconstruct the choice point rather than reasoning backward from outcome.
Test whether peaceful alternatives were credible, timely, and compatible with
defensive necessity. Distinguish genuine diplomacy from delay, propaganda,
capitulation demands, coercive bargaining, and agreements without follow-through.
Credit restraint under pressure and appropriate compromise; do not require peace
at any price. Preserve competing accounts and flag missing diplomatic records.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | The ruler consistently chose or engineered force-first escalation despite clear, credible peaceful alternatives, using diplomacy mainly as cover or ultimatum. |
| 2-3 | Repeated rejection, sabotage, or premature abandonment of plausible peaceful routes, with consequential coercion or violence and little genuine compromise. |
| 4-5 | Mixed or weak diplomacy: some serious engagement, but important avoidable escalation, maximalism, delay, poor implementation, or missed opportunities. |
| 6-7 | Generally chose credible diplomacy and proportionate compromise, though with notable coercive episodes, omissions, delays, or incomplete follow-through. |
| 8-9 | Sustained, good-faith, timely diplomacy and de-escalation under meaningful pressure, with credible implementation and limited avoidable coercion. |
| 10 | Exceptional peaceful statecraft that resolved or durably de-escalated grave disputes through principled, verifiable compromise despite strong incentives or pressure to use force. |

## Evidence Requirements

- At least one citation and structured UCDP/SIPRI prior, or `not_available`.
- A dated decision sequence identifying threat, alternatives, ruler choices, and
  outcome without conflating them.
- At least one qualifying international choice point and evidence of the ruler's
  authority over it; otherwise apply the non-score rule above.
- Evidence about feasibility and counterpart conduct, not only one side's claim.
- At least one target-year or near-period source and contrary evidence or a
  documented no-finding.
- Source-mix and classification/archival-gap caveats.

Preferred source types:

- UN resolutions, Secretary-General reports, mediation records, treaty texts,
  ICJ/PCA records, OSCE and regional intergovernmental records;
- UCDP conflict and peace-agreement data, PA-X, and SIPRI context;
- official diplomatic documents and archives for offers and decisions,
  independently corroborated for good-faith claims;
- reputable contemporaneous wires/media for chronology;
- established historical and academic work for decision processes and
  counterfactual alternatives.

## Bias And Comparability Checks

- `visibility_bias_check`: public democracies may expose failed bargaining while
  secret diplomacy elsewhere remains unknown.
- `repression_silence_check`: controlled narratives and sealed archives weaken
  claims that no alternatives existed.
- `population_scale_check`: assess stakes, capability, and choice—not country
  population or raw event totals.
- `source_type_check`: balance official narratives with independent, opposing,
  intergovernmental, or archival evidence.
- `recency_check`: separate the target decision from later peace or escalation.
- `subagent_calibration_check`: compare similar threat contexts and explicitly
  test adjacent cases.

Also check hindsight/outcome bias, victor's narrative, false equivalence between
aggressor and defender, negotiation-access bias, and the confounding effect of
counterpart bad faith.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `2b1_diplomacy_deescalation_v1`
- `severity_band`: apply to avoidable force-first conduct using the common enum
- `state_responsibility`: apply to the ruler/state role using the common enum
- `accountability_level`: apply to review, correction, and responsibility for
  avoidable escalation using the common enum

Question-specific additional calibration fields:

- `international_choice_point_exposure`: `material_with_decisive_authority`,
  `material_with_shared_authority`, `material_with_limited_authority`,
  `no_material_choice_point`, or `unclear`; the last two require
  `not_applicable` or insufficient/manual-review disposition, not a score.
- `peaceful_alternative_status`: `clear_and_credible`, `plausible_but_uncertain`,
  `weak`, `none_credible`, or `unclear`.
- `diplomatic_effort`: `sustained_good_faith`, `meaningful_but_incomplete`,
  `mixed`, `performative`, `rejected_or_sabotaged`, or `unclear`.
- `force_timing`: `not_used`, `after_reasonable_exhaustion`,
  `alongside_diplomacy`, `premature`, `preferred_first_option`, or `unclear`.
- `counterpart_constraint`: concise account of counterpart conduct and urgency.
- `implementation_status`: `durable`, `substantial`, `partial`, `failed_despite_effort`,
  `not_implemented`, `not_applicable`, or `unclear`.

## Smoke-Test Ruler Set

These are plausible calibration hypotheses, not final scores:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Nelson Mandela | South Africa | 1998 | international Lesotho/SADC choice-point eligibility edge; do not substitute domestic reconciliation |
| Mikhail Gorbachev | Soviet Union | 1985-1991 | high de-escalation under strategic pressure |
| Anwar Sadat | Egypt | 1977-1979 | major diplomatic initiative with wider conflict context |
| Menachem Begin | Israel | 1977-1981 | treaty achievement and force-use mixed edge case |
| John F. Kennedy | United States | 1962 | crisis choice-point edge case |
| Nikita Khrushchev | Soviet Union | 1962 | escalation and compromise mixed edge case |
| George W. Bush | United States | 2002-2003 | peaceful-alternatives/force-first low-anchor hypothesis |
| Vladimir Putin | Russia | 2021-2022 | diplomacy-versus-preplanned-force low-anchor hypothesis |
| Volodymyr Zelenskyy | Ukraine | 2022 | defender/counterpart-constraint edge case |

## Acceptance Checklist

- Evidence reconstructs choices and credible alternatives, not outcomes alone.
- Defensive necessity and counterpart conduct are explicitly assessed.
- Performative talks are distinguished from good-faith diplomacy.
- Local priors and registry citation profiles are present.
- The judge uses shared anchors across the smoke batch.
- Every score-bearing record includes complete calibration fields.
- Adjacent-anchor rejections and bias checks are substantive.
- Contrary accounts and archival uncertainty are preserved.
- The guide is updated after smoke testing.
