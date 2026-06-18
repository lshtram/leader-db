# Source Vetting Worksheet — Phase B (in-progress)

This is the working document for Phase B. It records per-source findings
as the agent researches each priority source. The final report at
`docs/source-vetting-report.md` is a clean summary of this worksheet.

Conventions:

- **Status:** `pending` → `probed` → `decided`.
- **Verdict:** one of `vetted_ok` / `vetted_with_caveats` / `blocked` / `replace`.
- The worksheet is **append-only**. New findings go below; nothing is
  deleted. Once a source is `decided`, its entry stays as the audit trail.

## Source Status Overview

Updated 2026-06-18, after CIRIGHTS, BTI, and RSF addenda. **All categories now have at least 2 sources** (some have 3+).

| Source | Status | Verdict | Researcher | Notes |
|---|---|---|---|---|
| archigos | **decided** | `vetted_with_caveats` | inline | 1875–2015 only; 8-year gap. |
| vdem | **decided** | `vetted_ok` | inline | v16 (March 2026) on disk, 28,093 rows × 202 countries. |
| world_bank_wdi | **decided** | `vetted_ok` | inline | API works for 2023. |
| leader_survival | **decided** | `vetted_with_caveats` | inline | 1789–2022, 1-year gap. |
| reign | **decided** | `vetted_with_caveats` | inline | Last release 2021-08. |
| world_bank_wgi | **decided** | `vetted_ok` | inline | xlsx + API both work. |
| transparency_cpi | **decided** | `vetted_with_caveats` | inline | Site OK; direct file gated by CDN. |
| freedom_house | **user-managed** | `vetted_with_caveats` | inline | Data behind email request. User sent email; place file if provider responds. |
| ucdp | **decided** | `vetted_ok` | inline | 26MB zip, last modified 2023-06. |
| cow_mid | **decided** | `blocked` | inline | 404 + SSL + data ends 2014. |
| sipri_milex | **decided** | `vetted_ok` | inline | SIPRI-Milex-data-1949-2025_v1.2.xlsx, 922KB. |
| sipri_yearbook_ch7 | **decided** | `vetted_ok` *(new)* | inline | World Nuclear Forces PDF, 717KB; covers nuclear arsenal data. |
| pts | **decided** | `vetted_ok` | inline | PTS-2025.csv at /Data/Files/. |
| cirights | **decided** | `vetted_with_caveats` | inline | DNS unreachable from sandbox, but user placed v3.12.10.24 files at `data/raw/cirights/`. |
| fas | **decided** | `vetted_with_caveats` | inline | HTML scrape with whitelist. |
| nti | **decided** | `blocked` | inline | Cloudflare 403. |
| wikidata_heads_of_state_government | **decided** | `vetted_ok` | inline | SPARQL endpoint. |
| wikipedia_search_extract | **decided** | `vetted_ok` | inline | Action API. |
| cia_world_leaders | **decided** | `blocked` | inline | Factbook retired 2025. |
| **undp_hdi** | **decided** | `vetted_ok` *(new)* | inline | HDI 2023-24 CSV, 1.9MB, 207 countries. The canonical social well-being source. |
| **polity_v** | **decided** | `vetted_ok` *(new)* | inline | Direct SPSS file from inscrdata.html. Polity V, 1800-2018. Fallback to Freedom House for political freedom. |
| **pwt** | **decided** | `vetted_ok` *(new)* | inline | Penn World Table 10.01 xlsx, 6.5MB. 2nd economic source. |
| **who_gho_api** | **decided** | `vetted_ok` *(new)* | inline | WHO Global Health Observatory OData API. Has life expectancy, immunizations, child mortality, NCDs, etc. 3rd social well-being source. |
| **bti** | **decided** | `vetted_ok` | inline | User placed cumulative BTI 2006–2026 scores xlsx; codebook acquired. |
| **imf_weo** | **decided** | `blocked` *(new)* | inline | Akamai bot-challenge 403 on all endpoints. User can fetch manually if needed; PWT is the alternative economic source. |
| **rsf_press_freedom** | **decided** | `vetted_ok` | inline | 24 annual CSVs acquired: 2002–2010 and 2012–2026; direct 2011 CSV missing. |

---

## Source: archigos

### Probe

