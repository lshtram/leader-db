# Workplan

## Current Status

The project scaffold is in place and Phase C Stage 2 adapter work is in the integration tail. We have:

- A Python package `leaders-db` (installed via `pip install -e .`) with a Typer CLI surface that enumerates all Stage 0–15 commands from [`requirements/top-level-requirements.md`](requirements/top-level-requirements.md) §8.
- The local-first data lake skeleton under `data/raw/<source>/`, `data/processed/`, `data/interim/`, `data/outputs/`, `data/logs/`, `data/metadata/` — one folder per priority source.
- A checked-in SQLite/PostgreSQL-compatible DDL migration (`src/leaders_db/db/migrations/0001_initial.sql`) covering the 11 prototype tables from requirement §7, plus matching SQLAlchemy ORM models.
- The fixed confidence formula `0.35·agreement + 0.25·authority + 0.25·specificity + 0.15·temporal_fit` implemented in `src/leaders_db/score/confidence.py` with band labels and unit tests.
- Strict LLM input/output Pydantic schemas in `src/leaders_db/llm/schemas.py` per requirement §10.
- The client 2023 source bundle moved into `data/raw/client_existing/` with a `metadata.json`.
- **20 reviewed Stage 2 adapters wired into `STAGE2_ADAPTERS`**: `vdem`, `world_bank_wdi`, `world_bank_wgi`, `ucdp`, `sipri_milex`, `sipri_yearbook_ch7`, `pts`, `undp_hdi`, `who_gho_api`, `archigos`, `reign`, `cirights`, `transparency_cpi`, `fas`, `bti`, `rsf_press_freedom`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`, `maddison_project`, `pwt`. The dispatch table is the single registry consumed by `leaders-db ingest-source --source <key>`. PWT 10.01 is the first per-source adapter built on the new shared `SourceAdapter` Protocol (`src/leaders_db/ingest/sources/pwt/`) — see the `pwt` Active blocker entry below for implementation + reviewer follow-up status.
- Source-adapter development for the highest-priority batch has landed; downstream Stage 3–15 work and the next tranche of Stage 2 adapters are the next milestones: **Freedom House FIW 2026 is now staged locally and ready for a future clean `leaders_db.sources` interface**, Polity V still needs source hygiene, and Leader Survival still needs the Demscore email-gated raw data. PWT is now implemented and wired.
- **Visualization workplan approved and Increments 1–4 complete/reviewed (2026-06-23):** `docs/viz-workplan.md` tracks the hybrid `leaders_db.viz` semantic layer + Apache Superset dashboard plan. The core abstraction is `viz_country_year_metrics` + `viz_metric_catalog` plus a generic semantic query layer; `viz_regime_year_population` is explicitly a cached example/proof query, not a bespoke-table pattern for every metric. Increment 3 adds generic agent CLI access through `leaders-db viz-metrics` and `leaders-db viz-query`. Increment 4 adds local Superset compose/config plus `leaders-db viz-build-superset-db`, which builds the read-only SQLite analytic artifact mounted into Superset. The next visualization action is Increment 5: secure client access via Cloudflare Tunnel/Access for `viz.chopsworkshop.com`. **Increment 6 landed 2026-06-25 — investigation-slice vertical slice** (`viz-run-investigation-slice`) wires the updated source architecture (PWT + Maddison + WDI through the unified `SourceIngestRunner`) to a constrained `gdp_per_capita` concept extraction, writes a chart-ready CSV + dependency-free HTML+SVG line chart, and refreshes the Superset SQLite artifact when the canonical core CSV is present (skipping the rebuild cleanly when it is absent). The chart groups by `(country_code, source_id, series_label)` and renders one polyline per indicator-or-recipe series with legend labels `"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"`, so values from different sources or same-source indicators for the same country/year are never chained into a single misleading time-series line. See `docs/viz-workplan.md` §Increment 6 and `docs/testing-guide-viz-superset.md` §Investigation-slice smoke check for the run-book.

The prototype has **not yet** implemented the full Stage 3–15 resolution, scoring, validation, and report-generation pipeline. Phase C currently focuses on source acquisition and Stage 2 normalized observations. **First deterministic scorer landed: `social_wellbeing`** — see the Phase D.1 entry below. **Stage 9 narrow single-country read-only seam landed** — see the Phase D.2 entry. The next round focuses on the evidence-bundle contract for the remaining categories, the Stage 3/4 leader resolver, and the per-category scorers that are not yet implemented.

Concrete numbers (as of 2026-06-20):

- Source-bundle coverage on disk: `vdem`, WDI/WGI evidence, SIPRI, PTS, UNDP HDI, WHO GHO (cache), CIRIGHTS, BTI, RSF (24 annual CSVs), **Freedom House FIW 2026** (`data/raw/freedom_house/` with three user-managed/restricted workbooks; raw database must not be published, derived public results are allowed unless the data itself would become public), Archigos, REIGN, transparency_cpi, fas, wikidata_heads_of_state_government (cache), wikipedia_search_extract (cache), PWT 10.01 (`data/raw/pwt/pwt1001.xlsx` + metadata, **adapter implemented + wired**), and the client bundle. `maddison_project` is implemented and fixture-proven, with the canonical upstream xlsx expected at `data/raw/maddison_project/mpd2023.xlsx` for real production ingestion. The remaining unimplemented/source-interface rows now include: `freedom_house` (raw staged; clean interface planned), `polity_v` (still blocked on source hygiene), and `leader_survival` (blocked on raw data). `pwt` is implemented and wired.
- 0 client 2023 rows ingested into `processed/client_2023_matrix_normalized.csv` (Stage 1 not run).
- 0 leader-year rows in `ruler_years` (Stage 4 not run).
- 1 run config in `configs/prototype-2023.yaml` (target year = 2023).
- Full pytest suite baseline has moved beyond the Phase D.2 number as source adapters and CYC work were added. Maddison-focused verification: `pytest -q tests/test_ingest_maddison_project.py tests/test_paths.py` passes (32 tests), and the non-CYC suite was reported green during the adapter restoration pass.

## Active Phase

**Phase C — data acquisition / Stage 2 adapters.** Phase B is signed off and remains a living source-vetting record. Current source tally after the Phase B addenda + Maddison Project implementation + Phase B Increment B PWT + FIW staging: 20 implemented (the 20 above) + 1 raw-staged/interface-pending (`freedom_house`) + 3 user-managed/blocked (`imf_weo`, `cow_mid`, `nti`) + 1 retired (`cia_world_leaders`) + 2 pending (`polity_v` needs source hygiene; `leader_survival` needs raw data) = 27 total source keys. All 8 rating categories have at least 2 distinct datasets. See [`docs/sources/vetting/report.md`](sources/vetting/report.md). Implementation continues one source at a time.

**Freedom House FIW staging note (2026-06-25):** The FIW 2026 workbooks were moved out of `data/raw/client_existing/` and into the correct external-source folder, `data/raw/freedom_house/`: `Aggregate_Category_and_Subcategory_Scores_FIW_2003-2026.xlsx`, `All_data_FIW_2013-2026.xlsx`, and `Country_and_Territory_Ratings_and_Statuses_FIW_1973-2026.xlsx`. The raw FIW database/workbooks are user-managed and must not be published or redistributed. We can publish derived results based on FIW with proper attribution, but if any use would make the underlying data publicly available, clear that use with Freedom House first. **Planned follow-up for another agent:** build the `freedom_house` interface under the clean `leaders_db.sources` architecture; do not wire a new legacy `src/leaders_db/ingest` adapter.

The older source-by-source backlog and prototype adapter notes remain in [`docs/sources/ingestion-plan.md`](sources/ingestion-plan.md), but future source-interface work is now governed by the clean `leaders_db.sources` architecture in [`docs/architecture/sources.md`](architecture/sources.md) and [`docs/requirements/sources.md`](requirements/sources.md). Treat `docs/sources/ingestion-plan.md` as historical/prototype reference unless a section is explicitly carried forward into the new source-system docs.

**Source-system reset direction (2026-06-23):** The project will define a clean
future source subsystem under `leaders_db.sources` rather than carrying forward
the prototype `ingest` architecture as the long-term foundation. Architecture,
requirements, and a plain-English guide are tracked in
[`docs/architecture/sources.md`](architecture/sources.md),
[`docs/requirements/sources.md`](requirements/sources.md), and
[`docs/sources/system-explained.md`](sources/system-explained.md). Existing source
capabilities remain available as legacy/reference code until migrated.

**Next source-migration path (2026-06-25):** Per user direction, continue clean
`leaders_db.sources` migrations before building the end-to-end investigation
flow. The next source adapter after WGI lands was **V-Dem**; V-Dem has now
landed (see the fifth clean-source migration entry in Done History at the
bottom of this workplan). Together with the already migrated PWT, Maddison
Project, WDI, WGI, and V-Dem adapters, the unified source interface now
covers the four structured source families needed for a complete 1900-2026
inquiry (PWT + Maddison = historical economy; WDI = current economy; WGI =
governance; V-Dem = political regime / repression / corruption / social
well-being). The next major milestone is a **vertical slice of an
investigation** that runs from these source adapters through
`InMemoryEvidenceRepository`, semantic concepts / evidence bundles, scoring
or analysis logic, and a documented answer with provenance. **Active next
action:** design + execute the 1900-2026 vertical-slice investigation
through the migrated source pipeline; defer additional source migrations
(e.g. `transparency_cpi`, `rsf_press_freedom`, `bti`) until the vertical
slice lands unless an interim blocker requires them.

**Source concept-catalog slice landed (2026-06-24) — semantic indicator
catalog under `leaders_db.sources.concepts`.** A real-life
experiment using PWT, Maddison, and WDI through the new source
interface showed that cross-source analysis still required too much
manual indicator-name knowledge (for example WDI/Maddison
GDP-per-capita strings and PWT GDP-per-capita derivation from
output-side real GDP + population). The follow-up slice adds a
small query/analysis-time normalization layer above
`NormalizedObservation` and below scoring/research code so callers
can ask for stable concepts like `gdp_per_capita`, `population`,
and `gdp_total` while preserving source-specific indicator codes
and provenance
([`docs/architecture/sources.md`](architecture/sources.md) §5.8 +
[`docs/requirements/sources.md`](requirements/sources.md) §10A
SRC-CONCEPT-001..010). The package ships under
`src/leaders_db/sources/concepts/` as a focused sub-package
(`__init__.py` re-exports the public API; `_dataclasses.py`,
`_catalog.py`, `_direct.py`, `_derived.py`, and `_api.py` split the
dataclasses, the static catalog data, the direct + derived
extraction helpers, and the public functions respectively; all six
modules stay under the 400-line convention). The slice exposes:

- Stable concept keys (`gdp_per_capita`, `population`, `gdp_total`)
  via `list_concepts()`.
- Source-specific mappings via `resolve_concept(concept_key,
  source_id=None)` covering WDI direct
  (`wdi_gdp_per_capita` + `wdi_gdp_per_capita_ppp_constant_2017`,
  `wdi_population`, `wdi_gdp_current_usd` +
  `wdi_gdp_constant_2015_usd`), Maddison direct
  (`maddison_project_gdp_per_capita_2011_intl`,
  `maddison_project_population_thousands`, and the already-derived
  `maddison_project_gdp_total_2011_intl_derived`), and PWT direct
  + derived
  (`pwt_population`, `pwt_real_gdp_output_side` +
  `pwt_real_gdp_expenditure_side`, and the derived
  `gdp_per_capita = pwt_real_gdp_output_side / pwt_population`
  recipe carrying the `derived_concept` quality flag and the
  `pwt_gdp_per_capita_via_rgdpo_over_pop` recipe key in
  `extension`).
- `extract_concept(observations, concept_key, source_id=None)`
  returns a `tuple[ConceptObservation, ...]` over the provided
  observations only -- the catalog never reads raw files, calls
  source adapters, instantiates `SourceIngestRunner`, or imports
  `leaders_db.ingest`. The boundary is enforced by:
  1. AST inspection of every concept subpackage source file
     (`test_concepts_module_does_not_import_legacy_ingest_at_import`).
  2. The canonical import-boundary submodule list in
     `tests/sources/test_import_boundary.py::test_sources_submodules_do_not_import_legacy_ingest`
     now includes `leaders_db.sources.concepts` and its five
     focused submodules.
  3. A monkeypatched `SourceIngestRunner.__init__` sentinel +
     `Path.open` sentinel inside the catalog tests
     (`test_extract_concept_does_not_call_adapters_or_runners` +
     `test_extract_concept_does_not_read_raw_files`).
- A documented diagnostic helper `extract_concept_result(...)`
  returns a `ConceptExtractionResult` dataclass carrying the
  emitted observations PLUS the aggregated structured
  `SourceWarning` records raised by per-row direct-mapping
  diagnostics (the existing `missing_value` warning) AND
  per-scope derived-mapping drop reasons (the eight new
  per-failure-mode codes: `concept_missing_numerator`,
  `concept_missing_denominator`, `concept_ambiguous_pair`,
  `concept_non_numeric_numerator`,
  `concept_non_numeric_denominator`, `concept_zero_denominator`,
  `concept_missing_source_version`,
  `concept_pair_year_mismatch`). The convenience `extract_concept`
  wrapper returns only the observations tuple so the minimal
  public API stays flat. Per
  `docs/architecture/sources.md` §5.8 / `docs/requirements/sources.md`
  §10A SRC-CONCEPT-013.
- Two actionable custom exceptions:
  `UnknownConceptError` (unknown concept key names the known keys
  in its message) and `UnsupportedConceptSourceError` (unknown
  concept/source pair names the supported sources). Both inherit
  from a common `ConceptCatalogError(ValueError)` base.
- The PWT derived recipe refuses to silently guess: missing
  numerator, missing denominator, ambiguous pair (multiple
  numerators or denominators per scope), year mismatch, non-numeric
  values, zero denominator, NaN / inf denominator, and missing or
  mismatched `source_version` each return zero rows for the
  affected scope rather than emitting a fabricated value. The
  derivation scope key includes `year` (SRC-CONCEPT-011) so the
  same country with valid 2018 AND 2019 inputs yields TWO derived
  rows (one per country-year) instead of collapsing into an
  ambiguous multi-year bucket; `source_version` is checked inside
  the (country, year) scope (SRC-CONCEPT-012) so mismatched
  versions still surface the `concept_missing_source_version`
  diagnostic.
- Direct mappings surface a structured `missing_value` warning on
  rows whose input observation has a missing / non-numeric value
  -- the row itself is emitted with `value=None` and
  `value_type="missing"` (NOT dropped) so the analyst can see the
  upstream gap without losing the observation id / locator. The
  warning message correctly reflects this: "row is emitted with
  value=None and value_type='missing' so the analyst can see the
  upstream gap without losing the observation id / locator".
- `client_existing` is intentionally absent from the catalog; every
  concept raised against the client matrix raises
  `UnsupportedConceptSourceError` per SRC-CONCEPT-010.
- An integration-style test
  (`test_concepts_extract_gdp_per_capita_from_real_runner_output`)
  drives the canonical `SourceIngestRunner` against staged WDI /
  Maddison / PWT bundles and feeds the emitted observations
  through `extract_concept` to prove the catalog wires end-to-end
  with the migrated adapters. 33 focused tests landed in
  `tests/sources/test_concepts.py`.

**Source-system Phase C/D result (2026-06-23):** The Phase B
reviewer-blocker remediation is complete end-to-end. Production code in
`src/leaders_db/sources/registry.py` and `src/leaders_db/sources/runner.py`
now satisfies the full Phase B contract:

- **Duplicate-slug rejection is implemented.** `InMemorySourceRegistry.register`
  raises `ValueError` per `SRC-REG-004`
  ([`docs/requirements/sources.md`](requirements/sources.md) §9). The contract
  test `tests/sources/test_registry.py::test_register_rejects_duplicate_slug_with_value_error`
  passes.
- **`SourceIngestRunner` is wired through the new registry.** The runner is
  constructed as `SourceIngestRunner(registry).run(request)` (single
  `request` argument; the registry seam supplies the adapter). It drives
  the lifecycle in the documented order `check_ready -> read_raw ->
  transform` and returns a `SourceIngestResult`. The contract tests
  `tests/sources/test_runner.py::test_runner_run_dispatches_lifecycle_in_order`
  and `test_runner_does_not_dispatch_through_legacy_stage2_adapters` pass;
  the runner never consults `STAGE2_ADAPTERS` and there is no legacy dispatch
  path.
- **No persistence, DB, or source-migration work landed in this pass.**
  Validation, persistence, manifest generation, and the per-source migration
  inventory in [`docs/architecture/sources.md`](architecture/sources.md) §7
  are explicitly deferred to a later phase. The runner's `SourceIngestResult.manifest`
  is `None` and the no-legacy-dispatch test guards the boundary.

Current verification: `pytest -q tests/sources` passes 290 tests
(`tests/sources/test_contracts.py` 41, `test_import_boundary.py` 5,
`test_legacy_compatibility.py` 7, `test_query.py` 14, `test_query_repository.py` 37,
`test_registry.py` 13, `test_runner.py` 4,
`test_pwt_adapter.py` 21,
`test_maddison_project_adapter.py` 22,
`test_world_bank_wdi_adapter.py` 45,
`test_world_bank_wgi_adapter.py` 23,
`test_vdem_adapter.py` 25,
`test_concepts.py` 33)
with **zero failures** and no NON-PASS-ELIGIBLE entries.
`ruff check src/leaders_db/sources tests/sources
docs/requirements/sources.md docs/architecture/sources.md` is clean.

**Concept-catalog carve-out (2026-06-25):** The diagnostic-helper
refactor (per the reviewer-blocker remediation: year-scoped
grouping, structured ``SourceWarning`` surface, source_version
provenance gate) added a focused sibling helper
`src/leaders_db/sources/concepts/_derived_reasons.py` (~482 lines)
that owns per-scope drop-reason construction for the derivation
helpers. The carve-out is intentional: the verbose diagnostic
messages + structured `context` dicts are part of the documented
"no silent data invention" contract and trimming them would weaken
the forensic value of the diagnostic helper. The rest of the
concept sub-package stays under the 400-line convention
(`_derived.py` 331, `_catalog.py` 337, `_api.py` 303,
`_dataclasses.py` 246, `_direct.py` 160, `__init__.py` 164). The
canonical import-boundary submodule list in
`tests/sources/test_import_boundary.py` and the AST inspection
list in `test_concepts_module_does_not_import_legacy_ingest_at_import`
both now include `leaders_db.sources.concepts._derived_reasons`.

**In-memory `EvidenceRepository` slice landed (2026-06-25) — first
concrete `InMemoryEvidenceRepository` in
`src/leaders_db/sources/query.py`.** The Phase B
`EvidenceRepository` `Protocol` and `EvidenceQuery` dataclass shipped
with a small `_FakeEvidenceRepository` test fake inside
`tests/sources/test_query.py` that returned everything it was given,
recorded every call, and skipped filter semantics. That fake was
adequate to pin the no-ingestion / no-raw-read boundary for the
Protocol surface, but it did not satisfy
[`docs/requirements/sources.md`](requirements/sources.md) §10
SRC-QUERY-002 (filter semantics), §10 SRC-QUERY-003 (include flags),
or any of the documented filter dimensions for real consumers. With
the concept catalog landed (2026-06-24), concept-extraction flows
that source observations from `EvidenceRepository` need a real
filtering implementation behind the Protocol -- not another ad hoc
per-test fake.

The new `InMemoryEvidenceRepository` is the canonical
implementation that downstream consumers can pick up by importing
`from leaders_db.sources import InMemoryEvidenceRepository`. It is:

- **Read-only and deterministic.** The constructor accepts three
  sequences (`observations`, `manifests`, `attributions`) and copies
  each into an internal tuple so the caller-owned lists are never
  mutated. There is no I/O: no raw reads, no adapter calls, no
  `SourceIngestRunner` instantiation, no processed/DB writes, no
  `leaders_db.ingest` import. The repository boundary is enforced
  by (a) the canonical import-boundary submodule list in
  `tests/sources/test_import_boundary.py`, (b) the AST inspection
  list in `test_concepts_module_does_not_import_legacy_ingest_at_import`,
  and (c) monkeypatched `SourceIngestRunner.__init__` +
  `Path.open` / `Path.read_text` / `Path.read_bytes` sentinels in
  the new `tests/sources/test_query_repository.py` tests.
- **Filter-honoring.** Every documented filter dimension is honored
  with the documented semantics: `None` is "unfiltered"; an empty
  tuple `()` is "no observations match that dimension"; the input
  observation order is preserved in the result tuple;
  `source_ids` match against `SourceId.slug`; `leaders` match
  against either `leader_id` or `leader_name` so callers can query
  by either dimension until leader IDs are stable. The four
  `EvidenceQuery.include_*` flags are **advisory** in this slice
  (the repository always returns the full stored observation);
  future persistence-backed repositories can honor them without
  changing the `EvidenceRepository` surface.
- **Manifest-lookup by `(slug, run_id)` with an explicit-`run_id`
  preference.** `get_manifest(source_id, run_id=...)` performs an
  exact `(slug, run_id)` lookup; `get_manifest(source_id)` returns
  the only stored manifest for that source if exactly one exists,
  and raises `KeyError` with an actionable message naming the
  available run ids if multiple manifests exist for the same
  source (the slice prefers explicit ambiguity over silent
  picking). A missing manifest always raises `KeyError` naming
  the source slug and the known run ids.
- **Attribution-lookup preserves request order and skips missing.**
  `get_attributions(source_ids)` returns attributions in the order
  of the requested `source_ids` argument; sources without a stored
  attribution are silently skipped, matching the documented
  `_FakeEvidenceRepository` contract.
- **Concept-catalog integration.** Synthetic WDI / Maddison / PWT
  observations are loaded into the repository, queried via
  `EvidenceQuery`, and the filtered subset is fed into
  `extract_concept` / `extract_concept_result` to verify the
  repository wires end-to-end with the concept layer without
  re-running ingestion. The new
  `tests/sources/test_query_repository.py` carries the focused
  tests for every filter dimension, every manifest/attribution
  error path, every boundary sentinel, and the concept
  integration; `tests/sources/test_query.py` is unchanged
  because the `EvidenceRepository` `Protocol` surface and the
  `EvidenceQuery` dataclass are unchanged.

The slice ships with **zero** changes to the `EvidenceRepository`
`Protocol`, the `EvidenceQuery` dataclass, the contract tests in
`tests/sources/test_query.py`, the concept catalog, or the runner /
registry / adapter paths. It is a pure implementation addition: a
real concrete repository that downstream scorers, validators, and
research tools can depend on, instead of repeating the private test
fake across modules.

**First clean-source migration landed (2026-06-23) — PWT under
`leaders_db.sources.adapters.pwt`.** The PWT 10.01 source is the
first source rebuilt under the new `leaders_db.sources` interface
(docs/architecture/sources.md §7.1 priority 1, docs/requirements/sources.md
§12 SRC-MIG-005). The new package is a thin adapter that
implements the canonical `SourceAdapter` Protocol
(`descriptor` + `check_ready` + `read_raw` + `transform`) and
reuses the legacy reader / transform under
`leaders_db.ingest.sources.pwt` via lazy imports so the package
boundary is preserved (`tests/sources/test_pwt_adapter.py`
asserts `import leaders_db.sources.adapters.pwt` does NOT pull in
`leaders_db.ingest`). The legacy `STAGE2_ADAPTERS["pwt"]` entry
remains unchanged -- the new package exposes explicit
`create_pwt_adapter()` and `register_pwt(registry)` factories and
does NOT auto-register on import (per
docs/architecture/sources.md §10.1). The new adapter honors the
full request scope: `years=` and `countries=` filter the
long-format DataFrame; `leaders=` emits a structured
`UNSUPPORTED_FILTER` warning; `years=2023` (out-of-coverage)
emits zero observations + a `year_absent` warning (no stale-proxy
fill, SRC-COV-002 / SRC-COV-003); a mismatched `source_version=`
(e.g. `"9.99"` against a canonical PWT 10.01 bundle) FAILS
readiness with a structured `unsupported_version` error per
`docs/requirements/sources.md` §3 SRC-REQ-009 -- the runner
raises `RuntimeError` before calling `read_raw` / `transform`,
so the legacy bundle metadata cannot be silently overwritten
by an unsupported version stamp. The runner
also validates the staged bundle's metadata `source_version`: missing or
mismatched metadata versions fail readiness, and the canonical `10.01` value
propagates consistently to `RawAsset.version` and every emitted
`NormalizedObservation.source_version`. The runner
end-to-end contract is proven by
`tests/sources/test_pwt_adapter.py::test_pwt_runner_produces_normalized_observations`
(17 fixture observations round-tripped) and
`tests/sources/test_pwt_adapter.py::test_pwt_runner_does_not_consult_legacy_stage2_adapters`
(monkeypatched `STAGE2_ADAPTERS["pwt"]` tracker is never invoked).
The PWT descriptor exposes `source_id="pwt"`, `default_version="10.01"`,
the canonical PWT 10.01 homepage URL, `attribution_key="pwt"`,
coverage hint 1950-2019, and the `economic_country_year` observation
family. No persistence, manifest, or DB writes landed; the
runner still returns `manifest=None`. The next migration slice
candidates are Maddison (priority 2), WDI (priority 3), WGI
(priority 4), per docs/architecture/sources.md §7.1.

**Second clean-source migration landed (2026-06-24) — Maddison Project Database 2023 under
`leaders_db.sources.adapters.maddison_project`.** Maddison Project is
the second source rebuilt under the new `leaders_db.sources`
interface (docs/architecture/sources.md §7.1 priority 2,
docs/requirements/sources.md §12 SRC-MIG-005). The new package is a
thin adapter that implements the canonical `SourceAdapter` Protocol
(`descriptor` + `check_ready` + `read_raw` + `transform`) and reuses
the legacy reader under `leaders_db.ingest.maddison_project_xlsx`
via lazy imports so the package boundary is preserved
(`tests/sources/test_maddison_project_adapter.py` asserts
`import leaders_db.sources.adapters.maddison_project` does NOT pull
in `leaders_db.ingest`). The legacy `STAGE2_ADAPTERS["maddison_project"]`
entry remains unchanged -- the new package exposes explicit
`create_maddison_project_adapter()` and `register_maddison_project(registry)`
factories and does NOT auto-register on import (per
docs/architecture/sources.md §10.1). The new adapter honors the
full request scope: `years=` and `countries=` filter the long-format
DataFrame; `leaders=` emits a structured `unsupported_filter`
warning; `years=(2023,)` triggers the documented 1-year-gap proxy
mapping (2023 -> 2022) -- every emitted observation carries the
`proxy_year` quality flag plus `requested_year=2023` /
`proxy_source_year=2022` in its `extension` payload, and the
readiness envelope surfaces a structured `maddison_project_proxy_year`
warning naming the mapping so the proxy is never silent;
`years=(2024,)` (or any year beyond 2022) emits zero observations +
a `year_absent` warning -- no multi-year stale-proxy fill
(SRC-COV-002 / SRC-COV-003); a mismatched `source_version=` (e.g.
`"9999"` against a canonical Maddison 2023 bundle) FAILS readiness
with a structured `unsupported_version` error per
`docs/requirements/sources.md` §3 SRC-REQ-009 -- the runner raises
`RuntimeError` before calling `read_raw` / `transform`, so the
legacy bundle metadata cannot be silently overwritten by an
unsupported version stamp. The runner also validates the staged
bundle's metadata `source_version`: missing or mismatched metadata
versions fail readiness, and the canonical `"2023"` value propagates
consistently to `RawAsset.version` and every emitted
`NormalizedObservation.source_version`. The runner end-to-end
contract is proven by
`tests/sources/test_maddison_project_adapter.py::test_maddison_project_runner_produces_normalized_observations`
(21 fixture observations round-tripped) and
`tests/sources/test_maddison_project_adapter.py::test_maddison_project_runner_does_not_consult_legacy_stage2_adapters`
(monkeypatched `STAGE2_ADAPTERS["maddison_project"]` tracker is
never invoked). The Maddison descriptor exposes
`source_id="maddison_project"`, `default_version="2023"`, the
canonical Maddison Project homepage URL,
`attribution_key="maddison_project"`, coverage hint 1-2022, and the
`economic_country_year` observation family. No persistence, manifest,
or DB writes landed; the runner still returns `manifest=None`. The
bundle metadata.json's `checksum_sha256` field accepts BOTH the
flat-string shape (PWT-compatible) and the per-file dict shape
(Maddison's canonical shape) for backward compatibility with bundles
staged before the unified readiness contract. The bundle metadata's
`source_version` field was aligned to the canonical `"2023"` stamp
(matching the legacy DB writer's `version = "2023"` convention) so
the readiness gate matches the staged metadata. The next migration
slice candidates are WDI (priority 3), WGI (priority 4), V-Dem
(priority 5), per docs/architecture/sources.md §7.1.

**Third clean-source migration landed (2026-06-24) — World Bank WDI under
`leaders_db.sources.adapters.world_bank_wdi`.** WDI is the third
source rebuilt under the new `leaders_db.sources` interface
(docs/architecture/sources.md §7.1 priority 3,
docs/requirements/sources.md §12 SRC-MIG-005), after the PWT
10.01 and Maddison Project Database 2023 adapters. The new package
is a thin adapter that implements the canonical `SourceAdapter`
Protocol (`descriptor` + `check_ready` + `read_raw` + `transform`)
and uses a local cache-only reader in the unified package; the legacy
HTTP flow is not used for supported policies.
Legacy imports from `leaders_db.ingest.wdi_io` are limited to lazy
catalog-resolution and attribution compatibility seams, so package
boundary is preserved (`tests/sources/test_world_bank_wdi_adapter.py`
asserts `import leaders_db.sources.adapters.world_bank_wdi` does
NOT pull in `leaders_db.ingest`; the canonical import-boundary
submodule list in `tests/sources/test_import_boundary.py` now
iterates the new submodule as well). The legacy
`STAGE2_ADAPTERS["world_bank_wdi"]` entry remains unchanged -- the
new package exposes explicit `create_world_bank_wdi_adapter()`
and `register_world_bank_wdi(registry)` factories and does NOT
auto-register on import (per docs/architecture/sources.md §10.1).
The new adapter honors the full request scope: `years=` and
`countries=` filter the cache-reader wide-format frame (`year=None`
before filtering); `leaders=`
emits a structured `unsupported_filter` warning; `years=` outside
the documented 1960+ coverage envelope emits zero observations
+ a `year_absent` warning -- no stale-proxy fill (SRC-COV-002 /
SRC-COV-003). A mismatched `source_version=` (e.g. `"World Bank
API v1"` against a canonical WDI bundle whose metadata records
`"World Bank API v2; cached indicator responses"`) FAILS
readiness with a structured `unsupported_version` error per
`docs/requirements/sources.md` §3 SRC-REQ-009 -- the runner raises
`RuntimeError` before calling `read_raw` / `transform`, so the
legacy bundle metadata cannot be silently overwritten by an
unsupported version stamp. The runner also validates the staged
bundle's metadata `source_version`: missing or mismatched metadata
versions fail readiness, and the canonical `"World Bank API v2;
cached indicator responses"` value propagates consistently to
`RawAsset.version` and every emitted
`NormalizedObservation.source_version`. The runner end-to-end
contract is proven by
`tests/sources/test_world_bank_wdi_adapter.py::test_wdi_runner_produces_normalized_observations`
(125 fixture observations round-tripped for the unfiltered run;
61 for `years=(2023,)`, 25 for `countries=('USA',)`, 12 for
`years=(2023,) + countries=('USA',)`) and
`test_wdi_runner_does_not_consult_legacy_stage2_adapters`
(monkeypatched `STAGE2_ADAPTERS["world_bank_wdi"]` tracker is
never invoked). The WDI descriptor exposes
`source_id="world_bank_wdi"`,
`default_version="World Bank API v2; cached indicator responses"`,
the canonical WDI v2 API base URL
(`https://api.worldbank.org/v2/`),
`attribution_key="world_bank_wdi"`, `source_type="api"`,
`requires_network=True`, coverage hint 1960-present, and
supported observation families `("economic_country_year",
"social_country_year")`. The adapter is **offline / cache-first
by default and offline-only in this slice**: for
`cache_policy="offline_only"` / `"prefer_cache"` with explicit
`years=`, missing or incomplete cache fails readiness with a
structured `network_cache_unavailable` / `missing_raw` error
BEFORE `read_raw` / `transform` are called (per
`docs/requirements/sources.md` §11 SRC-TYPE-002 -- API sources
use cache policy). `cache_policy="refresh"` / `"no_cache"` is
NOT supported by the unified WDI adapter in this slice: it
fails readiness with a structured `unsupported_cache_policy`
error because `WDIAdapter.read_raw` never invokes the network
regardless of `request.cache_policy` -- the unified adapter
uses a local cache-only read path (`_read_cached_wdi_responses`
 in `_cache_reader.py`, re-exported from `_transform.py` for
compatibility, and `_enumerate_cache_files` in `_readiness.py`)
 that reads the staged per-(year, indicator) JSON cache files
