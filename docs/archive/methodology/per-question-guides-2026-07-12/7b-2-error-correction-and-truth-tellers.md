# 7B.2 Error Correction And Treatment Of Truth-Tellers

Status: draft; not yet smoke-tested

## Question Identity

- `methodology_id`: `7B.2`
- Category: `ruler_personal_integrity_and_honesty`
- Evidence strategy: `internet_manual`
- Rubric version: `7b2_correction_truth_tellers_v1`
- Guide owner/status note: initial draft for guide expansion and later all-ruler calibration.

## Question Text

Does the ruler admit errors, correct false claims, and allow truthful reporting,
or do they knowingly mislead, double down, blame others, and punish truth-tellers?

## What This Question Asks

Registry context: low transparency alone is not automatically dishonesty. It is
relevant when it supports intentional deception, manipulation of public
information, punishment of truth-tellers, or avoidance of accountability.

Higher scores mean the ruler acknowledges consequential mistakes, corrects false
claims, permits evidence to reach the public, and protects independent reporters,
officials, experts, auditors, and whistleblowers who communicate inconvenient
truth. Lower scores mean knowing persistence in falsehood, scapegoating, coerced
false narratives, concealment, retaliation, or institutional punishment. Evaluate
both personal responses and ruler-directed state or party conduct.

## What This Question Does Not Ask

- Do not rescore the original truth or falsity alone; `7B.1` covers habitual
  truthfulness, while this question centers response after credible correction.
- Do not treat ordinary personnel discipline, lawful secrecy enforcement, or good-
  faith disagreement as punishment of truth-tellers without evidence.
- Do not infer admission merely from a policy reversal, or refusal to confess from
  litigation posture alone.
- Do not score general press freedom except where conduct is tied to truthful
  reporting, correction, concealment, or retaliation attributable to the ruler.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Follow [`../local-first-researcher-guide.md`](../local-first-researcher-guide.md),
query exact-case local evidence, and apply
[`../source-confidence-registry.json`](../source-confidence-registry.json).
Explicitly record absent local evidence. Use the approved Parallel Search wrapper
for discovery and cite underlying URLs. Every citation needs the four registry
profile fields, and every shard needs the prescribed `run_profile`.

## Researcher Instructions

Collect episode-level evidence: the initial claim/error; credible notice given to
the ruler; response timing; admission, correction, partial correction, silence,
double-down, blame-shifting, or retaliation; who suffered consequences; legal or
institutional remedy; and whether the conduct recurred. Seek contrary examples of
admission, apology, correction, restored officials, protected reporting, or
independent review. Separate criticism from demonstrably truthful reporting and
personal ruler acts from autonomous agency conduct. Do not assign final scores.

## Judge Instructions

Apply `7b2_correction_truth_tellers_v1` to the entire batch. Give most weight to
responses after the ruler had reliable notice, and to material issues. Distinguish
face-saving rhetoric from substantive correction, and political criticism from
retaliation using state or party power. Do not reward a correction that leaves the
falsehood operational or punish a ruler for reasonably contesting uncertain facts.
Flag unclear attribution, notice, or truth status for research. Aggregate the two
dimensions explicitly: correction behavior and treatment of truth-tellers are not
substitutes. Serious ruler-attributable retaliation sets a ceiling even where
personal admission or correction is strong: systematic suppression caps the score
at 3, serious repeated punishment caps it at 5, and one material unremedied episode
caps it at 7. Apply a higher score only when attribution is not established or an
effective, ruler-supported remedy materially changes the accountability finding.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Systematic denial and false narrative enforcement: the ruler knowingly doubles down and uses state/party power to silence or punish truth-tellers, with impunity. |
| 2-3 | Repeated refusal to correct major falsehoods, blame-shifting, concealment, or serious retaliation across multiple consequential episodes. |
| 4-5 | Mixed but concerning conduct: some corrections or tolerated scrutiny coexist with recurring defensiveness, incomplete admissions, scapegoating, or selective retaliation. |
| 6-7 | Generally accepts correction and truthful scrutiny, but notable delayed, partial, defensive, or poorly remedied episodes remain. |
| 8-9 | Prompt, substantive correction and protection of truthful reporting are the strong norm; retaliation is rare, disavowed, and effectively remedied. |
| 10 | Exceptional accountability: proactive admission, correction, disclosure, independent review, and durable protection of truth-tellers even at major political cost. |

