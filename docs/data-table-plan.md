# Data Table Plan

This workplan defines the database tables we want to build and populate so the
project can answer the methodology questions in
[`methodology/ranking-evaluation-criteria.md`](methodology/ranking-evaluation-criteria.md).

The goal is practical: create easy-to-query tables that turn scattered source
files into a base layer of facts, ruler identity, question answers, evidence
links, and later scores.

This is a planning document, not a schema migration. Table names may change when
implemented, but the layers and dependencies should stay stable.

## Plain-English model

The data should flow like this:

```text
raw source files
  -> cleaned observations
  -> core country/year and ruler/year tables
  -> harmonized topic tables
  -> question-answer tables
  -> category scores and review queues
```

The client matrix is never evidence. It is only a comparison/reference later.

## Infrastructure phases

Each table below lists which infrastructure phases must exist before that table
can be considered complete.

| Phase | Name | What must be available |
|---:|---|---|
| **I0** | Existing base | Current DB migrations, source registry, local data lake, `normalized_observations`, and source metadata. |
| **I1** | Database bootstrap | A clear command/path that creates the working SQLite database and applies all migrations. The system should not fail with a confusing “missing table” error. |
| **I2** | Source-to-observation ingestion | Clean source adapters can populate `normalized_observations` from local raw files without rereading raw files during later analysis. |
| **I3** | Country-year grid | A repeatable builder creates all in-scope country/year rows. |
| **I4** | Ruler identity layer | Archigos/REIGN/Wikidata/manual sources can populate leaders, ruler spells, and ruler-years. |
| **I5** | Concept harmonization | Source indicators are mapped into stable concepts such as GDP per capita, population, conflict fatalities, corruption, democracy, HDI, etc. |
| **I6** | Harmonized fact-table builders | Generic builders can write friendly country-year topic tables from concepts/observations. |
| **I7** | Question registry | Every methodology question has an ID, text, category, expected answer type, and evidence strategy. |
| **I8** | Question-answer persistence | Generic answer tables and evidence-link tables exist and support reruns without duplicate rows. |
| **I9** | Ruler-period evidence support | Period-level goal/program/crisis evidence can be stored for questions that are not naturally one-year facts. |
| **I10** | Internet/manual evaluator storage | Web/manual/LLM evaluation records can be stored with citations, score, confidence, warnings, and source traceability. |
| **I11** | Score aggregation | Category scores can be computed from question-answer rows and written to final score/review tables. |

### Infrastructure phase details

This section explains what each infrastructure phase means in practical terms.
It is written for future agents as implementation guidance. The table above is
the short dependency label; the sections below are the actual workplan.

#### I0 — Existing base

**Plain meaning:** the project already has a local data lake, source registry,
database migrations, and some source adapters. This is the starting point, not a
new work item.

**Already implemented:**

- `data/raw/<source>/`, `data/processed/`, `data/outputs/`, `data/catalog/`, and
  related local-data folders exist by convention.
- The prototype DB schema already defines core tables such as `countries`,
  `country_years`, `leaders`, `ruler_spells`, `ruler_years`, `sources`,
  `source_observations`, `normalized_observations`, `ruler_scores`, and
  `validation_results`.
- Many source adapters/readers exist for sources such as WDI, WGI, V-Dem, UCDP,
  SIPRI, PTS, CIRIGHTS, Transparency CPI, FAS, Archigos, REIGN, BTI, RSF, UNDP,
  WHO, Freedom House, Polity, Maddison, and PWT.
- The client matrix is explicitly a validation reference only, not evidence.

**Still missing / not guaranteed:**

- A fresh default database may not contain all expected tables unless migrations
  are applied correctly.
- Having source adapters on disk does not mean source rows have been loaded into
  the working database.
- Several core tables exist in schema but may be empty.

**Done means:** no code needed just for I0; agents should treat it as the current
base and verify actual table/data presence before claiming downstream phases are
ready.

**Unlocks:** D1, D6, and planning for all later tables.

#### I1 — Database bootstrap

**Status (2026-06-29): implemented.** The normal local SQLite file is
`data/catalog/leaders_db.sqlite`. Run `leaders-db init-db` to create it; the
command applies all checked-in migrations in order. Read commands that use the
local evidence store now check for required persisted tables and report a
friendly setup message instead of raw `no such table` SQL errors. Explicit
`--db-url` callers remain supported.

**Plain meaning:** there must be one obvious working database file and a clear way
to create it. Commands must fail with helpful messages if the database is missing
or uninitialized.

**Already implemented:**

- A database engine/session layer exists.
- Migration files exist, including the base schema and later research/evidence
  tables.
- CLI commands can accept `--db-url` in some places.

**Still missing / weak:**

- The default database path is not obvious enough for normal use.
- The new evidence-summary command failed when run against the default DB because
  `normalized_observations` was missing there.
- Users should not need to understand SQL errors such as `no such table`.

**Build tasks:**

1. Decide and document the normal working SQLite path, probably under
   `data/catalog/`.
2. Ensure the database initialization command applies every migration, not only
   the first one.
3. Add a database readiness check used by CLI commands that need persisted data.
4. Replace raw SQL missing-table errors with a message like: “The local evidence
   database is not initialized. Run `<command>` or pass `--db-url`.”
5. Add a smoke test: initialize a fresh database, then run a simple read command
   without passing `--db-url`.

**Done means:** a clean checkout can create the working database and run a tiny
query without manual DB-path guessing.

**Unlocks:** D2-D7 and every later table that depends on a real database.

#### I2 — Source-to-observation ingestion

**Plain meaning:** turn local raw source files into cleaned rows in
`normalized_observations`. Later analysis should read the database, not raw files.

**Already implemented:**

- Many source adapters exist.
- `normalized_observations` exists as the shared cleaned-observation store.
- Source observations preserve source slug, observation id, family, indicator,
  value, year, country, leader fields where present, raw locator, transform
  locator, warnings, and metadata.
- I2 first infrastructure slice (2026-06-29): `leaders-db sources ingest
  <source>` now persists non-dry clean-source runs to the initialized working
  database (`data/catalog/leaders_db.sqlite` by default, or `--db-url`) through
  `SourceIngestRunner` / `normalized_observations`; reruns upsert on
  `(source_slug, observation_id)`. `leaders-db sources coverage` reports rows
  actually loaded in the DB by source, observation family, indicator, min/max
  year, country count, and missing raw-locator count, with a registry-backed
  source-status section that marks zero-row manual/user-managed sources as
  `blocked_user_managed` rather than failed.

**Still missing / weak:**

- Some processed parquet files were observed empty even while raw files existed.
- Real priority-source loading still depends on the operator running ingestion
  against locally managed raw files; fixture tests do not touch user raw data.
- The coverage report is DB-backed and does not infer adapter failures; failed
  runs remain visible through ingest readiness/errors, while coverage statuses
  distinguish `loaded`, `no_rows`, and `blocked_user_managed`.

**Build tasks:**

