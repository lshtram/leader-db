# Methodology Gate — 2020 Diverse-20

Date: 2026-07-14

## Decision

The completed Luna research and eight-judge smoke run validates the execution
topology, but its v1 chapter scores are not production-ready. Preserve all 160
results as immutable smoke artifacts. Do not promote them or silently overwrite
them. The guides advance to revised v2 drafts and require targeted evidence repair
plus rejudgment.

## Audit scope

Two independent agents reviewed all chapter orderings, rationales, 122 manual-review
flags, and seven nulls against the common calibration contract and exact guides.
They separated evidence/projection shortages from judge or rubric defects.

## Cross-chapter findings

1. Several judges assigned fine-grained midpoint scores from country baselines,
   generic priors, silence, or non-exposure without ruler-attributed discriminating
   evidence.
2. Evidence leaked across chapter boundaries: domestic repression influenced 2B,
   generic policy/election matters influenced 3B, and repression/freedom substituted
   for personal integrity in 7B.
3. High inherited institutional or welfare baselines were sometimes credited as
   ruler performance without enough target-period contribution.
4. `manual_review_required` was used as a generic low-confidence flag. Chapters 1B,
   2B, 5B, 7B, and 8B flagged every ruler, making the queue operationally useless.
5. Decimal scores such as 3.3 and 8.2 overstated the precision supported by sparse
   dossiers.

## Chapter decisions

| Chapter | Decision | Principal correction |
|---|---|---|
| 1B | Rejudge | Classify exposure; null unknown gaps; require direct risk-bearing choices for positive anchors. |
| 2B | Rejudge | Apply a conflict/exposure gate and exclude purely domestic repression. |
| 3B | Rejudge | Require a physical-safety nexus and constrain inherited-baseline credit. |
| 4B | Rejudge after projection checks | Preserve the strong core rubric; require direct high-anchor contribution and reject empty projections. |
| 5B | Rejudge | Do not infer low performance from poverty/opacity; require policy plus implementation/outcome evidence outside the middle band. |
| 6B | Rejudge | Treat wholly contextual cases consistently as null; require attributable welfare action or outcome. |
| 7B | Full rejudge required; v1 invalid | Admit national institutions/repression only with a direct personal-integrity nexus. |
| 8B | Rejudge | Freeze a broad program portfolio; cap planning/control without implementation and outcomes. |

## Evidence and projection repairs before v2 judges

- Continue Pashinyan research for 4B–8B; the repeated nulls reflect a systemic dossier
  gap rather than a reason to weaken the rubrics.
- Repair Merkel's 8B projection, which exposed no usable evidence despite narrative
  and local-prior references.
- Fill direct international-conflict/authority evidence for Pashinyan, Erdogan, and
  Salman in 2B.
- Improve direct US physical-integrity evidence for 3B.
- Recheck the zero-evidence 1B cases, notably Pinera and Orban, and classify actual
  exposure rather than assigning an assumed midpoint.
- Recheck empty or contextual-only 5B/6B cases, particularly Orban, Modi, Pashinyan,
  and the low anchors whose rationales did not establish dominant harmful choices.

## Manual-review semantics

The v2 common contract reserves release-blocking review for identity/projection
integrity, decisive-source disputes, attribution uncertainty capable of moving the
score at least one point, recoverable nulls, and material calibration inconsistency.
Routine thinness and ordinary caveats lower confidence and widen ranges instead.

## Activation gate

The next run should not repeat all ruler research. Repair the named dossier/projection
gaps, then create new guide-hash-bound v2 judge jobs for all eight chapters. Accept v2
only if:

- every non-null score rests on ruler-attributed chapter-discriminating evidence;
- chapter-boundary contamination is absent in a substantive sample and all extremes;
- high and low anchors meet their evidence floors;
- null handling is consistent across evidentially comparable cases;
- manual-review flags are selective and use a stable reason type;
- adjacent ordering and confidence/range are independently reviewed.
