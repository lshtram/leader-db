# AMLO 2022 Chapter 5B Frozen-Trio Human Benchmark

Status: initial human benchmark for extraction testing  
Benchmark version: `amlo-2022-5b-frozen-trio-human-v1`  
Reference package: `amlo-2022-5b-document-reader-ab-v1/run-13`  
Sources: `BOOK-013`, `MAC-010`, `LAW-005`

## Purpose

This benchmark defines the expected evidence content before comparing another
extractor run with earlier runs. It is based on direct reading of the frozen
reference texts, not on the number of candidates produced or accepted in any
previous calibration.

The counting unit is one traceable source supporting one materially distinct
fact. A fact is stored once and may map to several Chapter 5B lenses. Repetition
of the same fact in an executive summary, main text, annex, table, or staff
appraisal does not create another fact.

## Count Target

| Source | Core facts | Optional useful granularity | Maximum defensible total |
|---|---:|---:|---:|
| `BOOK-013` | 7 | 3 | 10 |
| `MAC-010` | 36 | 6 | 42 |
| `LAW-005` | 4 | 0 | 4 |
| **Frozen trio** | **47** | **9** | **56** |

The estimated fact universe is **47 core facts**. The extraction acceptance
target is at least **36 of those facts** (75 percent, rounded up). A run may
contain roughly **36–56 accepted facts**, depending on recall and whether it
preserves optional methodological or quantitative detail as separate claims.
Counts outside this range are diagnostic, not automatic failures:

- Fewer than 36 core facts fails the recall target.
- Between 36 and 46 core facts passes the recall target, with omitted IDs
  retained as diagnostics for later corpus stages.
- More than 56 means the excess must be checked for duplicate restatements,
  question-by-question splitting, or immaterial table fragments.
- A run can legitimately exceed 56 only when every additional item is shown to
  have a distinct material meaning and locator.

The funnel is expected to encounter repeated coverage when it expands beyond
the frozen trio. It therefore does not need to recover every fact from every
individual extraction pass. Missing facts remain visible for clustering and
gap-directed research rather than being treated as a gate failure.

## Core Fact Inventory

### `BOOK-013`: seven contextual facts

The biography ends around the 2018 inauguration. Its economic content is useful
for stated strategy and inherited commitments, but it cannot establish 2022
implementation or outcomes.

| ID | Material fact | Primary locator | Required qualification |
|---|---|---|---|
| B01 | The 2018 platform proposed reducing current public spending and redirecting resources to investment without raising taxes or issuing debt. | block 62 | Campaign commitment, not proven execution |
| B02 | It proposed gradually raising the minimum wage to 171 pesos and old-age pensions to 1,500 pesos per month by the end of the term. | block 62 | Campaign targets |
| B03 | It proposed more domestic gasoline production and refineries to reduce imports and prices. | block 62 | Campaign policy mechanism |
| B04 | It proposed reviewing and, where considered necessary, reversing the prior energy reform. | block 62 | Campaign commitment |
| B05 | It proposed energy and food self-sufficiency, including guaranteed prices for local agricultural producers. | block 62 | Campaign commitment |
| B06 | The platform combined support for macro stability, budget discipline, a floating peso, and Banco de México autonomy with opposition to privatization of strategic sectors and preference for national production and domestic demand. | block 63 | Source characterization of the platform |
| B07 | Project 18 was coordinated by Alfonso Romo and organized into four commissions, including Economy and Development, under principles including financial viability, austerity, poverty reduction, and sustainable development. | block 60 | Planning/personnel context; no proof of 2022 operational independence |

Optional biography facts are the free nationwide internet proposal, the student
scholarship proposal, and the Santa Lucía airport alternative in block 64.
They may be retained as pre-period investment/distribution context, but do not
belong in the core 2022 evidence set.

### `MAC-010`: 36 core facts