1. Run the highest-value local sources into the working database.
2. For each source, report row counts by `observation_family`, indicator, year
   range, and country count.
3. Mark blocked/user-managed sources separately from failed sources.
4. Ensure ingestion is idempotent: rerunning the same source should update or
   replace stable rows, not duplicate them.
5. Preserve raw/source locators for every row.

**Done means:** `normalized_observations` contains queryable evidence rows for the
priority sources and a coverage report says what is present/missing.

**Unlocks:** D7 and all harmonized fact tables D8-D17.

#### I3 — Country-year grid

**Plain meaning:** create the complete list of country/year rows we expect to
answer. This is the project calendar and map.

**Already implemented:**

- `countries` and `country_years` are already part of the schema.
- Country normalization utilities exist.
- I3 now provides `leaders-db scope build-country-years` and
  `leaders-db scope country-year-coverage`. The build command populates
  `countries` from a deterministic current ISO 3166-1 alpha-3 universe
  (`pycountry` when installed, otherwise the packaged I3 seed) plus a packaged
  year-level lifecycle seed, then expands requested country/year intervals
  idempotently while marking out-of-lifecycle rows audit-only.
- The packaged lifecycle seed includes a conservative, year-level `PSE` policy:
  `PSE` is retained as a polity-sensitive current ISO entry but enters the D3-D5
  ruler-scoring denominator only from the 2012 UN non-member observer State
  anchor; earlier rows remain audit-only rather than identity gaps.
- The legacy prototype config still stores `1900-2023` in
  `configs/prototype-2023.yaml` under `scope.start_year` / `scope.end_year`, but
  active D3-D5 identity work currently uses explicit CLI overrides for
  `1950-2025`. This is a quality-first stepwise working period, not a final
  product-scope claim; 2023 is retained as a diagnostic/client-comparison slice.

**Still missing / weak:**

- The lifecycle model is year-level and intentionally not a complete historical
  ontology, but it has been expanded for the active 1950-2025 D3-D5 scope. It
  now covers post-1950 independence / modern statehood anchors for most current
  included ISO3 countries that would otherwise inflate pre-statehood ruler
  denominators, plus selected ceased predecessor states such as `SUN`, `CSK`,
  and `YUG`.
- Population thresholds, recognition/sovereignty edge cases, disputed-country
  cases, and detailed successor subperiods are not yet globally modeled.

**Build tasks:**

1. Decide the first target range. **Current:** active D3-D5 work uses
   `1950-2025` through explicit CLI overrides. The legacy prototype config still
   carries `1900-2023`; treat that as a config default/diagnostic baseline, not
   the current identity-coverage goal.
2. Populate `countries` with canonical ISO3 names and normalized names.
   **Done:** via `pycountry` when available, otherwise the packaged I3 seed,
   plus packaged lifecycle rows such as historical `YUG`.
3. Generate `country_years` for all in-scope country/year pairs.
   **Done:** deterministic and idempotent; audit rows are generated for the
   requested country/year grid and rows outside each country code's
   valid-from/valid-to interval are marked `included_in_project = false` with a
   lifecycle exclusion reason rather than silently omitted.
4. Add `included_in_project`, `inclusion_reason`, and confidence/coverage notes.
   **Partial:** schema fields are populated with lifecycle inclusion/exclusion
   reasons where present; detailed global scope rules remain future work.
5. Produce a country-year coverage report. **Done:** text or JSON via CLI.

**Done means:** for any target year in the configured range, the system can list
the current ISO3 countries that should receive answers and reports the current
limitations for excluded/uncertain scope rules not yet represented.

**Unlocks:** D2, D8-D17, D24, D29.

#### I4 — Ruler identity layer

**Plain meaning:** for every country/year, identify the ruler or dominant ruling
figure we are evaluating.

**Already implemented:**

- Schema tables exist: `leaders`, `leader_aliases`, `ruler_spells`, and
  `ruler_years`.
- I4 infrastructure now consumes persisted `normalized_observations` identity
  families (`leader_identity_spell`, `leader_identity_month`, and
  `leader_identity_country_year`) and idempotently populates `leaders`,
  `leader_aliases`, `ruler_spells`, and overlapping `ruler_years` through
  `leaders-db identity build-ruler-years`.
- D3-D5 operational run on 2026-06-30 proved non-client local identity evidence
  can populate the tables: 2,752 total `leaders`, 14,358 evidence-backed
  `ruler_spells`, and 15,663 evidence-backed `ruler_years` after excluding the
  three `vertical_slice_client_seed` rows from coverage. Archigos contributes
  1,972 spells / 3,303 ruler-years over 1900-2015 where its source-native
  country code maps to the lifecycle grid; REIGN contributes 12,386 spells /
  12,360 ruler-years over 1950-2021.
- D3-D5 current-identity continuation on 2026-06-30 persisted 325 Wikidata
  HoS/HoG `leader_identity_country_year` observations for 2023 from the locally
  staged `cyc_2023_all_c01e7af7cf.json` Wikidata SPARQL cache. The source
  adapter consumes this cache only for explicit all-country year requests where
  the older `wd_ALL_<year>_all_<hash>.json` cache is absent; the ISO3 values are
  source-provided `countryISO3` bindings, not client-matrix evidence or stale
  REIGN/Archigos fill. D3-D5 now reports the current-year path as automated
  coverage/gap diagnostics, not full data completion: the 2023 audit grid has
  249 country-year rows, the included scoring denominator is 195, and 54 rows are
  `out_of_scope` audit rows. Basic included-only coverage is 188 covered / 7
  missing / 195 total, where covered includes rows that still need attention.
- `leaders-db identity ruler-coverage [--year ...] [--json]` reports total,
  covered, missing, disputed, multiple-possible, low-confidence, and
  source-conflict country-years.
- D3-D5 automated reporting now extends `ruler-coverage` with a reusable
  detailed gap report: `--detail`, `--output json|csv|markdown`, `--year`,
  `--start-year`, `--end-year`, and `--write-artifact`. The report classifies
  every country-year instead of chasing individual current-year gaps by hand.
  Stable classifications include the backward-compatible labels `resolved`,
  `multiple_candidates`, and `source_conflict`, plus the adjudication-aware
  labels `resolved_auto_single_candidate`, `resolved_auto_role_priority`,
  `resolved_auto_duration_majority`, `multiple_candidates_manual_review`,
  `source_conflict_manual_review`, `missing_no_identity_observation`,
  `missing_unresolved_country_mapping`, `missing_source_out_of_range`,
  `missing_current_source_cache`, `disputed_rule`, `low_confidence`, and
  `out_of_scope`. Source diagnostics
  report loaded identity rows, min/max years, mapped country counts, usable rows,
  skipped rows, unresolved country rows, missing leader rows, and missing time
  anchors for Archigos/REIGN/Wikidata-style identity observations already loaded
  in `normalized_observations`.
