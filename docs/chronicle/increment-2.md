# Country-Year Chronicle — Increment 2 Implementation Notes

Date: 2026-06-21

Sub-project: **Country-Year Chronicle** (`cyc`)

Scope: implementation notes for Increment 2 (Maddison-backed
economy fields + provenance-aware ruler resolver) per
[`docs/chronicle/workplan.md`](workplan.md)
§7 and the Increment 0/1 findings.

This document records what was shipped, what is deferred, and the
runtime/test wiring. The full Increment 0/1 contract, column
order, and taxonomy decisions remain authoritative in the
Increment 0/1 docs.

## 1. What landed

- **Maddison Project Database 2023 (Stage 2) wired into the
  Chronicle slice.** New module
  `src/leaders_db/chronicle/_maddison_source.py` owns the
  Chronicle-side loader that reads the Stage 2 narrow parquet (or
  the raw xlsx as a fallback) and returns the
  `gdppc` / `pop` / `derived_gdp_total` triple per
  `(iso3, year)`. The Stage 2 adapter itself is in
  `src/leaders_db/ingest/maddison_project*.py` and ships under
  the `maddison_project` key in `STAGE2_ADAPTERS`.

- **Combined Maddison + WDI economy precedence.** New module
  `src/leaders_db/chronicle/_economy_fields.py` replaces the
  WDI-only `_wdi_fields.py` path with the documented Increment
  2 contract:
  - Maddison is preferred for `year <= 2022` when its data is
    present.
  - WDI is preferred for `year >= 2023` (the canonical recent
    source).
  - For `year >= 2023` where WDI has no row, the Maddison 2022
    proxy is used as a final fallback; the row builder attaches
    the `proxy_year_used` flag so the audit trail is explicit.
  - GDP / GDP-per-capita methods are explicit:
    `maddison_direct`, `maddison_direct_proxy`, `wdi_direct`,
    or `derived_gdp_over_population`.

