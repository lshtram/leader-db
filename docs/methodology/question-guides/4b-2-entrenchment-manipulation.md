# 4B.2 Entrenchment Manipulation

Status: draft for 2020 all-ruler vertical slice

## Question Identity

- `methodology_id`: `4B.2`
- Category: `political_freedom`
- Evidence strategy: `internet_manual`
- Rubric version: `4b2_entrenchment_manipulation_v1`
- Guide owner/status note: initial guide for the 2020 all-ruler vertical slice.

## Question Text

Did the ruler refrain from manipulating electoral rules, courts, media, election
commissions, security forces, or public resources to entrench themselves?

## What This Question Asks

This question scores whether the ruler avoided using state, legal, electoral,
media, or coercive machinery to preserve personal or party rule. Higher scores
mean the ruler did not bend institutions for incumbency advantage and accepted
neutral rules even when they constrained the government. Lower scores mean the
ruler systematically altered, captured, or abused institutions and public assets
to make removal from power harder.

The main scoring dimensions are:

- changes to electoral laws, districting, party-registration rules, term limits,
  constitutional rules, or ballot access that favor the ruler;
- capture or pressure on courts, election commissions, media regulators,
  prosecutors, legislatures, audit bodies, or local governments;
- state-resource abuse, public-employee mobilization, clientelism, campaign-finance
  advantages, or official propaganda for ruler entrenchment;
- use of police, military, intelligence services, party enforcers, or emergency
  powers to intimidate opposition or election administrators;
- whether remedies, oversight, courts, monitors, or transfers of power constrained
  the ruler;
- target-year fit and broader ruler-period context.

## What This Question Does Not Ask

- Do not score general democracy quality unless it bears on institutional
  manipulation or entrenchment.
- Do not duplicate `4B.1` by scoring ordinary election quality alone; focus on the
  ruler's manipulation of rules and institutions for advantage.
- Do not treat lawful institutional reform as manipulation without evidence of
  partisan, personal, coercive, or anti-competitive purpose/effect.
- Do not punish constitutional monarchs or ceremonial presidents by default when
  they lack control over the relevant institutions; preserve role caveats.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Before launching any `internet-research` worker, build and attach the local
structured-prior artifact for the exact ruler/country/year:

```bash
leaders-db research build-local-prior \
  --methodology-id 4B.2 \
  --year 2020 \
  --iso3 <ISO3> \
  --leader "<Ruler name>" \
  --output <local-prior.json> \
  --json
```

For all-scope preparation, use the package builder:

```bash
leaders-db research build-local-prior-slice \
  --methodology-id 4B.2 \
  --year 2020 \
  --output-dir data/outputs/research/4b2_2020_local_priors \
  --json
```

The artifact status must be handled explicitly:

- `evidence_found`: use the local facts as structured priors and do not refetch
  local structured datasets such as Freedom House, V-Dem, WGI, BTI, RSF, or Polity
  unless narrative/ruler-specific detail is needed.
- `no_evidence_found`: proceed only with a clear note that selected local facts are
  absent for this country-year; do not silently invent structured priors.
- `not_applicable`: do not produce a score-bearing record unless the scope decision
  is corrected; mark the case not applicable/manual review.
- `error`: do not launch dependent research until `missing_or_empty_reason` is
  inspected and resolved.

## Researcher Instructions

The `internet-research` worker collects cited evidence only. It should not assign
the final comparative score. For the target ruler/country/year, collect concise
evidence on:

- electoral-law, constitutional, districting, term-limit, party-registration, or
  ballot-access changes used for incumbent advantage;
- pressure, capture, or retaliation involving courts, election commissions,
  prosecutors, legislatures, media regulators, public broadcasters, or independent
  oversight bodies;
- abuse of public resources, state media, security forces, administrative permits,
  public employment, social benefits, or procurement for ruler/party advantage;
- contrary evidence such as independent court remedies, credible oversight,
  neutral election administration, opposition victories, peaceful concessions, or
  reforms with broad/nonpartisan support;
- structured-source priors from the local artifact and any necessary narrative
  sources, separated by target-year, near-period, and ruler-period evidence.

Researchers should return citations with source roles such as
`structured_dataset`, `election_observer`, `ngo`, `court_or_legal`, `official`,
`media`, `academic`, or `intergovernmental`.

## Judge Instructions

The `ruler-quality-judge` receives all 2020 evidence records for `4B.2` and scores
the full batch together. The judge must:

- use `rubric_version = "4b2_entrenchment_manipulation_v1"`;
- use one `calibration_batch_id` for the whole batch;
- compare every ruler against the same anchors before finalizing scores;
- score manipulation/entrenchment by the ruler, not only background regime type;
- preserve de facto ruler and formal-office caveats;
- treat absence of reported manipulation cautiously in closed information
  environments;
