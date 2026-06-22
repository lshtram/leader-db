# Ranking Evaluation Criteria

This document is the working question bank for the 8 ruler-year ranking
categories in `leaders-db`. It translates the currently identified source
metrics into plain-language evaluation questions: for each category, what are we
trying to answer, which sources already answer that question, and which extra
questions should remain available for later expert/LLM adjudication even when no
current structured source covers them.

The client/customer 2023 matrix is intentionally absent from the evidence
columns. It is a validation reference only, not a scoring source.

## Scope and status

- Current category source plans live in `src/leaders_db/score/category_plans/`.
- Current scorer group weights live in `src/leaders_db/score/_*_rubric.py`.
- Current source coverage and caveats live in `docs/source-vetting/report.md` and
  `docs/data-sources.md`.
- Some vetted sources are not yet in the operational Stage 9 plans because their
  Stage 2 adapters or raw-bundle hygiene are blocked. They are still listed here
  where relevant as future coverage.

Legend:

- **Used now** — included in the current category source plan / scorer rubric.
- **Vetted, not active** — vetted or user-managed but not currently wired into
  the scoring plan.
- **Additional standard** — useful question from established governance,
  human-rights, development, peace/conflict, or nuclear-risk standards, but not
  currently answered directly by our structured sources.
- **Exclude / low value** — collected by a source or derivable from it, but not a
  good independent scoring question for this category.

## Cross-category source references

- **V-Dem**: democracy, civil-liberties, corruption, governance, egalitarian, and
  repression indicators. The V-Dem v16 codebook organizes high-level democracy
  indices such as `v2x_polyarchy` and `v2x_libdem`, mid-level components, and
  indicator families including elections, executive, judiciary, civil liberty,
  media, and political equality: <https://www.v-dem.net/documents/70/codebook_v16.pdf>.
- **World Bank WGI**: six governance dimensions: Voice and Accountability,
  Political Stability, Government Effectiveness, Regulatory Quality, Rule of
  Law, and Control of Corruption. WGI defines governance as how authority is
  selected/monitored/replaced, government policy capacity, and respect for
  institutions: <https://www.worldbank.org/en/publication/worldwide-governance-indicators/frequently-asked-questions>.
- **PTS**: 1-5 political-terror scale from Amnesty International, Human Rights
  Watch, and U.S. State Department human-rights reports; coders assess scope,
  intensity, and range of physical-integrity abuse: <https://www.politicalterrorscale.org/Data/Documentation.html>.
- **CIRIGHTS**: physical-integrity rights components for disappearances,
  extrajudicial killings, political imprisonment, torture, plus additive rights
  indices.
- **UCDP**: state-based conflict, internationalized conflict, and one-sided
  violence event/fatality signals: <https://ucdp.uu.se/downloads/>.
- **SIPRI milex**: military expenditure as resource burden / scale signal,
  including share of GDP, per-capita spending, constant USD, and share of
  government spending: <https://www.sipri.org/databases/milex/sources-and-methods>.
- **FAS / SIPRI Yearbook Ch.7**: nuclear arsenal inventory, deployed warheads,
  stockpile/reserve, and retired warheads. SIPRI Yearbook 2025 describes global
  inventory, military stockpiles, and warheads available for potential use:
  <https://www.sipri.org/sites/default/files/SIPRIYB25c06%266A.pdf>.
- **UNDP HDI**: health, education, and standard-of-living dimensions: life
  expectancy, expected/mean years of schooling, and GNI per capita:
  <https://hdr.undp.org/data-center/human-development-index>.
- **Transparency International CPI**: perceived public-sector corruption using at
  least 3 data sources per country and publishing score, standard error, and
  confidence interval: <https://www.transparency.org/en/news/how-cpi-scores-are-calculated>.
- **RSF World Press Freedom Index**: press-freedom score using political,
  legal, economic, sociocultural, and journalist-safety contextual indicators:
  <https://rsf.org/en/methodology-used-compiling-world-press-freedom-index-2025>.
- **BTI**: expert-coded transformation index with political transformation,
  economic transformation, and governance dimensions; standardized codebook with
  questions/criteria: <https://bti-project.org/en/methodology>.
- **World Bank WDI**: primary World Bank collection of development indicators,
  including GDP/GNI, trade, education, health, inequality, FDI, and population:
  <https://databank.worldbank.org/source/world-development-indicators>.

---

## 1. Nuclear / global existential responsibility

