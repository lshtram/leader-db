# Local-First Researcher Guide

This guide is mandatory for `internet-research` workers on score-bearing manual
questions. It is the durable process reset: inspect local Leaders DB evidence first,
then begin broad web discovery immediately. Discovery is permissive; source quality,
attribution, temporal fit, and locator rules are applied after candidates have been
found and opened, not as search filters.

## Required research order

1. **Inspect the local guides.** Read this guide, every selected chapter guide under
   `docs/methodology/chapter-guides/`, and the cited-evaluation calibration rules
   in `docs/methodology/cited-evaluation-calibration.md` before external research.
2. **Query local DB/artifacts.** Use the structured read-only CLI
   `leaders-db research local-evidence`, local-prior artifacts, and the CLI
   commands below before opening the web. Internet-research workers must not use
   raw `sqlite3`, arbitrary SQL, Python DB snippets, or general shell access.
3. **Profile source confidence.** Read
   [`source-confidence-registry.json`](source-confidence-registry.json) before
   collecting citations. Every citation must include `source_confidence`,
   `source_confidence_reason`, `source_type`, and `final_evidence_use` with one
   of `final_evidence`, `context`, or `discovery_only`. Rate newly discovered
   sources by analogy and explain the rating.
4. **Discover broadly.** Use general, archive-oriented, source-specific, event-specific,
   and local-language searches. Do not limit discovery to a pre-approved source list.
5. **Open, extract, then filter.** Fetch promising underlying pages and documents.
   Prefer primary records, credible NGOs, intergovernmental bodies, scholarship,
   archives, and reputable media for final evidence. Weak sources may remain leads.

If local evidence is absent or incomplete, write that explicitly (for example,
`structured_prior_summary: "no selected local structured evidence found"`). Never
invent a prior from memory.

For a full ruler-period run, use one persistent researcher thread and work through
chapters `1B`–`8B` and their lenses in order. Begin with one broad ruler-period
reconnaissance across all chapters, then inspect and reuse the accumulated ledger
before searching only for each lens's remaining gaps. For each accepted source-claim
unit, preserve a stable
evidence ID, exact reference, main-points summary, useful locator or excerpt, period
and ruler fit, contrary material, and candidate chapter/lens links. Store the item
once and reuse it wherever it is genuinely relevant. After the initial pass, a
no-search evidence reviewer checks every selected chapter and returns all recoverable
gaps to the same thread for at most three rounds. Only after a pass or documented
saturation/access blocker does a separate no-search formatter serialize the dossier.
The formatter may normalize and annotate the ledger but may not turn absent mappings
into `no_evidence_found`; mapped evidence determines coverage, and missing or
unexplained dispositions remain `research_blocked`.

## Search-tool policy for this environment

The researcher owns discovery and may perform as many purposeful, chapter-specific
search iterations as needed for reasonable saturation. Use the search/fetch tools
available in the active Codex execution profile; the project Parallel Search CLI
wrapper is one supported path:

- **Discovery:** `leaders-db research parallel-search --objective ... --query ... --output ... --json`
- **Exact known URLs:** the active profile's URL-opening/fetch capability

Never apply a recent-news freshness filter to historical research. For each chapter,
keep a lightweight candidate log with query, title, URL, and status (`unopened`,
`opened`, `accepted`, `rejected`, or `access_blocked`). Candidate logging does not
require evidence-schema fields. A snippet is never final evidence: open or fetch the
underlying source first. The 5–20 source-claim target is the filtered evidence ledger,
not the size of the candidate pool or the number of results inspected.

Avoid redundant queries, unsafe browser code, and automation that bypasses the active
profile's security policy. Tool choice must not create a fixed query allowance or a
preselected-link packet. Search again when a chapter theme, contrary interpretation,
source type, attribution question, or reviewer-identified gap remains unresolved.

Supported discovery command shape:

```bash
leaders-db research parallel-search \
  --objective "Find cited evidence for <question/country/ruler/year>; prioritize primary, observer, legal, NGO, intergovernmental, and reputable media sources." \
  --query "<country> <ruler> <topic> <year>" \
  --query "<country> <topic> report <year>" \
  --output <approved-output-dir>/<case-id>-parallel-search-01.json \
  --json
```

The wrapper output is a discovery/profile artifact. Read its `results`,
`excerpts`, and `usage` fields, but final evidence citations must cite the
underlying source URLs rather than the wrapper JSON file.

