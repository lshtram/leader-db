# Source Attributions

> **This file is the durable record of every data source the project has used or considered using.** It is normative: every Stage 15 report, manual-review queue, exported CSV, and LLM rationale must include the attribution block from this file. The pipeline must never publish output without attribution.
>
> **For URL and provenance details** (download links, checksums, file sizes), see [`docs/data-sources.md`](data-sources.md) and the per-source `data/raw/<source>/metadata.json`.
>
> **For in-progress vetting findings** (which sources are still being probed, what we considered and rejected), see [`docs/source-vetting/worksheet.md`](source-vetting/worksheet.md).
>
> **For the final sign-off** (the version reviewed by the user and the gate for Phase C), see [`docs/source-vetting/report.md`](source-vetting/report.md) — signed off 2026-06-17 21:00; living addenda continue to amend it as new sources are vetted or re-probed.

---

## 1. Sources In Use

Each source below is in active use by the pipeline. The table at the end of this section summarizes the same information for quick reference.

### `archigos` — historical leader identity (1875–2015)

- **What we extract:** leader identity, tenure start/end dates, entry/exit types, gender, birth/death dates. (Stata `.dta` file.)
- **What we don't use:** the post-2015 era (data ends 31 December 2015). This is acceptable for the prototype because the 2023 reference is the client bundle and Wikidata covers 2023+.
- **License:** free academic; cite Goemans, Gleditsch, and Chiozza 2009.
- **Citation:**
  > Goemans, Henk E., Kristian Skrede Gleditsch, and Giacomo Chiozza. 2009. "Introducing Archigos: A Data Set of Political Leaders." *Journal of Peace Research* 46(2): 269–183.
- **Attribution text in reports:** "Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009)."

### `reign` — historical leader identity, monthly (1950–2021-08)

- **What we extract:** monthly leader identification, regime type, election outcomes, irregular events. (CSV file `REIGN_2021_8.csv` from GitHub.)
- **What we don't use:** post-August 2021 (monthly updates ceased). Used as historical backstop only.
- **License:** free academic; cite Bell 2016.
- **Citation:**
  > Bell, Curtis. 2016. *The Rulers, Elections, and Irregular Governance (REIGN) Dataset*. Broomfield, CO: OEF Research. Available at oefresearch.org.
- **Attribution text in reports:** "REIGN dataset (Bell 2016), snapshot of August 2021."

### `leader_survival` — political leaders, 1789–2022 (PLT post-1789)

- **What we extract:** leader identity, entry/exit dates, type of leader position, biographical background. (Stata + CSV from Demscore H-DATA v5.)
- **What we don't use:** 2023 (coverage ends 2022, 1-year gap). Best of the historical trio.
- **License:** free academic; cite Gerring et al. 2024.
- **Citation:**
  > Gerring, John, Xin Nong, Ben Chatterton, Lee Cojocaru, Cem Mert Dalli, Carl Henrik Knutsen, Andrej Kokkonen, Daniel Steven Smith, Jan Teorell, Sam Selsky, Daisy Ward, and Ji Yeon Jeon. 2024. "Leader Tenure through the Ages: The Growth of Constraints." Unpublished manuscript, University of Texas at Austin.
- **Attribution text in reports:** "Leader Survival (PLT post-1789) v5, H-DATA (Gerring et al. 2024)."

### `vdem` — Varieties of Democracy, 1789–2025 (v16)

- **What we extract:** political-freedom indices (liberal, electoral, participatory, deliberative, egalitarian democracy), governance, corruption, repression, judicial independence, and ~531 other indicators. The Stage 2 adapter will narrow the indicator list to the columns referenced by the indicator catalog.
- **What we don't use:** coder-level data (privacy-sensitive) and the "Country-Date" granularity (we aggregate to country-year).
- **License:** free academic; cite V-Dem Institute v16. **DOI:** https://doi.org/10.23696/vdemds26.
- **Citation (verbatim from `suggested_citation.pdf` in the dataset):**
  > Coppedge, Michael, John Gerring, Carl Henrik Knutsen, Staffan I. Lindberg, Jan Teorell, David Altman, Fabio Angiolillo, Michael Bernhard, Agnes Cornell, M. Steven Fish, Linnea Fox, Lisa Gastaldi, Haakon Gjerløw, Adam Glynn, Ana Good God, Allen Hicken, Katrin Kinzelbach, Joshua Krusell, Kyle L. Marquardt, Kelly McMann, Valeriya Mechkova, Juraj Medzihorsky, Anja Neundorf, Pamela Paxton, Daniel Pemstein, Josefine Pernes, Johannes von Römer, Brigitte Seim, Rachel Sigman, Svend-Erik Skaaning, Jeffrey Staton, Aksel Sundström, Marcus Tannenberg, Eitan Tzelgov, Yi-ting Wang, Tore Wig, Steven Wilson and Daniel Ziblatt. 2026. "V-Dem [Country-Year/Country-Date] Dataset v16" Varieties of Democracy (V-Dem) Project. https://doi.org/10.23696/vdemds26.
  >
  > **And:**
  >
  > Pemstein, Daniel, Kyle L. Marquardt, Eitan Tzelgov, Yi-ting Wang, Juraj Medzihorsky, Joshua Krusell, Farhad Miri, and Johannes von Römer. 2026. "The V-Dem Measurement Model: Latent Variable Analysis for Cross-National and Cross-Temporal Expert-Coded Data". V-Dem Working Paper No. 21. 11th edition. University of Gothenburg: Varieties of Democracy Institute.