- explain why each score is not one point lower or higher;
- mark `manual_review_required` when ruler identity, constitutional role, or
  attribution to the target ruler is uncertain.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Systematic entrenchment: rules, courts, media, election bodies, security forces, and state resources are captured or manipulated so removal is practically impossible. |
| 2-3 | Severe manipulation across several channels: constitutional/electoral engineering, captured courts/media/election bodies, intimidation, or state-resource abuse materially entrenches the ruler. |
| 4-5 | Recurring incumbent manipulation or institutional pressure creates major unfair advantage, but some opposition space, remedies, or constraints remain. |
| 6-7 | Mostly neutral institutions with notable flaws, episodic state-resource abuse, partisan appointments, weak remedies, or disputed reforms that advantage incumbents. |
| 8-9 | Strong restraint: rules and institutions remain broadly neutral, independent oversight exists, and any abuses are isolated, remedied, or not attributable to the ruler. |
| 10 | Exemplary restraint: the ruler strengthens neutral institutions, avoids incumbency abuse, accepts effective constraints, and leaves no credible entrenchment pattern. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- Local structured-prior artifact status and summary in `structured_prior_summary`.
- Evidence about target-year or near-period institutional manipulation/restraint.
- Source-mix note explaining whether the record relies heavily on one source type.
- Explicit caveat when the ruler has limited constitutional power over the relevant
  institutions or when no target-year election/institutional change occurred.

Preferred source types:

- structured datasets: V-Dem, Freedom House, BTI, WGI, RSF, Polity where locally
  available;
- election observers: OSCE/ODIHR, OAS, AU, EU, Commonwealth, Carter Center;
- court/legal/election-commission records;
- NGO/intergovernmental reports;
- reputable local/international media for rule changes, state-resource abuse,
  media pressure, institutional capture, or security-force intimidation.

## Bias And Comparability Checks

The judge must complete the common bias checks in `answer_payload.calibration`.
For `4B.2`, interpret them this way:

- `visibility_bias_check`: explain why open-society reporting volume did not
  overstate manipulation relative to closed regimes.
- `repression_silence_check`: explain whether missing complaints, court cases,
  monitor reports, or media coverage reflect genuine restraint or repression.
- `population_scale_check`: separate isolated local abuses from system-level
  institutional capture.
- `source_type_check`: explain reliance on structured priors, observers, courts,
  official bodies, media, or NGOs.
- `recency_check`: distinguish target-year actions from inherited or later
  entrenchment patterns.
- `subagent_calibration_check`: compare the ruler to adjacent high, mid, and low
  manipulation cases in the batch.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `4b2_entrenchment_manipulation_v1`
- `severity_band`: one of `none`, `isolated`, `recurring`, `widespread`,
  `systematic`, `mass`
- `state_responsibility`: one of `direct`, `state_aligned`, `tolerated`,
  `failed_to_prevent`, `non_state_only`, `unclear`
- `accountability_level`: one of `strong`, `partial`, `weak`, `none`,
  `perpetrator_impunity`, `state_policy`

Question-specific additional calibration fields:

- `manipulation_status`: one of `none_found`, `isolated_or_alleged`,
  `recurring_advantage`, `systematic_entrenchment`, `no_meaningful_constraints`,
  `not_applicable`, or `unclear`.
- `institutional_remedy_status`: one of `effective`, `partial`, `weak`,
  `captured`, `not_applicable`, or `unclear`.
- `entrenchment_channels`: list of channels such as `electoral_rules`, `courts`,
  `media`, `election_commission`, `security_forces`, `public_resources`,
  `constitutional_or_term_limit_change`, `party_or_legislature_capture`,
  `none_found`, `not_applicable`, or `unclear`.

## Smoke-Test Ruler Set

Use these 2020 anchors to sanity-check the batch ordering:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Kim Jong Un | North Korea | 2020 | no meaningful institutional constraints / worst anchor |
| Xi Jinping | China | 2020 | party-state institutional capture anchor |
| Alexander Lukashenka | Belarus | 2020 | election/security/media manipulation anchor |
| Vladimir Putin | Russia | 2020 | constitutional and managed-institution entrenchment anchor |
| Recep Tayyip Erdoğan | Türkiye | 2020 | media/courts/electoral-resource manipulation concern |
| Donald Trump | United States | 2020 | open-system stress test with institutional resistance |
| Jacinda Ardern | New Zealand | 2020 | high-restraint anchor |
| Angela Merkel | Germany | 2020 | high-restraint anchor |

## Acceptance Checklist

- Local structured-prior artifacts exist before internet research and have explicit
  `evidence_found`, `no_evidence_found`, `not_applicable`, or `error` handling.
- Research records include citations, source roles, and target-period caveats.
- The watchdog validates every shard output before judge scoring.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores distinguish ruler entrenchment from generic democracy quality.
- Identity and constitutional-role caveats are preserved.
- Bias checks are specific, not boilerplate.
- Contrary evidence and institutional remedies are preserved.
- The guide is updated after the 2020 run.
