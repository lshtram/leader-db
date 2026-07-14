# Cited Evaluation Calibration

This note defines the first common-meter rules for cited/manual ruler-quality
evaluations. It is not a replacement for structured source scoring. It applies
when a human or `internet-research` subagent produces cited qualitative records
for questions whose registry evidence strategy is `internet_manual`.

Every score-bearing manual/internet question should also have a question-specific
guide under `docs/methodology/question-guides/`. Use
[`question-guides/template.md`](question-guides/template.md) for new questions and
follow the vertical-slice workflow in
[`question-guides/readme.md`](question-guides/readme.md) before scaling a question.

## Separation of roles

Use a two-step workflow wherever practical:

1. Evidence pass: gather cited claims, quotes, caveats, and source disagreement.
2. Calibration pass: assign `score_1_to_10`, `confidence_score`, and final
   caveats using the shared rubric for that methodology question.

The evidence pass should not invent a local scoring scale. The calibration pass
should compare multiple rulers against the same anchors before accepting close
relative scores.

Question-specific instructions belong in the question guide, not in ad hoc chat
prompts. The chat prompt may point researchers and judges to the guide, but the
guide is the durable source of truth.

## Preferred workflow: one judge per question-year batch

For score-bearing manual/internet questions, the preferred operational pattern is
one calibrated judge for the full question-year batch:

1. Many research workers gather evidence for individual ruler/country cases.
2. One calibration worker receives all evidence records for the same
   `methodology_id` and target year.
3. That calibration worker applies the question rubric to every ruler in the
   batch and writes the final score-bearing records.
4. A separate reviewer audits the batch for rubric drift, missed evidence, and
   systematic over- or under-scoring.

This is better than independent per-ruler scoring because the same judge holds the
full comparison set in memory and can apply one meter consistently. It is also
better than a purely mechanical calibration command for early development because
the judge can reason over caveats, contradictory evidence, and edge cases.

The same-judge pattern does not remove bias by itself. It can create consistent
bias if the judge's interpretation is wrong. Therefore every same-judge batch
still needs a fixed rubric, required calibration fields, preserved citations, and
an adversarial review pass.

Use separate judges only when the batch is too large for one context window. In
that case, split by question and year first, not by region or regime type, and run
a final cross-batch calibration over anchor cases.

## Required calibration fields

Every score-bearing cited evaluation must include a `calibration` object inside
`answer_payload`. These fields are required for every `internet_manual` question
that emits `score_1_to_10`; question-specific rubrics may add fields but should
not remove these common fields.

| Field | Required value shape | Purpose |
|---|---|---|
| `rubric_version` | Stable string, for example `3b1_domestic_safety_v1` | Identifies the exact meter used. |
| `calibration_batch_id` | Stable string for the question/year batch | Tells which rulers were judged together. |
| `calibrated_against` | List of ruler/country/year labels | Records the comparison set available to the judge. |
| `severity_band` | `none`, `isolated`, `recurring`, `widespread`, `systematic`, `mass` | Prevents article volume from substituting for severity and scale. |
| `state_responsibility` | `direct`, `state_aligned`, `tolerated`, `failed_to_prevent`, `non_state_only`, `unclear` | Separates direct ruler/state abuse from ordinary crime or non-state violence. |
| `accountability_level` | `strong`, `partial`, `weak`, `none`, `perpetrator_impunity`, `state_policy` | Distinguishes abuse with remedy from abuse with impunity or policy support. |
| `information_environment` | `open`, `partly_restricted`, `closed`, `highly_repressive`, `unclear` | Forces silence-under-repression handling. |
| `period_fit` | `target_year`, `ruler_period`, `near_period`, `outside_period`, `unclear` | Prevents recency or stale evidence from driving the score. |
| `source_mix` | List such as `structured_dataset`, `ngo`, `court_or_legal`, `media`, `un_or_intergovernmental`, `official`, `academic` | Makes source-type balance visible. |
| `structured_prior_summary` | String or object; may be `not_available` | Records what structured sources say before narrative evidence modifies it. |
| `contrary_evidence` | List of concise contrary claims or empty list | Preserves disagreement instead of smoothing it away. |
| `score_rationale` | Concise string | Explains why this score fits the anchor. |
| `lower_anchor_rejected` | Concise string | Explains why the next lower anchor is too harsh. |
| `higher_anchor_rejected` | Concise string | Explains why the next higher anchor is too generous. |
| `visibility_bias_check` | Concise string | States how media/reporting volume was handled. |
| `repression_silence_check` | Concise string | States how missing evidence was interpreted in the information environment. |
| `population_scale_check` | Concise string | States how absolute count, prevalence, and systematicity were separated. |
| `source_type_check` | Concise string | States whether the source mix is broad or biased. |
| `recency_check` | Concise string | States whether evidence matches the requested year/period. |
| `subagent_calibration_check` | Concise string | States how the case was compared to other rulers in the batch. |

