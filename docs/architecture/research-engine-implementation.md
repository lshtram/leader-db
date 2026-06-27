# Research Engine Implementation Blueprint

## Purpose

This document turns the high-level research-engine architecture into an
implementation plan. It is written in two layers:

1. plain-English explanation of what each part does;
2. technical contracts that developers can implement and test.

The companion overview is [`research-engine.md`](research-engine.md). The
implementation workplan is [`../research-engine-workplan.md`](../research-engine-workplan.md).

## Plain-English picture

The engine should work like this:

```text
Ask a question
  -> classify it against the known question bank
  -> make a clear, inspectable plan
  -> collect already-ingested evidence
  -> identify evidence gaps
  -> optionally acquire targeted new evidence
  -> convert source-specific data into stable concepts
  -> build a table
  -> calculate trends / rankings / coverage
  -> write findings and reports
  -> optionally publish the table to Superset
```

Example:

```text
Question: What was Sweden's GDP in 1962?
```

The system should not open a random Excel file directly. It should:

1. recognize the concept: `gdp_total`;
2. recognize the scope: Sweden, 1962;
3. query stored evidence observations;
4. detect whether enough evidence exists;
5. acquire more evidence only if the plan allows it;
6. derive GDP if needed, for example `gdppc * population`;
7. return the value with source, unit, caveats, and provenance.

For complex qualitative questions, an LLM may help classify the user's wording
against the known question bank and propose a route. It does not become the
source of truth. The executable plan must still reference known question specs,
concept specs, source rules, and output schemas, or be marked as a proposed new
question requiring human approval.

## Evidence is just normalized database rows

The research engine should keep evidence conceptually simple. An evidence item is
not a special opaque object. It is a normalized database row:

```text
scope_json + indicator_key + value + value_type + source_id + provenance
```

Example structured row:

```text
scope_json={"country":"USA","year":1984}
indicator_key=gdp_total
value=4037600
value_type=numeric
source_id=world_bank_wdi
unit=current_usd
provenance_json={... raw file / API locator ...}
```

Example generated research row:

```text
scope_json={"ruler":"Benjamin Netanyahu","country":"ISR","year":2023}
indicator_key=has_open_criminal_or_corruption_case
value=true
value_type=boolean
source_id=generated_legal_research
provenance_json={... URL, quote, retrieval date, task id ...}
```

The custom part of this project is not the row idea. It is:

- normalizing many source formats into this row shape;
- preserving source locators and attribution;
- deciding which evidence rows answer each research question;
- producing findings and reports without losing traceability.

## Traceability invariant

Traceability is mandatory:

```text
answer / finding -> evidence row ids -> original source locators
```

Every answer must be able to point to supporting evidence rows. Every evidence
row must point to the original source.

For structured datasets, provenance should include:

- source id and version;
- raw path or API endpoint;
- raw row/cell/API locator;
- retrieval or download date;
- transform/catalog rule used.

For targeted web/manual research, provenance should include:

- source URL or bibliographic locator;
- source title where available;
- quote or precise reference where available;
- retrieval date;
- acquisition task id;
- path to the agent/manual research output artifact;
- human-review status.

Large transcripts, PDFs, screenshots, and agent logs should live as files under
the run/source artifact folders. The database stores pointers, hashes, quotes,
and concise metadata.

## Scope for the first implementation

The research engine must be designed around the real question bank in
[`../methodology/ranking-evaluation-criteria.md`](../methodology/ranking-evaluation-criteria.md),
especially chapters 1-8 and ruler-focused chapters 1B-8B. GDP, GDP per capita,
and population are useful infrastructure smoke tests, but they are not the
center of the product and must not bias the architecture.

The first implementation should prove a **representative question-bank vertical
slice**, not an economic-only product.

Initial supported question families should include examples from different
evidence shapes:

| Evidence shape | Example question family | Why it matters |
|---|---|---|
| Structured country-year numeric | population, GDP, conflict fatalities, CPI, HDI | Proves normal database-backed evidence. |
| Structured country-year categorical | Freedom House status, regime bucket, treaty status | Proves non-numeric concepts. |
| Leader/ruler identity | who was ruler / formal vs actual leader | Proves leader-year entity scope. |
| Qualitative cited research | open lawsuits, nuclear threats, proxy support, stated governing program | Proves targeted acquisition and generated evidence. |
| Mixed evidence bundle | category/ruler-year question combining several sources | Proves real scoring/reporting workflow. |

Initial supported concepts should be chosen to cover those shapes, for example:

- `population` or `gdp_total` as a simple structured smoke test;
- `conflict_involvement` or `state_based_fatalities` for chapter 2;
- `political_freedom_status` for chapter 4;
- `ruler_identity` for Stage 4 / ruler-year scope;
- `leader_open_criminal_or_corruption_case` as a targeted-acquisition prototype;
- one category-level evidence bundle concept, such as `integrity_evidence_bundle`
  or `international_peace_evidence_bundle`.

Initial analyses should include:

- point lookup;
- table creation;
- source coverage;
- missingness;
- ranking / ordering where meaningful;
- evidence-bundle summary;
- qualitative acquisition status and human-review queue.

Out of scope for the first implementation:

- unchecked free-form LLM planning;
- broad natural-language parsing;
- automatic external web research without an explicit acquisition task;
- custom dashboard generation inside Superset;
- full leader/ruler scoring.

## Package layout

Target package over time:

```text
src/leaders_db/research/
├── __init__.py
├── questions.py
├── planner.py
├── dataset_builder.py
├── analysis.py
├── findings.py
├── runner.py
├── artifacts.py
├── gaps.py
├── acquisition.py
├── warnings.py
└── viz_publish.py
```

Increment 1 should stay smaller. Start with:

```text
src/leaders_db/research/
├── __init__.py
├── models.py
├── planner.py
├── dataset_builder.py
├── runner.py
└── artifacts.py
```

The first-slice models live in `models.py`: `RowScope`, `ScopeFilter`,
`ResearchQuestion`, `InvestigationPlan`, `EvidenceGapReport`,
`EvidenceAcquisitionTask`, `AnalyticalDatasetRow`, `AnalysisResult`, `Finding`,
and `ResearchRunResult`. Split into `questions.py`, `analysis.py`, `findings.py`,
`gaps.py`, and `acquisition.py` only when the module grows.

Responsibilities:

| Module | Owns | Must not own |
|---|---|---|
| `models.py` | First-slice Pydantic models until split is justified. | Source parsing, DB queries. |
| `questions.py` | Request models and supported question keys. | Source parsing, DB queries. |
| `planner.py` | Convert a supported question into an explicit plan. | Raw-file reads, analysis calculations. |
| `dataset_builder.py` | Build analytical rows from evidence + concepts. | Report prose, Superset UI logic. |
| `analysis.py` | Compute point lookup, ranking, CAGR, coverage. | Source ingestion. |
| `findings.py` | Convert analysis results into structured findings. | Markdown rendering. |
| `artifacts.py` | Write question, plan, dataset, findings, manifest. | Business logic. |
| `runner.py` | Orchestrate the full research run. | Source-specific transformations. |
| `warnings.py` | Stable warning/caveat codes. | Free-form exception policy. |
| `gaps.py` | Compare required evidence with available evidence. | Web research, report writing. |
| `acquisition.py` | Define approved evidence-acquisition tasks and strict outputs. | Unstructured notes, unsupported claims. |
| `viz_publish.py` | Convert research outputs to viz/Superset-ready tables. | Official metric definitions. |

## Core objects

Use Pydantic models or frozen dataclasses. Prefer Pydantic if objects cross file,
CLI, or artifact boundaries.

## Generic scope and filter model

The research engine itself should not assume that every research domain is about
countries, rulers, and years. Those are important dimensions for `leaders-db`,
but a future research project could investigate companies, treaties, court cases,
institutions, events, quarters, documents, or technologies.

