# Architecture — Unified Source System

This document defines the future source-ingestion and source-query architecture
for `leaders-db`. It is intentionally separate from the current prototype
Stage 2 implementation under `src/leaders_db/ingest/`.

The current codebase has proven useful patterns, especially the PWT shared
adapter experiment, but the target architecture below is the clean source system
that all current and future sources should eventually use.

---

## 1. Purpose

The source system answers two different questions:

1. **How do we turn raw source material into normalized evidence?**
2. **How do later scoring, validation, and research code ask for that evidence
   consistently?**

The answer is a new `leaders_db.sources` subsystem with:

- one source adapter contract for every source,
- one runner for readiness / read / transform / validate / persist / manifest,
- one normalized observation model,
- one manifest / provenance / attribution contract,
- one evidence-query interface for downstream research questions.

This replaces the long-term role of ad hoc per-source functions and the legacy
`STAGE2_ADAPTERS` dispatch table.

---

## 2. Design Principles

1. **One public interface for every source.** A local xlsx, web API, cached JSON,
   PDF, HTML page, manually staged dataset, derived source, and future LLM-gated
   ambiguity helper all enter through the same source lifecycle.
2. **Thin adapters, strong shared runner.** Source adapters parse source-native
   material. Shared infrastructure owns validation, persistence, idempotency,
   manifesting, and common provenance rules.
3. **Normalized observations are the evidence unit.** Downstream scoring and
   research code should not know whether a value came from Excel, an API, or a
   PDF. It consumes normalized observations and provenance.
4. **Manifests are first-class.** Every run records inputs, outputs, warnings,
   coverage, source version, attribution, and hashes.
5. **No silent data invention.** Missing or out-of-coverage data produces zero
   rows plus explicit warnings unless a documented derived-source rule applies.
6. **The client matrix is validation-only.** If represented in the source system,
   it is marked `validation_only` and never counted as evidence.
7. **Local-first, not service-first.** The architecture stays a Python research
   tool using local files, SQLite/PostgreSQL, and deterministic outputs.
8. **Legacy stays isolated.** Existing prototype code may remain available, but
   new source work should be built under the new source subsystem.

---

## 3. Package Boundary

Target package:

```text
src/leaders_db/sources/
├── __init__.py
├── contracts.py          # dataclasses, protocols, enums
├── registry.py           # central source registry and discovery
├── runner.py             # SourceIngestRunner lifecycle orchestration
├── validation.py         # shared source-contract validation
├── persistence.py        # processed-file + DB persistence
├── manifests.py          # manifest models and read/write helpers
├── provenance.py         # raw assets, locators, checksums
├── attribution.py        # machine-readable attribution registry
├── coverage.py           # coverage reports and out-of-coverage helpers
├── warnings.py           # warning/error code constants
├── cache.py              # API/cache policy helpers
├── query.py              # EvidenceRepository research/query interface
├── cli.py                # new `leaders-db sources ...` commands
└── adapters/
    └── <source_slug>/
        ├── __init__.py
        ├── adapter.py
        ├── descriptor.py
        ├── schema.py
        ├── catalog.csv
        └── README.md
```

Legacy package:

```text
src/leaders_db/ingest/
```

Rules:

- New source adapters go under `src/leaders_db/sources/adapters/<source>/`.
- Do not add new sources to the old `STAGE2_ADAPTERS` table.
- Legacy code may remain runnable while the new subsystem is built.
- A later mechanical migration may move old prototype modules into `legacy-src/`
  or `src/leaders_db_legacy/`, but that should be a separate reviewed move with
  import/CLI compatibility decisions made explicitly.

---

## 4. Core Lifecycle

Every source follows this lifecycle:

```text
discover/register
  -> check_ready(request)
  -> read_raw(request)
  -> transform(request, raw)
  -> validate(request, observations)
  -> persist(request, observations, validation)
  -> build_manifest(...)
  -> query via EvidenceRepository
```

### 4.1 Discover / register

The central registry exposes source descriptors and adapter instances:

```python
registry.list_sources()
registry.get(SourceId("pwt"))
```

The registry is the target replacement for `STAGE2_ADAPTERS`.

### 4.2 Readiness

`check_ready(request)` verifies raw files, metadata, checksums, source version,
manual approvals, cache availability, and request validity before any parsing.

### 4.3 Raw read

