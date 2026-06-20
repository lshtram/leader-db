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
- Current source coverage and caveats live in `docs/source-vetting-report.md` and
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
| Does the country possess nuclear warheads at all? | FAS `fas_total_inventory`; SIPRI `sipri_yearbook_ch7_nuclear_warheads_total_inventory` | Used now | Required anchor. Non-nuclear countries should not receive invented numeric evidence. |
| How large is the total nuclear arsenal? | FAS total inventory; SIPRI total inventory | Used now | Lower is better. Measures capability/risk, not intent. |
| How many warheads are deployed or operationally available? | FAS operational strategic / nonstrategic; SIPRI deployed warheads | Used now | Stronger risk signal than inactive total inventory. |
| How large is the military stockpile versus reserve/nondeployed arsenal? | FAS military stockpile; FAS reserve/nondeployed | Used now | Helps separate active military capability from inactive/retired holdings. |
| Is there evidence of disarmament activity? | SIPRI retired warheads | Used now | Higher retired count is treated as better disarmament signal, but large retired counts can also reflect historically large arsenals. |
| Is the source observation direct-year or stale? | FAS snapshot date; SIPRI Yearbook publication year | Used now via confidence / temporal-fit | FAS consolidated page has a known freshness caveat; do not treat stale FAS values as fully current. |
| Has the state signed/ratified key nuclear restraint treaties and safeguards? | NPT / CTBT / TPNW / IAEA safeguards data | Additional standard | Relevant to responsibility but not yet in current source plan. NTI was blocked; future IAEA/UN treaty data could cover this. |
| Is the state expanding, modernizing, or reducing the arsenal? | Year-over-year FAS/SIPRI deltas; Nuclear Notebook narrative | Additional standard | Needed for responsibility vs static capability. Not yet normalized. |
| Has the leader made explicit nuclear threats or adopted high-risk nuclear doctrine? | Cited expert/manual review; possible LLM adjudication with constrained sources | Additional standard | Important for existential responsibility; not answered by arsenal count. |
| Does the country merely rank high because it has population/economy/military size? | Population, GDP, conventional military metrics | Exclude / low value for nuclear score | Useful context elsewhere, but not evidence of nuclear responsibility. |

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

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| How prosperous is the average resident in market-rate terms? | WDI `wdi_gdp_per_capita` | Used now | Required WDI anchor. |
| How prosperous is the average resident after PPP adjustment? | WDI `wdi_gdp_per_capita_ppp_constant_2017`; future PWT output-side/expenditure-side GDP per capita | Used now / future | Required WDI anchor; PWT would improve cross-validation. |
| What is national income per person? | WDI `wdi_gni_per_capita_atlas`; UNDP GNI in social score | Used now | Complements GDP per capita. |
| How large is the economy? | WDI current GDP; WDI constant GDP | Used now | Supports global influence/context, but should not dominate well-being. |
| Is the economy open to trade? | WDI exports % GDP; WDI imports % GDP | Used now | Supporting signal, not a direct welfare guarantee. |
| Is the economy attracting external investment? | WDI FDI inflows current USD | Used now | Supporting confidence/prosperity signal; volatile. |
| What is the population base for scale interpretation? | WDI population | Used now | Context / denominator; not inherently good or bad. |
| Does the country have socioeconomic development and a functioning market economy? | BTI Q6 socioeconomic development; Q7 market competition; Q11 economic performance | Used now | Expert-coded cross-validation. |
| Are growth, inflation, unemployment, debt, and fiscal stability sound? | IMF WEO / WDI macro series / World Bank | Additional standard | Not currently in plan; important for competence/economic score. |
| Are benefits broadly shared rather than captured by elites? | Gini, poverty, inequality, social mobility | Additional standard / partly social score | Current economic category is prosperity-heavy; distribution lives mostly in social well-being. |
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

| Evaluation question | Current / candidate source metrics | Source status | Notes |
|---|---|---|---|
| Does the government deliver quality public services and credible policy? | WGI `wgi_government_effectiveness` | Used now | Required WGI anchor. |
| Does the rule of law support predictable implementation? | WGI `wgi_rule_of_law` | Used now | Required WGI anchor; overlaps with political freedom but used here as governance capacity. |
| Can the government formulate and implement sound regulations? | WGI `wgi_regulatory_quality` | Used now | Measures policy/regulatory competence. |
| Is political power stable enough to govern without violent or unconstitutional disruption? | WGI `wgi_political_stability` | Used now | Stability is not morality; it is a capacity/risk signal. |
| Are citizens able to monitor and hold government accountable? | WGI voice/accountability; V-Dem `v2x_accountability` | Used now | Accountability improves competence and limits abuses. |
| Are courts and legislature effective constraints on the executive? | V-Dem judicial constraints `v2x_jucon`; legislative constraints `v2xlg_legcon` | Used now | Captures institutional checks. |
| Is the political system democratically governed enough to support effective accountability? | V-Dem multiplicative polyarchy `v2x_mpi`; V-Dem regime classifier `v2x_regime` | Used now | Fallback/contextual source-plan indicators. |
| Does expert assessment judge governance quality/performance high? | BTI Governance Index; BTI Governance Performance | Used now | Biennial cross-validation. |
| Did the leader manage crises, disasters, public health, or security shocks competently? | Disaster mortality, pandemic outcomes, IMF/WDI shock response, manual review | Additional standard | Important leader competence dimension not covered directly by annual governance composites. |
| Did the leader improve outcomes relative to inherited baseline? | Time-series deltas in WGI/BTI/WDI/HDI/conflict | Additional standard | Current score is level-based; future version should separate level from trajectory. |
| Is authoritarian stability alone evidence of effectiveness? | WGI political stability only | Exclude / low value if used alone | Stability without accountability can mask repression; must be combined with other groups. |

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
   PWT lands; it currently allows one source because WDI coverage is broad and
   PWT is blocked on source hygiene.
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
