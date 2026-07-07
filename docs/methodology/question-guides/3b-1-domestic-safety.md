# 3B.1 Domestic Safety From State Violence

Status: draft for 2020 all-ruler vertical slice

## Question Identity

- `methodology_id`: `3B.1`
- Category: `domestic_safety`
- Evidence strategy: `internet_manual`
- Rubric version: `3b1_domestic_safety_v1`
- Guide owner/status note: initial guide for the 2020 all-ruler vertical slice.

## Question Text

Did the ruler protect residents from state violence, torture, disappearances,
political imprisonment, extrajudicial killing, and arbitrary or exemplary
punishment?

## What This Question Asks

This question scores whether residents were protected from ruler/state-linked
physical-integrity abuse during the target year or ruler period. Higher scores
mean stronger protection from state terror, torture, disappearances, political
imprisonment, extrajudicial killing, and arbitrary punishment, with credible
accountability when abuse occurs.

The main scoring dimensions are:

- severity and scale of physical-integrity abuse;
- directness of ruler/state responsibility;
- whether abuse is isolated, recurring, widespread, systematic, or mass;
- accountability, remedy, and restraint;
- target-year fit and ruler-period context;
- reliability of the information environment.

## What This Question Does Not Ask

- Do not score ordinary crime or homicide unless state actors, state-aligned
  actors, prisons, police, military, intelligence services, or politically
  protected groups are implicated.
- Do not score general democracy, elections, press freedom, or corruption except
  where they affect evidence reliability, accountability, or impunity.
- Do not score by the number of news articles or search hits.
- Do not treat absence of reports in closed regimes as evidence that abuse did not
  occur.
- Do not use the client matrix as evidence.

## Researcher Instructions

The `internet-research` worker collects cited evidence only. It should not assign
the final comparative score. For the target ruler/country/year, collect concise
evidence on:

- state violence, torture, disappearances, political imprisonment, extrajudicial
  killing, arbitrary detention, prison abuse, exemplary punishment, and security
  force abuse;
- whether abuse was direct state policy, tolerated practice, failure to prevent,
  or unclear;
- whether accountability existed through courts, prosecution, independent
  investigations, ombudsman bodies, legislative oversight, or credible reforms;
- structured-source priors where available, especially PTS, CIRIGHTS, V-Dem,
  UCDP, Freedom House, BTI, UN reports, Amnesty, and Human Rights Watch;
- contrary evidence such as credible accountability, reforms, isolated nature of
  incidents, or source disagreement;
- target-year evidence separately from broader ruler-period evidence.

Researchers should return citations with source roles such as
`structured_dataset`, `ngo`, `un_or_intergovernmental`, `court_or_legal`,
`media`, `official`, or `academic`.

## Judge Instructions

The `ruler-quality-judge` receives all 2020 evidence records for `3B.1` and scores
the full batch together. The judge must:

- use `rubric_version = "3b1_domestic_safety_v1"`;
- use one `calibration_batch_id` for the whole batch;
- compare every ruler against the same anchors before finalizing scores;
- avoid using evidence volume as severity;
- treat open-country evidence volume as a confidence aid, not an automatic score
  penalty;
- treat closed-country silence as lower confidence, not exculpatory evidence;
- explain why each score is not one point lower or higher;
- preserve contrary evidence and caveats;
- mark `manual_review_required` when evidence is too thin or structurally biased.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Systematic state terror or mass repression: recurrent killings, torture, disappearances, political imprisonment, or arbitrary punishment as state/ruler policy, with impunity. |
| 2-3 | Severe recurring state abuse: credible patterns of torture, arbitrary detention, disappearances, lethal repression, political imprisonment, or prison/security-force abuse, with weak or selective remedies. |
| 4-5 | Significant abuse patterns or targeted repression, but not generalized state terror; safeguards exist but are partial, politicized, or unreliable. |
| 6-7 | No systematic terror and meaningful safeguards, but serious police, detention, prison, protest, asylum, minority, or security-force abuses remain. Accountability is partial or uneven. |
| 8-9 | Strong protection from state physical-integrity abuse; rare serious abuses; credible investigation, remedy, and transparency; no evidence of systematic ruler-backed repression. |
| 10 | Exceptional protection: rare violations, robust independent accountability, high transparency, durable safeguards, and strong evidence that the ruler/state prevents and remedies abuse. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- Structured-source prior where available, or `not_available` with explanation.
- At least one source addressing target-year or near-period state/security-force
  abuse.