`read_raw(request)` reads immutable local files or allowed API/cache responses
and returns raw assets plus structured payloads.

### 4.4 Transform

`transform(request, raw)` emits normalized observations. It applies requested
year, country, and leader filters before persistence.

### 4.5 Validate

Shared validation enforces required fields, provenance, attribution, duplicate
rules, coverage behavior, no silent stale fills, and request-scope correctness.

### 4.6 Persist

Shared persistence writes processed observations and DB rows idempotently. Source
adapters should not hand-roll DB engines or output paths.

### 4.7 Manifest

Each run writes an immutable manifest under `data/processed/<source>/`, with an
optional latest pointer.

### 4.8 Query

Downstream scoring/research code uses `EvidenceRepository`, not raw files and not
source-specific adapter functions.

---

## 5. Core Contracts

The exact implementation may use dataclasses or Pydantic models, but these fields
define the architecture.

### 5.1 Source identity

```python
@dataclass(frozen=True)
class SourceId:
    slug: str
```

`slug` must match the adapter registry key, raw folder, processed folder,
manifest source key, and attribution key unless a documented alias exists.

### 5.2 Source descriptor

```python
@dataclass(frozen=True)
class SourceDescriptor:
    source_id: SourceId
    display_name: str
    source_type: Literal[
        "dataset", "api", "manual", "derived", "document",
        "knowledge_base", "validation_only"
    ]
    supported_observation_families: tuple[str, ...]
    default_version: str | None
    homepage_url: str | None
    attribution_key: str
    coverage_hint: CoverageHint
    requires_manual_approval: bool = False
    requires_network: bool = False
```

### 5.3 Ingest request

```python
@dataclass(frozen=True)
class SourceIngestRequest:
    source_id: SourceId
    years: tuple[int, ...] | None = None
    countries: tuple[str, ...] | None = None
    leaders: tuple[str, ...] | None = None
    raw_root: Path = Path("data/raw")
    processed_root: Path = Path("data/processed")
    metadata_root: Path = Path("data/metadata")
    db_url: str | None = None
    db_session: Any | None = None
    source_version: str | None = None
    run_id: str | None = None
    dry_run: bool = False
    overwrite: bool = False
    cache_policy: Literal[
        "offline_only", "prefer_cache", "refresh", "no_cache"
    ] = "prefer_cache"
    output_formats: tuple[Literal["parquet", "csv"], ...] = ("parquet",)
```

Rules:

- `years=None` means all available years in the source, not “current year.”
- Unsupported filters produce structured warnings or errors, never silent broad
  ingestion.
- `dry_run=True` must not mutate files or DB rows.
- API adapters must obey `cache_policy`.

### 5.4 Raw asset and locator

```python
@dataclass(frozen=True)
class RawAsset:
    asset_id: str
    source_id: SourceId
    version: str | None
    media_type: str | None
    path: Path | None = None
    url: str | None = None
    checksum_sha256: str | None = None
    retrieved_at: datetime | None = None
    immutable: bool = True

@dataclass(frozen=True)
class RawLocator:
    asset_id: str
    path: str | None = None
    url: str | None = None
    sheet: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    page_number: int | None = None
    html_selector: str | None = None
    json_pointer: str | None = None
    api_endpoint: str | None = None
    api_params_hash: str | None = None
```

### 5.5 Normalized observation

```python
@dataclass(frozen=True)
class NormalizedObservation:
    source_id: SourceId
    observation_id: str
    observation_family: str
    indicator_code: str
    value: str | int | float | bool | None
    value_type: Literal["numeric", "categorical", "text", "boolean", "json", "missing"]
    year: int | None
    country_code: str | None
    country_name: str | None
    leader_id: str | None
    leader_name: str | None
    unit: str | None
    scale: str | None
    source_version: str | None
    raw_locator: RawLocator
    transform_locator: TransformLocator
    quality_flags: tuple[str, ...]
    warnings: tuple[SourceWarning, ...]
    extension: Mapping[str, JsonValue]
```

This contract is the bridge between source-specific data and future research
questions.

### 5.6 Adapter and runner

Adapters stay thin:

```python
class SourceAdapter(Protocol):
    descriptor: SourceDescriptor

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult: ...
    def read_raw(self, request: SourceIngestRequest) -> RawReadResult: ...
    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]: ...
```

