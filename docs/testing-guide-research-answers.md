# Research Answer Persistence Testing Guide

## Generic cited evaluations

Use this path for already-cited manual/internet research outputs from a human or
`internet-research` subagent. The subagent should produce records in the
`CitedEvaluation` JSON shape; the importer validates the shape and files the
answer plus citation links. Score-bearing records should follow the common-meter
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

The preferred workflow is one calibration worker per `methodology_id` / target-year
batch. Research workers may gather individual evidence records, but the same
calibration worker should apply the shared rubric to all rulers in that batch so
close cases are judged against one meter. A separate reviewer should then audit
the batch for common-scale failures and systematic bias.

Before launching an `internet-research` worker, build a local structured-prior
artifact and include it in the worker prompt/input. This prevents workers from
refetching structured datasets that are already in the local DB:

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
structured datasets such as Freedom House unless the local prior is absent,
contradictory, or needs ruler-specific/narrative detail.

Build a durable all-scope local-prior package for an approved question/year with:

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
generated 196 artifacts, all `evidence_found`, with 3,088 selected local facts and
195 artifacts carrying ruler metadata. The package also includes an
`internet_research_launch_plan.md` with a bounded four-case smoke set. Full
all-ruler internet research was not launched; it remains pending human approval or
a safe parent-owned dispatcher with watchdog validation.

For sharded `internet-research` runs, validate every worker artifact before using
or judging it. The parent session should create one status JSON per expected
output and run:

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
