# Country-Year Chronicle Workplan

## 1. Sub-project name

**Country-Year Chronicle** (`cyc`)

The Country-Year Chronicle is a new longitudinal vertical slice for `leaders-db`:

```text
country × year, 1900-2026
    -> ruler / ruling authority
    -> political regime bucket
    -> system / ideology classification
    -> population, GDP, GDP per capita
    -> military spend
    -> standard area and, later, controlled / imperial area
    -> source provenance, confidence, and data-quality flags
```

This slice complements the current 2023 ruler-scoring prototype by creating a
historical country-year profile backbone. It should remain provenance-first and
gap-tolerant: missing or uncertain historical data is represented explicitly, not
filled with invented values.

## 2. Product goal

Produce an auditable historical profile table that lets a researcher ask, for any
country-year from 1900 through 2026:

- who ruled or dominated the state that year;
- what type of political regime it had;
- what broad system / ideology classification best describes it;
- what its population, GDP, GDP per capita, military spend, and area were;
- which source supplied each field and how confident the system is;
- where the gaps, proxy years, successor-state problems, colonial-status issues,
  or disputed-rule cases are.

The first deliverable is a CSV-producing vertical slice. Database persistence can
come later after the output contract stabilizes.

## 3. Scope decisions accepted

### 3.1 Keep political regime and system type separate

The slice must not collapse governance openness and ideology/economic model into
one overloaded label.

Use these separate dimensions:

1. **Political regime bucket** — how power is obtained and constrained.
2. **System type** — broad institutional / ideological / economic-political
   character of the state.

Initial political-regime buckets:

- `Full democracy`
- `Flawed democracy`
- `Hybrid regime`
- `Authoritarian`
- `Unknown`

Initial system-type values:

- `Liberal capitalist democracy`
- `Social democracy`
- `Conservative capitalist democracy`
- `Communist one-party state`
- `Socialist / state-led economy`
- `State-capitalist authoritarian system`
- `Military dictatorship`
- `Personalist dictatorship`
- `Monarchy`
- `Theocracy`
- `Fascist / ultranationalist regime`
- `Colonial administration`
- `Single-party nationalist regime`
- `Transitional / provisional government`
- `Mixed / unclear`
- `Unknown`

These labels are classification outputs with confidence and notes, not claims of
perfect historical truth.

### 3.2 Defer full imperial / controlled-area logic

The first version includes both:

- `country_area_km2`
- `controlled_area_km2`

For MVP, `controlled_area_km2` may equal `country_area_km2` unless a specifically
sourced controlled-area value is available. Empire, colony, occupation, and
additional-territory handling is a later phase with explicit provenance.

### 3.3 Start as an experimental vertical slice

Do not start with a schema migration. First build a deterministic artifact under:

```text
data/outputs/country-year-chronicle/
```

Once the shape and source behavior are proven, decide whether to add canonical DB
tables or views.

## 4. Target output contract

Initial CSV:

```text
data/outputs/country-year-chronicle/country_year_chronicle_1900_2026.csv
```

Recommended columns:

```text
year
iso3
country_name
country_status
region
subregion

ruler_name
ruler_title
ruler_type
ruler_source
ruler_source_year_used
ruler_confidence
shared_rule_flag
disputed_rule_flag

political_regime_bucket
political_regime_raw_score
political_regime_source
political_regime_source_year_used
political_regime_confidence

system_type_primary
system_type_secondary
system_type_source
system_type_confidence
system_type_notes

population
population_source
population_source_year_used

gdp
gdp_unit
gdp_source
gdp_source_year_used

gdp_per_capita
gdp_per_capita_unit
gdp_per_capita_method

military_spend
military_spend_unit
military_spend_source
military_spend_source_year_used

country_area_km2
controlled_area_km2
area_source
area_source_year_used
controlled_area_note

data_quality_flags
row_confidence
provenance_summary
```

All public outputs must carry the applicable source-attribution block, matching
the normative text in `docs/source-attributions.md`.

## 5. Source strategy

Use already-vetted and already-ingested project sources where possible. Add new
sources only after vetting and local data-lake staging.

