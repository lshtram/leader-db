# Simple Evidence Extractor

A clean-room prototype for extracting factual evidence from supplied local text.
MiniMax M3 reasons freely but persists evidence only through the local `evidence`
CLI. Code owns source hashes, exact excerpts, offsets, registry state, and final
acceptance.

Each model invocation receives a short-lived random capability bound by the
runner to one role, one source range, and the facts created or assigned in that
range. The model cannot select reviewer authority or write the authoritative
registry directly.

This project deliberately imports nothing from `leaders_db` and does not consume
prior evidence-funnel outputs.

## Current status

The deterministic source, CLI, append-only registry, review lifecycle, materialized
JSONL outputs, M3/M2.7 runner, and synthetic tests are implemented. The first live
LAW-005 boundary stopped before source inspection because this host's Codex
`workspace-write` sandbox cannot start shell commands: its `bwrap` helper fails with
`RTM_NEWADDR: Operation not permitted`. The prototype does not bypass that boundary.

## Commands

```bash
simple-evidence prepare --manifest manifest.json --output prepared.json
simple-evidence run --manifest manifest.json --config m3.json --output runs/demo
simple-evidence materialize --manifest manifest.json --registry runs/demo/registry.jsonl
```

The model-facing worker exposes only:

```bash
./evidence show SOURCE [START] [END]
./evidence add SOURCE START [END] --summary "fact"
./evidence correct FACT_ID [--start S] [--end E] [--summary "fact"]
./evidence confirm FACT_ID
```