Every shard must emit a `run_profile` object or sibling profile JSON recording
timing, local-artifact reads, local evidence CLI calls, search calls attempted /
succeeded / failed, fetch calls, usage/token fields when exposed, and explicit
`unknown_not_exposed_by_tool` values when raw usage is unavailable.

## Source-confidence profiling

The tracked source-confidence registry is
[`source-confidence-registry.json`](source-confidence-registry.json). It defines
default confidence levels, allowed uses, caveats, and claim-type overrides. Apply it
to every citation and add these fields next to the cited URL/title/quote:

```json
{
  "source_confidence": "medium_high",
  "source_confidence_reason": "Reuters is a reputable wire source used for dated event chronology; primary legal text was not available in this excerpt.",
  "source_type": "media",
  "final_evidence_use": "final_evidence"
}
```

Source-diversity requirements:

- Low or very-low confidence sources may not be sole support for a score-bearing
  claim.
- Grokipedia is `very_low` and `discovery_only`.
- Wikipedia is `medium_high` mainly for orientation/basic facts and source
  discovery; avoid it as sole support for manipulation/entrenchment claims.
- Official government sites are conditional: `medium_low` for self-serving claims
  about fairness, legality, restraint, or legitimacy, but can be `medium_high` or
  `high` for formal facts such as legal texts, dates, certified results, office
  records, and judgments.
- For every material claim, prefer at least two independent source types when
  available. If one source type dominates, explain that in the source-mix note.

## Local DB and artifact inventory

The normal SQLite path is:

```text
data/catalog/leaders_db.sqlite
```

Current local evidence layers include:

- `country_year_facts`: the preferred harmonized country-year fact table. It
  stores selected values, candidates, source slugs, source observation IDs,
  confidence/quality fields, warnings, rationale, and review prompts.
- `normalized_observations`: source-adapter observations loaded from local raw
  files. Use this for source-level rows when `country_year_facts` is too compact.
- `source_observations`: older audit-backbone table; it may be present but is not
  the primary current fact path.
- `countries` and `country_years`: ISO3 country names and included/excluded
  country-year scope decisions.
- `ruler_identity_adjudications`: the principal-ruler/adjudication layer. The
  selected principal ruler is also published in `country_year_facts` as
  `field_key = 'principal_ruler'` when available.
- `research_question_answers` and `research_answer_evidence_links`: persisted
  D24-D27 answers and their evidence links. Existing answers are context, not a
  substitute for the current chapter guide.

Local D11-D17 fact families currently represented through `country_year_facts`
include:

- **D11 political freedom:** V-Dem democracy/civil-liberty/suffrage/rule-of-law /
  expression/association concepts, RSF press freedom, and Freedom House political
  rights / civil liberties numeric ratings; EIU/BTI remain partial.
- **D12 domestic safety:** V-Dem physical-integrity/liberty/civil-society /
  extrajudicial-killing concepts, UCDP one-sided violence, CIRIGHTS, and PTS.
- **D13 international conflict:** UCDP state-based and internationalized conflict
  event/fatality facts; aggressor/proxy role remains future/manual.
- **D14 military:** SIPRI military expenditure constant USD, per capita, share of
  GDP, and share of government spending.
- **D15 corruption/integrity:** V-Dem corruption concepts, Transparency CPI, and
  WGI control of corruption.
- **D16 governance capacity:** V-Dem accountability/constraints/multiparty/regime
  concepts, WGI voice/rule-of-law/effectiveness/regulatory quality, and partial
  BTI governance/status/democracy-status concepts.
- **D17 nuclear risk:** FAS arsenal-count facts; treaty/doctrine/threat evidence
  remains future/manual/web.

Local facts are incomplete. Missing local facts are a finding to report, not a
reason to re-fetch local structured datasets from the web.

## Full-ruler local evidence package

Before a full `1B`–`8B` Luna researcher starts, the parent builds one
question-provenance artifact for every selected lens from `country_year_facts` and
then inlines a deduplicated `ruler_local_prior_package_v1`. The trusted raw artifact
retains all per-lens statuses and hashes; the prompt package stores each identical
fact once with stable `LF###` IDs, its exact source observation IDs, a valid
`local-prior:<methodology-id>` locator, and candidate chapter/lens links.

The active `local_structured_prior_v2` routing is:

| Chapter | Local fact families | Required interpretation boundary |
|---|---|---|
| 1B | FAS nuclear inventory, military stockpile, deployed/nondeployed warheads | Capability context only; absence is not proof of non-nuclear restraint or responsible conduct. |
| 2B | UCDP state/internationalized conflict; SIPRI military expenditure | Country exposure and resource context; establish ruler role, aggression/defense, and alternatives separately. |
| 3B | CIRIGHTS, PTS, UCDP one-sided violence, V-Dem physical integrity/repression | Country-year safety/repression baseline; narrative evidence must establish ruler/control attribution. |
| 4B | V-Dem, Freedom House, RSF, WGI, BTI political-freedom/governance facts | Institutional baseline; do not convert country ratings automatically into personal conduct. |
| 5B | GDP/GNI per capita, total GDP, population, BTI status | Economic level/scale context; distribution, shocks, causal credit, and policy implementation require additional evidence. |
| 6B | HDI, life expectancy, mortality, immunization, schooling, GNI per capita | Welfare outcomes/baselines; respect source-year warnings, lags, inherited trends, and attribution. |
| 7B | WGI/V-Dem/CPI corruption, accountability, and rule-of-law facts | Institutional integrity context; never infer personal honesty, enrichment, or deception from country indicators alone. |
| 8B | WGI effectiveness/regulatory quality, BTI governance, accountability/rule of law | Inherited state-capacity context; not proof of the ruler's program, execution, adaptation, or causal contribution. |

`candidate_methodology_ids` are routing hints rather than automatic evidence
mappings. The researcher must first audit the local package by chapter, distinguish
country/inherited context from ruler-attributable conduct, and state which fact IDs
are retained, contextual, or unused. It then uses approved internet discovery only
for missing narrative, attribution, contrary evidence, decisions, implementation,
and outcomes. A missing database row is never interpreted as a zero event or a
favorable condition.

The compact package preserves a disposition for every methodology lens. Repeated
missingness reasons and recommended instruction sets are stored once and referenced
by ID. Treat `error` as a blocking local-input failure that must remain visible in
the handoff; internet material must not disguise a database or extraction failure.

## Approved direct local DB access

The approved direct local DB access path for `internet-research` is the
structured, read-only local evidence command. It queries bounded
methodology/year/ISO3 scopes through the existing local structured-prior builder,
excludes client-matrix source slugs, and returns artifact-shaped statuses
(`evidence_found`, `no_evidence_found`, `not_applicable`, `error`). It does not
accept user SQL.

Codex workers use the tracked researcher skill and the permissions of their active
execution profile. The historical OpenCode permission template is compatibility
material only and is not the normative research workflow. Never depend on an ignored,
machine-local OpenCode file to define researcher search scope.

```bash
leaders-db research local-evidence \
  --methodology-id 4B.2 \
  --year 2020 \
  --iso3 USA \
  --iso3 CAN \
  --json
```

If no `--iso3` is provided, the command fails with an artifact-shaped error
instead of dumping the database. For multiple ISO3s, JSON output contains
`records` plus `status_counts`.

## SQL examples for parent/debug sessions only

The SQL below documents the underlying tables for maintainers and parent/debug
sessions. It is **not** an approved `internet-research` subagent path.

Use read-only queries. With SQLite:

```bash
sqlite3 data/catalog/leaders_db.sqlite "SELECT COUNT(*) FROM country_year_facts;"
```

Country and scope check:

```sql
SELECT c.iso3, c.country_name, cy.year, cy.included_in_project, cy.inclusion_reason
FROM country_years cy
JOIN countries c ON c.id = cy.country_id
WHERE c.iso3 = 'USA' AND cy.year = 2020;
```

Local harmonized facts for a case:

```sql
SELECT cyf.field_key, cyf.selected_value_text, cyf.selected_value_number,
       cyf.confidence_score, cyf.source_slugs_json, cyf.rationale
FROM country_year_facts cyf
JOIN countries c ON c.id = cyf.country_id
WHERE c.iso3 = 'USA' AND cyf.year = 2020
ORDER BY cyf.field_key;
```

Principal ruler/adjudication context:

```sql
SELECT c.iso3, ria.year, ria.selected_leader_name, ria.classification,
       ria.review_status, ria.rationale, ria.source_slugs_json
FROM ruler_identity_adjudications ria
JOIN countries c ON c.id = ria.country_id
WHERE c.iso3 = 'USA' AND ria.year = 2020;
```

