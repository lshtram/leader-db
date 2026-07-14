# Research Answer Persistence Testing Guide

## Research-run readiness

Check a bounded ruler-dossier pilot before launching any model:

```bash
leaders-db research readiness \
  --mode dossier_researcher \
  --year 2020 \
  --question-id 4B.2 \
  --provider-profile minimax-m2.7-researcher \
  --output-dir data/outputs/research/<new-run-id> \
  --json
```

Omit `--question-id` only when intentionally checking the full 80-lens dossier
target. Check one chapter judge with a judge-capable profile:

```bash
leaders-db research readiness \
  --mode chapter_judge \
  --year 2020 \
  --chapter-id 4B \
  --provider-profile minimax-m3-long-context \
  --output-dir data/outputs/research/<new-judge-run-id> \
  --json
```

A nonzero exit blocks launch. Never reuse a nonempty output directory merely to
make readiness pass; resumability will use an explicit existing-run contract in
the durable orchestrator.

## Durable job ledger

Plan a bounded dossier run only after readiness passes:

```bash
leaders-db research jobs plan-dossiers \
  --year 2020 \
  --run-key pilot-4b2-2020-v1 \
  --question-id 4B.2 \
  --provider-profile openai-luna-candidate \
  --output-root data/outputs/research/pilot-4b2-2020-v1 \
  --json
```

Plan one chapter judge after dossier jobs exist. Its dependency edges prevent premature
claiming:

```bash
leaders-db research jobs plan-chapter-judge \
  --year 2020 \
  --run-key pilot-4b2-2020-v1 \
  --chapter-id 4B \
  --provider-profile openai-terra-candidate \
  --output-root data/outputs/research/pilot-4b2-2020-v1/judges/4b \
  --json
```

Workers use `research jobs claim`, retain the returned `lease_token`, then pass
it as `--lease-token` to periodic `heartbeat` and `checkpoint` commands and to
the final `complete` or `fail`. A token from an expired or superseded claim is
rejected even when the worker ID is reused. Use `retry` only while attempts remain and
`quarantine` for work that must leave the queue. Never update ledger tables with
ad hoc SQL during a run.

Execute one dependency-ready dossier through the configured Codex surface:

```bash
leaders-db research jobs run-one \
  --worker-id dossier-worker-01 \
  --run-key pilot-4b2-2020-v1 \
  --lease-seconds 900 \
  --heartbeat-seconds 60 \
  --timeout-seconds 7200 \
  --json
```

The parent first runs the exact stored researcher model/profile without a response
schema. That pass maintains `research-materials.md` when possible and returns a
flexible evidence handoff. A separately persisted formatter profile (Luna by CLI
default) interprets that material and emits the strict dossier JSON. The parent
then normalizes harmless non-score-bearing inconsistencies with audit warnings,
validates evidence-integrity fields, and atomically publishes the artifact before
completing the job. Codex sees the repository read-only and only its job output
directory is additionally writable.

Dossier plans persist the resolved `configs/research-workflow.yaml` contract.
One researcher receives the complete guides and local facts, then works through
chapters 1B–8B sequentially with direct, iterative internet research. Researchers
aim for 5–20 retained non-duplicative items per chapter, normally about 10. The
count is a quality target, not a publication gate: sparse rulers remain acceptable
with a clear record of what was checked and why the shortfall persists. A reviewer
may return deficient chapters to the same researcher session for up to three
rounds. Researcher, reviewer, formatter, and judge usage remain separately
auditable and are combined for run-level cost reporting.

Usage and pricing verification is covered by `pytest -q
tests/research/test_costing.py`. It checks cached/uncached parsing, no reasoning
double count, unknown models, retry aggregation, and long-context ranges.
`actual_billed_cost_usd` stays unknown for subscription/Coding Plan execution.

Focused verification:

```bash
pytest -q tests/research/test_research_workflow.py \
  tests/research/test_research_recovery.py
```

After usable dossier dependencies reach a terminal state, execute the chapter
judge through the same worker command:

```bash
leaders-db research jobs run-one \
  --worker-id chapter-judge-4b-01 \
  --run-key pilot-4b-2020-v1 \
  --job-type question_judge \
  --lease-seconds 900 \
  --heartbeat-seconds 60 \
  --timeout-seconds 7200 \
  --json
```

The internal `question_judge` spelling remains only for migration compatibility;
this executes one complete chapter. The child cannot browse and must judge every
available dossier once. The parent validates batch identity and dossier-local
evidence references, stamps observed usage, publishes the artifact, then
atomically upserts the batch into `chapter_scores` and completes the ledger job.

Run the focused no-network executor smoke with:

```bash
pytest -q tests/research/test_chapter_judge_worker.py
```

It exercises a two-ruler 4B batch with a fake Codex boundary and proves that an
expired lease cannot persist partial rows. It is an infrastructure smoke, not a
model-quality calibration run.

## Legacy/manual cited-evaluation importer

