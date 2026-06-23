# Data Sources

The per-source registry for `data/raw/<source>/`. Each source gets its own folder and a `metadata.json` capturing provenance, license, version, download date, and ingestion status. Required by REQ-LAKE-002.

## Conventions

- One folder per source: `data/raw/<source_key>/`.
- Folder names are lowercase snake_case matching the import module (`src/leaders_db/ingest/<source_key>.py`).
- `metadata.json` shape is the example from `req/top-level-requirements.md` §5:

```json
{
  "source_name": "V-Dem",
  "source_version": "v16",
  "download_date": "YYYY-MM-DD",
  "coverage": "country-year",
  "years_available": "varies by country",
  "license_note": "check source terms",
  "local_files": ["vdem_country_year_v16.csv"],
  "ingestion_status": "downloaded",
  "source_url": "https://www.v-dem.net/",
  "checksum_sha256": "..."
}
```

- `ingestion_status` is one of `pending`, `downloaded`, `ingested`, `unavailable`, `blocked_login`, `blocked_permission`, `parse_failed`.
- Source registry intent:
  - **Using now**: sources with implemented or planned Stage 2 ingestion for current prototype scoring.
  - **Need / future**: sources identified by the question-bank design as necessary to answer uncovered or weakly covered questions; not yet vetted or implemented.
  - **Blocked / user-managed**: sources that are useful but need manual acquisition, permissions, or a substitute.
- The source-by-source implementation backlog and modular adapter interface plan lives in [`source-ingestion-plan.md`](source-ingestion-plan.md).

## Priority Source Registry (requirement §6)

**Updated 2026-06-21 with ranking-question gap addenda.** The "Verdict" column reflects the per-source verdict. The Phase B report (`source-vetting/report.md`) is restructured by **rating category** to make the "at least 2 sources per category" rule visible. Future rows in this file are intentionally allowed: they track sources we now know we need, even before Phase B-style vetting and Stage 2 implementation.

Verdicts: ✅ vetted_ok / ⚠️ vetted_with_caveats / ❌ blocked / ⏸️ deferred.

Intent: **Using now** / **Need / future** / **Blocked / user-managed**.

### Leader identity sources

| Source key | Verdict | Description | Coverage | Notes |
|---|---|---|---|---|
| `archigos` | ⚠️ | Archigos dataset on political leaders | 1875–2015 (8-year gap) | free academic; Stata `.dta`; useful historical backstop only. |
| `leader_survival` | ⚠️ | Leader Survival (PLT post-1789) | 1789–2022 (1-year gap) | free academic; Demscore H-DATA v5 (March 2025). Best of the three. |
| `reign` | ⚠️ | Rulers, Elections, and Irregular Governance (REIGN) | 1950–2021-08 (frozen) | free academic; GitHub-hosted snapshot. Monthly updates ceased Aug 2021. |
| `soviet_leaders_curated` | ✅ | Soviet leaders curated (Wikipedia-anchored) | 1922-12-30 to 1991-12-25 | Hand-curated, versioned spell list at `data/raw/soviet_leaders_curated/soviet_leaders.csv`. Fills the SUN ruler gap that neither Archigos nor REIGN can resolve cleanly (merged Russian-Empire + USSR + RUS ccode). Transition years (1924, 1953, 1985) emit `multiple_rulers`. Underlying Wikipedia facts are not copyrightable; the curated CSV is a project artifact. |
| `wikidata_heads_of_state_government` | ✅ | Wikidata WikiProject Heads of state and government (SPARQL) | 1789–current (daily-updated) | CC0 1.0. **Primary 2023 source** — fills the gap. |
| `wikipedia_search_extract` | ✅ | Wikipedia Action API (search + extract) | all years | CC BY-SA 4.0. Narrative context for LLM rationale. |
| `cia_world_leaders` | ❌ | CIA World Factbook World Leaders | retired | The CIA World Factbook and its World Leaders page were retired in 2025. |
| `client_existing` | n/a | The client's manually built 2023 matrix (validation/test reference only; not an evidence source) | 2023 | local xlsx; see `data/raw/client_existing/metadata.json`. |

