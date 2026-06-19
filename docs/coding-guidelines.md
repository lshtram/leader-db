# Coding Guidelines

These apply to the Python package under `src/leaders_db/`. The goal is a reproducible research prototype: a run config in `configs/<name>.yaml` chooses the target year, sources, and pipeline flags, and production code should execute the same orchestration path regardless of those choices.

## General

- Prefer small, explicit modules with single responsibilities.
- Keep changes minimal and targeted; touch only what the request requires.
- Favor deterministic behavior and reproducible outputs.
- Avoid hidden global state; pass dependencies through parameters or constructors.
- Design for extension through typed config, Pydantic schemas, registries, and composition — not through editing core execution code for each new run.
- Keep every source and test file focused; split before files grow unwieldy (mirror the AGENTS.md 400-line convention used by other projects).

## Configuration-Driven Runs

- Treat `RunConfig` and nested Pydantic models as the run contract.
- A normal run is initialized from a YAML config under `configs/`, then run through generic orchestration code.
- Do not require production-code edits to change the target year, source selection, scoring category set, scoring weights, validation thresholds, output paths, or the LLM provider.
- Put run-specific values in YAML config files, generated artifacts, provider metadata, or explicit CLI flags — not in reusable package functions.
- CLI flags may override config values for diagnostics, but the resolved config used by the run must be persisted under `data/logs/<run-id>/` for reproducibility.
- Prefer typed config sections over ad hoc dictionaries once values cross module boundaries.

## Hard-Coded Values

- Production code must not hard-code research parameters: target years, source selection, country lists, leader lists, scoring weights, category rubrics, confidence thresholds, validation cutoffs, output paths, LLM prompts, retry counts, or local data paths.
- Constants are acceptable for stable domain schema values (column names, category keys, the fixed `0.35/0.25/0.25/0.15` confidence weights, source folder names) when documented and owned by the relevant module.
- If a value changes the scientific result of a run, it belongs in config or persisted run metadata.
- Avoid module-level mutable defaults; use `default_factory` for collections.

## Modularity

- Keep side effects at composition boundaries: CLI commands, provider adapters, artifact writers, explicit download/cache operations.
- Keep data providers, normalization, leader resolution, indicator extraction, scoring, confidence, comparison, manual-review, and reporting independently testable.
- Do not let provider-specific column names or value formats leak into generic scoring, comparison, or reporting code. Normalize provider data into the canonical schema first.
- Prefer adding a new adapter or config section over adding broad `if source == "vdem"` branches in core execution paths.
- CLI functions should remain thin: parse/override config, call package functions, display concise results.

## Data And Schema

- The canonical leader/ruler/score schema lives in [`database-schema.md`](database-schema.md) and `src/leaders_db/db/models.py`. Treat those as the source of truth.
- Use ISO3 (`countries.iso3`) as the primary country key. Use `leader_aliases` for name variants.
- Preserve raw values, normalized values, and source provenance separately. Never overwrite `client_score` or `client_matrix_leader_name`.
- Validate required columns, year ranges, duplicate `(country_id, year)` keys, missing `iso3`, and invalid scores at module boundaries.
- Return new DataFrames or records instead of mutating caller-owned inputs unless mutation is explicit in the function contract.
- Prefer `pathlib.Path` over string path manipulation; the helpers in `src/leaders_db/paths.py` are the standard entry point.

## Confidence Formula

The fixed weights are normative. See [`src/leaders_db/score/confidence.py`](../src/leaders_db/score/confidence.py) and requirement §11. Do not invent a different weighting in a one-off script.

## LLM Use

- Use the strict Pydantic input/output schemas in `src/leaders_db/llm/schemas.py`.
- LLM is for ambiguity only (§10, §18). Never use it to invent scores, replace structured datasets, cite sources not given, silently resolve ambiguous leader identity, or fetch large datasets repeatedly when local data exists.
- Persist the LLM prompt, response, and resolved Pydantic output to `data/outputs/llm_calls/<run-id>/` for audit.
- Validate the LLM response against the schema before persisting. Reject and log if validation fails.
- The `llm` extra is **not** installed by default. The package must remain importable and runnable without it.

## Python Standards

- Use type hints for public functions and module boundaries.
- Use Pydantic v2 models for config, run metadata, and any payload that crosses a file, CLI, provider, or artifact boundary.
- Use dataclasses or Pydantic models for structured internal payloads when the shape matters.
- Prefer pure functions for transformations; explicit objects for stateful adapters (e.g. SQLAlchemy session wrappers).
- Raise specific exceptions with actionable messages at validation boundaries.
- Avoid broad `except Exception` except at isolation boundaries where failures are converted into explicit result records.
- Keep imports local only when they avoid optional dependency costs or isolate CLI-only behavior.
- Keep pandas transformations readable: name intermediate frames when logic is non-trivial, sort before grouped time-series operations, make index expectations explicit.