- **Attribution text in reports:** "V-Dem v16 (Coppedge et al. 2026)."

### `world_bank_wdi` — World Bank WDI, 1960–2023+

- **What we extract:** population, GDP, GDP per capita, inflation, unemployment, and other economic indicators. Indicator codes are listed in the indicator catalog.
- **License:** **CC BY 4.0 International**; the World Bank's [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) require attribution in the form "The World Bank: Dataset name: Data source (if known)."
- **Citation:**
  > World Bank. 2024. World Development Indicators. Washington, D.C.: The World Bank. https://data.worldbank.org/ Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
- **Attribution text in reports:** "World Bank WDI (World Bank 2024)."

### `world_bank_wgi` — World Bank WGI, 1996–2022

- **What we extract:** six aggregate governance indicators (Voice and Accountability, Political Stability, Government Effectiveness, Regulatory Quality, Rule of Law, Control of Corruption). Estimate column only (the 5 other per-year statistics — StdErr, NumSrc, Rank, Lower, Upper — are deferred to a future iteration if the score module needs per-source confidence intervals).
- **License:** **CC BY 4.0 International**; the World Bank's [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) require attribution in the form "The World Bank: Dataset name: Data source (if known)."
- **Citation:**
  > World Bank. 2023. Worldwide Governance Indicators. Washington, D.C.: The World Bank. https://info.worldbank.org/governance/wgi/ Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
- **Attribution text in reports:** "World Bank WGI (World Bank 2023)."

### `ucdp` — Uppsala Conflict Data Program, 1989–2022 (GED 23.1)

- **What we extract:** country-year aggregates of organized violence. The UCDP GED 23.1 dataset is event-level (~316,818 events in v23.1); the Stage 2 adapter aggregates events to country-year using `type_of_violence` (1 = state-based, 2 = non-state, 3 = one-sided) and `gwnob` (the Gleditsch-Ward state number for side_b, identifying cross-border / internationalized state-based events). Feeds `international_peace` (type=1 + intl subset) and `domestic_violence` (type=3). Non-state conflict (type=2) is not on the indicator catalog.
- **License:** free academic; cite UCDP per <https://ucdp.uu.se/terms-of-use/>.
- **Citation (verbatim, byte-identical to `UCDP_ATTRIBUTION` in code):**
  > Davies, Shawn, Garounis, Nicholas, Sollenberg, Ralph, and Allansson, Marie (2023). UCDP Georeferenced Event Dataset (GED) 23.1. Uppsala Conflict Data Program. https://ucdp.uu.se/downloads/
- **Attribution text in reports:** "UCDP GED 23.1 (Davies et al. 2023)."

### `transparency_cpi` — Transparency International CPI, 1995–2023

- **What we extract:** annual CPI score per country. (CSV mirrored via the OCHA Humanitarian Data Exchange (HDX); the canonical Transparency International xlsx download is CDN-gated per the source-vetting report §3.6, so the durable HDX-mirrored CSV is the production provenance. Stage 2 normalizes the HDX CSV to a narrow parquet and persists the verbatim cell as `source_observations.raw_value` for audit.)
- **License:** free for non-commercial use with attribution; cite Transparency International.
- **Citation:**
  > Transparency International. 2023. *Corruption Perceptions Index 2023*. Berlin: Transparency International. https://www.transparency.org/en/cpi/2023
- **Attribution text in reports:** "Transparency International CPI 2023."

### `sipri` — Stockholm International Peace Research Institute

- **What we extract:** military expenditure (share of GDP and government expenditure), arms transfers, nuclear forces. Sub-datasets selected by the Stage 2 adapter. The `sipri_milex` Stage 2 adapter extracts the Military Expenditure Database; the `sipri_yearbook_ch7` Stage 2 adapter (separate entry below) extracts nuclear forces.
- **License:** free; cite SIPRI.
- **Citation:**
  > Stockholm International Peace Research Institute. 2026. SIPRI Military Expenditure Database. https://www.sipri.org/databases/milex
- **Attribution text in reports:** "SIPRI milex (Stockholm International Peace Research Institute 2026)."

### `pts` (folder: `political_terror_scale`) — Political Terror Scale, 1976–2023

- **What we extract:** annual PTS score per country (1–5 scale, inverted so that high = less terror for our scoring convention).
- **License:** free academic; cite Wood, Gibney, et al.
- **Citation:**
  > Wood, Reed M., Mark Gibney, and others. *The Political Terror Scale (PTS)*. https://www.politicalterrorscale.org/
- **Attribution text in reports:** "Political Terror Scale (Wood, Gibney, et al.)."

### `cirights` — CIRI Human Rights Data Project, 1981–2022

- **What we extract:** the **Physical Integrity Rights Index** plus its four component indicators (Disappearances, Extrajudicial Killings, Political Imprisonment, Torture), the Repression Index, and the broader Civil and Political Rights Index — 7 catalog indicators total per the catalog at `src/leaders_db/ingest/catalogs/cirights.csv`. Per-country-year, 207 countries. Feeds the domestic-violence / repression category. The 2023 prototype uses 2022 as proxy (1-year gap) and records the proxy in the run manifest.
- **What we don't use:** the worker-rights law/practice columns (1994+) and the human-trafficking columns (1998+) and the Overall Human Rights Score / Women's Social Rights columns (2005+) for the 2023 prototype — they have shorter coverage and are not on the indicator catalog. Can be added in a later iteration.
- **License:** free academic; cite Cingranelli, Richards, and Crepaz. User-managed: file placed at `data/raw/cirights/` because the project site is not programmatically reachable from this environment.
- **Citation:**
  > Cingranelli, David L., David L. Richards, and Kelly M. Crepaz. 2024. "The Cingranelli-Richards (CIRI) Human Rights Data Project Dataset." Version v3.12.10.24. https://www.cirights.org/
