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
- Current source coverage and caveats live in `docs/sources/vetting/report.md` and
  `docs/sources/registry.md`.
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
leader/ruler-quality question bank. The scoring target is not "what static
condition was the country in?" but "what responsibility did the ruler bear for
the trajectory: what did they inherit, intend, choose, tolerate, prevent,
improve, or worsen during the ruler-year?" These questions are deliberately
source-agnostic for now. They should be used to design the human/LLM rubric first;
source mapping can be added later.

General attribution rules for all 1B-8B questions:

- Judge the ruler's **intentions, decisions, incentives, actions, omissions, and
  tolerated practices**, not only aggregate national outcomes or static country
  conditions.
- Separate inherited baseline from ruler-caused change: ask what the ruler
  inherited, what trajectory was already underway, what they tried to change,
  what they resisted changing, and what worsened or improved because of their
  choices.
- Give more weight to choices inside the ruler's plausible authority or control:
  formal powers, informal dominance, party/military control, coalition
  constraints, time in office, implementation capacity, external shocks, and
  international/security constraints.
- Distinguish good intent with poor execution from bad intent, indifference, or
  deliberate harm.
- Penalize performative announcements when they are not followed by resources,
  appointments, implementation, monitoring, or correction.
- Treat systematic appointment of loyalists, family members, business partners,
  cronies, or "yes-men" over competent professionals as evidence about both
  integrity and effectiveness.
- Do not treat low counts of visible punishments, arrests, or violent events as
  automatically low repression when credible evidence shows pervasive fear,
  surveillance, arbitrary enforcement, selective exemplary punishment, or a
  chilling effect that prevents opposition from surfacing.

### 1B. Ruler responsibility for nuclear / global existential risk

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **1B.1 — Nuclear investment and capability trajectory** | Did nuclear investment and capability increase or decrease during the ruler’s tenure? | Compare the inherited position and prior trend with changes in spending, research, facilities, fissile-material production, arsenal size, delivery systems, destructive capability, modernization, testing, deployment, and readiness; identify what the ruler caused, continued, or could not reasonably reverse. Any increase in weapons capability is adverse unless modernization has the sole and undisputed motivation of improved safety. | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **1B.2 — Nuclear rhetoric, doctrine, and normalization** | Did the ruler’s words and doctrine reduce or increase the perceived legitimacy and likelihood of nuclear acquisition, threat, or use? | Examine threats, acquisition advocacy, first-use and retaliation doctrine, reassurance or de-escalation, and whether actions and operational posture matched the rhetoric. Include influential non-nuclear rulers where their conduct materially affected nuclear norms. | **Rhetoric and representations**; **Formal acts and law**; **Implementation and operational conduct** |
| **1B.3 — Safe nuclear control** | Did the ruler keep nuclear weapons and decisions safe and controlled? | Did the ruler enact, fund, staff, implement, and enforce effective command-and-control, custody, safety, inspection, and accident-prevention safeguards, and correct identified failures? | **Resources**; **Personnel**; **Implementation and operational conduct** |
| **1B.4 — Arms control, inspections, and international leadership** | Did the ruler preserve, strengthen, comply with, or weaken systems intended to reduce nuclear danger? | Examine treaties, inspections, disarmament, test restrictions, negotiations, confidence-building measures, sanctions enforcement, and international leadership, including by non-nuclear countries. | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **1B.5 — Nuclear cover for aggression** | Did the ruler avoid using nuclear power to protect aggression or repression? | Did the ruler avoid formally or operationally using nuclear capability to authorize, shield, or intensify conventional aggression, territorial coercion, or domestic repression? | **Formal acts and law**; **Rhetoric and representations**; **Implementation and operational conduct** |
| **1B.6 — Preventing proliferation** | Did the ruler stop allies, clients, and domestic actors from spreading nuclear weapons? | Did the ruler establish and enforce proliferation controls against allies, proxies, clients, firms, and domestic factions, and respond when monitoring exposed evasion or assistance? | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **1B.7 — Independent risk expertise** | Did the ruler empower qualified experts who could warn about catastrophic risks? | Did the ruler appoint qualified, independent experts, protect their access and dissent, and resource risk-reducing institutions rather than replace expertise with loyalty or ideology? | **Personnel**; **Resources**; **Implementation and operational conduct** |
| **1B.8 — Crisis de-escalation** | During crises, did the ruler act to prevent catastrophic escalation? | In crises, did the ruler issue and implement de-escalatory decisions, preserve communication and decision safeguards, and correct procedures exposed as dangerous? | **Implementation and operational conduct**; **Rhetoric and representations**; **Formal acts and law** |
| **1B.9 — Other existential weapons and technologies** | Did the ruler responsibly control biological, chemical, environmental, and emerging technological risks capable of catastrophic cross-border or global harm? | Include only matters with a credible catastrophic or existential dimension, such as biological or chemical weapons and catastrophic environmental, AI, cyber, or space risks—not ordinary technological, environmental, military, or public-health policy. | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **1B.10 — Lasting risk posture** | Did the ruler leave the country and the wider world safer or more endangered than before? | Synthesize the inherited baseline and previous trend, measurable changes, ruler attribution, crises avoided or aggravated, external pressures, unresolved dangers, and durability. | **Outcomes**; **Implementation and operational conduct** |