- **Canonical URL:** https://www.rochester.edu/college/faculty/hgoemans/data.htm (data page; the actual Stata file is linked from here)
- **Direct download URL (Stata 14):** https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta
- **Probed:** 2026-06-17, via `curl -sIL` and `webfetch`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the data page is reachable (200 OK). The candidate direct URL `https://www.rochester.edu/college/faculty/hgoemans/Archigos-4.1-updated.zip` returns 404 — that filename is not what the page links. The actual download is a Stata `.dta` file, not a zip.
- **License:** free academic; cite Goemans, Gleditsch, and Chiozza 2009 ("Introducing Archigos: A Dataset of Political Leaders," *Journal of Peace Research* 46(2): 269–183).
- **Coverage:** **1875 through 31 December 2015** (per the data page: "Version 4.1, updated until 31 December 2015 is available").
- **Format:** Stata 14 (`.dta`).
- **Country set:** ~201 countries (the Archigos page says "more than 3,000 leaders 1875–2004" but version 4.1 is broader; needs Stage 2 verification).
- **Gotchas:** No version newer than 4.1 exists. The CHISOLS v5.0 extension (Leeds et al.) uses Archigos 4.1 and only extends to 2018. **Archigos does not cover 2023.**
- **Caveat for the prototype:** Archigos is a useful historical backstop (1875–2015) but cannot validate 2023 leaders. For 2023, the client bundle is the only structured source until Wikidata/CIA is added.
- **Replacement candidate (for 2023):** Leader Survival (PLT post-1789, 1789–2022, 1-year gap is the closest available) or a Wikidata WikiProject Heads of state and government extraction.

---

## Source: vdem

### Probe

- **Canonical URL:** https://v-dem.net/data/the-v-dem-dataset/
- **Version 16 download page:** https://v-dem.net/data/the-v-dem-dataset/country-year-v-dem-fullothers-v16/ (full dataset)
- **Probed:** 2026-06-17, via `curl -sIL` and `webfetch`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the data page is reachable (200 OK). The actual download requires a free user account — the page has a "Sign In" button. There is no paywall, but there is a registration gate.
- **License:** free academic; cite V-Dem Institute. Latest version is **v16 (March 2026)**.
- **Coverage:** 1789–2023 (per the V-Dem dataset description; Country-Year Full+Others includes 531 indicators across 200+ countries).
- **Format:** STATA, CSV, R, SPSS. CSV is the most portable choice.
- **Country set:** ~200 countries (per the V-Dem documentation).
- **Gotchas:** The download is gated by a free V-Dem account. The prototype will need V-Dem credentials in `.env` (e.g. `LEADERSDB_VDEM_EMAIL` and `LEADERSDB_VDEM_PASSWORD`). The dataset is large (~30k country-year rows × 531 indicators). For a prototype, **Country-Year Core** (5 high-level indices + 93 sub-indices + 179 indicators) is a more focused alternative.
- **Caveat for the prototype:** A one-time free registration is required; the prototype will need to handle login + session cookies for downloads. The Stage 2 adapter will use Playwright/curl-with-cookies.

### Evidence file

- `tmp/source-vetting-evidence/v-dem-country-year-v16-page.html` (30KB) — captured response.

---

## Source: world_bank_wdi

### Probe

- **Canonical URL:** https://api.worldbank.org/v2/
- **Probed:** 2026-06-17, via `curl -sL` and JSON parse.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

### Findings

- **Reachability:** the API is reachable. No authentication required.
- **License:** World Bank Open Data license; free for any use with attribution.
- **Coverage:** 1960–current (varies by indicator). 2023 data confirmed for `SP.POP.TOTL` (population, total) — see evidence file.
- **Format:** JSON (default), XML on request.
- **Country code:** ISO2 — must be lifted to ISO3 for our schema.
- **Pagination:** `per_page=100` and `page=N` parameters; the prototype should page through results.
- **Sample evidence:**
  ```
  GET https://api.worldbank.org/v2/country/MEX;USA;CHN;IND;DEU/indicator/SP.POP.TOTL?date=2023&format=json&per_page=100
  → returns 5 records, each with countryiso3code, date, value, unit.
  ```

### Evidence file

- `tmp/source-vetting-evidence/wdi-population-2023-sample.json` — 5 records for 2023.

---

## Source: leader_survival

### Probe

- **Canonical URL (Stockholm U / Demscore H-DATA page):** https://www.su.se/english/research/research-catalogue/research-projects/6/h-data--/datasets
- **Direct download page:** https://www.demscore.se/data/static-datasets/h-data-static-datasets/ (H-DATA v5, March 2025)
- **Probed:** 2026-06-17, via `webfetch`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the Stockholm University datasets page is reachable; the Demscore page is reachable.
- **License:** free academic; cite Gerring et al. 2024 (and the H-DATA v5 release notes).
- **Coverage:** **1789–2022** (per the H-DATA page: "10,662 leader spells in 186 countries (or territories) from 1789-2022").
- **Format:** STATA (`.dta`, 12MB), CSV (2MB), R, codebook PDF. STATA + CSV are the practical choices.
- **Country set:** 186 countries/territories.
- **Last update:** 2025-02-25 (H-DATA v5, March 2025).
- **Gotchas:** The PLT (Political Leaders through Time) dataset family has several sub-products; the post-1789 part is what we need. **Coverage ends 2022, not 2023** — a 1-year gap.
- **Caveat for the prototype:** The best leader source we have for global coverage, but still misses 2023. For 2023 specifically, we either:
  1. Use the client bundle (which is the 2023 reference anyway).
  2. Add a Wikidata-based extraction for the 2023 rows only (WikiProject Heads of state and government; daily-updated).
  3. Use CIA World Leaders for current leaders.
