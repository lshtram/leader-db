# Research Engine Workplan

## Goal

Implement the complete research engine described in
[`architecture/research-engine.md`](architecture/research-engine.md): reusable
source evidence, persistent querying, concept/metric extraction, analytical
datasets, trend findings, reports, and Superset-ready outputs.

Implementation-level contracts live in
[`architecture/research-engine-implementation.md`](architecture/research-engine-implementation.md).

## Current base

Already available:

- local data lake;
- prototype database schema;
- unified source contracts;
- several clean source adapters;
- in-memory evidence repository;
- source concept catalog slice;
- visualization semantic layer;
- Superset local integration;
- GDP-per-capita investigation slice.

## Immediate execution strategy — Slice 1 stabilization

Status: active as of 2026-06-29.

The research engine now prioritizes reusable vertical-slice execution over
source-specific expansion. A vertical slice is defined by the research request,
not by an input database. The first slice family is:

```text
one question + one year + all in-scope countries
```

The same runner should be able to take different question/year pairs from
chapters 1-8 and 1B-8B, gather whatever evidence is needed, persist answer rows,
and expose queryable result tables without writing new bespoke code for each run.
When a run fails or requires code changes, the output of that iteration is an
infrastructure-gap list plus the smallest generic improvement needed before
rerunning.

Validation ladder for Slice 1:

1. run the current proving case (`question_id="2.1"`, one target year, all
   countries) end-to-end through generic orchestration;
2. rerun Slice 1 with several other structured chapter 1-8 questions/years;
3. rerun Slice 1 with several 1B-8B internet-research-heavy questions/years;
4. require that repeated Slice 1 cases run by changing request parameters, not by
   adding per-question code paths, except where a new generic capability is
   explicitly identified and implemented;
5. only after repeated Slice 1 cases are stable, move to Slice 2 (`one question +
   one country/ruler + all years`).

Immediate known infrastructure to inspect next:

- generic `run_question(question_id, years, countries/rulers)` orchestration;
- question registry coverage for methodology question IDs and expected answer
  types;
- generic dispatch from a question spec to structured evidence, internet
  research, or manual-review fallback;
- country/ruler scope injection for all-country runs;
- persistence into `research_question_answers` and evidence-link tables;
- repeatability/idempotency when the same slice is rerun with only parameters
  changed.

First infrastructure assessment (2026-06-29): before this iteration Q2.1 Slice 1
required hand assembly of country scope, evidence repository, answer builder, and
result persistence. `leaders_db.research.slice_runner.run_slice_1_question_year`
now provides the generic programmatic runner surface for `one question + one year
+ all or selected in-scope countries`, with Q2.1 registered as the first supported
handler and persistence routed through `research_question_answers`. Remaining
generic gaps for other Slice 1 questions are handler/spec coverage and dispatch
strategy for structured evidence versus internet-research/manual-review paths.

## Increment 1 — in-memory representative vertical slice

Status: implemented and reviewed on 2026-06-27.

Verification:

- `pytest -q tests/research` — passed, 5 tests.
- `ruff check src/leaders_db/research tests/research` — passed.
- Fresh reviewer result after implementation: PASS after this status update blocker
  was resolved; runtime behavior was already accepted as Increment 1 scoped.

Deliverables:

- minimal `src/leaders_db/research/` package with `models.py`, `planner.py`,
  `dataset_builder.py`, `runner.py`, and `artifacts.py`;
- `RowScope` for concrete row identity and `ScopeFilter` for multi-entity/range
  questions;
- fixture/in-memory evidence rows only; no new DB table yet;
- one structured question-bank example and one qualitative/acquisition-planning
  example;
- artifact output under `data/outputs/research/<run-id>/`.

Success check:

```text
fixture evidence can produce question.json, plan.json, evidence-gap-report.json,
analytical-dataset.csv, findings.json, and manifest.json with evidence traceability
```

Proof surface: `pytest -q tests/research` proves multi-value filters expand into
unambiguous row scopes and findings link to evidence row ids.

## Increment 2 — question/concept registry and planner rules

Status: implemented.

Deliverables:

- `QuestionSpec` and `ConceptSpec` registries;
- direct registered planning;
- LLM-assisted classification contract only, not execution;
- unsupported question path: `needs_question_spec_review`;
- planner guardrails documented in tests.