### 2B. Ruler responsibility for international peace vs aggression and war

Preliminary focus: establish the ruler’s authority and security context; inherited
wars, deployments, and support; a complete inventory of material overseas force;
scale and consequences; and ruler attribution based on independent evidence. Record
conduct before judging justification. Ruler explanations are claims and receive no
presumption of credibility.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **2B.1 — Peaceful alternatives** | Did the ruler seriously try peaceful options before using force? | When credible peaceful alternatives existed, did the ruler use formal decisions, diplomatic authority, and available legislative or cabinet processes to pursue them before authorizing or supporting force? | **Formal acts and law**; **Implementation and operational conduct** |
| **2B.2 — Actual overseas force, war, and escalation** | Did the ruler initiate, order, authorize, support, knowingly allow, expand, or prolong material military or violent action abroad, and what were its scale and consequences? | First record every material action without excluding conduct described as defensive, lawful, necessary, retaliatory, or humanitarian. Include force outside the state’s broadly internationally recognized territory, destructive cyber operations causing physical harm or material escalation, and material enabling support. Identify the ruler’s role, direct and supported actors, scale, casualties, displacement, destruction, territorial effects, escalation, and whether the ruler inherited, expanded, reduced, or ended the action. ‘Knowingly allowed’ requires knowledge, practical authority or leverage, and failure to take reasonable corrective action. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **2B.3 — Honest justification for force** | Was the ruler’s stated justification for force supported by independent evidence? | Treat the ruler’s explanation only as a claim or evidence of intent. Assess contemporaneous evidence, actual conduct, independent findings, peaceful alternatives, legality, necessity, proportionality, and consequences from outside in, with no presumption that claims of defense, necessity, retaliation, humanitarian purpose, or national interest are true. | **Rhetoric and representations**; **Formal acts and law** |
| **2B.4 — Civilian and prisoner protection** | Did the ruler protect civilians and prisoners during conflict? | Did the ruler adopt, resource, and enforce lawful rules of engagement, civilian protection, and prisoner safeguards, investigate violations, and provide discipline or remedy? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **2B.5 — Control of proxies, arms, and enabling support** | Did the ruler prevent supported forces and arms recipients from causing abuse? | Did the ruler establish and enforce controls over arms, intelligence, targeting, financing, logistics, bases, proxies, and allied forces; monitor foreseeable abuse; and suspend support or correct policy when harm emerged? Enabling support ordinarily receives less weight than direct action, but more where it was indispensable, large, knowing, controlled, or readily stoppable. | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **2B.6 — Scrutiny of war claims** | Did the ruler allow independent checks of claims made about conflict? | Did the ruler permit legislative, judicial, media, and independent scrutiny of conflict claims and correct false or misleading official accounts? | **Formal acts and law**; **Implementation and operational conduct**; **Rhetoric and representations** |
| **2B.7 — Ceasefires and settlements** | Did the ruler seriously pursue and uphold peace agreements? | Did the ruler negotiate, approve, implement, and comply with credible ceasefires, peace agreements, confidence-building measures, and lawful settlements, and help make them durable? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **2B.8 — Responsible military resources** | Were military resources used for real security rather than power, profit, or intimidation? | Did military budgets, mobilization, and procurement address genuine security needs transparently and proportionately rather than enrich networks, entrench security elites, or intimidate neighbors? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **2B.9 — Accountability and remedy** | Did the ruler accept responsibility and remedy unlawful harm from conflict? | Did the ruler cooperate with courts, inquiries, audits, and casualty disclosure; accept responsibility; correct unlawful policy; discipline responsible actors; and provide meaningful remedy? | **Implementation and operational conduct**; **Rhetoric and representations**; **Outcomes** |
| **2B.10 — Lasting international peace** | Did the ruler leave international relations more peaceful and lawful? | Did the ruler leave relations more peaceful, stable, and lawful through durable institutions and settlements, accounting for inherited conflicts, actual authority, and external constraints? | **Outcomes**; **Formal acts and law**; **Implementation and operational conduct** |

