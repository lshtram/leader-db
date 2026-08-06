# Attempt 4 result: 100-candidate target

## Outcome

- Candidate IDs: 115
- Parent-verified unique canonical candidate URLs: 109
- Model-reported unique URLs before correction: 114
- Exact duplicates caught by parent verification: 5
- Documents successfully opened: 31
- Final accepted source documents: 20
- Context-only documents: 17
- Access blocked: 12
- Opened but demoted: 11
- Final accepted URLs: 20
- Final accepted domains: 8

The quantitative target was met: more than 100 unique candidate URLs were discovered,
31 underlying documents were opened, and exactly 20 sources survived final selection.
No accepted record was counted from a snippet-only or unopened candidate.

## Resource profile

- Successful profiled turns: 7
- Profiled web-search/tool calls: 160
- Profiled researcher time: 3,630.4 seconds (60.5 minutes)
- Cumulative input tokens: 850,608
- Cached input tokens: 166,272
- Output tokens: 196,053
- Known estimated GPT-5.4-mini cost: $1.408
- One additional all-pool inspection attempt timed out after 900 seconds and emitted no
  usable profile or notebook. Its token usage and cost are unknown and are excluded
  from the known estimate.

The first discovery turn reached the surface's 30-search ceiling at 63 unique URLs.
A second discovery turn added 46 net-new unique URLs after parent-side deduplication.
The initial attempt to inspect the entire pool in one turn timed out. Three bounded
inspection waves were required.

## Final source concentration

| Domain | Accepted URLs |
|---|---:|
| `ukraine.un.org` | 7 |
| `odihr.osce.org` | 3 |
| `ukraine.ohchr.org` | 3 |
| `president.gov.ua` | 3 |
| `icrc.org` | 1 |
| `reutersconnect.com` | 1 |
| `loc.gov` | 1 |
| `en.special.kremlin.ru` | 1 |

Although the accepted set has 20 URLs, it contains only eight domains and is heavily
concentrated in UN operational notes and Ukrainian government peace-formula material.
Seven UN-in-Ukraine pages mainly represent one diplomatic/humanitarian source family,
and three Ukrainian presidential pages represent one advocacy family. They are distinct
documents but not ten independent source families.

## Coverage quality

Strong:

- Civilian harm and humanitarian law
- Occupation coercion
- Child transfers
- Humanitarian mitigation
- Black Sea Grain Initiative chronology
- General diplomacy and peace-formula activity

Weak:

- 2B.3 motive and defensive necessity
- 2B.6 Putin's public justification and misinformation
- 2B.8 military spending and mobilization motives: only one final source
- Direct Putin/Kremlin transcripts
- Russian fiscal and budget primary records
- Proxy command and financing
- Turkish and African mediation-party records

The final ledger therefore meets the numerical target but does not yet meet a balanced
chapter-quality target. Candidate breadth alone did not prevent final-source
concentration. The selector over-retained serial updates from the same UN/grain-deal
family and Ukrainian peace-formula family while dropping too much of the strategic,
budget, proxy, and direct-Putin material.

## Workflow lesson

A workable production design needs all of the following constraints, not only a raw
candidate target:

1. At least 100 parent-verified unique candidate URLs across multiple discovery turns.
2. Inspection waves of roughly 15–25 candidates; 40 is near the timeout boundary and
   an all-pool inspection is not viable.
3. At least 20 successfully opened accepted documents.
4. Minimum useful-source floors for every lens before final selection.
5. A cap on one publisher or event family in the final ledger unless concentration is
   substantively unavoidable.
6. Explicit source-family counts separate from URL counts.
7. Parent-side URL canonicalization and reconciliation.
8. Final selection that preserves direct ruler statements, primary policy/budget/legal
   records, adverse monitoring, favorable/contrary material, and mediation records.

The next selector prompt should reserve slots before ranking globally—for example,
minimum allocations for diplomacy, initiation/coercion, motives/justification,
civilian conduct, proxies, military resources, accountability, and end-state evidence—
then use remaining slots for the strongest cross-lens sources. That would prevent
abundant humanitarian and grain-deal material from crowding out thin but essential
lenses.
