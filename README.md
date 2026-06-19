# leaders-db

AI-agent data collection and validation system for the **Leaders Database** — a project that consolidates multiple ratings of world political leaders into a single auditable, confidence-scored, client-validated dataset.

The authoritative product brief is [`docs/req/top-level-requirements.md`](docs/req/top-level-requirements.md). Implementation is staged; see [`docs/workplan.md`](docs/workplan.md) for current status and [`docs/architecture.md`](docs/architecture.md) for system design.

## What this prototype does

1. Loads the client's manually built 2023 matrix as a *validation/test reference* (not ground truth and not an evidence source).
2. Downloads and caches a curated set of structured external datasets (Archigos, REIGN, V-Dem, RSF, World Bank WDI/WGI, BTI, Transparency CPI, UCDP, SIPRI, PTS, CIRIGHTS, FAS, NTI, Freedom House).
3. Normalizes countries to ISO3 and leader identities across sources.
4. Resolves the actual ruler for each country-year with explicit match/conflict flags.
5. Generates provisional category scores per ruler-year from structured indicators.
6. Calls an LLM **only** for ambiguous interpretation under a strict JSON contract.
7. Compares system output against the client matrix; emits a manual-review queue and a confidence score per item.

## Quick start

```bash
# 1. Create a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install the package (editable) with dev + duckdb extras
pip install -e ".[dev,duckdb]"

# 3. Initialize the local data lake folders and SQLite catalog
leaders-db init-data-lake
leaders-db init-db

# 4. Inspect the CLI surface
leaders-db --help
```

> **Status:** the package, CLI surface, database schema, confidence formula, source-vetting docs, and 18 Stage 2 adapters are in place (Phase C.10 integration pass landed 2026-06-19). Phase C data acquisition continues one source at a time; downstream Stage 3–15 resolution, scoring, and reporting are still ahead. Run `pytest` to verify the current implementation and `leaders-db --help` to enumerate the planned commands.

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Matches the requirement document and reference projects (`vfactor`, `sfactor`). |
| DataFrames | pandas + pyarrow | Stable, well-known, the prototype asks for pandas/polars; we start with pandas. |
| Database | SQLite (prototype) / PostgreSQL (future) | Requirement §7 — "PostgreSQL is preferred if the system will become a webapp." |
| ORM / migrations | SQLAlchemy 2.x + raw SQL DDL | SQLAlchemy for the model layer; one checked-in DDL migration for clarity. |
| Validation | Pydantic v2 | Config and LLM input/output schemas. |
| CLI | Typer | Same as `vfactor`/`sfactor`. |
| Excel / Word | openpyxl, python-docx | The client data is in `.xlsx` and `.docx`. |
| LLM | optional adapter under `src/leaders_db/llm/` | Strict JSON-output contract per requirement §10. |
| Tests | pytest | Same as `vfactor`/`sfactor`. |
| Catalog (optional) | DuckDB | Mirrors `vfactor`'s `data/catalog/<project>.duckdb` for fast parquet analytics. |

## Repository layout

```
leaders-db/
├── AGENTS.md                # AI-agent rules (mode selection, always-on rules)
├── README.md                # this file
├── pyproject.toml
├── .gitignore
├── docs/                    # workplan, architecture, coding-guidelines,
│   ├── req/                 # top-level-requirements, requirements-core
│   └── reviews/             # review outputs
├── src/leaders_db/          # Python package
│   ├── cli.py               # Typer CLI
│   ├── config.py            # Pydantic run config
│   ├── env.py               # .env loader
│   ├── paths.py             # data lake path helpers
│   ├── db/                  # SQLAlchemy models + initial migration
│   ├── ingest/              # Stage 0–2 (source availability, client validation loader, external sources)
│   ├── normalize/           # country / leader-name / year normalization
│   ├── resolve/             # Stage 3–5 (country match, leader resolution, indicator extraction)
│   ├── score/               # category scoring + confidence formula
│   ├── validate/            # Stage 12–15 (comparison, manual-review queue, summary report)
│   ├── llm/                 # strict-JSON LLM adapter
│   └── export/              # CSV / markdown / HTML writers
├── tests/                   # pytest, fixtures, smoke
├── data/                    # local data lake (gitignored contents, committed README + metadata)
│   ├── raw/<source>/        # immutable downloaded files + per-source metadata.json
│   ├── processed/           # normalized parquet/csv
│   ├── interim/             # mid-pipeline scratch
│   ├── outputs/             # reports, CSVs, validation summaries
│   ├── logs/                # pipeline run logs
│   └── metadata/            # cross-source catalog metadata
├── research/                # exploratory analyses, leader memos (gitignored)
├── configs/                 # YAML run configs (e.g. prototype-2023.yaml)
├── scripts/                 # one-off shell helpers (init_data_lake.sh, etc.)
├── examples/                # tiny worked examples
└── tmp/                     # scratch (gitignored)
```

## Live smoke scripts

`scripts/` contains one-off helpers that exercise the public API outside
the pytest suite. They are **not** part of CI; they are gated by an env
var (or interactive prompt) to prevent accidental API calls.

| Script | Purpose | Gating |
|---|---|---|
| `scripts/init_data_lake.sh` | Create the data lake skeleton (`data/raw/<source>/`, etc.) for a fresh checkout. | none — safe |
| `scripts/smoke_wikidata_wikipedia.py` | Live HTTP smoke for the Wikidata SPARQL and Wikipedia Action API Stage 2 adapters. Uses an isolated temp dir + temp SQLite (via `LEADERSDB_PROJECT_ROOT`); does **not** touch the production DB or parquet. | `LEADERSDB_SMOKE_YES=1` (else interactive y/N prompt) |

Run a live smoke after a Stage 2 adapter lands:

```bash
LEADERSDB_SMOKE_YES=1 python scripts/smoke_wikidata_wikipedia.py
```

## Important rules

- **No silent overwrites and no client-as-source.** The client matrix is a validation/test reference only; it is not counted as an independent evidence source. The system records `client_score`, `system_proposed_score`, `final_score`, and `score_delta_vs_client` separately. See requirement §3, §9, §12.
- **LLM is for ambiguity only.** Strict JSON output schema. Do not invent scores, do not cite sources not given, do not fetch large datasets repeatedly. See requirement §10 and §18.
- **Degrade gracefully across history.** Post-2000 is easiest; pre-1900 is out of scope. The system must never fill missing historical data with invented values. See requirement §13.
- **Confidence formula is fixed** at 0.35/0.25/0.25/0.15 of source agreement / source authority / evidence specificity / temporal fit. See requirement §11 and `src/leaders_db/score/confidence.py`.

## License & Attribution

MIT — see [`LICENSE`](LICENSE).

External datasets keep their own licenses and citation requirements. The normative source-attribution record is [`docs/source-attributions.md`](docs/source-attributions.md) — that file is the single source of truth and is kept in sync with every implemented Stage 2 adapter. Per AGENTS.md Always-On Rule #15, every public output (Stage 15 report, manual-review queue, exported CSV, run log, CLI end-of-run echo) must include the relevant attribution block; the doc carries the full per-source table, license notes, citations, and the exact attribution text for every source. The summary table in that file is the authoritative index of current sources — do not enumerate sources in this README (it would drift the moment a new source lands).