- D3-D5 adjudication v1 now selects a principal ruler-year only where deterministic
  evidence is safe while preserving all candidates. The current no-migration
  implementation stores the selection rule and evidence trail in existing
  `ruler_years` fields: `match_status` carries `resolved_auto_single_candidate`,
  `resolved_auto_role_priority`, `resolved_auto_duration_majority`,
  `preserved_competing_candidate`, `multiple_candidates_manual_review`, or
  `source_conflict_manual_review`; `review_status` distinguishes `auto_resolved`
  from `needs_review`; `review_note` records the selection rule, competing
  candidates, source/title observations, warnings, and confidence penalties; and
  `system_selected_leader_name` points competing rows at the selected principal
  name when one exists. Auto-resolved disagreements are penalized by 10 confidence
  points and unresolved/manual conflicts by 20 points. The first rules are:
  exactly-one-candidate, actual/dominant executive over formal-only officeholder,
  simple two-candidate majority-year duration, alias cleanup for superficial
  title/suffix/parenthetical variants, and manual review for unresolved source
  conflicts, no-majority transitions, three-plus candidates, and coup/contested /
  de-facto/disputed cases unless source metadata clearly marks the actual ruler.
- D3-D5 source-native country-code mapping refinement on 2026-07-01 moved the
  largest actionable 1950-2025 missing-identity cluster into the shared source
  country-code bridge instead of the identity builder. The mapped source-native
  codes are `ROK→KOR`, `TAW→TWN`, `DRC→COD`, `CEN→CAF`, `CDI→CIV`, `CAP→CPV`,
  `CON→COG`, `MAC→MKD`, `BOS→BIH`, `CZR→CZE`, `OMA→OMN`, `SER→SRB`, and
  `BHU→BTN`. Archigos and REIGN now emit mapped project `country_code` values
  from that bridge, and country filters can use either the source-native token or
  the mapped project ISO3. After local Archigos re-ingest and 1950-2025 identity
  rebuild, the refreshed artifact reports 12,265 included scoring targets, 11,617
  covered target rows (94.72%), 384 `missing_no_identity_observation`, 264
  `missing_current_source_cache`, and 6,887 `out_of_scope` audit rows. This run
  did not fetch live data, edit raw files, use the client matrix as evidence, or
  manually chase individual rulers.
- D3-D5 REIGN alias/COW mapping refinement on 2026-07-02 added the remaining
  high-impact REIGN-native aliases/codes to the same shared bridge: `St Lucia` /
  56 → `LCA`, `St Kitts and Nevis` / 60 → `KNA`, `St Vincent` / 57 → `VCT`,
  `Micronesia` / 987 → `FSM`, and `Korea South` / 732 → `KOR`. `Soviet Union`
  rows map to historical `SUN` through 1991, and the REIGN country filter avoids
  matching those rows as `RUS` via COW code 365. After local REIGN re-ingest and
  a 1950-2025 identity rebuild, the refreshed artifact reports 12,265 included
  scoring targets, 11,850 covered target rows (96.62%), 151
  `missing_no_identity_observation`, 264 `missing_current_source_cache`, and
  6,887 `out_of_scope` audit rows. Remaining top included gaps (`PSE`, `AND`,
  `OMN`, `SOM`) are not safe alias-only REIGN mapping fixes under the current
  no-manual-chasing constraint.
- D3-D5 scope refinement on 2026-06-30 added a conservative packaged exclusion
  seed for clear ISO territory/dependency/special entries so they remain in the
  audit grid but are not counted in the ruler-scoring denominator. The 2023
  scope now has 249 country-year rows, 195 included scoring targets, and 54
  excluded non-sovereign/special entries. The earlier broad missing set was split
  into out-of-scope territory/special entries, included current-state
  cache/mapping gaps, and one scope/recognition-policy case (`PSE`) retained for
  review. The policy also removes previously covered `PYF`
  from the denominator; `XKS` appears in Wikidata source rows but is not in the
  current country grid.
- D3-D5 local Wikidata role refinement on 2026-06-30 broadened the clean
  transform to retain source ISO3 rows where Wikidata models the broad role as
  `Q14212` (prime minister). Those rows are emitted under the existing
  head-of-government indicator, with the source role/concrete office preserved
  in the observation extension. The local 2023 rebuild now has basic
  included-only coverage of 188 covered / 7 missing / 195 targets. The detailed
  classification artifact separates those rows into 88 `resolved`, 100
  `multiple_candidates`, 7 `missing_no_identity_observation`, and 54
  `out_of_scope` audit rows; the 7 missing countries are not silently filled.
- D3-D5 2024-2025 current-identity continuation on 2026-07-02 used only already
  staged local Wikidata HoS/HoG Chronicle/SPARQL caches. The readiness-selected
  cache files are `cyc_2024_all_c01e7af7cf.json` and
  `cyc_2025_all_c01e7af7cf.json`; both passed `offline_only` readiness and were
  ingested through `leaders-db sources ingest wikidata_heads_of_state_government
  --year <year> --cache-policy offline_only`. The active 1950-2025 coverage
  artifact now reports 12,203 included scoring targets, 12,092 covered targets
  (99.09%), 102 `missing_no_identity_observation`, 9
  `missing_current_source_cache`, and 6,949 out-of-scope audit rows. No live
  fetch, raw edit, client-matrix evidence, ad hoc scrape, or invented leader row
  was used.
- D3-D5 durable adjudication layer on 2026-07-02 added
  `ruler_identity_adjudications`, a queryable one-row-per-included-country-year
  table built from the existing v1 `ruler_years` adjudication statuses and
  detailed coverage output. `leaders-db identity build-adjudications --start-year
  1950 --end-year 2025` upserts principal selections and unresolved/research
  prompts without duplicating rows on rerun. The first active-period operational
  build persisted 12,203 rows: 9,924 `auto_resolved`, 2,168 `needs_review`, and
  111 `research_required`; unresolved rows carry candidate IDs, source context,
  rationale, recommended next action, and a future manual/internet-research
  prompt. No live fetch, client-matrix evidence, raw edit, or invented ruler was
  used.
- D3-D5 generic fact publication on 2026-07-02 added `country_year_facts`, a
  reusable one-row-per-country-year-field adjudication table. The ruler identity
  builder now publishes `field_key = principal_ruler` there in addition to the
  ruler-specific table, using the same candidate values, selected entity,
  confidence, warnings, source links, rationale, review status, and future
  research prompt. This is the intended pattern for later fields such as GDP,
  political freedom, conflict fatalities, nuclear status, sanctions, coups, and
  methodology question cells; future producers should add fields to the generic
  contract instead of creating one-off adjudication mechanisms.
- D3-D5 automated second-pass adjudication on 2026-07-02 added a conservative
  year-coverage rule inside `build-ruler-identity-adjudications`. Candidate JSON
  now carries `year_coverage_days` and `year_coverage_ratio`; unresolved
  transition rows can be upgraded to
  `resolved_auto_year_coverage_majority` / `year_coverage_majority` when dated
  intervals show one candidate covering more than half of the target year, that
  candidate has decisive coverage, and no disputed/shared/coup/contested/de-facto/
  junta hard-review marker is present. Rows that still lack reliable coverage or contain hard conflicts keep
  `needs_review`/`research_required` plus the research prompt. The generic
  `principal_ruler` fact mirrors the selected entity and stores the selected
  coverage ratio as `temporal_fit_score`.
