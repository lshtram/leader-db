# Country-Year Chronicle — Increment 3 Implementation Notes

Date: 2026-06-21

Sub-project: **Country-Year Chronicle** (`cyc`)

Scope: implementation notes for Increment 3 (SUN rulers via a
curated, Wikipedia-anchored spell list + CShapes 2.0 country-area
source + conservative `controlled_area_km2` fallback) per
[`docs/chronicle/workplan.md`](workplan.md)
§7 and the Increment 0/1/2 findings.

This document records what shipped, what is deferred, and the
runtime/test wiring. The full Increment 0/1/2 contract, column
order, and taxonomy decisions remain authoritative in the
Increment 0/1/2 docs.

## 1. What landed

- **Soviet-leaders curated source for SUN.** New module
  `src/leaders_db/chronicle/_sun_ruler_loader.py` reads the
  curated, versioned CSV at
  `data/raw/soviet_leaders_curated/soviet_leaders.csv` (8 leaders:
  Lenin 1922-12-30 to 1924-01-21, Stalin 1924-01-21 to 1953-03-05,
  Malenkov 1953-03-05 to 1953-09-07, Khrushchev 1953-09-07 to
  1964-10-14, Brezhnev 1964-10-14 to 1982-11-10, Andropov
  1982-11-12 to 1984-02-09, Chernenko 1984-02-13 to 1985-03-10,
  Gorbachev 1985-03-11 to 1991-12-25) plus a new
  `data/raw/soviet_leaders_curated/metadata.json` with the
  Wikipedia anchor URL, citation, and license note. The data is
  derived from Wikipedia's "List of leaders of the Soviet Union"
  page (which itself is a public-domain summary of well-documented
  historical facts; the curated CSV is a project artifact placed
  under `data/raw/`). The new source key is
  `soviet_leaders_curated` and the canonical attribution text
  is recorded in `docs/sources/attributions.md` §1.

