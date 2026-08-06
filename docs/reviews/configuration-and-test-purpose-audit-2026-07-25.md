# Configuration And Test-Purpose Audit

Date: 2026-07-25

## Conclusion

The repository is not yet fully configuration-driven. It has good configuration
patterns in the conversational collector, source registries, workflow YAML, and JSON
question catalogue, but several research prompts and question copies remain embedded
in Python. The test suite also contains a mixture of strong behavioral tests and
literal-prose assertions. The latter must not be used to compensate for duplicated
configuration.

This audit changes the governing rule immediately: production and tests both consume
one versioned source of research-changing values. Tests validate code behavior around
that source; they do not maintain another expected copy.

## Inventory

Static inspection covered all 230 `test_*.py` files and all Python files under
`src/leaders_db/`.

- 3,405 test functions and 11,875 assertions were inventoried.
- 1,223 assertions use literal string membership. Most exercise serialized outputs,
  CLI behavior, attribution requirements, parsing, or safety boundaries; this pattern
  is nevertheless a review signal rather than proof of value.
- 119 test files mention or read documentation. Normative attribution drift checks are
  required; mutable editorial-document mirrors are not.
- Five source-AST tests enforce deliberate import-isolation boundaries. These test an
  architectural behavior and are not ordinary prose checks.
- The research/runtime inventory found configuration-backed conversational prompts,
  but also hard-coded prompt builders in `research/`, `hybrid_experiment/prompts.py`,
  reviewer continuation, formatter, and judge modules.
- The ruler-quality detailed questions exist in JSON but are also copied into
  `research/registry.py`; this is a shadow configuration.

## Immediate corrections

- Removed the production-document test that pinned eight chapter-guide prose layouts.
  Replaced it with a synthetic behavioral test of the three supported guide-section
  headings: researcher guidance is extracted while lens and judge sections are not.
- Reduced the chapter-prompt test from an editorial checklist to selected-input,
  chapter-isolation, machine-contract, resource-interpolation, and size-bound behavior.
- Removed pytest parsing of methodology Markdown and guide prose. Runtime registry and
  executable question JSON still have a legitimate equality invariant until the
  registry consumes that JSON directly.
- Replaced exact editorial examples in the layered-table renderer test with selection,
  ordering, and sibling-exclusion behavior.
- Removed fixed catalogue counts, manifest counts, prompt-version text, lens titles,
  and prompt-size expectations from the newly touched tests. Those tests now derive
  their subjects and expected catalogue values from production configuration, or
  exercise a deliberately small synthetic input.
- Made `questions.json` the runtime source for all 1B–8B detailed question text and
  registry metadata in `research/registry.py`; the registry no longer carries those
  eighty prose copies.
- Moved the complete active chapter-researcher prompt to the versioned
  `chapter_research_prompt.json`. Runtime code supplies only interpolation values and
  rejects a template whose placeholder contract is incomplete or unknown.
- Moved the hybrid experiment's production-file fingerprint list to
  `hybrid_baseline_manifest.json`; its test verifies populated hashes without
  shadowing the configured list or its length.

## Tests that remain justified

- Input validation, transformations, scoring formulas, provenance, missingness,
  database persistence, lease fencing, artifact hashes, and public serialization.
- Security and isolation boundaries, including no-network/no-shell paths and import
  isolation.
- Exact source attribution wording, because repository rule 15 makes that wording
  normative public output.
- Schema and registry uniqueness when production loads those values.
- Prompt tests limited to interpolation, selected-scope isolation, stable machine
  delimiters, safety boundaries, and configuration version propagation.

## Tests requiring migration rather than blind deletion

Prompt-literal clusters remain in evidence review, notebook continuation, hybrid
experiments, local-prior orientation, and judging. Some protect material safety and
methodology constraints, but they currently do so by pinning prose. As each prompt
moves to JSON, replace those assertions with:

1. configuration schema validation;
2. correct template selection and interpolation;
3. scope and data-minimization checks;
4. machine-contract and safety-boundary checks;
5. version/hash persistence;
6. controlled LLM quality experiments for semantic prompt quality.

## Runtime configuration migration

| Area | Current state | Required migration |
|---|---|---|
| Ruler detailed questions | Complete: registry loads validated JSON text and identity metadata for 1B–8B | Preserve stable IDs and quality-gate future catalogue versions |
| Layer titles/simple questions/categories | Versioned JSON candidate | Keep one validated JSON source; no expected copies in tests |
| Chapter researcher prompt | Versioned validated JSON; runtime interpolates data only | Persist prompt version/hash in every run artifact and quality-gate future edits |
| Reconnaissance/collector prompts | Mostly JSON-backed | Consolidate version metadata and schema validation |
| Evidence reviewer prompts | Python literals | Move to reviewer prompt JSON |
| Continuation/takeover prompts | Python literals | Move to continuation prompt JSON |
| Formatter/dossier prompts | Python literals | Move to formatter prompt JSON |
| Chapter judge prompt | Python literal | Move to judge prompt JSON |
| Hybrid experiment prompts | Python literals | Move to experiment prompt JSON or retire superseded paths |
| Reports and user-facing templates | Mixed Python literals | Externalize only versioned/research-changing templates; ordinary error messages and small UI labels may remain code |

Each migration is a separate rollback-safe commit. A prompt moves only with schema
validation, artifact hashing, behavioral tests, and a preserved predecessor hash.

## Meaning of “hard-coded”

The audit does not classify every literal in a program as configuration:

- **Configuration:** research questions, prompts, source selections, weights, limits,
  thresholds, model choices, cohort membership, and output-changing policy. These must
  be versioned data consumed by production and tests.
- **Protocol and schema:** JSON field names, stable machine delimiters, database column
  names, enum values, and the normative confidence formula. These belong in typed code
  or a schema when they define the interface itself.
- **Test input and expected behavior:** a small invented row, URL, score, or malformed
  payload may be literal when the test creates that exact input and verifies its
  transformation. It must not reproduce mutable production configuration.
- **Ordinary implementation text:** actionable exceptions and internal log labels may
  remain in code unless their wording changes research behavior or is a public,
  versioned output template.

Moving protocol tokens and tiny fixtures into JSON would obscure the software contract
without making runs more configurable. The migration targets values that can change a
research result or operational run.

The question JSON also owns the required chapter IDs and lens-number grid. Runtime
validates the exact generated ID set, so removing a chapter or renaming the same lens
in two related catalogues cannot silently redefine completeness. Tests mutate the
loaded configuration to prove that short chapters, removed chapters, renamed IDs, and
duplicates are rejected; they do not repeat the configured values.
