# Prototype Requirements Document

## AI-Agent Data Collection System for Leaders Database

## 1. Purpose

Build a first prototype data collection and validation system for the Leaders Database. The system should collect, normalize, and validate data for a specific target year, starting with 2023 because the client already has an existing manually created study for that year. The prototype should produce a structured database of countries, actual rulers, leader tenures, external indicators, proposed category ratings, source evidence, validation status, confidence scores, and comparison against the client’s existing matrix.

The first prototype is not expected to fully replace human judgment. It should create a reliable pipeline that combines structured dataset ingestion, rule-based transformations, LLM-assisted interpretation, source comparison, confidence scoring, and human-review flags.

---

## 2. First prototype scope

### In scope

* Collect data for one target year at a time.
* Initial target year: 2023.
* Identify countries above the project population threshold, initially matching the client’s 2023 approach.
* Identify the actual ruler or dominant ruling figure for each country-year.
* Collect external indicators relevant to the project’s main scoring categories.
* Generate provisional category scores for each ruler.
* Compare generated values against the existing client matrix for 2023.
* Store all data in a structured relational database.
* Keep raw downloaded datasets locally to avoid repeated online fetching.
* Track sources, versions, licenses, download dates, and transformation scripts.
* Produce confidence scores and validation flags for each important item.

---

## 3. Guiding principle

The system should treat the client’s existing 2023 ratings as a “manual validation reference,” not as ground truth and not as an evidence source. The goal is to reproduce, challenge, explain, and validate the client’s matrix by comparing it with structured external datasets and documented evidence.

The client/customer 2023 matrix must never be counted as one of the independent data sources used to support a factual claim, leader identity, category score, source-agreement confidence component, or source-authority confidence component. It may be loaded only to preserve the customer-provided values for tests, regression validation, comparison reports, delta calculations, and manual-review prioritization.

The system should separate:

* factual data,
* external indicators,
* inferred judgments,
* LLM-generated analysis,
* human-reviewed final values,
* confidence scores,
* source references,
* and disagreements.

---

## 4. Main entities to collect

For each target year, the system should collect and store:

### Country-year record

* Country name
* ISO3 country code
* Year
* Population
* GDP
* GDP per capita where available
* Region
* Sovereignty / dependency status if available
* Inclusion status in project scope
* Notes on country matching problems

### Ruler record

* Leader full name
* Alternative spellings
* Country
* Office/title
* Start date
* End date
* Was leader in office during target year?
* Was leader the actual ruler or formal officeholder?
* Shared-rule flag
* Disputed-rule flag
* Junta / monarch / prime minister / president / supreme leader / party leader / military ruler classification
* Source agreement status
* Confidence score

### Ruler-year score record

For each ruler-year, collect or infer scores for the main project categories:

1 Global nuclear responsibility / global existential responsibility
2 International peace vs aggression and war
3 Domestic safety vs domestic violence, oppression, and incitement
4 Political freedom vs authoritarian rule
5 Economic well-being and prosperity
6 Social well-being and prosperity
7 Integrity and honesty
8 Effectiveness and competence
9 Optional separate field: power retention / political survival capacity
10 Optional separate field: global influence / military/economic/nuclear influence

---

## 5. Required local data lake

Before running the collection pipeline, the coding agent should create a local data lake structure.

Suggested folder structure:

```text
data/
  raw/
    archigos/
    leader_survival/
    reign/
    vdem/
    freedom_house/
    world_bank_wdi/
    world_bank_wgi/
    transparency_cpi/
    ucdp/
    cow_mid/
    political_terror_scale/
    cirights/
    sipri/
    fas/
    nti/
    client_existing/
  processed/
  interim/
  outputs/
  logs/
  metadata/
```

Each raw dataset folder should contain:

* original downloaded file
* source metadata JSON
* download date
* source URL
* source version
* license/terms note
* checksum
* ingestion status
* any known coverage limits

Example metadata file:

