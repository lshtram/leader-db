# 6B.1 Human Welfare as a Core Purpose

Status: draft

## Question Identity

- `methodology_id`: `6B.1`
- Category: social well-being and human development
- Evidence strategy: `internet_manual`
- Rubric version: `6b1_welfare_core_purpose_v1`
- Guide owner/status note: Initial draft for smoke testing; not production-ready.

## Question Text

Did the ruler treat human welfare as a core purpose of rule rather than as
propaganda, patronage, or secondary concern?

## What This Question Asks

Whether welfare was a durable, governing priority revealed by budgets,
institutions, implementation, crisis tradeoffs, monitoring, and willingness to
serve people outside the ruler's support base. High performance means welfare
regularly shapes consequential choices. Low performance means neglect, spectacle,
conditional largesse, or propaganda substitutes for genuine provision.

## What This Question Does Not Ask

- Do not score welfare outcomes or service access alone; 6B.2 covers access and 6B.10 covers inherited-to-left trajectory.
- Do not equate high social spending with priority without testing execution, incidence, and opportunity costs.
- Do not equate universal rhetoric, a flagship project, or leader-branded charity with a welfare-centered state.
- Do not punish a poor country simply for low absolute service levels.
- Do not use the client matrix as evidence.

## Researcher Instructions

Follow the mandatory local-first sequence: run bounded
`leaders-db research local-evidence` for this methodology ID/year/ISO3 and explicitly record
`not_available`; then use the approved `leaders-db research parallel-search`
wrapper only for unresolved gaps and exact-URL fetching for selected sources. Emit
the required `run_profile` with local artifact/CLI reads, discovery
attempts/results, fetches, timing, and exposed usage (or
`unknown_not_exposed_by_tool`). Every citation must carry `source_confidence`,
`source_confidence_reason`, `source_type`, and `final_evidence_use` under the
source-confidence registry.

Gather evidence on stated plans only when linked to budgets or action; social-sector
budget priority and execution; durable ministries, entitlements, and delivery
systems; protection during fiscal or security tradeoffs; monitoring and correction;
coverage beyond supporters; crisis conduct; and propaganda, diversion, leakage,
or political conditionality. Compare target-year choices with ruler-period patterns
and inherited capacity. Record policy reversals, fiscal constraints, conflict,
disasters, and contrary evidence.

Use local WDI, UNDP, PIP, and governance priors where available as context. Prefer
budgets and audits, laws and administrative data, WHO/UNICEF/UNESCO/ILO/FAO/UNDP,
World Bank and regional development-bank analysis, household surveys, peer-reviewed
research, and credible civil-society or media investigations. Official promotional
material is context unless corroborated. Profile every citation.

## Judge Instructions

Infer governing purpose from repeated costly choices, delivery architecture, and
correction, not speeches or outcome levels alone. Account for baseline resources
and genuine emergencies while asking how available discretion was used. Universal,
rights-based, durable systems normally provide stronger evidence than discretionary
leader-branded benefits, but assess actual implementation. Preserve mixed cases
where sincere programs coexist with patronage or exclusion.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Welfare is systematically sacrificed, weaponized, or reduced to propaganda while severe preventable suffering is knowingly disregarded. |
| 2-3 | Neglect, discriminatory patronage, diversion, or spectacle repeatedly dominates over genuine welfare purpose. |
| 4-5 | Welfare receives material attention, but priority is inconsistent, politicized, poorly executed, narrow, or readily displaced by other ruler goals. |
| 6-7 | Welfare is a substantial and recurring governing priority with real institutions and delivery, but important exclusions, patronage, or tradeoff failures remain. |
| 8-9 | Welfare consistently drives budgets, institutions, crisis choices, and correction across groups, with limited material politicization. |
| 10 | Exceptional and durable human-centered rule demonstrably prioritizes dignity and welfare even under severe constraints and adverse political incentives. |

## Evidence Requirements

- At least one citation, preferably with two independent source types for the governing-priority claim.
- A structured prior where available, or `not_available`, treated as context rather than direct proof of intent.
- Evidence from consequential choices: budgets, institutions, implementation, crisis tradeoffs, or correction.
- Evidence on universality versus political conditionality and at least one contrary finding or explicit gap.
- Source-mix and target-year/ruler-period notes.

Preferred source types:

- Budgets, laws, audits, administrative records, household surveys, and independent fiscal institutions.
- UN agencies, World Bank, regional development banks, and local structured human-development data.
- Peer-reviewed public-policy research, credible civil society, and reputable investigative or wire reporting.

## Bias And Comparability Checks

Complete all common checks. Additionally check:

- `income_baseline_check`: judge prioritization within available means, not absolute service standards.
- `spending_delivery_check`: separate appropriations and headline spending from execution and beneficiary experience.
- `propaganda_branding_check`: test whether leader branding obscures weak, conditional, or inherited provision.
- `security_tradeoff_check`: examine whether prestige/security projects displaced feasible welfare protection.
- `universalism_check`: identify political, ethnic, regional, gender, citizenship, or class exclusions.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `6b1_welfare_core_purpose_v1`
- `severity_band`: recurrence and breadth of welfare neglect, weaponization, or propaganda substitution.
- `state_responsibility`: `direct` for ruler-directed allocation or conditionality; otherwise use the closest common value.
- `accountability_level`: capacity to audit delivery, expose failure, correct policy, and remedy exclusion.

Question-specific additional fields:

- `welfare_priority`: `core`, `strong`, `mixed`, `secondary`, `instrumental_or_propaganda`, `unclear`.
- `delivery_commitment`: `strong`, `meaningful`, `weak`, `symbolic`, `none`, `unclear`.
- `benefit_conditionality`: `rights_based`, `mostly_universal`, `mixed`, `patronage_based`, `punitive`, `unclear`.
- `constraint_and_tradeoff_summary`: concise baseline and discretionary-choice account.

## Smoke-Test Ruler Set

These are calibration hypotheses, not evaluated scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Clement Attlee | United Kingdom | 1945-1951 | high-anchor candidate; durable welfare institutions under postwar constraint |
| Jose Mujica | Uruguay | 2010-2015 | positive candidate; welfare priority versus fiscal and implementation limits |
| Julius Nyerere | Tanzania | 1964-1985 | intent/outcome edge; strong welfare purpose with coercion and economic failures |
| Lula da Silva | Brazil | 2003-2010 | positive/mixed; institutionalized social priority and political incentives |
| Hugo Chavez | Venezuela | 1999-2013 | mixed edge; large welfare missions, leader branding, oil dependence, and politicization |
| Nicolae Ceausescu | Romania | 1981-1989 | low-anchor candidate; austerity and severe household deprivation |
| Kim Jong Il | North Korea | 1994-2011 | low/closed-information edge; famine, regime priorities, propaganda, and evidence limits |

## Acceptance Checklist

- Research records include citation confidence profiles and consequential-choice evidence.
- Priority is distinguished from access, aggregate outcomes, spending, and rhetoric.
- Baseline resources, constraints, delivery, conditionality, and crisis tradeoffs are addressed.
- Smoke cases are calibrated together or through overlapping anchors.
- Every score-bearing record has complete calibration and substantive anchor rejections.
- Contrary evidence and closed-information caveats are preserved.
- The guide was revised after smoke testing before activation.
