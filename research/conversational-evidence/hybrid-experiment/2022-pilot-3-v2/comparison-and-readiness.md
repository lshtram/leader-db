# 2022 hybrid v2 three-ruler pilot: comparison and readiness

## Decision

The v2 architecture is materially better than the 2024 production flow on cost,
turn count, evidence auditability, and duplication. It is ready for a **five-ruler
gate**, but not yet for an unattended 20-ruler launch. The remaining concern is not
raw source volume: it is uneven post-review yield and source-family concentration.

## Pilot results

| Ruler | Turns | Searches | Model time | Cost | Claims | URLs | Domains | Final reviewer-kept claims |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Vladimir Putin | 11 | 164 | 75.7 min | $2.14 | 102 | 91 | 43 | 92 (90%) |
| Narendra Modi | 12 | 193 | 81.0 min | $2.39 | 108 | 85 | 34 | 69 (64%) |
| Jair Bolsonaro | 12 | 132 | 67.7 min | $2.05 | 108 | 100 | 26 | 101 (94%) |
| **Total / mean** | **35** | **489** | **224.4 min** | **$6.58** | **318** | **276** | **34.3 mean** | **262 (82%)** |

The claims-to-URL ratio is 1.15 overall (318/276). That is modest, explainable reuse,
not record inflation. After final review, 262 claims remain usable. One malformed
Brazil 2B JSON record was excluded and recorded in `parse-rejections.json`; its 12
valid sibling records were retained.

## Comparison with the 2024 production flow

The 2024 20-ruler production run averaged $5.22, 143.8 model-minutes, 156.8 searches,
741 evidence rows, 145.9 unique URLs, and 35.6 domains per ruler. Its Putin case had
649 rows from only 94 URLs: 6.9 rows per URL, including repeated reinterpretations of
the same reports across lenses.

The 2022 v2 pilot averages $2.19, 74.8 model-minutes, 163 searches, 106 claims, 92
URLs, and 34.3 domains per ruler. It therefore costs 58% less and uses 48% less model
time while retaining similar global domain diversity. Its 1.15 claims per URL is 83%
lower than production Putin's 6.9 rows per URL. The evidence units also retain locator,
period fit, ruler attribution, contrary evidence, confidence reasoning, and exact lens
mappings, which the old short rows did not.

The tradeoff is fewer raw URLs than the old flow's average. This is mostly deliberate:
v2 removes duplicate syndications and does not count one document repeatedly for ten
lenses. The no-search reviewer still removed/contextualized 39 of Modi's 108 claims,
showing that raw volume alone is not sufficient.

## Quality findings

- Putin: 91 URLs and 43 domains; 90% of claims survived review. Chapter 7B stayed
  below the ten-URL target and retained a manual-review gap rather than being padded.
- Modi: 85 URLs and 34 domains; only 64% survived final review. Official Indian
  sources dominate 2B, 5B, 6B, and 8B. The follow-up improved gaps but final review
  still requires manual handling for 1B and 7B.
- Bolsonaro: 100 URLs and 26 domains; 94% survived review. Chapter 4B has only five
  URLs from two domains, while 2B, 7B, and 8B have source-family concentration.
- All three dossiers ended in `manual_review`, which is a defensible output rather
  than a failure: the flow preserves credible gaps and does not manufacture certainty.

## Reliability improvements made during the pilot

1. The parser now accepts conventional Markdown list and inline-code wrappers while
   preserving strict JSON/schema validation.
2. A completed model turn left unfiled by validation can be promoted on resume, so
   paid research is not repeated.
3. Retry failure counts reset after durable stage progress; only consecutive
   no-progress failures can terminate a ruler.
4. The reviewer prompt includes the exact object schema and now validates reliably.
5. Valid claim records survive when a sibling line is malformed; every excluded line
   is recorded by line number, validation reason, and SHA-256.

## Full-run projection and gate

At the pilot mean, 20 rulers project to about **$43.88**. The observed per-ruler range
projects to **$41.08-$47.76**, below the manifest's $60 hard ceiling and far below the
old 2024 run's $104.48 researcher cost. Sequential model time projects to 24.9 hours;
the configured staged concurrency (1, then 3, then 5 workers) should reduce wall time
substantially, subject to provider latency and long-tail chapters.

Before releasing all 20, run two additional contrasting rulers to reach a five-ruler
gate. Acceptance should require: no new parser/retry defect, mean cost below $3, at
least 80 distinct URLs per ruler or an explicit credible-gap rationale, and no dossier
with less than 60% reviewer-kept claims. If that gate passes, the remaining 15 can run
under the existing $3-per-ruler and $60 aggregate ceilings.
