# Data Sources

The per-source registry for `data/raw/<source>/`. Each source gets its own folder and a `metadata.json` capturing provenance, license, version, download date, and ingestion status. Required by REQ-LAKE-002.

## Conventions

- One folder per source: `data/raw/<source_key>/`.
- Folder names are lowercase snake_case matching the import module (`src/leaders_db/ingest/<source_key>.py`).
- `metadata.json` shape is the example from `requirements/top-level-requirements.md` §5:

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
- Historical/prototype source-by-source implementation notes live in
  [`ingestion-plan.md`](ingestion-plan.md). Future source-interface
  work is governed by the clean source architecture in
  [`../architecture/sources.md`](../architecture/sources.md) and the testable
  requirements in [`../requirements/sources.md`](../requirements/sources.md).

## Priority Source Registry (requirement §6)

**Updated 2026-06-21 with ranking-question gap addenda.** The "Verdict" column reflects the per-source verdict. The Phase B report (`sources/vetting/report.md`) is restructured by **rating category** to make the "at least 2 sources per category" rule visible. Future rows in this file are intentionally allowed: they track sources we now know we need, even before Phase B-style vetting and Stage 2 implementation.

Verdicts: ✅ vetted_ok / ⚠️ vetted_with_caveats / ❌ blocked / ⏸️ deferred.

Intent: **Using now** / **Need / future** / **Blocked / user-managed**.

### Leader identity sources

| Source key | Verdict | Description | Coverage | Notes |
|---|---|---|---|---|
| `archigos` | ⚠️ | Archigos dataset on political leaders | 1875–2015 (8-year gap; staged file has start years 1840–2015) | free academic; Stata `.dta`; useful historical backstop only. Clean adapter at `src/leaders_db/sources/adapters/archigos/` emits `leader_identity_spell` observations from local `Archigos_4.1_stata14.dta`; it cannot validate 2023 leaders. |
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
| `eiu_democracy_index` | ⚠️ | Economist Intelligence Unit Democracy Index | **New candidate staged 2026-06-29** at `data/raw/eiu_democracy_index/`: public/report PDFs for 2006, 2008, 2010-2019, and 2021-2024. Clean `leaders_db.sources.adapters.eiu_democracy_index` adapter reads local PDFs only and emits conservative political-freedom/democracy validation observations for overall score, rank, rank change when present, five category sub-scores, and regime type when recoverable. License/redistribution still needs source-vetting; raw PDFs must not be redistributed. EIU did not publish annual updates for 2007 or 2009. The 2020 PDF was located but blocked in this environment (FUNDESA mirror returned 403; official `pages.eiu.com` did not resolve), so user placement is still needed for a complete 2006-2024 report set. |
| `rsf_press_freedom` | ✅ | Reporters Without Borders World Press Freedom Index | Annual CSVs on disk at `data/raw/rsf_press_freedom/`: 2002–2010 and 2012–2026. Direct `2011.csv` is absent; RSF publishes a combined 2011/2012 edition represented by the 2012 file. Use as a press/media-freedom sub-signal, not a full political-freedom replacement. |
| `freedom_house` | ✅ | Freedom House Freedom in the World | FIW 2026 user-managed/restricted workbooks are staged at `data/raw/freedom_house/`; clean `leaders_db.sources.adapters.freedom_house` adapter reads the 1973-2026 ratings/statuses workbook for political rights, civil liberties, and status. Do not redistribute raw FIW files. |

