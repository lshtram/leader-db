# Frozen 20-ruler Luna dossier and chapter-judge run — 2026-07-14

## Scope and outcome

The production-shaped workflow completed for the frozen `2020-diverse-20` cohort,
SHA-256 `9fb504ec57209f1c5950aa680930d181224bb68aaa42931fb6aa306da00de2ce`.
Every ruler-year received one local-first Luna research session across all 80 lenses,
an independent evidence review, at most one bounded continuation, and a separate
formatter. All 20 dossier jobs completed.

The final dossiers contain 444 retained evidence records, of which 419 (94.4%) are
visible to chapter projections, 3,841 evidence-to-lens mappings, and 1,308 coverage
rows with direct references. Each dossier has all 80 terminal coverage rows and at
least half of its retained evidence mapped. Evidence counts range from 12 to 39 per
ruler; sparse chapters and countries remain valid rather than being padded.

Eight Luna judges then each applied one common chapter meter across the same 20-ruler
cohort. The database contains 160 run-scoped chapter-score rows. Of these, 153 have
numeric scores and seven are explicit insufficient-evidence results: Pashinyan in
4B-8B, Orban in 5B, and Merkel in 8B. These are evidence-specific nulls, not software
failures. The draft guides remain in smoke status pending substantive review of score
ordering and 122 manual-review flags.

## Chapter result summary

| Chapter | Scored | Null | Score range | Mean score | Mean confidence |
|---|---:|---:|---:|---:|---:|
| 1B | 20 | 0 | 2.5-6.5 | 5.15 | 38.2 |
| 2B | 20 | 0 | 3.0-7.4 | 5.10 | 43.0 |
| 3B | 20 | 0 | 1.5-9.0 | 4.47 | 67.3 |
| 4B | 19 | 1 | 1.2-9.0 | 4.62 | 74.0 |
| 5B | 18 | 2 | 2.5-6.5 | 4.69 | 49.0 |
| 6B | 19 | 1 | 2.0-7.5 | 4.24 | 49.6 |
| 7B | 19 | 1 | 1.5-7.5 | 4.45 | 58.8 |
| 8B | 18 | 2 | 3.5-8.0 | 5.33 | 54.9 |

## Live failure findings corrected

The run exposed several production-only failure modes and corrected them with focused
tests, Ruff checks, and independent review:

1. Parent-approved URL handling now admits exact HTTP(S) locators embedded in trusted
   parent results and numeric content-ID variants used by open-only retrieval, while
   child search remains prohibited and final citations remain source-boundary checked.
2. Per-chapter discovery checkpoints are checksum verified and reusable. One
   exception-backed indeterminate chapter call may retry; completed chapters are not
   purchased again and crash-like ambiguous calls still block.
3. Completed research, review, continuation, and formatter artifacts are recoverable.
   Invalid completed jobs can be audited, invalidated, and granted one explicit retry.
4. Formatter publication requires a substantive reviewed yield and makes at least half
   of retained evidence visible to judges. Exact `local-prior:<lens>` locators receive
   deterministic contextual mappings. Formatters are told never to concatenate IDs and
   to map every retained item at least once.
5. Judge projections are embedded directly in the prompt after parent-side hashing and
   context estimation. This removed dependence on an intermittently failing `bwrap`
   filesystem sandbox. A multi-ruler all-null result can no longer publish.
6. Supported-and-weak lens overlap is normalized without losing the weakness note.
   Out-of-projection decisive references are only removed, never guessed or replaced;
   affected judgments are forced to manual review and retain an audit note.
7. A uniformly fractional 0-1 confidence batch is normalized to the canonical 0-100
   scale. Mixed, all-zero, all-one, nonnumeric, or out-of-range batches are untouched.

## Usage and cost

The 20 final dossier artifacts record 51,752,165 combined tokens and a
PAYG-equivalent range of **$18.808036-$35.503421**, including **$0.90** for parent
search. The eight final judge artifacts record 2,219,225 tokens and
**$2.512721-$3.635629**. Combined recorded artifacts total 53,971,390 tokens and
**$21.320757-$39.139050**.

These figures include policy-approved failed attempts when the worker could recover
their exposed usage, but should not be treated as an invoice. Actual Codex subscription
billing is not exposed, and provider/orchestration failures may have overhead that is
not represented in the final artifact counters.

## Readiness conclusion

The intended topology is now proven end to end: one reusable evidence dossier per
ruler-period, followed by one common-meter judge per chapter-year cohort. The next
large-run gate is methodological rather than orchestration readiness: review the
comparative rankings, inspect manual-review cases and nulls, refine draft guide anchors,
and decide whether Luna remains the judge model or whether a higher-quality model should
rejudge selected chapters while reusing the same dossiers.