### 3B. Ruler responsibility for domestic safety vs violence, oppression, and incitement

Preliminary focus: establish the trend in state violence and political imprisonment;
intimidation and retaliation; intergroup violence; serious private and organized
violence; and the ruler’s authority, decisions, and response, using independent
evidence where available. Record a material rise in crime with governmental inaction
while distinguishing incapacity, ineffective action, neglect, tolerance, and collusion.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **3B.1 — Actual state violence and political imprisonment** | Did state violence, torture, disappearance, political imprisonment, killing, or other severe punishment increase or decrease during the ruler’s tenure? | Record the conduct regardless of whether domestic law authorized it. Examine frequency, severity, targeted populations, major episodes, change from the inherited position, the ruler’s responsibility, and whether verified abuse was prevented, corrected, and remedied. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **3B.2 — Control of coercive forces** | Did the ruler prevent and punish abuse by security forces and aligned groups? | Did the ruler appoint, resource, direct, and discipline police, military, intelligence, prison, militia, party, and aligned private actors—including during domestic crises—to prevent abuse rather than tolerate or reward it? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **3B.3 — Incitement, persecution, and targeted hatred** | Did the ruler’s rhetoric, policies, or tolerance contribute to persecution or violence against opponents or identifiable groups? | Did the ruler avoid personally or officially inciting hatred, revenge, dehumanization, scapegoating, or violence against opponents, minorities, migrants, journalists, civil society, or other groups, and act when supporters or officials translated such messages into harm? | **Rhetoric and representations**; **Implementation and operational conduct**; **Outcomes** |
| **3B.4 — Complaints and independent oversight** | Could abuse be reported, investigated, corrected, and remedied independently? | Did the ruler create, fund, and respect independent courts, complaint systems, civilian oversight, and investigations, comply with findings, and provide victim remedy? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **3B.5 — Emergency powers, surveillance, and coercive administration** | Did the ruler use emergency, surveillance, security, administrative, or legal powers to protect people or to intimidate, punish, collectively control, or silence them? | Examine enactment, renewal, administration, review, repeal, actual effects, and whether powers were used for protection or for intimidation, collective punishment, retaliation, or control. Domestic legality does not turn oppressive conduct into acceptable conduct. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **3B.6 — Intimidation and climate of fear** | Did people face a credible climate of fear or intimidation even when visible violence was infrequent? | Examine threats, systematic surveillance, exemplary punishment, arbitrary detention, employment or licensing retaliation, withdrawal of benefits, selective taxation, pressure on families, and official or unofficial harassment. Severe exemplary punishment may sustain control with little recurring visible violence. | **Implementation and operational conduct**; **Outcomes** |
| **3B.7 — Intergroup violence and protection of targeted groups** | Did serious violence between domestic groups increase or decrease, and did the ruler prevent, encourage, tolerate, or punish it? | Include ethnic, religious, political, regional, caste, and socioeconomic violence, as well as violence against vulnerable groups; examine prevention, protection, displacement, enforcement, punishment, and equitable access across regions and populations. | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **3B.8 — Safe protest and dissent** | Could people protest, dissent, organize, and oppose the ruler without violence, detention, disappearance, intimidation, or other serious retaliation? | Did laws, permit systems, policing orders, and actual enforcement protect peaceful protest, dissent, organization, and opposition, with accountability and remedy for retaliation or excessive force? Domestic legality does not determine whether retaliation was coercive or abusive. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **3B.9 — Serious private and organized violence** | Did the ruler make ordinary life safer from serious private, criminal, and organized violence? | Record material trends in homicide, kidnapping, severe sexual violence, extortion, organized crime, and gang or cartel control, together with territorial control and effective protection. A material increase with governmental inaction must be noted, while distinguishing lack of capacity, ineffective action, neglect, deliberate tolerance, and collusion. | **Resources**; **Implementation and operational conduct**; **Rhetoric and representations** |
| **3B.10 — Lasting domestic safety** | Did the ruler leave people durably safer from state violence, intimidation, intergroup violence, and serious private or organized violence than before? | Synthesize the inherited position and trends in state violence, intimidation, intergroup violence, and serious private or organized violence, accounting for reporting freedom, population exposure, authority, government action or inaction, and external shocks. | **Outcomes**; **Implementation and operational conduct** |

