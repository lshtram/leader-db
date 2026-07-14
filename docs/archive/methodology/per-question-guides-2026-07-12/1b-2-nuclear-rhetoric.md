# 1B.2 Responsible Nuclear Rhetoric

Status: draft

## Question Identity

- `methodology_id`: `1B.2`
- Category: `nuclear_global_existential_responsibility`
- Evidence strategy: `internet_manual`
- Rubric version: `1b2_nuclear_rhetoric_v1`
- Guide owner/status note: initial draft for multi-ruler smoke testing.

## Question Text

Did the ruler use nuclear rhetoric responsibly, avoiding reckless threats,
brinkmanship, apocalyptic language, or normalization of nuclear use?

## What This Question Asks

This question scores how the ruler's public and credibly documented private
nuclear communications affected escalation, norms, miscalculation, and public
understanding. Higher scores mean precise, restrained, consistent communication
that preserves deterrence without casually normalizing nuclear use and that
clarifies or de-escalates crises. Lower scores mean explicit or implied nuclear
threats, apocalyptic or dehumanizing language, bluffing, contradictory signals,
or repeated statements that lower the perceived threshold for nuclear use.

## What This Question Does Not Ask

- Do not score arsenal size, modernization, or doctrine unless needed to
  interpret the words' credibility and risk.
- Do not assume every reference to deterrence or retaliation is reckless.
- Do not treat a sensational media paraphrase as the ruler's words; recover the
  transcript, recording, or reliable quotation where possible.
- Do not ignore audience, translation, conditionality, or immediate crisis
  context.
- Do not give automatic high scores to rulers who said little in closed systems.
- Do not use the client matrix as evidence.

## Researcher Instructions

Collect evidence only, using local artifacts before external search. Build a
dated statement log with exact short quotations where copyright limits permit,
links to full primary records, audience, language/translation notes, trigger or
condition, and subsequent clarification or retraction. Include:

- explicit threats, euphemistic threats, demonstrations of resolve, launch/use
  conditions, and statements about first use or retaliation;
- apocalyptic, civilizational, exterminatory, dehumanizing, joking, casual, or
  prestige-oriented references to nuclear weapons;
- restrained crisis messages, reaffirmation of taboo, no-use/limited-use
  clarification, hotlines, and corrective statements;
- consistency with official doctrine and operational signaling;
- evidence of likely audience and material escalation or de-escalation effects;
- contrary examples within the same target year or ruler period.

Profile citations with `source_confidence`, `source_confidence_reason`,
`source_type`, and `final_evidence_use`. Primary transcripts are preferred for
wording; independent expert or reputable media evidence is preferred for
interpretation and context. Low or `very_low` confidence sources cannot be sole
support for score-bearing claims.

## Judge Instructions

The judge must score the whole batch with
`rubric_version = "1b2_nuclear_rhetoric_v1"` and one batch ID. Evaluate the
pattern, not the most viral quotation. Distinguish direct quotations from
paraphrases, explicit threats from analyst inference, deterrent conditionality
from indiscriminate menace, and a corrected slip from repeated strategic
brinkmanship. Consider the ruler's authority and whether audiences could
reasonably treat the statement as policy. Explain both adjacent-anchor
rejections and flag translation, authenticity, or attribution disputes.

`no_material_rhetoric_found` never supports an automatic high score. If the
ruler lacked meaningful nuclear authority or exposure, mark the question
`not_applicable` (or retain an unscored record where the schema requires one).
If the ruler had meaningful authority/exposure but the information environment
cannot establish a representative rhetoric record, use
`insufficient_evidence`/`manual_review_required`. A score may be assigned for
documented restraint only when sufficiently broad, target-period evidence shows
how the ruler communicated during real nuclear-policy or crisis exposure; even
then, silence alone is not positive performance.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | Repeated, explicit, credible, and extreme nuclear threats or apocalyptic normalization form a central strategy and materially heighten use or miscalculation risk. |
| 2-3 | Recurring reckless threats, brinkmanship, contradictory signaling, or casual normalization, with little meaningful correction or restraint. |
| 4-5 | Mixed record: consequential irresponsible statements or implied threats coexist with restraint, clarification, or limited frequency. |
| 6-7 | Generally responsible and bounded communication, but notable ambiguity, rhetorical escalation, inconsistency, or isolated irresponsible episodes remain. |
| 8-9 | Consistently restrained, precise, norm-preserving rhetoric, including credible clarification and de-escalation during tension; rare lapses are corrected. |
| 10 | Exemplary crisis and routine communication that actively reduces miscalculation, reinforces nuclear restraint, and remains clear and responsible under severe pressure. |

## Evidence Requirements