- D3-D5 REIGN monthly identity aggregation on 2026-07-03 fixes the prior
  one-month-fragment failure mode for `leader_identity_month` rows. The identity
  builder now aggregates consecutive month-end observations for the same
  source/country/leader/role/flags into one observed spell while leaving
  non-consecutive gaps unbridged. A 1950-2025 local rebuild changed generic
  `principal_ruler` fact counts from 10,172 `auto_resolved`, 1,920
  `needs_review`, 111 `research_required` to 11,370 `auto_resolved`, 722
  `needs_review`, 111 `research_required`. Remaining durable adjudication review
  rows are mostly source conflicts rather than REIGN-only monthly fragments: 636
  `source_conflict_manual_review` and 86 `multiple_candidates_manual_review`.
  Source-set breakdown for those 722 review rows is 322 REIGN+Wikidata, 304
  Archigos+REIGN, 50 Wikidata-only, 28 REIGN-only, 10 Archigos+REIGN+Wikidata,
  and 8 Archigos-only.
- D3-D5 cited internet-research adjudication on 2026-07-03 added a narrow
  conflict-resolution rule for reviewed identity observations persisted as
  `source_slug = internet_research_adjudication`. When an unresolved
  source-conflict/manual country-year has exactly one such candidate, the
  candidate is marked as actual ruler, source/spell confidence is at least 80,
  year coverage is greater than 50%, and that candidate has no disputed/shared/
  coup/contested/junta hard marker, `build-ruler-identity-adjudications` selects
  it as `resolved_research_adjudicated` using selection rule
  `internet_research_adjudication`. Candidate JSON now also carries source notes
  so normalized-observation IDs and simple citation URL/quote fields from the
  reviewed observation remain visible. The UAE/ARE test case for 2014-2025 now
  resolves to Mohammed bin Zayed Al Nahyan from the cited research adjudication
  observation instead of remaining `source_conflict_manual_review`.
- Raw/adapter support exists or is planned for Archigos, REIGN, Wikidata, and
  related leader sources.
- The project rules already distinguish actual ruler from formal officeholder.

**Still missing / weak:**

- Local project `ruler_years` now contain evidence-backed Archigos/REIGN rows
  where source coverage and country mapping permit, plus partial 2023 Wikidata
  rows where the staged current-identity cache and lifecycle grid match. The
  remaining 2023 gaps are explicit missing country-years, not stale fills.
- The resolver still needs deeper person disambiguation, co-ruler adjudication,
  client-name comparison, and broader human source-disagreement review workflows.
  I4 now
  persists first-class adjudication/review records in
  `ruler_identity_adjudications` and publishes the same principal-ruler cell to
  `country_year_facts`; the current internet-research write-back support is a
  conservative principal-ruler identity rule only, not a general review system.

**Build tasks:**

1. Populate `leaders` and aliases from available leader sources.
2. Populate `ruler_spells` with start/end dates, title, source dataset, actual vs
   formal status, shared/disputed flags, and confidence.
3. Expand spells into `ruler_years` for the country-year grid.
4. Store match status and confidence. Do not silently overwrite the client matrix
   leader string. **Current:** selection metadata remains on candidate
   `ruler_years`, `ruler_identity_adjudications` persists the country-year
   principal selection or unresolved review/research queue, and
   `country_year_facts` publishes the generic `principal_ruler` cell.
5. Produce a ruler identity coverage report: missing, disputed, multiple possible
   rulers, low confidence, and source conflicts.

**Done means:** every in-scope country/year has either a selected ruler row or an
explicit unresolved/manual-review marker. For the current infrastructure slice,
that marker is now persisted in `ruler_identity_adjudications`, published as the
generic `principal_ruler` row in `country_year_facts`, and can also be exported
through the generated D3-D5 gap report artifacts.

**I4 normalized-observation contract:** `leaders-db identity build-ruler-years`
does not read raw files. It consumes persisted `normalized_observations` rows in
the following families only: `leader_identity_spell`, `leader_identity_month`,
and `leader_identity_country_year`.

- Required country match: one of `country_code`, `extension.country_code`,
  `extension.country_iso3`, `extension.iso3`, supported source-native
  three-letter identity codes such as `extension.archigos_idacr` /
  `extension.reign_country`, or supported COW numeric code extensions such as
  `extension.archigos_ccode` / `extension.reign_ccode` must match
  `countries.iso3`; if none are present, `country_name`,
  `extension.country_name`, or `extension.country_label` may match
  `countries.country_name_normalized` exactly after normalization. Rows with no
  match are skipped and counted in coverage. The source-native/COW mapping is a
  small documented bridge for loaded identity sources, not a complete global
  historical country ontology.
- Required leader name: one of `leader_name`, `extension.leader_name`,
  `extension.person_label`, `extension.reign_leader`, or
  `extension.archigos_leader_name`. Source-native IDs such as `leader_id`,
  `extension.person_qid`, and `extension.archigos_obsid` are provenance only;
  they are not inserted as `leader_aliases.alias` because aliases are reserved
  for human-readable spellings.
- Required time anchor: `extension.start_date` or `extension.start`; otherwise
  `extension.start_year` or row `year` is used with `extension.month` /
  `extension.reign_month` when present. Rows with no start date/year are skipped.
- Optional end date: `extension.end_date` / `extension.end`; otherwise
  `extension.end_year` / `extension.archigos_end_year` with optional
  `extension.end_month`. `leader_identity_month` rows expand only to that month,
  and `leader_identity_country_year` rows without explicit end dates expand only
  to that row year. Open-ended spells expand only across existing included
  `country_years` rows.
- Optional status fields: `extension.office_title`, `extension.office_label`,
  `extension.is_actual_ruler`, `extension.is_formal_leader`,
  `extension.rule_type`, `extension.actual_ruler_status`,
  `extension.shared_rule_flag`, `extension.disputed_rule_flag`,
  `extension.confidence_score`, and `extension.confidence`. If actual/formal
  flags are absent, Wikidata head-of-state rows default to formal-only,
  Wikidata head-of-government rows default to actual+formal, and other identity
  rows default to actual ruler.

**Unlocks:** D3-D5, D18-D22, D25-D28.

#### I5 — Concept harmonization

**Plain meaning:** translate source-specific indicator names into shared project
concepts. For example, a World Bank code becomes `gdp_per_capita`.

**Already implemented:**

- A concept bridge exists for a first economic slice.
- Some concepts are already supported, including GDP per capita, population, and
  total GDP.

**Still missing / weak:**

- Most methodology concepts do not yet have a stable concept key and mapping.
- We need concept definitions for conflict, military spending, HDI, life
  expectancy, education, poverty, democracy, press freedom, repression,
  corruption, governance, and nuclear risk.

