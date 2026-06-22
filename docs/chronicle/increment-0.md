# Country-Year Chronicle — Increment 0 Findings

Date: 2026-06-20

Sub-project: **Country-Year Chronicle** (`cyc`)

Mode: docs / investigation. No production code is implemented in this increment.

## 1. Increment 0 decision summary

Increment 0 confirms that the first CYC implementation should proceed as an
experimental CSV-producing vertical slice, not a schema migration.

Recommended first implementation target:

```text
leaders-db run-country-year-chronicle \
  --start-year 1900 \
  --end-year 2026 \
  --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
  --output data/outputs/country-year-chronicle/pilot.csv
```

Rationale for adding `IND` to the pilot:

- It exposes colonial/decolonization status logic without forcing full empire
  controlled-area modeling in MVP.
- It tests transition from colonial rule to independent country-year records.

Rationale for including both `RUS` and `SUN` in the pilot:

- CYC should model state identities explicitly from the beginning, rather than
  flattening Russia / Soviet Union / Russian Federation into one continuity line.
- Continuity can be represented later with a separate successor-state mapping.

The first implementation should emit rows for resolvable country-years and carry
flags for unresolved successor-state, colonial, or source-gap cases.

## 2. Local data inventory

### 2.1 Processed source artifacts currently available

The local `data/processed/` directory contains these parquet artifacts:

| Source | Processed artifact | Rows | Local year span | CYC relevance |
|---|---|---:|---|---|
| `vdem` | `vdem_country_year.parquet` | 179 | 2022 only in current processed artifact | Political regime bucket and political/system signals. Raw V-Dem supports 1789-2025 and can be re-run for more years. |
| `world_bank_wdi` | `wdi_country_year.parquet` | 217 | 2022 only in current processed artifact | Population, GDP, GDP per capita. API supports 1960+; current local processed output is one-year only. |
| `world_bank_wgi` | `wgi_country_year.parquet` | 214 | 2022 only | Governance context; not core MVP but useful later. |
| `undp_hdi` | `undp_hdi_country_year.parquet` | 1,023 | 2022 only in current processed artifact | Social context; not core MVP. Raw source covers 1990-2022. |
| `who_gho_api` | `who_gho_api_country_year.parquet` | 200 | 2022 only | Social context; not core MVP. |
| `bti` | `bti_country_year.parquet` | 137 | 2023 only | Governance/system context for recent years; biennial 2006-2026 raw. |
| `rsf_press_freedom` | `rsf_press_freedom_country_year.parquet` | 12,900 | 2002-2026 | Press-freedom sub-signal; can support political/system classification confidence. |
| `transparency_cpi` | `transparency_cpi_country_year.parquet` | 180 | 2022 only | Integrity context; not core MVP. |
| `cirights` | `cirights_country_year.parquet` | 195 | 2022 only | Rights/repression context; not core MVP. |
| `pts` | `pts_country_year.parquet` | 0 | none | Adapter exists but no local full processed rows in this checkout. |
| `ucdp` | `ucdp_country_year.parquet` | 124 | 2022 only | Conflict/military context, but not direct military spend. |
| `sipri_milex` | `sipri_milex_country_year.parquet` | 174 | 2022 only | Military spend. Raw metadata says canonical xlsx is not staged; local processed artifact is one-year output. |
| `fas` | `fas_country_year.parquet` | 9 | 2014 snapshot | Nuclear status context; not core MVP. |
| `archigos` | `archigos_leader_spell.parquet` | 0 | none | Adapter/schema available, but current processed artifact is empty. Raw data exists and supports historical leader spells. |
| `reign` | `reign_leader_month.parquet` | 0 | none | Adapter/schema available, but current processed artifact is empty. Raw data exists and supports 1950-2021 leader-month records. |

### 2.2 Local database state

The local SQLite catalog at `data/catalog/leaders_db.sqlite` exists and contains
the canonical prototype tables. Current counts observed during Increment 0:

