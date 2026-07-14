# Five-question ruler dossier model comparison — 2026-07-12

> Historical per-question-guide pilot. The active design now uses eight chapter
> guides and one holistic score per chapter.

## Scope

This guide-validation pilot used one resolved ruler-year, Nikol Pashinyan in
Armenia in 2020, and the five currently available draft question guides:
`3B.1`, `3B.2`, `4B.1`, `4B.2`, and `4B.3`. Four jobs ran concurrently with
the same parent-supplied local priors and the same approved Parallel Search
artifact. Each job was allowed one repair attempt.

The guides are drafts, so this is not a production score-bearing run. The
researcher collected and mapped evidence but did not score the ruler.

## Results

| Model | Outcome | Attempts | Input tokens | Cached input | Output tokens | Active wall time |
|---|---:|---:|---:|---:|---:|---:|
| `gpt-5.6-luna` | completed | 2 | 305,918 | 221,696 | 15,852 | 304 s |
| `gpt-5.6-terra` | semantic failure | 2 | 485,019 | 381,696 | 10,652 | 223 s |
| `MiniMax-M3` | invalid JSON | 2 | 1,484,787 | 1,286,912 | 20,458 | 216 s |
| `MiniMax-M2.7` | invalid JSON | 2 | 1,480,231 | 1,325,537 | 30,080 | 507 s |

Usage is cumulative across every `turn.completed` event in both attempts.
Reasoning tokens are a subset of output tokens and are not added again. Active
wall time is the sum of ledger `claimed` to terminal-event intervals and excludes
the deliberate gap before repair. Exact dollar cost is unavailable because the
runtime did not expose model prices; no rate was inferred.

## Quality review

The independent ranking was Luna, Terra, MiniMax-M2.7, then MiniMax-M3.

Luna produced the only schema-valid dossier. It contains four deduplicated
evidence records, ten many-to-many mappings, partial coverage for all five
questions, explicit unresolved gaps, and useful cross-question reuse: every
evidence record maps to two or three questions. It is a cautious judge-input
skeleton, not a complete dossier. One aggregate local-prior record and one US
State Department report supply almost all evidence; independent NGO, court, and
observer corroboration is absent. The State Department is also mislabeled as an
intergovernmental source, and its publication date needs correction.

Terra was concise and mostly source-faithful, but had only two evidence records
and five mappings. Its local structured priors were not represented as traceable
evidence, and its `4B.1` coverage judgment was too strong for a year without a
national election. Both attempts violated the invariant requiring independently
mapped contrary evidence for covered questions.

MiniMax-M2.7 generated apparent breadth but not reliable bounded evidence. Its
first output was schema-invalid, lacked the required mapping table, used later
2025–2026 material for a 2020 dossier, and overinterpreted generic indicators.
Its repair returned Markdown prose instead of JSON. MiniMax-M3 returned a
truncated fenced JSON object and then an empty repair output.

## Interpretation and decision

This run validates the intended one-ruler/many-question architecture and shows
that evidence can be reused across question handoffs. It does not yet validate a
full evidence-collection run. The shared discovery set was the experiment's
largest weakness: only one of ten results was materially useful, most results
concerned 2026, and one was unrelated app-store material. The comparison therefore
measures synthesis restraint and contract compliance more than research quality.

Luna is the current default candidate for the next low-cost dossier pilot. Terra
remains worth retesting after the contrary-evidence prompt/repair path is made
more explicit. Neither MiniMax model is ready for unattended dossier production
under the current Codex contract, and both consumed roughly three to five times
Luna's input tokens while failing to publish.

Before another model comparison, improve parent discovery with question-theme
queries bounded to the ruler period and preferred sources such as Human Rights
Watch, Amnesty International, Council of Europe, OSCE, courts, the ombudsman, and
local watchdogs. Then run the same fixed discovery packet through the candidates
and judge source fidelity, coverage, reuse, contract success, and cumulative cost.
