# Source Ingestion Plan

This document is the implementation backlog and interface plan for adding the remaining and future data-source ingestion paths. It complements [`data-sources.md`](data-sources.md), [`source-vetting/report.md`](source-vetting/report.md), and the Stage 2 source-location rules in [`architecture.md`](architecture.md#source-location-and-traceability-convention).

## Goals

1. Work **source by source**. Each source gets one isolated implementation slice, with its own proof, review, and documentation update before the next source starts.
2. Maximize separation. Source-specific parsing, locators, metadata, tests, and fixture data must not leak into generic orchestration, scoring, or other source adapters.
3. Standardize the connector contract. A generic Stage 2 runner should be able to call any source adapter through the same interface while still allowing source-specific readers for xlsx, csv, pdf, SPARQL, OData, SDMX, HTML, or manually staged files.
4. Preserve auditability. Every emitted observation must trace back to a raw file row, API record, table cell, page URL, statement id, or document locator.
5. Do not implement against guesses. A source with no vetted URL, no user-managed local file, no license note, or no `metadata.json` remains blocked until source hygiene is complete.

## Non-goals

- This plan does not replace the existing 19 implemented adapters immediately.
- This plan does not change the scoring formulas or confidence weights.
- This plan does not make narrative/manual sources equal to structured datasets. Narrative sources require cited-snippet extraction and separate review gates before they can influence scores.

## Proposed modular layout

The current code uses flat modules such as `src/leaders_db/ingest/wdi.py`, `wdi_io.py`, and `wdi_db.py`. New source work should move toward a per-source package layout:

```text
src/leaders_db/ingest/
├── registry.py                         # future canonical adapter registry
├── interfaces.py                       # shared protocols / result models
├── common/                             # generic helpers only
│   ├── artifacts.py                    # atomic parquet/csv/manifest writes
│   ├── metadata.py                     # metadata.json validation/loading
│   ├── observations.py                 # source_observations writer helpers
│   └── locators.py                     # shared locator validation helpers
└── sources/
    └── <source_key>/
        ├── __init__.py                 # public adapter export
        ├── adapter.py                  # public Stage 2 adapter class/function
        ├── config.py                   # source constants + typed options
        ├── catalog.csv                 # source-owned indicator catalog
        ├── reader.py                   # raw/API read and cache handling
        ├── transform.py                # source-specific normalization to rows
        ├── db.py                       # source + observation persistence
        ├── manifest.py                 # run manifest payload
        └── README.md                   # source-specific raw locator and caveats
```

Tests mirror the same shape:

```text
tests/ingest/sources/<source_key>/
├── test_adapter.py
├── test_reader.py
├── test_transform.py
├── test_db.py
└── fixtures/
```

Raw and processed data remain source-isolated:

```text
data/raw/<source_key>/metadata.json
data/processed/<source_key>/<source_key>_country_year.parquet
data/processed/<source_key>/<source_key>_run_manifest.json
```

### Migration rule for existing adapters

Do not perform a broad migration of all existing adapters as a standalone refactor. Instead:

1. New sources use the package layout above.
2. Existing flat adapters remain stable until they need non-trivial work.
3. When an existing adapter is touched for feature work, migrate only that source to `ingest/sources/<source_key>/` in the same source-specific slice.
4. Keep backward-compatible imports in the old flat module when tests or CLI still import it, e.g. `src/leaders_db/ingest/wdi.py` can re-export from `ingest.sources.world_bank_wdi.adapter` during migration.

## Shared Stage 2 adapter interface

Every source adapter should present the same public contract to the registry. The exact code can be refined during implementation, but the target shape is:

```python
class SourceAdapter(Protocol):
    source_key: str

    def check_ready(self) -> SourceReadiness: ...
    def read(self, request: IngestRequest) -> RawSourceBundle: ...
    def transform(self, bundle: RawSourceBundle, request: IngestRequest) -> NormalizedSourceFrame: ...
    def write(self, frame: NormalizedSourceFrame, request: IngestRequest) -> IngestResult: ...
    def ingest(self, request: IngestRequest) -> IngestResult: ...
```

Minimum shared models:

| Model | Purpose |
|---|---|
| `IngestRequest` | `source_key`, target years, optional country filter, raw/processed root override, DB URL/session, cache/network policy, force-refresh flag. |
| `SourceReadiness` | metadata status, raw files present, checksums verified, license known, network required, blocker reason if not ready. |
| `RawSourceBundle` | immutable pointers or verbatim payloads from raw files/API cache plus source metadata. |
| `NormalizedSourceFrame` | canonical rows ready for parquet and DB write; must include ISO3/year when applicable, raw values, numeric values, variable names, locators, temporal kind, and attribution. |
| `IngestResult` | Pydantic result crossing CLI/file boundaries: source id, output paths, observation count, years, country count, indicator count, cached/fetched count where relevant, warnings, and manifest path. |

`STAGE2_ADAPTERS` can initially keep function entries, but the registry should eventually point to adapter factories/classes and call `adapter.ingest(request)` through a single runner. That removes per-source CLI special cases while keeping source-specific parsing isolated.

## Assessment of already implemented adapters

The existing 19 adapters should be treated as **functionally acceptable but structurally pre-interface**.

What they already do well:

- They are source-separated enough for current operation: each source has a public orchestrator, reader/parser helpers, DB writer helpers, a Pydantic result model, a catalog, tests, attribution, processed output, and run manifest.
- They already follow the important production boundaries: source-specific parsing stays out of scoring; public CLI calls go through `STAGE2_ADAPTERS`; raw values and normalized values are preserved separately; most adapters write source locators and idempotent DB rows.
- They have substantial fixture and boundary coverage, including attribution drift guards and production dispatch tests.

Where the new plan is better:

- The existing adapters use a flat module layout (`wdi.py`, `wdi_io.py`, `wdi_db.py`, etc.) rather than a per-source package folder.
- Each source defines its own result model and function signature, so there is no shared `IngestRequest`, `SourceReadiness`, or `SourceAdapter` protocol yet.
- There is no uniform `check_ready()` step that validates metadata, raw files, checksums, license fields, and cache/network requirements before parsing begins.
- Indicator catalogs live in one shared `ingest/catalogs/` folder instead of inside the source package, which is workable but less self-contained.
- Generic patterns such as metadata validation, manifest writing, raw-value coercion, observation row construction, and locator validation are repeated across source-specific modules.
- Some older locator patterns are less granular than the new target contract. For example, early adapters may use source/country locators like `wdi:<iso3>` while later or future adapters should prefer source + row/API/file + year + raw column locators when available.

Recommendation:

Do **not** pause source expansion for a broad refactor of all 19 implemented adapters. That would be high-churn and low product value while the adapters already satisfy the current Stage 2 contract. Instead:

1. Build the shared interface and registry compatibility layer first.
2. Apply it to the next new source (`pwt`) as the proving case.
3. Backfill only thin compatibility wrappers for existing adapters, not full migrations.
4. Migrate an existing source only when it is already being touched for a real reason: broken source terms, missing raw locator, changed upstream format, new indicator catalog, or scorer integration gap.
5. Prioritize targeted fixes that improve auditability without moving files: readiness checks, locator specificity, manifest consistency, and common request/result adapters.

### Existing adapter improvement backlog

| Improvement | Applies to | Priority | Rationale |
|---|---|---:|---|
| Shared `IngestRequest` + `SourceReadiness` + `SourceAdapter` protocol | All adapters | High | Enables a generic connector and step-by-step source isolation without rewriting existing code. |
| Compatibility wrappers around existing orchestrator functions | All implemented adapters | High | Lets old flat adapters participate in the new registry while preserving stable imports and tests. |
| `check_ready()` metadata/raw-file validation | All local-file adapters first, API adapters second | High | Catches missing `metadata.json`, missing raw files, checksum drift, and blocked/user-managed states before parsing. |
| Common manifest schema helper | All adapters | Medium | Reduces repeated code and makes run artifacts easier to compare across sources. |
| Locator specificity audit | Early adapters such as WDI/WGI/UCDP/SIPRI milex/PTS | Medium | Improves raw row/cell traceability for confidence and manual review without changing source semantics. |
| Move catalogs into per-source package | New sources only at first | Low | Better self-containment, but migrating existing catalogs now would add churn and import-path risk. |
| Full per-source package migration | Existing adapters only when touched | Low | Structurally cleaner, but not worth a mass refactor before new source delivery. |

Decision rule: if a current adapter is already green, documented, and sufficient for Stage 5/9 evidence bundles, improve it only through the shared interface wrapper or a narrow auditability fix. Do not move it into `ingest/sources/<source_key>/` just for aesthetics.

## Required source-slice workflow

Each source is one slice. A slice is complete only when all items below are done.

1. **Vetting / source hygiene**
   - Confirm source URL, access method, license/terms, coverage, update cadence, and format.
   - Create or update `data/raw/<source_key>/metadata.json` with checksum and `ingestion_status`.
   - If raw data is user-managed, document the expected file names and do not add download code that guesses.
2. **Contract**
   - Add source README under the source package.
   - Add `catalog.csv` with variable names, source raw fields, category, direction, unit, scale, and notes.
   - Define locator pattern before implementation.
3. **Implementation**
   - Implement reader, transform, DB writer, manifest writer, and public adapter.
   - Register the adapter in the central registry/`STAGE2_ADAPTERS` only after tests prove the adapter can run.
4. **Testing**
   - Use tiny real-format fixtures; no invented historical data.
   - Test reader validation, transform semantics, raw locator generation, proxy/stale-year handling, DB writes, manifest, idempotent rerun, and CLI/registry boundary.
5. **Docs**
   - Update `docs/data-sources.md`, `docs/architecture.md` locator table or source-specific architecture doc, `docs/source-attributions.md`, and `docs/workplan.md` status.
   - Update `docs/req/requirements-core.md` only if adding/changing a requirement.
6. **Verification**
   - Run affected tests first.
   - Run `ruff` on changed Python files when code is changed.
   - For non-trivial source work, route to reviewer before starting the next source.

## Source-by-source backlog

### Tier 0 — interface and backlog setup

#### `source_adapter_interface`

Status: planning needed before the next new-source implementation.

Purpose: establish the package layout and connector contract used by future adapters.

Steps:

1. Add `src/leaders_db/ingest/interfaces.py` with Pydantic request/result/readiness models and a `Protocol` for adapters.
2. Add `src/leaders_db/ingest/registry.py` with adapter registration and lookup helpers.
3. Keep `STAGE2_ADAPTERS` backward-compatible while introducing the new registry.
4. Add a tiny fake adapter test proving the runner can call `check_ready -> read -> transform -> write` without knowing the source type.
5. Add a CLI regression test proving the existing `wikipedia_search_extract` `--query` branch is preserved and still rejects missing `--query` values with the current clear error.
6. Do not migrate existing adapters in this slice except for compatibility shims.

Done when: a new source can be added by creating `ingest/sources/<source_key>/` and registering it, without changing CLI flow or core execution logic.

### Tier 1 — existing vetted blockers

#### `pwt`

Status: vetted; source hygiene complete enough to start adapter work; adapter not yet implemented.

Why first: highest-value economic cross-check; xlsx shape should be tractable and complements WDI/Maddison.

Source hygiene now recorded:

- Canonical local file: `data/raw/pwt/pwt1001.xlsx`.
- Metadata: `data/raw/pwt/metadata.json` with SHA-256 `bf2b66c5fd8b465870eeab8bbfa3a57e73253a3236a933286259efbbb5fb67a2`, source URL, CC BY 4.0 license note, local file name, coverage, and `ingestion_status: downloaded`.
- Local workbook inspection confirms sheets `Info`, `Legend`, and `Data`; adapter must read only the `Data` sheet.

Registration gate:

- Keep `STAGE2_ADAPTERS["pwt"]` as `None` until tests prove the metadata gate, reader, transform, DB write, manifest, attribution, and CLI boundary.
- After tests pass, replace the `None` entry with a shim that builds an `IngestRequest` and delegates to the new registry. Do not make PWT appear runnable in the CLI before that point.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/pwt/`.
- Reader: xlsx `Data` sheet reader with required-column validation.
- Initial catalog candidates confirmed present in the local `Data` sheet: `rgdpe`, `rgdpo`, `pop`, `emp`, `avh`, `hc`, `ccon`, `cda`, `ctfp`, `rkna`, `rtfpna`. Additional present columns may be added only if cataloged and test-proven.
- Transform: one row per `(countrycode, year)`; derive per-capita variants only if documented in the catalog.
- Locator: `pwt:Data:<countrycode>:<year>:<raw_column>`.
- Scoring impact: economic well-being cross-validation and PPP methodology evidence.
- Year semantics: PWT emits **direct observed source-year rows only**. PWT 10.01 covers 1950-2019; a request for `--year 2023` must not proxy or stale-fill from 2019. It should complete with zero emitted observations for 2023 plus a manifest warning such as `requested_year_out_of_coverage`. No invented 2023 rows are allowed.

Proof:

- Fixture xlsx with 3 countries x 2 years x selected columns.
- Tests for missing required columns, duplicate country-year rows, numeric coercion, parquet metadata, DB rows, and CLI boundary.
- Tests for `year=2019`, `year=2023`, and no-year/all-years request paths; `year=2023` must produce no observations and must record an out-of-coverage warning in the manifest.
- Tests that raw file present without metadata blocks before reader access; metadata must include source URL, license note, checksum, local file `pwt1001.xlsx`, coverage, and `ingestion_status: downloaded`.

#### `polity_v`

Status: vetted, adapter blocked on raw file / metadata.

Why second: political-freedom historical cross-check; current scorer uses V-Dem/BTI/RSF, but Polity improves long-run and regime-consistency evidence.

Required source hygiene:

- Place `p5v2018.sav` under `data/raw/polity_v/`.
- Write `metadata.json` with source URL, checksum, license, coverage 1800-2018, and `ingestion_status: downloaded`.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/polity_v/`.
- Reader: SPSS `.sav` reader, likely `pyreadstat`.
- Catalog candidates: `polity`, `polity2`, `democ`, `autoc`, `durable`, `xrcomp`, `xropen`, `xconst`, `parreg`, `parcomp`.
- Transform: country/year rows with ISO3 mapping and special missing values handled explicitly.
- Locator: `polity_v:<country_code_or_name>:<year>:<raw_column>`.
- Scoring impact: political-freedom evidence and historical regime checks; not direct-year for 2023.

Proof:

- Fixture `.sav` or narrowly generated SPSS-compatible fixture from real-format columns.
- Tests for special Polity missing codes, stop-year/stale semantics, and country-name mapping.

#### `leader_survival`

Status: vetted with caveats, blocked on Demscore H-DATA v5 manual gate.

Why third: best leader-identity coverage through 2022 once staged.

Required source hygiene:

- User stages the Demscore H-DATA v5 file under `data/raw/leader_survival/`.
- Write metadata with source URL, license, version, checksum, local files, and coverage.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/leader_survival/`.
- Reader: format to be determined after raw file inspection; prefer CSV if provider offers it.
- Catalog: leader identity / spell fields only; not a category score source unless explicitly designed later.
- Transform: leader spell rows keyed by country, leader name, start date, end date, office/type fields, and source identifiers.
- Locator: `leader_survival:<country>:<leader_id_or_name>:<start_date>:<raw_column>`.
- Scoring impact: Stage 4 ruler resolution confidence, not category scoring.

Proof:

- Tests should compare tenure-spell extraction with Archigos/REIGN-style cases: single ruler, transition year, overlapping/shared leaders, missing end date.

#### `freedom_house`

Status: user-managed, email/request gate.

Why optional: useful political-freedom source, but V-Dem/BTI/RSF already satisfy current scorer threshold.

Required source hygiene:

- User stages FIW data under `data/raw/freedom_house/`.
- Metadata records source terms and local-file checksums.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/freedom_house/`.
- Reader: xlsx/csv depending on user-provided format.
- Catalog candidates: political rights, civil liberties, total score, freedom status.
- Transform: country/year rows with direction normalization deferred to Stage 6.
- Locator: `freedom_house:<sheet_or_file>:<iso3_or_country>:<year>:<raw_column>`.
- Scoring impact: political-freedom cross-check and missingness reduction.

### Tier 2 — high-ROI future structured sources

#### `world_bank_poverty_inequality_platform`

Status: need/future; not yet vetted for this project.

Why first among new sources: directly addresses poverty, inequality, and inclusive prosperity gaps in economic scoring.

Vetting tasks:

- Verify API endpoint, allowed formats, rate limits, citation, and license.
- Decide poverty lines and indicators to collect.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/world_bank_poverty_inequality_platform/`.
- Reader: API client with verbatim CSV/JSON cache by country/year/query.
- Catalog candidates: poverty headcount, poverty gap, Gini, mean/median welfare, distributional shares if available.
- Transform: one row per economy/year/indicator; preserve poverty-line metadata.
- Locator: `pip:<endpoint>:<country>:<year>:<poverty_line>:<indicator>`.
- Scoring impact: economic well-being inclusive-prosperity group.

#### `ilo_labor_statistics`

Status: need/future; not yet vetted.

Why: employment quality and labor access are missing from current economic score.

Vetting tasks:

- Choose bulk download vs SDMX API.
- Identify stable indicator codes and country/year coverage.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/ilo_labor_statistics/`.
- Reader: prefer bulk cached files if license/size is reasonable; use SDMX only if bulk is unsuitable.
- Catalog candidates: unemployment, youth unemployment, labor-force participation, vulnerable employment, informal employment, employment-to-population ratio, real wages if available.
- Locator: `ilo:<dataset_code>:<iso3>:<year>:<indicator_code>`.
- Scoring impact: economic well-being employment group.

#### `sipri_arms_transfers`

Status: need/future; not yet implemented.

Why: best candidate for conventional arms-transfer responsibility and proxy-war context.

Vetting tasks:

- Confirm CSV export route, terms/fair use, update cadence, and automation acceptability.
- Decide whether to ingest transfer register, TIV aggregate, or both.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/sipri_arms_transfers/`.
- Reader: cached CSV exports; avoid scraping interactive pages if terms discourage automation.
- Catalog candidates: exports by supplier/year, imports by recipient/year, TIV, weapon category, status, delivery year.
- Transform: aggregate to supplier-year and recipient-year; preserve transfer-level processed artifact separately if useful.
- Locator: `sipri_arms_transfers:<register_row_id_or_hash>:<supplier>:<recipient>:<delivery_year>`.
- Scoring impact: international-peace/proxy-aggression evidence, with careful distinction between legal arms exports and direct aggression.

#### `unoda_treaties`

Status: need/future; not yet vetted.

Why: structured treaty posture for nuclear-restraint questions.

Vetting tasks:

- Confirm source of NPT/TPNW/other nuclear treaty status and machine-readable access.
- Confirm whether UNODA or UN Treaty Collection is the better canonical source per treaty.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/unoda_treaties/`.
- Reader: API/CSV/table/PDF depending on vetted source.
- Catalog candidates: signature status, ratification/accession status, withdrawal/reservation status, effective dates.
- Locator: `unoda_treaties:<treaty_code>:<state>:<status_date>:<field>`.
- Scoring impact: nuclear responsibility treaty-restraint group.

#### `ctbto_treaty_status`

Status: need/future; not yet vetted.

Why: CTBT signature/ratification posture is a focused nuclear-restraint signal.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/ctbto_treaty_status/`.
- Reader: vetted table/API/PDF source.
- Catalog candidates: signed, ratified, annex-2 state flag, ratification date.
- Locator: `ctbto_treaty_status:<state>:<field>`.
- Scoring impact: nuclear responsibility treaty-restraint group.

#### `iaea_additional_protocol_status`

Status: need/future; not yet vetted.

Why: safeguards agreement and Additional Protocol status help distinguish monitored civilian programs from higher-risk latent capability.

Adapter plan:

- Package: `src/leaders_db/ingest/sources/iaea_additional_protocol_status/`.
- Reader: vetted IAEA status list, likely table/PDF.
- Catalog candidates: safeguards agreement type, additional protocol signed/in force, small quantities protocol status, status date.
- Locator: `iaea_additional_protocol_status:<state>:<status_date>:<field>`.
- Scoring impact: nuclear responsibility safeguards-restraint group.

### Tier 3 — complex future sources needing separate design

These should not be implemented before a source-specific design note and reviewer gate.

| Source | Main blocker / risk | Recommended next step |
|---|---|---|
| `iaea_safeguards` | Annual reports and safeguards conclusions are often narrative/PDF; evidence may be sensitive and state-specific. | Design a cited-snippet extraction model before adapter work. |
| `ctbto_nuclear_tests` | Need to distinguish actual nuclear tests, monitoring statements, and missile/component tests. | Vet structured test lists and define event taxonomy. |
| `nuclear_weapons_ban_monitor` | License/access and data structure unknown. | Vet as cross-check source for arsenal/treaty posture. |
| `csis_missile_threat` | Narrative country/missile profiles; risk of over-interpreting capability. | Design capability/test-event indicators and locators. |
| `cns_nti_missile_launches` | Access and blocked NTI domain risk. | Vet whether launch data is downloadable or user-managed. |
| `world_nuclear_association_profiles` | Civilian fuel-cycle narrative must not be treated as weapons intent. | Design civilian-vs-weapons-risk extraction rules. |
| `ucdp_external_support` | Sponsor-recipient-dyad mapping; source semantics must be understood. | Vet raw structure, then design sponsor-year aggregation. |
| `non_state_actor_dataset` | Dataset availability and relation to sponsor responsibility uncertain. | Vet and compare with UCDP external support first. |
| `dangerous_companions_nags` | Academic dataset availability/license unknown. | Vet only after UCDP external support. |
| `att_monitor` | National reports are heterogeneous and often narrative/PDF. | Treat as evidence-snippet/manual source first. |
| `acled` | Access/API key/terms and large event volume. | Vet terms and decide whether user-managed token is acceptable. |
| `world_bank_global_findex` | Survey waves, not annual; temporal-fit design needed. | Vet and define proxy-year rules. |
| `world_inequality_database` | Many series and units; easy to choose inconsistent indicators. | Vet and write a small indicator-selection note. |
| `government_manifestos` | Country-specific documents, language, and LLM/manual extraction required. | Separate promise-to-results ingestion design. |
| `budget_execution_reports` | Country-specific PDFs; weak standardization. | Separate document registry + cited-snippet design. |
| `national_statistics_goal_indicators` | Depends on each government's promises. | Defer until promise extraction exists. |
| `audit_oversight_reports` | Heterogeneous narrative evidence. | Treat as manual/cited-snippet evidence, not normal Stage 2. |

## Recommended execution order

Before starting code-bearing implementation, isolate the current working tree so the shared-interface/PWT diff is reviewable on its own. The repository currently has unrelated Chronicle/source-vetting/doc changes; those must be committed, stashed, reverted, or otherwise separated before Increment A or B code begins.

1. Build shared `SourceAdapter` interface and package skeleton support.
2. Implement `pwt` once source hygiene is complete.
3. Implement `polity_v` once source hygiene is complete.
4. Implement `leader_survival` after the user stages Demscore data.
5. Implement `freedom_house` if/when user stages FIW data.
6. Vet and implement `world_bank_poverty_inequality_platform`.
7. Vet and implement `ilo_labor_statistics`.
8. Vet and implement `sipri_arms_transfers`.
9. Vet and implement `unoda_treaties`, `ctbto_treaty_status`, and `iaea_additional_protocol_status` as the first nuclear-restraint tranche.
10. Design separately for narrative/proxy/promise-to-results sources.

## Source-slice acceptance checklist

Use this checklist before marking any source complete:

- [ ] Source has a vetted registry row in `docs/data-sources.md`.
- [ ] `data/raw/<source_key>/metadata.json` exists and has checksum/license/source URL/version/coverage.
- [ ] Source package lives under `src/leaders_db/ingest/sources/<source_key>/` or has a documented migration exception.
- [ ] Catalog exists and is source-owned.
- [ ] Adapter uses shared request/result/readiness models.
- [ ] Reader validates required raw columns and format/version.
- [ ] Transform preserves raw value, normalized numeric value, year, ISO3/country key, temporal kind, and raw locator.
- [ ] Processed artifact is written atomically.
- [ ] Run manifest is written.
- [ ] DB `sources` and `source_observations` rows are idempotent for reruns.
- [ ] CLI/registry boundary is tested.
- [ ] Attribution text is present and drift-guarded.
- [ ] Architecture locator table or source README is updated.
- [ ] Affected tests and lint pass.
- [ ] Reviewer pass recorded for non-trivial adapters.
