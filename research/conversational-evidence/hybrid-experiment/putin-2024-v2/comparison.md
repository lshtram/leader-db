# Putin 2024 controlled comparison: production flow vs chapter-wide v2

## Bottom line

V2 is a better **research note process**, but it is not yet a better production dossier.
It found more distinct web documents, used far fewer turns, cost less than half as much,
and produced much better locators, temporal caveats, ruler attribution, and contrary
evidence. However, the old flow still has more distinct URLs inside five of eight
chapters and a much stronger validated claim-to-lens output contract. V2 stopped at 118
URLs rather than its 120 minimum target, and its final formatter preserved only a thin
URL index plus chapter notes rather than canonical source-claim records.

Recommendation: keep v2's chapter-wide research and combined review, but do not replace
the main flow yet. Fix the acceptance ledger and formatter, then repeat one controlled
run. Do not add more prompts.

## Resource comparison

| Measure | 2024 production flow | Chapter-wide v2 | Difference |
|---|---:|---:|---:|
| Total model turns | 163 (82 research + 81 format) | 13 | -92% |
| Web/tool calls | 143 | 191 | +34% |
| Elapsed model time | 7,808 s (130.1 min) | 4,155 s (69.2 min) | -47% |
| Recorded estimated cost | $4.53 researcher only | $1.94 all recorded turns | -57% |
| Input tokens | 13.53M including formatter | 2.01M | -85% |
| Output tokens | 417,478 including formatter | 192,433 | -54% |
| Distinct URLs | 94 | 118 | +24 (+26%) |
| Distinct domains | 31 | 48 | +17 (+55%) |
| Final evidence/URL rows | 649 claim rows | 118 URL-index rows | Not equivalent |
| Run artifact size | 3.9 MB | 1.4 MB | -64% |

The cost comparison favors v2 even though the old $4.53 figure excludes the 81 Luna
formatter turns. It is therefore conservative. V2 made more web calls because each
chapter was explicitly asked to inspect about 30 documents; it saved money by avoiding
80 separate growing-context lens conversations and 80 formatter calls.

## Coverage by chapter

| Chapter | Production distinct URLs | V2 distinct URLs | Production domains | V2 domains |
|---|---:|---:|---:|---:|
| 1B | 12 | 19 | 6 | 9 |
| 2B | 22 | 19 | 10 | 8 |
| 3B | 33 | 13 | 14 | 6 |
| 4B | 24 | 21 | 13 | 13 |
| 5B | 33 | 18 | 13 | 10 |
| 6B | 45 | 18 | 17 | 9 |
| 7B | 31 | 14 | 15 | 11 |
| 8B | 38 | 18 | 12 | 12 |

This is the key qualification to the global 118-vs-94 result. V2 spread its sources
across chapters and reused much less. It had 110 chapter-linked URLs and 140
chapter-URL occurrences; only 24 URLs served more than one chapter. Production had 238
chapter-URL occurrences from 94 global URLs. Thus v2 is globally broader, but the old
flow is deeper by raw distinct-URL count in Chapters 2B, 3B, 4B, 5B, 6B, 7B, and 8B.
Only 13 exact URLs overlap between the two runs, so v2 genuinely explored a different
source set rather than simply repackaging the old dossier.

## Duplication and evidence quality

The production dossier has 649 claim rows derived from 94 URLs. Sixty-nine URLs are
reused, only 25 are singletons, and there are 555 rows beyond one row per URL. This is
not 555 exact duplicates: most summaries differ because the same document was
reinterpreted for different lenses. But the degree of repetition is substantial. For
example, the same Freedom House `Freedom in the World 2024` page produces 50 different
evidence rows, and `Nations in Transit 2024` produces 28. Several Reuters stories each
produce 17-27 rows. This inflates the apparent 649-record volume and risks counting one
source family or underlying fact many times.

V2 removes URL duplication before its final index and explicitly rejects duplicate
syndications in each chapter. Its chapter notes are materially more auditable. A typical
7B record includes the exact decree or event, page-line locator, source type, credibility,
target-year fit, direct or limited Putin attribution, contrary interpretation, and exact
lenses. The old record has title, publisher, date, URL, and a short lens-specific summary
but no locator, source-confidence explanation, attribution limit, or contrary field.

V2 still has concentration problems: 30 of 118 URLs are `www.investing.com` Reuters
syndications. Chapters 1B, 2B, and 6B exceed the 35% top-domain warning. This is less
severe globally than production's record-level concentration (`investing.com` accounts
for 201 of 649 rows), but it remains a real source-family issue.

## Review result and weaknesses

The first combined no-search review passed 1B-4B and 8B and requested one follow-up for
5B-7B. The follow-up added eight URLs, moving the dossier from 112 to 118. The final
review kept 1B-4B and 8B as pass and placed 5B, 6B, and 7B in manual review:

- 5B remained macro-heavy and weak on causal attribution from Putin's choices to broad
  prosperity.
- 6B still relied heavily on official self-report and aggregate indicators.
- 7B had credible Putin-specific secrecy and patronage evidence, but personal enrichment
  remained indirect.

Those are sensible substantive cautions, not evidence-collection crashes. The reviewer
also preserved credible nonrecoverable gaps in passed chapters.

There are three implementation weaknesses before v2 can replace production:

1. The parent currently treats every URL in a chapter note as accepted and attaches all
   lens IDs mentioned anywhere in that note. It needs a parsed source-claim ledger with
   exact per-record mappings.
2. The formatter emits the 118-row URL index and compressed chapter notes, not canonical
   evidence records carrying claims, locators, confidence, attribution, and contrary
   evidence. The richer raw research is therefore not fully represented in the dossier.
3. In this run, the grouped follow-up received credible gaps from passed chapters as well
   as targeted gaps from 5B-7B. The runner has been corrected after the run so future
   follow-ups include only chapters explicitly marked `targeted_follow_up`; this result
   remains unchanged for auditability.

## Decision

V2 demonstrates that chapter-wide research is the right cost/quality direction. It cut
recorded cost by about 57% and time by about 47% while increasing global URL and domain
diversity and improving the actual research prose. But the 118-URL index is not yet a
drop-in replacement for the old 649 claim rows and 80 validated mappings. The next test
should keep exactly the same 13-turn maximum and add only deterministic parsing and a
strict no-search source-claim formatter. Success criteria should be 120-160 accepted
URLs, 12-20 distinct URLs per chapter, exact per-record mappings, zero unmapped accepted
records, and no loss of locator/attribution/contrary detail.
