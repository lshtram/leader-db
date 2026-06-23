# UNDP HDI Stage 2 Adapter Architecture

## §1 Purpose

The `undp_hdi` adapter is the Phase C.8 / Stage 2 ingestion design for the UNDP Human Development Report 2023-24 composite indices time-series CSV. Stage 2 transforms the provider-native file into auditable, catalog-driven source observations while leaving country normalization, score normalization, confidence scoring, and client-matrix comparison to later stages.

UNDP HDI supports `social_wellbeing` because it is the canonical cross-national composite of health, education, and income, and because its component measures explain the composite. The adapter extracts exactly five social-wellbeing indicators: HDI, life expectancy, expected years of schooling, mean years of schooling, and GNI per capita.

## §2 Source

| Fact | Value |
|---|---|
| Source key | `undp_hdi` |
| Source URL | `https://hdr.undp.org/sites/default/files/2023-24_HDR/HDR23-24_Composite_indices_complete_time_series.csv` |
| Local CSV path | `data/raw/undp_hdi/HDR23-24_Composite_indices_complete_time_series.csv` |
| Metadata path | `data/raw/undp_hdi/metadata.json` |
| Version | HDR 2023-24, latest data year 2022 |
| Coverage | 1990-2022, 33 annual observations per populated indicator (some countries have empty 1990 cells; e.g. Nigeria has no `hdi_1990` / `mys_1990`) |
| File size | 1,919,243 bytes |
| Encoding | `latin-1`; UTF-8 fails on country names with diacritics |
| Shape | 206 countries x 1,076 columns, wide format, one row per country (10 aggregate regions with `ZZ*` iso3 prefixes are present but not counted as countries) |
| Static columns | `iso3`, `country`, `hdicode`, `region` |
| Region codes | `SA`, `ECA`, `AS`, `SSA`, `LAC`, `EAP` |
| HDI code values | `Low`, `Medium`, `High`, `Very High` |
| SHA-256 | `d987af8fb17913d6c4b83e9e0e4bb23356166f606744e9818a28d06967a56eec` |
| License/citation note | Free with attribution; canonical text in `docs/sources/attributions.md` under `undp_hdi` |

The source is `vetted_ok` in `docs/sources/vetting/report.md` and is one of the social-wellbeing sources alongside WDI social indicators and WHO GHO API. The adapter must not download the file during Stage 2; it reads the staged local CSV and metadata.

## §3 Indicator catalog

| variable_name | raw_column prefix | category | higher_is_better | raw_scale | normalized_scale_target | unit |
|---|---|---|---:|---|---|---|
| `undp_hdi_hdi` | `hdi` | `social_wellbeing` | 1 | `0-1` | `0-10` | `index` |
| `undp_hdi_life_expectancy` | `le` | `social_wellbeing` | 1 | `years` | `0-10` | `years` |
| `undp_hdi_expected_years_schooling` | `eys` | `social_wellbeing` | 1 | `years` | `0-10` | `years` |
| `undp_hdi_mean_years_schooling` | `mys` | `social_wellbeing` | 1 | `years` | `0-10` | `years` |
| `undp_hdi_gni_per_capita` | `gnipc` | `social_wellbeing` | 1 | `2017 PPP $` | `0-10` | `USD_2017_PPP` |

These five indicators were chosen because they are the HDI composite and the core health, education, and income inputs needed to explain that composite. All five are `higher_is_better=1`.

For this prototype, the adapter excludes inequality-adjusted indicators, gender-disaggregated indicators, rank fields, 2022-only metadata fields such as `hdi_rank_2022`, `gdi_group_2022`, `gii_rank_2022`, `rankdiff_hdi_phdi_2022`, and all non-social-wellbeing prefixes. Those fields can be added later only by catalog extension after a separate design decision.

## §4 Data flow

```text
data/raw/undp_hdi/HDR23-24_Composite_indices_complete_time_series.csv
        |
        | pd.read_csv(csv_path, encoding="latin-1", dtype=str)
        v
wide provider frame: 207 countries x 1,076 columns
        |
        | validate static columns: iso3, country, region, hdicode
        | select id_vars + catalog-driven {prefix}_{year} columns
        v
catalog-filtered wide frame
        |
        | pd.melt(
        |   id_vars=["iso3", "country", "region", "hdicode"],
        |   var_name="col_year",
        |   value_name="raw_value",
        | )
        v
long frame with col_year values such as hdi_2022 and gnipc_1990
        |
        | parse {prefix}_{year}; filter to catalog prefixes
        | drop empty numeric cells at debug level
        v
Stage 2 observation frame -> parquet -> source_observations -> manifest
```

