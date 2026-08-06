# Budgeted hybrid GPT-5.4-mini evidence flow

Status: design proposal for review; not yet implemented.

## 1. Objective and budget envelope

This flow stays close to the 2024 lens-oriented collector while adding chapter-level
depth and quality controls. It does not ask the model to discover 100 documents per
chapter.

Target per ruler-year:

- 120–180 distinct accepted URLs globally, with cross-chapter reuse;
- normally 12–18 accepted source-claim units per chapter;
- 25–40 verified candidate URLs per chapter before inspection;
- one initial research round and at most one targeted gap-fill round per chapter;
- approximately $4–6 for GPT-5.4-mini research and no-search review/formatting;
- no final score during evidence research.

The source targets are depth goals, not automatic readiness rules. A chapter may pass
below target only with a documented credible scarcity/access blocker and a reviewer
finding that further broad search is unlikely to improve the material gaps.

## 2. Roles

### Parent controller — deterministic Python

The controller owns identity validation, local-prior loading, prompt assembly, thread
IDs, tool/turn budgets, URL canonicalization, deduplication, source IDs, ledgers,
coverage calculations, quality gates, retry limits, profiling, and checkpoints.

### Persistent researcher — GPT-5.4-mini with web access

One persistent thread researches the ruler-period and chapters 1B–8B in order. It
discovers candidates, opens promising documents, extracts evidence, records contrary
material and attribution, and responds to targeted reviewer gaps. It never scores.

### Evidence reviewer — separate GPT-5.4-mini, no web access

The reviewer reads one chapter package and checks scope, adequacy, attribution,
contrary evidence, concentration, and genuine gaps. It cannot add facts or sources.

### Formatter — separate no-search model

The formatter transcribes only accepted evidence into the strict dossier schema. It
cannot research or improve the evidence.

## 3. Configurable controls

Suggested initial configuration:

```yaml
candidate_target_per_chapter: 30
candidate_minimum_with_blocker: 20
candidate_hard_maximum: 40
accepted_target_per_chapter: 15
accepted_minimum: 10
accepted_maximum: 18
initial_research_rounds: 1
gap_fill_rounds: 1
inspection_batch_size: 15
reconnaissance_max_accepted_sources: 12
gap_fill_max_new_candidates: 15
gap_fill_max_new_accepted: 6
minimum_distinct_domains: 5
maximum_single_domain_share: 0.30
minimum_primary_or_official: 2
minimum_independent_sources: 3
minimum_outcome_sources: 1
require_contrary_or_favorable_material: true
require_central_claim_ruler_attribution: true
turn_timeout_seconds: 900
full_ruler_cost_warning_usd: 5.00
full_ruler_cost_stop_usd: 6.50
```

The cost stop applies before starting a new chapter or gap-fill turn. It does not kill a
paid call already in progress. The run stops resumably and reports the remaining work.

## 4. Step-by-step execution

### Step 0 — Parent validation and local preparation; no model call

The controller:

1. Resolves and locks ruler, country, ISO3, and period.
2. Rejects identity-quarantined or not-ready jobs.
3. Loads the 80-question catalog and all eight chapter guides.
4. Loads and validates local priors, excluding the client matrix as evidence.
5. Builds a deduplicated local fact package and authority-baseline hints.
6. Loads any existing global source ledger and completed-query register.
7. Creates an atomic session checkpoint and immutable config snapshot.

No prompt is sent if these checks fail.

### Step 1 — Initial ruler reconnaissance

One web-enabled call starts the persistent researcher thread. The objective is a compact
authority and event map, not a large evidence dossier.

#### Prompt 1 — exact template

