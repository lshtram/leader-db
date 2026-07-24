# 5B Economic Well-Being and Prosperity

Status: draft; v4 objective-evidence questions require controlled rejudgment

## Chapter Identity

- `chapter_id`: `5B`
- Category: ruler intention and action for economic well-being and prosperity
- Evidence unit: one ruler and target year or defined ruler-period
- Final output: one chapter score, not ten question scores
- Rubric version: `chapter_5b_v4`
- Judge topology: one chapter judge applies this guide across all eligible rulers in the same year/period batch.

The ten questions are overlapping lenses on one judgment: whether the ruler used available authority competently and fairly to improve durable economic opportunity.

## Ten Evidence Lenses

1. **5B.1** — Did the ruler's legislative agenda, formal policies, and executed budgets pursue broad-based sustainable prosperity rather than rents, loyalty purchases, or short-term popularity?
2. **5B.2** — Did the ruler appoint qualified economic professionals through credible processes, empower their operational independence, and retain or replace them based on performance rather than loyalty?
3. **5B.3** — Did the ruler enact, administer, and comply with credible fiscal, tax, debt, monetary, and financial rules that protected macroeconomic stability and long-term investment?
4. **5B.4** — Did the ruler create and consistently enforce fair laws and regulations for competition, entrepreneurship, property, trade, investment, and job creation?
5. **5B.5** — Did the ruler enforce competition, procurement, disclosure, and anti-corruption rules against politically connected actors, cooperate with audits and courts, and remedy proven favoritism or capture?
6. **5B.6** — Did enacted and executed budgets produce timely, high-quality infrastructure, education, health, technology, administrative capacity, and predictable regulation rather than announcements or patronage projects?
7. **5B.7** — Did the ruler publish reliable economic information, permit independent evaluation and audit, and correct laws, programs, or implementers when evidence showed failure rather than rely on slogans, denial, patronage, or scapegoating?
8. **5B.8** — Did tax, labor, wage, benefit, investment, and regional policies distribute gains and burdens fairly in actual incidence across classes, regions, genders, and groups?
9. **5B.9** — During inflation, unemployment, debt, sanctions, commodity, or other shocks, did the ruler use timely, funded, and transparently targeted measures, monitor their effects, and correct mistakes?
10. **5B.10** — Did the ruler leave a stronger and more durable economic trajectory than inherited, accounting for implementation lags, external conditions, institutional constraints, and distribution rather than GDP alone?

## Researcher Evidence Plan

Build one cited evidence dossier without scoring. Follow the local-first researcher guide and source-confidence registry. Start with local WDI, PIP, WGI, V-Dem, CPI, BTI and other available time series. Then use national statistics, budgets and audits; central-bank and fiscal records; IMF, World Bank, ILO, OECD and regional-bank analysis; peer-reviewed work; and credible investigative/local reporting. Treat government claims as context unless independently corroborated.

Collect policy choices and implementation concerning development strategy, appointments and genuine delegated authority, inflation/debt/fiscal/monetary management, market and property rules, corruption/capture, productivity investment, evidence-based correction, distribution, crisis response and inherited-to-left trajectory. Separate announcements, appropriations, implementation and outcomes. Record household/median conditions and inequality alongside averages; identify commodity cycles, sanctions, wars, disasters, global financial conditions and donor programs. Reuse evidence across genuinely related lenses and permit flexible coverage language.

Each evidence item must preserve, in fields or clearly recoverable prose: the factual claim; citation or URL plus source title, publisher and publication date when available; target-year/ruler-period fit; source-confidence assessment and source role; the basis and strength of attribution to the ruler; and material uncertainty or disagreement. Missing bibliographic details may be marked unknown rather than invented. Formatting deviations are normalization work, not grounds to discard otherwise usable evidence.

## Baseline, Attribution, and Sparse Evidence

Judge choices against feasible options at the inherited income, capacity, debt, institutions, geography, resource base and security environment. Do not credit commodity windfalls or global booms automatically, and do not debit unavoidable shocks without assessing preparation and response. Separate central ruler authority from independent central banks, legislatures, predecessor programs, subnational action and external assistance. Outcomes inform the record but do not prove attribution by themselves.

Older or lower-capacity cases may lack modern indicators. Use fiscal archives, price/wage series, historical scholarship, contemporary reports and observable institutional choices. Missing lenses reduce confidence; they never invalidate research or impose a score cap. Where only outcomes survive, state attribution uncertainty rather than inventing intent.

Baseline conditions and outcomes without a ruler-attributed policy or response are
context only and cannot determine the score's direction. If no discriminating choice,
implementation, or response is evidenced, return null. Scores outside 4–6 require
ruler-attributed policy plus independent implementation or outcome evidence; scores
of 2–3 require demonstrated dominant predation, instability, exclusion, or repeated
harmful choices, not low national income or closed-system opacity. For annual crisis
years, distinguish shock preparation and response from the inherited long-run
trajectory and do not treat one year's outcome as the whole tenure.

## Chapter Judge and Lens Weighting

