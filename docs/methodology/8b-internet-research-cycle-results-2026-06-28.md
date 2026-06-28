# 8B Internet-Research Protocol Cycle Results — 2026-06-28

Input set: [`8b-internet-research-random-test-cases.md`](8b-internet-research-random-test-cases.md).

The cycle used fresh `internet-research` subagents with the improved 8B output
contract embedded in each prompt. The project-local agent file was also updated,
but opencode must be restarted before that file change is guaranteed to affect
future subagent calls.

## Improved 8B output contract tested

Each probe was asked to return:

- `leader_resolution`
- `program_source`
- `implementation_or_outcome_window`
- `verdict`
- `evidence_quality`
- `confidence`
- `manual_review_reason`
- `candidate_structured_observation`

After reviewing the first cycle, the required output contract was tightened for
future runs:

- Every future 8B probe must include a `rating.score_1_10` on the project's
  prototype 1..10 scale. The scale follows the scorer convention: normalized
  `0.0 → 1`, normalized `1.0 → 10`, and intermediate values are mapped with
  `round(1 + 9 * normalized)`.
- Every general ruler-year conclusion must include a `goal_coverage` matrix,
  preferably the 5-8 most important stated goals for the period. A probe may use
  fewer goals only when the source record clearly contains fewer evaluable goals
  or when the caller explicitly asks for a single-policy probe.
- Goal coverage must not collapse broad effectiveness into one economic metric.
  It should cover the program's actual domains: economic, social,
  institutional/state-building, security/peace, foreign policy, territorial,
  coalition/party, and crisis-management goals as applicable.
- The saved structured observation must be rich enough to justify the score later:
  goal source, baseline/constraint, implementation evidence, outcome evidence,
  side effects or cross-category harms, per-goal score, confidence, URLs, and
  evidence gaps.

Verdict taxonomy:

- `supported`
- `partially_supported`
- `mixed_or_contested`
- `insufficient_evidence`
- `not_applicable`

Evidence-quality taxonomy:

- `high`
- `medium`
- `low`
- `manual_review_required`

## Results summary

| case_id | country | year | question_id | leader/government resolved | verdict | evidence_quality | confidence | manual review? | protocol note |
|---:|---|---:|---|---|---|---|---|---|---|
| 1 | Sweden | 1938 | 8B.2 | Per Albin Hansson / Hansson II coalition | supported | medium | medium | No, caveat only | Worked; party manifesto + budget/law/SOU sources were enough, but no formal coalition agreement found. |
| 2 | Tanzania | 1967 | 8B.3 | Julius Nyerere / TANU government | partially_supported | medium | medium | Yes | Worked for mobilization, but outcomes and coercive/disruptive implementation require review. |
| 3 | Ghana | 1965 | 8B.9 | Kwame Nkrumah / CPP government | mixed_or_contested | medium | medium | Recommended | Worked; short-term consolidation advanced objectives, but 1966 collapse contradicts durable preservation. |
| 4 | Japan | 1964 | 8B.7 | Hayato Ikeda / LDP government | supported | high | high | No | Strong case; official/IMF/World Bank sources support directional outcome movement. |
| 5 | Kenya | 1976 | 8B.10 | Jomo Kenyatta / KANU government | partially_supported | medium | medium | No, caveat only | Worked partially; broad ideological program requires decomposition for scoring. |
| 6 | Germany | 1954 | 8B.4 | West Germany / Konrad Adenauer | supported | medium | medium | No, caveat only | Worked; agent correctly disambiguated FRG from GDR. |
| 7 | Egypt | 1956 | 8B.1 | Gamal Abdel Nasser | supported | medium | medium | No, caveat only | Worked; clear programmatic source found, but not a formal 1956 state manifesto. |
| 8 | India | 1951 | 8B.6 | Jawaharlal Nehru / Congress government | supported | medium | medium | No | Worked; First Five Year Plan gives observable implementation path. |
| 9 | Spain | 1959 | 8B.5 | Francisco Franco | partially_supported | medium | medium | Recommended | Worked for economic/security coordination; thinner for regions/party/agencies. |
| 10 | France | 1962 | 8B.8 | Charles de Gaulle | supported | high | medium | No | Strong high-salience program case: Algeria tactical adaptation through referendums/Évian; confidence normalized from the subagent's non-standard `medium-high` to `medium`. |

## Cycle findings

1. The improved structure helps substantially. The `leader_resolution`,
   `program_source`, and `implementation_or_outcome_window` fields made the
   outputs easier to compare and prevented the probes from collapsing broad 8B
   questions into binary promise-delivery claims.
2. 8B works best when a primary program source exists: Japan's Income Doubling
   Plan, India's First Five Year Plan, Kenya's Sessional Paper No. 10, Ghana's
   Seven-Year Development Plan, Spain's 1959 decree, and France's Algeria
   referendum/Évian trail.
3. Some questions need decomposition before scoring. 8B.5, 8B.9, and 8B.10 are
   broad and often mix short-term execution with long-term outcomes or coercive
   implementation.
4. `manual_review_reason` is necessary even when `manual_review_required` is
   false, because medium-confidence outputs often have useful caveats without
   being blocked.
5. Country/year disambiguation must remain mandatory. Germany 1954 is ambiguous
   unless the probe explicitly chooses West Germany or East Germany.

## Recommended next protocol changes

- Treat `confidence` as one of `high`, `medium`, `low`, or
  `manual_review_required`; avoid non-standard bands such as `medium-high` in
  future prompts.
- Add a `scope` field: `single_program`, `whole_government`, or
  `dominant_program`, so agents disclose whether the finding covers a single
  high-salience program or the whole ruler-year.
- Add `decompose_for_scoring: true|false` for broad questions like 8B.5,
  8B.9, and 8B.10.
- Require a 1..10 rating and a goal-by-goal evidence record for every future
  probe; yes/no labels are not sufficient for project scoring.
- Preserve the 8B ideology-neutral warning in every prompt: execution capacity
  is assessed relative to the ruler's own program, not moral desirability.