Therefore, the generic engine uses dimension objects instead of hardcoded fields
like `country_code`, `leader_name`, and `year`.

There are two different shapes, and implementation must keep them separate:

1. **Row scope** — concrete identity for one evidence or analytical row. It has
   one value per dimension key.
2. **Scope filter** — query/request scope. It may contain many values, ranges,
   or grouping dimensions.

```python
class DimensionBinding(BaseModel):
    key: str
    value: str | int | float | bool | None
    value_type: Literal["string", "integer", "number", "boolean", "date", "missing"]
    role: Literal["entity", "time", "category", "filter", "grouping"] = "filter"
    label: str | None = None

class RowScope(BaseModel):
    dimensions: tuple[DimensionBinding, ...]

class DimensionFilter(BaseModel):
    key: str
    values: tuple[str | int | float | bool, ...] = ()
    start: str | int | float | None = None
    end: str | int | float | None = None
    role: Literal["entity", "time", "category", "filter", "grouping"] = "filter"

class ScopeFilter(BaseModel):
    filters: tuple[DimensionFilter, ...]
```

Examples:

```python
RowScope(dimensions=(
    DimensionBinding(key="country", value="USA", value_type="string", role="entity"),
    DimensionBinding(key="year", value=1984, value_type="integer", role="time"),
))
```

```python
ScopeFilter(filters=(
    DimensionFilter(key="country", values=("USA", "CHN", "IND"), role="entity"),
    DimensionFilter(key="year", start=1950, end=2023, role="time"),
))
```

`leaders-db` can define a project-specific dimension profile with standard keys
such as `country`, `year`, `leader`, `ruler`, `category`, `source`, and `event`.
Those keys are configuration/profile vocabulary, not hardcoded engine fields.

Planner/dataset-builder rule:

```text
ScopeFilter -> many concrete RowScope values -> analytical/evidence rows
```

For example, a filter with `country in (USA, CHN)` and `year 2020-2021` expands
to four concrete row scopes. Each evidence row and analytical row stores exactly
one concrete `RowScope`; it does not store a multi-country or range filter as its
identity.

For convenience, output writers may flatten common row-scope dimensions into CSV columns
such as `country`, `year`, or `leader`, but internal research objects should keep
the generic `RowScope` / `ScopeFilter` distinction.

## Planning modes

There are three planning modes.

### 1. Direct registered planning

The question already names a known `question_key` and known concepts.

```text
ResearchQuestion -> registered planner -> InvestigationPlan
```

This is the safest and first implementation path.

### 2. LLM-assisted classification

The user asks in normal language. The LLM may classify it into an existing
question-bank entry.

Example:

```text
User: Does the ruler have open corruption lawsuits?
LLM classification: question_code=integrity/legal_cases, concept=leader_open_criminal_or_corruption_case
Planner: leader_year_qualitative_evidence
```

The LLM output is only accepted if it maps to known registry entries:

- known `question_key`;
- known `concept_key`;
- known entity scope;
- known output schema;
- known acquisition policy.

If the mapping is valid, the normal registered planner creates the
`InvestigationPlan`.

### 3. Proposed new question/spec

If the LLM cannot map the request to known registry entries, it may propose a new
question spec. That proposal is not executable until reviewed.

```text
User question
  -> LLM proposed QuestionSpec
  -> human review / edit
  -> registry update
  -> normal planner
```

This is how the system grows without letting the LLM invent operational rules.

Planner guardrails:

- The LLM may classify or propose; it may not silently execute unsupported
  research.
- Every executable plan must be deterministic and serializable.
- Every concept must have an output schema and evidence policy.
- Every acquisition task must have allowed source types and a strict result
  schema.
- Unknown questions become `needs_question_spec_review`, not ad hoc scripts.

## Question and concept registries

The planner depends on curated registries.

