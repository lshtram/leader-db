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

## Manual / boundary checks

Use a fresh Python process to confirm the import boundary:

```bash
python - <<'PY'
import importlib
import sys

importlib.import_module("leaders_db.sources.adapters.pwt")
importlib.import_module("leaders_db.sources.adapters.world_bank_wgi")
importlib.import_module("leaders_db.sources.adapters.vdem")
leaked = sorted(name for name in sys.modules if name.startswith("leaders_db.ingest"))
print(leaked)
assert leaked == []
PY
```

Expected: `[]`. The PWT, WGI, and V-Dem adapter modules import cleanly
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
- The sixth / seventh / ... clean source migrations
  (transparency_cpi, rsf_press_freedom, bti, ...). PWT,
  Maddison Project, World Bank WDI, World Bank WGI, and
  V-Dem are the proof-of-pattern across dataset (PWT),
  historical xlsx (Maddison), API/cache (WDI),
  local-file governance xlsx (WGI), and large local CSV
  (V-Dem) source shapes; future migrations follow the
  same `src/leaders_db/sources/adapters/<slug>/` layout.