- **Decision pending user sign-off** (see "Cross-Cutting Decisions" below).

---

## Source: reign

### Probe

- **Canonical URL:** https://oefdatascience.github.io/REIGN.github.io/
- **GitHub data:** https://github.com/OEFDataScience/REIGN.github.io (gh-pages branch, `data_sets/`)
- **Probed:** 2026-06-17, via `curl -sIL`, GitHub API listing, and `webfetch`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the GitHub repository is reachable. The data files are served via `https://raw.githubusercontent.com/OEFDataScience/REIGN.github.io/gh-pages/data_sets/...`.
- **License:** free academic; cite Bell 2016 (OEF Research) and the REIGN codebook.
- **Coverage:** **1950–2021-08** (per the OEF website: "August 2021 marked the last scheduled monthly update of the REIGN database and the CoupCast project. ... data collection for REIGN and ongoing coup risk estimation for Coupcast has been ceased.").
- **Format:** CSV. Last data file is `REIGN_2021_8.csv` (34MB) on GitHub.
- **Country set:** 201+ countries, 2,300+ leaders.
- **Gotchas:** The GitHub data is a **static snapshot**; no further monthly updates. The deprecation of the older `cdn.rawgit.com` URLs means new code must use `raw.githubusercontent.com`.
- **Caveat for the prototype:** REIGN covers 1950–2021, not 2023. Like Archigos and Leader Survival, it's a historical backstop, not a 2023 source.
- **Best use:** historical validation of the resolver for any year 1950–2021.

---

## Source: world_bank_wgi

### Probe

- **Canonical URL:** https://info.worldbank.org/governance/wgi/
- **Direct dataset URL (xlsx):** https://www.worldbank.org/content/dam/sites/govindicators/doc/wgidataset.xlsx
- **API endpoint:** https://api.worldbank.org/v2/sources/3/indicators?format=json
- **Probed:** 2026-06-17, via `curl -sL` and `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

### Findings

- **Reachability:** the xlsx file is reachable (2.1MB, last modified 2023-11-14). The API is reachable.
- **License:** World Bank Open Data license; free for any use with attribution.
- **Coverage:** 1996–2023 (six aggregate governance indicators: Voice and Accountability, Political Stability, Government Effectiveness, Regulatory Quality, Rule of Law, Control of Corruption). The WGI explicitly does not provide point-in-time-precise data; values are normalized.
- **Format:** xlsx (the WGI dataset file) and JSON (the World Bank Indicators API). The xlsx is the official WGI release; the API indicator `CC.EST` returns 404 — the right API source is `sources/3` for WGI, not the regular `/v2/` indicators.
- **Country set:** ~200 countries.
- **Gotchas:** WGI values are point estimates with wide uncertainty bands; the prototype should record both the estimate and the standard error.
- **Sample evidence:** downloaded `wgidataset.xlsx` (2.1MB) — see `tmp/source-vetting-evidence/wgi-dataset-2023.xlsx`.

---

## Source: transparency_cpi

### Probe

- **Canonical URL:** https://www.transparency.org/en/cpi/2023
- **Direct file URL (after redirect):** https://files.transparencycdn.org/images/CPI2023-Results-and-trends.xlsx
- **Probed:** 2026-06-17, via `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the CPI 2023 page is reachable. The direct file URL returns 307 redirect to `files.transparencycdn.org`, which returns 403. **The CDN-gated URL is not directly downloadable**; the file is served behind some form of access control.
- **License:** free for non-commercial use with attribution; cite Transparency International.
- **Coverage:** 1995–2023 annual scores.
- **Format:** xlsx.
- **Country set:** ~180 countries.
- **Gotchas:** The CDN-gated download suggests we may need to register for an API key or scrape the report. Alternative: use the "CPI 2023 table of results" page HTML which is freely browsable.
- **Caveat for the prototype:** The Stage 2 adapter may need to use the page's HTML report rather than the xlsx file. Or it can request an API key from Transparency International.

---

## Source: freedom_house

### Probe

- **Canonical URL:** https://freedomhouse.org/report/freedom-world
- **Publication archives page:** https://freedomhouse.org/reports/publication-archives
- **Probed:** 2026-06-17, via `webfetch` and `curl -sIL`.
- **Status:** user-managed / pending response.
- **Verdict:** `vetted_with_caveats` (manual email gate).

### Findings

- **Reachability:** the website is reachable, the report pages are reachable, and the report PDFs are downloadable. However, **the underlying FIW data file is gated behind an email request**.
- **From the FIW archives page (verbatim):**
  > "Interested in downloading *Freedom in the World* report data? Please email research@freedomhouse.org with 'FIW Data Request' in the subject line and our team will assist you."