Current scorer groups: FAS nuclear forces 60%, SIPRI Yearbook Ch.7 nuclear
forces 40%. This category is intentionally lighter than the others because most
countries are non-nuclear and raw arsenal counts do not fully answer leader
responsibility.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Does the country possess nuclear warheads at all? | **Used now:** FAS `fas_total_inventory`; SIPRI `sipri_yearbook_ch7_nuclear_warheads_total_inventory`. **Future cross-check:** Nuclear Weapons Ban Monitor state profiles. | Used now | Required anchor. Non-nuclear countries should not receive invented numeric evidence. |
| Does the country appear to aspire to obtain nuclear weapons or maintain a credible weapons option? | **Appropriate sources:** IAEA safeguards reports; NTI country profiles; Arms Control Association country profiles; CRS/DIA reports for specific states; official doctrine/statements. | Additional standard | Important for countries with no confirmed warheads. This captures intent and direction, not only current possession. |
| Is the country enriching uranium, separating plutonium, producing fissile material, or expanding dual-use fuel-cycle capacity in a way that raises weapons-risk concerns? | **Appropriate sources:** IAEA safeguards reports; IAEA Additional Protocol / safeguards status lists; World Nuclear Association country fuel-cycle profiles; NTI profiles. | Additional standard | Distinguish civilian safeguarded activity from suspicious, unsafeguarded, high-enrichment, reprocessing, plutonium separation, or weapons-relevant activity. |
| Has the country violated, evaded, withdrawn from, or limited nuclear safeguards and monitoring? | **Appropriate sources:** IAEA Board of Governors / safeguards reports; IAEA safeguards conclusion statements; NPT / Additional Protocol status; UN Security Council sanctions records. | Additional standard | A non-nuclear country can still create high existential responsibility through concealment, inspection denial, or breakout behavior. |
| How large is the total nuclear arsenal? | **Used now:** FAS total inventory; SIPRI total inventory. **Future cross-check:** Nuclear Weapons Ban Monitor / FAS country Nuclear Notebook articles. | Used now | Lower is better. Measures capability/risk, not intent. |
| How many warheads are deployed or operationally available? | **Used now:** FAS operational strategic / nonstrategic; SIPRI deployed warheads. **Future cross-check:** FAS country Nuclear Notebook articles; SIPRI yearbook narrative. | Used now | Stronger risk signal than inactive total inventory. |
| How large is the military stockpile versus reserve/nondeployed arsenal? | **Used now:** FAS military stockpile; FAS reserve/nondeployed. **Future cross-check:** SIPRI yearbook narrative; Nuclear Weapons Ban Monitor. | Used now | Helps separate active military capability from inactive/retired holdings. |
| Is there evidence of disarmament activity? | **Used now:** SIPRI retired warheads. **Appropriate future sources:** New START / arms-control reporting where applicable; FAS/SIPRI year-over-year deltas; UNODA treaty/status records. | Used now | Higher retired count is treated as better disarmament signal, but large retired counts can also reflect historically large arsenals. |
| Is the source observation direct-year or stale? | **Used now:** FAS snapshot date; SIPRI Yearbook publication year. **Future source hygiene:** per-source metadata timestamps and versioned report dates. | Used now via confidence / temporal-fit | FAS consolidated page has a known freshness caveat; do not treat stale FAS values as fully current. |
| Has the state signed/ratified key nuclear restraint treaties and safeguards? | **Appropriate sources:** UNODA Treaties Database; UN Treaty Collection; CTBTO treaty-status records; Nuclear Weapons Ban Monitor; IAEA safeguards / Additional Protocol status. | Additional standard | Relevant to responsibility but not yet in current source plan. NTI was blocked; future IAEA/UN treaty data could cover this. |
| Is the state expanding, modernizing, or reducing the arsenal? | **Appropriate sources:** SIPRI Yearbook modernization narrative; FAS Nuclear Notebook country articles; DIA Nuclear Challenges reports; Nuclear Weapons Ban Monitor. | Additional standard | Needed for responsibility vs static capability. Not yet normalized. |
| Is the country testing or developing nuclear-capable delivery systems, especially medium/intermediate/intercontinental ballistic missiles or submarine-launched systems? | **Appropriate sources:** CSIS Missile Threat; CNS/NTI Missile and SLV Launch Databases; FAS/NTI country profiles; UN sanctions/expert-panel reports. | Additional standard | Delivery-system tests can signal nuclear ambition or increased risk even before confirmed warhead possession. |
| Has the country conducted nuclear explosive tests, subcritical tests, missile re-entry tests, or other experiments that advance weaponization? | **Appropriate sources:** CTBTO nuclear-test records and monitoring statements; Arms Control Association nuclear-testing timeline; FAS/SIPRI/NTI profiles; CNS/NTI missile-launch data for delivery experiments. | Additional standard | Experiments should be separated by type: actual nuclear tests are stronger evidence than delivery or component tests. |
| Is the country miniaturizing warheads, mating warheads to missiles, improving re-entry vehicles, or otherwise moving from latent capability to deployable weapons? | **Appropriate sources:** FAS Nuclear Notebook country articles; NTI country profiles; DIA Nuclear Challenges reports; CSIS Missile Threat; expert/manual evidence. | Additional standard | This bridges raw fissile capability and operational nuclear threat. |
| Has the leader made explicit nuclear threats or adopted high-risk nuclear doctrine? | **Appropriate sources:** official speeches/statements; UN records; credible news archives; FAS/SIPRI/NTI/DIA narrative assessments; constrained LLM/manual adjudication with citations. | Additional standard | Important for existential responsibility; not answered by arsenal count. |
| Does the country merely rank high because it has population/economy/military size? | **Context only:** population, GDP, conventional military metrics. | Exclude / low value for nuclear score | Useful context elsewhere, but not evidence of nuclear responsibility. |

---

## 2. International peace vs aggression and war