- At least one citation and a structured prior or `not_available` explanation.
- Primary text/audio/video or a high-quality contemporaneous quotation for each
  material statement where available.
- Independent context addressing audience, conditionality, translation, and
  strategic significance.
- Target-year and broader ruler-period statements separated.
- Contrary rhetoric or explicit no-finding statement, plus source-mix caveat.
- An explicit authority/exposure determination whenever no material rhetoric is
  found; absence must resolve to `not_applicable`, `insufficient_evidence`, or a
  score supported by affirmative evidence of restraint, never an automatic high.

Preferred source types:

- official speech/transcript archives, UN records, legislative records, and
  verified recordings for primary wording;
- FAS, SIPRI, IAEA, UNODA, CTBTO, and established arms-control institutions for
  doctrinal context;
- Reuters, Associated Press, BBC, and comparable outlets for chronology and
  verified quotation;
- peer-reviewed or established expert analysis for signaling and translation.

## Bias And Comparability Checks

Complete the common checks, interpreting:

- `visibility_bias_check`: prolific/openly archived speakers generate more
  examples than rulers whose speech is controlled or inaccessible.
- `repression_silence_check`: sparse records in closed systems do not prove
  restraint.
- `population_scale_check`: use nuclear authority, audience reach, and crisis
  consequence rather than population.
- `source_type_check`: distinguish primary wording from media paraphrase and
  expert interpretation.
- `recency_check`: keep target-year statements distinct from famous remarks in
  other periods.
- `subagent_calibration_check`: compare frequency, explicitness, credibility,
  correction, and crisis context across adjacent cases.

Explicitly check translation bias, selection of viral remarks, partisan framing,
doctrine-versus-rhetoric mismatch, and outcome bias when reckless statements did
not lead to escalation.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `1b2_nuclear_rhetoric_v1`
- `severity_band`: apply to the rhetoric pattern: `none`, `isolated`,
  `recurring`, `widespread`, `systematic`, or `mass`
- `state_responsibility`: `direct` for authenticated ruler speech; otherwise use
  the appropriate common value, including `unclear`
- `accountability_level`: apply to clarification, correction, institutional
  discipline, or normalization using the common enum

Question-specific additional calibration fields:

- `rhetoric_pattern`: `norm_reinforcing`, `restrained`, `mixed`, `reckless`,
  `extreme`, `no_material_rhetoric_found`, or `unclear`.
- `nuclear_rhetoric_exposure`: `material_crisis_or_policy_exposure`,
  `routine_nuclear_authority`, `limited_indirect_exposure`,
  `no_meaningful_authority`, or `unclear`; this field controls the
  no-material-rhetoric disposition above.
- `threat_explicitness`: `none`, `implicit`, `conditional_explicit`,
  `unconditional_explicit`, or `unclear`.
- `statement_authenticity`: `primary_verified`, `reliably_quoted`,
  `contested_translation`, `secondary_only`, or `unclear`.
- `correction_status`: `not_needed`, `promptly_corrected`, `partly_clarified`,
  `uncorrected`, `repeated_or_amplified`, or `unclear`.
- `crisis_context`: concise description of audience, conditions, and concurrent
  operational signals.

## Smoke-Test Ruler Set

These cases are hypotheses for guide testing, not asserted final scores:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| John F. Kennedy | United States | 1962 | high-stakes crisis-communication edge case |
| Nikita Khrushchev | Soviet Union | 1962 | brinkmanship and negotiated retreat mixed case |
| Ronald Reagan | United States | 1981-1987 | rhetoric changing across a ruler period |
| Donald Trump | United States | 2017 | explicit threat/brinkmanship low-anchor hypothesis |
| Kim Jong Un | North Korea | 2017 | reciprocal-threat and translation-context case |
| Vladimir Putin | Russia | 2022 | repeated nuclear-signaling low-anchor hypothesis |
| Joe Biden | United States | 2022 | isolated wording/clarification edge case |
| Xi Jinping | China | 2022 | controlled-rhetoric and doctrine-versus-opacity case |
| Jacinda Ardern | New Zealand | 2020 | non-nuclear, limited-authority/no-material-rhetoric edge |

## Acceptance Checklist

- Material claims link to authenticated wording where possible.
- Quotation, paraphrase, translation, and analysis are clearly separated.
- Frequency, explicitness, credibility, correction, and crisis context are
  recorded.
- Silence in closed systems is not scored as restraint.
- The judge evaluates all smoke cases together or with shared anchors.
- Every score-bearing record has complete calibration fields.
- Adjacent-anchor reasoning and bias checks are substantive.
- Contrary statements and ambiguity are preserved.
- The guide is revised after smoke testing.
