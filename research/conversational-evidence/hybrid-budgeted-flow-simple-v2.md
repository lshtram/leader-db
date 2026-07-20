# Simple budgeted GPT-5.4-mini research flow — v2

Status: revised proposal for review. It does not replace or modify the current flow.

The original, more detailed proposal remains unchanged in
`hybrid-budgeted-flow-proposal.md`.

## 1. Review of the first proposal

The first proposal had the right controls but too much conversation overhead.

| Original element | Decision | Reason |
|---|---|---|
| Separate reconnaissance | Keep, simplify | A shared authority and event baseline prevents repeated research. |
| Separate chapter discovery prompt | Remove as a separate turn | Discovery and evidence selection are naturally one research task. |
| One or two inspection prompts per chapter | Remove | This repeated the candidate inventory and increased output and context. |
| Deterministic URL and count checks | Keep | Scripts are better than prompts at counting and deduplication. |
| Reviewer after every chapter | Replace with one full-ruler review | The reviewer can compare all eight chapters and detect cross-chapter contamination better. |
| Gap-fill prompt for every weak chapter | Replace with one conditional grouped prompt | Only material, recoverable gaps should trigger more paid research. |
| Reviewer confirmation per gap-filled chapter | Replace with one combined re-review | Fewer turns and better cross-chapter consistency. |
| Separate researcher self-audit | Remove | It duplicated the evidence review. |
| No-search formatter | Keep, simplify | Research and serialization should remain separate. |

The revised design uses four prompt templates:

1. ruler reconnaissance;
2. chapter research, repeated for the eight chapters;
3. full-ruler no-search evidence review, used once and optionally once more;
4. one conditional grouped gap-fill;
5. final no-search formatting.

There are five functional prompt types if formatting is counted. A normal run uses
11 model turns: 1 reconnaissance, 8 chapter turns, 1 review, and 1 formatting turn.
If material gaps are recoverable, it uses 13 turns: one gap-fill and one re-review are
added. Only 9 turns are normally web-enabled; 10 when gap-fill is needed.

## 2. Research targets

These are goals, not reasons to pad the evidence:

- 120–180 distinct accepted URLs for the complete ruler-year;
- normally 10–18 accepted source-claim units per chapter, with about 12–15 preferred;
- roughly 25–40 distinct documents considered per chapter;
- one chapter research turn;
- at most one grouped gap-fill turn for the entire ruler;
- target cost: $4–6 per ruler;
- hard resumable stop before starting a new turn if projected cost exceeds the configured
  ceiling.

A source may support several lenses and chapters. It is stored once and reused. Missing
evidence lowers confidence or remains a documented gap; it is never replaced with filler.

## 3. What the scripts control

The scripts should be strict about mechanics and light about research judgment.

They control:

- locked ruler identity and period;
- client-matrix exclusion;
- local-prior validation;
- one persistent researcher thread;
- chapter order;
- atomic checkpoints and resume;
- URL canonicalization and duplicate removal;
- stable evidence IDs and cross-chapter reuse;
- accepted-source, domain, and lens counts;
- model usage, elapsed time, searches, and estimated cost;
- one optional gap-fill maximum;
- strict final schema validation.

They should report, but not mechanically reject, a chapter for:

- fewer than 10 accepted sources;
- fewer than five domains;
- more than 35% of accepted sources from one domain;
- missing primary, independent, outcome, contrary, or ruler-attribution evidence;
- a lens with no concrete evidence or explicit gap.

The no-search reviewer decides whether those warnings are material. This avoids turning
reasonable source concentration or genuine scarcity into arbitrary failure.

## 4. Controlled-run isolation and preservation

The experiment must not change the current production or 2024 collector flow.

Before implementation:

1. Record `git status` and hashes of every existing collector prompt, config, runner,
   formatter, and result schema.
2. Save a baseline manifest under the new experiment folder.
3. Leave existing prompts and scripts in place; do not edit them for the test.
4. Add the experimental prompts, config, runner, session state, and results under a new
   run key and directory.
5. Import stable shared utilities only where this does not alter their behavior.
6. Do not commit over or delete the earlier prompt tests or deep-run artifacts.
7. If the experiment is rejected, removing the new experiment directory restores the
   previous behavior without a code rollback.
8. Replacement of the main flow requires a separate comparison and explicit decision.

Suggested experimental locations:

```text
src/leaders_db/conversational_evidence/hybrid_experiment/
research/conversational-evidence/hybrid-experiment/<ruler>-<year>/
```

## 5. Step-by-step flow

### Step 0 — Prepare the run; no model prompt

