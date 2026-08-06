# Automated chapter-saturation pilot — 2022

## Purpose

Test whether one generic GPT-5.4-mini process can reproduce the breadth and quality of
the earlier manual three-case saturation probe without case-specific directions. The
production 2022 flow was not changed.

## Process tested

Each chapter starts from client-matrix-excluding local priors and its complete chapter
guide. A persistent researcher works in discovery waves. Each wave targets roughly 35
candidates and 20 opened documents, follows several source/query families, opens the
underlying source, and emits validated source-claim records. Python canonicalizes URLs,
deduplicates source-claim keys, measures domains, lenses, and official-source share,
and decides whether another wave is required.

The target is 20–35 useful URLs and at least 10 domains. Counts are not quotas. The run
continues when evidence remains source-concentrated even after the raw URL target is
met. A separate no-search curator then dispositions every record, collapses wire and
institutional families, prefers synthesis over repeated incidents, limits a single
source family to 25% of the shortlist, and checks that official/primary-government
material does not exceed 67% when independent evidence exists. All prompts, raw turns,
validated ledgers, curation decisions, profiles, and resolved controls are retained.

## Results

| Case | Original 2022 URLs | Manual combined | Candidates reported | Opened reported | Raw automated URLs | Final useful URLs | Source families | Dropped in curation | Cost | Research + curation time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Putin 2B | 16 | 27 | 75–80 | 46 | 43 | 34 | 14 | 11 | $0.48 | 18.9 min |
| Biden 5B | 12 | 26 | 148 | 71 | 55 | 30 | 18 | 27 | $0.89 | 33.9 min |
| Tshisekedi 4B | 13 | 21 | 77 | 51 | 39 | 26 | 13 | 15 | $0.78 | 30.1 min |

The final shortlists average 30 useful URLs, compared with 12–16 in the original run
and 21–27 after manual expansion. Total model cost was about $2.15 for the three
chapter cases. Tool calls were 56, 75, and 96 respectively.

## What the controls changed

- Putin's raw 43 URLs included repeated mobilization, annexation, and peace-talk wire
  stories. Curation dropped 11 and retained 34. Four drops were direct duplicate-family
  replacements; the remainder were overlapping strategic commentary or repeated
  mechanisms. The result sits within the manual 35–50 useful-ceiling estimate, allowing
  for the manual estimate's uncertainty.
- Biden initially reached 44 URLs but 75% of its claims were official/primary. The
  process refused to stop, ran an independent-source wave, and reached 55 raw URLs with
  a 63% official/primary share. Post-curation composition was checked again; the final
  30-record set contains 18 official/primary records (60%) and retains independent
  inflation, distribution, household-welfare, and attribution evidence.
- Tshisekedi initially reached 20 URLs but had eight CPJ claims and no 4B.7 mapping.
  Further waves supplied the missing lens and broader local/official/rights material.
  Curation reduced 41 records to 26 and capped the CPJ case-report family at 6/26
  (23.1%). The final count is within the manual 25–35 ceiling.

## Assessment

The generic process reproduced and modestly exceeded the manual probe's useful
evidence breadth in all three cases. It did not achieve quality merely by increasing
search calls: the first raw results contained substantial same-story, same-mechanism,
or same-institution repetition. The decisive improvement was a measured loop:
discovery, deterministic accounting, composition-triggered gap search, then strict
no-search family curation.

The test also corrects the earlier idea that one universal two-wave target is enough.
Putin needed two waves, Biden needed a third because of source composition, and
Tshisekedi needed three because of concentration and missing coverage. The controls,
not case-specific prompts, selected those paths.

## Recommendation before production replacement

Keep this implementation isolated for now. The next gate should run the same process
unchanged on five complete rulers or a stratified 12–16 chapter sample, including a
closed information environment and a genuinely sparse historical case. Promotion
should require:

1. 20–35 curated useful URLs normally, with explicit credible scarcity below 20;
2. at least 10 useful source families where the source landscape permits;
3. no family above 25% after curation without an explicit scarcity exception;
4. official/primary share at or below 67% when independent sources exist;
5. all ten lenses mapped or an explicit evidence gap, without padding;
6. post-curation duplication and composition checks, not raw URL counts alone;
7. a ruler-level cost projection below the agreed budget before replacing the 2022
   production flow.

The main unresolved risk is cost scaling across eight chapters. This pilot cost only
$0.48–$0.89 per chapter; naive multiplication gives roughly $3.8–$7.1 per ruler before
cross-chapter reuse. A full-ruler pilot is therefore required to measure reuse and
determine whether the process can stay near the $5 mean-cost objective.
