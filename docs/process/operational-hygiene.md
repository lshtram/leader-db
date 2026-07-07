# Operational Hygiene

This document consolidates two always-on rules that govern how work happens
in this repository:

- **Cleanup & coherence** — no junk, no slop, no stale files after any
  operation (Always-On Rule #13 in [`AGENTS.md`](../../AGENTS.md)).
- **Review discipline** — full code review after every code-bearing change,
  findings fixed in place, never deferred to "later in the project"
  (Always-On Rule #14 in [`AGENTS.md`](../../AGENTS.md)).
- **Subagent/search reliability** — constrained subagent delegation and
  project-scoped `glob` / `grep` usage to avoid silent hangs (Always-On
  Rule #17 in [`AGENTS.md`](../../AGENTS.md)).

These rules are non-negotiable. They apply to every agent session, every
mode (Pragmatic Implementation, TDD, Quick Fix, Exploration, Debug),
every phase (A → B → C → D → E), and every human operator.

## Why these rules exist

The project is research-oriented and built iteratively. Without explicit
hygiene rules, agents (and humans) tend to leave behind:

- `print()` and `TODO(debug)` lines in source code.
- Scratch notebooks and one-off scripts in the project root.
- Commented-out "we might want this later" code.
- Orphan docs, half-finished experiments, stale fixtures.
- Stacked unreviewed code that "looks fine for now" but accumulates
  technical debt.
- Search-heavy subagents that silently hang after broad `glob` / `grep`
  calls, leaving the parent session blocked with no useful progress.

By Phase E (activation) the codebase becomes hard to read, hard to test,
hard to reproduce, and hard to review. These rules keep the project
coherent from day one.

## Rule 1 — Cleanup & Coherence

### Scope

Every operation. Specifically:

- A new module, function, class, or test is written.
- A bug is debugged.
- A feature is explored or prototyped.
- A refactor is performed.
- A doc is drafted.
- A config is changed.

### What "cleanup" means

After the operation, before the next task begins, the agent must:

1. **Remove instrumentation.** Delete any `print()`, `console.log`, debug
   log statements, or `TODO(debug)` markers added during the work.
2. **Delete or relocate scratch files.**
   - If a one-off reproducer has lasting value, move it under `tests/`
     and turn it into a proper regression test.
   - Otherwise, delete it or relocate it to `tmp/<YYYY-MM-DD>-<slug>/`
     with a date prefix.
3. **Delete scratch scripts in the wrong place.** Ad-hoc Python or shell
   scripts in the project root or under `src/` are forbidden. They
   belong in:
   - `scripts/` for reusable shell helpers
   - `research/<topic>-<date>/` for exploratory analyses
   - `tmp/<YYYY-MM-DD>-<slug>/` for one-off work
   - `tests/` for reusable test code
4. **Drop commented-out code and "fix later" notes.** If code is
   commented out, delete it (it's in git history if needed). Replace
   "fix later" notes with proper TODOs that reference an issue or
   `docs/workplan.md`.
5. **Remove stale fixtures.** Test fixtures that are no longer used
   must be deleted, not left in `tests/fixtures/`.
6. **Remove debug-only files.** One-off CSVs, downloaded inspection
   artifacts, scratch notebooks, `out.txt`, `scratch.py`, `try.py`,
   etc. — gone.
7. **Verify `.gitignore` is respected.** Run `git status` and confirm
   no `__pycache__/`, `*.pyc`, `.venv/`, `data/raw/<source>/*.xlsx`,
   etc. is staged. Run `find . -name '__pycache__' -o -name '*.pyc'`
   to confirm none is committed.

### What "coherence" means

The project must look like a coherent system, not a half-built prototype:

- **No orphan docs.** A doc that has been superseded is either updated
  to reflect the new state or deleted.
- **No orphan modules.** A Python module that is no longer imported
  anywhere is either reintroduced (with tests) or deleted.
- **No orphan configs.** A YAML config that is no longer used by any
  CLI command is either re-introduced or deleted.
- **No orphan tests.** A test that no longer matches the implementation
  is updated, not left failing.
- **Naming consistency.** Module names, table names, file names follow
  the documented conventions; no one-off variations.
- **No half-finished experiments in `src/`.** Exploratory code lives
  in `research/`, not in the production package.

### A cleanup checklist (run before considering work done)

```text
[ ] No `print(`, `console.log`, or `TODO(debug)` in src/ or tests/
[ ] No scratch .py / .sh files in the project root
[ ] No scratch notebooks in the project root or src/
[ ] No commented-out code in src/ or tests/
[ ] No "fix later" / "TBD" notes without a tracking reference
[ ] No orphan docs in docs/
[ ] No orphan modules in src/ (every .py is imported somewhere)
[ ] No orphan tests (every test_*.py matches an active behavior)
[ ] No orphan configs in configs/
[ ] No stale fixtures in tests/fixtures/
[ ] No orphan __pycache__ / .pyc / .log / .sqlite files in git status
[ ] No data/raw/<source>/*.xlsx in git status (the data lake is gitignored)
[ ] git status is clean or only contains the intended change
```

### When the rule is allowed to bend

- During an active debug session, `TODO(debug)` instrumentation is
  expected — but it must be removed before the session ends (Mode 3.5).
- During an active TDD red phase, a failing test is expected — but
  it must reach green before the phase ends.
- A research workspace under `research/<topic>-<date>/` may contain
  scratch material while the workspace is active — but the workspace
  is closed (moved under `docs/archive/` or deleted) once the
  investigation is over.

## Rule 2 — Review Discipline

### Scope

Every code-bearing change:

- A new module, function, class, or method.
- A bug fix.
- A schema migration.
- A refactor.
- An LLM adapter change.
- A confidence-formula tweak.
- A new external dependency.

Doc-only changes (`docs:`, `chore:docs`) are exempt from the
"reviewer agent" step but still require a self-review for consistency
with the rest of the project.

### What "review" means

After the code is written, before the next task begins:

1. **Self-review against [`docs/process/coding-guidelines.md`](coding-guidelines.md).**
   Walk the D2 review checklist at the bottom of that document.
   Findings are fixed in place, not deferred.
2. **Run the affected tests.** `pytest -q` for a quick pass; the
   relevant test file for a focused pass.
3. **Run `ruff` when configured.** `ruff check src tests` catches
   style and banned-pattern issues automatically.
4. **Address findings immediately.** If a finding is "suboptimal but
   works for now", fix it now. The "later" that never comes is a
   direct path to Phase E inheriting a mountain of debt.
5. **For non-trivial changes, route to the `reviewer` agent via the
   project-manager.** The reviewer is an independent gate — it never
   modifies code, only flags findings. The agent submitting the code
   resolves each finding before moving on.

### What counts as "non-trivial" (route to the reviewer agent)

- A new top-level module under `src/leaders_db/`.
- A new per-category scoring module.
- A change to the canonical confidence formula.
- A change to the schema (new migration, column rename, type change).
- A change to the LLM strict-JSON contract.
- A change to the data-lake layout or naming.
- A new external dependency.
- A bug fix where the root cause is non-obvious.

### What stays as a self-review (no reviewer agent)

- A typo fix in a docstring.
- A small helper function in a module that is already under review.
- A config tweak.
- A test-only change (e.g. extending a fixture).
- A documentation-only change.

### The review loop

```
write code
   |
   v
self-review against docs/process/coding-guidelines.md
   |
   v
run tests + ruff
   |
   v
fix findings in place
   |
   v
[non-trivial?] -- yes --> route to reviewer agent
   |                          |
   |                          v
   |                     reviewer findings
   |                          |
   |                          v
   |                     fix findings
   |                          |
   |<-------------------------+
   v
next task (or commit, if asked)
```

### Stacking unreviewed code is forbidden

"Stacking" means: writing more code on top of code that has open
review findings, in the hope of "addressing everything at the end".

This is explicitly forbidden. Every code-bearing change must pass
review (self or reviewer-agent) **before the next task begins**. If
a finding is unclear, escalate via the project-manager; do not
patch-and-proceed.

### When the rule is allowed to bend

- During a single-task hot fix (e.g. CI is red and a one-line revert
  is needed), a self-review is sufficient.
- A documentation-only commit is reviewed for consistency only.
- During Phase B (source vetting), probes are scripts, not code; the
  probe runner that ships in Phase C is reviewed normally.

## Rule 3 — Subagent And Search Tool Reliability

### Scope

Every delegated subagent task and every search-heavy operation that uses
OpenCode's `glob`, `grep`, or ripgrep-backed tools.

### Why this exists

OpenCode subagents and search tools can hang silently in some environments,
especially after broad `glob` / `grep` calls, omitted search paths, concurrent
sessions on the same repository, nested permission prompts, or operations
outside the workspace. A hung subagent can block the parent session forever.

### Required practice

Before launching a subagent or broad search, the agent must:

1. **Prefer direct reads when possible.** If the target file is known or can be
   identified with one narrow search, do not delegate the lookup to a subagent.
2. **Bound every subagent prompt.** Specify the exact goal, allowed directories,
   maximum search rounds, and expected return shape.
3. **Scope every search path.** Pass the repository root or a narrower project
   directory to `glob` / `grep`. Never rely on an omitted path that may default
   to `$HOME`, `/`, or a parent workspace.
4. **Use narrow patterns.** Prefer `src/**/*.py`, `docs/**/*.md`, or a named
   package subtree over `**/*`.
5. **Avoid external absolute paths.** Keep transient files under project `tmp/`,
   not `/tmp`, unless the user explicitly asks otherwise.
6. **Avoid nested permission prompts.** Do not rely on `ask` permissions inside
   headless or subagent flows; configure explicit `allow` / `deny` behavior.
7. **Limit concurrency.** Avoid multiple OpenCode/Codex sessions running large
   `glob` / `grep` searches against the same repository at the same time.
8. **Interrupt instead of waiting indefinitely.** If a subagent is silent after
   search tool calls, stop it, inspect for runaway `rg` / `opencode` processes,
   and retry with a narrower prompt.
9. **Capture repro details for recurring hangs.** Record OpenCode version,
   provider/model, OS, prompt shape, active sessions, whether external paths or
   permission prompts were involved, and debug logs from
   `--print-logs --log-level DEBUG`.

### Search reliability checklist

```text
[ ] Direct read used instead of subagent when the file path is known
[ ] Subagent prompt has explicit scope, limits, and expected final answer
[ ] glob/grep path is repo-root or narrower, never omitted accidentally
[ ] Pattern is narrow enough to avoid full-workspace traversal where possible
[ ] No external absolute paths unless explicitly required
[ ] No nested `ask` permission flow in delegated/headless work
[ ] No concurrent broad searches in another OpenCode/Codex session
[ ] Hang diagnostics captured if a stall recurs
```

## How the rules interact

- Cleanup (Rule 1) ensures the project is coherent **after** each
  task.
- Review (Rule 2) ensures the code that lands is sound **before**
  the next task.
- Subagent/search reliability (Rule 3) ensures exploration and delegation
  stay bounded so work does not silently stall.
- Together they form a "no slop, no debt, no silent hang" loop: every change
  lands in a coherent, reviewed state, ready for the next change.

If a reviewer finds that an earlier change introduced junk, the
fix is to clean up that change **before** proceeding — not to
add a "cleanup" commit at the end of the project.

## Operational check before commit

Run this before every commit:

```bash
# 1. Coherence
git status                                    # only intended changes
find . -name '__pycache__' -o -name '*.pyc'  # nothing committed
find . -name 'TODO(debug)' -not -path './.venv/*'  # nothing in src/ or tests/

# 2. Tests
.venv/bin/python -m pytest -q

# 3. Lint (when configured)
.venv/bin/ruff check src tests

# 4. Self-review walkthrough
# (mental walk of docs/process/coding-guidelines.md D2 review checklist)
```

If any check fails, fix the failure before committing.

## Where to record operational decisions

- A reusable pattern: add it to [`docs/process/coding-guidelines.md`](coding-guidelines.md).
- A reviewer finding that recurs: add it to the D2 review checklist
  in [`docs/process/coding-guidelines.md`](coding-guidelines.md).
- A new operational rule: add it here and reference from [`AGENTS.md`](../../AGENTS.md).
- A phase-level operational decision: add it to [`docs/workplan.md`](../workplan.md).