```json
{
  "source_name": "V-Dem",
  "source_version": "v16",
  "download_date": "YYYY-MM-DD",
  "coverage": "country-year",
  "years_available": "varies by country",
  "license_note": "check source terms",
  "local_files": ["vdem_country_year_v16.csv"],
  "ingestion_status": "downloaded"
}
```

---

## 6. Priority datasets for prototype

The agent should start with datasets that are structured, downloadable, and useful for 2023 validation.

### Leader identity sources

Use up to three sources per leader identity:

1. Archigos
2. Leader Survival Dataset / Political Leaders through Time
3. REIGN

Fallback/auxiliary sources:

* CIA World Leaders for current/recent leaders
* Rulers.org
* Wikidata/Wikipedia
* Client matrix

### Political freedom sources

Use:

1. V-Dem
2. Freedom House
3. EIU / Polity / BMR where available

### Economic sources

Use:

1. World Bank WDI
2. IMF where available
3. Penn World Table / Maddison for historical expansion later

### Governance / effectiveness sources

Use:

1. World Bank WGI
2. BTI Governance Index where available
3. V-Dem governance/executive constraint/state-capacity indicators

### Corruption / integrity sources

Use:

1. Transparency International CPI
2. World Bank WGI Control of Corruption
3. V-Dem corruption indicators

### Conflict / international aggression sources

Use:

1. UCDP
2. Correlates of War / MID
3. SIPRI military expenditure / arms transfer data

### Domestic repression / violence sources

Use:

1. Political Terror Scale
2. CIRIGHTS
3. ACLED or UCDP one-sided violence where available

### Nuclear / global responsibility sources

Use:

1. FAS nuclear forces
2. SIPRI nuclear forces / military expenditure
3. NTI country profiles

For the first prototype, nuclear/global responsibility may be a lighter module, because most countries are non-nuclear and because responsibility requires judgment beyond raw data.

---

## 7. Database schema: first version

Use PostgreSQL or SQLite for the prototype. PostgreSQL is preferred if the system will become a webapp.

### Core tables

#### `countries`

* `id`
* `iso3`
* `country_name`
* `country_name_normalized`
* `region`
* `notes`

#### `country_years`

* `id`
* `country_id`
* `year`
* `population`
* `gdp_current_usd`
* `gdp_per_capita`
* `included_in_project`
* `inclusion_reason`
* `source_confidence`

#### `leaders`

* `id`
* `full_name`
* `normalized_name`
* `birth_date`
* `death_date`
* `gender`
* `notes`

#### `leader_aliases`

* `id`
* `leader_id`
* `alias`
* `source_id`

#### `ruler_spells`

* `id`
* `leader_id`
* `country_id`
* `office_title`
* `start_date`
* `end_date`
* `source_dataset`
* `is_actual_ruler`
* `is_formal_leader`
* `rule_type`
* `shared_rule_flag`
* `disputed_rule_flag`
* `confidence_score`
* `notes`

#### `ruler_years`

* `id`
* `leader_id`
* `country_id`
* `year`
* `ruler_spell_id`
* `actual_ruler_status`
* `client_matrix_leader_name`
* `system_selected_leader_name`
* `match_status`
* `confidence_score`
* `review_status`
* `review_note`

#### `score_categories`

* `id`
* `category_key`
* `category_name`
* `description`
* `rubric_low`
* `rubric_mid`
* `rubric_high`

#### `ruler_scores`

* `id`
* `ruler_year_id`
* `category_id`
* `client_score`
* `system_proposed_score`
* `final_score`
* `score_delta_vs_client`
* `confidence_score`
* `source_agreement`
* `human_review_required`
* `rationale_short`
* `review_status`

#### `sources`

* `id`
* `source_name`
* `source_type`
* `source_url`
* `version`
* `license_note`
* `download_date`
* `coverage_start_year`
* `coverage_end_year`
* `notes`

#### `source_observations`

* `id`
* `source_id`
* `country_id`
* `leader_id`
* `year`
* `variable_name`
* `raw_value`
* `normalized_value`
* `unit`
* `source_row_reference`
* `confidence`
* `notes`

#### `validation_results`