Example shape:

```json
{
  "calibration": {
    "rubric_version": "3b1_domestic_safety_v1",
    "calibration_batch_id": "3b1_2023_batch_2026_07_06",
    "calibrated_against": [
      "Russia / Vladimir Putin / 2022",
      "United States / Joe Biden / 2023",
      "Hungary / Viktor Orban / 2023"
    ],
    "severity_band": "recurring",
    "state_responsibility": "direct",
    "accountability_level": "partial",
    "information_environment": "open",
    "period_fit": "target_year",
    "source_mix": ["structured_dataset", "ngo", "media", "official"],
    "structured_prior_summary": "PTS/CIRIGHTS/V-Dem indicate meaningful safeguards with serious rights concerns.",
    "contrary_evidence": ["Courts and press reported remedies in some cases."],
    "score_rationale": "Score 7 fits meaningful safeguards with serious recurring abuses.",
    "lower_anchor_rejected": "Score 6 is too harsh because abuses are not shown as systematic state terror.",
    "higher_anchor_rejected": "Score 8 is too generous because serious detention/policing concerns remain.",
    "visibility_bias_check": "High press visibility increases evidence volume but was not treated as severity.",
    "repression_silence_check": "Open environment makes missing evidence more meaningful than in closed regimes.",
    "population_scale_check": "Incidents were treated as recurring concerns, not proof of mass/systematic abuse.",
    "source_type_check": "Uses structured, NGO, media, and official sources; court-source coverage remains partial.",
    "recency_check": "Target-year and near-period evidence are separated.",
    "subagent_calibration_check": "Compared against lower-scored systematic repression cases and higher-scored strong-safeguard cases."
  }
}
```

The importer rejects score-bearing records missing this object. Reviewers should
also treat incomplete or boilerplate calibration fields as blockers.

## Generic 1-10 direction

Unless a question-specific rubric says otherwise, `10` means strongest positive
ruler-quality performance for the question and `1` means strongest negative
performance. Scores must be justified by severity, scale, state responsibility,
duration, and accountability, not by the raw volume of search results.

## Domestic safety anchor for 3B.1

For `3B.1` domestic safety vs state violence/oppression, higher is better:

| Score | Anchor |
|---:|---|
| 1 | Systematic state terror: recurrent killings, torture, disappearances, political imprisonment, or mass repression as policy. |
| 2-3 | Severe recurring state abuse, arbitrary detention, torture, or lethal repression with weak remedies. |
| 4-5 | Significant abuse patterns or targeted repression, but not generalized terror; safeguards are partial or unreliable. |
| 6-7 | No systematic terror and meaningful safeguards, but serious police, detention, prison, asylum, protest, or minority-rights abuses remain. |
| 8-9 | Strong protection, rare serious abuses, credible investigation/remedy, and open reporting. |
| 10 | Very strong protection, rare violations, robust accountability, high transparency, and durable safeguards. |

## Entrenchment-manipulation anchor for 4B.2

For `4B.2` political-freedom entrenchment manipulation, higher is better and means
the ruler refrained from bending institutions for incumbency advantage. Use
`rubric_version = "4b2_entrenchment_manipulation_v1"` and the question-specific
fields from `question-guides/4b-2-entrenchment-manipulation.md`:
`manipulation_status`, `entrenchment_channels`, and
`institutional_remedy_status`.