### Political freedom sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `vdem` | ✅ | Varieties of Democracy (V-Dem) | **v16 (March 2026) is on disk** at `data/raw/vdem/`. |
| `polity_v` | ✅ | Polity V dataset | Direct `.sav` file from inscrdata.html; 1800–2018, 167 countries. **Fallback to Freedom House for 2023.** |
| `rsf_press_freedom` | ✅ | Reporters Without Borders World Press Freedom Index | Annual CSVs on disk at `data/raw/rsf_press_freedom/`: 2002–2010 and 2012–2026. Direct `2011.csv` is absent; RSF publishes a combined 2011/2012 edition represented by the 2012 file. Use as a press/media-freedom sub-signal, not a full political-freedom replacement. |
| `freedom_house` | ⚠️ | Freedom House Freedom in the World | FIW data is gated behind an email request. **User handling; email sent, awaiting response.** |

### Economic sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `world_bank_wdi` | ✅ | World Bank World Development Indicators | Free API; 2023 data confirmed. |
| `maddison_project` | ✅ | Maddison Project Database 2023 (Bolt and van Zanden 2024) | Canonical 4.9 MB xlsx is expected at `data/raw/maddison_project/mpd2023.xlsx` for real ingestion; raw file is not committed. 169 countries; covers 1–2022 (no 2023 data; **only year == 2023 target-year requests are proxied to 2022 per the documented 1-year-gap pattern** — years 2024+ are NOT silently backed by Maddison 2022; if WDI is missing those rows are blank with `missing_population` / `missing_gdp` flags). CC BY 4.0. **Provides the historical real-economy signal for the `economic_wellbeing` rating category.** Stage 2 adapter reads ONLY the `Full data` sheet and computes the derived total real GDP indicator (`gdppc * pop * 1000`) at row time when both cells are present. The Chronicle row builder uses Maddison for 1900-2022 and falls back to Maddison 2022 as the documented 1-year-gap proxy for year == 2023 only. |
| `pwt` | ✅ | Penn World Table 10.01 | Free xlsx, 6.5MB; 183 economies, 1950–2019, PPP-based; cross-validates WDI. Raw file is staged at `data/raw/pwt/pwt1001.xlsx` with `metadata.json`. **Stage 2 adapter implemented + wired (Phase B Increment B + second-pass reviewer follow-up):** `STAGE2_ADAPTERS["pwt"]` dispatches to `leaders_db.ingest.sources.pwt.ingest_pwt`; the per-source package at `src/leaders_db/ingest/sources/pwt/` is the reference implementation of the new shared `SourceAdapter` Protocol. Honors every request-scoped field end-to-end (raw_root, processed_root, database_url, year/years, country_filter, parquet_path, catalog_path). For target years beyond 2019, PWT does NOT silently proxy/stale-fill rows; out-of-coverage requests emit zero observations plus a `requested_year_out_of_coverage` manifest warning (87 focused tests, including a `year=2023` zero-row assertion and a `years=(2018,)` / `country_filter=('USA',)` request-scoping regression proof). The `registry.ingest_source` runner is opt-in (callers must `register('pwt', PWTAdapter())` before dispatch); the CLI uses `STAGE2_ADAPTERS` directly. |
| `imf_weo` | ❌ | IMF World Economic Outlook | Akamai bot challenge (403). User can fetch manually if needed. |
| `world_bank_poverty_inequality_platform` | ⏸️ | World Bank Poverty and Inequality Platform | **Need / future.** Needed for Chapter 5 inclusive-prosperity questions: poverty headcount, poverty gap, inequality, and distribution. Not yet vetted or implemented. |
| `ilo_labor_statistics` | ⏸️ | ILO labor-market indicators | **Need / future.** Needed for Chapter 5 employment-quality questions: unemployment, labor-force participation, vulnerable/informal employment, youth unemployment, real wages where available. Not yet vetted or implemented. |
| `world_bank_global_findex` | ⏸️ | World Bank Global Findex / financial inclusion | **Need / future.** Candidate for Chapter 5 access-to-basic-economic-services questions, especially account ownership and financial access. Not yet vetted or implemented. |
| `world_inequality_database` | ⏸️ | World Inequality Database | **Need / future.** Candidate for top income/wealth shares, elite concentration, and distribution beyond Gini. Not yet vetted or implemented. |