### 4B. Ruler commitment to political freedom vs authoritarian rule

Preliminary focus: establish the inherited level and prior direction of political
freedom; material changes in voting, expression, media, assembly, association,
opposition, and political equality; the principal laws, actions, and incidents;
beginning-and-end comparative assessments where available; and ruler attribution.
Comparative datasets guide research but do not determine the judgment. A significant
decline remains adverse even when formally legal or presented as an emergency.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **4B.1 — Genuine electoral choice** | Did genuine electoral choice and the ability to vote freely increase or decrease during the ruler’s tenure? | Examine changes in voter eligibility, registration, intimidation, competition, electoral administration, and acceptance of verified results, together with the ruler’s relevant laws, resources, and conduct. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.2 — No entrenchment of power** | Did the ruler avoid changing or abusing institutions to stay in power? | Did the ruler refrain from proposing, signing, decreeing, manipulating, or obstructing laws, courts, election administration, security forces, media, or public resources to entrench personal or party power? | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **4B.3 — Opposition and civic freedom** | Did people’s freedom to criticize, assemble, protest, associate, and organize political opposition increase or decrease during the ruler’s tenure? | Examine changes in law and practice affecting opposition, criticism, satire, protest, assembly, association, and civil-society monitoring, and whether violations were corrected and remedied. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.4 — Independent checks on power** | Did courts, legislatures, auditors, and other institutions remain able to constrain the ruler? | Did the ruler protect the jurisdiction, appointment independence, tenure, funding, and decisions of courts, legislatures, election bodies, auditors, and local governments even when they constrained the ruler? | **Formal acts and law**; **Personnel**; **Implementation and operational conduct** |
| **4B.5 — Politically neutral institutions** | Did the ruler avoid filling neutral institutions with loyalists and political pressure? | Did appointments, dismissals, civil-service rules, and administrative practice preserve politically neutral institutions rather than impose loyalty tests, party capture, intimidation, or a personality cult? | **Personnel**; **Formal acts and law**; **Implementation and operational conduct** |
| **4B.6 — Independent information and media** | Did freedom of expression, independent media, and access to uncensored information increase or decrease during the ruler’s tenure? | Examine changes in media, information-access, ownership, and licensing rules and in actual censorship, propaganda, disinformation, pressure, and access to independent information. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.7 — Equal political rights** | Did all groups have equal political rights and access? | Did the ruler enact and enforce equal political rights and access for minorities, women, excluded groups, opposition regions, and unpopular viewpoints? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.8 — Term limits and transfer** | Did the ruler respect succession rules and peaceful transfer of power? | Did the ruler preserve and comply with term limits, succession rules, coalition commitments, and constitutional transfer rather than amend, evade, or obstruct them for continued power? Formal legality, public debate, or claims of emergency, stability, or national necessity create no presumption of legitimacy; assess the practical effect on succession, competition, institutional independence, coercion, and state resources. | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.9 — Digital freedom and surveillance** | Did the ruler avoid using surveillance and digital controls to suppress politics? | Did the ruler narrowly authorize, transparently procure, and lawfully oversee surveillance and digital controls, or use law, shutdowns, and administrative harassment to suppress political freedom? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **4B.10 — Lasting democratic resilience** | Did the ruler leave political freedom and democracy durably stronger or weaker, both overall and in the specific political freedoms examined above? | Assess durable change from the inherited position through enacted, implemented, and independently reviewable institutions, including voting, expression, media, assembly, association, opposition, and political equality, while accounting for correction and constraints. | **Outcomes**; **Formal acts and law**; **Implementation and operational conduct** |

