# 7B.1 Truthfulness

Status: draft; not yet smoke-tested

## Question Identity

- `methodology_id`: `7B.1`
- Category: `ruler_personal_integrity_and_honesty`
- Evidence strategy: `internet_manual`
- Rubric version: `7b1_truthfulness_v1`
- Guide owner/status note: initial draft for guide expansion and later all-ruler calibration.

## Question Text

Does the ruler habitually tell the truth to the public, legislature, courts,
allies, and international partners, especially on matters where deception would
protect power or reputation?

## What This Question Asks

Registry context: low transparency alone is not automatically dishonesty,
especially under genuine security, privacy, or diplomatic constraints. It becomes
evidence when it supports intentional deception, concealment of illegal,
destructive, or self-serving activity, manipulation of public information,
punishment of truth-tellers, or avoidance of accountability.

Higher scores mean a sustained record of materially truthful communication,
including when candor is politically costly. Lower scores require a demonstrated
pattern of knowing or reckless material falsehoods, fabricated evidence, concealed
facts, or contradictory representations made to protect power or reputation.
Assess frequency, materiality, intent, audience, correction, and consequences.

## What This Question Does Not Ask

- Do not equate policy failure, prediction error, rhetoric, exaggeration, or an
  honestly disputed interpretation with a knowing lie.
- Do not infer dishonesty merely from secrecy justified by genuine security,
  privacy, legal, or diplomatic constraints.
- Do not score general corruption, promise-keeping, press freedom, popularity, or
  ideological agreement except as direct evidence of truthfulness.
- Do not count repetitions of one falsehood as independent patterns without noting
  their common origin, and do not score by fact-check volume.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Read [`../local-first-researcher-guide.md`](../local-first-researcher-guide.md),
query `leaders-db research local-evidence` for the exact case, and read
[`../source-confidence-registry.json`](../source-confidence-registry.json) before
web discovery. Record `no_evidence_found` rather than inventing a structured prior.
Use `leaders-db research parallel-search` for discovery and allowed exact-URL
fetching for underlying sources. Final citations must cite the underlying URL,
not the discovery artifact. Every citation requires `source_confidence`,
`source_confidence_reason`, `source_type`, and `final_evidence_use`; every shard
requires the prescribed `run_profile`.

## Researcher Instructions

Collect cited evidence without assigning the final comparative score. Build a
chronology of independently verifiable material statements and identify the exact
words, audience, available facts at the time, later findings, ruler knowledge or
recklessness, correction, and stakes. Seek both documented deception and examples
of costly candor or accurate correction. Separate target-year, near-period, and
broader ruler-period evidence. Distinguish original falsehoods from repetition,
satire, mistranslation, aides' statements, and claims not attributable to the
ruler. Preserve credible disputes about intent or factuality.

## Judge Instructions

Judge all cases for the question-year batch together using
`7b1_truthfulness_v1`. Weight material, independently established deception more
than imprecision or trivial errors. Require evidence of knowledge, recklessness,
or an implausible pattern before using the lowest anchors. Evaluate conduct, not
whether the ruler's policies or ideology are desirable. Explain adjacent-anchor
rejections and require more research where source access or attribution is weak.
Do not assign above 7, or describe conduct as sustained or habitual, unless the
record samples a representative breadth of the relevant period, material subject
areas, and applicable audiences rather than relying on isolated favorable cases.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Pervasive, strategic deception is a central instrument of rule across audiences; fabricated or concealed material facts protect power, with no credible commitment to correction. |
| 2-3 | Repeated, knowing material falsehoods or concealment across several major matters substantially distort accountability; truthful exceptions do not alter the pattern. |
| 4-5 | A meaningful recurring pattern of misleading claims exists, but intent, scope, or materiality is mixed and important truthful conduct or constraints remain. |
| 6-7 | Generally truthful on material matters, with notable misleading episodes, reckless claims, or opacity; these are limited, contested, corrected, or not habitual. |
| 8-9 | Strong sustained truthfulness, including politically costly candor; material errors are rare and promptly corrected, with credible independent scrutiny. |
| 10 | Exceptional, durable truthfulness across audiences under adverse incentives, proactive correction and disclosure, and no credible material deception pattern. |

