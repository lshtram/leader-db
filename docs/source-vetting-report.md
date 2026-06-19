# Source Vetting Report — Phase B Outcome (B.1 + B.2)

> **Status: signed off; living source record.** This is the canonical Phase B deliverable. Phase C (data acquisition) is underway; addenda are recorded here as sources are recovered or newly adopted.
>
> The report is a clean summary of [`docs/source-vetting-worksheet.md`](source-vetting-worksheet.md) (the audit trail) and a by-rating-category view of the coverage. The attribution text per source is in [`docs/source-attributions.md`](source-attributions.md).
>
> **Updated 2026-06-18 (addenda):** CIRIGHTS and BTI are now on disk; RSF Worldwide Press Freedom Index annual CSVs were acquired and added as a political-freedom sub-signal. Freedom House remains user-managed, not programmatically blocked forever.

---

## 1. Scope

Phase B vetted every priority external source listed in requirement §6, the three sources added in the first round (Wikidata, Wikipedia, CIA — CIA retired), the five second-source candidates added in the second round, and the RSF Worldwide Press Freedom Index addendum.

**Current external source count:** 26 distinct source entries across 8 rating categories: 15 ✅ vetted_ok, 7 ⚠️ vetted_with_caveats / user-managed, 4 ❌ blocked, 0 ⏸️ deferred.

The client bundle (`data/raw/client_existing/`) was excluded from the external-source probe itself — its `metadata.json` was written in Phase A and the Stage 1 loader reads it as the 2023 validation/reference artifact. It is **not** listed as an external source and must not be counted as evidence, source agreement, or source authority. It is used only for tests, validation comparisons, deltas, and manual-review triggers.

## 2. Coverage per rating category — the "≥ 2 sources" rule

The 8 rating categories are from requirement §4. Each must have at least **two distinct datasets** from different producers / methodologies for cross-validation (REQ-CONF-002 "source_agreement_score" + "source_authority_score" need ≥ 2 sources to be meaningful).

| # | Rating category | Datasets | Count | Status |
|---|---|---|---|---|
| 1 | **Nuclear** | FAS + SIPRI Yearbook Ch.7 | 2 | ✅ |
| 2 | **International peace** | UCDP + SIPRI milex | 2 | ✅ |
| 3 | **Domestic violence / repression** | PTS + UCDP one-sided + V-Dem repression | 3 | ✅ |
| 4 | **Political freedom** | V-Dem + Polity V + RSF press freedom (+ Freedom House user-managed if fetched) | 3-4 | ✅ |
| 5 | **Economic well-being** | WDI + PWT (+ IMF WEO user-managed if fetched) | 2-3 | ✅ |
| 6 | **Social well-being** | UNDP HDI + WDI subset + WHO GHO API | 3 | ✅ |
| 7 | **Integrity / corruption** | TI CPI + WGI Control of Corruption + V-Dem corruption | 3 | ✅ |
| 8 | **Effectiveness / governance** | WGI + V-Dem governance + BTI | 3 | ✅ |

**All 8 categories now have at least 2 distinct sources.** The user's "≥ 2 per category" requirement is met.

## 3. Per-source verdict (26 external source entries)

Verdicts are derived from the 10-check Phase B probe checklist in [`docs/source-vetting-plan.md`](source-vetting-plan.md).

### 3.1 Leader identity (REQ-SRC-001)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `archigos` | ⚠️ `vetted_with_caveats` | 1875–2015 | Free, Stata 14, cite Goemans/Gleditsch/Chiozza 2009. **8-year gap** to 2023. |
| `leader_survival` | ⚠️ `vetted_with_caveats` | 1789–2022 | Free, Demscore H-DATA v5 (March 2025). **1-year gap** to 2023. |
| `reign` | ⚠️ `vetted_with_caveats` | 1950–2021-08 | GitHub-hosted snapshot, monthly updates ceased Aug 2021. Historical only. |
| `wikidata_heads_of_state_government` | ✅ `vetted_ok` | daily-updated | CC0 1.0. SPARQL endpoint verified. **Primary 2023 source.** |
| `wikipedia_search_extract` | ✅ `vetted_ok` | all years | CC BY-SA 4.0. Action API verified. Narrative context. |
| `cia_world_leaders` | ❌ `blocked` | retired | CIA World Factbook retired in 2025. Gap covered by Wikidata. |