The shared runner owns orchestration:

```python
class SourceIngestRunner:
    def __init__(self, registry: SourceRegistry) -> None: ...

    @property
    def registry(self) -> SourceRegistry: ...

    def run(
        self,
        request: SourceIngestRequest,
    ) -> SourceIngestResult: ...
```

The runner is registry-backed: it looks up the adapter for
`request.source_id` via `SourceRegistry.get_adapter` and never accepts an
adapter argument. The new registry is the single dispatch surface — the
runner does not consult the legacy `leaders_db.ingest.STAGE2_ADAPTERS`
table. `SourceIngestRunner.run(request)` currently drives the adapter
lifecycle in the documented fixed order `check_ready -> read_raw ->
transform` and returns a `SourceIngestResult` whose `manifest` is `None`;
shared validation, persistence, and manifest generation are deferred to
later phases and remain runner-owned when implemented.

### 5.7 Evidence repository

```python
@dataclass(frozen=True)
class EvidenceQuery:
    source_ids: tuple[SourceId, ...] | None = None
    observation_families: tuple[str, ...] | None = None
    indicator_codes: tuple[str, ...] | None = None
    years: tuple[int, ...] | None = None
    countries: tuple[str, ...] | None = None
    leaders: tuple[str, ...] | None = None
    include_raw_locators: bool = True
    include_attribution: bool = True

class EvidenceRepository(Protocol):
    def query_observations(self, query: EvidenceQuery) -> Sequence[NormalizedObservation]: ...
    def get_manifest(self, source_id: SourceId, run_id: str | None = None) -> SourceManifest: ...
    def get_attributions(self, source_ids: Sequence[SourceId]) -> Sequence[SourceAttribution]: ...
```

Scorers, validation reports, manual review, and research tools should depend on
this query interface instead of calling source adapters directly.

---

## 6. Required Invariants

Every source must satisfy these invariants:

1. Raw assets are immutable.
2. Every observation has a source id, source version, indicator code, entity
   scope, raw locator, transform locator, and attribution link.
3. Every successful non-dry-run writes processed observations and a manifest.
4. Every DB write is idempotent for the request scope.
5. Out-of-coverage years produce warnings and zero rows unless a documented
   derived-source rule applies.
6. Network access happens only when cache policy allows it.
7. Manual-gated sources fail readiness until local metadata/approval exists.
8. Derived indicators declare input manifests and never masquerade as raw
   external evidence.
9. Client-matrix data, if represented, is `validation_only` and excluded from
   evidence scoring and source agreement.
10. Public-output-capable manifests carry normative source attribution text.

---

## 7. Source Migration Inventory

All listed sources should eventually be represented under the new interface.

### 7.1 Implemented prototype sources to rebuild or migrate

| Source slug | Current prototype status | New-interface target role | Suggested migration priority |
|---|---|---|---|
| `pwt` | implemented in prototype shared-adapter experiment | economic country-year observations | 1 |
| `maddison_project` | implemented | historical economic country-year observations | 2 |
| `world_bank_wdi` | implemented | WDI API/cache country-year indicators | 3 |
| `world_bank_wgi` | implemented | WGI governance country-year indicators | 4 |
| `vdem` | implemented | large political/social country-year indicators | 5 |
| `transparency_cpi` | implemented | corruption/integrity country-year indicators | 6 |
| `rsf_press_freedom` | implemented | press-freedom country-year indicators | 7 |
| `bti` | implemented | governance / democracy / transformation indicators | 8 |
| `archigos` | implemented | leader identity and tenure | 9 |
| `reign` | implemented | leader identity, regime, tenure | 10 |
| `ucdp` | implemented | conflict and violence observations | 11 |
| `sipri_milex` | implemented | military-expenditure observations | 12 |
| `sipri_yearbook_ch7` | implemented | nuclear-force observations | 13 |
| `pts` | implemented | political terror / repression indicators | 14 |
| `cirights` | implemented | human-rights indicators | 15 |
| `undp_hdi` | implemented | HDI/social well-being indicators | 16 |
| `who_gho_api` | implemented | health API/cache indicators | 17 |
| `fas` | implemented | nuclear-force document/API-style observations | 18 |
| `wikidata_heads_of_state_government` | implemented | knowledge-base leader identity observations | 19 |
| `wikipedia_search_extract` | implemented | cached web/knowledge snippets | 20 |