### Economic sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `world_bank_wdi` | ✅ | World Bank World Development Indicators | Free API; 2023 data confirmed. |
| `maddison_project` | ✅ | Maddison Project Database 2023 (Bolt and van Zanden 2024) | Canonical 4.9 MB xlsx is expected at `data/raw/maddison_project/mpd2023.xlsx` for real ingestion; raw file is not committed. 169 countries; covers 1–2022 (no 2023 data; **only year == 2023 target-year requests are proxied to 2022 per the documented 1-year-gap pattern** — years 2024+ are NOT silently backed by Maddison 2022; if WDI is missing those rows are blank with `missing_population` / `missing_gdp` flags). CC BY 4.0. **Provides the historical real-economy signal for the `economic_wellbeing` rating category.** Stage 2 adapter reads ONLY the `Full data` sheet and computes the derived total real GDP indicator (`gdppc * pop * 1000`) at row time when both cells are present. The Chronicle row builder uses Maddison for 1900-2022 and falls back to Maddison 2022 as the documented 1-year-gap proxy for year == 2023 only. |
| `pwt` | ✅ | Penn World Table 10.01 | Free xlsx, 6.5MB; 183 economies, 1950–2019, PPP-based; cross-validates WDI. Raw file is staged at `data/raw/pwt/pwt1001.xlsx` with `metadata.json`. **Stage 2 adapter implemented + wired (Phase B Increment B + second-pass reviewer follow-up):** `STAGE2_ADAPTERS["pwt"]` dispatches to `leaders_db.ingest.sources.pwt.ingest_pwt`; the per-source package at `src/leaders_db/ingest/sources/pwt/` is the reference implementation of the new shared `SourceAdapter` Protocol. Honors every request-scoped field end-to-end (raw_root, processed_root, database_url, year/years, country_filter, parquet_path, catalog_path). For target years beyond 2019, PWT does NOT silently proxy/stale-fill rows; out-of-coverage requests emit zero observations plus a `requested_year_out_of_coverage` manifest warning (87 focused tests, including a `year=2023` zero-row assertion and a `years=(2018,)` / `country_filter=('USA',)` request-scoping regression proof). The `registry.ingest_source` runner is opt-in (callers must `register('pwt', PWTAdapter())` before dispatch); the CLI uses `STAGE2_ADAPTERS` directly. |
| `imf_weo` | ❌ | IMF World Economic Outlook | Akamai bot challenge (403). User can fetch manually if needed. |
| `world_bank_poverty_inequality_platform` | ⚠️ | World Bank Poverty and Inequality Platform | **Implemented (2026-06-28) under the clean `leaders_db.sources` interface** at `src/leaders_db/sources/adapters/world_bank_poverty_inequality_platform/`. Offline / cache-first in this slice (no live HTTP fetching per the task brief); reads a staged cached CSV (`pip_stats.csv`) or cached JSON wrapper (`pip_stats.json`) from `data/raw/world_bank_poverty_inequality_platform/` plus a runtime-local `metadata.json` (gitignored per Always-On Rule #9). Emits ONE observation family (`poverty_inequality_country_year`) with 3 source-native catalog indicators (one per numeric indicator cell: `world_bank_poverty_inequality_platform_poverty_headcount_ratio` / `world_bank_poverty_inequality_platform_poverty_gap` / `world_bank_poverty_inequality_platform_gini_index`). The transform never invents a value from missing source-native data; blank / non-numeric cells are emitted as `value=None` / `value_type="missing"` plus the verbatim raw cell text on `extension.raw_value`. The source-native country code (the World Bank's own reporting identifier -- a 3-character code that LOOKS LIKE ISO3 but is NOT a canonical ISO3 mapping) is preserved verbatim on the audit-trail extension payload; `country_code` remains `None` until later matching / resolution stages introduce a canonical ISO3 mapping. Per-row PPP version + reporting level + welfare type + poverty line + version_id are preserved on the audit-trail extension payload so downstream code can recover the verbatim source-native provenance. **Important caveat:** PIP poverty / inequality estimates are SURVEY- and PPP-specific and SHOULD NOT be silently mixed across PIP version stamps (e.g. `20260324_2021` vs `20260324_2017`) or PPP bases (2021 PPP vs 2017 PPP) without explicit metadata propagation. World Bank Terms of Use for Datasets; free use with attribution. `cache_policy='refresh'` / `'no_cache'` fails readiness with a structured `world_bank_poverty_inequality_platform_unsupported_cache_policy` error. No persistence, manifest, or DB writes landed; the runner still returns `manifest=None`. No legacy `STAGE2_ADAPTERS["world_bank_poverty_inequality_platform"]` entry exists (no legacy Stage 2 implementation). |
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
| `sipri_arms_transfers` | ⚠️ | SIPRI Arms Transfers Database | **Implemented (2026-06-27) under the clean `leaders_db.sources` interface** at `src/leaders_db/sources/adapters/sipri_arms_transfers/`. Offline / cache-only in this slice (no live network fetch); reads a staged cached export (the canonical `trade_register.csv` file OR the canonical `trade_register.json` base64-JSON wrapper) from `data/raw/sipri_arms_transfers/` plus a runtime-local `metadata.json` (gitignored per Always-On Rule #9). Emits TWO observation families: `arms_transfer_register_row` (per-transfer, 3 per-row indicators `sipri_arms_transfers_tiv_delivered` / `sipri_arms_transfers_tiv_ordered` / `sipri_arms_transfers_number_delivered`) and `arms_transfer_country_year_aggregate` (deterministic per-`(role, country, year)` sum of TIV delivered over the cached bundle). **Important caveat:** arms-transfer data is evidence of arms flows between recorded supplier / recipient countries and is NOT direct proof of aggression, proxy sponsorship, or illegality. Downstream scorers MUST NOT silently treat arms-transfer TIV totals as a proxy for aggression / responsibility without an explicit secondary-source corroboration step (UCDP external support, sanctions records, expert-panel reports, manual evidence). SIPRI copyright; non-commercial use; attribution required. `cache_policy='refresh'` / `'no_cache'` fails readiness with a structured `sipri_arms_transfers_unsupported_cache_policy` error. No persistence, manifest, or DB writes landed; the runner still returns `manifest=None`. The legacy `STAGE2_ADAPTERS["sipri_arms_transfers"]` slot remains `None` (no legacy Stage 2 implementation). |
| `att_monitor` | ⏸️ | Arms Trade Treaty Monitor / national arms-export reports | **Need / future.** Candidate cross-check for arms-transfer legality, export approvals, and transfers despite civilian-harm risks. Not yet vetted or implemented. |
| `acled` | ⏸️ | Armed Conflict Location & Event Data Project | **Need / future.** Candidate for near-real-time actor-event conflict data and proxy/militia activity. Access/API requirements must be vetted. |

### Domestic repression / violence sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `political_terror_scale` | ✅ | Political Terror Scale | Direct file at `/Data/Files/PTS-2025.xlsx`; 1976–2025 coverage. |
| `cirights` | ⚠️ | CIRIGHTS Physical Integrity Rights | User-managed. v3.12.10.24 (Dec 2024) placed manually because `cirights.org` is DNS-unreachable from this environment. 207 countries × 1981–2022. **1-year gap to 2023** (use 2022 as proxy). See `data/raw/cirights/metadata.json`. |
| `acled_ucdp_osv` | ✅ | UCDP one-sided violence (subset of `ucdp`) | Same download as `ucdp`. |
| `icc_cases` | ⚠️ | International Criminal Court public cases and defendants | **New candidate staged 2026-06-29** at `data/raw/icc_cases/`: official ICC HTML snapshots for 75 defendants and 34 cases. Useful for severe legal-accountability/manual-review flags, not broad human-rights scoring. Narrow scope: only situations/persons reaching ICC proceedings, and downstream use must distinguish warrants/summons/charges/convictions/acquittals/dismissals/fugitives/custody/appeals. |

### Nuclear / global responsibility sources

| Source key | Verdict | Description | Notes |
|---|---|---|---|
| `fas` | ⚠️ | Federation of American Scientists nuclear notebook | Stage 2 adapter scrapes the consolidated "Status of World Nuclear Forces" page (`programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html`), a single parseable HTML `<table id="table1">` with all 9 nuclear-armed states. Per-country guides (nuke.fas.org/guide/<country>/) are table-of-contents landing pages; the consolidated status table is the canonical FAS-Nuclear-Notebook summary cited by SIPRI Yearbook Ch.7. **Snapshot freshness caveat:** the consolidated page's `<meta name="date">` element is dated 2014-04-30 as of probe (2026-06-19); the page is updated "continuously" per FAS but the consolidated snapshot has not changed. Stage 11 confidence penalises the temporal-fit gap between the snapshot year and the prototype's target year (2023). |
| `sipri_yearbook_ch7` | ✅ | SIPRI Yearbook Chapter 7: World Nuclear Forces (PDF) | 717KB; cross-checks FAS for nuclear arsenal facts. |
| `nti` | ❌ | Nuclear Threat Initiative country profiles | Cloudflare 403. |
| `iaea_safeguards` | ⚠️ | IAEA Safeguards Status List (PDF, status as of 2025-12-31) | **Implemented (2026-06-27) under the clean `leaders_db.sources` interface** at `src/leaders_db/sources/adapters/iaea_safeguards/`. Offline / cache-only in this slice (no live download / scraping); reads a single cached status-list PDF (`sg-agreements-comprehensive-status.pdf`) from `data/raw/iaea_safeguards/` plus a runtime-local `metadata.json` (gitignored per Always-On Rule #9). Emits ONE observation family (`nuclear_safeguards_status_country`) with 4 source-native catalog indicators (one per non-State column in the cached PDF table: `iaea_safeguards_safeguards_agreement_status` / `iaea_safeguards_additional_protocol_status` / `iaea_safeguards_small_quantities_protocol_status` / `iaea_safeguards_infcirc_number`). The catalog deliberately does NOT include a separate `iaea_safeguards_safeguards_agreement_type` indicator -- the canonical IAEA table has a single `Safeguards Agreement` column carrying the composite status label (e.g. `In Force: 153` / `Not in Force: 66` / `N/A`), NOT a separate type column. The adapter never invents a type column from the composite label. Captures safeguards / legal / status evidence -- the composite status of a Comprehensive Safeguards Agreement, the Additional Protocol / Small Quantities Protocol status, and the INFCIRC document identifier -- and is NOT a direct nuclear-weapons score or proof of compliance / non-compliance by itself. The raw-read boundary iterates every PDF page and accumulates rows from every page whose header matches the canonical column set, preserving `page_number` per row so the `RawLocator.page_number` field carries the exact page the row originated from. Downstream scorers MUST NOT silently treat a `Not in Force` AP cell as proof of non-cooperation; the descriptor's `coverage_hint.notes` carries the explicit caveat. The status list is a single-point legal snapshot; the descriptor advertises a single-year 2025 envelope so out-of-coverage year requests (e.g. `years=(2023,)`) emit zero observations plus a structured `YEAR_ABSENT` warning (no stale-proxy fill per SRC-COV-002 / SRC-COV-003). `cache_policy='refresh'` / `'no_cache'` fails readiness with a structured `iaea_safeguards_unsupported_cache_policy` error. The adapter does NOT invent ISO3 country codes; the source-native state display names are preserved verbatim on every emitted observation's `extension["iaea_safeguards_state"]` field. IAEA permits download / copy / use with acknowledgement for research / private study / commercial / non-commercial use subject to restrictions; do not redistribute the full PDF / table in outputs; attribution required. No persistence, manifest, or DB writes landed; the runner still returns `manifest=None`. The legacy `STAGE2_ADAPTERS["iaea_safeguards"]` slot remains `None` (no legacy Stage 2 implementation). |
| `iaea_additional_protocol_status` | ⏸️ | IAEA safeguards agreement / Additional Protocol status lists | **Subsumed by `iaea_safeguards`.** The Additional Protocol status cell is one of the 4 source-native catalog indicators emitted by the unified `iaea_safeguards` adapter (`iaea_safeguards_additional_protocol_status`); do not implement as a separate adapter. The `iaea_additional_protocol_status` slug in §7.2 is a subset / family of `iaea_safeguards`, not a standalone source row. |
| `unoda_treaties` | ⏸️ | UNODA Treaties Database / UN Treaty Collection | **Need / future.** Needed for NPT, CTBT, TPNW, and other nuclear-restraint treaty status. Not yet vetted or implemented. |
| `ctbto_treaty_status` | ⚠️ | CTBTO States Signatories (CTBT signature and ratification status) | **Implemented (2026-06-28) under the clean `leaders_db.sources` interface** at `src/leaders_db/sources/adapters/ctbto_treaty_status/`. Offline / cache-only in this slice (no live download / scraping per the CTBTO terms-of-use); reads a staged cached CSV (`states-signatories.csv`) or HTML fallback (`states-signatories.html`) from `data/raw/ctbto_treaty_status/` plus a runtime-local `metadata.json` (gitignored per Always-On Rule #9). Emits ONE observation family (`nuclear_treaty_status_country`) with 2 source-derived catalog indicators (one per date-bearing column in the canonical CTBTO table: `ctbto_treaty_status_signature_status` and `ctbto_treaty_status_ratification_status`). The transform never invents a signature / ratification status from empty / blank date cells -- an empty signature date cell is ALWAYS treated as `not_signed` and an empty ratification date cell is ALWAYS treated as `not_ratified`. The catalog deliberately does NOT include a default `ctbto_treaty_status_annex_2_status` indicator -- the canonical CTBTO public page does NOT carry an Annex 2 flag column; the adapter only emits an OPTIONAL Annex 2 observation when the cached fixture / source-native data carries an explicit `Annex 2` column (and never invents an Annex 2 flag from missing source-native data). Raw signature / ratification dates are preserved verbatim as strings on the audit-trail extension payload (the adapter does NOT coerce them to numeric years that could mislead Stage 11 confidence calculations). Captures CTBT treaty-status evidence -- the source-derived signature / ratification status flags -- and is NOT direct proof of nuclear behaviour, compliance, or non-compliance by itself. The status table is a single-point treaty-status snapshot (canonical probed stamp 2024-03-13); the descriptor advertises a single-year 2024 envelope so out-of-coverage year requests (e.g. `years=(2023,)`) emit zero observations plus a structured `YEAR_ABSENT` warning (no stale-proxy fill). `cache_policy='refresh'` / `'no_cache'` fails readiness with a structured `ctbto_treaty_status_unsupported_cache_policy` error. CTBTO terms-of-use permit download / copy / use with acknowledgement for personal, non-commercial, research / teaching use; the pipeline does NOT redistribute copied full table in outputs; attribution required. |
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

The steps below describe the legacy/prototype Stage 2 path. For new work, prefer
the `leaders_db.sources` path defined in [`../architecture/sources.md`](../architecture/sources.md)
and [`../requirements/sources.md`](../requirements/sources.md). Keep this
legacy checklist only when maintaining or comparing old `src/leaders_db/ingest/`
adapters.

1. Create `data/raw/<source_key>/` with a placeholder `metadata.json` (`ingestion_status: pending`).
2. Add a module `src/leaders_db/ingest/<source_key>.py` with a `download_<source_key>()` and `ingest_<source_key>()` entrypoint.
3. Add a CLI command if it is a new top-level source (`leaders-db ingest-source --source <source_key>`).
4. Update this file's registry table.
5. Add tests under `tests/test_ingest_<source_key>.py`.
6. Update `docs/requirements/core.md` with any new REQ-* lines.

See [`AGENTS.md`](../../AGENTS.md) §3 (read before edit) and the always-on rules #1–#6 for the surrounding discipline.