```text
You are the evidence researcher for one resolved political ruler-period in the Leaders
Database. You will remain in this same research thread while chapters 1B through 8B are
processed in order. Research evidence only. Do not assign, suggest, or imply any score.

RESOLVED IDENTITY
- Ruler: {ruler}
- Country: {country}
- ISO3: {iso3}
- Period: {period_start} through {period_end}
- Identity resolution status: locked by the parent

CLIENT MATRIX POLICY
The client matrix is validation-only and is not evidence. Do not inspect it, cite it,
infer from it, or use it to choose favorable or adverse material.

LOCAL PACKAGE
{local_prior_summary}

TASK
Build a compact ruler-period reconnaissance that later chapter research can reuse.
Establish:
1. the ruler's formal office and ordinary national policy/appointment responsibility;
2. material legal, coalition, party, military, or institutional constraints;
3. the major target-period events and inherited conditions likely relevant across the
   eight chapters;
4. the strongest primary, institutional, scholarly, local-language, favorable, adverse,
   and contrary source families to search later;
5. any closed-information or access problems already visible.

Accept no more than {reconnaissance_max_accepted_sources} reusable authority or
cross-chapter baseline sources. Search iteratively, but keep this a reconnaissance pass:
do not build chapter inventories and do not repeat a local dataset already represented
in the supplied package.

OUTPUT — COMPACT MARKDOWN ONLY

## Authority baseline
For each accepted baseline source, give one row:
BASE-{number} | title | publisher | date | canonical URL | source type | precise useful
claim/locator | temporal fit | ruler-attribution use | limitations

## Target-period event map
Compact bullets with candidate chapter IDs; no long narrative.

## Source-family plan
For each chapter, list promising source families and local-language query themes.

## Access and attribution risks
List only concrete risks.

## Queries completed
List the actual query families used in this turn.

Do not output a score. Do not create 80 lens rows. Do not claim that a page was opened
unless you opened it.
```

### Step 2 — Parent parses reconnaissance; no model call

The controller canonicalizes URLs, rejects invalid/mirror duplicates, assigns global
evidence keys, stores the authority baseline once, updates cumulative usage/cost, and
creates a compact global ledger index. It never copies the same baseline record into
eight chapter ledgers.

### Step 3 — Begin one chapter with reuse plus bounded discovery

The controller selects the next chapter, supplies its complete guide and ten questions,
and provides only the relevant compact ledger/local-prior slice. One web-enabled call
must both reuse existing evidence and discover 25–40 candidate documents.

#### Prompt 2 — exact template, repeated once per chapter

```text
Continue the same ruler-period research thread. Work only on Chapter {chapter_id} for
{ruler} during {period_label}. Research evidence only; do not score.

CHAPTER GUIDE
{complete_chapter_guide}

TEN EVIDENCE LENSES
{chapter_questions}

RELEVANT LOCAL PRIORS
{chapter_local_priors}

REUSABLE GLOBAL EVIDENCE INDEX
{relevant_global_evidence_index}

COMPLETED CHAPTER QUERIES
{completed_query_families_or_none}

PARENT TARGETS
- Desired verified candidate URLs after this turn: {candidate_target_per_chapter}
- Hard maximum candidate rows returned: {candidate_hard_maximum}
- Existing verified chapter candidates: {existing_candidate_count}
- Existing accepted evidence potentially reusable here: {reusable_evidence_count}

TASK
1. First identify which existing global evidence records genuinely support this chapter.
   Reuse them; do not rediscover or rewrite them.
2. Identify the concrete missing evidence themes across the ten lenses. A missing lens is
   not automatically a request for its own source; one strong source may support several
   lenses.
3. Search broadly but purposefully across distinct query and source families until the
   candidate target is reached, the hard maximum is reached, or a specific search/access
   blocker makes the target unreasonable.
4. Include primary/legal records, independent institutional monitoring or scholarship,
   reputable reporting, relevant local-language sources, outcomes, ruler attribution,
   and favorable or contrary evidence where available.
5. Candidate search results are not accepted evidence. Do not claim opened status in the
   candidate table unless you actually opened the underlying document.

DEDUPLICATION RULES
- One underlying document equals one candidate even if it has mirrors, translations,
  print pages, tracking parameters, or syndications.
- Prefer the original publisher URL.
- Exclude search pages, snippets without a recoverable URL, tag/index pages, irrelevant
  pages, and repeated coverage that adds no distinct evidence.
- Do not repeat any URL in the parent-supplied global or chapter index.

OUTPUT — COMPACT MARKDOWN ONLY

## Reused evidence
One line per reused global evidence ID:
evidence ID | exact Chapter {chapter_id} lenses | why it is in scope | attribution limit

## Missing themes before discovery
Short bullets naming the exact evidence needed.

## New candidate inventory
Return between 0 and {candidate_hard_maximum} rows:
{chapter_id}-C### | title | publisher | date | canonical URL | source family/type |
language | likely exact lenses | one-line distinct relevance | opened yes/no |
duplicate-family note

## Removed during discovery
Counts and short reasons for invalid URL, mirror, syndication, irrelevant, temporal, and
same-event-family removals. Do not reproduce removed rows in full.

## Query families completed
List actual query families, including local-language searches.

## Unresolved candidate gaps or blocker
Be specific. Do not ask the user whether to continue; the parent controller decides.

Do not return full evidence summaries yet. Do not score.
```

