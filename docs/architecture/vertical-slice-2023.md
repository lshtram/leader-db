# Vertical slice 2023 architecture

## 1. Purpose and scope

This document designs a deliberately thin downstream vertical slice after Phase C.8.
Its purpose is to prove that the current Stage 2 source adapters can feed the
database, a tiny ruler-year layer, provisional score rows, validation rows, and
auditable output files for the 2023 client matrix.

This is not the real Stage 3-15 activation. It is a named experimental slice
that uses a few countries, a few indicators, and transparent provisional formulas
so the team can discover integration gaps before writing more source adapters.

The slice must preserve the core invariants:

- no schema or migration changes unless a blocker is found;
- no silent overwrite of client scores;
- client, system, final, and delta score fields remain separate;
- every slice-owned row is idempotently re-runnable;
- every output states that formulas are provisional and limited to this slice.

Recommended module boundary: `src/leaders_db/vertical_slice/slice_2023.py` with
small helper modules only if needed. The module is allowed to compose existing
Stage 2 adapters and existing DB/session helpers; it must not become the real
Stage 3-15 orchestration layer.

## 2. Exact country/category scope

Target year: `2023`.

Countries, keyed only by ISO3:

| ISO3 | Client country | Client leader | Client row facts used by slice |
|---|---|---|---|
| `MEX` | Mexico | Andrés Manuel López Obrador | social=7, integrity=5 |
| `NGA` | Nigeria | Bola Tinubu | social=4, integrity=3 |
| `USA` | United States | Joe Biden | social=8, integrity=8 |

Scored categories:

1. `social_wellbeing` — primary category for first pass.
2. `integrity` — second category if WGI Control of Corruption is available for
   2023 or a documented 2022 one-year proxy.

The slice may read client scores for other visible columns for comparison notes,
but it must not write `ruler_scores` for categories outside this scope.

## 3. Inputs and source adapters to run

Client input:

- file: `data/raw/client_existing/LATEST BARR'S POLITICAL MATRIX 041725 (1).xlsx`
- sheet: `Main`
- header rows: rows 2-4 in spreadsheet terms already identified by the user;
  pandas read should treat data as starting at zero-based row index `5`.

Stage 2 adapters required by the slice:

| Source key | Why used | Year handling |
|---|---|---|
| `undp_hdi` | `undp_hdi_hdi` for `social_wellbeing` | Adapter already records 2022 as the 2023 proxy where needed. |
| `world_bank_wgi` | `wgi_control_of_corruption` for `integrity` | Use 2023 if present; otherwise use 2022 as a one-year proxy with temporal-fit penalty and output note. |
| `world_bank_wdi` | Optional country-year context (`population`, GDP fields) and extra social context if already present | Use 2023 where present; missing values stay NULL. |

Optional diagnostic adapters, not required to compute the two scores:

- `vdem` can cross-check integrity/social inputs if already ingested, but the
  first slice should avoid multi-source scoring unless that remains trivial.
- `ucdp`, `sipri_milex`, `sipri_yearbook_ch7`, and `pts` should not be pulled
  into scoring for this slice unless the user explicitly widens categories.

Adapter policy:

- If required `source_observations` already exist for the selected source/year,
  the slice may reuse them.
- If absent, call the existing Stage 2 adapter through the `STAGE2_ADAPTERS`
  registry or the adapter callable. Do not duplicate adapter parsing logic.
- Do not re-download source files; rely on the existing local raw/data-cache
  behavior of each Stage 2 adapter.

## 4. DB rows to populate and idempotency strategy

The slice writes only these existing tables:

- `countries`
- `country_years`
- `leaders`
- `ruler_spells`
- `ruler_years`
- `score_categories`
- `ruler_scores`
- `source_observations` country links only, not raw observation content except
  through existing Stage 2 adapters
- `validation_results`

No new table and no migration are recommended.

Slice-owned markers:

- `ruler_spells.source_dataset = "vertical_slice_client_seed"`
- `ruler_spells.notes` starts with `vertical_slice_2023:`
- `ruler_years.match_status = "client_only"`
- `ruler_years.review_note` starts with `vertical_slice_2023:`
- `ruler_scores.rationale_short` starts with `vertical_slice_2023:`
- `validation_results.validation_note` starts with `vertical_slice_2023:`

Idempotent rerun sequence inside one transaction where practical:

1. Resolve existing slice ruler-years for `(year=2023, ISO3 in MEX/NGA/USA)`.
2. Delete slice-owned `validation_results` for their `ruler_score` item IDs.
3. Delete slice-owned `ruler_scores` for selected categories.
4. Delete slice-owned `ruler_years` and `ruler_spells` if marked by the slice.
5. Keep reusable `countries`, `country_years`, `leaders`, `score_categories`,
   and Stage 2 `source_observations`; upsert/update them rather than deleting.