### 3.2 Political freedom (REQ-SRC-002)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `vdem` | ✅ `vetted_ok` | 1789–2025 | **v16 on disk.** 28,093 rows × 202 countries. DOI 10.23696/vdemds26. |
| `polity_v` | ✅ `vetted_ok` | 1800–2018 | Direct SPSS file from inscrdata.html. **2nd source for political freedom.** |
| `rsf_press_freedom` | ✅ `vetted_ok` | 2002–2026 (2011 direct CSV missing) | Annual CSVs acquired at `data/raw/rsf_press_freedom/`. Use as a press/media-freedom sub-signal. Methodology changes around 2022; pre/post-2022 scores require explicit normalization. |
| `freedom_house` | ⚠️ `user-managed` | 1972–2024 | Data gated behind email request. User sent the request; if placed in `data/raw/freedom_house/`, the Stage 2 ingest can use it. Otherwise V-Dem + Polity V + RSF provide political-freedom cross-validation. |

### 3.3 Economic (REQ-SRC-003)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `world_bank_wdi` | ✅ `vetted_ok` | 1960–2023+ | Free API, 2023 data confirmed. |
| `pwt` | ✅ `vetted_ok` | 183 economies, 1950–2019 | Penn World Table 10.01, 6.5MB xlsx. **PPP-based — different methodology from WDI's market-rate.** |
| `imf_weo` | ❌ `blocked` | annual | Akamai bot challenge (403). User can fetch manually if WEO specifically required; PWT is the 2nd source. |

### 3.4 Social well-being (NEW — added in B.2)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `undp_hdi` | ✅ `vetted_ok` | 1990–2022 | HDR 2023-24, 207 countries, 1.9MB CSV. **The canonical social well-being composite.** |
| `world_bank_wdi_social` | ✅ `vetted_ok` | health / education / inequality indicators | Subset of WDI. |
| `who_gho_api` | ✅ `vetted_ok` | ongoing | WHO Global Health Observatory OData API; ~2000 indicators. |

### 3.5 Governance / effectiveness (REQ-SRC-004)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `world_bank_wgi` | ✅ `vetted_ok` | 1996–2023 | xlsx + API. Sample downloaded. |
| `vdem_governance` | ✅ `vetted_ok` | 1789–2025 | Subset of V-Dem (already on disk). |
| `bti` | ✅ `vetted_ok` | 2006–2026 (biennial) | Cumulative xlsx on disk at `data/raw/bti/`. 12 editions × 137–159 countries × 123 columns. For 2023, use the `BTI 2024` sheet (covers 2022–2023). |

### 3.6 Corruption / integrity (REQ-SRC-005)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `transparency_cpi` | ⚠️ `vetted_with_caveats` | 1995–2023 | Stage 2 adapter implemented 2026-06-19. Direct xlsx CDN-gated; Stage 2 downloads the canonical CSV from the OCHA HDX mirror (`data.humdata.org`). The publisher remains Transparency International; HDX is the durable mirror. 180 countries for the 2023 release with score / rank / sources / standardError / lowerCi / upperCi / region extracted. |
| `world_bank_wgi_corruption` | ✅ `vetted_ok` | 1996–2023 | Subset of WGI. |
| `vdem_corruption` | ✅ `vetted_ok` | 1789–2025 | Subset of V-Dem. |

### 3.7 Conflict / international aggression (REQ-SRC-006)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `ucdp` | ✅ `vetted_ok` | 1946–2023+ | Free 26MB zip, 2023 data confirmed. |
| `sipri_milex` | ✅ `vetted_ok` | 1949–2025 | SIPRI-Milex-data-1949-2025_v1.2.xlsx. |
| `cow_mid` | ❌ `blocked` | 1816–2014 | Data ends 2014; site SSL issues. |