| ID | Material fact | Primary locator |
|---|---|---|
| M01 | Real GDP expanded 1.8 percent in the first half of 2022 after stagnation in the second half of 2021; the report attributes the pickup mainly to catch-up momentum, improving wages, and fiscal support. | page 8, ¶3 |
| M02 | Recovery was uneven: labor conditions improved ahead of output, construction and some services remained below pre-pandemic output, and the estimated output gap was nearly closed by mid-2022. | page 9, ¶4 |
| M03 | By August 2022 headline inflation was 8.7 percent, food inflation 14.1 percent, and core inflation 8.1 percent; food accounted for more than half the excess over target. | page 9, ¶5 |
| M04 | IMF staff projected growth of 2.1 percent in 2022 and 1.2 percent in 2023, with weaker U.S. growth and tighter financial conditions central to the slowdown. | page 13, ¶¶13–14 |
| M05 | Without significant structural reforms, medium-term growth was expected to be about 2 percent and potential output growth per capita only slightly above 1 percent. | page 14, ¶16 |
| M06 | Mexico's short-run GDP exposure to U.S. growth exceeded one-for-one in the report's estimate, while nearshoring was a possible upside risk. | pages 14–15, ¶17; pages 76–77 |
| M07 | Banco de México raised its policy rate to 9.25 percent through progressively larger hikes, leaving the ex-ante real rate near 4 percent by September 2022. | pages 10 and 17, ¶¶6, 19 |
| M08 | IMF staff assessed Banxico's response as appropriately proactive but recommended further restrictive policy and clearer rate-path communication. | pages 17–18, ¶¶19–22 |
| M09 | The government maintained a broadly neutral 2022 fiscal stance, targeting a deficit of 3.8 percent of GDP; staff estimated gross public-sector debt near 56 percent of GDP. | page 2 |
| M10 | Staff assessed public debt as sustainable, but warned that weaker growth or fiscal slippage would put it on a rising path. | page 21, ¶30 |
| M11 | FEIP reserves had fallen below 0.1 percent of GDP after pandemic use, constraining rapid shock response; the authorities proposed reforms intended to rebuild it. | page 21, ¶29 |
| M12 | The peso remained comparatively stable despite portfolio outflows, supported by rate differentials, fiscal and monetary credibility, remittances, and adequate reserves. | pages 11 and 22 |
| M13 | Banks were well capitalized, with capital adequacy above 19 percent, comfortable liquidity, declining nonperforming loans, and broadly contained systemic vulnerabilities. | pages 12 and 23, ¶¶10, 35 |
| M14 | The FSAP identified gaps in regulatory-agency autonomy/resources, consolidated supervision, crisis resolution, macroprudential tools, and cybersecurity oversight. | pages 24–25, ¶¶37–38 |
| M15 | Mexico had aligned much of its AML/CFT framework with FATF standards, but effectiveness, beneficial-ownership information, enforcement resources, and fintech risks still required work. | page 25, ¶41 |
| M16 | The 2022 anti-inflation package relied heavily on fuel subsidies; authorities estimated all measures at about 1.86–2 percent of GDP. | pages 19 and 74, ¶23 |
| M17 | Fuel-price stabilization cost about 1.4–1.5 percent of GDP and directly reduced headline inflation by about 2 percentage points at its peak effect. | pages 19 and 74–75 |
| M18 | Fuel support was poorly targeted: higher-income households benefited disproportionately; the top income quintile accounted for about 45 percent of fuel-excise payments versus 6 percent for the bottom quintile. | pages 19–20, ¶¶23, 29 n.7 |
| M19 | Higher oil revenue approximately offset the 2022 fuel-subsidy cost, but that balance depended on oil/refining margins and could require cuts elsewhere after another price spike. | pages 74–75, ¶¶3–4 |
| M20 | Food-price measures mostly expanded existing agricultural and household programs, cost roughly 0.25–0.3 percent of GDP, and had minimal or unclear direct inflation effects. | pages 19 and 74–75 |
| M21 | Fiscal support, minimum-wage increases, labor measures, recovery, and record remittances may collectively have contributed to about 5 percent year-on-year growth in real per-capita labor income by mid-2022. | page 19, ¶24 |
| M22 | The minimum wage was projected to rise from 42 percent of the median formal wage in 2018 to 59 percent in 2022, while staff warned continued large increases could add inflation and formality risks. | pages 19 and 31, ¶¶24, 54 |
| M23 | Universal/noncontributory pensions were increased; pension reforms expanded eligibility and minimum benefits but raised near-term costs and could weaken formal-work incentives. | pages 19 and 91–92 |
| M24 | The 2021 subcontracting law restricted labor outsourcing; most affected workers appear to have shifted to direct employment without a material aggregate employment loss, though GDP measurement was distorted. | pages 69–70 |
| M25 | Poverty remained around 40 percent, rose during the pandemic, and had returned roughly to pre-pandemic levels as real income recovered. | page 27, ¶44 |
| M26 | Large regional inequalities persisted, with the South experiencing less integration, investment, opportunity, and real income than northern and central regions. | page 27, ¶45 |
| M27 | The administration's development agenda combined redistribution, USMCA implementation, wage and outsourcing reforms, pensions, and Isthmus infrastructure, while staff found important productivity constraints unresolved. | page 28, ¶46 |
| M28 | Spending on education, health, public investment, and safety nets remained below relevant comparators; staff proposed a permanent 2–3 percent-of-GDP productive-spending increase financed by tax reform. | pages 28–30, ¶¶47–51 |
| M29 | Non-oil revenue was nearly 6 percent of GDP below Latin American peers and about half the OECD average; staff recommended VAT, income, property, and carbon-tax reforms with protection for poor households. | page 29, ¶50 |
| M30 | Tax-administration reforms since 2019 coincided with income/corporate-tax and VAT revenue gains of 1.0 and 0.6 percent of GDP by 2022, but the report says causal isolation is difficult and returns may diminish. | page 90 |
| M31 | PEMEX's first-half 2022 earnings more than doubled and debt declined somewhat, but debt remained high and staff called for restructuring, profitable-field focus, asset sales, pension reform, and more private partnerships. | pages 12–13 and 29 |
| M32 | Weak contract enforcement, corruption, crime, and incomplete anticorruption implementation continued to impede investment, formal employment, public services, and business formation. | page 30, ¶53 |
| M33 | USMCA implementation included independent state labor courts, but sectoral restrictions, cumbersome permits, competition-authority budget cuts, and other regulatory hurdles constrained competition. | page 32, ¶55 |
| M34 | A new electricity law replaced auctions with nonmarket policies and gave regulatory power to CFE, creating conflicts of interest and disrupting contracts; the attempted constitutional reversal remained incomplete. | pages 32–33, ¶56 |
| M35 | Authorities reported sharply increased public investment in underdeveloped regions and faster labor-dispute resolution, while staff continued to identify human-capital, infrastructure, governance, and productivity gaps. | page 33, ¶58 and page 35 |
| M36 | Authorities defended fuel-price stabilization as a presidential commitment supporting households and limiting second-round inflation; IMF staff preferred more targeted support to protect priority spending and price signals. | pages 20–22, ¶¶27, 29, 31 |

