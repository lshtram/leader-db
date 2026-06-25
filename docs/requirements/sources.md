# Requirements — Unified Source System

This document defines testable requirements for the future `leaders_db.sources`
subsystem. It complements [`../architecture/sources.md`](../architecture/sources.md)
and the core project requirements in [`core.md`](core.md).

The requirements below apply to the new clean source architecture. Existing
prototype code under `src/leaders_db/ingest/` is legacy unless explicitly migrated.

---

## 1. Scope

- **SRC-SCOPE-001:** The system shall provide one unified public source interface
  for every current and future data source.
- **SRC-SCOPE-002:** The unified source interface shall support local files, API
  caches, manually staged bundles, document sources, derived indicators, and
  validation-only sources.
- **SRC-SCOPE-003:** New source work shall be implemented under
  `src/leaders_db/sources/`, not by adding new source modules to the legacy
  `src/leaders_db/ingest/` subsystem.
- **SRC-SCOPE-004:** The legacy ingestion subsystem may remain available during
  migration, but shall not be the target interface for future source work.

---

## 2. Source Identity and Descriptor

- **SRC-ID-001:** Each source shall have a stable `SourceId.slug`.
- **SRC-ID-002:** The source slug shall match the source registry key, raw-data
  folder, processed-data folder, manifest source id, and attribution entry unless
  a documented alias is provided.
- **SRC-ID-003:** Each source shall expose a `SourceDescriptor` containing display
  name, source type, default version, supported observation families, coverage
  hint, attribution key, and manual/network requirements.
- **SRC-ID-004:** Source descriptors shall be queryable through the central source
  registry.

---

## 3. Request Scoping

- **SRC-REQ-001:** Each source run shall accept a single `SourceIngestRequest`.
- **SRC-REQ-002:** `SourceIngestRequest` shall support source id, years,
  countries, leaders, raw root, processed root, metadata root, DB URL/session,
  source version, run id, dry-run mode, overwrite mode, cache policy, and output
  formats.
- **SRC-REQ-003:** `years=None` shall mean all available years in the source, not
  the current year.
- **SRC-REQ-004:** Source adapters shall apply requested year, country, and leader
  filters where the source has those dimensions.
- **SRC-REQ-005:** If a source cannot support a requested filter, it shall emit a
  structured warning or validation error rather than silently ignoring the filter.
- **SRC-REQ-006:** A source adapter shall not hardcode project-root paths when a
  request-scoped root or DB URL/session is provided.
- **SRC-REQ-007:** `dry_run=True` shall not mutate the filesystem or database.
- **SRC-REQ-008:** Network-capable sources shall obey the request cache policy.
- **SRC-REQ-009:** Unsupported source-version requests shall fail readiness with
  an actionable error.

---

## 4. Source Lifecycle

- **SRC-LIFE-001:** Each source shall support the lifecycle:
  `check_ready -> read_raw -> transform -> validate -> persist -> manifest`.
- **SRC-LIFE-002:** `check_ready` shall validate required raw assets, metadata,
  checksums where available, license/attribution fields, source version, manual
  approval markers, and request validity before parsing raw payloads.
- **SRC-LIFE-003:** `read_raw` shall read raw assets without modifying them.
- **SRC-LIFE-004:** `transform` shall convert raw payloads into normalized
  observations and shall attach raw locators and transform locators.
- **SRC-LIFE-005:** Shared validation shall reject or warn on missing required
  fields, duplicate observation ids, missing provenance, missing attribution,
  invalid values, unsupported filters, and silent stale/proxy behavior.
- **SRC-LIFE-006:** Shared persistence shall own processed file writes, DB writes,
  idempotency behavior, and manifest writes unless an exception is documented and
  reviewed.
- **SRC-LIFE-007:** The runner shall call lifecycle steps in a fixed order.

---

## 5. Normalized Observations

- **SRC-OBS-001:** Every source shall emit `NormalizedObservation` records as its
  evidence output.
- **SRC-OBS-002:** Each normalized observation shall include source id,
  observation id, observation family, indicator code, value, value type, source
  version, raw locator, transform locator, quality flags, and warnings.