| Field group | First-choice sources | Notes |
|---|---|---|
| Country-year existence / country name | existing `countries` table, V-Dem country-year coverage, WDI country coverage | Needs successor-state and non-sovereign handling. |
| Ruler identity | Archigos, REIGN, Wikidata/Wikipedia fallback | PLT / Leader Survival remains blocked until raw data is staged. |
| Political regime bucket | V-Dem first; Polity V later when raw is staged | EIU-style labels are only recent; for 1900+ use a derived bucket and label it as such. |
| System type | classification layer from regime indicators + ruler/state metadata + curated mapping | Should carry confidence and notes. Avoid LLM unless explicitly gated. |
| Population | WDI for 1960+; historical population source for 1900-1959 | Historical source must be vetted before use. |
| GDP / GDP per capita | WDI recent; PWT / Maddison historical after staging | PWT is currently blocked on raw file placement. |
| Military spend | SIPRI milex for available years | Pre-SIPRI historical coverage will be sparse; use explicit missingness flags. |
| Area | static area source first; controlled-area source later | Imperial/controlled area is deferred. |

## 6. Confidence and flags

The Chronicle should expose uncertainty directly. Initial flags:

- `missing_ruler`
- `multiple_rulers`
- `shared_rule`
- `disputed_rule`
- `proxy_year_used`
- `missing_population`
- `missing_gdp`
- `missing_military_spend`
- `missing_area`
- `regime_source_gap`
- `system_type_low_confidence`
- `successor_state_issue`
- `colonial_status_issue`
- `controlled_area_not_modeled`
- `source_conflict`

`row_confidence` should initially be a simple transparent aggregate of field-level
availability/confidence, not the fixed ruler-score confidence formula unless this
is later promoted into the main scoring pipeline.

## 7. Implementation increments

### Increment 0 — requirements and source inventory

Mode: docs / investigation.

Status: **complete**. Findings are recorded in
[`country-year-chronicle-increment-0.md`](country-year-chronicle-increment-0.md).

Deliverables:

1. Confirm final output columns and label taxonomy.
2. Inventory existing processed data that can support CYC immediately.
3. Identify source gaps for 1900-1959 population/GDP and country area.
4. Add any new external datasets to `docs/data-sources.md` and
   `docs/source-attributions.md` only after vetting.

Exit criteria:

- Agreed CSV contract.
- Agreed first-country pilot list.
- Clear list of blocked vs ready sources.

### Increment 1 — pilot countries, 1900-2026

Mode: fast path if source contracts are clear; TDD if taxonomy or source joins are
still ambiguous.

Pilot country/state identities:

- United States
- United Kingdom
- France
- India, to expose colonial/decolonization status logic
- Russia / Russian Federation (`RUS`)
- Soviet Union (`SUN`), modeled as a separate historical state identity
- China / PRC / ROC handling (`CHN` first, with unresolved cases flagged)

Status: **complete (2026-06-20)**. See [`country-year-chronicle-increment-1.md`](country-year-chronicle-increment-1.md) for the full implementation notes.

Deliverables:

1. ✅ New package `src/leaders_db/chronicle/` with 11 focused modules
   (all ≤ 422 lines; the original 559-line `row_builder.py` was
   safely split into `row_builder.py` plus three private helpers
   `_formatters.py`, `_flags.py`, `_wdi_fields.py`):
   `__init__.py`, `constants.py`, `sources.py`, `regime.py`,
   `system_type.py`, `row_builder.py`, `csv_writer.py`, `runner.py`,
   `_formatters.py`, `_flags.py`, `_wdi_fields.py`.
2. ✅ CLI command:

   ```bash
   leaders-db run-country-year-chronicle \
     --start-year 1900 \
     --end-year 2026 \
     --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
     --output data/outputs/country-year-chronicle/pilot.csv
   ```

3. ✅ CSV output with source/proxy/confidence fields, attribution
   comment block, atomic write through tempfile + rename, and the
   exact column order from Increment 0 §4.
4. ✅ 124 focused pytest tests across 5 new test files.

Exit criteria:

- ✅ Pilot CSV writes deterministically.
- ✅ Missing historical fields are flagged, not fabricated.
- ✅ Source attribution block is present (drift-guarded against
  `docs/source-attributions.md`).
- ✅ Tests and ruff pass.

### Increment 2 — Maddison + ruler resolver (COMPLETED 2026-06-21)