6. Reinsert deterministic slice-owned ruler and score rows.

The implementation must not delete or rewrite non-slice rows. If a non-slice
leader already exists with the same normalized name, reuse it; otherwise create
a leader with notes identifying it as seeded from the client matrix for this
slice.

## 5. Client matrix parser contract

Create a small parser seam rather than using a one-off notebook. Recommended
importable contract:

```text
load_vertical_slice_client_rows(path, sheet, year, iso3_scope) -> list[ClientSliceRow]
```

`ClientSliceRow` should be a typed/Pydantic boundary object with:

- `iso3`
- `country_name`
- `population_raw`
- `leader_name`
- `year_started_raw`
- `client_scores: dict[str, int | None]`
- `source_row_number`

Column mapping by zero-based pandas position:

- country: `3`
- population: `4`
- leader: `14`
- year_started: `15`
- international_peace: `18`
- domestic_safety_security: `19`
- political_freedom: `20`
- economic_wellbeing: `21`
- social_wellbeing: `22`
- integrity: `23`
- combo: `24`
- power_retention/effectiveness-ish: `25`
- nuclear responsibility: `29`

Parser validation:

- exactly one row must be found for each scoped country name/ISO3;
- category score cells used by the slice must be integers in `0..10` or NULL;
- leader string must be non-empty;
- row number is retained for audit and output files;
- parser never writes to DB by itself.

## 6. Country matching strategy for slice only

This slice does not implement the real Stage 3 alias layer. It seeds and uses a
fixed ISO3 map:

| Client country | ISO3 | Preferred name |
|---|---|---|
| Mexico | `MEX` | Mexico |
| Nigeria | `NGA` | Nigeria |
| United States | `USA` | United States |

Country upsert behavior:

- insert missing `countries` rows with normalized names from the existing
  country normalizer;
- update only empty optional fields if needed;
- create/update `country_years` for `(country_id, 2023)` with client population
  if parseable and WDI values when available;
- set `included_in_project=True` and
  `inclusion_reason="vertical_slice_2023_selected_country"`.

Observation linking behavior:

- For ISO3-bearing observations, set `source_observations.country_id` when
  `source_row_reference` is one of `wdi:<ISO3>`, `wgi:<ISO3>`,
  `undp_hdi:<ISO3>`, or `vdem:<ISO3>`.
- Only update rows whose `country_id` is NULL or already points to the same ISO3.
- Do not attempt general matching for UCDP numeric IDs, SIPRI display names, or
  PTS COW codes in this slice unless a tiny explicit map is added and reviewed.
- Emit unmatched counts in `vertical_slice_summary.md` rather than silently
  treating them as successful matches.

## 7. Leader/ruler-year seeding strategy for slice only

Because leader-identity sources are not implemented yet, the slice seeds ruler
rows from the client matrix and marks them explicitly as client-only.

For each scoped country:

1. Normalize the client leader string using the existing leader-name normalizer.
2. Reuse an existing `leaders` row by exact normalized name if present;
   otherwise insert a leader row with `notes` mentioning client matrix seeding.
3. Insert a `ruler_spells` row with:
   - `source_dataset="vertical_slice_client_seed"`
   - `start_date` from client `year_started` if a year can be parsed, otherwise
     `2023-01-01` with a note that the date is a slice placeholder
   - `end_date=NULL`
   - `is_actual_ruler=True`
   - `is_formal_leader=True` only if office information becomes available;
     otherwise leave conservative/default metadata
   - `confidence_score=40` because this is single-source client seeding
4. Insert a `ruler_years` row with:
   - `year=2023`
   - `actual_ruler_status="actual_ruler"`
   - `client_matrix_leader_name=<raw client string>`
   - `system_selected_leader_name=<same string>`
   - `match_status="client_only"`
   - `confidence_score=40`
   - `review_status="manual_review_required"`
   - `review_note` explaining that real Stage 4 is not implemented.

This proves downstream row linkage without pretending that leader resolution is
complete.

## 8. Minimal scoring formulas and caveats

All formulas are provisional and slice-only. Scores are rounded to the nearest
integer and clipped to `0..10`. `final_score` remains NULL.

### `social_wellbeing`

Primary formula:

```text
system_proposed_score = round(10 * undp_hdi_hdi_value)
```

Expected input:

- `source_observations.variable_name = "undp_hdi_hdi"`
- prefer `year=2023`; allow documented 2022 proxy for UNDP HDI because the
  current adapter records the one-year-gap proxy semantics.

Confidence components for validation row:

- agreement: `60` for one direct source compared with a client row;
- authority: `80` for UNDP HDI;
- specificity: `80` because HDI is country-year specific but not ruler-specific;
- temporal fit: `80` when using a 2022 proxy for 2023, `100` if 2023 direct.

### `integrity`

Primary formula if WGI is available:

```text
normalized = clamp((wgi_control_of_corruption_estimate + 2.5) / 5.0, 0, 1)
system_proposed_score = round(10 * normalized)
```

Expected input:

- `source_observations.variable_name = "wgi_control_of_corruption"`
- use direct `normalized_value` only if the adapter has already normalized WGI
  z-scores to 0-1; otherwise compute from `raw_value` as above.
- prefer 2023; allow 2022 as a one-year proxy with temporal-fit note.

Confidence components for validation row:

- agreement: `60` for one direct source compared with a client row;
- authority: `80` for World Bank WGI;
- specificity: `80` because WGI is country-year specific but not ruler-specific;
- temporal fit: `80` for 2022 proxy, `100` for 2023 direct.

If WGI Control of Corruption is not present, skip `integrity` rows rather than
inventing a score. The output must list `integrity` as unavailable for the
affected country.

### Ruler score fields

For each available `(ruler_year, category)`:

- `client_score`: value parsed from the client matrix;
- `system_proposed_score`: slice formula result;
- `final_score`: NULL;
- `score_delta_vs_client`: `system_proposed_score - client_score` when both are
  present;
- `confidence_score`: output of the existing fixed confidence helper;
- `source_agreement`: `medium` for one-source provisional scores;
- `human_review_required`: true when absolute delta > 2, confidence < 60, or a
  proxy year was used; otherwise false is allowed but note still says slice;
- `review_status`: `manual_review_required` for this first slice unless the
  project-manager explicitly accepts auto-medium behavior.

## 9. Validation/comparison outputs

Write all public files under:

```text
data/outputs/vertical_slice_2023/
```

Required files:

1. `vertical_slice_scores.csv`
   - one row per written `ruler_scores` row;
   - columns: `iso3`, `country`, `leader`, `year`, `category_key`,
     `client_score`, `system_proposed_score`, `final_score`,
     `score_delta_vs_client`, `confidence_score`, `source_variable`,
     `source_year`, `source_raw_value`, `review_status`, `rationale_short`.
2. `vertical_slice_comparison.csv`
    - one row per scoped `(country, category)`, including skipped/missing rows;
    - columns include `validation_status`, `missing_reason`, `manual_review_required`.
3. `vertical_slice_timeseries.csv`
   - optional source-only multi-year table written when the caller supplies
     `years` / `--years`;
   - rows are one per available `(iso3, year, category)` source observation;
   - required columns: `iso3`, `country`, `year`, `category_key`,
     `system_proposed_score`, `source_variable`, `source_year`,
     `source_raw_value`, `source_kind`, `confidence_score`, `note`;
   - this file deliberately excludes client-comparison and leader-identity
     columns (`client_score`, `score_delta_vs_client`, `leader`) because
     client comparison and ruler-year seeding are 2023-only in this slice;
   - for years before 2023, source observations must be exact-year/direct;
     for 2023, the documented 2022 proxy is allowed and marked `proxy`.
4. `vertical_slice_summary.md`
    - purpose/scope statement;
    - country/category count;
    - source adapters reused/run;
    - direct-vs-proxy year counts;
    - requested time-series years, when supplied;
    - score-delta table;
    - skipped inputs;
    - attribution block from `docs/sources/attributions.md` for each source used;
    - explicit caveat that this is not final scoring and that client comparison
      is 2023-only when the multi-year source-only table is written.

DB validation rows:

- one `validation_results` row per written `ruler_scores` row;
- `item_type="ruler_score"`;
- `item_id=<ruler_scores.id>`;
- `validation_status` is `match` when absolute delta <= 1, `high_delta` when
  absolute delta > 2, otherwise `conflict` or `low_confidence` as applicable;
- confidence component columns use the values described in section 8.

## 10. CLI or callable entry point recommendation

Recommended public runtime seam:

```text
leaders-db run-vertical-slice-2023 --config configs/prototype-2023.yaml
```

Recommended importable seam:

```text
run_vertical_slice_2023(config: RunConfig, *, countries: Sequence[str] | None = None,
                        categories: Sequence[str] | None = None,
                        years: Sequence[int] | None = None) -> VerticalSliceResult
```