- **SRC-OBS-003:** Country-year observations shall include year and country code.
- **SRC-OBS-004:** Leader-level observations shall include leader id or leader
  name where available, and shall preserve ambiguity flags where identity is not
  deterministic.
- **SRC-OBS-005:** Source-specific extension fields shall be structured and
  documented per source.
- **SRC-OBS-006:** Observation ids shall be deterministic for the same source,
  source version, indicator, entity scope, and raw locator.
- **SRC-OBS-007:** Missing or invalid raw cells shall not be silently converted
  into numeric values.

---

## 6. Provenance, Locators, and Attribution

- **SRC-PROV-001:** Every normalized observation shall be traceable to a raw file,
  API record, cached response, document page, table cell, HTML selector, JSON
  pointer, or equivalent source locator where possible.
- **SRC-PROV-002:** Each raw asset shall carry an asset id, source id, media type,
  path or URL, source version, retrieval timestamp where applicable, and checksum
  where available.
- **SRC-PROV-003:** Raw assets under `data/raw/<source>/` shall never be modified
  in place by source ingestion.
- **SRC-PROV-004:** Every manifest shall include normative source attribution.
- **SRC-PROV-005:** Public outputs shall consume attribution from the source
  attribution contract, not from ad hoc adapter strings.
- **SRC-PROV-006:** The client matrix shall never be represented as an evidence
  source. If included in the source registry, it shall be marked `validation_only`.

---

## 7. Coverage, Missingness, and Historical Behavior

- **SRC-COV-001:** Each source shall declare a coverage hint and shall report
  actual run coverage in its manifest.
- **SRC-COV-002:** Out-of-coverage year requests shall emit zero observations for
  those years and a structured warning unless an explicit derived-source rule is
  documented.
- **SRC-COV-003:** A source shall not silently stale-fill or proxy-fill from a
  different year.
- **SRC-COV-004:** If a documented proxy/derived rule exists, the observation
  shall carry quality flags and provenance for the source year and derived rule.
- **SRC-COV-005:** Missingness reasons shall be explicit: missing raw, missing
  metadata, country absent, year absent, indicator null, unsupported filter,
  manual gate, network/cache unavailable, or source not implemented.

---

## 8. Persistence and Manifests

- **SRC-PERSIST-001:** A successful non-dry-run source run shall write processed
  observations under `data/processed/<source>/`.
- **SRC-PERSIST-002:** Parquet shall be the default canonical processed format;
  CSV may be emitted as an optional audit-friendly mirror.
- **SRC-PERSIST-003:** A successful non-dry-run source run shall write an
  immutable manifest under `data/processed/<source>/`.
- **SRC-PERSIST-004:** Manifests shall include request summary, run id, source
  version, raw assets, output assets, observation count, coverage, warnings,
  attribution, adapter version, content hash, and idempotency key.
- **SRC-PERSIST-005:** DB writes shall be idempotent for a stable request scope.
- **SRC-PERSIST-006:** Re-running the same source request shall not duplicate DB
  `source_observations` rows.
- **SRC-PERSIST-007:** Corrective reruns with country/year filters shall not delete
  observations outside the requested scope.

---

## 9. Registry and CLI

- **SRC-REG-001:** The new source system shall provide a central static registry
  before any plugin system is considered.
- **SRC-REG-002:** The registry shall support listing source descriptors and
  retrieving adapters by source id.
- **SRC-REG-003:** New source CLI commands shall use the central registry, not the
  legacy `STAGE2_ADAPTERS` table.
- **SRC-REG-004:** The registry shall reject a duplicate
  `SourceId.slug` registration with `ValueError`. Registering the same slug
  twice is a programming error and MUST NOT silently overwrite the previous
  adapter; the `ValueError` message shall name the offending slug so the
  caller can fix the wiring before the runner dispatches a request.
- **SRC-CLI-001:** The CLI shall support source listing, describing, readiness
  checks, ingestion, manifest inspection, and evidence queries.