```python
class QuestionSpec(BaseModel):
    question_code: str
    question_key: str
    text: str
    category: str
    expected_scope_keys: tuple[str, ...]
    concept_keys: tuple[str, ...]
    default_analyses: tuple[str, ...]
    acquisition_policy: Literal["none", "plan_only", "run_approved_tasks"]

class ConceptSpec(BaseModel):
    concept_key: str
    expected_scope_keys: tuple[str, ...]
    evidence_shape: Literal[
        "structured_numeric",
        "structured_categorical",
        "qualitative_cited",
        "evidence_bundle",
    ]
    observation_families: tuple[str, ...]
    required_output_schema: str
    allowed_source_types: tuple[str, ...]
    acquisition_allowed: bool
```

For chapters 1-8 and 1B-8B, each evaluation question should eventually have a
`QuestionSpec`. The planner is generic because it reads these specs; it does not
need to understand each question from scratch every time.

### `ResearchQuestion`

Plain English: the user's request after we make it explicit.

```python
class ResearchQuestion(BaseModel):
    question_id: str
    question_key: str
    display_text: str
    concepts: tuple[str, ...]
    scope_filter: ScopeFilter
    analyses: tuple[str, ...]
    preferred_sources: tuple[str, ...] = ()
```

Rules:

- `question_key` must be from a supported registry, not arbitrary text.
- Scope dimensions identify entities, time windows, categories, filters, or
  grouping dimensions. They are generic key/value pairs.
- `question_id` must be safe for paths.

Technical shape example:

```python
ResearchQuestion(
    question_id="leader-legal-cases-selected-2023",
    question_key="leader_year_qualitative_evidence",
    display_text="For selected rulers in 2023, identify open criminal or corruption legal cases with cited evidence.",
    concepts=("leader_open_criminal_or_corruption_case",),
    scope_filter=ScopeFilter(filters=(
        DimensionFilter(key="country", values=("ISR", "BRA", "USA"), role="entity"),
        DimensionFilter(key="year", values=(2023,), role="time"),
    )),
    analyses=("coverage", "human_review_queue"),
    preferred_sources=("official_court_records", "prosecutor_records", "reputable_news"),
)
```

### `InvestigationPlan`

Plain English: the exact recipe the machine will run.

```python
class InvestigationPlan(BaseModel):
    question_id: str
    concept_keys: tuple[str, ...]
    evidence_query: EvidenceQuery
    source_priority: tuple[str, ...]
    scope_filter: ScopeFilter
    output_grain: Literal[
        "dimensioned_concept",
        "category_bundle",
        "evidence_record",
    ]
    analyses: tuple[str, ...]
    include_missing_rows: bool = True
    acquisition_policy: Literal["none", "plan_only", "run_approved_tasks"] = "none"
```

Rules:

- The plan must be serializable to `plan.json` before execution.
- The plan must say exactly which evidence will be queried.
- `include_missing_rows=True` creates analytical coverage rows, not source
  observations.
- `acquisition_policy` controls whether missing evidence may trigger new
  targeted research. Default is `none`.

### `EvidenceGapReport`

Plain English: what the system needed but could not find in stored evidence.

```python
class EvidenceGapReport(BaseModel):
    question_id: str
    required_concepts: tuple[str, ...]
    available_count: int
    missing: tuple[EvidenceGap, ...]
    can_continue: bool
    recommended_acquisition_tasks: tuple[str, ...]

class EvidenceGap(BaseModel):
    gap_id: str
    concept_key: str
    scope_filter: ScopeFilter
    reason: Literal[
        "source_not_ingested",
        "country_absent",
        "year_absent",
        "indicator_missing",
        "qualitative_evidence_needed",
        "insufficient_source_quality",
    ]
    required_evidence: str
```

Rules:

- Gaps are not failures by default.
- Gaps become acquisition tasks only when the plan allows acquisition.
- A gap report must be written to the run manifest.

### `EvidenceAcquisitionTask`

Plain English: a controlled request to collect missing evidence.

This covers future qualitative questions such as:

```text
Does this ruler have open criminal or corruption lawsuits?
```