Current scorer groups: UCDP conflict involvement 65%, SIPRI military expenditure
35%.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Was the country involved in state-based armed conflict in the target/proxy year? | UCDP `ucdp_state_based_events`, `ucdp_state_based_fatalities` | Used now | Fatalities are required in the current plan; lower is better. |
| Was any conflict internationalized / cross-border? | UCDP `ucdp_intl_events`, `ucdp_intl_fatalities` | Used now | Captures external state involvement / international aggression better than domestic-only conflict. |
| How severe was the conflict in human cost? | UCDP fatalities | Used now | Fatalities are a severity signal; event counts are a frequency signal. |
| How frequent was conflict activity? | UCDP event counts | Used now | Helps distinguish one-off violence from sustained war. |
| How heavy is military spending relative to the economy? | SIPRI `sipri_milex_share_of_gdp` | Used now | Preferred military-burden indicator; lower generally better for peace burden. |
| How large is military spending in absolute terms and per capita? | SIPRI constant USD; SIPRI per capita | Used now | Scale / capability context. Absolute size should not alone imply aggression. |
| How much of the government budget is absorbed by the military? | SIPRI share of government spending | Used now | Opportunity-cost / prioritization signal. |
| Was the country the initiator/aggressor rather than a defender/victim? | COW MID initiator/revisionist fields; UCDP actor-role interpretation; manual review | Additional standard / future | Essential for moral ranking. COW MID is blocked/outdated; UCDP events need role interpretation before we can score this directly. |
| Did the country sponsor proxy warfare or armed non-state groups abroad through arms, training, financing, intelligence, sanctuary, logistics, or command support? | UCDP External Support Dataset / External Support in Non-State Conflict Dataset; Non-State Actor Dataset; Dangerous Companions / NAGs; SIPRI Arms Transfers; ATT Monitor; ACLED actor-event data; manual evidence | Additional standard / future | This is a chapter 2 peace/aggression question. It is only partly covered by UCDP internationalized conflict and is not captured by military spending alone. |
| Did the country instigate, prolong, or intensify conflicts while avoiding direct battlefield responsibility through proxies, deniable militias, partner forces, or arms flows? | UCDP external-support variables; SIPRI arms transfers to governments/non-state recipients; UN expert-panel reports; sanctions records; manual evidence | Additional standard / future | Captures cases such as state support to militant groups or partner forces in Yemen, Lebanon, Syria, Gaza, and similar proxy theaters. |
| Did the country provide arms or training despite credible evidence that recipients commit atrocities, attack civilians, destabilize neighboring states, or violate humanitarian law? | SIPRI Arms Transfers; ATT Monitor / national export reports; UN panels of experts; ICRC/IHL assessments; credible conflict reports | Additional standard / future | Bridges proxy support with civilian-harm responsibility. This should not be hidden inside the recipient country's domestic-violence score. |
| Did the leader participate in peace agreements, ceasefires, or de-escalation? | UCDP Peace Agreement Dataset / PA-X / manual evidence | Additional standard | Not currently in plan; needed to avoid penalizing a leader who ends inherited wars. |
| Does spending reflect defensive threat environment or alliance obligations? | SIPRI + regional threat context / NATO obligations | Additional standard | Avoid over-interpreting military burden as aggression. |

---

## 3. Domestic safety vs domestic violence, oppression, and incitement

Current scorer groups: CIRIGHTS physical integrity/repression 35%, PTS state
terror 30%, UCDP one-sided violence 20%, V-Dem civil-liberties/repression 15%.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Are people generally protected from state terror and physical-integrity abuse? | PTS Amnesty / HRW / State Department scores; CIRIGHTS `physint`; V-Dem `v2x_clphy` | Used now | Core domestic-safety anchor. PTS lower score = less terror; CIRIGHTS/V-Dem higher = more rights respect. |
| Are disappearances used by the state or state-aligned actors? | CIRIGHTS `cirights_disap` | Used now | Direct physical-integrity component. |
| Are extrajudicial killings / political killings present? | CIRIGHTS `cirights_kill`; V-Dem `v2clkill` | Used now | Direct lethal repression signal. |
| Are people imprisoned for political reasons? | CIRIGHTS `cirights_polpris`; PTS level descriptions | Used now | Distinguishes authoritarian coercion from general crime. |
| Is torture practiced or tolerated? | CIRIGHTS `cirights_tort`; PTS level descriptions | Used now | Direct physical-integrity component. |
| How broad, intense, and indiscriminate is political terror? | PTS 1-5 coding from Amnesty, HRW, State reports | Used now | PTS explicitly asks coders to consider scope, intensity, and range. |
| Is there one-sided violence against civilians? | UCDP `ucdp_onesided_events`, `ucdp_onesided_fatalities` | Used now | Event-based cross-check; lower is better. |
| Are political, private, and physical civil liberties protected? | V-Dem `v2x_clpol`, `v2x_clpriv`, `v2x_clphy` | Used now | Broader civil-liberties context beyond physical violence. |
| Is civil society repressed? | V-Dem `v2csreprss` | Used now | Lower repression is better; supports oppression/incitement diagnosis. |
| Is domestic hate incitement, state propaganda, or targeting of minorities present? | Potential V-Dem exclusion / media / civil society variables; human-rights reports | Additional standard | User mentioned incitement. Current plan has repression proxies but no dedicated incitement metric. |
| Is violence mostly non-state crime rather than political/state violence? | Homicide/crime data, UNODC, WHO | Additional standard | Domestic safety includes public safety, but current category is currently political violence/repression-heavy. |
| Are deaths from ordinary criminal homicide counted as domestic violence? | General homicide rates | Exclude / low value unless category is widened | Not in current scoring definition unless we explicitly broaden beyond state/political violence. |

---

## 4. Political freedom vs authoritarian rule