- **License:** The data is free for non-commercial use, but requires an email request. This is a manual gate that does not fit a programmatic Phase 2 ingest.
- **Coverage:** 1972–current.
- **Format:** xlsx (data); PDF (narrative reports).
- **Decision:** not programmatically available, but no longer treated as a hard replacement problem because the user sent the FIW request email. If the data arrives, place it under `data/raw/freedom_house/`; otherwise V-Dem + Polity V + RSF cover political-freedom cross-validation for the current prototype.

---

## Source: rsf_press_freedom

### Probe

- **Canonical URL:** https://rsf.org/en/index
- **Direct annual CSV pattern:** `https://rsf.org/sites/default/files/import_classement/{year}.csv`
- **Probed:** 2026-06-18, via direct HTTP download and metadata parse.
- **Status:** decided; raw files acquired.
- **Verdict:** `vetted_ok`.

### Findings

- **Reachability:** direct annual CSVs are reachable for 2002–2010 and 2012–2026. The direct `2011.csv` URL returns 404; RSF public pages refer to a combined 2011/2012 edition, represented by the 2012 file.
- **License / terms:** free public dataset; cite Reporters Without Borders / Reporters sans frontières.
- **Coverage:** 24 annual files, 139–180 non-empty country/territory rows depending on year. Current coverage reaches 2026.
- **Format:** semicolon-delimited CSV. Decimal separator is comma. Encodings observed: `utf-8-sig` and `cp1252`. The 2022 CSV includes blank separator lines.
- **Methodology:** 2022+ uses a richer schema and different methodology, including component scores/ranks for political, economic, legal, social/sociocultural, and safety/security context. Pre-2022 and 2022+ scores must not be merged without explicit normalization.
- **Local files:** `data/raw/rsf_press_freedom/` with 24 CSV files and `metadata.json` containing SHA-256 checksums, headers, row counts, and methodology caveats.
- **Decision:** add as a political-freedom source. Use it as a press/media-freedom sub-signal, not as a replacement for V-Dem, Polity V, or Freedom House.

---

## Source: ucdp

### Probe

- **Canonical URL:** https://ucdp.uu.se/downloads/
- **Direct dataset URL (UCDP GED 23.1, June 2023):** https://ucdp.uu.se/downloads/ged/ged231-csv.zip
- **Probed:** 2026-06-17, via `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

### Findings

- **Reachability:** the UCDP downloads page is reachable. The candidate `ged231-csv.zip` is 26MB, last modified 2023-06-06. Note: this is the 23.1 version; later versions may exist; Stage 2 should look for the latest at runtime.
- **License:** free academic; cite UCDP.
- **Coverage:** 1946–2023 (UCDP GED covers state-based, non-state, and one-sided violence).
- **Format:** CSV (in a zip).
- **Country set:** global; multiple sub-datasets (state-based conflict, non-state, one-sided violence).
- **Country code:** UCDP uses its own GW (Gleditsch-Ward) codes; the Stage 2 adapter must map these to ISO3.
- **Decision:** primary source for international-conflict (REQ-SRC-006) and one-sided-violence (REQ-SRC-007) indicators.

---

## Source: cow_mid

### Probe

- **Canonical URL:** https://correlatesofwar.org/data-sets/MID
- **Direct dataset URL (v4.0 zip):** https://correlatesofwar.org/wp-content/uploads/MID-4.0.zip
- **Probed:** 2026-06-17, via `curl -sIL` and `curl -v`.
- **Status:** decided.
- **Verdict:** `blocked`.

### Findings

- **Reachability:** the COW homepage IP resolves (146.6.162.203), but TLS handshake fails with "SSL certificate problem: unable to get local issuer certificate" — our CA bundle doesn't trust the chain. (May work in a browser.) The MID download page itself returns 404, and the candidate `MID-4.0.zip` URL also returns 404.
- **License:** free academic; cite COW.
- **Coverage:** 1816–2014 (data ends 2014; 9 years short of 2023).
- **Decision:** `blocked` regardless of the SSL issue — even with the file, the data ends 2014. **Replace with UCDP** for international-conflict indicators (UCDP GED 23.1 has 2023 data).

---

## Source: sipri

### Probe

- **Canonical URL (milex landing):** https://www.sipri.org/databases/milex
- **Direct data file (milex, 1949–2025):** https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx
- **SIPRI Yearbook 2024 (nuclear chapter):** https://www.sipri.org/sites/default/files/YB24%2007%20WNF.pdf (Chapter 7, World Nuclear Forces)
- **Probed:** 2026-06-17, via `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_ok` for both milex and Yearbook nuclear chapter.

### Findings

- **Reachability:** the milex landing page is reachable. The direct data file URL is reachable (200, 922KB xlsx, last modified 2026-04-27). The Yearbook Chapter 7 PDF is reachable (200, 717KB, last modified 2024-06-14).
- **License:** free; cite SIPRI.
- **Coverage:** milex 1949–2025; Yearbook is annual.
- **Format:** milex = xlsx; Yearbook = PDF (text extraction needed for tabular data).
- **Country set:** global.
- **Gotchas:** the version number on milex changes (`v1.2` here). The Yearbook chapters are individual PDFs — Chapter 7 is the nuclear one. Stage 2 adapters must discover the latest version of each at runtime.

---

## Source: pts (political_terror_scale)

### Probe

- **Canonical URL:** https://www.politicalterrorscale.org/
- **Data page:** https://www.politicalterrorscale.org/Data/
- **Direct download page:** https://www.politicalterrorscale.org/Data/Download.html
- **Direct file URL (2025 release):** https://www.politicalterrorscale.org/Data/Files/PTS-2025.xlsx (also .csv, .dta)
- **Codebook:** https://www.politicalterrorscale.org/Data/Files/PTS-Codebook-V230.pdf
- **Probed:** 2026-06-17, via `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