```python
class EvidenceAcquisitionTask(BaseModel):
    task_id: str
    question_id: str
    gap_id: str
    acquisition_type: Literal[
        "source_ingestion",
        "targeted_web_research",
        "manual_research",
        "document_review",
    ]
    scope_filter: ScopeFilter
    evidence_need: str
    required_output_schema: str
    allowed_source_types: tuple[str, ...]
    status: Literal["planned", "approved", "running", "completed", "failed"]
```

Rules:

- The task must be explicit before an agent researches anything.
- Large batches are represented as many tasks under one acquisition batch.
- A task must define a strict output schema.
- Agent prose is not evidence until converted into structured records.

### `AcquiredEvidenceRecord`

Plain English: structured evidence produced by a targeted research task.

```python
class AcquiredEvidenceRecord(BaseModel):
    task_id: str
    subject_scope: RowScope
    claim_key: str
    value: bool | int | float | str | None
    value_type: Literal["boolean", "numeric", "categorical", "text", "missing"]
    source_url: str
    source_title: str | None
    source_type: str
    quote: str | None
    retrieved_at: str
    confidence_score: int
    human_review_required: bool
    caveats: tuple[str, ...]
```

Rules:

- A record needs a source URL or bibliographic locator.
- A direct quote is required where available.
- The record is persisted as a generated/researched evidence source before it is
  used in analysis.
- Unsupported claims must become `human_review_required=True` or
  `value_type="missing"`.

### `AnalyticalDatasetRow`

Plain English: one row in the table created for the question.

```python
class AnalyticalDatasetRow(BaseModel):
    question_id: str
    row_scope: RowScope
    concept_key: str
    value: float | int | str | None
    value_type: Literal["numeric", "categorical", "text", "missing"]
    unit: str | None
    source_id: str | None
    source_observation_ids: tuple[str, ...]
    coverage_status: Literal[
        "direct", "derived", "proxy", "stale", "missing", "not_applicable"
    ]
    confidence_score: int | None
    warning_codes: tuple[str, ...]
    caveats: tuple[str, ...]
    provenance_json: dict[str, object]
```

Required CSV columns:

```text
question_id,row_scope_json,concept_key,value,value_type,unit,source_id,
source_observation_ids,coverage_status,confidence_score,warning_codes,caveats,
provenance_json
```

Output writers may add flattened convenience columns from `row_scope`, such as
`country`, `year`, or `leader`, for readability and Superset compatibility. The
canonical row identity remains `row_scope_json`.

### `AnalysisResult`

Plain English: a calculation performed over the dataset.

```python
class AnalysisResult(BaseModel):
    question_id: str
    analysis_type: str
    result_id: str
    rows: tuple[dict[str, object], ...]
    warning_codes: tuple[str, ...]
    caveats: tuple[str, ...]
```

Examples of `analysis_type`:

- `point_lookup`
- `coverage`
- `missingness`
- `ranking_by_year`
- `cagr`

### `Finding`

Plain English: a report-ready claim with supporting evidence.

```python
class Finding(BaseModel):
    finding_id: str
    question_id: str
    claim: str
    support: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    analysis_result_ids: tuple[str, ...]
    confidence_score: int | None
    caveats: tuple[str, ...]
    warning_codes: tuple[str, ...]
```

Rules:

- A finding must link to analysis results or evidence observations.
- If evidence is insufficient, the finding should say so instead of inventing a
  conclusion.
- Reports should render evidence links so a reviewer can navigate from claim to
  row to original source.

### `ResearchRunResult`

Plain English: summary of what the run produced.

```python
class ResearchRunResult(BaseModel):
    run_id: str
    question_id: str
    status: Literal["success", "partial", "failed"]
    output_dir: Path
    dataset_path: Path | None
    findings_path: Path | None
    report_path: Path | None
    manifest_path: Path | None
    warning_codes: tuple[str, ...]
```

## Artifact layout

Each research run writes a self-contained folder:

```text
data/outputs/research/<run-id>/
├── question.json
├── plan.json
├── evidence-gap-report.json
├── acquisition-tasks.json
├── acquired-evidence.json
├── analytical-dataset.csv
├── analysis-results.json
├── findings.json
├── report.md
├── manifest.json
└── viz/
    └── research-country-year-metrics.csv
```

