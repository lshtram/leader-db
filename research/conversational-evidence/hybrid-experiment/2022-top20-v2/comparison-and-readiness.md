# 2022 top-20 hybrid run: profile and readiness

## Outcome

The controlled v2 flow completed all 20 reviewed ruler identities and all eight
comparative chapter judges. It produced 160 chapter evaluations: 155 numeric scores
and five evidence-based nulls. The post-judge targeted review cleared every mechanical
projection flag without changing a score.

Chapter 1B respects the absolute historical floor. No ruler received 1; Vladimir Putin
received 2.0. The four 1B nulls (DR Congo, Egypt, Ethiopia, Philippines) reflect absent
judgeable ruler-attributed existential-risk conduct, not an inferred midpoint or low
score.

## Cost and time

- Evidence research: $41.590358 total; $2.079518 mean per ruler.
- Eight chapter judges: $1.856599 total; $0.092830 mean per ruler.
- Measured research plus judging: $43.446957 total; $2.172348 mean per ruler.
- Research job time: 25.66 summed hours across rulers.
- Judge job time: 1.39 summed hours; about 38 minutes wall time with concurrency.
- Audit CLI runs did not expose price telemetry. Their incremental cost does not put the
  run near the approved $5 mean ceiling.

## Evidence quality and duplication

- 2,062 accepted research claims, 1,686 distinct ruler-local URLs, and 692 summed
  ruler-local domains.
- Mean per ruler: 103.1 claims, 84.3 distinct URLs, and 34.6 domains.
- Claim-to-URL reuse was 376 records (18.2%). This is an upper-bound duplication proxy:
  many reused URLs support multiple distinct claims or lenses and are not duplicates.
- The no-search reviewers removed or contextualized 454 records (22.0%), leaving 1,608
  reviewed records (78.0% retention) available across their admissible chapter uses.
- Low retention was not hidden. Egypt retained 46/87 because its 1B material was mostly
  institutional context rather than Sisi-attributed conduct; the judge returned null
  instead of inventing a score.

| ISO3 | Research cost | Claims | URLs | Domains | Retained |
|---|---:|---:|---:|---:|---:|
| BGD | $2.165 | 110 | 76 | 36 | 73 |
| BRA | $2.054 | 108 | 100 | 26 | 101 |
| CHN | $1.767 | 116 | 89 | 30 | 77 |
| COD | $2.221 | 122 | 94 | 38 | 98 |
| DEU | $2.428 | 107 | 86 | 29 | 86 |
| EGY | $1.876 | 87 | 70 | 29 | 46 |
| ETH | $2.318 | 98 | 78 | 40 | 79 |
| IDN | $2.134 | 104 | 93 | 39 | 101 |
| IND | $2.388 | 108 | 85 | 34 | 69 |
| IRN | $1.786 | 83 | 72 | 36 | 55 |
| JPN | $1.762 | 103 | 76 | 23 | 97 |
| MEX | $2.142 | 104 | 93 | 43 | 91 |
| NGA | $2.129 | 108 | 87 | 33 | 66 |
| PAK | $2.466 | 108 | 92 | 40 | 81 |
| PHL | $1.916 | 101 | 87 | 37 | 64 |
| RUS | $2.141 | 102 | 91 | 43 | 92 |
| THA | $1.874 | 109 | 86 | 40 | 75 |
| TUR | $2.120 | 96 | 71 | 39 | 77 |
| USA | $1.850 | 100 | 82 | 25 | 96 |
| VNM | $2.054 | 88 | 78 | 33 | 84 |

## Judge profile

- 1,669,188 input tokens, including 510,976 cached input tokens.
- 211,026 output tokens, including 74,988 reasoning-output tokens.
- The first 8B attempt exhausted context at four records per lens and incurred no
  recorded cost. The successful retry used three diverse records per lens, retained
  the full omission ledger, and cost $0.302114.
- Final batches have zero `manual_review_required` flags after targeted no-search review.
- The only score-1 cases are Putin in 2B (international peace) and 4B (political
  freedom). There is no 1B score of 1.

## Readiness

The final post-fix score/order audit returned `pass`: 160 evaluations, 155 numeric
scores, five defensible nulls, zero manual-review flags, no remaining ordering or floor
issue, and a release recommendation. This remains a controlled research artifact rather
than a packaged Stage 15 public export. Any public export must include the exact
normative attribution text from `docs/sources/attributions.md`.