Success check:

```text
known question specs become deterministic InvestigationPlan objects
```

Proof surface: `pytest -q tests/research` and
`ruff check src/leaders_db/research tests/research` cover known question planning,
unknown question review path, and classification-contract mapping to known specs.

## Increment 3 — evidence gap and acquisition-task planning

Status: implemented and reviewed on 2026-06-28.

Verification:

- `pytest -q tests/research` — passed, 24 tests.
- `ruff check src/leaders_db/research tests/research` — passed.

Deliverables:

- `EvidenceGapReport` generation;
- `EvidenceAcquisitionTask` planning;
- strict acquired-evidence schema definitions;
- no live web research execution yet;
- generated evidence examples as fixture rows.

Success check:

```text
missing qualitative evidence produces planned acquisition tasks, not invented values
```

Proof surface: tests cover missing evidence, acquisition allowed, acquisition not
approved, and generated evidence rows with URL/quote provenance.

## Increment 4 — report and artifact proof

Status: implemented and reviewed on 2026-06-28.

Deliverables:

- Markdown report writer;
- JSON findings writer;
- CSV appendix writer;
- attribution block injection;
- provenance/caveat section;
- method section.

Success check:

```text
research run produces readable report plus machine-readable findings
```

Proof surface: generated Markdown/JSON/CSV artifacts include method, caveats,
provenance, evidence ids, and attribution blocks.

Verification:

- `pytest -q tests/research` — passed, 24 tests.
- `ruff check src/leaders_db/research tests/research` — passed.

## Increment 5 — persistent evidence store

Status: implemented and reviewed on 2026-06-28.

Deliverables:

- `normalized_observations` migration and ORM model, or documented compatibility
  view if we defer a new table;
- serializers between normalized evidence rows and DB rows;
- `SqlEvidenceRepository` implementing `EvidenceRepository`;
- generic `scope_json` / dimension-binding storage, with optional convenience
  views for common `leaders-db` dimensions;
- required provenance fields that let every row point to the original source;
- no raw file reads during evidence queries.

Success check:

```text
ingested observations can be queried from SQLite without rerunning adapters
```

Proof surface: focused pytest coverage for DB serialization/deserialization and
`SqlEvidenceRepository` filters, including traceability from evidence rows to
source locators.

Verification:

- `pytest -q tests/research tests/test_db_schema.py` — passed, 40 tests.
- `ruff check src/leaders_db/research src/leaders_db/db tests/research tests/test_db_schema.py` — passed.

## Increment 6 — shared source validation, persistence, manifests

Status: implemented (2026-06-28).

Deliverables:

- shared validator for normalized evidence rows;
- persistence service for processed files and DB rows;
- manifest writer/reader;
- idempotency behavior for reruns;
- structured warnings for missing metadata, out-of-coverage years, missing raw
  files, unsupported filters, duplicate IDs, and missing provenance.

Success check:

```text
SourceIngestRunner can execute check_ready -> read_raw -> transform -> validate -> persist -> manifest
```

Proof surface: one migrated source run writes observations, a manifest, and no
duplicate rows on rerun.

Implementation note: `SourceIngestRunner(registry, engine=...)` now opts into
shared validation, processed observation artifacts under
`processed_root/<source>/observations-<run_id>.<format>`, SQL persistence via
`normalized_observations`, deterministic manifest JSON under
`processed_root/<source>/manifest-<run_id>.json`, and idempotent upserts keyed by
`(source_slug, observation_id)`. The default `SourceIngestRunner(registry)` path
remains side-effect free and returns `manifest=None` for existing in-memory
callers.

Verification:

- `pytest -q tests/sources/test_runner.py tests/sources/test_maddison_project_adapter.py tests/research/test_sql_repository.py tests/test_db_schema.py` — passed, 48 tests.
- `pytest -q tests/sources` — passed, 2 skipped.
- `ruff check src/leaders_db/sources tests/sources/test_runner.py tests/sources/test_maddison_project_adapter.py` — passed.

## Increment 7 — concept/metric catalog bridge

Status: implemented (2026-06-28).

Deliverables:

- explicit mapping between `leaders_db.sources.concepts` and `leaders_db.viz.metrics`;
- initial canonical concepts across several evidence shapes, with GDP/population
  only as a smoke-test subset;