CSV reading must use `pd.read_csv(..., encoding="latin-1")`; UTF-8 is not a valid default for this source. The WIDE-to-LONG UNPIVOT uses `pd.melt` with `id_vars=["iso3", "country", "region", "hdicode"]`, `var_name="col_year"`, and `value_name="raw_value"`.

Column parsing treats `col_year` as `{prefix}_{year}`. Implementation should split on the final underscore (`rsplit("_", 1)`) or read the last four chars as the year and require the preceding char to be `_`. After parsing, keep only catalog prefixes: `hdi`, `le`, `eys`, `mys`, and `gnipc`. This filtering drops rank fields, 2022-only metadata fields, and non-social-wellbeing prefixes.

Approximate shape: 206 countries x 5 indicators x 33 years = 33,990 potential observations before empty-cell drops. For `year=2022`, the upper bound is about 206 x 5 = 1,030 observations. For prototype target year 2023, use the latest available 2022 row as a one-year-gap proxy, following CIRIGHTS and Leader Survival.

## §5 Module split

| Module | Line cap | Responsibilities |
|---|---:|---|
| `src/leaders_db/ingest/undp_hdi.py` | ≤ 280 | Orchestration, `attribution()`, public `ingest_undp_hdi()` function, and public re-exports, including `UndpHdiIngestResult` and `write_undp_hdi_parquet` from helper modules. |
| `src/leaders_db/ingest/undp_hdi_io.py` | ≤ 340 | Catalog loading, raw/processed paths, attribution constant, source key, and named constants. |
| `src/leaders_db/ingest/undp_hdi_csv.py` | ≤ 400 | CSV reading, schema validation, empty-cell handling, region validation, and `hdicode` validation. |
| `src/leaders_db/ingest/undp_hdi_unpivot.py` | ≤ 250 | WIDE-to-LONG UNPIVOT, `{prefix}_{year}` parsing, narrow-frame construction, and `source_row_reference` attachment. |
| `src/leaders_db/ingest/undp_hdi_parquet.py` | ≤ 150 | Parquet write and file-level attribution/source-key metadata. |
| `src/leaders_db/ingest/undp_hdi_result.py` | ≤ 150 | Pydantic `UndpHdiIngestResult` public result model and validators. |
| `src/leaders_db/ingest/undp_hdi_db.py` | ≤ 350 | DB source row, observations, idempotent delete/reinsert, and manifest. |
| `src/leaders_db/ingest/undp_hdi_db_helpers.py` | ≤ 250 | DB row coercion, bundle metadata parsing, and manifest payload helpers. |

PTS lesson applied: helper modules are part of the final split rather than a last-minute review rescue. `undp_hdi_db_helpers.py`, `undp_hdi_result.py`, and `undp_hdi_parquet.py` keep the documented caps enforceable while `undp_hdi.py` preserves the public re-export surface expected by tests and CLI callers.

No `undp_hdi_http.py` is needed because the adapter reads a staged local CSV. No score, confidence, or normalization formula code belongs in these modules.

## §6 Sentinel and validation handling

- Empty numeric cells: drop the observation and log a debug-level count by prefix/year and total. Empty cells are expected because many inequality-adjusted indicators are sparse; they are not warning-level events.
- Unknown region or `hdicode`: warn and preserve the row rather than fail. These values are audit metadata, not Stage 2 join keys.
- Unknown required static columns: hard failure. Required static columns are `iso3`, `country`, `region`, and `hdicode`.
- Unknown catalog prefix: ignored unless an expected prefix from the catalog is missing entirely.
- Missing expected `{prefix}_{year}` columns for an in-scope prefix/year: hard failure for the affected release because the catalog contract is no longer satisfied.
- Year-2022-only rank/metadata columns: dropped during prefix filtering, not treated as malformed indicator columns.

## §7 Country resolution

`iso3` is the primary Stage 2 key. The adapter does not normalize country names, does not map aliases, and does not populate `country_id`; Stage 3 owns that resolution.