Default `countries` should be `("MEX", "NGA", "USA")`; default `categories`
should be `("social_wellbeing", "integrity")`. These defaults are acceptable
only because the module name is explicitly a 2023 vertical slice; if reused for
general pipeline activation, move them into config.

`VerticalSliceResult` should report row counts and output paths:

- countries seeded/updated;
- source observations linked;
- client rows parsed;
- ruler years written;
- score rows written;
- validation rows written;
- time-series years requested and rows written, when `years` is supplied;
- output file paths;
- warnings/skipped categories.

The CLI should be thin: load config, call the importable seam, print counts and
paths. Tests should call both the importable seam and the CLI boundary.

## 11. Test/proof plan

The test-builder/developer should implement proof before/with code. This plan is
designed to avoid tests that pass while real use still fails.

| Requirement ID | Requirement | Proof surface |
|---|---|---|
| VS-2023-001 | Runs selected Stage 2 adapters or reuses existing observations | Package integration with temp DB + adapter registry seam; CLI smoke for missing/present observations. |
| VS-2023-002 | Seeds MEX/NGA/USA countries and country-years idempotently | Unit + package integration, rerun twice and assert stable row counts. |
| VS-2023-003 | Links ISO3-bearing observations from source row references | Package integration against fixture observations for WDI/WGI/UNDP/V-Dem. |
| VS-2023-004 | Parses only selected client rows and columns | Unit test with a tiny xlsx fixture preserving header/data-row offsets. |
| VS-2023-005 | Seeds leaders/ruler spells/ruler years as client-only slice rows | Package integration checking `match_status`, notes, and no external-resolution claim. |
| VS-2023-006 | Computes provisional social score from HDI | Unit for formula and integration from DB observation to `ruler_scores`. |
| VS-2023-007 | Computes or skips provisional integrity from WGI | Unit for z-score scaling and integration that skips without inventing data. |
| VS-2023-008 | Carries client/system/final/delta separately | Package integration inspecting `ruler_scores`; `final_score` must remain NULL. |
| VS-2023-009 | Writes validation rows with fixed confidence formula components | Unit for confidence inputs and integration for `validation_results`. |
| VS-2023-010 | Writes all three output files with attribution and caveats | Runtime/CLI proof against temp data lake; read files and assert required columns/phrases. |
| VS-2023-011 | Idempotent rerun does not delete non-slice rows | Package integration with sentinel non-slice row that survives rerun. |

Minimum real-boundary proof:

- one CLI test or smoke command must run `run-vertical-slice-2023` against an
  initialized temporary data lake and SQLite database;
- one multi-year proof must run with a `years` scope such as
  `2020,2021,2022,2023` and assert that `vertical_slice_timeseries.csv` is
  source-only, while DB `ruler_years` / `ruler_scores` / `validation_results`
  remain scoped to 2023;
- one post-implementation manual/runtime smoke should use the real client xlsx
  and local raw source files for the three countries, writing the real
  `data/outputs/vertical_slice_2023/` artifacts.

Could tests pass while real use fails? Yes, if tests only use in-memory rows and
never exercise xlsx parsing, the Stage 2 registry, SQLite persistence, or output
files. Therefore the plan requires both package integration and at least one CLI
or runtime boundary proof.

## 12. Out of scope / what remains for real Stage 3-15

Out of scope for this slice:

- full client matrix ingestion;
- full country alias/matching workflow;
- real leader resolution from Archigos/REIGN/Leader Survival/Wikidata;
- all countries and population-threshold inclusion logic;
- final category rubrics for any category;
- multi-source weighted scoring;
- real manual-review queue prioritization beyond row flags;
- LLM calls;
- schema changes;
- final Stage 15 validation files named in the full requirements.

What remains for real Stage 3-15:

- replace fixed ISO3 map with maintained alias table and ambiguity reporting;
- replace client-only leader seeding with structured leader-source resolution;
- define category rubrics using all vetted signals and confidence components;
- produce official validation/report outputs for the full client 2023 scope;
- support high-delta/manual-review workflows without conflating them with the
  experimental vertical-slice outputs.

## 13. Reviewer/process expectations

This design is Phase A architecture output for the slice. The next agents should
not treat it as implementation.

- The test-builder defines failing tests from section 11 before production code.
- The developer implements the smallest code path that satisfies those tests.
- The project-manager/developer runs the affected tests and any agreed runtime
  smoke commands.
- The reviewer performs static/code/content review by default and does not rerun
  commands unless the user explicitly requests command reruns.
- Any implementation that widens countries, categories, formulas, schema, or
  source scope must update this document or supersede it with a reviewed design.
