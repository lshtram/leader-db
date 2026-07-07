# 3B.2 Security-Force And Tolerated-Enforcer Abuse

Status: draft for 2020 all-ruler vertical slice

## Question Identity

- `methodology_id`: `3B.2`
- Category: `domestic_safety`
- Evidence strategy: `internet_manual`
- Rubric version: `3b2_security_force_abuse_v1`
- Guide owner/status note: initial guide for the 2020 all-ruler vertical slice.

## Question Text

Did the ruler prevent, punish, or tolerate abuse by police, military,
intelligence services, prisons, militias, party enforcers, informal loyalists,
or tolerated vigilantes?

## What This Question Asks

This question scores whether the ruler prevented and punished abuse by coercive
state or state-protected actors during the target year or ruler period. Higher
scores mean the ruler kept police, military, intelligence, prison staff,
militias, party enforcers, loyalist groups, and tolerated vigilantes under lawful
restraint, with credible accountability for abuse. Lower scores mean the ruler
used, tolerated, protected, or failed to restrain those actors.

The main scoring dimensions are:

- which actors committed abuse and whether they were state-linked or protected;
- whether abuse was isolated, recurring, widespread, systematic, or policy-like;
- whether the ruler prevented, punished, tolerated, encouraged, or benefited from
  abuse;
- accountability through prosecution, discipline, independent investigation,
  civilian oversight, courts, ombudsman bodies, or reform;
- target-year fit and ruler-period context;
- information-environment limits and source reliability.

## What This Question Does Not Ask

- Do not score ordinary crime unless public agents, state-aligned groups,
  protected loyalists, tolerated vigilantes, prisons, security forces, or
  politically connected armed actors are implicated.
- Do not score all human-rights violations; focus on abuse by coercive or
  protected actors and the ruler's prevention, tolerance, or punishment.
- Do not double-count every finding from `3B.1`; this question is specifically
  about actor control and accountability.
- Do not treat a single prosecution as proof of strong accountability if wider
  impunity persists.
- Do not treat absence of reports in closed regimes as evidence that abuse did
  not occur.
- Do not use the client matrix as evidence.

## Researcher Instructions

The `internet-research` worker collects cited evidence only. It should not assign
the final comparative score. For the target ruler/country/year, collect concise
evidence on:

- police, military, intelligence, prison, militia, party-enforcer, loyalist, or
  tolerated-vigilante abuse;
- whether abuse was committed by formal state actors, state-aligned actors,
  politically protected groups, or non-state actors tolerated by authorities;
- whether officials prevented, investigated, prosecuted, disciplined, ignored,
  covered up, encouraged, or rewarded abuse;
- structured-source priors where available, especially CIRIGHTS, V-Dem, PTS,
  UCDP, Freedom House, BTI, UN reports, Amnesty, and Human Rights Watch;
- contrary evidence such as credible prosecutions, independent oversight,
  reforms, isolated nature of incidents, or source disagreement;
- target-year evidence separately from broader ruler-period evidence.

Researchers should return citations with source roles such as
`structured_dataset`, `ngo`, `un_or_intergovernmental`, `court_or_legal`,
`media`, `official`, or `academic`.

## Judge Instructions

The `ruler-quality-judge` receives all 2020 evidence records for `3B.2` and
scores the full batch together. The judge must:

- use `rubric_version = "3b2_security_force_abuse_v1"`;
- use one `calibration_batch_id` for the whole batch;
- compare every ruler against the same anchors before finalizing scores;
- focus on prevention, punishment, tolerance, and impunity, not only abuse
  severity;
- avoid using evidence volume as severity;
- treat open-country evidence volume as a confidence aid, not an automatic score
  penalty;
- treat closed-country silence as lower confidence, not exculpatory evidence;
- explain why each score is not one point lower or higher;
- preserve contrary evidence and caveats;
- mark `manual_review_required` when evidence is too thin, actor attribution is
  unclear, or ruler identity is contested.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Ruler uses or protects abusive coercive actors as a core governing tool: systematic torture, killings, disappearances, prison abuse, political detention, militia/loyalist violence, or vigilante terror with state-policy impunity. |