One judge compares the whole ruler batch. Weight evidence qualitatively by material welfare consequence, breadth, duration, ruler control, baseline-adjusted change, source strength and sustainability. Catastrophic predation or stabilization may dominate several smaller policies. Appointments matter through their consequences and independence, not résumé prestige alone. Distribution, durability and household security prevent headline GDP from dominating. `5B.10` is a synthesis, not an extra arithmetic vote.

Ten lenses provide redundancy: missing appointment evidence may be offset by strong direct evidence of policy and results; abundant macro data cannot erase capture or exclusion. State strong and weak lenses, confidence and unresolved contradictions. Produce one score only.

## One-Chapter 1–10 Rubric

| Score | Chapter anchor |
|---:|---|
| 1 | Ruler-driven predation, catastrophic mismanagement or systematic economic exclusion destroys broad and durable prosperity. |
| 2–3 | Extraction, cronyism, reckless instability or repeated incompetent choices dominate, with little effective correction or broad counterweight. |
| 4–5 | Material gains and competent choices coexist with serious instability, capture, exclusion, weak implementation or unsustainable policy; trajectory is mixed. |
| 6–7 | The ruler makes substantially competent, broadly beneficial choices and leaves improvement, but notable distributional, institutional, stability or durability weaknesses remain. |
| 8–9 | Sustained, independently supported stewardship creates broad opportunity, stability, productive capacity and resilience with limited material failures. |
| 10 | Exceptional baseline-adjusted transformation combines broad household gains, fair institutions, resilience and durable capacity while resisting strong extractive incentives. |

## Common Chapter-Judge Output Envelope

The result should use the shared semantic envelope. Exact field spelling may be normalized after handoff.

- `chapter_id`: `5B`
- `rubric_version`: `chapter_5b_v4`
- `calibration_batch_id` and `calibrated_against`
- `score_1_to_10`, or null with `insufficient_evidence_reason`
- `confidence_score` and `plausible_score_range`
- `decisive_positive_evidence` and `decisive_negative_evidence`, referencing evidence items
- `inherited_baseline_and_constraints` and `ruler_attribution`
- `supported_lenses` and `missing_or_weak_lenses`
- `contrary_evidence` and unresolved disagreements
- `source_mix` and `structured_prior_summary`
- `chapter_rationale`, `lower_anchor_rejected`, and `higher_anchor_rejected`
- `manual_review_required`, `manual_review_reason_type`, and `manual_review_reason`

Chapter-specific extras: `external_conditions`, `distribution_and_household_effects`,
and `trajectory`.

`Insufficient_evidence` is a permitted judgment for an exceptionally thin case, not an automatic consequence of missing lenses. Flexible natural language is valid.

## Calibration, Confidence, and Bias Checks

Check income/baseline comparability, commodity and foreign-aid windfalls, crisis and sanctions context, GDP-average versus household/distribution bias, survivorship and data-quality bias, official-statistics manipulation, population/scale, regional heterogeneity, recency, hindsight and ideological bias. Do not prefer state-led or market-led policy as such; judge evidenced effects, rights, resilience and feasible alternatives.

## Smoke-Test Cases

| Ruler | Country | Period | Calibration purpose |
|---|---|---:|---|
| Seretse Khama | Botswana | 1966–1980 | resource stewardship and low-baseline institution building |
| Lee Kuan Yew | Singapore | 1965–1990 | transformation, distribution and authoritarian-context separation |
| Park Chung-hee | South Korea | 1961–1979 | rapid growth with coercion, chaebol and baseline caveats |
| Deng Xiaoping | China | 1978–1992 | large reform gains and distribution/institution attribution |
| Lula da Silva | Brazil | 2003–2010 | inclusion, commodity conditions and durability |
| Narendra Modi | India | 2014–2023 | investment/formalization versus jobs, distribution and favoritism |
| Hugo Chávez | Venezuela | 1999–2013 | early welfare gains versus oil dependence and sustainability |
| Mobutu Sese Seko | Zaire | 1965–1997 | predation and institutional destruction low anchor |
| Ellen Johnson Sirleaf | Liberia | 2006–2018 | post-conflict constraint and donor-attribution test |
| Liz Truss | United Kingdom | 2022 | very short tenure and market-shock attribution edge case |
| Maria da Lourdes Pintasilgo | Portugal | 1979–1980 | less-visible historical, short-tenure and gender calibration case |

## Acceptance Checklist

- A numeric score requires a ruler-attributed economic choice plus evidence of
  implementation, remedy, or attributable outcome. Plans, rhetoric, inherited
  macroeconomic conditions, and generic country indicators cannot set its direction.

- The exact ten lenses guide evidence but yield one chapter score.
- Local priors, citations, confidence profiles, contrary evidence and period distinctions are preserved.
- Announcements, implementation, outcomes and ruler attribution are separated.
- Baseline, shocks, distribution, household welfare and sustainability are explicit.
- Missing lenses reduce confidence and never invalidate or mechanically cap the chapter.
- One judge compares the complete batch using one meter.
- Flexible statuses/wording are normalized later rather than treated as research failure.
- Ideology and national-income level are not score shortcuts.
- Smoke cases are calibrated together before activation.
