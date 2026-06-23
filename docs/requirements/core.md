# Requirements - Core

This document is the locally tracked REQ-* / NFR-* baseline derived from the authoritative product brief [`top-level-requirements.md`](top-level-requirements.md). Section numbers in parentheses reference the brief.

## Functional Requirements

### Scope and data collection (§2)

- **REQ-SCOPE-001**: System shall collect data for one target year at a time.
- **REQ-SCOPE-002**: Initial target year shall be 2023.
- **REQ-SCOPE-003**: System shall identify countries above the project population threshold, initially matching the client's 2023 approach.
- **REQ-SCOPE-004**: System shall identify the actual ruler or dominant ruling figure for each country-year.
- **REQ-SCOPE-005**: System shall generate provisional category scores for each ruler.
- **REQ-SCOPE-006**: System shall compare generated values against the existing client matrix for 2023.
- **REQ-SCOPE-007**: System shall store all data in a structured relational database.
- **REQ-SCOPE-008**: System shall keep raw downloaded datasets locally to avoid repeated online fetching.
- **REQ-SCOPE-009**: System shall track sources, versions, licenses, download dates, and transformation scripts.
- **REQ-SCOPE-010**: System shall produce confidence scores and validation flags for each important item.

### Guiding principle (§3)

- **REQ-REF-001**: The client matrix shall be treated as a manual reference dataset, not as ground truth.
- **REQ-REF-002**: The system shall separate: factual data, external indicators, inferred judgments, LLM-generated analysis, human-reviewed final values, confidence scores, source references, and disagreements.
- **REQ-REF-003**: The system shall never silently overwrite a client value.
- **REQ-REF-004**: The client/customer 2023 matrix shall not be counted as an independent data source for factual claims, leader identity, category scoring, source-agreement confidence, or source-authority confidence. It may be used only as a validation/test reference, comparison baseline, delta source, and manual-review trigger.

### Entities (§4)

- **REQ-ENT-001**: System shall collect country-year records (name, ISO3, population, GDP, GDP per capita, region, sovereignty/dependency status, inclusion status, notes on matching problems).
- **REQ-ENT-002**: System shall collect ruler records (full name, alternative spellings, country, office/title, start date, end date, in-office-during-target-year flag, actual-vs-formal flag, shared-rule flag, disputed-rule flag, ruler-type classification, source agreement status, confidence score).
- **REQ-ENT-003**: System shall collect ruler-year score records for each of the ten categories listed in §4 (nuclear responsibility, international peace, domestic safety, political freedom, economic well-being, social well-being, integrity, effectiveness, power retention [optional], global influence [optional]).

### Local data lake (§5)

- **REQ-LAKE-001**: System shall maintain the `data/raw/<source>/`, `data/processed/`, `data/interim/`, `data/outputs/`, `data/logs/`, `data/metadata/` folder layout.
- **REQ-LAKE-002**: Each `data/raw/<source>/` folder shall contain the original downloaded file and a `metadata.json` with source name, version, download date, source URL, license, checksum, ingestion status, coverage limits.
- **REQ-LAKE-003**: Each implemented source shall have a complete source-location trail: raw path, metadata file, indicator catalog, adapter entrypoint, processed output location, run manifest, DB `source_observations` rows, source-row locator pattern, and tests/fixtures.
- **REQ-LAKE-004**: Every source observation used in a score shall be traceable back to a raw row, cell, API record, or document locator; missing locator information shall block high-confidence scoring for that observation.

### Priority datasets (§6)

