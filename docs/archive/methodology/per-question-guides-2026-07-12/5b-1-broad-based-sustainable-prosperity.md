# 5B.1 Broad-Based, Sustainable Prosperity

Status: draft

## Question Identity

- `methodology_id`: `5B.1`
- Category: economic well-being and prosperity
- Evidence strategy: `internet_manual`
- Rubric version: `5b1_broad_sustainable_prosperity_v1`
- Guide owner/status note: Initial draft for smoke testing; not production-ready.

## Question Text

Did the ruler intend and act to create broad-based, sustainable prosperity rather
than extract rents, buy loyalty, or maximize short-term popularity?

## What This Question Asks

Whether the ruler's revealed priorities and consequential actions pursued durable,
widely shared economic opportunity. High performance requires a coherent pattern
of institution-building, productive investment, fiscal or resource stewardship,
and inclusion. Low performance means extraction, clientelism, asset stripping, or
short-lived giveaways dominated policy. Judge intent from actions, allocations,
implementation, and correction—not rhetoric alone.

## What This Question Does Not Ask

- Do not score GDP growth, commodity windfalls, or market rallies as intent by themselves.
- Do not punish unavoidable short-term relief during a genuine crisis.
- Do not duplicate 5B.3 macro stability, 5B.5 corruption, or 5B.10 inherited-to-left trajectory except where they reveal this question's governing purpose.
- Do not assume every redistribution program is vote buying or every market reform is broad-based.
- Do not use the client matrix as evidence.

## Researcher Instructions

Collect cited evidence only, following the local-first researcher guide. First run
the bounded `leaders-db research local-evidence` query for this methodology ID,
year, and ISO3; report `not_available` rather than inventing a prior. Use the
approved `leaders-db research parallel-search` wrapper only after local evidence,
and use exact-URL fetching for selected underlying sources. The worker must emit
the required `run_profile`, including local artifact/CLI reads, Parallel Search
attempts and results, fetch calls, timing, and exposed usage (or
`unknown_not_exposed_by_tool`). Every citation must carry `source_confidence`,
`source_confidence_reason`, `source_type`, and `final_evidence_use` from the
source-confidence registry. Separate
campaign statements and plans from enacted budgets, laws, implementation, and
beneficiary incidence. Identify durable productivity or institutional measures;
tax, subsidy, procurement, concession, privatization, and natural-resource choices;
regional and group distribution; patronage or electoral timing; reversals; and
independent assessments. Distinguish target-year acts from ruler-period patterns
and inherited programs. Preserve contrary evidence and explain external shocks.

Profile every citation with the source-confidence registry fields. Prefer local
WDI/PIP, WGI, V-Dem, CPI, and other structured priors where directly relevant,
then audited budgets, supreme-audit or legislative records, IMF/World Bank/ILO/OECD
analysis, peer-reviewed research, and reputable investigative or wire reporting.
Official claims about success are context unless independently corroborated.

## Judge Instructions

Compare the full question-year batch before final scores. Weight revealed choices,
implementation, distribution, and durability more than slogans or one-year outputs.
Separate inherited conditions and exogenous shocks from ruler-controlled policy.
Treat evidence volume as confidence, not merit. A mixed record may combine genuine
productive investment with patronage; explain which pattern dominates and why the
next lower and higher anchors do not fit. Request research rather than inferring
intent from sparse outcome data.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Predatory extraction or systematic asset/rent capture is the governing model, with severe, durable harm to broad prosperity. |
| 2-3 | Extraction, loyalty buying, crony privilege, or reckless short-termism repeatedly dominates, with little credible durable counterweight. |
| 4-5 | Material productive or inclusive measures coexist with substantial patronage, unsustainable populism, capture, weak implementation, or incoherence. |
| 6-7 | A credible broad-based and durable strategy is substantially implemented, but important exclusions, reversals, patronage, or sustainability weaknesses remain. |
| 8-9 | Sustained, implemented, broadly inclusive institution-building and productive investment predominate, with limited material extraction or short-term manipulation. |
| 10 | Exceptional, durable, independently evidenced stewardship consistently subordinates personal and political rents to broad prosperity, including under adverse incentives. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation, and preferably two independent source types for material claims.
- A structured-source prior where available, or `not_available` with explanation.
- Evidence of enacted action or resource allocation, not rhetoric alone.
- Evidence addressing breadth and sustainability, plus contrary evidence or an explicit search gap.
- A source-mix note and target-year/ruler-period separation.

Preferred source types:

- Audited budgets, laws, procurement/resource-concession records, audit institutions, and legislative analysis.
- IMF, World Bank, ILO, OECD, regional development banks, and local structured datasets.
- Peer-reviewed economic/political-economy research and credible independent media or civil society.

## Bias And Comparability Checks

Complete all common calibration checks. Additionally check:

- `commodity_windfall_check`: separate favorable prices or discoveries from ruler choices.
- `crisis_relief_check`: distinguish necessary temporary relief from electoral loyalty buying.
- `distribution_check`: test who actually benefited across income, region, gender, and political affiliation.
- `implementation_check`: distinguish announcements and appropriations from delivery and durable institutions.
- `baseline_constraint_check`: compare choices available at the inherited income, capacity, debt, sanctions, and conflict baseline.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `5b1_broad_sustainable_prosperity_v1`
- `severity_band`: extent and recurrence of extraction/short-termism, using the common enum.
- `state_responsibility`: `direct` for ruler-directed policy; `state_aligned`, `tolerated`, `failed_to_prevent`, or `unclear` where appropriate.
- `accountability_level`: strength of audit, correction, and consequences for extraction or failed implementation.

Question-specific additional fields:

- `policy_orientation`: `broad_sustainable`, `mostly_broad`, `mixed`, `mostly_extract_or_short_term`, `extractive`, `unclear`.
- `beneficiary_breadth`: `broad`, `uneven`, `narrow`, `regime_network`, `unclear`.
- `durability_evidence`: `strong`, `moderate`, `weak`, `none`, `unclear`.
- `external_conditions`: concise account of windfalls, shocks, sanctions, conflict, or inherited constraints.

## Smoke-Test Ruler Set

These are hypotheses for calibration roles, not evaluated scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Lee Kuan Yew | Singapore | 1965-1990 | high-anchor candidate; test breadth versus growth and state control |
| Seretse Khama | Botswana | 1966-1980 | high-anchor candidate; resource stewardship and institution building |
| Lula da Silva | Brazil | 2003-2010 | positive/mixed; inclusion, growth, commodity conditions, and durability |
| Narendra Modi | India | 2014-2023 | contested middle/edge; investment and formalization versus distribution and favoritism claims |
| Hugo Chavez | Venezuela | 1999-2013 | mixed-to-low edge; social inclusion versus oil dependence, patronage, and sustainability |
| Mobutu Sese Seko | Zaire | 1965-1997 | low-anchor candidate; personal extraction and institutional decay |
| Teodoro Obiang Nguema Mbasogo | Equatorial Guinea | 1979-2023 | low/breadth edge; resource wealth with narrow benefits |

## Acceptance Checklist

- Research records include citations, confidence profiles, and source roles.
- Acts, allocations, implementation, breadth, and durability are distinguished from rhetoric and outcomes.
- The judge scored all smoke-test rulers in one batch or with overlapping anchors.
- Every score-bearing record includes complete calibration fields.
- Scores are coherent relative to adjacent cases and account for baseline and shocks.
- Anchor rejections and bias checks are substantive.
- Contrary evidence and caveats are preserved.
- The guide was revised after smoke testing before activation.