**Build tasks:**

1. Define concept keys for each harmonized fact table.
2. Map each concept to source indicators and source priority rules.
3. Define units, direction, allowed value type, and whether higher is better.
4. Mark concepts as direct, derived, proxy, manual/evaluator-only, or unavailable.
5. Add coverage tests for concept extraction.

**Done means:** agents can ask for a concept like `state_based_fatalities` or
`vdem_electoral_democracy` without knowing the raw source column name.

**Unlocks:** D8-D17 and structured parts of D24-D27.

#### I6 — Harmonized fact-table builders

**Plain meaning:** build friendly tables from concepts and observations. These
tables are easier to inspect than raw evidence rows.

**Already implemented:**

- A small economic trend publishing helper exists.
- The visualization concept bridge proves the basic pattern for some economic
  concepts.
- The generic `country_year_facts` table now exists as the reusable adjudicated
  country-year cell contract. The first producer is ruler identity, which writes
  `field_key = principal_ruler`; later I5/I6 builders should publish their own
  fields into the same table before or alongside any topic-specific convenience
  views/tables.

**Still missing / weak:**

- We do not yet have builders for each major topic field/table.
- Builders must keep evidence traceability instead of flattening away sources.

**Build tasks:**

1. Use `country_year_facts` as the standard output pattern for adjudicated fact
   rows: country-year, field key, selected value, candidates, source observation
   ids, confidence, quality components, warnings, review status, and research
   prompt.
2. Build the first tables: population, economy, conflict, and military.
3. Add later builders for social development, political freedom, domestic safety,
   corruption, governance, and nuclear risk.
4. Add coverage reports showing missing years and source disagreement.
5. Make reruns deterministic and idempotent.

**Done means:** each topic has a queryable country-year table that can answer the
basic structured questions and link back to source observations.

**Unlocks:** D8-D17 and many country-year question answers in D24.

#### I7 — Question registry

**Plain meaning:** turn the markdown question bank into a structured registry the
system can execute against.

**Already implemented:**

- `docs/methodology/ranking-evaluation-criteria.md` contains the human-readable
  question bank.
- Some research-engine machinery exists or is in progress for registered
  questions.

**Still missing / weak:**

- The markdown question bank is not yet fully represented as structured records.
- Each question needs metadata: answer level, evidence strategy, answer type, and
  expected output fields.

**Build tasks:**

1. Create a structured question registry from sections 1-8 and 1B-8B.
2. For every question, store: question id, text, category, answer level
   (`country_year`, `ruler_year`, `ruler_period`), answer type, and evidence
   strategy.
3. Tag questions as `structured`, `structured_plus_context`, `internet/manual`,
   or `not_yet_supported`.
4. Ensure question IDs remain stable and match the methodology document.
5. Add a sync/check test that detects drift between markdown and registry.

**Done means:** an agent can select a question ID and know what table/evidence
strategy is supposed to answer it.

**Unlocks:** D23-D27.

#### I8 — Question-answer persistence

**Plain meaning:** create the stable tables where answers to methodology questions
are saved, with evidence links and rerun behavior.

**Already implemented:**

- The current workplan mentions research answer tables such as
  `research_questions`, `research_question_answers`, and evidence links.
- There are active/uncommitted research-result changes in the worktree, so agents
  must inspect current code before changing this area.

**Still missing / weak:**

- The final contract for country-year, ruler-year, and ruler-period answers is not
  yet settled in this data-table plan.
- Answer rows must carry score, confidence, verdict, warnings, missingness, and
  evidence links consistently.

**Build tasks:**

1. Finalize whether to use generic research tables, specific answer tables, or a
   generic table plus views.
2. Support answer scopes: country-year, ruler-year, ruler-period.
3. Add unique keys so reruns update the same answer rather than duplicate it.
4. Store score/value, confidence, verdict, evidence status, warnings, and manual
   review flags.
5. Implement `answer_evidence_links` for normalized observations and web/manual
   citations.

**Done means:** running the same question twice produces one updated answer row
with traceable evidence, not ad hoc CSVs or duplicate rows.

**Unlocks:** D24-D27 and score aggregation in D28-D30.

#### I9 — Ruler-period evidence support

**Plain meaning:** store evidence about a ruler’s whole period: goals, programs,
implementation, crises, appointments, and corruption cases.

**Already implemented:**

- The need is described in the methodology document, especially 8B.
- A local evidence summary command exists to give evaluators structured context.

**Still missing / weak:**

- No stable DB tables yet for goals, implementation evidence, crises,
  appointments, or ruler-period corruption cases.
- Structured country-year numbers alone cannot answer many 1B-8B questions.

**Build tasks:**

1. Define `ruler_period_goals` with source text, domain, specificity, and period.
2. Define `ruler_period_goal_implementation` for laws, budgets, institutions,
   appointments, milestones, and outcomes.
3. Define crisis, appointment, and corruption-case storage.
4. Link each period record to ruler spells/years and source evidence.
5. Support both manual entry and evaluator-produced JSON records.

**Done means:** questions like “Did the ruler define goals?”, “Did they implement
them?”, and “Did they adapt?” can be answered from stored period evidence rather
than only from one-year numeric indicators.

**Unlocks:** D18-D22 and period-level D25-D27.

#### I10 — Internet/manual evaluator storage

**Plain meaning:** store sourced judgment records when structured data is not
enough. This covers web/manual/LLM evaluator outputs.

**Already implemented:**

- The ruler-evaluator concept has been designed.
- A local evidence summary command gives evaluators structured local context.
- 8B trial prompts showed the desired output shape: score 1-10, goal coverage,
  citations, confidence, warnings, and reusable evidence record.

**Still missing / weak:**

- Evaluator outputs are not yet persisted in the main database.
- Citations and snippets are not yet linked to question-answer rows.
- Opencode agent files are local/ignored and require restart/reset to take effect.

**Build tasks:**

1. Define the evaluator-output JSON schema accepted by the app.
2. Store evaluator records with question id, ruler/country/year or period,
   score_1_10, verdict, confidence, citations, goal coverage, and caveats.
3. Link evaluator evidence to answer rows via `answer_evidence_links`.
4. Distinguish local structured evidence, web citations, manual notes, and LLM
   reasoning artifacts.
5. Add safeguards: no invented citations, no client matrix as evidence, and manual
   review when confidence is low.

**Done means:** an evaluator can answer a qualitative ruler question and the
database can store that answer with enough evidence to justify it later.

**Unlocks:** D18-D27, especially ruler-quality questions 1B-8B.

#### I11 — Score aggregation

**Plain meaning:** combine question answers into final category scores and review
queues.

**Already implemented:**

- `ruler_scores` exists in the schema.
- Some deterministic scoring code exists.
- The fixed confidence formula exists.

**Still missing / weak:**

- Final scores are not yet derived from the full question-answer tables.
- Category aggregation from 1B-8B answers needs explicit rules.
- Manual-review queues must point back to answer/evidence rows.

