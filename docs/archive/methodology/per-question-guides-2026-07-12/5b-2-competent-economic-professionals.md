# 5B.2 Competent Economic Professionals

Status: draft

## Question Identity

- `methodology_id`: `5B.2`
- Category: economic well-being and prosperity
- Evidence strategy: `internet_manual`
- Rubric version: `5b2_economic_professionals_v1`
- Guide owner/status note: Initial draft for smoke testing; not production-ready.

## Question Text

Did the ruler appoint competent economic professionals and empower them, rather
than loyalists, family members, business partners, or ideological yes-men?

## What This Question Asks

Whether key economic-policy posts were filled through credible competence and
whether officeholders had real authority to give evidence-based advice, administer
policy, resist improper pressure, and remain when advice was inconvenient. High
performance combines qualified appointments, institutional autonomy, and respected
professional process. Low performance combines nepotism or cronyism with hollow
titles, ideological obedience, intimidation, or rapid dismissal for unwelcome advice.

## What This Question Does Not Ask

- Do not infer competence solely from elite degrees, foreign credentials, or market approval.
- Do not infer empowerment from appointment alone or incompetence from one policy disagreement.
- Do not score the ruler's entire cabinet, civil service, corruption record, or economic outcomes unless they illuminate economic appointments and authority.
- Do not penalize lawful political direction; elected leaders may choose goals while professionals advise and implement.
- Do not use the client matrix as evidence.

## Researcher Instructions

Follow the mandatory local-first sequence: run bounded
`leaders-db research local-evidence` for this methodology ID/year/ISO3 and explicitly record
`not_available`; then, only as needed, use the approved
`leaders-db research parallel-search` wrapper and exact-URL fetching. Emit the required `run_profile`
with local reads, discovery attempts/results, fetches, timing, and exposed usage
(or `unknown_not_exposed_by_tool`). Every citation must include
`source_confidence`, `source_confidence_reason`, `source_type`, and
`final_evidence_use` under the source-confidence registry.

Identify finance/economy/planning ministers, central-bank leaders, senior budget
and tax officials, economic advisers, and major regulatory or state-enterprise
appointments relevant to the target period. Document qualifications and relevant
track record, selection process, family/business/party ties, statutory tenure and
actual autonomy, access to the ruler, documented influence, resignations or
dismissals, parallel informal decision centers, and credible reports of advice
overridden for loyalty or personal gain. Separate ordinary turnover and legitimate
policy disagreement from purges or capture. Preserve counterexamples within the
same administration.

Use local governance and economic priors as context, never as direct proof of who
was empowered. Prefer appointment decrees and biographies for formal facts;
central-bank statutes, court/legislative/audit records, IMF Article IV and program
documents, official minutes where reliable, academic institutional studies, and
reputable reporting for actual authority. Profile every citation.

Assess competence consistently across five dimensions rather than by credentials
or outcomes alone:

1. `relevant_expertise_experience`: subject knowledge and experience pertinent to
   the assigned institution and inherited policy problem.
2. `demonstrated_administrative_performance`: credible evidence of managing staff,
   budgets, implementation, coordination, and correction in this or prior roles.
3. `analytical_process_quality`: use of evidence, transparent assumptions,
   consultation, contingency planning, monitoring, and willingness to revise.
4. `conflicts_and_independence`: family, business, patronage, ideological, or
   financial conflicts and capacity to give unwelcome advice.
5. `mandate_execution`: whether the official performed the lawful institutional
   mandate competently, distinct from whether later macro outcomes were favorable.

Rate each dimension `strong`, `adequate`, `mixed`, `weak`, or `unclear`, with
cited reasons. Missing biographical detail is `unclear`, not proof of incompetence.

## Judge Instructions

Judge both appointment quality and practical empowerment. A technocratic appointee
who is ignored or used as a facade cannot support a high score; a politically
affiliated appointee may still be competent and independently effective. Compare
turnover, autonomy, and conflicts across the batch and ruler period. Avoid hindsight
bias from macroeconomic outcomes, and request research when qualifications or the
real decision chain are opaque.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Key economic authority is systematically reserved for family, cronies, or obedient agents, while expertise is excluded or punished. |
| 2-3 | Loyalty and personal networks repeatedly outweigh competence; qualified officials have little authority or are purged for resisting improper policy. |
| 4-5 | Mixed appointments or unclear authority: some credible professionals operate alongside politicized, conflicted, unstable, or bypassed decision centers. |
| 6-7 | Mostly competent appointments with meaningful authority, but notable politicization, interference, turnover, or weak institutional protection remains. |
| 8-9 | Strong, sustained merit-based appointments and genuine professional autonomy, including tolerance of unwelcome advice, with few material exceptions. |
| 10 | Exceptional, durable professional governance: competence and independent advice consistently prevail over personal loyalty across key institutions and crises. |

