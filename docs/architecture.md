# Architecture — Leaders Database Prototype

This document defines the system design. The authoritative product brief is [`top-level-requirements.md`](top-level-requirements.md); section numbers below reference that document.

## Purpose

A local-first Python research prototype that consolidates structured external datasets, the client's manually built 2023 matrix, and rule-based/LLM-assisted analysis into a confidence-scored, auditable database of world political leaders and their category ratings. The client matrix is treated as a *validation/test reference*, not ground truth and not an evidence source — the system is designed to *reproduce, challenge, explain, and validate* it against independent external data. (§3)

## Scope

**In scope (§2):** one target year at a time, initially 2023; countries above the client's population threshold; the actual ruler or dominant ruling figure per country-year; external indicators per scoring category; provisional category scores; client-matrix comparison; structured relational database; locally cached raw downloads; full source provenance; per-item confidence scores; manual-review flags.

**Out of scope (for the first prototype):** years before 1900 (graceful degradation); production webapp; multilingual UI; live LLM research from scratch (the design §18 explicitly rejects this).

## High-Level Architecture

```mermaid
flowchart LR
    subgraph inputs[Inputs]
        Client["Client 2023 matrix\n(xlsx)"]
        External["External structured sources\n(Archigos, REIGN, V-Dem, ...)"]
        LLM[("LLM adapter\noptional")]
    end

    subgraph lake[Local Data Lake]
        Raw["data/raw/&lt;source&gt;/"]
        Processed["data/processed/"]
        Outputs["data/outputs/"]
    end

    subgraph db[("SQLite / PostgreSQL")]
        Tables["11 tables per §7"]
    end

    subgraph pipeline[Pipeline — Stages 0–15]
        S0["Stage 0\nsource availability"]
        S1["Stage 1\nclient ingest"]
        S2["Stage 2\nexternal ingest"]
        S3["Stage 3\ncountry match"]
        S4["Stage 4\nleader resolve"]
        S5["Stage 5\nindicator extract"]
        S6_8["Stages 6–8\nnormalize / align"]
        S9_11["Stages 9–11\nscore + confidence"]
        S12_15["Stages 12–15\ncompare / review / report"]
    end

    Client --> Raw
    External --> Raw
    Raw --> S0
    Raw --> S1
    Raw --> S2
    S1 --> Tables
    S2 --> Tables
    S3 --> Tables
    S4 --> Tables
    S5 --> Tables
    S6_8 --> S9_11
    S9_11 --> Tables
    S9_11 -. "ambiguous only" .-> LLM
    S12_15 --> Outputs
    S12_15 --> Tables
```

## Core Components

| Component | Module(s) | Stage(s) | Responsibility |
|---|---|---|---|
| CLI surface | `src/leaders_db/cli.py` | — | Typer CLI exposing every Stage 0–15 command. |
| Run config | `src/leaders_db/config.py` | — | Pydantic config + YAML loading from `configs/*.yaml`. |
| Path layer | `src/leaders_db/paths.py` | — | Data-lake path helpers (`raw_dir`, `processed_dir`, ...). |
| Database | `src/leaders_db/db/` | — | SQLAlchemy engine, ORM models, DDL migration. |
| Source availability | `src/leaders_db/ingest/source_availability.py` | 0 | Probe whether each priority dataset is downloadable; emit report. |
| Client ingest | `src/leaders_db/ingest/client_matrix.py` | 1 | Extract `countries`, `leaders`, `ruler_years`, category scores from client xlsx. |
| External ingest | `src/leaders_db/ingest/{archigos,reign,leader_survival,vdem,...}.py` + `external.py` | 2 | One adapter per source; writes to `source_observations`. |
| Country normalization | `src/leaders_db/normalize/countries.py` | 3 | ISO3 primary key, alias table, historical-name handling. |
| Leader resolution | `src/leaders_db/resolve/leader_resolver.py` | 4 | Pull candidates from multiple sources; assign `match_status` per §4 rules. |
| Indicator extraction | `src/leaders_db/resolve/indicators.py` | 5 | Per-category indicator bundles per ruler-year. |
| Category scoring | `src/leaders_db/score/{political_freedom,corruption,economic,domestic_violence,peace,nuclear}.py` | 9–10 | Convert indicator bundles to 0–10 scores. |
| Confidence | `src/leaders_db/score/confidence.py` | 11 | Fixed formula `0.35/0.25/0.25/0.15`; band labels per §11. |
| Comparison | `src/leaders_db/validate/comparison.py` | 12 | Client vs system per category; deltas; summary metrics. |
| Manual review queue | `src/leaders_db/validate/manual_review_queue.py` | 14 | Prioritized queue per §14 priority order. |
| Summary report | `src/leaders_db/validate/summary_report.py` | 15 | Markdown summary + CSV exports per §12. |
| LLM adapter | `src/leaders_db/llm/{caller,schemas}.py` | — | Strict JSON contract per §10. Used only for ambiguity. |
| Export | `src/leaders_db/export/{csv_writer,markdown_report}.py` | — | Writes under `data/outputs/`. |