**Build tasks:**

1. Define category aggregation rules from question answers.
2. Compute `system_proposed_score`, confidence, rationale, and review flags.
3. Write or update `ruler_scores` / future score tables idempotently.
4. Create drill-down output: score -> questions -> evidence links.
5. Send missing/conflicting/low-confidence cases to manual review.

**Done means:** the project can generate a category score that is explainable from
stored question answers and evidence, not a black-box or one-off script.

**Unlocks:** D28-D30.

## Data table workplan

### 1. Identity and scope tables — start here

These tables define the world we are scoring.

| Step | Table | Purpose | Supports questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D1** | `countries` | One row per country, using ISO3 as the stable key. | All country and ruler questions. | I0 | Schema populated by the I3 builder from current ISO3 plus a partial lifecycle seed; historical `YUG` is included as a seed row. |
| **D2** | `country_years` | One row per country per year in scope. | All chapter 1-8 country-year questions; all 1B-8B ruler-year questions need this as their calendar. | I1, I3 | Populated idempotently by valid lifecycle intervals where known; global lifecycle/recognition/population rules remain partial. |
| **D3** | `leaders` | One row per ruler/person. | All 1B-8B ruler-quality questions. | I1, I4 | Populated from evidence-backed Archigos/REIGN/Wikidata identity observations where source country mapping permits; same-name person disambiguation remains future work. |
| **D4** | `ruler_spells` | One row per leader’s period of rule. | All 1B-8B; especially period questions like 8B.10 and 5B.10. | I1, I2, I4 | Populated from persisted identity observations; historical Archigos/REIGN coverage is operational and 2023 Wikidata coverage is partial. |
| **D5** | `ruler_years` + `ruler_identity_adjudications` + `country_year_facts.principal_ruler` | Candidate ruler-years plus one durable principal-selection/review row, also published through the generic country-year fact contract. | Main anchor for every 1B-8B answer. | I1, I3, I4 | Populated for available evidence-backed spells. The active D3-D5 working period is 1950-2025 for now, with persisted adjudication rows, generic `principal_ruler` fact rows, and JSON/CSV/Markdown gap artifacts; local Wikidata caches now cover the 2024-2025 current-identity path without live fetch. The 2023 grid is useful as a diagnostic slice, not the coverage goal. |
| **D6** | `sources` | Registry of datasets and source versions. | Evidence traceability for every answer. | I0, I1 | Already in schema. |
| **D7** | `normalized_observations` | Clean source observations in one shared format. | Base evidence for almost all structured questions. | I1, I2 | Already in schema. Needs reliable population and clear default DB path. |

### 2. Harmonized country-year fact tables

These are friendly analysis tables built from `normalized_observations`. They do
not replace source evidence; they make it easier to answer questions.

The shared write target for adjudicated cells is now `country_year_facts`. The
topic table names below may still become convenience views/tables, but producers
should first write generic fact rows so all fields share the same candidate,
quality, confidence, review, and research-prompt mechanism.

| Step | Table | Main fields | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D8** | `country_year_population` | population, source, year, confidence. | Section 5 context; denominators for per-capita metrics; inclusion threshold. | I1, I2, I3, I5, I6 | Partly supported via WDI population concept. |
| **D9** | `country_year_economy` | GDP, GDP per capita, GDP PPP, GNI, trade, FDI, inflation, unemployment, debt/fiscal where available. | 5. economic well-being; 5B.1-5B.10; 8B outcome checks for economic goals. | I1, I2, I3, I5, I6 | GDP/population/GDP total partly supported. More concepts needed. |
| **D10** | `country_year_social_development` | HDI, life expectancy, child mortality, immunization, schooling, literacy, inequality, poverty, services access. | 6. social well-being; 6B.1-6B.10; parts of 5. inclusive prosperity. | I1, I2, I3, I5, I6 | Partly supported through `country_year_facts` direct concepts for UNDP HDI/life expectancy/GNI/schooling and WHO GHO under-5 mortality/immunization. Poverty/inequality/services remain future concepts. |
| **D11** | `country_year_political_freedom` | democracy, suffrage, civil liberties, rule of law, press freedom, democratic institutions, Freedom House/Polity later. | 4. political freedom; 4B.1-4B.10. | I1, I2, I3, I5, I6 | Partly supported through `country_year_facts` direct concepts for V-Dem electoral/liberal democracy, civil liberties, suffrage, rule of law, expression, association, and RSF press freedom score/rank. Freedom House/EIU/BTI require ISO3 mapping cleanup before publication. |
| **D12** | `country_year_domestic_safety` | PTS, physical integrity, torture, disappearances, killings, political imprisonment, one-sided violence, civil-society repression, incitement/manual marker. | 3. domestic safety; 3B.1-3B.10. | I1, I2, I3, I5, I6 | Partly supported through `country_year_facts` direct V-Dem concepts for physical integrity, political/private liberties, civil-society repression, and extrajudicial killings. UCDP one-sided violence, CIRIGHTS, and PTS need ISO3/country-code mapping cleanup before publication. Incitement remains manual/web. |
| **D13** | `country_year_international_conflict` | state-based conflict, internationalized conflict, event counts, fatalities, conflict severity/frequency, peace agreement markers, aggressor/proxy markers later. | 2. peace/aggression; 2B.1-2B.10. | I1, I2, I3, I5, I6; I10 for role/proxy claims | UCDP observations exist, but current rows use numeric UCDP country IDs rather than ISO3, so `country_year_facts` publication is blocked on country-code mapping cleanup. Aggressor/proxy role remains future/manual. |
| **D14** | `country_year_military` | military spend, spend % GDP, spend per capita, spend % government budget. | 2.4-2.8 context; 2B.8; nuclear/security context. | I1, I2, I3, I5, I6 | SIPRI Milex observations exist, but current normalized rows do not have usable ISO3 country-year pairs, so publication is blocked on country-code mapping cleanup. |
| **D15** | `country_year_corruption_integrity` | WGI corruption, V-Dem corruption, executive corruption, public-sector corruption, CPI score/source count/error. | 7. integrity; 7B.3-7B.10 support. | I1, I2, I3, I5, I6 | Partly supported through `country_year_facts` direct V-Dem concepts for corruption, executive corruption, and public-sector corruption. WGI/CPI require further mapping/source-priority work. |
| **D16** | `country_year_governance_capacity` | WGI government effectiveness/rule of law/regulatory quality, BTI governance, V-Dem accountability/constraints. | 8. effectiveness background; 8B support; also 4 and 5B. | I1, I2, I3, I5, I6 | Partly supported through `country_year_facts` direct V-Dem concepts for accountability, judicial/legislative constraints, multiparty institutions, and regime type. WGI/BTI require further mapping/source-priority work. |
| **D17** | `country_year_nuclear_risk` | has nuclear weapons, total inventory, deployed warheads, stockpile, reserve, retired warheads, safeguards/treaties, modernization, threats/manual marker. | 1. nuclear/global risk; 1B.1-1B.10. | I1, I2, I3, I5, I6; I10 for rhetoric/doctrine/manual claims | Partly supported through `country_year_facts` direct FAS 2014 arsenal-count concepts for total inventory, military stockpile, operational strategic/nonstrategic, and reserve/nondeployed warheads. Treaty/doctrine/threats and non-FAS source expansion remain future/manual/web work. |