| Table | Rows | CYC implication |
|---|---:|---|
| `countries` | 147 | Useful seed, but not full 1900-2026 country-year universe. |
| `country_years` | 3 | Only the previous narrow vertical slice; not enough for CYC. |
| `leaders` | 3 | Only previous narrow slice. |
| `ruler_spells` | 3 | Only previous narrow slice. |
| `ruler_years` | 3 | Only previous narrow slice. |
| `source_observations` | 34,051 | Useful evidence store, mostly from already-run Stage 2 outputs. |

Decision: CYC Increment 1 should build from processed parquet/raw adapters and
not assume the current DB has the needed country-year/ruler universe.

### 2.3 Raw source readiness notes

| Source | Raw local status | Metadata status | CYC implication |
|---|---|---|---|
| `vdem` | Raw v16 bundle is staged | `metadata.json` present | Ready for regime derivation across 1789-2025, subject to re-running adapter for requested years. |
| `world_bank_wdi` | API-backed cache exists | `metadata.json` present | Ready for 1960+ population/GDP by API/cache, but not 1900-1959. |
| `archigos` | `Archigos_4.1_stata14.dta` staged | `metadata.json` present | Ready for leader-spell extraction through 2015 after non-empty processing / resolver logic. |
| `reign` | `REIGN_2021_8.csv` staged | `metadata.json` present | Ready for leader-month extraction 1950-2021 after non-empty processing / resolver logic. |
| `wikidata_heads_of_state_government` | API/cache source configured | `metadata.json` present | Ready as fallback/current-source path, but historical completeness must be tested. |
| `wikipedia_search_extract` | API/cache source configured | `metadata.json` present | Narrative fallback only; not primary structured evidence. |
| `sipri_milex` | Metadata says canonical raw xlsx is not staged | `metadata.json` present | Local one-year processed output exists, but full 1949-2025 CYC military-spend run should wait for raw xlsx staging/metadata update. |
| `pwt` | `pwt1001.xlsx` is present | `metadata.json` missing | Potentially ready for 1950-2019 GDP/population, but must not be treated as canonical until metadata/source docs are updated and adapter is implemented. |
| `polity_v` | `p5v2018.sav` is present | `metadata.json` missing | Potentially ready for 1800-2018 political regime cross-check, but must not be treated as canonical until metadata/source docs are updated and adapter is implemented. |
| `leader_survival` | no raw data | no usable metadata | Still blocked on Demscore/manual gate. |
| `un_snaama` | `snaama_gdp_expenditure_current_usd.zip` is present | source not registered | Unvetted/unregistered; do not use until vetted and added to source registry/attributions. |

## 3. Ready / blocked matrix by target field