### 3.8 Domestic repression / violence (REQ-SRC-007)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `pts` (folder `political_terror_scale`) | ✅ `vetted_ok` | 1976–2025 | Direct file `/Data/Files/PTS-2025.xlsx`. |
| `cirights` | ⚠️ `vetted_with_caveats` (user-managed) | 1981–2022 | DNS-unreachable from this sandbox; v3.12.10.24 (Dec 2024) placed manually at `data/raw/cirights/`. 207 countries. **1-year gap to 2023** — use 2022 as proxy. |
| UCDP one-sided (subset of `ucdp`) | ✅ `vetted_ok` | 1989–2023 | Subset of UCDP. |
| V-Dem repression (subset of `vdem`) | ✅ `vetted_ok` | 1789–2025 | Subset of V-Dem. |

### 3.9 Nuclear / global responsibility (REQ-SRC-008)

| Source | Verdict | Coverage | Why |
|---|---|---|---|
| `fas` | ⚠️ `vetted_with_caveats` | ongoing | Stage 2 adapter implemented 2026-06-19. The consolidated "Status of World Nuclear Forces" page (`programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html`) returns a single parseable HTML `<table id="table1">` with all 9 nuclear-armed states + 5 numeric columns (Operational Strategic, Operational Nonstrategic, Reserve/Nondeployed, Military Stockpile, Total Inventory). The page's `<meta name="date">` element is 2014-04-30 as of probe (2026-06-19) — the snapshot year is recorded in the run manifest and Stage 11 confidence penalises the temporal-fit gap to 2023. Per-country guides (nuke.fas.org/guide/<country>/) are landing pages with little structured data; the consolidated snapshot is the canonical FAS-Nuclear-Notebook summary cited by SIPRI Yearbook Ch.7. |
| `sipri_yearbook_ch7` | ✅ `vetted_ok` | annual | SIPRI Yearbook Ch.7: World Nuclear Forces (PDF), 717KB. **Cross-checks FAS for nuclear arsenal facts.** |
| `nti` | ❌ `blocked` | ongoing | Cloudflare 403 even with browser UA. |

## 4. Summary by verdict

