# 4B.3 Opposition Tolerance

Status: draft for 2020 10-case full-flow smoke shard

## Question Identity

- `methodology_id`: `4B.3`
- Category: `political_freedom`
- Evidence strategy: `internet_manual`
- Rubric version: `4b3_opposition_tolerance_v1`
- Guide owner/status note: initial guide for a controlled 2020 local-first flow test.

## Question Text

Did the ruler tolerate opposition victories, criticism, satire, investigative
journalism, protest, and civil-society monitoring?

## What This Question Asks

This question scores whether the ruler allowed independent political and civic
actors to criticize, monitor, organize, protest, report, and win meaningful local
or national contests without retaliation. Higher scores mean opposition parties,
journalists, satirists, protesters, NGOs, monitors, and watchdog institutions had
protected space and real remedies when abuses occurred. Lower scores mean the
ruler or state-aligned forces punished, intimidated, censored, outlawed, smeared,
or otherwise chilled those actors.

The main scoring dimensions are:

- acceptance of opposition wins or critical opposition activity without retaliation;
- tolerance of criticism, satire, investigative reporting, independent media, and
  public-interest leaks;
- protest rights, assembly permits, policing restraint, and absence of selective
  arrests or violence against protesters;
- freedom for NGOs, civil-society monitors, election observers, unions, lawyers,
  academics, and watchdog groups to operate;
- legal, administrative, tax, security, ownership, licensing, or online pressure
  used to chill opposition, media, protest, or civil society;
- whether courts, parliaments, ombuds, regulators, or other remedies constrained
  abuse;
- target-year fit and broader ruler-period context.

## What This Question Does Not Ask

- Do not score general democracy quality unless it bears on tolerance of
  opposition, criticism, media, protest, or civil society.
- Do not duplicate `4B.1` by scoring election quality alone; focus on whether
  opposition success and civic challenge were tolerated after or around contests.
- Do not duplicate `4B.2` by scoring institutional manipulation itself unless it
  directly chills opposition/media/protest/civil society.
- Do not treat ordinary protest disorder, defamation law, or neutral enforcement
  as intolerance without evidence of selective, chilling, ruler/state-aligned, or
  disproportionate use.
- Do not punish constitutional monarchs or ceremonial presidents by default when
  they lack control over police, regulators, prosecutors, or media pressure;
  preserve role caveats.
- Do not use the client matrix as evidence.

## Required Local Structured Prior Before Internet Research

Before launching any `internet-research` worker, read and follow
[`../local-first-researcher-guide.md`](../local-first-researcher-guide.md). The
mandatory order is: inspect local guides, query the local DB/artifacts, use
preferred external sources, and use general web search last. Do not create a
separate local-prior prep phase as the main research strategy; the local prior is
one input that tells the worker what the local DB already contains.

Use the safe read-only local evidence command for worker-side local checks:

```bash
leaders-db research local-evidence \
  --methodology-id 4B.3 \
  --year 2020 \
  --iso3 <ISO3> \
  --json
```

For parent-side preparation, build and attach the local structured-prior artifact
for the exact ruler/country/year:

```bash
leaders-db research build-local-prior \
  --methodology-id 4B.3 \
  --year 2020 \
  --iso3 <ISO3> \
  --leader "<Ruler name>" \
  --output <local-prior.json> \
  --json
```

The artifact status must be handled explicitly:

- `evidence_found`: use the local facts as structured priors and do not refetch
  local structured datasets such as Freedom House, V-Dem, WGI, BTI, RSF, or Polity
  unless narrative/ruler-specific detail is needed.
- `no_evidence_found`: proceed only with a clear note that selected local facts are
  absent for this country-year; do not silently invent structured priors.
- `not_applicable`: do not produce a score-bearing record unless the scope decision
  is corrected; mark the case not applicable/manual review.
- `error`: do not launch dependent research until `missing_or_empty_reason` is
  inspected and resolved.

Single search-tool policy for this environment: use the direct Parallel Search
CLI wrapper (`leaders-db research parallel-search`) for discovery, and
`webfetch` for exact known URLs when snippets are insufficient. Do not use
Parallel MCP discovery/fetch tools, Minimax web search, Brave generic searches,
Playwright/browser searches, duplicate search passes, or unsafe browser code for
4B.3 evidence discovery.
Every shard must emit a `run_profile` as required by the local-first guide.

## Researcher Instructions

The `internet-research` worker collects cited evidence only. It should not assign
the final comparative score. For the target ruler/country/year, collect concise
evidence on:

- acceptance or rejection of opposition victories, criticism, satire, monitoring,
  and legislative/local challenges;
- arrests, violence, surveillance, bans, prosecutions, tax or NGO-law pressure,
  licensing, ownership, defamation, foreign-agent, national-security, or online
  controls directed at opposition, journalists, protesters, or civil society;
- protest policing, emergency restrictions, internet shutdowns, and whether
  restrictions were neutral/public-health measures or selective anti-opposition
  tools;
- contrary evidence such as peaceful protests, critical media operating freely,
  court remedies, dropped charges, opposition wins accepted, or independent NGOs
  monitoring government without retaliation;
- structured-source priors from the local artifact and necessary narrative sources,
  separated by target-year, near-period, and ruler-period evidence.

Researchers should return citations with source roles such as
`structured_dataset`, `ngo`, `court_or_legal`, `official`, `media`, `academic`,
`election_observer`, or `intergovernmental`.

Every citation must include source-confidence fields from
[`../source-confidence-registry.json`](../source-confidence-registry.json):
`source_confidence`, `source_confidence_reason`, `source_type`, and
`final_evidence_use`. Low and very-low confidence sources may not be the sole
support for score-bearing claims.

## Judge Instructions

The `ruler-quality-judge` receives all 2020 evidence records for `4B.3` and scores
the full batch together. The judge must:

- use `rubric_version = "4b3_opposition_tolerance_v1"`;
- use one `calibration_batch_id` for the whole batch;
- compare every ruler against the same anchors before finalizing scores;
- score ruler/state tolerance, not only background regime type;
- distinguish direct ruler action, state-aligned action, tolerated harassment, and
  non-state-only intimidation;
- treat absence of criticism/protest complaints cautiously in closed information
  environments;
- explain why each score is not one point lower or higher;
- mark `manual_review_required` when ruler identity, constitutional role,
  emergency context, or attribution to the target ruler is uncertain.

## 1-10 Scoring Anchors

| Score | Anchor |
|---:|---|
| 1 | No meaningful opposition/civic space: opposition victories are impossible or punished; criticism, satire, independent journalism, protest, and civil-society monitoring are systematically criminalized, censored, or crushed. |
| 2-3 | Severe intolerance across several channels: opposition, media, protesters, or NGOs face recurring arrests, violence, bans, closures, smear campaigns, or legal/administrative harassment with impunity. |
| 4-5 | Recurring selective restrictions chill opposition/civic activity, but some criticism, protest, investigative journalism, or civil-society work continues with meaningful risk and uneven remedies. |
| 6-7 | Broad civic space with notable flaws: criticism and protest are usually possible, but there are episodic disproportionate policing, legal threats, media pressure, NGO restrictions, or weak remedies. |
| 8-9 | Strong tolerance: opposition wins and public criticism are generally accepted, independent media/protest/civil society operate freely, and abuses are isolated, remedied, or not attributable to the ruler. |
| 10 | Exemplary tolerance: the ruler actively protects opposition, criticism, satire, investigative journalism, peaceful protest, and civil-society monitoring even when politically damaging. |

## Evidence Requirements

Minimum evidence for a score-bearing record:

- At least one citation.
- Local structured-prior artifact status and summary in `structured_prior_summary`.
- Evidence about target-year or near-period opposition/media/protest/civil-society
  tolerance or restriction.
- Source-mix note explaining whether the record relies heavily on one source type.
- Source-confidence fields on every citation and no sole reliance on low or
  very-low confidence sources for score-bearing claims.
- `run_profile` profiling for every shard, including timing, local evidence reads, Parallel
  call counts, fetch counts, and explicit usage/token unknowns when hidden.
- Explicit caveat when the ruler has limited constitutional power, when no target
  year protest/election/media test occurred, or when COVID/emergency restrictions
  complicate comparability.

Preferred source types:

- local structured datasets: V-Dem expression/association/civil-liberty concepts,
  Freedom House political rights/civil liberties, RSF press freedom, WGI voice and
  accountability/rule of law, and related structured priors where locally
  available. Do not re-fetch these from the web for numeric/structured values;
  use external pages only for ruler-specific narrative, legal, media, protest, or
  contradiction-resolution detail;
- election observers and election commissions when opposition victories or losses
  are relevant;
- courts, legal dockets, NGO-law records, media-regulator actions, and official
  parliamentary or human-rights institutions;