### Findings

- **Reachability:** the home, Data, and Download pages are all reachable (200 OK, small files). Direct file URLs are simple static paths under `/Data/Files/`.
- **License:** free academic; cite Wood, Gibney, et al.
- **Coverage:** the latest release is PTS-2025; the dataset covers 1976–2023.
- **Format:** xlsx, csv, dta (all three formats available for the same release).
- **Country set:** global (~200 countries).
- **Gotchas:** the dataset uses a 1–5 scale where **higher = more terror**. The Stage 2 ingest must invert before scoring (the per-category scoring modules expect "high score = good").
- **Evidence files:** `tmp/source-vetting-evidence/pts-data-page.html`, `pts-download-page.html`.

---

## Source: cirights

### Probe

- **Canonical URL:** https://www.cirights.org/ (and `https://cirights.org/`)
- **Probed:** 2026-06-17, via `curl -v`.
- **Status:** decided.
- **Verdict:** `blocked`.

### Findings

- **Reachability:** **DNS-level unreachable.** Both `www.cirights.org` and `cirights.org` fail to resolve ("Could not resolve host").
- **License:** free academic; cite Cingranelli, Richards, and Clay.
- **Coverage:** 1981–2023 per the source-vetting plan, but **the domain is unreachable from this environment** as of 2026-06-17.
- **Decision:** `blocked` for the prototype. **Replace with PTS** (Political Terror Scale) for the domestic-violence indicator, supplemented by UCDP one-sided violence where available, and V-Dem's repression indicators.

---

## Source: fas

### Probe

- **Canonical URL:** https://fas.org/issues/nuclear-weapons/ (redirects to https://fas.org/publication/nuclear-weapons-2024/)
- **Status page (Status of World Nuclear Forces):** https://fas.org/initiative/status-world-nuclear-forces/
- **Probed:** 2026-06-17, via `curl -sIL`.
- **Status:** decided.
- **Verdict:** `vetted_with_caveats`.

### Findings

- **Reachability:** the status page is reachable (200 OK). The country pages redirect to publication pages (e.g., `https://fas.org/initiative/status-world-nuclear-forces/united-states/` → `https://fas.org/publication/united-states-discloses-nuclear-warhead-numbers-restores-nuclear-transparency/`).
- **License:** free; cite FAS.
- **Coverage:** ongoing. The Nuclear Notebook is published as a series of articles, one per nuclear-armed state.
- **Format:** HTML pages, one per country.
- **Country set:** the 9 nuclear-armed states (US, Russia, China, UK, France, India, Pakistan, North Korea, Israel). Plus ~6 "indirect" states with US/Russian weapons on their territory.
- **Gotchas:** the country pages are stable but the URL structure is `/initiative/status-world-nuclear-forces/<country>/` with a 301 to `/publication/<slug>/`. The Stage 2 adapter will use a curated whitelist of country slugs and follow the redirects.

---

## Source: nti

### Probe

- **Canonical URL:** https://www.nti.org/countries/
- **Probed:** 2026-06-17, via `curl -sIL` with browser-like User-Agent.
- **Status:** decided.
- **Verdict:** `blocked`.

### Findings

- **Reachability:** the URL returns **HTTP 403 (Cloudflare bot challenge)** even with a browser-like User-Agent. The server is reachable but Cloudflare's anti-bot protection blocks automated requests.
- **License:** free; cite NTI.
- **Coverage:** ongoing.
- **Country set:** global; country profiles for every nation.
- **Decision:** `blocked`. The nuclear arsenal coverage we wanted from NTI is also covered by FAS, so the gap is not blocking. If a future iteration needs NTI-specific content (e.g., nuclear materials, sites), the Stage 2 adapter will need a real browser (Playwright) to bypass the challenge.

---

## Cross-Cutting Decisions