### 3. Ruler-period interpretation tables

These support questions where a simple country-year number is not enough.

| Step | Table | Purpose | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D18** | `ruler_period_goals` | Stores the ruler/government’s stated goals: official plan, campaign platform, budget speech, national program, ideology, etc. | 8B.1, 8B.2, 8B.7, 8B.10; also 5B/6B when goals are economic/social. | I4, I7, I9, I10 | Not supported yet. Needs evaluator/manual/web records. |
| **D19** | `ruler_period_goal_implementation` | Stores evidence that a goal was funded, staffed, legislated, launched, monitored, or corrected. | 8B.2-8B.8; 5B.6-5B.9; 6B.4-6B.6. | I4, I7, I9, I10 | Not supported yet. |
| **D20** | `ruler_period_crises` | Stores major crises and ruler response: war, disaster, pandemic, famine, economic shock, coup, unrest. | 2B, 3B, 5B.9, 6B.6, 8B.8-8B.10. | I4, I7, I9, I10 | Not supported yet. |
| **D21** | `ruler_period_appointments` | Stores important appointments and whether they look professional, loyalist, family, military, patronage, technocratic, etc. | 5B.2, 6B.4, 7B.5, 8B.4. | I4, I7, I9, I10 | Not supported yet. |
| **D22** | `ruler_period_corruption_cases` | Stores leader/family/inner-circle corruption allegations, findings, sanctions, court cases, procurement scandals. | 7B.3-7B.10; also 5B.5 and 8B side effects. | I4, I7, I9, I10 | Not supported yet. |

### 4. Question-answer tables

These are the working tables that turn evidence into direct answers to the
methodology questions.

| Step | Table | Purpose | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D23** | `methodology_questions` | Stores question ID, text, category, answer type, evidence strategy, and whether it is country-year, ruler-year, or ruler-period. | All sections 1-8 and 1B-8B. | I7 | Partly supported in the code registry: Q2.1 plus all 8B.1-8B.10 ruler-effectiveness questions are registered with answer level/type, evidence strategy, support status, output fields, and text-sync tests against the methodology document. Full DB sync and complete sections 1-8 / 1B-7B remain future work. |
| **D24** | `country_year_question_answers` | One answer per country/year/question for the chapter 1-8 country-condition questions. | Sections 1-8. | I3, I5, I7, I8 | Implemented for now through the generic `research_question_answers` table rather than a new grain-specific table. `persist_research_answers` is the typed D24-D27 write contract; Q2.1 continues to use the same table through its wrapper. |
| **D25** | `ruler_year_question_answers` | One answer per ruler/country/year/question for 1B-8B. | 1B-8B. | I4, I7, I8, I10 | Uses the same generic `research_question_answers` path for now, keyed by question/year/ISO3/method and optional ruler fields. Dedicated ruler-year tables are deferred until answer shapes stabilize. |
| **D26** | `ruler_period_question_answers` | One answer per ruler period/question, for questions that cannot honestly be answered one year at a time. | 5B.10, 6B.10, 8B.7-8B.10, many 1B/2B/7B questions. | I4, I7, I8, I9, I10 | Uses the same generic `research_question_answers` path for now, with period-level details stored in `answer_json` and the relevant evaluation/end year in `year` / `evidence_year`. Dedicated period tables are deferred. |
| **D27** | `answer_evidence_links` | Links each answer to exact source observations, web citations, quotes, local files, or manual evidence. | Required for all answer tables. | I8, I10 | Implemented for now through `research_answer_evidence_links`; `persist_research_answers` refreshes links idempotently on rerun. |

### 5. Score and review tables

These consume the answer tables. They should not be built first.

| Step | Table | Purpose | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D28** | `ruler_category_scores` / existing `ruler_scores` | Final per-ruler-year category scores, confidence, rationale, review status. | Aggregates 1B-8B into eight category scores. | I8, I11 | Existing `ruler_scores` schema exists, but scoring from answer tables is not ready. |
| **D29** | `country_category_scores` | Optional per-country-year category scores separate from ruler responsibility. | Aggregates sections 1-8. | I8, I11 | Not explicit today. Optional. |
| **D30** | `manual_review_items` | Queue uncertain, conflicting, missing, or high-impact answers for human review. | All sections. | I8, I10, I11 | Partly supported by validation/manual-review ideas, but not tied to new answer tables. |

## Suggested execution order

### Phase A — make the database usable

Status (2026-06-29): complete for I1. The documented working SQLite path is
`data/catalog/leaders_db.sqlite`; `leaders-db init-db` initializes it with every
checked-in migration, including `normalized_observations` and the research result
tables, and default evidence reads fail with an actionable initialization message
when the database is missing or uninitialized.

1. Confirm the default working SQLite path.
2. Add a friendly setup/check command if needed.
3. Confirm all migrations create `normalized_observations` and the research answer
   tables in a fresh database.
4. Run a tiny smoke query against the default DB without passing `--db-url`.

Blocks: D2-D30 if not done.

### Phase B — populate identity first

Status (2026-07-01): I3/I4 are implemented for the country/year identity base.
Run `leaders-db scope build-country-years --start-year 1950 --end-year 2025`
after `leaders-db init-db` to populate/update the current active working period,
then `leaders-db scope country-year-coverage --json` to inspect totals. This
1950-2025 period is a quality-first, stepwise D3-D5 working range for now, not a
final product-scope claim; the period may change as evidence quality and project
needs evolve. The legacy `configs/prototype-2023.yaml` scope remains a config
default/diagnostic baseline, and 2023 remains a diagnostic/client-comparison
slice rather than the identity-coverage goal. A partial packaged lifecycle seed
now prevents selected known anachronisms such as Slovenia in 1900 and Yugoslavia
after 2002, but global state lifetimes, recognition/sovereignty edge cases,
population thresholds, and disputed cases remain incomplete.

1. Populate `countries`.
2. Build `country_years` for the target range.
3. Populate `leaders`, `ruler_spells`, and `ruler_years` from persisted leader
   identity observations with `leaders-db identity build-ruler-years`.
4. Produce an identity coverage report with
   `leaders-db identity ruler-coverage --json`: missing countries/years,
   disputed rulers, shared/multiple rule, low-confidence matches, and source
   conflicts.

Completes/starts: D1-D5.

### Phase C — populate normalized observations

1. Run clean source ingestion for the highest-value structured sources already on
   disk. I2 supplies the DB-persisting command path:
   `leaders-db sources ingest <source> [--db-url ...]`.
2. Confirm `normalized_observations` has rows by source, country, year,
   indicator. Use `leaders-db sources coverage [--output json]`, which reads the
   DB only and does not reopen raw source files.