| Verdict | Count | Sources |
|---|---|---|
| ✅ `vetted_ok` | 15 | `vdem`, `rsf_press_freedom`, `world_bank_wdi`, `pwt`, `undp_hdi`, `who_gho_api`, `world_bank_wgi`, `ucdp`, `sipri_milex`, `sipri_yearbook_ch7`, `pts`, `polity_v`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`, `bti` |
| ⚠️ `vetted_with_caveats` / user-managed | 7 | `archigos`, `reign`, `leader_survival`, `transparency_cpi` (adapter landed 2026-06-19, HDX mirror pattern), `fas` (adapter landed 2026-06-19, HTML scrape of consolidated status page), `cirights` (user-managed), `freedom_house` (email request sent) |
| ❌ `blocked` | 4 | `cow_mid`, `cia_world_leaders`, `nti`, `imf_weo` |
| ⏸️ `deferred` | 0 | (none) |

## 5. Replacements for blocked / user-managed sources

| Blocked | Replacement | Rationale |
|---|---|---|
| `freedom_house` | `polity_v` + `rsf_press_freedom` while awaiting user-managed FIW data | Polity V is free and covers 1800–2018; RSF covers annual press freedom through 2026. If the user provides FIW data, it becomes an additional political-freedom source rather than silently replacing the others. |
| `cow_mid` | `ucdp` | UCDP GED 23.1 has 2023 data and covers the same international-conflict signal. |
| `cirights` | (no replacement needed) | Data placed manually by user on 2026-06-17. PTS + UCDP one-sided + V-Dem repression remain as the cross-validation set. |
| `cia_world_leaders` | `wikidata_heads_of_state_government` | Wikidata's "currently in office" query is daily-updated and provides the same backstop. |
| `nti` | `sipri_yearbook_ch7` | SIPRI Yearbook Ch.7 (World Nuclear Forces) provides the 2nd source for nuclear arsenal facts. |
| `imf_weo` | `pwt` | PWT (Penn World Table) uses PPP adjustments — different methodology from WDI's market-rate metrics, making it a useful cross-validation. |

## 6. Caveats the Stage 2 ingest must handle

| Source | Caveat to handle |
|---|---|
| `archigos` | Stata 14 `.dta`; may need `pyreadstat`. Coverage stops 2015. |
| `reign` | Use `raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv`; the older `cdn.rawgit.com` URLs are deprecated. |
| `leader_survival` | H-DATA v5 (March 2025). Use the CSV format for portability. |
| `vdem` | **Already on disk.** 388MB CSV. Narrow indicator list per the indicator catalog; the Stage 2 ingest must not load all 531 columns into memory unnecessarily. |
| `polity_v` | SPSS `.sav`; needs `pyreadstat`. Coverage stops 2018. |
| `rsf_press_freedom` | Semicolon-delimited annual CSVs with comma decimal separator. Direct `2011.csv` is absent (combined 2011/2012 edition represented by 2012). 2022+ schema/methodology differs from 2002–2021; normalize pre/post-2022 explicitly. The 2022 CSV has blank separator rows. Encodings observed: `utf-8-sig`, `cp1252`. |
| `world_bank_wdi` | ISO2 → ISO3 mapping; pagination for >100 countries. |
| `pwt` | URL pattern includes version number (e.g., `pwt100.xlsx` for 10.01). Stage 2 must discover the latest version. |
| `world_bank_wgi` | Use the `wgidataset.xlsx` file; the standard WGI API endpoint is `sources/3`, not `/v2/indicators`. |
| `undp_hdi` | Direct CSV at `https://hdr.undp.org/sites/default/files/2023-24_HDR/HDR23-24_Composite_indices_complete_time_series.csv`. 207 rows × wide format. |
| `who_gho_api` | OData at `https://ghoapi.azureedge.net/api/`. Filter by indicator code (e.g., `WHOSIS_000001` for life expectancy). |
| `ucdp` | UCDP uses GW (Gleditsch-Ward) country codes — needs a mapping table to ISO3. |
| `transparency_cpi` | **HDX mirror download**, not xlsx (CDN-gated). Stage 2 adapter downloads the canonical per-year CSV from `data.humdata.org/dataset/<uuid>/resource/<ruuid>/download/global_cpi_<year>.csv` and parses 180 country rows with score / rank / sources / standardError / lowerCi / upperCi / region. |
| `sipri_milex` | Discover the latest version at runtime; do not hard-code `v1.2`. |
| `sipri_yearbook_ch7` | PDF text extraction needed. Chapter-specific URL: `https://www.sipri.org/sites/default/files/YB24%2007%20WNF.pdf` (verify each year). |
| `pts` | Invert 1–5 scale (5 = most terror → 0 score; 1 = least terror → 10 score). |
| `cirights` | User-managed. File placed at `data/raw/cirights/`. Coverage stops 2022 (1-year gap to 2023). Some "Laws" columns and Human Trafficking have shorter coverage (1994+, 1998+). For 2023, use 2022 as proxy and let the temporal-fit component of the confidence formula reflect the gap. |
| `bti` | Multi-sheet xlsx with one sheet per BTI edition (2006–2026, biennial, 12 sheets). For 2023, use the `BTI 2024` sheet (covers 2022–2023). First column on each sheet is a multi-line "Regions:" label that must be skipped; data starts at row 2. ISO3 conversion required (BTI uses country names). |
| `fas` | Single HTML `<table id="table1">` on the consolidated status page (`programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html`) with all 9 nuclear-armed states. Page snapshot dated 2014-04-30 per `<meta name="date">` (as of probe 2026-06-19); the snapshot year is recorded in the run manifest and Stage 11 confidence penalises the temporal-fit gap to 2023. Per-country pages mostly serve as table-of-contents. |
| `wikidata_heads_of_state_government` | SPARQL query with `?headOfState p:P39 ?statement` pattern; translate Q-IDs to ISO3 via `wbgetentities`. |
| `wikipedia_search_extract` | Use a descriptive User-Agent; respect the API's pagination; disambiguate by pageid. |
| `client_existing` | Validation/reference artifact only. Never overwrite `client_score`; never count the client matrix as an independent source for evidence, scoring, source agreement, or source authority. |