_(Recorded as they come up. Examples: which replacement to use for `cow_mid`;
whether to use the V-Dem full dataset or V-Dem Lite; whether the World Bank
WGI download needs special handling for missing years.)_

### 2026-06-17 — User feedback: at least 2 sources per rating category

The user reviewed the report and pointed out that the per-source structure
hid a critical gap: several rating categories had only one distinct dataset.
The 8 rating categories per requirement §4 are:

1. **Nuclear** — was: FAS (1). **Fix:** add SIPRI Yearbook Chapter 7.
2. **International peace** — was: UCDP + SIPRI milex (2). **No change.**
3. **Domestic violence** — was: PTS + UCDP one-sided + V-Dem repression (3). **No change.**
4. **Political freedom** — was: V-Dem (1). **Fix:** add Polity V (fallback); Freedom House user-managed.
5. **Economic** — was: WDI (1). **Fix:** add Penn World Table (PWT) for PPP-based cross-validation.
6. **Social well-being** — was: WDI subset only (1, implicit). **Fix:** add UNDP HDI as the canonical composite; add WHO GHO API as a third source for health-specific indicators.
7. **Integrity / corruption** — was: TI CPI + WGI Control of Corruption + V-Dem corruption (3). **No change.**
8. **Effectiveness / governance** — was: WGI + V-Dem governance (2). **BTI later recovered** when the user placed the cumulative xlsx and the canonical downloads page was found.

### 2026-06-17 — Coverage matrix per rating category (after B.2 second wave)

| # | Category | Datasets | Count |
|---|---|---|---|
| 1 | Nuclear | FAS + SIPRI Yearbook Ch.7 | 2 ✅ |
| 2 | International peace | UCDP + SIPRI milex | 2 ✅ |
| 3 | Domestic violence | PTS + UCDP one-sided + V-Dem repression | 3 ✅ |
| 4 | Political freedom | V-Dem + Polity V + RSF press freedom (+ Freedom House if user provides) | 3-4 ✅ |
| 5 | Economic | WDI + PWT | 2 ✅ |
| 6 | Social well-being | WDI subset + UNDP HDI + WHO GHO API | 3 ✅ |
| 7 | Integrity / corruption | TI CPI + WGI Control of Corruption + V-Dem corruption | 3 ✅ |
| 8 | Effectiveness / governance | WGI + V-Dem governance + BTI | 3 ✅ |

All 8 categories now have at least 2 sources. Several have 3.

### 2026-06-17 — IMF WEO blocked; BTI initially deferred, later recovered

- **IMF WEO** is blocked by Akamai's bot challenge (403 on all endpoints tried). The PWT is a viable alternative for cross-validation (different methodology: PPP vs market exchange rate). If the user really wants WEO specifically, they can register at https://www.imf.org and download the WEO dataset manually (similar to the V-Dem local-file pattern).
- **BTI 2024** initially returned 500 errors on `/en/reports` and `/en/data`. This was later superseded: the canonical `/en/downloads` page is alive, BTI 2026 is released, and the user placed the cumulative `BTI_2006-2026_Scores.xlsx` under `data/raw/bti/`.

### 2026-06-17 — Wikidata nuclear arsenal approach

The naive SPARQL query (`P1830` = country of origin) returns wrong results. The Wikidata model for "has nuclear weapons" is complex and uses multiple properties. For the prototype, the simplest reliable approach is a **curated list** of the 9 nuclear-armed states, cross-checked against FAS:

- USA (Q30), Russia (Q159), China (Q148), UK (Q145), France (Q142), India (Q668), Pakistan (Q843), North Korea (Q423), Israel (Q801).

The Wikidata head-of-state query already returns data for these countries; the nuclear-arsenal facts come from FAS (and now also from SIPRI Yearbook Ch.7). The Stage 2 adapter will read the curated list from `data/raw/wikidata_heads_of_state_government/nuclear_states.json` (generated once and cached).

---

## New sources added in the second wave (B.2)

### `undp_hdi` — UNDP Human Development Index

- **Probe:** https://hdr.undp.org/data-center/human-development-index (page) and https://hdr.undp.org/sites/default/files/2023-24_HDR/HDR23-24_Composite_indices_complete_time_series.csv (direct file).
- **Probed:** 2026-06-17, via `curl -sIL` and a 1.9MB partial download.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

#### Findings

- **Reachability:** the data-center page is reachable (200). The direct CSV URL is reachable (200, 1.9MB, text/csv).
- **License:** free; cite UNDP.
- **Coverage:** 1990–2022 country-year.
- **Format:** CSV. Columns include `iso3`, `country`, `region`, `hdicode` (development tier), `hdi_YYYY`, `le_YYYY` (life expectancy at birth), `eys_YYYY` (expected years of schooling), `mys_YYYY` (mean years of schooling), `gnipc_YYYY` (GNI per capita), plus inequality and gender disaggregations (IHDI, GII, GDI).
- **Country set:** 207 countries.
- **Evidence file:** `tmp/source-vetting-evidence/undp-hdi-2023-24.csv` (1.9MB).