directly and converts each cached WDI payload into the local
wide-format row layout required by the unified transform layer
for the cache-only contract. For `years=None` the
readiness gate enumerates the cache root and refuses to
dispatch if any discovered cache file is malformed (to preserve
the cache-only contract); for explicit
`years=` the gate refuses missing / incomplete / corrupt cache
BEFORE `read_raw` / `transform` are called (per the
comprehensive cache-policy remediation). The bundle metadata's
`checksum_sha256` is REQUIRED and accepts three shapes: (a)
`null` paired with a non-empty `checksum_note` mentioning the
API / cache / per-response / checksum contract (canonical WDI
shape); (b) a 64-character hex SHA-256 string (flat-bundle);
(c) a per-file dict mapping file names to 64-character hex
SHA-256 strings. Missing `checksum_sha256`, `null` without an
actionable `checksum_note`, or a non-null shape that does not
validate all fail readiness with a structured
`missing_metadata` error. Per-observation `RawLocator` carries
the cache file path + `api_endpoint` template + `json_pointer`
so downstream audit code can resolve the canonical WDI v2 URL
for each (year, indicator, country) row; the pointer is
`"/1/<numeric_index>"` (the data list under `payload[1]` is
indexed numerically in the WDI v2 response), computed by the
`load_wdi_cache_index` helper in `_transform.py` so audit code
can re-parse the cache file and recover the matching record
byte-for-byte; per-row `extension` fields carry the raw WDI
indicator code (e.g. `NY.GDP.MKTP.CD`) as
`wdi_raw_indicator_code`, the cache year, and the canonical
attribution text (Rule #15). No persistence, manifest, or DB
writes landed; the runner still returns `manifest=None`. The
next migration slice candidates are WGI (priority 4), V-Dem
(priority 5), per docs/architecture/sources.md §7.1.

**Planned vertical slice: Country-Year Chronicle (`cyc`).** A new longitudinal country-year profile slice is planned in [`docs/chronicle/workplan.md`](chronicle/workplan.md). It targets `country × year` records for 1900-2026 with ruler, political regime bucket, system/ideology classification, population, GDP, military spend, area, provenance, confidence, and data-quality flags. Increment 0 source inventory / CSV contract findings are complete in [`docs/chronicle/increment-0.md`](chronicle/increment-0.md), and Increment 1 pilot implementation is complete. **Increment 2 is complete (2026-06-21) — Maddison-backed economy fields + provenance-aware ruler resolver (Archigos + REIGN, no client matrix, no LLM) shipped together; see [`docs/chronicle/increment-2.md`](chronicle/increment-2.md). Increment 3 is complete (2026-06-21) — SUN rulers (Wikipedia-anchored curated spell list) + CShapes 2.0 country-area source + conservative `controlled_area_km2` fallback with the explicit `controlled_area_country_only` flag; see [`docs/chronicle/increment-3.md`](chronicle/increment-3.md). Increment 4 (controlled / imperial area design pass) is explicitly DEFERRED per user request 2026-06-21. Increment 5 is complete (2026-06-21) — all-country scope (~200 ISO3 codes derived from V-Dem coverage + pilot historical identity overlay) + condensed CSV export with the documented Increment 5 column set and the four-label `existence_status` (exists / not_formed / split_or_dissolved / out_of_scope_unknown); see [`docs/chronicle/increment-5.md`](chronicle/increment-5.md).** The next CYC action is the controlled / imperial area design pass (originally Increment 4 in the workplan).

**CYC ruler-gap note (2026-06-21):** Per user direction, colonial/dependent country-years are temporarily filled with the literal `colonial-rule` when V-Dem's `v2svindep` independence indicator is `0` and no specific ruler source resolves. This is a coarse placeholder only. The open methodological question — whether these rows should eventually carry local colonial governors, metropole/imperial heads of state, separate `local_ruler` / `sovereign_ruler` fields, or a non-sovereign status rather than a ruler — is deferred and must be resolved before treating colonial-era ruler rows as authoritative.

**CYC population-stabilization note (2026-06-21):** Per user direction, after stabilizing ruler coverage, population coverage was lifted by adding V-Dem fallbacks behind Maddison/WDI. The fallback precedence is: V-Dem `e_wb_pop` (absolute persons), then `e_mipopula` (thousands, converted to absolute persons), then `e_pop` (Fariss et al. latent-variable population estimate scaled from ten-thousands to absolute persons). To reduce remaining missingness below 5%, the Chronicle also uses bounded same-country V-Dem population interpolation for internal gaps up to 75 years and a one-year carry-forward population proxy (for example 2025 from 2024) when no exact value exists; these non-exact fills carry explicit `population_interpolated` or `population_proxy_year_used` flags. Regenerated `all_countries_1900_2026_*` outputs now fill 19,393 of 20,340 existing country-years (95.3%), up from the initial 14,266 (70.1%). Remaining population gaps are 947 rows (4.7%), concentrated in historical/successor or special-scope identities such as `SML`, `ZZB`, `PSG`, `YMD`, `SLB`, `TLS`, `COD`, `STP`, and `COG` that still lack safe structured population rows in the staged sources.

**CYC module-size carve-out (2026-06-21):** Two Chronicle modules are temporarily above the normal 400-line convention while the slice is being stabilized: `src/leaders_db/chronicle/sources.py` (legacy source facade containing V-Dem/WDI/SIPRI/Regime source classes) and `src/leaders_db/chronicle/_wikidata_recent_rulers.py` (single-purpose Wikidata recent-rulers adapter with query/cache/parser/source/loader logic). This is an explicit short-term carve-out, not a precedent for new modules. Follow-up threshold: before adding any new source family or substantial new behavior to either file, split `sources.py` into focused V-Dem/WDI/SIPRI/regime modules and split `_wikidata_recent_rulers.py` into query/cache/parser/source-loader helpers. Small bug fixes and tests may land in place to avoid destabilizing the current population/ruler outputs.

**CYC GDP-stabilization note (2026-06-21):** GDP/GDP-per-capita coverage was lifted by adding an exact V-Dem fallback behind Maddison/WDI. The fallback uses V-Dem `e_gdp` and `e_gdppc` only when both are present for the exact country-year; it does not interpolate or stale-proxy GDP. These are Fariss et al. latent-variable estimates, not Maddison/WDI currency-denominated GDP values, so Chronicle rows carry explicit unit labels: `gdp_unit=vdem_latent_gdp_units`, `gdp_per_capita_unit=vdem_latent_gdppc_units`, and `gdp_per_capita_method=vdem_latent_direct`. Regenerated `all_countries_1900_2026_*` outputs now fill 16,443 of 20,340 existing country-years for GDP and GDP per capita (80.8%), up from 13,544 (66.6%). Remaining gaps are 3,897 rows (19.2%), dominated by 1900-1949 rows, 2024-2025 rows with no staged recent GDP source, and special/historical identities such as `SML`, `ZZB`, `UZB`, `PSG`, `YMD`, `ERI`, `GUY`, `MDV`, `PNG`, `SLB`, `SOM`, `SUR`, `TLS`, and `VUT`.

**CYC WDI-cache GDP improvement note (2026-06-22):** The Chronicle WDI loader now reads `data/raw/world_bank_wdi/coverage_cache/*_1960_2024.json` as exact country-year observations in addition to the processed parquet, lifting GDP coverage from 16,443 / 20,340 = 80.84% to **16,643 / 20,340 = 81.82%** (+200 exact rows, dominated by 2024). Coverage is measured against the Increment 5 relevant denominator (`existence_status == "exists"`; `not_formed` / `split_or_dissolved` rows are excluded by the new `relevant_gdp_coverage` helper in `_economy_fields.py`). The cache loader is bounded to 1960-2024: a 2025/2026 record is dropped on read, so the 2024 → 2025/2026 multi-year stale-proxy is impossible. Source precedence is preserved — Maddison still wins for pre-2023 years when both have a direct hit; for 2023 the WDI cache now wins over the Maddison 2022 1-year-gap proxy (so pilot rows like USA 2023 carry the WDI 21,955,252,291,274 value instead of the Maddison 2022-derived 19,493,170,521,846). The four cache files consumed are `NY.GDP.MKTP.KD_1960_2024.json`, `NY.GDP.MKTP.CD_1960_2024.json`, `NY.GDP.PCAP.CD_1960_2024.json`, `NY.GDP.PCAP.PP.KD_1960_2024.json`; World Bank aggregate / regional codes (`AFE`, `WLD`, `HIC`, etc.) are filtered at the loader. **>90% GDP coverage is NOT reachable from exact local WDI cache + PWT alone** in this pass: 3,697 of the 3,897 remaining missing rows are either (a) 1900-1949 historical years outside the WDI cache window, or (b) Maddison-absent small / successor / colonial identities (`SML`, `PSG`, `YMD`, etc.). No 1900-1950 colonial / historical estimates were added; only exact cache-backed fills were accepted. The 2025/2026 WDI staleness contract is unchanged. The new loader lives in `src/leaders_db/chronicle/_wdi_cache_source.py` (one focused helper module, ~190 lines) so the 760-line `sources.py` carve-out was not enlarged; focused tests landed in `tests/test_chronicle_wdi_cache_source.py` (13 tests) and `tests/test_chronicle_economy_fields.py` (10 new WDI-cache + coverage-metric tests).

### Active blockers

- **`polity_v` — Stage 2 adapter blocked on source hygiene (updated 2026-06-20).** Polity V is ✅ `vetted_ok` in the source-vetting report, and Increment 0 for Country-Year Chronicle observed `data/raw/polity_v/p5v2018.sav` locally. However, there is still **no `data/raw/polity_v/metadata.json`**, and the source remains non-canonical for adapters until metadata captures the source URL, SHA-256 checksum, download date, license note, and `ingestion_status: downloaded`. The `STAGE2_ADAPTERS["polity_v"]` entry stays at `None` until that source-hygiene step is complete.

- **`pwt` — Stage 2 adapter implemented + wired (Phase B Increment B + second-pass reviewer follow-up; updated 2026-06-22).** PWT is ✅ `vetted_ok`; the local raw file is `data/raw/pwt/pwt1001.xlsx` (PWT 10.01, `Data` sheet, 1950–2019 rows for 183 country/economy codes) and `data/raw/pwt/metadata.json` records the canonical SHA-256 (`bf2b66c5...`), source URL, CC BY 4.0 license note, local file name, and `ingestion_status: downloaded`. `STAGE2_ADAPTERS["pwt"]` now points at the per-source `ingest_pwt` orchestrator; the new shared `SourceAdapter` Protocol (`src/leaders_db/ingest/sources/pwt/`) is the reference implementation for the per-source package layout. **Remaining PWT-specific reviewer follow-up:** `registry.ingest_source` still requires an explicit `register('pwt', PWTAdapter())` call (the registry is opt-in by design — the CLI uses `STAGE2_ADAPTERS['pwt']` directly, the registry runner is the shared-protocol seam). The implementation honors every request-scoped field end-to-end (raw_root, processed_root, database_url, year/years, country_filter, parquet_path, catalog_path) with full DB assertion coverage (87 focused tests).

- **`leader_survival` — Stage 2 adapter blocked on Demscore H-DATA v5 manual email/form gate (2026-06-19).** Leader Survival (PLT post-1789) is ⚠️ `vetted_with_caveats`. The Demscore H-DATA v5 (March 2025) dataset requires a manual form/email + gender verification step; no raw file is staged. The placeholder `data/raw/leader_survival/` folder carries only a `.gitkeep`. `STAGE2_ADAPTERS["leader_survival"]` stays at `None` until the data is placed locally.

### Source expansion notes for ranking-question gaps

- **Nuclear / existential-risk source expansion (identified during ranking-criteria review, 2026-06-21).** Current implemented nuclear coverage (`fas` + `sipri_yearbook_ch7`) is adequate for confirmed arsenal/warhead facts but not sufficient for the broader questions now captured in `docs/methodology/ranking-evaluation-criteria.md` chapter 1: nuclear aspiration, uranium enrichment / plutonium separation / fuel-cycle risk, safeguards evasion, treaty posture, nuclear explosive tests, ballistic-missile and delivery-system experiments, miniaturization, and weaponization movement. Candidate source keys to vet/add later: `iaea_safeguards`, `iaea_additional_protocol_status`, `unoda_treaties`, `ctbto_treaty_status`, `ctbto_nuclear_tests`, `nuclear_weapons_ban_monitor`, `csis_missile_threat`, `cns_nti_missile_launches`, `world_nuclear_association_profiles`, and user-managed `nti_country_profiles` if direct scraping remains blocked.
- **Proxy-aggression source expansion (identified during ranking-criteria review, 2026-06-21).** Chapter 2 should not only score direct wars and military spending. It also needs sponsor responsibility for proxy warfare: arms, training, sanctuary, financing, intelligence/logistics, militia enablement, and conflict instigation by states that avoid direct battlefield participation. Current `ucdp` partially captures internationalized conflicts and foreign government involvement; `sipri_milex` does not capture proxy sponsorship. Candidate sources to vet/add later: UCDP External Support Dataset / External Support in Non-State Conflict Dataset, Non-State Actor Dataset, Dangerous Companions / NAGs state-support data, SIPRI Arms Transfers Database, ATT Monitor / national arms-export data, ACLED actor-event data, and selected manual evidence for clandestine or deniable support.

## Phase Order (commit to this)

The work is split into five sequential phases. **Do not start a later phase until the earlier one is complete and reviewed.**

| Phase | Scope | Status |
|---|---|---|
| **A. Infrastructure** | Package, CLI surface, schema, paths, configs, smoke tests, data-lake folders, client bundle moved into `data/raw/client_existing/` with `metadata.json`. | complete (2026-06-17) |
| **B. Source vetting** | For every priority source in §6, probe availability (URL reachable, no login wall, no paywall, license compatible, coverage reaches the target year, format parseable, expected checksum reproducible). Emit `data/outputs/source_vetting_report.{csv,md}` with per-source verdict. Replace "trust the source list" with evidence per source. | complete; living addenda |
| **C. Data acquisition** | Stage 0–2 ingest: `check-source-availability` runner, Stage 1 client validation-reference parser, one Stage 2 adapter per vetted external source. Each adapter writes `data/raw/<source>/metadata.json` and `data/processed/<source>/*.parquet`. Gated on Phase B. | active |
| **D. Testing** | Pytest coverage for every implemented stage including boundary tests that fail when production wiring is removed. End-to-end smoke run on a single country-year (e.g. Mexico 2023). | not started |
| **E. Activation** | Stage 3–15 (country match, leader resolver, indicator extraction, scoring modules, confidence wiring, comparison, manual-review queue, summary report) on the full client 2023 scope. Acceptance per requirement §16. | not started |

## Phase B approach (user feedback, 2026-06-17)

The Phase B plan at [`sources/vetting/plan.md`](sources/vetting/plan.md) is the gate for Phase C. The user has explicitly steered the execution:

- **Manual research first.** The user does not expect a generic probe script to handle every source. For each priority source, the agent actually visits the website, finds the canonical download link, reads the license, and confirms coverage.
- **Per-source custom where needed.** Where a generic probe does not work, the source is researched manually and a per-source custom probe is acceptable.
- **Self-review and fix in place.** Per Always-On Rule #14, the agent reviews its own work and fixes findings before moving on. Serious problems (sources that turn out to be `blocked` with no acceptable substitute, or where the canonical URL has changed in a way that affects downstream code) are escalated to the user.
- **Inline for the first few sources.** The first 3–4 sources are researched inline to build the pattern. After the patterns are clear, subagents may be dispatched in parallel for the remaining sources.
- **Final report location.** The canonical source-vetting report lives at `docs/sources/vetting/report.md` (committed, auditable). A machine-readable copy is written to `data/outputs/source_vetting_report.csv` (gitignored — evidence trail). The MD in `data/outputs/` is gitignored and not load-bearing.
- **Worksheet for in-progress notes.** A working document at `docs/sources/vetting/worksheet.md` captures per-source findings as the agent goes. It is the audit trail of Phase B; the final report is a clean summary derived from it.

## Operational Practice (every task, every phase)

Two project-wide rules govern **every** task in **every** phase:

1. **Cleanup & coherence — no slop, no junk.** After any operation, run the
   cleanup checklist in [`operational-hygiene.md`](process/operational-hygiene.md) §
   "Rule 1". No `TODO(debug)`, no scratch scripts in the project root, no
   commented-out code, no orphan docs/modules/configs, no stale fixtures,
   no `__pycache__` / `.pyc` / log files committed. The project must look
   coherent after every operation, not "at the end".
2. **Full code review after every code-bearing change — fix findings in
   place.** After any module/function/class/fix lands, self-review against
   [`coding-guidelines.md`](process/coding-guidelines.md) and the D2 review
   checklist, run the affected tests + `ruff`, and address findings
   immediately. For non-trivial changes (new modules, schema migrations,
   LLM contract, confidence formula, score modules) route to the `reviewer`
   agent via the project-manager. **Stacking unreviewed code is forbidden**
   — every code-bearing commit must pass review before the next task
   begins. See [`operational-hygiene.md`](process/operational-hygiene.md) §
   "Rule 2".

These rules are normative (AGENTS.md Always-On Rules #13 and #14). They
are not preferences, not "best-effort", not "if there's time at the end of
the project". A change that lands without review or that leaves junk
behind is not a finished change.

## Immediate Next Steps (Phase A → B)

The first build sequence from [`requirements/top-level-requirements.md`](requirements/top-level-requirements.md) §17 is the canonical ordering **for phases C–E only.** Before any of that, Phase B (source vetting) must run.

**Phase A finish line (this phase):**

1. Confirm the data lake folders and SQLite migration with `leaders-db init-data-lake && leaders-db init-db`.
2. Make `pytest -q` and `leaders-db --help` green.
3. Move existing xlsx/docx into `data/raw/client_existing/` and write `metadata.json`.
4. Hand off to Phase B with an explicit source-vetting plan.

**Phase B plan (to be written after Phase A):** [`docs/sources/vetting/plan.md`](sources/vetting/plan.md) will enumerate, for every priority source in §6, a probe checklist (URL reachable, no login wall, no paywall, license compatible, coverage reaches 2023, format parseable, checksum reproducible, known coverage gaps), the verdict field (`vetted_ok` / `vetted_with_caveats` / `blocked` / `replace`), and the report format. No Stage 2 ingest module is written until its source's verdict is `vetted_ok` or `vetted_with_caveats`.

## Scope Baseline

Scope is defined by [`requirements/top-level-requirements.md`](requirements/top-level-requirements.md) and refined in [`requirements/core.md`](requirements/core.md). Architecture lives in [`architecture/overview.md`](architecture/overview.md). The schema is normative in [`architecture/database-schema.md`](architecture/database-schema.md).

## Done History

- **Fifth clean-source migration landed (2026-06-25) — V-Dem v16 under
  `src/leaders_db/sources/adapters/vdem/`.** V-Dem is
  the fifth source rebuilt under the new `leaders_db.sources`
  interface (docs/architecture/sources.md §7.1 priority 5,
  docs/requirements/sources.md §12 SRC-MIG-005), after
  PWT 10.01, Maddison Project Database 2023, World Bank WDI,
  and World Bank WGI. V-Dem is a large local CSV source
  (388MB / 28093 rows / 4618 columns) with `metadata.json`
  and a 26MB zip; the unified adapter is **not** network-backed
  (`requires_network=False`); the descriptor advertises
  `source_type="dataset"`. The new package implements the
  full `SourceAdapter` Protocol (`descriptor` + `check_ready` +
  `read_raw` + `transform`) and reuses the legacy reader /
  transform / catalog under `leaders_db.ingest.vdem_io` via
  lazy imports so the package boundary documented in
  docs/architecture/sources.md §10.1 is preserved; the package
  import does NOT pull in `leaders_db.ingest`
  (`tests/sources/test_vdem_adapter.py::test_vdem_adapter_module_does_not_import_legacy_ingest_at_import`
  + the import-boundary submodule list in
  `tests/sources/test_import_boundary.py`). The legacy
  `STAGE2_ADAPTERS["vdem"]` entry remains unchanged -- the
  new package exposes explicit `create_vdem_adapter()` /
  `register_vdem(registry)` factories and does NOT
  auto-register on import (per docs/architecture/sources.md
  §10.1). The new adapter honors the full request scope:
  `years=` and `countries=` filter the narrow DataFrame on
  the new transform side (the legacy reader returns the
  full frame when called with `year=None`); `leaders=`
  emits a structured `unsupported_filter` warning
  (SRC-REQ-005); `years=(1788,)` or `years=(2026,)`
  (out of coverage) emit zero observations plus a
  structured `year_absent` warning -- no stale-proxy fill
  (SRC-COV-002 / SRC-COV-003). A mismatched `source_version=`
  (e.g. `"9999"` against a canonical V-Dem bundle whose
  metadata records `"v16"`) FAILS readiness with a
  structured `unsupported_version` error per
  docs/requirements/sources.md §3 SRC-REQ-009 -- the runner
  raises `RuntimeError` before calling `read_raw` /
  `transform`, so the legacy bundle metadata cannot be
  silently overwritten by an unsupported version stamp. The
  runner also validates the staged bundle's metadata
  `source_version`: missing or mismatched metadata versions
  fail readiness, and the canonical `"v16"` value
  propagates consistently to `RawAsset.version` and every
  emitted `NormalizedObservation.source_version`. The bundle
  metadata's `checksum_sha256` is REQUIRED and accepts a
  64-character hex SHA-256 string (covers the staged zip,
  NOT the 388MB CSV). The gate validates the metadata shape
  AND, if the zip is staged alongside the CSV, recomputes
  the zip's SHA-256 and compares against the metadata field.
  Missing / malformed `checksum_sha256` fails readiness with
  a structured `missing_metadata` error; a mismatched zip
  SHA-256 fails readiness with the V-Dem-specific
  `vdem_checksum_mismatch` code. The CSV (388MB) is NEVER
  hashed by the unified adapter -- the audit chain is
  preserved via the legacy parquet metadata, the canonical
  attribution text (Rule #15), and the zip-checksum match.
  The runner end-to-end contract is proven by
  `tests/sources/test_vdem_adapter.py::test_vdem_runner_produces_normalized_observations`
  (220 fixture observations round-tripped -- 5 countries
  x 2 years x 22 indicators) and
  `test_vdem_runner_does_not_consult_legacy_stage2_adapters`
  (monkeypatched legacy `STAGE2_ADAPTERS["vdem"]` tracker
  is never invoked). The V-Dem descriptor exposes
  `source_id="vdem"`, `default_version="v16"`, the canonical
  V-Dem DOI homepage URL (`https://doi.org/10.23696/vdemds26`),
  `attribution_key="vdem"`, coverage hint 1789-2025, five
  observation families (`political_country_year`,
  `governance_country_year`, `corruption_country_year`,
  `repression_country_year`, `social_country_year`),
  `source_type="dataset"`, and `requires_network=False`.
  Per-observation `RawLocator` carries the staged CSV path
  + the raw V-Dem column name (e.g. `v2x_polyarchy`);
  `row_number` is intentionally `None` because the legacy
  narrow frame loses the CSV row index through the
  long-to-wide pivot -- the unified transform never
  fabricates locators. Per-observation `extension` carries
  the canonical attribution text (Rule #15), the
  `source_row_reference="vdem:<country_text_id>"` pattern
  (matching the legacy Stage 2 DB writer), the
  `vdem_raw_column`, `vdem_country_id`, `vdem_country_text_id`,
  `vdem_rating_category` (catalog `rating_category`),
  `raw_value` (audit-trail string preserving V-Dem missing
  sentinels like `"-999.0"`), and the `raw_scale` /
  `higher_is_better` / `normalized_scale_target` direction
  hints. The new `VDEM_ATTRIBUTION_TEXT` constant is
  byte-identical to the legacy `VDEM_ATTRIBUTION` constant
  in `src/leaders_db/ingest/vdem_io.py` and to the `vdem`
  section in `docs/sources/attributions.md`;
  `test_vdem_attribution_text_matches_attributions_doc`
  enforces byte-identity (drift guard). 25 focused tests
  in `tests/sources/test_vdem_adapter.py` cover the full
  slice acceptance criteria (descriptor / factory /
  registry / runner / request-scoping / out-of-coverage /
  readiness-failure / checksum-shape / checksum-mismatch /
  correct-zip / canonical-version-propagation /
  V-Dem-specific extension / import-boundary /
  STAGE2_ADAPTERS-no-touch). Module sizes: `__init__.py`
  141 lines, `_descriptor.py` 234 lines,
  `_metadata_validators.py` 325 lines, `_readiness.py`
  307 lines, `_catalog.py` 114 lines, `_missing_values.py`
  118 lines, `_raw_read.py` 160 lines, `_pipeline.py`
  164 lines, `_transform.py` 319 lines, and `adapter.py`
  358 lines; no V-Dem production-module carve-out is
  needed.
  `tests/sources/test_vdem_adapter.py`. **With V-Dem
  landed, the unified source interface now covers the four
  structured source families needed for a complete
  1900-2026 inquiry** (PWT + Maddison = historical economy;
  WDI = current economy; WGI = governance; V-Dem = political
  regime / repression / corruption / social well-being).
  The next major milestone is a vertical slice of an
  investigation that runs from these source adapters
  through `InMemoryEvidenceRepository`, semantic concepts /
  evidence bundles, scoring or analysis logic, and a
  documented answer with provenance. The runner still
  returns `manifest=None`; no persistence, DB writes, or
  manifest writing landed. The package exposes explicit
  `create_vdem_adapter()` /
  `register_vdem(registry)` factories and does NOT
  auto-register on import (§10.1).

- **Sixth clean-source migration landed (2026-06-25) — UCDP GED 23.1 under
  `src/leaders_db/sources/adapters/ucdp/`.** UCDP is the
  sixth source rebuilt under the clean
  `leaders_db.sources` interface (docs/architecture/sources.md
  §7.1 priority 11, docs/requirements/sources.md §12 SRC-MIG-005),
  after PWT 10.01, Maddison Project Database 2023, World Bank
  WDI, World Bank WGI, and V-Dem. UCDP is structurally distinct
  from the prior five clean-source migrations: PWT / Maddison /
  WDI / WGI / V-Dem are country-year tables, while UCDP GED is
  an **event-level** dataset (316,818 events in v23.1). The
  Stage 2 adapter aggregates events to country-year by
  `type_of_violence` (1 = state-based, 3 = one-sided) and the
  cross-border filter (`type=1 AND gwnob.notna()` for the
  internationalized subset) before the long-to-wide pivot. The
  unified transform layer consumes the wide-format country-year
  DataFrame and emits one `NormalizedObservation` per
  `(country_id, year, variable_name)` triple. UCDP is
  local-file only (no HTTP layer in the new package;
  `requires_network=False`); the descriptor advertises
  `source_type="dataset"`. The new package implements the
  full `SourceAdapter` Protocol (`descriptor` + `check_ready`
  + `read_raw` + `transform`) and reuses the legacy reader /
  event-level aggregator under `leaders_db.ingest.ucdp_io`
  and `leaders_db.ingest.ucdp_aggregate` via lazy imports so
  the package boundary documented in docs/architecture/sources.md
  §10.1 is preserved; the package import does NOT pull in
  `leaders_db.ingest`
  (`tests/sources/test_ucdp_adapter.py::test_ucdp_adapter_module_does_not_import_legacy_ingest_at_import`
  + the import-boundary submodule list in
  `tests/sources/test_import_boundary.py`). The legacy
  `STAGE2_ADAPTERS["ucdp"]` entry remains unchanged -- the new
  package exposes explicit `create_ucdp_adapter()` /
  `register_ucdp(registry)` factories and does NOT
  auto-register on import (per docs/architecture/sources.md
  §10.1). The new adapter honors the full request scope:
  `years=` and `countries=` filter the wide-format DataFrame on
  the new transform side (the legacy reader returns the full
  frame when called with `year=None`); the request `countries=`
  filter applies as an exact match against the UCDP
  `country_id` integer (NOT ISO3) -- callers who want to filter
  by ISO3 must use the legacy path or Stage 3 country match to
  resolve first; `leaders=` emits a structured `unsupported_filter`
  warning (SRC-REQ-005); `years=(2023,)` or `years=(1988,)`
  (out of coverage) emit zero observations plus a structured
  `year_absent` warning -- no stale-proxy fill (SRC-COV-002 /
  SRC-COV-003). A mismatched `source_version=` (e.g. `"9999"`
  against a canonical UCDP bundle whose metadata records
  `"GED 23.1"`) FAILS readiness with a structured
  `unsupported_version` error per
  docs/requirements/sources.md §3 SRC-REQ-009 -- the runner
  raises `RuntimeError` before calling `read_raw` /
  `transform`, so the legacy bundle metadata cannot be silently
  overwritten by an unsupported version stamp. The runner also
  validates the staged bundle's metadata `source_version`:
  missing or mismatched metadata versions fail readiness, and
  the canonical `"GED 23.1"` value propagates consistently to
  `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`. **The mandatory
  readiness requirement is on raw-file presence:** the
  gate returns `ready=False` with a structured `missing_raw`
  error when `ged231-csv.zip` is not staged on disk,
  regardless of the metadata's `local_files` /
  `checksum_sha256` shape. The canonical UCDP bundle
  metadata carries `local_files=[]` /
  `checksum_sha256=null` / `ingestion_status="pending"` --
  a deliberately minimal shape so the operator can update
  the metadata once the zip is staged. A metadata-only
  bundle (no staged zip) is intentionally NOT
  runner-ready -- it has value for readiness-only
  inspection (validating metadata shape, schema
  migrations, sanity-checking `expected_local_files`
  annotations) but the runner raises `RuntimeError`
  BEFORE `read_raw` / `transform`. The bundle metadata's
  `checksum_sha256` accepts the canonical empty-bundle
  shape (`null` paired with `ingestion_status="pending"`,
  the staged `data/raw/ucdp/metadata.json` shape) OR a
  64-character hex SHA-256 string (when the zip is staged).
  The gate validates the metadata shape AND, if the zip
  is staged alongside the metadata, recomputes the zip's
  SHA-256 and compares against the metadata field.
  A malformed `checksum_sha256` fails readiness with a
  structured `missing_metadata` error; a mismatched zip
  SHA-256 fails readiness with the UCDP-specific
  `ucdp_checksum_mismatch` code. The zip is hashed only
  for local integrity verification when metadata supplies
  a checksum; the audit chain is preserved via the
  canonical attribution text (Rule #15). The
  readiness-failure tests cover missing `ged231-csv.zip`
  (the `missing_raw` short-circuit, plus the runner-level
  `_SpyUCDPAdapter` proof that the runner raises
  `RuntimeError` BEFORE `read_raw` / `transform`) and
  the canonical UCDP empty-bundle metadata shape
  (`test_ucdp_empty_shape_bundle_is_not_runner_ready` +
  `test_ucdp_metadata_only_without_zip_blocks_runner_short_circuit`).
  The runner end-to-end contract is proven by
  `tests/sources/test_ucdp_adapter.py::test_ucdp_runner_produces_normalized_observations`
  (60 fixture observations round-tripped -- 5 countries x 2
  years x 6 indicators after event-level aggregation of the
  22-event fixture) and
  `test_ucdp_runner_does_not_consult_legacy_stage2_adapters`
  (monkeypatched legacy `STAGE2_ADAPTERS["ucdp"]` tracker is
  never invoked). The UCDP descriptor exposes
  `source_id="ucdp"`, `default_version="GED 23.1"`, the
  canonical UCDP downloads page
  (`https://ucdp.uu.se/downloads/`), `attribution_key="ucdp"`,
  coverage hint 1989-2022, two observation families
  (`international_peace_country_year` for the 4 state-based
  indicators + `domestic_violence_country_year` for the 2
  one-sided indicators), `source_type="dataset"`, and
  `requires_network=False`. Per-observation `RawLocator` carries
  the staged zip path + the catalog `variable_name` (e.g.
  `ucdp_state_based_events`); `row_number` is intentionally
  `None` because UCDP is event-level data and the legacy wide
  frame loses the event row index through the long-to-wide
  pivot -- the unified transform never fabricates locators.
  Per-observation `quality_flags` carries the
  `ucdp_aggregated_from_events` flag so downstream audit code
  can recognize the aggregate locator convention. Per-observation
  `extension` carries the canonical UCDP attribution text
  (Rule #15), the
  `source_row_reference="ucdp:<country_id>"` pattern (matching
  the legacy Stage 2 DB writer), the `ucdp_country_id`,
  `ucdp_rating_category` (catalog `rating_category`),
  `ucdp_raw_column`, `ucdp_filter_logic`, the
  `ucdp_events_total` / `ucdp_events_filtered` (carried from
  `df.attrs` onto every observation), `raw_value` (audit-trail
  string), and the `raw_scale` / `higher_is_better` /
  `normalized_scale_target` direction hints. The new
  `UCDP_ATTRIBUTION_TEXT` constant is byte-identical to the
  legacy `UCDP_ATTRIBUTION` constant in
  `src/leaders_db/ingest/ucdp_io.py` and to the `ucdp` section
  in `docs/sources/attributions.md`;
  `test_ucdp_attribution_text_matches_attributions_doc`
  enforces byte-identity (drift guard). 28 focused tests in
  `tests/sources/test_ucdp_adapter.py` cover the full slice
  acceptance criteria (descriptor / factory / registry /
  runner / request-scoping / out-of-coverage /
  readiness-failure / unsupported-version /
  metadata-only-bundle-not-runner-ready /
  runner-short-circuit-on-missing-zip /
  canonical-version-propagation / ISO3-vs-country-id /
  aggregate-locator-quality-flag / rule-id-pattern /
  indicator-codes / import-boundary /
  STAGE2_ADAPTERS-no-touch). The focused single-source test
  file is `tests/sources/test_ucdp_adapter.py`. Module sizes:
  `__init__.py` 180 lines, `_descriptor.py` 231 lines,
  `_metadata_validators.py` 400 lines, `_readiness.py` 332
  lines, `_catalog.py` 136 lines, `_constants.py` 35 lines,
  `_missing_values.py` 81 lines, `_observation_builder.py`
  249 lines, `_raw_read.py` 208 lines, `_pipeline.py` 197
  lines, `_transform.py` 230 lines, and `adapter.py` 394
  lines; no UCDP production-module carve-out is needed
  (the largest module is the `adapter.py` lifecycle class at
  394 lines, under the 400-line convention). The runner still
  returns
  `manifest=None`; no persistence, DB writes, or manifest
  writing landed. The package exposes explicit
  `create_ucdp_adapter()` / `register_ucdp(registry)` factories
  and does NOT auto-register on import (§10.1). **With UCDP
  landed, the unified source interface now covers the first
  event-level source family**: PWT + Maddison = historical
  economy; WDI = current economy; WGI = governance; V-Dem =
  political regime / repression / corruption / social
  well-being; UCDP = organized conflict / one-sided violence
  (event-level aggregations). The next major milestone is a
  vertical slice of an investigation that runs from these
  source adapters through `InMemoryEvidenceRepository`,
  semantic concepts / evidence bundles, scoring or analysis
  logic, and a documented answer with provenance.

- **Investigation-slice vertical slice landed (2026-06-25) — Increment 6 of
  [`docs/viz-workplan.md`](viz-workplan.md).** Small end-to-end proof
  flow that wires the updated source architecture to a constrained
  investigation question without free-form LLM parsing or rewrite of
  legacy ingest. New module `src/leaders_db/viz/investigation_slice.py`
  exposes `run_investigation_slice()`: registers PWT + Maddison + WDI
  through the unified `SourceIngestRunner`, flattens the resulting
  `NormalizedObservation` tuples, runs the semantic concept catalog
  (`extract_concept_result(..., concept_key="gdp_per_capita")`),
  writes a chart-ready long-form CSV under
  `data/processed/viz/country-year-chronicle/`, emits a deterministic
  dependency-free HTML+SVG line chart beside it, and (when the
  canonical core CSV is present) refreshes the read-only Superset
  SQLite artifact via `build_superset_sqlite_db()`. Supported question
  keys are restricted to a small registry
  (`SUPPORTED_QUESTIONS` -> `gdp_per_capita_major_powers` for
  USA / GBR / FRA / IND / CHN over 1950-2023); unknown keys fail fast
  via `UnknownInvestigationQuestionError`; not-ready sources surface
  as structured coverage gaps on the result envelope and the slice
  keeps going with the other sources; a slice that completes with zero
  concept rows raises `RuntimeError` rather than silently emitting an
  empty CSV. New Typer CLI command
  `leaders-db viz-run-investigation-slice --question <key>
  [--countries ...] [--start-year ...] [--end-year ...]
  [--raw-root ...] [--data-dir ...] [--superset-db ...]
  [--no-rebuild-superset-db]` is registered on the existing
  :data:`app`. `VIZ_CSV_TABLES` in `src/leaders_db/viz/superset_db.py`
  picks up the new investigation CSV as an optional entry so the
  Superset builder loads it under
  `viz_investigation_gdp_per_capita_major_powers` whenever the slice
  has run. New focused pytest coverage in
  `tests/test_viz_investigation_slice.py` (13 tests, all using fake
  adapters + temp dirs so the tests do not depend on staged raw
  bundles): the runner drives every adapter through
  `check_ready -> read_raw -> transform`; concept extraction feeds
  the CSV rows; CSV rows are deterministically sorted; the static
  HTML+SVG is written and references every requested country; the
  Superset SQLite artifact contains the new table; the slice skips
  the Superset rebuild cleanly when the canonical core CSV is absent;
  the slice continues when a source is not-ready; the slice refuses
  unknown question keys and the empty-result path; the CLI
  registers and rejects unknown question keys. `ruff check` clean
  on all changed/new files; `pytest -q
  tests/test_viz_investigation_slice.py
  tests/test_cli_viz.py tests/test_viz_superset_growth_tables.py
  tests/test_imports.py` passes (38 tests); the broader source-suite
  (`tests/sources/`) and Chronicle slice remain green. Docs updated:
  `docs/viz-workplan.md` §Increment 6 (run-book + artifact list),
  `docs/testing-guide-viz-superset.md` §Investigation-slice smoke
  check (manual + automated checks). The slice is intentionally
  constrained: one supported question, deterministic, no LLM
  parser; future expansion adds entries to
  `SUPPORTED_QUESTIONS` rather than evolving the slice into a
  free-form question engine.

- **Fourth clean-source migration landed (2026-06-25) — World Bank WGI under
  `src/leaders_db/sources/adapters/world_bank_wgi/`.** WGI is
  the fourth source rebuilt under the new `leaders_db.sources`
  interface (docs/architecture/sources.md §7.1 priority 4,
  docs/requirements/sources.md §12 SRC-MIG-005), after PWT
  10.01, Maddison Project Database 2023, and World Bank WDI.
  WGI is a local-file source (single xlsx, 6 indicator sheets,
  no network) so the unified adapter is no-network by design
  (`requires_network=False`); the descriptor advertises
  `source_type="dataset"`. The new package is a thin adapter
  that implements the canonical `SourceAdapter` Protocol
  (`descriptor` + `check_ready` + `read_raw` + `transform`)
  and reuses the legacy reader under
  `leaders_db.ingest.wgi_xlsx` via lazy imports so the
  `leaders_db.sources` package boundary documented in
  docs/architecture/sources.md §10.1 is preserved; the package
  import does NOT pull in `leaders_db.ingest`
  (`tests/sources/test_world_bank_wgi_adapter.py::test_wgi_adapter_module_does_not_import_legacy_ingest_at_import`
  + the import-boundary submodule list in
  `tests/sources/test_import_boundary.py`). The legacy
  `STAGE2_ADAPTERS["world_bank_wgi"]` entry remains unchanged
  -- the new package exposes explicit
  `create_world_bank_wgi_adapter()` /
  `register_world_bank_wgi(registry)` factories and does NOT
  auto-register on import (per docs/architecture/sources.md
  §10.1). The new adapter honors the full request scope:
  `years=` and `countries=` filter the wide-format DataFrame on
  the new transform side (the legacy reader returns the full
  frame when called with `year=None`); `leaders=` emits a
  structured `unsupported_filter` warning; `years=(2023,)` or
  `years=(1995,)` (out of coverage) emit zero observations plus
  a structured `year_absent` warning -- no stale-proxy fill
  (SRC-COV-002 / SRC-COV-003). A mismatched `source_version=`
  (e.g. `"9999"` against a canonical WGI bundle whose metadata
  records `"Worldwide Governance Indicators 2023 Update (data
  through 2022)"`) FAILS readiness with a structured
  `unsupported_version` error per docs/requirements/sources.md
  §3 SRC-REQ-009 -- the runner raises `RuntimeError` before
  calling `read_raw` / `transform`, so the legacy bundle
  metadata cannot be silently overwritten by an unsupported
  version stamp. The runner also validates the staged bundle's
  metadata `version` / `source_version`: missing or mismatched
  metadata versions fail readiness, and the canonical
  `"Worldwide Governance Indicators 2023 Update (data through
  2022)"` value propagates consistently to `RawAsset.version`
  and every emitted `NormalizedObservation.source_version`.
  The readiness gate accepts BOTH the canonical primary metadata
  shape (`source_version` / `checksum_sha256` / `local_files` /
  `license_note` / `coverage`) AND the staged WGI legacy shape
  (`version` / `sha256` / `local_file` / `license` /
  `coverage_start_year` + `coverage_end_year`) so the existing
  staged bundle metadata does not need to be rewritten as
  part of the migration. The runner end-to-end contract is
  proven by `test_wgi_runner_produces_normalized_observations`
  (59 fixture observations round-tripped -- 5 countries x 2
  years x 6 indicators minus one `#N/A` cell at MEX 2021
  `wgi_political_stability`) and
  `test_wgi_runner_does_not_consult_legacy_stage2_adapters`
  (monkeypatched legacy `STAGE2_ADAPTERS["world_bank_wgi"]`
  tracker is never invoked). The WGI descriptor exposes
  `source_id="world_bank_wgi"`, `default_version="Worldwide
  Governance Indicators 2023 Update (data through 2022)"`,
  the canonical WGI homepage URL
  (`https://info.worldbank.org/governance/wgi/`),
  `attribution_key="world_bank_wgi"`, coverage hint 1996-2022,
  and the `governance_country_year` observation family.
  Per-observation `RawLocator` carries the staged xlsx path +
  the per-indicator sheet name (e.g. `VoiceandAccountability`
  for `wgi_voice_and_accountability`); `row_number` is
  intentionally `None` because the legacy wide frame loses
  the xlsx row index through the long-to-wide pivot -- the
  unified transform never fabricates locators. Per-observation
  `extension` carries the canonical attribution text (Rule
  #15), the `source_row_reference="world_bank_wgi:<iso3>"`
  pattern (matching the legacy Stage 2 DB writer), the
  `wgi_sheet_name` (canonical xlsx sheet name), and the
  `wgi_indicator_category` (catalog `rating_category`,
  `effectiveness` for 5 indicators + `integrity` for
  `wgi_control_of_corruption`). The new
  `WORLD_BANK_WGI_ATTRIBUTION_TEXT` constant is byte-identical
  to the legacy `WGI_ATTRIBUTION` constant in
  `src/leaders_db/ingest/wgi_io.py` and to the
  `world_bank_wgi` entry in `docs/sources/attributions.md`;
  `test_wgi_attribution_text_matches_attributions_doc` enforces
  byte-identity (drift guard). 23 focused tests in
  `tests/sources/test_world_bank_wgi_adapter.py` cover the
  full slice acceptance criteria (descriptor / factory /
  registry / runner / request-scoping / out-of-coverage /
  readiness-failure / canonical-version-propagation /
  primary-shape / import-boundary / STAGE2_ADAPTERS-no-touch).
  Module sizes: `__init__.py` 109 lines, `_descriptor.py`
  189 lines, `_metadata_validators.py` 303 lines,
  `_readiness.py` 293 lines, `_raw_read.py` 161 lines,
  `_pipeline.py` 119 lines, `_transform.py` 319 lines,
  and `adapter.py` 354 lines; no WGI production-module
  carve-out is needed. The focused single-source test file is
  `tests/sources/test_world_bank_wgi_adapter.py`. The runner
  still returns `manifest=None`; no persistence, DB writes,
  or manifest writing landed. The package exposes explicit
  `create_world_bank_wgi_adapter()` /
  `register_world_bank_wgi(registry)` factories and does NOT
  auto-register on import (§10.1). The next migration slice
  candidate is V-Dem (priority 5), per
  docs/architecture/sources.md §7.1.

- **Country-Year Chronicle Increment 3 completed (2026-06-21).** Closes the documented Increment 2 gaps: (a) SUN rulers 1922-1991 populated via a curated, Wikipedia-anchored spell list at `data/raw/soviet_leaders_curated/soviet_leaders.csv` (8 leaders: Lenin, Stalin, Malenkov, Khrushchev, Brezhnev, Andropov, Chernenko, Gorbachev) with transition years (1924, 1953, 1985) emitting `multiple_rulers`; (b) CShapes 2.0 (Schvitz et al. 2022) integrated as the country-area source (44.5 MB raw CSV at `data/raw/cshapes/CShapes-2.0.csv`, SHA-256 verified, gitignored) with a GW 365 dispatch rule (SUN 1922-1991, RUS 1991+) that uses asymmetric containment to prevent SUN-era territory values from leaking into RUS rows; (c) `controlled_area_km2` populated with the conservative fallback (`country_area_km2`) plus the new `controlled_area_country_only` flag; imperial / dependency summing explicitly deferred (no vetted dependency-controller mapping was staged in this pass; ICOW Colonial History download URL is broken on 2026-06-21). **Reviewer-gate follow-up (2026-06-21)**: `row_builder.py` grew to 500 lines during the Increment 3 pass and broke the documented 400-line convention; the row-builder helpers were extracted into 5 focused sibling modules (`_row_identity.py` 67 lines, `_row_ruler.py` 83, `_row_regime.py` 47, `_row_sipri.py` 54, `_row_area.py` 109) so `row_builder.py` is now 309 lines. The Chronicle slice now ships **25 focused modules** (was 20; Increment 3 added `_sun_ruler_loader.py`, `_area_source.py`, and the 5 row-helper siblings). Four modules are now documented carve-outs from the 400-line convention: `constants.py` (476 lines, long-table / schema constants, carved out since Increment 1), `sources.py` (414 lines, legacy source facade / source classes; split deferred for compatibility; follow-up if growth crosses 440 lines), `runner.py` (421 lines, CLI boundary orchestration / composition seam; follow-up split if it grows beyond 440 lines), and `ruler_resolver.py` (402 lines, three-source resolver with the SUN curated helper; a 2-line overage that does not warrant another split). Pilot CSV regenerates 889 rows for the 7-country 1900-2026 scope and reports `sources_used = archigos, cshapes, maddison_project, reign, sipri_milex, soviet_leaders_curated, vdem`. Final coverage: 70 of 70 in-window SUN rows have a ruler; 645 of 645 in-window rows have a real `country_area_km2`; 49 rows past CShapes coverage (2020+) carry the `area_proxy_year_used` flag; 749 rows have the conservative `controlled_area_country_only` flag. New `docs/sources/attributions.md` Section 1 entries for `cshapes` and `soviet_leaders_curated` (drift-guarded by new tests in `test_chronicle_constants.py`). 48 new focused pytest tests (18 SUN curated + 18 CShapes area + 6 attribution drift + 3 production wiring + 3 fix-to-existing-tests); full suite green at 1757 passing (was 1709; +48 net). `ruff check .` clean; `git diff --check` clean. **SUN transition-year wording fix**: `tests/test_chronicle_sun_curated.py` and the Increment 3 doc no longer describe SUN 1922 as "full year" — it is correctly described as a partial-year spell (Lenin positive-overlap with the country-year after USSR formation on 1922-12-30); SUN 1991 is described as covered until 1991-12-25 (the USSR dissolution date), not as a full calendar year of rule. Implementation notes in [`docs/chronicle/increment-3.md`](chronicle/increment-3.md).

- **Country-Year Chronicle Increment 2 completed (2026-06-21).** Maddison Project Database 2023 is wired into the Chronicle economy fields with the documented source-precedence contract (Maddison preferred for 1900-2022, WDI preferred for 2023+, Maddison 2022 used as a 1-year-gap proxy for **exactly year == 2023 only** when WDI is missing — the reviewer gate explicitly forbids silently reusing Maddison 2022 as a multi-year stale proxy for 2024+). A narrow provenance-aware ruler resolver (Archigos v4.1 through 2015 + REIGN 2021-8 monthly for 1950-2021, leader-with-most-months heuristic, no client matrix, no LLM) populates the ruler columns for the first time. The Chronicle slice now ships 18 focused modules (was 17; the Increment 2 sign-off pass added `sqlite_writer.py` for the SQLite artifact companion). All modules <= 414 lines; `row_builder.py` sits exactly at the 400-line convention ceiling. The CLI run produces 889 rows for the 7-country 1900-2026 pilot and reports `sources_used = archigos, maddison_project, reign, sipri_milex, vdem`. The default command also writes a SQLite artifact at `data/outputs/country-year-chronicle/pilot.sqlite` (one `country_year_chronicle` table with TEXT/INTEGER/REAL columns + a `source_attributions` sidecar); 46 new focused pytest tests added (9 + 9 reviewer-blocker economy-fields + 6 attribution drift + 6 production wiring + 13 SQLite + 13 ruler resolver; was 22); full suite green at 1705 passing (was 1671; +34 net). Maddison source hygiene complete: local `data/raw/maddison_project/metadata.json` written with the canonical SHA-256 of `mpd2023.xlsx` (`ecc5916c...`); the 4.9 MB xlsx bundle is gitignored per Always-On Rule #9. Full implementation notes at [`docs/chronicle/increment-2.md`](chronicle/increment-2.md). Caveats: SUN rows remain `missing_ruler` (neither source carries a separate SUN `ccode`); 2024+ Maddison proxy is explicitly NOT done (rows left blank with `missing_population`/`missing_gdp`); static area source and ruler titles are still deferred; Maddison + REIGN attribution text was previously a short abbreviation and is now byte-identical to the canonical `docs/sources/attributions.md` strings (drift-guarded).

- **Phase C.11 — Maddison Project Database Stage 2 adapter landed (2026-06-20).** Added `maddison_project` as the historical real-economy source for `economic_wellbeing`. The adapter reads the Maddison Project Database 2023 xlsx `Full data` sheet (`countrycode`, `country`, `region`, `year`, `gdppc`, `pop`), emits GDP per capita, population-in-thousands, and derived total real GDP (`gdppc * pop * 1000`) observations, writes attribution-bearing parquet, registers source rows, persists a run manifest, supports the 2023→2022 one-year proxy pattern, and is wired into `STAGE2_ADAPTERS` plus `PRIORITY_SOURCES`. Focused proof: `pytest -q tests/test_ingest_maddison_project.py tests/test_paths.py` passes (32 tests), including the real Typer `leaders-db ingest-source --source maddison_project --year 2022` boundary through an isolated data lake and DB. The raw 4.9 MB `mpd2023.xlsx` is not committed; real production ingestion expects it at `data/raw/maddison_project/mpd2023.xlsx`.

- **Country-Year Chronicle Increment 1 completed (2026-06-20).** Implemented the experimental CSV-producing vertical slice per `docs/chronicle/increment-0.md` §4 and the workplan §7. New package `src/leaders_db/chronicle/` (11 focused modules, all ≤ 422 lines: `__init__.py`, `constants.py`, `sources.py`, `regime.py`, `system_type.py`, `row_builder.py`, `csv_writer.py`, `runner.py`, plus the private helpers `_formatters.py`, `_flags.py`, and `_wdi_fields.py` extracted from the original 559-line `row_builder.py` to keep it under the 400-line convention) plus a new Typer CLI module `src/leaders_db/cli/commands_chronicle.py` registered in `src/leaders_db/cli/__init__.py`. CLI command: `leaders-db run-country-year-chronicle --start-year <Y> --end-year <Y> --countries <ISO3,...> --output <path>` (with `--allow-regime-proxy/--no-allow-regime-proxy`). Default ISO3 scope is the Increment 0 pilot set `USA,GBR,FRA,IND,RUS,SUN,CHN`; default year window is 1900-2026; default output path is `<project_root>/data/outputs/country-year-chronicle/country_year_chronicle.csv`. Output is one CSV row per requested `(iso3, year)` pair regardless of source coverage — the row simply carries more `missing_*` / `*_gap` flags. V-Dem `v2x_regime` (raw CSV read, narrowed to the requested iso3 set) is the political-regime source; the 2025 proxy year is the documented default for years beyond V-Dem coverage (2026 today), opt-out via `--no-allow-regime-proxy`. WDI processed parquet is the population/GDP source (1960+ when the local parquet has a row; the current local parquet only contains 2022, so pre-2023 rows are empty with `missing_population`/`missing_gdp` flags per Increment 0 contract). SIPRI milex processed parquet is the military-spend source (only 2022 has a row today; SUN gets nothing because the parquet uses display names and the 1922-1991 successor state is not present in the 2022 snapshot); the `missing_military_spend` flag is driven **only** by the canonical CSV target field `milex_constant_usd` — ancillary per-capita / share-of-GDP values do not clear it. Ruler fields, area, and controlled area are always empty with `missing_ruler`/`missing_area`/`controlled_area_not_modeled` flags. `country_status` is dynamic per row: IND pre-1947 (years ≤ `colonial_status_until=1946`) emits `colonial/dependent` and IND 1947+ emits `independent`; SUN emits `successor_state`; the rest emit `independent`. The `colonial_status_issue` flag continues to fire on pre-1947 IND rows. System-type classifier is conservative and deterministic: curated country-period mappings for `SUN 1922-1991`, `CHN 1949-2026`, `IND 1858-1946`; **RUS is intentionally NOT curated** — it falls through to the regime-bucket fallback (Full/Flawed democracy → Liberal capitalist democracy; Hybrid/Authoritarian → Mixed / unclear; Unknown → Unknown with `system_type_low_confidence`). CSV is written atomically through a tempfile + rename; the leading `#` comment block carries the source-attribution strings (canonical text from `docs/sources/attributions.md` §1 — byte-for-byte drift-guarded by `test_vdem_attribution_matches_attributions_doc`, `test_wdi_attribution_matches_attributions_doc`, `test_sipri_attribution_matches_attributions_doc`). No client matrix and no LLM. 124 focused pytest tests across 5 files: `tests/test_chronicle_constants.py` (column contract, attribution, CSV writer, atomic write, curated mapping invariants, COUNTRY_METADATA), `tests/test_chronicle_regime.py` (direct v2x_regime mapping, polyarchy fallback, 2025 proxy flag, RegimeSource.from_vdem_lookup proxy logic), `tests/test_chronicle_system_type.py` (SUN/CHN/IND curated + RUS regime-bucket fallback for Full/Flawed/Hybrid/Authoritarian/Unknown, notes content), `tests/test_chronicle_row_builder.py` (row shape, one row per identity-year, missing-flag propagation, pre/post-existence gaps, successor-state / colonial flags, proxy-year flag, row_confidence aggregate, RUS Authoritarian/Hybrid → Mixed / unclear, IND dynamic `country_status`, SIPRI flag-from-`milex_constant_usd`-only contract, no client-matrix import), `tests/test_cli_chronicle.py` (Typer registration, --help content, default output path resolution, --output / --countries / --start-year / --end-year validation, --allow-regime-proxy / --no-allow-regime-proxy behavior, 7-country pilot end-to-end smoke, parsed-row assertions for IND 1900 / 1946 / 1947 and RUS Authoritarian/Hybrid fallback). Ruff is clean on all new files and the full test suite passes (1669 tests). The slice reads from the real local data lake in production (`data/raw/vdem/V-Dem-CY-Full+Others-v16.csv` for V-Dem; processed parquets for WDI and SIPRI) and writes the CSV under `data/outputs/country-year-chronicle/` per Increment 0 §4. Implementation notes in [`docs/chronicle/increment-1.md`](chronicle/increment-1.md). Next CYC action: Increment 2 — extend to all countries for the 1960-2026 recent window with a summary artifact, missingness report, and manual-review queue.
- **Country-Year Chronicle Increment 0 completed (2026-06-20).** Added the CYC planning record at [`docs/chronicle/workplan.md`](chronicle/workplan.md) and the Increment 0 findings at [`docs/chronicle/increment-0.md`](chronicle/increment-0.md). Increment 0 inventories local processed artifacts and the SQLite catalog, confirms the first CSV contract, separates political-regime buckets from system/ideology classification, recommends pilot identities `USA,GBR,FRA,IND,RUS,SUN,CHN`, and records the ready/blocked field matrix. Key findings: V-Dem is ready for 1789-2025 political regime derivation; WDI is ready for 1960+ population/GDP; Archigos/REIGN raw files are ready but current processed artifacts are empty and the full leader resolver is still pending; PWT and Polity raw files are visible locally but lack `metadata.json` and should not be consumed as canonical inputs until source hygiene is corrected; no vetted static area source is ready; controlled/imperial area remains deferred and flagged for MVP. Next CYC action: Increment 1 experimental read-only CSV with attribution block, proxy/missingness flags, and CLI boundary tests.
- Created initial docs: `AGENTS.md`, `docs/workplan.md`, `docs/architecture/overview.md`, `docs/process/coding-guidelines.md`, `docs/requirements/core.md`, `docs/reviews/README.md`.
- Created Python package layout under `src/leaders_db/` mirroring the §15 repository structure (with `db/`, `ingest/`, `normalize/`, `resolve/`, `score/`, `validate/`, `llm/`, `export/`).
- Added Typer CLI surface exposing every Stage 0–15 command from requirement §8 (stubs only).
- Added `src/leaders_db/db/migrations/0001_initial.sql` covering the 11 prototype tables from requirement §7, plus SQLAlchemy ORM models in `src/leaders_db/db/models.py`.
- Added `src/leaders_db/score/confidence.py` implementing the fixed `0.35/0.25/0.25/0.15` formula with band labels and full type annotations.
- Added `src/leaders_db/llm/schemas.py` with strict input/output Pydantic models per requirement §10.
- Created data lake folders under `data/raw/<source>/` for every priority source plus `client_existing/`.
- Moved the existing client source bundle (`*.xlsx`, `*.docx`) into `data/raw/client_existing/` and added a `metadata.json`.
- Added first run config `configs/prototype-2023.yaml` (target year = 2023) and `scripts/init_data_lake.sh`.
- Added smoke tests proving: package imports, CLI `--help`, config loading, paths helpers, db schema migration applies cleanly, normalize helpers round-trip, and confidence formula produces expected values.
- Recorded Phase A → B → C → D → E ordering with Phase B (source vetting) gating Phase C (data acquisition implementation).
- Phase A marked complete. Phase B plan written at `docs/sources/vetting/plan.md` with a per-source probe checklist (URL reachable, no login wall, no paywall, license compatible, coverage reaches 2023, format parseable, checksum reproducible) and a four-value verdict schema (`vetted_ok` / `vetted_with_caveats` / `blocked` / `replace`). Phase B exit criteria defined; no Stage 2 adapter is written until its source passes the probe.
- **Phase B complete (pending user sign-off; superseded by later addenda below).** Probed 18 sources (15 from §6 + Wikidata + Wikipedia + CIA, with CIA retired). Final tallies at that time: 8 ✅ vetted_ok (`vdem`, `world_bank_wdi`, `world_bank_wgi`, `ucdp`, `sipri`, `pts`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`), 5 ⚠️ vetted_with_caveats (`archigos`, `reign`, `leader_survival`, `transparency_cpi`, `fas`), 5 ❌ blocked (`freedom_house`, `cow_mid`, `cirights`, `cia_world_leaders`, `nti`). **The 2023 leader-identity gap is closed** by adding Wikidata (CC0) and Wikipedia (CC BY-SA) per user request; V-Dem v16 (388MB, 28,093 rows × 202 countries, SHA-256 captured) is on disk and ready for Stage 2. Wrote [`docs/sources/vetting/report.md`](sources/vetting/report.md) (the sign-off document) and [`docs/sources/attributions.md`](sources/attributions.md) (every source + license + citation + attribution text). Added AGENTS.md Always-On Rule #15 ("carry source attribution forward in every public output") and `docs/sources/attributions.md` is now normative. Eight evidence files saved under `tmp/source-vetting-evidence/` for audit.
- **Phase B second wave (per user feedback; superseded by later CIRIGHTS/BTI/RSF addenda below).** User flagged that the per-source report structure hid the "≥ 2 sources per rating category" requirement and that I had been treating WDI only as an economic source. Added 5 second-source candidates: UNDP HDI (`vetted_ok`, 1.9MB CSV, 207 countries, 1990–2022), Polity V (`vetted_ok`, direct SPSS, 1800–2018), Penn World Table 10.01 (`vetted_ok`, 6.5MB xlsx), WHO GHO API (`vetted_ok`, OData, ~2000 indicators), SIPRI Yearbook Ch.7 World Nuclear Forces (`vetted_ok`, 717KB PDF). Found the missing 8th rating category (Social well-being) and added UNDP HDI + WHO GHO as 2nd and 3rd sources. Restructured the report by rating category. IMF WEO blocked by Akamai 403 (user can fetch manually if needed). BTI 2024 was initially deferred (site returned 500 errors), then recovered in the addendum below. **All 8 rating categories now have at least 2 distinct datasets.**
- **Phase B signed off by user (2026-06-17 21:00; later BTI status superseded below).** User confirmed the report was correct on their end (liveness probe re-verified all then-current ✅ vetted_ok URLs; BTI home page recovered from earlier 500 errors but `/en/reports/bti-2024` data page still 500 at that time). Phase C (data acquisition) is now unblocked. User noted we "might reiterate through the whole thing later on" — so the sign-off is for the current run; the report is a living document. V-Dem v16 CSV (388MB, 4618 columns, 28,093 rows × 202 countries, 179 rows for 2023) is on disk at `data/raw/vdem/V-Dem-CY-Full+Others-v16.csv` and is the first Stage 2 adapter to land.
- **Phase C.1 — V-Dem Stage 2 ingest landed (2026-06-17 23:17).** First Stage 2 adapter implemented, end-to-end smoke for 2023 green. 18 new tests in `tests/test_ingest_vdem.py` (70 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/vdem.csv` lists 22 V-Dem columns across 5 rating categories (political_freedom, integrity, effectiveness, domestic_violence, social_wellbeing). Test fixture at `tests/fixtures/vdem/sample.csv` (10 real rows from the V-Dem v16 CSV — no invented data). End-to-end run against the real 388MB file for 2023 produces 3938 `source_observations` rows (179 countries × 22 indicators) in 6 s. The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` is the single registry for Stage 2; the CLI `leaders-db ingest-source --source <key>` consumes it. `session_scope()` (in `db/session.py`) now resolves the default URL through `project_root()` so the `LEADERSDB_PROJECT_ROOT` env var controls where the DB lives — tests are isolated without per-adapter `database_url` workarounds. Parquet metadata carries the V-Dem attribution per Rule #15. CLI is wired and the test suite stays clean (no production-DB pollution from pytest). **Awaiting user sign-off before starting WDI.**
- **Phase C.1 — V-Dem reviewed and refined (2026-06-18).** Independent reviewer found 5 blockers, 8 important issues, 5 nits. All fixed: V-Dem attribution text aligned to the canonical citation in `docs/sources/attributions.md` (drift-guard test added); `session_scope()` now honors `LEADERSDB_PROJECT_ROOT` (3-line upstream fix in `db/session.py`); V-Dem adapter split into 3 modules (`vdem.py` 237 lines, `vdem_io.py` 287, `vdem_db.py` 355 — all under 400); `IngestResult` is now a Pydantic `BaseModel` (was a dataclass); `VDEM_ATTRIBUTION` is printed in the CLI end-of-run output; the run manifest is auto-written by the orchestrator (was separate); the catalog `raw_scale` for `v2csreprss` and `v2clkill` is now "continuous" (the * (no suffix) version is a Bayesian point estimate that can be negative — corrected from "0-4" which is the survey scale); V-Dem's `country_id` is renamed to `vdem_country_id` in the narrow frame to avoid collision with the `countries.id` FK; the `test_session_scope_respects_leader_sdb_project_root_env` regression test guards the env-var fix; the `test_vdem_attribution_matches_attributions_doc` test guards the attribution-doc consistency; `_coerce_float` and `_coerce_float_from_string` handle pandas NaN, the `nan` string, the `-999` sentinel, and empty string (defense in depth). Test count grew from 70 to 82; ruff is clean on all new code. **Re-dispatching the reviewer to verify.**
- **Phase C.2 — WDI Stage 2 ingest landed (2026-06-18).** Second Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. 31 new tests in `tests/test_ingest_wdi.py` (113 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/wdi.csv` lists 14 World Bank WDI indicators across 2 categories (economic_wellbeing, social_wellbeing). Test fixture at `tests/fixtures/world_bank_wdi/cache/{2022,2023}/` — 28 JSON files with real WDI v2 responses for 5 countries (MEX, USA, SWE, IND, NGA) × 14 indicators × 2 years. End-to-end live smoke against the real WDI API for 2023 produces 3038 `source_observations` rows (217 real countries × 14 indicators) in ~60 s. The `WDI_ATTRIBUTION` constant is byte-identical to the citation in `docs/sources/attributions.md` (drift-guard test added). WDI follows the same pattern as V-Dem but with an extra module because WDI needs HTTP: `wdi.py` 276 lines (orchestrator + `WDIIngestResult` Pydantic), `wdi_io.py` 479 lines (catalog + read + parquet), `wdi_db.py` 369 lines (sources + observations + manifest), `wdi_http.py` 238 lines (HTTP + cache). Reviewer caught 1 blocker (duplicate `world_bank_wgi` dispatch key), 5 important (lint warnings, end-to-end test gap, docstring bug, design-doc code drift, missing confidence-NULL test), and 4 nits — all 8 fixed in a single iteration. After re-review, 4 follow-up items were addressed: §2.5 + §2.8 doc numbers updated (196→217, 2744→3038), wdi.py docstring corrected (removed false "400-line" claim), wdi_io.py split into wdi_io.py + wdi_http.py to reduce the largest module from 614 to 479 lines (still over the 400-line convention; the 80-line static aggregate denylist is the main remaining bulk; accepted for the prototype). **PASS on the second pass. Moving to WGI next per the priority list.**
- **Phase C.3 — WGI Stage 2 ingest landed (2026-06-18).** Third Stage 2 adapter via the same pipeline. 30 new tests in `tests/test_ingest_wgi.py` (143 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/wgi.csv` lists 6 WGI indicators (5 in "effectiveness" + 1 in "integrity" for cross-validation with TI CPI). WGI is structurally different from WDI: it reads a single xlsx file (not an HTTP API), with 6 indicator sheets, 214 countries, 24 years, and a `"#N/A"` literal string missing-data sentinel. Test fixture at `tests/fixtures/world_bank_wgi/sample.xlsx` — 6 sheets, 5 countries × 2 years × 6 indicators, real WGI values pulled from the live xlsx. WGI follows the V-Dem 3-module pattern (no HTTP layer), then split into 5 modules after review: `wgi.py` 250 lines (orchestrator + `WGIIngestResult` Pydantic), `wgi_io.py` 307 lines (catalog + paths + parquet), `wgi_xlsx.py` 266 lines (xlsx read + long→wide pivot), `wgi_db.py` 309 lines (sources + observations + manifest), `wgi_db_helpers.py` 169 lines (coercion + bundle metadata). Live smoke against the real 2.1 MB xlsx is gated on staging the bundle; unit tests prove the contract. The `WGI_ATTRIBUTION` constant is byte-identical to the citation in `docs/sources/attributions.md` (drift-guard test added; CC BY 4.0 license recorded). Reviewer caught 3 blockers (index-swap schema mutation, attribution text drift, ruff warning), 3 important (file split, default_xlsx_path raise semantics, dead code), and 2 nits — all 6 fixed in a single iteration. **PASS on the second pass. Moving to UCDP next per the priority list.**
- **Phase C.4 — UCDP Stage 2 ingest landed (2026-06-18).** Fourth Stage 2 adapter via the same pipeline. 35 new tests in `tests/test_ingest_ucdp.py` (178 total, all passing). UCDP is the first Stage 2 adapter that requires **aggregation**: the source data is event-level (316,818 events in v23.1, 1989-2022, zip → 218 MB CSV), and the adapter must aggregate by country-year to produce 6 indicator values per (country, year) row. Indicator catalog at `src/leaders_db/ingest/catalogs/ucdp.csv` lists 6 UCDP indicators (4 international_peace: state-based + intl events/fatalities; 2 domestic_violence: one-sided events/fatalities). The internationalized filter uses `gwnob.notna()` (foreign state involvement) — NOT the obvious `side_a_new_id != country_id` filter which is a no-op because UCDP's actor IDs and country IDs are in different identifier spaces. Test fixture at `tests/fixtures/ucdp/sample.zip` — 22 events, 5 countries × 2 years, real-format CSV with cross-border event. UCDP split into 6 modules: `ucdp.py` 299 (orchestrator), `ucdp_io.py` 348 (catalog + zip read + parquet), `ucdp_db.py` 338 (DB writers), `ucdp_db_helpers.py` 171 (coercion), `ucdp_aggregate.py` 184 (long→wide pivot), `ucdp_catalog.py` 140 (IndicatorSpec + catalog loader). `UCDP_ATTRIBUTION` byte-identical to the doc. Reviewer caught 2 blockers (duplicate `sipri_milex` dispatch key from earlier copy-paste; design doc dense-vs-sparse contradiction), 2 important (stale stub comment, stale `# type: ignore`), and 4 nits — all 7 fixes in a single iteration. **PASS on the second pass. Moving to SIPRI milex next per the priority list.**
- **Phase C.5 — SIPRI milex Stage 2 ingest landed (2026-06-18).** Fifth Stage 2 adapter via the same pipeline. 39 new tests in `tests/test_ingest_sipri_milex.py` (217 total, all passing). SIPRI milex reads a single xlsx with 10 sheets (5 data + 5 header/footnote). The 4 indicator sheets are `Share of GDP`, `Per capita`, `Constant (2024) US$`, `Share of Govt. spending`. Missing-data tokens: `"..."`, `"xxx"`, `""`. 15 region-label rows must be filtered out. Indicator catalog at `src/leaders_db/ingest/catalogs/sipri_milex.csv` lists 4 indicators in `international_peace` (all `higher_is_better=0`). The adapter detects the header row per sheet (column 0 == "Country"; the position varies by sheet — row 6, 6, 7, 8 for the 4 indicator sheets). SIPRI split into 5 modules: `sipri_milex.py` 330 (orchestrator + Pydantic `SipriMilexIngestResult` with 8 fields incl. `regions_covered` and `country_count` audit fields), `sipri_milex_io.py` 365 (catalog + paths + parquet), `sipri_milex_xlsx.py` 363 (per-sheet header detection + region filter + pivot), `sipri_milex_db.py` 296 (DB writers), `sipri_milex_db_helpers.py` 160 (coercion). `SIPRI_MILEX_ATTRIBUTION` byte-identical to the doc. **PASS on the first review (3 minor nits, all optional). Moving to SIPRI Yearbook Ch.7 next per the priority list.**
- **Phase C.6 — SIPRI Yearbook Ch.7 Stage 2 ingest landed (2026-06-18).** Sixth Stage 2 adapter (and first **PDF-based** source in the pipeline). 51 new tests in `tests/test_ingest_sipri_yearbook_ch7.py` (268 total, all passing). Adapter parses a single PDF (`/Data/Files/YB24_Ch7.pdf`, 717KB) for the Table 7.1 ("World nuclear forces, January 2024") that lists inventory / deployed / retired warheads for 9 nuclear-armed states. Indicator catalog at `src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv` lists 3 indicators in `international_peace` (`total_inventory` higher_is_better=0, `deployed` higher_is_better=0, `retired` higher_is_better=1 — more retired = more disarmament progress). Three PDF sentinels: `–` (U+2013 en-dash → 0), `..` (two-dot → None), `c. <num> [letter]` (China's deployed figure with footnote letter → int with letter preserved in `raw_value`). Test fixture at `tests/fixtures/sipri_yearbook_ch7/sample.pdf` — 1-page PDF generated by `reportlab` with a known Table 7.1 layout. New module: `sipri_yearbook_ch7_pdf.py` (pdfplumber-based parser, 389 lines). New deps: `pdfplumber>=0.11` (runtime) and `reportlab>=4.0` (dev, for the test fixture). Split into 5 modules: `sipri_yearbook_ch7.py` 364 (orchestrator + Pydantic `SipriYearbookCh7IngestResult` with 8 fields), `sipri_yearbook_ch7_io.py` 400 (catalog + paths + parquet), `sipri_yearbook_ch7_pdf.py` 389 (PDF → DataFrame parser), `sipri_yearbook_ch7_db.py` 379 (DB writers), `sipri_yearbook_ch7_db_helpers.py` 309 (coercion). `SIPRI_YEARBOOK_CH7_ATTRIBUTION` byte-identical to the doc. Reviewer caught 2 blockers (28 ruff errors in test file, 2 stray `=0.11` / `=4.0` files at project root), 1 important (raw_value test would raise on `int("1 770 d")`), 1 nit — all resolved in a single fix pass. **PASS on the second review. Moving to PTS (Political Terror Scale) next per the priority list.**
- **Phase C.7 — PTS Stage 2 ingest landed (2026-06-18).** Seventh Stage 2 adapter. 39 new tests in `tests/test_ingest_pts.py` (307 total, all passing). PTS reads a single xlsx (`PTS-2025.xlsx`, 572KB, 10,531 data rows × 14 columns, 1 sheet "PTS-2025") for the Political Terror Scale 2025 release. Indicator catalog at `src/leaders_db/ingest/catalogs/pts.csv` lists 3 indicators in `domestic_violence` (`pts_amnesty_score` / `pts_human_rights_watch_score` / `pts_state_dept_score` — all `higher_is_better=0` per "more terror = worse"). The 14-column long format has 3 indicator columns (PTS_A / PTS_H / PTS_S) and 3 NA_Status_X columns (integer 0/66/77/88/99 where 0=present, 66=not covered, 77=country didn't exist, 88=not coded, 99=missing). The §6 4-case sentinel matrix: (case 1) int 1-5 + NA_Status=0 → keep, (case 2) int 1-5 + NA_Status≠0 → drop + log debug, (case 3) 'NA' string + NA_Status≠0 → drop, (case 4) 'NA' string + NA_Status=0 → log warning + drop. The architect's 3 live-data findings: (a) the live xlsx has 7 World Bank country-and-lending-groups region codes (`eap`/`eca`/`lac`/`mena`/`na`/`sa`/`ssa`) not 6; (b) all 5 NA_Status codes (0/66/77/88/99) are present; (c) the 'mena, ssa' string anomaly (49 rows for African Union) is preserved with a comment. Test fixture at `tests/fixtures/pts/sample.xlsx` is a slice of the real xlsx (5 rows: Afghanistan 2022/2023, Andorra 2022, United States 2022/2023) produced by `tests/fixtures/pts/build_sample_xlsx.py` (idempotent, committed). Final split: 6 modules: `pts.py` 399 (orchestrator + Pydantic `PtsIngestResult` 8 fields), `pts_io.py` 368 (catalog + paths + parquet + 4 named constants), `pts_xlsx.py` 400 (xlsx read + 4-case sentinel matrix + defensive checks), `pts_xlsx_pivot.py` 256 (NEW — long-to-wide pivot + raw_lookup attachment), `pts_db.py` 279 (sources + observations + manifest), `pts_db_helpers.py` 216 (NEW — coercion + bundle metadata). `PTS_ATTRIBUTION` byte-identical to the doc. Reviewer caught 2 blockers (`pts_xlsx.py` 545 lines and `pts_db.py` 431 lines — both over the 400-line cap; the architecture doc §5 had a 350-line split-trigger for `pts_db.py` that the developer ignored), 2 important (defensive checks for the named constants not wired, Pydantic `model_fields` deprecation in test). **PASS on the second review after the fix split. Moving to UNDP HDI next per the priority list.**
- **Phase C.8 — UNDP HDI Stage 2 ingest landed (2026-06-18).** Eighth Stage 2 adapter and the canonical social-wellbeing composite source. 39 new tests in `tests/test_ingest_undp_hdi.py` (346 total, all passing). UNDP HDI reads a latin-1 wide CSV (`HDR23-24_Composite_indices_complete_time_series.csv`, 1.9MB, 206 countries after excluding aggregate `ZZ*` rows, 1990-2022) and extracts 5 catalog indicators in `social_wellbeing`: `hdi`, `le`, `eys`, `mys`, and `gnipc`. For prototype target year 2023, the adapter uses 2022 as a one-year-gap proxy and records the proxy semantics in the manifest. Test fixture at `tests/fixtures/undp_hdi/sample.csv` is a real-format slice produced by `tests/fixtures/undp_hdi/build_sample_csv.py`, including Côte d'Ivoire for latin-1 coverage, Nigeria empty-cell cases, and a real blank-region USA row. Final split: `undp_hdi.py` 269 (orchestrator + public re-exports), `undp_hdi_io.py` 300 (catalog/paths/constants), `undp_hdi_csv.py` 328 (CSV read + validation), `undp_hdi_unpivot.py` 163 (wide-to-long UNPIVOT), `undp_hdi_parquet.py` 56 (parquet metadata), `undp_hdi_result.py` 103 (Pydantic result), `undp_hdi_db.py` 299 (sources/observations/manifest), `undp_hdi_db_helpers.py` 220 (coercion + bundle metadata). Runtime proof: focused UNDP tests passed, full suite passed, real-file 2022 produced 1,023 rows, full no-year run produced 32,432 rows, raw SHA-256 stayed unchanged, CLI dispatch writes DB/parquet/manifest through production paths, and final static reviewer PASS recorded no remaining blockers or important issues. Per user direction, source-adapter development now pauses for a thin downstream vertical slice.
- **Phase C.9 — WHO Global Health Observatory (GHO) OData API Stage 2 ingest landed (2026-06-19).** Ninth Stage 2 adapter and the first **API-backed** source in the pipeline that is HTTP-cached (alongside the WDI HTTP-cache pattern; the WHO GHO API is a public OData 4.0 endpoint at `https://ghoapi.azureedge.net/api/`, no auth). 36 new tests in `tests/test_ingest_who_gho_api.py` (475 total, all passing). The adapter narrows the ~2000-indicator WHO GHO API to 5 in-scope `social_wellbeing` indicators defined in `src/leaders_db/ingest/catalogs/who_gho_api.csv`: `WHOSIS_000001` (life expectancy at birth, SEX_BTSX filter), `MDG_0000000007` (under-5 mortality rate, SEX_BTSX filter), `WHS4_100` / `WHS4_117` / `WHS4_543` (DTP3 / HepB3 / BCG immunization coverage, no SEX dimension). Per the source-vetting report §6 the API has a hard `$top=1000` cap and the catalog's `dim1_filter` field is the API-specific extension that scopes SEX-disaggregated indicators to the both-sexes aggregate (so the Stage 2 frame is one row per `country, year`). The parser filters non-country `SpatialDimType` records (REGION, WORLDBANKINCOMEGROUP, GLOBAL) at the long-frame level so the wide frame is country-only. The verbatim WHO GHO API `Value` field (e.g. `"76.4 [76.3-76.5]"` with confidence-interval bounds) is preserved as the `source_observations.raw_value` audit trail via a sibling `<variable>_raw_value` column emitted by the read orchestrator. `source_row_reference` is `who_gho_api:<raw_column>:<iso3>` (e.g. `who_gho_api:WHOSIS_000001:MEX`). Test fixture at `tests/fixtures/who_gho_api/cache/2019/` and `cache/2021/` (10 real-format JSON files: 5 indicators × 2 years × 5 countries) is a real slice of the live API captured by `build_sample_cache.py` from the larger `cache_raw/` evidence directory (committed real-format evidence, ~1.2 MB). The 5-country × 1-year × 5-indicator fixture produces 25 source_observations rows in a single-year run; the orchestrator passes the cached-vs-fetched counts on the `WhoGhoApiIngestResult` (8-field Pydantic model, same contract as WDI). Bundle metadata at `data/raw/who_gho_api/metadata.json` documents the API + cache layout. Final split (8 modules, the WDI-style pattern): `who_gho_api.py` 249 (orchestrator + public re-exports + `attribution()` helper), `who_gho_api_io.py` 476 (catalog + paths + parquet write + response parser), `who_gho_api_read.py` 229 (read orchestrator + year resolution), `who_gho_api_http.py` 336 (HTTP + cache + URL builder), `who_gho_api_db.py` 283 (sources + observations + manifest), `who_gho_api_db_helpers.py` 267 (coercion + observation-row builder), `who_gho_api_result.py` 96 (Pydantic result). The `who_gho_api_io` <-> `who_gho_api_read` <-> `who_gho_api_http` cycle is broken by lazy imports inside `read_who_gho_api` (the http module needs the OData API constants from io; the read module needs the http functions + io parser). `WHO_GHO_API_ATTRIBUTION` byte-identical to the canonical citation in `docs/sources/attributions.md`; a drift-guard test enforces it. `STAGE2_ADAPTERS["who_gho_api"]` is registered in `src/leaders_db/ingest/__init__.py` (replacing the `None` placeholder). Ruff clean on all new files. The CLI `leaders-db ingest-source --source who_gho_api --year 2021` runs end-to-end through the production paths (parquet, DB rows, manifest, attribution echo). `docs/architecture/overview.md` Source Locator Table updated to mark `who_gho_api` as `implemented`. Per the user's directive the WHO GHO source-attribution in `docs/sources/attributions.md` was already present from Phase B; no wording change needed.
- **Thin downstream vertical slice 2023 completed (2026-06-18).** Added an explicitly experimental slice at `src/leaders_db/vertical_slice/` with CLI command `leaders-db run-vertical-slice-2023` to prove the Stage 2-to-validation flow before all sources are implemented. Scope: countries `MEX`, `NGA`, `USA`; categories `social_wellbeing` and `integrity`; client rows parsed from `data/raw/client_existing/LATEST BARR'S POLITICAL MATRIX 041725 (1).xlsx` as validation/reference rows only, not as source evidence; social score formula `round(10 * undp_hdi_hdi)` using UNDP HDI 2022 as the 2023 proxy; integrity score formula `round(10 * clamp((wgi_control_of_corruption + 2.5) / 5.0))` using WGI 2022 as the 2023 proxy. After staging `data/raw/world_bank_wgi/wgidataset.xlsx` (2,106,620 bytes, SHA-256 `28f7bc1540df6c5a79bd9769fb8b2413d07a3765f3ef74d8879728b0cd154860`) and running WGI Stage 2 for 2022, the real local run populated the DB with 3 countries, 3 country-years, 3 leaders, 3 ruler-spells, 3 ruler-years, 6 `ruler_scores`, and 6 `validation_results`, and linked 33 source observations (including 3 WGI Control of Corruption observations). The slice now also supports a source-only multi-year output via `--years`; for `2020,2021,2022,2023`, `vertical_slice_timeseries.csv` writes 24 rows (4 years × 3 countries × 2 categories), uses exact/direct source years for 2020-2022, uses the 2022 proxy for 2023, and deliberately excludes client/leader columns because client comparison and DB ruler/score/validation rows remain 2023-only. Outputs written under `data/outputs/vertical_slice_2023/`: `vertical_slice_scores.csv` (6 rows), `vertical_slice_comparison.csv` (6 rows, no skipped inputs), `vertical_slice_timeseries.csv` (24 source-only rows), and `vertical_slice_summary.md` (provisional caveat + UNDP/WGI/client attribution note + 2023-only client-comparison caveat). Tests: `tests/test_vertical_slice_2023.py` has 39 tests; full collected suite is 385 tests and passes. Static reviewer PASS after remediation confirmed no remaining blockers or important issues before the multi-year extension; a static re-review covers the extension.
- **Phase B addendum — CIRIGHTS user-managed (2026-06-17).** User placed CIRI v3.12.10.24 (xlsx + Stata zip + codebook PDF) at `data/raw/cirights/` and asked the docs to flip the verdict. Probe-era "DNS-level unreachable" finding is moot now that the data is on disk. New tally: 14 ✅ vetted_ok, 6 ⚠️ vetted_with_caveats (added `cirights`, user-managed), 4 ❌ blocked, 1 ⏸️ deferred. `data/raw/cirights/metadata.json` written with SHA-256 checksums (all 3 files verified). `docs/sources/registry.md`, `docs/sources/vetting/report.md` (sections 3.8, 4, 5, 6, 8), and `docs/sources/attributions.md` (new "Sources In Use" entry, summary table, citation cheat-sheet, Stage 15 template) updated in the same pass. **For 2023, use 2022 as proxy** — 1-year gap, same shape as `leader_survival`. `cirights` is now eligible for Phase C Stage 2 adapter; the data is on disk and just needs the indicator catalog.
- **Phase B addendum — BTI recovered, flipped to vetted_ok (2026-06-17).** Re-probed BTI per user request — BTI 2026 ("Repression Meets Resistance") is released, the canonical downloads page `/en/downloads` is fully alive. The two 500-returning URLs (`/en/data`, `/en/reports/bti-2024`) are vestigial; the data has moved. User placed `BTI_2006-2026_Scores.xlsx` (cumulative, 12 biennial editions × 137–159 countries × 123 columns) at `data/raw/bti/`; I pulled the BTI 2026 codebook PDF. New tally: 15 ✅ vetted_ok (added `bti`), 6 ⚠️ vetted_with_caveats, 4 ❌ blocked, 0 ⏸️ deferred. **For 2023, use the `BTI 2024` sheet** (BTI 2024 was published in 2024 and covers 2022–2023). Governance / effectiveness category now has 3 sources (WGI + V-Dem governance + BTI). Same three docs updated in the same pass: `docs/sources/registry.md` (registry row), `docs/sources/vetting/report.md` (§3.5, §4, §6, §8, §1 source count, §8 Phase C implications), `docs/sources/attributions.md` (new entry, summary table, citation cheat-sheet, Stage 15 template, EIU cross-ref fixed). 82 tests still green.
- **Phase B addendum — RSF World Press Freedom Index acquired (2026-06-18).** Added `rsf_press_freedom` as a ✅ vetted_ok political-freedom source. Downloaded 24 annual CSVs from RSF's direct pattern (`https://rsf.org/sites/default/files/import_classement/{year}.csv`) into `data/raw/rsf_press_freedom/`: 2002–2010 and 2012–2026. Direct `2011.csv` is absent; RSF treats the period as a combined 2011/2012 edition represented by the 2012 file. Wrote `data/raw/rsf_press_freedom/metadata.json` with SHA-256 checksums, header groups, row counts, encoding notes (`utf-8-sig`, `cp1252`), comma decimal separator, the 2022 blank-row caveat, and the 2022 methodology/schema break. RSF is a press/media-freedom sub-signal, not a replacement for V-Dem/Polity/Freedom House. New tally: 16 ✅ vetted_ok, 7 ⚠️ vetted_with_caveats / user-managed, 4 ❌ blocked, 0 ⏸️ deferred. Updated `docs/sources/registry.md`, `docs/sources/vetting/plan.md`, `docs/sources/vetting/worksheet.md`, `docs/sources/vetting/report.md`, `docs/sources/attributions.md`, `README.md`, and this workplan for coherence.
- **Phase C.9 attempt — PWT Stage 2 ingest BLOCKED on raw bundle (2026-06-18).** Picked up PWT (Penn World Table 10.01) per the priority list, but the Stage 2 contract could not be honored: `data/raw/pwt/` does not exist and no `metadata.json` has been written there. The only PWT file currently on disk is `tmp/source-vetting-evidence/pwt100.xlsx` (6,561,820 bytes, captured 2026-06-17 during the Phase B second-wave probe). Per Always-On Rule #9 and `docs/architecture/local-data-store.md`, Stage 2 adapters must read immutable `data/raw/<source>/` inputs with `metadata.json`; the gitignored `tmp/source-vetting-evidence/` folder is Phase B scratch evidence, not a Stage 2 source of truth, and reading from it would silently treat scratch as canonical — explicitly forbidden. Therefore: **no `ingest_pwt()` was written; no production adapter code was written; no fake data was fabricated.** Action taken: (1) added a `pwt` row to the Source Locator Table in `docs/architecture/overview.md` with the verbatim blocker ("vetted, adapter blocked on raw bundle, raw file `pwt100.xlsx` required, not yet staged"); (2) recorded this blocker entry here in the workplan Done History. The `pwt` row in `STAGE2_ADAPTERS` remains `None`. To unblock: the user stages `pwt100.xlsx` (PWT 10.01, the canonical xlsx for the version reviewed in Phase B) at `data/raw/pwt/pwt100.xlsx` and writes the matching `data/raw/pwt/metadata.json` (source URL `https://www.rug.nl/ggdc/productivity/pwt/`, license note, download date, SHA-256, ingestion_status). Once those are in place, Phase C.9 resumes with the same architect → test-builder → developer → reviewer loop used for the 8 implemented adapters; the indicator catalog (`src/leaders_db/ingest/catalogs/pwt.csv`) is intentionally not created now because authoring it without walking the live column set in the staged xlsx would be guessing. Source-attributions entry for `pwt` already exists at `docs/sources/attributions.md` §1 (`Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015).`) and does not need to change. No code paths, tests, or fixtures were touched; full collected suite baseline (385 tests) was not re-run because no code changed.

- **Phase C.10 — Stage 2 integration pass landed (2026-06-19).** The orchestrators for 9 newly implemented sources (`archigos`, `reign`, `cirights`, `transparency_cpi`, `fas`, `bti`, `rsf_press_freedom`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`) were wired into the central `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py`. The dispatch table now has 26 keys (was 25): 18 wired to real orchestrators, 3 raw-blocked (`polity_v`, `pwt`, `leader_survival`), 4 user-managed/blocked (`freedom_house`, `imf_weo`, `cow_mid`, `nti`), and `cia_world_leaders` (retired). The single source-of-truth principle is preserved: every CLI `--source <key>` argument resolves through the dispatch table, and removing the orchestrator entry causes the CLI to print the standard "not implemented yet" message. Boundary tests: tightened the previously-permissive `test_cirights_dispatch_entry` (was a no-op) to assert wiring; added `test_dispatch_table_wires_*` + `test_dispatch_table_no_duplicate_*_key` for the 6 newly wired sources (`archigos`, `bti`, `reign`, `rsf_press_freedom`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`); updated the 8 pre-existing `expected_keys` sets in `test_ingest_{vdem,wdi,wgi,ucdp,sipri_milex,sipri_yearbook_ch7,who_gho_api}` to include `rsf_press_freedom` (the one key missing from the older tests that the new dispatch table adds). New focused test count: 277 passing across the 7 newly integrated source test files. Full suite: **817 passing** (was 805 before the integration; +12 from the new dispatch-wiring tests). Ruff clean on all changed files. `docs/architecture/overview.md` Source Locator Table and Category Source Plans updated; `docs/sources/registry.md` already had the 7 newly integrated sources' registry rows; `docs/sources/attributions.md` already had the entries (the orchestrator attribution constants are byte-identical to the doc, drift-guarded). The Phase C.10 entry ties together the per-source addenda added by the subagents into one coherent registry, and the same entry also documents the 3 remaining raw-blocked sources (`polity_v`, `pwt`, `leader_survival`).

- **Phase D.1 — First deterministic scorer landed: `social_wellbeing` (2026-06-19).** The first per-category deterministic scorer is implemented at `src/leaders_db/score/social_wellbeing.py` (facade) with three private supporting modules under the same package: `_social_wellbeing_rubric.py` (group weights and variable→group map), `_social_wellbeing_components.py` (per-group component/ref computation, 1..10 scale mapping, leader-name fallback), and `_social_wellbeing_flags.py` (missingness summary, proxy count, flag detection, rationale). All four files are ≤ 400 lines (facade 399, rubric 150, components 196, flags 200). Public import path `leaders_db.score.social_wellbeing.score_social_wellbeing` is preserved unchanged across the split; `score_social_wellbeing` and `CATEGORY_KEY` are also re-exported from `leaders_db.score` (the package root) so the Stage 9 pipeline can wire the scorer through a single import. The scorer is the deterministic entry point for one country-year/category; the client 2023 matrix is **never** used as evidence (always-on rule #6) — the scorer strips `EXCLUDED_SOURCE_KEYS` (`client_existing` / `client_matrix`) at the boundary as defence-in-depth in case the Stage 5 bundle builder forgets the upstream exclusion. The minimum-viable gate now counts **distinct sources of usable observations** (normalized_value not None, in-plan variable, non-client source) rather than all distinct sources — this closes a reviewer blocker where a source whose row arrived with `normalized_value=None` was previously counted as viable evidence. The insufficient-data path is the SOCIAL_WELLBEING_PLAN's `SparseDataPolicy.INSUFFICIENT_DATA` branch: scores `None`, `is_insufficient_data=True`, both `INSUFFICIENT_DATA` and `SPARSE_DATA` flags fire. Proof surface (all green): 16 happy-path tests in `tests/test_score_social_wellbeing.py`, 9 flag-detection tests in `tests/test_score_social_wellbeing_flags.py`, 3 client-comparison tests in `tests/test_score_social_wellbeing_client.py`, 6 reviewer-blocker regression tests in `tests/test_score_social_wellbeing_remediation.py` (including the wiring boundary test that fails if the package-root export is removed), and 2 new bundle contract tests in `tests/test_score_evidence_contract.py` (`test_bundle_usable_observations_excludes_null_normalized_rows` and `test_bundle_usable_observations_excludes_client_source_keys`). Full suite: **1088 passing** (was 1082 before the scorer landed; +6 from the new remediation tests, +2 from the new bundle-contract tests; the pre-existing `test_score_social_wellbeing_observation_with_none_normalized_is_skipped` was updated to pair the null observation with a second *usable* undp_hdi observation so the bundle still clears the new usable-evidence gate while the test's intent — "null observations do not contribute" — is preserved). Ruff clean on all changed files. **Limitations / next:** the scorer is deterministic-only; it does not call the LLM, does not compute the §11 confidence score, and does not apply the client delta (those are downstream). The other seven categories (`political_freedom`, `economic_wellbeing`, `international_peace`, `domestic_violence`, `integrity`, `effectiveness`, `nuclear`) remain pending — the existing `political_freedom.py` is still a stub. The Stage 3/4 leader resolver, the comparison stage, the manual-review queue, and the summary report are also still pending; the vertical-slice scoring path (`src/leaders_db/vertical_slice/scoring.py`) is the only other path that currently emits a per-category score, and it uses its own single-source formula.

- **Phase D.2 — Stage 9 narrow single-country read-only seam wired (2026-06-19).** The Phase D.1 scorer is wired into a thin Stage 9 production path end-to-end. Three new modules land: `src/leaders_db/score/dispatch.py` (single ``category_key → scorer function`` registry — ``supported_score_categories()``, ``get_category_scorer(key)``, ``score_category_bundle(bundle)``); `src/leaders_db/score/stage9.py` (the orchestration seam — ``score_category_for_country(session, *, country_iso3, year, category_key, leader_name=None) -> ScoreResult`` composes ``build_category_evidence_bundle`` + ``score_category_bundle``); and the CLI surface ``leaders-db score-category --category <cat> --year <year> --country <ISO3>`` (single-country path; ``--country`` omission keeps the existing batch "not implemented yet" placeholder). Only ``social_wellbeing`` is registered; adding a new category is a one-line ``_SCORERS`` edit. **Scope is deliberately narrow**: read-only, single country-year, **no** ``ruler_scores`` persistence (Stage 4 leader resolver is still pending), **no** LLM escalation, **no** client-matrix consultation, **no** batch materialization. The seam is a thin reporting path, not a persistence path. Public import paths ``leaders_db.score.social_wellbeing.score_social_wellbeing`` and ``leaders_db.score.dispatch.score_category_bundle`` are stable. Boundary tests pin the contract: ``tests/test_score_dispatch.py`` (14 tests: supported set is exactly ``("social_wellbeing",)``; dispatch routes the bundle to the real scorer; unsupported category raises ``ValueError`` listing the supported set and pointing at ``_SCORERS``); ``tests/test_score_stage9.py`` (6 tests: end-to-end Mexico 2023 ``social_wellbeing`` against an isolated SQLite DB returns a real ``ScoreResult`` with 10 observation refs across 4 distinct sources; the sparse-bundle path returns ``is_insufficient_data=True``; unsupported-category and missing-country raise ``ValueError`` with the expected messages). CLI tests in ``tests/test_cli_smoke.py`` (4 new tests: stub message preserved when ``--country`` is omitted; unsupported category with ``--country`` fails with ``BadParameter`` listing ``social_wellbeing``; ``--country ZZZ`` with no DB row fails with the expected message; ``--country MEX --category social_wellbeing --year 2023`` against a seeded isolated DB prints the score summary block). All 4 new tests + the 14 dispatch + 6 stage9 tests pass; full suite is **1116 passing** (up from 819 before; +24 new). Ruff clean on all changed files. The deferred import of ``build_category_evidence_bundle`` inside ``score_category_for_country`` documents the cycle-avoidance rationale (the package root ``leaders_db.score`` eagerly imports ``stage9``; ``stage9`` cannot eagerly import ``resolve.indicators`` without a circular). Phase D.2 closes the gap between "we have a deterministic scorer" and "we can run it against a real DB row"; Phase E work (persistence, batch materialization, the remaining 7 category scorers, comparison, manual-review queue, summary report) follows.

- **Phase D.3 — Stage 9 all-countries 2022 social_wellbeing vertical slice landed (2026-06-19).** The Phase D.2 single-country seam is extended into a thin read-only all-countries batch path. Three additions to `src/leaders_db/score/stage9.py`: ``score_category_for_all_countries(session, *, year, category_key) -> tuple[ScoreResult, ...]`` (iterates ``countries`` ordered by ``iso3`` and delegates to the per-country seam; countries with no eligible observations return a clean ``is_insufficient_data=True`` row rather than being dropped), ``write_score_results_csv(results, output_path)`` (atomic-rename CSV writer with the canonical missingness-investigation columns declared as a module-level tuple ``SCORE_RESULTS_CSV_COLUMNS``), and the ``_score_result_to_row`` row builder. Insufficient-data rows write the literal ``"NA"`` sentinel for both score columns so a reviewer can sort / filter / count missingness without re-deriving the value; the ``review_flags`` column is pipe-separated. The CLI ``leaders-db score-category`` gains ``--all-countries`` (boolean, mutually exclusive with ``--country``) and ``--output <path>`` (overrides the default ``data/outputs/<category>_<year>_scores.csv``; parent directories created). The body of the new path is extracted into ``_run_score_category_all_countries`` so the Typer callback stays under the 50-statement convention. **Scope remains narrow**: read-only, one year, **no** ``ruler_scores`` persistence (Stage 4 leader resolver still pending), **no** LLM escalation, **no** client-matrix consultation, **no** persistence of any kind (only the per-country CSV is written). The seam is the canonical reusable pattern for the per-category vertical slices that follow ``social_wellbeing`` — each new category reuses the same call shape; only ``category_key`` changes once the next per-category scorer lands. New focused test count: 17 tests across ``tests/test_score_stage9_batch.py`` (the new batch + CSV suite, 11 tests) and ``tests/test_cli_score_category_batch.py`` (the CLI surface for the new path, 6 tests). Boundary tests pin the contract: ``score_category_for_all_countries`` returns one ``ScoreResult`` per ``Country`` in ``iso3`` order; the dense MEX row gets a real score (10 observation refs across 4 sources) while the empty BRA row emits a clean insufficient-data result; the result is a real ``tuple`` (not a generator) so the CSV writer and a future summary can both walk it; the CSV header matches ``SCORE_RESULTS_CSV_COLUMNS`` exactly and includes the missingness-investigation columns (``observed_count``, ``expected_count``, ``missing_count``, ``missing_primary_count``); the CLI fails fast on unsupported category, refuses ``--country`` + ``--all-countries`` together with a clear mutual-exclusion message, prints the concise ``rows / scored_count / insufficient_count / output_path`` summary, and keeps the existing no-flag batch stub intact. Module sizes: ``src/leaders_db/cli.py`` 821 lines (was 689; +132 from the new flags + extracted ``_run_score_category_all_countries`` helper; the 400-line convention is for test + source files, and the CLI is documented as "thin" in ``docs/architecture/overview.md``); ``src/leaders_db/score/stage9.py`` 444 lines (was 149; +295 from the batch seam + CSV helper; ~10% over the 400-line convention because the module owns three distinct concerns — per-country seam, batch seam, CSV writer — each with full docstrings; splitting was deferred to avoid premature partitioning per the WDI precedent where ``wdi_io.py`` was accepted at 479 lines with explicit workplan notes); ``tests/test_score_stage9.py`` 292 lines; ``tests/test_score_stage9_batch.py`` 422 lines (the focused seed-fixture block is the bulk); ``tests/test_cli_score_category_batch.py`` 337 lines; ``tests/test_cli_smoke.py`` 332 lines. Ruff clean on all changed files; ``git diff --check`` clean.
- **Phase D.4 — Stage 9 CSV carries normative source attribution block (2026-06-19).** Closes the AGENTS.md rule #15 reviewer blocker on the Phase D.3 all-countries CSV slice. New focused module `src/leaders_db/score/_attributions.py` (161 lines) owns the single-source-of-truth mapping :data:`CATEGORY_SOURCE_ATTRIBUTIONS` (`category_key` → tuple of `(source_key, attribution_text)` pulled verbatim from `docs/sources/attributions.md` §1) and the helper `build_attribution_comment_lines` that emits the per-category `# Attribution: <text>` comment lines. Only `social_wellbeing` is mapped today (the 4 expected sources per `SOCIAL_WELLBEING_PLAN.expected_sources`: `undp_hdi`, `who_gho_api`, `world_bank_wdi`, `vdem`); `client_existing` is explicitly excluded per AGENTS.md rule #6 (the client 2023 matrix is validation reference, never an attribution source). `write_score_results_csv` gains an optional `category_key=` kwarg and writes the attribution comment block at the top of the file **before** the stable `SCORE_RESULTS_CSV_COLUMNS` header so the data shape is byte-for-byte unchanged for every existing consumer. The writer derives the category from the first `ScoreResult` when the kwarg is omitted (keeps the existing single-`ScoreResult` test path working unchanged); the CLI passes the explicit category so the block is present even on an empty batch. **Final CSV shape** (the only shape accepted as a public output by this seam):

  ```
  # Attribution: UNDP HDR 2023-24 (United Nations Development Programme 2024).
  # Attribution: WHO Global Health Observatory (World Health Organization).
  # Attribution: World Bank WDI (World Bank 2024).
  # Attribution: V-Dem v16 (Coppedge et al. 2026).
  iso3,country_name,year,category_key,system_proposed_score_1_10,normalized_score_0_1,score_status,is_insufficient_data,human_review_required,review_flags,observed_count,expected_count,missing_count,missing_primary_count,observation_ref_count,rationale_short
  BRA,Brazil,2023,social_wellbeing,NA,NA,insufficient_data,True,True,insufficient_data|sparse_data,0,17,17,1,0,
  MEX,Mexico,2023,social_wellbeing,8,0.7800,scored,False,False,,10,17,7,0,10,UNDP HDI composite + components ...
  ```

  Consumers parse with `csv.reader` and skip rows whose first cell starts with `#`, or use `pandas.read_csv(..., comment="#")`. The attribution block is additive metadata only; the data header remains `SCORE_RESULTS_CSV_COLUMNS` (16 columns, unchanged from Phase D.3). New focused test count: 12 tests in `tests/test_score_stage9_attribution.py` (a sibling file so the canonical `test_score_stage9_batch.py` stays under the 400-line convention; both files share the seed / CSV-reader helpers via direct import) — covering the helper's per-source emission, byte-for-byte match against the doc strings, no `client_existing`, `comment="#"` parsing round-trip, explicit kwarg override, and the no-attribution-on-unknown-category defensive path — plus 1 new CLI test in `tests/test_cli_score_category_batch.py` (`test_score_category_all_countries_csv_carries_attribution`) that asserts the block is present in the actual `data/outputs/social_wellbeing_2023_scores.csv` produced by the CLI surface (the runtime proof of AGENTS.md rule #15 end-to-end). The `_read_csv_rows` helper in `test_score_stage9_batch.py` was extended to skip `#`-prefixed rows so the existing column-shape assertions still hold without modification; an `_read_attribution_lines` companion helper returns the raw attribution lines so the comment-block contract is pinned independently of the data-shape contract. Module sizes: `src/leaders_db/score/_attributions.py` 161 lines (new, focused single-purpose module); `src/leaders_db/score/stage9.py` 497 lines (was 444; +53 from the `category_key` kwarg, the attribution resolution block, and the comment-line write loop — still within tolerance per the WDI precedent of accepted-oversized modules); `tests/test_score_stage9_batch.py` 468 lines (was 422; +46 from the helper updates — the file is ~17% over the 400-line convention; the comment-skipping helper and the `_read_attribution_lines` companion carry the attribution-block contract alongside the existing data-shape contract, and splitting them into the new sibling would force a circular import); `tests/test_score_stage9_attribution.py` 363 lines (new, focused sibling); `tests/test_cli_score_category_batch.py` 431 lines (was 337; +94 from the new CLI attribution test). Full suite: **1146 passing** (was 1116 before; +30 from the new attribution tests). Ruff clean on all changed files; `git diff --check` clean.

- **Phase D.5 — `integrity` per-category scorer landed + Stage 9 slimmed + test files split (2026-06-19).** Closes the three reviewer blockers from the Phase D.4 review: (a) only `social_wellbeing` is registered / mapped so the dispatcher and the CSV attribution both fail to cover the second implemented scorer; (b) `src/leaders_db/score/stage9.py` carried the per-country seam, the batch seam, AND the CSV writer in one 497-line module — over the 400-line convention; (c) `tests/test_score_stage9_batch.py` and `tests/test_cli_score_category_batch.py` are at 468 / 431 lines (~17% / ~8% over the convention). Three focused changes land:

  1. **`integrity` is implemented and wired into the dispatcher.** The second per-category deterministic scorer follows the same facade + private-modules split as `social_wellbeing`. New modules: `src/leaders_db/score/integrity.py` 325 lines (facade + `score_integrity` + `CATEGORY_KEY = "integrity"` + public re-exports), `src/leaders_db/score/_integrity_rubric.py` 129 lines (component weights and variable→component map), `src/leaders_db/score/_integrity_components.py` 220 lines (per-component bookkeeping, scale mapping, leader-name fallback), `src/leaders_db/score/_integrity_flags.py` 247 lines (flag detection: `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE` / `INSUFFICIENT_DATA` + `human_review_required` invariant). All four files are ≤ 400 lines. `src/leaders_db/score/dispatch.py` `_SCORERS` is now `{"social_wellbeing": score_social_wellbeing, "integrity": score_integrity}`; `supported_score_categories()` returns `("integrity", "social_wellbeing")` (lexicographic); `get_category_scorer("integrity")` returns the real scorer (boundary test fails if the entry is removed). `score_integrity` is re-exported from the package root `leaders_db.score` (`__init__.py`) so the dispatcher and the future Stage 9 caller import it through one path. The scorer strips `EXCLUDED_SOURCE_KEYS` (`client_existing` / `client_matrix`) at the boundary (defence-in-depth in case the bundle builder forgets the upstream exclusion). The minimum-viable gate counts **distinct sources of usable observations** (not all distinct sources — the same rule as Phase D.1). The insufficient-data path is `SparseDataPolicy.INSUFFICIENT_DATA`; scores `None`, `is_insufficient_data=True`, both `INSUFFICIENT_DATA` and `SPARSE_DATA` flags fire.

  2. **Integrity attribution mapping added to `_attributions.py`.** The single-source-of-truth mapping :data:`CATEGORY_SOURCE_ATTRIBUTIONS` now has an `integrity` entry with the three expected sources per `INTEGRITY_PLAN.expected_sources`: `("wgi", "World Bank WGI (World Bank 2023).")`, `("vdem", "V-Dem v16 (Coppedge et al. 2026).")`, `("ti_cpi", "Transparency International CPI 2023.")`. `client_existing` is excluded per AGENTS.md rule #6. The block is emitted by the same `write_score_results_csv(category_key="integrity")` path that emits the social-wellbeing block — `tests/test_score_stage9_csv.py::test_write_score_results_csv_includes_integrity_attribution` is the runtime proof that the dispatcher / Stage 9 CLI can produce a per-category attribution block for both wired categories. Module size: `src/leaders_db/score/_attributions.py` 184 lines (was 161; +23 from the integrity tuple).

  3. **Stage 9 CSV writer extracted to `_stage9_csv.py`; `stage9.py` slimmed.** The CSV column declaration, the row builder, the NA sentinel, and the atomic-rename writer move into a new focused module `src/leaders_db/score/_stage9_csv.py` (284 lines). `src/leaders_db/score/stage9.py` drops from 497 lines to 278 lines (under the 400-line convention) — it now owns only the per-country and all-countries seams and re-exports the writer / column tuple via `from ._stage9_csv import SCORE_RESULTS_CSV_COLUMNS, write_score_results_csv`. Public import path `leaders_db.score.stage9.write_score_results_csv` is preserved unchanged across the split, so the CLI and every test surface keep importing from the same path.

  4. **Remediation test surface added; oversized test files split.** Four sibling integrity test files land following the same facade + private-modules split: `tests/test_score_integrity.py` 203 lines (happy path / rubric weights / missingness rollup), `tests/test_score_integrity_components.py` 276 lines (per-component bookkeeping + scale mapping + rationale + leader fallback + determinism + per-observation client exclusion), `tests/test_score_integrity_flags.py` 298 lines (flag-detection paths and `human_review_required` invariant), `tests/test_score_integrity_remediation.py` 327 lines (the **client-contamination / missingness correctness** reviewer-blocker regression tests — three tests: client `MissingObservation` rows do not inflate missingness counts / by_reason / by_severity, do not trigger `MISSING_PRIMARY_SOURCE` through `primary_missing_observations`, and are filtered in the insufficient-data branch as well). Test fixtures live in `tests/_integrity_factories.py` (mirror of `_social_wellbeing_factories`). Dispatcher tests in `tests/test_score_dispatch.py` grew from 14 to 18 — adding the `integrity` happy-path / registry / unsupported-list assertions (the registry's lex-sorted shape is `("integrity", "social_wellbeing")`; the `political_freedom` / `economic_wellbeing` / `corruption` / `domestic_violence` / `international_peace` / `nuclear` / `effectiveness` parametrized unsupported set is unchanged). The oversized test files are split under the focused-file convention:

     - `tests/test_score_stage9_batch.py` (348 lines) keeps the all-countries batch seam (`score_category_for_all_countries`) and the shared `_seed_mexico_and_brazil` / `_read_csv_rows` / `_read_attribution_lines` / `_is_comment_row` helpers used by the CSV writer test siblings.
     - `tests/test_score_stage9_batch_csv.py` (239 lines, new) is the writer's data-shape contract — NA sentinel for insufficient rows, missingness columns populated, pipe-separated `review_flags`, parent-directory creation, atomic-rename.
     - `tests/test_score_stage9_csv.py` (322 lines, unchanged) is the writer's attribution-block contract.
     - `tests/test_cli_score_category_batch.py` (259 lines) keeps the happy-path CLI surface (default output path, summary block, `--output` override).
     - `tests/test_cli_score_category_batch_errors.py` (161 lines, new) is the error paths — unsupported category, `--country` + `--all-countries` mutual exclusion, no-flag batch stub preserved.
     - `tests/test_cli_score_category_batch_attribution.py` (238 lines, new) is the AGENTS.md rule #15 runtime proof at the CLI surface.

           Each split file is under the 400-line convention; the helpers and seed factory are duplicated once between the two CLI siblings (no private-import chain) so each CLI test file is standalone-runnable. The split is consistent with the `social_wellbeing` / `integrity` split pattern: facade + private-modules + focused sibling tests, no `__init__` orchestrator. Full suite: **1179 passing** (was 1146 before; +33 from the new integrity tests, dispatcher growth, and the CLI / batch_csv split). Ruff clean on all changed files; `git diff --check` clean.

- **Phase D.6 — `political_freedom` per-category scorer landed (2026-06-19).** The fifth per-category deterministic scorer follows the same facade + private-modules split as `social_wellbeing` / `integrity` / `effectiveness` / `economic_wellbeing`. The `NotImplementedError` stub at `src/leaders_db/score/political_freedom.py` is replaced with the deterministic 3-group rubric (V-Dem democratic / liberal / civil-liberties 0.50, BTI political transformation 0.30, RSF press freedom 0.20); `POLITICAL_FREEDOM_PLAN` ships with 16 indicators (7 V-Dem, 7 BTI, 2 RSF) and `minimum_viable_sources=2` + `SparseDataPolicy.INSUFFICIENT_DATA` so a below-threshold bundle returns a clean `is_insufficient_data=True` result with the full derived flag set (`INSUFFICIENT_DATA` prepended before `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE`). New modules: `src/leaders_db/score/political_freedom.py` 385 lines (facade + `score_political_freedom` + `CATEGORY_KEY = "political_freedom"`), `src/leaders_db/score/_political_freedom_rubric.py` 170 lines (3 group weights and 16-row variable→group map), `src/leaders_db/score/_political_freedom_components.py` 221 lines (per-group component bookkeeping, 1..10 scale mapping, leader-name fallback), `src/leaders_db/score/_political_freedom_flags.py` 247 lines (flag detection: `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE` / `INSUFFICIENT_DATA` + `human_review_required` invariant). All four files are ≤ 400 lines. `src/leaders_db/score/dispatch.py` `_SCORERS` is now `{"social_wellbeing": ..., "integrity": ..., "effectiveness": ..., "economic_wellbeing": ..., "political_freedom": score_political_freedom}`; `supported_score_categories()` returns the lexicographically-sorted 5-tuple; `get_category_scorer("political_freedom")` returns the real scorer (boundary test fails if the entry is removed). `score_political_freedom` is re-exported from the package root `leaders_db.score` (`__init__.py`). The scorer strips `EXCLUDED_SOURCE_KEYS` (`client_existing` / `client_matrix`) at the boundary (defence-in-depth in case the bundle builder forgets the upstream exclusion). The minimum-viable gate counts **distinct sources of usable observations** (same rule as the prior four scorers). Attribution mapping added to `_attributions.py` — `political_freedom` → `(vdem, rsf_press_freedom, bti)` with verbatim attribution text from `docs/sources/attributions.md` §1. Five new test files land: `tests/test_score_political_freedom.py` 299 lines (happy path / rubric weights / missingness rollup), `tests/test_score_political_freedom_components.py` 297 lines (per-component bookkeeping + scale mapping + rationale + leader fallback + determinism + per-observation client exclusion), `tests/test_score_political_freedom_flags.py` 283 lines (flag-detection paths and `human_review_required` invariant), `tests/test_score_political_freedom_insufficient_flags.py` 212 lines (the insufficient-data branch flag-derivation regression — the `detect_flags` prepending pattern closed on the prior scorers), `tests/test_score_political_freedom_remediation.py` 335 lines (the **client-contamination / missingness correctness** reviewer-blocker regression tests — three tests: client `MissingObservation` rows do not inflate missingness counts / by_reason / by_severity, do not trigger `MISSING_PRIMARY_SOURCE` through `primary_missing_observations`, and are filtered in the insufficient-data branch as well). Production seam proof in `tests/test_score_stage9_political_freedom.py` 401 lines (8 tests: MEX 2023 dense bundle → real `ScoreResult` with 16 observation refs across 3 sources; BRA empty bundle → clean insufficient-data; batch seam returns one row per country in iso3 order). Test factories in `tests/_political_freedom_factories.py` 169 lines (mirror of the prior four factory files). Full suite: **1329 passing** (was 1280 before; +49 from the new political_freedom unit / insufficient / remediation / components / flags / stage9 tests, the dispatcher / stage9 / CLI unsupported-category test updates from `political_freedom` to `corruption`, the new `test_write_score_results_csv_includes_political_freedom_attribution`, the new dispatcher boundary tests for `political_freedom`, and the new dispatcher package-root re-export test). Ruff clean on all changed files; `git diff --check` clean.

- **Phase D.7 — `domestic_violence` per-category scorer landed (2026-06-20).** The sixth per-category deterministic scorer follows the same facade + private-modules split as `social_wellbeing` / `integrity` / `effectiveness` / `economic_wellbeing` / `political_freedom`. The `NotImplementedError` stub at `src/leaders_db/score/domestic_violence.py` is replaced with the deterministic 4-group rubric (PTS state-terror 0.30, CIRIGHTS physical-integrity / repression 0.35, UCDP one-sided violence 0.20, V-Dem civil-liberties / repression 0.15); `DOMESTIC_VIOLENCE_PLAN` ships with 17 indicators (3 PTS, 7 CIRIGHTS, 2 UCDP, 5 V-Dem) and `minimum_viable_sources=2` + `SparseDataPolicy.INSUFFICIENT_DATA` so a below-threshold bundle returns a clean `is_insufficient_data=True` result with the full derived flag set (`INSUFFICIENT_DATA` prepended before `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE`). New modules: `src/leaders_db/score/domestic_violence.py` 399 lines (facade + `score_domestic_violence` + `CATEGORY_KEY = "domestic_violence"`), `src/leaders_db/score/_domestic_violence_rubric.py` 203 lines (4 group weights and 17-row variable→group map), `src/leaders_db/score/_domestic_violence_components.py` 223 lines (per-group component bookkeeping, 1..10 scale mapping, leader-name fallback), `src/leaders_db/score/_domestic_violence_flags.py` 260 lines (flag detection: `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE` / `INSUFFICIENT_DATA` + `human_review_required` invariant). All four files are ≤ 400 lines. `src/leaders_db/score/dispatch.py` `_SCORERS` adds the `domestic_violence` entry; `supported_score_categories()` returns the lexicographically-sorted 6-tuple; `get_category_scorer("domestic_violence")` returns the real scorer (boundary test fails if the entry is removed). `score_domestic_violence` is re-exported from the package root `leaders_db.score` (`__init__.py`). The scorer strips `EXCLUDED_SOURCE_KEYS` (`client_existing` / `client_matrix`) at the boundary (defence-in-depth, same rule as the prior five scorers). The minimum-viable gate counts distinct sources of usable observations. Attribution mapping added to `_attributions.py` — `domestic_violence` → `(pts, cirights, ucdp, vdem)` with verbatim attribution text from `docs/sources/attributions.md` §1. Six new test files land: `tests/test_score_domestic_violence.py` (11 tests, happy path / rubric weights / missingness rollup including the rubric-weighted expected-score check that pins normalized=0.605 → 6/10 for the realistic fixture), `tests/test_score_domestic_violence_components.py` (10 tests, per-component bookkeeping + scale mapping + rationale + leader fallback + determinism + per-observation client exclusion), `tests/test_score_domestic_violence_flags.py` (11 tests, flag-detection paths and `human_review_required` invariant), `tests/test_score_domestic_violence_insufficient_flags.py` (5 tests, insufficient-data branch flag-derivation regression — the `detect_flags` prepending pattern closed on the prior scorers), `tests/test_score_domestic_violence_remediation.py` (3 tests, the **client-contamination / missingness correctness** reviewer-blocker regression tests — client `MissingObservation` rows do not inflate missingness counts / by_reason / by_severity, do not trigger `MISSING_PRIMARY_SOURCE` through `primary_missing_observations`, and are filtered in the insufficient-data branch as well), and `tests/test_score_stage9_domestic_violence.py` (8 tests, the Stage 9 production seam proof — MEX 2023 dense bundle → real `ScoreResult` with 17 observation refs across 4 sources; sparse bundle with single source → insufficient-data; batch seam returns one row per country in iso3 order with BRA empty → clean insufficient-data). Test factories in `tests/_domestic_violence_factories.py` 191 lines (mirror of the prior five factory files). `tests/test_score_dispatch.py` grows from 20 to 21 tests (the new `domestic_violence` boundary + registry entry + re-export assertion; the parametrized unsupported-category set shrinks from `{corruption, domestic_violence, international_peace, nuclear}` to `{corruption, international_peace, nuclear}` since `domestic_violence` is now wired). `tests/test_score_stage9_attribution.py` grows from 7 to 8 tests with the new `domestic_violence_emits_four_lines` test plus the `domestic_violence` addition to the byte-for-byte substring assertion. Full suite: **1379 passing** (was 1329 before; +50 from the new domestic-violence tests, the dispatcher / stage9 attribution wiring updates, and the new `domestic_violence` Stage 9 DB-backed proof). Ruff clean on all changed files; `git diff --check` clean. **Limitations / next:** the scorer is deterministic-only; it does not call the LLM, does not compute the §11 confidence score, and does not apply the client delta (those are downstream, same as the prior five scorers). The remaining un-wired categories are `corruption`, `international_peace`, and `nuclear`. The Stage 4 leader resolver, the comparison stage, the manual-review queue, and the summary report remain pending.


- **Phase D.8 — `international_peace` per-category scorer landed (2026-06-20).** The seventh per-category deterministic scorer follows the same facade + private-modules split as `social_wellbeing` / `integrity` / `effectiveness` / `economic_wellbeing` / `political_freedom` / `domestic_violence`. The legacy `NotImplementedError` stub at `src/leaders_db/score/peace.py` is preserved as a back-compat surface (raises `NotImplementedError` + emits `DeprecationWarning` pointing at the new module) while the canonical deterministic implementation lands at `src/leaders_db/score/international_peace.py`. The rubric is a transparent 2-group split (UCDP conflict involvement 0.65, SIPRI Military Expenditure 0.35); `INTERNATIONAL_PEACE_PLAN` ships with 8 indicators (4 UCDP state-based + internationalized, 4 SIPRI milex share/scale), all `LOWER_IS_BETTER`, and `minimum_viable_sources=2` + `SparseDataPolicy.INSUFFICIENT_DATA` so a below-threshold bundle returns a clean `is_insufficient_data=True` result with the full derived flag set (`INSUFFICIENT_DATA` prepended before `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE`). New modules: `src/leaders_db/score/international_peace.py` 382 lines (facade + `score_international_peace` + `CATEGORY_KEY = "international_peace"`), `src/leaders_db/score/_international_peace_rubric.py` 169 lines (2 group weights and 8-row variable→group map), `src/leaders_db/score/_international_peace_components.py` 223 lines (per-group component bookkeeping, 1..10 scale mapping, leader-name fallback), `src/leaders_db/score/_international_peace_flags.py` 287 lines (flag detection: `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE` / `INSUFFICIENT_DATA` + `human_review_required` invariant; rationale suppresses numeric-score sentence on insufficient-data path to match the reviewer-blocker fix from `domestic_violence`). All four files are ≤ 400 lines. `src/leaders_db/score/dispatch.py` `_SCORERS` adds the `international_peace` entry; `supported_score_categories()` returns the lexicographically-sorted 7-tuple; `get_category_scorer("international_peace")` returns the real scorer (boundary test fails if the entry is removed). `score_international_peace` is re-exported from the package root `leaders_db.score` (`__init__.py`). The scorer strips `EXCLUDED_SOURCE_KEYS` (`client_existing` / `client_matrix`) at the boundary (defence-in-depth in case the bundle builder forgets the upstream exclusion). New `CATEGORY_SOURCE_ATTRIBUTIONS` entry for `international_peace` maps the 2 expected sources (`ucdp` → "UCDP GED 23.1 (Davies et al. 2023).", `sipri_milex` → "SIPRI milex (Stockholm International Peace Research Institute 2026)."); `client_existing` is excluded per AGENTS.md rule #6. CLI help text for `score-category --category` lists `international_peace` alongside the other registered categories. Six new test files land following the same facade + private-modules split: `tests/test_score_international_peace.py` (happy path / rubric weights / missingness rollup), `tests/test_score_international_peace_components.py` (per-component bookkeeping + scale mapping + rationale + leader fallback + determinism + per-observation client exclusion), `tests/test_score_international_peace_flags.py` (flag-detection paths and `human_review_required` invariant), `tests/test_score_international_peace_insufficient_flags.py` (insufficient-data branch: derived `MISSING_PRIMARY_SOURCE` / `SPARSE_DATA` / `LOW_CONFIDENCE` triples, the rationale-doesn't-state-numeric-score reviewer-blocker fix, the client-source filter), `tests/test_score_international_peace_remediation.py` (the **client-contamination / missingness correctness** regression tests — three tests: client `MissingObservation` rows do not inflate missingness counts / by_reason / by_severity, do not trigger `MISSING_PRIMARY_SOURCE` through `primary_missing_observations`, and are filtered in the insufficient-data branch as well), and `tests/_international_peace_factories.py` (the shared test factories: `international_peace_make_obs`, `international_peace_make_bundle`, `realistic_international_peace_observations`). Two new Stage 9 production-seam proof files: `tests/test_score_stage9_international_peace.py` (single-country + sparse-bundle + batch-seam tests; seeds MEX 2023 with UCDP + SIPRI milex observations across all 8 indicators) and `tests/test_score_stage9_international_peace_batch.py` (CSV-facing insufficient-data rationale proof, mirroring the `domestic_violence_batch` sibling). Dispatcher tests in `tests/test_score_dispatch.py` grew to add the `international_peace` happy-path / registry / unsupported-list assertions (the registry's lex-sorted shape is now `('domestic_violence', 'economic_wellbeing', 'effectiveness', 'integrity', 'international_peace', 'political_freedom', 'social_wellbeing')`; the `corruption` / `nuclear` parametrized unsupported set is unchanged). Attribution tests in `tests/test_score_stage9_attribution.py` grew to add the `international_peace` per-category line-count assertion + the `sipri_milex` substring to the byte-for-byte text match, and `tests/test_score_stage9_csv_categories.py` grew to add the `international_peace` per-category explicit-kwarg writer test. Each new test file is under the 400-line convention. The `peace.py` legacy stub keeps the `from leaders_db.score.peace import score_peace` import path working with a `DeprecationWarning` + `NotImplementedError` so a stale caller fails fast.


- **Phase D.9 — `nuclear` per-category scorer landed (2026-06-20).** The eighth and final per-category deterministic scorer follows the same facade + private-modules split as the 7 prior scorers. The legacy `NotImplementedError` stub at `src/leaders_db/score/nuclear.py` is replaced with the deterministic 2-group rubric (FAS nuclear forces 0.60, SIPRI Yearbook Ch.7 nuclear forces 0.40); `NUCLEAR_PLAN` ships with 8 indicators (5 FAS consolidated-status-page indicators, 3 SIPRI Yearbook Ch.7 Table-7.1 indicators) and `minimum_viable_sources=1` + `SparseDataPolicy.PROVISIONAL_SCORE`. The nuclear specialization (per requirement §6 "most countries are non-nuclear") is **non-nuclear states must never receive an invented numeric score**: the scorer treats every below-threshold bundle as insufficient-data, and the rationale explicitly says "non-nuclear state or no FAS / SIPRI Yearbook Ch.7 row" so a manual-review reader can distinguish a non-nuclear country (~190 of ~200 prototype countries) from a sparse-bundle pathology. The :attr:`ReviewFlag.NUCLEAR_CASE` population-split flag fires on the **scored** path iff the bundle carries any usable FAS / SIPRI Yearbook Ch.7 observation (the §14 manual-review-queue hook per REQ-REV-002); the flag is deliberately **not** added on the insufficient-data path. New modules: `src/leaders_db/score/nuclear.py` 399 lines (facade + `score_nuclear`), `src/leaders_db/score/_nuclear_rubric.py` 199 lines (2 group weights, 8-row variable→group map), `src/leaders_db/score/_nuclear_components.py` 251 lines (per-group bookkeeping, scale mapping, leader fallback, client re-filter, nuclear-source-evidence helper), `src/leaders_db/score/_nuclear_flags.py` 365 lines (flag detection + rationale with nuclear-specific "non-nuclear / no nuclear-source evidence" wording). All four files ≤ 400 lines. Dispatcher `_SCORERS` adds the `nuclear` entry; `supported_score_categories()` returns the lexicographically-sorted 8-tuple. Attribution mapping adds `nuclear` with the 2 expected sources (`fas`, `sipri_yearbook_ch7`); `client_existing` is excluded per AGENTS.md rule #6. New focused test count: 56 tests across `test_score_nuclear.py` (11), `test_score_nuclear_components.py` (10), `test_score_nuclear_flags.py` (11), `test_score_nuclear_insufficient_flags.py` (9), `test_score_nuclear_remediation.py` (3), `test_score_stage9_nuclear.py` (8), `test_score_stage9_nuclear_batch.py` (2), plus updated `test_score_dispatch.py` + `test_score_dispatch_per_category.py` + `test_score_stage9_attribution.py`. Full suite: **1495 passing** (was 1439 before; +56). Ruff clean on all new files; `git diff --check` clean. **All 8 categories from requirement §4 now have a deterministic scorer wired into the Stage 9 dispatcher.**

## Phase C approach (data acquisition)

Phase C builds one Stage 2 ingest adapter per ✅ vetted_ok source. The pattern is set by V-Dem (the first and biggest) and reused by all the others. **One source lands → self-reviewed → tested → user sign-off → next source.** This avoids stacking unreviewed code (Rule #14) and lets the user steer the indicator catalog before we get too far.

### Phase C conventions (locked here, not per source)

These are the cross-source rules every Stage 2 adapter must follow. They live here, not in per-source files, so the rules are auditable in one place.

1. **Indicator catalog per source.** Every adapter reads from a narrow list of indicator columns defined in `src/leaders_db/ingest/catalogs/<source>.csv` (one CSV per source, sibling to the adapter module — not under `data/metadata/`). The catalog is the single source of truth for which raw columns map to which `variable_name` in `source_observations`. Catalogs are committed alongside the adapter code: the path is `src/...` because the catalog is part of the source code — it defines the adapter's input contract and the import path is stable. Each catalog also stores `raw_scale`, `normalized_scale_target`, `higher_is_better`, `unit`, and `description` per indicator so the score modules in Stage 9-10 do not have to re-derive them. The V-Dem catalog (the first one) is at `src/leaders_db/ingest/catalogs/vdem.csv`.

2. **No raw edits.** Adapters read from `data/raw/<source>/`, never write. They write to `data/processed/<source>/` (parquet) and to the `source_observations` SQLite table (via the ORM). The raw folder stays bit-identical to the downloaded bundle (with `metadata.json`).

3. **Idempotent re-runs.** Re-running an adapter with the same raw files produces the same `source_observations` rows. Adapters delete and re-insert rows for `(source_id, year)` scope, not append.

4. **One CLI command per source.** `leaders-db ingest-source --source <source>` is the user-facing surface. Each adapter registers itself in a single dispatch table in `src/leaders_db/ingest/__init__.py` (avoiding the `if/elif` chain smell). The CLI subcommand is auto-derived from the source list.

5. **Pytest coverage that defines "done".** A new test file `tests/test_ingest_<source>.py` covers: (a) the catalog loads and resolves the right columns, (b) the read function returns the expected row count for a known year, (c) the write function produces the expected parquet + SQLite row count, (d) re-running is idempotent. Tests use a small fixture (5–10 rows, 2–3 indicators) committed under `tests/fixtures/<source>/` — not the full file.

6. **Attribution text in the public output.** Per Rule #15, every adapter's `_attribution()` helper returns the per-source attribution text from `docs/sources/attributions.md`. The end-of-run CLI output prints it; the parquet metadata includes it; future Stage 15 reports include it.

7. **No invented data.** Adapters never fill in missing values, never interpolate, never extrapolate. Missing values stay `NULL` in SQLite and `NaN` in parquet. Older years degrade gracefully (more NULLs, lower confidence downstream) per requirement §13.

### Phase C execution order

Per [`docs/sources/vetting/report.md`](sources/vetting/report.md) §8, the build order is:

1. **vdem** (complete — first adapter, biggest file, set the pattern)
2. `world_bank_wdi`, `world_bank_wgi`, `ucdp`, `sipri_milex`, `sipri_yearbook_ch7`, `pts` (complete as of C.7)
3. `undp_hdi` (complete as of C.8), `who_gho_api` (complete as of C.9)
4. `archigos`, `reign`, `cirights`, `transparency_cpi`, `fas`, `bti`, `rsf_press_freedom` (Phase C.10 — caveat/user-managed second-batch landed; raw + metadata on disk, indicator catalogs authored, orchestrators shipped, central dispatch wired)
5. `wikidata_heads_of_state_government`, `wikipedia_search_extract` (Phase C.10 — always-on helpers; thin wrappers over the public API/endpoint; central dispatch wired)
6. **Complete**: `pwt` (Phase B Increment B + second-pass reviewer follow-up) — shared `SourceAdapter` Protocol + per-source package layout implemented; `STAGE2_ADAPTERS["pwt"]` wired to `ingest_pwt`; honors `years=` / `country_filter=` / request-scoped `raw_root` / `processed_root` / `database_url` end-to-end.
7. **Next**: `polity_v` once source hygiene is complete, then `leader_survival` once raw data is staged
8. Optional user-managed: `freedom_house`, `imf_weo` (no code until data is placed locally)
9. Blocked: `cow_mid`, `cia_world_leaders`, `nti` (no code)
10. Deferred: (none)

### Phase C exit criteria

- [x] V-Dem Stage 2 ingest implemented, tested, self-reviewed, end-to-end smoke for 2023 green.
- [x] At least the second-priority batch (WDI/WGI/UCDP) implemented.
- [x] `pytest -q` green through the reviewed C.8 baseline (346 tests).
- [x] **`STAGE2_ADAPTERS` dispatch table is wired for 18 sources as of C.10** (was 9 after C.9: added `archigos`, `reign`, `cirights`, `transparency_cpi`, `fas`, `bti`, `rsf_press_freedom`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`).
- [x] `pytest -q` green through the reviewed C.10 integration baseline (819 tests as of 2026-06-19).
- [ ] `data/processed/<source>/` populated for every implemented source.
- [ ] `source_observations` rows present for the implemented sources × 2023.
- [ ] No raw files modified, no `TODO(debug)`, no scratch scripts in the project root (Rule #13).
- [ ] No unreviewed code lands (Rule #14).
- [ ] Workplan Done History updated as each source lands.