| Score | Anchor |
|---:|---|
| 1 | Systematic entrenchment through captured rules, courts, media, election bodies, security forces, and public resources. |
| 2-3 | Severe manipulation across several channels materially entrenches the ruler. |
| 4-5 | Recurring manipulation creates major incumbent advantage, though some constraints remain. |
| 6-7 | Mostly neutral institutions with notable flaws or episodic state-resource/institutional abuse. |
| 8-9 | Strong restraint, broad institutional neutrality, and credible remedies for isolated abuses. |
| 10 | Exemplary restraint and active strengthening of neutral constraints against incumbency abuse. |

## Opposition-tolerance anchor for 4B.3

For `4B.3` political-freedom opposition tolerance, higher is better and means the
ruler tolerated opposition victories, criticism, satire, investigative journalism,
peaceful protest, and civil-society monitoring. Use
`rubric_version = "4b3_opposition_tolerance_v1"` and the question-specific fields
from `question-guides/4b-3-opposition-tolerance.md`: `tolerance_status`,
`opposition_tolerance_channels`, and `remedy_or_accountability_status`.

| Score | Anchor |
|---:|---|
| 1 | No meaningful opposition/civic space; opposition, criticism, journalism, protest, and civil-society monitoring are systematically criminalized, censored, or crushed. |
| 2-3 | Severe intolerance across several channels with recurring arrests, violence, bans, closures, legal harassment, or impunity. |
| 4-5 | Recurring selective restrictions chill civic activity, though some opposition, media, protest, or monitoring space remains. |
| 6-7 | Broad civic space with notable flaws, episodic disproportionate policing, legal threats, media pressure, or weak remedies. |
| 8-9 | Strong tolerance, with criticism, opposition activity, media, protest, and civil society generally protected and abuses isolated or remedied. |
| 10 | Exemplary tolerance and active protection of opposition, criticism, satire, investigative journalism, peaceful protest, and civil-society monitoring. |

## Bias mechanisms to check

- Visibility bias: open societies produce more reports about smaller violations;
  closed societies can hide larger violations.
- Silence-under-repression bias: absence of reports is weak evidence where
  journalists, NGOs, courts, opposition, or victims cannot speak safely.
- Population-size bias: larger countries naturally produce more incidents and
  more reporting; distinguish absolute counts, rates, and systematic policy.
- Source-type bias: advocacy reports, official statements, courts, media, and
  structured datasets have different blind spots.
- Regime-type comparability bias: abuse plus accountability is different from
  abuse with impunity or deliberate state policy.
- Recency bias: current scandals can crowd out the full target-year or ruler
  period record.
- Search-language and media-access bias: English-language search can miss local
  evidence or overrepresent internationally salient cases.
- Conflict-context bias: wartime, insurgency, occupation, and civil unrest can
  change base rates, but do not excuse direct state abuse.
- Subagent calibration bias: separate agents can apply different implicit score
  anchors unless the prompt and review process force a shared meter.

## Mitigation rules

- Prefer structured human-rights sources as anchors when available: PTS,
  CIRIGHTS, V-Dem, UCDP, Freedom House, BTI, and credible UN/NGO reports.
- Record both severity and scale: isolated, recurring, widespread, systematic,
  mass.
- Record accountability separately: investigation, prosecution, court remedy,
  institutional reform, denial, impunity, or official policy.
- Treat no-findings results as low-confidence in closed information environments.
- Do not count media volume as severity. One well-documented disappearance is
  not equivalent to hundreds of disappearances merely because the first produced
  more searchable articles.
- Compare borderline cases in batches. If two rulers differ by only one or two
  points, rerun a calibration pass over both records together.
- Preserve dissenting evidence and caveats in `answer_json` rather than smoothing
  away contradictions.

## Confidence score input

`confidence_score` is stored as a 0-100 percentage. Importers accept either a
0-100 value such as `94` or a fractional value such as `0.94`, which is normalized
to `94` during validation.
