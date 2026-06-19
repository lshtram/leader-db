# AGENTS.md — leaders-db Agent Rules

This file tells AI agents how to operate in this repository. **Read it first** whenever you open this workspace, then read [`docs/workplan.md`](docs/workplan.md) and [`docs/req/top-level-requirements.md`](docs/req/top-level-requirements.md).

The authoritative product brief is **`docs/req/top-level-requirements.md`**. The stage numbering in this file (Stage 0–15) refers to the pipeline stages defined there in §8.

---

## 1. What This Project Is

`leaders-db` is a Python data-collection and validation prototype for the **Leaders Database** — a structured, auditable, confidence-scored database of world political leaders and their category ratings, designed to *reproduce, challenge, explain, and validate* the client's existing 2023 matrix.

The system combines:

- structured dataset ingestion (Archigos, REIGN, Leader Survival, V-Dem, World Bank WDI/WGI, Transparency CPI, UCDP, SIPRI, PTS, CIRIGHTS, FAS, NTI, Freedom House),
- rule-based country/leader normalization,
- LLM-assisted interpretation **only where structured data is insufficient** (strict JSON contract),
- explicit confidence scoring per item,
- a manual-review queue with no silent overwrites of the client matrix.

This is a research prototype, not a live service, and not a political-judgment product.

## 2. Authoritative starting points

Read in this order before doing any non-trivial work:

1. [`docs/req/top-level-requirements.md`](docs/req/top-level-requirements.md) — product brief, §1–18. The numbering of pipeline stages in this AGENTS.md follows §8 there.
2. [`docs/workplan.md`](docs/workplan.md) — current status, active phase, next steps.
3. [`docs/architecture.md`](docs/architecture.md) — system design and module boundaries.
4. [`docs/req/requirements-core.md`](docs/req/requirements-core.md) — the locally tracked REQ-* / NFR-* baseline derived from the brief.
5. [`docs/coding-guidelines.md`](docs/coding-guidelines.md) — style, banned patterns, review checklist.
6. [`docs/data-sources.md`](docs/data-sources.md) — the per-source registry for `data/raw/<source>/`.
7. [`docs/local-data-store.md`](docs/local-data-store.md) — the data-lake folder rules.
8. [`docs/database-schema.md`](docs/database-schema.md) — the 11-table prototype schema.

Do not re-derive the schema or the pipeline order from comments in code; both are normative in the docs above.

## 3. Modes of Work

### 3.1 Pragmatic Implementation Mode (default for now)

Use this mode unless the user explicitly asks for TDD, a formal review gate, or a documentation-only investigation.

- Read the relevant code and docs before editing.
- Make minimal, surgical changes — touch only what the request requires.
- Add or update focused `pytest` coverage that defines the completed work.
- Run the smallest meaningful verification command first, usually `pytest -q` or a single test file.
- Keep `docs/workplan.md`, `docs/architecture.md`, and `docs/req/requirements-core.md` in sync.

### 3.2 TDD Mode — only when explicitly requested

When the user says **"TDD"**, follow `~/.config/opencode/dev-process.md` strictly with no phase skipping. The first TDD module is most likely Stage 9 (leader resolver for 2023) or Stage 14 (confidence scoring) — confirm with the user first.

Current tooling:

| Concern | Tool / Command |
|---|---|
| Package manager | `pip` (or `uv`) against `pyproject.toml`; `.venv` may exist locally |
| Test command | `pytest -q` |
| Type checker | `mypy` (if enabled later) |
| Lint / format | `ruff` (configured in `pyproject.toml`) |
| LLM adapter | optional; the `llm` extra is **not** installed by default |

### 3.3 Quick Fix Mode

For localized corrections that do not change product behavior broadly:

- Read the relevant code and docs first.
- Make the minimal targeted change.
- Run the affected test file (e.g. `pytest tests/test_<file>.py -q`).
- Self-review against [`docs/coding-guidelines.md`](docs/coding-guidelines.md) — fix findings in place, do not defer (Always-On Rule #14).
- Clean up after the operation per Always-On Rule #13 — no debug prints, no scratch files left behind, no commented-out code, no stale fixtures.
- Commit with a conventional commit only when explicitly asked.

### 3.4 Exploration / Documentation Mode

- Prefer read-and-report unless edits are explicitly requested.
- Keep `docs/workplan.md`, `docs/architecture.md`, and `docs/req/requirements-core.md` consistent.
- Cite source URLs in `docs/data-sources.md` for any new external dataset.

### 3.5 Debug Mode

- Capture the full error / symptom before forming a hypothesis.
- Route resistant bugs to `debugger`, then `debugger-hard` if needed.
- Remove **all** `TODO(debug)` instrumentation, debug print statements, scratch notebooks, and one-off reproducers before commit (Always-On Rule #13). If a reproducer has lasting value, move it under `tests/`; otherwise delete or relocate it to `tmp/` with a date prefix.
- After the bug is fixed, run a self-review (Always-On Rule #14) and a regression test.

## 4. Always-On Rules

These apply in every mode, every session:

1. **Follow [`docs/coding-guidelines.md`](docs/coding-guidelines.md).** Style, banned patterns, type-safety rules, and the D2 review checklist live there.
2. **Use conventional commits.** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. No mixed-up commits.
3. **Run the affected tests before committing.** `pytest -q` for a quick pass, full suite before merge.
4. **Never commit secrets, tokens, credentials, or `.env` files.** The `.gitignore` already excludes them; do not bypass it with `git add -f`.
5. **Prefer minimal, targeted changes over broad rewrites.** Do not refactor unrelated modules in the same commit.
6. **The client matrix is validation/test reference only, never evidence and never silently overwritten.** It must not count as an independent source for leader identity, factual claims, category scoring, source agreement, or source authority. Always carry `client_score`, `system_proposed_score`, `final_score`, and `score_delta_vs_client` separately. (Requirement §3, §9, §12.)
7. **LLM is for ambiguity only.** Use the strict JSON contract in `src/leaders_db/llm/`. Never invent scores, never cite sources not given, never fetch large datasets repeatedly when local data exists. (Requirement §10, §18.)
8. **No invented historical data.** Older years degrade gracefully: fewer indicators, more uncertainty, more manual review, more "not available" fields, more confidence penalties. (Requirement §13.)
9. **Use the local data lake rules.** Raw inputs in `data/raw/<source>/` with a `metadata.json`; normalized outputs in `data/processed/`; never edit a raw file in place. See [`docs/local-data-store.md`](docs/local-data-store.md).
10. **Confidence formula is fixed.** `0.35·agreement + 0.25·authority + 0.25·specificity + 0.15·temporal_fit` per requirement §11. Do not invent a different weighting in a one-off script.
11. **Use `./tmp` for transient files.** Project-scoped scratch, not `/tmp`. Add it to `.gitignore` (already done).
12. **Check for existing materials before starting work.** Run `git status` and skim `research/`, `data/processed/`, and `docs/reviews/` so we do not redo something already committed.
13. **Clean up after every operation — no slop.** After any edit, debug session, exploration, experiment, or refactor, the agent must remove `TODO(debug)` instrumentation, delete or relocate scratch files (into `tmp/` or `research/`), kill ad-hoc scripts left in the project root or under `src/`, drop commented-out code and "fix later" notes, and remove stale fixtures. The project must stay coherent: no junk files, no half-finished experiments in `src/`, no debug print statements, no orphan docs, no stale `__pycache__` / `.pyc` / log files committed. Run `git status` and `find . -name '__pycache__' -o -name '*.pyc'` before considering work done. Detail in [`docs/operational-hygiene.md`](docs/operational-hygiene.md).
14. **Full code review after every code-bearing change — fix findings immediately, do not defer.** Every module, function, class, bug fix, schema migration, or non-trivial edit must be self-reviewed against [`docs/coding-guidelines.md`](docs/coding-guidelines.md) (style, banned patterns, type safety, D2 review checklist) **before the next task begins**. Run the affected tests, run `ruff` (when configured), and address findings in place. For non-trivial changes (new modules, score-formula tweaks, LLM adapter wiring, schema migrations, anything that touches the canonical confidence formula or the strict LLM contract), route to the `reviewer` agent via the project-manager. Stacking unreviewed code is forbidden — no code lands without a clean review pass. Detail in [`docs/operational-hygiene.md`](docs/operational-hygiene.md).
15. **Carry source attribution forward in every public output.** Every Stage 15 summary report, manual-review queue, exported CSV, LLM rationale, and `README.md` must include the attribution block from [`docs/source-attributions.md`](docs/source-attributions.md). The pipeline must never publish output without attribution. The attribution text for a source is normative — the exact wording in `source-attributions.md` is what the pipeline emits, not a paraphrase. When a new source is added or an existing source is upgraded, the change is reflected in `source-attributions.md` in the same commit; deferring attribution updates is forbidden.

## 5. Key Documents

| Document | Purpose |
|---|---|
| [`docs/req/top-level-requirements.md`](docs/req/top-level-requirements.md) | Authoritative product brief (the "what") |
| [`docs/workplan.md`](docs/workplan.md) | Current status, active phase, next steps, done history |
| [`docs/architecture.md`](docs/architecture.md) | System design, module boundaries, data flow |
| [`docs/coding-guidelines.md`](docs/coding-guidelines.md) | Style, banned patterns, D2 review checklist |
| [`docs/operational-hygiene.md`](docs/operational-hygiene.md) | Cleanup-coherence + review discipline (Always-On Rules #13, #14) |
| [`docs/source-attributions.md`](docs/source-attributions.md) | Every source + what we extract + license + citation + attribution text (Always-On Rule #15) |
| [`docs/req/requirements-core.md`](docs/req/requirements-core.md) | Locally tracked REQ-* / NFR-* baseline |
| [`docs/data-sources.md`](docs/data-sources.md) | Per-source registry: URL, version, license, coverage |
| [`docs/local-data-store.md`](docs/local-data-store.md) | `data/raw` vs `data/processed` vs `data/catalog` rules |
| [`docs/database-schema.md`](docs/database-schema.md) | The 11-table prototype schema |
| [`docs/source-vetting-plan.md`](docs/source-vetting-plan.md) | Phase B: per-source paywall/license/availability probe plan |
| [`docs/reviews/`](docs/reviews/) | Reviewer gate outputs (initially empty) |
| [`configs/`](configs/) | YAML run configs, starting with `prototype-2023.yaml` |
| `~/.config/opencode/dev-process.md` | Canonical TDD cycle (only when user says "TDD") |

## 6. Current Project Structure

```
src/leaders_db/
├── __init__.py
├── cli.py                  # Typer CLI entrypoint exposed as `leaders-db`
├── config.py               # Pydantic run config schema + YAML loading
├── env.py                  # .env loader
├── paths.py                # data lake path helpers (raw/processed/interim/outputs/...)
├── db/
│   ├── engine.py           # SQLAlchemy engine factory (SQLite default, PostgreSQL-ready)
│   ├── session.py          # session scope
│   ├── models.py           # ORM models for the 11 prototype tables
│   └── migrations/0001_initial.sql  # checked-in DDL for the prototype schema
├── ingest/                 # Stage 0–2
│   ├── source_availability.py  # Stage 0
│   ├── client_matrix.py        # Stage 1
│   ├── archigos.py             # Stage 2 — one file per priority source
│   ├── leader_survival.py
│   ├── reign.py
│   ├── vdem.py
│   ├── freedom_house.py
│   ├── world_bank_wdi.py
│   ├── world_bank_wgi.py
│   ├── transparency_cpi.py
│   ├── ucdp.py
│   ├── pts.py
│   ├── cirights.py
│   ├── sipri.py
│   ├── fas.py
│   ├── nti.py
│   └── external.py         # generic ingestion helpers
├── normalize/              # country / leader-name / year normalization
│   ├── countries.py
│   ├── leader_names.py
│   └── years.py
├── resolve/                # Stage 3–5
│   ├── country_match.py        # Stage 3
│   ├── leader_resolver.py      # Stage 4
│   └── indicators.py           # Stage 5
├── score/                  # category scoring + confidence
│   ├── normalization.py        # 0–1 / 1–10 scaling helpers
│   ├── political_freedom.py    # one module per category (per requirement §6/§9)
│   ├── corruption.py
│   ├── economic.py
│   ├── domestic_violence.py
│   ├── peace.py
│   ├── nuclear.py              # lighter module per requirement §6
│   └── confidence.py           # Stage 14, the fixed 0.35/0.25/0.25/0.15 formula
├── validate/               # Stage 12–15
│   ├── comparison.py           # Stage 12
│   ├── manual_review_queue.py  # Stage 14
│   └── summary_report.py       # Stage 15
├── llm/                    # strict-JSON LLM adapter (optional)
│   ├── caller.py               # provider-agnostic JSON output wrapper
│   └── schemas.py              # Pydantic input/output per requirement §10
└── export/                 # CSV / markdown / HTML writers
    ├── csv_writer.py
    └── markdown_report.py

data/
├── raw/<source>/           # one folder per priority source + client_existing
├── processed/              # normalized parquet/csv
├── interim/                # mid-pipeline scratch
├── outputs/                # reports and CSVs
├── logs/                   # run logs
└── metadata/               # cross-source catalog metadata

tests/
├── conftest.py
├── test_imports.py
├── test_config.py
├── test_paths.py
├── test_db_schema.py
├── test_llm_schemas.py
├── test_normalize_countries.py
├── test_score_confidence.py
└── fixtures/

configs/
└── prototype-2023.yaml     # first run config (target year = 2023)

research/                   # exploratory analyses and leader memos (gitignored)
scripts/                    # one-off shell helpers
examples/                   # tiny worked examples
tmp/                        # scratch (gitignored)
```

## 7. Local Data Lake And Catalog

The project is local-first. We use a small data lake on disk plus a SQLite catalog, not a service.

Layer rules:

- `data/raw/<source>/`: immutable or provider-native source files. Each folder carries a `metadata.json` (source name, version, download date, source URL, license, checksum, ingestion status, coverage).
- `data/processed/`: deterministic normalized parquet/csv. Re-runs are idempotent.
- `data/interim/`: mid-pipeline scratch (e.g. cross-source joined frames before scoring).
- `data/outputs/`: reports, validation CSVs, manual-review queue, summary markdown.
- `data/logs/`: per-run log files.
- `data/metadata/`: cross-source catalog metadata (e.g. `country_aliases.csv`, `source_authority_table.csv`).
- `research/`: derived exploratory analyses and leader memos. Not in the data lake — treated like `vfactor`'s `research/` bucket.

Full rules in [`docs/local-data-store.md`](docs/local-data-store.md).

## 8. Important Commands

The CLI is exposed as `leaders-db` once the package is installed. Surface only at this stage (Stage 0+ stubs):

```bash
# Setup
leaders-db init-data-lake          # create data/raw/<source>/ folders if missing
leaders-db init-db                 # apply db/migrations/0001_initial.sql to a fresh SQLite file

# Stage 0 — source availability
leaders-db check-source-availability

# Stage 1 — ingest client matrix
leaders-db ingest-client-matrix --year 2023

# Stage 2 — ingest external sources
leaders-db ingest-source --source vdem
leaders-db ingest-source --source world_bank_wdi
# ... one flag per priority source

# Stage 3 — country matching
leaders-db match-countries

# Stage 4 — leader resolution
leaders-db resolve-leaders --year 2023

# Stage 5 — indicator extraction
leaders-db extract-indicators --year 2023

# Stage 9–12 — scoring
leaders-db score-category --year 2023 --category political_freedom
leaders-db score-all --year 2023
leaders-db compute-confidence --year 2023

# Stage 12–15 — comparison, manual review, summary
leaders-db compare-vs-client --year 2023
leaders-db build-review-queue --year 2023
leaders-db summary-report --year 2023
```

Run `leaders-db --help` for the live list as stages ship.

## 9. Picking Up Mid-Project

1. Read [`docs/workplan.md`](docs/workplan.md) (current status) and the latest `Done History` entry.
2. Re-read [`docs/req/top-level-requirements.md`](docs/req/top-level-requirements.md) §8 (pipeline stages) and §16 (acceptance criteria) to anchor the next step.
3. Inspect `data/raw/`, `data/processed/`, and `research/` before assuming a clean slate.
4. Run `pytest -q` to confirm the baseline is green.
5. Identify which pipeline stage the active work belongs to (Stage 0–15) and resume from there.