### 5B. Ruler intention and action for economic well-being and prosperity

Preliminary focus: establish the inherited economy and prior trend; beginning-and-end
changes in GDP, GDP per capita, income, employment, inflation, debt, and distribution
where comparable; the principal economic decisions; major external shocks; and the
ruler’s attributable contribution.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **5B.1 — Broad and sustainable prosperity** | Did the ruler pursue lasting prosperity for the public rather than private gain and political loyalty? | Did the ruler's legislative agenda, formal policies, and executed budgets pursue broad-based sustainable prosperity rather than rents, loyalty purchases, or short-term popularity? | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **5B.2 — Qualified economic leadership** | Did the ruler empower capable economic professionals rather than loyalists? | Did the ruler appoint qualified economic professionals through credible processes, empower their operational independence, and retain or replace them based on performance rather than loyalty? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **5B.3 — Macroeconomic stability** | Did the ruler protect stable public finances, money, debt, and investment conditions? | Did the ruler enact, administer, and comply with credible fiscal, tax, debt, monetary, and financial rules that protected macroeconomic stability and long-term investment? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **5B.4 — Fair economic rules** | Did businesses and workers operate under fair and predictable economic rules? | Did the ruler create and consistently enforce fair laws and regulations for competition, entrepreneurship, property, trade, investment, and job creation? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **5B.5 — Resistance to economic capture** | Did the ruler resist favoritism, monopoly power, and politically connected privilege? | Did the ruler enforce competition, procurement, disclosure, and anti-corruption rules against politically connected actors, cooperate with audits and courts, and remedy proven favoritism or capture? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **5B.6 — Productive public investment** | Did public resources produce useful foundations for long-term prosperity? | Did enacted and executed budgets produce timely, high-quality infrastructure, education, health, technology, administrative capacity, and predictable regulation rather than announcements or patronage projects? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **5B.7 — Evidence and correction** | Did the ruler use honest evidence and correct economic policies that failed? | Did the ruler publish reliable economic information, permit independent evaluation and audit, and correct laws, programs, or implementers when evidence showed failure rather than rely on slogans, denial, patronage, or scapegoating? | **Rhetoric and representations**; **Implementation and operational conduct**; **Outcomes** |
| **5B.8 — Fair distribution** | Were economic gains and burdens shared fairly across people and regions? | Did tax, labor, wage, benefit, investment, and regional policies distribute gains and burdens fairly in actual incidence across classes, regions, genders, and groups? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **5B.9 — Managing economic shocks** | Did the ruler respond competently and fairly to major economic shocks? | During inflation, unemployment, debt, sanctions, commodity, or other shocks, did the ruler use timely, funded, and transparently targeted measures, monitor their effects, and correct mistakes? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **5B.10 — Lasting economic trajectory** | Did the ruler leave the economy on a stronger and fairer path? | Compare beginning-and-end and time-series changes in GDP, GDP per capita, income, employment, inflation, debt, productivity, and distribution such as the Gini coefficient where comparable. Attribute changes cautiously, accounting for inherited trends, implementation lags, external conditions, institutional constraints, and distribution rather than GDP alone. | **Outcomes**; **Implementation and operational conduct** |