The parent validates identity and local priors, creates the baseline manifest, snapshots
the experimental configuration, and initializes the global source ledger and profile.
If identity or local readiness fails, the run does not start.

### Step 1 — Ruler reconnaissance; one web-enabled prompt

This establishes reusable authority, context, and search directions. It should be brief.

#### Prompt 1 — reconnaissance

```text
Research {ruler}, ruler of {country}, during {period_label}.

This is evidence research for eight later chapters. Do not score the ruler.

Start with the local facts below. Do not search again for facts already supplied locally.
The client matrix is not evidence and must not be used.

LOCAL FACTS
{local_prior_summary}

Build a short reusable baseline:

1. Confirm the ruler's office, authority, and important constraints.
2. Identify the major events and inherited conditions of the period.
3. Identify the best primary, independent, local-language, favorable, and critical source
   families for later chapter research.
4. Note important access or attribution problems.

Keep only the most useful cross-chapter sources, normally no more than 12.

For each retained source give:
- title, publisher, date, and direct URL;
- the precise fact it supports;
- whether it describes the target period, inherited context, or later context;
- how it can fairly be attributed to the ruler;
- important limitations or contrary points.

Finish with a compact event map and source plan for Chapters 1B–8B.
Do not score. Do not create 80 separate lens answers.
```

### Step 2 — Parent stores the baseline; no model prompt

The parent canonicalizes URLs, assigns stable IDs, stores each source once, and builds a
compact index for reuse. It records usage and checkpoints the persistent thread ID.

### Steps 3–10 — Research Chapters 1B through 8B; one prompt per chapter

The same prompt is used eight times in guide order. Discovery, opening documents,
selection, and summarization happen in one coherent research turn.

#### Prompt 2 — chapter research

```text
Now research Chapter {chapter_id} for {ruler} during {period_label}.
Continue in the same research thread. Do not score.

CHAPTER GUIDE
{complete_chapter_guide}

TEN LENSES
{chapter_questions}

RELEVANT LOCAL FACTS
{chapter_local_priors}

EXISTING REUSABLE EVIDENCE
{relevant_global_evidence_index}

Research the chapter as a whole, not as ten isolated questions.

- Reuse existing evidence when it genuinely applies.
- Search broadly enough to consider roughly 25–40 distinct documents.
- Open the most promising documents and retain only the best non-duplicative evidence,
  normally 10–18 sources.
- Prefer original and primary sources where available, but include strong independent
  monitoring, scholarship, reputable reporting, and relevant local-language material.
- Include meaningful favorable or contrary evidence.
- Distinguish ruler conduct from inherited conditions and general country context.
- Explain attribution. Personal-integrity claims require a personal connection.
- Do not pad weak lenses or repeat the same event through many publishers.

Return a concise research note with these sections:

## Reused evidence
List existing evidence IDs and the exact chapter lenses they inform.

## New evidence
For each retained source give:
- title, publisher, date, and direct URL;
- a precise claim summary and useful locator or short excerpt;
- source type and why it is credible;
- temporal fit;
- ruler attribution and its limits;
- favorable or contrary points;
- exact Chapter {chapter_id} lenses.

## Search and rejection summary
State approximately how many distinct documents were considered. Summarize duplicate,
irrelevant, weak, blocked, and out-of-period removals without listing every rejected row.

## Remaining gaps
Name only specific gaps that could matter to a later chapter judgment. Say whether more
search is likely to help.

Do not repeat previously stored evidence in full. Do not score.
```

After each chapter, the parent extracts and deduplicates URLs, assigns global IDs, checks
the mechanical warnings, updates the compact global evidence index, records cost, and
checkpoints. It does not ask the model to restate the chapter.

### Step 11 — Full-ruler evidence review; one no-search prompt

The reviewer sees all eight chapters together. This is more effective than eight small
reviews because it can detect duplicated evidence and thematic contamination.

#### Prompt 3 — combined no-search evidence review

