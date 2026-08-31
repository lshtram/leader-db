# Table-row question-writer transport — 2026-08-14

## Decision

Task 3 **passed** at the diagnostic question-writer boundary. The writer can opt into an
exact-row projection after reconstructing every row against frozen source units, while
the established whole-unit evidence field remains unchanged and remains the default for
legacy consumers.

## Compatibility design

`EvidenceCitation` now accepts the existing paragraph address or an exact physical table
line address. The line form retains source ID, unit, physical line number, Unicode
code-point offsets, UTF-8 substring SHA-256, and exact excerpt. `BoundEvidence` continues
to require and store its original whole-unit `exact_excerpt` and hash. It additionally
rejects table citations whose source identity or unit range differs from the parent
evidence.

The question writer's default serialization is unchanged. Its explicit compact-table
option requires a map of frozen source units, resolves each cited line again, checks the
stored hash and exact excerpt, and only then omits the duplicate whole-unit excerpt from
the serialized request. Mixed paragraph/row collections, unavailable units, source drift,
or excerpt disagreement stop before model execution.

## Frozen measurement

The gate reused the passing Task 2 result and the preserved corrected baseline record for
`BATCH-0021-R01-E006`. The compatibility migration retained the baseline whole-unit text
byte-for-byte and attached the 38 source, header, population, statistic, and value lines
that passed Task 2. The compact evidence preserves 60.1%, 71.9%, 65.7%, and 49.2%, the
`Total(1)`/rented `Total(2)` distinction, descriptive limitations, and the absence of
ruler-specific causal attribution.

The like-for-like consumer measurement includes the complete writer prompt and response
schema:

- legacy whole-unit request: 148,462 characters and 35,391 estimated input tokens;
- compact exact-row request: 24,983 characters and 9,364 estimated input tokens;
- complete serialized character reduction: 83.2%.

No model call was required. The first diagnostic directory (`...transport-v1`) used the
migrated record for both sides and therefore included row metadata in its nominal legacy
side. It is retained as a superseded immutable diagnostic. The corrected like-for-like
v2 corrected the like-for-like evidence projection but measured tokens without the response
schema. Both are retained as superseded diagnostics. The complete corrected result is
`research/runs/netanyahu-2023-cost-opt-step12-table-row-writer-transport-v3/`.

## Verification and boundary

Focused compatibility, writer, reconstruction, tamper, and transport tests pass; scoped
Ruff and diff checks pass; independent review is clean. This result integrates one
diagnostic consumer only. It does not change whole-unit discovery, automatically enable
compact transport for other consumers, add a model phase, or begin Task 4.