Artifact meaning:

| File | Purpose |
|---|---|
| `question.json` | The explicit user request. |
| `plan.json` | The machine plan before execution. |
| `evidence-gap-report.json` | Missing evidence after the first repository query. |
| `acquisition-tasks.json` | Planned/approved targeted evidence collection tasks. |
| `acquired-evidence.json` | Structured outputs from targeted research tasks. |
| `analytical-dataset.csv` | Main table generated for the question. |
| `analysis-results.json` | Calculations over the dataset. |
| `findings.json` | Report-ready claims. |
| `report.md` | Human-readable narrative. |
| `manifest.json` | Inputs, outputs, warnings, versions, run metadata. |
| `viz/*.csv` | Optional chart/Superset-ready tables. |

## Runner sequence

`ResearchRunner.run(question)` must execute in this order:

```text
1. validate question
2. create run_id and output directory
3. write question.json
4. build InvestigationPlan
5. write plan.json
6. query EvidenceRepository
7. build EvidenceGapReport
8. if allowed, create EvidenceAcquisitionTask records
9. if approved, run acquisition tasks and persist acquired evidence
10. re-query EvidenceRepository if new evidence was persisted
11. extract requested concepts
12. build analytical dataset rows
13. write analytical-dataset.csv
14. run requested analyses
15. write analysis-results.json
16. generate findings
17. write findings.json
18. write report.md
19. optionally publish viz CSVs
20. write manifest.json
21. return ResearchRunResult
```

Failure rule:

- If the question cannot be planned, fail before writing dataset outputs.
- If evidence is incomplete, produce partial outputs with explicit warnings.
- If evidence is incomplete and acquisition is not allowed, continue only with
  explicit gap/caveat records.
- If acquisition is allowed but not approved, write planned tasks but do not run
  them.
- If zero usable evidence rows exist, fail or produce an insufficient-evidence
  report; do not fabricate values.

## Targeted evidence acquisition

Some future questions require evidence that is not already present in a source
database. Example:

```text
Does each ruler have open lawsuits for criminal offenses or corruption?
```

This should create a generated research dataset, not loose notes.

Flow:

```text
EvidenceGapReport
  -> EvidenceAcquisitionTask[]
  -> subagent / manual / document research
  -> AcquiredEvidenceRecord[]
  -> generated source observations
  -> EvidenceRepository
```

For a batch of 1,000 leaders/years, the system creates one acquisition batch with
many explicit tasks. Each task returns strict JSON. The accepted records are then
persisted under a generated source, for example:

```text
data/processed/generated/leader-legal-cases/<run-id>.csv
data/processed/generated/leader-legal-cases/<run-id>-manifest.json
```

Those records become reusable evidence. Future questions query them through the
same `EvidenceRepository` interface.

Generated evidence source rules:

- source id should be stable, for example `generated_leader_legal_cases`;
- source type should be `generated_research` or equivalent;
- every record requires source locator, retrieval date, confidence, and review
  status;
- prompts, agent outputs, and accepted structured records must be persisted;
- generated evidence never has higher authority than primary structured or
  official records unless reviewed.

The generated dataset should be treated like any other source: it has rows,
source metadata, a manifest, attribution/usage notes, and raw locators. The only
difference is that its rows were created by approved research tasks rather than a
pre-existing external database.

## Evidence and concept flow

The research engine reads evidence only through `EvidenceRepository`.

```text
SqlEvidenceRepository
  -> NormalizedObservation[]
  -> extract_concept_result(...)
  -> ConceptObservation[]
  -> AnalyticalDatasetRow[]
```

The research engine must not:

- import legacy `leaders_db.ingest` modules;
- read files in `data/raw/`;
- call source adapters directly;
- silently choose a proxy year.

## Source priority and duplicates

