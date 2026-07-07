# 4B.1 Electoral Contestability

Status: draft for 2020 all-ruler vertical slice

## Question Identity

- `methodology_id`: `4B.1`
- Category: `political_freedom`
- Evidence strategy: `internet_manual`
- Rubric version: `4b1_electoral_contestability_v1`
- Guide owner/status note: initial guide for the 2020 all-ruler vertical slice.

## Question Text

Did the ruler genuinely accept that power should be contestable through free,
fair, and meaningful elections?

## What This Question Asks

This question scores whether the ruler accepted electoral contestability as a
real constraint on power. Higher scores mean opposition parties could compete,
votes could matter, electoral bodies and courts were not captured for ruler
entrenchment, and the ruler accepted the possibility of losing power. Lower
scores mean elections were absent, performative, manipulated, violently
intimidated, legally engineered, or ignored when inconvenient.

The main scoring dimensions are:

- whether national executive power was meaningfully contestable;
- freedom and fairness of elections in or near the target year;
- opposition access to ballots, media, funding, security, and legal remedies;
- independence of election commissions, courts, legislatures, and monitors;
- intimidation, arrests, disqualifications, fraud, vote buying, internet
  shutdowns, emergency measures, or abuse of state resources;
- whether incumbents accepted losses, term limits, and transfer rules;
- target-year fit and broader ruler-period context.

## What This Question Does Not Ask

- Do not score general democracy quality unless it bears on meaningful electoral
  contestability.
- Do not reward elections that are frequent but not meaningfully competitive.
- Do not punish hereditary or non-electoral constitutional monarchs by default if
  the scored ruler is not the electoral executive; preserve identity caveats.
- Do not treat high turnout as evidence of freedom without checking coercion,
  fairness, and opposition access.
- Do not use the client matrix as evidence.

## Researcher Instructions

The `internet-research` worker collects cited evidence only. It should not assign
the final comparative score. For the target ruler/country/year, collect concise
evidence on:

- election quality, contestability, opposition rights, and incumbent advantage;
- whether opposition candidates/parties were barred, jailed, intimidated, exiled,
  censored, or deprived of resources;
- whether electoral commissions, courts, media regulators, security forces, and
  state resources were used neutrally or to entrench the ruler;
- whether the ruler accepted term limits, losses, power sharing, and transfer
  rules;
- structured-source priors where available, especially V-Dem, Freedom House,
  BTI, EIU, Varieties of Party Identity/Regimes where available, and OSCE/OAS/AU
  observer reports;
- contrary evidence such as credible alternation, independent oversight,
  opposition victories, judicial remedies, peaceful concessions, or monitors
  finding credible elections;
- target-year evidence separately from broader ruler-period evidence.

Researchers should return citations with source roles such as
`structured_dataset`, `election_observer`, `ngo`, `official`, `court_or_legal`,
`media`, `academic`, or `intergovernmental`.

## Judge Instructions

The `ruler-quality-judge` receives all 2020 evidence records for `4B.1` and
scores the full batch together. The judge must:

- use `rubric_version = "4b1_electoral_contestability_v1"`;
- use one `calibration_batch_id` for the whole batch;
- compare every ruler against the same anchors before finalizing scores;
- score meaningful contestability, not merely whether an election occurred;
- preserve de facto ruler and formal-office caveats;
- avoid over-penalizing countries with no target-year national election if the
  broader electoral system remained meaningfully contestable;
- explain why each score is not one point lower or higher;
- mark `manual_review_required` when ruler identity, constitutional role, or
  election timing makes attribution uncertain.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | No meaningful electoral contestability: one-party, military, monarchy, personalist, or captured system; opposition cannot realistically win executive power; elections absent, sham, or ignored. |
