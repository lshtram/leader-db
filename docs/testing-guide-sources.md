# Testing Guide — Unified Source Interface

This guide covers the `leaders_db.sources` interface slice: the clean source
package boundary, registry seam, minimal runner dispatch, query protocol, and
legacy-access separation. The PWT 10.01 adapter under
`src/leaders_db/sources/adapters/pwt/` is the first source rebuilt under this
interface, the Maddison Project Database 2023 adapter under
`src/leaders_db/sources/adapters/maddison_project/` is the second, and the
World Bank WDI adapter under
`src/leaders_db/sources/adapters/world_bank_wdi/` is the third (API/cache-
backed source). See `docs/architecture/sources.md` §7.1 and `docs/workplan.md`
for the migration history.

## Automated checks

Run the focused source-interface suite:

```bash
pytest -q tests/sources
```

Verifies:

- importing `leaders_db.sources` (and the new
  `leaders_db.sources.adapters.pwt` submodule) does not import legacy
  `leaders_db.ingest`;
- the explicit `leaders_db.sources.legacy` bridge imports legacy lazily;
- legacy `leaders_db.ingest.STAGE2_ADAPTERS` remains accessible;
- `InMemorySourceRegistry` lists, retrieves, and rejects duplicate source slugs;
- `SourceIngestRunner.run(request)` dispatches through the new registry in the
  fixed `check_ready -> read_raw -> transform` order;
- runner dispatch does not call legacy `STAGE2_ADAPTERS`;
- source request, observation, provenance, manifest, warning, and query contracts
  expose the documented fields;
- the query protocol can be implemented by an in-memory fake without rerunning
  ingestion or reading raw files;
- the PWT adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry`;
- the PWT adapter runs end-to-end through the new runner against a fixture
  `raw_root` and produces `NormalizedObservation` records;
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the legacy
  `pwt` slot is monkeypatched to a tracker;
- `years=` / `countries=` filters are honored; `years=(2023,)` (out of
  coverage) emits zero observations plus a `year_absent` warning; `leaders=`
  emits an `unsupported_filter` warning;
- a mismatched `source_version=` (e.g. `"9.99"` against the canonical
  PWT 10.01 bundle) fails readiness with a structured
  `unsupported_version` error per
  `docs/requirements/sources.md` §3 SRC-REQ-009, and the
  `SourceIngestRunner` raises `RuntimeError` before invoking
  `read_raw` / `transform` so the legacy bundle metadata
  cannot be silently overwritten;
- the readiness-failure tests for missing `metadata.json`,
  missing `pwt1001.xlsx`, `checksum_sha256` mismatch, missing
  metadata `source_version`, and mismatched metadata `source_version`
  each prove the runner short-circuits before `read_raw` / `transform`
  (call order verified via the `_SpyPWTAdapter` wrapper);
- canonical metadata `source_version="10.01"` propagates consistently to
  `RawAsset.version` and every emitted `NormalizedObservation.source_version`.

The Archigos v4.1 clean migration adds the source-specific leader-spell
contract on top of the shared source interface:

- the Archigos adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes source_id `archigos`, default version
  `"v4.1 (Stata 14)"`, attribution_key `archigos`, dataset type,
  `requires_network=False`, coverage hint 1840-2015, and the
  `leader_identity_spell` observation family;
- `SourceIngestRunner.run(request)` drives Archigos end-to-end through the new
  registry against `tests/fixtures/archigos/sample.dta` staged under a temporary
  `raw_root` and produces one observation per leader-spell identity field;
- `years=None` reads all available spell start years in the staged file,
  multi-year requests emit every requested in-coverage start year, and
  `years=(2023,)` emits zero rows plus a `year_absent` warning because Archigos
  ends in 2015;
- `countries=` filters apply to source-native `idacr` / `ccode` tokens only;
  `leaders=` warns and is ignored;
- readiness failures cover missing `metadata.json`, missing `.dta`, malformed or
  wrong `local_files`, unsupported request/source metadata versions, checksum
  mismatch, and correct checksum;
- emitted observations preserve `obsid`, `idacr`, `ccode`, raw column, raw value,
  legacy normalized value, `source_row_reference`, raw locator path, and
  normative Archigos attribution text without inventing ISO3 or `leader_id`;
- importing `leaders_db.sources.adapters.archigos` does not import legacy
  `leaders_db.ingest`, and the runner does not consult `STAGE2_ADAPTERS`.

Focused Archigos verification:

```bash
pytest -q tests/sources/test_archigos_adapter.py tests/sources/test_import_boundary.py tests/test_ingest_archigos.py
ruff check src/leaders_db/sources/adapters/archigos/ tests/sources/test_archigos_adapter.py tests/sources/test_import_boundary.py
```

The REIGN 2021-8 clean migration adds the source-specific leader-month contract
on top of the shared source interface:

- the REIGN adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes source_id `reign`, default version
  `"2021-8 (August 2021 release, final)"`, attribution_key `reign`, dataset
  type, `requires_network=False`, coverage hint 1950-2021, and the
  `leader_identity_month` observation family;
- `SourceIngestRunner.run(request)` drives REIGN end-to-end through the new
  registry against `tests/fixtures/reign/sample.csv` staged under a temporary
  `raw_root` and produces one observation per leader-month identity/governance
  field;
- `years=None` reads all available years in the staged file, multi-year requests
  emit every requested in-coverage year, and `years=(2023,)` emits zero rows plus
  a `year_absent` warning because REIGN ends in 2021-08;
- `countries=` filters apply to source-native `country` / `ccode` tokens only;
  `leaders=` warns and is ignored;
- readiness failures cover missing `metadata.json`, missing CSV, malformed or
  wrong `local_files`, unsupported request/source metadata versions, checksum
  mismatch, and correct checksum;
- emitted observations preserve source-native country, `ccode`, year, month,
  leader name, raw column, raw value, legacy normalized value,
  `source_row_reference`, raw locator path, and normative REIGN attribution text
  without inventing ISO3 or `leader_id`;
- importing `leaders_db.sources.adapters.reign` does not import legacy
  `leaders_db.ingest`, and the runner does not consult `STAGE2_ADAPTERS`.

Focused REIGN verification:

```bash
pytest -q tests/sources/test_reign_adapter.py tests/sources/test_import_boundary.py tests/test_ingest_reign.py
ruff check src/leaders_db/sources/adapters/reign/ tests/sources/test_reign_adapter.py tests/sources/test_import_boundary.py
```

The SIPRI Military Expenditure Database clean migration adds the source-specific
country-year military-expenditure contract on top of the shared source
interface:

- the SIPRI Milex adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes source_id `sipri_milex`, default version
  `"SIPRI milex 1949-2025 release"`, attribution_key `sipri_milex`, dataset
  type, `requires_network=False`, coverage hint 1949-2025, and the
  `international_peace_country_year` observation family;
- `SourceIngestRunner.run(request)` drives SIPRI Milex end-to-end through the
  new registry against `tests/fixtures/sipri_milex/sample.xlsx` staged under a
  temporary `raw_root` and produces one observation per non-missing country,
  year, and catalog indicator;
- `years=None` reads all available fixture years, multi-year requests emit every
  requested in-coverage year, and out-of-coverage years emit zero rows plus a
  `year_absent` warning;
- `countries=` filters apply to source-native SIPRI display country names only;
  `leaders=` warns and is ignored;
- readiness failures cover missing `metadata.json`, missing xlsx, malformed or
  wrong `local_files`, unsupported request/source metadata versions, checksum
  mismatch, and correct checksum;
- emitted observations preserve source-native country, raw workbook sheet, raw
  value, normalized float, source row reference, region-filter audit metadata,
  raw locator path, and normative SIPRI attribution text without inventing ISO3
  or leader identifiers;
- importing `leaders_db.sources.adapters.sipri_milex` does not import legacy
  `leaders_db.ingest`, and the runner does not consult `STAGE2_ADAPTERS`.

Focused SIPRI Milex verification:

```bash
pytest -q tests/sources/test_sipri_milex_adapter.py tests/sources/test_import_boundary.py tests/test_ingest_sipri_milex.py
ruff check src/leaders_db/sources/adapters/sipri_milex/ tests/sources/test_sipri_milex_adapter.py tests/sources/test_import_boundary.py
```

The SIPRI Yearbook Ch.7 clean migration adds the PDF/document-source contract on
top of the shared source interface:

- the adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes source_id `sipri_yearbook_ch7`, default
  version `"YB2024 (data: January 2024)"`, attribution_key
  `sipri_yearbook_ch7`, document type, `requires_network=False`, 2024 snapshot
  coverage, and the `nuclear_country_year` observation family;
- `SourceIngestRunner.run(request)` drives SIPRI Yearbook Ch.7 end-to-end
  through the new registry against `tests/fixtures/sipri_yearbook_ch7/sample.pdf`
  staged under a temporary `raw_root` with canonical runtime-local metadata;
- `years=None` reads the snapshot year, multi-year requests emit the
  in-snapshot year and warn for out-of-snapshot years, and out-of-snapshot-only
  requests emit zero rows plus a `year_absent` warning;
- `countries=` filters apply to source-native SIPRI display country names only;
  `leaders=` warns and is ignored;
- readiness failures cover missing runtime-local `metadata.json`, missing PDF,
  malformed or wrong `local_files`, unsupported request/source metadata
  versions, checksum mismatch, and correct checksum;
- emitted observations preserve source-native country, raw PDF path/page/column,
  raw cell text, normalized integer or `None`, source row reference,
  `pdf_pages_total`, `snapshot_year`, and normative SIPRI Yearbook attribution
  text without inventing ISO3 or leader identifiers;
- importing `leaders_db.sources.adapters.sipri_yearbook_ch7` does not import
  legacy `leaders_db.ingest`, and the runner does not consult `STAGE2_ADAPTERS`.

Focused SIPRI Yearbook Ch.7 verification:

```bash
pytest -q tests/sources/test_sipri_yearbook_ch7_adapter.py tests/sources/test_import_boundary.py tests/test_ingest_sipri_yearbook_ch7.py
ruff check src/leaders_db/sources/adapters/sipri_yearbook_ch7/ tests/sources/test_sipri_yearbook_ch7_adapter.py tests/sources/test_import_boundary.py
```

The Maddison Project Database 2023 slice adds the source-specific
coverage semantics on top of the shared contract:

- the Maddison adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes the canonical Maddison Project
  2023 static metadata (source_id `maddison_project`, default version
  `2023`, attribution_key `maddison_project`, dataset type, 1-2022
  coverage hint, `economic_country_year` observation family, canonical
  Maddison Project homepage URL);
- `SourceIngestRunner.run(request)` drives Maddison end-to-end through
  the new registry against a fixture `raw_root` and produces
  `NormalizedObservation` records (21 fixture observations
  round-tripped);
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the
  legacy `maddison_project` slot is monkeypatched to a tracker;
- `years=(2023,)` triggers the documented 1-year-gap proxy mapping
  to 2022 data: every emitted observation carries the `proxy_year`
  quality flag plus `requested_year=2023` / `proxy_source_year=2022`
  in its `extension` payload, and the result envelope surfaces a
  structured `maddison_project_proxy_year` warning naming the
  mapping;
- `years=(2024,)` (out of coverage) emits zero observations plus a
  structured `YEAR_ABSENT` warning -- no multi-year stale-proxy fill
  (SRC-COV-002 / SRC-COV-003);
- `years=` / `countries=` filters are honored; `leaders=` emits an
  `unsupported_filter` warning;
- the readiness-failure tests for missing `metadata.json`, missing
  `mpd2023.xlsx`, `checksum_sha256` mismatch, missing metadata
  `source_version`, and mismatched metadata `source_version` each
  prove the runner short-circuits before `read_raw` / `transform`;
- canonical metadata `source_version="2023"` propagates consistently
  to `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`.

Run focused lint for this slice:

```bash
ruff check src/leaders_db/sources tests/sources docs/requirements/sources.md docs/architecture/sources.md
```

Verifies formatting/import/static-analysis hygiene for the new package, source
tests, and source-interface docs touched by this slice.

The World Bank WDI slice (third clean-source migration, API/cache-backed)
adds the source-specific cache-policy semantics on top of the shared
contract:

- the WDI adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes the canonical WDI static metadata
  (source_id `world_bank_wdi`, default version `"World Bank API v2;
  cached indicator responses"`, attribution_key `"world_bank_wdi"`, api
  type, 1960-present coverage hint, both `economic_country_year` and
  `social_country_year` observation families, WDI v2 API homepage URL,
  requires_network=True);