## 7. Phase C unblock conditions

Phase C (data acquisition) may begin once the following conditions are met:

- [x] Every priority source has a row in this report with a verdict.
- [x] Every rating category has at least 2 distinct datasets.
- [x] Every `vetted_ok` / `vetted_with_caveats` source has a canonical URL in `docs/data-sources.md`.
- [x] Every `blocked` source has a documented blocker in `docs/data-sources.md`.
- [x] Every `metadata.json` placeholder is updated with the verified `source_url`.
- [x] The V-Dem v16 file is on disk with SHA-256 captured.
- [x] Every per-source attribution block is captured in `docs/source-attributions.md` with citation text and license.
- [x] **User sign-off on this report** — signed off 2026-06-17; later addenda remain living updates.

## 8. Phase C implications

When Phase C begins, the following Stage 2 ingest modules can be implemented immediately:

- **High priority (vetted_ok, on disk or trivial download):**
  - `vdem` (already on disk; Phase C.1)
  - `world_bank_wdi` (API; Phase C.2)
  - `world_bank_wgi` (xlsx + API; Phase C.3)
  - `pwt` (xlsx) — **adapter blocked on raw bundle** (see workplan Done History)
  - `ucdp` (zip; Phase C.4)
  - `sipri_milex` (xlsx; Phase C.5)
  - `sipri_yearbook_ch7` (PDF; Phase C.6)
  - `pts` (xlsx; Phase C.7)
  - `undp_hdi` (CSV; Phase C.8)
  - `who_gho_api` (OData; Phase C.9)
  - `polity_v` (SPSS) — **adapter blocked on raw file** (see workplan Done History)
  - `bti` (cumulative xlsx already on disk; multi-sheet, 12 biennial editions; **adapter landed 2026-06-19, see `src/leaders_db/ingest/bti*.py`**)
  - `rsf_press_freedom` (annual CSVs already on disk; press/media-freedom sub-signal; **adapter landed 2026-06-19, see `src/leaders_db/ingest/rsf_press_freedom*.py`**)
- **Medium priority (vetted_with_caveats, need careful adapter):**
  - `archigos` (Stata; **adapter landed 2026-06-19, see `src/leaders_db/ingest/archigos*.py`**)
  - `reign` (large CSV, GitHub raw; **adapter landed 2026-06-19, see `src/leaders_db/ingest/reign*.py`**)
  - `leader_survival` (Demscore download) — **adapter blocked on Demscore email gate** (see workplan Done History)
  - `transparency_cpi` (HTML scrape — **adapter landed 2026-06-19 via HDX mirror**; see `src/leaders_db/ingest/transparency_cpi*.py`)
  - `fas` (HTML whitelist scrape — **adapter landed 2026-06-19 via consolidated status page**; see `src/leaders_db/ingest/fas*.py`)
  - `cirights` (user-managed; v3.12.10.24 xlsx on disk, 1-year gap to 2023; **adapter landed 2026-06-19, see `src/leaders_db/ingest/cirights*.py`**)
- **Always-on helpers (not per-source adapters):**
  - `wikidata_heads_of_state_government` (SPARQL; **adapter landed 2026-06-19, see `src/leaders_db/ingest/wikidata_heads_of_state_government*.py`**)
  - `wikipedia_search_extract` (Action API; **adapter landed 2026-06-19, see `src/leaders_db/ingest/wikipedia_search_extract*.py`**)
- **User-managed (optional, pending user/provider response):**
  - `freedom_house` (email request sent)