- **Attribution text in reports:** "CIRI Human Rights Data Project v3.12.10.24 (Cingranelli, Richards, and Crepaz 2024)."

### `fas` — Federation of American Scientists nuclear notebook

- **What we extract:** for the ~9 nuclear-armed states, the consolidated FAS "Status of World Nuclear Forces" page (`https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html`) — a single HTML table with 5 indicator columns (Operational Strategic, Operational Nonstrategic, Reserve/Nondeployed, Military Stockpile, Total Inventory). The page is updated "continuously" per FAS but the consolidated snapshot is dated 2014-04-30 as of probe; the parsed snapshot year is recorded in the run manifest as the freshness stamp. Stage 11 confidence penalises the temporal-fit gap between the FAS snapshot year and the prototype's target year (2023). Per-country guides (nuke.fas.org/guide/<country>/) are updated more frequently; the consolidated status page is the canonical FAS Nuclear Notebook summary cited by SIPRI Yearbook Ch.7.
- **License:** free; cite FAS.
- **Citation:**
  > Federation of American Scientists. *Nuclear Notebook*. https://fas.org/issues/nuclear-weapons/
- **Attribution text in reports:** "FAS Nuclear Notebook (Federation of American Scientists)."

### `wikidata_heads_of_state_government` — Wikidata WikiProject

- **What we extract:** per-country `(head of state, head of government, start date, end date)` for the target year, plus the ISO3 country code (via `wbgetentities`). Fills the 2023 leader gap.
- **License:** **CC0 1.0** (Public Domain Dedication). No attribution required, but we credit the project as a courtesy.
- **Citation:**
  > Wikidata contributors. *Wikidata: WikiProject Heads of state and government*. https://www.wikidata.org/wiki/Wikidata:WikiProject_Heads_of_state_and_government
- **Attribution text in reports:** "Wikidata (CC0 1.0)."

### `wikipedia_search_extract` — Wikipedia Action API

- **What we extract:** page extracts (intro/lead) for leaders, countries, and contextual terms; page search for disambiguation. Reusable for LLM rationale input, manual-review context, and event verification.
- **License:** **CC BY-SA 4.0** (text of articles). API responses are licensed per the wiki's terms.
- **Citation:**
  > Wikipedia contributors. *Wikipedia, The Free Encyclopedia*. https://en.wikipedia.org/
- **Attribution text in reports:** "Wikipedia (CC BY-SA 4.0)."

### `client_existing` — the client's manually built 2023 validation reference

- **What we extract:** the reference dataset. The Stage 1 client ingest reads the xlsx bundle, normalizes country/leader names, and populates `ruler_scores.client_score` for the comparison stage.
- **License:** **internal client bundle; not redistributable.** Per the project brief and the REQ-REF-001 / REQ-REF-004 contract, the client matrix is a validation/test reference only: the system never overwrites `client_score`, and the matrix is never counted as an independent source for evidence, scoring, source agreement, or source authority. Outputs that quote client values must not include them in redistributable forms.
- **Attribution text in reports:** "Client-supplied 2023 matrix (internal; not for redistribution)."

### `undp_hdi` — UNDP Human Development Index (HDR 2023-24)

- **What we extract:** HDI (the composite), life expectancy at birth, expected years of schooling, mean years of schooling, GNI per capita. Per-country-year. Inequality-adjusted HDI, Gender Development Index, and Gender Inequality Index are present in the source CSV but are **not** extracted by the Stage 2 adapter (they are excluded per `docs/architecture/undp-hdi.md` §3 + §11).
- **License:** free; cite UNDP.
- **Citation:**
  > UNDP. 2024. *Human Development Report 2023-2024*. United Nations Development Programme. https://hdr.undp.org/
- **Attribution text in reports:** "UNDP HDR 2023-24 (United Nations Development Programme 2024)."

### `polity_v` — Polity V dataset

- **What we extract:** Polity score (regime type), durability, executive recruitment, executive constraints, political competition, political participation. Per-country-year, 1800–2018.
- **License:** free; cite Marshall, Jaggers, Gleditsch.
- **Citation:**
  > Marshall, Monty G., Ted Robert Gurr, and Keith Jaggers. 2018. *Polity5: Political Regime Characteristics and Transitions, 1800-2018*. Center for Systemic Peace.
- **Attribution text in reports:** "Polity V (Marshall, Jaggers, Gleditsch 2018)."

### `pwt` — Penn World Table 10.01

- **What we extract:** real GDP expenditure-side (`rgdpe`) and output-side (`rgdpo`) at chained PPPs, population (`pop`), employment (`emp`), average annual hours worked (`avh`), human capital index (`hc`), real consumption (`ccon`), capital depreciation (`cda`), TFP (`ctfp`, `rtfpna`), and capital stock (`rkna`). Per-country-year, 183 economies.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0); cite Feenstra, Inklaar, Timmer.
- **Citation:**
  > Feenstra, Robert C., Robert Inklaar, and Marcel P. Timmer. 2015. "The Next Generation of the Penn World Table." *American Economic Review* 105(10): 3150–3182.