### Country-area sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `cshapes` | ✅ | CShapes 2.0 (Schvitz et al. 2022) | 44.5 MB raw CSV at `data/raw/cshapes/CShapes-2.0.csv`; SHA-256 verified; gitignored per Always-On Rule #9. 1886-2019 coverage. CC BY-NC-SA 4.0. Provides `country_area_km2` per `(iso3, year)`. The Chronicle-side loader dispatches the GW 365 record (Russian Empire + USSR + RUS) to SUN (1922-1991) and RUS (1991+) via asymmetric containment rules. Years past coverage (2020+) are proxied from the most recent CShapes year and tagged with `area_proxy_year_used`. Imperial / controlled-area summing is NOT done by CShapes alone — the dependency-controller join is deferred per the Increment 4 work item. |
| `icow_colonial` | ❌ | ICOW Colonial History (Hensel) | The canonical download URL (`http://www.paulhensel.org/icowcol/Data/colhist.zip`) returned HTTP 404 on 2026-06-21. Substitute decision: conservative `controlled_area_km2 = country_area_km2` fallback with the explicit `controlled_area_country_only` flag. If a working URL or alternative dependency-controller source is identified, the controlled-area summing is the Increment 4 work item. |

### Social well-being sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `undp_hdi` | ✅ | UNDP Human Development Index (HDR 2023-24) | Direct CSV at `https://hdr.undp.org/sites/default/files/2023-24_HDR/HDR23-24_Composite_indices_complete_time_series.csv`; 207 countries, 1990–2022. |
| `world_bank_wdi_social` | ✅ | WDI health / education / inequality indicators | Subset of `world_bank_wdi`. |
| `who_gho_api` | ✅ | WHO Global Health Observatory (OData) | Free OData API; ~2000 indicators, including `WHOSIS_000001` (life expectancy). |

### Governance / effectiveness sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `world_bank_wgi` | ✅ | World Bank Worldwide Governance Indicators | Free xlsx + API; 2023 data confirmed. |
| `vdem_governance` | ✅ | V-Dem governance sub-indicators | Subset of `vdem` (already on disk). |
| `bti` | ✅ | Bertelsmann BTI Governance Index | Cumulative xlsx (`BTI_2006-2026_Scores.xlsx`) on disk at `data/raw/bti/`. 12 biennial editions × 137–159 countries × 123 columns. **For 2023, use the `BTI 2024` sheet** (covers 2022–2023). See `data/raw/bti/metadata.json`. |

### Corruption / integrity sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `transparency_cpi` | ⚠️ | Transparency International Corruption Perceptions Index | Stage 2 adapter downloads the canonical per-year CSV from the OCHA HDX mirror (`data.humdata.org/dataset/<uuid>/resource/<ruuid>/download/global_cpi_<year>.csv`); the direct xlsx download from transparency.org is CDN-gated. The publisher is Transparency International; HDX is the durable mirror. For the prototype's 2023 target year, 180 countries + per-country score / rank / sources / standardError / lowerCi / upperCi / region are extracted. |
| `world_bank_wgi_corruption` | ✅ | WGI Control of Corruption (subset of `world_bank_wgi`) | Same download as `world_bank_wgi`. |
| `vdem_corruption` | ✅ | V-Dem corruption variables | Subset of `vdem` (already on disk). |