| Target field | Increment 1 readiness | Source plan | Notes |
|---|---|---|---|
| `year` | Ready | Generated range from CLI/config | Validate `start_year <= end_year`; default pilot 1900-2026. |
| `iso3` | Partially ready | CLI country list + source country mappings | Historical states such as `SUN` require explicit mapping support. |
| `country_name` | Partially ready | Current country table + source display names | Need state-identity table or curated mapping for historical entities. |
| `country_status` | MVP-ready with flags | Curated pilot mapping | Values should include `independent`, `colonial/dependent`, `successor_state`, `unknown`. |
| `region`, `subregion` | Partially ready | Existing source metadata / current country table | Accept missing for pilot if mapping not available. |
| `ruler_name` | Partially ready | Archigos for 1900-2015; REIGN for 1950-2021; Wikidata/Wikipedia fallback for gaps | Stage 4 full resolver is not implemented. Increment 1 needs a narrow read-only resolver or explicit placeholders with flags. |
| `ruler_title` | Partially ready | Wikidata/Wikipedia fallback, REIGN government type, curated pilot mapping | Archigos does not directly provide office title. |
| `ruler_type` | Partially ready | REIGN `government`, V-Dem regime, curated pilot mapping | Keep separate from `system_type_primary`. |
| `political_regime_bucket` | Ready for V-Dem years | V-Dem `v2x_regime`, `v2x_polyarchy`, `v2x_libdem` | V-Dem covers 1789-2025. 2026 needs proxy or unknown until source updates. |
| `political_regime_raw_score` | Ready for V-Dem years | Prefer `v2x_regime`; retain democracy indices as support | Thresholds/taxonomy must be documented/configured. |
| `system_type_primary` | MVP-ready as conservative classifier | Derived from regime bucket + curated country-period mapping + ruler/government hints | Emit `Unknown` / `Mixed / unclear` when unsupported. |
| `system_type_secondary` | MVP-ready as optional | Same as primary | Optional for state-capitalist/social-democratic nuance. |
| `population` | Ready for 1960+; blocked for 1900-1949; partial via PWT 1950-2019 after metadata | WDI 1960+; PWT candidate 1950-2019; Maddison candidate for 1900+ | Maddison Project Database 2023 should be vetted for 1900-1949 and broad historical coverage. |
| `gdp` | Ready for 1960+; blocked for 1900-1949; partial via PWT 1950-2019 after metadata | WDI current/constant GDP; PWT candidate; Maddison candidate | Must keep units/methodology explicit. |
| `gdp_per_capita` | Ready for 1960+; partial historical | WDI direct; PWT/MPD direct or derived | If derived, record `gdp_per_capita_method`. |
| `military_spend` | Partial | SIPRI processed 2022 only; SIPRI raw expected for 1949-2025 | Pre-1949 should be missing/flagged in MVP. |
| `country_area_km2` | Blocked for canonical run | Need vetted static area source | Candidate sources include SimpleMaps/CIA-derived country area or another ISO3 area table; must be vetted and attributed first. |
| `controlled_area_km2` | MVP-placeholder only | Equals `country_area_km2` when standard area exists, otherwise blank | Full imperial/controlled area deferred. Add `controlled_area_not_modeled` flag. |
| `data_quality_flags` | Ready | Deterministic row builder | Pipe-separated flags. |
| `row_confidence` | Ready as transparent MVP aggregate | Field availability + source confidence | Do not use fixed ruler-score formula unless promoted to main scoring pipeline. |
| `provenance_summary` | Ready | Row builder from field source columns | Short machine-readable summary, not a replacement for source-specific columns. |

## 4. Finalized Increment 1 CSV contract

Increment 1 should use the output contract below. It intentionally keeps source
and source-year fields next to each measured/classified value.

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

CSV writer requirements:

- write an attribution comment block before the header;
- preserve this exact column order;
- use empty fields for unavailable numeric/text values;
- use pipe-separated `data_quality_flags`;
- write atomically through a temporary file + rename;
- do not consult the client matrix.

## 5. Taxonomy decisions for Increment 1

### 5.1 Political regime bucket

Use V-Dem first because local raw coverage is 1789-2025.

Preferred initial mapping from V-Dem `v2x_regime`:

| V-Dem `v2x_regime` | Native meaning | CYC bucket |
|---:|---|---|
| 0 | Closed autocracy | `Authoritarian` |
| 1 | Electoral autocracy | `Hybrid regime` |
| 2 | Electoral democracy | `Flawed democracy` |
| 3 | Liberal democracy | `Full democracy` |

If `v2x_regime` is missing but democracy indices exist, use configured thresholds
on `v2x_polyarchy` / `v2x_libdem` and add a `regime_source_gap` or
`proxy_year_used` flag as appropriate. Exact threshold values should live in a
taxonomy/config module, not buried in row-building code.

For 2026, use 2025 V-Dem as a one-year proxy only if the CLI/config explicitly
allows proxy years; otherwise emit `Unknown` with `regime_source_gap`.

### 5.2 System type

Use conservative deterministic rules in Increment 1:

1. Known country-period mappings for obvious systems:
   - USSR/SUN during Soviet period -> `Communist one-party state`.
   - PRC/CHN after 1949 -> `Communist one-party state`, secondary
     `State-capitalist authoritarian system` for recent years only if configured.
   - India before independence in pilot -> `Colonial administration`.