## Evidence Requirements

Minimum evidence: one citation, local-prior status, target-period evidence,
contrary evidence, and source-mix assessment. Each major episode should establish
the underlying truth, ruler notice, response, attribution, and consequences using
independent evidence where possible. Preferred sources: primary statements and
corrections; court judgments, inquiry/audit/inspector-general and legislative
records; whistleblower protection or retaliation findings; independent media and
fact-checkers; press-freedom or human-rights organizations; academic studies.
Official claims about their own restraint require independent corroboration.

## Bias And Comparability Checks

Complete all common checks. Address the visibility advantage of open systems;
silence and coerced narratives in closed systems; whether many reports describe
one episode; whether the truth-teller's claim was independently substantiated;
formal versus de facto retaliation; translation and local-source access; and
whether correction speed and substance were evaluated consistently.

## Required Calibration Values

Use every common calibration field.

- `rubric_version`: `7b2_correction_truth_tellers_v1`
- `severity_band`: common enum, interpreted as frequency/materiality of refusal or retaliation
- `state_responsibility`: common enum, interpreted as ruler/state/party attribution
- `accountability_level`: common enum, interpreted as remedy for falsehood or retaliation
- `correction_pattern`: `proactive`, `prompt`, `delayed_or_partial`, `mixed`, `usually_refuses`, `systematic_double_down`, or `unclear`
- `truth_teller_treatment`: `protected`, `generally_tolerated`, `mixed`, `pressured`, `punished`, `systematically_suppressed`, or `unclear`
- `notice_quality`: `clear`, `probable`, `limited`, `not_shown`, or `unclear`
- `retaliation_channels`: list from `dismissal`, `prosecution`, `detention`, `violence`, `regulatory`, `financial`, `smear_or_threat`, `institutional_obstruction`, `none_found`, `unclear`
- `retaliation_score_cap`: `3_systematic_suppression`, `5_serious_repeated`, `7_material_unremedied`, `no_cap_effective_remedy`, `no_cap_not_attributable`, `no_cap_none_found`, or `unclear`

## Smoke-Test Ruler Set

These roles are hypotheses for testing, not final scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Donald Trump | United States | 2020 | double-down and truth-teller-retaliation evidence case |
| Boris Johnson | United Kingdom | 2021-2022 | correction, apology, and parliamentary accountability distinctions |
| Richard Nixon | United States | 1972-1974 | concealment and retaliation with strong documentary record |
| Mikhail Gorbachev | Soviet Union | 1987-1991 | institutional opening and correction under transition |
| Jacinda Ardern | New Zealand | 2020 | crisis correction high-anchor candidate |
| Angela Merkel | Germany | 2015-2021 | admission/correction candidate with policy-dispute controls |
| Xi Jinping | China | 2020 | closed information and attribution edge case |
| Cyril Ramaphosa | South Africa | 2020-2022 | inquiry, disclosure, and contested-accountability middle case |

## Acceptance Checklist

- Local-first and citation-profile requirements are satisfied.
- Notice, truth status, response, attribution, consequence, and remedy are explicit.
- Original falsehood (`7B.1`) is not conflated with response to correction.
- Correction behavior and truth-teller treatment are aggregated separately, and any ruler-attributable retaliation cap is applied and explained.
- Lawful confidentiality and good-faith dispute are not presumed retaliation.
- Contrary corrections and protection examples are preserved.
- One batch judge completes all fields and substantive adjacent-anchor rejections.
- Smoke roles are tested rather than assumed, and the guide is revised afterward.