### Step 4 — Parent candidate processing; no model call

The controller:

1. Canonicalizes every candidate URL.
2. Removes within-chapter and global duplicates while preserving cross-chapter reuse.
3. Rejects IDs without valid URLs.
4. Calculates domain, source-family, language, temporal, and likely-lens distributions.
5. Selects at most 30 candidates for inspection, normally in two batches of 15.
6. Prioritizes weak lenses, primary records, contrary evidence, attribution, outcomes,
   and underrepresented domains instead of simply taking the first rows.
7. If fewer than 20 valid candidates remain without a credible blocker, marks discovery
   quality as failed and reserves the chapter's one gap-fill round.

### Step 5 — Inspect and accept evidence

The researcher receives only one 15-candidate batch at a time plus the compact accepted
ledger index. Normally this produces two web-enabled calls per chapter. The second call
may be skipped when quality targets are already met after the first batch.

#### Prompt 3 — exact template, one or two inspection batches per chapter

```text
Continue Chapter {chapter_id} for {ruler} in the same research thread. Inspect only the
candidate rows supplied below. Do not search broadly for unrelated replacements in this
turn. Do not score.

TEN EVIDENCE LENSES
{chapter_questions}

CURRENT ACCEPTED CHAPTER INDEX
{accepted_chapter_index_or_none}

CANDIDATES TO INSPECT
{inspection_batch}

CURRENT QUALITY GAPS
{current_quality_gaps}

TASK
Open and read the strongest relevant underlying documents in this batch. Give every
requested candidate exactly one disposition:
- opened_accepted
- opened_context_only
- opened_rejected_weak
- opened_rejected_irrelevant
- rejected_duplicate_document
- rejected_duplicate_event_family
- rejected_temporal
- access_blocked
- deferred_lower_priority

Accept a source only when it contributes a materially distinct, traceable claim needed
for Chapter {chapter_id}. Do not accept a document merely to reach a number. One accepted
source may map to several exact lenses. A substantial report may support multiple
materially distinct claims, but it remains one source family and one URL.

For accepted evidence, preserve favorable or contrary points and distinguish:
- target-period ruler conduct;
- inherited/country context;
- outcomes;
- allegations versus established findings;
- ordinary authority-based attribution versus direct personal action.

OUTPUT — COMPACT MARKDOWN ONLY

## Newly accepted evidence
At most {remaining_acceptance_capacity} records. For each:
SOURCE TEMP ID | candidate ID | title | publisher | date | canonical URL | source type |
language | precise claim summary | locator or short excerpt | temporal fit |
ruler-attribution basis and limit | contrary/favorable point | exact Chapter
{chapter_id} lenses | source confidence and reason

## Candidate dispositions
One compact line for every supplied candidate ID:
candidate ID | disposition | accepted SOURCE TEMP ID if any | short reason

## Updated substantive gaps
Only gaps that remain after reading this batch.

Do not repeat previously accepted records. Do not provide a chapter score or a long
chapter narrative.
```