Mode: fast path with reviewer gate.

Scope: ship Maddison Project Database 2023 as the canonical historical
real-economy source (1-2022 with a 2023 -> 2022 1-year-gap proxy) and a
narrow provenance-aware ruler resolver (Archigos through 2015, REIGN
1950-2021, no client matrix, no LLM). Wire both into the Chronicle row
builder so the pilot CSV carries real ruler identities and real
historical Maddison-backed economy fields.

Status: **complete (2026-06-21)**. See [`country-year-chronicle-increment-2.md`](country-year-chronicle-increment-2.md)
for the full implementation notes.

Deliverables:

1. ✅ Maddison Project Database 2023 Stage 2 adapter landed in
   `src/leaders_db/ingest/maddison_project*.py`. 47 focused tests in
   `tests/test_ingest_maddison_project.py`. Indicator catalog at
   `src/leaders_db/ingest/catalogs/maddison_project.csv` lists the
   three catalog indicators (gdppc, pop, derived total).
2. ✅ Maddison source hygiene complete: local
   `data/raw/maddison_project/metadata.json` written with the
   canonical SHA-256 of `mpd2023.xlsx`. The 4.9 MB xlsx bundle is
   gitignored per Always-On Rule #9.
3. ✅ Maddison integrated into Chronicle economy fields with the
   documented precedence (Maddison preferred 1900-2022, WDI preferred
   2023+, Maddison 2022 used as a 1-year-gap proxy only when WDI is
   missing for 2023+).
4. ✅ Provenance-aware ruler resolver in
   `src/leaders_db/chronicle/ruler_resolver.py` with a
   `_ruler_loader.py` helper. The resolver covers Archigos 1840-2015,
   REIGN 1950-2021 (leader-with-most-months heuristic), and emits
   `multiple_rulers` for years with more than one leader.
5. ✅ Row builder extended: new optional kwargs `maddison` and
   `ruler_resolver`; `missing_ruler` flag is no longer hard-coded for
   every row.
6. ✅ CLI command `leaders-db run-country-year-chronicle` runs end-to-
   end and produces a 889-row pilot CSV for the 7-country 1900-2026
   scope. End-of-run summary reports
   `sources_used = archigos, maddison_project, reign, sipri_milex,
   vdem` when all raw data is staged locally.
7. ✅ 22 focused pytest tests added (9 in
   `tests/test_chronicle_economy_fields.py`, 13 in
   `tests/test_chronicle_ruler_resolver.py`).
8. ✅ All 124 existing Increment 1 chronicle tests still pass. Full
   suite green at 1671 passing.

Exit criteria:

- ✅ Pilot CSV writes deterministically.
- ✅ Missing historical fields are flagged, not fabricated.
- ✅ Source attribution block is present (drift-guarded against
  `docs/source-attributions.md`).
- ✅ Tests and ruff pass.
- ✅ Maddison 2023 -> 2022 proxy is documented + tested.
- ✅ Ruler resolver uses no client matrix and no LLM (drift guards in
  tests).

### Increment 3 — SUN rulers + CShapes area + controlled-area fallback (COMPLETED 2026-06-21)

Mode: fast path with reviewer gate.

Scope: close the documented Increment 2 gaps for the Country-Year
Chronicle slice. (a) Add a curated Soviet-leaders spell list to
fill the SUN ruler gap (Archigos / REIGN do not carry a separate
SUN `ccode`). (b) Add CShapes 2.0 as the country-area source for
the pilot ISO3 set. (c) Populate `controlled_area_km2` with the
conservative fallback (controlled == country) and the explicit
`controlled_area_country_only` flag; imperial / dependency summing
remains deferred (no vetted dependency-controller mapping was
staged in this pass).

Status: **complete (2026-06-21)**. See
[`country-year-chronicle-increment-3.md`](country-year-chronicle-increment-3.md)
for the full implementation notes.

Deliverables:

1. ✅ New `data/raw/soviet_leaders_curated/soviet_leaders.csv` (8
   leader spells covering 1922-12-30 to 1991-12-25) plus
   `metadata.json` with the Wikipedia anchor URL, citation, and
   license note. The CSV is hand-curated and is byte-identical
   to the local raw file; the underlying Wikipedia facts are
   not copyrightable.
