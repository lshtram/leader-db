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

**Still missing / weak:**

- Not every adapter is guaranteed to write into `normalized_observations` in the
  current working DB.
- Some processed parquet files were observed empty even while raw files existed.
- We need a reliable source-coverage report for rows actually loaded into the DB.

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

**Still missing / weak:**

- `country_years` may be empty or incomplete.
- The in-scope universe must be explicit: years, country list, population
  threshold, exclusions, predecessor/successor country handling, and disputed
  country cases.

**Build tasks:**

1. Decide the first target range, for example 1900-2023 or a narrower pilot.
2. Populate `countries` with canonical ISO3 names and normalized names.
3. Generate `country_years` for all in-scope country/year pairs.
4. Add `included_in_project`, `inclusion_reason`, and confidence/coverage notes.
5. Produce a country-year coverage report.

**Done means:** for any target year, the system can list exactly which countries
should receive answers and which are excluded or uncertain.

**Unlocks:** D2, D8-D17, D24, D29.

#### I4 — Ruler identity layer

**Plain meaning:** for every country/year, identify the ruler or dominant ruling
figure we are evaluating.

**Already implemented:**

- Schema tables exist: `leaders`, `leader_aliases`, `ruler_spells`, and
  `ruler_years`.
- Raw/adapter support exists or is planned for Archigos, REIGN, Wikidata, and
  related leader sources.
- The project rules already distinguish actual ruler from formal officeholder.

**Still missing / weak:**

- `ruler_years` is currently noted as empty in the main workplan.
- The resolver must handle co-rulers, disputed rule, formal-only leaders, client
  name differences, and source disagreement.

**Build tasks:**

1. Populate `leaders` and aliases from available leader sources.
2. Populate `ruler_spells` with start/end dates, title, source dataset, actual vs
   formal status, shared/disputed flags, and confidence.
3. Expand spells into `ruler_years` for the country-year grid.
4. Store match status and confidence. Do not silently overwrite the client matrix
   leader string.
5. Produce a ruler identity coverage report: missing, disputed, multiple possible
   rulers, low confidence, and source conflicts.

**Done means:** every in-scope country/year has either a selected ruler row or an
explicit unresolved/manual-review marker.

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

**Still missing / weak:**

- We do not yet have builders for each major topic table.
- Builders must keep evidence traceability instead of flattening away sources.

**Build tasks:**

1. Define a standard output pattern for harmonized fact rows: country, year,
   concept, value, unit, source, source observation ids, confidence, warnings.
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
| **D1** | `countries` | One row per country, using ISO3 as the stable key. | All country and ruler questions. | I0 | Already in schema. Needs population/refresh check. |
| **D2** | `country_years` | One row per country per year in scope. | All chapter 1-8 country-year questions; all 1B-8B ruler-year questions need this as their calendar. | I1, I3 | Already in schema, but not fully populated. |
| **D3** | `leaders` | One row per ruler/person. | All 1B-8B ruler-quality questions. | I1, I4 | Already in schema. Needs population. |
| **D4** | `ruler_spells` | One row per leader’s period of rule. | All 1B-8B; especially period questions like 8B.10 and 5B.10. | I1, I2, I4 | Already in schema. Needs complete resolver/population. |
| **D5** | `ruler_years` | One row per ruler/country/year. | Main anchor for every 1B-8B answer. | I1, I3, I4 | Already in schema; current workplan says 0 rows. Highest priority gap. |
| **D6** | `sources` | Registry of datasets and source versions. | Evidence traceability for every answer. | I0, I1 | Already in schema. |
| **D7** | `normalized_observations` | Clean source observations in one shared format. | Base evidence for almost all structured questions. | I1, I2 | Already in schema. Needs reliable population and clear default DB path. |

### 2. Harmonized country-year fact tables

These are friendly analysis tables built from `normalized_observations`. They do
not replace source evidence; they make it easier to answer questions.

