# Production Reconnaissance Smoke Test

Date: 2026-07-24  
Case: Vladimir Putin, Russia, 2022  
Model: `gpt-5.6-sol`

This run used the exact promoted production prompt and the intended blank-slate
execution restrictions: no project rules, shell, filesystem tools, apps, plugins,
subagents, or goals.

## Result

- 17 developed atomic evidence records;
- 17 physical `SOURCE_CLAIM_JSON` lines;
- 17 records recovered by the production parser;
- the recovered manifest passed the production ledger validator;
- all dispositions normalized from producer `accepted` to internal `final_evidence`;
- 51 URLs preserved in the readable memo;
- 4,813 output words;
- 1,175,128 cumulative input tokens, including retrieved and replayed web context;
- 12,121 output tokens.

The machine appendix therefore works without researcher filesystem access. The high
cumulative input use also shows that informational saturation has variable cost even
under the hybrid prompt. Token and elapsed-time monitoring remain required before
scaling the next controlled evaluation.

Artifacts:

- [`output.md`](putin/output.md)
- [`events.jsonl`](putin/events.jsonl)