- **REQ-SRC-001**: Leader identity sources shall include Archigos, Leader Survival / Political Leaders through Time, REIGN, with fallback to CIA World Leaders, Rulers.org, and Wikidata/Wikipedia. The client matrix is excluded from this source set and is used only as the validation reference.
- **REQ-SRC-002**: Political freedom sources shall include V-Dem, Freedom House, EIU / Polity / BMR where available.
- **REQ-SRC-003**: Economic sources shall include World Bank WDI, IMF where available, Penn World Table / Maddison later.
- **REQ-SRC-004**: Governance / effectiveness sources shall include World Bank WGI, BTI Governance Index where available, V-Dem governance/executive-constraint/state-capacity indicators.
- **REQ-SRC-005**: Corruption / integrity sources shall include Transparency International CPI, WGI Control of Corruption, V-Dem corruption indicators.
- **REQ-SRC-006**: Conflict / international aggression sources shall include UCDP, COW/MID, SIPRI military expenditure / arms transfer data.
- **REQ-SRC-007**: Domestic repression / violence sources shall include Political Terror Scale, CIRIGHTS, ACLED or UCDP one-sided violence where available.
- **REQ-SRC-008**: Nuclear / global responsibility sources shall include FAS nuclear forces, SIPRI nuclear forces / military expenditure, NTI country profiles.

### Database schema (§7)

- **REQ-DB-001**: System shall use PostgreSQL or SQLite for the prototype. PostgreSQL is preferred if the system will become a webapp.
- **REQ-DB-002**: System shall implement the 11 core tables: `countries`, `country_years`, `leaders`, `leader_aliases`, `ruler_spells`, `ruler_years`, `score_categories`, `ruler_scores`, `sources`, `source_observations`, `validation_results` — with the column definitions from §7.
- **REQ-DB-003**: `ruler_scores` shall always carry `client_score`, `system_proposed_score`, `final_score`, and `score_delta_vs_client` as separate fields.

### Pipeline stages (§8)

- **REQ-STAGE-001**: Stage 0 shall probe each priority dataset for download availability and emit `outputs/source_availability_report.{csv,md}`.
- **REQ-STAGE-002**: Stage 1 shall load the client's existing 2023 matrix as a validation/reference artifact and emit `processed/client_2023_matrix_normalized.csv`; Stage 1 output shall not populate `source_observations` as an independent evidence source.
- **REQ-STAGE-003**: Stage 2 shall provide one ingestion script per source, normalizing country names, ISO codes, and year fields, writing to `source_observations`, and logging missing or unmatched countries.
- **REQ-STAGE-004**: Stage 3 shall use ISO3 as primary key, maintain a country alias table, handle historical country names and name changes, and never silently merge ambiguous countries.
- **REQ-STAGE-005**: Stage 4 shall resolve the actual ruler per country-year using the match statuses from §4 (`exact_match`, `name_variant_match`, `different_formal_same_actual`, `multiple_possible_rulers`, `client_only`, `external_only`, `conflict_between_sources`, `manual_review_required`) and the rules from §4 (≥2 agreeing structured sources ⇒ high confidence; client vs structured disagreement ⇒ keep both and flag review; president+PM coexistence ⇒ actual-ruler decision via dataset coding and office power; junta/shared leadership ⇒ multiple leaders or composite).
- **REQ-STAGE-006**: Stage 5 shall build per-category evidence bundles per ruler-year from the category source plan, including expected sources, available observations, missing observations, proxy/stale observations, not-applicable indicators, raw locators, normalized values, and category-specific metadata.
- **REQ-STAGE-007**: Stage 5 shall distinguish missingness reasons, including source not implemented, raw file absent, country row absent, target year absent, indicator null, not applicable, blocked/paywalled, and intentionally excluded by configuration.
- **REQ-STAGE-008**: Stages 6-10 shall normalize heterogeneous raw indicators into comparable signals, preserve direction and scale metadata, and combine multiple indicators through category-specific deterministic scoring functions rather than single-number pass-throughs.

### Score-generation logic (§9)