- **Attribution text in reports:** "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)."

### `bti` — Bertelsmann Transformation Index, 2006–2026 (biennial)

- **What we extract:** the **G | Governance Index**, **GII | Governance Performance**, **S | Status Index**, **SI | Democracy Status**, plus the 17 questions Q1–Q5 (political transformation: stateness, political participation, rule of law, stability of democratic institutions, political and social integration) and Q6–Q12 (economic transformation). Per-country-edition, 137–159 countries depending on edition. Feeds the **governance / effectiveness** category, with secondary signals for **political freedom** (Q1–Q5) and **economic well-being** (Q6–Q12).
- **What we don't use:** the per-country "Category" classification columns (the BERTELSMANN-specific qualitative labels) — the numeric scores (1–10) are what the scoring rubric consumes.
- **License:** free; cite Bertelsmann Stiftung. Reprinted with permission per BTI terms of use.
- **Citation:**
  > Bertelsmann Stiftung. 2026. *BTI 2026 Transformation Index*. Gütersloh: Bertelsmann Stiftung. https://bti-project.org/
- **Attribution text in reports:** "BTI 2026 (Bertelsmann Stiftung 2026)."

### `who_gho_api` — WHO Global Health Observatory

- **What we extract:** life expectancy, immunizations, child mortality, NCDs, health system capacity, and ~2000 other indicators. OData API at `https://ghoapi.azureedge.net/api/`.
- **License:** open; cite WHO.
- **Citation:**
  > World Health Organization. *Global Health Observatory*. Geneva: WHO. https://www.who.int/data/gho
- **Attribution text in reports:** "WHO Global Health Observatory (World Health Organization)."

### `sipri_yearbook_ch7` — SIPRI Yearbook Chapter 7: World Nuclear Forces

- **What we extract:** nuclear arsenal facts (warhead counts, delivery systems) for the 9 nuclear-armed states. PDF (text extraction in Stage 2).
- **License:** free; cite SIPRI Yearbook.
- **Citation:**
  > Stockholm International Peace Research Institute. 2024. "World Nuclear Forces." In SIPRI Yearbook 2024: Armaments, Disarmament and International Security. Oxford University Press.
- **Attribution text in reports:** "SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024)."

### `rsf_press_freedom` — Reporters Without Borders World Press Freedom Index, 2002–2026

- **What we extract:** annual country/territory press-freedom score, rank, and country labels. For 2022+ editions, also extract component context scores/ranks (political, economic, legal, social/sociocultural, and safety/security) where needed by the indicator catalog. Feeds political freedom as a **press/media-freedom sub-signal**.
- **What we don't use:** RSF as a complete replacement for V-Dem, Polity V, or Freedom House. Pre-2022 and 2022+ scores use different methodology/schema and must not be merged without explicit normalization. Direct `2011.csv` is absent; RSF's combined 2011/2012 edition is represented by the 2012 file.
- **License:** public dataset; cite Reporters Without Borders / Reporters sans frontières and the World Press Freedom Index.
- **Citation:**
  > Reporters Without Borders. 2026. *World Press Freedom Index*. Paris: Reporters Without Borders / Reporters sans frontières. https://rsf.org/en/index
- **Attribution text in reports:** "RSF World Press Freedom Index (Reporters Without Borders 2026)."

### `maddison_project` — Maddison Project Database 2023 (real-economy history, 1–2022)

- **What we extract:** real GDP per capita (2011 international dollars, long-run comparable), population (thousands), and a DERIVED total real GDP indicator (`gdppc * pop * 1000`) computed by the Stage 2 adapter when both cells are present for the same country-year. Feeds the `economic_wellbeing` rating category.
- **What we don't use:** pre-1 and post-2022 values (the 2023 release ends at 2022; 2023 target-year requests are proxied to 2022 per the CIRIGHTS / UNDP HDI / Leader Survival 1-year-gap pattern). Per-indicator wide tabs (GDPpc, Population, Regional data, Maddison original sources, Notes, Sources) are also not used — the Stage 2 contract reads ONLY the `Full data` sheet.
- **License:** CC BY 4.0 International. Free academic + non-commercial; cite Bolt and van Zanden (2024) verbatim.
- **Citation:**
  > Bolt, Jutta and Jan Luiten van Zanden (2024), "Maddison style estimates of the evolution of the world economy: A new 2023 update", Journal of Economic Surveys, 1-41. DOI: 10.1111/joes.12618.
- **Attribution text in reports:** "Bolt, Jutta and Jan Luiten van Zanden (2024), 'Maddison style estimates of the evolution of the world economy: A new 2023 update', Journal of Economic Surveys, 1-41. DOI: 10.1111/joes.12618. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
- **Canonical download:** https://dataverse.nl/api/access/datafile/421302 (Excel).
- **Canonical page:** https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2023

### `cshapes` — CShapes 2.0 (historical country boundaries and area, 1886–2019)

