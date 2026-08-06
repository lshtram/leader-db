# 2022 Five-Ruler Bias Pilot

Date: 2026-07-23

Status: passed the five-ruler development gate; not a promoted release.

## Scope

The common-meter run `2022-bias-five-judge-v1` judged all eight chapters across the
same five preserved dossiers: Joe Biden, Félix Tshisekedi, Vladimir Putin, Olaf Scholz,
and Jonas Gahr Støre. The cases test open reporting, closed-regime silence, sparse and
conflict-affected evidence, concentrated authority, coalition/federal constraints, and a
high inherited institutional baseline.

## Results

| Chapter | Biden | Tshisekedi | Putin | Scholz | Støre |
|---|---:|---:|---:|---:|---:|
| 1B | 5.5 (76) | 6.0 (54) | 3.0 (83) | 6.0 (58) | 6.5 (63) |
| 2B | 6.5 (70) | 4.5 (58) | 1.5 (88) | 6.5 (47) | 6.0 (50) |
| 3B | 7.0 (68) | 4.5 (72) | 3.5 (78) | 7.5 (56) | 7.5 (64) |
| 4B | 7.5 (78) | 4.5 (68) | 2.5 (64) | 7.0 (48) | 7.0 (55) |
| 5B | 6.0 (72) | 5.0 (60) | null (18) | 5.5 (61) | 5.5 (58) |
| 6B | 5.5 (58) | 5.0 (52) | null (18) | 5.0 (42) | 5.0 (46) |
| 7B | 5.5 (43) | 5.0 (34) | 4.5 (29) | 5.0 (31) | null (18) |
| 8B | 6.0 (68) | 4.5 (60) | 4.0 (35) | 5.0 (42) | 5.5 (65) |

Parentheses contain confidence on the 0-100 scale. These are provisional pilot outputs,
not promoted rankings.

## Deterministic and manual audits

- All eight jobs completed and produced 40 ruler-chapter evaluations. Thirty-seven are
  scored; three are reasoned nulls. Putin 5B/6B lacked discriminating ruler-attributed
  implementation or outcomes, and Støre 7B lacked a direct personal-integrity nexus.
- Every evaluation contains material bias findings with cited evidence, a confidence/range
  effect, remaining uncertainty, and explicit confirmation that report volume was not used
  as severity and no blanket democracy/autocracy correction was applied.
- Every evaluation calibrated against at least two actual cohort dossiers. All structured
  prior summaries are populated. Chapter 7B correctly describes country-level priors as
  institutional context that is insufficient for a personal-integrity finding; it does not
  claim that the local package was absent.
- Judge prompts contain no `client_score`, `system_proposed_score`, or
  `score_delta_vs_client` fields.
- The personal-nexus boundary held. Støre received a null; Tshisekedi, Putin, and Scholz
  retained low confidence and manual review where knowledge, benefit, protection,
  deception, or obstruction remained unresolved. National corruption was not itself
  treated as ruler misconduct.
- The inherited-baseline/authority boundary held in 8B. Støre's strong welfare and
  administrative institutions were described as inherited; coalition, ministry,
  municipal, agency, parliamentary, NATO, pandemic, war, energy, and inflation constraints
  limited attribution. The score reflects mixed execution evidence, not the moral value of
  objectives or Norway's baseline alone.
- Against the prior Biden/Tshisekedi two-ruler run, median absolute score drift is 0.5 and
  maximum drift is 1.0. No unchanged case moved more than the promotion threshold. The
  largest changes were Biden 1B (6.5 to 5.5) and Tshisekedi 2B (5.5 to 4.5), both within
  the explicit five-case calibration ranges.
- Chapter 4B required one semantic repair attempt. Its first candidate contained an
  invalid calibration key and overlapping weak/supported lens descriptions; tolerant
  normalization preserved the useful candidate, and the repair completed without changing
  dossiers or searching. This remains a stability signal for the cohort gate, not a reason
  to silently accept invalid references.

## Gate decision

The five-ruler gate passes for continued controlled development. The pipeline demonstrated
full evidence collection and full comparative judging across the intended bias contrasts,
with bounded retries, explicit nulls, valid local-prior transmission, and score stability
within the one-point limit. This does not authorize immediate production promotion: the
next controlled increment is the complete 20-ruler 2022 cohort with preserved old/new
artifacts, followed by the source-family, order, local-evidence, cost, and manual-reading
audits in the implementation plan.