For each written observation, `source_row_reference = f"undp_hdi:{iso3}"`, for example `undp_hdi:USA`. `country_id` remains `NULL` at Stage 2. The source `country` display name is preserved verbatim, including diacritics from the latin-1 CSV.

## §8 Test plan

The test-builder should write about 38 tests across 9 categories. The fixture `tests/fixtures/undp_hdi/sample.csv` must be a real-format slice from the raw CSV, latin-1 encoded, not hand-authored.

1. Catalog loader tests (5): load exactly 5 specs; required 7 columns; `higher_is_better` converts to `True`; missing catalog raises `FileNotFoundError`; raw prefixes equal `hdi`, `le`, `eys`, `mys`, `gnipc` in order.
2. CSV reader tests (6): reads latin-1 diacritics; configured encoding avoids UTF-8 failure; missing CSV raises `FileNotFoundError`; missing static column raises `ValueError`; unknown region/`hdicode` warns and preserves row; expected prefix missing raises actionable error.
3. Wide-to-long narrow frame tests (7): `pd.melt` shape is correct; final-underscore `{prefix}_{year}` parsing works; only 5 catalog prefixes remain; 2022-only rank metadata is dropped; years are `int`; empty cells are debug/drop; `country`, `region`, and `hdicode` metadata is preserved.
4. DB writer tests (6): source registration is idempotent; observation row count equals non-empty cells; `source_row_reference` uses `undp_hdi:<iso3>`; `country_id` and `confidence` are `NULL`; rerun is idempotent by source/year scope; run manifest records `year_window`, attribution, source key, row counts, and proxy-year semantics.
5. Attribution drift-guard (2): attribution constant appears in `docs/sources/attributions.md`; parquet metadata carries attribution and source key.
6. End-to-end real-file smoke (3): gated real-file smoke for `year=2022` produces about 1,035 potential rows before empty drops; `year=2023` uses 2022 proxy semantics; `year=None` covers 1990-2022 and five indicators without modifying raw files.
7. Orchestrator tests (4): `ingest_undp_hdi()` writes parquet, DB rows, and manifest; year filter works; result fields are sorted and stable; consecutive runs are idempotent.
8. CLI/dispatch tests (3): `STAGE2_ADAPTERS["undp_hdi"] is undp_hdi.ingest_undp_hdi`; no duplicate dispatch key; `leaders-db ingest-source --source undp_hdi` follows the real dispatch path.
9. Public surface tests (2): public functions are importable from expected modules; `UndpHdiIngestResult` exposes exactly the required fields and `attribution` property.

Could code pass these tests while failing in real use? The real-file smoke, CLI dispatch proof, parquet metadata proof, and attribution drift guard are the boundary proofs intended to prevent that. Unit tests alone are not sufficient because latin-1 encoding, real wide-column shape, and 2023-as-2022 proxy behavior are runtime risks.

## §9 Public surface

