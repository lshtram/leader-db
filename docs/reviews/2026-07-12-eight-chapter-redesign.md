# Eight-chapter ruler-quality redesign — 2026-07-12

## Decision

The active ruler-quality workflow now uses eight chapter guides and eight
chapter-year judges. The 80 questions remain authoritative, but function as ten
overlapping evidence lenses inside each chapter rather than 80 independent score
products.

For an illustrative 190-ruler year, the target is approximately 190 ruler
evidence sessions plus eight chapter judge sessions. Each judge applies one guide
across all eligible rulers and emits one holistic score per ruler/chapter/year.

## Guides

Eight draft guides live under `docs/methodology/chapter-guides/`. Automated and
independent review confirmed that all `1B.1`–`8B.10` question texts appear
verbatim. Every guide includes:

- one chapter purpose and 1–10 rubric;
- ten evidence lenses with qualitative, non-equal synthesis;
- ruler-attribution and inherited-baseline rules;
- sparse, historical, low-visibility, and closed-information handling;
- a common evidence-item semantic contract;
- a common chapter-judgment output envelope;
- source, bias, confidence, range, and manual-review rules;
- comparative smoke cases.

The 17 prior question guides and the earlier per-question calibration note are
archived under `docs/archive/methodology/`. They do not satisfy readiness.

Independent review initially found underdetermined low-exposure cases in 1B/2B
and inconsistent output envelopes. The guides now use opportunity-adjusted
scoring: limited exposure is not automatic excellence or failure; documented
responsible choices can support a high score, while no discriminating opportunity
widens the range and lowers confidence. All guides now share the same envelope.

## Permissive handoff, strict evidence integrity

The dossier parent now normalizes harmless model-output defects and records
`normalization_warnings`:

- nonsequential or duplicate evidence IDs;
- missing coverage-to-question mappings;
- arbitrary coverage wording;
- evidence attached to a nominal no-evidence status;
- absent advisory collections and extra explanatory fields;
- duplicate coverage rows.

Ambiguous duplicate-ID references are conservatively retained against all
duplicate records and explicitly warned. The input candidate is deep-copied.

The following remain blockers or manual-review conditions: invented/missing
citations, incorrect ruler identity, false period attribution, fabricated claims
or quotations, unsafe discovery, and parent/worker scope mismatch.

## Chapter planning and failure reconciliation

Readiness now accepts `dossier_researcher` or `chapter_judge`. A chapter judge
requires exactly `.1`–`.10` for one chapter and uses the tracked
`ruler-chapter-judge` skill. The CLI planner is
`research jobs plan-chapter-judge --chapter-id <1B-8B>`.

For migration compatibility, the database retains the internal job-type value
`question_judge`; its semantic unit is now one chapter. Pending dependencies block
claim as before. Failed, cancelled, or quarantined dossiers become explicit
`unavailable_dossiers`, are removed from `dossier_job_keys`, and do not deadlock
the chapter batch, including when failure occurs after judge planning.

## Discovery and sparse evidence

Parent discovery now searches four evidence themes rather than one query made of
question IDs: governing strategy/implementation, economy/social welfare,
rights/integrity, and international security. The artifact records a non-blocking
quality summary based on result count and substantive domain diversity. A sparse
packet lowers confidence and requests targeted follow-up; it does not suppress an
obscure or historical ruler merely for limited web visibility.

## Remaining work

- Implement and smoke-test the executable chapter-judge worker and chapter-score
  persistence path against `chapter_scores`.
- Add targeted discovery continuation driven by missing themes rather than a
  fixed number of search results.
- Run a small chapter-level comparative batch before marking any guide active.
- Benchmark a low-cost formatter profile separately from evidence research.
