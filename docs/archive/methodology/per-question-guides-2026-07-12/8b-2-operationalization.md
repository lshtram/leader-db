# 8B.2 Program Operationalization

Status: draft; not yet smoke-tested

## Question Identity

- `methodology_id`: `8B.2`
- Category: `ruler_effectiveness_and_competence`
- Evidence strategy: `internet_manual`
- Rubric version: `8b2_program_operationalization_v1`
- Guide owner/status note: initial ideology-neutral draft for guide expansion.

## Question Text

Does the ruler translate that program into concrete priorities, plans, budgets,
appointments, timelines, institutions, and enforcement mechanisms?

## What This Question Asks

Registry context: 8B is ideology-neutral and measures execution capacity against
the ruler's own declared or revealed program. Moral judgment belongs elsewhere.

Higher scores mean the ruler converts an identifiable program into a credible
operating architecture: prioritized plans, resources, responsible personnel,
sequencing, timelines, institutions, legal authorities, monitoring, and
enforcement appropriate to the stated or revealed goals. Lower scores mean the
program remains rhetorical, unfunded, unassigned, internally contradictory, or
administratively implausible. Assess design and commitment, not ultimate results.

An identifiable explicit or rigorously evidenced revealed program is a
score-bearing prerequisite. If the program is unclear, return insufficient
evidence and request targeted `8B.1` follow-up; do not assign a midpoint or low
score merely because the comparison baseline is missing.

## What This Question Does Not Ask

- Do not judge whether the goals are moral, lawful, democratic, peaceful, or good
  public policy; harmful coercive programs may be operationalized competently.
- Do not reward outcome success (`8B.7`/`8B.10`) or full implementation/state
  reach (`8B.3`, `8B.5`, `8B.6`) except as evidence that an operating mechanism existed.
- Do not infer commitment from headline spending alone; test alignment,
  additionality, execution authority, and opportunity costs.
- Do not penalize a ruler for inherited bureaucracy unless evidence shows their
  own program was not translated into operational choices.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Follow [`../local-first-researcher-guide.md`](../local-first-researcher-guide.md),
query exact-case local evidence, and apply
[`../source-confidence-registry.json`](../source-confidence-registry.json).
Structured governance capacity is context, not proof that this ruler
operationalized this program. Use approved Parallel Search for discovery, cite
underlying URLs, provide all four citation-profile fields, and emit `run_profile`.

## Researcher Instructions

First identify the program using `8B.1` evidence or state that it is unclear.
Then trace each material goal to plans, laws/decrees, budgets and actual
appropriations, appointments with mandates, timelines/milestones, new or repurposed
institutions, interagency responsibility, territorial channels, monitoring, and
enforcement. Test whether resources and authorities are proportionate, not merely
announced. Seek contrary evidence: unfunded mandates, delayed budgets, vacant or
incompetent appointments, contradictory agencies, symbolic bodies, abandoned
timelines, or legal blockage. Separate target-year action from inherited or later
machinery. Do not assign a final score.

## Judge Instructions

Apply `8b2_program_operationalization_v1` across the batch. Score the documented
chain from program to operating mechanism, including coverage of the ruler's main
priorities, specificity, resources, responsibility, timing, and enforceability.
Do not let moral approval, repression, generic state capacity, or later outcomes
drive the score. Adjust for tenure and genuine external constraints without
turning aspiration into operationalization. If `8B.1` direction is genuinely
unclear, do not score: mark insufficient evidence and request targeted `8B.1`
research rather than inventing a program or imposing a midpoint/low penalty.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | No credible translation of program into operating machinery; major goals remain slogans or chaotic decrees without resources, responsibility, sequencing, or enforceability. |
| 2-3 | Sparse or largely symbolic plans, appointments, and budgets; severe gaps and contradictions make operational commitment implausible. |
| 4-5 | Some concrete mechanisms exist, but important priorities are unfunded, weakly assigned, delayed, fragmented, or dependent on improvised enforcement. |
| 6-7 | Most major priorities have credible plans, resources, personnel, institutions, and timelines, though notable design, coordination, or enforcement gaps remain. |
| 8-9 | Strong, coherent operational architecture covers the main program with aligned budgets, capable mandates, sequencing, monitoring, and enforcement. |
| 10 | Exceptional conversion of the full priority program into specific, adequately resourced, accountable, adaptive, and durable operating mechanisms. |