Current scorer groups: V-Dem democratic/liberal/civil-liberties 50%, BTI
political transformation 30%, RSF press freedom 20%. Vetted-but-not-active:
Polity V and Freedom House.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Are leaders chosen through free and meaningful elections? | V-Dem `v2x_polyarchy`; BTI democracy status / political participation; future Freedom House political rights | Used now / future | V-Dem electoral democracy index is required. |
| Are elections broad, competitive, and inclusive? | V-Dem suffrage `v2x_suffr`; V-Dem polyarchy components; BTI Q2 participation | Used now | Covers participation and inclusion. |
| Are civil liberties protected? | V-Dem `v2x_civlib`; V-Dem freedom of expression `v2x_freexp`; V-Dem freedom of association `v2x_frassoc_thick` | Used now | Direct civil-liberties questions. |
| Is there rule of law / judicial constraint? | V-Dem `v2x_rule`; BTI Q3 rule of law | Used now | User example: independent courts. |
| Are democratic institutions stable and accepted? | BTI Q4 democratic institutions | Used now | Captures institutional functioning beyond election day. |
| Is the state capable and legitimate enough to protect political order? | BTI Q1 stateness | Used now | Relevant to political transformation but not a pure liberty measure. |
| Are political/social cleavages integrated without excluding opposition? | BTI Q5 political/social integration | Used now | Helps identify polarized or exclusionary systems. |
| Is media/press free from political pressure? | RSF headline score; RSF political-context component; V-Dem media indicators if added | Used now | User example: independent media. RSF is only 20% because it is narrower than full political freedom. |
| Is political freedom high under a liberal-democratic model, not only electoral competition? | V-Dem `v2x_libdem` | Used now | Required current indicator; captures liberal checks beyond electoral democracy. |
| Is regime autocracy/democracy classification consistent across sources? | Polity V polity/autocracy/democracy; Freedom House status | Vetted, not active / user-managed | Add when adapters/raw data land. |
| Is press-freedom rank itself a scoring question? | RSF rank | Exclude / low value | Rank is relative/derived, not an independent measurement; current plan uses score/context instead. |

---

## 5. Economic well-being and prosperity

Current scorer groups: WDI per-capita prosperity 45%, BTI economic
transformation 30%, WDI scale/openness/investment 25%. Vetted-but-not-active:
PWT. IMF WEO is blocked unless user-managed.

Design note: GDP/GNI averages are not sufficient. This category should separate
**aggregate prosperity** from **inclusive prosperity** so that a high-GDP,
high-inequality country is not treated as equivalent to a high-GDP,
low-inequality country with broad access to basic economic security.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| How prosperous is the average resident in market-rate terms? | WDI `wdi_gdp_per_capita` | Used now | Required WDI anchor. |
| How prosperous is the average resident after PPP adjustment? | WDI `wdi_gdp_per_capita_ppp_constant_2017`; future PWT output-side/expenditure-side GDP per capita | Used now / future | Required WDI anchor; PWT would improve cross-validation. |
| What is national income per person? | WDI `wdi_gni_per_capita_atlas`; UNDP GNI in social score | Used now | Complements GDP per capita. |
| How large is the economy? | WDI current GDP; WDI constant GDP | Used now | Supports global influence/context, but should not dominate well-being. |
| Is prosperity broadly distributed rather than concentrated among elites? | WDI Gini; World Bank Poverty and Inequality Platform; income/wealth share data; Palma ratio / top 10% share where available | Additional standard | This should be an explicit economic question, not only a social-score afterthought. High averages with extreme inequality should be penalized. |
| What share of people live in poverty or near-poverty? | World Bank international poverty headcount; national poverty lines; poverty gap; multidimensional poverty where available | Additional standard | Poverty rates and poverty gaps prevent GDP per capita from masking deprivation. |
| Do ordinary households have enough disposable income / consumption to live securely? | Household final consumption per capita; median income/consumption where available; real wage data; cost-of-living-adjusted measures | Additional standard | Median/household measures are often better than means for lived economic prosperity. |
| Is access to basic economic services broad and reliable? | WDI access to electricity, clean cooking, water/sanitation, internet/mobile, financial account ownership; infrastructure-service indicators | Additional standard / social overlap | Basic services are economic foundations. Health/education outcomes remain chapter 6, but access to infrastructure and essential services belongs here too. |
| Is employment broad, productive, and dignified? | ILO unemployment, labor-force participation, vulnerable employment, informal employment, youth unemployment; WDI labor indicators | Additional standard | A country can have high GDP but weak job access or precarious livelihoods. |
| Is upward mobility possible, or are economic opportunities locked by class, region, gender, ethnicity, or political connections? | World Bank mobility/equality-of-opportunity data; V-Dem equality indicators; BTI socioeconomic barriers | Additional standard | Captures whether prosperity is reachable by non-elite citizens. |
| Is the economy open to trade? | WDI exports % GDP; WDI imports % GDP | Used now | Supporting signal, not a direct welfare guarantee. |
| Is the economy attracting external investment? | WDI FDI inflows current USD | Used now | Supporting confidence/prosperity signal; volatile. |
| What is the population base for scale interpretation? | WDI population | Used now | Context / denominator; not inherently good or bad. |
| Does the country have socioeconomic development and a functioning market economy? | BTI Q6 socioeconomic development; Q7 market competition; Q11 economic performance | Used now | Expert-coded cross-validation. |
| Are growth, inflation, unemployment, debt, and fiscal stability sound? | IMF WEO / WDI macro series / World Bank | Additional standard | Not currently in plan; important for competence/economic score. |
| Are benefits broadly shared rather than captured by elites? | Gini, poverty, inequality, social mobility, labor share of income, regional inequality | Additional standard | This should be a core economic-prosperity dimension, not only a chapter 6 social dimension. |
| Is BTI Q13 level of difficulty a positive economic score? | BTI Q13 | Exclude / low value | Current source plan intentionally excludes it because direction is inverted and it measures difficulty, not performance. |

---

## 6. Social well-being and prosperity

