# Whole-Context Evidence Reader Diagnostic

Date: 2026-07-30  
Status: experimental; no evidence promoted  
Case: AMLO, Mexico, 2022, Chapter 5B  
Sources: `BOOK-013`, `MAC-010`, `LAW-005`

## Decision

The windowed CLI-agent experiment is on hold. Its unit of work—one extractor and
one reviewer session per 300-sentence window—does not scale to ordinary
long-context documents. The complete frozen trio is about 60,000 words and fits in
one modern model context.

Two one-call GPT-5.4-mini reader diagnostics received the complete source text and
the ten Chapter 5B lenses. Neither used search or a tool loop.

| Arm | Elapsed | Provider tokens | Facts | BOOK | MAC | LAW |
|---|---:|---:|---:|---:|---:|---:|
| Broad relevance | about 2 minutes | 120,090 | 100 | 59 | 38 | 3 |
| Target-period selective | about 2 minutes | 117,527 | 70 | 7 | 61 | 4 |

Source counts in the second arm overlap where one fact cites more than one source.

## Findings

- Whole-context reading solved the runtime problem: a complete trio pass took
  minutes rather than dozens of serial model sessions.
- The first prompt over-selected historical biography. The second prompt capped
  pre-period context and removed nearly all of that noise.
- The second memo is 2,895 words. Preliminary manual comparison places it around
  34–36 of the 47 benchmark facts, near the 75 percent recall threshold. A final
  record-by-record accuracy audit has not been completed.
- Remaining omissions are concentrated in detailed annex findings: tax-
  administration revenue gains, subcontracting effects, PEMEX condition and
  recommendations, precise subsidy incidence, selected USMCA/competition details,
  and two exact legal-table findings.
- The model ignored the requested 45–50 hard output count and returned 70 findings.
  This is a selection/pruning problem, not a corpus-runtime failure.
- Locator labels were usually present, but they remain model-selected references.
  Deterministic resolution and support checking are still required before promotion.

## Candidate Replacement

Use one whole-context reader per source package or model-context-sized package.
Give it the selected chapter questions, source roles, target period, and a
permissive evidence-memo task. Ask it to highlight material findings once, with
locator labels and question mappings. Then:

1. deterministically resolve each locator to source text;
2. use a compact selection pass to merge duplicates and remove low-materiality
   findings;
3. run one source-package factual review, not one review per chunk or fact; and
4. retain the original memo so formatting failures never erase substantive work.

Chunking is a fallback only when the complete relevant package exceeds model
context. The CLI-agent prototype remains a diagnostic and is not the active
expansion path.

## Complete 16-Source Expansion

The 16 frozen extracts contain about 250,846 estimated source tokens. A single
GPT-5.4-mini call received the complete package but exhausted the 400,000-token
context while generating its answer. Codex reported zero usage for that failed
call, so its token accounting is not usable.

The successful fallback used two large source-role packages plus one compact
merge:

| Pass | Contents | Elapsed | Provider tokens |
|---|---|---:|---:|
| Package A | IMF and OECD reports | about 32 seconds | 170,312 |
| Package B | Other 14 frozen sources | about 31 seconds | 113,543 |
| Merge | Package A and B memos only | about 51 seconds | 10,289 |
| **Total** | **Complete frozen package** | **about 115 seconds** | **294,144** |

The merged memo contains 14 consolidated evidence accounts and a
question-by-question coverage section for all ten Chapter 5B lenses. It preserves
favorable, adverse, mixed, and qualifying material; distinguishes official
self-reporting from independent and institutional analysis; identifies source
dependence and conflicts; and records claims needing original-passage
verification.

This passes the architecture/throughput experiment. It does not yet pass a final
evidence-publication gate: citations are page/block ranges rather than
deterministically bound spans, several consolidated accounts contain multiple
factual clauses, and the 14-account merge is more compressed than the two
underlying package memos.

## Researcher-Package Expansion

The next scale test used the evidence researcher's round-3 Chapter 5B ledger:
35 evidence records, 33 distinct URLs, and 17 publishers. Direct acquisition
produced 21 response bodies and 14 usable full-text extracts totaling about
2.8 MB. Duplicate URLs mean those 14 texts underlie 18 ledger records. The other
19 URLs were blocked, timed out, returned challenge/application shells, or were
otherwise not usable as full text; the test preserved these as acquisition
limitations and did not bypass them.

Five GPT-5.4-mini readers processed the usable texts by source role:

| Package | Elapsed | Provider tokens | Memo bytes |
|---|---:|---:|---:|
| IMF | 72.73 seconds | 103,375 | 17,180 |
| OECD | 69.77 seconds | 109,553 | 21,503 |
| Poverty report | 58.40 seconds | 144,835 | 14,427 |
| Poverty and program reports | 51.82 seconds | 84,413 | 14,016 |
| Banxico and shorter web sources | 66.35 seconds | 89,725 | 16,555 |
| **Total** | **about 143 seconds wall time** | **531,901** | **83,681** |

The IMF package ran first. The other four ran concurrently, so total reading wall
time is the first pass plus the slowest concurrent pass rather than the sum of
the elapsed column.

A fresh audit compared the five memos directly with the 35-entry researcher
ledger. Across the 18 entries whose underlying full text was supplied, 14 were
preserved accurately, four were partially preserved, none were absent, and none
were materially contradicted or distorted. This is 100 percent semantic recall,
77.8 percent exact preservation, and no observed factual reversal. Precision
loss centered on exact rates, counts, and comparison values.

Across all 35 entries, including sources unavailable to the reader, 17 were
preserved accurately, seven partially, 11 absent, and none materially distorted.
The missing entries primarily reflect acquisition coverage, so they must not be
treated as extraction failures. The existing verified researcher ledger remains
the record for access-limited sources.

An attempted compact merge reduced the package to ten thematic accounts and
lost quantities and locators. A stricter second merge stalled after producing no
answer and was terminated after 225 seconds. The supported topology therefore
stops at the source-role memos: preserve them as the judge/research package and
build only a deterministic index over them. Do not add a generative merge.