- **What we extract:** country area (km²) per country-year, keyed by Gleditsch-Ward state code. The Chronicle row builder narrows the raw CSV to the pilot ISO3 set (USA, GBR, FRA, IND, RUS, SUN, CHN), dispatches the GW 365 record (Russian Empire + USSR + RUS) to SUN for 1922-1991 and RUS for 1992+, and emits `country_area_km2` per `(iso3, year)`. CShapes coverage ends in 2019; rows for 2020+ are proxied from the most recent CShapes year and tagged with `area_proxy_year_used`.
- **What we don't use:** the `the_geom` / `cap_geom` WKT polygon columns (area only), dependency / colony rows (controlled-area summing is deferred per Increment 4), the COW-coded variant (only the GW-coded CSV is staged).
- **License:** **CC BY-NC-SA 4.0 International** (Creative Commons Attribution-NonCommercial-ShareAlike 4.0). Per CShapes 2.0 (Schvitz et al. 2022) terms; non-commercial redistribution requires attribution + share-alike.
- **Citation:**
  > Schvitz, Guy, Seraina Rüegger, Luc Girardin, Lars-Erik Cederman, Nils Weidmann, and Kristian Skrede Gleditsch. 2022. "Mapping The International System, 1886-2017: The CShapes 2.0 Dataset." Journal of Conflict Resolution 66(1): 144–61.
- **Attribution text in reports:** "CShapes 2.0 (Schvitz et al. 2022), ETH Zurich ICR."
- **Canonical download:** https://icr.ethz.ch/data/cshapes/CShapes-2.0.csv

### `soviet_leaders_curated` — Soviet Union rulers (curated subset, Wikipedia-anchored)

- **What we extract:** per-leader spells (start / end dates) for the Soviet Union identity (Lenin, Stalin, Malenkov, Khrushchev, Brezhnev, Andropov, Chernenko, Gorbachev), 1922-12-30 to 1991-12-25. Fills the SUN ruler gap that neither Archigos (ccode 365 is the merged Russian-Empire + USSR + RUS record) nor REIGN (monthly data for the same merged ccode) can resolve cleanly. The Chronicle resolver picks the leader with the most days in the requested year; transition years (1924, 1953, 1985) emit `multiple_rulers` and the lower `SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE` confidence.
- **What we don't use:** non-Soviet leaders (the CSV is SUN-only); the raw Wikipedia infobox / markup (only the curated spell list is loaded). The full Soviet leader records (every Politburo member, every Presidium chairman) are out of scope for the Increment 3 pilot — only the de facto leader (General Secretary / Premier) is populated.
- **License:** The curated CSV is a project artifact; the underlying facts (leader names, dates) are derived from Wikipedia and are not copyrightable. Cite the source URLs in the metadata for downstream attribution.
- **Citation:**
  > Wikipedia contributors. "List of leaders of the Soviet Union." Wikipedia, The Free Encyclopedia. https://en.wikipedia.org/wiki/List_of_leaders_of_the_Soviet_Union (anchored 2026-06-21).
- **Attribution text in reports:** "Soviet leaders (curated subset, Wikipedia 'List of leaders of the Soviet Union'), as of 2026-06-21."
- **Anchor URLs:** https://en.wikipedia.org/wiki/List_of_leaders_of_the_Soviet_Union, https://en.wikipedia.org/wiki/General_Secretary_of_the_Communist_Party_of_the_Soviet_Union, https://en.wikipedia.org/wiki/Premier_of_the_Soviet_Union

### Generated text (LLM rationale, Stage 9–10 output)

- The LLM is invoked only for ambiguous interpretation per REQ-LLM-001.
- The `LLMScoreOutput.rationale` field is the generated text. It is validated against the Pydantic schema before persistence.
- The LLM does not invent scores or cite sources not given (REQ-LLM-004). Rationale text is therefore derived from the indicators already in the attribution block above, and does not introduce new sources.
- No additional attribution is needed beyond the indicators cited in the rationale; the model's provenance is recorded per LLM call in `data/outputs/llm_calls/<run-id>/`.

### Summary table

