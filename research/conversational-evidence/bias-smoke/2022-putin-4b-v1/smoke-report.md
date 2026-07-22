# Putin 2022 Chapter 4B bias-contract smoke report

## Scope

This is the first live producer-to-judge test of the mandatory evidence-environment
and judgment-bias contracts. It used a copy-on-write catalog, collected and reviewed
Putin 2022 evidence for all ten Chapter 4B lenses, formatted a new dossier, and replaced
only Putin in the preserved lean-v4 20-ruler comparative batch. Production data and the
preserved release were not modified.

## Result

- The validated dossier contains 55 evidence records, 160 lens mappings, ten coverage
  records, and all twelve evidence-environment fields. The environment assessment cites
  23 dossier evidence IDs.
- The comparative judge completed all 20 evaluations in 408 seconds for an estimated
  $0.27. Putin remained at 1.0 with 94 confidence and a 1.0-1.5 plausible range. The
  preserved result was 1.0, 95 confidence, and the same range, so score drift was zero.
- Putin's judgment contains three cited material-bias findings, explicit effects on
  interpretation and confidence/range, and affirmative report-volume and no-blanket-
  regime-correction checks.
- Nine lenses are supported. 4B.8 remains explicitly weak because no transfer event
  occurred in 2022; absence was treated as a blocker, not adverse or favorable conduct.

## Full defect demonstrations

The first formatter candidate contained 55 usable cited records but eight contextual
records lacked exact lens mappings. The former consumer rejected the whole candidate.
The corrected consumer now retains exact mappings first, infers only auditable local or
coverage mappings, and routes remaining records as advisory context without inventing
substantive lens relevance. Formatter-only recovery then produced the valid dossier
without paying for or repeating research.

The comparative judge returned `"4B.8 direct transfer event"` in
`missing_or_weak_lenses`. The former normalization accepted only exact strings such as
`4B.8` and silently erased the useful gap. It now recovers a leading valid methodology
ID from descriptive text. Revalidation restores `4B.8` with no model rerun.

The saved-judgment repair helper also assumed that every run contained all eight
chapters. This one-chapter pilot therefore raised `FileNotFoundError` for `1B.json`.
It now repairs the chapter manifests actually present and still validates every output
against its supplied projections.

## Limits and promotion decision

The other 19 rulers use preserved projections whose evidence environments were never
collected; they are explicitly marked unassessed. This is sufficient for a controlled
Putin substitution test but not a cohort-level bias comparison. The result validates
feasibility and transmission, not the complete methodology. The next increment is
structured no-search reviewer enforcement of balanced search, silence/visibility,
duplication, allegations/findings, official-claim checking, denominators, authority,
baseline, shocks, and missing source types before an eight-chapter Putin run.