Use this compatibility path only for already-formatted cited records from a human
or legacy/manual workflow. It is not the ruler evidence-researcher contract: the
primary researcher emits a permissive, non-scoring notebook, and the separate
formatter emits the dossier. Records presented to this importer must already use
the `CitedEvaluation` JSON shape. Score-bearing records should follow the common-meter
calibration rules in
[`methodology/cited-evaluation-calibration.md`](methodology/cited-evaluation-calibration.md).
For score-bearing records, put the required `calibration` object under
`answer_payload`; this carries the rubric version, comparison batch, severity,
state-responsibility, accountability, information-environment, period-fit,
source-mix, and bias-check fields. The importer rejects records that set
`score_1_to_10` without this calibration object.

Print the current JSON Schema with:

```bash
leaders-db research cited-evaluation-schema
```

Create a starter record for a registered `internet_manual` methodology question:

```bash
leaders-db research cited-evaluation-template \
  --methodology-id 1B.1 \
  --year 1967 \
  --iso3 TZA \
  --country-name Tanzania \
  --leader-name "Julius Nyerere" \
  --period-label 1967-1985
```

Persist completed records with:

```bash
leaders-db research persist-cited-evaluations --input tmp/cited-evaluations.json
```

The input file can be a JSON array or an object with an `evaluations` array. Every
record must have at least one citation; citation URLs become
`research_answer_evidence_links.source_observation_id` values. `confidence_score`
is stored as a 0-100 percentage; the importer also accepts fractional inputs such
as `0.94` and normalizes them to `94`.

The importer rejects unregistered questions and questions whose registry evidence
strategy is not `internet_manual`. It does not run web research, create citations,
or invent evidence; it only validates and persists already-cited output.

The preferred workflow is one calibration worker per chapter/year batch. The same
judge applies all ten chapter lenses and one holistic rubric across all rulers so
close cases share one meter. A separate reviewer audits relative ordering,
missingness, attribution, and systematic bias.

Before launching an `internet-research` worker, require the worker to read
[`methodology/local-first-researcher-guide.md`](methodology/local-first-researcher-guide.md)
and every selected chapter guide. The mandatory order is local-first: inspect the
guides, query the local DB/artifacts, use preferred external sources, and use
general web search last. The approved direct local DB access path for a restricted
`internet-research` worker is the structured read-only CLI:

```bash
leaders-db research local-evidence \
  --methodology-id 4B.1 \
  --year 2020 \
  --iso3 USA \
  --json
```

This command uses the local structured-prior builder, excludes client-matrix
source slugs, accepts no arbitrary SQL, and returns artifact-shaped records plus
status counts. If no `--iso3` is provided, it fails rather than dumping all local
rows. Do **not** make a separate local-prior prep phase the main strategy;
instead build a local structured-prior artifact and include it in the worker
prompt/input as the concrete summary of already-loaded local structured facts
when durable artifact files are useful:

Codex workers use `.agents/skills/ruler-evidence-researcher/SKILL.md` and the
permissions of the active execution profile. The tracked OpenCode permission file
is historical compatibility material only; ignored machine-local OpenCode files do
not define the supported researcher workflow or its search allowance.

```bash
leaders-db research build-local-prior \
  --methodology-id 4B.1 \
  --year 2020 \
  --iso3 USA \
  --leader "Donald Trump" \
  --output tmp/4b1-usa-2020-local-prior.json \
  --json
```

The command reads the initialized local database only, preferring
`country_year_facts`; it does not read raw source files, call the web, or use the
client matrix. The artifact includes `status`, `local_facts`,
`missing_or_empty_reason`, and `recommended_research_instructions`. Empty and failure states are explicit: `no_evidence_found` means no selected
non-client local facts matched the configured prior mapping, `not_applicable`
means no included project country-year exists for the requested scope, and
`error` preserves the same artifact shape with `missing_or_empty_reason` for
invalid requests or local build failures. Workers should not re-fetch local
structured datasets such as Freedom House, V-Dem, RSF, WGI, BTI, CPI, PTS,
CIRIGHTS, UCDP, SIPRI, or FAS for numeric / structured priors. Use external pages
only for narrative, ruler-specific, legal, election, media, or
contradiction-resolution detail when local facts are insufficient for the
qualitative question.

Current web-search policy gives the researcher direct search and URL-opening
tools. It should issue as many purposeful chapter-specific iterations as needed
for reasonable saturation, while avoiding redundant queries and unsafe browser
automation. Reviewer-identified gaps return to the same researcher thread for up
to three rounds. Every score-bearing citation must carry
`source_confidence`, `source_confidence_reason`, `source_type`, and
`final_evidence_use` from `docs/methodology/source-confidence-registry.json`, and
each shard must emit a `run_profile` with timing, local evidence reads, Parallel
search/fetch counts and explicit usage/token unknowns when hidden.

The following single-question command is retained only as a historical/local-data
compatibility smoke; it is not the production ruler-research flow:

```bash
leaders-db research build-local-prior-slice \
  --methodology-id 4B.2 \
  --year 2020 \
  --output-dir data/outputs/research/4b2_2020_local_priors \
  --shard-size 10 \
  --json
```