### `polity_v` — Polity V dataset

- **Probe:** https://www.systemicpeace.org/polityproject.html (page) and https://www.systemicpeace.org/inscr/p5v2018.sav (direct data file via inscrdata.html).
- **Probed:** 2026-06-17.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

#### Findings

- **Reachability:** the project page is reachable (200, 24KB). The `inscrdata.html` page lists several `.sav` files; `p5v2018.sav` (Polity V 2018 release) is reachable.
- **License:** free; cite Marshall, Jaggers, Gleditsch.
- **Coverage:** 1800–2018 (~167 countries with population ≥ 500,000).
- **Format:** SPSS `.sav`. Python can read with `pyreadstat`.
- **Gotchas:** **the most recent Polity V release is 2018** — coverage does NOT extend to 2023. This is a 5-year gap to the prototype's target year. For 2023, Polity V is a fallback to Freedom House (which the user is fetching separately).
- **Evidence file:** `tmp/source-vetting-evidence/polity-inscrdata-page.html`.

### `pwt` — Penn World Table 10.01

- **Probe:** https://www.rug.nl/ggdc/productivity/pwt/ (page) and https://www.rug.nl/ggdc/docs/pwt100.xlsx (direct data file).
- **Probed:** 2026-06-17, via `curl -sIL` and a 6.5MB partial download.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

#### Findings

- **Reachability:** the GGDC page is reachable. The direct xlsx URL is reachable (200, 6.5MB).
- **License:** free; cite Feenstra, Inklaar, Timmer.
- **Coverage:** 183 economies, multiple years (typically 1950–2019).
- **Format:** xlsx (also available as `.dta`).
- **Gotchas:** the URL pattern includes the version number (e.g., `pwt100.xlsx` for version 10.01). Stage 2 must discover the latest version.
- **Evidence file:** `tmp/source-vetting-evidence/pwt100.xlsx` (6.5MB).

### `who_gho_api` — WHO Global Health Observatory

- **Probe:** https://www.who.int/data/gho (page) and https://ghoapi.azureedge.net/api/Indicator (OData endpoint).
- **Probed:** 2026-06-17, via `curl -sL`.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

#### Findings

- **Reachability:** the page is reachable (200). The OData API at `https://ghoapi.azureedge.net/api/Indicator` is reachable and returns a comprehensive indicator catalog.
- **License:** open; cite WHO.
- **Format:** OData JSON API. Indicators have codes like `WHOSIS_000001` (life expectancy at birth).
- **Coverage:** global, ~2000 indicators, mostly country-year, some disaggregated by sex/age.
- **Gotchas:** the API returns JSON. Per-indicator queries: `https://ghoapi.azureedge.net/api/WHOSIS_000001` returns the indicator + countries + numeric values.
- **Use case:** primary cross-validation source for the "social well-being" category's health dimension.

### `bti` — Bertelsmann BTI 2006–2026 (recovered)

- **Probe:** https://bti-project.org/en/, https://bti-project.org/en/downloads, and the user-managed cumulative xlsx.
- **Status:** decided.
- **Verdict:** `vetted_ok`.

#### Findings

- **Reachability:** the home page and canonical `/en/downloads` page load. The old `/en/reports` and `/en/data` URLs returned 500 during the initial probe and are treated as vestigial.
- **License:** free; cite Bertelsmann Stiftung.
- **Coverage:** biennial, 2006–2026 in the cumulative workbook. For 2023, use the `BTI 2024` sheet (covers 2022–2023).
- **Format:** xlsx data file plus codebook PDF.
- **Decision:** adopted as a governance/effectiveness source. Data is on disk at `data/raw/bti/`; see its metadata.

### `imf_weo` — IMF World Economic Outlook (blocked)

- **Probe:** https://www.imf.org/en/Publications/WEO and three alternative endpoints.
- **Status:** decided.
- **Verdict:** `blocked`.

#### Findings

- **Reachability:** the main page returns 403 (Akamai bot challenge). Alternative endpoints (`/external/datamapper/api/v1/WEO`, `/-/media/Files/Publications/WEO/...`, `/en/Publications/WEO/weo-database/...`) also return 403.
- **License:** free with account.
- **Coverage:** annual, 1980–current.
- **Decision:** `blocked`. The PWT is the alternative economic source for cross-validation. If the user wants WEO specifically, they can register at https://www.imf.org and download the WEO dataset manually (Option B pattern, same as V-Dem).

### 2026-06-17 — Leader identity coverage gap (CRITICAL — needs user sign-off)

None of the 3 priority leader-identity sources cleanly cover 2023:

- **Archigos:** 1875–2015 (8-year gap)
- **REIGN:** 1950–2021-08 (last monthly release was August 2021; updates ceased)
- **Leader Survival (PLT post-1789):** 1789–2022 (1-year gap, last updated 2025-02-25)

