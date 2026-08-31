# AGENTS.md — leaders-db Agent Rules

This file tells AI agents how to operate in this repository. **Read it first** whenever you open this workspace, then read [`docs/workplan.md`](docs/workplan.md), [`docs/requirements/top-level-requirements.md`](docs/requirements/top-level-requirements.md), and [`docs/methodology/ranking-evaluation-criteria.md`](docs/methodology/ranking-evaluation-criteria.md). For score-bearing manual/internet ruler-quality work, also read [`docs/methodology/cited-evaluation-calibration.md`](docs/methodology/cited-evaluation-calibration.md) and the relevant chapter guide under [`docs/methodology/chapter-guides/`](docs/methodology/chapter-guides/).

The authoritative product brief is **`docs/requirements/top-level-requirements.md`**. The stage numbering in this file (Stage 0–15) refers to the pipeline stages defined there in §8.

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

1. [`docs/requirements/top-level-requirements.md`](docs/requirements/top-level-requirements.md) — product brief, §1–18. The numbering of pipeline stages in this AGENTS.md follows §8 there.
2. [`docs/workplan.md`](docs/workplan.md) — current status, active phase, next steps.
3. [`docs/methodology/ranking-evaluation-criteria.md`](docs/methodology/ranking-evaluation-criteria.md) — the ruler-quality question bank, including the chapter 7/8 scoring criteria and question IDs (for example 8B.* effectiveness questions).
4. [`docs/methodology/cited-evaluation-calibration.md`](docs/methodology/cited-evaluation-calibration.md) — required chapter-level calibration contract, including sparse-evidence and bias rules.
5. [`docs/methodology/chapter-guides/readme.md`](docs/methodology/chapter-guides/readme.md) — the eight active chapter guides; each uses ten questions as evidence lenses for one score.
6. [`docs/architecture/overview.md`](docs/architecture/overview.md) — system design and module boundaries.
7. [`docs/requirements/core.md`](docs/requirements/core.md) — the locally tracked REQ-* / NFR-* baseline derived from the brief.
8. [`docs/process/coding-guidelines.md`](docs/process/coding-guidelines.md) — style, banned patterns, review checklist.
9. [`docs/sources/registry.md`](docs/sources/registry.md) — the per-source registry for `data/raw/<source>/`.
10. [`docs/architecture/local-data-store.md`](docs/architecture/local-data-store.md) — the data-lake folder rules.
11. [`docs/architecture/database-schema.md`](docs/architecture/database-schema.md) — the 11-table prototype schema.

Do not re-derive the schema or the pipeline order from comments in code; both are normative in the docs above.

## 3. Modes of Work

### 3.1 Pragmatic Implementation Mode (default for now)

Use this mode unless the user explicitly asks for TDD, a formal review gate, or a documentation-only investigation.

