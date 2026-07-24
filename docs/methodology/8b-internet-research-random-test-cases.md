# 8B Internet-Research Random Test Cases

This file defines a randomized evaluation set for testing the bounded
`internet-research` protocol against Chapter 8B ruler-effectiveness questions
from [`ranking-evaluation-criteria.md`](ranking-evaluation-criteria.md).

## Randomization method

- Date generated: 2026-06-28
- Random seed: `20260628`
- Sampling frame: curated historical ruler/government cases with target years in
  or near the 1900–1980 range and likely public-source coverage.
- Question assignment: one randomized assignment covering all `8B.1`–`8B.10`
  exactly once.
- Required case tuple: `(country, year, question_id)`.
- `leader_hint` is included only to keep research bounded; the research agent
  must still verify leader/government resolution from sources.

## Test cases

| case_id | country | year | question_id | leader_hint | question text |
|---:|---|---:|---|---|---|
| 1 | Sweden | 1938 | 8B.2 | Per Albin Hansson | Did the ruler translate that program into enacted laws, budgets, appointments, timelines, institutions, regulations, and enforcement mechanisms within actual authority? |
| 2 | Tanzania | 1967 | 8B.3 | Julius Nyerere | Does the ruler mobilize the state apparatus, party, military, bureaucracy, coalition, or ruling network effectively toward the chosen program? |
| 3 | Ghana | 1965 | 8B.9 | Kwame Nkrumah | Does the ruler manage crises and opposition in a way that preserves or advances the regime's chosen objectives, regardless of whether those objectives are morally good? |
| 4 | Japan | 1964 | 8B.7 | Hayato Ikeda | Do outcome indicators move in the direction the ruler claimed to seek, after allowing for realistic lags and external constraints? |
| 5 | Kenya | 1976 | 8B.10 | Jomo Kenyatta | By the end of the relevant period, is the ruler closer to achieving the stated ideological or policy program than at the start, accounting for inherited conditions and external shocks? |
| 6 | Germany | 1954 | 8B.4 | Konrad Adenauer | Does the ruler select and empower people who are capable of executing the program, whether professionals, loyal operators, technocrats, organizers, or coercive administrators? |
| 7 | Egypt | 1956 | 8B.1 | Gamal Abdel Nasser | Did the ruler state or reliably reveal a sufficiently clear program in dated speeches, manifestos, strategies, directives, or formal acts to freeze and test its policy, ideological, power, and international goals? |
| 8 | India | 1951 | 8B.6 | Jawaharlal Nehru | Does the ruler convert declarations into observable implementation rather than leaving goals as slogans, speeches, symbolic gestures, or propaganda only? |
| 9 | Spain | 1959 | 8B.5 | Francisco Franco | Does the ruler maintain internal discipline, coordination, and follow-through across ministries, regions, security forces, party structures, and implementing agencies? |
| 10 | France | 1962 | 8B.8 | Charles de Gaulle | When tactics fail, does the ruler adapt methods, replace ineffective implementers, reallocate resources, or otherwise correct course to keep advancing the program? |

## Protocol expectations for this test set

Each probe should return the structured 8B output fields defined in the
`internet-research` agent protocol:

- `leader_resolution`
- `program_source`
- `implementation_or_outcome_window`
- `rating.score_1_10`, using the project scale where normalized `0.0 → 1` and
  `1.0 → 10` via `round(1 + 9 * normalized)`
- `goal_coverage`, preferably covering the 5-8 most important stated goals for
  the ruler/government period rather than one convenient policy domain
- `verdict`
- `evidence_quality`
- `manual_review_reason`
- `candidate_structured_observation`

The test is successful when the protocol can produce a bounded, source-backed
finding with enough reusable evidence to justify the saved 1..10 rating, without
pretending that broad ideological or historical questions are binary
promise-delivery claims.