## Evidence Requirements

Minimum evidence includes multiple independent citations sufficient to cover the
material claim, the local-prior status, target-period narrative evidence, contrary
evidence, and a source-mix note. One citation is insufficient for any sustained,
habitual, or above-7 assessment. Scores above 7 require a documented,
representative sample across the relevant time span, major subject areas, and
applicable audiences, plus an explicit search for adverse cases. A low or
very-low confidence source cannot solely support a score-bearing claim. For a
claim of knowing deception, prefer the primary statement plus an independent
factual finding; allegations alone must be labeled. Preferred sources are official
transcripts/recordings and sworn records for the statement; courts, inquiries,
auditors, inspectors general, legislative records, and declassified documents for
facts and knowledge; reputable fact-checkers with transparent methods; academic
work; and reputable media for chronology. Government self-assessments are
conditional under the source-confidence registry.

## Bias And Comparability Checks

Complete all common checks. Specifically address unequal fact-checking ecosystems;
silence where media, courts, or whistleblowers are repressed; repeated coverage
versus distinct falsehoods; local-language and translation limits; retrospective
knowledge versus what was knowable when speaking; and whether equivalent
materiality and intent thresholds were applied across rulers.

## Required Calibration Values

Use every common field from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

- `rubric_version`: `7b1_truthfulness_v1`
- `severity_band`: common enum, interpreted as prevalence/materiality of deception
- `state_responsibility`: common enum, interpreted as attribution to ruler or ruler-directed apparatus
- `accountability_level`: common enum, interpreted as correction and independent remedy
- `truthfulness_pattern`: `strong`, `generally_truthful`, `mixed`, `recurring_deception`, `strategic_systematic_deception`, or `unclear`
- `intent_evidence`: `direct`, `strong_inference`, `limited_inference`, `not_shown`, or `unclear`
- `audiences_assessed`: list from `public`, `legislature`, `courts`, `allies`, `international_partners`, `other`
- `correction_behavior`: `prompt`, `eventual`, `partial`, `none`, `doubled_down`, `not_applicable`, or `unclear`

## Smoke-Test Ruler Set

These are plausible calibration roles, not predetermined scores.

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Donald Trump | United States | 2020 | high-visibility recurring-falsehood case; fact-check-volume bias |
| Boris Johnson | United Kingdom | 2021-2022 | legislature and official-accountability evidence case |
| Richard Nixon | United States | 1972-1974 | documented concealment and evidentiary-record case |
| Nelson Mandela | South Africa | 1994-1999 | high-integrity candidate requiring adverse-evidence search |
| Angela Merkel | Germany | 2015-2021 | generally truthful candidate with secrecy/policy-dispute boundaries |
| Mikhail Gorbachev | Soviet Union | 1987-1991 | changing openness within a constrained information system |
| Vladimir Putin | Russia | 2022 | closed-environment and international-partner claims edge case |
| Jacinda Ardern | New Zealand | 2020 | crisis communication and correction high-anchor candidate |

## Acceptance Checklist

- Local-first order, citation profiles, and `run_profile` are present.
- Material factual error is separated from intentional or reckless deception.
- Statements, facts, knowledge, audiences, corrections, and time periods are explicit.
- Above-7 and sustained/habitual findings use representative time, subject, and audience breadth and cannot rest on one citation.
- Contrary evidence and costly candor are preserved.
- One judge uses one batch meter and completes all calibration fields.
- Adjacent-anchor rejections and bias checks are substantive.
- Smoke cases are reviewed without treating their roles as predetermined scores.
- The guide is revised after smoke testing before activation.