2. Ruler/government hints where structured sources support them:
   - REIGN `government` values containing military/junta terms ->
     `Military dictatorship` when political bucket is not democratic.
   - monarchy terms -> `Monarchy`.
3. For democratic market economies, use `Liberal capitalist democracy` by default
   unless a curated country-period mapping marks `Social democracy`.
4. If no strong rule applies, emit `Mixed / unclear` or `Unknown` with low
   confidence.

Do not use an LLM for system classification in Increment 1.

## 6. New source candidates requiring vetting

These are candidates only. They are not approved CYC evidence until source
registry, attribution text, raw staging, metadata, adapter/tests, and review are
complete.

| Need | Candidate | Why it is useful | Increment 0 status |
|---|---|---|---|
| Historical GDP/population before WDI | Maddison Project Database 2023 | Public information says it covers 169 countries up to 2022 and long-run GDP per capita/population, with CC BY 4.0 attribution. | Candidate for first new source-vetting task. |
| 1950-2019 GDP/population cross-check | Penn World Table 10.01 | `pwt1001.xlsx` is already present locally and has Data sheet columns including `countrycode`, `country`, `year`, `pop`, `rgdpe`, `rgdpo`; observed year range 1950-2019 and 183 country codes. | Raw file present but metadata missing; adapter blocked until source docs/metadata are corrected. |
| Static country area | SimpleMaps country CSV or another ISO3 area source | Public page advertises ISO3 + area fields in km² and CC BY 4.0 for the basic CSV. | Candidate only; must vet licensing/download and attribution before use. |
| Historical country area / factbook values | CIA World Factbook archive | A third-party archive claims structured 1990-2025 Factbook fields including area, with public-domain original CIA data. | Candidate only; third-party transformation/license/provenance must be vetted carefully. |

## 7. Blockers and constraints

1. **No full 1900-2026 GDP/population coverage is ready today.** WDI starts in
   1960; PWT starts in 1950 but lacks metadata/adapter; Maddison/MPD needs vetting.
2. **No canonical static area source is ready today.** Area fields should be empty
   with `missing_area` until a vetted area source lands.
3. **No full leader resolver exists yet.** CYC Increment 1 needs a narrow read-only
   resolver or clear placeholder behavior. It must not silently treat client data
   as leader evidence.
4. **2026 regime values are not direct in V-Dem v16.** Use explicit proxy behavior
   or `Unknown`.
5. **Controlled/imperial area is not modeled in MVP.** Use the canonical flag
   spelling `controlled_area_not_modeled` consistently.
6. **PWT and Polity raw files are now visible locally but not canonical.** They
   need `metadata.json` and workplan/source-doc updates before adapters consume
   them as source-of-truth inputs.

## 8. Increment 1 acceptance criteria

Increment 1 is ready to start when these are accepted:

- CSV contract in §4 is stable.
- Pilot country list is `USA,GBR,FRA,IND,RUS,SUN,CHN` unless the user changes it.
- V-Dem is the first political-regime source.
- WDI is the first population/GDP source for 1960+.
- Pre-1960 population/GDP gaps are allowed in the pilot and must be flagged.
- Country area gaps are allowed in the pilot and must be flagged.
- Controlled-area logic is explicitly deferred and flagged.
- No LLM and no client matrix are used in Increment 1.

## 9. Recommended next work items

1. ✅ Implement Increment 1 as an experimental, read-only CSV vertical slice with
   tests and CLI boundary proof. Landed at `src/leaders_db/chronicle/` with the
   `leaders-db run-country-year-chronicle` CLI command. See
   [`increment-1.md`](increment-1.md)
   for the full Increment 1 implementation notes.
2. In parallel or immediately after, fix source hygiene for `pwt` and `polity_v`:
   add metadata and update blockers if the raw files are intended to be canonical.
3. Vet a static country-area source.
