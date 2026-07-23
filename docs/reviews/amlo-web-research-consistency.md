# AMLO 2022 Web-Research Consistency Gate

## Baselines

| Run | Prompt design | Accepted/recoverable claims | Distinct URLs | Result |
|---|---|---:|---:|---|
| lean-v4 | reconnaissance plus one persistent turn per chapter | 111 | 97 | quality baseline |
| bias-aware top-20 v1 | 462 KB initial prompt; fragmented continuations | 13 dossier records | 11 | regression |
| manual source-landscape probe | direct English/Spanish searches without the worker | authoritative sources found across all chapters | not used as a count gate | web scarcity rejected as explanation |

The automated promotion gate is at least lean-v4 breadth and source quality after
claim/event deduplication, with complete cumulative-ledger preservation. Counts alone
cannot pass a run.

## Iteration 1 — compact reconnaissance

- Run key: `2022-amlo-web-consistency-i01`
- Model: `gpt-5.6-luna`, matching the regressed run to isolate workflow changes.
- Initial prompt: 6,422 characters versus 462,278 (98.61% smaller).
- Reconnaissance: 10 substantive claims from seven strong source organizations,
  including INE, the official gazette/Congress, SCJN, SEGOB, IACHR, Human Rights
  Watch, and USTR.
- Trusted usage: 553,450 input tokens, of which 456,192 were cached; 4,807 output
  tokens. This is materially below the prior initial research turn's 1,567,961 input
  tokens but still shows large tool/session amplification relative to the 2,141-token
  prompt-size estimate.
- Failure: sandboxed file writing failed and the model returned a Markdown table rather
  than recoverable `SOURCE_CLAIM_JSON` lines. The run was stopped before completing
  Chapter 1B and explicitly marked failed rather than spending eight chapter turns with
  an incomplete accounting ledger.
- Repair: the producer prompt now requires one physical recoverable line per accepted
  claim; the tolerant parent also recovers labeled Markdown evidence tables. The actual
  iteration-1 handoff deterministically recovers all 10 rows after this repair.

## Next iteration

Run the complete eight-chapter sequence with the repaired fallback. Inspect after each
chapter:

1. new and cumulative defensible claims;
2. distinct opened URLs, domains, organizations, and source types;
3. exact-lens and chapter coverage;
4. manifest count versus notebook claim count;
5. input/cached/output tokens and prompt characters;
6. marginal evidence yield per token.

Stop early on evidence loss, repeated manifest growth, failure to open underlying
sources, or unreasonable context amplification.