This writes one artifact per included country-year under `artifacts/`, plus
`manifest.json` and `shard_plan.json`. The 2020 `4B.2` local-prior smoke run
generates 196 artifacts, all `evidence_found`, with 3,088 selected local facts and
195 artifacts carrying ruler metadata in the current local DB. The regenerated
clean package also includes a legacy `internet_research_launch_plan.md`. Do not
use that artifact to orchestrate production ruler research.

For compatibility imports, validate every artifact before using or judging it.
The production flow is one persistent researcher per ruler-period with all selected
chapter guides and local facts, direct chapter-sequential research, up to three
same-thread evidence-review continuations, separate formatting, and chapter judges.
The legacy status validator can still check older sharded outputs:

```bash
leaders-db research validate-shard-output \
  --status tmp/run/shard-01-status.json \
  --input tmp/run/shard-01-input.json \
  --output tmp/run/shard-01-output.json \
  --expected-record-count 10 \
  --max-expected-minutes 30 \
  --max-progress-stale-minutes 10 \
  --json
```

Workers or the parent session should write heartbeat updates while work is in
progress:

```bash
leaders-db research validate-shard-output \
  --status tmp/run/shard-01-status.json \
  --progress-message "searched election-observer sources for first five rulers" \
  --json
```

Do not trust a subagent's textual success report by itself. A shard is complete
only when the watchdog sees a parseable output file with the expected record
count, required evidence keys, and at least one citation per record. Missing
outputs after the deadline are `timed_out_or_stuck` and should be retried or split
into smaller shards. Missing outputs with no heartbeat within the configured
staleness window are `progress_stale`; treat those as stuck even if the final
deadline has not elapsed.

## 8B cited evaluations

This command remains as a compatibility wrapper for the older 8B-specific input
schema.

Persist already-cited 8B effectiveness evaluations with:

```bash
leaders-db research persist-8b-evaluations --input tmp/8b-evaluations.json
```

The input file can be a JSON array or an object with an `evaluations` array:

```json
{
  "evaluations": [
    {
      "methodology_id": "8B.3",
      "year": 1967,
      "iso3": "TZA",
      "country_name": "Tanzania",
      "leader_name": "Julius Nyerere",
      "leader_resolution": "Julius Nyerere / TANU government",
      "program_source": "Arusha Declaration",
      "implementation_or_outcome_window": "1967-1975",
      "verdict": "partially_supported",
      "evidence_quality": "medium",
      "confidence": "medium",
      "manual_review_reason": "Outcome side effects require review.",
      "score_1_to_10": 6,
      "confidence_score": 70,
      "goal_coverage": [{"goal": "ujamaa villages", "score_1_10": 5}],
      "candidate_structured_observation": {"support_status": "partially_supported"},
      "citations": [{"url": "https://example.test/program", "title": "Program source"}],
      "caveats": ["Broad mobilization question."]
    }
  ]
}
```

This command writes `research_questions`, `research_question_answers`, and
`research_answer_evidence_links`. It does not run web research, create citations,
or invent evidence; it only persists already-cited evaluator output.

Inspect persisted answers with:

```bash
leaders-db research list-answers --question-id 8B.3 --iso3 TZA --output json
leaders-db research list-answers --year 1967 --output csv
```

Available filters are `--question-id`, `--year`, `--iso3`, and
`--method-version`. JSON output includes expanded `evidence_links`; CSV output is
flat and includes `evidence_link_count`.
## Frozen 20-ruler research and judge smoke batch

The current comparative smoke cohort is
`configs/research-batches/2020-diverse-20.yaml`. Plan all 80 lenses with Luna research,
review, and formatting:

```bash
leaders-db research jobs plan-dossiers \
  --year 2020 \
  --run-key 2020-diverse-20-luna-v1 \
  --provider-profile openai-luna-candidate \
  --reviewer-profile openai-luna-candidate \
  --formatter-profile openai-luna-candidate \
  --batch-manifest configs/research-batches/2020-diverse-20.yaml \
  --discovery-plan configs/research-discovery.yaml \
  --output-root data/outputs/research/2020-diverse-20-luna-v1 \
  --json

leaders-db research jobs run-queue \
  --run-key 2020-diverse-20-luna-v1 \
  --job-type dossier_researcher \
  --concurrency 2 \
  --max-jobs 20 \
  --max-failures 2 \
  --json
```

After dossier QA is terminal, plan all eight comparative judges over the same cohort:

```bash
leaders-db research jobs plan-chapter-judge \
  --year 2020 \
  --run-key 2020-diverse-20-luna-v1 \
  --all-chapters \
  --provider-profile openai-luna-candidate \
  --output-root data/outputs/research/2020-diverse-20-luna-v1 \
  --json

leaders-db research jobs run-queue \
  --run-key 2020-diverse-20-luna-v1 \
  --job-type question_judge \
  --concurrency 2 \
  --max-jobs 8 \
  --max-failures 1 \
  --json
```

Judge workers build hash-bound chapter-only projections and fail before model execution
when the conservative input estimate would consume the declared context window minus
the required output reserve. Chapter guides remain smoke-status until this comparative
batch is reviewed.