Current scorer groups: HDI anchor 40%, health 20%, education 15%, income 15%,
inequality/social protection 10%.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| What is the overall human-development level? | UNDP `undp_hdi_hdi` | Used now | Required social-wellbeing anchor. |
| Do people live long and healthy lives? | UNDP life expectancy; WHO GHO life expectancy; WDI life expectancy | Used now | HDI health dimension plus WHO/WDI cross-check. |
| Is child mortality low? | WHO under-5 mortality; WDI under-5 mortality | Used now | Lower is better; stronger health-system outcome than life expectancy alone. |
| Are children immunized? | WHO DTP3, HepB3, BCG immunization | Used now | Preventive-health / public-health delivery signal. |
| Are people educated? | UNDP expected years schooling; UNDP mean years schooling; WDI adult literacy; WDI secondary enrollment | Used now | HDI education dimension plus WDI cross-check. |
| Is standard of living adequate? | UNDP GNI per capita | Used now | Standard-of-living dimension in HDI. |
| Is inequality low enough that welfare is broadly shared? | WDI Gini; V-Dem egalitarian component `v2x_egal`; V-Dem social-group equality `v2clsocgrp_ord` | Used now | Lower Gini is better; V-Dem higher equality is better. |
| Are poverty, food security, housing, and social-protection floors adequate? | World Bank poverty, FAO, ILO, WDI social protection | Additional standard | Not yet in plan; useful future expansion. |
| Are health and education services accessible across gender/region/minority groups? | Disaggregated WDI/UNDP/WHO; V-Dem equality indicators | Additional standard | Current data is mostly national aggregate. |
| Is high income alone enough for social well-being? | GDP/GNI only | Exclude / low value if used alone | Income is only one component; HDI explicitly combines health, education, and living standards. |

---

## 7. Integrity and honesty

Current scorer groups: WGI Control of Corruption 35%, V-Dem corruption
composite 35%, Transparency International CPI 30%.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Is public power used for private gain? | WGI `wgi_control_of_corruption`; TI CPI score | Used now | WGI explicitly includes petty/grand corruption and state capture. CPI is perception-based. |
| Is political corruption systemic across the political system? | V-Dem `vdem_v2x_corr` | Used now | Required V-Dem corruption anchor; lower raw corruption is better after inversion. |
| Is executive corruption present? | V-Dem `vdem_v2x_execorr` | Used now | Captures leader/executive corruption more directly than broad CPI. |
| Is public-sector corruption present? | V-Dem `vdem_v2x_pubcorr`; TI CPI; WGI CC | Used now | Cross-validates administrative corruption. |
| Do multiple independent perception/expert sources agree? | CPI number of sources / standard error / confidence interval; WGI source aggregation | Used now as evidence/confidence context | CPI uncertainty fields should inform confidence, not the score alone. |
| Are procurement, campaign finance, asset disclosure, conflict of interest, and judicial accountability clean? | OECD/OGP/GRECO/World Justice Project or country reports | Additional standard | Important integrity dimensions, not in current structured plan. |
| Are corruption allegations legally proven for the leader personally? | Courts, sanctions lists, investigative reporting | Additional standard / manual review | Category is country-year evidence now; leader-specific integrity remains future/manual. |
| Is CPI rank itself an independent question? | CPI rank | Exclude / low value | Rank is derived and relative; current plan uses score, uncertainty, and source count. |

---

## 8. Effectiveness and competence

Current scorer groups: WGI governance 45%, V-Dem governance/accountability 35%,
BTI governance 20%.

Design correction: this category should not primarily ask whether the state has
good generic governance indicators. It should ask whether the ruler/government
can **translate its own stated priorities into observable implementation and
results**. The evaluation starts from the government's advertised agenda
(campaign platform, speeches, budget priorities, formal plans), then checks
effort, execution, and outcome movement over a realistic time window. A
government should not be penalized for failing to improve an objective it never
claimed to prioritize, except where the issue is a basic duty of government.

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| What explicit goals did the government/ruler advertise for this term or year? | Campaign platform, government program, budget speech, national development plan, state-of-the-nation speeches, coalition agreement, official policy documents | Additional standard / manual evidence | This is the starting point. Do not score only generic outcomes; first identify the government's own claimed priorities. |
| Were the advertised goals specific enough to evaluate, or vague slogans without measurable commitments? | Goal text; implementation plans; KPIs; budget/program documents | Additional standard | Clear, measurable goals should be easier to evaluate; vague slogans should not receive credit as serious commitments. |
| Did the government allocate real resources, authority, staff, legislation, and administrative attention to the stated goals? | Budget execution; legislation/regulation; ministerial appointments; procurement; program rollout; civil-service staffing | Additional standard | Separates intention/effort from empty announcement. |
| Did implementation milestones occur on time and at the promised scale? | Project/program delivery data; budget execution rates; audit reports; procurement records; agency performance reports | Additional standard | Effort matters before outcomes mature, but effort should leave observable implementation traces. |
| Did the relevant outcome indicators move in the promised direction after a reasonable lag? | Goal-specific indicators: crime rates for crime promises; GDP/jobs/inflation for economic promises; conflict involvement for peace promises; health/education metrics for social promises | Additional standard | Results should be evaluated against the target domain and realistic timing, not a single universal governance score. |
| Did outcomes improve relative to the inherited baseline and comparable countries facing similar external conditions? | Time-series deltas; peer-country comparison; shock controls; regional/global trend adjustments | Additional standard | Avoid crediting a ruler for inherited trends or punishing them for global shocks outside their control. |
| Did the government correct course when evidence showed that a promised policy was failing? | Policy revisions; replacement of failing appointees; audit follow-up; public performance reviews; independent evaluation | Additional standard | Competence includes learning and adaptation, not only first-plan success. |
| Did the government hide, manipulate, or redefine metrics to claim success without real improvement? | Statistical-agency independence; audit findings; data revisions; censorship/pressure on agencies; discrepancy between official claims and independent data | Additional standard | This connects effectiveness with integrity: false performance claims should lower effectiveness. |
| Did the government achieve stated goals without unacceptable side effects in other categories? | Cross-category evidence: repression, corruption, war, inequality, rights violations, fiscal unsustainability | Additional standard | A ruler should not receive full effectiveness credit for reducing crime through terror, growing GDP through elite capture, or avoiding unrest through repression. |
| Did crisis performance match pre-crisis promises and basic duties of government? | Disaster mortality, pandemic outcomes, emergency response timelines, conflict/security shock response, audit/inquiry findings | Additional standard | Some competence duties apply even if not advertised: protect life, maintain basic services, and respond honestly to emergencies. |
| Are general governance-capacity indicators consistent with the observed promise-to-result record? | WGI government effectiveness/rule of law/regulatory quality; BTI governance performance; V-Dem accountability/constraints | Used now as background | These are useful supporting signals, but they should not define the category by themselves. |
| Is authoritarian stability alone evidence that the government achieved its goals? | WGI political stability only | Exclude / low value if used alone | Stability without delivery, truthfulness, or accountability can mask repression and should not be treated as effectiveness. |