The client bundle is the 2023 reference, but cross-validation is limited.

**Three options for filling the 2023 gap:**

1. **Do nothing; rely on the client bundle.** Low confidence on 2023 leader matches goes to manual review per REQ-REV-002. Historical rows (pre-2022) are validated by the three external sources.
2. **Add a Wikidata-based extractor.** Wikidata's WikiProject Heads of state and government (https://www.wikidata.org/wiki/Wikidata:WikiProject_Heads_of_state_and_government) is daily-updated, free, and supports SPARQL queries. Adds Stage 2 work for a new adapter.
3. **Add CIA World Leaders.** Free, current, but small (a few hundred leaders). A second fallback, not a primary.

**Recommended:** Option 1 (do nothing) for the first prototype, with a note that 2023 manual review will be heavy. If manual review becomes the bottleneck, add Option 2 in a future iteration.

### 2026-06-17 — User sign-off: add Wikidata + Wikipedia + CIA + V-Dem (local file)

The user reviewed the status and chose to add:
- **Wikidata WikiProject Heads of state and government** (SPARQL) — fills the 2023 gap.
- **Wikipedia search + extract** (MediaWiki Action API) — narrative context, reusable for LLM rationale.
- **CIA World Leaders** — current-leaders backstop.
- **V-Dem** — already on disk at `data/raw/vdem/V-Dem-CY-FullOthers-v16_csv.zip` (user downloaded manually; we adopted Option B, no credentials needed).

### 2026-06-17 — CIA World Factbook retired

The CIA World Factbook and its World Leaders page have been retired. The link `https://www.cia.gov/the-world-factbook/field/world-leaders/` 302-redirects to `https://www.cia.gov/stories/story/spotlighting-the-world-factbook-as-we-bid-a-fond-farewell/`. **CIA World Leaders is `blocked`**, but the gap it was meant to cover (current-leaders backstop) is already covered by Wikidata's "currently in office" query. The plan keeps Wikidata as the primary and does not add a replacement for CIA.

### 2026-06-17 — V-Dem v16 verified

- File: `data/raw/vdem/V-Dem-CY-FullOthers-v16_csv.zip` (26.8MB)
- Unzipped: `V-Dem-CY-Full+Others-v16.csv` (388MB)
- 28,093 rows × 202 countries, year range 1789–2025, **179 country-year rows for 2023** specifically.
- Suggested citation captured from the included `suggested_citation.pdf`; see `docs/source-attributions.md`.

### 2026-06-17 — Wikidata SPARQL verified

- Endpoint: `https://query.wikidata.org/sparql`
- Probe query returned a valid JSON result for USA → head of state Q22686 with start date 2017-01-20. The query needs refinement to filter to "currently in office during 2023" precisely, but the contract is clear.
- License: CC0 1.0. No auth, no rate-limit issues at small scale; large queries should be throttled.
- `vetted_ok` based on probe.

### 2026-06-17 — Wikipedia Action API verified

- Endpoint: `https://en.wikipedia.org/w/api.php`
- Search: `?action=query&list=search&srsearch=...` returns paginated search results with `pageid`.
- Extract: `?action=query&prop=extracts&exintro=true&explaintext=true&titles=...` returns the article intro.
- Probe: search + extract for "Andrés Manuel López Obrador" returned a comprehensive intro (300+ words).
- License: CC BY-SA 4.0. No auth. User-Agent header recommended (we set one).
- `vetted_ok`.

### 2026-06-17 — Freedom House email-gated; user-managed (superseded note)

Freedom House FIW data is gated behind an email request. The user has sent that request. Until the file arrives, political freedom is covered by V-Dem + Polity V + RSF; if FIW arrives, place it under `data/raw/freedom_house/` and add it as another political-freedom source. Freedom House narrative PDFs are still free and can be used as LLM input for qualitative context, but that's a Phase E concern.

### 2026-06-17 — COW MID blocked, replace with UCDP

COW MID 4.0 is doubly blocked: SSL cert issue in this environment AND data ends 2014. **Use UCDP GED 23.1** (or latest) for the international-conflict indicator.

### 2026-06-17 — CIRIGHTS initially DNS-blocked; user-managed data later placed

CIRIGHTS is DNS-unreachable from this environment, but the user later placed v3.12.10.24 files under `data/raw/cirights/`. Use CIRIGHTS as a user-managed domestic-repression source with a 1-year gap to 2023; PTS, UCDP one-sided violence, and V-Dem repression remain cross-validation sources.

### 2026-06-17 — TI CPI direct file gated; alternative: HTML report or API key request

The direct xlsx file is CDN-gated (403). The report page is HTML and free. **Recommended:** scrape the HTML report for the prototype; if we want the xlsx, request an API key from Transparency International (a small operational task).

---