- **SRC-CLI-002:** Source CLI commands shall expose request-scoping flags for
  years, countries, leaders, roots, DB URL, dry-run, overwrite, cache policy,
  source version, and output formats.
- **SRC-CLI-003:** Legacy CLI commands may remain temporarily but shall be
  documented as legacy once the new CLI is available.

---

## 10. Evidence Query Interface

- **SRC-QUERY-001:** Downstream scoring, validation, manual-review, and report
  code shall access source evidence through an `EvidenceRepository` interface.
- **SRC-QUERY-002:** Evidence queries shall support filtering by source,
  observation family, indicator, year, country, and leader.
- **SRC-QUERY-003:** Evidence query results shall be able to include raw locators,
  warnings, quality flags, manifests, and attribution.
- **SRC-QUERY-004:** Evidence queries shall not rerun ingestion.
- **SRC-QUERY-005:** Evidence queries shall not read raw files directly except in
  explicitly documented diagnostic tooling.
- **SRC-QUERY-006:** The source system shall expose a concrete in-memory
  `InMemoryEvidenceRepository` that implements the `EvidenceRepository`
  Protocol so tests, research scripts, and concept-extraction flows can
  query already-materialized evidence without re-running ingestion or
  reading raw files. The implementation lives in
  `src/leaders_db/sources/query.py` and is re-exported from the
  `leaders_db.sources` package root.
- **SRC-QUERY-007:** The in-memory repository constructor shall accept three
  sequences -- `observations`, `manifests`, `attributions` -- and shall
  copy each into an internal tuple so the caller-owned lists are never
  mutated.
- **SRC-QUERY-008:** `query_observations` shall filter by `source_ids`,
  `observation_families`, `indicator_codes`, `years`, `countries`, and
  `leaders`. A `None` filter value shall mean "unfiltered"; an empty
  tuple `()` shall mean "no observations match that dimension". The
  repository shall match `source_ids` against the stored
  `SourceId.slug`, shall match `leaders` against either `leader_id` or
  `leader_name` so callers can query by either dimension until leader
  IDs are stable, and shall preserve the input observation order in
  the result tuple.
- **SRC-QUERY-009:** `get_manifest` shall resolve an exact `(source_id.slug,
  run_id)` lookup when `run_id` is provided; when `run_id` is `None`,
  the repository shall return the stored manifest for the source if
  exactly one exists, and shall raise `KeyError` with an actionable
  message naming the available run ids if multiple manifests exist for
  the same source. A missing manifest shall raise `KeyError` naming the
  source slug and the known run ids.
- **SRC-QUERY-010:** `get_attributions` shall return attributions in the
  order of the requested `source_ids` argument; sources without a
  stored attribution shall be silently skipped (matching the documented
  prior `_FakeEvidenceRepository` contract).
- **SRC-QUERY-011:** The in-memory repository shall never import
  `leaders_db.ingest`, never instantiate `SourceIngestRunner`, never
  call source adapters, never read raw files, and never write
  processed/DB output. Tests shall enforce this boundary via
  monkeypatched `SourceIngestRunner.__init__` + `Path.open` /
  `Path.read_*` sentinels and via the import-boundary submodule list
  in `tests/sources/test_import_boundary.py`.
- **SRC-QUERY-012:** The five `EvidenceQuery.include_*` flags
  (`include_raw_locators`, `include_warnings`,
  `include_quality_flags`, `include_attribution`,
  `include_manifests`) are advisory in the in-memory implementation:
  the repository always returns the full stored observation. The
  flags exist on the contract so a future materialization step or
  persistence-backed repository can honor them without changing the
  `EvidenceRepository` surface.

---

## 10A. Semantic Concepts

- **SRC-CONCEPT-001:** The source system shall expose stable semantic concept
  keys for common cross-source indicators needed by analysts/scorers, starting
  with `gdp_per_capita`, `population`, and `gdp_total`.
- **SRC-CONCEPT-002:** Concept mappings shall preserve source-specific
  `NormalizedObservation.indicator_code` values; concepts are aliases or recipes
  over observations, not replacements for adapter indicator catalogs.
