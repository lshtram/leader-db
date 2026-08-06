# Putin 2023 Chapter 2B GPT-5.4-mini prompt comparison

Date: 2026-07-19

This experiment compared three GPT-5.4-mini research designs without changing the
collector code or normative project directives. All model notes, exact new prompts,
event logs, and per-turn profiles are preserved beneath this directory.

## Designs

1. **Current control**: the existing completed Putin run, using one reconnaissance
   turn followed by ten lens turns capped at six search/fetch calls each. The saved
   control slice includes the reconnaissance and Chapter 2B raw notes.
2. **Chapter-wide saturation**: the same reconnaissance prompt followed by one
   unconstrained Chapter 2B turn covering all ten lenses, with explicit source-pool,
   contrary-evidence, disposition, attribution, and saturation instructions.
3. **Staged research**: the same reconnaissance prompt followed by separate discovery,
   extraction, and targeted gap-fill turns. Candidate sources did not count as evidence
   unless the underlying item was opened and read.

## Quantitative comparison

| Measure | Current control | Chapter-wide saturation | Staged research |
|---|---:|---:|---:|
| Research turns including reconnaissance | 11 | 2 | 4 |
| Search/tool calls | 35 | 40 | 89 |
| Elapsed researcher time | 904.9 s | 625.1 s | 1,226.4 s |
| Input tokens | 1,033,751 | 179,516 | 406,510 |
| Cached input tokens | 832,640 | 16,640 | 55,808 |
| Output tokens | 51,052 | 29,230 | 60,625 |
| Estimated GPT-5.4-mini cost | $0.442 | $0.255 | $0.540 |
| Final accepted claim records | 84 mapped records | 16 ledger records | 23 ledger records |
| Distinct accepted URLs | 39 | 16 | 15 |
| Distinct accepted domains | 21 | 10 | 9 |

Token accounting uses cumulative persistent-thread usage correctly. For the control,
the reconnaissance turn is added to the marginal usage between the end of Chapter 1B
and the end of Chapter 2B. Summing every cumulative turn profile would substantially
overcount usage.

The accepted-record counts are not equivalent measures of quality. The control's 84
records include extensive repeated-source claim splitting and formatter mappings. Its
39 accepted URLs are concentrated in Reuters republications and mirrors: 14 records
use Investing.com, 11 use ThePrint, and several more use other wire republications.
The newer attempts deliberately retained fewer, stronger claim units and rejected
snippet-only or inaccessible candidates.

## Qualitative findings

### 1. Current control

Strengths:

- Ten separate lens notes make nominal lens coverage easy to obtain.
- The persistent evidence index encourages reuse.
- It produced many mapped records and URLs.

Weaknesses:

- The ten Chapter 2B turns used only 19 searches in total; four lens turns performed
  no web search at all despite being allowed up to six.
- Search depth depended heavily on whatever the model had already accumulated.
- Output volume overstated independent research breadth because the same wire stories,
  mirrors, and source claims were repeatedly split and mapped.
- Candidate-source dispositions, opened-versus-snippet status, saturation evidence,
  locators, temporal fit, and attribution were not consistently recorded.
- The approach used the most input tokens because each lens inherited a growing long
  conversation and evidence index.

### 2. Chapter-wide saturation

Strengths:

- Used 32 Chapter 2B searches in one connected investigation, compared with 19 across
  the control's ten lens turns.
- Produced a coherent 16-item ledger with explicit temporal fit, attribution,
  limitations, reused lens mappings, rejections, and saturation notes.
- Used stronger source concentration: UN/OHCHR, ICC, SIPRI, HRW, AP, official Russian
  material, and limited reputable reporting.
- Cheapest attempt and fastest overall, despite deeper active discovery.
- Avoided the enormous repeated-context cost of ten separate lens turns.

Weaknesses:

- Its claimed candidate-pool audit remained general rather than enumerating every
  inspected candidate.
- Some accepted material depended on secondary coverage where primary pages were hard
  to access.
- Sixteen retained claims are still not a large evidence pool for Putin in 2023.
- The single synthesis turn may compress or omit candidates before they are durably
  recorded.

### 3. Staged research

Strengths:

- Best research process and auditability.
- Discovery recorded query families, candidate sources, access failures, a source/lens
  matrix, and a prioritized extraction queue before final selection.
- Extraction explicitly accepted only opened-and-read sources and rejected snippets,
  inaccessible pages, duplicates, and weak candidates.
- Gap repair added 11 claim records, growing the ledger from 12 to 23. It materially
  improved direct or near-primary evidence on Putin's war aims, peace claims,
  mobilization, military expansion, military production, and grain-deal reasoning.
- The final ledger clearly separates direct Putin statements, state-level attribution,
  monitoring evidence, mitigating material, and limitations.
- Russian-language and Russian institutional material improved substantially through
  Consultant.ru and TASS when Kremlin pages could not be fetched.

Weaknesses:

- Most expensive and slowest attempt.
- Eighty-nine searches yielded only 15 accepted URLs. The low conversion rate partly
  reflects strict admissibility and repeated access failures, but it also shows that
  more calls do not automatically produce hundreds of readable documents.
- The final source pool is still concentrated: TASS supplies four accepted URLs and
  OHCHR three.
- The repair turn repeated the complete ledger, increasing output cost.
- The model declared effective saturation despite unresolved ICC and Kremlin access;
  that conclusion should be treated as tool-path saturation, not global literature
  saturation.

## Overall assessment

**Best quality: staged research.** It produced the most defensible and inspectable
research process, and the gap-repair turn demonstrably added material evidence rather
than merely rewriting the first ledger.

**Best cost/quality compromise: chapter-wide saturation.** It was cheaper than the
control, searched more actively, avoided repeated-context inflation, and produced a
much cleaner evidence set. For broad production testing, this is the strongest base
design.

**Weakest scientific design: current per-lens cap.** Its high nominal record count is
misleading because independent-document breadth and source quality are weaker than the
count suggests. The fixed cap is not the only problem: isolated lens turns and repeated
context encourage source reuse without forcing a transparent discovery pool.

## Recommended next prompt experiment

Use the chapter-wide design as the base, but add one conditional continuation rather
than always paying for three staged turns:

1. Run reconnaissance.
2. Run one chapter-wide saturation pass that must preserve an enumerated candidate
   inventory and an accepted ledger.
3. Automatically request a targeted continuation only when the first pass identifies
   material gaps, excessive source concentration, missing primary/contrary evidence,
   or fewer than a defensible number of opened source families.

The continuation should return only new or revised records plus a compact change log,
not repeat the entire ledger. This should retain most of Attempt 3's quality benefit
while approaching Attempt 2's cost and latency.

The next test should also distinguish these counters explicitly:

- search queries,
- candidate URLs discovered,
- unique documents successfully opened,
- documents rejected and why,
- accepted URLs,
- independent source families,
- accepted claim units,
- and lens mappings.

The present Codex event profile reports web-search tool invocations but does not expose
a reliable separate count of candidates returned versus underlying documents opened.
Prompt claims about documents inspected therefore remain auditable only through the
saved notebook, not through an independent tool-event counter.