| Source key | Used for | Coverage (year) | License | Output attribution text |
|---|---|---|---|---|
| `archigos` | leader identity (historical) | 1875–2015 | free academic | "Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009)." |
| `reign` | leader identity (historical) | 1950–2021-08 | free academic | "REIGN dataset (Bell 2016), snapshot of August 2021." |
| `leader_survival` | leader identity (historical) | 1789–2022 | free academic | "Leader Survival (PLT post-1789) v5, H-DATA (Gerring et al. 2024)." |
| `vdem` | political freedom, governance, corruption, repression, social well-being (subset) | 1789–2025 | free academic, DOI 10.23696/vdemds26 | "V-Dem v16 (Coppedge et al. 2026)." |
| `world_bank_wdi` | economic indicators, social well-being (subset) | 1960–2023+ | CC BY 4.0 | "World Bank WDI (World Bank 2024)." |
| `maddison_project` | historical economic indicators (GDP per capita, population, derived real GDP total) | 1–2022 | CC BY 4.0 | "Bolt, Jutta and Jan Luiten van Zanden (2024), 'Maddison style estimates of the evolution of the world economy: A new 2023 update', Journal of Economic Surveys, 1-41. DOI: 10.1111/joes.12618. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)." |
| `cshapes` | country area (km²) | 1886–2019 | CC BY-NC-SA 4.0 | "CShapes 2.0 (Schvitz et al. 2022), ETH Zurich ICR." |
| `soviet_leaders_curated` | SUN ruler identity (de facto leader spells) | 1922-12-30 to 1991-12-25 | Wikipedia-anchored curated facts | "Soviet leaders (curated subset, Wikipedia 'List of leaders of the Soviet Union'), as of 2026-06-21." |
| `pwt` | economic indicators (PPP) | 1950–2019 | free academic | "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)." |
| `bti` | governance index, governance performance, status index, political/economic transformation questions | 2006–2026 (biennial) | free, cite Bertelsmann Stiftung | "BTI 2026 (Bertelsmann Stiftung 2026)." |
| `world_bank_wgi` | governance indicators | 1996–2022 | CC BY 4.0 | "World Bank WGI (World Bank 2023)." |
| `ucdp` | organized violence, one-sided violence | 1989–2022 (GED 23.1) | free academic | "UCDP GED 23.1 (Davies et al. 2023)." |
| `transparency_cpi` | corruption perceptions | 1995–2023 | free, non-commercial | "Transparency International CPI 2023." |
| `sipri_milex` | military expenditure | 1949–2025 | free | "SIPRI milex (Stockholm International Peace Research Institute 2026)." |
| `sipri_yearbook_ch7` | nuclear arsenal facts | annual | free | "SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024)." |
| `pts` | political terror | 1976–2025 | free academic | "Political Terror Scale (Wood, Gibney, et al.)." |
| `cirights` | physical-integrity rights, repression, civil/political rights | 1981–2022 | free academic, user-managed | "CIRI Human Rights Data Project v3.12.10.24 (Cingranelli, Richards, and Crepaz 2024)." |
| `fas` | nuclear arsenal facts (cross-check) | ongoing | free | "FAS Nuclear Notebook (Federation of American Scientists)." |
| `undp_hdi` | social well-being (HDI composite + le/eys/mys/gnipc) | 1990–2022 | free | "UNDP HDR 2023-24 (United Nations Development Programme 2024)." |
| `who_gho_api` | social well-being (health indicators) | ongoing | open | "WHO Global Health Observatory (World Health Organization)." |
| `polity_v` | political freedom (1800–2018) | 1800–2018 | free academic | "Polity V (Marshall, Jaggers, Gleditsch 2018)." |
| `rsf_press_freedom` | political freedom (press/media-freedom sub-signal) | 2002–2026 (no direct 2011 CSV) | public dataset; cite RSF | "RSF World Press Freedom Index (Reporters Without Borders 2026)." |
| `wikidata_heads_of_state_government` | current/historical leaders | all | CC0 1.0 | "Wikidata (CC0 1.0)." |
| `wikipedia_search_extract` | narrative context | all | CC BY-SA 4.0 | "Wikipedia (CC BY-SA 4.0)." |
| `client_existing` | the 2023 validation/test reference | 2023 | internal | "Client-supplied 2023 matrix (internal; not for redistribution)." |

---

## 2. Sources Considered But Rejected

For each source below, the reason it was not used and the substitute decision.

### `freedom_house` — FIW data is user-managed / pending provider response