## Evidence Requirements

- At least one citation and preferably independent evidence for formal appointment and actual empowerment.
- A structured prior where available, or `not_available`; explain that it is contextual rather than direct.
- Coverage of multiple key posts or a justified explanation of why one institution dominates the case.
- Evidence on qualifications/ties and on practical authority, with contrary cases preserved.
- Source-mix and period-fit notes.

Preferred source types:

- Appointment records, statutory texts, central-bank publications, legislative hearings, courts, and audit records.
- IMF, World Bank, OECD, regional development banks, and credible professional institutional assessments.
- Academic studies, detailed biographies/interviews, and reputable investigative or wire reporting.

## Bias And Comparability Checks

Complete all common checks. Additionally check:

- `credentialism_check`: do not equate prestigious education with practical competence or integrity.
- `outcome_hindsight_check`: assess decision process without treating boom or recession as conclusive.
- `formal_actual_power_check`: test whether statutory office matched the real decision chain.
- `political_affiliation_check`: do not equate party affiliation with incompetence without evidence.
- `opacity_check`: lower confidence rather than assume merit or cronyism where appointments are undocumented.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `5b2_economic_professionals_v1`
- `severity_band`: recurrence and reach of loyalty-based appointment or professional suppression.
- `state_responsibility`: normally `direct` where the ruler appoints, dismisses, bypasses, or empowers; otherwise use the closest common value.
- `accountability_level`: institutional capacity to scrutinize appointments, conflicts, interference, and dismissals.

Question-specific additional fields:

- `appointment_quality`: `strong`, `mostly_competent`, `mixed`, `mostly_loyalist`, `captured`, `unclear`.
- `professional_empowerment`: `strong`, `meaningful`, `limited`, `facade`, `none`, `unclear`.
- `decision_center`: `formal_institutions`, `mixed`, `informal_inner_circle`, `family_or_business_network`, `unclear`.
- `turnover_interference_pattern`: concise account of tenure, dismissals, bypass, and political pressure.
- `competence_dimensions`: object containing `relevant_expertise_experience`,
  `demonstrated_administrative_performance`, `analytical_process_quality`,
  `conflicts_and_independence`, and `mandate_execution`, each rated `strong`,
  `adequate`, `mixed`, `weak`, or `unclear` with a concise cited rationale.

## Smoke-Test Ruler Set

These are calibration hypotheses, not evaluated scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Lee Kuan Yew | Singapore | 1965-1990 | high-anchor candidate; professional state capacity with concentrated political authority |
| Franklin D. Roosevelt | United States | 1933-1945 | high/mixed edge; strong expert teams, experimentation, and political direction |
| Manmohan Singh | India | 2004-2014 | positive candidate; expertise and coalition constraints |
| Recep Tayyip Erdogan | Turkey | 2018-2023 | low/mixed edge; central-bank turnover and unorthodox-policy pressure |
| Donald Trump | United States | 2017-2020 | contested middle/low; turnover, loyalty expectations, and institutional constraints |
| Robert Mugabe | Zimbabwe | 2000-2008 | low-anchor candidate; politicization and professional displacement |
| Ferdinand Marcos | Philippines | 1972-1986 | low/mixed edge; technocrats operating within family/crony capture |

## Acceptance Checklist

- Research records include citation profiles and distinguish formal appointment from actual authority.
- Multiple relevant institutions or a justified dominant institution are covered.
- Competence is assessed across all five shared dimensions; unclear dimensions reduce confidence rather than silently lowering the score.
- The judge calibrated all smoke cases together or with overlapping anchors.
- Complete calibration, substantive anchor rejections, and question-specific checks are present.
- Credential, affiliation, outcome-hindsight, and opacity biases are addressed.
- Contrary appointments and institutional constraints are preserved.
- The guide was revised after smoke testing before activation.