- **SRC-CONCEPT-003:** The concept catalog shall support resolving a concept key
  globally or for a specific `source_id`.
- **SRC-CONCEPT-004:** Direct concept mappings shall cover the WDI and Maddison
  economic observations used in the three-source experiment.
- **SRC-CONCEPT-005:** Derivation recipes shall support simple arithmetic over
  same-source, same-entity, same-year normalized observations, including PWT
  `gdp_per_capita = pwt_real_gdp_output_side / pwt_population`.
- **SRC-CONCEPT-006:** Derived concept results shall carry provenance to every
  input observation and shall include an explicit derivation marker or quality
  flag.
- **SRC-CONCEPT-007:** Concept extraction shall operate only on provided
  normalized observations or an evidence-query result; it shall not read raw
  files, call source adapters, rerun ingestion, or write processed/DB output.
- **SRC-CONCEPT-008:** Unknown concept keys and unsupported concept/source
  combinations shall fail with actionable errors rather than returning silent
  empty or guessed mappings.
- **SRC-CONCEPT-009:** Missing, non-numeric, ambiguous, or divide-by-zero inputs
  in a derivation shall produce no derived value for that scope and shall surface
  a structured warning.
- **SRC-CONCEPT-010:** The client matrix shall not be mapped as concept evidence;
  if queried through this layer, it remains validation-only and excluded from
  source agreement.
- **SRC-CONCEPT-011:** Derived concept scope keys shall include ``year`` so a
  single country with multiple valid years produces one derived row per
  country-year, never an ambiguous multi-year aggregate.
- **SRC-CONCEPT-012:** A derived concept shall require both inputs to share the
  same non-empty ``source_version``; missing or mismatched ``source_version``
  shall produce no derived row for that scope and shall surface a structured
  warning. ``source_version`` is checked inside the (country, year) scope, not
  as part of the scope key, so mismatched versions surface the
  missing-source-version diagnostic.
- **SRC-CONCEPT-013:** The catalog shall expose a documented diagnostic helper
  (``extract_concept_result``) that returns the emitted observations PLUS the
  aggregated structured warnings raised by per-row direct-mapping diagnostics
  AND per-scope derived-mapping drop reasons (missing numerator / denominator,
  ambiguous pair, non-numeric numerator / denominator, zero denominator,
  missing / mismatched ``source_version``, defensive year mismatch). The
  convenience ``extract_concept`` wrapper returns only the observations tuple
  so the minimal public API stays flat; both signatures share the same
  underlying extract logic.

---

## 11. Heterogeneous Source Types

- **SRC-TYPE-001:** Local tabular sources shall validate expected files, sheets,
  columns, and source metadata before transform.
- **SRC-TYPE-002:** API sources shall use cache policy and shall record endpoint,
  params hash, cache asset, and retrieval timestamp.
- **SRC-TYPE-003:** Multi-file bundles shall record each file as a raw asset and
  preserve file-level checksums where available.
- **SRC-TYPE-004:** PDF/HTML/document sources shall preserve page/selector
  locators and extraction quality flags.
- **SRC-TYPE-005:** Manual-gated sources shall fail readiness until required local
  metadata and approval markers are present.
- **SRC-TYPE-006:** Derived sources shall declare input source manifests and shall
  not masquerade as raw external evidence.
- **SRC-TYPE-007:** LLM-assisted ambiguity resolution, if added later, shall be a
  separate gated transform or resolver and shall not be part of normal source
  ingestion.

---

## 12. Migration Requirements

- **SRC-MIG-001:** The current prototype ingestion code shall be treated as legacy
  once the new source subsystem begins.
- **SRC-MIG-002:** Existing prototype capabilities shall not be deleted during the
  first new-source-system milestones.
- **SRC-MIG-003:** Old and new source systems shall be separated by package
  boundary and docs.
- **SRC-MIG-004:** Physical relocation of old code to `legacy-src/` or
  `src/leaders_db_legacy/` shall be performed only as a separate reviewed step.
- **SRC-MIG-005:** The first clean source migration shall be PWT, followed by
  Maddison and WDI/WGI unless user priorities change.
