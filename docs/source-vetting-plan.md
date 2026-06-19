# Source Vetting Plan — Phase B (historical; living audit trail)

This plan gates **Phase C (data acquisition)**. No Stage 2 ingest adapter is written until its source's verdict in `data/outputs/source_vetting_report.{csv,md}` is `vetted_ok` or `vetted_with_caveats`.

Phase A is complete: the package, CLI, schema, paths, configs, data-lake folders, and smoke tests are in place. The Phase A finish line is documented in [`workplan.md`](workplan.md). The 6 client-bundle files (5 xlsx + 1 docx) are staged under `data/raw/client_existing/` with a `metadata.json`.

The goal of Phase B is to replace "trust the §6 source list" with **evidence per source**: a row in the source-vetting report for each priority source that records whether the dataset is reachable, whether it requires a login, whether it requires payment, whether its license is compatible, whether it actually covers 2023, and whether its format is parseable. Anything that does not pass is blocked from being implemented until it does.

## Why this phase exists

The Stage 0 / Stage 2 implementation in §8 lists priority sources, but it does not verify that any of them are still reachable in 2026, that their terms of use are compatible with redistribution inside the project, or that they actually cover the prototype's target year (2023) without gaps. Implementing adapters against stale URLs or paywalled downloads wastes effort and pollutes `data/raw/` with partial files. This plan sequences the verification work ahead of the implementation work.

## Scope

In scope:

- The **14 external priority sources** listed in requirement §6. The client's own bundle (`client_existing`) is already on disk and is **not** re-vetted here — the relevant checks for the client bundle are documented in [`data-sources.md`](data-sources.md) and covered by the Stage 1 acceptance criteria.
- The decision to **replace** a source with a substitute when the canonical one fails vetting (e.g. switch V-Dem to V-Dem Lite if the full CSV is too large).
- The decision to **drop** a source if no replacement is acceptable.
- Probe results stored in a machine-readable CSV plus a human-readable Markdown report under `data/outputs/`.

Out of scope (Phase B):

- Actually downloading any source. Phase B only probes; downloads land in Phase C.
- Implementing Stage 2 adapters. They are stubs in `src/leaders_db/ingest/<source>.py`.
- Parsing or normalizing any source data.

## Per-Source Probe Checklist

For every source listed below, the probe runner captures:

1. **URL reachable** — `HEAD`/`GET` on the canonical download URL returns a 2xx or a 3xx that resolves to one.
2. **No login wall** — the response body does not require a username/password before the file is served.
3. **No paywall** — the response body does not require a paid subscription, institutional access, or a one-time purchase.
4. **License compatible** — the dataset's license terms permit use inside this project. "Compatible" means: free to read, free to cache locally under `data/raw/<source>/`, free to derive normalized parquet under `data/processed/<source>/`. We do **not** redistribute the raw file; we keep the source attribution verbatim.
5. **Coverage reaches 2023** — the dataset's release calendar includes the target year (2023) without an unreleased gap. We accept partial years (e.g. through Q3) but flag them as `vetted_with_caveats`.
6. **Format parseable** — the response is a parseable format (CSV / xlsx / parquet / Stata / JSON / HTML). HTML-only datasets (FAS, NTI) are acceptable but require a small whitelist of pages to scrape; this is called out in the report.
7. **Checksum reproducible** — when the dataset ships with a published SHA-256, the probe records the expected hash and (during Phase C) verifies it after download. Absence of a checksum is acceptable but flagged.
8. **Country-year grain** — the dataset can be joined on `(country_id, year)` after Stage 3 normalization. Datasets that require fuzzy matching (text snippets, web pages) are flagged with a parse-strategy note.
9. **Known coverage gaps** — what countries or years are missing, per the source's own documentation. Surfaced for the indicator catalog.
10. **Blocker notes** — free-form notes for any non-obvious issue (e.g. requires manual request, redirect chain, deprecated URL).

Each probe returns one of four verdicts:

| Verdict | Meaning | Phase C action |
|---|---|---|
| `vetted_ok` | All checks pass without caveats. | Implement the Stage 2 adapter. |
| `vetted_with_caveats` | Acceptable with caveats (partial year, HTML scrape, no checksum). | Implement with caveat notes recorded in the adapter's module docstring and in `metadata.json`. |
| `blocked` | Login wall, paywall, license incompatible, or unreachable. | Do not implement until the blocker resolves; re-probe in 30 days. |
| `replace` | The canonical source fails; a substitute is acceptable. | Probe the substitute; the substitute's verdict replaces the original's in the report. |

The probe runner is implemented in `src/leaders_db/ingest/source_availability.py` during Phase C. Its CLI command (`leaders-db check-source-availability`) is already wired in `src/leaders_db/cli.py`.

## Per-Source Probe Plan

The table below is the canonical Phase B probe plan. Each row records:

- **Source key** — the folder under `data/raw/<source>/`.
- **Canonical URL** — the URL the probe will hit. URLs must be verified before being committed (see "URL freshness rule" below).
- **License** — the terms of use noted in the source's own documentation.
- **Expected coverage** — what year range / country set the source claims to cover.
- **Known gotchas** — anything the adapter must handle that is not obvious from the format alone.
- **Replacement candidate** — for sources likely to fail, the substitute that the probe will fall back to.