- **Status:** ⚠️ user-managed. The user sent the FIW data request email; if the provider responds, place the file at `data/raw/freedom_house/`.
- **Why:** the Freedom House *Freedom in the World* data file is not freely downloadable. From the [publication archives page](https://freedomhouse.org/reports/publication-archives), verbatim: "Interested in downloading *Freedom in the World* report data? Please email research@freedomhouse.org with 'FIW Data Request' in the subject line and our team will assist you." A programmatic Phase 2 ingest cannot depend on an email gate.
- **Substitute decision:** V-Dem + Polity V + RSF cover political-freedom cross-validation while the FIW response is pending. If the user provides FIW data manually, it becomes an additional political-freedom source rather than silently replacing the others.

### `cow_mid` — data ends 2014; site has SSL issues in this environment

- **Status:** ❌ blocked for the prototype.
- **Why:** COW MID 4.0 covers 1816–2014 (9 years short of 2023) and the canonical zip URL returns 404. The COW homepage IP resolves but TLS handshake fails with "SSL certificate problem: unable to get local issuer certificate" in this sandbox environment. Even with the cert resolved, the data gap to 2023 is unbridgeable.
- **Substitute decision:** use UCDP for international-conflict indicators (UCDP GED 23.1 has 2023 data).

### `cirights` — superseded; data placed manually on 2026-06-17

> Moved to "Sources In Use" on 2026-06-17 after the user placed `cirights_v3.12.10.24.xlsx` (and the codebook PDF and the Stata zip) at `data/raw/cirights/`. The original "DNS-level unreachable" finding was correct at probe time but is moot now that the data is on disk. See Section 1 for the active entry.

### `cia_world_leaders` — CIA World Factbook retired

- **Status:** ❌ blocked for the prototype.
- **Why:** the CIA World Factbook and its World Leaders page have been retired in 2025. The URL `https://www.cia.gov/the-world-factbook/field/world-leaders/` 302-redirects to a farewell page. The user originally suggested this as a current-leaders backstop; Wikidata's "currently in office" query covers the same need.

### `nti` — Cloudflare bot challenge

- **Status:** ❌ blocked.
- **Why:** the URL returns 403 from Cloudflare even with a browser User-Agent. The server is reachable but Cloudflare's anti-bot blocks automated requests.
- **Substitute decision:** the nuclear arsenal coverage from FAS is cross-validated by SIPRI Yearbook Chapter 7 (added in the second wave). NTI is not needed.

### `eiu_polity_bmr` (partial — EIU only) — paywalled

- **Status:** 🟡 partially adopted.
- **Why:** EIU Democracy Index is paywalled. Polity V and BMR are free; Polity V is now adopted (see above), BTI is now adopted (moved to "Sources In Use" on 2026-06-17 after BTI 2026 was released).

### `HoG` (Heads of Government) — only 33 countries, 1870–2012

- **Status:** 🟡 not adopted.
- **Why:** HoG covers only 33 countries (Europe, Latin America, North America, Asia-Pacific) and the data ends in 2012. It is not a global leader dataset, and the post-2012 gap is unbridgeable.

### `imf_weo` — Akamai bot challenge

- **Status:** ❌ blocked for the prototype (Phase B verdict).
- **Why:** all IMF WEO endpoints return 403 from Akamai's bot challenge in this environment. The data is freely downloadable with a free IMF account, but programmatic access requires manual file placement.
- **Substitute decision:** Penn World Table (PWT) is the 2nd economic source for the prototype. PWT uses purchasing-power-parity (PPP) adjustments — a different methodology from WDI's market-exchange-rate-based metrics — which makes it a useful cross-validation. If the user wants WEO specifically, they can register at https://www.imf.org and place the WEO dataset manually in `data/raw/imf_weo/`.

### `bti` (Bertelsmann BTI) — superseded; data placed manually on 2026-06-17

> Moved to "Sources In Use" on 2026-06-17 after the user placed the cumulative `BTI_2006-2026_Scores.xlsx` (and the codebook PDF) at `data/raw/bti/`. The original "site returning 500 errors" finding on `/en/reports` and `/en/data` was correct at probe time but the canonical downloads page `/en/downloads` is alive, and BTI 2026 ("Repression Meets Resistance") has been released. See Section 1 for the active entry.

### `pwt_maddison` — superseded combined historical-economic candidate

- **Status:** 🟢 split into active sources.
- **Why:** the earlier combined placeholder bundled two distinct economic sources. Maddison Project Database 2023 is now adopted as `maddison_project` for historical real-economy coverage (see Section 1). Penn World Table is now adopted as `pwt` (see Section 1); its raw file and metadata are staged and the Stage 2 adapter is implemented + wired (`STAGE2_ADAPTERS["pwt"]` -> `leaders_db.ingest.sources.pwt.ingest_pwt`).

### `chicago_aisd` / `acled` — auxiliary violence sources

- **Status:** 🟡 deferred.
- **Why:** UCDP one-sided violence plus V-Dem's repression variables cover the prototype's needs. ACLED may be added in a future iteration if coverage is insufficient.

---

## 3. How Attribution Is Applied

The pipeline must carry attribution forward in every public output. The rules:

### 3.1 Stage 15 summary report

The markdown report at `data/outputs/validation_<year>_summary.md` ends with a "Sources & Attribution" section that lists every source used for that year, with the attribution text from the table above. Example:

```markdown
## Sources & Attribution

This validation report draws on the following sources:

- **Client-supplied 2023 matrix** (internal; not for redistribution) — the reference dataset.
- **V-Dem v16** (Coppedge et al. 2026) — political-freedom, governance, corruption, repression indicators.
- **World Bank WDI** (World Bank 2024) — population, GDP, GDP per capita.
- **World Bank WGI** (World Bank 2023) — six aggregate governance indicators.
- **BTI 2026** (Bertelsmann Stiftung 2026) — Governance Index, Status Index, political and economic transformation questions.
- **RSF World Press Freedom Index** (Reporters Without Borders 2026) — press/media-freedom signal.
- **UCDP GED 23.1** (Davies et al. 2023) — organized violence.
- **Transparency International CPI 2023** — corruption perceptions.
- **CIRI Human Rights Data Project v3.12.10.24** (Cingranelli, Richards, and Crepaz 2024) — physical-integrity rights and repression indicators.
- **Archigos v4.1** (Goemans, Gleditsch, and Chiozza 2009) — historical leader identity.
- **REIGN** (Bell 2016, snapshot of August 2021) — historical leader identity.
- **Leader Survival (PLT post-1789) v5** (Gerring et al. 2024) — historical leader identity.
- **Wikidata** (CC0 1.0) — current leaders and country code mapping.
- **Wikipedia** (CC BY-SA 4.0) — narrative context for manual review.
```

The `client_existing` line is included only for reports that quote or compare against client values. It is not an external evidence source and must not contribute to source agreement or source authority.

### 3.2 Manual-review queue CSV

The CSV at `data/outputs/validation_<year>_manual_review_queue.csv` carries the attribution block as a comment in the header (CSV has no native comments, so the first non-data row is a single-cell comment line: `# Sources: V-Dem v16 (Coppedge et al. 2026); World Bank WDI (World Bank 2024); ...`).

### 3.3 Per-ruler score rows in `ruler_scores`

The `ruler_scores.source_agreement` field carries a code like `"vdem+wb_wgi+wdi+ucdp"` — short source tags. The full attribution text is in the `data/outputs/llm_calls/<run-id>/` audit trail per call. The Stage 15 report's "Sources & Attribution" section is the canonical place to look up the full text from a source tag.

### 3.4 LLM rationale

The `LLMScoreOutput.rationale` field is generated text. It is not separately attributed per call (the LLM does not introduce new sources per REQ-LLM-004). The Stage 15 report's "Sources & Attribution" section applies.

### 3.5 README

The top-level `README.md` has a "License & Attribution" section that lists every source with attribution text. Updated whenever a new source is added or an existing source is upgraded.

### 3.6 Where the rule lives in the code

The attribution block is composed by `src/leaders_db/export/markdown_report.py` (or a sibling module) and is part of every output that crosses a public boundary. Test the rule: if a Stage 15 report is published without the attribution block, the test fails.

---

## 4. Citation Cheat-Sheet (copy-pasteable)

The exact citation text for each source, in the format most commonly expected by the source's own publication requirements.

```
Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009).
  Goemans, Henk E., Kristian Skrede Gleditsch, and Giacomo Chiozza. 2009.
  "Introducing Archigos: A Data Set of Political Leaders."
  Journal of Peace Research 46(2): 269–183.

REIGN dataset (Bell 2016), snapshot of August 2021.
  Bell, Curtis. 2016. The Rulers, Elections, and Irregular Governance
  (REIGN) Dataset. Broomfield, CO: OEF Research.

Leader Survival (PLT post-1789) v5, H-DATA (Gerring et al. 2024).
  Gerring, John, et al. 2024. "Leader Tenure through the Ages."
  Unpublished manuscript, University of Texas at Austin.

V-Dem v16 (Coppedge et al. 2026).
  Coppedge, Michael, et al. 2026. "V-Dem [Country-Year/Country-Date]
  Dataset v16." Varieties of Democracy (V-Dem) Project.
  https://doi.org/10.23696/vdemds26

World Bank WDI (World Bank 2024).
  World Bank. 2024. World Development Indicators.
  https://data.worldbank.org/

Bolt, Jutta and Jan Luiten van Zanden (2024), "Maddison style
estimates of the evolution of the world economy: A new 2023 update",
Journal of Economic Surveys, 1-41. DOI: 10.1111/joes.12618.
Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

CShapes 2.0 (Schvitz et al. 2022).
  Schvitz, Guy, Seraina Ruegger, Luc Girardin, Lars-Erik Cederman,
  Nils Weidmann, and Kristian Skrede Gleditsch. 2022. "Mapping The
  International System, 1886-2017: The CShapes 2.0 Dataset."
  Journal of Conflict Resolution 66(1): 144-61.

Soviet leaders (curated subset, Wikipedia 'List of leaders of the
Soviet Union'), as of 2026-06-21.
  Wikipedia contributors. "List of leaders of the Soviet Union."
  Wikipedia, The Free Encyclopedia.
  https://en.wikipedia.org/wiki/List_of_leaders_of_the_Soviet_Union

World Bank WGI (World Bank 2023).
  World Bank. 2023. Worldwide Governance Indicators.
  https://info.worldbank.org/governance/wgi/

BTI 2026 (Bertelsmann Stiftung 2026).
  Bertelsmann Stiftung. 2026. BTI 2026 Transformation Index.
  Gütersloh: Bertelsmann Stiftung. https://bti-project.org/

UCDP GED 23.1 (Davies et al. 2023).
  Davies, Shawn, et al. 2023. UCDP Georeferenced Event Dataset
  (GED) 23.1. Uppsala Conflict Data Program.
  https://ucdp.uu.se/downloads/

Transparency International CPI 2023.
  Transparency International. 2023. Corruption Perceptions Index
  2023. https://www.transparency.org/en/cpi/2023

SIPRI (Stockholm International Peace Research Institute 2024).
  Stockholm International Peace Research Institute. 2024.
  SIPRI Yearbook 2024. Oxford University Press.

Political Terror Scale (Wood, Gibney, et al.).
  Wood, Reed M., Mark Gibney, et al. The Political Terror Scale.
  https://www.politicalterrorscale.org/

CIRI Human Rights Data Project v3.12.10.24 (Cingranelli, Richards, and Crepaz 2024).
  Cingranelli, David L., David L. Richards, and Kelly M. Crepaz. 2024.
  "The Cingranelli-Richards (CIRI) Human Rights Data Project Dataset."
  Version v3.12.10.24. https://www.cirights.org/

FAS Nuclear Notebook (Federation of American Scientists).
  Federation of American Scientists. Nuclear Notebook.
  https://fas.org/issues/nuclear-weapons/

NTI Country Profiles (Nuclear Threat Initiative).
  Nuclear Threat Initiative. Country Profiles.
  https://www.nti.org/countries/

RSF World Press Freedom Index (Reporters Without Borders 2026).
  Reporters Without Borders. 2026. World Press Freedom Index.
  Paris: Reporters Without Borders / Reporters sans frontières.
  https://rsf.org/en/index

Wikidata (CC0 1.0).
  Wikidata contributors. Wikidata: WikiProject Heads of state and
  government. https://www.wikidata.org/wiki/Wikidata:WikiProject_Heads_of_state_and_government

Wikipedia (CC BY-SA 4.0).
  Wikipedia contributors. Wikipedia, The Free Encyclopedia.
  https://en.wikipedia.org/

Client-supplied 2023 matrix (internal; not for redistribution).
```

---

## 5. When a New Source Is Added

When the pipeline gains a new external source:

1. Add the source to the per-source `data/raw/<source>/metadata.json` (download URL, checksum, license).
2. Add a row to Section 1 of this file: what we extract, what we don't, license, citation, attribution text.
3. Update the Stage 15 report template to include the new attribution line.
4. Update `README.md`'s License & Attribution section.
5. Update `docs/data-sources.md` with the verified URL.
6. Add a test that the new attribution text appears in the report.

When a source is rejected, add a row to Section 2 with the reason and the substitute decision.

When a source's license or citation requirement changes (e.g., a new version of V-Dem is released), update Section 1 and Section 3 in the same commit. Do not defer.