| 2-3 | Severe recurring abuse by police, military, intelligence, prisons, militias, party enforcers, loyalists, or tolerated vigilantes; accountability is absent, token, selective, or subordinate to regime/security interests. |
| 4-5 | Significant abuse patterns or politicized tolerance, but not generalized terror; some safeguards or prosecutions exist but are partial, inconsistent, or overwhelmed by impunity. |
| 6-7 | Meaningful legal safeguards and some accountability, but recurring police, detention, prison, military, protest, minority, or loyalist abuses remain. |
| 8-9 | Strong prevention and accountability: rare serious abuses, credible investigation/remedy, independent oversight, and no evidence that the ruler tolerates or protects abusive actors. |
| 10 | Exceptional restraint and accountability: robust independent controls, transparent investigation, effective prevention, strong remedy for victims, and durable safeguards against state/protected-actor abuse. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- Structured-source prior where available, or `not_available` with explanation.
- At least one source addressing target-year or near-period actor abuse and
  accountability.
- Source-mix note explaining whether the record relies heavily on one source type.
- Explicit caveat when no high-quality target-year evidence is found.

Preferred source types:

- structured datasets: CIRIGHTS, V-Dem, PTS, UCDP, Freedom House, BTI;
- NGO/intergovernmental reports: Amnesty, Human Rights Watch, UN bodies, regional
  human-rights bodies;
- court/legal/official accountability sources;
- reputable local or international media for specific incidents and context;
- academic sources for ruler-period context where current reports are thin.

## Bias And Comparability Checks

The judge must complete the common bias checks in `answer_payload.calibration`.
For `3B.2`, interpret them this way:

- `visibility_bias_check`: explain why heavy reporting of police abuse in open
  societies did not automatically lower scores below closed regimes with fewer
  reports.
- `repression_silence_check`: explain whether missing evidence is meaningful or
  likely caused by fear, censorship, NGO exclusion, weak courts, closed prisons,
  or controlled media.
- `population_scale_check`: distinguish isolated incidents, recurring abuse,
  widespread patterns, and systematic policy or tolerated impunity.
- `source_type_check`: explain whether the record is balanced across structured,
  NGO, legal, media, official, and academic sources.
- `recency_check`: distinguish 2020 evidence from broader ruler-period evidence.
- `subagent_calibration_check`: compare the ruler to neighboring cases in the
  batch, especially cases one point above and below.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `3b2_security_force_abuse_v1`
- `severity_band`: one of `none`, `isolated`, `recurring`, `widespread`,
  `systematic`, `mass`
- `state_responsibility`: one of `direct`, `state_aligned`, `tolerated`,
  `failed_to_prevent`, `non_state_only`, `unclear`
- `accountability_level`: one of `strong`, `partial`, `weak`, `none`,
  `perpetrator_impunity`, `state_policy`

Question-specific additional calibration fields:

- `actor_types`: list of actor types found, such as `police`, `military`,
  `intelligence`, `prisons`, `militia`, `party_enforcers`, `loyalists`,
  `tolerated_vigilantes`, or `none_found`.
- `ruler_response`: one of `prevented`, `punished`, `partial_accountability`,
  `ignored`, `covered_up`, `encouraged`, `used_as_policy`, or `unclear`.
- `accountability_mechanisms`: concise description of prosecutions, discipline,
  civilian oversight, courts, ombudsman bodies, independent inquiries, reforms,
  or absence of remedy.

## Smoke-Test Ruler Set

The first full vertical slice is all available 2020 ruler/country rows. Use these
known anchors to sanity-check the batch ordering:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Kim Jong Un | North Korea | 2020 | worst-case state/security abuse anchor |
| Xi Jinping | China | 2020 | low-score systematic security-force/protected-actor abuse anchor |
| Alexander Lukashenka | Belarus | 2020 | low-score protest/security-force abuse anchor |
| Donald Trump | United States | 2020 | open-society policing/accountability edge case |
| Narendra Modi | India | 2020 | large federal/security-force and minority-abuse edge case |
| Jair Bolsonaro | Brazil | 2020 | police/militia accountability edge case |
| Lee Hsien Loong | Singapore | 2020 | high/mid edge with security-law detention concerns |
| Jacinda Ardern | New Zealand | 2020 | high-score accountability anchor |

## Acceptance Checklist

- Research records include citations, source roles, and target-period caveats.
- The watchdog validates every shard output before judge scoring.
- The judge scores all 2020 cases in one batch or with overlapping anchor cases if
  the full set is too large for context.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores are coherent relative to the anchor cases and adjacent scores.
- `lower_anchor_rejected` and `higher_anchor_rejected` are substantive.
- Bias checks are specific, not boilerplate.
- Contrary evidence and caveats are preserved.
- The guide is updated after the 2020 run.