```text
Review the complete evidence package for {ruler}, {period_label}.

Do not browse, add evidence, rewrite claims, or score the ruler.

For every chapter, decide whether the evidence can fairly present:
- the chapter-relevant governing conduct;
- important outcomes and contrary evidence;
- ruler attribution;
- the strongest favorable and adverse interpretations;
- material remaining uncertainty.

Pay special attention to:
- evidence that belongs in a different chapter;
- many sources repeating one event or publisher family;
- general country context presented as ruler conduct;
- allegations presented as established facts;
- post-period material presented as target-period evidence;
- impressive source counts hiding weak discriminating lenses;
- personal-integrity claims without a personal connection.

CHAPTER GUIDES
{all_selected_chapter_guides}

PARENT QUALITY SUMMARY
{all_chapter_quality_warnings}

EVIDENCE PACKAGE
{compact_full_ruler_evidence_package}

Return JSON only:
{
  "overall_decision": "pass" | "targeted_follow_up" | "manual_review",
  "chapters": [
    {
      "chapter_id": "1B",
      "decision": "pass" | "targeted_follow_up" | "credible_gap" | "manual_review",
      "remove_or_contextualize": [
        {"evidence_id": "ID", "reason": "specific reason"}
      ],
      "material_gaps": [
        {
          "gap": "specific missing evidence",
          "lenses": ["1B.x"],
          "best_source_or_query_direction": "specific direction",
          "why_it_matters": "short explanation"
        }
      ],
      "reason": "short assessment"
    }
  ]
}

Request targeted follow-up only for a material gap that one focused research turn is
likely to improve. Do not request generic additional sources.
```

### Step 12 — Optional grouped follow-up; at most one web-enabled prompt

This prompt is skipped when the reviewer passes the package or finds only credible
nonrecoverable gaps. If used, it sends all recoverable gaps back to the same researcher
in one turn.

#### Prompt 4 — targeted follow-up

```text
Address the material evidence gaps below for {ruler}, {period_label}.
Continue in the same research thread. This is the only follow-up research round.
Do not score and do not repeat broad chapter research.

CURRENT EVIDENCE INDEX
{global_evidence_index}

REVIEWER GAPS
{recoverable_reviewer_gaps}

Search only for these gaps. Prefer the suggested source directions, direct target-period
evidence, clear ruler attribution, outcomes, and missing favorable or contrary evidence.
Do not add sources to themes that are already well covered.

For each gap:

1. Say resolved, partly resolved, or not recoverable.
2. For each new retained source give title, publisher, date, direct URL, precise claim and
   locator, temporal fit, attribution and limits, contrary points, and exact chapter
   lenses.
3. Briefly list unsuccessful query directions or access blockers.

Keep the answer concise. Store one source once even if it helps several gaps or chapters.
Do not score.
```

### Step 13 — Optional combined re-review; one no-search prompt

When follow-up occurred, the same reviewer receives the updated package using Prompt 3
with this short prefix:

```text
This is the final review after the single allowed targeted follow-up. Apply the same
review criteria. The only allowed overall decisions are pass or manual_review. Do not
request more research.
```

### Step 14 — Parent reconciliation; no model prompt

The parent applies mechanical deduplication and reviewer-directed removals or context
flags. It checks that IDs, URLs, mappings, counts, and chapter decisions reconcile. It
does not invent evidence to repair gaps.

### Step 15 — No-search formatting; one prompt

#### Prompt 5 — formatter

```text
Convert the evidence package below into the required dossier JSON.

Do not browse, add facts, improve summaries, infer mappings, or score the ruler.
Preserve every evidence ID, URL, locator, temporal limit, attribution limit, contrary
point, explicit lens mapping, and documented gap.

Use only these question IDs:
{allowed_question_ids}

JSON SCHEMA
{dossier_json_schema}

EVIDENCE PACKAGE
{reconciled_evidence_package}

If an accepted record cannot be represented without invention, return a formatting error
that names its evidence ID. Return JSON only.
```

The parent validates the JSON. Formatting corrections reuse the same no-search formatter
and never restart research.

## 6. Why this should be better

Compared with the first proposal, this version:

- reduces normal turns from roughly 31–39 to 11;
- reduces web-enabled turns to nine in the normal case;
- lets the researcher complete one coherent chapter instead of repeatedly switching
  between discovery, inspection, selection, and correction;
- stops asking the model to reproduce candidate ledgers and deterministic calculations;
- reviews all chapters together, improving detection of cross-chapter contamination;
- permits only one focused follow-up for the entire ruler;
- keeps prompts short enough that the chapter guide and evidence remain the focus;
- trusts the researcher on search strategy while retaining parent-side audit and budget
  controls.

## 7. Risks to test in the controlled run

The simpler design is intentionally less prescriptive, so the controlled comparison must
measure whether GPT-5.4-mini:

1. actually considers roughly 25–40 documents in one chapter turn;
2. opens documents before accepting them;
3. returns 10–18 useful sources without padding;
4. keeps chapter scope clean, especially 7B versus 8B;
5. reports meaningful favorable and contrary evidence;
6. produces enough locator and attribution detail for formatting;
7. stays within the intended cost range;
8. avoids repeating the same evidence across chapter outputs.

If those fail, the response should be one narrow control added to the parent or prompt,
not a return to many micro-prompts.