* `id`
* `item_type`
* `item_id`
* `validation_status`
* `source_count`
* `source_agreement_score`
* `source_authority_score`
* `temporal_fit_score`
* `specificity_score`
* `final_confidence_score`
* `validation_note`

---

## 8. Pipeline stages

### Stage 0 — Source availability and download

The agent should first confirm that each assigned dataset is available and downloadable. If available, download a local copy. If not available, mark the dataset as unavailable and continue without blocking the entire pipeline.

Output:

```text
outputs/source_availability_report.csv
outputs/source_availability_report.md
```

Report fields:

* source name
* access method
* requires login?
* requires permission?
* downloaded successfully?
* local path
* version
* coverage
* license warning
* recommended use
* blocking/non-blocking issue

### Stage 1 — Ingest client data

Load the client’s existing 2023 matrix as the reference dataset.

Required extraction:

* country
* population
* external democracy/freedom/corruption values if present
* leader name
* leader start year
* all category scores
* notes
* existing source column
* inclusion/exclusion status

Output:

```text
processed/client_2023_matrix_normalized.csv
```

### Stage 2 — Ingest external structured datasets

Create one ingestion script per source.

Example scripts:

```text
src/ingest/ingest_archigos.py
src/ingest/ingest_leader_survival.py
src/ingest/ingest_reign.py
src/ingest/ingest_vdem.py
src/ingest/ingest_world_bank_wdi.py
src/ingest/ingest_world_bank_wgi.py
src/ingest/ingest_transparency_cpi.py
src/ingest/ingest_ucdp.py
src/ingest/ingest_pts.py
src/ingest/ingest_cirights.py
src/ingest/ingest_sipri.py
```

Each ingestion script should:

* load raw source file
* normalize country names and ISO codes
* normalize year fields
* write to `source_observations`
* log missing or unmatched countries
* preserve raw values

### Stage 3 — Country matching

Build a country-matching layer.

Requirements:

* Use ISO3 as primary key.
* Maintain a country alias table.
* Handle historical country names.
* Handle countries that changed names.
* Handle non-sovereign territories carefully.
* Do not silently merge ambiguous countries.

Output:

```text
outputs/country_matching_report.csv
```

### Stage 4 — Leader resolution

For each country-year:

1. Pull candidate leaders from Archigos, Leader Survival, REIGN, Wikidata/Wikipedia, and other external leader-identity sources.
2. Normalize leader names.
3. Compare names, dates, and office titles.
4. Select likely actual ruler.
5. Mark confidence and disagreement.

The client matrix leader string is loaded only as the validation reference for comparison and review flags; it is not evidence supporting the system-selected ruler.

Leader match statuses:

* `exact_match`
* `name_variant_match`
* `different_formal_same_actual`
* `multiple_possible_rulers`
* `client_only`
* `external_only`
* `conflict_between_sources`
* `manual_review_required`

Rules:

* If at least two structured sources agree on leader and dates, mark high confidence.
* If the client leader differs from structured sources, keep both and flag review.
* If a president and prime minister coexist, determine actual ruler based on dataset coding, office power, and country system.
* If junta/shared leadership exists, allow multiple leaders or a composite ruler record.

Output:

```text
outputs/leader_resolution_2023.csv
```

### Stage 5 — Indicator extraction

For each ruler-year, collect relevant country-year indicators.

Example indicators:

Political freedom:

* V-Dem liberal democracy index
* V-Dem electoral democracy index
* Freedom House total score
* Freedom House status
* EIU democracy score/class where available

Economic well-being:

* GDP growth
* GDP per capita
* inflation
* unemployment
* poverty rate where available

Social well-being:

* HDI
* life expectancy
* education indicators
* child mortality
* inequality / gender indicators where available

Integrity:

* Transparency CPI
* WGI Control of Corruption
* V-Dem corruption variables

Domestic violence:

* Political Terror Scale
* CIRIGHTS physical integrity variables
* UCDP one-sided violence or ACLED events where available

International peace/aggression:

* UCDP conflict involvement
* COW/MID dispute involvement
* SIPRI military expenditure as share of GDP/government expenditure

Effectiveness:

* WGI Government Effectiveness
* WGI Rule of Law
* BTI governance where available
* economic/social/political stability trend indicators

---

## 9. Score-generation logic

The system should generate provisional scores. It should not overwrite the client score.

For each category:

1. Collect indicator bundle.
2. Convert indicators to a normalized 0–1 or 1–10 scale.
3. Apply category rubric.
4. Generate proposed score.
5. Compare with client score.
6. Calculate delta.
7. Create rationale.
8. Flag high-delta cases for review.

### Score output example

```json
{
  "country": "Mexico",
  "year": 2023,
  "leader": "Andrés Manuel López Obrador",
  "category": "political_freedom",
  "client_score": 6,
  "system_proposed_score": 6,
  "score_delta": 0,
  "confidence_score": 78,
  "source_agreement": "medium_high",
  "rationale_short": "External democracy/freedom indicators show flawed but functioning democracy; concerns exist around institutions and judiciary.",
  "review_status": "not_reviewed"
}
```

---

## 10. LLM use

LLM calls should be used only where structured data is insufficient.

### Good uses of LLM

* Summarize source evidence for one leader/category.
* Explain why structured indicators may not capture leader-specific responsibility.
* Classify formal vs actual ruler in ambiguous cases.
* Generate short rationale text for a proposed score.
* Compare client notes with external evidence.
* Identify whether a score requires human review.
* Extract structured claims from a limited set of provided text snippets.

### Bad uses of LLM

* Inventing scores without sources.
* Replacing structured datasets.
* Citing sources it has not been given.
* Making final academic judgments without review.
* Fetching large datasets repeatedly when local data exists.
* Silently resolving ambiguous leader identity.

### LLM input requirements

Each LLM scoring call must include:

* country
* year
* leader candidate
* category
* relevant structured indicators
* client score if available
* client note if available
* up to three evidence snippets
* rubric description
* required output JSON schema

### Required LLM output format

```json
{
  "proposed_score": 0,
  "confidence": 0,
  "rationale": "",
  "main_supporting_evidence": [],
  "main_contradicting_evidence": [],
  "human_review_required": true,
  "review_reason": ""
}
```

---

## 11. Confidence score

Every important item should receive a confidence score from 0 to 100.

Suggested formula:

```text
confidence =
  0.35 * source_agreement_score +
  0.25 * source_authority_score +
  0.25 * evidence_specificity_score +
  0.15 * temporal_fit_score
```

### Component definitions

#### Source agreement score

* 100: three sources agree
* 80: two sources agree, third missing
* 60: sources broadly agree but differ in detail
* 40: sources partially conflict
* 20: major conflict
* 0: no external validation

#### Source authority score

* 100: structured academic/official dataset
* 80: reputable NGO or international organization dataset
* 60: reputable reference source
* 40: news/source text only
* 20: unclear source
* 0: no source

#### Evidence specificity score

* 100: directly about this leader/year/category
* 80: directly about this country/year/category
* 60: about leader tenure but not exact year
* 40: general country context
* 20: indirect proxy only
* 0: no relevant evidence

#### Temporal fit score

* 100: exact year
* 80: within one year
* 60: within leader tenure
* 40: near period but not exact
* 20: long-term historical context only
* 0: wrong period

Confidence bands:

* 85–100: high confidence
* 70–84: good confidence
* 50–69: medium confidence
* 30–49: low confidence
* 0–29: unreliable / manual review required

---

## 12. Comparison against client 2023 matrix

The prototype should produce a validation comparison report.

### Required comparisons

For each country:

* Client leader vs system leader
* Client leader start year vs external tenure data
* Client score vs system proposed score for each category
* Delta per category
* Overall average delta
* Confidence per item
* Missing data
* Disputed data
* Manual review required

### Required output files

```text
outputs/validation_2023_leader_identity.csv
outputs/validation_2023_scores.csv
outputs/validation_2023_summary.md
outputs/validation_2023_high_delta_cases.csv
outputs/validation_2023_manual_review_queue.csv
```

### Summary metrics