Source-level observations when a fact needs traceability:

```sql
SELECT source_slug, observation_family, indicator_code, value_json,
       country_code, year, raw_locator_json
FROM normalized_observations
WHERE country_code = 'USA' AND year = 2020
ORDER BY source_slug, indicator_code
LIMIT 100;
```

Previously persisted answers for QA/context:

```sql
SELECT question_id, year, iso3, ruler_name, score_1_to_10,
       confidence_score, coverage_status, answer_text
FROM research_question_answers
WHERE iso3 = 'USA' AND year = 2020
ORDER BY question_id;
```

Legacy source observations, if needed:

```sql
SELECT s.source_name, so.variable_name, so.raw_value, so.normalized_value, so.year
FROM source_observations so
JOIN sources s ON s.id = so.source_id
JOIN countries c ON c.id = so.country_id
WHERE c.iso3 = 'USA' AND so.year = 2020
LIMIT 100;
```

## CLI commands researchers may use

Direct safe local evidence lookup:

```bash
leaders-db research local-evidence \
  --methodology-id 4B.2 \
  --year 2020 \
  --iso3 USA \
  --json
```

Build one local-prior artifact:

```bash
leaders-db research build-local-prior \
  --methodology-id 4B.2 \
  --year 2020 \
  --iso3 USA \
  --leader "Donald Trump" \
  --output tmp/4b2-usa-2020-local-prior.json \
  --json
```

Build a clean all-scope local package with 10-case shards:

```bash
leaders-db research build-local-prior-slice \
  --methodology-id 4B.2 \
  --year 2020 \
  --output-dir data/outputs/research/4b2_2020_local_priors \
  --shard-size 10 \
  --json
```

Inspect persisted answers:

```bash
leaders-db research list-answers --question-id 4B.2 --year 2020 --output json
leaders-db research list-answers --year 2020 --iso3 USA --output csv
```

Print output contract and starter record:

```bash
leaders-db research cited-evaluation-schema
leaders-db research cited-evaluation-template \
  --methodology-id 4B.2 \
  --year 2020 \
  --iso3 USA \
  --country-name "United States" \
  --leader-name "Donald Trump" \
  --period-label 2020
```

Validate a shard output; do not trust a textual success report alone:

```bash
leaders-db research validate-shard-output \
  --status data/outputs/research/4b2_2020_local_priors/shard-001-status.json \
  --input data/outputs/research/4b2_2020_local_priors/shard-001-input.json \
  --output data/outputs/research/4b2_2020_local_priors/shard-001-output.json \
  --expected-record-count 10 \
  --max-expected-minutes 30 \
  --max-progress-stale-minutes 10 \
  --json
```

Summarize local ruler-period evidence when a question needs period context:

```bash
leaders-db evidence summarize-ruler-period \
  --country USA \
  --leader "Donald Trump" \
  --start-year 2017 \
  --end-year 2020 \
  --concept concept.gdp_per_capita \
  --output json
```

## Structured-data no-refetch rule

Local structured datasets such as Freedom House, V-Dem, RSF, WGI, BTI, CPI, PTS,
CIRIGHTS, UCDP, SIPRI, FAS, and similar locally ingested sources must **not** be
re-fetched from the web for numeric or structured priors. Use the local DB/artifact
for those values. External pages are allowed only for narrative, ruler-specific,
legal, election, media, or contradiction-resolution detail that the local facts do
not contain.

## Preferred external sources for 4B questions

For electoral contestability, entrenchment, and manipulation questions, prefer:

1. Election observer reports: OSCE/ODIHR, EU, OAS, AU, Commonwealth, Carter Center,
   credible regional observer missions.
2. Election commissions and official results/procedure documents.
3. Courts, constitutional texts, electoral-law amendments, legal dockets, and
   legislative records.
4. Official sanctions, parliamentary/legislative, or intergovernmental reports.
5. HRW, Amnesty, International IDEA, IFES, ICG, local credible NGOs, and other
   reputable civil-society reports.
6. Reputable local/international media as secondary sources for chronology,
   attribution, and live controversy.

Separate local structured priors from external narrative claims in your output.
Preserve contrary evidence and role caveats, especially for ceremonial leaders,
coalitions, de facto rulers, and closed information environments.
