# Putin 2023 candidate-heavy research profile

## Verdict

The experiment proves that GPT-5.4 mini can build much deeper chapter evidence pools
than the former small-call lens flow, but this configuration is not ready to replace the
canonical workflow. It reliably enforced 20–30 distinct accepted URLs after parent-side
validation, yet it did not reliably reach 100 candidates and the final ledgers remain
uneven in source-family balance and discriminating-lens coverage.

## Resource profile

- Wall-clock span from first profiled call to last: 27,376 seconds (7h 36m).
- Completed/recorded call time: 24,737 seconds (6h 52m).
- Completed phases: 77; per-turn profiles: 78, including one recorded context failure.
- Recorded web searches: 992. Two timed-out discovery attempts emitted no profile, so
  both search count and cost are lower bounds.
- Usage: 12,249,872 input tokens, 6,921,472 cached input tokens, and 1,268,205 output
  tokens, including 955,557 reasoning-output tokens.
- Estimated GPT-5.4 mini cost: at least $10.22 using the configured published-price
  fields. Unreported timeout usage is excluded.
- Stored run size: approximately 4.8 MiB.

## Depth and deduplication

| Chapter | Candidate URLs | Accepted URLs | Domains | Largest domain share |
|---|---:|---:|---:|---:|
| 1B | 100 | 28 | 16 | 28.6% |
| 2B | 104 | 23 | 6 | 30.4% |
| 3B | 99 | 25 | 12 | 16.0% |
| 4B | 74 | 29 | 15 | 20.7% |
| 5B | 57 | 22 | 7 | 36.4% |
| 6B | 107 | 26 | 10 | 26.9% |
| 7B | 100 | 25 | 8 | 16.0% |
| 8B | 100 | 30 | 7 | 30.0% |

- Five of eight chapters met the 100-document target. The shortfalls were 3B by 1,
  4B by 26, and 5B by 43.
- The chapter pools contain 772 candidate IDs and 741 canonical URL instances. The
  31-record difference is same-chapter duplication or candidate rows without a distinct
  canonical URL.
- Across chapters, the 741 candidate instances reduce to 620 unique URLs: 121 reuse
  instances involving 114 URLs, with one URL used in at most four chapters.
- The authoritative ledgers contain 208 accepted URL instances and 201 globally unique
  URLs. Only seven URLs recur across chapters, each in two chapters.
- Every authoritative chapter ledger contains 20–30 parsed rows and has no within-ledger
  duplicate canonical URL. The original oversized 1B and 3B ledgers remain preserved as
  non-authoritative audit artifacts.

## Qualitative findings

- 1B is strong on New START, CTBT rollback, Belarus deployment, and nuclear rhetoric,
  but weak on expert governance, safeguards, and dual-use precaution.
- 2B is strong on aggression, occupation, civilian harm, and accountability, but weak
  on affirmative peace-making and direct Putin negotiation conduct. Its six-domain set
  is narrow and heavily concentrated in RIA, OHCHR, PACE, and TASS.
- 3B is the best-balanced final ledger by domain. It is strong on repression and
  protest control, while oversight/remedy and the fear/self-censorship lens remain thin.
- 4B has broad domain diversity and strong repression/election evidence, but discovery
  stopped at 74 and evidence of affirmative institutional restraint is sparse.
- 5B is the weakest discovery result. It began with a zero-URL model refusal, ended at
  57, and relies heavily on the Bank of Russia, World Bank, and Kommersant. It remains
  weak on ruler-attributed appointments, competition enforcement, and distribution.
- 6B reached 107, but direct welfare administration, disability services, housing, and
  coercive use of benefits remain weaker than education/propaganda evidence.
- 7B has useful proxy-wealth and sanctions-evasion evidence, but a clean Putin asset
  trail, honest correction, and competence-over-loyalty evidence remain missing. Foreign
  enforcement and investigative families substitute for blocked Russian primary pages.
- 8B met the numeric target but is the largest substantive warning: Treasury, DOJ, and
  Reuters/Investing.com make up 70% of the final ledger. Much of that evidence is about
  sanctions, evasion, elite networks, or macro pressure rather than direct implementation
  competence. Personnel quality and internal coordination remain weak.

## Recommended next iteration

Do not simply raise the search-round ceiling. Use parent-owned query-family queues and
domain/lens quotas so each round has a bounded assignment, require a candidate artifact
even when the model reports a search ceiling, and stop inspection once the independent
reviewer finds 20–30 non-duplicative sources sufficient. Add a final admissibility review
for chapter scope—especially 8B—because URL uniqueness and source count do not prevent
cross-chapter thematic contamination.