- **CShapes 2.0 country-area source.** New module
  `src/leaders_db/chronicle/_area_source.py` reads the raw CSV
  at `data/raw/cshapes/CShapes-2.0.csv` (44.5 MB, SHA-256
  `e78d0b3a40605631f5a136c6155e0dd5290996c59765999e159385fdeaf7b157`,
  gitignored per Always-On Rule #9). The bundle is from ETH Zurich
  ICR ([icr.ethz.ch/data/cshapes/CShapes-2.0.csv](https://icr.ethz.ch/data/cshapes/CShapes-2.0.csv))
  and is licensed under CC BY-NC-SA 4.0. A new
  `data/raw/cshapes/metadata.json` captures the canonical URL,
  checksum, license, and citation (Schvitz et al. 2022). The
  loader narrows the 252-gwcode raw CSV to the pilot ISO3 set
  (USA, GBR, FRA, IND, RUS, SUN, CHN), dispatches the GW 365
  record (Russian Empire + USSR + RUS) to SUN for 1922-1991 and
  RUS for 1991+ via asymmetric containment rules (SUN keeps
  rows whose `gweyear` is in 1922-1991; RUS keeps rows whose
  `gwsyear` is >= 1991 — the latter prevents SUN-era territory
  values from leaking into RUS rows). CShapes coverage ends in
  2019; rows for 2020+ are proxied from the most recent CShapes
  year and tagged with `area_proxy_year_used`.

- **Conservative controlled-area fallback.** The row builder
  populates `controlled_area_km2` with `country_area_km2` when
  country area is available (the conservative "no separately
  modeled dependencies" fallback) and emits two flags:
  `controlled_area_not_modeled` (always; imperial / dependency
  summing remains deferred) and `controlled_area_country_only`
  (on top of `controlled_area_not_modeled`; the controlled-area
  value equals the country territory only / no separately modeled
  dependencies). The `controlled_area_note` field documents the
  fallback in human-readable form.

- **Ruler resolver extended for SUN.** The
  `RulerResolver` class now takes a `sun_frame` field loaded via
  the new `_sun_ruler_loader.load_sun_frame()`. The new
  `_lookup_sun` method intersects each spell's
  `[startdate, enddate]` with `[year-01-01, year-12-31]`, picks
  the leader with the most overlap days, and emits
  `multiple_rulers` when more than one spell overlaps the year.
  Confidence is `SOVIET_LEADERS_DIRECT_CONFIDENCE` (70) for
  single-leader years and `SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE`
  (50) for transition years.

- **Per-source constants extended.** New constants in
  `source_constants.py`:
  - `CSHAPES_ATTRIBUTION`, `CSHAPES_COVERAGE_END_YEAR`
    (2019), `CSHAPES_COVERAGE_START_YEAR` (1886),
    `CSHAPES_GW_TO_ISO3`, `CSHAPES_GW_YEAR_TO_ISO3` (the
    per-year dispatch table), `CSHAPES_DIRECT_CONFIDENCE` (80),
    `CSHAPES_PROXY_CONFIDENCE` (60).
  - `SOVIET_LEADERS_CURATED_ATTRIBUTION`,
    `SOVIET_LEADERS_DIRECT_CONFIDENCE` (70),
    `SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE` (50).
  - `SOURCE_TAG_CSHAPES`, `SOURCE_TAG_SOVIET_LEADERS_CURATED`.

- **Row builder extended.** The `assemble_flags` signature now
  takes `has_area`, `controlled_area_country_only`, and
  `area_proxy_used`. The row builder:
  - Calls the new `_populate_area_fields` helper (returns
    `has_area`, `controlled_area_country_only`,
    `area_proxy_used`).
  - Sets the new `FLAG_AREA_PROXY_YEAR_USED` and
    `FLAG_CONTROLLED_AREA_COUNTRY_ONLY` flags on top of the
    existing `FLAG_CONTROLLED_AREA_NOT_MODELED`.

- **CSV writer + SQLite sidecar updated.** Both attribute maps
  include the new `cshapes` and `soviet_leaders_curated` source
  keys. The CSV comment block carries the canonical attribution
  lines (drift-guarded by new tests in
  `tests/test_chronicle_constants.py`).

- **Provenance-audit contract preserved.** Per-source `*_source`
  tags drive the `provenance_summary` field (e.g.
  `ruler=soviet_leaders_curated`, `area_source=cshapes`). The
  `provenance_summary` format is unchanged; the new source tags
  slot in alongside `archigos` and `reign`.

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
  - REIGN raw csv at `data/raw/reign/REIGN_2021_8.csv`;
  - **NEW** CShapes 2.0 raw csv at
    `data/raw/cshapes/CShapes-2.0.csv`;
  - **NEW** Soviet-leaders curated csv at
    `data/raw/soviet_leaders_curated/soviet_leaders.csv`.
- **Output** is one CSV row per requested `(iso3, year)` pair
  regardless of source coverage. Missing fields are empty cells;
  the row carries the appropriate `missing_*` / `*_gap` /
  `proxy_year_used` / `multiple_rulers` / `area_proxy_year_used`
  / `controlled_area_country_only` flags.
- **Atomic write** through `tempfile` + `os.replace`; no
  partial files in `data/outputs/` after a failed run.
- **Attribution block** is the leading `#` comment lines.
  Each line is a byte-for-byte substring of
  `docs/sources/attributions.md` (drift-guarded by the
  `test_chronicle_constants` test file).

## 3. SUN curated source hygiene

- `data/raw/soviet_leaders_curated/metadata.json` was created
  with the canonical Wikipedia anchor URL, the three supporting
  Wikipedia URLs (List of leaders of the Soviet Union; General
  Secretary of the Communist Party of the Soviet Union; Premier
  of the Soviet Union), the citation, and the verbatim
  attribution text. The CSV is hand-curated and is byte-identical
  to the local raw file.
- `SOURCE_TAG_SOVIET_LEADERS_CURATED` is wired to
  `soviet_leaders_curated`. The CLI command
  `leaders-db run-country-year-chronicle` runs the full
  orchestrator end-to-end and includes the curated source
  automatically.
- The curated CSV is **not gitignored** because it's a small
  hand-curated artifact (8 rows × 7 columns). The raw CShapes
  CSV (44.5 MB) and the Maddison xlsx (4.9 MB) ARE gitignored per
  Always-On Rule #9.

## 4. CShapes source hygiene

- `data/raw/cshapes/CShapes-2.0.csv` was downloaded to the data
  lake from `https://icr.ethz.ch/data/cshapes/CShapes-2.0.csv`
  (44.5 MB, HTTP 200). SHA-256 verified:
  `e78d0b3a40605631f5a136c6155e0dd5290996c59765999e159385fdeaf7b157`.
  The CSV is **gitignored** per Always-On Rule #9 + the
  per-source pattern in `.gitignore`.
- `data/raw/cshapes/metadata.json` was written with the canonical
  download URL, the license (CC BY-NC-SA 4.0), the citation
  (Schvitz et al. 2022, JCR 66(1): 144-61), the checksum, and
  a documentation note about the GW 365 dispatch rule.
- `STAGE2_ADAPTERS` does NOT gain a new entry for CShapes
  (CShapes is not a Stage 2 indicator source; it is a Chronicle
  area source consumed directly by the Chronicle slice). The
  Chronicle-side loader in `src/leaders_db/chronicle/_area_source.py`
  is the production loader.

## 5. Country-status and area source contract

- **CShapes 2.0 → 2019 proxy mapping (year > 2019).** When the
  user asks for `year >= 2020` and the local CShapes has no row
  for that year, the row builder reads the most recent CShapes
  row (currently 2019), copies the area value, and attaches the
  `area_proxy_year_used` flag so the audit trail is explicit.
  The `area_source_year_used` field records the CShapes year
  actually read. This is documented as the only multi-year
  stale-proxy behavior; the reviewer-gate pattern is the same
  as the Maddison 2023 → 2022 1-year-gap proxy.
- **Controlled area is the conservative fallback.** When CShapes
  has a hit, `controlled_area_km2 = country_area_km2` and the
  `controlled_area_country_only` flag is added on top of the
  always-emitted `controlled_area_not_modeled` flag. Imperial
  / dependency summing remains deferred per Increment 4.
- **SUN / RUS dispatch via GW 365.** CShapes 2.0 carries a
  single GW 365 record for the consolidated Russian Empire +
  USSR + Russian Federation. The Chronicle treats SUN
  (1922-1991) and RUS (1991+) as separate identities. The
  dispatch uses asymmetric containment rules:
  - SUN keeps rows whose original `gweyear` is in 1922-1991
    (so the 1921-1945 row, whose 1922-1945 portion is SUN
    territory, qualifies; the 1991-2014 row's territory is
    post-SUN and does not feed SUN).
  - RUS keeps rows whose original `gwsyear >= 1991`
    (preventing SUN-era rows from leaking into RUS).

- **Multiple rulers flag.** REIGN's per-month granularity means
  some years have more than one leader (e.g. RUS 1991: Gorbachev
  → Yeltsin). The resolver picks the leader with the most
  months / days and emits the `multiple_rulers` flag. The
  `ruler_confidence` is dropped to the multi-leader confidence
  for the multi-leader years.
  For SUN, the multi-leader path is the curated source: the
  resolver picks the leader with the most overlap days in
  the requested year. SUN 1924 (Lenin → Stalin), SUN 1953
  (Stalin → Malenkov → Khrushchev), SUN 1985 (Chernenko →
  Gorbachev), and SUN 1984 (Andropov → Chernenko) all emit
  `multiple_rulers`.

- **SQLite artifact.** The command writes a SQLite artifact
  alongside the CSV at
  `<project_root>/data/outputs/country-year-chronicle/pilot.sqlite`
  by default. The schema is a single
  `country_year_chronicle` table (TEXT / INTEGER / REAL columns
  matching the CSV field names) plus a `source_attributions`
  sidecar table that mirrors the attribution block from the
  CSV comment lines. The CSV behavior is unchanged; the
  SQLite write is atomic.

## 6. Test coverage

- **18 tests in `tests/test_chronicle_sun_curated.py`:**
  default path resolution, loader behavior with missing /
  present / mixed curated CSV, SUN ruler resolution for 1922
  (Lenin), 1923 (Lenin), 1924 (Stalin + multiple_rulers), 1925
  (Stalin), 1945 (Stalin), 1953 (Malenkov + multiple_rulers),
  1984 (Chernenko + multiple_rulers due to Andropov→Chernenko
  overlap), 1985 (Gorbachev + multiple_rulers), 1991
  (Gorbachev), out-of-window missing (1921, 1992, 2000),
  missing-curated-CSV fallback, no cross-leak to non-SUN ISO3,
  row builder integration with `multiple_rulers` flag emission,
  ruler_source recording, provenance_summary, and SUN 1992
  missing-ruler.

- **18 tests in `tests/test_chronicle_area_source.py`:**
  default path resolution, constants stability (coverage years,
  GW mapping, dispatch table), loader narrowing to ISO3 scope,
  GW 365 SUN dispatch, GW 365 RUS dispatch (gwsyear >= 1991
  per the asymmetric rule), missing-file empty-frame fallback,
  lookup_area exact match, year-past-coverage proxy, unknown
  ISO3 missing, SUN-specific area (22,066,000 km² from the
  1921-1945 row's overlap), RUS 1991 narrowest-period match,
  row builder populates country_area from CShapes, conservative
  controlled-area fallback (controlled == country, both
  `controlled_area_not_modeled` and `controlled_area_country_only`
  flags), area-proxy flag for post-coverage years, placeholder
  when CShapes missing, SUN row populated from GW 365, no
  country-only flag when country area missing, and CShapes
  direct confidence constant.

- **6 new attribution drift tests in
  `tests/test_chronicle_constants.py`:**
  - `test_cshapes_chronicle_attribution_matches_attributions_doc`
  - `test_soviet_leaders_curated_attribution_matches_attributions_doc`
  - `test_build_attribution_block_emits_cshapes_line`
  - `test_build_attribution_block_emits_soviet_leaders_curated_line`
  - `test_write_chronicle_csv_emits_cshapes_line_in_file`
  - `test_write_chronicle_csv_emits_soviet_leaders_curated_line_in_file`
  - `test_cshapes_source_tag_constant_value`
  - `test_soviet_leaders_curated_source_tag_constant_value`
  - `test_flag_constants_match_increment3_spec`

- **3 new production-wiring tests in
  `tests/test_chronicle_production_wiring.py`:**
  - `test_runner_reports_cshapes_in_sources_used`
  - `test_runner_reports_soviet_leaders_curated_for_sun_rows`
  - `test_runner_combined_run_reports_all_seven_sources`

- **All 124 Increment 1 chronicle tests still pass.**
- **All 88 Increment 2 reviewer-gate tests still pass.**
- **All 47 Maddison Stage 2 tests still pass.**
- **Full suite green at 1757 passing (was 1709 at Increment 2
  sign-off; +48 net new tests).**

## 7. Known caveats / deferred work

- **Imperial / controlled area summing is deferred.** The
  conservative fallback (`controlled_area_km2 =
  country_area_km2`) is the production behavior for the
  Increment 3 pilot. The canonical dependency-controller
  source for the historical colonial period (ICOW Colonial
  History data v1.1) is documented in
  [`docs/sources/vetting/report.md`](../sources/vetting/report.md)
  but its download URL (`http://www.paulhensel.org/icowcol/Data/colhist.zip`)
  returned HTTP 404 on 2026-06-21 (the site has been reorganized
  to `data.icow.org/icowcol/` and the canonical redirect
  target is broken). Adding ICOW is the Increment 4 work item.
- **CShapes 2.0 only goes through 2019.** Year 2020+ rows use
  the CShapes 2019 area as a proxy with `area_proxy_year_used`.
  A current-year area source (CIA World Factbook, V-Dem area
  variables) is a future iteration if needed.
- **SUN curated source covers only the de facto leader.**
  Premier / Chairman of the Presidium are documented in
  `ruler_title` and `office` columns of the curated CSV but the
  row builder populates only `ruler_name` and `ruler_title` per
  the Increment 1 CSV contract. Surfacing full Soviet leadership
  roles (every Politburo member, every Presidium chairman) is
  a future iteration.
- **SUN is at the CShapes 1922-12-30 inception.** The SUN
  identity began with the USSR formation on 1922-12-30. SUN
  1922 carries Lenin (who was the head of government before
  the USSR formal founding and continued through 1924-01-21).
  The curated source uses the SUN inception date as the start
  of Lenin's SUN-era spell.
- **Russian SFSR / Russian Federation overlap in 1991.** RUS
  COUNTRY_METADATA has `start_year=1991`; SUN has
  `end_year=1991`. Both dispatch from GW 365; both pick up the
  1991-1991 row (16,882,600 km²). This is documented in the
  source constants comment and the test suite verifies the
  dispatcher behavior.

## 8. CLI usage

```bash
leaders-db run-country-year-chronicle \
  --start-year 1900 \
  --end-year 2026 \
  --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
  --output data/outputs/country-year-chronicle/pilot.csv
```

The Increment 3 run produces 889 rows (7 ISO3 × 127 years) and
reports:

```
sources_used: archigos, cshapes, maddison_project, reign,
              sipri_milex, soviet_leaders_curated, vdem
```

End-of-run coverage counts (see
`docs/chronicle/increment-3.md` for the
reproducible Python snippet):

- Total rows: 889.
- SUN rows: 127 total; 70 in-window (1922-1991) carry a real
  ruler name; 0 in-window SUN rows are blank.
- 645 of 645 in-window rows carry a real `country_area_km2`
  value.
- 645 of 645 in-window rows carry the conservative
  `controlled_area_km2` fallback value.
- 49 rows past CShapes coverage (2020+) carry the
  `area_proxy_year_used` flag.
- 749 rows carry the `controlled_area_country_only` flag (one
  per CShapes hit, including proxy years).

## 9. Module layout

The chronicle package now ships 25 focused modules (after the
Increment 3 reviewer-gate follow-up that split the 500-line
`row_builder.py` into focused sibling modules). The following
modules are carved out from the 400-line convention for justified
reasons and are explicitly documented below:

- `constants.py` (476 lines), which is a long static constants table
  for schema / column metadata.
- `sources.py` (414 lines), a legacy facade over source-class adapters
  and re-exports.
- `runner.py` (421 lines), the composition/CLI-seam boundary orchestrator
  that wires source loaders, default paths, and output selection.
- `ruler_resolver.py` (402 lines), a stable resolver surface with the
  full Archigos / REIGN / SUN lookup table and curated helper.

| Module | Purpose | Lines |
|---|---:|---:|
| `__init__.py` | Public re-exports | 117 |
| `constants.py` | Schema (columns, country metadata, regime / system-type defaults) — **carve-out (476 lines)** per Increment 1 | 476 |
| `source_constants.py` | Per-source constants (attribution, source tags, confidences, GW mappings) | 304 |
| `sources.py` | VDemSource / WdiSource / SipriSource loaders (+ MaddisonSource re-export) — **carve-out (414 lines)**: source facade + imports not split to keep module-level compatibility | 414 |
| `_maddison_source.py` | Maddison Project loader + raw xlsx reader | 327 |
| `_economy_fields.py` | Maddison + WDI economy precedence (population / GDP / per-capita) | 354 |
| `_provenance.py` | row_confidence / provenance_summary / assemble_flags | 198 |
| `_flags.py` | flag tuple assembly | 154 |
| `_formatters.py` | coerce_int / coerce_float / safe_int / empty_row_template | 89 |
| `_wdi_fields.py` | Original WDI-only helper (kept for back-compat; superseded by `_economy_fields.py`) | 94 |
| `_sun_ruler_loader.py` | SUN curated-leaders raw-file loader | 90 |
| `_area_source.py` | CShapes 2.0 country-area loader + GW dispatch | 291 |
| `regime.py` | V-Dem regime bucket derivation | 137 |
| `system_type.py` | Conservative system-type classifier | 120 |
| `csv_writer.py` | Atomic CSV write + attribution block | 177 |
| `runner.py` | CLI seam + path defaults + source-detection — **carve-out (421 lines)**: composition boundary for command wiring / defaults | 421 |
| `row_builder.py` | Per-(iso3, year) row composition | 309 |
| `ruler_resolver.py` | Provenance-aware ruler resolver (Archigos + REIGN + SUN curated) — **carve-out (402 lines)**: stable resolver surface with 2-line overage | 402 |
| `_ruler_loader.py` | Archigos / REIGN raw-file loaders | 125 |
| `sqlite_writer.py` | SQLite export + source_attributions sidecar | 306 |
| `_row_identity.py` | year / iso3 / country / status columns (`populate_identity`, `derive_country_status`) — **NEW (reviewer-gate follow-up)** | 67 |
| `_row_ruler.py` | Ruler-column population (`populate_ruler_placeholder`, `populate_ruler_fields`) — **NEW (reviewer-gate follow-up)** | 83 |
| `_row_regime.py` | Political-regime + system-type columns (`populate_regime`, `populate_system_type`) — **NEW (reviewer-gate follow-up)** | 47 |
| `_row_sipri.py` | SIPRI military-spend columns (`populate_sipri_fields`) — **NEW (reviewer-gate follow-up)** | 54 |
| `_row_area.py` | Area / controlled-area columns (`populate_area_placeholders`, `populate_area_fields`) — **NEW (reviewer-gate follow-up)** | 109 |

Notes on the carve-outs:

- `constants.py` (476 lines) is the long-table / schema constants
  file that was already an explicit Increment-1 carve-out from the
  400-line convention (see `increment-1.md`
  §128).
- `sources.py` (414 lines) is the legacy source facade that intentionally
  centralizes source class imports (`VDemSource`, `WdiSource`, `SipriSource`,
  and `MaddisonSource` re-export). If it grows above **440 lines** again,
  a follow-up split into `sources_*.py` helper modules is accepted.
- `runner.py` (421 lines) remains the composition boundary between CLI
  entrypoint and runtime orchestration (path discovery, source detection,
  output naming). If it grows above **440 lines**, split out source
  wiring helpers as a follow-up.
- `ruler_resolver.py` (402 lines) carries the resolver's full lookup
  table for three sources (Archigos + REIGN + SUN curated) plus the
  curated lookup helper. The 2-line overage is below the threshold that
  warrants another split; the public surface (`RulerResolver.resolve`,
  `RulerResult.missing`, `load_ruler_resolver`) is stable.

The reviewer-gate follow-up split preserved all public import
paths (`leaders_db.chronicle.row_builder.build_chronicle_rows` is
the unchanged public entry point) and all test imports
(`tests/test_chronicle_*` import `build_chronicle_rows` only).