### 7.2 Pending or blocked sources to implement only in the new interface

| Source slug | Current status | New-interface notes |
|---|---|---|
| `polity_v` | raw file observed locally, metadata incomplete | first post-interface source after docs/stubs if source hygiene is completed |
| `leader_survival` | blocked on Demscore manual gate | manual-gated source readiness proof |
| `freedom_house` | user-managed/local staging needed | manual/local xlsx source |
| `imf_weo` | blocked by access challenge | user-managed or future manual/API path |
| `cow_mid` | blocked/deferred | conflict source if raw access is resolved |
| `nti` | blocked/user-managed | nuclear/manual document source |
| `sipri_arms_transfers` | future | arms-transfer / proxy-war evidence |
| `iaea_safeguards` | future | nuclear safeguards evidence |
| `iaea_additional_protocol_status` | future | nuclear treaty/status evidence |
| `unoda_treaties` | future | treaty posture evidence |
| `ctbto_treaty_status` | future | nuclear-test-ban status evidence |
| `ctbto_nuclear_tests` | future | nuclear-test observations |
| `csis_missile_threat` | future | missile capability observations |
| `cns_nti_missile_launches` | future | missile-launch observations |
| `world_bank_poverty_inequality_platform` | future | poverty/inequality indicators |
| `ilo_labor_statistics` | future | labor/employment indicators |
| `world_bank_global_findex` | future | financial inclusion / access-to-basic-services indicators; survey-wave temporal-fit rules required |
| `world_inequality_database` | future | top income/wealth shares and distribution indicators; careful series/unit selection required |
| `ucdp_external_support` | future | proxy-aggression / external-support dyads and sponsor-year aggregation |
| `non_state_actor_dataset` | future | non-state actor capability/context and state-rebel dyad support context |
| `dangerous_companions_nags` | future | state support/cooperation with non-state armed groups; availability/license vetting required |
| `att_monitor` | future | arms-transfer legality and national arms-export report evidence; likely document/manual source |
| `acled` | future | actor-event conflict data and proxy/militia activity; API/license/token rules required |
| `nuclear_weapons_ban_monitor` | future | nuclear-armed/umbrella/treaty posture and disarmament profile evidence |
| `world_nuclear_association_profiles` | future | civilian fuel-cycle and nuclear infrastructure context; must distinguish civilian capacity from weapons intent |
| `nti_country_profiles` | blocked / user-managed future | manually captured NTI country-profile evidence if direct `nti` access remains blocked |
| `government_manifestos` | future | promise-to-results source for stated goals; likely manual/document + cited-snippet extraction |
| `budget_execution_reports` | future | budgets, execution, public-investment, and program-delivery records; heterogeneous document source |
| `national_statistics_goal_indicators` | future | country-specific official/independent outcome indicators tied to stated goals |
| `audit_oversight_reports` | future | implementation-quality and course-correction evidence from audit / oversight documents |

### 7.3 Documented aliases, subsets, retired candidates, and exclusions

These keys are still part of the unified-source inventory because existing docs
mention them, but their target representation may be an alias, subset, or
explicit exclusion rather than a normal source adapter.

| Source slug | Status | New-interface decision |
|---|---|---|
| `acled_ucdp_osv` | implemented as UCDP one-sided violence subset | represent as an observation family / catalog subset under `ucdp`, not a separate adapter unless requirements change |
| `chicago_aisd` | auxiliary/retired candidate in attribution notes | exclude from first migration unless re-vetted as a source; keep documented as not active evidence |
| `cia_world_leaders` | retired candidate | exclude from active unified registry unless revived as a validation/fallback source with explicit attribution and source hygiene |

### 7.4 Validation-only source

| Source slug | Role | Rule |
|---|---|---|
| `client_existing` | validation/comparison reference | may be represented only as `validation_only`; never evidence |

### 7.5 Chronicle / curated / subset source keys from `docs/sources/registry.md`

These source keys are documented in the broader project registry and must not be
lost, but their new-interface representation is either a normal adapter, a
Chronicle-focused adapter, or an alias/subset of another adapter.