### Conflict / international aggression sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `ucdp` | ✅ | Uppsala Conflict Data Program | Free 25.4MB zip; 1989-2022 data confirmed (the 23.1 release year is 2023; the data ends at 2022). Stage 2 adapter aggregates event-level data to country-year. **Primary international-conflict source** (replaces COW MID, which is blocked). |
| `cow_mid` | ❌ | Correlates of War Militarized Interstate Disputes | SSL cert issue in this environment + data ends 2014. `blocked`. |
| `sipri_milex` | ✅ | Stockholm International Peace Research Institute (milex) | Direct xlsx download; 1949–2025. |
| `sipri_yearbook_ch7` | ✅ | SIPRI Yearbook Chapter 7: World Nuclear Forces (PDF) | 717KB; cross-checks FAS for nuclear arsenal facts. |
| `ucdp_external_support` | ⏸️ | UCDP External Support Dataset / External Support in Non-State Conflict Dataset | **Need / future.** Needed for Chapter 2 proxy-aggression questions: state support to warring parties, non-state actors, sanctuary, finance, logistics, and military support. Not yet vetted or implemented. |
| `non_state_actor_dataset` | ⏸️ | Non-State Actor Dataset | **Need / future.** Candidate for state-rebel dyads, rebel capabilities, and external support context. Not yet vetted or implemented. |
| `dangerous_companions_nags` | ⏸️ | Dangerous Companions / NAGs state-support data | **Need / future.** Candidate for state cooperation/support to non-state armed groups. Not yet vetted or implemented. |
| `sipri_arms_transfers` | ⏸️ | SIPRI Arms Transfers Database | **Need / future.** Needed to identify conventional arms transfers to governments and, where available, non-state armed groups; useful for proxy-war and atrocity-risk questions. Not yet implemented. |
| `att_monitor` | ⏸️ | Arms Trade Treaty Monitor / national arms-export reports | **Need / future.** Candidate cross-check for arms-transfer legality, export approvals, and transfers despite civilian-harm risks. Not yet vetted or implemented. |
| `acled` | ⏸️ | Armed Conflict Location & Event Data Project | **Need / future.** Candidate for near-real-time actor-event conflict data and proxy/militia activity. Access/API requirements must be vetted. |

### Domestic repression / violence sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `political_terror_scale` | ✅ | Political Terror Scale | Direct file at `/Data/Files/PTS-2025.xlsx`; 1976–2025 coverage. |
| `cirights` | ⚠️ | CIRIGHTS Physical Integrity Rights | User-managed. v3.12.10.24 (Dec 2024) placed manually because `cirights.org` is DNS-unreachable from this environment. 207 countries × 1981–2022. **1-year gap to 2023** (use 2022 as proxy). See `data/raw/cirights/metadata.json`. |
| `acled_ucdp_osv` | ✅ | UCDP one-sided violence (subset of `ucdp`) | Same download as `ucdp`. |

### Nuclear / global responsibility sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `fas` | ⚠️ | Federation of American Scientists nuclear notebook | Stage 2 adapter scrapes the consolidated "Status of World Nuclear Forces" page (`programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html`), a single parseable HTML `<table id="table1">` with all 9 nuclear-armed states. Per-country guides (nuke.fas.org/guide/<country>/) are table-of-contents landing pages; the consolidated status table is the canonical FAS-Nuclear-Notebook summary cited by SIPRI Yearbook Ch.7. **Snapshot freshness caveat:** the consolidated page's `<meta name="date">` element is dated 2014-04-30 as of probe (2026-06-19); the page is updated "continuously" per FAS but the consolidated snapshot has not changed. Stage 11 confidence penalises the temporal-fit gap between the snapshot year and the prototype's target year (2023). |
| `sipri_yearbook_ch7` | ✅ | SIPRI Yearbook Chapter 7: World Nuclear Forces (PDF) | 717KB; cross-checks FAS for nuclear arsenal facts. |
| `nti` | ❌ | Nuclear Threat Initiative country profiles | Cloudflare 403. |
| `iaea_safeguards` | ⏸️ | IAEA safeguards reports / safeguards conclusions | **Need / future.** Needed for Chapter 1 questions on safeguards, monitoring, enrichment/fuel-cycle risk, and compliance. Not yet vetted or implemented. |
| `iaea_additional_protocol_status` | ⏸️ | IAEA safeguards agreement / Additional Protocol status lists | **Need / future.** Needed for safeguards and treaty-restraint questions. Not yet vetted or implemented. |
| `unoda_treaties` | ⏸️ | UNODA Treaties Database / UN Treaty Collection | **Need / future.** Needed for NPT, CTBT, TPNW, and other nuclear-restraint treaty status. Not yet vetted or implemented. |
| `ctbto_treaty_status` | ⏸️ | CTBTO treaty status | **Need / future.** Needed for CTBT signature/ratification posture. Not yet vetted or implemented. |
| `ctbto_nuclear_tests` | ⏸️ | CTBTO nuclear-test records / monitoring statements | **Need / future.** Needed for nuclear explosive-test history and recent testing signals. Not yet vetted or implemented. |
| `nuclear_weapons_ban_monitor` | ⏸️ | Nuclear Weapons Ban Monitor state profiles | **Need / future.** Candidate cross-check for nuclear-armed states, umbrella states, TPNW/NPT/CTBT posture, and disarmament compliance. Not yet vetted or implemented. |
| `csis_missile_threat` | ⏸️ | CSIS Missile Threat | **Need / future.** Needed for ballistic/cruise missile capability, delivery-system testing, and nuclear-capable missile context. Not yet vetted or implemented. |
| `cns_nti_missile_launches` | ⏸️ | CNS / NTI Missile and SLV Launch Databases | **Need / future.** Needed for missile-launch/test behavior and delivery-system experimentation. Not yet vetted or implemented. |
| `world_nuclear_association_profiles` | ⏸️ | World Nuclear Association country profiles / fuel-cycle profiles | **Need / future.** Candidate for civilian fuel-cycle, enrichment, reprocessing, and nuclear infrastructure context. Must distinguish civilian safeguarded capacity from weapons intent. |
| `nti_country_profiles` | ❌ / user-managed | NTI country profiles | **Need / future but currently blocked.** Direct NTI access was Cloudflare-blocked under `nti`; if user captures profiles manually, use as a user-managed source for nuclear aspiration, missile, WMD, and nonproliferation context. |