3. Produce a source coverage report for the methodology sections. The current I2
   report is source/family/indicator coverage; methodology-section rollups can be
   layered on top once the D6/D7 evidence-link/catalog mapping is finalized.

Completes/starts: D6-D7.

### Phase D — build first harmonized tables

Start with tables that rely on already-available concepts and sources.

1. `country_year_population`
2. `country_year_economy`
3. `country_year_international_conflict`
4. `country_year_military`

Completes/starts: D8-D9, D13-D14.

### Phase E — build remaining harmonized tables

1. `country_year_social_development`
2. `country_year_political_freedom`
3. `country_year_domestic_safety`
4. `country_year_corruption_integrity`
5. `country_year_governance_capacity`
6. `country_year_nuclear_risk`

Completes/starts: D10-D12, D15-D17.

### Phase F — formalize question answering

1. Create/sync `methodology_questions` from the markdown question bank.
2. Create final answer table contracts.
3. Create `answer_evidence_links`.
4. Run a few section 1-8 questions against structured tables.

Completes/starts: D23-D27 for structured questions.

### Phase G — ruler-period/evaluator evidence

1. Create `ruler_period_goals`.
2. Create `ruler_period_goal_implementation`.
3. Create crisis, appointment, and corruption-case tables.
4. Store evaluator outputs with citations and confidence.

Completes/starts: D18-D22 and ruler-period parts of D25-D27.

### Phase H — scoring and review

1. Aggregate question answers into category scores.
2. Write score rows.
3. Write manual-review rows.
4. Produce drill-down reports showing score -> question answers -> evidence.

Completes/starts: D28-D30.

## Questions already well supported by table plan

- GDP, population, HDI, conflict counts, military spending, corruption, political
  freedom, repression, and nuclear arsenal questions are well suited to structured
  country-year tables.
- “Who ruled this country in this year?” is well suited to the identity tables.
- “Did this ruler achieve their goals?” needs ruler-period goals and evaluator
  evidence, not just country-year numbers.
- “Was this ruler honest, corrupt, adaptive, or reckless?” often needs
  evaluator/manual/web evidence plus structured context.

## Important rule

Do not delay all progress until every table exists. Build in this order:

1. identity;
2. normalized observations;
3. first harmonized fact tables;
4. first question-answer rows;
5. ruler-period evaluator tables;
6. scores.

## Project-manager review notes — runner-first alignment

These notes were added after review of this plan against the current
slice-first research-runner goal.

### Agreement with the full scope

The broad scope in this document is directionally correct and should remain in
view. We do want the full durable database layer: identity/scope tables,
normalized observations, harmonized topic tables, question-answer rows,
evaluator/manual evidence, evidence links, score aggregation, and review queues.
The goal is not merely to answer one question; the goal is to make the system
able to run many questions, countries, years, rulers, and scoring passes from a
stable database foundation.

The table roadmap here is therefore useful as the long-term data model / data
warehouse plan.

### Main adjustment: add the generic runner as a first-class infrastructure layer

The plan should explicitly include the research execution layer, not only the
tables. The immediate validation target is:

```text
question_id + scope
  -> strategy dispatch
  -> evidence gathering from any relevant source/mechanism
  -> persisted answers/evidence links
  -> queryable tables/views
```

This runner must not be source-specific and must not require new bespoke code for
each individual query. A single question/year/all-countries slice is only a test
shape for the infrastructure, not the product scope. Once one Slice 1 case runs,
we should vary the question/year repeatedly and record whether the generic system
runs or which infrastructure gap blocks it.

Suggested additional infrastructure phase:

| Phase | Name | What must be available |
|---:|---|---|
| **I7.5** | Question execution strategy registry / runner | A generic `run_question(question_id, scope)` path that reads question metadata, selects an evidence strategy, gathers structured/internet/manual evidence as needed, writes persisted answers/evidence links, and returns explicit infrastructure gaps instead of crashing. |

Each question registry row should eventually carry enough metadata for this
runner, for example:

```text
question_id
answer_scope_type        -- country_year, ruler_year, ruler_period
answer_type              -- boolean, numeric, categorical, text, score, json
evidence_strategy        -- structured, structured_plus_context, internet/manual, hybrid, unsupported
structured_concepts
allowed_sources
proxy_policy
handler_key / strategy_key
manual_review_policy
internet_research_required
```

### Do not make one-off question handlers the normal path

The current Q2.1 implementation is acceptable as the first proving handler, but
the next work should avoid creating one permanent bespoke module per question.
Instead, Q2.1 should be used to harden the generic runner, result persistence,
coverage reporting, and strategy dispatch. New question-specific code should only
be added when it represents a reusable strategy class or a genuinely unique
research method.

### Harmonized tables are valuable, but should not be the only evidence route

The harmonized country-year tables in D8-D17 are useful and should be built.
They will make repeated visualizations and structured questions much easier.
However, the runner should be able to answer or mark gaps from multiple evidence
routes:

- direct `normalized_observations`;
- harmonized fact tables where available;
- ruler/country/year identity tables;
- proxy-year policies;
- internet/manual/evaluator records;
- explicit missing/manual-review outcomes.

Therefore, harmonized tables are important infrastructure, but not the only path
to question answers.

### Answer table shape: generic table first, views/specific tables later

This plan lists possible specific tables such as
`country_year_question_answers`, `ruler_year_question_answers`, and
`ruler_period_question_answers`. That separation may be useful later, but the
current implementation has started with a generic persisted results layer:

```text
research_questions
research_question_answers
research_answer_evidence_links
chapter_scores
```

Recommendation: keep the generic table as the write target first, with explicit
scope fields such as:

```text
answer_scope_type
year
iso3
ruler_id
ruler_name
period_start
period_end
```

Then expose specific dashboard-friendly views later:

```text
country_year_question_answers_view
ruler_year_question_answers_view
ruler_period_question_answers_view
```

This avoids premature schema fragmentation while still supporting the specific
query shapes the product needs.

### Priority implications

For immediate Slice 1 stabilization, the most important gaps are:

1. **I1 database bootstrap/readiness** — default DB path and friendly readiness
   checks must be reliable.
2. **I7 methodology question registry** — the markdown question bank needs
   structured executable metadata.
3. **I7.5 generic runner/strategy dispatch** — `question_id + scope` should run
   or return explicit infrastructure gaps.
4. **I2 evidence coverage reporting** — know what is actually loaded into
   `normalized_observations`, by source/indicator/year/country.
5. **I10 evaluator/internet/manual evidence storage** — required for randomized
   1B-8B Slice 1 tests.
6. **I5/I6 harmonized concepts/fact tables** — important for scale and visuals,
   but should serve the generic runner rather than replace it.

### Bottom line

Keep this full table plan. It is the right long-term scope. The requested change
is to make the generic question runner and strategy registry explicit peers of
the table work, because the system is successful only when new question/year/scope
runs are parameter changes, not new bespoke implementations.