- `SourceIngestRunner.run(request)` drives WDI end-to-end through the
  new registry against a fixture `raw_root` and produces
  `NormalizedObservation` records (125 fixture observations round-tripped
  for the unfiltered run; 61 for `years=(2023,)`; 25 for
  `countries=('USA',)`; 12 for `years=(2023,) + countries=('USA',)`);
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the
  legacy `world_bank_wdi` slot is monkeypatched to a tracker;
- `cache_policy="offline_only"` / `"prefer_cache"` with explicit `years=`
  and missing / incomplete cache fails readiness with a structured
  `network_cache_unavailable` / `missing_raw` error BEFORE `read_raw` /
  `transform` are called; the new runner is offline / cache-first by
  default and never silently hits the network;
- `cache_policy="refresh"` / `"no_cache"` is NOT supported by the
  unified WDI adapter in this slice: it fails readiness with a
  structured `unsupported_cache_policy` error BEFORE
  `read_raw` / `transform` are called. The unified adapter is
  offline / cache-only; `WDIAdapter.read_raw` never invokes the
  network. Use `cache_policy="offline_only"` / `"prefer_cache"`
  and stage the per-(year, indicator) JSON cache to refresh data.
- `years=None` skips the cache-directory gate (the readiness
  envelope accepts all-available-years semantics) but the
  `unsupported_cache_policy` gate still fires for
  `cache_policy="refresh"` / `"no_cache"` so callers cannot
  bypass it with `years=None`;
- `years=` outside the 1960+ coverage envelope emits zero observations
  plus a structured `YEAR_ABSENT` warning -- no stale-proxy fill
  (SRC-COV-002 / SRC-COV-003);
- `years=` / `countries=` filters are honored; `leaders=` emits an
  `unsupported_filter` warning;
- the readiness-failure tests for missing `metadata.json`,
  missing metadata `source_version`, mismatched metadata
  `source_version`, and unsupported request `source_version` each
  prove the runner short-circuits before `read_raw` / `transform`;
- the readiness-failure tests for the three `checksum_sha256`
  shapes (missing field, `null` without / with a non-actionable
  `checksum_note`, invalid hex / dict shape) each prove the
  runner short-circuits before `read_raw` / `transform` with a
  structured `missing_metadata` error;
- the readiness-failure tests for `cache_policy="refresh"` /
  `"no_cache"` (with and without explicit `years=`) each prove
  the runner short-circuits with a structured
  `unsupported_cache_policy` error;
- the canonical metadata `source_version="World Bank API v2; cached
  indicator responses"` propagates consistently to
  `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`;
- the per-observation `RawLocator` carries the cache file path +
  `api_endpoint` template + `json_pointer` so downstream audit code
  can resolve the canonical WDI v2 URL for each (year, indicator,
  country) row; the pointer is `"/1/<numeric_index>"` and the
  `test_wdi_observation_json_pointer_resolves` test opens the
  referenced cache JSON, resolves the pointer, and asserts it
  points at the matching record;