- **Blocked (do not implement):**
  - `cow_mid`, `cia_world_leaders`, `nti`, `imf_weo` (unless user fetches WEO manually)
- **Deferred (when site recovers):**
  - (none)

The Phase C.10 integration pass (2026-06-19) wired all 9 newly implemented orchestrators into the central `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py`. As of that pass, 18 of 26 source keys resolve to a real orchestrator; the remaining 3 (`polity_v`, `pwt`, `leader_survival`) are blocked on raw file placement, and 5 are user-managed/blocked/retired. The single source-of-truth principle is preserved: every CLI `--source <key>` argument resolves through the dispatch table, and removing the orchestrator entry causes the CLI to print the standard "not implemented yet" message.

## 9. Evidence files

Saved under `tmp/source-vetting-evidence/` for audit:

- `undp-hdi-2023-24.csv` — 1.9MB UNDP HDI time series
- `pwt100.xlsx` — 6.5MB Penn World Table
- `sipri-milex-1949-2025.xlsx` — 922KB SIPRI military expenditure
- `sipri-yearbook-2024-page.html` — 60KB SIPRI Yearbook index page
- `pts-data-page.html`, `pts-download-page.html` — PTS data
- `polity-inscrdata-page.html` — Polity V data page
- `wdi-population-2023-sample.json` — WDI sample (5 records for 2023)
- `wgi-dataset-2023.xlsx` — 2.1MB WGI dataset
- `v-dem-country-year-v16-page.html` — 30KB V-Dem landing page
- `reign-github-repo-listing.json` — REIGN repo listing
- `bti-reports-page.html` — BTI page (500 error captured)
- `data/raw/rsf_press_freedom/metadata.json` — durable RSF acquisition record with checksums for 24 annual CSVs

These are gitignored working files; they are evidence that the probes happened, not load-bearing artifacts.

## 10. Sign-off

The user signed off on Phase B on 2026-06-17 and the workplan moved the active-phase indicator from **B** to **C**. This report now acts as a living source record; addenda such as CIRIGHTS, BTI, and RSF are reflected here and in [`docs/workplan.md`](workplan.md)'s Done History.

If anything in this report is wrong (a wrong verdict, a missing source, a wrong replacement, a category under-served), fix it inline in `source-vetting-worksheet.md` and `source-attributions.md` before signing off — do not sign off and then patch.

## 11. The 8 rating categories — definitions and required sources

Per requirement §4, the prototype scores each ruler-year on these 8 categories. The acceptance criteria in §16 require provisional scores for at least four of them; the prototype will score all 8.

| # | Category | Rubric anchor (Stage 5 indicators) | Why ≥ 2 sources matter |
|---|---|---|---|
| 1 | Nuclear responsibility / global existential | FAS arsenal count + SIPRI arsenal count + (manual review) | Avoid one-source bias on a politically charged score. |
| 2 | International peace vs aggression | UCDP state-based conflict + SIPRI military expenditure share | Different methodologies (event-based vs expenditure-based). |
| 3 | Domestic safety vs violence | PTS + UCDP one-sided + V-Dem physical integrity | Three sources catch both state terror and conflict violence. |
| 4 | Political freedom vs authoritarian | V-Dem (531 indicators) + Polity V (1800–2018) + RSF press freedom + FH (user-managed) | V-Dem + Polity capture regime structure; RSF adds a current media-freedom sub-signal; FH is added if/when the user-managed file arrives. |
| 5 | Economic well-being | WDI (market rate) + PWT (PPP) | Different PPP/market-rate methodologies. |
| 6 | Social well-being | UNDP HDI (composite) + WDI (raw indicators) + WHO GHO (health) | Composite + raw + specialized. |
| 7 | Integrity / corruption | TI CPI (perception) + WGI (aggregate) + V-Dem (expert-coded) | Three independent methodologies. |
| 8 | Effectiveness / governance | WGI (6 indicators) + V-Dem (governance subset) + BTI | Three distinct governance methodologies. |