---

## Current source-plan weights summary

| Category | Scorer groups and weights | Minimum viable sources |
|---|---|---:|
| Nuclear | FAS 0.60; SIPRI Yearbook Ch.7 0.40 | 1 |
| International peace | UCDP conflict involvement 0.65; SIPRI military expenditure 0.35 | 2 |
| Domestic violence / repression | CIRIGHTS 0.35; PTS 0.30; UCDP one-sided violence 0.20; V-Dem repression/civil liberties 0.15 | 2 |
| Political freedom | V-Dem democracy/liberty 0.50; BTI political transformation 0.30; RSF press freedom 0.20 | 2 |
| Economic well-being | WDI per-capita prosperity 0.45; BTI economic transformation 0.30; WDI scale/openness/investment 0.25 | 1 |
| Social well-being | HDI 0.40; health 0.20; education 0.15; income 0.15; inequality 0.10 | 2 |
| Integrity | WGI control of corruption 0.35; V-Dem corruption 0.35; TI CPI 0.30 | 2 |
| Effectiveness | WGI governance 0.45; V-Dem governance/accountability 0.35; BTI governance 0.20 | 2 |

## Open follow-up questions for the scoring design

1. Decide whether `economic_wellbeing` should require two viable sources once
   the PWT adapter lands; it currently allows one source because WDI coverage is
   broad and PWT source hygiene is complete but the Stage 2 adapter is still
   pending.
2. Decide how to separate **country-level inherited conditions** from **leader
   responsibility / trajectory**. Many current indicators are country-year
   levels, not causal leader effects.
3. Add explicit incitement / hate-targeting questions if the domestic-safety
   category is meant to include rhetoric and propaganda, not only physical
   integrity and violence.
4. Add explicit international-aggression role attribution when COW/MID or a
   substitute conflict-role source becomes available.
5. Add nuclear treaty/doctrine/modernization indicators before treating the
   nuclear score as a full "global responsibility" score rather than a nuclear
   arsenal risk proxy.

---

## Ruler-quality evaluation categories: 1B-8B

The 1B-8B categories reframe the original country-year question bank into a
leader/ruler-quality question bank. The scoring target is not "what condition was
the country in?" but "what did the ruler intend, choose, tolerate, prevent,
improve, or worsen during the ruler-year?" These questions are deliberately
source-agnostic for now. They should be used to design the human/LLM rubric first;
source mapping can be added later.

General attribution rules for all 1B-8B questions:

- Judge the ruler's **intentions, decisions, incentives, actions, omissions, and
  tolerated practices**, not only aggregate national outcomes.
- Separate inherited baseline from ruler-caused change: ask what the ruler
  inherited, what they tried to change, what they resisted changing, and what
  happened under their control.
- Give more weight to choices inside the ruler's plausible authority: formal
  powers, informal dominance, party/military control, coalition constraints, and
  crisis constraints.
- Distinguish good intent with poor execution from bad intent, indifference, or
  deliberate harm.
- Penalize performative announcements when they are not followed by resources,
  appointments, implementation, monitoring, or correction.
- Treat systematic appointment of loyalists, family members, business partners,
  cronies, or "yes-men" over competent professionals as evidence about both
  integrity and effectiveness.

### 1B. Ruler responsibility for nuclear / global existential risk

| ID | Ruler-quality question |
|---|---|
| **1B.1** | Did the ruler seek to reduce nuclear or other existential risk, rather than increase prestige, leverage, or personal power through escalation? |
| **1B.2** | Did the ruler use nuclear rhetoric responsibly, avoiding reckless threats, brinkmanship, apocalyptic language, or normalization of nuclear use? |
| **1B.3** | Did the ruler strengthen command-and-control discipline, custody, safety, and accident-prevention safeguards? |
| **1B.4** | Did the ruler support arms-control, inspection, nonproliferation, disarmament, or de-escalation agreements in good faith? |
| **1B.5** | Did the ruler avoid using nuclear capability to shield conventional aggression, territorial coercion, or domestic repression? |
| **1B.6** | Did the ruler resist proliferation by allies, proxies, clients, or domestic factions when proliferation served short-term political interests? |
| **1B.7** | Did the ruler invest in risk-reducing expertise and institutions rather than surrounding nuclear/security decisions with loyalists or ideologues? |
| **1B.8** | In crisis moments, did the ruler de-escalate, communicate clearly, and preserve channels that reduce accidental war? |
| **1B.9** | Did the ruler handle dual-use technology, cyber, biological, AI, or other catastrophic-risk domains with precaution and transparency? |
| **1B.10** | Did the ruler leave the country's existential-risk posture safer or more dangerous than they inherited it? |

