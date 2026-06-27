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

Status: planned.

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

Proof surface: tests cover known question, unknown question, and LLM-classified
question mapping to known specs.

## Increment 3 — evidence gap and acquisition-task planning

Status: planned.

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

Status: planned.

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

## Increment 5 — persistent evidence store

Status: planned.

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

## Increment 6 — shared source validation, persistence, manifests

Status: planned.

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

## Increment 7 — concept/metric catalog bridge

Status: planned.

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

## Increment 8 — source CLI over the new source system

Status: planned.

Deliverables:

- `leaders-db sources list`;
- `leaders-db sources describe <source>`;
- `leaders-db sources check-ready <source>`;
- `leaders-db sources ingest <source>`;
- `leaders-db sources query ...`;
- clear distinction between legacy ingest commands and new source commands.

Success check:

```text
a source can be inspected, ingested, and queried through the new registry path
```

Proof surface: CLI tests for list/describe/check-ready/ingest/query using a
fixture-backed source.

## Increment 9 — visualization publishing and broader questions

Status: planned.

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
