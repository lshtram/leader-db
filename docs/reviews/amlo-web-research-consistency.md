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

## Iteration 2 — structured fallback

- Run key: `2022-amlo-web-consistency-i02`.
- Reconnaissance: 11 substantive claims from eight source organizations, returned as
  the required physical `SOURCE_CLAIM_JSON` lines.
- Trusted usage: 369,671 input tokens, of which 306,944 were cached; 10,071 output
  tokens. Input fell another 33% from iteration 1.
- Failure: the producer used `accepted` as its disposition and semantic routing labels
  instead of exact methodology IDs. Initial recovery also had not yet called the claim
  line parser. The run was stopped before completing Chapter 1B.
- Repair: initial and continuation handoffs now share the claim-line parser. The
  tolerant receiver normalizes `accepted`, `retained`, and `final` to
  `final_evidence`, drops malformed routing labels, and preserves valid chapter and
  exact-lens IDs. All 11 real iteration-2 lines recover as valid final evidence.

## Iteration 3 — targeted weak-chapter wave

- Selected scope: 5B, 6B, and 8B only; downstream review disabled for this
  web-research diagnostic.
- Reconnaissance retained 12 reusable records with 539,074 input tokens.
- Chapter 5B added 12 records with 1,012,330 input tokens; its mapped depth reached 16,
  above lean-v4's 15.
- Chapter 6B added 10 records with 1,548,109 input tokens; its mapped depth reached 22,
  close to lean-v4's 25.
- Chapter 8B added 10 records with 2,398,287 input tokens; its mapped depth reached 20,
  close to lean-v4's 23.
- The targeted ledger contains 44 records. Its canonical-key union with iteration 2
  contains 131 records, 95 distinct URLs, 51 domains, and 449 exact-lens mappings.
  That exceeds lean-v4 on claims, domains, and mappings and is within three URLs of its
  URL breadth.

The result demonstrates that fresh short targeted sessions preserve quality while
avoiding the steep eight-chapter history replay. Iteration 4 promotes that topology:
one short reconnaissance followed by fresh compact chapter sessions, each receiving a
bounded relevant-resource index and writing into one parent-owned cumulative ledger.
