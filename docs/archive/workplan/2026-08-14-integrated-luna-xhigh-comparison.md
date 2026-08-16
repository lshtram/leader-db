# Integrated Luna xhigh comparison

## Outcome

The user authorized a relaxed 176-call ceiling and replacing the Terra production actions
with `gpt-5.6-luna` at `xhigh` reasoning. Independent quality remained assigned to
`gpt-5.6-sol` at `high`. Both models used the Codex subscription; no API key was used.

The run was rejected during question writing. Ten 1B answers and the first two 2B answers
passed deterministic validation. The 2B.3 output omitted required evidence
`BATCH-0030-R02-E002` from its citation/disposition ledger, so it failed complete factual
coverage before independent comparison. The runner made no retry or repair call.

Six other chapter-first calls had been launched concurrently to reduce `xhigh` latency.
They were interrupted immediately after the failure, and process inspection confirmed no
orphan Luna worker remained. Their partial event logs have no completed usage record and
are retained rather than normalized into successful calls.

## Usage

- Authorized ceiling: 176 calls.
- Reserved calls: 19.
- Calls with completed usage: 13.
- Deterministically valid outputs: 12.
- Interrupted calls without completed usage: 6.
- Input tokens: 945,789, including 176,128 cached-input tokens.
- Output tokens: 108,499, including 68,112 reasoning-output tokens.
- Total tokens: 1,054,288.
- Sol quality-review, chapter-judge, and judgment-review calls: zero.

## Comparison decision

Luna `xhigh` did not establish quality equivalence to the corrected Terra baseline. The
first failing answer omitted one of 28 mandatory evidence records, while the gate requires
complete coverage. Because the single-pass contract forbids automatic correction and a
failed production result cannot proceed to independent review, the experiment is rejected.
This does not establish that all Luna answers are worse; it establishes that this exact
single-pass Luna configuration is not promotion-eligible.

Independent review reproduced the call, usage, failure, and hash arithmetic. It also found
that the immutable per-call request manifests identify Luna but omit reasoning effort and
do not retain sanitized argv, so those artifacts cannot independently prove `xhigh` even
though the release config specified it and the live process command showed it. The run is
already rejected; its artifacts were not rewritten. Future question-write and review
manifests now record their configured reasoning effort before execution.

The trusted result is
`research/runs/netanyahu-2023-integrated-luna-xhigh-v1/run-result.json`, which binds the
release config, preflight, failed output, and deterministic validation by SHA-256.
