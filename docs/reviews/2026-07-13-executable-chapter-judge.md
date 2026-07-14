# Executable Chapter Judge Review — 2026-07-13

## Scope

Implemented the first executable `ruler-chapter-judge` path. A dependency-ready
ledger job now reads every completed ruler dossier for one chapter/year, applies
the planned versioned chapter guide through the configured Codex model profile,
validates the comparative batch, writes an immutable artifact, and atomically
persists one holistic chapter score per ruler while completing the fenced job.

Migration `0008_chapter_judgment_payload.sql` rebuilds `chapter_scores` around a
ruler-year/rubric uniqueness key so co-rulers do not overwrite one another. It
adds run, job, calibration, uncertainty, review, and complete judgment-payload
fields. New writes use stable explicit positive integer IDs, portable boolean and
timestamp columns, and one transaction for all score rows plus job completion.

## Integrity and calibration gates

- The planned rubric version is immutable job input and must still match the
  active guide at execution and persistence.
- Dossier job/run, country, ruler, ruler-year, and period identities must match
  the completed dependency; the target year must fall inside the dossier period.
- Every available dossier is evaluated exactly once. Multi-ruler results must
  calibrate each ruler against at least one other available dossier key.
- Decisive evidence IDs must exist in that ruler's dossier and may not point to
  `discovery_only` material.
- Supported and missing/weak lens lists accept natural language elsewhere but
  retain valid, unique, disjoint chapter IDs.
- Sparse evidence can still yield a score with lower confidence and a wider
  range. Null scores remain reserved for genuine chapter-level insufficiency.
- Expired or superseded lease holders cannot publish any score row. Validated
  orphaned artifacts can be reused on retry without paying for the judge again.

## Review and verification

An independent reviewer found an initial co-ruler overwrite blocker and major
identity, calibration, retry, evidence-role, guide-extension, and migration
issues. All were fixed and re-reviewed. Final independent result: no blocker or
major finding remains.

Verification completed:

- `pytest -q tests/research/test_chapter_judge_worker.py` — green;
- all `tests/research` — green;
- complete default `pytest -q` suite — green, with only expected `--runslow`
  skips;
- `ruff check src tests` — green;
- `git diff --check` — green.

The focused executor smoke uses two co-rulers in one country-year through a fake
Codex boundary. It proves full dossier-to-artifact-to-database wiring, observed
usage stamping, full-envelope persistence, co-ruler separation, stale-lease
rollback, wrong-scope/rubric rollback, cross-ruler calibration, discovery-only
evidence rejection, and policy-approved retry reuse. It does not claim real-model
judgment quality.

## Next readiness item

Add targeted discovery continuation driven by missing chapter themes and source
mix. Then run a small real-model comparative chapter batch before activating any
draft guide or scaling to the full ruler manifest.