- concept coverage diagnostics;
- unit and source-precedence policy for each metric.

Success check:

```text
concept rows can be extracted from SQL-backed evidence and published as viz metrics
```

Proof surface: concept rows from the SQL evidence repo match expected fixture
values and appear in the viz metric catalog/output.

Implementation note: `leaders_db.viz.concept_bridge` now defines the explicit
concept-to-metric mapping for `gdp_per_capita`, `population`, and `gdp_total`,
publishes concept rows from any `EvidenceRepository` (including the SQL-backed
`SqlEvidenceRepository`) into the chart-ready viz output contract, and surfaces
per-concept/per-source coverage diagnostics. The viz metric registry includes
`concept.gdp_per_capita`, `concept.population`, and `concept.gdp_total` with the
source-precedence policy `world_bank_wdi -> maddison_project -> pwt`.

Verification:

- `pytest -q tests/test_viz_concept_bridge.py tests/sources/test_concepts.py tests/research/test_sql_repository.py` — passed, 49 tests.
- `pytest -q tests/test_viz_concept_bridge.py tests/test_cli_viz.py tests/test_viz_investigation_slice.py` — passed, 34 tests.
- `ruff check src/leaders_db/viz tests/test_viz_concept_bridge.py` — passed.

## Increment 8 — source CLI over the new source system

Status: completed (2026-06-28).

Delivered first slice:

- `leaders-db sources list`;
- `leaders-db sources describe <source>`;
- default clean source-registry composition for inspection commands;
- CLI tests proving the new commands use the clean `leaders_db.sources` registry
  path rather than legacy `leaders_db.ingest.STAGE2_ADAPTERS` dispatch.

Delivered check-ready slice:

- `leaders-db sources check-ready <source>`;
- readiness checks routed through the clean source registry / adapter lifecycle,
  not legacy Stage 2 dispatch;
- deterministic human-readable output and JSON output;
- clear unknown-source failures and non-zero exit for not-ready sources.

Delivered query slice:

- `leaders-db sources query`;
- filters for clean source ID, observation family, indicator, year, country, and
  leader mapped directly into `EvidenceQuery`;
- query routed through the clean `EvidenceRepository` boundary, backed in normal
  CLI use by persisted `normalized_observations` via `SqlEvidenceRepository`;
- deterministic table output and parseable JSON output;
- empty results exit 0 with clear output;
- sentinel tests prove the command does not consult legacy
  `leaders_db.ingest.STAGE2_ADAPTERS`.

First-slice verification:

- `pytest tests/test_cli_sources.py tests/sources/test_registry.py tests/sources/test_import_boundary.py -q` — passed, 23 tests.
- `ruff check src/leaders_db/cli/commands_sources.py src/leaders_db/cli/__init__.py src/leaders_db/sources/__init__.py src/leaders_db/sources/registry.py tests/test_cli_sources.py tests/sources/test_registry.py` — passed.

Check-ready slice verification:

- `pytest -q tests/test_cli_sources.py` — passed, 9 tests.
- `pytest -q tests/test_imports.py tests/test_cli_sources.py` — passed, 11 tests.
- `ruff check src/leaders_db/cli/commands_sources.py tests/test_cli_sources.py` — passed.

Delivered ingest slice:

- `leaders-db sources ingest <source>`;
- ingest routed through `build_default_source_registry()` and
  `SourceIngestRunner.run()`, not legacy Stage 2 dispatch;
- deterministic human-readable output and JSON output with readiness,
  validation status, observation count, manifest/run IDs when available, and
  warnings/errors;
- clear unknown-source failures and non-zero exit when readiness blocks ingest
  before raw read/transform.

Ingest slice verification:

- `pytest -q tests/test_cli_sources.py tests/sources/test_import_boundary.py` — passed, 19 tests.
- `ruff check src/leaders_db/cli/commands_sources.py src/leaders_db/cli/__init__.py src/leaders_db/sources/__init__.py tests/test_cli_sources.py` — passed.

Query slice verification:

- `pytest -q tests/test_cli_sources.py tests/sources/test_import_boundary.py` — passed, 24 tests.
- `pytest -q tests/test_imports.py tests/test_cli_sources.py` — passed, 21 tests.
- `ruff check src/leaders_db/cli/commands_sources.py src/leaders_db/cli/__init__.py tests/test_cli_sources.py` — passed.