* number of countries processed
* number of leaders matched exactly
* number of leaders matched by alias
* number of leader conflicts
* number of missing external leader records
* average score delta vs client
* categories with highest agreement
* categories with lowest agreement
* number of high-confidence scores
* number of low-confidence scores
* number requiring manual review

---

## 13. Handling older years

The system should be designed from the start to support older years, but older years will be progressively harder.

### Expected difficulty by period

* 2000 onward: easiest; many datasets available.
* 1950–1999: moderate; many political/economic/conflict datasets available, but less current detail.
* 1900–1949: harder; leader identity and conflict data exist, but social/governance indicators are thinner.
* before 1900: out of first prototype scope.

### Historical data principle

For older years, the system should degrade gracefully:

* fewer structured indicators,
* more uncertainty,
* more manual review,
* more reliance on historical leader datasets,
* more confidence penalties,
* more explicit “not available” fields.

The system must never fill missing historical data with invented values.

---

## 14. Review workflow

Every generated ruler-year should have one of the following statuses:

* `auto_high_confidence`
* `auto_medium_confidence`
* `manual_review_required`
* `reviewed_accepted`
* `reviewed_modified`
* `rejected`
* `insufficient_data`

Manual review queue should prioritize:

* leader identity mismatch
* category score delta greater than 2 points
* confidence below 60
* multiple possible rulers
* missing primary sources
* nuclear/global responsibility cases
* war/aggression cases
* severe human-rights/repression cases
* strong disagreement with client matrix

---

## 15. Implementation recommendation

### Suggested stack

* Python
* pandas / polars
* PostgreSQL or SQLite
* SQLAlchemy
* Pydantic for schemas
* pytest for tests
* DuckDB optional for analytical processing
* Jupyter notebooks optional for exploration
* LLM API wrapper with strict JSON output
* Streamlit optional for simple review UI later

### Repository structure

```text
leaders-database/
  README.md
  requirements.txt
  pyproject.toml
  data/
  docs/
  src/
    config/
    ingest/
    normalize/
    resolve/
    score/
    validate/
    llm/
    export/
  tests/
  outputs/
```

---

## 16. Acceptance criteria for first prototype

The first prototype is successful if it can:

* Load the client’s 2023 matrix.
* Download or ingest local copies of the priority datasets.
* Normalize countries and years.
* Resolve 2023 rulers for at least 50 countries, preferably all client-scored countries.
* Compare system-selected rulers against the client’s leaders.
* Generate provisional scores for at least four categories:

  * political freedom,
  * economic well-being,
  * integrity/corruption,
  * domestic violence/repression.
* Produce confidence scores for every generated item.
* Produce a manual-review queue.
* Produce a summary report showing agreement and disagreement with the client matrix.
* Keep all raw source data and transformed data reproducible.
* Avoid silent overwriting of client values.
* Avoid unsupported LLM-generated facts.

---

## 17. First build sequence for the coding agent

1. Create repository structure.
2. Create database schema.
3. Create local data lake folders.
4. Ingest client 2023 matrix.
5. Build country normalization and ISO3 matching.
6. Download or register availability of priority datasets.
7. Ingest V-Dem, WDI, WGI, Transparency CPI, UCDP, PTS/CIRIGHTS.
8. Ingest leader datasets: Archigos, Leader Survival, REIGN.
9. Build leader resolver for 2023.
10. Build political freedom scoring module.
11. Build corruption/integrity scoring module.
12. Build economic well-being scoring module.
13. Build domestic violence/repression scoring module.
14. Build confidence scoring module.
15. Build comparison reports vs client matrix.
16. Build manual review queue.
17. Produce final prototype report.

---

## 18. Key design warning

The system should not be designed as “LLM researches each leader from scratch.” That would be expensive, slow, inconsistent, and hard to validate.

The correct design is:

```text
download structured datasets once
→ normalize them
→ match country/year/leader
→ compute source-backed indicators
→ generate provisional scores
→ use LLM only for ambiguous interpretation
→ compare with client matrix
→ assign confidence
→ send difficult cases to human review
```

This approach gives the project a much better chance of becoming a credible database rather than a collection of AI-generated political opinions.
