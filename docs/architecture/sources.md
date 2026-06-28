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
├── query.py              # EvidenceRepository Protocol + InMemoryEvidenceRepository
├── concepts.py           # semantic concept catalog over observations
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
    def __init__(self, registry: SourceRegistry, *, engine: Engine | None = None) -> None: ...

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
transform -> validate`. SQL persistence and manifest writing are opt-in via the
constructor `engine`; the default `SourceIngestRunner(registry)` path remains
side-effect free and returns `manifest=None`, while `SourceIngestRunner(registry,
engine=...)` persists valid observations idempotently and writes processed
artifacts plus a deterministic manifest under
`processed_root/<source>/manifest-<run_id>.json`.

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

The first concrete repository implementation is
`InMemoryEvidenceRepository` (also in `src/leaders_db/sources/query.py`,
re-exported from the `leaders_db.sources` package root). It is the canonical
read-only, deterministic, no-I/O seam for downstream consumers in this slice:

- The constructor accepts three sequences -- `observations`,
  `manifests`, and `attributions` -- and copies each into an internal
  tuple so the caller-owned lists are never mutated.
- `query_observations(query)` filters the stored observations by every
  documented filter (`source_ids`, `observation_families`,
  `indicator_codes`, `years`, `countries`, `leaders`) and preserves the
  input observation order in the result. A `None` filter value means
  "unfiltered"; an empty tuple `()` is a deliberate filter that returns
  no observations for that dimension (natural membership semantics).
  `source_ids` match against the stored `SourceId.slug`; `leaders`
  match against either `leader_id` or `leader_name` so callers can
  query by either dimension until leader IDs are stable.
- `get_manifest(source_id, run_id=None)` returns the matching manifest.
  If `run_id` is provided, it is the exact `(slug, run_id)` lookup. If
  `run_id` is `None` and exactly one manifest is stored for the source,
  that manifest is returned. If multiple manifests exist for the same
  source and `run_id` is `None`, the call raises `KeyError` with an
  actionable message naming the source slug and the available run ids
  so the caller can pass an explicit run id instead of guessing. A
  missing manifest raises `KeyError` naming the source slug and the
  known run ids.
- `get_attributions(source_ids)` returns attributions in the order of
  the requested `source_ids` argument; sources without a stored
  attribution are silently skipped (matching the documented
  contract for the prior `_FakeEvidenceRepository` test fake).

The repository never imports `leaders_db.ingest`, never instantiates
`SourceIngestRunner`, never calls source adapters, and never reads raw
files. It is intended for tests, research scripts, and concept-extraction
flows that already hold materialized observation / manifest /
attribution records in memory. Future repository implementations
(e.g., a SQLite- or processed-parquet-backed reader) will live alongside
this one and implement the same `EvidenceRepository` Protocol without
breaking existing callers.

The five `EvidenceQuery.include_*` flags (`include_raw_locators`,
`include_warnings`, `include_quality_flags`, `include_attribution`,
`include_manifests`) are currently **advisory** in the in-memory
implementation: the repository always returns the full stored
observation including its locators, warnings, quality flags, and any
attached metadata. The flags exist on the contract so a future
materialization step can honor them without changing the
`EvidenceRepository` surface; future persistence-backed repositories
may strip the optional fields when a caller asks for lighter rows.
Tests and docs must not assume that the flags actually mutate the
returned rows in this slice.

### 5.8 Semantic concept catalog

The source system also exposes a small semantic indicator concept layer in
`leaders_db.sources.concepts`. It sits above `NormalizedObservation` and below
scoring/research code. Its purpose is to let analysts and scorers ask for stable
cross-source concepts such as `gdp_per_capita`, `population`, or `gdp_total`
without memorizing source-specific indicator strings such as
`wdi_gdp_per_capita_ppp_constant_2017` or
`maddison_project_gdp_per_capita_2011_intl`.

Concepts do **not** replace adapter indicator codes. Source-specific
`NormalizedObservation.indicator_code` values remain preserved for audit,
provenance, cataloging, and source-specific analysis. A concept is an alias or a
recipe over existing normalized observations; it is not a new evidence source and
must not count independently for source agreement.

Minimal public API sketch:

```python
def list_concepts() -> Sequence[ConceptDescriptor]: ...