### Step 6 — Parent ledger merge and deterministic quality gate; no model call

The controller assigns stable global evidence IDs, merges reused and new evidence, and
calculates the following. Counts are based on canonical URLs and independent source
families, not model prose.

1. Accepted range: normally 10–18; target 15.
2. All ten lenses have either mapped concrete evidence or an explicit searched gap.
3. At least five distinct domains, unless a justified primary-source concentration is
   reported.
4. No single domain exceeds 30%, unless the exception is explicitly reviewed.
5. At least two primary/official sources where available.
6. At least three independent monitoring, scholarly, or reputable reporting sources.
7. At least one outcome source.
8. Meaningful contrary/favorable evidence or a specific absence explanation.
9. Central chapter claims have ruler attribution appropriate to the guide.
10. No duplicate URLs, mirrors, same-document variants, or empty/snippet-only records.
11. Chapter-scope admissibility: evidence must address this chapter rather than merely
    sharing a ruler or event with another chapter.

The controller emits a compact quality report. Mechanical failures are fixed without a
model. Substantive failures go to the no-search reviewer.

### Step 7 — Independent no-search evidence review

One no-search call reviews the consolidated chapter package. It does not score and does
not add evidence.

#### Prompt 4 — exact template, separate no-search thread

```text
You are the no-search evidence-quality reviewer for Chapter {chapter_id}, {ruler},
{period_label}. Do not browse, add facts, add URLs, rewrite evidence, or assign a score.

CHAPTER GUIDE
{complete_chapter_guide}

TEN LENSES
{chapter_questions}

DETERMINISTIC QUALITY REPORT
{parent_quality_report}

ACCEPTED EVIDENCE LEDGER
{accepted_chapter_ledger}

REJECTION AND ACCESS SUMMARY
{rejection_and_access_summary}

TASK
Decide whether this evidence can fairly present the chapter-relevant governing conduct,
important contrary material, outcomes, and ruler attribution. Source count alone is not
adequacy. Check especially:
- chapter scope and contamination from sibling chapters;
- repeated source/event families masquerading as agreement;
- direct versus ordinary-authority attribution;
- allegations versus established findings;
- inherited context versus target-period conduct;
- missing favorable/contrary evidence;
- weak discriminating lenses hidden by generic coverage;
- closed-information and blocked-primary-source limitations.

OUTPUT — STRICT JSON ONLY
{
  "chapter_id": "{chapter_id}",
  "decision": "pass" | "targeted_gap_fill" | "credible_blocker_pass",
  "material_scope_problems": [
    {"evidence_id": "ID", "problem": "specific problem", "required_action": "remove|context_only|clarify"}
  ],
  "research_recoverable_gaps": [
    {
      "gap_id": "GAP-01",
      "exact_theme": "what is missing",
      "exact_lenses": ["{chapter_id}.x"],
      "preferred_source_types": ["type"],
      "preferred_query_directions": ["direction"],
      "why_material": "why the chapter is not yet fair"
    }
  ],
  "nonrecoverable_or_access_gaps": ["specific gap"],
  "concentration_assessment": "brief assessment",
  "attribution_assessment": "brief assessment",
  "contrary_evidence_assessment": "brief assessment",
  "reason": "concise decision rationale"
}

Return targeted_gap_fill only for material gaps likely to improve through one bounded
research round. Do not request generic 'more sources'.
```

### Step 8 — Parent applies removals and decides whether gap-fill is allowed

The controller deterministically removes or downgrades reviewer-identified inadmissible
records, recalculates the quality report, and checks:

- Has this chapter already used its one gap-fill round?
- Is projected full-ruler cost below the stop threshold?
- Did the reviewer identify exact research-recoverable gaps?

If any answer prevents research, the chapter is checkpointed with an explicit blocker.
Otherwise the same persistent researcher thread receives Prompt 5.

### Step 9 — One targeted gap-fill round, conditional

#### Prompt 5 — exact template

