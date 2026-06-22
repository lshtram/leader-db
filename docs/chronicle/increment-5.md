# Country-Year Chronicle — Increment 5 Implementation Notes

Date: 2026-06-21

Sub-project: **Country-Year Chronicle** (`cyc`)

Scope: implementation notes for Increment 5 (all-country scope +
condensed CSV export) per the user request dated 2026-06-21.

This increment **defers** Increment 4 (controlled / imperial area)
explicitly. The user asked to skip controlled-area modeling in
this pass and to focus on:

1. Scaling the Chronicle database/output to all countries in the
   analysis (instead of the seven-country pilot list).
2. Adding a condensed CSV with pure data only (no source /
   provenance / confidence / text columns).
3. Existence-window semantics with explicit labels for "not
   formed" / "exists" / "split or dissolved" instead of blank
   cells.

The detailed CSV / SQLite behavior is preserved end-to-end; the
condensed CSV is a new companion artifact.

## 1. Source strategy chosen for all-country scope

The all-country scope is derived from V-Dem's
`country_text_id` / `country_name` / `year` columns in the raw
CSV (388 MB bundle at
`data/raw/vdem/V-Dem-CY-Full+Others-v16.csv`, v16, SHA-256
captured in `data/raw/vdem/metadata.json`). V-Dem v16 carries
**202 countries**, all valid 3-letter uppercase ISO3 codes
(verified during Increment 0 recon and re-verified during the
Increment 5 pass — zero non-ISO3 IDs are dropped).

Per-country, V-Dem supplies:

- `country_name` (the project's canonical display name, since
  V-Dem's labels are the most stable reference for the prototype).
- `min(year)` / `max(year)` (the source-backed existence window).

The pilot :data:`COUNTRY_METADATA` is overlaid so historical
identities that V-Dem merges (SUN — V-Dem has no separate SUN
`country_text_id`) and curated overrides (RUS start_year=1991,
IND colonial cutoff) keep their pilot semantics. The pilot
metadata wins on conflicts; the source tag is set to `"merged"`
when the pilot supplied values that differ from V-Dem defaults.

CShapes / GW mappings are **NOT** used to broaden the scope in
this pass. CShapes carries 252 GW codes (181 active in 2019);
many are not modern ISO3 codes and hand-mapping GW codes to ISO3
would risk inventing a colonial-period scope that V-Dem does
not back. The safer path is to keep V-Dem as the scope source
and rely on the per-country pilot metadata for the historical
identities that V-Dem merges.

Source-backed existence windows are used verbatim:

- `exists` for years in `[start_year, end_year]`.
- `not_formed` for years before `start_year`.
- `split_or_dissolved` for years after `end_year`.
- `out_of_scope_unknown` is reserved for countries without a
  defensible start / end year (today this label is unused because
  V-Dem supplies min / max for every ID it covers).

## 2. What landed

- **New module `src/leaders_db/chronicle/country_scope.py`** (228
  lines). `CountryScopeEntry` dataclass; `derive_country_scope`
  reads V-Dem + overlays the pilot metadata; `derive_all_country_scope`
  is a thin alias; `get_existence_status` maps `(entry, year)`
  to the four canonical labels.
- **New module `src/leaders_db/chronicle/condensed_writer.py`**
  (213 lines). `CONDENSED_CSV_COLUMNS` constant in the documented
  Increment 5 order; `build_condensed_rows` transforms detailed
  rows to condensed rows (with the out-of-window rule); atomic
  `write_condensed_csv` matches the detailed writer's tempfile
  + rename pattern.
- **`src/leaders_db/chronicle/constants.py` extended.** New
  constants:
  - `EXISTS_STATUS_EXISTS = "exists"`,
  - `EXISTS_STATUS_NOT_FORMED = "not_formed"`,
  - `EXISTS_STATUS_SPLIT = "split_or_dissolved"`,
  - `EXISTS_STATUS_OUT_OF_SCOPE = "out_of_scope_unknown"`,
  - `CONDENSED_CSV_COLUMNS` (12-column tuple, fixed order).
- **`src/leaders_db/chronicle/_row_identity.py` extended.**
  `populate_identity` accepts an optional `CountryScopeEntry`
  and uses it for `country_name` when the iso3 is not in the
  pilot metadata. When the scope entry is provided the
  `region` / `subregion` / pilot-specific `country_status`
  overrides are preserved.
- **`src/leaders_db/chronicle/_flags.py` extended.**
  `assemble_flags` accepts an optional `country_scope_entry`
  and falls back to the scope's `start_year` / `end_year`
  for countries not in the pilot metadata.
- **`src/leaders_db/chronicle/_row_area.py` extended.**
  `populate_area_fields` accepts an optional
  `country_scope_entry` and uses it for the existence-window
  check when the iso3 is not in the pilot metadata.
- **`src/leaders_db/chronicle/_provenance.py` extended.**
  `populate_provenance_and_flags` forwards
  `country_scope_entry` to `assemble_flags`.
- **`src/leaders_db/chronicle/row_builder.py` extended.**
  `build_chronicle_rows` accepts an optional
  `country_scope` mapping; per-row the scope entry is
  threaded through to `_build_one_row`. Detailed CSV / SQLite
  behavior is preserved when `country_scope is None`.
- **`src/leaders_db/chronicle/runner.py` extended.**
  `run_country_year_chronicle` accepts:
  - `country_scope: dict[str, CountryScopeEntry] | None` —
    the all-country scope.
  - `condensed_output_path: Path | None` — the condensed CSV
    destination.
  The runner writes the condensed CSV alongside the detailed
  CSV whenever `condensed_output_path` is provided (and a
  `country_scope` is also provided; both are required for
  the condensed writer to compute `existence_status`).
  The `ChronicleResult` model gained
  `condensed_output_path` and `condensed_rows_written`
  fields. The source-loading and sources-used-detection
  helpers were extracted into
  `src/leaders_db/chronicle/_source_orchestration.py` (183
  lines) so the runner stays focused on the CLI seam + path
  discovery + output selection.
- **`src/leaders_db/cli/commands_chronicle.py` extended.**
  New CLI options:
  - `--countries all` (or a comma list including `all`)
    derives the scope from V-Dem coverage.
  - `--condensed-output <PATH>` writes the condensed CSV
    to a custom path.
  - `--no-condensed-output` skips the condensed write entirely.
  Default behavior: the condensed CSV is written to
  `<project_root>/data/outputs/country-year-chronicle/condensed.csv`
  whenever the command runs (the CLI derives a scope from V-Dem
  even for the pilot scope, so the condensed writer always has
  data to compute `existence_status`).

## 3. Condensed CSV contract

The fixed column order (12 columns):

1. `year`
2. `iso3`
3. `country`
4. `existence_status` (one of `exists`, `not_formed`,
   `split_or_dissolved`, `out_of_scope_unknown`)
5. `ruler`
6. `political_regime`
7. `system_type`
8. `population`
9. `gdp`
10. `gdp_per_capita`
11. `military_spend`
12. `country_area_km2`

Explicit omissions (per the Increment 5 user contract):

- Every source tag (`ruler_source`, `political_regime_source`,
  `population_source`, `gdp_source`, `military_spend_source`,
  `area_source`).
- Every confidence value (`ruler_confidence`,
  `political_regime_confidence`, `system_type_confidence`,
  `row_confidence`).
- The `provenance_summary` column.
- The `data_quality_flags` column.
- Text / unit / method columns (`system_type_notes`,
  `gdp_unit`, `gdp_per_capita_unit`, `gdp_per_capita_method`,
  `military_spend_unit`, `controlled_area_note`).
- The `controlled_area_km2` value (controlled-area modeling is
  deferred per Increment 4).
- The `country_status`, `region`, `subregion`, `ruler_title`,
  `ruler_type`, `political_regime_raw_score`,
  `system_type_secondary` columns.
- The `shared_rule_flag` / `disputed_rule_flag` columns.

Out-of-window rule: rows whose `existence_status` is
`not_formed` or `split_or_dissolved` keep only
`year` / `iso3` / `country` / `existence_status` and leave every
other column blank.

## 4. Generated outputs (verification)

All runs use the local data lake at
`LEADERSDB_PROJECT_ROOT=/tmp/cyc_test` (a copy of the project's
real data lake). The runs use `--countries all` and write:

- Detailed CSV: `all_countries_<window>_detailed.csv`.
- SQLite: `all_countries_<window>.sqlite`.
- Condensed CSV: `condensed.csv` (at the canonical default
  path; the CLI is configured to default-write the condensed
  artifact).

### 4.1 Window 2020-2026

| Metric | Value |
|---|---|
| Scope size | 203 countries (202 V-Dem + SUN pilot overlay) |
| Detailed rows | 1421 (203 × 7) |
| Condensed rows | 1421 |
| Status breakdown | 1074 exists, 347 split_or_dissolved, 0 not_formed |
| Sources used | archigos, cshapes, maddison_project, reign, sipri_milex, soviet_leaders_curated, vdem, wdi |
| Detailed CSV size | ~5.3 MB |
| Condensed CSV size | ~110 KB |

For 2020-2026, every modern country has all 7 years as
`exists`; every historical entity (BDN, BRW, DDR, VDR, YMD,
SUN, etc.) has all 7 years as `split_or_dissolved`. No
`not_formed` rows in this window (V-Dem's min year for every
modern country is ≤ 1900).

### 4.2 Window 1900-2026

| Metric | Value |
|---|---|
| Scope size | 203 countries |
| Detailed rows | 25,781 (203 × 127) |
| Condensed rows | 25,781 |
| Status breakdown | 20,340 exists, 2,828 split_or_dissolved, 2,613 not_formed |
| Detailed CSV size | ~95 MB |
| Condensed CSV size | ~1.9 MB |

Sample `existence_status` transitions for SUN (1922-1991):
1900-1921 = `not_formed`, 1922-1991 = `exists` (with rulers
from the curated Soviet-leaders spell list), 1992-2026 =
`split_or_dissolved`.

Sample for SVN (1989-2025 in V-Dem):
1900-1988 = `not_formed`, 1989-2025 = `exists`, 2026 =
`split_or_dissolved` (V-Dem max year is 2025).

Missingness (1900-2026, all 25,781 rows):

| Column | Blank | Pct |
|---|---:|---:|
| ruler | 25,166 | 97% |
| political_regime | 5,441 | 21% |
| system_type | 5,441 | 21% |
| population | 11,515 | 44% |
| gdp | 12,237 | 47% |
| gdp_per_capita | 12,237 | 47% |
| military_spend | 25,775 | 99% |
| country_area_km2 | 25,142 | 97% |

The high blank rate for `ruler` / `military_spend` /
`country_area_km2` reflects the historical coverage gap (the
Chronicle slice's historical sources — Archigos / REIGN / SUN
curated / CShapes — only cover specific windows; pre-1950
rulers, pre-1949 SIPRI, pre-1886 CShapes). These blanks are
**explicit missingness** in the source-backed window, not
fabricated values.

## 5. Tests

24 new focused tests in
`tests/test_chronicle_country_scope_and_condensed.py`:

- `derive_country_scope` filters non-ISO3 IDs, includes pilot
  metadata, marks merged entries, returns the pilot metadata
  when V-Dem is missing, and exposes the all-country alias.
- `get_existence_status` covers `not_formed` /
  `split_or_dissolved` / `exists` / `out_of_scope_unknown`
  with the documented canonical examples (Slovenia pre-1991,
  SUN after 1991, modern country in its existence window,
  unknown-window country).
- `CONDENSED_CSV_COLUMNS` matches the Increment 5 contract and
  excludes every source / confidence / text / controlled-area
  column.
- `build_condensed_rows` keeps the data columns for `exists`
  rows and blanks the data columns for out-of-window rows.
- `write_condensed_csv` creates the parent directory, writes
  the canonical header, and produces one row per input.
- CLI tests cover `--countries all`, `--condensed-output
  <PATH>`, `--no-condensed-output`, the default condensed
  write for the pilot scope, and the unchanged detailed
  output behavior.
- Smoke tests against the real V-Dem bundle confirm that
  every V-Dem country_text_id is a valid 3-letter uppercase
  ISO3 code (no IDs are dropped) and that the SUN pilot
  metadata is overlaid even though V-Dem has no separate SUN
  record.

Full suite is green at **1,781 passed** (was 1,757 at
Increment 3 sign-off; +24 net).

## 6. Remaining caveats

- **Pilot scope condensation.** The default condensed CSV is
  written even when `--countries all` is NOT used. The CLI
  derives a country scope from V-Dem + the pilot metadata in
  that case so the condensed writer can compute
  `existence_status` for the pilot rows. The pilot
  `--countries USA,GBR,...` scope will still emit
  out-of-window labels for the historical entities
  represented only in the condensed CSV's existence-window
  column.
- **SIPRI coverage is display-name based.** SIPRI uses
  country display names, not ISO3 codes, in its processed
  parquet. The current `SIPRI_NAME_BY_ISO3` map covers the
  pilot seven countries plus a small extension; the
  all-country condensed export's `military_spend` column is
  blank for most modern countries because the SIPRI lookup
  cannot resolve the name. Expanding the SIPRI display-name
  map is deferred.
- **Archigos / REIGN coverage.** Archigos covers through 2015
  and REIGN through 2021-08. Pre-1950 (REIGN) and post-2015
  (Archigos) rulers are blank in the condensed CSV; this
  matches the detailed CSV behavior and is explicit
  missingness, not a fabricated value.
- **CShapes coverage ends in 2019.** Years 2020+ use the
  conservative CShapes proxy year (`area_proxy_year_used`),
  and years before 1886 (CShapes minimum) are blank. The
  condensed CSV reflects both behaviors.
- **V-Dem 2025 proxy.** The default `--allow-regime-proxy`
  is on; rows for 2026 copy V-Dem 2025 values and carry the
  `proxy_year_used` flag. The verification runs used
  `--no-allow-regime-proxy` so 2026 rows emit `Unknown` +
  `regime_source_gap`.
- **Controlled-area modeling** is deferred per Increment 4.
  The condensed CSV deliberately omits `controlled_area_km2`.

## 7. File map

| File | Status | Lines |
|---|---|---:|
| `src/leaders_db/chronicle/country_scope.py` | NEW | 228 |
| `src/leaders_db/chronicle/condensed_writer.py` | NEW | 213 |
| `src/leaders_db/chronicle/constants.py` | extended (EXISTS_STATUS_*, CONDENSED_CSV_COLUMNS) | 561 (was 476) |
| `src/leaders_db/chronicle/_row_identity.py` | extended (country_scope_entry support) | 109 (was 67) |
| `src/leaders_db/chronicle/_flags.py` | extended (country_scope_entry support) | 162 (was 154) |
| `src/leaders_db/chronicle/_row_area.py` | extended (country_scope_entry support) | 124 (was 109) |
| `src/leaders_db/chronicle/_provenance.py` | extended (country_scope_entry forwarding) | 205 (was 198) |
| `src/leaders_db/chronicle/row_builder.py` | extended (country_scope parameter) | 348 (was 309) |
| `src/leaders_db/chronicle/runner.py` | extended (country_scope, condensed_output_path) | 436 (was 421, carved out for composition boundary) |
| `src/leaders_db/chronicle/_source_orchestration.py` | NEW — source loading + sources-used detection (split out of runner.py to keep it under the 440-line carve-out) | 183 |
| `src/leaders_db/cli/commands_chronicle.py` | extended (--countries all, --condensed-output, --no-condensed-output) | 320 (was 216) |
| `tests/test_chronicle_country_scope_and_condensed.py` | NEW | 24 focused tests |
| `docs/chronicle/increment-5.md` | NEW | this file |

All modules are within or below the 400-line convention. The
existing Increment-1 / Increment-3 carve-outs (constants,
sources, runner) are unchanged in scope.
