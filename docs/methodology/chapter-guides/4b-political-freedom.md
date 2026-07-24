# 4B Political Freedom vs Authoritarian Rule

Status: draft; v4 objective-evidence questions require controlled rejudgment

## Chapter Identity

- `chapter_id`: `4B`
- Category: political freedom vs authoritarian rule
- Evidence unit: one ruler and target year or defined ruler-period
- Final output: one chapter score, not ten question scores
- Rubric version: `chapter_4b_v4`
- Judge topology: one chapter judge applies this guide across all eligible rulers in the same year/period batch.

The ten questions below are complementary evidence lenses. They direct collection and expose different mechanisms; they are not independent gates or equally weighted sub-scores.

## Ten Evidence Lenses

1. **4B.1** — Did the ruler support and implement electoral and constitutional laws, funding, and administration that made power genuinely contestable, and accept verified opposition victories?
2. **4B.2** — Did the ruler refrain from proposing, signing, decreeing, manipulating, or obstructing laws, courts, election administration, security forces, media, or public resources to entrench personal or party power?
3. **4B.3** — Did the ruler protect in law and practice opposition, criticism, satire, investigative journalism, protest, association, and civil-society monitoring, and remedy violations?
4. **4B.4** — Did the ruler protect the jurisdiction, appointment independence, tenure, funding, and decisions of courts, legislatures, election bodies, auditors, and local governments even when they constrained the ruler?
5. **4B.5** — Did appointments, dismissals, civil-service rules, and administrative practice preserve politically neutral institutions rather than impose loyalty tests, party capture, intimidation, or a personality cult?
6. **4B.6** — Did the ruler support and enforce media, information-access, ownership, and licensing rules that enabled independent information rather than censorship, propaganda, disinformation, or pressure?
7. **4B.7** — Did the ruler enact and enforce equal political rights and access for minorities, women, excluded groups, opposition regions, and unpopular viewpoints?
8. **4B.8** — Did the ruler preserve and comply with term limits, succession rules, coalition commitments, and constitutional transfer rather than amend, evade, or obstruct them for continued power?
9. **4B.9** — Did the ruler narrowly authorize, transparently procure, and lawfully oversee surveillance and digital controls, or use law, shutdowns, and administrative harassment to suppress political freedom?
10. **4B.10** — Did the ruler leave political freedom and democratic resilience durably stronger than inherited through enacted, implemented, and independently reviewable institutions, accounting for correction and constraints?

## Researcher Evidence Plan

Collect a reusable, cited ruler-period dossier; do not score the chapter. Follow the local-first researcher guide and source-confidence registry. Start with local V-Dem, BTI, RSF, Freedom House/Polity when available, election and constitutional records, then search only unresolved gaps. Prefer election observers, courts, legislatures, audit/election bodies, UN or regional institutions, rights and press-freedom organizations, academic histories, and reputable local/international reporting. Official claims are useful for acts and stated intent but require independent checks for effects.

Seek evidence on election quality and alternation; institutional capture or restraint; treatment of opposition, protest, journalists, NGOs and satire; court and legislative independence; appointments and politicization; censorship, propaganda and digital controls; political inclusion; term limits and succession; and inherited-to-left trajectory. Preserve favorable, adverse and contrary evidence. One item may support several lenses when the relationship is real; do not duplicate the source merely to fill every lens. Flexible prose and coverage labels are acceptable if citations and meaning remain recoverable.

Each evidence item must preserve, in fields or clearly recoverable prose: the factual claim; citation or URL plus source title, publisher and publication date when available; target-year/ruler-period fit; source-confidence assessment and source role; the basis and strength of attribution to the ruler; and material uncertainty or disagreement. Missing bibliographic details may be marked unknown rather than invented. Formatting deviations are normalization work, not grounds to discard otherwise usable evidence.

## Baseline, Attribution, and Sparse Evidence

Separate inherited regime conditions from the ruler's choices. Credit opening, restraint, remedies and durable institution-building; debit capture, repression, erosion and knowing failure to prevent abuses within the ruler's authority. Record formal versus de facto authority, coalition constraints, subnational responsibility, conflict/emergency context and timing. Do not award a ruler an inherited democracy automatically or blame a new ruler for every inherited restriction.

Historical and obscure cases will have uneven records. Use contemporary archives, constitutional histories and reputable scholarship; note temporal distance and disagreement. Missing lenses lower confidence and may alter qualitative weight, but never invalidate a dossier or mechanically force a neutral/low score. Silence is especially weak evidence in closed systems.

An inherited democracy establishes context, not ruler merit. Scores of 8 or above
require direct target-period evidence that the ruler respected or strengthened
contestability, transfer rules, civic/media space, or independent constraints when
those constraints had practical force. A 9 normally requires meaningful pressure or
consequential strengthening. If a projection claims coverage but contains no cited
chapter evidence, return null and flag `projection_integrity`; do not infer a score
from the country baseline. Post-window events may be used only as retrospective
evidence about a target-period act, must be labeled, and may not silently expand the
period under judgment.

## Chapter Judge and Lens Weighting