```text
Continue Chapter {chapter_id} for {ruler}, {period_label}, in the same research thread.
This is the one permitted targeted gap-fill round. Do not redo broad discovery and do
not score.

CURRENT ACCEPTED EVIDENCE INDEX
{accepted_chapter_index}

REVIEWER-IDENTIFIED MATERIAL GAPS
{research_recoverable_gaps_json}

EXISTING URL EXCLUSION LIST
{existing_canonical_urls}

TASK
Search directly for the exact listed gaps. Use the requested source types and query
directions. Return no more than {gap_fill_max_new_candidates} new candidate URLs and no
more than {gap_fill_max_new_accepted} newly accepted sources.

Do not add general background, repeated reporting, sibling-chapter material, or sources
that merely reinforce already saturated themes. Prefer direct target-period documents,
strong ruler attribution, outcomes, and missing contrary/favorable evidence. If a gap
cannot be improved, document the exact searches, access barrier, or scarcity reason.

OUTPUT — COMPACT MARKDOWN ONLY

## Gap results
For every reviewer gap ID:
gap ID | resolved / partially_resolved / credible_blocker | concise reason

## Newly accepted evidence
For each accepted source:
SOURCE TEMP ID | gap ID | title | publisher | date | canonical URL | source type |
language | precise claim and locator | temporal fit | attribution basis and limit |
contrary/favorable point | exact lenses | confidence and reason

## Rejected or blocked candidates
candidate URL | gap ID | disposition | short reason

## Queries completed
List actual targeted queries.

Do not repeat the existing ledger. Do not score. Do not ask whether to continue.
```

### Step 10 — Final deterministic gate and reviewer confirmation

The controller merges new accepted evidence, reruns all quality gates, and sends the
updated package back to the same no-search reviewer with this shorter prompt.

#### Prompt 6 — exact template, no-search reviewer continuation

```text
Re-review Chapter {chapter_id} after its single targeted gap-fill round. Do not browse,
add evidence, or score.

PREVIOUS REVIEW
{previous_review_json}

UPDATED QUALITY REPORT
{updated_parent_quality_report}

UPDATED ACCEPTED LEDGER
{updated_accepted_chapter_ledger}

GAP-FILL SEARCH REPORT
{gap_fill_report}

Return strict JSON only:
{
  "chapter_id": "{chapter_id}",
  "decision": "pass" | "credible_blocker_pass" | "fail_manual_review",
  "remaining_material_scope_problems": [],
  "remaining_material_gaps": [],
  "reason": "concise final evidence-quality rationale"
}

Pass only if the concrete record is fair enough for later chapter judging. Use
credible_blocker_pass when the remaining limitation is documented and another similar
search round is unlikely to improve it. Use fail_manual_review when the evidence remains
materially misleading or out of scope. Do not request another research round.
```

### Step 11 — Repeat Steps 3–10 for chapters 1B through 8B

Before each new chapter, the controller checks cumulative cost, context status, and the
global evidence ledger. If the researcher's context is exhausted, it opens a fresh
thread with a compact handoff containing identity, authority baseline, global ledger
index, completed chapters, and remaining chapter—not the full prior transcripts.

### Step 12 — Researcher final self-audit, no broad web search

After all chapters, the persistent researcher receives one compact audit request.

#### Prompt 7 — exact template

```text
All selected chapters for {ruler}, {period_label}, have completed their bounded research
and evidence review. Do not conduct broad new web research and do not score.

GLOBAL LEDGER INDEX
{global_evidence_index}

CHAPTER QUALITY SUMMARIES
{chapter_quality_summaries}

TASK
Audit only for cross-chapter coherence:
1. duplicate underlying documents under different IDs;
2. contradictory claims that require both versions to be preserved;
3. evidence mapped to a chapter outside its substantive scope;
4. country/inherited context incorrectly presented as ruler conduct;
5. post-period material incorrectly presented as target-period evidence;
6. personal-integrity claims without a personal nexus;
7. unresolved global access or closed-information limitations.

OUTPUT — COMPACT MARKDOWN ONLY
## Duplicate-key corrections
## Contradictions to preserve
## Mapping cautions
## Attribution and temporal cautions
## Final unresolved limitations

Reference existing evidence IDs only. Do not add sources, rewrite claims, or score.
```