### 2B. Ruler responsibility for international peace vs aggression and war

| ID | Ruler-quality question |
|---|---|
| **2B.1** | Did the ruler choose diplomacy, compromise, and de-escalation when credible peaceful alternatives existed? |
| **2B.2** | Did the ruler initiate, expand, prolong, or justify wars of choice, cross-border coercion, annexation, or proxy conflict? |
| **2B.3** | Did the ruler distinguish defensive security needs from prestige, revenge, nationalism, diversionary politics, or regime-survival motives? |
| **2B.4** | Did the ruler respect civilian protection, humanitarian law, prisoner treatment, and proportionality in military operations? |
| **2B.5** | Did the ruler restrain security forces, militias, allies, proxies, and arms recipients from atrocities or destabilization? |
| **2B.6** | Did the ruler truthfully explain security threats to the public, or manipulate fear and misinformation to build support for conflict? |
| **2B.7** | Did the ruler pursue credible ceasefires, peace talks, confidence-building measures, or post-conflict reconciliation when possible? |
| **2B.8** | Did the ruler use military spending to meet real security needs, or to enrich networks, reward security elites, or project personal strength? |
| **2B.9** | Did the ruler accept accountability for military failures, civilian harm, and illegal conduct? |
| **2B.10** | Did the ruler leave regional/international relations more peaceful, stable, and lawful than they inherited them? |

### 3B. Ruler responsibility for domestic safety vs violence, oppression, and incitement

| ID | Ruler-quality question |
|---|---|
| **3B.1** | Did the ruler protect residents from state violence, torture, disappearances, political imprisonment, and extrajudicial killing? |
| **3B.2** | Did the ruler prevent, punish, or tolerate abuse by police, military, intelligence services, prisons, militias, party enforcers, or informal loyalists? |
| **3B.3** | Did the ruler personally incite hatred, revenge, dehumanization, scapegoating, or violence against opponents, minorities, migrants, journalists, or civil society? |
| **3B.4** | Did the ruler build systems for due process, complaint handling, civilian oversight, and independent investigation of abuse? |
| **3B.5** | Did the ruler use emergency powers, security laws, or anti-terror measures narrowly and lawfully, or as tools for intimidation and control? |
| **3B.6** | Did the ruler reduce domestic fear and insecurity without replacing criminal violence with state terror? |
| **3B.7** | Did the ruler protect women, children, minorities, and vulnerable groups from targeted violence and systematic neglect? |
| **3B.8** | Did the ruler allow peaceful protest, dissent, and community organization without retaliation? |
| **3B.9** | Did the ruler respond to domestic crises with protection and restraint rather than collective punishment, censorship, or militarized spectacle? |
| **3B.10** | Did the ruler leave citizens safer from both political violence and preventable domestic insecurity than they inherited them? |

### 4B. Ruler commitment to political freedom vs authoritarian rule

| ID | Ruler-quality question |
|---|---|
| **4B.1** | Did the ruler genuinely accept that power should be contestable through free, fair, and meaningful elections? |
| **4B.2** | Did the ruler refrain from manipulating electoral rules, courts, media, election commissions, security forces, or public resources to entrench themselves? |
| **4B.3** | Did the ruler tolerate opposition victories, criticism, satire, investigative journalism, protest, and civil-society monitoring? |
| **4B.4** | Did the ruler strengthen independent courts, legislatures, audit bodies, local governments, and oversight institutions even when they constrained the ruler? |
| **4B.5** | Did the ruler avoid personality cults, intimidation, arbitrary loyalty tests, party capture, or politicization of neutral state institutions? |
| **4B.6** | Did the ruler protect independent media and information access instead of spreading propaganda, disinformation, censorship, or pressure on owners/journalists? |
| **4B.7** | Did the ruler protect political equality for minorities, women, excluded groups, opposition regions, and unpopular viewpoints? |
| **4B.8** | Did the ruler respect term limits, succession rules, coalition commitments, and constitutional transfer of power? |
| **4B.9** | Did the ruler use surveillance, digital controls, internet shutdowns, or administrative harassment to limit political freedom? |
| **4B.10** | Did the ruler leave political freedom and democratic resilience stronger or weaker than they inherited it? |

### 5B. Ruler intention and action for economic well-being and prosperity

