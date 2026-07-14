# 6B.2 Access to Basic Services and Social Protection

Status: draft

## Question Identity

- `methodology_id`: `6B.2`
- Category: social well-being and human development
- Evidence strategy: `internet_manual`
- Rubric version: `6b2_basic_services_access_v1`
- Guide owner/status note: Initial draft for smoke testing; not production-ready.

## Question Text

Did the ruler improve access to basic health, education, water, sanitation,
housing, food security, and social protection?

## What This Question Asks

Whether ruler-attributable policy and implementation produced meaningful,
equitable, and reasonably durable improvement in access across this portfolio.
High performance requires broad evidence of real availability, affordability,
quality, and uptake, with attention to underserved groups. Low performance means
substantial deterioration, deliberate exclusion, destruction, diversion, or
failure to act despite feasible options.

## What This Question Does Not Ask

- Do not require every listed domain to improve equally, but do not generalize from one flagship service to the whole portfolio.
- Do not treat enrollment, facility counts, legal entitlement, or spending as access without quality, affordability, or use evidence.
- Do not attribute demographic trends, donor programs, or inherited pipelines automatically to the ruler.
- Do not compare absolute levels without baseline, income, conflict, geography, and shock context.
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

Build a domain matrix for health, education, water, sanitation, housing, food
security, and social protection. For each relevant domain record baseline and
target-period change; policy and implementation; rural/urban, regional, income,
gender, minority, disability, migrant or conflict-displacement gaps; affordability,
quality and uptake; durability; ruler attribution; and contrary indicators. Mark
domains unavailable rather than assuming no change. Separate nationwide access
from pilots and outputs from outcomes. Identify donor or subnational contributions,
conflict damage, disasters, pandemics, and data breaks.

Start with local WDI, UNDP, PIP and available country-year facts. Prefer national
statistics and household surveys with methodology metadata; WHO, UNICEF, UNESCO,
JMP, ILO, FAO/WFP, UN-Habitat, UNHCR and World Bank; independent audits and
evaluations; peer-reviewed research; and credible civil-society/media evidence for
exclusion or implementation gaps. Profile every citation and avoid mixing indicator
definitions or survey vintages silently.

## Judge Instructions

Judge improvement from the inherited baseline and feasible counterfactual, not
wealth level. Assess portfolio breadth, magnitude, distribution, quality, and
durability, while recording which domains are evidenced. One exceptional program
cannot conceal widespread deterioration; likewise, an unavoidable crisis setback
does not establish ruler failure if preparation and mitigation were strong. Weight
ruler attribution and independent corroboration. Use insufficient evidence when
domain or time coverage is too thin.

Apply portfolio-coverage gates before scoring. A domain is `evidenced` only when
at least one suitably profiled source supports a period-fit access claim; repeated
indicators from one publisher do not create independent domain coverage. Use these
caps unless the judge documents an exceptional reason and sends it to manual review:

- 0-1 evidenced domains: `insufficient_evidence`; no score.
- 2 evidenced domains: maximum score 5.
- 3 evidenced domains: maximum score 6.
- 4 evidenced domains: maximum score 7.
- 5 evidenced domains: maximum score 8.
- 6 evidenced domains: maximum score 9.
- All 7 domains: eligible for score 10, but coverage alone never warrants it.

For scores 8-10, evidence must also include at least three independent source types,
baseline-to-period comparison, distribution, quality/affordability, attribution,
and no unexamined material deterioration in an evidenced domain. A domain marked
`unavailable` means the search and local-first process found no adequate period-fit
evidence and lowers confidence/coverage; it must never be coded as `unchanged` or
`no_improvement`. `No improvement` requires affirmative evidence of stagnation or
deterioration.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Ruler action or knowing neglect drives catastrophic, broad deterioration or systematic exclusion across essential services and protection. |
| 2-3 | Severe deterioration, exclusion, destruction, diversion, or persistent feasible neglect affects several domains or large vulnerable populations. |
| 4-5 | Mixed or modest change: some meaningful gains coexist with stagnation, deterioration, poor quality, narrow coverage, or major inequalities. |
| 6-7 | Clear, reasonably broad improvement in real access, with remaining domain gaps, unequal reach, quality problems, or limited durability. |
| 8-9 | Large, independently evidenced, equitable and durable gains across most relevant domains, including underserved groups, with few material setbacks. |
| 10 | Exceptional portfolio-wide transformation from baseline, with near-universal effective access, strong quality and durability, and robust attribution to ruler-led action. |