def resolve_concept(
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> Sequence[ConceptMapping]: ...

def extract_concept(
    observations: Sequence[NormalizedObservation],
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> Sequence[ConceptObservation]: ...

def extract_concept_result(
    observations: Sequence[NormalizedObservation],
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> ConceptExtractionResult: ...
```

`resolve_concept` returns the source-specific direct mappings and derivation
recipes for a stable key. `extract_concept` works over already-loaded
`NormalizedObservation` records, typically from `EvidenceRepository`; it does
not read raw files, rerun ingestion, write processed files, or mutate source
records.

`extract_concept_result` is the diagnostic helper that returns a
`ConceptExtractionResult` dataclass with two tuple fields -- `observations`
(same shape as `extract_concept`) plus `warnings` (a tuple of
`SourceWarning` records aggregating every per-row direct-mapping diagnostic
AND every per-scope derived-mapping drop reason). The convenience
`extract_concept` wrapper returns only the observations tuple so the minimal
public API stays flat; callers that need structured diagnostics for
missing / ambiguous / non-numeric / zero / missing-source-version /
mismatched-year inputs use `extract_concept_result`.

Concept mappings may be direct aliases, for example:

- `gdp_per_capita` from WDI GDP-per-capita indicators.
- `gdp_per_capita` from Maddison Project `gdppc`-derived observations.
- `population` from WDI or Maddison population observations.

Concept mappings may also be simple derivation recipes when all inputs are
already normalized observations from the same source/entity/year. For example,
PWT may expose:

```text
gdp_per_capita = pwt_real_gdp_output_side / pwt_population
```

Derived concept outputs must carry provenance to every input observation id and
locator, preserve the source id and source version, and include an explicit
quality flag / derivation marker such as `derived_concept` plus the recipe key.
If any required input is missing, non-numeric, zero where division would be
undefined, ambiguous for the requested (source_id, country, year, leader)
scope, or carrying a missing / mismatched `source_version` stamp, extraction
returns no derived concept row for that scope and surfaces a structured
`SourceWarning` via the diagnostic helper. The derivation scope key
includes `year` so a single country with valid 2018 AND 2019 inputs produces
two distinct scopes (one derived row per country-year) rather than collapsing
into one ambiguous multi-year bucket; `source_version` is intentionally
checked inside the scope once both sides are paired so mismatched versions
still surface the missing-source-version diagnostic.

The diagnostic helper uses stable per-failure-mode warning codes (e.g.
`concept_missing_numerator`, `concept_missing_denominator`,
`concept_ambiguous_pair`, `concept_non_numeric_numerator`,
`concept_non_numeric_denominator`, `concept_zero_denominator`,
`concept_missing_source_version`, `concept_pair_year_mismatch`) so callers
can branch on actionable codes rather than parsing message strings.

This layer is query/analysis-time normalization only. It does not mutate source
ingestion output, does not persist a new canonical observation table yet, and
does not introduce CLI commands in the current slice.

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

| Source slug | Current prototype status | New-interface target role | Suggested migration priority | Clean-interface adapter status |
|---|---|---|---|---|
| `pwt` | implemented in prototype shared-adapter experiment | economic country-year observations | 1 | migrated |
| `maddison_project` | implemented | historical economic country-year observations | 2 | migrated |
| `world_bank_wdi` | implemented | WDI API/cache country-year indicators | 3 | migrated |
| `world_bank_wgi` | implemented | WGI governance country-year indicators | 4 | migrated |
| `vdem` | implemented | large political/social country-year indicators | 5 | migrated |
| `transparency_cpi` | implemented | corruption/integrity country-year indicators | 6 | migrated |
| `rsf_press_freedom` | implemented | press-freedom country-year indicators | 7 | migrated |
| `bti` | implemented | governance / democracy / transformation indicators | 8 | migrated |
| `archigos` | implemented | leader identity and tenure | 9 | migrated |
| `reign` | implemented | leader identity, regime, tenure | 10 | migrated |
| `ucdp` | implemented | conflict and violence observations | 11 | migrated |
| `sipri_milex` | implemented | military-expenditure observations | 12 | migrated |
| `sipri_yearbook_ch7` | implemented | nuclear-force observations | 13 | migrated |
| `pts` | implemented | political terror / repression indicators | 14 | migrated |
| `cirights` | implemented | human-rights indicators | 15 | migrated |
| `undp_hdi` | implemented | HDI/social well-being indicators | 16 | migrated |
| `who_gho_api` | implemented | health API/cache indicators | 17 | migrated |
| `fas` | implemented | nuclear-force document/API-style observations | 18 | migrated |
| `wikidata_heads_of_state_government` | implemented | knowledge-base leader identity observations | 19 | migrated |
| `wikipedia_search_extract` | implemented | cached web/knowledge snippets | 20 | migrated |

### 7.2 Pending or blocked sources to implement only in the new interface

| Source slug | Current status | New-interface notes |
|---|---|---|
| `polity_v` | implemented (2026-06-27) | first post-interface source from "databases not yet in legacy"; lives at `src/leaders_db/sources/adapters/polity_v/`; reads `p5v2018.sav` via `pyreadstat.read_sav`; canonical 1800-2018 coverage hint; single `political_freedom_country_year` family; documented special codes -66 / -77 / -88 are NOT coerced to numeric; runtime-local `metadata.json` is gitignored per Always-On Rule #9 (see §7.18 entry for the migration notes) |
| `leader_survival` | blocked on Demscore manual gate | manual-gated source readiness proof |
| `imf_weo` | blocked by access challenge | user-managed or future manual/API path |
| `cow_mid` | blocked/deferred | conflict source if raw access is resolved |
| `nti` | blocked/user-managed | nuclear/manual document source |
| `sipri_arms_transfers` | implemented (2026-06-27) | offline / cache-only arms-transfer register + per-`(role, country, year)` aggregates; no live fetch in this slice |
| `iaea_safeguards` | implemented (2026-06-27) | nuclear safeguards legal / status evidence; offline / cache-only; see §7.20 detailed note |
| `iaea_additional_protocol_status` | future | nuclear treaty/status evidence -- subsumed by `iaea_safeguards`; see §7.21 |
| `unoda_treaties` | future | treaty posture evidence |
| `ctbto_treaty_status` | implemented (2026-06-28) | CTBT signature / ratification status evidence; offline / cache-only; see §7.21 detailed note |
| `world_bank_poverty_inequality_platform` | implemented (2026-06-28) | poverty / inequality / distribution observations; offline / cache-only; see §7.22 detailed note |
| `ctbto_nuclear_tests` | future | nuclear-test observations |
| `csis_missile_threat` | future | missile capability observations |
| `cns_nti_missile_launches` | future | missile-launch observations |
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
| `political_terror_scale` | documented source key for PTS (disk-folder alias only) | reconciled: canonical clean-interface slug is `pts`; the on-disk folder name `political_terror_scale/` is preserved as the human-readable bundle alias. The clean adapter lives at `leaders_db.sources.adapters.pts` with `source_id.slug == "pts"` and `descriptor.attribution_key == "pts"`; the bundle dir resolver maps `request.raw_root + "political_terror_scale/"`. This is the same pattern as the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / Transparency International CPI clean migrations where the dispatch key is short but the disk folder is human-readable. |
| `world_bank_wdi_social` | WDI health / education / inequality subset | represent as observation family / catalog subset under `world_bank_wdi`, not a separate raw adapter |
| `vdem_governance` | V-Dem governance sub-indicators | represent as observation family / catalog subset under `vdem`, not a separate raw adapter |
| `world_bank_wgi_corruption` | WGI Control of Corruption subset | represent as observation family / catalog subset under `world_bank_wgi`, not a separate raw adapter |
| `vdem_corruption` | V-Dem corruption variables | represent as observation family / catalog subset under `vdem`, not a separate raw adapter |

### 7.6 RSF World Press Freedom Index (clean migration)

`rsf_press_freedom` is the ninth source rebuilt under
the clean `leaders_db.sources` interface
(§7.1 priority 7, [`docs/requirements/sources.md`](../requirements/sources.md) §12
SRC-MIG-006), after PWT 10.01, Maddison Project Database
2023, World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, and Political Terror
Scale. The unified adapter lives at
`leaders_db.sources.adapters.rsf_press_freedom` with
`source_id.slug == "rsf_press_freedom"` and
`descriptor.attribution_key == "rsf_press_freedom"`.

Unlike the prior clean-source migrations, RSF is
**the first source with multiple local annual input
files** (24 annual CSVs covering 2002-2010 +
2012-2026; the direct `2011.csv` is intentionally
absent). The unified adapter's
`read_raw` call reads each per-year file
independently rather than concatenating them into
one wide CSV, preserves the canonical
semicolon-delimited + comma-decimal-separator
parsing, and surfaces the BOM-first / cp1252-fallback
encoding detection via the legacy reader
(`leaders_db.ingest.rsf_press_freedom_csv`).

**Documented 2011 missing / direct-CSV caveat.**
The direct `2011.csv` is absent; RSF's combined
2011/2012 edition is represented by the 2012 file
(its `Year (N)` column reads `"2011-12"`). Year=2011
requests fail readiness with a structured
`rsf_year_2011_absent` warning (NOT a generic
`year_absent` so the operator can distinguish the
documented 2011 caveat from a generic
out-of-coverage year). The runner short-circuits
with `RuntimeError` BEFORE `read_raw` /
`transform`; downstream code should request the
2012 file (`years=(2012,)`) for 2011-related
data and MUST NOT silently proxy 2011 -> 2012 (no
stale-proxy fill per SRC-COV-002 / SRC-COV-003).

**Pre/post-2022 methodology / schema
distinction.** Pre-2022 files (2002-2021) use a
16-col wide format with score + rank only; the 5
component-context indicators
(`rsf_press_freedom_political_context` /
`rsf_press_freedom_economic_context` /
`rsf_press_freedom_legal_context` /
`rsf_press_freedom_social_context` /
`rsf_press_freedom_safety`) are NOT emitted for
these years because the actual columns are
absent in the legacy CSV. Post-2022 files
(2022+) use a 22-26 col wide format with score +
rank + 5 component-context columns; all 7 catalog
indicators are emitted for these years. The
pre/post-2022 methodology/schema distinction is
preserved on every observation via the
`extension["rsf_schema_group"]` field (1 =
pre-2022; 2+ = post-2022). The unified transform
does NOT silently merge pre/post-2022 methodology
-- the raw cell text is preserved verbatim on
`extension["raw_value"]` and the
`rsf_schema_group` flag tells downstream code
which methodology applied. The 2022 file
carries 181 blank separator rows between data
rows that the legacy reader drops; the unified
transform emits zero observations for the
separator rows (no fabricated observations).

**Press/media-freedom sub-signal.** Per
`docs/sources/vetting/report.md` §3.2, RSF is
explicitly NOT a full political-freedom
replacement -- it is a press/media-freedom
sub-signal for the `political_freedom` rating
category, complementing V-Dem / Polity V /
Freedom House. The descriptor advertises
`source_type="dataset"`,
`requires_network=False`, and the single
observation family
`political_freedom_country_year`.

### 7.7 Bertelsmann Transformation Index / BTI (clean migration)

`bti` is the tenth source rebuilt under the clean
`leaders_db.sources` interface (§7.1 priority 8,
[`docs/requirements/sources.md`](../requirements/sources.md) §12
SRC-MIG-006), after PWT 10.01, Maddison Project Database
2023, World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, Political Terror
Scale, and Reporters Without Borders (RSF). The
unified adapter lives at
`leaders_db.sources.adapters.bti` with
`source_id.slug == "bti"` and
`descriptor.attribution_key == "bti"`.

The BTI cumulative xlsx is structurally close to
WGI / V-Dem / PTS: a single local file, no HTTP
layer. The canonical bundle is
`data/raw/bti/BTI_2006-2026_Scores.xlsx` (12
edition sheets: one BTI edition per sheet from
`BTI 2006_old` through `BTI 2026`; 137-159
countries per edition; 123 columns) plus
`BTI2026_Codebook.pdf` and `metadata.json`. The
unified adapter is local-file only
(`requires_network=False`); the runner NEVER
invokes the network.

**Biennial sheet/year mapping.** BTI is
biennial: each edition covers the ~2-year period
preceding publication (BTI 2024 covers 2022-2023;
BTI 2026 covers 2024-2025). For the prototype
target year 2023, the canonical mapping resolves
to the `BTI 2024` sheet (covers 2022-2023). The
per-edition covered interval map
(`_BTI_EDITION_COVERED_INTERVAL` in
`src/leaders_db/ingest/bti_io.py`) and the
`sheet_for_year` resolver drive explicit
`years=` sheet selection at read time. The
unified raw-read path reads every requested
in-coverage BTI sheet, and `years=None` reads
every available BTI sheet in the staged workbook.
The transform layer then narrows the wide frame
to the requested year(s). The resolved sheet name + covered
interval are carried on every observation's
`extension` (`bti_sheet_name` / `bti_target_year`)
so downstream Stage 5 score modules can apply
the proxy / source-edition semantics without
re-reading the parquet metadata.

**12 catalog indicators across 3 observation
families.** The canonical BTI catalog at
`src/leaders_db/ingest/catalogs/bti.csv` lists 12
indicator rows across 3 rating categories:

- `effectiveness_country_year` (2 indicators):
  `bti_governance_index` +
  `bti_governance_performance`.
- `political_freedom_country_year` (7 indicators):
  `bti_status_index` + `bti_democracy_status` +
  Q1-Q5 political transformation questions.
- `economic_wellbeing_country_year` (3 indicators):
  Q6/Q7/Q11 economic transformation questions.

The descriptor advertises all three observation
families so downstream query code can filter by
family without consulting the per-source catalog.

**Governance / effectiveness primary signal.**
Per `docs/sources/registry.md` §1 +
`docs/sources/attributions.md` § `bti`, BTI is
the canonical governance / effectiveness source
for the prototype, complementing V-Dem
(broader democracy indicators) and World Bank
WGI (quantitative governance estimates). BTI is
NOT a full political-freedom replacement (the
`political_freedom_country_year` family is one
of three observation families BTI emits, not a
full replacement for the political-freedom
category). The Stage 5 `political_freedom`
scorer's BTI group weight is 0.30 (per
`_political_freedom_rubric.py`); the BTI
contribution to a country-year political-freedom
score is a 0.30-weighted average of the 7
political-freedom indicators.

**Direction hint.** All 12 indicators share
`raw_scale="1-10"` with `10 = best`
(`higher_is_better=True`); the raw 1-10 value is
preserved verbatim on the observation's
`normalized_value` (no inversion needed).

**Attribution.** The unified `BTI_ATTRIBUTION_TEXT`
constant is byte-identical to the legacy
`BTI_ATTRIBUTION` constant in
`src/leaders_db/ingest/bti_io.py` (the short
form `"BTI 2026 (Bertelsmann Stiftung 2026)."`)
and to the `Attribution text in reports` line in
the `bti` section of
`docs/sources/attributions.md` (Always-On Rule
#15). The
`test_bti_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity.

### 7.8 Freedom House Freedom in the World / FIW (clean migration)

`freedom_house` is implemented under the clean
`leaders_db.sources` interface at
`src/leaders_db/sources/adapters/freedom_house/`.
The adapter is local-file only (`requires_network=False`)
and uses the user-managed FIW 2026 bundle staged at
`data/raw/freedom_house/` without modifying or publishing
the raw workbooks.

The first FIW clean adapter intentionally uses the core
ratings/statuses workbook only:
`Country_and_Territory_Ratings_and_Statuses_FIW_1973-2026.xlsx`.
It reads the country and territory ratings sheets and emits
three `political_freedom_country_year` indicators per
nonblank country/territory survey edition: political rights,
civil liberties, and Freedom House status. The aggregate and
all-data FIW 2026 workbooks remain staged for later expansion,
but are not required by this adapter path.

Readiness requires `metadata.json`, requires the canonical
2026 ratings/statuses workbook to appear in
`metadata.local_files` and on disk, validates the per-file
SHA-256 from `metadata.checksum_sha256` when present, rejects
unsupported request versions, warns on out-of-coverage years,
and warns that leader filters are ignored for this
country/territory-year source. Requests with `years=None`
read all survey editions available in the workbook; multi-year
requests emit every requested in-coverage year.

Each observation preserves the source-native country or
territory name without inventing ISO3, carries the workbook
sheet, row number, raw column, survey edition year, raw value,
and year(s)-under-review in provenance extension fields, and
includes the normative Freedom House attribution text from
`docs/sources/attributions.md`.

### 7.9 Archigos v4.1 (clean migration)

`archigos` is implemented under the clean `leaders_db.sources`
interface at `src/leaders_db/sources/adapters/archigos/` with
`source_id.slug == "archigos"` and
`descriptor.attribution_key == "archigos"`. The adapter is
local-file only (`requires_network=False`) and reads the staged
Stata 14 bundle at `data/raw/archigos/Archigos_4.1_stata14.dta`.
It reuses the legacy Archigos catalog and Stata parser only through
lazy imports inside the raw-read function, so importing the clean
adapter does not import `leaders_db.ingest`.

Archigos is leader-spell data, not country-year data. The clean
adapter preserves that unit: it emits one `leader_identity_spell`
observation per leader-spell identity field and keys each observation
by the spell start year. It does not expand spells to every covered
year and does not fabricate 2023 rows. Requests with `years=None`
read every available spell start year in the staged file; multi-year
requests emit all requested in-coverage start years; out-of-coverage
years such as 2023 surface `year_absent` warnings and emit zero rows.

Readiness requires `metadata.json`, requires the canonical `.dta` file
to appear in `metadata.local_files` and on disk, validates
`source_version="v4.1 (Stata 14)"`, rejects unsupported request
versions, and verifies `metadata.checksum_sha256["Archigos_4.1_stata14.dta"]`
when present. `leaders=` filters warn and are ignored. `countries=`
filters are applied only to source-native Archigos identifiers (`idacr`
and `ccode`); the adapter does not invent ISO3 country codes.

Each observation carries the raw filename, source row reference
(`archigos:<obsid>:<year>:<raw_column>`), `obsid`, `idacr`, `ccode`,
raw column, raw value, legacy normalized value, catalog scale/unit,
direction hint, and normative Archigos attribution text. `country_code`
and `leader_id` remain `None` until Stage 3/4 canonical mapping exists.

### 7.10 REIGN 2021-8 (clean migration)

REIGN 2021-8 is migrated under `src/leaders_db/sources/adapters/reign/` as a
local-file-only clean adapter. The adapter reads the staged
`data/raw/reign/REIGN_2021_8.csv` through lazy legacy parser imports, validates
`metadata.json`, `local_files`, optional SHA-256 metadata, and the canonical
version string `2021-8 (August 2021 release, final)`, then emits
`leader_identity_month` observations for the eight legacy catalog variables.

REIGN remains leader-month evidence, not country-year evidence. The clean
adapter preserves source-native `country`, `ccode`, `year`, `month`, leader name,
raw column, raw value, legacy normalized value, `source_row_reference`, and the
normative REIGN attribution text; it does not invent ISO3, `leader_id`, 2023
rows, leader-year rollups, or month expansions. Requests outside 1950-2021 warn
and emit zero rows. `leaders=` warns and is ignored; `countries=` filters only on
source-native country display token or COW `ccode`.

### 7.11 SIPRI Military Expenditure Database (clean migration)

SIPRI Milex is migrated under `src/leaders_db/sources/adapters/sipri_milex/`
as a local-file-only clean adapter. It reads the staged
`data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx` through lazy legacy
catalog/parser imports, so importing the clean adapter does not import
`leaders_db.ingest`. Readiness requires `metadata.json`, requires the canonical
xlsx to appear in `metadata.local_files` and on disk, validates the optional
per-file SHA-256 checksum, rejects unsupported request versions, warns on
out-of-coverage years, and warns that leader filters are ignored for this
country-year source.

The adapter emits `international_peace_country_year` observations for the four
legacy catalog variables: `sipri_milex_share_of_gdp`,
`sipri_milex_per_capita`, `sipri_milex_constant_usd`, and
`sipri_milex_share_of_govt_spending`. Requests with `years=None` read all years
available in the workbook; multi-year requests emit all requested in-coverage
years. Missing cells (`...`, `xxx`, empty/coerced NaN) are skipped rather than
fabricated.

Each observation preserves source-native country display name, year, indicator
sheet, raw filename, raw value, normalized float, source row reference
(`sipri_milex:<display_name>`), region-filter audit metadata from the legacy
reader, and the normative SIPRI attribution text. The adapter does not invent
ISO3 country codes or leader identifiers; `country_code`, `leader_id`, and
`leader_name` remain `None` until later matching/resolution stages.

### 7.12 SIPRI Yearbook Chapter 7 (clean migration)

SIPRI Yearbook Ch.7 is migrated under
`src/leaders_db/sources/adapters/sipri_yearbook_ch7/` as a local-file-only clean
adapter. It reads the runtime-local staged
`data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf` through lazy legacy catalog/PDF
parser imports, so importing the clean adapter does not import
`leaders_db.ingest`. Readiness requires a runtime-local `metadata.json`,
requires the canonical PDF filename to appear in `metadata.local_files` and on
disk, validates the optional per-file SHA-256 checksum when present, rejects
unsupported request/source metadata versions, warns on out-of-snapshot years,
and warns that leader filters are ignored for this country-year document source.

The adapter emits `nuclear_country_year` observations for the three legacy
catalog variables: `sipri_yearbook_ch7_nuclear_warheads_total_inventory`,
`sipri_yearbook_ch7_nuclear_warheads_deployed`, and
`sipri_yearbook_ch7_nuclear_warheads_retired`. Requests with `years=None` read
the PDF snapshot year; multi-year requests emit the in-snapshot year and warn for
out-of-snapshot years. `countries=` filters match source-native SIPRI display
names only.

Each observation preserves source-native country display name, snapshot year,
PDF filename/page, raw catalog column, raw PDF cell text, normalized integer or
`None`, source row reference (`sipri_yearbook_ch7:<display_name>`),
`pdf_pages_total`, `snapshot_year`, and the normative SIPRI Yearbook
attribution text. The adapter does not invent ISO3 country codes or leader
identifiers; `country_code`, `leader_id`, and `leader_name` remain `None` until
later matching/resolution stages. Raw metadata is not committed with the source;
it is a local runtime requirement beside the user-staged PDF.

### 7.13 CIRIGHTS (clean migration)

CIRIGHTS is migrated under `src/leaders_db/sources/adapters/cirights/` as a
local-file-only clean adapter. It reads the runtime-local staged
`data/raw/cirights/cirights_v3.12.10.24.xlsx` through lazy legacy catalog/xlsx
parser imports, so importing the clean adapter does not import
`leaders_db.ingest`. Readiness requires a runtime-local `metadata.json`, requires
the canonical xlsx filename to appear in `metadata.local_files` and on disk,
validates `source_version="v3.12.10.24 (data), v2.8.27.23 (codebook)"`, tolerates
extra local files/checksums, validates the optional per-file xlsx SHA-256 when
present, rejects unsupported request/source metadata versions, warns on
out-of-coverage years, and warns that leader filters are ignored for this
country-year source.

The adapter emits `domestic_violence_human_rights_country_year` observations for
the seven legacy catalog variables: `cirights_physint`, `cirights_repression`,
`cirights_civpol`, `cirights_disap`, `cirights_kill`, `cirights_polpris`, and
`cirights_tort`. Requests with `years=None` read all available workbook years;
in-coverage multi-year requests emit all requested years. A requested 2023 is
accepted with a warning and maps to the 2022 data year; observations remain
labeled as `year=2022`. If both 2022 and 2023 are requested, the clean adapter
emits one 2022 observation set rather than duplicate proxy rows.

Each observation preserves source-native country display name, actual data year,
raw workbook/sheet/column locator, raw value, normalized numeric value,
`source_row_reference` (`cirights:<safe_country_token>:<year>:<raw_column>`),
per-observation `year_window`, proxy audit metadata when applicable, and the
normative CIRIGHTS attribution text. The adapter skips missing indicator cells
instead of fabricating values, does not invent ISO3 country codes or leader
identifiers, and leaves `country_code`, `leader_id`, and `leader_name` as `None`
until later matching/resolution stages. Raw metadata is not committed with the
source; it is a gitignored local runtime requirement beside the user-staged
CIRIGHTS raw bundle.

### 7.14 UNDP HDI (clean migration)

UNDP HDI is migrated under `src/leaders_db/sources/adapters/undp_hdi/` as a
local-file-only clean adapter. It reads the runtime-local staged
`data/raw/undp_hdi/HDR23-24_Composite_indices_complete_time_series.csv` through
lazy legacy catalog/CSV/unpivot imports, so importing the clean adapter does not
import `leaders_db.ingest`. The adapter declares the
`social_wellbeing_country_year` family for country-year evidence from HDI, life
expectancy, schooling, and income indicators.

Readiness requires runtime-local `metadata.json` and the canonical CSV on disk.
It accepts the newer metadata shape (`source_version`, `local_files`, optional
`checksum_sha256`) and the existing legacy raw-local shape (`version`, matching
`source_key`, and top-level `sha256` without `local_files`). When `local_files`
is present, it must be a string list containing the canonical CSV. When either
checksum shape is present, the adapter validates the CSV SHA-256. The raw
metadata is not committed with the source; it remains a gitignored local runtime
file beside the user-staged CSV.

The adapter emits the five legacy catalog variables: `undp_hdi_hdi`,
`undp_hdi_life_expectancy`, `undp_hdi_expected_years_schooling`,
`undp_hdi_mean_years_schooling`, and `undp_hdi_gni_per_capita`. Requests with
`years=None` read all years available in the CSV. A requested 2023 is accepted
with a warning and maps to the 2022 data year; observations remain labeled as
`year=2022`. If both 2022 and 2023 are requested, the clean adapter emits one
2022 observation set rather than duplicate proxy rows. `countries=` matches ISO3
or the source-native country display name. `leaders=` warns and is ignored.

Each observation preserves ISO3 `country_code`, source-native country display,
actual data year, raw CSV path and `{raw_column}_{year}` column locator, raw
value, normalized numeric value, `source_row_reference` (`undp_hdi:<ISO3>`),
`region`, `hdicode`, proxy audit metadata when applicable, and the normative
UNDP attribution text. The adapter skips missing indicator cells instead of
fabricating values, does not invent leader identifiers, and leaves `leader_id`
and `leader_name` as `None`.

The WHO GHO API clean migration adds the source-specific
API/cache-backed country-year social-wellbeing contract on
top of the shared contract:

- the WHO GHO API adapter descriptor is registerable /
  listable through the `InMemorySourceRegistry` and exposes
  the canonical WHO GHO static metadata (source_id
  `who_gho_api`, default version `"GHO OData v1"`,
  attribution_key `who_gho_api`, `api` source type,
  1990-present coverage hint, single observation family
  `social_wellbeing_country_year`, WHO GHO OData v1 API
  homepage URL `https://ghoapi.azureedge.net/api/`,
  `requires_network=True`);
- `SourceIngestRunner.run(request)` drives WHO GHO API
  end-to-end through the new registry against the fixture
  cache under `tests/fixtures/who_gho_api/cache/{2019,2021}/`
  staged under a temporary `raw_root` with the runtime-local
  metadata shape and produces `NormalizedObservation` records
  (44 fixture observations across 2 years × 5 indicators ×
  5 countries, minus missing cells like MEX 2021 under-5
  mortality);
- the readiness gate accepts BOTH the canonical primary
  metadata shape (`source_version` / `source_url`) AND the
  existing raw-local legacy shape (`version` / `source_url` /
  `sha256: null`) so the staged
  `data/raw/who_gho_api/metadata.json` does not need to be
  rewritten as part of the migration;
- the runner does not consult legacy `STAGE2_ADAPTERS` even
  when the legacy `who_gho_api` slot is monkeypatched to a
  tracker; the unified read path is cache-only and NEVER
  invokes the network under supported cache policies
  (`offline_only` / `prefer_cache`);
- the unified adapter never invents values, ISO3, country
  names, leader IDs, missing rows, or proxy years: cells
  with null `NumericValue` are skipped; countries / years
  not present in the cache are skipped; `leader_id` /
  `leader_name` are always `None`;
- the cache-policy gate blocks `cache_policy="refresh"` /
  `"no_cache"` with a structured
  `unsupported_cache_policy` error BEFORE `read_raw` /
  `transform` are called -- the unified adapter never
  hits the network in this slice; HTTP sentinels installed
  on `leaders_db.ingest.who_gho_api_http.fetch_who_gho_api_payload`
  AND `requests.get` are never invoked by the supported
  cache policies;
- the per-observation `RawLocator` carries the cache file
  path + the per-`(year, IndicatorCode)` asset id +
  `column_name` (the WHO GHO API `IndicatorCode`) +
  `row_number=None` (the legacy long-to-wide pivot loses
  the API response row index); the audit-trail
  `extension.who_gho_api_raw_column` carries the same
  IndicatorCode so downstream audit code can resolve the
  per-observation source-native raw column without
  consulting the legacy catalog;
- the per-observation `extension` payload carries the
  canonical WHO GHO API attribution text (Rule #15), the
  `source_row_reference="who_gho_api:<raw_column>:<iso3>"`
  pattern (matching the legacy Stage 2 DB writer), the
  verbatim `Value` string (e.g. `"70.8 [70.7-71.1]"` with
  bounds) as the audit-trail `raw_value`, the
  `dim1_filter` (catalog `dim1_filter`, `SEX_BTSX` for
  SEX-disaggregated indicators, empty for
  immunization-only indicators), the
  `spatial_dim_type` (`COUNTRY` -- the parser filters
  non-country records at the parser level), and the
  `raw_scale` / `higher_is_better` /
  `normalized_scale_target` direction hints;
- the first-match-wins semantics of the legacy
  `pd.pivot_table(..., aggfunc="first")` are preserved
  across the long-to-wide transform: when the WHO GHO
  API returns multiple `COUNTRY` disaggregation records
  per `(iso3, year, indicator)` (e.g. WEALTHQUINTILE_WQ5
  + WEALTHQUINTILE_TOTL on `MDG_0000000007`), the unified
  transform emits ONE observation per triple -- the first
  record's value AND raw_value, not a silent
  last-record-wins flip;
- importing
  `leaders_db.sources.adapters.who_gho_api` does not
  import `leaders_db.ingest`; the legacy `STAGE2_ADAPTERS`
  dispatch slot for `who_gho_api` remains callable for
  backward compatibility.

### 7.15 FAS (Federation of American Scientists) Nuclear Notebook (clean migration)

`fas` is migrated under `src/leaders_db/sources/adapters/fas/` as
a local-file-only clean adapter. It reads the staged
`<raw_root>/fas/fas_status.html` (the consolidated FAS "Status
of World Nuclear Forces" HTML page snapshot) through lazy legacy
parser imports, so importing the clean adapter does NOT pull in
`leaders_db.ingest`.

Readiness requires a runtime-local `metadata.json`, validates
`source_version="consolidated status table"`, requires the
canonical `fas_status.html` to appear in `metadata.local_files`
when the field is present (the field is also accepted as absent
for backward compatibility), validates the optional per-file
SHA-256 `checksum_sha256` when supplied (accepting BOTH the
canonical flat-string shape `checksum_sha256 = "<64-hex>"` and
the per-file dict shape `{"fas_status.html": "<64-hex>"}`),
rejects unsupported request/source metadata versions, blocks
`cache_policy="refresh"` / `"no_cache"` with a structured
`unsupported_cache_policy` error, and warns on out-of-snapshot
years (FAS is a single-snapshot source so requesting a year
other than the snapshot year surfaces a `YEAR_ABSENT` warning per
SRC-COV-002 / SRC-COV-003 with no silent stale-proxy fill).

The adapter emits `nuclear_country_year` observations for the five
legacy catalog variables (`fas_operational_strategic`,
`fas_operational_nonstrategic`, `fas_reserve_nondeployed`,
`fas_military_stockpile`, `fas_total_inventory`). `years=None`
reads the snapshot year; an explicit `years=` request that
matches the snapshot year emits the snapshot rows with no
warning; a request that does NOT match the snapshot year still
emits the snapshot rows (no silent relabeling to the requested
year) AND tags every observation with `extension.requested_year`
+ `proxy_snapshot_semantics` audit metadata so downstream
audit code can detect the temporal-fit gap. `countries=` filters
match source-native FAS display names only (the FAS table does
NOT carry ISO3 codes; Stage 3 resolves ISO3 via
`country_aliases.csv` later); an ISO3 filter silently emits zero
rows. `leaders=` warns and is ignored.

Sentinel handling: `n.a.` and `?` cells are represented
consistently with the legacy DB writer semantics (the row IS
emitted with `value=None` / `value_type="missing"` AND the
audit `raw_value` preserves the sentinel literal); `<10` cells
map to the upper bound `10` with the raw literal `&lt;10`
preserved; numeric cells like `1,600` / `8,000` are coerced
correctly; the legacy parser strips `<sup>` footnote markers
before populating `_raw_value`, so the clean adapter's audit
`raw_value` is the post-strip legacy cell text, not the original
footnote-bearing HTML/text.

Each observation preserves source-native country display name
(no ISO3 invention), parsed snapshot year, raw column name, raw
value, normalized numeric value (or `None` for sentinels),
`source_row_reference` (`fas:<raw_column>:<country>`),
`url=FAS_STATUS_PAGE_URL`, `row_number=None` (the legacy wide
frame loses the HTML row index through the long-to-wide pivot),
`column_name=<raw_column>`, `snapshot_year`, `year_window`,
proxy audit metadata when applicable, and the normative FAS
attribution text `FAS Nuclear Notebook (Federation of American
Scientists).` The adapter does not invent ISO3 country codes or
leader identifiers; `country_code`, `leader_id`, and
`leader_name` remain `None` until later matching/resolution
stages. Raw metadata is not committed with the source; it is a
gitignored local runtime requirement beside the user-staged HTML
cache.

### 7.16 Wikidata WikiProject heads-of-state-and-government (clean migration)

`wikidata_heads_of_state_government` is migrated under
`src/leaders_db/sources/adapters/wikidata_heads_of_state_government/`
as a cache-only clean adapter. It reads the per-``(year,
country_qids)`` JSON cache recorded under
`<raw_root>/wikidata_heads_of_state_government/cache/`
through lazy legacy parser imports, so importing the clean
adapter does NOT pull in `leaders_db.ingest`.

Wikidata is the **always-on leader-identity helper** for the
prototype (per `docs/requirements/top-level-requirements.md`
§3 + §9 + §12). It is structurally distinct from every prior
clean migration: a **knowledge-base** source (per
`docs/architecture/sources.md` §5.2) carrying per-binding
leader-identity evidence, NOT a country-year scoring source
and NOT a leader-spell source. Each SPARQL binding carries one
`(country_qid, country_label, person_qid, person_label,
office_qid, office_label, start_date, end_date, statement_uri)`
tuple.

The descriptor advertises `source_id="wikidata_heads_of_state_government"`,
`default_version="SPARQL"`, `attribution_key="wikidata_heads_of_state_government"`,
`source_type="knowledge_base"`, `requires_network=False`,
coverage hint `None` (Wikidata is global, all-years,
all-countries), and the single observation family
`leader_identity_country_year`. The homepage URL is the
canonical SPARQL endpoint `https://query.wikidata.org/sparql`;
the WikiProject page
`https://www.wikidata.org/wiki/Wikidata:WikiProject_Heads_of_state_and_government`
is recorded in the coverage-hint notes.

Readiness requires a runtime-local `metadata.json`, validates
the canonical `source_version="SPARQL"` stamp (the legacy
alias `"SPARQL endpoint (no version)"` is also accepted on the
staged metadata for backward compatibility), rejects
unsupported request/source metadata versions, blocks
`cache_policy="refresh"` / `"no_cache"` with a structured
`unsupported_cache_policy` error, and validates the per-
`(year, country_qids)` JSON cache (file presence + SPARQL JSON
shape with a `results.bindings` list) for the requested
parameter set. For `years=None` the readiness gate uses the
canonical current-holders cache file
(`wd_ALL_current_all_<template_hash>.json`); for
`years=(YYYY,)` the gate uses the file matching the first
requested year (`wd_ALL_<year>_<country_hash>_<template_hash>.json`).

The adapter emits `leader_identity_country_year` observations
for the two legacy catalog variables
(`wikidata_head_of_state_held` for office Q30461 and
`wikidata_head_of_government_held` for office Q22857062).
`years=(YYYY,)` reads the matching single-year cache file and
emits one observation per binding with `year=YYYY`; multi-year
requests are explicitly unsupported in this cache-only slice; `years=None` reads the legacy current-holders
cache and emits one observation per binding with `year` taken
from the parsed row's `start_date` year (or `None` only when
the start date is absent). The original `start_date` and
`end_date` qualifiers are preserved on every emitted
observation's `extension.start_date` / `extension.end_date`
audit fields so downstream audit code can see the full
temporal envelope of each binding.

`countries=` filters are Wikidata-QID matches against the
`country_qid` column; non-QID inputs (e.g. `"USA"`) surface a
structured `wikidata_non_qid_country_filter` warning AND
silently emit zero rows (the unified adapter never invents
ISO3 codes). `wd:Q30` prefixed QIDs match the same as bare
`Q30` (the legacy parser's defensive `wd:` prefix stripping is
preserved). `leaders=` is unsupported and surfaces a
structured `UNSUPPORTED_FILTER` warning per SRC-REQ-005 (Stage
4 is the resolver for leader-identity evidence; Stage 2 does
not filter by leader).

Each observation preserves the Wikidata English country /
person / office labels verbatim (`country_name`,
`leader_name`, plus `extension.country_label` /
`extension.person_label` / `extension.office_label`), the
Wikidata QIDs (`extension.country_qid` /
`extension.person_qid` / `extension.office_qid`), the
verbatim SPARQL binding JSON as `extension.raw_binding`
(audit-trail copy of the API response row), the
`source_row_reference="wikidata:<country_qid>:<office_qid>:<person_qid>:<statement_hash>"`
pattern (matching the legacy DB writer; the 10-character
SHA-256 prefix of the statement URI is the
`extension.statement_hash` audit field), and the canonical
Wikidata attribution text `"Wikidata (CC0 1.0)."` per
Rule #15. `country_code` and `leader_id` remain `None` until
Stage 3 / Stage 4 fill them via the canonical country / leader
mapping tables. The unified adapter does not invent ISO3
country codes, leader identifiers, missing values, or proxy
years. `RawLocator` carries the cache file path + the SPARQL
endpoint URL + the per-cache asset id
(`wikidata_heads_of_state_government:cache:<cache_key>`);
`row_number` is intentionally `None` because the legacy parser
does not expose the SPARQL binding index (the binding index is
recoverable from the `statement_hash` audit field).

The unified adapter is cache-only in this slice
(`requires_network=False`, no HTTP layer in the new
package). The runner NEVER invokes the network; the legacy
`fetch_wikidata_sparql_payload` is intentionally NEVER imported
or invoked by the unified read path. The HTTP sentinel contract
is enforced by the `test_offline_only_runner_does_not_invoke_network`
+ `test_prefer_cache_runner_does_not_invoke_network` tests
which monkeypatch both
`leaders_db.ingest.wikidata_heads_of_state_government_http.fetch_wikidata_sparql_payload`
AND `requests.get` to raise `AssertionError` if either is
invoked.

### 7.17 Wikipedia Action API (search + extract) (clean migration)

`wikipedia_search_extract` is migrated under
`src/leaders_db/sources/adapters/wikipedia_search_extract/` as a
cache-only clean adapter. It reads the per-``(query, action)`` JSON
cache recorded under
`<raw_root>/wikipedia_search_extract/cache/` through lazy legacy
parser imports, so importing the clean adapter does NOT pull in
`leaders_db.ingest`.

Wikipedia Action API is the **always-on narrative-context helper**
for the prototype (per
`docs/requirements/top-level-requirements.md` §3 + §9 + §12). It is
API-backed (public Wikipedia Action API at
`https://en.wikipedia.org/w/api.php`, CC BY-SA 4.0) but the
unified runner is offline / cache-first by default and the unified
adapter is offline / cache-only in this slice
(`requires_network=False`). The canonical legacy cache key
convention `wikipedia_<action>_<query_hash>_<params_hash>.json` is
preserved verbatim — the canonical fixture filenames are
`wikipedia_extracts_62f100bfa4_default.json` (Joe Biden extracts),
`wikipedia_search_62f100bfa4_7d0587b5ac.json` (Joe Biden search),
and `wikipedia_extracts_6f47c90e93_default.json` (AMLO extracts).

The clean-slice request-input contract maps the Wikipedia Action
API query list to `request.leaders` (this source is a cached
web/knowledge snippet helper, `leaders=` here means query strings,
NOT resolved leader IDs). Missing / empty `leaders=` fails readiness
with a structured `wikipedia_search_extract_missing_queries` error
BEFORE the reader opens the cache — the helper does NOT browse /
discover. `years=` and `countries=` are unsupported filters for
this source (the Action API responses are not temporally scoped and
not country-coded); the readiness envelope surfaces a structured
`unsupported_filter` warning per request filter when set (the
runner ignores the filters and still emits the cached rows; the
unified adapter never invents year / country / leader values).

The descriptor advertises
`source_id="wikipedia_search_extract"`,
`default_version="Action API"`,
`attribution_key="wikipedia_search_extract"`,
`source_type="api"`, `requires_network=False`, coverage hint
`None` (Wikipedia is global, not temporally scoped), single
observation family `leader_identity_context` (distinguished from
the Wikidata `leader_identity_country_year` family so the two
leader-context sources can co-exist in the registry without
collision), Action API homepage URL
`https://en.wikipedia.org/w/api.php`, and the canonical attribution
text `Wikipedia (CC BY-SA 4.0).` per Rule #15. The adapter
accepts BOTH the canonical primary metadata shape
(`source_version="Action API"`) AND the legacy alias
(`version="Action API (no version)"`) so the existing staged
bundle does not need to be rewritten as part of the migration.
The metadata `version` / `source_version` field is OPTIONAL for a
cache-only bundle (the staged metadata is not required at runtime;
the cache files are the source of truth); when present, the gate
validates the canonical primary shape OR the legacy alias.

The adapter emits one `leader_identity_context` observation per
parsed Action API response row: one per `extracts` page (article
lead / intro paragraph as `value`) or one per `search` hit
(search snippet as `value`); `value_type='text'`; `year=None`,
`country_code=None`, `leader_id=None`, `leader_name=None` (the
Action API responses are not temporally scoped, not
country-coded, and not leader-resolved; Stage 3 / Stage 4 resolve
from the verbatim `raw_value` audit trail). The two in-scope
indicator codes from the legacy catalog
(`src/leaders_db/ingest/catalogs/wikipedia_search_extract.csv`) are
`wikipedia_extract_lead` (for the `extracts` Action API action)
and `wikipedia_search_results` (for the `search` Action API
action).

The per-observation `extension` carries the canonical attribution
text (Rule #15), the legacy DB-writer `source_row_reference`
(`wikipedia:<variable_name>:<hint>` where `<hint>` is the
parser-emitted per-row `wikipedia:<pageid>:<title>` (extracts) or
`wikipedia:search:<pageid>:<title>` (search)), the verbatim per-row
payload JSON (`raw_row_payload`), the verbatim query string,
the action name, the title, the pageid, the verbatim `extract`
text, the `cache_key`, the `value_type='text'` /
`raw_scale='text'` / `normalized_scale_target='text'` /
`higher_is_better=True` direction hints, the cache path
reference, and the `attribution` block. `RawLocator` carries the
Action API URL (`url=WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL`) +
the canonical `api_params_hash` (the legacy `build_cache_key`
output) + the `api_endpoint` template so audit code can resolve
the canonical Wikipedia URL for each emitted observation.
`TransformLocator` uses the canonical
`wikipedia_search_extract_query_v1` transform name.

Cache-policy semantics: `cache_policy="refresh"` / `"no_cache"` is
NOT supported by the unified adapter in this slice — readiness
surfaces a structured `unsupported_cache_policy` error BEFORE the
reader opens the cache. The runner NEVER invokes the network; the
legacy
`leaders_db.ingest.wikipedia_search_extract_http.fetch_wikipedia_action_api_payload`
HTTP layer is intentionally NEVER invoked by the unified read path
(verified by
`test_runner_does_not_invoke_http_layer` which monkeypatches the
legacy HTTP helper to raise `AssertionError` if invoked).

### 7.18 Polity V / Polity5 v2018 (clean migration, first "databases not yet in legacy")

Polity V is the **first source from the "databases not yet in
legacy" list** (the prior §7.1 list of 20 legacy-implemented
sources plus the §7.6-§7.17 series of clean migrations)
rebuilt under the clean `leaders_db.sources` interface. There
is **no legacy Stage 2 module to reuse** --
`STAGE2_ADAPTERS["polity_v"]` is `None` per the workplan Done
History ("blocked on source hygiene / raw file placement") --
so the unified adapter uses `pyreadstat.read_sav` directly
(lazy-imported inside the raw-read function) and emits the
canonical `NormalizedObservation` records end-to-end through
the new registry.

The unified Polity V adapter lives at
`src/leaders_db/sources/adapters/polity_v/` with
`source_id.slug == "polity_v"` and
`descriptor.attribution_key == "polity_v"`.

**Source-specific SPSS / pyreadstat contract.**

Polity V is the **first SPSS `.sav` source** under the clean
interface. The unified adapter's `read_raw` opens the staged
`p5v2018.sav` via `pyreadstat.read_sav` (1.4 MB / 17574 rows /
37 columns / SHA-256
`c0405a807777610a65fe430e4b4828fda16717afc4b5d6e34bf56f1ca100f2f6`),
filters the wide frame to the canonical 1800-2018 envelope
(dropping the historical 1776-1799 backfill + the 2019-2020
stray rows) so the descriptor's coverage hint is the
authoritative public contract, and emits a `RawReadResult`
carrying the filtered frame plus a `RawAsset` record (path,
SHA-256, source URL). The reader validates the staged
`metadata.json` + the per-file SHA-256 + the canonical
`source_version="p5v2018"` BEFORE opening the SPSS file; every
blocker surfaces a structured `SourceWarning(severity="error")`
so the runner raises `RuntimeError` BEFORE `read_raw` /
`transform` (per the documented readiness contract).

**Source-specific special-code matrix.**

Polity V component cells carry documented special codes
(`-66` / `-77` / `-88`) PLUS the canonical valid range
(`-10..+10` for `polity` / `polity2`; `0..+N` for sub-components).
The unified transform applies the documented coercion matrix:

- Valid int (in the indicator-specific valid range) -> emit
  `value=<int>` / `value_type='numeric'`. Valid negative scores
  (`-10..-1`) on `polity` / `polity2` ARE preserved as numeric
  observations -- they are real political-freedom data, NOT
  special codes.
- Special code (`-66` / `-77` / `-88`) -> emit
  `value=None` / `value_type='missing'` + the verbatim raw cell
  text on `extension.raw_value`. The observation is NOT
  dropped; the analyst can see the upstream gap without losing
  the observation id / locator (matches the PTS / RSF / FAS
  defensive pattern).
- NaN / blank / non-numeric / out-of-range -> emit
  `value=None` / `value_type='missing'` + the verbatim raw cell
  text on `extension.raw_value`.

**Source-specific coverage filter.**

Polity V covers 1800-2018 per the canonical attribution block
in `docs/sources/attributions.md` § `polity_v`. The unified
transform's raw-read layer filters to the canonical envelope so
the descriptor's coverage hint is authoritative; the readiness
envelope surfaces a structured `YEAR_ABSENT` warning on
out-of-coverage year requests (e.g. `years=(2023,)` for the
prototype's target year -- Polity V ends in 2018) per
SRC-COV-002 / SRC-COV-003 (no stale-proxy fill).

**Source-specific leader-filter semantics.**

Polity V is country-year political-freedom evidence, NOT
leader-identity evidence. The readiness envelope surfaces a
structured `UNSUPPORTED_FILTER` warning on `leaders=`
(SRC-REQ-005) -- the runner ignores the filter and still emits
the cached rows; the unified adapter never invents leader
values.

**Source-specific canonical catalog.**

The 11 catalog indicators all emit under the single
`political_freedom_country_year` observation family:

- `polity_v_polity` (composite regime score)
- `polity_v_polity2` (revised regime score)
- `polity_v_democ` (democracy sub-component)
- `polity_v_autoc` (autocracy sub-component)
- `polity_v_durable` (regime durability years)
- `polity_v_xrreg` / `polity_v_xrcomp` / `polity_v_xropen`
  (executive recruitment indicators)
- `polity_v_xconst` (executive constraints)
- `polity_v_parreg` / `polity_v_parcomp` (participatory
  indicators)

The descriptor advertises the single observation family so
downstream query code can filter by
`observation_family == "political_freedom_country_year"`
without consulting the per-source catalog.

**Runtime hygiene.**

The runtime-local `data/raw/polity_v/metadata.json` is
gitignored per Always-On Rule #9 -- the canonical bundle is
the user-staged `p5v2018.sav`; metadata is a runtime-local
requirement beside the user-staged raw `.sav` (matches the
CIRIGHTS / SIPRI Milex / SIPRI Yearbook Ch.7 pattern). The
readiness gate accepts the canonical primary metadata shape
(`source_version` / `source_url` / `license_note` /
`local_files` / `checksum_sha256` / `ingestion_status` /
`coverage` / `source_name` / `download_date` / `notes`) and
fails readiness with structured `missing_metadata` /
`missing_raw` / `unsupported_version` errors so the runner
refuses to dispatch `read_raw` / `transform`.

The legacy `STAGE2_ADAPTERS["polity_v"]` slot remains `None`
(the unified adapter does NOT add a legacy orchestrator
because Polity V was the first "databases not yet in legacy"
entry per the §7.2 row update). The new package exposes
explicit `create_polity_v_adapter()` and
`register_polity_v(registry)` factories and does NOT
auto-register on import (per `docs/architecture/sources.md`
§10.1). The unified attribution text
 `"Polity V (Marshall, Jaggers, Gleditsch 2018)."` is
 byte-identical to the `polity_v` row in
 `docs/sources/attributions.md` (Always-On Rule #15; the
 `test_polity_v_attribution_text_matches_attributions_doc`
 drift guard enforces byte-identity).

### 7.19 SIPRI Arms Transfers Database (clean migration, cache-only)

`sipri_arms_transfers` is the **next feasible
clean-interface-only source** after ``polity_v``
(`docs/architecture/sources.md` §7.2 ``sipri_arms_transfers``
row; second post-interface source with no legacy Stage 2
implementation). There is **no legacy Stage 2 module to
reuse** -- ``STAGE2_ADAPTERS["sipri_arms_transfers"]`` is
``None`` per the workplan Done History ("blocked on source
hygiene / raw file placement") -- so the unified adapter is
built from scratch.

The unified SIPRI Arms Transfers adapter lives at
`src/leaders_db/sources/adapters/sipri_arms_transfers/` with
`source_id.slug == "sipri_arms_transfers"` and
`descriptor.attribution_key == "sipri_arms_transfers"`.

**Source-specific cache-only contract.**

The SIPRI Arms Transfers Database is SIPRI's public record of
international transfers of major conventional arms (1950-2025
per the canonical 2026-03-09 SIPRI update). The unified
adapter in this slice is **offline / cache-only** -- the task
brief explicitly cautions against adding a broad network
downloader because "the existing clean-source architecture
[does] not expose an explicit safe cache_policy/http-client
pattern [the adapter] can mirror". The canonical Stage 2
access path is a single staged cached export from
`data/raw/sipri_arms_transfers/`:

1. **Direct CSV** -- the canonical `trade_register.csv` file.
2. **Base64-JSON wrapper** -- the canonical `trade_register.json`
   file containing base64-encoded CSV bytes (the canonical
   shape the SIPRI public app's backend API
   `https://atbackend.sipri.org/api/p/trades/trade-register-csv/`
   returns).

The unified adapter never invokes the network; live fetch is
intentionally NOT supported in this slice. The
`cache_policy='refresh'` / `'no_cache'` policies fail
readiness with a structured
`sipri_arms_transfers_unsupported_cache_policy` error
BEFORE `read_raw` / `transform` are called -- the runner
refuses to dispatch rather than silently surfacing an
HTTP-fetched payload.

**Source-specific schema contract.**

The cached CSV / JSON export carries 8 documented required
columns (`Supplier` / `Recipient` / `Order year` /
`Delivery year` / `Designation` / `Status` /
`Numbers delivered` / `TIV (delivered)`). The raw-read layer
validates the parsed header against this set BEFORE the
transform layer consumes the frame; a missing required column
fires a structured `SipriArmsTransfersSchemaError` carrying
the missing-columns / expected-columns / actual-columns
context so the transform layer does NOT silently emit
partial output on a schema contract violation. SIPRI
preamble / citation lines (the lines that precede the
documented header row in the canonical SIPRI Trade Register
export) are split out and preserved on the audit-trail
`extension["sipri_arms_transfers_preamble"]` field on every
emitted observation so downstream code can recover the
verbatim SIPRI citation block per Always-On Rule #15.

**Source-specific observation families.**

The unified adapter emits TWO observation families so
downstream query code can filter by family without
consulting the per-source catalog:

1. `arms_transfer_register_row` -- one observation per cached
   transfer row, per indicator. The 3 per-row indicator
   codes are `sipri_arms_transfers_tiv_delivered` /
   `sipri_arms_transfers_tiv_ordered` /
   `sipri_arms_transfers_number_delivered`. Rows with
   missing / blank / non-numeric TIV or number cells are
   emitted with `value=None` / `value_type="missing"` plus
   the verbatim raw cell text on `extension.raw_value` --
   the observation is NOT dropped (matches the SIPRI
   Yearbook Ch.7 / FAS / RSF / PTS defensive pattern).

2. `arms_transfer_country_year_aggregate` -- one
   observation per `(role, country, year)` triple where
   `role` is `"supplier"` or `"recipient"`. The aggregate
   is the deterministic sum of TIV (delivered) over all
   transfers in the cached bundle where the country appears
   as supplier (resp. recipient) and the delivery year
   matches the year. The per-`(role, country, year)` scope
   key keeps supplier-side and recipient-side aggregates
   separate (no double-counting when the same country
   appears as both supplier and recipient in the same
   year). The 2 per-aggregate indicator codes are
   `sipri_arms_transfers_supplier_year_tiv_delivered` and
   `sipri_arms_transfers_recipient_year_tiv_delivered`.

**Source-specific coverage envelope + year semantics.**

The SIPRI Arms Transfers Database covers 1950-2025 per the
canonical attribution block in
`docs/sources/attributions.md` § `sipri_arms_transfers`. The
descriptor advertises the canonical envelope; the readiness
envelope surfaces a structured `YEAR_ABSENT` warning on
out-of-coverage year requests (e.g. `years=(2026,)` -- one
year past the latest SIPRI update) per SRC-COV-002 /
SRC-COV-003 (no stale-proxy fill). The prototype's target
year 2023 falls WITHIN the canonical envelope (1950-2025)
so 2023 is in-coverage.

**Source-specific leader-filter semantics.**

SIPRI Arms Transfers is a supplier-recipient flow source,
not leader-identity evidence. The readiness envelope surfaces
a structured `UNSUPPORTED_FILTER` warning on `leaders=`
(SRC-REQ-005) -- the runner ignores the filter and still
emits the in-coverage rows; the unified adapter never invents
leader values.

**Source-specific ISO3 caveat.**

The SIPRI Trade Register uses SIPRI's own country display
names, which are NOT ISO3. The unified adapter preserves the
source-native supplier / recipient display names verbatim on
every emitted observation's
`extension["sipri_arms_transfers_supplier"]` /
`extension["sipri_arms_transfers_recipient"]` fields. The
adapter does NOT invent ISO3 codes; `country_code` /
`leader_id` / `leader_name` remain `None` until later
matching / resolution stages introduce a canonical ISO3
mapping.

**Source-specific attribution caveat.**

The descriptor's `coverage_hint.notes` carries the explicit
SIPRI Arms Transfers caveat: arms-transfer data is evidence
of arms flows between recorded supplier / recipient countries
and is NOT direct proof of aggression, proxy sponsorship, or
illegality. Downstream scorers MUST NOT silently treat
arms-transfer TIV totals as a proxy for aggression /
responsibility without an explicit secondary-source
corroboration step (UCDP external support, sanctions
records, expert-panel reports, manual evidence). This is
the documented caveat the
`docs/methodology/ranking-evaluation-criteria.md` Chapter 2
proxy-aggression question applies to arms-transfer evidence.

**Runtime hygiene.**

The runtime-local `data/raw/sipri_arms_transfers/metadata.json`
is gitignored per Always-On Rule #9. The readiness gate
validates the canonical metadata fields (source_name /
source_version / source_url / license_note / coverage /
local_files / ingestion_status / checksum_sha256 /
download_date / notes) plus the per-file SHA-256 when
supplied (the gate accepts BOTH the canonical flat-string
shape `checksum_sha256 = "<64-hex>"` AND the per-file dict
shape `checksum_sha256 = {"trade_register.csv":
"<64-hex>"}` -- matching the SIPRI Milex / SIPRI Yearbook
Ch.7 / CIRIGHTS convention). Missing or mismatched metadata
fails readiness with structured `missing_metadata` /
`missing_raw` / `sipri_arms_transfers_metadata_version_mismatch`
/ `sipri_arms_transfers_checksum_mismatch` errors so the
runner refuses to dispatch `read_raw` / `transform`. The
canonical version stamp is
`"SIPRI Arms Transfers Trade Register 2026-03-09 (data 1950-2025)"`.

The legacy `STAGE2_ADAPTERS["sipri_arms_transfers"]` slot
remains `None` (the unified adapter does NOT add a legacy
orchestrator). The new package exposes explicit
`create_sipri_arms_transfers_adapter()` and
`register_sipri_arms_transfers(registry)` factories and
does NOT auto-register on import (per
`docs/architecture/sources.md` §10.1). The unified
attribution text
`"SIPRI Arms Transfers Database (Stockholm International Peace Research Institute 2026)."`
is byte-identical to the `sipri_arms_transfers` row in
`docs/sources/attributions.md` (Always-On Rule #15; the
`test_sipri_arms_transfers_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity).

The 39 focused tests in
`tests/sources/test_sipri_arms_transfers_adapter.py` cover
the SIPRI-specific slice of the unified-source adapter
contract:

- Descriptor / factory / registry surface
  (``test_descriptor_factory_and_registry``,
  ``test_register_helper_registers_against_explicit_registry``,
  ``test_indicator_codes_match_canonical_5``,
  ``test_required_columns_match_canonical_8``,
  ``test_attribution_text_matches_attributions_doc``,
  ``test_attribution_key_matches_attributions_doc``).
- ``SourceIngestRunner`` end-to-end on the direct-CSV
  cached shape
  (``test_runner_emits_register_and_aggregate_observations``,
  ``test_runner_emits_register_row_for_each_indicator``,
  ``test_runner_emits_aggregate_observations_for_in_coverage_year``,
  ``test_runner_aggregate_math_is_deterministic``,
  ``test_runner_non_numeric_tiv_emits_missing_with_raw_value``,
  ``test_runner_delivery_year_range_parses_first_year``,
  ``test_runner_preserves_preamble_on_extension``,
  ``test_runner_years_none_reads_all_fixture_rows``,
  ``test_runner_countries_filter_applies_to_supplier_or_recipient``,
  ``test_runner_does_not_invent_iso3_codes``,
  ``test_runner_observation_ids_are_unique``,
  ``test_runner_extension_carries_canonical_attribution``,
  ``test_runner_source_version_propagates_to_observations``,
  ``test_runner_transform_locator_rule_id_matches_source_row_reference``).
- ``SourceIngestRunner`` end-to-end on the base64-JSON
  cached shape
  (``test_runner_reads_base64_json_cached_shape``,
  ``test_base64_json_envelope_decode_handles_alternative_keys``).
- SIPRI-specific year-scoping semantics
  (``test_runner_out_of_coverage_year_warns_and_emits_zero``)
  plus the new
  ``test_years_filter_emits_no_delivery_year_2020_from_order_year_2018``
  which proves a ``years=(2018,)`` request emits no
  ``year=2020`` observations / aggregates from an
  order-2018 / delivery-2020 record.
- SIPRI-specific leader-filter warning
  (``test_runner_leader_filter_warns_but_is_ignored``).
- ``STAGE2_ADAPTERS``-no-touch dispatch contract
  (``test_runner_does_not_consult_legacy_stage2_adapters``).
- Readiness failures (parametrised)
  (``test_correct_bundle_passes_readiness``,
  ``test_unsupported_request_version_fails_readiness``,
  ``test_unsupported_cache_policy_fails_readiness``,
  ``test_checksum_mismatch_fails_readiness``,
  ``test_readiness_failures``,
  ``test_missing_required_csv_column_fails_readiness``,
  ``test_preamble_only_cached_export_emits_warning``).
- Import boundary + network boundary
  (``test_importing_adapter_does_not_import_legacy_ingest``,
  ``test_adapter_does_not_use_network``).
- Preamble-detection robustness against punctuation-
  containing preamble lines (commas, semicolons, quotes)
  for BOTH the direct-CSV and base64-JSON cached shapes
  (``test_raw_read_handles_punctuation_preamble_csv``,
  ``test_raw_read_handles_punctuation_preamble_base64_json``).
- ``RawAsset.checksum_sha256`` population for BOTH cached
  shapes
  (``test_raw_asset_checksum_populated_csv``,
  ``test_raw_asset_checksum_populated_base64_json``).
- ``SourceAdapter`` Protocol conformance
  (``test_adapter_satisfies_source_adapter_protocol``).

The ``tests/sources/test_import_boundary.py`` canonical
submodule list now includes
`leaders_db.sources.adapters.sipri_arms_transfers`.

### 7.20 IAEA Safeguards Status List (clean migration, offline / cache-only)

`iaea_safeguards` is the **next feasible
clean-interface-only source** after ``sipri_arms_transfers``
(`docs/architecture/sources.md` §7.2 ``iaea_safeguards`` row;
third post-interface source with no legacy Stage 2
implementation). There is **no legacy Stage 2 module to
reuse** -- ``STAGE2_ADAPTERS["iaea_safeguards"]`` remains
``None`` per the workplan Done History ("need / future" before
this slice) -- so the unified adapter is built from scratch.

The unified IAEA Safeguards adapter lives at
`src/leaders_db/sources/adapters/iaea_safeguards/` with
`source_id.slug == "iaea_safeguards"` and
`descriptor.attribution_key == "iaea_safeguards"`.

**Source-specific scope: legal / status evidence only.**

The task brief scoped this slice deliberately to the public
IAEA Safeguards Status List PDF
(`https://www.iaea.org/sites/default/files/20/01/sg-agreements-comprehensive-status.pdf`,
"Conclusion of Safeguards Agreements, Additional Protocols and
Small Quantities Protocols", status as of 31 December 2025).
This is a **single-point legal / status snapshot** covering
~190 States: the source-native composite `Safeguards Agreement`
status label for a Comprehensive Safeguards Agreement (CSA),
the status of an Additional Protocol
(AP) signed / approved / in force / not in force / not signed,
the status of a Small Quantities Protocol (SQP) modified /
original / not applicable / not in force, and the INFCIRC
document identifier. The slice does NOT cover the per-country
"conclusions" of safeguards (the formal IAEA State-level
conclusions document); downstream code that needs
conclusions-level evidence must wait for a future adapter
(``iaea_additional_protocol_status`` in §7.2 is a subset /
family of this same source -- NOT a separate adapter).

**Source-specific cache-only contract.**

The IAEA Safeguards Status List is published as a public PDF
that the IAEA permits download / copy / use with acknowledgement
for research / private study / commercial / non-commercial use
subject to restrictions; do not redistribute the full PDF /
table in outputs. The unified adapter is **offline /
cache-only** in this slice -- the task brief explicitly cautions
against adding a broad network downloader because the existing
clean-source architecture does not expose a dedicated safe
``cache_policy`` / http-client pattern for IAEA Safeguards.
Live fetch is intentionally NOT supported; the
``cache_policy='refresh'`` / ``'no_cache'`` policies fail
readiness with a structured
``iaea_safeguards_unsupported_cache_policy`` error BEFORE
``read_raw`` / ``transform`` are called -- the runner refuses
to dispatch rather than silently surfacing an HTTP-fetched
payload. The canonical Stage 2 access path is a single staged
cached PDF at
`data/raw/iaea_safeguards/sg-agreements-comprehensive-status.pdf`
plus a runtime-local `metadata.json` (gitignored per
Always-On Rule #9).

**Source-specific schema contract.**

The cached status-list PDF carries 5 documented required
columns: `State` / `Safeguards Agreement` / `INFCIRC` /
`Additional Protocol` / `Small Quantities Protocol`. The
raw-read layer (via `pdfplumber`) tries the
`extract_tables()` path first then falls back to text
extraction, validates the parsed header against the 5 canonical
required columns, and raises `IaeaSafeguardsSchemaError` BEFORE
the transform layer consumes the frame; the transform layer
does NOT silently emit partial output on a schema contract
violation.

**Source-specific observation families.**

The unified adapter emits ONE observation family
(`nuclear_safeguards_status_country`) with 4 source-native
catalog indicators (one per non-State column in the cached
PDF table):

- `iaea_safeguards_safeguards_agreement_status` -- the
  composite CSA status cell (verbatim source-native label
  preserved on
  `extension["iaea_safeguards_safeguards_agreement_status_raw"]`).
- `iaea_safeguards_additional_protocol_status` -- the AP
  status cell (verbatim source-native label preserved on
  `extension["iaea_safeguards_additional_protocol_status_raw"]`).
- `iaea_safeguards_small_quantities_protocol_status` -- the
  SQP status cell (verbatim source-native label preserved on
  `extension["iaea_safeguards_small_quantities_protocol_status_raw"]`).
- `iaea_safeguards_infcirc_number` -- the INFCIRC document
  identifier (text; verbatim source-native identifier
  preserved on `extension["iaea_safeguards_infcirc_raw"]`).

The catalog deliberately does NOT include a separate
`iaea_safeguards_safeguards_agreement_type` indicator: the
canonical IAEA table has a single `Safeguards Agreement`
column carrying the composite status label (e.g.
`In Force: 153` / `Not in Force: 66` / `N/A`), NOT a separate
type column; the adapter never invents a type column from
the composite label.

Per-row emission produces up to 4 observations per cached
country row (5 rows x 4 indicators = 20 observations for a full
5-row fixture). Empty cells (e.g. blank INFCIRC for non-States)
emit `value=None` / `value_type="missing"` plus the verbatim
raw cell text on `extension.raw_value` so audit code can
recover the original cell.

**Source-specific multi-page PDF semantics.**

The raw-read boundary iterates every PDF page and accumulates
rows from every page whose header matches the canonical column
set; the reader does NOT stop at the first matching page. Each
parsed row carries a 1-based `page_number` key so the
transform layer can populate `RawLocator.page_number` with
the exact page the row originated from. Multi-page PDFs
(typical for the ~190 country rows of the public IAEA
Safeguards Status List) paginate rows across pages; the
per-row page provenance is preserved verbatim on every
emitted observation's `RawLocator.page_number` field.

**Source-specific coverage envelope + year semantics.**

The IAEA Safeguards Status List is a single-point legal /
status snapshot (the canonical probed stamp is "status as of
31 December 2025"). The descriptor advertises a single-year
envelope (`start_year == end_year == 2025`); the readiness
envelope surfaces a structured `YEAR_ABSENT` warning on
out-of-coverage year requests (e.g. `years=(2023,)` -- the
prototype's target year -- falls outside the envelope) per
SRC-COV-002 / SRC-COV-003 (no stale-proxy fill). The
prototype's target year 2023 falls OUTSIDE the canonical
envelope; the transform emits zero observations for that year
(no stale-proxy to 2025). The descriptor's `coverage_hint.notes`
explicitly tells operators that the snapshot is a single
legal observation, not a multi-year time series.

**Source-specific leader-filter semantics.**

The IAEA Safeguards Status List is a country-level legal /
status snapshot, NOT leader-identity evidence. The readiness
envelope surfaces a structured `UNSUPPORTED_FILTER` warning on
`leaders=` (SRC-REQ-005) -- the runner ignores the filter and
still emits the cached rows; the unified adapter never invents
leader values.

**Source-specific ISO3 caveat.**

The IAEA Safeguards Status List uses IAEA's own State display
names, which are NOT ISO3. The unified adapter preserves the
source-native state display name verbatim on every emitted
observation's `extension["iaea_safeguards_state"]` field. The
adapter does NOT invent ISO3 codes; `country_code` /
`leader_id` / `leader_name` remain `None` until later matching
/ resolution stages introduce a canonical ISO3 mapping.

**Source-specific attribution caveat.**

The descriptor's `coverage_hint.notes` carries the explicit
caveat that this source captures safeguards / legal / status
evidence -- the source-native safeguards agreement status,
INFCIRC reference, Additional Protocol status, and Small
Quantities Protocol status -- and is NOT a direct nuclear-weapons score or
proof of safeguards compliance / non-compliance by itself.
Downstream scorers MUST NOT silently treat a `Not in Force` AP
cell as proof of non-cooperation; the Stage 11 confidence
formula penalises the temporal-fit gap between the cached
status date and the prototype's target year (2023). The
canonical attribution text
`"IAEA Safeguards Status List, Conclusion of Safeguards
Agreements, Additional Protocols and Small Quantities
Protocols (International Atomic Energy Agency, status as of 31
December 2025)."` is byte-identical to the `iaea_safeguards`
row in `docs/sources/attributions.md` (Always-On Rule #15).
The canonical version stamp
`"IAEA Safeguards Status List, status as of 2025-12-31"`
propagates consistently to `RawAsset.version` and every
emitted `NormalizedObservation.source_version`. The legacy
`STAGE2_ADAPTERS["iaea_safeguards"]` slot remains `None` (no
legacy Stage 2 implementation); the new package exposes
explicit `create_iaea_safeguards_adapter()` and
`register_iaea_safeguards(registry)` factories and does NOT
auto-register on import (per `docs/architecture/sources.md`
§10.1).

**Source-specific test surface.**

The focused tests in
`tests/sources/test_iaea_safeguards_adapter.py` cover: the
descriptor / factory / registry / public surface (8 tests);
the canonical 4-indicator catalog; the
attribution-text drift guard (2 tests); the readiness-failure
matrix (6 readiness-blocker cases + cache-policy gate +
unsupported-version blocker + unsupported-leaders-filter
advisory warning); the year semantics (out-of-coverage year
emits zero observations + advisory `YEAR_ABSENT` warning;
in-coverage year emits the full observation set; `years=None`
emits the full observation set); the country filter (single
match, no-match, multiple matches, source-native display name);
the runner end-to-end contract (full-bundle + scoped requests);
the observation shape (source-native state preserved verbatim
+ no ISO3 invention + per-indicator value / value_type
+ raw_locator + transform_locator); the schema-error path
(`IaeaSafeguardsSchemaError` for missing required columns);
the import-boundary contract (no `leaders_db.ingest` leak);
the no-network boundary (HTTP / socket sentinels never
invoked); and the duplicate-slug `ValueError` registration
guard (SRC-REG-004). The synthetic PDF fixture is built by
`tests/fixtures/iaea_safeguards/build_sample_pdf.py` via
`reportlab` (5 hand-authored synthetic country rows + 1
header row; the country labels and cell values are NOT real
IAEA Safeguards data per the task brief: "fixtures must not
redistribute IAEA tables").

The `tests/sources/test_import_boundary.py` canonical
submodule list now includes
`leaders_db.sources.adapters.iaea_safeguards`.

### 7.21 CTBTO States Signatories — CTBT treaty-status (clean migration, offline / cache-only)

`ctbto_treaty_status` is the **next feasible
clean-interface-only source** after ``iaea_safeguards``
(`docs/architecture/sources.md` §7.2 ``ctbto_treaty_status``
row; fourth post-interface source with no legacy Stage 2
implementation). There is **no legacy Stage 2 module to
reuse** -- ``STAGE2_ADAPTERS["ctbto_treaty_status"]``
remains unset per the workplan Done History ("need / future"
before this slice) -- so the unified adapter is built from
scratch.

The unified CTBTO Treaty Status adapter lives at
`src/leaders_db/sources/adapters/ctbto_treaty_status/` with
`source_id.slug == "ctbto_treaty_status"` and
`descriptor.attribution_key == "ctbto_treaty_status"`.

**Source-specific scope: treaty-status evidence only.**

The task brief scoped this slice deliberately to the public
CTBTO States Signatories page
(`https://www.ctbto.org/our-mission/states-signatories`,
"States Signatories — Comprehensive Nuclear-Test-Ban
Treaty", status as of 13 March 2024). This is a **single-point
treaty-status snapshot** covering ~196 States: the source-
derived signature status (`"signed"` iff the signature date
is non-empty in the cached row, `"not_signed"` otherwise)
and the source-derived ratification status (`"ratified"` iff
the ratification date is non-empty in the cached row,
`"not_ratified"` otherwise). The slice does NOT cover
per-country nuclear behaviour, compliance, or non-compliance
-- the source is a treaty-status observation, NOT direct
proof of nuclear behaviour, compliance, or non-compliance.
The signature / ratification date cells are preserved verbatim
as strings on the audit-trail extension payload (the adapter
does NOT coerce them to numeric years that could mislead Stage
11 confidence calculations). The `iaea_additional_protocol_status`
slug in §7.2 is a subset / family of the `iaea_safeguards`
adapter (the Additional Protocol status cell is one of the
4 source-native catalog indicators emitted by `iaea_safeguards`)
and is NOT a separate adapter.

**Source-specific cache-only contract.**

The CTBTO States Signatories page is delivered as a public
HTML table that the CTBTO terms-of-use
(`https://www.ctbto.org/terms-of-use`) permit users to visit,
download and copy subject to terms; personal, non-commercial,
research / teaching use is permitted with acknowledgement; do
not redistribute or derivative-compile without permission;
the "designations" caveat preserves the CTBTO's neutral
diplomatic nomenclature. The unified adapter is **offline /
cache-only** in this slice -- the task brief explicitly
cautions against adding live download / scraping ("Do NOT
implement live download/scraping. Build an offline/cache-
first adapter"). Live fetch is intentionally NOT supported;
the ``cache_policy='refresh'`` / ``'no_cache'`` policies fail
readiness with a structured
``ctbto_treaty_status_unsupported_cache_policy`` error BEFORE
``read_raw`` / ``transform`` are called -- the runner refuses
to dispatch rather than silently surfacing an HTTP-fetched
payload. The canonical Stage 2 access path is a single staged
cached CSV at
`data/raw/ctbto_treaty_status/states-signatories.csv` (or the
HTML fallback at `data/raw/ctbto_treaty_status/states-signatories.html`)
plus a runtime-local `metadata.json` (gitignored per
Always-On Rule #9).

**Source-specific schema contract.**

The cached CTBTO States Signatories export carries 4
documented required columns: `Region` / `State` /
`Signature Date` / `Ratification Date`. The raw-read layer
parses the cached CSV via the Python `csv` module (or a
built-in HTML table parser for the HTML fallback), validates
the parsed header against the 4 canonical required columns,
and raises `CtbtoTreatyStatusSchemaError` BEFORE the
transform layer consumes the frame; the transform layer does
NOT silently emit partial output on a schema contract
violation. The optional `Annex 2` column is preserved on the
parsed row only when the cached fixture / source-native data
carries the column -- the canonical CTBTO public page does
NOT carry an Annex 2 flag, so the transform layer does NOT
emit an Annex 2 observation by default and never invents an
Annex 2 flag from missing source-native data.

**Source-specific observation family.**

The unified adapter emits ONE observation family
(`nuclear_treaty_status_country`) with 2 source-derived
catalog indicators (one per date-bearing column in the
cached CTBTO table):

- `ctbto_treaty_status_signature_status` -- the source-
  derived signature status sentinel: `"signed"` iff the
  signature date is non-empty in the cached row,
  `"not_signed"` otherwise. The transform never invents a
  signature status from empty / blank date cells -- an empty
  signature date cell is ALWAYS treated as `"not_signed"`.
- `ctbto_treaty_status_ratification_status` -- the source-
  derived ratification status sentinel: `"ratified"` iff the
  ratification date is non-empty in the cached row,
  `"not_ratified"` otherwise. The transform never invents a
  ratification status from empty / blank date cells -- an
  empty ratification date cell is ALWAYS treated as
  `"not_ratified"`.

The catalog deliberately does NOT include a default
`ctbto_treaty_status_annex_2_status` indicator: the canonical
CTBTO public page does NOT carry an Annex 2 flag column
(Annex 2 refers to the 44 States that the CTBTO PrepCom
identified as needing to ratify the CTBT for the Treaty to
enter into force, but the public table does NOT surface an
Annex 2 status column); the adapter never invents an Annex 2
flag from missing source-native data. The transform layer
preserves an OPTIONAL Annex 2 indicator emission when the
cached fixture / source-native data carries an explicit
`Annex 2` flag column, but the default 2-indicator catalog
does NOT include the Annex 2 indicator.

Per-row emission produces 2 observations per cached State row
by default (6 rows × 2 indicators = 12 observations for the
default fixture; 6 rows × 3 indicators = 18 observations
when the cached fixture carries an explicit `Annex 2`
column).

**Source-specific coverage envelope + year semantics.**

The CTBTO States Signatories page is a single-point
treaty-status snapshot (the canonical probed stamp is "status
as of 13 March 2024" -- the date of the latest ratifying
state Papua New Guinea). The descriptor advertises a
single-year envelope (`start_year == end_year == 2024`); the
readiness envelope surfaces a structured `YEAR_ABSENT`
warning on out-of-coverage year requests (e.g. `years=(2023,)`
-- the prototype's target year -- falls outside the
envelope) per SRC-COV-002 / SRC-COV-003 (no stale-proxy
fill). The prototype's target year 2023 falls OUTSIDE the
canonical envelope; the transform emits zero observations
for that year (no stale-proxy to 2024). The descriptor's
`coverage_hint.notes` explicitly tells operators that the
snapshot is a single legal observation, not a multi-year
time series.

**Source-specific leader-filter semantics.**

The CTBTO States Signatories page is a country-level
treaty-status snapshot, NOT leader-identity evidence. The
readiness envelope surfaces a structured `UNSUPPORTED_FILTER`
warning on `leaders=` (SRC-REQ-005) -- the runner ignores
the filter and still emits the cached rows; the unified
adapter never invents leader values.

**Source-specific ISO3 caveat.**

The CTBTO States Signatories page uses CTBTO's own State
display names, which are NOT ISO3. The unified adapter
preserves the source-native State display name verbatim on
every emitted observation's
`extension["ctbto_treaty_status_state"]` field, along with
the source-native Region display name on
`extension["ctbto_treaty_status_region"]`. The adapter does
NOT invent ISO3 codes; `country_code` / `leader_id` /
`leader_name` remain `None` until later matching / resolution
stages introduce a canonical ISO3 mapping.

**Source-specific attribution + legal caveat.**

The descriptor's `coverage_hint.notes` carries the explicit
caveat that this source captures CTBT treaty-status
evidence -- the source-derived signature / ratification
status flags -- and is NOT direct proof of nuclear behaviour,
compliance, or non-compliance. Downstream scorers MUST NOT
silently treat an unsigned / unratified status cell as
proof of nuclear activity or non-cooperation; the Stage 11
confidence formula penalises the temporal-fit gap between
the cached snapshot date (2024-03-13) and the prototype's
target year (2023). The canonical attribution text
`"CTBTO States Signatories, Comprehensive Nuclear-Test-Ban
Treaty signature and ratification status (Comprehensive
Nuclear-Test-Ban Treaty Organization, status as of 13 March
2024)."` is byte-identical to the `ctbto_treaty_status` row
in `docs/sources/attributions.md` (Always-On Rule #15). The
canonical version stamp
`"CTBTO States Signatories, status as of 2024-03-13"`
propagates consistently to `RawAsset.version` and every
emitted `NormalizedObservation.source_version`. No legacy
`STAGE2_ADAPTERS["ctbto_treaty_status"]` entry exists
(no legacy Stage 2 implementation); the new package exposes
explicit `create_ctbto_treaty_status_adapter()` and
`register_ctbto_treaty_status(registry)` factories and does
NOT auto-register on import (per `docs/architecture/sources.md`
§10.1).

**Source-specific test surface.**

The focused tests in
`tests/sources/test_ctbto_treaty_status_adapter.py` cover: the
descriptor / factory / registry / public surface (8 tests);
the canonical 2-indicator catalog + Annex 2 absence / presence
assertion (3 tests); the attribution-text drift guard (2
tests); the readiness-failure matrix (5 readiness-blocker
cases + cache-policy gate + unsupported-version blocker +
unsupported-leaders-filter advisory warning); the year
semantics (out-of-coverage year emits zero observations +
advisory `YEAR_ABSENT` warning; in-coverage year emits the
full observation set; `years=None` emits the full observation
set); the country filter (single match, no-match, multiple
matches, source-native display name); the signature /
ratification status sentinels (signed+ratified row, signed
but not-yet-ratified row, unsigned+unratified row -- the
unsigned / unratified rows are NOT silently treated as
signed / ratified); the observation shape (source-native
State preserved verbatim + no ISO3 invention + raw_locators +
transform_locators + attribution text); the Annex 2 indicator
emission path (OPTIONAL emission when the cached fixture
carries an explicit `Annex 2` column, NO emission when the
column is absent); the schema-error path
(`CtbtoTreatyStatusSchemaError` for missing required columns);
the import-boundary contract (no `leaders_db.ingest` leak);
the no-network boundary (HTTP / socket sentinels never
invoked); the duplicate-slug `ValueError` registration guard
(SRC-REG-004); and the HTML fallback contract (the
raw-read boundary loads the HTML fallback when the CSV is
absent and parses the `<table>` via the built-in HTML
parser). The synthetic CSV fixture is built by
`tests/fixtures/ctbto_treaty_status/build_sample_csv.py` (6
hand-authored synthetic State rows + 1 header row; the State
labels and date cells are NOT real CTBTO Treaty Status data
per the task brief: "fixtures must not redistribute copied
full table in outputs").

The `tests/sources/test_import_boundary.py` canonical
submodule list now includes
`leaders_db.sources.adapters.ctbto_treaty_status`.

### 7.22 World Bank Poverty and Inequality Platform / PIP (clean migration, offline / cache-only)

`world_bank_poverty_inequality_platform` is the **next feasible
clean-interface-only source** after ``ctbto_treaty_status``
(``docs/architecture/sources.md`` §7.2
``world_bank_poverty_inequality_platform`` row; no legacy Stage
2 implementation, and no legacy ``STAGE2_ADAPTERS`` slot is
added for this clean-interface-only slice). The unified adapter
is built from scratch.

The unified World Bank PIP adapter lives at
`src/leaders_db/sources/adapters/world_bank_poverty_inequality_platform/`
with `source_id.slug == "world_bank_poverty_inequality_platform"`
and `descriptor.attribution_key == "world_bank_poverty_inequality_platform"`.

**Source-specific scope: poverty / inequality / distribution
observations only.**

The task brief scoped this slice deliberately to the public
World Bank PIP dataset (PIP home page
`https://pip.worldbank.org/`, PIP API
`https://pip.worldbank.org/api` -- CSV / JSON endpoints). PIP
delivers per-(country_code, country_name, year, reporting_level,
welfare_type, poverty_line) country-year observations: the
poverty headcount ratio, the poverty gap, and the Gini index.
The source-native `country_code` is the World Bank's own
reporting identifier -- a 3-character code that LOOKS LIKE
ISO3 but is NOT a canonical ISO3 mapping; the adapter does NOT
assume it is ISO3 even when it resembles one. Per-row PPP
version + reporting level + welfare type + poverty line are
preserved on the audit-trail extension payload.

**Source-specific cache-only contract.**

The unified adapter is **offline / cache-first** in this slice
-- the task brief explicitly cautions against adding live HTTP
fetching ("Build an offline/cache-first adapter. Do NOT
implement live HTTP fetching"). Live fetch is intentionally
NOT supported; the ``cache_policy='refresh'`` / ``'no_cache'``
policies fail readiness with a structured
``world_bank_poverty_inequality_platform_unsupported_cache_policy``
error BEFORE ``read_raw`` / ``transform`` are called -- the
runner refuses to dispatch rather than silently surfacing an
HTTP-fetched payload. The canonical Stage 2 access path is a
single staged cached CSV at
`data/raw/world_bank_poverty_inequality_platform/pip_stats.csv`
(or the cached JSON wrapper at
`data/raw/world_bank_poverty_inequality_platform/pip_stats.json`)
plus a runtime-local `metadata.json` (gitignored per
Always-On Rule #9).

**Source-specific schema contract.**

The cached World Bank PIP export carries 11 documented required
columns: `country_code` / `country_name` / `year` /
`reporting_level` / `welfare_type` / `poverty_line` /
`headcount` / `poverty_gap` / `gini` / `version_id` /
`ppp_version`. The raw-read layer
parses the cached CSV via the Python `csv` module (or the JSON
parser for the JSON fallback), validates the parsed header
against the 11 canonical required columns, and raises
`WorldBankPipSchemaError` BEFORE the transform layer consumes
the frame; the transform layer does NOT silently emit partial
output on a schema contract violation. Runtime metadata must
also declare `version_id` and `ppp_version`, and every parsed
row's `version_id` / `ppp_version` cells must match the
metadata's canonical supported basis; missing, mismatched, or
mixed PIP version / PPP bases fail before transform so
observations cannot be mislabeled across PIP releases. Optional
columns (`ppp_base_year` / `survey_year` /
`survey_comparability` / `notes`) are preserved on the parsed
row payload when the cached header declares them; the transform
never invents a value from missing source-native data.

**Source-specific observation family.**

The unified adapter emits ONE observation family
(`poverty_inequality_country_year`) with 3 source-native
catalog indicators (one per numeric indicator cell typically
exposed by the canonical PIP CSV / JSON export):

- `world_bank_poverty_inequality_platform_poverty_headcount_ratio`
  -- the poverty headcount ratio at the row's poverty line.
  Preserved verbatim on
  `extension["world_bank_poverty_inequality_platform_poverty_line_raw"]`.
- `world_bank_poverty_inequality_platform_poverty_gap` -- the
  poverty gap at the row's poverty line.
- `world_bank_poverty_inequality_platform_gini_index` -- the
  Gini index of the row's distribution.

The catalog deliberately does NOT include a default PPP factor
/ survey-year indicator beyond what the source-native CSV /
JSON explicitly exposes; the transform never invents a value
from missing source-native data.

Per-row emission produces 3 observations per cached row for the
default 3-indicator catalog (N rows x 3 indicators = 3N
observations).

**Source-specific coverage envelope + year semantics.**

PIP coverage is version-stamped and PPP / survey / welfare-type
specific. The descriptor advertises a broad 1960-2024 envelope
(PIP records typically begin in the early 1960s when
survey-based poverty estimates become available for low /
lower-middle income countries; the canonical probe stamp is
2021 for the `20260324_2021` PIP version with a few extrapolation
cells into 2024 for a handful of countries). The readiness
envelope surfaces a structured `YEAR_ABSENT` warning on
out-of-coverage year requests (e.g. `years=(2050,)` -- well
beyond the canonical envelope) per SRC-COV-002 / SRC-COV-003
(no stale-proxy fill). The prototype's target year 2023 falls
WITHIN the canonical envelope so 2023 is in-coverage; the
transform emits zero observations for an out-of-coverage year
request without silently proxying to the nearest in-coverage
year.

**Source-specific leader-filter semantics.**

The World Bank PIP dataset is a country-year poverty /
inequality source, NOT leader-identity evidence. The readiness
envelope surfaces a structured `UNSUPPORTED_FILTER` warning on
`leaders=` (SRC-REQ-005) -- the runner ignores the filter and
still emits the cached rows; the unified adapter never invents
leader values.

**Source-specific ISO3 caveat.**

The cached World Bank PIP CSV / JSON row carries a 3-character
`country_code` column that LOOKS LIKE ISO3 but is the World
Bank's own reporting identifier (NOT a canonical ISO3 mapping
introduced by the project). The unified adapter preserves the
source-native `country_code` verbatim on the audit-trail
extension payload
(`extension["world_bank_poverty_inequality_platform_country_code_raw"]`)
and does NOT assume the source identifier is a canonical ISO3
even when it resembles one. The `country_code` field on
emitted observations remains `None` until later matching /
resolution stages introduce a canonical ISO3 mapping.

**Source-specific attribution + version / PPP caveat.**

The descriptor's `coverage_hint.notes` carries the explicit
caveat that PIP poverty / inequality estimates are SURVEY- and
PPP-specific and SHOULD NOT be silently mixed across PIP
version stamps (e.g. `20260324_2021` vs `20260324_2017`) or PPP
bases (2021 PPP vs 2017 PPP) without explicit metadata
propagation. Downstream scorers MUST NOT silently treat a PIP
cell as comparable across version stamps or PPP bases without
explicit metadata propagation; the Stage 11 confidence
formula penalises the temporal-fit gap between the cached PIP
version release date and the prototype's target year. The
canonical attribution text ``"World Bank (2025) Poverty and
Inequality Platform (version {version_ID}) [Data set] World
Bank Group, www.pip.worldbank.org."`` is byte-identical to
the ``world_bank_poverty_inequality_platform`` row in
``docs/sources/attributions.md`` (Always-On Rule #15); the
``{version_ID}`` placeholder is interpolated at observation
emission time from the canonical PIP version stamp. The
canonical version stamp
``"World Bank PIP, version 20260324_2021"`` propagates
consistently to ``RawAsset.version`` and every emitted
``NormalizedObservation.source_version``. No legacy
``STAGE2_ADAPTERS["world_bank_poverty_inequality_platform"]``
entry exists (no legacy Stage 2 implementation); the new
package exposes explicit
``create_world_bank_poverty_inequality_platform_adapter()`` and
``register_world_bank_poverty_inequality_platform(registry)``
factories and does NOT auto-register on import (per
``docs/architecture/sources.md`` §10.1).

**Source-specific test surface.**

The focused tests in
`tests/sources/test_world_bank_poverty_inequality_platform_adapter.py`
cover: descriptor / factory / registry / public surface (4
tests); the canonical 3-indicator catalog + 11 required
columns, including required ``version_id`` / ``ppp_version``
release-basis fields (2 tests); the attribution-text drift guard (2 tests);
the readiness-failure matrix (6 readiness-blocker cases via
parametrize + cache-policy gate + unsupported-version blocker
+ unsupported-leaders-filter advisory warning); the year
semantics (out-of-coverage year emits zero observations +
advisory `YEAR_ABSENT` warning; in-coverage year emits the row
set; `years=None` emits the in-coverage observation set; the
prototype's target year 2023 is in-coverage); the country
filter (single match, no-match, multiple matches,
source-native display name); the blank / non-numeric cell
sentinel path (`value_type='missing'` plus the verbatim raw
cell text); the observation shape (source-native country code
+ display name preserved verbatim + no ISO3 invention +
raw_locators + transform_locators + attribution text with
`{version_ID}` interpolation); the per-row PPP version +
reporting level + welfare type + poverty line + version_id
audit-trail preservation; the schema-error path
(`WorldBankPipSchemaError` for missing required columns); the
import-boundary contract (no `leaders_db.ingest` leak); the
no-network boundary (HTTP / socket sentinels never invoked);
the duplicate-slug `ValueError` registration guard
(SRC-REG-004); the JSON fallback contract (the raw-read
boundary loads the JSON fallback when the CSV is absent and
parses the array via the built-in JSON parser); the
selected-file contract (the actually-present SELECTED cache
file is declared in `metadata.local_files` AND covered by
`metadata.checksum_sha256`); and the observation-id
uniqueness invariant (per-row + per-indicator). The synthetic
CSV / JSON fixture is built by
`tests/fixtures/world_bank_poverty_inequality_platform/build_sample_csv.py`
(6 hand-authored synthetic country-year rows; the country
labels and numeric cells are NOT real World Bank PIP data per
the task brief: "prefer synthetic non-real country labels if
it tests parser mechanics without factual assertions").

The `tests/sources/test_import_boundary.py` canonical
submodule list now includes
`leaders_db.sources.adapters.world_bank_poverty_inequality_platform`.

**Skipped candidates (deferred to a later slice).**

Three other ``docs/architecture/sources.md`` §7.2 rows were
considered for this slice and intentionally skipped /
recorded here so future work can pick them up with explicit
source-shape / access design:

- ``ctbto_nuclear_tests`` -- CTBTO nuclear-test records /
  monitoring statements. The CTBTO event / monitoring data is
  gated / contractual or narrative, not a stable public event
  table for this slice. Requires source-shape design (event
  taxonomy: actual nuclear tests vs monitoring statements vs
  component tests; the ``docs/sources/ingestion-plan.md``
  §``ctbto_nuclear_tests`` row already flagged this blocker).
- ``csis_missile_threat`` -- CSIS Missile Threat. Narrative
  country / missile profiles; risk of over-interpreting
  capability. Requires capability / test-event indicators and
  locators design per
  ``docs/sources/ingestion-plan.md`` §``csis_missile_threat``.
- ``cns_nti_missile_launches`` -- CNS / NTI Missile and SLV
  Launch Databases. NTI-adjacent access risk (the canonical
  ``nti`` slug is Cloudflare-blocked per the workplan Done
  History); requires source-specific design per
  ``docs/sources/ingestion-plan.md`` §``cns_nti_missile_launches``.

These three rows remain in §7.2 as ``future`` / ``blocked``
future work; they were NOT implemented in this slice because
the source-shape / access design is ambiguous and the PIP
dataset was the cleanest documented public event / indicator
table for a low-risk offline / cache-first adapter.

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
   implements the full `SourceAdapter` Protocol and uses a cache-only
    read path in the unified adapter package; the legacy HTTP flow
    is not consulted for supported policies. Legacy imports from
   `leaders_db.ingest.wdi_io` are limited to lazy catalog-resolution
   and attribution compatibility seams, so the package import does
   NOT pull in `leaders_db.ingest`
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
       (`_read_cached_wdi_responses` in `_cache_reader.py`,
       re-exported from `_transform.py` for compatibility, and
       `_enumerate_cache_files` in `_readiness.py`) that reads staged
       per-(year, indicator) JSON cache files directly. For compatibility,
       legacy imports are used only for catalog-attribution wiring, not
       for no-network parsing or read execution flow.
      For `years=None`
     the readiness gate enumerates the cache root and refuses
to dispatch if any discovered cache file is malformed (to preserve
the cache-only contract);
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
 7. **Fourth clean-source migration landed (2026-06-25) — World Bank WGI under
    `src/leaders_db/sources/adapters/world_bank_wgi/`.** WGI is
    the fourth source rebuilt under the new
    `leaders_db.sources` interface (docs/architecture/sources.md
    §7.1 priority 4, docs/requirements/sources.md §12 SRC-MIG-005),
    after PWT 10.01, Maddison Project Database 2023, and World
    Bank WDI. WGI is a local-file source (single xlsx, 6
    indicator sheets, no network) so the unified adapter is
    no-network by design (`requires_network=False`); the
    descriptor advertises
    `source_type="dataset"`. The new package implements the
    full `SourceAdapter` Protocol and reuses the legacy reader
    under `leaders_db.ingest.wgi_xlsx` via lazy imports so the
    package import does NOT pull in `leaders_db.ingest`
    (`tests/sources/test_world_bank_wgi_adapter.py::test_wgi_adapter_module_does_not_import_legacy_ingest_at_import`
    + the import-boundary submodule list in
    `tests/sources/test_import_boundary.py`). The legacy
    `STAGE2_ADAPTERS["world_bank_wgi"]` entry remains
    unchanged -- the new package exposes explicit
    `create_world_bank_wgi_adapter()` /
    `register_world_bank_wgi(registry)` factories and does
    NOT auto-register on import (per docs/architecture/sources.md
    §10.1). The new adapter honors the full request scope:
    `years=` and `countries=` filter the wide-format DataFrame
    on the new transform side (the legacy reader returns the
    full frame when called with `year=None`); `leaders=`
    emits a structured `UNSUPPORTED_FILTER` warning
    (SRC-REQ-005); `years=` outside the documented 1996-2022
    coverage envelope emits zero observations plus a
    structured `YEAR_ABSENT` warning -- no stale-proxy fill
    (SRC-COV-002 / SRC-COV-003). A mismatched
    `source_version=` (e.g. `"9999"` against a canonical WGI
    bundle whose metadata records `"Worldwide Governance
    Indicators 2023 Update (data through 2022)"`) FAILS
    readiness with a structured `unsupported_version` error
    per docs/requirements/sources.md §3 SRC-REQ-009 -- the
    runner raises `RuntimeError` before calling `read_raw` /
    `transform`, so the legacy bundle metadata cannot be
    silently overwritten by an unsupported version stamp. The
    runner also validates the staged bundle's metadata
    `version` / `source_version`: missing or mismatched
    metadata versions fail readiness, and the canonical
    `"Worldwide Governance Indicators 2023 Update (data
    through 2022)"` value propagates consistently to
    `RawAsset.version` and every emitted
    `NormalizedObservation.source_version`. The readiness
    gate accepts BOTH the canonical primary metadata shape
    (`source_version` / `checksum_sha256` / `local_files` /
    `license_note` / `coverage`) AND the staged WGI legacy
    shape (`version` / `sha256` / `local_file` / `license` /
    `coverage_start_year` + `coverage_end_year`) so the
    existing staged bundle metadata does not need to be
    rewritten as part of the migration. The runner
    end-to-end contract is proven by
    `tests/sources/test_world_bank_wgi_adapter.py::test_wgi_runner_produces_normalized_observations`
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
    `attribution_key="world_bank_wgi"`, coverage hint
    1996-2022, and the `governance_country_year` observation
    family. Per-observation `RawLocator` carries the xlsx
    path + the per-indicator sheet name (e.g.
    `VoiceandAccountability` for `wgi_voice_and_accountability`);
    `row_number` is intentionally `None` because the legacy
    wide frame loses the xlsx row index through the long-to-wide
    pivot -- the unified transform never fabricates locators.
    Per-observation `extension` carries the canonical
    attribution text (Rule #15), the
    `source_row_reference="world_bank_wgi:<iso3>"` pattern
    (matching the legacy Stage 2 DB writer), the
    `wgi_sheet_name` (canonical xlsx sheet name), and the
    `wgi_indicator_category` (catalog `rating_category`,
    `effectiveness` for 5 indicators + `integrity` for
    `wgi_control_of_corruption`). The runner still returns
    `manifest=None`; no persistence, DB writes, or manifest
    writing landed. The package exposes explicit
    `create_world_bank_wgi_adapter()` /
    `register_world_bank_wgi(registry)` factories and does
    NOT auto-register on import (§10.1). The next migration
    slice candidates are V-Dem (priority 5), per
    docs/architecture/sources.md §7.1.
  8. **Fifth clean-source migration landed (2026-06-25) — V-Dem v16 under
     `src/leaders_db/sources/adapters/vdem/`.** V-Dem is
     the fifth source rebuilt under the clean
     `leaders_db.sources` interface
     (docs/architecture/sources.md §7.1 priority 5,
     docs/requirements/sources.md §12 SRC-MIG-005), after
     PWT 10.01, Maddison Project Database 2023, World Bank
     WDI, and World Bank WGI. V-Dem is a large local CSV
     source (388MB / 28093 rows / 4618 columns) with
     `metadata.json` and a 26MB zip; it is **not**
     network-backed in the unified adapter
     (`requires_network=False`). The descriptor advertises
     `source_type="dataset"`. The new package implements
     the full `SourceAdapter` Protocol (`descriptor` +
     `check_ready` + `read_raw` + `transform`) and reuses
     the legacy reader / transform / catalog under
     `leaders_db.ingest.vdem_io` via lazy imports so the
     package boundary documented in
     docs/architecture/sources.md §10.1 is preserved; the
     package import does NOT pull in `leaders_db.ingest`
     (`tests/sources/test_vdem_adapter.py::test_vdem_adapter_module_does_not_import_legacy_ingest_at_import`
     + the import-boundary submodule list in
     `tests/sources/test_import_boundary.py`). The legacy
     `STAGE2_ADAPTERS["vdem"]` entry remains unchanged --
     the new package exposes explicit
     `create_vdem_adapter()` /
     `register_vdem(registry)` factories and does NOT
     auto-register on import (per docs/architecture/sources.md
     §10.1). The new adapter honors the full request scope:
     `years=` and `countries=` filter the narrow DataFrame
     on the new transform side (the legacy reader returns
     the full frame when called with `year=None`); `leaders=`
     emits a structured `unsupported_filter` warning
     (SRC-REQ-005); `years=(1788,)` or `years=(2026,)`
     (out of coverage) emit zero observations plus a
     structured `year_absent` warning -- no stale-proxy fill
     (SRC-COV-002 / SRC-COV-003). A mismatched `source_version=`
     (e.g. `"9999"` against a canonical V-Dem bundle whose
     metadata records `"v16"`) FAILS readiness with a
     structured `unsupported_version` error per
     docs/requirements/sources.md §3 SRC-REQ-009 -- the
     runner raises `RuntimeError` before calling
     `read_raw` / `transform`, so the legacy bundle metadata
     cannot be silently overwritten by an unsupported version
     stamp. The runner also validates the staged bundle's
     metadata `source_version`: missing or mismatched
     metadata versions fail readiness, and the canonical
     `"v16"` value propagates consistently to
     `RawAsset.version` and every emitted
     `NormalizedObservation.source_version`. The bundle
     metadata's `checksum_sha256` is REQUIRED and accepts
     a 64-character hex SHA-256 string (covers the staged
     **zip**, NOT the 388MB CSV). The gate validates the
     metadata shape AND, if the zip is staged alongside the
     CSV, recomputes the zip's SHA-256 and compares against
     the metadata field. Missing / malformed
     `checksum_sha256` fails readiness with a structured
     `missing_metadata` error; a mismatched zip SHA-256
     fails readiness with the V-Dem-specific
     `vdem_checksum_mismatch` code. The CSV (388MB) is
     NEVER hashed by the unified adapter -- the audit chain
     is preserved via the legacy parquet metadata, the
     canonical attribution text (Rule #15), and the
     zip-checksum match. The runner end-to-end contract is
     proven by
     `tests/sources/test_vdem_adapter.py::test_vdem_runner_produces_normalized_observations`
     (220 fixture observations round-tripped -- 5 countries
     x 2 years x 22 indicators) and
     `test_vdem_runner_does_not_consult_legacy_stage2_adapters`
     (monkeypatched legacy `STAGE2_ADAPTERS["vdem"]` tracker
     is never invoked). The V-Dem descriptor exposes
     `source_id="vdem"`, `default_version="v16"`, the
     canonical V-Dem DOI homepage URL
     (`https://doi.org/10.23696/vdemds26`),
     `attribution_key="vdem"`, coverage hint 1789-2025,
     five observation families
     (`political_country_year`,
     `governance_country_year`,
     `corruption_country_year`,
     `repression_country_year`,
     `social_country_year`), `source_type="dataset"`, and
     `requires_network=False`. Per-observation
     `RawLocator` carries the staged CSV path + the raw
     V-Dem column name (e.g. `v2x_polyarchy`); `row_number`
     is intentionally `None` because the legacy narrow
     frame loses the CSV row index through the long-to-wide
     pivot -- the unified transform never fabricates
     locators. Per-observation `extension` carries the
     canonical attribution text (Rule #15), the
     `source_row_reference="vdem:<country_text_id>"`
     pattern (matching the legacy Stage 2 DB writer), the
     `vdem_raw_column`, `vdem_country_id`,
     `vdem_country_text_id`, `vdem_rating_category`
     (catalog `rating_category`), `raw_value` (audit-trail
     string preserving V-Dem missing sentinels), and the
     `raw_scale` / `higher_is_better` /
     `normalized_scale_target` direction hints. The new
     `VDEM_ATTRIBUTION_TEXT` constant is byte-identical
     to the legacy `VDEM_ATTRIBUTION` constant in
     `src/leaders_db/ingest/vdem_io.py` and to the
     `vdem` section in `docs/sources/attributions.md`;
     `test_vdem_attribution_text_matches_attributions_doc`
     enforces byte-identity (drift guard). 25 focused
     tests in `tests/sources/test_vdem_adapter.py` cover
     the full slice acceptance criteria (descriptor /
     factory / registry / runner / request-scoping /
     out-of-coverage / readiness-failure /
     checksum-shape / checksum-mismatch / correct-zip /
     canonical-version-propagation / V-Dem-specific
     extension / import-boundary / STAGE2_ADAPTERS-no-touch).
     Module sizes: `__init__.py` 148 lines,
     `_descriptor.py` 235 lines, `_metadata_validators.py`
     326 lines, `_readiness.py` 308 lines, `_catalog.py`
     114 lines, `_missing_values.py` 129 lines,
     `_raw_read.py` 160 lines, `_pipeline.py` 165 lines,
     `_transform.py` 319 lines, and `adapter.py` 359 lines;
     no V-Dem production-module carve-out is needed.
     **With V-Dem landed, the unified source interface
     now covers the last structured source needed for a
     complete 1900-2026 inquiry** (PWT + Maddison =
     historical economy; WDI = current economy; WGI =
     governance; V-Dem = political regime /
     repression / corruption / social well-being). The
     next major milestone is a vertical slice of an
     investigation that runs from the migrated source
     adapters through `InMemoryEvidenceRepository`,
     semantic concepts / evidence bundles, scoring or
     analysis logic, and a documented answer with
     provenance. The runner still returns `manifest=None`;
     no persistence, DB writes, or manifest writing
landed. The package exposes explicit
     `create_vdem_adapter()` /
     `register_vdem(registry)` factories and does NOT
     auto-register on import (§10.1).
   9. **Sixth clean-source migration landed (2026-06-25) — UCDP GED 23.1 under
      `src/leaders_db/sources/adapters/ucdp/`.** UCDP is
      the sixth source rebuilt under the clean
      `leaders_db.sources` interface
      (docs/architecture/sources.md §7.1 priority 11,
      docs/requirements/sources.md §12 SRC-MIG-005),
      after PWT 10.01, Maddison Project Database 2023,
      World Bank WDI, World Bank WGI, and V-Dem. UCDP is
      structurally distinct from the prior five
      clean-source migrations: PWT / Maddison / WDI / WGI
      / V-Dem are country-year tables, while UCDP GED is
      an **event-level** dataset (316,818 events in
      v23.1) shipped as a 25.4 MB zip with one 218 MB
      CSV. The unified adapter aggregates events to
      country-year by `type_of_violence` (1 =
      state-based, 3 = one-sided) and the cross-border
      filter (`type=1 AND gwnob.notna()` for the
      internationalized subset) before the long-to-wide
      pivot. UCDP is local-file only (no HTTP layer in
      the new package; `requires_network=False`); the
      descriptor advertises `source_type="dataset"`. The
      new package implements the full `SourceAdapter`
      Protocol (`descriptor` + `check_ready` +
      `read_raw` + `transform`) and reuses the legacy
      reader / event-level aggregator under
      `leaders_db.ingest.ucdp_io` and
      `leaders_db.ingest.ucdp_aggregate` via lazy
      imports so the package boundary documented in
      docs/architecture/sources.md §10.1 is preserved;
      the package import does NOT pull in
      `leaders_db.ingest`
      (`tests/sources/test_ucdp_adapter.py::test_ucdp_adapter_module_does_not_import_legacy_ingest_at_import`
      + the import-boundary submodule list in
      `tests/sources/test_import_boundary.py`). The
      legacy `STAGE2_ADAPTERS["ucdp"]` entry remains
      unchanged -- the new package exposes explicit
      `create_ucdp_adapter()` / `register_ucdp(registry)`
      factories and does NOT auto-register on import
      (per docs/architecture/sources.md §10.1). The
      request `countries=` filter applies as an exact
      match against the UCDP `country_id` integer (NOT
      ISO3) -- callers who want to filter by ISO3 must
      use the legacy path or Stage 3 country match to
      resolve first; `leaders=` emits a structured
      `unsupported_filter` warning; `years=(2023,)` or
      `years=(1988,)` (out of coverage) emit zero
      observations plus a structured `year_absent`
      warning -- no stale-proxy fill (SRC-COV-002 /
      SRC-COV-003). A mismatched `source_version=` (e.g.
      `"9999"` against a canonical UCDP bundle whose
      metadata records `"GED 23.1"`) FAILS readiness
      with a structured `unsupported_version` error per
      docs/requirements/sources.md §3 SRC-REQ-009 -- the
      runner raises `RuntimeError` before calling
      `read_raw` / `transform`, so the legacy bundle
      metadata cannot be silently overwritten by an
      unsupported version stamp. The runner also
      validates the staged bundle's metadata
      `source_version`: missing or mismatched metadata
      versions fail readiness, and the canonical
      `"GED 23.1"` value propagates consistently to
      `RawAsset.version` and every emitted
      `NormalizedObservation.source_version`. The
      bundle metadata's `checksum_sha256` accepts the
      canonical empty-bundle shape (`null` paired with
      `ingestion_status="pending"`, the staged
      `data/raw/ucdp/metadata.json` shape) OR a
      64-character hex SHA-256 string (when the zip is
      staged). A non-null, non-hex-64-character
      `checksum_sha256` fails readiness with a
      structured `missing_metadata` error; a mismatched
      zip SHA-256 fails readiness with the UCDP-specific
      `ucdp_checksum_mismatch` code. The zip is hashed only
      for local integrity verification when metadata supplies
      a checksum; the audit chain is preserved via the canonical
      attribution text (Rule #15). The runner end-to-end contract is
      proven by
      `tests/sources/test_ucdp_adapter.py::test_ucdp_runner_produces_normalized_observations`
      (60 fixture observations round-tripped -- 5
      countries x 2 years x 6 indicators after
      event-level aggregation of the 22-event fixture)
      and
      `test_ucdp_runner_does_not_consult_legacy_stage2_adapters`
      (monkeypatched legacy `STAGE2_ADAPTERS["ucdp"]`
      tracker is never invoked). The UCDP descriptor
      exposes `source_id="ucdp"`, `default_version="GED
      23.1"`, the canonical UCDP downloads page
      (`https://ucdp.uu.se/downloads/`),
      `attribution_key="ucdp"`, coverage hint 1989-2022,
      two observation families
      (`international_peace_country_year` for the 4
      state-based indicators +
      `domestic_violence_country_year` for the 2
      one-sided indicators), `source_type="dataset"`,
      and `requires_network=False`. Per-observation
      `RawLocator` carries the staged zip path + the
      catalog `variable_name` (e.g.
      `ucdp_state_based_events`); `row_number` is
      intentionally `None` because UCDP is event-level
      data and the legacy wide frame loses the event row
      index through the long-to-wide pivot -- the
      unified transform never fabricates locators. The
      per-observation `quality_flags` carries the
      `ucdp_aggregated_from_events` flag so downstream
      audit code can recognize the aggregate locator
      convention. Per-observation `extension` carries
      the canonical UCDP attribution text (Rule #15),
      the `source_row_reference="ucdp:<country_id>"`
      pattern (matching the legacy Stage 2 DB writer),
      the `ucdp_country_id`, `ucdp_rating_category`,
      `ucdp_raw_column`, `ucdp_filter_logic`, the
      `ucdp_events_total` / `ucdp_events_filtered`
      (carried from `df.attrs` onto every observation),
      `raw_value` (audit-trail string), and the
      `raw_scale` / `higher_is_better` /
      `normalized_scale_target` direction hints. The
      new `UCDP_ATTRIBUTION_TEXT` constant is
      byte-identical to the legacy `UCDP_ATTRIBUTION`
      constant in `src/leaders_db/ingest/ucdp_io.py` and
      to the `ucdp` section in
      `docs/sources/attributions.md`;
      `test_ucdp_attribution_text_matches_attributions_doc`
      enforces byte-identity (drift guard). 28 focused
      tests in `tests/sources/test_ucdp_adapter.py`
      cover the full slice acceptance criteria
      (descriptor / factory / registry / runner /
      request-scoping / out-of-coverage /
      readiness-failure / unsupported-version /
      metadata-only-bundle-not-runner-ready /
      runner-short-circuit-on-missing-zip /
      canonical-version-propagation / ISO3-vs-country-id
      / aggregate-locator-quality-flag / rule-id-pattern
      / indicator-codes / import-boundary /
      STAGE2_ADAPTERS-no-touch). Module sizes:
      `__init__.py` 180 lines, `_descriptor.py` 231
      lines, `_metadata_validators.py` 400 lines,
      `_readiness.py` 332 lines, `_catalog.py` 136
      lines, `_constants.py` 35 lines,
      `_missing_values.py` 81 lines,
      `_observation_builder.py` 249 lines, `_raw_read.py`
      208 lines, `_pipeline.py` 197 lines,
      `_transform.py` 230 lines, and `adapter.py` 394
      lines; no UCDP production-module carve-out is
      needed. The UCDP unified path is local-file only
      (`requires_network=False`, no HTTP layer in the
      new package); the canonical bundle metadata
      ships with `local_files=[]` / `checksum_sha256=null`
      / `ingestion_status="pending"` -- a deliberately
      minimal shape so the operator can update the
      metadata once the zip is staged. The mandatory
      readiness requirement is on raw-file presence:
      the gate returns `ready=False` with a structured
      `missing_raw` error if `ged231-csv.zip` is not
      staged on disk, regardless of the metadata's
      `local_files` / `checksum_sha256` shape. A
      metadata-only bundle (no staged zip) is
      intentionally NOT runner-ready -- the runner
      raises `RuntimeError` BEFORE `read_raw` /
      `transform`. The metadata-only bundle still has
      value for readiness-only inspection (validating
      metadata shape, schema migrations, sanity-checking
      `expected_local_files` annotations) but the
      readiness envelope is NOT ready until the zip is
      staged. The new package does NOT implement
      manifest writing, processed-file persistence, or
      DB writes; the runner still returns
      `manifest=None`. The package exposes
      explicit `create_ucdp_adapter()` /
      `register_ucdp(registry)` factories and does NOT
      auto-register on import (§10.1). **With UCDP
      landed, the unified source interface now covers
the first event-level source family** (PWT +
      Maddison = historical economy; WDI = current
      economy; WGI = governance; V-Dem = political
      regime / repression / corruption / social
      well-being; UCDP = organized conflict / one-sided
      violence -- event-level aggregations to
      country-year).
   9a. **Seventh clean-source migration landed
      (2026-06-26) -- Transparency International CPI 2023
      under `src/leaders_db/sources/adapters/transparency_cpi/`.**
      CPI is the seventh source rebuilt under the clean
      ``leaders_db.sources`` interface
      (docs/architecture/sources.md section 7.1 priority
      6, docs/requirements/sources.md section 12
      SRC-MIG-005), after PWT 10.01, Maddison Project
      Database 2023, World Bank WDI, World Bank WGI,
      V-Dem, and UCDP. CPI is a country-year corruption
      / integrity source (180 countries, 1995-2023);
      the canonical TI xlsx download is CDN-gated per
      docs/sources/vetting/report.md section 3.6, so the
      canonical per-year CSV is the OCHA HDX-mirrored
      verbatim Transparency International release. The
      unified adapter is local-file only
      (``requires_network=False``, no HTTP layer in the
      new package); the descriptor advertises
      ``source_type="dataset"``. The new package
      implements the full ``SourceAdapter`` Protocol
      (``descriptor`` + ``check_ready`` + ``read_raw`` +
      ``transform``) and reuses the legacy reader /
      transform under
      ``leaders_db.ingest.transparency_cpi_csv`` via
      lazy imports so the package boundary documented in
      docs/architecture/sources.md section 10.1 is
      preserved; the package import does NOT pull in
      ``leaders_db.ingest``
      (``tests/sources/test_transparency_cpi_adapter.py::test_transparency_cpi_adapter_module_does_not_import_legacy_ingest_at_import``
      + the import-boundary submodule list in
      ``tests/sources/test_import_boundary.py``). The
      legacy ``STAGE2_ADAPTERS["transparency_cpi"]``
      entry remains unchanged -- the new package exposes
      explicit ``create_transparency_cpi_adapter()`` /
      ``register_transparency_cpi(registry)`` factories
      and does NOT auto-register on import (per
      docs/architecture/sources.md section 10.1). The
      request ``years=`` and ``countries=`` filters are
      applied to the wide-format DataFrame after the
      legacy read (the unified adapter always reads the
      canonical 2023 CSV -- ``transparency_cpi_2023.csv``
      -- matching the staged bundle's
      ``local_files`` annotation; the year filter is
      applied on the wide frame so out-of-coverage year
      requests still pass readiness and the transform
      emits zero observations plus a structured
      ``YEAR_ABSENT`` warning per offending year, with
      no stale-proxy fill per SRC-COV-002 /
      SRC-COV-003). ``leaders=`` emits a structured
      ``unsupported_filter`` warning per SRC-REQ-005.
      A mismatched ``source_version=`` (e.g.
      ``"CPI 2024"`` against a canonical CPI 2023 bundle
      whose metadata records ``"CPI 2023"``) FAILS
      readiness with a structured ``unsupported_version``
      error per docs/requirements/sources.md section 3
      SRC-REQ-009 -- the runner raises ``RuntimeError``
      before calling ``read_raw`` / ``transform``, so
      the legacy bundle metadata cannot be silently
      overwritten by an unsupported version stamp. The
      runner also validates the staged bundle's
      metadata ``source_version``: missing or
      mismatched metadata versions fail readiness, and
      the canonical ``"CPI 2023"`` value propagates
      consistently to ``RawAsset.version`` and every
      emitted ``NormalizedObservation.source_version``.
      The canonical bundle metadata
      (``data/raw/transparency_cpi/metadata.json``)
      ships with ``checksum_sha256=null`` (matching the
      legacy bundle shape) -- the readiness gate
      validates the metadata shape AND, when a non-null
      SHA-256 is staged, recomputes the CSV's SHA-256
      and compares against the metadata field; a
      mismatched CSV SHA-256 fires the module-local
      ``transparency_cpi_checksum_mismatch`` error
      code. The mandatory readiness requirement is on
      raw-file presence: the gate returns ``ready=False``
      with a structured ``missing_raw`` error when the
      per-year CSV is not staged on disk, regardless of
      the metadata's ``local_files`` /
      ``checksum_sha256`` shape; a metadata-only bundle
      is intentionally NOT runner-ready so the runner
      raises ``RuntimeError`` BEFORE ``read_raw`` /
      ``transform``. The runner end-to-end contract is
      proven by
      ``tests/sources/test_transparency_cpi_adapter.py::test_transparency_cpi_runner_produces_normalized_observations``
      (5 fixture observations round-tripped -- 5
      countries x 1 year x 1 indicator
      ``cpi_score``) and
      ``test_transparency_cpi_runner_does_not_consult_legacy_stage2_adapters``
      (monkeypatched legacy
      ``STAGE2_ADAPTERS["transparency_cpi"]`` tracker
      is never invoked) plus
      ``test_transparency_cpi_runner_does_not_invoke_network``
      (HTTP sentinels on the legacy fetcher and
      ``requests.get`` are never invoked). The CPI
      descriptor exposes ``source_id="transparency_cpi"``,
      ``default_version="CPI 2023"``, the canonical TI
      CPI 2023 homepage URL
      (``https://www.transparency.org/en/cpi/2023``),
      ``attribution_key="transparency_cpi"``, coverage
      hint 1995-2023, single observation family
      ``integrity_country_year``,
      ``source_type="dataset"``, and
      ``requires_network=False``. Per-observation
      ``RawLocator`` carries the staged CSV path + the
      catalog ``raw_column`` (``score``) + the
      positional row index in the wide frame (the legacy
      reader sorts by iso3 ascending for deterministic
      idempotency, so the row index is preserved
      byte-for-byte with the input CSV). Per-observation
      ``extension`` carries the canonical CPI
      attribution text (Rule #15), the
      ``source_row_reference="transparency_cpi:score:<iso3>"``
      pattern (matching the legacy Stage 2 DB writer),
      the ``transparency_cpi_iso3`` / ``cpi_country_name``
      / ``cpi_region`` audit-trail labels, the per-row
      confidence fields ``cpi_rank`` / ``cpi_sources`` /
      ``cpi_standard_error`` / ``cpi_lower_ci`` /
      ``cpi_upper_ci``, and the ``raw_scale`` /
      ``higher_is_better`` /
      ``normalized_scale_target`` direction hints
      (``higher_is_better=True`` because a higher CPI
      score = cleaner perception = better). The new
      ``TRANSPARENCY_CPI_ATTRIBUTION_TEXT`` constant is
      byte-identical to the legacy
      ``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
      ``src/leaders_db/ingest/transparency_cpi_io.py`` and
      to the ``transparency_cpi`` section in
      ``docs/sources/attributions.md``;
      ``test_transparency_cpi_attribution_text_matches_attributions_doc``
      enforces byte-identity (drift guard). Mirror vs.
      publisher attribution is documented in
      ``docs/sources/attributions.md`` transparency_cpi
      section: the report-facing attribution block names
      Transparency International CPI 2023 (the canonical
      publisher name), NOT the OCHA HDX mirror (which is
      the durable CSV provenance path documented
      separately in the bundle metadata's
      ``hdx_mirror_url`` field). The CPI unified path
      is local-file only (``requires_network=False``, no
      HTTP layer in the new package). The runner NEVER
      invokes the network. The readiness gate validates
      the staged ``transparency_cpi_2023.csv`` (mandatory
      raw-file presence -- a missing CSV fires
      ``missing_raw``) and the metadata checksum /
      version / license / coverage fields BEFORE
      ``read_raw`` / ``transform`` are called. 30 focused
      tests in
      ``tests/sources/test_transparency_cpi_adapter.py``
      cover the full slice acceptance criteria
      (descriptor / factory / registry / runner /
      request-scoping / out-of-coverage /
      readiness-failure / unsupported-version /
      metadata-only-bundle-not-runner-ready /
      runner-short-circuit-on-missing-csv /
      canonical-version-propagation /
      checksum-shape / checksum-mismatch /
      correct-checksum-match / per-row audit-trail /
      attribution-drift-guard / indicator-code /
      raw-locator-row-index / direction-hints /
      no-network / import-boundary /
      STAGE2_ADAPTERS-no-touch). Module split: each
      production module stays under the documented
      400-line convention; ``adapter.py`` owns the
      lifecycle class + registration helpers + protocol
      conformance guard, ``_descriptor.py`` owns the
      canonical constants + ``build_transparency_cpi_descriptor``
      factory, ``_catalog.py`` owns the lazy legacy
      catalog loader + rating-category mapping,
      ``_readiness.py`` + ``_metadata_validators.py`` own
      the readiness gate (orchestrator + per-field
      validators), ``_missing_values.py`` owns the
      per-cell coercion helpers, ``_observation_builder.py``
      owns the per-row ``NormalizedObservation``
      construction helper, ``_raw_read.py`` owns the
      raw-read orchestration, ``_pipeline.py`` owns the
      transform-pipeline orchestration (year / country
      filter), and ``_transform.py`` owns the per-row
      emission loop. Run ``wc -l
      src/leaders_db/sources/adapters/transparency_cpi/*.py``
      for the current counts; the comprehensive module
      docstrings explain the mirror vs. publisher
      attribution contract for the audit trail. The runner
      still returns ``manifest=None``; no persistence,
      DB writes, or manifest writing landed. The package
      exposes explicit ``create_transparency_cpi_adapter()``
      / ``register_transparency_cpi(registry)`` factories
      and does NOT auto-register on import (section
      10.1). **With CPI landed, the unified source
      interface now covers the perception-based
      integrity sub-signal** (PWT + Maddison = historical
      economy; WDI = current economy; WGI = governance;
      V-Dem = political regime / repression / corruption /
      social well-being; UCDP = organized conflict /
      one-sided violence; CPI = corruption perceptions).
      Together with V-Dem's ``vdem_corruption`` subset
      and WGI's ``world_bank_wgi_corruption`` subset
      (both documented in section 7.5 as observation-
      family / catalog subsets under the parent
      adapters, not separate adapters), the integrity /
      corruption rating category is now fully covered by
      the unified source interface.

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
  `check_ready -> read_raw -> transform -> validate` lifecycle and returns a
  real `SourceIngestResult`. The runner never touches the legacy
  `STAGE2_ADAPTERS` table. When constructed without an engine, it remains
  side-effect free and returns `manifest=None`. When constructed with an engine,
  it rejects invalid observations, upserts valid rows through the shared SQL
  evidence store, writes processed observation artifacts, and writes a source-run
  manifest JSON under the request's `processed_root`.

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
| SRC-PERSIST-001 through SRC-PERSIST-007 | Package integration / SQLite + filesystem boundary | Construct `SourceIngestRunner(registry=..., engine=...)` with a fixture adapter; assert the run validates observations, persists one SQL row, writes a manifest, and an identical rerun does not duplicate rows. |
| SRC-QUERY-001 through SRC-QUERY-005 | Unit / query interface | Assert `EvidenceQuery` contains source/family/indicator/year/country/leader filters plus include flags; assert an `EvidenceRepository` fake can implement read-only query methods without invoking ingestion. |
| SRC-DEFAULT-001 through SRC-DEFAULT-007 | Package integration / static inspection | Assert package name is `leaders_db.sources`, default request output format is parquet, default cache policy is `prefer_cache`, no real adapter is registered by default, and `client_existing` is not auto-registered as evidence. |

Question check: could code pass these tests while failing in real use? For Phase
A, yes if only unit tests are written. Therefore Phase B must include the import
boundary and legacy compatibility package-integration checks above, and the first
real adapter phase must add filesystem/SQLite manifest proof before claiming the
source system works end to end.