Success check:

```text
a source can be inspected, ingested, and queried through the new registry path
```

Proof surface: CLI tests for list/describe/check-ready/ingest/query using a
fixture-backed source.

## Increment 9 — visualization publishing and broader questions

Status: first slice implemented (2026-06-28).

Delivered first slice:

- reusable economic trend publishing helper over persisted evidence via
  `SqlEvidenceRepository` / `EvidenceRepository`;
- GDP per capita, population, and total GDP trend rows are built by reusing the
  Increment 7 concept metric bridge (`concept.gdp_per_capita`,
  `concept.population`, `concept.gdp_total`), not by adding new source-specific
  extraction logic;
- deterministic `viz_economic_trends.csv` writer for selected countries and
  inclusive year ranges;
- optional Superset SQLite table registration as `viz_economic_trends` when the
  CSV is present.

First-slice success check:

```text
SQL-backed normalized observations can be published as GDP/population trend rows
and loaded into the read-only viz/Superset artifact without rerunning adapters
```

Proof surface: `tests/test_viz_economic_trends.py` covers fixture observations in
`normalized_observations` -> concept bridge metrics -> filtered economic trend
CSV -> optional Superset SQLite table.

Fast-path Q2.1 helper slice (2026-06-28):

- Added a pure `leaders_db.research.question_2_1` helper for methodology
  Question 2.1, "Was the country involved in state-based armed conflict?".
- The helper reads only through `EvidenceRepository` using UCDP indicators
  `ucdp_state_based_events` and `ucdp_state_based_fatalities` in observation
  family `international_peace_country_year`, emits one row per in-scope country,
  and preserves source observation ids plus ruler-name fields from an injected
  resolver/callback.
- Exact 2023 UCDP evidence is still not claimed by this slice: the local GED
  23.1 metadata covers 1989-2022. Any 2023 run must either surface missing
  coverage or pass an explicit proxy year, which is marked `coverage_status =
  "proxy"` with a warning/caveat rather than masquerading as direct 2023 data.

Persisted Q2.1 result-layer trial (2026-06-29):

- Added migration `0003_research_results.sql` for question metadata,
  dashboard-ready question answers, answer-to-evidence drill-down links, and a
  future chapter-score aggregate table.
- Added `leaders_db.research.results_store.persist_q2_1_answers(...)` to upsert
  already-built Q2.1 rows into the persisted result layer and refresh UCDP
  evidence links on rerun without reading raw files or rerunning adapters.
- First proof remains fixture/test-backed because exact local UCDP 2023 evidence
  is unavailable in GED 23.1; no production 2023 direct result is claimed.

Trial commands:

```bash
pytest -q tests/test_research_results_store.py tests/test_research_question_2_1.py tests/test_db_schema.py
ruff check src/leaders_db/db/models.py src/leaders_db/research/results_store.py tests/test_research_results_store.py tests/test_db_schema.py
```

Candidate question families:

- economic trend questions;
- regime / population questions;
- leader-tenure questions;
- corruption / governance trend questions;
- political freedom trend questions;
- source disagreement and coverage questions.

Success check:

```text
new supported questions require adding config/catalog entries and analysis specs, not bespoke scripts
```

Proof surface: add a second question family without changing the research runner
control flow; optionally publish research output as read-only Superset data.

## Implementation order

Recommended order:

1. in-memory representative vertical slice;
2. question/concept registry and planner rules;
3. gap and acquisition-task planning;
4. report/artifact proof;
5. persistent evidence store;
6. validation/persistence/manifests;
7. concept/metric bridge;
8. source CLI;
9. viz publishing and broader question families.

## First proof slice

Use a small fixture-backed slice as the first proof:

```text
1. One structured question-bank row, e.g. conflict fatalities or political
   freedom status for a few dimension scopes.
2. One leader/ruler-scope question that has missing evidence.
3. One planned qualitative acquisition task, e.g. open criminal/corruption legal
   case evidence, without live web execution.
```

Why this slice:

- proves evidence rows, scope filters, row scopes, gap reports, findings, and
  traceability;
- avoids building persistence/CLI/Superset before validating the core loop;
- avoids biasing the architecture toward GDP-only country-year tables.