## Evidence Requirements

- At least one suitably profiled citation per evidenced domain; multiple independent source types are required for high scores.
- A structured-source prior where available, or `not_available` with explanation.
- A domain-coverage matrix stating evidenced, unavailable, unchanged, improved, or worsened domains.
- Baseline and target-period fit, ruler attribution, distribution, quality/affordability, and contrary evidence.
- A source-mix note; low or very-low confidence sources may not solely support material claims.

Preferred source types:

- National statistics/household surveys and independently audited administrative data.
- WHO, UNICEF/JMP, UNESCO, ILO, FAO/WFP, UN-Habitat, UNHCR, UNDP, World Bank, and regional development banks.
- Peer-reviewed evaluations, audit institutions, credible civil society, and reputable media for implementation and exclusion gaps.

## Bias And Comparability Checks

Complete all common checks. Additionally check:

- `baseline_and_income_check`: compare change and feasible action, not raw country rank.
- `portfolio_balance_check`: prevent one well-measured domain from standing in for all seven.
- `access_quality_check`: distinguish nominal availability from affordable, safe, usable, good-quality service.
- `distribution_check`: inspect group and geographic gaps rather than national averages alone.
- `attribution_check`: separate ruler policy from inherited projects, donors, subnational government, trends, and shocks.
- `measurement_break_check`: identify survey, definition, PPP, boundary, and administrative-reporting changes.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `6b2_basic_services_access_v1`
- `severity_band`: breadth and magnitude of access deterioration/exclusion or remaining deprivation.
- `state_responsibility`: `direct`, `failed_to_prevent`, or another common value based on attribution.
- `accountability_level`: strength of measurement, audit, complaint, correction, and remedy for service failure.

Question-specific additional fields:

- `domain_coverage`: object covering `health`, `education`, `water`, `sanitation`, `housing`, `food_security`, and `social_protection`; each value is `improved`, `unchanged`, `worsened`, or `unavailable`, with source IDs and a period-fit note.
- `evidenced_domain_count`: integer 0-7 used to enforce the portfolio score cap.
- `access_change`: `transformative_improvement`, `broad_improvement`, `mixed`, `little_change`, `broad_deterioration`, `catastrophic_deterioration`, `unclear`.
- `distribution_of_change`: `equitable`, `mostly_broad`, `uneven`, `narrow_or_exclusionary`, `unclear`.
- `quality_affordability`: `strong`, `adequate`, `mixed`, `weak`, `unclear`.
- `ruler_attribution`: `strong`, `moderate`, `weak`, `negative`, `unclear`.

## Smoke-Test Ruler Set

These are calibration hypotheses, not evaluated scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Park Chung-hee | South Korea | 1961-1979 | positive/mixed edge; rapid service and education gains with baseline and attribution questions |
| Paul Kagame | Rwanda | 2000-2023 | positive/contested; broad health gains, inequality and information-environment checks |
| Lula da Silva | Brazil | 2003-2010 | positive candidate; social protection and poverty/food-security gains across a large federation |
| Narendra Modi | India | 2014-2023 | mixed/positive edge; sanitation, water and protection expansion versus quality and distribution gaps |
| Hugo Chavez | Venezuela | 1999-2013 | mixed trajectory; early access gains versus durability and data-quality concerns |
| Nicolae Ceausescu | Romania | 1981-1989 | low-anchor candidate; austerity-era food, heat, health and household deprivation |
| Kim Jong Il | North Korea | 1994-2011 | low/closed-information edge; famine and service collapse with attribution and evidence constraints |
| Ellen Johnson Sirleaf | Liberia | 2006-2018 | baseline/constraint edge; post-conflict rebuilding, donor attribution, and Ebola shock |

## Acceptance Checklist

- Research records contain citation profiles and a seven-domain coverage matrix.
- Portfolio score caps are enforced; `unavailable` is never treated as no improvement.
- Baseline, effective access, quality, affordability, distribution, durability, and attribution are distinguished.
- Indicator definitions and time-series breaks are documented.
- Smoke cases are calibrated together or with overlapping anchors.
- Every score-bearing record has complete common and question-specific calibration.
- Anchor rejections and bias checks are substantive; contrary evidence is preserved.
- The guide was revised after smoke testing before activation.