The six optional IMF facts are: detailed 2023 budget composition; the downside
scenario's modeled output loss; the tariff/retailer components of PACIC as
separate items; detailed pension parameter changes; the emissions-trading and
carbon-pricing package; and pension funds' stabilizing role in the domestic
government-securities market. Each is useful, but none is required to preserve
the materially decisive Chapter 5B account from this three-source package.

### `LAW-005`: four core facts

| ID | Material fact | Primary locator |
|---|---|---|
| L01 | Agreement 173/2022 formally set fuel-tax support for 10–16 December 2022 under the cited fuel-stimulus decrees. | block 1 |
| L02 | The support percentages were 26.96 percent for gasoline below 91 octane, zero for gasoline at or above 91 octane/non-fossil fuels, and 59.77 percent for diesel. | block 2, Article One |
| L03 | The corresponding fiscal-stimulus amounts were 1.4803, 0, and 3.6071 pesos per liter, and the reduced IEPS quotas were 4.0114, 4.6375, and 2.4283 pesos per liter. | block 2, Articles Two–Three |
| L04 | Complementary per-liter support was zero for all three fuel categories during that week. | block 2, Article Four |

These facts establish the legal instrument and exact weekly rates. They do not
by themselves establish incidence, pass-through, annual fiscal cost, policy
effectiveness, or a personal presidential decision.

## Quality Gate

### Final accepted evidence

All accepted evidence must satisfy every hard condition:

1. The stored excerpt is copied by code as one contiguous span from the frozen
   source and is hash-bound to that source.
2. The locator resolves to that span, and the span alone supports the factual
   wording without relying on an unstored neighboring passage.
3. Dates, quantities, actors, attribution, legal status, and causal language do
   not exceed the source.
4. Forecasts, recommendations, authorities' views, IMF staff findings, enacted
   rules, implementation, and outcomes are labeled distinctly.
5. Pre-period campaign material is labeled contextual and cannot be presented
   as evidence of 2022 implementation.
6. One fact is stored once and mapped to all applicable questions; question
   mappings do not duplicate the text.
7. Contrary findings and material qualifications are preserved.
8. Repeated IMF source passages and official data restated by the IMF are not
   counted as independent corroboration.

Because citation text and locators are captured deterministically, exact span
integrity remains a hard technical requirement: every stored quotation must
match its cited source span. The factual-accuracy target for candidate claims is
**at least 90 percent**. Errors must remain auditable and correctable by the
verification stage; they are not converted into a requirement for perfect
first-pass semantic extraction.

### Extraction performance

- **Core recall:** at least 75 percent of the 47 core facts: **36 facts** after
  rounding up.
- **Factual accuracy:** at least 90 percent of extracted claims must be
  materially distinct and supported at the stated level of attribution,
  certainty, and temporal fit.
- **Citation-span integrity:** 100 percent of stored quotations and locators
  must resolve exactly because these are captured and checked by code rather
  than reproduced from model memory.
- Attribution errors include turning a campaign promise into implementation,
  an IMF recommendation into government action, or a Banco de México action
  into a personal presidential action. These count against the 90 percent
  factual-accuracy target.

There is no separate “pivotal fact” gate. Material importance is a later judge
assessment and is contestable; the extraction test should not encode one
reviewer's view of which facts will decide the chapter.

## Diagnosing Count Errors

### Under-extraction

Under-extraction is measured by missing core IDs, not merely by a low record
count. The extraction gate weights the 47 core facts equally; later clustering,
gap research, and judging may assess their relative importance.

### Over-extraction

The following do not create distinct facts:

- the same fuel-subsidy findings repeated in the executive summary, main text,
  annex, and appraisal;
- one copy of a fact for each question to which it maps;
- splitting one three-fuel table into nine isolated cells when the table's
  material meaning is preserved by one or two records;
- separating a recommendation from each sentence of its supporting rationale
  when they express one policy judgment;
- chart labels, headings, footnotes, or forecast years with no independent
  judge-useful meaning;
- multiple fragments required only because the model failed to request enough
  adjacent context.

The benchmark therefore does not classify the earlier **41-candidate** run from
its count alone: it can pass if at least 36 core facts are present at 90 percent
accuracy. The earlier **236-candidate** run remains a strong over-extraction
signal, but that conclusion must likewise be confirmed by matching both runs
against these fact IDs rather than comparing counts alone.