- Read the relevant code and docs before editing.
- Make minimal, surgical changes — touch only what the request requires.
- Add or update focused `pytest` coverage that defines the completed work.
- Run the smallest meaningful verification command first, usually `pytest -q` or a single test file.
- Keep `docs/workplan.md`, `docs/architecture/overview.md`, and `docs/requirements/core.md` in sync.

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
- Self-review against [`docs/process/coding-guidelines.md`](docs/process/coding-guidelines.md) — fix findings in place, do not defer (Always-On Rule #14).
- Clean up after the operation per Always-On Rule #13 — no debug prints, no scratch files left behind, no commented-out code, no stale fixtures.
- Commit with a conventional commit only when explicitly asked.

### 3.4 Exploration / Documentation Mode

- Prefer read-and-report unless edits are explicitly requested.
- Keep `docs/workplan.md`, `docs/architecture/overview.md`, and `docs/requirements/core.md` consistent.
- Cite source URLs in `docs/sources/registry.md` for any new external dataset.

### 3.5 Debug Mode

- Capture the full error / symptom before forming a hypothesis.
- Route resistant bugs to `debugger`, then `debugger-hard` if needed.
- Remove **all** `TODO(debug)` instrumentation, debug print statements, scratch notebooks, and one-off reproducers before commit (Always-On Rule #13). If a reproducer has lasting value, move it under `tests/`; otherwise delete or relocate it to `tmp/` with a date prefix.
- After the bug is fixed, run a self-review (Always-On Rule #14) and a regression test.

### 3.6 Subagent And Search Tool Reliability

OpenCode subagents and broad `glob` / `grep` / ripgrep-backed searches can hang silently in some environments. Treat search-heavy delegation as a reliability risk and constrain it deliberately:

- Prefer direct `read` calls when the likely file path is known. Do not delegate a simple file lookup to a subagent.
- Keep subagent tasks narrow and bounded: specify the exact directory, filename patterns, maximum search rounds, and expected final response.
- Always scope `glob` and `grep` to the repository root or a narrower project directory. Do **not** let searches default to `$HOME`, `/`, parent workspaces, `/tmp`, or other external absolute paths.
- Avoid broad patterns such as `**/*` unless there is no practical alternative; prefer patterns like `src/**/*.py`, `docs/**/*.md`, or a named package subdirectory.
- Avoid concurrent OpenCode/Codex sessions searching the same repository when possible; concurrent `grep` / `glob` searches have been observed to block each other.
- Avoid `ask` permissions in headless or delegated subagent flows. Use explicit `allow` / `deny` rules so a nested permission prompt cannot silently stall the parent.
- Keep transient files inside project `tmp/`, not `/tmp`, so delegated file operations stay within the workspace boundary.
- If a subagent produces no progress after search tool calls, interrupt early, inspect for runaway `rg` / `opencode` processes, and retry with a narrower prompt rather than waiting indefinitely.
- When diagnosing a hang, capture OpenCode version, provider/model, OS, prompt shape, active sessions, and debug logs (`--print-logs --log-level DEBUG`) before changing workflow assumptions.

## 4. Always-On Rules

These apply in every mode, every session:

1. **Follow [`docs/process/coding-guidelines.md`](docs/process/coding-guidelines.md).** Style, banned patterns, type-safety rules, and the D2 review checklist live there.
2. **Use conventional commits.** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. No mixed-up commits.
3. **Run the affected tests before committing.** `pytest -q` for a quick pass, full suite before merge.
4. **Never commit secrets, tokens, credentials, or `.env` files.** The `.gitignore` already excludes them; do not bypass it with `git add -f`.
5. **Prefer minimal, targeted changes over broad rewrites.** Do not refactor unrelated modules in the same commit.
6. **The client matrix is validation/test reference only, never evidence and never silently overwritten.** It must not count as an independent source for leader identity, factual claims, category scoring, source agreement, or source authority. Always carry `client_score`, `system_proposed_score`, `final_score`, and `score_delta_vs_client` separately. (Requirement §3, §9, §12.)
7. **Scoring LLMs are for ambiguity only.** Adjudicators use the strict JSON contract in `src/leaders_db/llm/`. The ruler evidence researcher is the explicit exception: it performs cited external research in a permissive notebook, which a separate no-search formatter converts to the strict dossier. Never invent scores or sources, and never re-fetch large datasets when local data exists. (Requirement §10, §18.)
8. **No invented historical data.** Older years degrade gracefully: fewer indicators, more uncertainty, more manual review, more "not available" fields, more confidence penalties. (Requirement §13.)
9. **Use the local data lake rules.** Raw inputs in `data/raw/<source>/` with a `metadata.json`; normalized outputs in `data/processed/`; never edit a raw file in place. See [`docs/architecture/local-data-store.md`](docs/architecture/local-data-store.md).
10. **Confidence formula is fixed.** `0.35·agreement + 0.25·authority + 0.25·specificity + 0.15·temporal_fit` per requirement §11. Do not invent a different weighting in a one-off script.
11. **Use `./tmp` for transient files.** Project-scoped scratch, not `/tmp`. Add it to `.gitignore` (already done).
12. **Check for existing materials before starting work.** Run `git status` and skim `research/`, `data/processed/`, and `docs/reviews/` so we do not redo something already committed.
13. **Clean up after every operation — no slop.** After any edit, debug session, exploration, experiment, or refactor, the agent must remove `TODO(debug)` instrumentation, delete or relocate scratch files (into `tmp/` or `research/`), kill ad-hoc scripts left in the project root or under `src/`, drop commented-out code and "fix later" notes, and remove stale fixtures. The project must stay coherent: no junk files, no half-finished experiments in `src/`, no debug print statements, no orphan docs, no stale `__pycache__` / `.pyc` / log files committed. Run `git status` and `find . -name '__pycache__' -o -name '*.pyc'` before considering work done. Detail in [`docs/process/operational-hygiene.md`](docs/process/operational-hygiene.md).
14. **Full code review after every code-bearing change — fix findings immediately, do not defer.** Every module, function, class, bug fix, schema migration, or non-trivial edit must be self-reviewed against [`docs/process/coding-guidelines.md`](docs/process/coding-guidelines.md) (style, banned patterns, type safety, D2 review checklist) **before the next task begins**. Run the affected tests, run `ruff` (when configured), and address findings in place. For non-trivial changes (new modules, score-formula tweaks, LLM adapter wiring, schema migrations, anything that touches the canonical confidence formula or the strict LLM contract), route to the `reviewer` agent via the project-manager. Stacking unreviewed code is forbidden — no code lands without a clean review pass. Detail in [`docs/process/operational-hygiene.md`](docs/process/operational-hygiene.md).
15. **Carry source attribution forward in every public output.** Every Stage 15 summary report, manual-review queue, exported CSV, LLM rationale, and `README.md` must include the attribution block from [`docs/sources/attributions.md`](docs/sources/attributions.md). The pipeline must never publish output without attribution. The attribution text for a source is normative — the exact wording in `docs/sources/attributions.md` is what the pipeline emits, not a paraphrase. When a new source is added or an existing source is upgraded, the change is reflected in `docs/sources/attributions.md` in the same commit; deferring attribution updates is forbidden.
16. **Score-bearing manual/internet evaluations require chapter guides and calibration.** The required role chain is one ruler-period `internet-research` workflow, iterative review by a no-search evidence reviewer for every selected chapter (up to three targeted rounds), a separate no-search formatter, one `ruler-chapter-judge` per chapter/year batch, and a final score/order auditor. The parent retains the complete local package and cumulative evidence ledger. Every researcher prompt receives only a short briefing, its selected chapter guide/questions, and a bounded index of relevant resources already found; never stuff the complete local evidence package, all guides, or raw prior tool history into a prompt. Fresh compact chapter sessions may be used in research-only quality/token experiments, but they do not enter the score-bearing flow until compact reviewer continuation and formatter handoff pass their own end-to-end gate. Researchers work through chapters in order, store cited evidence once for reuse across lenses, and search directly until reasonably saturated. Missing lenses reduce confidence rather than mechanically lowering or invalidating the score. Any score-bearing record must follow [`docs/methodology/cited-evaluation-calibration.md`](docs/methodology/cited-evaluation-calibration.md).
17. **Constrain subagents and search tools to avoid silent hangs.** Search-heavy subagents must use explicit project-scoped paths, narrow patterns, bounded search rounds, and no nested `ask` permission flow. Prefer direct reads over delegated exploration when files are known. If `glob` / `grep` / `rg` stalls, interrupt and retry narrower; do not wait indefinitely. Detail in §3.6 and [`docs/process/operational-hygiene.md`](docs/process/operational-hygiene.md).
18. **Persist through monitored long-running work.** When the user asks for an end-to-end run, monitoring, or completion, do not return control while required work or safely recoverable background work remains. Keep the session active; monitor durable jobs and child processes; renew or recover leases; stop exact orphan processes after supervisor timeouts; resume from trusted checkpoints; run downstream judging, audit, and publication stages; and respond only when the requested outcome is complete or genuinely requires new user authority. A progress update is not a terminal handoff.
19. **Never turn a monitoring boundary into a terminal response.** Tool yield limits, quiet worker output, elapsed turn time, context pressure, and an approaching response boundary are not blockers and do not authorize a final answer while monitored work remains. Continue polling in the same turn, using short waits that preserve user updates; if execution infrastructure interrupts the turn, reconnect to the durable supervisor and resume from the ledger before doing anything else. Before any final response on an end-to-end run, verify from persisted state that every requested stage is complete, no required job is pending/running/retryable, the audit passed, and the final publication artifact exists and validates. If any check fails, continue monitoring or recovery instead of returning.
20. **Preflight model transport size and split losslessly.** Before launching any corpus-reader, reviewer, formatter, or judge call, measure the complete serialized request (instructions, evidence, metadata, and response schema) against the provider's character and token limits with a safety margin. Split oversized inputs deterministically by stable document units; preserve source IDs, hashes, unit ranges, and locators; and merge and deduplicate the results through an audited manifest. Retrying an unchanged over-limit request is not a recovery strategy. Publication remains blocked until every original unit is represented or explicitly dispositioned.
21. **Obtain explicit approval for API-key-backed model runs; honor end-to-end authorization on the subscription surface.** The default model execution surface is the existing Codex/subscription workflow. A user instruction to run a named pipeline or experiment end to end authorizes every planned Codex/subscription model stage, bounded retry, and quota-only continuation needed to complete that scope without renewed approval at phase boundaries. Before the first call, the agent shall still create and validate zero-call preflights, persist provider/model/reasoning, call and token ceilings, expected artifacts, and production eligibility, and remain within those reviewed bounds. Stop only for a material scientific, structural, provenance, identity, transport, quality, or non-quota failure; a model substitution; a directly billed surface; or a material expansion beyond the authorized scope. Before using `OPENAI_API_KEY`, another provider credential, or any directly billed model API—even for a diagnostic, cache probe, quality review, retry, or experiment—the agent must notify the user and obtain explicit approval for a bounded run stating provider/model, purpose, maximum calls, estimated input/cached-input/output tokens, estimated cost and hard spending ceiling, expected artifacts, and eligibility. Never treat a repository credential as authorization or switch from subscription to direct billing silently. Record approved or end-to-end-authorized limits and actual usage in the run manifest.
22. **Fix the general pipeline, never a failed test run.** Treat scientific, structural, provenance, identity, transport, and quality failures as immutable diagnostics. Diagnose and fix the reusable rule, then use a fresh run directory and release identity; never repair or relabel such a failed run into a pass. A run stopped solely because its aggregate input or output quota was exhausted may continue in place under an existing end-to-end subscription authorization when an append-only amendment stays within its recorded run envelope and binds the exact settled ledger prefix. Raising that envelope requires explicit user approval of the increased bounded quota. The request inventory, model, prompts, schemas, artifacts, and call ceiling must remain unchanged; settled calls must never be rerun, all usage remains cumulative, and any non-quota failure still requires a fresh run. Any exception, normalization, retry allowance, concurrency policy, or budget rule must be prospective, tested, and independently reviewed before execution.

## 5. Key Documents

| Document | Purpose |
|---|---|
| [`docs/requirements/top-level-requirements.md`](docs/requirements/top-level-requirements.md) | Authoritative product brief (the "what") |
| [`docs/workplan.md`](docs/workplan.md) | Current status, active phase, next steps, done history |
| [`docs/methodology/ranking-evaluation-criteria.md`](docs/methodology/ranking-evaluation-criteria.md) | Ruler-quality question bank and scoring criteria, including chapter 7/8 question IDs |
| [`docs/methodology/cited-evaluation-calibration.md`](docs/methodology/cited-evaluation-calibration.md) | Required calibration fields, bias controls, and one-judge workflow for score-bearing cited/manual evaluations |
| [`docs/methodology/chapter-guides/readme.md`](docs/methodology/chapter-guides/readme.md) | Eight active chapter guides: ten evidence lenses and one final score per chapter |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | System design, module boundaries, data flow |
| [`docs/process/coding-guidelines.md`](docs/process/coding-guidelines.md) | Style, banned patterns, D2 review checklist |
| [`docs/process/operational-hygiene.md`](docs/process/operational-hygiene.md) | Cleanup-coherence + review discipline (Always-On Rules #13, #14) |
| [`docs/sources/attributions.md`](docs/sources/attributions.md) | Every source + what we extract + license + citation + attribution text (Always-On Rule #15) |
| [`docs/requirements/core.md`](docs/requirements/core.md) | Locally tracked REQ-* / NFR-* baseline |
| [`docs/sources/registry.md`](docs/sources/registry.md) | Per-source registry: URL, version, license, coverage |
| [`docs/architecture/local-data-store.md`](docs/architecture/local-data-store.md) | `data/raw` vs `data/processed` vs `data/catalog` rules |
| [`docs/architecture/database-schema.md`](docs/architecture/database-schema.md) | The 11-table prototype schema |
| [`docs/sources/vetting/plan.md`](docs/sources/vetting/plan.md) | Phase B: per-source paywall/license/availability probe plan |
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

Full rules in [`docs/architecture/local-data-store.md`](docs/architecture/local-data-store.md).

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
2. Re-read [`docs/requirements/top-level-requirements.md`](docs/requirements/top-level-requirements.md) §8 (pipeline stages) and §16 (acceptance criteria) to anchor the next step.
3. Inspect `data/raw/`, `data/processed/`, and `research/` before assuming a clean slate.
4. Run `pytest -q` to confirm the baseline is green.
5. Identify which pipeline stage the active work belongs to (Stage 0–15) and resume from there.

## 10. Customer-Facing Writing

Use [`.agents/skills/customer-methodology-writing/SKILL.md`](.agents/skills/customer-methodology-writing/SKILL.md) for customer-facing methodology, pipeline, research, evaluation, report, guide, presentation, and explanatory prose.

Core rules:

- Describe the work factually; do not advertise its virtues.
- Describe what each role and stage does. Use negative wording only for a concrete, material risk, exclusion, or boundary, and pair it with the control that addresses the risk.
- Write clear adult prose. Plain language removes unnecessary jargon while preserving precision and nuance.
- State each substantive point once in the best location. Repeat only for a necessary action, a material extension, or a safety-critical control.