For many research questions, multiple sources may provide evidence for the same
dimension scope, such as the same country/year, leader/year, ruler/category, or
some future non-political entity/time/category combination.

Initial rule:

1. preserve all source rows in evidence-level output;
2. choose one display value for the main analytical table using `source_priority`;
3. record alternates in `provenance_json`;
4. warn when sources materially disagree.

Example priority for one economic concept:

```text
world_bank_wdi > pwt > maddison_project
```

For older years where WDI is absent, Maddison or PWT may be selected. The selected
source must be explicit in the row.

Other question families need their own source priority rules. For example,
official court records may outrank news reports for lawsuits, while structured
UCDP records may outrank qualitative news summaries for conflict involvement.

## Warning and caveat model

Use stable warning codes, not only prose.

Initial codes:

| Code | Meaning |
|---|---|
| `missing_source_observation` | Expected source/indicator absent. |
| `year_out_of_coverage` | Requested year outside source coverage. |
| `concept_not_derivable` | Required input indicators missing. |
| `source_disagreement` | Multiple sources disagree materially. |
| `proxy_or_stale_value` | Value comes from a non-target year. |
| `unit_mismatch` | Sources use incompatible units. |
| `insufficient_evidence` | No reliable answer can be produced. |
| `acquisition_required` | Existing evidence is insufficient and new evidence is needed. |
| `acquisition_not_approved` | Acquisition task exists but was not approved to run. |
| `acquired_evidence_needs_review` | New evidence exists but requires human review. |

Caveats are human-readable explanations attached to rows, analyses, findings, and
reports.

## Increment 1 proof slice

The first implementation should be a small fixture-backed proof slice, not the
full research engine and not a GDP-only product.

Required first-slice coverage:

1. **One structured question-bank row** — for example conflict fatalities or
   political freedom status for a few concrete row scopes.
2. **One leader/ruler-scope missing-evidence example** — enough to prove the
   engine can express a non-country-only question.
3. **One planned qualitative acquisition task** — for example open
   criminal/corruption legal-case evidence, without live web execution.

Deferred until after Increment 1:

- broad GDP/economic time-series tables;
- live web acquisition;
- generated evidence persistence;
- Superset publishing;
- SQL-backed evidence storage.

Structured smoke-test example, if needed for fixture mechanics only:

```python
ResearchQuestion(
    question_id="gdp-major-powers-1950-2023",
    question_key="country_year_economic_table",
    display_text="Create GDP, GDP per capita, and population table for selected countries from 1950 to 2023.",
    concepts=("gdp_total", "gdp_per_capita", "population"),
    scope_filter=ScopeFilter(filters=(
        DimensionFilter(key="country", values=("USA", "CHN", "IND", "GBR", "FRA", "SWE"), role="entity"),
        DimensionFilter(key="year", start=1950, end=2023, role="time"),
    )),
    analyses=("coverage", "ranking_by_year", "cagr"),
    preferred_sources=("world_bank_wdi", "pwt", "maddison_project"),
)
```

Expected outputs for this optional smoke test:

- one row per `(country, year, concept)` where available;
- explicit missing coverage rows when configured;
- coverage summary by source/concept/year;
- rankings for selected years;
- CAGR for each country/concept where start and end values exist;
- Markdown report with attribution and caveats.

Qualitative acquisition-planning example:

```python
ResearchQuestion(
    question_id="leader-legal-cases-selected-2023",
    question_key="leader_year_qualitative_evidence",
    display_text="For selected rulers in 2023, identify open criminal or corruption legal cases with cited evidence.",
    concepts=("leader_open_criminal_or_corruption_case",),
    scope_filter=ScopeFilter(filters=(
        DimensionFilter(key="country", values=("ISR", "BRA", "USA"), role="entity"),
        DimensionFilter(key="year", values=(2023,), role="time"),
    )),
    analyses=("coverage", "human_review_queue"),
    preferred_sources=("official_court_records", "prosecutor_records", "reputable_news"),
)
```

Expected outputs for Increment 1:

- one acquisition task per selected ruler/year where stored evidence is missing;
- `evidence-gap-report.json` with explicit missing evidence;
- `acquisition-tasks.json` with planned tasks and strict required output schema;
- no live web calls;
- no generated evidence persistence except optional fixture rows clearly marked as
  fixture-backed.

Later increments add executed acquisition, strict JSON acquired-evidence records,
generated evidence persistence, and human-review queues for ambiguous or weakly
sourced cases.

## Visualization publishing contract

The research engine may publish a Superset-ready CSV, but Superset remains only a
viewer.

Canonical research viz output should include generic scope first:

```text
query_id
metric_id
metric_label
grain
scope_json
value
value_unit
source_keys
source_row_references
attribution_texts
provenance_json
coverage_status
confidence_score
missingness_flags
```

For `leaders-db`, the viz publisher may also flatten common scope dimensions into
the existing country-year visualization contract where useful:

```text
query_id
metric_id
metric_label
grain
year
country_iso3
country_name
value
value_unit
source_keys
source_row_references
attribution_texts
provenance_json
coverage_status
confidence_score
missingness_flags
```

Rules:

- Do not put raw source data in public viz outputs.
- Include attribution text.
- Include coverage and provenance enough to audit the chart.
- Superset reads the output; it does not define the metric.

## Testing and proof surfaces

Minimum test groups:

1. **Question validation** — invalid years, unknown concepts, bad question keys.
2. **Planner tests** — question becomes the expected `InvestigationPlan`.
3. **Dataset builder tests** — fixed observations become expected rows.
4. **Missingness tests** — absent evidence creates warnings, not invented values.
5. **Analysis tests** — CAGR, ranking, coverage, point lookup.
6. **Artifact tests** — all expected files are written atomically.
7. **Boundary tests** — research package does not import `leaders_db.ingest` or read
   `data/raw/`.
8. **Viz tests** — optional viz CSV follows the required output columns.
9. **Traceability tests** — findings link to evidence row ids and evidence rows
   carry source locators.

First verification command should be focused, for example:

```bash
pytest -q tests/research
```

## Implementation order

Implement in this order:

1. first-slice object models in `models.py`;
2. planner for a representative structured question from chapters 1-8;
3. planner for one leader-year qualitative/acquisition question from chapters 1B-8B;
4. dataset builder using an in-memory repository fixture;
5. gap/acquisition task planning without running web research;
6. analysis functions;
7. artifact writer;
8. runner orchestration;
9. SQL-backed evidence repository integration;
10. viz publishing;
11. CLI command.

This order allows the research engine to be proven with fixtures before it
depends on the persistent evidence store.

## Scale and database migration

Expected scale is manageable but non-trivial.

Very rough order of magnitude:

| Item | Rough scale |
|---|---:|
| Countries | 150-200 |
| Years, 1900-2026 | 127 |
| Country-years | ~20k-25k |
| Ruler-years | ~30k-50k |
| Evaluation questions | ~180-250 |
| Fully expanded ruler/question/year evaluations | millions |

Evidence row sizes:

| Evidence type | Rough size per row |
|---|---:|
| Simple structured numeric | ~0.5-2 KB |
| Structured with provenance JSON | ~1-3 KB |
| Qualitative web evidence with URL + quote | ~2-10 KB |
| Full agent transcript | store as file, not DB row |

Database size scenarios:

| Scenario | Approx size |
|---|---:|
| MVP / first slices | <1 GB |
| Broad structured evidence | ~2-15 GB |
| Structured + generated evidence at scale | ~20-100 GB |

Use SQLite for local MVP work. Keep the repository layer clean so the project can
migrate to PostgreSQL later if size, concurrency, or operations require it.

Migration rules:

- all reads/writes go through repository classes, not ad hoc SQL;
- use SQLAlchemy-compatible schema patterns;
- avoid SQLite-specific SQL in core paths;
- keep CSV/JSON/Parquet export/import artifacts;
- store large artifacts as files with DB pointers;
- test against PostgreSQL before the database becomes operationally large.