Pydantic result model name: `UndpHdiIngestResult` (spelling: `Undp`, not `Undpp`). Fields: `source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `regions_covered`, `year_window`.

Public functions: `load_undp_hdi_catalog`, `read_undp_hdi_csv`, `build_undp_hdi_observations`, `ingest_undp_hdi`, and `attribution`.

The orchestrator should re-export the public test seams needed by `tests/test_ingest_undp_hdi.py`, following the WGI and PTS pattern.

## §10 Acceptance criteria

- Catalog exists with exactly the five specified indicators and no speculative rows.
- Adapter tests pass, including catalog, CSV, UNPIVOT, DB, orchestrator, CLI, and public-surface tests.
- At least one real-boundary proof runs against the real local CSV and verifies latin-1 reading, shape, and 2022 proxy semantics.
- Parquet output and run manifest include UNDP HDI attribution.
- DB writes are idempotent and preserve `country_id=NULL` and `confidence=NULL` for Stage 3 and Stage 11.
- CLI dispatch is wired through `STAGE2_ADAPTERS` without duplicate keys.
- `docs/workplan.md` is updated only after implementation and review land.
- Reviewer verifies line caps, split trigger, real-format fixture, no raw-file edits, and no confidence-formula changes.

## §11 Out of scope

- Inequality-adjusted indicators.
- Gender-disaggregated indicators.
- Rank fields.
- Year-2022-only metadata fields such as `hdi_rank_2022`, `gdi_group_2022`, `gii_rank_2022`, and `rankdiff_hdi_phdi_2022`.
- All non-social-wellbeing prefixes.
- Download automation or live web fetches.
- Country normalization beyond preserving `iso3` and `country`.
- Score normalization, confidence scoring, and any change to the fixed confidence formula.

## §12 Regression checklist

1. Real-format fixture is sliced from the raw CSV, not invented.
2. No hand-authored fake CSV shape; fixture preserves `prefix_YYYY` columns.
3. Latin-1 encoding is wired in constants and reader defaults.
4. Exact raw column prefixes are `hdi`, `le`, `eys`, `mys`, `gnipc`.
5. Variables are catalog-driven, not hard-coded in DB writes.
6. No silent country normalization; `iso3` and `country` are preserved.
7. Source attribution drift guard matches `docs/sources/attributions.md`.
8. Module line caps are respected.
9. PTS split trigger lesson is applied before `undp_hdi_db.py` grows past 350 lines.
10. Defensive constants are wired for encoding, static columns, region codes, HDI code values, and expected prefixes.
11. DB writes are idempotent by source/year scope, following WGI and PTS.
12. Parquet metadata carries source key and attribution, following V-Dem, WDI, WGI, UCDP, SIPRI, and PTS.
13. Year proxy semantics are explicit: 2023 requests use latest available 2022 data.
14. Empty-cell semantics are debug/drop-observation, not warning spam.
15. Dispatch table replaces the existing `None` value; it does not add a duplicate key.
16. No technical debt: no TODO(debug), no scratch files, no raw edits, no confidence-formula changes.

Lessons by predecessor: V-Dem established catalog-driven narrow extraction and attribution metadata; WDI established real boundary proofs and CLI dispatch; WGI established local multi-module DB writer patterns; UCDP established manifest/audit discipline for transformed data; SIPRI milex established shape-changing spreadsheet lessons and region/aggregate filtering discipline; SIPRI Yearbook Ch.7 established strict attribution for non-tabular source adapters; PTS established line-cap enforcement and early helper split triggers.

## §13 Dispatch table entry

Exact implementation instruction for `src/leaders_db/ingest/__init__.py`: add the import and map `"undp_hdi"` to `undp_hdi.ingest_undp_hdi`.

```python
from . import undp_hdi

STAGE2_ADAPTERS = {
    # replace the existing value; do not add a second key
    "undp_hdi": undp_hdi.ingest_undp_hdi,
}
```

If the import block already groups implemented adapters, add `undp_hdi` to that existing import list. The dispatch-table test must fail if `"undp_hdi"` is missing, duplicated, or still mapped to `None`.

## §14 Workplan and docs updates

When implementation and review land, update `docs/workplan.md` Done History with Phase C.8 details: test count, module split and line counts, real-file smoke row counts, fixture provenance, dispatch wiring, attribution guard, and reviewer result.

Check `docs/sources/attributions.md` before implementation. If the existing `undp_hdi` citation is missing or differs from the adapter constant, update the docs and the drift-guard expectation in the same commit. If a manual testing guide is created later, name it `docs/testing-guide-undp-hdi.md` and record the real-file smoke command and row counts.

## §15 Lessons from prior reviews

- V-Dem: keep the adapter catalog-driven, carry source attribution into parquet/manifest, and avoid loading unnecessary provider columns when a narrow catalog is enough.
- World Bank WDI: public/runtime behavior needs real boundary proof; CLI dispatch and cache/runtime wiring must be tested, not just helper functions.
- World Bank WGI: local multi-module file adapters need explicit DB writer seams and a drift guard for attribution and source-file shape.
- UCDP: transformations must be auditable through manifests and clear row-count expectations before and after filtering.
- SIPRI milex: shape-changing sources need real-format fixtures and defensive constants for provider-specific labels; do not silently drop aggregates or regions without proof.
- SIPRI Yearbook Ch.7: source-specific parsing must not dilute attribution or hide extraction assumptions; public reports need source provenance.
- PTS: enforce line caps early, split helper modules before review, preserve raw identifiers, and treat dispatch-table duplicate keys as blockers.