- **SRC-MIG-006:** Future unimplemented sources, including Polity V and Leader
  Survival, shall be implemented only in the new source system.
- **SRC-MIG-007:** Importing `leaders_db.sources` shall not import
  `leaders_db.ingest` or any legacy source adapter at package import time.
- **SRC-MIG-008:** Legacy access, when needed during migration, shall go through
  an explicitly named compatibility seam with lazy legacy imports; legacy modules
  and CLI paths shall remain importable and runnable until separately retired.

---

## 13. Testing Requirements

- **SRC-TEST-001:** Every adapter shall pass shared source-contract tests.
- **SRC-TEST-002:** Contract tests shall cover descriptor validity, readiness,
  request scoping, normalized observations, provenance, validation, manifest,
  persistence, idempotency, out-of-coverage behavior, attribution, and dry-run.
- **SRC-TEST-003:** Each adapter shall also have source-specific parser and
  transform tests with small representative fixtures.
- **SRC-TEST-004:** Contract tests shall include filesystem and SQLite boundary
  proof for at least one fixture source.
- **SRC-TEST-005:** API adapters shall have tests proving no hidden network access
  under `offline_only`.
- **SRC-TEST-006:** Optional smoke tests may run against staged real raw data when
  present, but unit/contract tests shall not require large upstream datasets.
- **SRC-TEST-007:** Golden manifests shall normalize dynamic fields such as
  timestamps while checking stable manifest structure and warning behavior.
- **SRC-TEST-008:** Tests shall fail if an adapter bypasses shared runner
  persistence or manifesting rules.
- **SRC-TEST-009:** Initial contract tests shall prove the new package imports
  without importing `leaders_db.ingest`, while `leaders_db.ingest` remains
  independently importable.
- **SRC-TEST-010:** Initial contract tests shall prove source dispatch is routed
  through the new registry seam: the ``SourceIngestRunner`` is wired through
  ``SourceRegistry`` (not the legacy ``STAGE2_ADAPTERS`` table) and drives
  ``check_ready -> read_raw -> transform`` on the adapter it retrieves from
  the registry. The query boundary is the ``EvidenceRepository`` ``Protocol``
  plus an in-memory fake implementation; no runtime query implementation
  beyond the protocol and fake is expected in this slice, and query contract
  tests are PASS-ELIGIBLE.

---

## 14. Defaults for the Next Implementation Phase

The next test-builder/developer phase should target these defaults. They are no
longer open for the initial stubs and contract tests.

- **SRC-DEFAULT-001:** The new package name is `leaders_db.sources`.
- **SRC-DEFAULT-002:** Parquet is the canonical processed observation output;
  CSV is optional/audit-friendly.
- **SRC-DEFAULT-003:** Manifests use immutable `manifest-<run_id>.json`; an
  optional `manifest-latest.json` pointer may be added by shared infrastructure.
- **SRC-DEFAULT-004:** Observation ids are centrally computed by shared source
  infrastructure from source id, source version, indicator code, entity scope,
  and raw locator unless a source has an approved stronger deterministic id.
- **SRC-DEFAULT-005:** Attribution should be exposed through a machine-readable
  registry that is kept in sync with `docs/sources/attributions.md`; adapters do
  not hardcode attribution prose.
- **SRC-DEFAULT-006:** Old CLI commands may coexist temporarily, but new source
  commands use `leaders-db sources ...` and the central registry.
- **SRC-DEFAULT-007:** `client_existing` is outside the evidence source registry
  for the first implementation milestone. If later represented in the source
  registry, it must be `validation_only`.

## 15. Deferred Design Questions

These questions do not block initial stubs/contract tests and must not weaken the
requirements above.

1. Whether to add dedicated DB tables such as `source_runs` or
   `source_manifests`; the first milestone may store manifests as files and use
   existing source/source_observation tables.
2. When to hide or remove old legacy CLI commands after the new source commands
   are available.
3. Whether to physically move old prototype modules to `legacy-src/` or
   `src/leaders_db_legacy/`; this must be a separate reviewed migration.