- **REQ-SCORE-001**: System shall not overwrite the client score.
- **REQ-SCORE-002**: For each category, system shall collect indicators, normalize to a 0–1 or 1–10 scale, apply the category rubric, generate the proposed score, compute the delta vs client, create a rationale, and flag high-delta cases for review.
- **REQ-SCORE-003**: Each category scorer shall consume an explicit evidence bundle, not ad hoc database lookups or a single raw value, and shall emit the score, normalized indicator contributions, source weights, missingness notes, disagreement notes, and rationale.
- **REQ-SCORE-004**: Category source plans shall define required, preferred, and fallback indicators; minimum viable source thresholds; default weights; directionality; accepted proxy-year rules; and whether sparse data should produce a low-confidence provisional score or `insufficient_data`.
- **REQ-SCORE-005**: Scorers shall never silently average incompatible indicators or silently drop conflicting indicators. Conflicts shall reduce source agreement confidence and, when material, trigger manual review.
- **REQ-SCORE-006**: The current vertical-slice single-source formulas are provisional plumbing checks only. The main pipeline shall replace them with evidence-bundle based scorers before broad category validation.

### LLM use (§10)

- **REQ-LLM-001**: LLM calls shall be used only where structured data is insufficient.
- **REQ-LLM-002**: Each LLM scoring call shall include: country, year, leader candidate, category, relevant structured indicators, client score if available, client note if available, up to three evidence snippets, rubric description, required output JSON schema.
- **REQ-LLM-003**: Required LLM output format shall be a JSON object with fields: `proposed_score` (int), `confidence` (int 0–100), `rationale` (str), `main_supporting_evidence` (list of str), `main_contradicting_evidence` (list of str), `human_review_required` (bool), `review_reason` (str).
- **REQ-LLM-004**: LLM shall never invent scores, replace structured datasets, cite sources not given, silently resolve ambiguous leader identity, or fetch large datasets repeatedly when local data exists.
- **REQ-LLM-005**: Level 1 LLM adjudication shall be constrained to the assembled evidence bundle, rubric, and provided snippets only; it shall not browse the web or use undocumented facts.
- **REQ-LLM-006**: Level 2 external LLM research may be added only behind an explicit configuration flag after Level 1 is implemented and reviewed. Any externally researched claim shall be stored as a cited evidence snippet with URL or bibliographic reference, quote/claim text, retrieval date, relevance, and source type.
- **REQ-LLM-007**: LLM outputs shall be treated as adjudication/rationale support and manual-review input, not as equivalent to structured datasets or a source-authority shortcut.

### Confidence score (§11)

- **REQ-CONF-001**: System shall compute confidence as `0.35 * source_agreement_score + 0.25 * source_authority_score + 0.25 * evidence_specificity_score + 0.15 * temporal_fit_score`.
- **REQ-CONF-002**: Component values shall follow the 0/20/40/60/80/100 scales from §11.
- **REQ-CONF-003**: Confidence bands shall be 85–100 high, 70–84 good, 50–69 medium, 30–49 low, 0–29 unreliable/manual review.
- **REQ-CONF-004**: Confidence components shall be derived from evidence bundles: source agreement from normalized indicator consistency, authority from available independent source quality, specificity from country/year/ruler/category fit, and temporal fit from direct-year/proxy/stale status.
- **REQ-CONF-005**: Missing expected indicators shall affect confidence and review status according to the category source plan; missingness shall not be hidden by normalizing only the available indicators.
- **REQ-CONF-006**: The client/customer matrix shall never improve source agreement, source authority, evidence specificity, or temporal-fit confidence components.

### Comparison against client 2023 matrix (§12)

- **REQ-CMP-001**: System shall produce per-country comparisons (client leader vs system leader, start year vs external tenure, per-category scores vs client, per-category deltas, average delta, per-item confidence, missing data, disputed data, manual review required).
- **REQ-CMP-002**: System shall emit `outputs/validation_2023_leader_identity.csv`, `outputs/validation_2023_scores.csv`, `outputs/validation_2023_summary.md`, `outputs/validation_2023_high_delta_cases.csv`, `outputs/validation_2023_manual_review_queue.csv`.
- **REQ-CMP-003**: Summary metrics shall include number of countries processed, exact matches, alias matches, conflicts, missing external records, average score delta, highest and lowest agreement categories, high-confidence and low-confidence counts, manual-review count.

### Older years (§13)