- the per-observation `extension` payload carries the raw WDI
  indicator code (e.g. `NY.GDP.MKTP.CD`) as `wdi_raw_indicator_code`,
  plus the canonical attribution text (Rule #15);
- the cache-policy remediation tests prove the unified WDI adapter
  is provably no-network under supported cache policies
  (`offline_only` / `prefer_cache`) for both `years=None`
  (all-available-years) and explicit-`years=` requests:
  - `test_wdi_offline_only_no_year_filter_partial_cache_does_not_hit_network`
    and
    `test_wdi_prefer_cache_no_year_filter_partial_cache_does_not_hit_network`
    drive `SourceIngestRunner` against a staged incomplete cache
    (only SP.POP.TOTL present), with HTTP sentinels installed on
    `leaders_db.ingest.wdi_http.fetch_wdi_payload` AND
    `requests.get`. Both sentinels remain uninvoked; the runner
    emits observations ONLY for the staged indicator;
  - `test_wdi_offline_only_no_year_filter_empty_cache_does_not_hit_network`
    drives the runner against an empty cache directory with
    `cache_policy="offline_only"` + `years=None`; no HTTP is
    invoked and the runner emits zero observations
    (all-available-years semantics);
  - `test_wdi_corrupt_cached_json_blocks_readiness_for_discovered_files`
    and `test_wdi_corrupt_cached_json_blocks_readiness_for_explicit_years`
    drive the runner with a staged corrupt (invalid JSON) cache
    file; readiness fails with a structured `missing_raw` error
    naming the offending file BEFORE `read_raw` / `transform` are
    called. No HTTP sentinel is invoked;
  - `test_wdi_explicit_year_partial_cache_blocks_readiness_and_skips_runner`
    drives the runner with `years=(2023,)` + staged incomplete
    cache; readiness fails with `missing_raw` and the runner
    short-circuits. No HTTP sentinel is invoked;
  - `test_wdi_unsupported_cache_policy_no_year_filter_does_not_hit_network`
    drives the runner with `cache_policy="refresh"` +
    `years=None`; readiness fails with `unsupported_cache_policy`
    and the runner short-circuits. No HTTP sentinel is invoked.

  The cache-policy remediation is the second reviewer pass on the
  same no-network contract (the first pass only covered explicit
  years + missing/incomplete cache; the second pass extends the
  contract to `years=None` partial-cache / corrupt-cache /
  empty-cache scenarios and adds HTTP-sentinel production-path
  tests).

The semantic concept-catalog slice (`leaders_db.sources.concepts`) should add
focused tests under `tests/sources` for the query-time normalization layer:

- `list_concepts()` exposes stable keys such as `gdp_per_capita`, `population`,
  and `gdp_total` without importing legacy `leaders_db.ingest`;
- `resolve_concept(concept_key)` returns source-specific direct mappings, and
  `resolve_concept(concept_key, source_id=...)` narrows to one source;
- WDI and Maddison fixture observations extract direct `gdp_per_capita` /
  `population` concept rows while preserving original indicator codes;
- PWT fixture observations derive `gdp_per_capita` from
  `pwt_real_gdp_output_side / pwt_population`;
- derived concept rows carry input observation ids/provenance and an explicit
  derivation marker / quality flag;
- unknown concept keys and unsupported concept/source pairs raise actionable
  errors;
- concept extraction consumes only provided `NormalizedObservation` records (or
  an in-memory `EvidenceRepository` fake result) and does not read raw files,
  call adapters, rerun ingestion, write manifests, or consult the client matrix
  as evidence;
- the PWT derivation scope key includes `year` so the same country with valid
  2018 AND 2019 inputs emits two distinct derived rows (one per country-year);
- the PWT derivation requires both inputs to share the same non-empty
  `source_version` -- missing or mismatched `source_version` produces zero
  derived rows and surfaces a structured `concept_missing_source_version`
  warning on the diagnostic helper's `warnings` tuple;
- the diagnostic helper `extract_concept_result` surfaces every per-scope
  derived-mapping drop reason with a stable per-failure-mode code
  (`concept_missing_numerator`, `concept_missing_denominator`,
  `concept_ambiguous_pair`, `concept_non_numeric_numerator`,
  `concept_non_numeric_denominator`, `concept_zero_denominator`,
  `concept_missing_source_version`, `concept_pair_year_mismatch`) AND every
  per-row direct-mapping `missing_value` warning. The convenience
  `extract_concept` wrapper returns only the observations tuple so the minimal
  public API stays flat.

The in-memory evidence-repository slice (`InMemoryEvidenceRepository`,
in `src/leaders_db/sources/query.py`, re-exported from the
`leaders_db.sources` package root) should add focused tests under
`tests/sources/test_query_repository.py` for the read-only query seam:

- the in-memory repository satisfies the runtime-checkable
  `EvidenceRepository` `Protocol` (`isinstance(repository,
  EvidenceRepository)` is True) and is importable from the
  `leaders_db.sources` package root;
- the constructor copies `observations` / `manifests` / `attributions`
  into internal tuples so caller-owned lists are not mutated and the
  same sequences can be reused after construction;
- every filter dimension (`source_ids`, `observation_families`,
  `indicator_codes`, `years`, `countries`, `leaders`) is honored;
  `None` returns the unfiltered stream; an empty tuple `()` returns
  no observations for that dimension; the input observation order is
  preserved in the result tuple;
- the `leaders` filter matches against either `leader_id` or
  `leader_name`, so callers can query by either dimension until
  leader IDs are stable;
- `get_manifest(source_id, run_id="...")` performs an exact
  `(slug, run_id)` lookup and raises `KeyError` for unknown run ids;
- `get_manifest(source_id)` returns the only manifest when exactly
  one is stored, and raises `KeyError` naming the available run ids
  when multiple manifests exist for the same source;
- `get_manifest` raises `KeyError` with an actionable message when
  no manifest is stored for the requested source;
- `get_attributions` returns attributions in the requested
  `source_ids` order and silently skips sources without a stored
  attribution;
- the in-memory repository never imports `leaders_db.ingest`,
  never instantiates `SourceIngestRunner`, never calls source
  adapters, and never opens raw files: the tests monkeypatch
  `SourceIngestRunner.__init__` and `Path.open` /
  `Path.read_text` / `Path.read_bytes` as sentinels and assert
  they are never invoked; the canonical import-boundary submodule
  list in `tests/sources/test_import_boundary.py` covers
  `leaders_db.sources.query`;
- the integration with the concept catalog: synthetic WDI /
  Maddison / PWT observations are loaded into the repository,
  queried via `EvidenceQuery`, and the filtered subset is fed into
  `extract_concept` / `extract_concept_result` to verify that the
  repository wires end-to-end with the concept layer without
  re-running ingestion.

The existing `tests/sources/test_query.py` (Phase B `Protocol` /
`EvidenceQuery` contract tests) keeps passing unchanged: the in-memory
repository is the first concrete implementation of the existing
`EvidenceRepository` Protocol and does not change the contract.

Optional legacy compatibility smoke:

```bash
pytest -q tests/ingest
```

Verifies the existing legacy ingestion tests remain green after source-interface
changes. The PWT-specific legacy suite
(`tests/ingest/sources/pwt/`) is the regression guard for the legacy
`STAGE2_ADAPTERS["pwt"]` path and must keep passing unchanged. The
WDI legacy suite (`tests/test_ingest_wdi.py`) is the regression guard
for the legacy `STAGE2_ADAPTERS["world_bank_wdi"]` path; the new
`tests/sources/test_world_bank_wdi_adapter.py` slice asserts that
the legacy `STAGE2_ADAPTERS["world_bank_wdi"]` slot is never invoked
by the new runner (`test_wdi_runner_does_not_consult_legacy_stage2_adapters`)
and that the legacy constant `WDI_ATTRIBUTION` is byte-identical to
the new `WORLD_BANK_WDI_ATTRIBUTION_TEXT`
(`test_wdi_attribution_text_matches_legacy_constant`).

The World Bank WGI slice (fourth clean-source migration, local-file /
no-network) adds the source-specific legacy-shape metadata contract
on top of the shared contract:

- the WGI adapter descriptor is registerable / listable through
  the `InMemorySourceRegistry` and exposes the canonical WGI
  static metadata (source_id `world_bank_wgi`, default version
  `"Worldwide Governance Indicators 2023 Update (data through
  2022)"`, attribution_key `"world_bank_wgi"`, dataset type,
  1996-2022 coverage hint, `governance_country_year`
  observation family, WGI homepage URL
  `https://info.worldbank.org/governance/wgi/`,
  `requires_network=False`);
- `SourceIngestRunner.run(request)` drives WGI end-to-end through
  the new registry against a fixture `raw_root` and produces
  `NormalizedObservation` records (59 fixture observations
  round-tripped -- 5 countries x 2 years x 6 indicators minus
  one `#N/A` cell at MEX 2021 `wgi_political_stability`);
- the runner does not consult legacy `STAGE2_ADAPTERS` even when
  the legacy `world_bank_wgi` slot is monkeypatched to a
  tracker;
- `years=(2023,)` and `years=(1995,)` (out of coverage) emit
  zero observations plus a structured `YEAR_ABSENT` warning
  -- no stale-proxy fill (SRC-COV-002 / SRC-COV-003);
- `years=` and `countries=` filters are honored; `leaders=`
  emits a structured `unsupported_filter` warning;
- the readiness-failure tests for missing `metadata.json`,
  missing `wgidataset.xlsx`, `sha256` mismatch (legacy key),
  missing metadata `version` (legacy key), mismatched
  metadata `version`, and unsupported request
  `source_version` each prove the runner short-circuits
  before `read_raw` / `transform`;
- the readiness gate accepts BOTH the canonical primary
  metadata shape (PWT / Maddison / WDI convention:
  `source_version` / `checksum_sha256` / `local_files` /
  `license_note` / `coverage`) AND the staged WGI legacy
  shape (`version` / `sha256` / `local_file` / `license` /
  `coverage_start_year` + `coverage_end_year`);
  `test_wgi_primary_shape_bundle_is_accepted_by_readiness`
  drives the runner against a staged primary-shape bundle
  and proves the runner short-circuits are identical to the
  legacy-shape case;
- the canonical metadata `source_version="Worldwide Governance
  Indicators 2023 Update (data through 2022)"` propagates
  consistently to `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`;
- per-observation `RawLocator` carries the staged xlsx path
  + the canonical per-indicator sheet name
  (`VoiceandAccountability` /
  `Political StabilityNoViolence` /
  `GovernmentEffectiveness` / `RegulatoryQuality` /
  `RuleofLaw` / `ControlofCorruption`); `row_number` is
  intentionally `None` because the legacy wide frame loses
  the xlsx row index through the long-to-wide pivot -- the
  unified transform never fabricates locators;
- the per-observation `extension` payload carries the
  canonical WGI attribution text (Rule #15), the
  `source_row_reference="world_bank_wgi:<iso3>"` pattern
  (matching the legacy Stage 2 DB writer), the
  `wgi_sheet_name` (canonical xlsx sheet name), and the
  `wgi_indicator_category` (catalog `rating_category`,
  `effectiveness` for 5 indicators + `integrity` for
  `wgi_control_of_corruption`);
- the legacy `WGI_ATTRIBUTION` constant in
  `src/leaders_db/ingest/wgi_io.py` is byte-identical to the
  new `WORLD_BANK_WGI_ATTRIBUTION_TEXT`
  (`test_wgi_attribution_text_matches_attributions_doc` asserts
  the byte-identity AND that the unified text is a substring
  of `docs/sources/attributions.md`);
- the WGI unified path is local-file only
  (`requires_network=False`, no HTTP layer in the new
  package). The runner NEVER invokes the network. The
  readiness gate validates the staged `wgidataset.xlsx` and
  the metadata checksum / version / license /
  coverage fields BEFORE `read_raw` / `transform` are
  called.

The V-Dem slice (fifth clean-source migration, large
local CSV) adds the source-specific checksum-scope and
V-Dem-specific extension contract on top of the shared
contract:

- the V-Dem adapter descriptor is registerable / listable
  through the `InMemorySourceRegistry` and exposes the
  canonical V-Dem static metadata (source_id `vdem`,
  default version `"v16"`, attribution_key `"vdem"`,
  dataset type, 1789-2025 coverage hint, five observation
  families (`political_country_year`,
  `governance_country_year`, `corruption_country_year`,
  `repression_country_year`, `social_country_year`),
  V-Dem DOI homepage URL
  `https://doi.org/10.23696/vdemds26`,
  `requires_network=False`);
- `SourceIngestRunner.run(request)` drives V-Dem
  end-to-end through the new registry against a fixture
  `raw_root` and produces `NormalizedObservation` records
  (220 fixture observations round-tripped -- 5 countries
  x 2 years x 22 indicators);
- the runner does not consult legacy `STAGE2_ADAPTERS`
  even when the legacy `vdem` slot is monkeypatched to a
  tracker;
- `years=(1788,)` and `years=(2026,)` (out of coverage)
  emit zero observations plus a structured `YEAR_ABSENT`
  warning -- no stale-proxy fill (SRC-COV-002 /
  SRC-COV-003);
- `years=` and `countries=` filters are honored;
  `leaders=` emits a structured `unsupported_filter`
  warning;
- the readiness-failure tests for missing `metadata.json`,
  missing `V-Dem-CY-Full+Others-v16.csv`, missing
  `local_files` reference, malformed `checksum_sha256`
  (not a 64-char hex string), mismatched zip SHA-256
  (V-Dem-specific `vdem_checksum_mismatch` code), missing
  metadata `source_version`, mismatched metadata
  `source_version`, and unsupported request
  `source_version` each prove the runner short-circuits
  before `read_raw` / `transform`;
- the metadata `checksum_sha256` covers the staged zip,
  NOT the 388MB CSV: the gate validates the metadata
  SHAPE (must be a 64-character hex SHA-256 string) AND,
  if the zip is staged, recomputes the zip's SHA-256 and
  compares against the metadata field. The CSV is NEVER
  hashed by the unified adapter (audit chain preserved via
  the legacy parquet metadata + the canonical attribution
  text);
- the canonical metadata `source_version="v16"`
  propagates consistently to `RawAsset.version` and every
  emitted `NormalizedObservation.source_version`;
- per-observation `RawLocator` carries the staged CSV
  path + the raw V-Dem column name (e.g. `v2x_polyarchy`);
  `row_number` is intentionally `None` because the legacy
  narrow frame loses the CSV row index through the
  long-to-wide pivot -- the unified transform never
  fabricates locators;
- the per-observation `extension` payload carries the
  canonical V-Dem attribution text (Rule #15), the
  `source_row_reference="vdem:<country_text_id>"` pattern
  (matching the legacy Stage 2 DB writer), the
  `vdem_raw_column` (catalog `raw_column`),
  `vdem_country_id` (V-Dem integer id for Stage 3
  country match), `vdem_country_text_id` (V-Dem COW
  code), `vdem_rating_category` (catalog
  `rating_category`), `raw_value` (audit-trail string
  preserving V-Dem missing sentinels like `"-999.0"`),
  and the `raw_scale` / `higher_is_better` /
  `normalized_scale_target` direction hints;
- the legacy `VDEM_ATTRIBUTION` constant in
  `src/leaders_db/ingest/vdem_io.py` is byte-identical to
  the new `VDEM_ATTRIBUTION_TEXT`
  (`test_vdem_attribution_text_matches_attributions_doc`
  asserts the byte-identity AND that the unified text is
  a substring of `docs/sources/attributions.md`);
- the V-Dem unified path is local-file only
  (`requires_network=False`, no HTTP layer in the new
  package). The runner NEVER invokes the network. The
  readiness gate validates the staged CSV and the
  metadata checksum / version / license / coverage
  fields BEFORE `read_raw` / `transform` are called.
- **With V-Dem landed, the unified source interface
    covers the four structured source families needed for
    a complete 1900-2026 inquiry** (PWT + Maddison =
    historical economy; WDI = current economy; WGI =
    governance; V-Dem = political regime / repression /
    corruption / social well-being). The next major
    milestone is a vertical-slice investigation that runs
    from these source adapters through
    `InMemoryEvidenceRepository`, semantic concepts /
    evidence bundles, scoring or analysis logic, and a
    documented answer with provenance.

The UCDP slice (sixth clean-source migration, event-level
/ local-file) adds the source-specific event-level
aggregation + aggregate locator convention contract on
top of the shared contract:

- the UCDP adapter descriptor is registerable / listable
  through the `InMemorySourceRegistry` and exposes the
  canonical UCDP static metadata (source_id `ucdp`,
  default version `"GED 23.1"`, attribution_key `"ucdp"`,
  dataset type, 1989-2022 coverage hint, two observation
  families (`international_peace_country_year`,
  `domestic_violence_country_year`), UCDP downloads
  homepage URL (`https://ucdp.uu.se/downloads/`),
  `requires_network=False`);
- `SourceIngestRunner.run(request)` drives UCDP
  end-to-end through the new registry against a fixture
  `raw_root` and produces `NormalizedObservation` records
  (60 fixture observations round-tripped -- 5 countries x
  2 years x 6 indicators after event-level aggregation of
  the 22-event fixture);
- the runner does not consult legacy `STAGE2_ADAPTERS`
  even when the legacy `ucdp` slot is monkeypatched to a
  tracker;
- the request `countries=` filter applies as an exact
  match against the UCDP `country_id` integer (NOT ISO3) --
  `test_ucdp_country_filter_is_applied` drives the runner
  with `countries=('645',)` and verifies the 12 Iraq
  observations round-trip; `test_ucdp_iso3_country_filter_produces_zero_observations`
  drives the runner with `countries=('IRQ',)` and verifies
  zero observations (callers who want to filter by ISO3
  must use the legacy path or Stage 3 country match to
  resolve first);
- `years=(2023,)` and `years=(1988,)` (out of coverage)
  emit zero observations plus a structured `YEAR_ABSENT`
  warning -- no stale-proxy fill (SRC-COV-002 /
  SRC-COV-003);
- `years=` and `countries=` filters are honored;
  `leaders=` emits a structured `unsupported_filter`
  warning;
- the readiness-failure tests for missing `metadata.json`,
  missing `ged231-csv.zip`, missing required field
  (`source_url`), mismatched metadata `source_version`,
  and unsupported request `source_version` each prove
  the runner short-circuits before `read_raw` /
  `transform`;
- the readiness gate accepts the canonical UCDP bundle
  metadata shape (`local_files=[]` /
  `checksum_sha256=null` /
  `ingestion_status="pending"`, the staged
  `data/raw/ucdp/metadata.json` shape) ONLY when the
  canonical `ged231-csv.zip` is staged on disk alongside
  the metadata. The canonical UCDP bundle metadata
  carries `local_files=[]` and `checksum_sha256=null` --
  a deliberately minimal shape so the operator can update
  the metadata once the zip is staged. The mandatory
  readiness requirement is on raw-file presence: the gate
  returns `ready=False` with a structured `missing_raw`
  error if `ged231-csv.zip` is not staged on disk,
  regardless of the metadata's `local_files` /
  `checksum_sha256` shape. A metadata-only bundle (no
  staged zip) is intentionally NOT runner-ready -- it has
  value for readiness-only inspection (validating metadata
  shape, schema migrations, sanity-checking
  `expected_local_files` annotations) but the runner
  raises `RuntimeError` BEFORE `read_raw` / `transform`.
  `test_ucdp_empty_shape_bundle_is_not_runner_ready`
  drives the readiness gate against the canonical
  empty-shape metadata (no staged zip) and asserts the
  readiness envelope is NOT ready with a structured
  `missing_raw` error; `test_ucdp_metadata_only_without_zip_blocks_runner_short_circuit`
  drives the runner end-to-end against the same
  metadata-only bundle via a `_SpyUCDPAdapter` wrapper and
  asserts the runner short-circuits BEFORE `read_raw` /
  `transform` (the call list stays `["check_ready"]`).
  `test_ucdp_checksum_mismatch_fails_readiness` drives
  the readiness gate against a staged zip with a
  deliberately wrong checksum and asserts the readiness
  gate fires the UCDP-specific `ucdp_checksum_mismatch`
  error code;
- the canonical metadata `source_version="GED 23.1"`
  propagates consistently to `RawAsset.version` and every
  emitted `NormalizedObservation.source_version`;
- per-observation `RawLocator` carries the staged zip
  path + the catalog `variable_name` (e.g.
  `ucdp_state_based_events`); `row_number` is intentionally
  `None` because UCDP is event-level data and the legacy
  wide frame loses the event row index through the
  long-to-wide pivot -- the unified transform never
  fabricates locators. The aggregate locator convention is
  carried on the `transform_locator.rule_id` (`ucdp:<country_id>:<year>:<variable_name>`)
  and the `quality_flags` tuple
  (`ucdp_aggregated_from_events`);
- per-observation `extension` carries the canonical UCDP
  attribution text (Rule #15), the
  `source_row_reference="ucdp:<country_id>"` pattern
  (matching the legacy Stage 2 DB writer), the
  `ucdp_country_id`, `ucdp_rating_category`,
  `ucdp_raw_column`, `ucdp_filter_logic`,
  `ucdp_events_total` / `ucdp_events_filtered`, `raw_value`
  (audit-trail string), and the `raw_scale` /
  `higher_is_better` / `normalized_scale_target`
  direction hints;
- the legacy `UCDP_ATTRIBUTION` constant in
  `src/leaders_db/ingest/ucdp_io.py` is byte-identical to
  the new `UCDP_ATTRIBUTION_TEXT`
  (`test_ucdp_attribution_text_matches_attributions_doc`
  asserts byte-identity AND that the unified text is a
  substring of `docs/sources/attributions.md`);
- the UCDP unified path is local-file only
  (`requires_network=False`, no HTTP layer in the new
  package). The runner NEVER invokes the network. The
  readiness gate validates the staged `ged231-csv.zip`
  (mandatory raw-file presence -- a missing zip fires
  `missing_raw`) and the metadata checksum / version /
  license / coverage fields BEFORE `read_raw` /
  `transform` are called.
- **With UCDP landed, the unified source interface now
  covers the first event-level source family**: PWT +
  Maddison = historical economy; WDI = current economy;
  WGI = governance; V-Dem = political regime / repression
  / corruption / social well-being; UCDP = organized
  conflict / one-sided violence (event-level aggregations
  to country-year).

The Transparency International CPI slice (seventh
clean-source migration, country-year / no-network)
adds the source-specific per-year CSV + mirror vs.
publisher attribution contract on top of the shared
contract:

- the CPI adapter descriptor is registerable / listable
  through the ``InMemorySourceRegistry`` and exposes the
  canonical CPI static metadata (source_id
  ``transparency_cpi``, default version ``"CPI 2023"``,
  attribution_key ``transparency_cpi``, dataset type,
  1995-2023 coverage hint, single observation family
  ``integrity_country_year``, TI CPI 2023 homepage URL
  ``https://www.transparency.org/en/cpi/2023``,
  ``requires_network=False``);
- ``SourceIngestRunner.run(request)`` drives CPI
  end-to-end through the new registry against a fixture
  ``raw_root`` and produces ``NormalizedObservation``
  records (5 fixture observations round-tripped -- 5
  countries x 1 year x 1 indicator ``cpi_score``);
- the runner does not consult legacy ``STAGE2_ADAPTERS``
  even when the legacy ``transparency_cpi`` slot is
  monkeypatched to a tracker;
- the request ``countries=`` filter applies as an exact
  match against the CPI ``iso3`` alpha-3 code
  (``test_transparency_cpi_country_filter_is_applied``
  drives the runner with ``countries=('MEX',)`` and
  verifies the single Mexico observation
  round-trips);
- ``years=(2024,)`` (after coverage) and
  ``years=(1994,)`` (before coverage) emit zero
  observations plus a structured ``YEAR_ABSENT``
  warning -- no stale-proxy fill (SRC-COV-002 /
  SRC-COV-003);
- ``years=`` and ``countries=`` filters are honored;
  ``leaders=`` emits a structured ``unsupported_filter``
  warning;
- the readiness-failure tests for missing ``metadata.json``,
  missing ``transparency_cpi_2023.csv``, missing
  required field (``source_url``), mismatched
  metadata ``source_version``, and unsupported request
  ``source_version`` each prove the runner
  short-circuits before ``read_raw`` / ``transform``;
- the canonical CPI bundle metadata ships with
  ``checksum_sha256=null`` + ``local_files=["transparency_cpi_2023.csv"]``
  (the canonical staged bundle metadata shape). The
  gate accepts the null checksum (``checksum_sha256: null``)
  AND a 64-character hex SHA-256 matching the staged CSV
  bytes; a malformed checksum shape (e.g. non-null but
  non-64-character-hex) fails readiness with a structured
  ``missing_metadata`` error, and a mismatched SHA-256
  against a non-null ``checksum_sha256`` fails readiness
  with the module-local ``transparency_cpi_checksum_mismatch``
  error code. A present-but-null ``local_files`` (an
  explicit ``"local_files": null`` in the staged JSON)
  fails readiness with ``missing_metadata`` because the
  canonical metadata requires the field as a list. The
  mandatory readiness requirement is on raw-file
  presence: a metadata-only bundle (no staged CSV) is
  intentionally NOT runner-ready, even though
  ``checksum_sha256=null`` is the canonical metadata
  shape. The gate returns ``ready=False`` with a structured
  ``missing_raw`` error when the per-year CSV is not
  staged on disk, regardless of the metadata's
  ``local_files`` / ``checksum_sha256`` shape;
- the canonical metadata ``source_version="CPI 2023"``
  propagates consistently to ``RawAsset.version`` and
  every emitted ``NormalizedObservation.source_version``;
- per-observation ``RawLocator`` carries the staged CSV
  path + the catalog ``raw_column`` (``score``) + the
  positional row index in the wide frame (the legacy
  reader sorts by iso3 ascending for deterministic
  idempotency, so the row index is preserved
  byte-for-byte with the input CSV);
- per-observation ``extension`` carries the canonical
  CPI attribution text (Rule #15), the
  ``source_row_reference="transparency_cpi:score:<iso3>"``
  pattern (matching the legacy Stage 2 DB writer), the
  CPI ``iso3`` / ``country`` / ``region`` audit-trail
  labels, the per-row confidence fields
  ``cpi_rank`` / ``cpi_sources`` /
  ``cpi_standard_error`` / ``cpi_lower_ci`` /
  ``cpi_upper_ci``, and the direction hints
  (``higher_is_better=True`` because a higher CPI
  score = cleaner perception = better);
- the legacy ``TRANSPARENCY_CPI_ATTRIBUTION`` constant
  in ``src/leaders_db/ingest/transparency_cpi_io.py`` is
  byte-identical to the new
  ``TRANSPARENCY_CPI_ATTRIBUTION_TEXT``
  (``test_transparency_cpi_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text is a
  substring of ``docs/sources/attributions.md``);
- the CPI unified path is local-file only
  (``requires_network=False``, no HTTP layer in the new
  package). The runner NEVER invokes the network --
  ``test_transparency_cpi_runner_does_not_invoke_network``
  installs sentinels on
  ``leaders_db.ingest.transparency_cpi_http.fetch_transparency_cpi_csv``
  AND ``requests.get``, asserts neither sentinel is
  invoked while the runner executes the new CPI
  adapter lifecycle end-to-end;
- the mirror vs. publisher attribution contract is
  documented in ``docs/sources/attributions.md``
  transparency_cpi section: the report-facing
  attribution block names Transparency International
  CPI 2023 (the canonical publisher name), NOT the OCHA
  HDX mirror (which is the durable CSV provenance path
  documented separately in the bundle metadata's
  ``hdx_mirror_url`` field).
- **With CPI landed, the unified source interface now
  covers the perception-based integrity sub-signal**
  (PWT + Maddison = historical economy; WDI = current
  economy; WGI = governance; V-Dem = political regime /
  repression / corruption / social well-being; UCDP =
  organized conflict / one-sided violence; CPI =
  corruption perceptions). Together with V-Dem's
  ``vdem_corruption`` subset and WGI's
  ``world_bank_wgi_corruption`` subset (both documented
  in ``docs/architecture/sources.md`` section 7.5 as
  observation-family / catalog subsets under the parent
  adapters, not separate adapters), the integrity /
  corruption rating category is now fully covered by
  the unified source interface.

The Political Terror Scale (PTS) slice (eighth
clean-source migration, country-year / no-network /
local xlsx / NA_Status sentinel-matrix per-row data
contract) adds the Political Terror Scale source to
the unified source interface on top of the shared
contract:

- the PTS adapter descriptor is registerable / listable
  through the ``InMemorySourceRegistry`` and exposes
  the canonical PTS static metadata (source_id
  ``pts``, default version ``"PTS-2025"``,
  attribution_key ``pts``, dataset type, 1976-2024
  coverage hint, single observation family
  ``domestic_violence_country_year``, PTS homepage
  URL ``https://www.politicalterrorscale.org/``,
  ``requires_network=False``). The canonical
  clean-interface slug is ``pts``; the on-disk folder
  alias is ``political_terror_scale/`` (preserved
  from the live download). This reconciliation is
  documented in ``docs/architecture/sources.md``
  section 7.5 (the ``political_terror_scale`` entry)
  and propagated through the public API
  (``PTS_SOURCE_KEY = "pts"``).
- ``SourceIngestRunner.run(request)`` drives PTS
  end-to-end through the new registry against a
  fixture ``raw_root`` and produces
  ``NormalizedObservation`` records. The fixture's 5
  country-year rows (Afghanistan 2022 + Afghanistan
  2023 + Andorra 2022 + USA 2022 + USA 2023) round-trip
  11 valid observations across the 3 catalog
  indicators (Andorra's PTS_A + PTS_H drop on
  NA_Status=88; USA's PTS_S drops on NA_Status=88 in
  both years -- matching the legacy
  ``tests/test_ingest_pts.py`` contract).
- the runner does not consult legacy
  ``STAGE2_ADAPTERS`` even when the legacy ``pts``
  slot is monkeypatched to a tracker
  (``test_pts_runner_does_not_consult_legacy_stage2_adapters``
  proves the no-legacy-dispatch contract).
- the request ``countries=`` filter applies as an
  exact match against the ``COW_Code_A`` 3-letter
  alphabetic column (the canonical primary key per
  design doc section 7.2); ``test_pts_country_filter_is_applied``
  drives the runner with ``countries=('AFG',)`` and
  verifies the 6 Afghanistan observations round-trip.
- ``years=(2025,)`` (after coverage) and
  ``years=(1975,)`` (before coverage) emit zero
  observations plus a structured ``YEAR_ABSENT``
  warning -- no stale-proxy fill (SRC-COV-002 /
  SRC-COV-003);
- the readiness-failure tests cover the documented
  per-bundle failure classes on two layers: the
  runner-short-circuit layer and the structured
  ``check_ready()`` layer.
  The runner-short-circuit layer (``test_pts_missing_xlsx_fails_readiness_with_missing_raw``
  / ``test_pts_missing_metadata_fails_readiness_with_missing_metadata``
  / ``test_pts_unsupported_source_version_fails_readiness``
  / ``test_pts_mismatched_metadata_version_fails_readiness``
  / ``test_pts_malformed_sha256_fails_readiness``
  / ``test_pts_mismatched_sha256_fails_readiness``
  / ``test_pts_correct_sha256_passes_readiness``
  / ``test_pts_malformed_local_files_fails_readiness``)
  drives the production ``SourceIngestRunner`` against
  a staged bundle, wraps the adapter in a
  ``_SpyPTSAdapter``, and asserts the runner
  short-circuits BEFORE ``read_raw`` / ``transform``
  (the call list stays ``["check_ready"]``).
  The structured ``check_ready()`` layer pins the
  exact error code, ``severity='error'``,
  ``source_id.slug='pts'``, and key ``context`` fields
  directly on ``ReadinessResult.errors`` -- defense
  in depth so a refactor that swaps the error code
  (or drops the severity flag) cannot silently
  regress the contract:
  ``test_pts_check_ready_missing_metadata_emits_structured_error``
  proves the ``missing_metadata`` branch on a
  metadata-only stage (context keys ``bundle_dir``
  + ``xlsx_name``);
  ``test_pts_check_ready_missing_xlsx_emits_structured_error``
  proves the ``missing_raw`` branch on a
  metadata-only stage;
  ``test_pts_check_ready_unsupported_request_version_emits_structured_error``
  proves the SRC-REQ-009 ``unsupported_version``
  branch (context carries ``requested_version`` +
  ``canonical_version``);
  ``test_pts_check_ready_mismatched_bundle_version_emits_structured_error``
  proves the ``pts_metadata_version_mismatch``
  branch when the bundle's ``version`` stamp is not
  the canonical ``"2025"``;
  ``test_pts_check_ready_malformed_sha256_emits_structured_error``
  proves the checksum-shape ``missing_metadata``
  branch when the metadata's ``sha256`` is non-hex;
  ``test_pts_check_ready_sha256_mismatch_emits_structured_error``
  proves the ``pts_checksum_mismatch`` branch when a
  well-formed sha256 disagrees with the staged xlsx
  bytes;
  ``test_pts_check_ready_malformed_local_files_emits_structured_error``
  proves the ``missing_metadata`` branch when
  ``local_files`` is present-but-null;
  ``test_pts_check_ready_wrong_local_files_emits_structured_error``
  proves the ``missing_metadata`` branch when
  ``local_files`` is non-empty but does NOT include
  the canonical xlsx filename;
  ``test_pts_check_ready_missing_required_metadata_field_emits_structured_error``
  proves the ``missing_metadata`` branch when a
  required metadata field is empty (defends the
  per-field validator chain);
  ``test_pts_check_ready_invalid_ingestion_status_emits_structured_error``
  proves the ``missing_metadata`` branch when
  ``ingestion_status`` is not in the documented
  acceptable set.
  ``test_pts_check_ready_happy_path_emits_no_errors``
  pins the green-path envelope -- the canonical
  bundle returns ``ready=True`` with no errors so a
  future refactor that always emits an error cannot
  silently regress the contract.
- the canonical metadata ``source_version="PTS-2025"``
  propagates consistently to ``RawAsset.version`` AND
  every emitted ``NormalizedObservation.source_version``.
  The bundle's ``version="2025"`` (bare-year stamp) is
  a different shape and is validated by
  ``_metadata_source_version_blocker`` but does not
  carry onto observations.
- per-observation ``RawLocator`` carries the staged
  xlsx path + the catalog ``raw_column`` (``PTS_A``
  / ``PTS_H`` / ``PTS_S``) + the positional row index
  in the wide frame (the legacy reader sorts by
  ``COW_Code_A`` ascending for deterministic
  idempotency; the unified transform preserves the
  row index via ``_locate_row_index``);
- per-observation ``extension`` carries the canonical
  PTS attribution text (Rule #15; byte-identical to
  the legacy ``PTS_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/pts_io.py`` and to the
  ``pts`` section in ``docs/sources/attributions.md``),
  the ``source_row_reference="pts:<COW_Code_A>"``
  pattern (matching the legacy Stage 2 DB writer),
  the PTS-specific audit-trail fields
  (``pts_cow_code`` / ``pts_country_name`` /
  ``pts_region`` / ``pts_na_status``), the
  pre-coercion ``raw_value`` cell text (int
  string for valid cells; ``"NA"`` for dropped cells
  per the §6.3 audit-trail matrix), and the direction
  hints (``higher_is_better=False`` / ``raw_scale``
  ``"ordinal"`` / ``normalized_scale_target``
  ``"0-10"`` -- the raw 1-5 value is preserved
  verbatim and the Stage 5 score module inverts the
  direction);
- the §6 sentinel-matrix contract is preserved
  byte-for-byte. The per-row observation emission
  skips cells where ``NA_Status != 0`` AND where
  ``PTS_X='NA'`` AND ``NA_Status=0`` (the case-4
  inconsistency path); the case-1 (valid) cells
  emit ``value`` as the int 1-5. The sentinel-matrix
  helper tests
  (``test_pts_sentinel_matrix_case_1_valid_int`` /
  ``_case_2_int_with_nonzero_status`` /
  ``_case_3_na_with_nonzero_status`` /
  ``_case_4_inconsistency`` /
  ``_unknown_na_status_warning`` /
  ``_all_known_na_status_codes``) cover the 4-case
  matrix + the §6.5 defensive check + all 5 known
  ``NA_Status`` codes (``0`` / ``66`` / ``77`` / ``88``
  / ``99``);
- the legacy ``PTS_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/pts_io.py`` is byte-identical
  to the new ``PTS_ATTRIBUTION_TEXT``
  (``test_pts_attribution_text_matches_attributions_doc``
  asserts byte-identity AND that the unified text is
  a substring of ``docs/sources/attributions.md`` --
  Rule #15 drift guard);
- the PTS unified path is local-file only
  (``requires_network=False``, no HTTP layer in the
  new package). The runner NEVER invokes the network
  -- there is no HTTP layer in the clean adapter at
  all. ``test_pts_runner_never_invokes_network``
  pins the contract on the actual production runner
  path: it monkeypatches the canonical Python
  network surfaces (``requests.get`` / ``requests.post``
  / ``requests.head`` / ``urllib.request.urlopen`` /
  ``socket.socket``) to raise, while wrapping the legacy
  ``read_pts`` bridge as an allowed local-xlsx reader spy
  that must receive only the staged ``xlsx_path`` and no
  hidden network kwargs. It then drives
  ``SourceIngestRunner.run(request)`` end-to-end from
  a staged fixture and asserts the 11 observations
  round-trip without invoking any network tripwire (the
  canonical bundle is staged at
  ``data/raw/political_terror_scale/PTS-2025.xlsx``
  and the readiness gate validates the staged xlsx
  + the metadata checksum / version / license /
  coverage / file-format / ingestion_status / notes
  / local_files fields BEFORE ``read_raw`` /
  ``transform`` are called);
- the clean package ``__all__`` exposes every public
  symbol documented in the adapter module +
  descriptor (``test_pts_public_surface_is_coherent``
  enforces the public surface contract).

## Manual / boundary checks

Use a fresh Python process to confirm the import boundary:

```bash
python - <<'PY'
import importlib
import sys

importlib.import_module("leaders_db.sources.adapters.pwt")
importlib.import_module("leaders_db.sources.adapters.world_bank_wgi")
importlib.import_module("leaders_db.sources.adapters.vdem")
importlib.import_module("leaders_db.sources.adapters.ucdp")
importlib.import_module("leaders_db.sources.adapters.transparency_cpi")
importlib.import_module("leaders_db.sources.adapters.pts")
leaked = sorted(name for name in sys.modules if name.startswith("leaders_db.ingest"))
print(leaked)
assert leaked == []
PY
```

Expected: `[]`. The PWT, WGI, V-Dem, UCDP, Transparency
International CPI, and PTS adapter modules import
cleanly
without pulling in the legacy ingest package.

Use the explicit lazy bridge only when legacy access is needed:

```bash
python - <<'PY'
from leaders_db.sources.legacy import get_legacy_stage2_adapters

adapters = get_legacy_stage2_adapters()
print(len(adapters), "pwt" in adapters)
assert "pwt" in adapters
PY
```

Expected: a positive adapter count and `True` for `pwt`.

## Out of scope for this slice

- Processed-file persistence, database writes, manifest writing, and shared
  validation beyond the current contract envelope.
- New CLI commands under `leaders-db sources ...`.
- Moving or deleting legacy `src/leaders_db/ingest/` code.
- The remaining clean source migrations
  (archigos, reign, sipri_milex,
  sipri_yearbook_ch7, cirights, undp_hdi, who_gho_api,
  fas, wikidata_heads_of_state_government,
  wikipedia_search_extract, ...).
  PWT, Maddison Project, World Bank WDI, World Bank
  WGI, V-Dem, UCDP, Transparency International CPI,
  PTS, RSF, BTI, and Freedom House are the proof-of-pattern across
  dataset (PWT), historical xlsx (Maddison),
  API/cache (WDI), local-file governance xlsx (WGI),
  large local CSV (V-Dem), event-level zip (UCDP),
  per-year CSV (CPI), single xlsx (PTS), and
  multi-file annual CSV (RSF), biennial local xlsx (BTI), and
  user-managed restricted local xlsx (Freedom House FIW) source shapes;
  future migrations follow the
  same `src/leaders_db/sources/adapters/<slug>/` layout.

## Freedom House Freedom in the World

The Freedom House adapter lives at
`src/leaders_db/sources/adapters/freedom_house/` and reads the
user-managed FIW 2026 ratings/statuses workbook staged under
`data/raw/freedom_house/`. It emits the three core FIW political-freedom
signals (`freedom_house_political_rights`,
`freedom_house_civil_liberties`, `freedom_house_status`) as
`political_freedom_country_year` observations.

**Verification commands:**

```bash
.venv/bin/pytest -q tests/sources/test_freedom_house_adapter.py \
                    tests/sources/test_import_boundary.py
.venv/bin/ruff check src/leaders_db/sources/adapters/freedom_house/ \
                  tests/sources/test_freedom_house_adapter.py \
                  tests/sources/test_import_boundary.py
wc -l src/leaders_db/sources/adapters/freedom_house/*.py
```

These tests verify descriptor/factory/registry/runner wiring, readiness
success and failure paths, checksum validation, `years=None` all-years
semantics, multi-year requests, out-of-coverage warnings, ignored leader
filters, import-boundary isolation from `leaders_db.ingest`, no network
access, source attribution drift, and raw locator/provenance preservation.

## RSF World Press Freedom Index

The RSF adapter lives at
`src/leaders_db/sources/adapters/rsf_press_freedom/`
and follows the same
`leaders_db.sources.adapters.<slug>/` layout as the
prior clean-source migrations. The canonical
descriptor / factory / lifecycle class live in
`adapter.py`; the static constants in `_constants.py`
+ `_indicator_constants.py` (the 7 indicator names +
the 2 base raw_columns, extracted from `_constants.py`
to keep it under the 400-line convention) +
`_descriptor.py`; the readiness gate in
`_readiness.py` + `_metadata_validators.py` +
`_metadata_version_validators.py` +
`_files_validators.py` + `_year_validators.py`; the
catalog helpers in `_catalog.py`; the missing-value
helpers in `_missing_values.py`; the per-row
emission in `_transform.py` + `_helpers.py`; the
per-row observation construction in
`_observation_builder.py` +
`_observation_helpers.py`; the raw-read
orchestration in `_raw_read.py`; the
transform-pipeline orchestration in `_pipeline.py`;
and the registration helpers + protocol
conformance guard in `_registration.py`.

**Verification commands:**

```bash
# Full RSF adapter suite + import-boundary + legacy
# RSF tests + the focused subset.
.venv/bin/pytest -q tests/sources/test_rsf_press_freedom_adapter.py \
                    tests/sources/test_import_boundary.py \
                    tests/test_ingest_rsf_press_freedom.py
.venv/bin/ruff check src/leaders_db/sources/adapters/rsf_press_freedom/ \
                  tests/sources/test_rsf_press_freedom_adapter.py \
                  tests/sources/test_import_boundary.py
.venv/bin/wc -l src/leaders_db/sources/adapters/rsf_press_freedom/*.py
```

The RSF slice acceptance covers the descriptor /
factory / protocol / register / listable contract;
the runner end-to-end on staged fixtures for both
the pre-2022 schema (2002) and the post-2022
schema (2023); the canonical version propagation
(`"RSF Press Freedom Index 2026"`); the readiness
gate (missing metadata, missing per-year CSV,
malformed `local_files`, malformed `files` entry,
mismatched bundle `source_version`, mismatched
per-file `sha256`, unsupported request
`source_version`, year=2011 documented missing
caveat, year=2027 out-of-coverage year filter);
the request-scoping warnings (out-of-coverage year
filter, leader filter); the no-network contract on
the production runner path (monkeypatched
`requests.*` / `urllib.request.urlopen` /
`socket.socket` tripwires); the per-observation
extension (RSF-specific `rsf_raw_column` /
`rsf_iso3` / `rsf_category` / `rsf_actual_column` /
`rsf_schema_group` audit-trail fields,
`source_row_reference="rsf_press_freedom:<iso3>:<actual>"`
pattern, verbatim `raw_value` cell text, direction
hints); the import-boundary contract (no
`leaders_db.ingest` import at module import time);
and the legacy `STAGE2_ADAPTERS` non-routing
contract.

## Bertelsmann Transformation Index / BTI

The BTI adapter lives at
`src/leaders_db/sources/adapters/bti/` and
follows the same
`leaders_db.sources.adapters.<slug>/` layout as
the prior clean-source migrations. The canonical
descriptor / factory / lifecycle class live in
`adapter.py`; the static core constants in
`_constants.py`; the 12 indicator names + 12
raw column names in `_indicator_constants.py`;
the descriptor factory in `_descriptor.py`; the
readiness gate in `_readiness.py` +
`_metadata_validators.py` +
`_checksum_validators.py`; the catalog helpers
in `_catalog.py`; the missing-value coercion
helpers in `_missing_values.py`; the per-row
emission loop in `_transform.py` +
`_transform_helpers.py`; the per-row observation
construction in `_observation_builder.py`; the
raw-read orchestration in `_raw_read.py`; the
transform-pipeline orchestration in
`_pipeline.py`; and the registration helpers +
protocol conformance guard in `adapter.py`.

**Biennial sheet/year mapping.** BTI is the
first source with a **biennial sheet/year
mapping**: each BTI edition covers the ~2-year
period preceding publication. For the prototype
target year 2023, the canonical mapping resolves
to the `BTI 2024` sheet (covers 2022-2023); for
year 2021 -> `BTI 2022`; for year 2025 -> `BTI
2026`. The per-edition covered interval map lives
in `_BTI_EDITION_COVERED_INTERVAL` in
`src/leaders_db/ingest/bti_io.py`; the
`sheet_for_year` resolver drives explicit
`years=` sheet selection at read time. The unified
raw-read path reads every requested in-coverage
BTI sheet, and `years=None` reads every available
BTI sheet in the staged workbook. The resolved
per-row sheet name + covered interval are carried
on every observation's `extension`
(`bti_sheet_name` / `bti_target_year`) so
downstream Stage 5 score modules can apply the
proxy / source-edition semantics without
re-reading the parquet metadata.

**Verification commands:**

```bash
# Full BTI adapter suite + import-boundary + legacy
# BTI tests + the focused subset.
.venv/bin/pytest -q tests/sources/test_bti_adapter.py \
                    tests/sources/test_import_boundary.py \
                    tests/test_ingest_bti.py
.venv/bin/ruff check src/leaders_db/sources/adapters/bti/ \
                  tests/sources/test_bti_adapter.py \
                  tests/sources/test_import_boundary.py
.venv/bin/wc -l src/leaders_db/sources/adapters/bti/*.py
```

The BTI slice acceptance covers the descriptor /
factory / protocol / register / listable contract
(source_id `bti`, default version `"BTI 2026"`,
attribution_key `bti`, dataset type, 2002-2025
coverage hint, 3 observation families
`effectiveness_country_year` /
`political_freedom_country_year` /
`economic_wellbeing_country_year`, BTI homepage
URL); the runner end-to-end on a staged fixture
(5 country-edition rows x 12 indicators = 60
observations round-trip); the canonical version
propagation (`"BTI 2026"`); the **biennial
sheet/year mapping** (target year 2023 -> `BTI
2024`; year 2021 -> `BTI 2022`; year 2025 ->
`BTI 2026`; `years=None` emits all available
fixture sheets; multi-year requests emit each
requested in-coverage sheet); the readiness gate
(missing metadata, missing xlsx, missing required
metadata field, malformed `local_files`, wrong
`local_files`, malformed checksum, mismatched
checksum, correct checksum pass, malformed
bundle `source_version`, mismatched bundle
`source_version`, unsupported request
`source_version`, invalid `ingestion_status`); the
request-scoping warnings (out-of-coverage year
filter, leader filter); the no-network contract on
the production runner path (monkeypatched
`requests.*` / `urllib.request.urlopen` /
`socket.socket` tripwires, plus a spy on the
legacy `read_bti` bridge that asserts only the
local xlsx is read); the per-observation extension
(BTI-specific `bti_raw_column` /
`bti_country_name` / `bti_sheet_name` /
`bti_target_year` / `bti_rating_category`
audit-trail fields, `source_row_reference="bti:<country_name>"`
pattern matching the legacy Stage 2 DB writer,
verbatim `raw_value` cell text, direction hints
(`higher_is_better=True` + `raw_scale="1-10"` +
`normalized_scale_target="0-10"`)); the
import-boundary contract (no `leaders_db.ingest`
import at module import time); the legacy
`STAGE2_ADAPTERS` non-routing contract; and the
clean package `__all__` public-surface coherence
contract.