One judge scores the complete ruler batch with a common meter. Judge the overall freedom people could exercise and the ruler's contribution to it. Weight lenses qualitatively by consequence, ruler responsibility, duration, breadth, source strength and period fit. Electoral contestability, coercive closure, institutional constraints, civic/media space and transfer rules will often be decisive; minor administrative incidents should not outweigh systematic capture. `4B.10` synthesizes trajectory and must not double-count every underlying event. Redundancy is intentional: corroborating lenses increase confidence, not arithmetic weight.

The judge may score with only part of the lens set when the available evidence establishes the regime and ruler pattern. State which lenses are strong, weak or unavailable and why. Never manufacture a per-lens score or average.

## One-Chapter 1–10 Rubric

| Score | Chapter anchor |
|---:|---|
| 1 | The ruler systematically eliminates meaningful political choice and independent constraint through repression, captured institutions, censorship, entrenchment and/or refusal of lawful transfer. |
| 2–3 | Severe authoritarian rule dominates across several consequential mechanisms; opposition and oversight exist only narrowly or at substantial risk. |
| 4–5 | Material competition or civic space coexists with recurring manipulation, capture, exclusion or intimidation; the ruler's contribution is mixed or erosive. |
| 6–7 | Meaningful political freedom and constraints operate, but important ruler-attributable flaws, unequal access, pressure or institutional weaknesses remain. |
| 8–9 | The ruler consistently respects broad contestability, rights, independent institutions and transfer rules, with isolated or credibly remedied shortcomings. |
| 10 | Exceptional, durable protection and strengthening of pluralism and neutral constraints, including when those constraints threaten the ruler's own power. |

## Common Chapter-Judge Output Envelope

The chapter result should use the shared semantic envelope below. Exact field spelling can be normalized cheaply after LLM handoff; no useful judgment should be rejected only for synonymous wording.

- `chapter_id`: `4B`
- `rubric_version`: `chapter_4b_v4`
- `calibration_batch_id` and `calibrated_against`
- `score_1_to_10`, or null with `insufficient_evidence_reason`
- `confidence_score` and `plausible_score_range`
- `decisive_positive_evidence` and `decisive_negative_evidence`, referencing evidence items
- `inherited_baseline_and_constraints` and `ruler_attribution`
- `supported_lenses` and `missing_or_weak_lenses`
- `contrary_evidence` and unresolved disagreements
- `source_mix` and `structured_prior_summary`
- `chapter_rationale`, `lower_anchor_rejected`, and `higher_anchor_rejected`
- `manual_review_required`, `manual_review_reason_type`, and `manual_review_reason`

Chapter-specific extra: `trajectory`.

`Insufficient_evidence` is a permitted judgment for an exceptionally thin case, not an automatic consequence of missing lenses. Natural-language values are acceptable; preserve meaning rather than enforcing brittle enums.

## Calibration, Confidence, and Bias Checks

Check visibility and silence-under-repression bias, population and incident-volume bias, regime-type comparability, election-cycle timing, wartime/emergency claims, formal-versus-de-facto authority, English-language/search-access bias, and recency. Compare rulers with similar inherited systems as well as the full batch. High reporting volume in open societies is not itself worse performance.

## Smoke-Test Cases

| Ruler | Country | Period | Calibration purpose |
|---|---|---:|---|
| Kim Jong Un | North Korea | 2012–2023 | closed personalist low anchor and silence bias |
| Alexander Lukashenka | Belarus | 2020 | manipulated election and coercive entrenchment |
| Vladimir Putin | Russia | 2012–2023 | long-run institutional erosion and transfer avoidance |
| Narendra Modi | India | 2014–2023 | competitive elections with contested civic/institutional record |
| Donald Trump | United States | 2020–2021 | transfer stress test within resilient institutions |
| Nelson Mandela | South Africa | 1994–1999 | democratic transition, inclusion and voluntary departure |
| Angela Merkel | Germany | 2005–2021 | high institutional-restraint comparison |
| Jacinda Ardern | New Zealand | 2017–2023 | high freedom with crisis/emergency scrutiny |
| Lee Kuan Yew | Singapore | 1965–1990 | prosperity-versus-contestability edge case |
| Violeta Chamorro | Nicaragua | 1990–1997 | less-visible historical transition, institutional constraint and gender comparison |

## Acceptance Checklist

- Scores above `7` require affirmative ruler-attributed self-binding, protection, or
  expansion of freedom; inherited democratic institutions alone cannot establish a
  high anchor.

- All ten exact lenses remain visible, but only one chapter score is produced.
- Research is local-first, cited, source-profiled, period-fit and preserves contrary evidence.
- The judge scores the full batch with one rubric and records adjacent comparisons.
- Baseline, de facto authority, ruler attribution and trajectory are explicit.
- Missing lenses reduce confidence and never invalidate the dossier.
- Flexible LLM wording/statuses are accepted when evidence and uncertainty are recoverable.
- Systematic mechanisms outweigh article count and isolated events.
- Bias checks and anchor rejections are substantive.
- Smoke cases are reviewed together before this draft is activated.