### 6B. Ruler intention and action for social well-being and human development

Preliminary focus: establish the inherited level and prior trend in essential services
and life chances; the ruler’s principal social policies and executed resources;
material changes across affected groups and regions; major crises and external support;
and the ruler’s attributable contribution.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **6B.1 — Welfare as a governing purpose** | Did the ruler make people's wellbeing a real priority? | Did the ruler enact and fund enforceable social commitments that made human welfare a core purpose of government rather than propaganda, patronage, or a secondary concern? | **Formal acts and law**; **Resources**; **Implementation and operational conduct** |
| **6B.2 — Access to essential services** | Did people gain effective access to essential services and social protection? | Did laws, eligibility rules, executed budgets, and service administration improve affordable, effective access and uptake across health, education, water, sanitation, housing, food security, and social protection? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **6B.3 — Priority for vulnerable groups** | Did vulnerable people and poor regions receive real protection and support? | Did the ruler enact, target, fund, and enforce protection for poor regions, children, older people, women, minorities, disabled people, and marginalized groups, with evidence of actual incidence and exclusion? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **6B.4 — Professional service delivery** | Were social services run by capable people with adequate resources? | Did the ruler appoint and retain qualified administrators, provide adequate staffing and resources, and use transparent procurement to deliver social services rather than patronage? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **6B.5 — Measurement and correction** | Did the ruler measure social programs honestly and fix what did not work? | Did the ruler publish credible welfare and service data, permit audit and independent evaluation, and correct program design, implementation, or personnel when evidence showed failure? | **Rhetoric and representations**; **Implementation and operational conduct**; **Outcomes** |
| **6B.6 — Protection during crises** | Did the ruler reduce avoidable suffering during major crises? | Did preparedness laws, emergency decisions, funding, and implementation reduce avoidable and unequally distributed suffering during pandemics, disasters, displacement, famine, or economic shocks? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **6B.7 — No political allocation of welfare** | Were benefits and basic needs protected from political favoritism and punishment? | Did formal eligibility rules, administrative practice, and appeal systems prevent welfare, permits, jobs, food, and housing from becoming instruments of political loyalty or punishment? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **6B.8 — Dignity and equal opportunity** | Did the ruler protect equal dignity and opportunity in everyday life? | Did the ruler enact and enforce equal-rights, anti-discrimination, accessibility, and dignity protections, with practical remedy rather than relying on national averages alone? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **6B.9 — Durable social institutions** | Did the ruler build social institutions that could last beyond personal rule? | Did the ruler create durable social institutions with statutory authority, reliable funding, professional staffing, transparent standards, and resilience beyond personal rule? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **6B.10 — Lasting life chances** | Did ordinary people finish the period with better life chances? | Did ordinary people, including disadvantaged groups, finish the period with durably better life chances than inherited, accounting for policy lag, baseline, donor or subnational roles, and external shocks? | **Outcomes**; **Implementation and operational conduct** |

### 7B. Ruler personal integrity and honesty