| ID | Ruler-quality question |
|---|---|
| **5B.1** | Did the ruler intend and act to create broad-based, sustainable prosperity rather than extract rents, buy loyalty, or maximize short-term popularity? |
| **5B.2** | Did the ruler appoint competent economic professionals and empower them, rather than loyalists, family members, business partners, or ideological yes-men? |
| **5B.3** | Did the ruler protect macroeconomic stability, fiscal responsibility, monetary credibility, and long-term investment conditions? |
| **5B.4** | Did the ruler create fair rules for entrepreneurship, competition, property rights, trade, investment, and job creation? |
| **5B.5** | Did the ruler resist corruption, favoritism, monopolies, oligarchic capture, and politically connected business privileges? |
| **5B.6** | Did the ruler invest in productivity foundations: infrastructure, education, health, technology, administrative capacity, and predictable regulation? |
| **5B.7** | Did the ruler make economic policy based on evidence and correction of mistakes, or on slogans, denial, patronage, and scapegoating? |
| **5B.8** | Did the ruler distribute economic gains fairly across regions, classes, genders, and groups rather than privileging regime supporters? |
| **5B.9** | Did the ruler manage shocks, inflation, unemployment, debt, sanctions, commodity changes, or crises with competence and honesty? |
| **5B.10** | Did the ruler leave the economy on a stronger trajectory than they inherited, accounting for external constraints? |

### 6B. Ruler intention and action for social well-being and human development

| ID | Ruler-quality question |
|---|---|
| **6B.1** | Did the ruler treat human welfare as a core purpose of rule rather than as propaganda, patronage, or secondary concern? |
| **6B.2** | Did the ruler improve access to basic health, education, water, sanitation, housing, food security, and social protection? |
| **6B.3** | Did the ruler prioritize vulnerable groups, poor regions, children, elderly people, women, minorities, disabled people, and marginalized communities? |
| **6B.4** | Did the ruler fund and manage social services with competent professionals rather than patronage networks? |
| **6B.5** | Did the ruler use evidence, measurement, and transparent correction to improve service delivery? |
| **6B.6** | Did the ruler reduce avoidable suffering during crises such as pandemics, disasters, conflict displacement, famine, or economic shocks? |
| **6B.7** | Did the ruler avoid using welfare, permits, jobs, food, housing, or benefits as tools of political loyalty and punishment? |
| **6B.8** | Did the ruler protect dignity and equal opportunity, not only aggregate welfare numbers? |
| **6B.9** | Did the ruler build durable social institutions that would survive beyond their personal rule? |
| **6B.10** | Did the ruler leave ordinary people with better life chances than they inherited, accounting for baseline and constraints? |

### 7B. Ruler personal integrity and honesty

| ID | Ruler-quality question |
|---|---|
| **7B.1** | Does the ruler habitually tell the truth to the public, legislature, courts, allies, and international partners? |
| **7B.2** | Does the ruler admit errors, correct false claims, and allow truthful reporting, or do they double down, blame others, and punish truth-tellers? |
| **7B.3** | Does the ruler separate personal/family/business interests from state decisions, public contracts, licensing, regulation, and foreign policy? |
| **7B.4** | Does the ruler or close family profit from office through assets, contracts, monopolies, gifts, bribes, emoluments, insider access, or opaque foundations? |
| **7B.5** | Does the ruler appoint competent professionals, or fill government with family, friends, cronies, donors, business associates, loyalists, and yes-men? |
| **7B.6** | Does the ruler tolerate independent investigation of their conduct, assets, campaign finance, conflicts of interest, and associates? |
| **7B.7** | Does the ruler use state power to protect themselves from accountability, punish investigators, or neutralize courts, prosecutors, auditors, and media? |
| **7B.8** | Does the ruler keep promises and respect formal commitments, or opportunistically reverse positions for personal advantage? |
| **7B.9** | Does the ruler avoid nepotism, favoritism, clientelism, and transactional politics in appointments, pardons, procurement, and enforcement? |
| **7B.10** | Does the ruler model ethical standards that improve public trust, or normalize lying, impunity, self-dealing, and cynicism? |

### 8B. Ruler effectiveness and competence

Design note: this category is **ideology-neutral**. It does not ask whether the
ruler's ideology, goals, or moral purposes were good. It asks whether the ruler
could define a direction, mobilize the state, coordinate people and institutions,
execute consistently, adapt tactically, and produce results aligned with the
ruler's own declared program. A ruler can be morally evil, repressive, or harmful
in other categories while still being highly competent/effective in this narrow
execution sense. Moral evaluation belongs mainly in the peace, domestic safety,
political freedom, social welfare, and integrity categories; 8B measures
execution capacity and goal-realization discipline.

| ID | Ruler-quality question |
|---|---|
| **8B.1** | Does the ruler articulate a clear governing ideology, strategic direction, or program that can be evaluated against later action? |
| **8B.2** | Does the ruler translate that program into concrete priorities, plans, budgets, appointments, timelines, institutions, and enforcement mechanisms? |
| **8B.3** | Does the ruler mobilize the state apparatus, party, military, bureaucracy, coalition, or ruling network effectively toward the chosen program? |
| **8B.4** | Does the ruler select and empower people who are capable of executing the program, whether professionals, loyal operators, technocrats, organizers, or coercive administrators? |
| **8B.5** | Does the ruler maintain internal discipline, coordination, and follow-through across ministries, regions, security forces, party structures, and implementing agencies? |
| **8B.6** | Does the ruler convert declarations into observable implementation rather than leaving goals as slogans, speeches, symbolic gestures, or propaganda only? |
| **8B.7** | Do outcome indicators move in the direction the ruler claimed to seek, after allowing for realistic lags and external constraints? |
| **8B.8** | When tactics fail, does the ruler adapt methods, replace ineffective implementers, reallocate resources, or otherwise correct course to keep advancing the program? |
| **8B.9** | Does the ruler manage crises and opposition in a way that preserves or advances the regime's chosen objectives, regardless of whether those objectives are morally good? |
| **8B.10** | By the end of the relevant period, is the ruler closer to achieving the stated ideological or policy program than at the start, accounting for inherited conditions and external shocks? |