### Leader identity sources (REQ-SRC-001)

| Source | Canonical URL (placeholder — verify during Phase B) | License | Expected coverage | Known gotchas | Replacement |
|---|---|---|---|---|---|
| `archigos` | https://www.rochester.edu/college/faculty/hgoemans/Archigos-4.1-updated.zip | free academic; cite Goemans et al. | 1875–2020+ | Versioned "Archigos 4.1-updated"; archive contains multiple CSV files; the country code column needs mapping to ISO3. | (none planned) |
| `leader_survival` | https://leaders.dartmouth.edu/ | free academic; cite Chair et al. | 1875–2020+ | Requires a manual download form (email request historically); verify the current download flow during Phase B. | REIGN as fallback if download is blocked. |
| `reign` | https://oefdatascience.shinyapps.io/Reign/ or direct CSV mirror | free academic; cite Bell et al. | 1950–2020+ monthly | Country-month grain must be rolled up to country-year for the leader resolver. | (none planned) |

### Political freedom sources (REQ-SRC-002)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `vdem` | https://v-dem.net/data/the-v-dem-dataset/ | free academic; cite V-Dem Institute; **registration required for download** | 1789–2023 | Requires a free registration; the registered download URL is personalized. The probe must log in (or detect the login page) and verify the download. | `vdem_lite` (publicly accessible subset) if full dataset is unavailable. |
| `freedom_house` | https://freedomhouse.org/reports/publication-archives | free; cite Freedom House | 1972–2023 | Annual xlsx; sometimes splits political-rights / civil-liberties into separate tabs. | EIU / Polity as auxiliary. |
| `rsf_press_freedom` | https://rsf.org/en/index | free; cite Reporters Without Borders | 2002–2026 | Semicolon-delimited annual CSVs; direct `2011.csv` is missing because RSF has a combined 2011/2012 edition; methodology changes around 2022. | Use only as a press/media-freedom sub-signal. |

### Economic sources (REQ-SRC-003)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `world_bank_wdi` | https://api.worldbank.org/v2/ | free; no key required | 1960–2023 | API has per-call limits; the adapter must page through results. Country code is ISO2, must be lifted to ISO3. | IMF WEO later (auxiliary). |

### Governance / effectiveness sources (REQ-SRC-004)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `world_bank_wgi` | https://info.worldbank.org/governance/wgi/ | free; no key required | 1996–2023 | Aggregate governance indicators; per-indicator series with missing years. | V-Dem governance subset (already in `vdem`). |

### Corruption / integrity sources (REQ-SRC-005)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `transparency_cpi` | https://www.transparency.org/en/cpi | free; cite Transparency International | 1995–2023 | The CPI is a perception index (0–100, higher = cleaner). Some country-years are missing. | WGI Control of Corruption (subset of `world_bank_wgi`). |

### Conflict / international aggression sources (REQ-SRC-006)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `ucdp` | https://ucdp.uu.se/downloads/ | free academic; cite UCDP | 1946–2023 | Multiple sub-datasets (state-based, non-state, one-sided); the adapter picks the right one per category. | ACLED later (auxiliary). |
| `cow_mid` | https://correlatesofwar.org/data-sets/MID | free academic; cite COW | 1816–2014 (latest) | Stops at 2014; **does not cover 2023**. Expected verdict: `blocked` for our purposes. | UCDP armed conflict dataset. |
| `sipri` | https://www.sipri.org/databases | free; cite SIPRI | 1949–2023 | Multiple sub-datasets; the adapter picks the right one per indicator. | (none planned) |

### Domestic repression / violence sources (REQ-SRC-007)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `political_terror_scale` | https://www.politicalterrorscale.org/ | free academic; cite Wood et al. | 1976–2023 | Annual scale 1–5; the adapter inverts (5 → "most terror"). | CIRIGHTS subset. |
| `cirights` | https://www.cirights.org/ | free academic; cite Cingranelli et al. | 1981–2023 | Standardizes physical-integrity rights scores. | PTS as fallback. |

### Nuclear / global responsibility sources (REQ-SRC-008)

| Source | Canonical URL | License | Coverage | Gotchas | Replacement |
|---|---|---|---|---|---|
| `fas` | https://fas.org/issues/nuclear-weapons/ | free; cite FAS | ongoing | HTML pages, not bulk download. The adapter uses a curated whitelist of country pages. | SIPRI nuclear forces (subset of `sipri`). |
| `sipri_nuclear` | https://www.sipri.org/databases | free | 1945–2023 | Same as `sipri`. | (none planned) |
| `nti` | https://www.nti.org/countries/ | free; cite NTI | ongoing | HTML pages. The adapter uses a curated whitelist of country profiles. | FAS as fallback. |

## URL Freshness Rule

Before committing any URL into `docs/data-sources.md`, the probe runner must hit the URL once during Phase B and confirm:

- The URL returns 2xx.
- The response body identifies the dataset unambiguously (title, version, year).
- The URL is the **canonical** distribution endpoint (not a third-party mirror).

URLs that redirect more than twice are flagged for human review. URLs that require JavaScript execution are flagged for a Phase C scraping strategy decision.

## Probe Runner Contract

`src/leaders_db/ingest/source_availability.py` (Phase C implementation) implements:

```python
def check_all_sources(year: int) -> dict[str, str]:
    """Return a per-source verdict map.

    Returns a mapping of source_key -> one of:
        'vetted_ok' | 'vetted_with_caveats' | 'blocked' | 'replace'
    """
```

The runner writes two artifacts:

- `data/outputs/source_vetting_report.csv` — one row per source with all 10 probe fields.
- `data/outputs/source_vetting_report.md` — human-readable summary with a per-source narrative.

Each run is logged under `data/logs/<run-id>/` with the resolved run config and the probe payload (URLs and headers only — never credentials).

## Verdict Schema

```text
vetted_ok           — full pass; implement the adapter in Phase C as planned.
vetted_with_caveats — implement with caveat notes; record the caveat in the
                      adapter's docstring and in metadata.json.
blocked             — do not implement. Re-probe in 30 days. The blocker
                      (login wall, paywall, license) is documented in the
                      report. If three consecutive blocked verdicts land
                      for a source, the project-manager opens a
                      "replace" review.
replace             — the canonical source failed; a substitute is acceptable.
                      Probe the substitute and use its verdict. If no
                      acceptable substitute exists, the source is dropped.
```

## Output Report Format

`data/outputs/source_vetting_report.csv` columns:

| Column | Type | Notes |
|---|---|---|
| `source_key` | text | matches `data/raw/<source>/` |
| `canonical_url` | text | the URL probed |
| `reachable` | bool | 2xx or 3xx → true |
| `login_required` | bool | page redirects to a login form |
| `paywall` | bool | page returns "subscribe to download" or similar |
| `license` | text | human-readable license note (from the source's docs) |
| `license_compatible` | bool | per the rule above |
| `coverage_start_year` | int | earliest country-year covered |
| `coverage_end_year` | int | latest country-year covered |
| `covers_target_year` | bool | true if `target_year` is in `[coverage_start_year, coverage_end_year]` |
| `format` | text | `csv`, `xlsx`, `parquet`, `dta`, `sav`, `json`, `html`, ... |
| `parseable` | bool | per the format check |
| `expected_checksum_sha256` | text | published checksum when available; empty otherwise |
| `known_gaps` | text | free-form note |
| `replacement` | text | candidate source key when verdict is `replace` |
| `verdict` | text | one of the four values |
| `verdict_notes` | text | free-form note explaining the verdict |
| `probed_at` | text | ISO timestamp |

`data/outputs/source_vetting_report.md` mirrors the CSV with a per-source narrative.

## Phase B Exit Criteria

Phase B is complete when:

1. Every priority source in §6 has a row in `source_vetting_report.csv`.
2. Every row has a non-empty `verdict` (`vetted_ok` / `vetted_with_caveats` / `blocked` / `replace`).
3. The Markdown report is human-readable and any human reviewers agree with the verdicts.
4. For every `vetted_ok` or `vetted_with_caveats` source, the canonical URL is recorded in `docs/data-sources.md`.
5. For every `blocked` source, the blocker is documented in `docs/data-sources.md` (and the workplan records the re-probe date).
6. For every `replace` verdict, the substitute has been probed and its verdict is the one used going forward.
7. The `metadata.json` placeholder for each `data/raw/<source>/` is updated with the probed `source_url`.

Phase C begins only after Phase B's exit criteria are met and the report is reviewed.

## URL Verification Workflow

Before adding any URL into the table above, the Phase B agent (or a human reviewer) must:

1. Open the URL in a browser, log out of any session, and confirm the dataset is reachable.
2. Capture the canonical distribution endpoint (the direct link that returns the file, not a marketing landing page).
3. Record the license note verbatim from the source's documentation.
4. Record the published coverage range from the source's documentation.
5. Note any required registration, CAPTCHA, or institutional login.

The captured URL is committed to `docs/data-sources.md` only after step 1 succeeds without authentication. Any URL that does not pass step 1 is moved to a `Blocked URLs — Re-probe Schedule` section at the bottom of `docs/data-sources.md`.

## What Phase B Does Not Do

- **It does not download any data.** Phase C does that.
- **It does not implement any ingest adapter.** Adapters remain stubs.
- **It does not change the priority source list.** Adding or removing sources is a requirements change (REQ-SRC-*) and must go through [`docs/req/requirements-core.md`](req/requirements-core.md) first.
- **It does not write to `data/raw/<source>/` content.** The folders are empty (except for `client_existing`, which was filled during Phase A) and stay empty until Phase C.

## Done When

Phase B closes when the project-manager signs off on the source-vetting report and the workplan moves the active-phase indicator from **A** to **B** to **C**. The transition is recorded in [`workplan.md`](workplan.md)'s Done History.