Preliminary focus: identify the most significant documented falsehoods, manipulation,
or concealment; material personal, family, or business interests connected to office;
major uses of public power benefiting close associates, the party, supporters, or
favored groups; use of office to entrench power; and credible independent findings and
the ruler’s response. Formal legality or claims of necessity do not determine
legitimacy.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **7B.1 — Truthfulness and misleading communication** | Did the ruler tell the truth when lying could protect their power or reputation? | Examine explicit falsehoods, deliberate material omissions, fabricated or distorted evidence, selective presentation of data, coordinated misinformation, and attempts to manipulate public understanding or sentiment through knowingly false or seriously misleading claims, especially when deception would protect power, benefit, or reputation. | **Rhetoric and representations**; **Formal acts and law** |
| **7B.2 — Correcting falsehoods and errors** | Did the ruler admit and correct false claims and mistakes? | When reliable records, courts, audits, or investigations expose error or falsehood, does the ruler correct the record, comply, and remedy harm rather than retaliate, conceal, or knowingly repeat the claim? | **Rhetoric and representations**; **Implementation and operational conduct**; **Outcomes** |
| **7B.3 — Conflicts of interest** | Did the ruler keep personal and family interests separate from public decisions? | Does the ruler support and personally comply with conflict-of-interest, disclosure, recusal, divestment, and ethics rules separating personal, family, and business interests from state decisions? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **7B.4 — Personal profit from office** | Did the ruler or close family improperly profit from public office? | Do asset, tax, gift, ownership, contract, foundation, emolument, bribe, insider-access, and legal records show that the ruler or close family profited from office, and did the ruler permit final findings, recovery, and accountability? | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **7B.5 — Nepotism and loyalist appointments** | Did the ruler choose officials for competence rather than personal loyalty or connections? | Do the ruler's appointments and removals reflect competence and lawful process, or family, friendship, donations, business ties, and loyalty used to protect or entrench personal or political power? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **7B.6 — Independent investigation** | Could independent institutions investigate the ruler and close associates? | Did the ruler preserve the law, jurisdiction, appointments, funding, and access needed for independent investigation of their conduct, assets, campaigns, associates, and concealed decisions? | **Formal acts and law**; **Personnel**; **Implementation and operational conduct** |
| **7B.7 — Transparency, concealment, and obstruction** | Did the ruler make material public decisions and information reasonably transparent rather than conceal, distort, or obstruct scrutiny? | Did the ruler disclose material information about public decisions, government performance, public resources, conflicts of interest, and significant risks, and comply with subpoenas, judgments, audits, disclosure duties, and legitimate investigations? Genuine security, diplomatic, investigative, or personal confidentiality may justify proportionate secrecy, but the ruler’s assertion of emergency, public order, national security, or national interest is not sufficient. | **Formal acts and law**; **Implementation and operational conduct**; **Rhetoric and representations** |
| **7B.8 — Promises and good faith** | Did the ruler keep commitments and explain changes honestly? | Do the ruler's documented legislative positions, formal commitments, and implemented decisions show consistent good-faith promises, or opportunistic reversal and concealed tradeoffs for personal advantage? | **Rhetoric and representations**; **Formal acts and law**; **Implementation and operational conduct** |
| **7B.9 — Favoritism and clientelism** | Did the ruler avoid using public power to reward favored people and networks or to entrench personal or political power? | Did the ruler personally direct, benefit from, knowingly tolerate, or correct favoritism and clientelism in appointments, procurement, licensing, pardons, enforcement, public resources, and privileged access that advantaged family, friends, business associates, the ruling party, supporters, or favored socioeconomic, ethnic, or religious groups? A policy is not adverse merely because it benefits a group; look for improper preference, discrimination, reciprocal political support, personal benefit, or entrenchment. | **Resources**; **Implementation and operational conduct**; **Outcomes** |
| **7B.10 — Ethical example and public trust** | Did the ruler's conduct strengthen ethical standards and public trust? | Did the ruler's personal conduct and support for durable integrity institutions strengthen public trust, or normalize lying, impunity, personal or family profit from office, conflicts of interest, favoritism, patronage, use of public resources for personal or political advantage, and cynicism? | **Rhetoric and representations**; **Implementation and operational conduct**; **Outcomes** |

Low transparency alone is not automatically dishonesty, especially under genuine
security, privacy, or diplomatic constraints. It becomes evidence for 7B when it
supports intentional deception, concealment of illegal/destructive/self-serving
activity, manipulation of public information, punishment of truth-tellers, or
avoidance of accountability.

### 8B. Ruler effectiveness and competence