- **Provenance-aware ruler resolver.** New module
  `src/leaders_db/chronicle/ruler_resolver.py` (with a
  `_ruler_loader.py` helper for the raw file readers) loads
  Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009) and
  REIGN 2021-8 (Bell 2016, OEF Research) directly from the local
  data lake. The resolver:
  - picks the Archigos leader whose `start_year <= year <=
    end_year` for `year <= 2015`;
  - picks the REIGN leader with the most months in the
    requested year for `1950 <= year <= 2021`;
  - returns the missing-ruler placeholder when no source
    covers the year;
  - returns missing for `SUN` rows because neither Archigos nor
    REIGN has a separate SUN `ccode` (the merged Russian-
    Empire + USSR + RUS record does not cleanly map to the
    Soviet Union identity);
  - never invents a ruler, never consults the client matrix,
    never calls an LLM (per Always-On Rule #6).

- **Row builder extended** to consume the new sources. The
  public function `build_chronicle_rows` accepts the two new
  keyword arguments `maddison` and `ruler_resolver` (both
  optional, defaults preserve Increment 1 behavior). When the
  resolver is `None` the row builder emits the Increment 1
  placeholder for every row (no ruler columns populated,
  `missing_ruler` flag set).

- **CSV writer** emits the Maddison + Archigos + REIGN
  attribution lines (alphabetical order, byte-identical to
  `docs/source-attributions.md`). Drift guard lives in the
  Maddison Stage 2 test
  `test_maddison_project_attribution_matches_attributions_doc`.

- **Per-source constants module.** New
  `src/leaders_db/chronicle/source_constants.py` owns the
  attribution text, source-tag constants, per-source confidence
  values, COW->ISO3 mapping, and coverage end-years. The
  existing `constants.py` re-exports them for back-compat with
  the older test suite.

- **CLI command unchanged.** The existing
  `leaders-db run-country-year-chronicle` now loads Maddison,
  Archigos, and REIGN automatically (the runner resolves the
  raw-data-lake paths through `leaders_db.paths`). No new CLI
  flags; the source-precedence rules are documented here and
  exercised by the new tests.

## 2. Runtime boundaries

- **Read-only.** No writes to the prototype SQLite catalog,
  no `client_matrix` import, no LLM adapter import.
- **Sources consumed in production:**
  - raw V-Dem CSV at `data/raw/vdem/V-Dem-CY-Full+Others-v16.csv`
    (always read raw because the processed parquet only
    contains 2022);
  - processed WDI parquet at
    `data/processed/world_bank_wdi/wdi_country_year.parquet`;
  - processed SIPRI milex parquet at
    `data/processed/sipri_milex/sipri_milex_country_year.parquet`;
  - Maddison Project: narrow parquet at
    `data/processed/maddison_project/maddison_project_country_year.parquet`,
    falling back to the raw xlsx at
    `data/raw/maddison_project/mpd2023.xlsx`;
  - Archigos raw dta at
    `data/raw/archigos/Archigos_4.1_stata14.dta`;
  - REIGN raw csv at
    `data/raw/reign/REIGN_2021_8.csv`.
- **Output** is one CSV row per requested `(iso3, year)` pair
  regardless of source coverage. Missing fields are empty
  cells; the row carries the appropriate `missing_*` /
  `*_gap` / `proxy_year_used` / `multiple_rulers` flags.
- **Atomic write** through `tempfile` + `os.replace`; no
  partial files in `data/outputs/` after a failed run.
- **Attribution block** is the leading `#` comment lines.
  Each line is a byte-for-byte substring of
  `docs/source-attributions.md` (drift-guarded by the
  Maddison Stage 2 test).

## 3. Maddison source hygiene

- `data/raw/maddison_project/metadata.json` was created
  locally with the canonical SHA-256 of `mpd2023.xlsx`
  (`ecc5916ca12789b983fc4be437f8a354bbf4291323605324ac3e0aea4c57cbb6`).
  The bundle file `mpd2023.xlsx` (4.9 MB) is gitignored per
  Always-On Rule #9 + `docs/local-data-store.md`.
- `STAGE2_ADAPTERS["maddison_project"]` is wired to
  `maddison_project.ingest_maddison_project`; the CLI command
  `leaders-db ingest-source --source maddison_project` runs the
  full orchestrator end-to-end.
- Indicator catalog at
  `src/leaders_db/ingest/catalogs/maddison_project.csv` lists
  the 3 catalog indicators: `gdppc` (2011 international
  dollars), `pop` (thousands), and `__derived_gdp_total__`
  (derived total real GDP = gdppc × pop × 1000).
- 47 focused tests in `tests/test_ingest_maddison_project.py`
  pass. The Stage 2 orchestrator end-to-end produces 21 rows
  from the fixture, and the Year 2023 → 2022 proxy mapping is
  recorded in the run manifest.

## 4. Country-status and regime classifier contract

- **Maddison 2023 → 2022 proxy (year == 2023 only).** When the
  user asks for `year == 2023` and the local WDI has no row
  for that year, the row builder reads the Maddison 2022 row,
  lifts `pop` from thousands to absolute persons (`* 1000`),
  emits the Maddison-derived GDP total when both cells are
  present, and attaches the `proxy_year_used` flag so the
  audit trail is explicit. The unit labels (`2011_intl_dollars`,
  `thousands`, `derived_2011_intl_dollars`) keep the proxy
  provenance visible downstream.

  The proxy is restricted to exactly year == 2023 per the
  Increment 2 reviewer gate: for years 2024 / 2025 / 2026 the
  Maddison 2022 row is **not** silently reused as a multi-year
  stale proxy. When WDI is missing for those years the row is
  left blank with `missing_population` / `missing_gdp` flags
  (no Maddison hit, no per-capita value, no proxy flag). The
  docs and tests explicitly forbid any other multi-year stale
  proxy behavior.

- **Ruler columns populated for the first time.** Archigos
  fills the historical leader names through 2015; REIGN fills
  the recent monthly leader names 1950-2021 (with the most-
  months heuristic). For years both sources cover, Archigos
  wins (it carries the start/end dates so the resolution is
  exact). For years only REIGN covers (2016-2021), REIGN is
  the source. `ruler_type` carries the REIGN `government`
  string when REIGN is the source; `ruler_title` is always
  empty (neither source carries ruler titles).

- **Source-tag-driven provenance.** Per the Increment 2
  reviewer gate, the row's `provenance_summary` derives the
  `wdi=yes` and `maddison=yes` bits from the row's per-field
  source tags (`population_source == "wdi"`, `gdp_source ==
  "maddison_project"`, etc.), NOT from the `has_population or
  has_gdp` booleans. A Maddison-only historical row (e.g. USA
  1920 with no WDI row) reports `wdi=no, maddison=yes`. The
  `row_confidence` aggregate drops the WDI term when
  `wdi_hit=False`, so a Maddison-only 1920 row does not
  silently inherit a WDI confidence weight.

- **SUN remains the documented gap.** Archigos and REIGN both
  use the COW `ccode` scheme; `ccode 364` (Soviet Union) does
  not appear in either source. The merged `ccode 365` record
  covers Russian Empire + USSR + RUS and does not cleanly map
  to the Soviet Union identity, so SUN rows always carry
  `missing_ruler`. A vetted SUN-specific source is the
  Increment 3 / Stage 4 work item.

- **Multiple-rulers flag.** REIGN's per-month granularity
  means some years have more than one leader (e.g. RUS 1991:
  Gorbachev → Yeltsin). The resolver picks the leader with the
  most months and emits the `multiple_rulers` flag. The
  `ruler_confidence` is dropped to
  `REIGN_MULTI_LEADER_CONFIDENCE` (50) for the multi-leader
  years.

- **SQLite artifact.** The command writes a SQLite artifact alongside
  the CSV at
  `<project_root>/data/outputs/country-year-chronicle/pilot.sqlite` by
  default. The schema is a single `country_year_chronicle` table
  (TEXT / INTEGER / REAL columns matching the CSV field names)
  plus a `source_attributions` sidecar table that mirrors
  the attribution block from the CSV comment lines. The CSV
  behavior is unchanged; the SQLite write is atomic (built in a temp
  file under the same directory and renamed via `os.replace`).
  Pass `--sqlite-output <PATH>` to write the SQLite artifact to a
  custom path.

## 5. Test coverage

- 13 tests in `tests/test_chronicle_ruler_resolver.py`:
  direct Archigos hit (USA 1900 / McKinley), direct REIGN hit
  (USA 2000 / Bush), multi-leader REIGN path (RUS 1991 /
  Gorbachev 8 months vs Yeltsin 4 months), modern gap (year
  > 2021), SUN row always returns missing-ruler, empty-frame
  graceful degradation, row-builder integration (data-quality
  flag emission + provenance_summary recording).

- 18 tests in `tests/test_chronicle_economy_fields.py` (was
  9; +9 reviewer-blocker regression tests for the Maddison
  proxy / WDI provenance contract):
  Maddison-only row reports `wdi=no, maddison=yes` (audit
  trail); WDI-only row reports `wdi=yes, maddison=no`;
  Maddison proxy fires for year == 2023 only (year > 2023
  with no WDI leaves the row blank); Maddison proxy does not
  fire for 2025 or 2026; WDI present in 2023 wins over
  Maddison 2022; WDI present in 2024 wins over Maddison 2022;
  Maddison proxy per-capita carries `maddison_direct_proxy`
  method; direct `_provenance` helper unit tests
  (`wdi_hit_from_row`, `maddison_hit_from_row`).

- 6 tests in `tests/test_chronicle_production_wiring.py`
  (NEW; production-wiring proof): end-to-end runner load of
  the real Maddison xlsx fixture + Archigos .dta fixture +
  REIGN csv fixture via the production loader chain;
  `sources_used` includes all three; CSV comment block is
  byte-identical to the canonical `docs/source-attributions.md`
  strings; 3-country x 3-year smoke.

- 13 tests in `tests/test_chronicle_sqlite.py` (NEW;
  SQLite artifact): default path resolution under
  `LEADERSDB_PROJECT_ROOT`; canonical schema with documented
  column types; numeric coercion (INTEGER / REAL / NULL for
  empty cells); `source_attributions` sidecar populated with
  canonical citation strings; unknown-source skip; atomic
  write; CLI integration including default-on and explicit-path
  modes; row-count parity with the CSV companion file.

- 6 attribution drift tests in `tests/test_chronicle_constants.py`
  (NEW; reviewer-blocker regression for the Maddison + REIGN
  attribution text): the canonical Chronicle constants
  (`MADDISON_PROJECT_ATTRIBUTION`, `REIGN_ATTRIBUTION`,
  `ARCHIGOS_ATTRIBUTION`) must each be a byte-identical
  substring of `docs/source-attributions.md`; the CSV writer
  must emit the canonical text in the leading comment block;
  the literal CSV file produced by the runner must contain
  the canonical text.
- 9 tests in `tests/test_chronicle_economy_fields.py`: Maddison
  preferred over WDI for pre-2023, WDI used when Maddison
  absent, WDI preferred for 2023 when present, Maddison proxy
  used for 2023 when WDI missing, missing flags when no
  source has data, Maddison preferred for early historical
  year (1900), `maddison=None` falls back to WDI-only,
  Maddison proxy constants documented, provenance_summary
  records Maddison hit.
- All 124 existing Increment 1 chronicle tests still pass.
- All 47 Maddison Stage 2 tests still pass.

## 6. Known caveats / deferred work

- **Static area source still missing.** Country area and
  controlled-area columns are still empty with
  `controlled_area_not_modeled` + `missing_area` flags. A
  vetted static area source (SimpleMaps, CIA Factbook
  archive, etc.) is the next data-acquisition item.
- **Ruler titles are always empty.** Archigos and REIGN do
  not carry ruler titles (e.g. "President", "Prime
  Minister"). A future Increment 3 work item could combine
  REIGN's `government` string + curated ruler-period mappings
  to surface titles for the well-documented identities.
- **2026 Maddison gap.** Maddison's 2023 release ends at
  2022. For years 2023+, WDI is the canonical recent source.
  When WDI is missing for a year the Maddison 2022 proxy
  fires (with `proxy_year_used`). For years 2024+ the row is
  likely empty unless WDI is re-run for those years.
- **No PWT integration.** Penn World Table 10.01 raw bundle
  is visible locally but the source has no `metadata.json`
  yet. Adding PWT would give a second historical cross-check
  for Maddison's GDP per capita series (1950-2019 once
  staged).
- **No leader survival (PLT) integration.** Leader Survival
  is still blocked on the Demscore H-DATA v5 manual
  email/form gate; raw data is not staged locally.

## 7. CLI usage

```bash
leaders-db run-country-year-chronicle \
  --start-year 1900 \
  --end-year 2026 \
  --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
  --output data/outputs/country-year-chronicle/pilot.csv
```

The Increment 2 run produces 889 rows (7 ISO3 × 127 years).
The end-of-run summary reports `sources_used` =
`archigos, maddison_project, reign, sipri_milex, vdem` when
all raw data is staged locally. WDI is included in the
provenance_summary of rows where its values were used; it is
omitted from `sources_used` only when the local processed
parquet has no rows for the requested year window (the
current local parquet only contains 2022).

The CLI works without the Maddison xlsx, Archigos dta, or
REIGN csv (each missing source is logged as a warning and the
relevant fields become empty). The CLI works without the WDI
processed parquet (the same).

## 8. Module layout

The chronicle package now ships 9 focused modules (after the
Increment 2 split). All are <= 414 lines; `row_builder.py`
sits exactly at the 400-line convention ceiling; the rest are
under it.

| Module | Purpose | Lines |
|---|---|---:|
| `__init__.py` | Public re-exports | 90 |
| `constants.py` | Schema (columns, country metadata, regime / system-type defaults) | 432 |
| `source_constants.py` | Per-source constants (attribution, source tags, confidences, COW mappings) | 162 |
| `sources.py` | VDemSource / WdiSource / SipriSource loaders (+ MaddisonSource re-export) | 414 |
| `_maddison_source.py` | Maddison Project loader + raw xlsx reader | 326 |
| `_economy_fields.py` | Maddison + WDI economy precedence (population / GDP / per-capita) | 286 |
| `_provenance.py` | row_confidence / provenance_summary / assemble_flags | 144 |
| `_flags.py` | flag tuple assembly | 126 |
| `_formatters.py` | coerce_int / coerce_float / safe_int / empty_row_template | 89 |
| `_wdi_fields.py` | Original WDI-only helper (kept for back-compat; superseded by `_economy_fields.py`) | 94 |
| `regime.py` | V-Dem regime bucket derivation | 137 |
| `system_type.py` | Conservative system-type classifier | 120 |
| `csv_writer.py` | Atomic CSV write + attribution block | 154 |
| `runner.py` | CLI seam + path defaults + source-detection | 349 |
| `row_builder.py` | Per-(iso3, year) row composition | 400 |
| `ruler_resolver.py` | Provenance-aware ruler resolver (Archigos + REIGN) | 290 |
| `_ruler_loader.py` | Archigos / REIGN raw-file loaders | 124 |
