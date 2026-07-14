# Codex Dossier Worker Pilot — 2026-07-12

## Outcome

Item 4 is operational for bounded ruler-dossier research. The final fresh pilot
used OpenAI Luna for Nikol Pashinyan / Armenia / 2020 / `4B.2` and completed on
its first attempt under the v2 contract.

- Ledger job: `7`
- Evidence records: 6
- Coverage: `partially_covered`
- Scores assigned: none
- Parent Parallel Search: succeeded; artifact and search ID recorded
- Child discovery: none; exact-URL opens only
- Local prior: 17 facts; artifact path and SHA-256 recorded
- Provider/model: `openai-luna-candidate` / `gpt-5.6-luna`
- Exposed usage: 276,023 input + 7,564 output = 283,587 total tokens

Both artifact hashes were independently verified. A read-only evidence QA pass
accepted the dossier for a bounded 4B.2 judge test with explicit temporal-fit,
partial-coverage, and source-diversity flags.

Final verification passed: repository-wide `ruff check .`, focused worker/ledger/
planner/readiness tests, `git diff --check`, the full default `pytest -q` suite
(29 pre-existing slow tests skipped), and the final bounded code review with no
blocker or important finding.

## Failures that improved the contract

Earlier pilots failed safely and published no canonical output:

1. Codex strict-output schema required every property and rejected unrestricted
   objects. The dossier schema now emits the strict Codex variant.
2. Luna used inconsistent evidence-ID namespaces. Every evidence reference now
   shares a constrained type, IDs must be ordered `E001...`, and per-question
   mappings/coverage are cross-validated.
3. The model mistyped immutable run metadata. The parent now stamps identity,
   period, question, provider, and model fields from the claimed ledger job.
4. Child-side general discovery violated the guide after a sandboxed wrapper
   failure. Approved Parallel Search now runs in the parent; child discovery is
   audited and rejected while exact-URL fetches remain allowed.
5. Reviewer-discovered filesystem races led to lease-token-scoped attempt
   directories, fenced publication, orphaning on failed checkpoint, and
   unconditional process-group cleanup.

## Remaining readiness limits

- The final pilot covers one draft-guided question, not the full ruler bank.
- Only 5 of 80 question guides exist and all remain drafts; 75 are missing.
- 283,587 tokens for one ruler/question is not cost-ready. Prompt/context
  compaction, token budgets, and model comparisons are required before scaling.
- The judge must preserve the dossier's partial coverage and near-period evidence
  caveats; absence of direct 2020 evidence is not evidence of restraint.