- Source-mix note explaining whether the record relies heavily on one source type.
- Explicit caveat when no high-quality target-year evidence is found.

Preferred source types:

- structured datasets: PTS, CIRIGHTS, V-Dem, UCDP, Freedom House, BTI;
- NGO/intergovernmental reports: Amnesty, Human Rights Watch, UN bodies, Council
  of Europe, Inter-American/African/European human-rights bodies where relevant;
- court/legal/official accountability sources;
- reputable local or international media for specific incidents and context;
- academic sources for ruler-period context where current reports are thin.

## Bias And Comparability Checks

The judge must complete the common bias checks in `answer_payload.calibration`.
For `3B.1`, interpret them this way:

- `visibility_bias_check`: explain why heavy reporting in open societies did not
  inflate severity.
- `repression_silence_check`: explain whether missing evidence is meaningful or
  likely caused by fear, censorship, NGO exclusion, weak courts, or closed media.
- `population_scale_check`: separate isolated incidents, recurring patterns,
  prevalence, and systematic state policy.
- `source_type_check`: explain whether the record is balanced across structured,
  NGO, legal, media, official, and academic sources.
- `recency_check`: distinguish 2020 evidence from broader ruler-period evidence.
- `subagent_calibration_check`: compare the ruler to neighboring cases in the
  batch, especially cases one point above and below.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `3b1_domestic_safety_v1`
- `severity_band`: one of `none`, `isolated`, `recurring`, `widespread`,
  `systematic`, `mass`
- `state_responsibility`: one of `direct`, `state_aligned`, `tolerated`,
  `failed_to_prevent`, `non_state_only`, `unclear`
- `accountability_level`: one of `strong`, `partial`, `weak`, `none`,
  `perpetrator_impunity`, `state_policy`

Question-specific additional calibration fields:

- `target_abuse_types`: list of abuse types found, such as `torture`,
  `disappearances`, `political_imprisonment`, `extrajudicial_killing`,
  `arbitrary_detention`, `prison_abuse`, `protest_repression`, or `none_found`.
- `state_actor_scope`: concise description of implicated actors: police, military,
  intelligence, prisons, militias, party enforcers, tolerated vigilantes, or none.

## Smoke-Test Ruler Set

The first full vertical slice is all available 2020 ruler/country rows. Use these
known anchors to sanity-check the batch ordering:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Vladimir Putin | Russia | 2020 | low-score authoritarian/state-abuse anchor |
| Xi Jinping | China | 2020 | low-score mass/systematic repression anchor |
| Donald Trump | United States | 2020 | open-society edge case with serious policing/protest/detention concerns |
| Viktor Orban | Hungary | 2020 | mid/high edge: rule-of-law concern but not mass physical-integrity terror |
| Jacinda Ardern | New Zealand | 2020 | high-score open-society accountability anchor |
| Angela Merkel | Germany | 2020 | high-score strong-safeguard anchor |
| Narendra Modi | India | 2020 | large-population/religious-minority/security-force edge case |
| Bashar al-Assad | Syria | 2020 | worst-case mass/systematic violence anchor if in scope |

## Acceptance Checklist

- Research records include citations, source roles, and target-period caveats.
- The judge scores all 2020 cases in one batch or with overlapping anchor cases if
  the full set is too large for context.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores are coherent relative to the anchor cases and adjacent scores.
- `lower_anchor_rejected` and `higher_anchor_rejected` are substantive.
- Bias checks are specific, not boilerplate.
- Contrary evidence and caveats are preserved.
- The guide is updated after the 2020 smoke run.