### Step 13 — Parent global reconciliation; no model call

The controller applies only mechanical duplicate-key merges and flags substantive audit
issues for manual review. It validates:

- one stable evidence record per canonical source-locator-claim unit;
- all chapter/lens mappings reference existing evidence;
- global and chapter counts reconcile;
- client-matrix policy remains excluded;
- every completed query, rejection, blocker, model profile, and thread ID is retained;
- final projected cost and usage are complete or explicitly lower bounds.

### Step 14 — No-search formatting

The formatter receives the reconciled permissive ledger and produces the strict dossier.

#### Prompt 8 — exact template

```text
You are a no-search transcription formatter. Convert the supplied reconciled evidence
ledger into the required dossier schema. Do not browse, infer, improve, combine, expand,
or add facts, URLs, publishers, dates, locators, confidence reasons, attribution, or
question mappings.

ALLOWED QUESTION IDS
{allowed_question_ids}

STRICT OUTPUT SCHEMA
{dossier_json_schema}

RECONCILED EVIDENCE LEDGER
{reconciled_evidence_ledger}

CHAPTER QUALITY AND GAP STATUSES
{chapter_quality_and_gap_statuses}

RULES
- Preserve every stable evidence ID unchanged.
- Preserve one record even when it maps to many questions.
- Retain only explicit allowed question mappings.
- Keep context, temporal limits, attribution limits, contrary material, and gaps.
- Never convert a missing lens into favorable evidence or a zero.
- Omit no accepted record silently; if an accepted record cannot be serialized, return a
  formatting error naming its ID.
- Return strict JSON only.
```

### Step 15 — Parent schema validation and handoff; no model call

The controller validates the strict dossier, coverage mappings, stable IDs, URL fields,
counts, hashes, and chapter statuses. Formatting errors return to the same no-search
formatter; they never trigger new research. The result is ready for separate chapter
judging, which is outside this evidence flow.

## 5. Expected prompt count

For a normal full ruler-year:

- 1 reconnaissance prompt;
- 8 chapter discovery prompts;
- approximately 12–16 inspection prompts, depending on early quality passes;
- 8 initial no-search review prompts;
- approximately 2–4 targeted gap-fill prompts, not automatically eight;
- matching short reviewer confirmations for those gap fills;
- 1 final researcher audit;
- 1 formatter prompt.

Expected total: roughly 31–39 model turns, but only about 21–29 are web-enabled. The
deep 100-document experiment used 77 completed phases and 992 recorded searches. This
hybrid reduces cost by limiting full evidence extraction to promising documents and by
making gap-fill conditional.

## 6. What scripts must enforce rather than prompts

The model must not be trusted to enforce these itself:

1. Exact identity and client-matrix exclusion.
2. Persistent thread ID and context-rollover handoff.
3. Cost warnings and stop threshold.
4. Candidate and accepted URL counts.
5. URL canonicalization, mirrors, and duplicate documents.
6. Global cross-chapter source reuse.
7. Source-domain and event-family concentration.
8. Primary, independent, outcome, contrary, attribution, and scope gates.
9. Maximum one gap-fill round per chapter.
10. Stable evidence IDs and mapping integrity.
11. Atomic checkpointing and resume without repeating paid turns.
12. Token, time, search, timeout, and lower-bound cost profiling.
13. Strict final schema validation.

## 7. Decision points for review before implementation

1. Is $6.50 an acceptable hard stop, or should it be $5.50?
2. Should the normal accepted target be 12 or 15 per chapter?
3. Should domain concentration be a hard 30% gate or a reviewer-visible warning when a
   primary official family legitimately dominates?
4. Is one targeted gap-fill round sufficient, with any remaining material issue sent to
   manual review?
5. Should the no-search reviewer use GPT-5.4-mini, or a cheaper model under the same
   strict JSON contract?