## Database Schema

The 11-table schema from §7 is the source of truth and lives in [`docs/database-schema.md`](docs/database-schema.md). The SQL DDL is at [`src/leaders_db/db/migrations/0001_initial.sql`](../src/leaders_db/db/migrations/0001_initial.sql); ORM models at [`src/leaders_db/db/models.py`](../src/leaders_db/db/models.py).

Critical invariants the schema enforces:

- **Client matrix is preserved as a reference dataset.** `ruler_scores` always carries `client_score`, `system_proposed_score`, `final_score`, and `score_delta_vs_client` separately. (§3, §9, §12)
- **Client matrix is not evidence.** It is never counted as a source supporting leader identity, factual claims, category scores, `source_agreement`, or `source_authority`; it is loaded only for tests, validation, comparison, deltas, and manual-review triggers. (§3)
- **Source provenance is mandatory.** `source_observations` carries `(source_id, country_id, leader_id, year, variable_name, raw_value, normalized_value, unit, source_row_reference, confidence)`.
- **No silent overwrite.** `final_score` is set only by the manual-review workflow or by an explicit `accept` action; the system never replaces `client_score` with `system_proposed_score` automatically.

## Local Data Lake

See [`docs/local-data-store.md`](docs/local-data-store.md). Folder rules:

- `data/raw/<source>/` is immutable; each folder carries a `metadata.json`.
- `data/processed/` is deterministic normalized output (parquet/csv); re-runs are idempotent.
- `data/interim/` is mid-pipeline scratch (joined frames before scoring).
- `data/outputs/` is the public interface — reports, validation CSVs, manual-review queue.
- `data/logs/` is per-run logs.
- `data/metadata/` is cross-source catalog metadata (aliases, authority table).
- `research/` is derived exploratory analyses and leader memos (gitignored).

## Confidence Scoring

Implemented as a fixed formula in `src/leaders_db/score/confidence.py`:

```
confidence = 0.35 * agreement + 0.25 * authority + 0.25 * specificity + 0.15 * temporal_fit
```

with the component ranges and band labels per §11. **Do not** invent a different weighting in a one-off script. (Always-on rule #10 in [`AGENTS.md`](../AGENTS.md).)

## LLM Use

The LLM is invoked **only** for ambiguous interpretation (form-vs-actual ruler, brief rationale text, evidence summarization) per §10. Every LLM scoring call must include the country, year, leader candidate, category, structured indicators, client score/note (if available), up to three evidence snippets, rubric description, and the required output JSON schema. Output is validated against the Pydantic schema in `src/leaders_db/llm/schemas.py` before being persisted.

Forbidden: inventing scores without sources; replacing structured datasets; citing sources not given; silently resolving ambiguous leader identity; fetching large datasets repeatedly when local data exists. (§10, §18)

## Historical-Year Handling

Older years degrade gracefully (§13). The pipeline must:

- carry forward `not_available` rather than invent data;
- lower confidence even when indicators are present (temporal-fit penalties);
- raise manual-review priority for thin indicator bundles;
- record, never overwrite, the absence of data.

Years before 1900 are explicitly out of scope for the first prototype.

## Cross-Cutting Concerns

- **Reproducibility:** every run is determined by `configs/<name>.yaml` plus the contents of `data/raw/` and `data/processed/`. Run metadata is logged under `data/logs/<run-id>/`.
- **Idempotency:** re-running any stage must produce the same outputs without re-downloading source files that are already in `data/raw/<source>/` with a valid `metadata.json`.
- **Logging:** per-stage progress and warnings go to `data/logs/`. The CLI uses Typer + Python `logging` with a level controlled by `--verbose` / `--quiet`.
- **Tests:** every implemented stage must include a smoke test plus one boundary test that fails if the production wiring is removed (per AGENTS rule #6).

## Acceptance Criteria

The first prototype is successful when, per §16:

- it can load the client's 2023 matrix;
- it can download/ingest local copies of the priority datasets;
- it normalizes countries and years;
- it resolves 2023 rulers for at least 50 countries (preferably all client-scored countries);
- it compares system-selected rulers against the client's leaders;
- it generates provisional scores for at least four categories (political freedom, economic well-being, integrity/corruption, domestic violence/repression);
- it produces confidence scores for every generated item;
- it produces a manual-review queue;
- it produces a summary report;
- it keeps all raw source data and transformed data reproducible;
- it avoids silent overwriting of client values;
- it avoids unsupported LLM-generated facts.

## Phase Order

Work is split into five sequential phases (see [`docs/workplan.md`](workplan.md) for the active-phase indicator):

- **A. Infrastructure** — package, CLI, schema, paths, configs, smoke tests, data lake folders, client bundle.
- **B. Source vetting** — per-source probe of availability, paywall, license, coverage, format. No Stage 2 ingest is written until a source passes vetting.
- **C. Data acquisition** — Stage 0–2 ingest adapters, one per vetted source.
- **D. Testing** — pytest coverage including boundary tests; one end-to-end smoke run on a single country-year.
- **E. Activation** — Stage 3–15 on the full client 2023 scope.