- HRW, Amnesty, CPJ, RSF narrative reports, Freedom House narrative reports,
  CIVICUS, International IDEA, IFES, ICG, local credible NGOs, and other reputable
  civil-society reports;
- reputable local/international media for chronology, attribution, and specific
  incidents.

## Bias And Comparability Checks

The judge must complete the common bias checks in `answer_payload.calibration`.
For `4B.3`, interpret them this way:

- `visibility_bias_check`: explain why open-society reporting volume did not
  overstate intolerance relative to closed regimes.
- `repression_silence_check`: explain whether missing protest, media, NGO, or
  opposition complaints reflect genuine tolerance or fear/censorship.
- `population_scale_check`: separate isolated incidents in large/open societies
  from nationwide chilling patterns.
- `source_type_check`: explain reliance on structured priors, NGOs, courts,
  official bodies, media, or observer reports.
- `recency_check`: distinguish target-year actions from inherited or later
  repression/tolerance patterns.
- `subagent_calibration_check`: compare the ruler to adjacent high, mid, and low
  tolerance cases in the batch.

## Required Calibration Values

Use the common required fields from
[`../cited-evaluation-calibration.md`](../cited-evaluation-calibration.md).

Question-specific defaults:

- `rubric_version`: `4b3_opposition_tolerance_v1`
- `severity_band`: one of `none`, `isolated`, `recurring`, `widespread`,
  `systematic`, `mass`
- `state_responsibility`: one of `direct`, `state_aligned`, `tolerated`,
  `failed_to_prevent`, `non_state_only`, `unclear`
- `accountability_level`: one of `strong`, `partial`, `weak`, `none`,
  `perpetrator_impunity`, `state_policy`

Question-specific additional calibration fields:

- `tolerance_status`: one of `protected`, `mostly_tolerated`,
  `selectively_restricted`, `recurring_repression`, `systematic_repression`,
  `no_meaningful_space`, or `unclear`.
- `remedy_or_accountability_status`: one of `effective`, `partial`, `weak`,
  `none`, `state_policy`, `not_applicable`, or `unclear`.
- `opposition_tolerance_channels`: list of channels such as
  `opposition_victories`, `criticism_or_satire`, `investigative_journalism`,
  `protest`, `civil_society_monitoring`, `media_pressure`,
  `legal_or_administrative_harassment`, `security_force_intimidation`,
  `internet_or_information_controls`, `none_found`, `not_applicable`, or
  `unclear`.

## Smoke-Test Ruler Set

Use these 2020 anchors to sanity-check the batch ordering:

| Ruler | Country | Year / period | Expected role in calibration |
|---|---|---:|---|
| Xi Jinping | China | 2020 | low-tolerance / no meaningful civic-opposition space anchor |
| Alexander Lukashenka | Belarus | 2020 | protest/opposition/media repression anchor |
| Vladimir Putin | Russia | 2020 | systemic pressure on opposition/media/civil society anchor |
| Recep Tayyip Erdoğan | Türkiye | 2020 | recurring media/civil-society/opposition pressure concern |
| Narendra Modi | India | 2020 | contested middle case with protest/media/civil-society concerns |
| Viktor Orbán | Hungary | 2020 | EU member middle-low case with media/NGO pressure concerns |
| Jair Bolsonaro | Brazil | 2020 | open-system stress test with media/civil-society/protest conflicts |
| Donald Trump | United States | 2020 | open-system stress test with opposition/protest/media pressure claims and institutional resistance |
| Jacinda Ardern | New Zealand | 2020 | high-tolerance anchor |
| Angela Merkel | Germany | 2020 | high-tolerance anchor |

## Acceptance Checklist

- Local structured-prior artifacts exist before internet research and have explicit
  `evidence_found`, `no_evidence_found`, `not_applicable`, or `error` handling.
- Researchers read `docs/methodology/local-first-researcher-guide.md` and use the
  local-first order before any external search.
- Researchers use only Parallel Search plus allowed exact-URL fetching in this
  environment; forbidden search/browser alternatives are not used.
- Research records include citations, source roles, source-confidence fields, and
  target-period caveats.
- Research shards include `run_profile` profiling.
- The watchdog validates every shard output before judge scoring.
- Every score-bearing record includes `answer_payload.calibration`.
- Scores distinguish ruler tolerance from generic democracy quality.
- Identity, constitutional-role, and emergency/COVID caveats are preserved.
- Bias checks are specific, not boilerplate.
- Contrary evidence and remedies are preserved.
- The guide is updated after the 2020 run.
