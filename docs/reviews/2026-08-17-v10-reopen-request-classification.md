# V10 reopen-request classification

## Purpose

This is a zero-model-call diagnosis of the accepted evidence reopen requests in the
immutable `netanyahu-2023-integrated-luna-sol-v10` writing artifacts. It determines where
the missing material originated before another release spends writing or review quota.
It does not change v10 or decide that every requested item should be promoted.

## Result

The 80 frozen answers contain 72 accepted reopen requests across 56 questions. They name
60 distinct evidence records. All 72 have the same structural classification:

- the evidence record exists in the frozen 786-record dossier;
- the record is routed to the exact question that requested it;
- the record appears in that question's compact candidate index;
- the record was not selected as required exact evidence;
- the writer therefore could inspect its summary but could not cite or treat its facts as
  established.

There are no requests for an unknown evidence ID and no requests that require new internet
research. This is an evidence-selection/completion defect, not a corpus-collection defect
and not a failure to disposition evidence that was already required.

## Distribution

| Chapter | Answers with requests | Requests |
|---|---:|---:|
| 1B | 5 | 7 |
| 2B | 8 | 11 |
| 3B | 10 | 12 |
| 4B | 7 | 10 |
| 5B | 7 | 9 |
| 6B | 6 | 7 |
| 7B | 7 | 9 |
| 8B | 6 | 7 |
| **Total** | **56** | **72** |

The requests are not confined to weak or remote candidates. Every requested item is
explicitly routed to its question. In the routed-candidate order, 37 of 72 requests are in
the first 15 and 47 are in the first 20; the median rank is 15. The range is 2 through 118.
The set is predominantly adverse evidence: 57 adverse, 13 mixed, one favorable, and one
context item. It includes records from the State Comptroller, UN bodies, the ICC, the U.S.
Department of State, Freedom House, the Bank of Israel, the Knesset, major news agencies,
research institutes, and three Wikipedia records.

Ten evidence IDs were requested for more than one question. Two were requested three
times (`BATCH-0002-E016` and `BATCH-0009-E015`); eight were requested twice. This leaves
60 distinct records behind the 72 question-specific requests.

## What is established and what remains a judgment

The structural diagnosis is conclusive: selection omitted all 72 from exact evidence.
The writer described each as potentially material, but that statement is not an
independent adjudication. Some records are direct, target-period, ruler-attributed evidence;
others are inherited context, later retrospective findings, commentary, or duplicative
corroboration. Automatically promoting every request would turn Luna's caution into the
scientific selection rule and could substantially enlarge already large question packets.

The next contract therefore needs an explicit completion decision before writing:

1. inspect each proposed exact-evidence addition against the question, its existing exact
   evidence, period fit, ruler attribution, source authority, polarity, and limitations;
2. accept only additions that introduce a materially distinct point or materially improve
   authority, attribution, period, balance, or confidence;
3. persist accepted and rejected dispositions with reasons and input hashes;
4. build a completely fresh release from the accepted set;
5. keep v10 immutable and do not treat the completion decision as another return in its
   exhausted failed-run lineage.

## Reproduction

The counts were reconstructed directly from the eight frozen `question-packages/*/package.json`
files and eighty `question-writing/*/questions/*/accepted-output.json` files. For each
request, the check required the evidence ID to be absent from `priority_evidence`, present
in `coverage.reopenable_evidence_ids`, present in `candidate_index`, and to include the
requesting question in the candidate's `question_ids`. All 72 passed those checks.

No model call, API key, external search, or mutation of a run artifact was used.