| Step | Table | Main fields | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D8** | `country_year_population` | population, source, year, confidence. | Section 5 context; denominators for per-capita metrics; inclusion threshold. | I1, I2, I3, I5, I6 | Partly supported via WDI population concept. |
| **D9** | `country_year_economy` | GDP, GDP per capita, GDP PPP, GNI, trade, FDI, inflation, unemployment, debt/fiscal where available. | 5. economic well-being; 5B.1-5B.10; 8B outcome checks for economic goals. | I1, I2, I3, I5, I6 | GDP/population/GDP total partly supported. More concepts needed. |
| **D10** | `country_year_social_development` | HDI, life expectancy, child mortality, immunization, schooling, literacy, inequality, poverty, services access. | 6. social well-being; 6B.1-6B.10; parts of 5. inclusive prosperity. | I1, I2, I3, I5, I6 | Adapters exist for several sources; not yet one harmonized table. |
| **D11** | `country_year_political_freedom` | democracy, suffrage, civil liberties, rule of law, press freedom, democratic institutions, Freedom House/Polity later. | 4. political freedom; 4B.1-4B.10. | I1, I2, I3, I5, I6 | Partly supported through V-Dem, BTI, RSF, Freedom House/Polity adapters. |
| **D12** | `country_year_domestic_safety` | PTS, physical integrity, torture, disappearances, killings, political imprisonment, one-sided violence, civil-society repression, incitement/manual marker. | 3. domestic safety; 3B.1-3B.10. | I1, I2, I3, I5, I6 | Partly supported through PTS, CIRIGHTS, UCDP, V-Dem. Incitement remains manual/web. |
| **D13** | `country_year_international_conflict` | state-based conflict, internationalized conflict, event counts, fatalities, conflict severity/frequency, peace agreement markers, aggressor/proxy markers later. | 2. peace/aggression; 2B.1-2B.10. | I1, I2, I3, I5, I6; I10 for role/proxy claims | UCDP/SIPRI partly supported. Aggressor/proxy role not ready. |
| **D14** | `country_year_military` | military spend, spend % GDP, spend per capita, spend % government budget. | 2.4-2.8 context; 2B.8; nuclear/security context. | I1, I2, I3, I5, I6 | Partly supported through SIPRI Milex. |
| **D15** | `country_year_corruption_integrity` | WGI corruption, V-Dem corruption, executive corruption, public-sector corruption, CPI score/source count/error. | 7. integrity; 7B.3-7B.10 support. | I1, I2, I3, I5, I6 | Partly supported through WGI, V-Dem, CPI. |
| **D16** | `country_year_governance_capacity` | WGI government effectiveness/rule of law/regulatory quality, BTI governance, V-Dem accountability/constraints. | 8. effectiveness background; 8B support; also 4 and 5B. | I1, I2, I3, I5, I6 | Partly supported. Needs concept harmonization. |
| **D17** | `country_year_nuclear_risk` | has nuclear weapons, total inventory, deployed warheads, stockpile, reserve, retired warheads, safeguards/treaties, modernization, threats/manual marker. | 1. nuclear/global risk; 1B.1-1B.10. | I1, I2, I3, I5, I6; I10 for rhetoric/doctrine/manual claims | Arsenal counts partly supported. Treaty/doctrine/threats need more infrastructure/sources. |

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
| **D23** | `methodology_questions` | Stores question ID, text, category, answer type, evidence strategy, and whether it is country-year, ruler-year, or ruler-period. | All sections 1-8 and 1B-8B. | I7 | Partly present as markdown only. Needs DB/registry sync. |
| **D24** | `country_year_question_answers` | One answer per country/year/question for the chapter 1-8 country-condition questions. | Sections 1-8. | I3, I5, I7, I8 | Partly related to current `research_question_answers`; needs final contract. |
| **D25** | `ruler_year_question_answers` | One answer per ruler/country/year/question for 1B-8B. | 1B-8B. | I4, I7, I8, I10 | Not fully supported. Current evaluator design points here. |
| **D26** | `ruler_period_question_answers` | One answer per ruler period/question, for questions that cannot honestly be answered one year at a time. | 5B.10, 6B.10, 8B.7-8B.10, many 1B/2B/7B questions. | I4, I7, I8, I9, I10 | Not supported yet. |
| **D27** | `answer_evidence_links` | Links each answer to exact source observations, web citations, quotes, local files, or manual evidence. | Required for all answer tables. | I8, I10 | Partly planned/current research engine references this. Needs formalization. |

### 5. Score and review tables

These consume the answer tables. They should not be built first.

| Step | Table | Purpose | Supports methodology questions | Needed infrastructure | Current support |
|---:|---|---|---|---|---|
| **D28** | `ruler_category_scores` / existing `ruler_scores` | Final per-ruler-year category scores, confidence, rationale, review status. | Aggregates 1B-8B into eight category scores. | I8, I11 | Existing `ruler_scores` schema exists, but scoring from answer tables is not ready. |
| **D29** | `country_category_scores` | Optional per-country-year category scores separate from ruler responsibility. | Aggregates sections 1-8. | I8, I11 | Not explicit today. Optional. |
| **D30** | `manual_review_items` | Queue uncertain, conflicting, missing, or high-impact answers for human review. | All sections. | I8, I10, I11 | Partly supported by validation/manual-review ideas, but not tied to new answer tables. |

## Suggested execution order

### Phase A — make the database usable

1. Confirm the default working SQLite path.
2. Add a friendly setup/check command if needed.
3. Confirm all migrations create `normalized_observations` and the research answer
   tables in a fresh database.
4. Run a tiny smoke query against the default DB without passing `--db-url`.

Blocks: D2-D30 if not done.

### Phase B — populate identity first

1. Populate `countries`.
2. Build `country_years` for the target range.
3. Populate `leaders`, `ruler_spells`, and `ruler_years` from available leader
   sources.
4. Produce an identity coverage report: missing countries/years, disputed rulers,
   shared rule, and low-confidence matches.

Completes/starts: D1-D5.

### Phase C — populate normalized observations

1. Run clean source ingestion for the highest-value structured sources already on
   disk.
2. Confirm `normalized_observations` has rows by source, country, year, indicator.
3. Produce a source coverage report for the methodology sections.

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