- **REQ-HIST-001**: System shall support older years with graceful degradation (fewer indicators, more uncertainty, more manual review, more reliance on historical leader datasets, more confidence penalties, more "not available" fields).
- **REQ-HIST-002**: System shall never fill missing historical data with invented values.

### Review workflow (§14)

- **REQ-REV-001**: Each ruler-year shall carry exactly one review status from: `auto_high_confidence`, `auto_medium_confidence`, `manual_review_required`, `reviewed_accepted`, `reviewed_modified`, `rejected`, `insufficient_data`.
- **REQ-REV-002**: Manual review queue shall prioritize: leader identity mismatch, category score delta > 2, confidence < 60, multiple possible rulers, missing primary sources, nuclear/global responsibility cases, war/aggression cases, severe human-rights/repression cases, strong disagreement with client matrix.

### Stack (§15)

- **REQ-STACK-001**: Implementation shall use Python, pandas (polars optional later), PostgreSQL or SQLite, SQLAlchemy, Pydantic, pytest, DuckDB optional, Jupyter optional, LLM API wrapper with strict JSON output, Streamlit optional later.
- **REQ-STACK-002**: Repository structure shall follow §15 (`src/{config,ingest,normalize,resolve,score,validate,llm,export}/`).

### Acceptance (§16)

- **REQ-ACC-001**: First prototype shall load the client's 2023 matrix.
- **REQ-ACC-002**: First prototype shall download or ingest local copies of the priority datasets.
- **REQ-ACC-003**: First prototype shall normalize countries and years.
- **REQ-ACC-004**: First prototype shall resolve 2023 rulers for at least 50 countries (preferably all client-scored countries).
- **REQ-ACC-005**: First prototype shall compare system-selected rulers against the client's leaders.
- **REQ-ACC-006**: First prototype shall generate provisional scores for at least four categories: political freedom, economic well-being, integrity/corruption, domestic violence/repression.
- **REQ-ACC-007**: First prototype shall produce confidence scores for every generated item.
- **REQ-ACC-008**: First prototype shall produce a manual-review queue.
- **REQ-ACC-009**: First prototype shall produce a summary report showing agreement and disagreement with the client matrix.
- **REQ-ACC-010**: First prototype shall keep all raw source data and transformed data reproducible.
- **REQ-ACC-011**: First prototype shall avoid silent overwriting of client values.
- **REQ-ACC-012**: First prototype shall avoid unsupported LLM-generated facts.
- **REQ-ACC-013**: First evidence-bundle prototype shall prove at least one all/mostly-available case, one mixed-direction multi-indicator case, one missing-primary-source case, one source-conflict case, and one stale/proxy-year case before broad client-matrix validation is trusted.
- **REQ-ACC-014**: First evidence-bundle prototype shall expose enough output detail for a reviewer to locate every contributing raw source value and every missing expected value for each generated score.

## Non-Functional Requirements

- **NFR-REPRO-001**: Runs must be reproducible from stored artifacts, configs, and source provenance.
- **NFR-MOD-001**: Data ingest, normalization, resolution, scoring, confidence, validation, and reporting modules must remain independently testable.
- **NFR-AUDIT-001**: Every generated item must carry a confidence score, source provenance, and review status.
- **NFR-SAFE-001**: The LLM adapter must validate responses against the strict Pydantic schema before persisting.
- **NFR-SAFE-002**: Secrets and credentials must not be committed or written into reports, logs, or artifacts.
- **NFR-PERF-001**: Idempotent re-runs must not re-download already-cached source files unless the cache is explicitly invalidated.
- **NFR-EXT-001**: New external sources must be addable through a new adapter + a new `data/raw/<source>/` folder + a config entry, without changing core execution paths.

## Notes

- Detailed architecture and rationale live in [`../architecture/overview.md`](../architecture/overview.md).
- Schema details live in [`../architecture/database-schema.md`](../architecture/database-schema.md).
- Per-source provenance lives in [`../sources/registry.md`](../sources/registry.md).
- Future modules may split this file into `requirements-<module>.md` files as surface area grows.
