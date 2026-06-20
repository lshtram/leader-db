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

Deliverables:

1. Experimental module under `src/leaders_db/vertical_slice/country_year_chronicle.py`
   or a dedicated `src/leaders_db/country_year/` package if the design stabilizes.
2. CLI command, tentatively:

   ```bash
   leaders-db run-country-year-chronicle \
     --start-year 1900 \
     --end-year 2026 \
     --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
     --output data/outputs/country-year-chronicle/pilot.csv
   ```

3. CSV output with source/proxy/confidence fields.
4. Focused pytest coverage for row shape, source precedence, proxy flags,
   regime/system classification, and CLI boundary wiring.

Exit criteria:

- Pilot CSV writes deterministically.
- Missing historical fields are flagged, not fabricated.
- Source attribution block is present.
- Tests and ruff pass.

### Increment 2 — all countries, reliable recent window

Mode: fast path with reviewer gate.

Scope:

- All resolvable country-years for `1960-2026`.
- Prioritize WDI-supported fields and existing leader/regime sources.

Deliverables:

1. Replace hard-coded pilot list with configurable country selection.
2. Write all-country recent-window CSV.
3. Add summary artifact with row counts, missingness by field, and top data-quality
   flags.
4. Add manual review report for rows with missing rulers, source conflicts, or
   successor-state issues.

Exit criteria:

- All-country `1960-2026` run completes locally.
- Missingness report is understandable.
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

Start **Increment 1** after user confirmation:

1. Implement an experimental read-only CSV vertical slice for
   `USA,GBR,FRA,IND,RUS,SUN,CHN` over 1900-2026.
2. Use V-Dem first for political-regime buckets and WDI first for 1960+ economic
   fields.
3. Emit missing/proxy/source-gap flags rather than fabricating pre-1960 GDP,
   missing area, or unresolved ruler data.
4. Add tests for row shape, regime mapping, system-type fallback, source/proxy
   flags, attribution block, and CLI boundary wiring.