Preliminary focus: identify only the three to five principal officially declared
governing goals; the inherited position, authority, and main obstacles; the principal
actions, resources, and implementers; observable progress and failure; and the
durability of results. Remaining in power is excluded as a governing achievement.

Design note: this category is **ideology-neutral**. It does not ask whether the
ruler's ideology, goals, or moral purposes were good. It asks whether the ruler
could define a direction, mobilize the state, coordinate people and institutions,
execute consistently, adapt tactically, and produce results aligned with the
ruler's own declared or revealed program. A ruler can be morally evil,
repressive, or harmful in other categories while still being highly
competent/effective in this narrow execution sense. Moral evaluation belongs
mainly in the peace, domestic safety, political freedom, social welfare, and
integrity categories; 8B measures execution capacity, power consolidation, state
reach, durability, influence, and goal-realization discipline.

| Lens | Simple question | Detailed research question | Priority evidence |
|---|---|---|---|
| **8B.1 — Clear governing program** | Were the ruler’s principal officially declared governing goals sufficiently clear to evaluate? | Identify only the three to five most important officially declared governing goals in dated speeches, manifestos, strategies, directives, or formal acts. Do not infer hidden personal goals and then credit the ruler for achieving them. | **Rhetoric and representations**; **Formal acts and law** |
| **8B.2 — Turning goals into machinery** | Did the ruler turn goals into concrete plans, rules, resources, people, and institutions? | Did the ruler translate that program into enacted laws, budgets, appointments, timelines, institutions, regulations, and enforcement mechanisms within actual authority? | **Formal acts and law**; **Personnel**; **Implementation and operational conduct** |
| **8B.3 — Mobilizing the ruling system** | Did the ruler effectively mobilize the state and ruling network toward those goals? | Did executed resources and administrative records show effective mobilization of the state, party, military, coalition, or ruling network toward the ruler's chosen program? | **Resources**; **Personnel**; **Implementation and operational conduct** |
| **8B.4 — Capable implementers** | Did the ruler choose and manage people capable of carrying out the program? | Did the ruler appoint, empower, retain, and when necessary replace people capable of executing the program, whether professionals, technocrats, organizers, loyal operators, or coercive administrators? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **8B.5 — Coordination and control** | Did the ruler maintain coordination and follow-through across the system? | Did the ruler maintain documented coordination, territorial reach, milestone completion, and compliance across ministries, regions, institutions, security forces, and implementing agencies? | **Implementation and operational conduct**; **Outcomes** |
| **8B.6 — From plans to practice** | Did the ruler turn plans and announcements into real government action? | Did legislation, budgets, and directives become observable enforcement, services, projects, and institutional practice rather than remain slogans, plans, or symbolic acts? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **8B.7 — Progress toward declared goals** | Did the ruler produce meaningful progress toward the principal officially declared governing goals? | Did outcome and distribution indicators move toward the principal officially declared governing goals after accounting for baseline, realistic lag, authority, external shocks, and plausible causal alternatives? | **Outcomes**; **Implementation and operational conduct** |
| **8B.8 — Learning and correction** | Did the ruler adapt and correct course when methods failed? | Did audits, evaluations, and implementation failures lead the ruler to adapt methods, replace implementers, reallocate resources, and correct course? | **Personnel**; **Implementation and operational conduct**; **Outcomes** |
| **8B.9 — Managing crises and resistance** | Did the ruler handle crises and resistance without losing the declared governing program? | Did formal decisions and implemented responses to crises, opposition, international relations, and institutional resistance preserve or advance the declared governing objectives and durable implementation? | **Formal acts and law**; **Implementation and operational conduct**; **Outcomes** |
| **8B.10 — Durable goal achievement** | By the end of the ruler’s tenure, had the principal officially declared governing goals been substantially and durably achieved? | Assess whether the principal officially declared governing goals became durable law, institutions, capacity, state practice, and achieved outcomes, accounting for failures and long-term fragility. Remaining in power does not count as achievement of a governing goal. | **Outcomes**; **Formal acts and law**; **Implementation and operational conduct** |