2. ✅ CShapes 2.0 downloaded to `data/raw/cshapes/CShapes-2.0.csv`
   (44.5 MB, SHA-256 verified, gitignored per Always-On Rule
   #9). New `metadata.json` with the canonical download URL,
   license (CC BY-NC-SA 4.0), and citation (Schvitz et al. 2022).
3. ✅ New `src/leaders_db/chronicle/_sun_ruler_loader.py` (89
   lines) and `src/leaders_db/chronicle/_area_source.py` (197
   lines).
4. ✅ `RulerResolver` extended with `_lookup_sun` that picks the
   leader with the most days in the requested year; transition
   years (1924, 1953, 1985) emit `multiple_rulers`.
5. ✅ Row builder extended with `cshapes` parameter; new
   `_populate_area_fields` helper; new flags
   `FLAG_AREA_PROXY_YEAR_USED` and
   `FLAG_CONTROLLED_AREA_COUNTRY_ONLY`.
6. ✅ CSV writer attribution map and SQLite sidecar map updated.
7. ✅ `docs/source-attributions.md` updated with the new Section
   1 entries (CShapes 2.0, Soviet leaders curated) plus the
   summary table rows.
8. ✅ 48 new focused pytest tests (18 SUN curated + 18 CShapes
   area + 6 attribution drift + 3 production wiring + 3
   fix-to-existing-tests); full suite green at 1757 passing
   (was 1709 at Increment 2 sign-off; +48 net).
9. ✅ `ruff check .` clean; `git diff --check` clean; pilot CSV
   and SQLite regenerated.

Exit criteria:

- ✅ SUN rows 1922-1991 carry real ruler names (Lenin, Stalin,
  Malenkov, Khrushchev, Brezhnev, Andropov, Chernenko,
  Gorbachev) with the `multiple_rulers` flag for transition
  years.
- ✅ Pilot country area populated for the entire 1886-2019
  CShapes coverage window plus the proxy years (2020+); 645 of
  645 in-window rows have a real `country_area_km2` value.
- ✅ `controlled_area_km2` populated with the conservative
  fallback for every row with country area;
  `controlled_area_country_only` flag emitted; imperial /
  dependency summing explicitly deferred per the Increment 4
  work item.
- ✅ No invented historical data; no LLM; no client matrix;
  source attribution carried forward in every public output.
- ✅ `pytest -q` and `ruff check .` pass; production wiring
  proven end-to-end.

### Increment 4 — all countries, reliable recent window

Mode: fast path with reviewer gate.

Scope:

- All resolvable country-years for `1960-2026`.
- Prioritize WDI-supported fields and existing leader/regime sources.
- Replace hard-coded pilot list with configurable country selection.
- Add summary artifact with row counts, missingness by field, and top data-quality
  flags.
- Add manual review report for rows with missing rulers, source conflicts, or
  successor-state issues.
- Stage and integrate the ICOW Colonial History dataset (download URL is broken
  on 2026-06-21; deferred to Increment 4 once a working URL or alternative
  source is identified) for `controlled_area_km2` imperial / dependency summing.

Deliverables:

1. Replace hard-coded pilot list with configurable country selection.
2. Write all-country recent-window CSV.
3. Add summary artifact with row counts, missingness by field, and top data-quality
   flags.
4. Add manual review report for rows with missing rulers, source conflicts, or
   successor-state issues.
5. Stage ICOW or alternative dependency-controller source and integrate the
   `controlled_area_km2` imperial / dependency summing.

Exit criteria:

- All-country `1960-2026` run completes locally.
- Missingness report is understandable.
- `controlled_area_km2` no longer uses the conservative fallback
  for the GBR / FRA / NLD / etc. imperial eras.
- Reviewer passes source attribution, provenance, and no-client-evidence checks.

### Increment 3 — extend to 1900

Mode: investigation plus implementation. Use TDD for any new adapter or canonical
source integration.

Deliverables:

1. Vet and stage historical population/GDP source(s), likely Maddison / OWID / PWT
   depending availability and licensing.
2. Implement adapters only for vetted, locally staged sources.
3. Extend run window to `1900-2026` for all countries where country-year existence
   can be resolved.
4. Add explicit handling for country transitions, e.g. USSR/Russia, Qing/ROC/PRC,
   colonial independence years, Germany splits/reunification.

Exit criteria:

- Full-range CSV exists.
- Pre-1960 coverage gaps are quantified.
- Successor-state caveats are visible in output flags and summary.

### Increment 4 — controlled / imperial area extension

Mode: design first; likely TDD after requirements approval.

Deliverables:

1. Define legal/administrative meaning of `controlled_area_km2`.
2. Decide whether colonies/dependencies appear as their own rows, metropole-owned
   area, or both.
3. Vet a historical territorial-control / empire-area source.
4. Add controlled-area fields without overwriting standard country area.

Exit criteria:

- Controlled-area definition is documented.
- Ambiguous empire/occupation cases carry notes and confidence.
- Standard country-area output remains stable.

## 8. Suggested first labels and derivations

### Political regime bucket

First implementation should derive buckets from V-Dem or Polity-like indicators
with documented thresholds. The output must indicate that the bucket is
project-derived, not necessarily a native source label.

Example placeholder direction:

```text
high democracy signal      -> Full democracy
medium-high signal         -> Flawed democracy
middle / competitive hybrid -> Hybrid regime
low signal                 -> Authoritarian
missing                    -> Unknown
```

Exact thresholds belong in config or a documented taxonomy file, not hard-coded
inside transformation logic.

### System type

First implementation can combine:

- institutional form from ruler/title/state metadata;
- regime bucket;
- curated country-year or country-period mappings for clearly defined systems;
- structured indicators where available.

The first pass should be conservative. If no strong rule applies, emit
`Mixed / unclear` or `Unknown` with a low confidence score.

## 9. Non-goals for the first implementation

- No invented historical values.
- No LLM browsing as a default data source.
- No client matrix use as evidence.
- No full database migration until the CSV contract stabilizes.
- No attempt to fully model empires, colonial areas, occupations, or disputed
  territorial control in MVP.
- No single combined `democracy-capitalist` field that mixes political openness,
  institutional form, and economic model.

## 10. Initial proof surfaces

Minimum tests / verification expected for code-bearing increments:

1. Unit tests for row construction and required columns.
2. Unit tests for political-regime bucket derivation.
3. Unit tests for system-type classification fallback behavior.
4. Unit tests for source precedence and proxy-year flags.
5. CLI boundary test proving the command writes through the production path.
6. Golden small CSV or parsed-row assertions for the five-country pilot.
7. Attribution-block test for public CSV output.
8. `pytest -q` or focused affected test command plus `ruff` before review.

## 11. Project-management routing

Risk classification: **medium-high**.

Reason:

- The first CSV slice is straightforward, but taxonomy and 1900-2026 historical
  coverage create ambiguity.
- Any new source adapter or schema migration increases risk.
- Controlled/imperial area is historically sensitive and should be designed
  before implementation.

Recommended process:

- Increment 0: docs / investigation.
- Increment 1: fast path if we keep it experimental and source contracts are
  explicit; reviewer gate required.
- Increment 2: fast path with reviewer gate.
- Increment 3: use TDD for new source adapters or if source joins require new
  canonical contracts.
- Increment 4: architecture/design review before implementation.

## 12. Open questions before coding

1. Do we want `system_type_primary` to be mostly curated in early versions, or do
   we require a purely source-derived taxonomy from day one?
2. Which historical GDP/population source should be vetted first for 1900-1959?
   Increment 0 recommends Maddison Project Database 2023.
3. Is standard country area enough for MVP, with `controlled_area_not_modeled`
   flagged for imperial cases?
4. Should the locally visible `pwt1001.xlsx` and `p5v2018.sav` be promoted to
   canonical raw sources by writing metadata and updating the active blockers?

## 13. Immediate next action

Start **Increment 2** after user confirmation:

1. Implement an experimental read-only CSV vertical slice for
   `USA,GBR,FRA,IND,RUS,SUN,CHN` over 1900-2026.
2. Use V-Dem first for political-regime buckets and WDI first for 1960+ economic
   fields.
3. Emit missing/proxy/source-gap flags rather than fabricating pre-1960 GDP,
   missing area, or unresolved ruler data.
4. Add tests for row shape, regime mapping, system-type fallback, source/proxy
   flags, attribution block, and CLI boundary wiring.