### Promise-to-results / effectiveness sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `government_manifestos` | ⏸️ | Campaign platforms, coalition agreements, government programs, state-of-the-nation speeches | **Need / future.** Required for Chapter 8's revised promise-to-results framing: identify what the ruler/government advertised as goals before judging delivery. Likely manual/LLM-assisted extraction with citations. |
| `budget_execution_reports` | ⏸️ | Budgets, budget execution, audit reports, public investment / program-delivery records | **Need / future.** Required to distinguish effort and implementation from slogans. Not yet vetted or implemented. |
| `national_statistics_goal_indicators` | ⏸️ | Goal-specific official and independent outcome indicators | **Need / future.** Required for Chapter 8 to compare stated goals against outcome movement: crime, GDP/jobs/inflation, education, health, conflict, etc. Use existing category indicators where possible, plus country-specific indicators when needed. |
| `audit_oversight_reports` | ⏸️ | Supreme audit institution, parliamentary oversight, inspector-general, public evaluation reports | **Need / future.** Candidate evidence for implementation quality, milestone delivery, failures, and course correction. Not yet vetted or implemented. |

## Source Authority And Specificity Tables

These cross-source tables live in `data/metadata/` and are loaded at runtime:

- `source_authority_table.csv` — numeric authority weight per source per indicator family (per §11 source_authority_score).
- `country_aliases.csv` — alias-to-ISO3 mapping built up across ingests.
- `indicator_catalog.csv` — obsolete draft location. The canonical Stage 5 contracts are the committed per-source catalogs in `src/leaders_db/ingest/catalogs/<source>.csv` plus the category source plans in `src/leaders_db/score/source_plans.py`. Any consolidated metadata file should be generated from those contracts, not edited as an independent source of truth.

The system must **not** invent authority weights in a one-off script. Add or change weights only by editing `data/metadata/source_authority_table.csv` and recording the change in `docs/reviews/`.

## Adding a new source

1. Create `data/raw/<source_key>/` with a placeholder `metadata.json` (`ingestion_status: pending`).
2. Add a module `src/leaders_db/ingest/<source_key>.py` with a `download_<source_key>()` and `ingest_<source_key>()` entrypoint.
3. Add a CLI command if it is a new top-level source (`leaders-db ingest-source --source <source_key>`).
4. Update this file's registry table.
5. Add tests under `tests/test_ingest_<source_key>.py`.
6. Update `docs/req/requirements-core.md` with any new REQ-* lines.

See [`AGENTS.md`](../AGENTS.md) §3 (read before edit) and the always-on rules #1–#6 for the surrounding discipline.