| Source slug | Current status | New-interface representation |
|---|---|---|
| `soviet_leaders_curated` | implemented as curated local CSV for SUN ruler gaps | first-class manual/curated leader-source adapter with project-authored provenance; no web facts invented at runtime |
| `cshapes` | implemented for Chronicle country-area rows | first-class country-area source adapter under `leaders_db.sources`, even if first used by Chronicle only |
| `icow_colonial` | blocked; canonical URL returned 404 | keep as blocked future controlled-area / dependency-controller source until a working raw source is vetted |
| `political_terror_scale` | documented source key for PTS | canonical external source slug should be reconciled during migration: either rename `pts` -> `political_terror_scale` or keep `pts` with `political_terror_scale` as documented alias |
| `world_bank_wdi_social` | WDI health / education / inequality subset | represent as observation family / catalog subset under `world_bank_wdi`, not a separate raw adapter |
| `vdem_governance` | V-Dem governance sub-indicators | represent as observation family / catalog subset under `vdem`, not a separate raw adapter |
| `world_bank_wgi_corruption` | WGI Control of Corruption subset | represent as observation family / catalog subset under `world_bank_wgi`, not a separate raw adapter |
| `vdem_corruption` | V-Dem corruption variables | represent as observation family / catalog subset under `vdem`, not a separate raw adapter |

---

## 8. Legacy Separation Plan

The project should separate prototype achievements from the new source system in
stages.

### Stage 1 — logical separation now

- Keep existing code in place so commands/tests continue to work.
- Add the new `leaders_db.sources` package.
- Add docs and contract tests for the new package.
- Stop adding new source functionality to the old `ingest` subsystem.

### Stage 2 — first clean source migrations

- Rebuild PWT in `leaders_db.sources.adapters.pwt` without relying on old
  `STAGE2_ADAPTERS`.
- Then rebuild Maddison, WDI/WGI, and V-Dem to prove local tabular, historical,
  API/cache, and large-file patterns.

### Stage 3 — deprecate legacy CLI paths

- Add `leaders-db sources ...` commands backed by the new registry.
- Keep old commands temporarily as compatibility wrappers.
- Mark old Stage 2 commands as legacy in CLI help and docs.

### Stage 4 — optional physical move

After enough new infrastructure is stable, choose one of these physical
separation options:

1. **Keep legacy in place but frozen** under `src/leaders_db/ingest/`.
2. **Move prototype source-ingestion code to `legacy-src/`** and keep only a
   compatibility shim in `src/`.
3. **Move old modules to `src/leaders_db_legacy/`** if importable legacy code is
   still needed.

Recommendation: do not physically move all current code in the same step as the
new interface docs. First build the new package and contract tests. Perform any
large legacy move as its own mechanical, reviewed commit.

---

## 9. First Milestones

1. **Docs and requirements.** Land this architecture, source requirements, and
   the layman guide.
2. **Importable stubs.** Add `leaders_db.sources` contracts, registry, runner,
   manifests, persistence, query, and warning/error code stubs.
3. **Contract tests.** Write failing tests that define the shared contract.
4. **First clean adapter.** Rebuild PWT under `leaders_db.sources.adapters.pwt`.
   **Landed (2026-06-23)** as a thin adapter that implements the
   `SourceAdapter` Protocol (`descriptor` + `check_ready` + `read_raw` +
   `transform`) and reuses the legacy reader / transform via lazy
   imports. The package import does NOT pull in `leaders_db.ingest`
   (verified by `tests/sources/test_pwt_adapter.py::test_pwt_adapter_module_does_not_import_legacy_ingest_at_import`).
   The runner end-to-end contract is verified by
   `tests/sources/test_pwt_adapter.py::test_pwt_runner_produces_normalized_observations`
   (17 fixture observations round-tripped) and
   `test_pwt_runner_does_not_consult_legacy_stage2_adapters` (legacy
   `STAGE2_ADAPTERS["pwt"]` tracker is never invoked). No persistence,
   manifest, or DB writes landed; the runner still returns `manifest=None`.
   The package exposes explicit `create_pwt_adapter()` /
   `register_pwt(registry)` factories and does NOT auto-register on import
   (§10.1).