| 2-3 | Elections exist but are heavily manipulated through repression, disqualification, fraud, captured institutions, intimidation, censorship, or refusal to allow genuine alternation. |
| 4-5 | Some real competition but major incumbent advantages, unfair rules, media/court/election-body capture, intimidation, or selective enforcement seriously distort contestability. |
| 6-7 | Meaningful elections and possible alternation, but notable flaws remain: money/media imbalance, gerrymandering, intimidation, emergency restrictions, weak electoral bodies, or uneven enforcement. |
| 8-9 | Free, fair, and meaningful electoral contestability with credible institutions, peaceful alternation or real possibility of defeat, and limited flaws. |
| 10 | Exemplary contestability: robust independent electoral institutions, equal political rights, transparent finance/media access, credible remedies, and strong acceptance of electoral loss/limits. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- Structured-source prior where available, or `not_available` with explanation.
- Evidence about target-year or near-period electoral contestability.
- Source-mix note explaining whether the record relies heavily on one source type.
- Explicit caveat when no national election occurred in 2020 but near-period
  evidence is used.

Preferred source types:

- structured datasets: V-Dem, Freedom House, BTI, EIU, Varieties of Democracy;
- election observers: OSCE/ODIHR, OAS, AU, EU, Commonwealth, Carter Center;
- court/legal and election-commission sources;
- NGO/intergovernmental reports;
- reputable local/international media for election incidents and transitions.

## Bias And Comparability Checks

The judge must complete the common bias checks in `answer_payload.calibration`.
For `4B.1`, interpret them this way:

- `visibility_bias_check`: explain why high reporting in open societies did not
  overstate electoral flaws relative to closed regimes.
- `repression_silence_check`: explain whether lack of opposition complaints,
  media reports, or observer access reflects genuine fairness or repression.
- `population_scale_check`: separate isolated irregularities from system-level
  distortions that change contestability.
- `source_type_check`: explain reliance on structured indices, observers, courts,
  official bodies, media, or NGOs.
- `recency_check`: distinguish target-year election evidence from near-period or
  ruler-period context.
- `subagent_calibration_check`: compare the ruler to adjacent high, mid, and low
  contestability cases in the batch.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `4b1_electoral_contestability_v1`
- `severity_band`: one of `none`, `isolated`, `recurring`, `widespread`,
  `systematic`, `mass`
- `state_responsibility`: one of `direct`, `state_aligned`, `tolerated`,
  `failed_to_prevent`, `non_state_only`, `unclear`
- `accountability_level`: one of `strong`, `partial`, `weak`, `none`,
  `perpetrator_impunity`, `state_policy`

Question-specific additional calibration fields:

- `electoral_system_status`: one of `no_meaningful_elections`, `sham_elections`,
  `hegemonic_elections`, `competitive_but_unfair`, `competitive_with_flaws`,
  `free_and_fair`, or `unclear`.
- `incumbent_acceptance_of_loss`: one of `accepted`, `partially_accepted`,
  `not_tested`, `rejected`, `prevented_test`, or `unclear`.
- `contestability_constraints`: list of constraints such as `candidate_bans`,
  `opposition_arrests`, `media_capture`, `fraud`, `state_resource_abuse`,
  `violence_intimidation`, `captured_election_body`, `captured_courts`,
  `internet_shutdowns`, `none_found`.

## Smoke-Test Ruler Set

Use these 2020 anchors to sanity-check the batch ordering:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Kim Jong Un | North Korea | 2020 | no meaningful elections / worst anchor |
| Xi Jinping | China | 2020 | no genuine national electoral contestability |
| Alexander Lukashenka | Belarus | 2020 | manipulated election/refusal-of-contestability anchor |
| Vladimir Putin | Russia | 2020 | authoritarian-managed contestability anchor; preserve identity caveat if manifest differs |
| Donald Trump | United States | 2020 | contested-transfer/open-democracy stress-test edge case |
| Narendra Modi | India | 2020 | competitive system with major concerns edge case |
| Jacinda Ardern | New Zealand | 2020 | high contestability anchor |
| Angela Merkel | Germany | 2020 | high contestability anchor |

## Acceptance Checklist

- Research records include citations, source roles, and target-period caveats.
- The watchdog validates every shard output before judge scoring.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores distinguish meaningful contestability from merely holding elections.
- Identity and constitutional-role caveats are preserved.
- Bias checks are specific, not boilerplate.
- Contrary evidence and caveats are preserved.
- The guide is updated after the 2020 run.