## Database Standards

- The prototype uses SQLite for simplicity; the production path is PostgreSQL.
- SQLAlchemy 2.x declarative ORM is the model layer.
- The canonical DDL is checked in at `src/leaders_db/db/migrations/0001_initial.sql`. Schema changes require a new migration file (`0002_*.sql`).
- Use the session factory from `src/leaders_db/db/session.py`; do not open ad-hoc connections in module code.
- All identifiers that cross module boundaries use the canonical names from the migration (`countries.iso3`, `ruler_years.ruler_year_id`, etc.).

## Testing Standards

- Tests define completed work.
- Add focused pytest coverage for implemented behavior and bug fixes.
- Public/runtime behavior should include boundary proof: CLI path, registry wiring, provider factory, config loading, migration persistence.
- Mock only external dependencies: network, vendor APIs, expensive LLM calls, and filesystem writes when appropriate.
- Prefer small fixtures that prove schema and time-ordering behavior over large opaque datasets.
- For config-driven behavior, test that changing config changes runtime behavior without changing production code.
- Always run the affected test file before committing (`pytest tests/test_<file>.py -q`).

## Safety And Security

- Never commit secrets, API keys, credentials, `.env`, tokens, or private datasets. The `.gitignore` already excludes them; do not bypass it with `git add -f`.
- Treat LLM-generated code/output as untrusted until validated against the Pydantic schema.
- Disallow nondeterministic or unsafe runtime paths in any LLM-generated code path.
- Keep API keys and provider credentials in environment variables or ignored local files only.
- Do not write secrets or raw credential-bearing configs into reports, logs, artifacts, or exceptions.

## Documentation

- Keep `docs/workplan.md`, `docs/architecture.md`, and `docs/req/requirements-core.md` synchronized.
- Use lowercase-kebab-case names for documentation files.
- Add `docs/testing-guide-<module>.md` only for formal TDD/reviewed modules or substantial manual workflows.
- Document new config fields with their purpose, defaults, and reproducibility implications.
- Document new extension points before relying on them in multiple modules.

## Review Checklist

The D2 review checklist. Run this against every code-bearing change
**before** the next task begins. Findings are fixed in place, never
deferred. See [`operational-hygiene.md`](operational-hygiene.md) for the
full review discipline.

- Does the change satisfy documented requirements and only those requirements?
- Does the same production path run different parameters, sources, categories, and validation windows from config alone?
- Are research-changing values in config or persisted metadata rather than hard-coded in package code?
- Are module boundaries preserved between data, normalization, resolution, scoring, confidence, validation, and reporting?
- Are tests meaningful and failing when runtime wiring is removed?
- Are safety constraints enforced around LLM execution?
- Are reproducibility artifacts / version metadata preserved?
- Are docs/workplan updated for status changes?
- Are client-matrix invariants preserved (no silent overwrite, separate score fields)?
- Is the change minimal and targeted (no drive-by refactors of unrelated code)?
- Are no `print()`, `console.log`, or `TODO(debug)` left in src/ or tests/?
- Are no scratch files, orphan docs, orphan modules, orphan configs, or stale fixtures left behind? (See [`operational-hygiene.md`](operational-hygiene.md) § "Cleanup & Coherence".)
- Are all type hints present on public functions and module boundaries?
- Are Pydantic models used for any payload that crosses a file/CLI/provider/artifact boundary?
- Are the `0.35/0.25/0.25/0.15` confidence weights untouched (no one-off override)?
- Is the LLM response validated against the strict Pydantic schema before persistence?
- Is `git status` clean of `__pycache__`, `*.pyc`, `.log`, `.sqlite`, `data/raw/<source>/*.{xlsx,csv,...}`?

## Operational Hygiene

Two project-wide rules govern every operation:

1. **Cleanup & coherence** — no slop, no junk, no stale files after any
   operation. See [`operational-hygiene.md`](operational-hygiene.md) §
   "Rule 1" for the full checklist.
2. **Review discipline** — full code review after every code-bearing
   change, findings fixed in place, never deferred. See
   [`operational-hygiene.md`](operational-hygiene.md) § "Rule 2" for
   the loop and what counts as non-trivial.

These are non-negotiable. They apply to every mode, every phase, every
agent session, and every human operator.