5. **Second/third adapters.** Rebuild Maddison and WDI/WGI to prove the design
   across different source shapes. **Maddison Project Database 2023 landed
   (2026-06-24)** as the second clean-source migration under
   `src/leaders_db/sources/adapters/maddison_project/`. The adapter
   implements the full `SourceAdapter` Protocol and reuses the legacy
   reader under `leaders_db.ingest.maddison_project_xlsx` via lazy imports;
   the package import does NOT pull in `leaders_db.ingest`
   (`tests/sources/test_maddison_project_adapter.py::test_maddison_project_adapter_module_does_not_import_legacy_ingest_at_import`).
   The runner end-to-end contract is proven by
   `test_maddison_project_runner_produces_normalized_observations`
   (21 fixture observations round-tripped) and
   `test_maddison_project_runner_does_not_consult_legacy_stage2_adapters`
   (monkeypatched legacy `STAGE2_ADAPTERS["maddison_project"]` tracker
   is never invoked). Source-specific year semantics: Maddison 2023
   release ends at 2022; a request for `years=(2023,)` triggers the
   documented 1-year-gap proxy mapping to 2022 data and surfaces a
   structured `maddison_project_proxy_year` warning on the readiness
   envelope plus the `proxy_year` quality flag and the
   `requested_year` / `proxy_source_year` extension fields on every
   emitted observation; a request for `years=(2024,)` (or any year
   beyond 2022) emits zero observations plus a structured `YEAR_ABSENT`
   warning -- no multi-year stale-proxy fill (SRC-COV-002 / SRC-COV-003).
    The canonical version `"2023"` propagates consistently to
    `RawAsset.version` and every emitted
    `NormalizedObservation.source_version`. The runner still returns
    `manifest=None`; no persistence, DB writes, or manifest writing
    landed. The package exposes explicit
    `create_maddison_project_adapter()` / `register_maddison_project(registry)`
    factories and does NOT auto-register on import (§10.1).
  6. **Third clean-source migration landed (2026-06-24) — World Bank WDI under
     `src/leaders_db/sources/adapters/world_bank_wdi/`.** WDI is
     the third source rebuilt under the new `leaders_db.sources`
     interface (docs/architecture/sources.md §7.1 priority 3,
     docs/requirements/sources.md §12 SRC-MIG-005), after PWT
     10.01 and Maddison Project Database 2023. The new package
     implements the full `SourceAdapter` Protocol and reuses
     the legacy reader / catalog loader under
     `leaders_db.ingest.wdi_io` via lazy imports; the package
     import does NOT pull in `leaders_db.ingest`
     (`tests/sources/test_world_bank_wdi_adapter.py::test_wdi_adapter_module_does_not_import_legacy_ingest_at_import`
     + the import-boundary submodule list in
     `tests/sources/test_import_boundary.py`). The runner
     end-to-end contract is proven by
     `test_wdi_runner_produces_normalized_observations` (125
     fixture observations round-tripped for the unfiltered run;
     61 for `years=(2023,)`, 25 for `countries=('USA',)`, 12
     for `years=(2023,) + countries=('USA',)`) and
     `test_wdi_runner_does_not_consult_legacy_stage2_adapters`
     (monkeypatched legacy `STAGE2_ADAPTERS["world_bank_wdi"]`
     tracker is never invoked). The WDI descriptor exposes
     `source_id="world_bank_wdi"`,
     `default_version="World Bank API v2; cached indicator
     responses"` (matches the staged bundle's metadata.json
     byte-for-byte), `attribution_key="world_bank_wdi"`,
     `source_type="api"`, `requires_network=True`, coverage
     hint 1960-present, and supported observation families
     `("economic_country_year", "social_country_year")`. The
     canonical `"World Bank API v2; cached indicator
     responses"` version propagates consistently to
     `RawAsset.version` and every emitted
     `NormalizedObservation.source_version`. The adapter is
     **offline / cache-first by default and offline-only in
     this slice**: for `cache_policy="offline_only"` /
     `"prefer_cache"` with explicit `years=`, missing or
     incomplete cache fails readiness with a structured
     `network_cache_unavailable` / `missing_raw` error before
     `read_raw` / `transform` are called (per
     `docs/requirements/sources.md` §11 SRC-TYPE-002 -- API
     sources use cache policy). `cache_policy="refresh"` /
     `"no_cache"` is NOT supported by the unified WDI
     adapter in this slice: it fails readiness with a
     structured `unsupported_cache_policy` error because
     `WDIAdapter.read_raw` never invokes the network
     regardless of the request's `cache_policy` -- the unified
     adapter uses a local cache-only read path
     (`_read_cached_wdi_responses` in `_transform.py`,
     `_enumerate_cache_files` in `_readiness.py`) that reads
     the staged per-(year, indicator) JSON cache files directly
     and mirrors the legacy
     `leaders_db.ingest.wdi_http.parse_wdi_payload` /
     `leaders_db.ingest.wdi_io.read_wdi` long-to-wide pivot
     just enough for the cache-only contract. For `years=None`
     the readiness gate enumerates the cache root and refuses
     to dispatch if any discovered cache file is malformed
     (would force the legacy read_wdi fallback into HTTP);
     for explicit `years=` the gate refuses missing /
     incomplete / corrupt cache BEFORE `read_raw` /
     `transform` are called (per the comprehensive cache-policy
     remediation that addresses the second reviewer pass on the
     same no-network contract). The bundle
     metadata's `checksum_sha256` is REQUIRED and accepts
     three shapes: (a) `null` paired with a non-empty
     `checksum_note` mentioning the API / cache /
     per-response / checksum contract (canonical WDI
     shape); (b) a 64-character hex SHA-256 string
     (flat-bundle); (c) a per-file dict mapping file
     names to 64-character hex SHA-256 strings. Missing
     `checksum_sha256`, `null` without an actionable
     `checksum_note`, or a non-null shape that does not
     validate all fail readiness with a structured
     `missing_metadata` error. Per-observation
     `RawLocator` carries the cache file path +
     `api_endpoint` template + `json_pointer` so downstream
     audit code can resolve the canonical WDI v2 URL for
     each (year, indicator, country) row; the pointer is
     `"/1/<numeric_index>"` (the data list under
     `payload[1]` is indexed numerically in the WDI v2
     response), computed by the
     `load_wdi_cache_index` helper in
     `_transform.py` so audit code can re-parse the
     cache file and recover the matching record
     byte-for-byte. Per-row `extension` fields carry the
     raw WDI indicator code (`wdi_raw_indicator_code`),
     the cache year, and the canonical attribution text
     (Rule #15). The runner still returns `manifest=None`;
     no persistence, DB writes, or manifest writing
     landed. The package exposes explicit
     `create_world_bank_wdi_adapter()` /
     `register_world_bank_wdi(registry)` factories and
     does NOT auto-register on import (§10.1).
 7. **CLI transition.** Add `leaders-db sources ...` commands and begin retiring
    `STAGE2_ADAPTERS`.

---

## 10. Phase A Boundary and Phase B Test Plan

This section defines the proof surface for the initial importable stubs under
`src/leaders_db/sources/`. Phase A intentionally adds contracts and seams only;
it does not register real sources, migrate PWT, add CLI commands, persist files,
or call legacy ingestion.

### 10.1 Phase A decisions

- `leaders_db.sources` is a clean package boundary. Its package import exports
  contracts, registry, runner, and query interfaces, but does not import
  `leaders_db.ingest`.
- Legacy access remains available through the existing `leaders_db.ingest`
  modules and CLI paths. The optional `leaders_db.sources.legacy` seam may import
  legacy code lazily only inside explicit helper calls.
- The new registry starts empty. It may list/register/get descriptors and
  adapters for tests or future composition, but it does not auto-register legacy
  adapters or the reference PWT experiment.
- The registry contract requires `register` to reject a duplicate
  `SourceId.slug` with `ValueError` (see `SRC-REG-004` in
  [`../requirements/sources.md`](../requirements/sources.md) §9). The
  `InMemorySourceRegistry.register` implementation now satisfies this
  contract; the Phase B contract test
  `tests/sources/test_registry.py::test_register_rejects_duplicate_slug_with_value_error`
  passes.
- The `SourceIngestRunner` is no longer a `NotImplementedError` stub. It
  is constructed with a `SourceRegistry` and exposes it as
  `runner.registry`; `run(request)` drives the documented
  `check_ready -> read_raw -> transform` lifecycle and returns a real
  `SourceIngestResult`. The runner never touches the legacy
  `STAGE2_ADAPTERS` table. Shared validation, persistence, and manifest
  generation are intentionally deferred to a later phase — the runner
  surfaces the adapter-produced `ReadinessResult`, materialised
  `NormalizedObservation` tuple, and a convenience `ValidationResult`
  without writing files or DB rows.

### 10.2 Phase B tests and proof surfaces

| Requirement IDs | Proof surface | Planned failing test before implementation |
|---|---|---|
| SRC-SCOPE-003, SRC-MIG-003, SRC-MIG-007, SRC-TEST-009 | Unit / import boundary | Import `leaders_db.sources` in a fresh interpreter after installing an import hook or checking `sys.modules`; assert no `leaders_db.ingest` module appears as a side effect. |
| SRC-SCOPE-004, SRC-MIG-002, SRC-MIG-008, SRC-TEST-009 | Package integration / legacy compatibility | Import `leaders_db.ingest` and inspect `STAGE2_ADAPTERS`; assert existing keys remain available and legacy import still succeeds after importing `leaders_db.sources`. |
| SRC-MIG-008 | Unit / lazy seam | Import `leaders_db.sources.legacy` alone and assert it does not import `leaders_db.ingest`; then call the explicit legacy adapter helper and assert the lazy boundary returns the legacy mapping. |
| SRC-ID-001 through SRC-ID-004, SRC-REG-001, SRC-REG-002, SRC-REG-004 | Unit / registry contract | Register a fake adapter with a `SourceDescriptor`; assert `list_descriptors`, `get_descriptor`, and `get_adapter` return by `SourceId` and unknown ids raise `KeyError`. Per `SRC-REG-004`, a duplicate-slug registration must raise `ValueError` (this test is PASS-ELIGIBLE — `InMemorySourceRegistry.register` now rejects duplicates). |
| SRC-REG-003, SRC-LIFE-007, SRC-TEST-010 | Unit / dispatch seam | Construct `SourceIngestRunner(registry=...)`; assert it exposes the registry seam (`runner.registry` is identity-equal to the constructor argument) and that `run(request)` drives the adapter through `check_ready -> read_raw -> transform` in that exact order while never calling into `leaders_db.ingest.STAGE2_ADAPTERS`. The lifecycle and no-legacy-dispatch tests are PASS-ELIGIBLE — the runner is wired. |
| SRC-REQ-001 through SRC-REQ-009 | Unit / contract shape | Instantiate `SourceIngestRequest`; assert it includes source id, year/country/leader filters, roots, DB URL/session, source version, run id, `dry_run`, `overwrite`, `cache_policy`, and output formats; assert `years=None` is preserved as all-years semantics. |
| SRC-LIFE-001 through SRC-LIFE-007 | Unit / protocol shape | Type/duck-test a fake adapter against `SourceAdapter`; assert required methods are `check_ready`, `read_raw`, and `transform`, and shared runner remains responsible for validate/persist/manifest. |
| SRC-OBS-001 through SRC-OBS-007, SRC-PROV-001 through SRC-PROV-005 | Unit / model contract | Instantiate `NormalizedObservation`, `RawAsset`, `RawLocator`, `TransformLocator`, `SourceAttribution`, and `SourceManifest`; assert provenance, warning, quality-flag, attribution, source-version, and extension fields are present. |
| SRC-COV-001 through SRC-COV-005 | Unit / descriptor and warning contract | Instantiate `CoverageHint` and structured `SourceWarning` values for out-of-coverage and missingness codes; assert warnings can carry source id, severity, and machine-readable context. |
| SRC-PERSIST-001 through SRC-PERSIST-007 | Unit / stub safety now; package integration later | Assert Phase A has no persistence implementation and no file/DB mutation path. Later adapter contract tests must add filesystem + SQLite boundary proof for a fixture source. |
| SRC-QUERY-001 through SRC-QUERY-005 | Unit / query interface | Assert `EvidenceQuery` contains source/family/indicator/year/country/leader filters plus include flags; assert an `EvidenceRepository` fake can implement read-only query methods without invoking ingestion. |
| SRC-DEFAULT-001 through SRC-DEFAULT-007 | Package integration / static inspection | Assert package name is `leaders_db.sources`, default request output format is parquet, default cache policy is `prefer_cache`, no real adapter is registered by default, and `client_existing` is not auto-registered as evidence. |

Question check: could code pass these tests while failing in real use? For Phase
A, yes if only unit tests are written. Therefore Phase B must include the import
boundary and legacy compatibility package-integration checks above, and the first
real adapter phase must add filesystem/SQLite manifest proof before claiming the
source system works end to end.
