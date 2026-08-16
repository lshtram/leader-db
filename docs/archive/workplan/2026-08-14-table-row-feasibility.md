# Table-row citation feasibility — 2026-08-14

## Decision

The isolated deterministic representation is **promising** for one bounded quality
comparison. It is not integrated with production and does not authorize broader use.

## Method

The prototype addresses each nonblank physical source line by source ID, extraction-unit
number, Python Unicode-code-point offsets, and UTF-8 SHA-256. It classifies lines with at
least two numeric tokens as candidate table rows and keeps every other line as explicit
context. The classification is a navigation heuristic, not semantic proof.

The test used Labour Force Survey units 236–247 from the frozen Netanyahu acquisition.
Every nonblank source character is covered by exactly resolvable line spans; omitted
characters are only leading/trailing whitespace and line separators. Duplicate, unordered,
nonpositive, boolean, and non-integer unit identities are rejected.

## Measurement

- Source slice: 12 units and 142,433 characters.
- Nonblank characters represented exactly: 38,936 of 38,936.
- Candidate table rows: 820; context lines: 128.
- Largest exact line: 177 characters; no line exceeds 5,000.
- Like-for-like paragraph baseline for the three known comparison passages: 39,620
  characters.
- Three exact data rows: 482 characters.
- Three data rows plus every context line from their source units: 1,866 characters.
- Like-for-like reduction: 95.3%.

The earlier verifier transported 52,723 citation characters, but that total is not used as
the baseline because it includes a different fact set and a duplicate passage.

## Provenance and verification

The machine-readable measurement is at
`research/runs/netanyahu-2023-cost-opt-step10-table-row-feasibility-v1/measurement.json`.
It binds the frozen extraction and predecessor verified-evidence artifact by SHA-256.
Tests reconstruct the extraction hash, predecessor hash, complete coverage totals,
paragraph baseline, exact known rows, context-inclusive size, and reduction arithmetic.

Nine focused row/paragraph tests pass. Scoped Ruff and diff checks pass, and independent
review found no remaining blocker. No model or API call was made.

## Next decision

Run one bounded quality comparison using the same corrected facts. Keep whole-unit fact
discovery, provide exact rows with their context/header lines only at the existing quality
boundary, and stop after one result. Promotion requires complete factual coverage,
unambiguous column interpretation, exact citation integrity, and material request savings.