## Evidence Requirements

Minimum evidence: one citation, local-prior status, an identifiable explicit or
rigorously evidenced revealed program as a score-bearing prerequisite,
target/ruler-period operational evidence, contrary evidence, and source-mix note.
At least two operational channels should be examined when relevant; announcement-
only evidence cannot support a high anchor. Preferred sources: enacted budgets,
appropriation and expenditure records; laws, decrees, regulations, implementation
plans and timelines; appointment/mandate records; audit, legislative oversight,
procurement and implementation reports; intergovernmental program reviews;
academic analyses and reputable media. Official documents are strong for formal
design and allocations, but self-reported sufficiency or success requires
independent corroboration.

## Bias And Comparability Checks

Complete all common checks. Address better documentation in rich/open states;
opaque off-budget and coercive machinery; central versus federal/coalition powers;
country size and administrative complexity; inherited versus ruler-created
mechanisms; nominal versus real budget values; tenure and realistic planning lag;
crisis improvisation; and outcome/morality contamination.

## Required Calibration Values

Use every common calibration field, explicitly interpreting the generic values.

- `rubric_version`: `8b2_program_operationalization_v1`
- `severity_band`: common enum, interpreted as extent of operationalization gaps
- `state_responsibility`: common enum, interpreted as ruler ownership/control of mechanisms
- `accountability_level`: common enum, interpreted as monitoring, correction, and enforceable responsibility
- `operationalization_status`: `none`, `symbolic`, `partial`, `substantial`, `comprehensive`, or `unclear`
- `mechanisms_present`: list from `priorities`, `plans`, `budgets`, `appointments`, `timelines`, `institutions`, `legal_authority`, `monitoring`, `enforcement`, `none_found`, `unclear`
- `resource_alignment`: `absent`, `weak`, `mixed`, `strong`, `comprehensive`, or `unclear`
- `program_dependency`: `clear_8b1_program`, `partly_inferred_program`, `unclear_program`, or `not_available`; `unclear_program` and `not_available` require insufficient-evidence disposition and targeted `8B.1` follow-up, not a score
- `implementation_stage`: `announcement`, `formal_adoption`, `resourced_setup`, `operating`, `not_applicable`, or `unclear`

## Smoke-Test Ruler Set

Plausible roles only; no final scores are assigned here.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Franklin D. Roosevelt | United States | 1933-1936 | broad program-to-institution/budget high candidate |
| Lee Kuan Yew | Singapore | 1965-1980 | long-horizon institutional operationalization candidate |
| Adolf Hitler | Germany | 1933-1939 | harmful coercive program; ideology-neutrality stress test |
| Narendra Modi | India | 2014-2019 | scale, federalism, and program machinery case |
| Donald Trump | United States | 2017-2020 | plans, appointments, budget alignment, and fragmentation case |
| Boris Yeltsin | Russia | 1991-1999 | crisis, weak institutions, and external-advice edge |
| Volodymyr Zelenskyy | Ukraine | 2022 | wartime emergency operationalization edge |
| Liz Truss | United Kingdom | 2022 | short-tenure announcement-versus-machinery edge |

## Acceptance Checklist

- Local-first order, source profiles, and run profile are present.
- An explicit or carefully labeled revealed program precedes assessment.
- An unclear or unavailable program blocks scoring and triggers targeted `8B.1` follow-up rather than a midpoint/low penalty.
- Plans, resources, responsibility, timing, institutions, monitoring, and enforcement are traced.
- Announcements and nominal budgets are not treated as sufficient by themselves.
- Operationalization is separated from morality, generic capacity, implementation, and outcomes.
- Contrary design and resource evidence is preserved.
- One batch judge completes all fields and substantive adjacent-anchor rejections.
- Smoke roles are tested and the guide is revised before activation.
